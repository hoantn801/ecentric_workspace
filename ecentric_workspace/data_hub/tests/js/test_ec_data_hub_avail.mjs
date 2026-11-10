// Trung tam Du lieu DOT 2 - ec_data_hub.bundle.js tren HTML THAT cua /du-lieu/san-co (fixture render tu
// avail_service + jinja, xem test_avail.TestAvailFixtures) + goi y tuong tu tren form tao yeu cau.
//     node ecentric_workspace/data_hub/tests/js/test_ec_data_hub_avail.mjs
// (test_ec_data_hub.mjs import file nay va cong so ket qua - cong QC chay ca hai.)
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
const FIX = join(here, "fixtures");
const BUNDLE = readFileSync(join(APP, "public", "js", "ec_data_hub.bundle.js"), "utf8");
const CSS = readFileSync(join(APP, "public", "css", "ec_data_hub.bundle.css"), "utf8");
const API = JSON.parse(readFileSync(join(FIX, "avail_api.json"), "utf8"));
const C = API.codes;
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL (dot 2): " + n); } };
const eq = (a, b, n) => ok(JSON.stringify(a) === JSON.stringify(b), n + " -> " + JSON.stringify(a) + " != " + JSON.stringify(b));
const flush = async (n = 12) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 2)); };

async function page(name, { me = "thu.nguyen@ecentric.vn", url = "https://team.ecentric.vn/du-lieu/san-co", failOn = {} } = {}) {
  const html = readFileSync(join(FIX, name + ".html"), "utf8");
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
    else if (method === "suggest") data = API.suggest;
    else if (method === "plan_defaults") data = API.plan_defaults;
    else if (method === "propose") data = { name: "DP-2026-0009", due_at: "2026-11-10 09:30:00" };
    else if (method === "plan_availability") data = { code: "DA-2026-0099", due: "2026-11-20", pm_task: "TASK-2026-00123", warning: "" };
    else if (method === "review_proposal") data = { status: args.verdict, created: [] };
    else if (method === "save_availability") data = { name: "AV-001", created: false };
    else if (method === "save_library") data = { name: "RL-00009", created: true };
    else data = {};
    return Promise.resolve({ ok: success, status: success ? 200 : 417, json: () => Promise.resolve({ message: { success, message, data } }) });
  };
  w.eval(BUNDLE);
  await flush();
  return { dom, w, d: w.document, calls, H: w.ECDataHub };
}
const visible = (d, sel) => Array.from(d.querySelectorAll(sel)).filter((x) => !x.hidden);
const posted = (calls, m) => calls.filter((c) => c.method === m && c.post);

// ------------------------------------------------------------------ ham thuan ------------
{
  const { H } = await page("avail_user");
  const A = H.avail;
  ok(A && typeof A.install === "function", "bundle gan ECDataHub.avail");
  const row = { team: "Commercial", search: "commercial video shopee tiktok lazada", full: "0", gap: "1", plan: "1", stale: "0", front: "0" };
  ok(A.matrixMatch(row, { q: "video" }), "loc ma tran: tim");
  ok(!A.matrixMatch(row, { team: "Service" }), "loc ma tran: team");
  ok(A.matrixMatch(row, { state: "plan" }) && !A.matrixMatch(row, { state: "full" }), "loc ma tran: trang thai");
  ok(A.libMatch({ team: "Service", search: "affiliate" }, { q: "aff" }) && !A.libMatch({ team: "Service", search: "x" }, { team: "Commercial" }), "loc thu vien");
  const h = A.suggestHtml({ library: [{ title: "<b>PnL</b>", link: "javascript:alert(1)", team: "C" }], requests: [] });
  ok(h.indexOf("&lt;b&gt;PnL") > 0, "goi y escape tieu de");
  ok(h.indexOf("Đã có dashboard tương tự") > 0, "goi y: cau chu dung mockup");
  eq(A.suggestHtml({ library: [], requests: [] }), "", "khong co goi y -> rong");
  eq(A.nowLocal(new Date(2026, 10, 9, 8, 5)), "2026-11-09T08:05", "datetime-local");
  const ev = A.proposalDetailHtml({ data_type: "<img src=x onerror=alert(1)>", links: ["javascript:alert(1)", "https://ok.vn/a\"b"],
    files: [{ name: "<b>x</b>.png", url: "javascript:alert(1)", size: 10 }], urgency: "Khẩn", urgency_reason: "<script>" });
  ok(ev.indexOf("<img") < 0 && ev.indexOf("<script>") < 0 && ev.indexOf("<b>x") < 0, "chi tiet: escape moi gia tri");
  ok(ev.indexOf("javascript:") < 0, "chi tiet: khong tao link javascript:");
  eq(A.proposalErrors({ department: "D", data_type: "T", platforms: ["Shopee"], frequency: "Một lần", purpose: "p", urgency: "Khẩn" },
     ["Cao", "Khẩn"], "2026-11-09T08:00"), ["Mức “Khẩn” cần ghi lý do cần gấp."], "kiem form: Khan can ly do");
  eq(A.splitLinks(" https://a.vn\n\nhttps://b.vn, https://c.vn "), ["https://a.vn", "https://b.vn", "https://c.vn"], "tach link");
}

