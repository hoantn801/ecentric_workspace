// Trung tam Du lieu - ec_data_hub.bundle.js tren HTML THAT (fixture render tu data_hub/service.py + jinja,
// xem test_data_hub.TestFixtures). API gia tra du lieu that cua bo mau (fixtures/api.json).
//     node ecentric_workspace/data_hub/tests/js/test_ec_data_hub.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
const FIX = join(here, "fixtures");
const BUNDLE = readFileSync(join(APP, "public", "js", "ec_data_hub.bundle.js"), "utf8");
const CSS = readFileSync(join(APP, "public", "css", "ec_data_hub.bundle.css"), "utf8");
const API = JSON.parse(readFileSync(join(FIX, "api.json"), "utf8"));
const C = API.codes;
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const eq = (a, b, n) => ok(JSON.stringify(a) === JSON.stringify(b), n + " -> " + JSON.stringify(a) + " != " + JSON.stringify(b));
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setTimeout(r, 2)); };

async function page(name, { me = "thu.nguyen@ecentric.vn", url = "https://team.ecentric.vn/du-lieu", bootPatch = null, failOn = {} } = {}) {
  let html = readFileSync(join(FIX, name + ".html"), "utf8");
  if (bootPatch) {
    html = html.replace(/(<script type="application\/json" id="edh-boot">)([\s\S]*?)(<\/script>)/, (m, a, b, c) => {
      const boot = JSON.parse(b); bootPatch(boot); return a + JSON.stringify(boot).replace(/</g, "\\u003c") + c;
    });
  }
  const dom = new JSDOM(html, { url, runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  const calls = [];
  w.__edhNoReload = true;
  w.frappe = { csrf_token: "tok" };
  w.fetch = (u, opts = {}) => {
    const method = u.split("data_hub.api.")[1].split("?")[0];
    let args = {};
    if (opts.method === "POST") args = JSON.parse(opts.body || "{}");
    else new URL(u, "https://x").searchParams.forEach((v, k) => { args[k] = v; });
    calls.push({ method, args, post: opts.method === "POST", csrf: (opts.headers || {})["X-Frappe-CSRF-Token"] });
    let data = null, success = true, message = "";
    if (failOn[method]) { success = false; message = failOn[method]; }
    else if (method === "get_ticket") data = (API.details[args.code] || {})[me];
    else if (method === "gantt") data = args.start ? API.gantt_next : API.gantt;
    else if (method === "create") data = { code: "DR-2026-0011" };
    else if (method === "preview_due") data = API.preview[args.code];
    else if (method === "accept") data = { status: "Đang xử lý", due: args.due_date, pm_task: "TASK-2026-00099", warning: "" };
    else if (method === "update") data = { changes: ["hạn"], warnings: [], status: "Đang xử lý" };
    else if (method === "people") data = API.people;
    else data = {};
    return Promise.resolve({ ok: success, status: success ? 200 : 417, json: () => Promise.resolve({ message: { success, message, data } }) });
  };
  w.eval(BUNDLE);
  await flush();   // jsdom: DOMContentLoaded chay sau khi tao -> bundle gan su kien luc do
  return { dom, w, d: w.document, calls, H: w.ECDataHub };
}

// ------------------------------------------------------------------ ham thuan ------------
{
  const { H, d } = await page("index_user");
  const boot = JSON.parse(d.getElementById("edh-boot").textContent);
  const server = boot.rows.map((r) => r.code);
  const shuffled = boot.rows.slice().reverse();
  eq(H.sortRows(shuffled).map((r) => r.code), server, "JS sap xep GIONG server (Khan -> qua han -> han gan; dong cuoi)");
  eq(server[0], C.voucher, "Khan de xuat len dau");
  const row = { scope: "open", type: "Crawl data mới", team: "Commercial", mine: "1", search: "dr-2026-0007 crawl voucher thu nguyễn", code: "DR-2026-0007" };
  ok(H.filterMatch(row, { scope: "open", q: "voucher" }), "loc: tim theo tieu de");
  ok(!H.filterMatch(row, { scope: "done" }), "loc: Da xong loai dong dang mo");
  ok(!H.filterMatch(row, { scope: "all", team: "Service" }), "loc: team");
  ok(H.filterMatch(row, { scope: "all", mine: true }) && !H.filterMatch(Object.assign({}, row, { mine: "0" }), { mine: true, scope: "all" }), "loc: chi cua toi");
  eq(H.slaDays(boot.type_hints, "Power BI mới", "Cao"), 6, "SLA hint 7 x 0.8 lam tron len");
  eq(H.slaDays(boot.type_hints, "Xử lý dữ liệu", "Khẩn"), 2, "SLA hint 3 x 0.5 = 2");
  eq(H.slaDays(boot.type_hints, "", "Cao"), null, "chua chon loai -> khong co hint");
  eq(H.mentionsIn("Nhờ @Linh Vương xem", [{ user: "linh", name: "Linh Vương" }, { user: "hoan", name: "Hoàn Trần" }]), ["linh"], "@ten con trong noi dung moi tinh");
  ok(H.linkify('<b>x</b> https://a.vn/x?y=1 @Linh', [{ name: "Linh" }]).indexOf("&lt;b&gt;") === 0, "linkify escape HTML");
  ok(H.linkify("xem https://a.vn/x").indexOf('href="https://a.vn/x"') > 0, "linkify tao link");
  ok(H.linkify("javascript:alert(1)").indexOf("<a") < 0, "khong linkify javascript:");

  // moi popup cua bo mau (moi vai) ve sach: khong "[object", "undefined", "null", "NaN"
  let dirty = [];
  for (const code of Object.keys(API.details)) for (const u of Object.keys(API.details[code])) {
    const h = H.renderDetail(API.details[code][u], u);
    if (/\[object|undefined|>null<|NaN/.test(h)) dirty.push(code + "/" + u);
  }
  eq(dirty, [], "popup ve sach cho moi yeu cau / vai");

  // Gantt layout
  const L = H.ganttLayout(API.gantt);
  eq(L.n, 21, "Gantt 21 ngay");
  eq(L.todayIdx, 7, "hom nay 09/11 = cot 8 (bat dau thu Hai 02/11)");
  const linh = L.lanes.find((l) => l.key === "linh.vuong@ecentric.vn");
  const pnl = linh.bars.find((b) => b.code === C.pnl);
  // pnl: bat dau 29/10 (truoc cua so -> cat), qua han: keo toi hom nay 09/11
  ok(pnl.clipL && pnl.leftPct === 0, "thanh bat dau truoc cua so bi cat trai");
  ok(Math.abs(pnl.widthPct - 8 / 21 * 100) < 1e-9, "thanh qua han keo toi hom nay (02/11..09/11 = 8 cot)");
  ok(pnl.css === "late" && pnl.lateLeftPct !== null, "phan qua han to rieng");
  ok(pnl.extLeftPct !== null && pnl.extLeftPct > 0, "phan da doi han (03/11 -> 06/11) gach cheo");
  eq(pnl.top, 6, "thanh dau o top 6");
  const rating = linh.bars.find((b) => b.code === C.rating);
  eq(Math.round(rating.leftPct * 21 / 100), 2, "rating bat dau 04/11 = cot 3");
  ok(linh.height >= 58, "hang toi thieu 58px");
  const none = L.lanes.find((l) => l.key === "__none");
  eq(none.bars.length, 3, "3 yeu cau cho nhan o hang Chua phan cong");
  eq(L.lanes[L.lanes.length - 1].key, "__done", "hang Da xong o cuoi");
}

// ------------------------------------------------------------------ trang nhan vien -------
{
  const { w, d, calls } = await page("index_user");
  const rows = () => [...d.querySelectorAll("[data-edh-rows] tr")];
  const visible = () => rows().filter((r) => !r.hidden).map((r) => r.dataset.code);
  eq(visible().length, 8, "mac dinh Dang mo: 8 dong (server ve san)");
  ok(!d.querySelector("[data-edh-accept-ov]"), "nhan vien: khong co hop Nhan viec");
  ok(![...d.querySelectorAll(".edh-tab")].some((a) => a.textContent === "Điều phối"), "nhan vien: khong co tab Dieu phoi");
  const scope = d.querySelector('[data-edh-f="scope"]');
  scope.value = "all"; scope.dispatchEvent(new w.Event("change"));
  eq(visible().length, 10, "Tat ca: 10 dong");
  scope.value = "done"; scope.dispatchEvent(new w.Event("change"));
  eq(visible(), [C.stock], "Da xong: chi dong Hoan tat");
  const q = d.querySelector('[data-edh-f="q"]');
  q.value = "khong-co-gi"; q.dispatchEvent(new w.Event("input"));
  ok(!d.querySelector("[data-edh-empty]").hidden, "khong khop -> trang thai rong");
  q.value = ""; q.dispatchEvent(new w.Event("input"));
  scope.value = "open"; scope.dispatchEvent(new w.Event("change"));
  const mine = d.querySelector('[data-edh-f="mine"]');
  mine.checked = true; mine.dispatchEvent(new w.Event("change"));
  eq(visible().sort(), [C.voucher, C.pnl, C.live].sort(), "Chi cua toi (Thu gui 3 yeu cau dang mo)");
  mine.checked = false; mine.dispatchEvent(new w.Event("change"));
  const team = d.querySelector('[data-edh-f="team"]');
  team.value = "Service"; team.dispatchEvent(new w.Event("change"));
  ok(visible().every((c) => [C.misa, C.aff, C.clean, C.tiktok].includes(c)) && visible().length === 4, "loc team Service");
  team.value = ""; team.dispatchEvent(new w.Event("change"));

  // popup: bam dong -> GIUA man hinh, URL ?ma=, Esc dong, tra focus
  const tr = rows().find((r) => r.dataset.code === C.pnl);
  tr.focus();
  tr.click();
  const ov = d.querySelector("[data-edh-detail-ov]");
  ok(!ov.hidden, "bam dong -> popup mo");
  ok(ov.classList.contains("edh-ov-center"), "popup giua man hinh (giong /pm)");
  ok(d.querySelector(".edh-dm-loading"), "dang tai -> co trang thai loading");
  await flush();
  eq(calls.filter((c) => c.method === "get_ticket").length, 1, "goi get_ticket 1 lan");
  ok(w.location.search.indexOf("ma=" + C.pnl) >= 0, "URL ?ma= de chia se link");
  const box = d.querySelector("[data-edh-detail]");
  ok(box.querySelector(".edh-dm-title").textContent.indexOf("Friso") > 0, "popup ve tieu de");
  ok(box.querySelector(".edh-dm-info") && box.querySelector(".edh-dm-chat"), "2 card: thong tin + trao doi");
  ok(box.textContent.indexOf("06/11/2026") >= 0 && box.querySelector(".edh-summary s").textContent === "03/11/2026", "han moi + gach han cu");
  ok(box.textContent.indexOf("đã dời 1 lần") >= 0, "so lan doi han");
  ok(!box.querySelector("[data-edh-edit]"), "nhan vien khong co o Cap nhat cua team Data");
  ok(box.querySelector("[data-edh-compose]"), "nguoi gui nhan tin duoc");
  ok(box.textContent.indexOf("Chờ brand gửi file mapping SKU") >= 0, "tien do co ly do doi han");
  ok(box.querySelector('a[href^="/pm#task/TASK-"]'), "link task /pm");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  ok(ov.hidden, "Esc dong popup");
  ok(w.location.search.indexOf("ma=") < 0, "dong popup -> bo ?ma=");
  ok(d.activeElement === tr, "tra focus ve dong da mo");

  // phim Enter tren dong
  const tr2 = rows().find((r) => r.dataset.code === C.voucher);
  tr2.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await flush();
  ok(!ov.hidden && d.querySelector("[data-edh-detail] .edh-banner.is-info").textContent.indexOf("vị trí 1") >= 0, "Enter mo popup; vi tri hang doi");
  ok(d.querySelector("details.edh-cancel"), "nguoi gui huy duoc khi Cho tiep nhan");
  ov.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  ok(ov.hidden, "bam nen toi -> dong");

  // nhan tin: @ten, gui 1 lan
  tr.click(); await flush();
  const ta = d.querySelector("#edh-msg");
  ta.value = "Nhờ @Li"; ta.selectionStart = ta.selectionEnd = ta.value.length;
  ta.dispatchEvent(new w.Event("input"));
  const menu = d.querySelector(".edh-at-menu");
  ok(menu && menu.textContent.indexOf("Linh Vương") >= 0, "go @ -> goi y nguoi lien quan");
  menu.querySelector("li").dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true }));
  ok(ta.value.indexOf("@Linh Vương ") >= 0, "chon goi y -> chen @Ten");
  ta.value += "xem giúp";
  const send = d.querySelector("[data-edh-send]");
  d.querySelector("[data-edh-compose]").dispatchEvent(new w.Event("submit", { cancelable: true }));
  d.querySelector("[data-edh-compose]").dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  const sends = calls.filter((c) => c.method === "send_message");
  eq(sends.length, 1, "chong gui 2 lan");
  eq(JSON.parse(sends[0].args.mentions), ["linh.vuong@ecentric.vn"], "gui kem @mention");
  ok(sends[0].post && sends[0].csrf === "tok", "POST kem CSRF");
  ok(send, "co nut gui");
}

// ------------------------------------------------------------------ tao yeu cau -----------
{
  const { w, d, calls } = await page("index_user");
  const btn = d.querySelector("[data-edh-new]");
  btn.click();
  const ov = d.querySelector("[data-edh-new-ov]");
  ok(!ov.hidden, "mo form tao");
  ok(d.activeElement === d.querySelector("#edh-new-type"), "focus vao o dau");
  const f = d.querySelector("[data-edh-new-form]");
  const hint = d.querySelector("[data-edh-sla-hint]");
  ok(hint.textContent.indexOf("Chọn loại") === 0, "chua chon loai -> huong dan");
  f.elements.request_type.value = "Power BI mới"; f.elements.request_type.dispatchEvent(new w.Event("change"));
  ok(hint.textContent.indexOf("7 ngày làm việc") > 0, "Power BI moi: 7 ngay");
  f.elements.proposed_priority.value = "Cao"; f.elements.proposed_priority.dispatchEvent(new w.Event("change"));
  ok(hint.textContent.indexOf("6 ngày làm việc") > 0, "Cao: 6 ngay (x0.8 lam tron len)");
  ok(d.querySelector("[data-edh-urgent-box]").hidden, "khong Khan -> an o ly do");
  f.elements.proposed_priority.value = "Khẩn"; f.elements.proposed_priority.dispatchEvent(new w.Event("change"));
  ok(!d.querySelector("[data-edh-urgent-box]").hidden, "Khan -> hien o ly do");
  ok(hint.textContent.indexOf("4 ngày") > 0 && hint.textContent.indexOf("nếu team Data xác nhận") > 0, "Khan: 4 ngay, neu xac nhan");
  f.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  const err = d.querySelector("[data-edh-new-err]");
  ok(!err.hidden && err.textContent.indexOf("Chưa có tiêu đề") >= 0 && err.textContent.indexOf("lý do") >= 0, "kiem truoc khi gui");
  eq(calls.filter((c) => c.method === "create").length, 0, "loi -> khong goi API");
  f.elements.title.value = "Dashboard voucher";
  f.elements.description.value = "Theo ngày";
  f.elements.urgent_reason.value = "BOD thứ Năm";
  f.dispatchEvent(new w.Event("submit", { cancelable: true }));
  f.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  const cr = calls.filter((c) => c.method === "create");
  eq(cr.length, 1, "chong bam 2 lan");
  const data = JSON.parse(cr[0].args.data);
  eq([data.request_type, data.proposed_priority, data.urgent_reason, data.files], ["Power BI mới", "Khẩn", "BOD thứ Năm", []], "du lieu gui");
  eq(w.__edhReloaded, "?ma=DR-2026-0011", "gui xong -> tai lai mo popup yeu cau moi");
  ok(ov.hidden, "dong form");
  btn.click();
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  ok(ov.hidden, "Esc dong form tao");
}