// ------------------------------------------------------------------ nhan vien ------------
{
  const { w, d, calls } = await page("avail_user");
  eq(visible(d, "[data-edh-mrow]").length, 27, "ma tran 27 nhom (52 dong) ve san o server");
  ok(!d.querySelector("[data-edh-plan-cell]") && !d.querySelector("[data-edh-plan-ov]"), "nhan vien: khong co Len ke hoach");
  ok(d.querySelector("[data-edh-av=library]").hidden, "mac dinh xem ma tran");
  // loc
  const st = d.querySelector('[data-edh-af="state"]');
  st.value = "plan"; st.dispatchEvent(new w.Event("change"));
  eq(visible(d, "[data-edh-mrow]").map((r) => r.querySelector("b").textContent), ["Video", "Voucher & Flashsale"], "loc Dang bo sung");
  eq(visible(d, "[data-edh-mteam]").map((r) => r.dataset.edhMteam), ["Commercial"], "an nhom team khong con dong");
  st.value = "stale"; st.dispatchEvent(new w.Event("change"));
  eq(visible(d, "[data-edh-mrow]").length, 1, "loc Tre cap nhat");
  st.value = ""; st.dispatchEvent(new w.Event("change"));
  const q = d.querySelector('[data-edh-af="q"]');
  q.value = "khong-co-gi"; q.dispatchEvent(new w.Event("input"));
  ok(!d.querySelector("[data-edh-mempty]").hidden, "khong khop -> trang thai rong");
  q.value = "omisell"; q.dispatchEvent(new w.Event("input"));
  eq(visible(d, "[data-edh-mrow]").length, 1, "tim theo san Khac");
  // o dang lam -> popup DA
  d.querySelector(`.edh-cellplan[data-edh-open="${C.da_video}"]`).click();
  await flush();
  ok(!d.querySelector("[data-edh-detail-ov]").hidden, "bam o 'Dang lam' -> popup chi tiet DA");
  const box = d.querySelector("[data-edh-detail]").innerHTML;
  ok(box.indexOf("Bổ sung <b>Video</b>") >= 0 && box.indexOf("Hoàn tất thì các ô đã chọn tự chuyển") >= 0, "popup DA: san / kenh / luat dong");
  ok(box.indexOf("Bổ sung data") >= 0, "popup DA: nhan loai");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  // de xuat (10/11/2026: phong ban ERP, loai chon / them moi, chip san, tan suat, ly do Cao / Khan, can truoc, tep)
  d.querySelector("[data-edh-propose]").click();
  const pf = d.querySelector("[data-edh-prop-form]");
  ok(!d.querySelector("[data-edh-prop-ov]").hidden, "mo hop de xuat");
  eq(pf.elements.department.tagName, "SELECT", "phong ban = dropdown ERP (khong go tay)");
  eq(pf.elements.department.value, "Commercial - EC", "phong ban mac dinh = phong ban nguoi gui");
  eq(Array.from(pf.elements.department.options).map((o) => o.textContent).filter((x) => x.indexOf("Service") >= 0),
     ["Service - BM", "Service - EC"], "trung ten giua cong ty -> hien ten day du");
  ok(!pf.querySelector("datalist") && !pf.querySelector("[list]"), "khong con datalist trong hop de xuat");
  eq(pf.querySelectorAll(".edh-chip > input[type=checkbox] + span").length, 6, "san + kenh = chip (input an + span)");
  ok(pf.elements.data_type_new.hidden, "o loai moi an khi chua chon");
  ok(d.querySelector("[data-edh-urg-why]").hidden && pf.elements.urgency_reason.disabled, "ly do gap an khi Binh thuong");
  ok(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(pf.elements.needed_by.min), "Can truoc: min = bay gio");
  pf.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  const e0 = d.querySelector("[data-edh-prop-err]").textContent;
  ok(!d.querySelector("[data-edh-prop-err]").hidden && posted(calls, "propose").length === 0, "thieu truong -> bao loi, khong gui");
  ok(e0.indexOf("loại dữ liệu") >= 0 && e0.indexOf("tần suất") >= 0 && e0.indexOf("sàn") >= 0, "bao dung truong thieu");
  // loai moi
  pf.elements.data_type_pick.value = "__new__"; pf.elements.data_type_pick.dispatchEvent(new w.Event("change"));
  ok(!pf.elements.data_type_new.hidden && pf.elements.data_type_new.required, "chon 'Loại mới…' -> hien o nhap, bat buoc");
  pf.elements.data_type_new.value = "Livestream session";
  // chip: bam vao input (nhu bam chip)
  pf.querySelector('input[name="platforms"][value="TikTok"]').click();
  ok(pf.querySelector('input[name="platforms"][value="TikTok"]').checked, "bam chip -> chon");
  pf.elements.other_platform.value = "Facebook";
  pf.elements.frequency.value = "Hằng ngày";
  pf.querySelector('input[name="channels"][value="powerbi"]').click();
  pf.elements.source_links.value = "https://seller.shopee.vn/a\nshopee.vn/b";
  pf.elements.purpose.value = "Đo video";
  pf.elements.urgency.value = "Cao"; pf.elements.urgency.dispatchEvent(new w.Event("change"));
  ok(!d.querySelector("[data-edh-urg-why]").hidden && !pf.elements.urgency_reason.disabled, "muc Cao -> hien o ly do");
  pf.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  const e1 = d.querySelector("[data-edh-prop-err]").textContent;
  ok(e1.indexOf("http://") >= 0 && e1.indexOf("lý do cần gấp") >= 0 && posted(calls, "propose").length === 0, "link sai + thieu ly do -> chan");
  pf.elements.source_links.value = "https://seller.shopee.vn/a\nhttps://seller.shopee.vn/b";
  pf.elements.urgency_reason.value = "Chốt ngân sách 12.12";
  pf.elements.needed_by.value = "2020-01-01T08:00";
  pf.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  ok(d.querySelector("[data-edh-prop-err]").textContent.indexOf("tương lai") >= 0, "Can truoc trong qua khu -> chan");
  pf.elements.needed_by.value = "2099-12-01T17:00";
  pf.elements.data_from.value = "2026-10-01";
  pf.dispatchEvent(new w.Event("submit", { cancelable: true }));
  pf.dispatchEvent(new w.Event("submit", { cancelable: true }));     // bam 2 lan
  await flush();
  const pc = posted(calls, "propose");
  eq(pc.length, 1, "chong bam 2 lan");
  const pd = JSON.parse(pc[0].args.data);
  eq([pd.department, pd.data_type, pd.platforms, pd.other_platform, pd.urgency, pd.urgency_reason, pd.frequency, pd.channels, pd.needed_by, pd.data_from],
     ["Commercial - EC", "Livestream session", ["TikTok"], "Facebook", "Cao", "Chốt ngân sách 12.12", "Hằng ngày", ["powerbi"], "2099-12-01T17:00", "2026-10-01"], "du lieu de xuat");
  ok(!("data_type_pick" in pd) && !("data_type_new" in pd) && !("guide_files" in pd) && !("files" in pd), "khong gui truong phu / tep rong");
  eq(pc[0].csrf, "tok", "POST kem CSRF");
  ok(d.querySelector("[data-edh-prop-ov]").hidden && w.__edhReloaded !== undefined, "gui xong dong hop + tai lai");
  ok(d.querySelector("[data-edh-toast]").textContent.indexOf("DP-2026-0009") >= 0, "toast co ma de xuat");
  // chi tiet de xuat (nhan vien khac: thay ten tep, khong co link tai)
  const boot = JSON.parse(d.getElementById("edh-boot").textContent);
  d.querySelector(`[data-edh-pdet-open="${C.p_voucher}"]`).click();
  ok(!d.querySelector("[data-edh-pdet-ov]").hidden, "mo hop Chi tiet");
  const det = d.querySelector("[data-edh-pdet]").innerHTML;
  ok(det.indexOf("Cần số trước khi chốt ngân sách 12.12") >= 0 && det.indexOf("edh-urgwhy") >= 0, "chi tiet: ly do gap noi bat");
  ok(det.indexOf('href="https://seller.shopee.vn/portal/marketing/vouchers" target="_blank" rel="noopener noreferrer"') >= 0, "chi tiet: link nguon mo tab moi");
  ok(det.indexOf("17:00 01/12/2026") >= 0 && det.indexOf("Hằng ngày") >= 0 && det.indexOf("01/10/2026 – nay") >= 0, "chi tiet: can truoc / tan suat / khoang");
  ok(det.indexOf("huong-dan-voucher.png") >= 0, "chi tiet: ten tep");
  eq(boot.proposals[C.p_voucher].files[0].url === "" , false, "nguoi de xuat (Thu) co link tai tep cua minh");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  ok(d.querySelector("[data-edh-pdet-ov]").hidden, "Esc dong Chi tiet");
  // thu vien
  d.querySelector('[data-edh-sub="library"]').click();
  ok(!d.querySelector("[data-edh-av=library]").hidden && d.querySelector("[data-edh-av=matrix]").hidden, "chuyen Thu vien");
  eq(new URL(w.location.href).searchParams.get("xem"), "thu-vien", "URL ?xem=thu-vien");
  const lq = d.querySelector('[data-edh-lf="q"]');
  lq.value = "pnl"; lq.dispatchEvent(new w.Event("input"));
  eq(visible(d, "[data-edh-lrow]").length, 1, "tim trong thu vien");
  ok(!d.querySelector("[data-edh-lib-new]"), "nhan vien khong them bao cao");
}