// ------------------------------------------------------------------ loi API than thien -----
{
  const { w, d } = await page("index_user", { failOn: { get_ticket: "Không tìm thấy yêu cầu này." } });
  d.querySelector("[data-edh-rows] tr").click();
  await flush();
  ok(d.querySelector(".edh-dm-loading.is-err").textContent.indexOf("Không tìm thấy") >= 0, "loi -> thong diep tieng Viet trong popup");
}

// ------------------------------------------------------------------ deep link -------------
{
  const code = C.aff;
  const { w, d, calls } = await page("index_user", { me: "hien.nguyen@ecentric.vn", url: "https://team.ecentric.vn/du-lieu?ma=" + code,
    bootPatch: (b) => { b.open = API.details[code]["hien.nguyen@ecentric.vn"]; b.me = "hien.nguyen@ecentric.vn"; } });
  const ov = d.querySelector("[data-edh-detail-ov]");
  ov.hidden = false; // server ve san khi co ?ma= (fixture render khong co ma)
  ok(d.querySelector(".edh-dm-title"), "?ma= -> popup ve ngay tu du lieu nhung san");
  eq(calls.length, 0, "deep link khong goi API");
  const okBtn = d.querySelector("[data-edh-ok]");
  ok(okBtn && d.querySelector("[data-edh-nok]"), "nguoi gui thay Dat / Chua dat");
  d.querySelector("[data-edh-nok]").click();
  ok(!d.querySelector("[data-edh-nok-box]").hidden, "Chua dat -> hien o ly do");
  d.querySelector("[data-edh-nok-send]").click();
  await flush();
  eq(calls.filter((c) => c.method === "respond").length, 0, "Chua dat khong ly do -> khong gui");
  d.querySelector("#edh-nok-r").value = "Thiếu cột GMV";
  d.querySelector("[data-edh-nok-send]").click();
  await flush();
  const r = calls.filter((c) => c.method === "respond");
  eq([r.length, r[0] && r[0].args.verdict, r[0] && r[0].args.reason], [1, "Chưa đạt", "Thiếu cột GMV"], "gui Chua dat + ly do");
}