// ------------------------------------------------------------------ propose loi server --
{
  const { w, d } = await page("avail_user", { failOn: { propose: "Hôm nay bạn đã gửi 10 đề xuất." } });
  d.querySelector("[data-edh-propose]").click();
  const pf = d.querySelector("[data-edh-prop-form]");
  pf.elements.data_type_pick.value = "Video";
  pf.querySelector('input[name="platforms"][value="Shopee"]').checked = true;
  pf.elements.frequency.value = "Một lần";
  pf.elements.purpose.value = "x";
  pf.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  eq(d.querySelector("[data-edh-prop-err]").textContent, "Hôm nay bạn đã gửi 10 đề xuất.", "loi server hien trong hop");
  ok(!d.querySelector("[data-edh-prop-ov]").hidden, "hop van mo de sua");
  ok(!d.querySelector("[data-edh-prop-submit]").disabled, "mo khoa nut sau loi");
}

// ------------------------------------------------------------------ team Data -----------
{
  const me = "linh.vuong@ecentric.vn";
  const { w, d, calls } = await page("avail_team", { me });
  const boot = JSON.parse(d.getElementById("edh-boot").textContent);
  // len ke hoach tu danh sach Can bo sung (de xuat da duyet)
  d.querySelector('[data-edh-plan="Service|Affiliate order"]').click();
  await flush();
  const f = d.querySelector("[data-edh-plan-form]");
  ok(!d.querySelector("[data-edh-plan-ov]").hidden, "mo hop Len ke hoach");
  eq([f.elements.team.value, f.elements.data_type.value, f.elements.proposal.value, f.elements.priority.value],
     ["Service", "Affiliate order", C.p_gmv, "Cao"], "dien san tu de xuat da duyet");
  eq(Array.from(f.querySelectorAll('input[name="platforms"]:checked')).map((x) => x.value), ["TikTok", "Lazada"], "san con thieu da chon");
  eq(Array.from(f.querySelectorAll('input[name="channels"]:checked')).map((x) => x.value), ["sharepoint", "powerbi"], "kenh lay tu de xuat");
  ok(f.elements.note.value.indexOf("Tần suất: Hằng ngày") >= 0 && f.elements.note.value.indexOf("1 link nguồn") >= 0, "ghi chu = tom tat de xuat");
  ok(d.querySelector("[data-edh-plan-prop]").textContent.indexOf("QBR tuần sau") >= 0, "bang de xuat: ly do gap");
  eq(f.elements.assignee.value, me, "nguoi xu ly mac dinh = minh");
  ok(!d.querySelector("[data-edh-plan-prop]").hidden, "bang 'tu de xuat' hien");
  eq(calls.filter((c) => c.method === "plan_defaults").map((c) => c.args.priority), ["Cao"], "muc Cao -> hoi lai han mac dinh");
  eq(f.elements.due_date.value, API.plan_defaults.due, "ket thuc mac dinh theo quy tac (x he so)");
  f.elements.start_date.value = "2026-11-12"; f.elements.start_date.dispatchEvent(new w.Event("change"));
  await flush();
  eq(calls.filter((c) => c.method === "plan_defaults").pop().args.start_date, "2026-11-12", "doi ngay bat dau -> tinh lai ket thuc");
  f.querySelectorAll('input[name="channels"]').forEach((c) => { c.checked = false; });
  f.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  ok(d.querySelector("[data-edh-plan-err]").textContent.indexOf("kênh đích") >= 0, "khong chon kenh -> bao loi");
  f.querySelector('input[name="channels"][value="dw"]').checked = true;
  f.elements.note.value = "Crawl API";
  f.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  const pc = posted(calls, "plan_availability");
  eq(pc.length, 1, "gui ke hoach");
  const pd = JSON.parse(pc[0].args.data);
  eq([pd.team, pd.data_type, pd.platforms, pd.channels, pd.proposal, pd.assignee, pd.start_date, pd.note],
     ["Service", "Affiliate order", ["TikTok", "Lazada"], ["dw"], C.p_gmv, me, "2026-11-12", "Crawl API"], "du lieu ke hoach");
  ok(d.querySelector("[data-edh-toast]").textContent.indexOf("DA-2026-0099") >= 0, "toast ma DA + task /pm");
  // len ke hoach tu o "Chua co"
  const live = Object.values(boot.rows).find((r) => r.data_type === "Live" && r.platform === "Lazada");
  d.querySelector(`[data-edh-plan-cell="${live.name}"]`).click();
  eq(Array.from(f.querySelectorAll('input[name="platforms"]:checked')).map((x) => x.value), ["Lazada"], "o 'Chua co' -> chi san do");
  eq([f.elements.proposal.value, f.elements.data_type.value], ["", "Live"], "o khong tu de xuat");
  eq(Array.from(f.querySelectorAll('input[name="channels"]:checked')).length, 3, "khong tu de xuat -> mac dinh ca 3 kenh");
  eq(f.elements.note.value, "", "khong tu de xuat -> ghi chu trong");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  ok(d.querySelector("[data-edh-plan-ov]").hidden, "Esc dong hop ke hoach");
  // sua dong
  const prod = Object.values(boot.rows).find((r) => r.data_type === "Orderline" && r.platform === "TikTok");
  d.querySelector(`[data-edh-row-edit="${prod.name}"]`).click();
  const rf = d.querySelector("[data-edh-rowf]");
  eq([rf.elements.frequency.value, rf.elements.data_owner.value, rf.elements.in_powerbi.checked, rf.elements.team.readOnly],
     ["Hằng ngày", me, true, true], "dien san dong dang sua (khoa team/loai/san)");
  rf.querySelector("[data-edh-r-now]").click();
  ok(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(rf.elements.last_updated.value), "nut Bay gio");
  rf.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  const rd = JSON.parse(posted(calls, "save_availability")[0].args.data);
  eq([rd.name, rd.in_sharepoint, rd.in_powerbi, rd.frequency], [prod.name, 1, 1, "Hằng ngày"], "luu dong");
  d.querySelector("[data-edh-row-new]").click();
  eq([rf.elements.name.value, rf.elements.team.readOnly], ["", false], "them dong moi: form trong");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  // duyet / tu choi
  d.querySelector(`[data-edh-approve="${C.p_creator}"]`).click();
  await flush();
  eq(posted(calls, "review_proposal").map((c) => [c.args.name, c.args.verdict]), [[C.p_creator, "Đã duyệt"]], "Duyet");
  d.querySelector(`[data-edh-reject="${C.p_creator}"]`).click();
  const wf = d.querySelector("[data-edh-why-form]");
  wf.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  ok(!d.querySelector("[data-edh-why-err]").hidden && posted(calls, "review_proposal").length === 1, "Tu choi bat buoc ly do");
  wf.elements.reason.value = "Đã có trong Kalodata";
  wf.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  eq(posted(calls, "review_proposal").pop().args, { name: C.p_creator, verdict: "Từ chối", reason: "Đã có trong Kalodata" }, "Tu choi + ly do");
}