// ------------------------------------------------------------------ Gantt -----------------
{
  const { w, d, calls } = await page("index_user");
  d.querySelector('[data-edh-view="gantt"]').click();
  ok(!d.querySelector("[data-edh-gantt]").hidden && d.querySelector("[data-edh-list]").hidden, "bat Gantt");
  ok(w.location.search.indexOf("xem=gantt") >= 0, "URL ?xem=gantt");
  await flush();
  const bars = d.querySelectorAll("[data-edh-bar]");
  const n = API.gantt.lanes.reduce((s, l) => s + l.bars.length, 0);
  eq(bars.length, n, "ve du thanh");
  ok(d.querySelector(".edh-g-today"), "duong hom nay");
  eq(d.querySelectorAll(".edh-g-days .is-off").length, API.gantt.days.filter((x) => x.off).length, "ngay nghi to xam");
  ok(d.querySelector('[data-edh-bar="' + C.pnl + '"] .edh-bar-ext'), "phan doi han gach cheo");
  ok(d.querySelector(".edh-g-who").textContent.indexOf("yêu cầu") > 0, "canh ten: so yeu cau");
  d.querySelector('[data-edh-bar="' + C.rating + '"]').click();
  await flush();
  ok(!d.querySelector("[data-edh-detail-ov]").hidden, "bam thanh -> popup");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  d.querySelector('[data-edh-g-shift="7"]').click();
  await flush();
  const g = calls.filter((c) => c.method === "gantt");
  eq(g.map((c) => c.args.start || ""), ["", "2026-11-09"], "tuan sau -> start +7");
  d.querySelector('[data-edh-view="list"]').click();
  ok(d.querySelector("[data-edh-gantt]").hidden && w.location.search.indexOf("xem=") < 0, "ve Danh sach");
}

// ------------------------------------------------------------------ team Data -------------
{
  const me = "linh.vuong@ecentric.vn";
  const { w, d, calls } = await page("index_team", { me });
  ok(d.querySelector("[data-edh-accept-ov]"), "team Data co hop Nhan viec");
  ok([...d.querySelectorAll(".edh-tab")].some((a) => a.textContent === "Điều phối"), "team Data thay tab Dieu phoi");
  // dang xu ly -> o Cap nhat; doi han bat buoc ly do
  [...d.querySelectorAll("[data-edh-rows] tr")].find((r) => r.dataset.code === C.rating).click();
  await flush();
  const edit = d.querySelector("[data-edh-edit]");
  ok(edit, "team Data thay o Cap nhat");
  ok(d.querySelector("[data-edh-detail] .edh-summary").textContent.indexOf("[object") < 0, "khong in object ra man hinh");
  eq([...edit.elements.assignee.options].map((o) => o.textContent), ["Dũng Phạm", "Hoàn Trần", "Linh Vương"], "o nguoi xu ly = team Data");
  eq([...edit.elements.status.options].map((o) => o.textContent), ["Đang xử lý", "Tạm dừng – chờ người gửi", "Chờ nghiệm thu"], "trang thai team Data dat duoc");
  ok(d.querySelector("[data-edh-e-reason-box]").hidden, "chua doi han -> an ly do");
  edit.elements.due_date.value = "2026-11-20"; edit.elements.due_date.dispatchEvent(new w.Event("change"));
  ok(!d.querySelector("[data-edh-e-reason-box]").hidden, "doi han -> hien ly do");
  edit.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  ok(!d.querySelector("[data-edh-e-err]").hidden, "doi han khong ly do -> chan");
  eq(calls.filter((c) => c.method === "update").length, 0, "khong goi update");
  edit.elements.reason.value = "Lazada đổi API";
  edit.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  const up = calls.filter((c) => c.method === "update");
  eq(up.length, 1, "goi update");
  eq(JSON.parse(up[0].args.data).due_date, "2026-11-20", "gui han moi");
  ok(w.__edhReloaded.indexOf("ma=" + C.rating) >= 0, "luu xong -> tai lai giu popup");

  // cho tiep nhan -> Nhan viec
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  [...d.querySelectorAll("[data-edh-rows] tr")].find((r) => r.dataset.code === C.voucher).click();
  await flush();
  const accBtn = d.querySelector("[data-edh-detail] [data-edh-accept]");
  ok(accBtn, "Cho tiep nhan: nut Nhan viec");
  accBtn.click();
  const aov = d.querySelector("[data-edh-accept-ov]");
  ok(!aov.hidden, "mo hop Nhan viec tren popup");
  const af = d.querySelector("[data-edh-accept-form]");
  eq([af.elements.assignee.value, af.elements.priority.value, af.elements.start_date.value, af.elements.due_date.value],
    [me, "Khẩn", "2026-11-09", "2026-11-13"], "mac dinh: minh, Khan de xuat, hom nay, han theo quy tac");
  ok(!d.querySelector("[data-edh-acc-urgent]").hidden, "hien ly do Khan de xac nhan / ha muc");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  ok(aov.hidden && !d.querySelector("[data-edh-detail-ov]").hidden, "Esc dong hop tren cung truoc");
  accBtn.click();
  af.elements.start_date.value = "2026-11-10"; af.elements.start_date.dispatchEvent(new w.Event("change"));
  await flush();
  eq(af.elements.due_date.value, API.preview[C.voucher].due, "doi ngay bat dau -> hoi lai han theo quy tac");
  af.elements.due_date.value = "2026-11-25"; af.elements.due_date.dispatchEvent(new w.Event("change"));
  ok(!d.querySelector("[data-edh-acc-reason-box]").hidden, "han khac quy tac -> bat buoc ly do");
  af.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  eq(calls.filter((c) => c.method === "accept").length, 0, "thieu ly do -> khong gui");
  af.elements.reason.value = "Chờ API Shopee";
  af.dispatchEvent(new w.Event("submit", { cancelable: true }));
  af.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  const acc = calls.filter((c) => c.method === "accept");
  eq(acc.length, 1, "Nhan viec 1 lan");
  eq([acc[0].args.code, acc[0].args.due_date, acc[0].args.reason, acc[0].args.priority], [C.voucher, "2026-11-25", "Chờ API Shopee", "Khẩn"], "du lieu Nhan viec");
}