// ------------------------------------------------------------------ thu vien (team) ------
{
  const { w, d, calls } = await page("avail_team_lib", { me: "linh.vuong@ecentric.vn", url: "https://team.ecentric.vn/du-lieu/san-co?xem=thu-vien" });
  ok(!d.querySelector("[data-edh-av=library]").hidden, "?xem=thu-vien ve san o server");
  d.querySelector("[data-edh-lib-new]").click();
  const lf = d.querySelector("[data-edh-lib-form]");
  lf.elements.title.value = "PnL Friso";
  lf.elements.link.value = "ftp://x";
  lf.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  ok(d.querySelector("[data-edh-lib-err]").textContent.indexOf("http") >= 0, "link phai http(s)");
  lf.elements.link.value = "https://app.powerbi.com/friso";
  lf.dispatchEvent(new w.Event("submit", { cancelable: true }));
  await flush();
  eq(JSON.parse(posted(calls, "save_library")[0].args.data).link, "https://app.powerbi.com/friso", "luu bao cao");
  const tg = d.querySelector("[data-edh-lib-toggle]");
  tg.click();
  await flush();
  eq(posted(calls, "library_active")[0].args, { name: tg.dataset.edhLibToggle, active: "0" }, "An bao cao");
  const ed = d.querySelector("[data-edh-lib-edit]");
  ed.click();
  ok(lf.elements.name.value === ed.dataset.edhLibEdit && lf.elements.title.value.length > 0, "Sua: dien san");
}