// ------------------------------------------------------------------ Dieu phoi -------------
{
  const { w, d, calls } = await page("ops_team", { me: "linh.vuong@ecentric.vn", url: "https://team.ecentric.vn/du-lieu/dieu-phoi" });
  eq(d.querySelectorAll(".edh-col").length, 4, "kanban 4 cot");
  const first = d.querySelector(".edh-col .edh-kc");
  eq(first.dataset.code, C.voucher, "Khan dau cot Cho tiep nhan");
  first.querySelector("[data-edh-accept]").click();
  const af = d.querySelector("[data-edh-accept-form]");
  ok(!d.querySelector("[data-edh-accept-ov]").hidden, "Nhan tu kanban");
  eq(af.elements.assignee.options.length, 4, "chon nguoi trong team Data (+ dong trong)");
  eq(af.elements.due_date.value, "2026-11-13", "han mac dinh tu boot");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  d.querySelector("[data-edh-resume]").click();
  await flush();
  eq(calls.filter((c) => c.method === "resume").map((c) => c.args.code), [C.live], "Tiep tuc viec tam dung");
  d.querySelector("[data-edh-open]").click();
  await flush();
  ok(!d.querySelector("[data-edh-detail-ov]").hidden, "bam the -> popup");
}

// ------------------------------------------------------------------ mobile 390px (CSS) -----
{
  ok(/@media \(max-width:640px\)\{[^@]*\.edh-kanban\{display:flex;overflow-x:auto/.test(CSS), "390px: kanban vuot ngang");
  ok(/@media \(max-width:640px\)\{[^@]*\.edh-tbl thead\{display:none\}/.test(CSS), "390px: bang thanh the");
  ok(/@media \(max-width:640px\)\{[^@]*\.edh-dmodal\{max-height:none;min-height:100%;border-radius:0\}/.test(CSS), "390px: popup toan man hinh");
  ok(/@media \(max-width:900px\)\{[^@]*\.edh-dm-b\{grid-template-columns:1fr\}/.test(CSS), "<=900px: popup 1 cot");
  ok(!/(^|\})\s*(body|html|\*|a|button|table)\s*[{,]/.test(CSS.replace(/body\.edh-noscroll/g, "")), "CSS khong dung selector tran");
}

// ------------------------------------------------------------------ dot 2 (file rieng) -----
{
  const r = (await import("./test_ec_data_hub_avail.mjs")).result;
  oks += r.oks; fails += r.fails;
}

console.log(`${oks} dat, ${fails} hong`);
process.exit(fails ? 1 : 0);