// ------------------------------------------------------------------ goi y tren form tao ----
{
  const { w, d, calls } = await page("index_suggest", { url: "https://team.ecentric.vn/du-lieu" });
  d.querySelector("[data-edh-new]").click();
  const t = d.getElementById("edh-new-title"), box = d.querySelector("[data-edh-similar]");
  t.value = "PB"; t.dispatchEvent(new w.Event("input"));
  await new Promise((r) => setTimeout(r, 400)); await flush();
  eq(calls.filter((c) => c.method === "suggest").length, 0, "< 3 ky tu -> khong hoi");
  t.value = "Dashboard PnL"; t.dispatchEvent(new w.Event("input"));
  t.value = "Dashboard PnL theo ngày Friso"; t.dispatchEvent(new w.Event("input"));
  await new Promise((r) => setTimeout(r, 400)); await flush();
  const sc = calls.filter((c) => c.method === "suggest");
  eq(sc.map((c) => c.args.q), ["Dashboard PnL theo ngày Friso"], "debounce: chi hoi lan cuoi");
  ok(!box.hidden && box.textContent.indexOf("Đã có dashboard tương tự: Dashboard PnL tổng hợp brand") >= 0, "hien dashboard tuong tu");
  ok(box.textContent.indexOf("Đang có yêu cầu tương tự") >= 0 && box.querySelector('a[href^="/du-lieu?ma="]'), "hien yeu cau dang mo tuong tu + link");
  ok(box.querySelector('a[target="_blank"][rel~="noopener"]'), "link dashboard mo tab moi an toan");
}

// ------------------------------------------------------------------ CSS 390px -----------
{
  ok(/\.edh-d\.is-sp\{background:#60a5fa\}/.test(CSS) && /\.edh-gl\.is-da,\.edh-bar\.is-da\{background:var\(--edh-teal\)\}/.test(CSS), "mau cham + thanh DA xanh ngoc");
  ok(/@media \(max-width:640px\)\{[^@]*\.edh-mtx\{min-width:640px\}/.test(CSS), "390px: ma tran cuon ngang (khong vo bang)");
  ok(/@media \(max-width:640px\)\{[^@]*\.edh-tbl\.edh-mtx thead[^{]*\{display:table-header-group\}/.test(CSS), "390px: ma tran giu dang bang");
  ok(!/(^|\})\s*(body|html|\*|a|button|table)\s*[{,]/.test(CSS.replace(/body\.edh-noscroll/g, "")), "CSS khong dung selector tran");
}

export const result = { oks, fails };
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  console.log(`${oks} dat, ${fails} hong (dot 2)`);
  process.exit(fails ? 1 : 0);
}
