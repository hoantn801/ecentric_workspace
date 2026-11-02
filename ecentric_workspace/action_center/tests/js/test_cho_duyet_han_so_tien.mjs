// "Cho toi duyet" (03/11/2026, UX quan ly): han noi bang loi, phieu qua han noi bat + dong tom tat,
// so tien dam tren the, va so tien lon (>= 20.000.000) phai bam Duyet HAI lan.
//     node ecentric_workspace/action_center/tests/js/test_cho_duyet_han_so_tien.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
const HTML = readFileSync(join(APP, "action_center", "pages", "my_work", "main_section.html"), "utf8");
const BUNDLE = readFileSync(join(APP, "public", "js", "ec_cho_duyet.bundle.js"), "utf8");
const CSS = readFileSync(join(APP, "public", "css", "ec_cho_duyet.bundle.css"), "utf8");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 3)); };
const p2 = (n) => (n < 10 ? "0" : "") + n;
const at = (hours) => { const d = new Date(Date.now() + hours * 3600000); return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}:00`; };
const CAP = { can_approve: true, can_reject: true, can_request_info: true, needs_input: false, needs_input_reason: "", comment_required: false };

const ROWS = () => ([
  { request: "R1", type_label: "Thanh toán", title: "KOL tháng 10", requester_name: "Mai", submitted_at: at(-72), due_at: at(-50), level_name: "TP",
    summary: [{ label: "Người nhận", value: "Cty A" }, { label: "Số tiền", value: "185.400.000" }], capabilities: CAP },
  { request: "R2", type_label: "Thanh toán", title: "Tạm ứng vật tư", requester_name: "Hùng", submitted_at: at(-5), due_at: at(26 * 24), level_name: "TP",
    summary: [{ label: "Người nhận", value: "Hùng" }, { label: "Số tiền", value: "2.350.000" }], capabilities: CAP },
  { request: "R3", type_label: "Hợp đồng", title: "HĐ brand B", requester_name: "An", submitted_at: at(-5), due_at: null, level_name: "CEO",
    summary: [{ label: "Loại", value: "Dịch vụ" }, { label: "Brand", value: "B" }, { label: "Hiệu lực", value: "01/12/2026" }, { label: "Giá trị", value: "90.500.000" }],
    capabilities: Object.assign({}, CAP, { sign_required: true }), sign_files: [] },
]);

function boot() {
  const i = HTML.indexOf('<div class="ecw"');
  const s = HTML.search(/<script id="ec-mywork-js">/);
  const markup = HTML.slice(i, s);
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url: "https://x.test/viec-cua-toi" });
  const w = dom.window;
  const calls = []; let rows = ROWS();
  w.frappe = { csrf_token: "tok" };
  w.fetch = (url, init) => {
    const m = String(url).split("?")[0].split(".").pop();
    const body = init && init.body ? JSON.parse(init.body) : null;
    calls.push([m, body]);
    const res = (obj) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(obj) });
    if (m === "list_my_pending") return res({ message: { rows, count: rows.length } });
    if (m === "quick_decide") { rows = rows.filter((r) => r.request !== body.request_name); return res({ message: { ok: true, remaining: rows.length } }); }
    return res({ message: {} });
  };
  w.eval(BUNDLE);
  return { w, calls };
}
const $ = (w, q) => w.document.querySelector(q);

{ // 1) han noi bang loi
  const { w } = boot(); await flush();
  const due1 = $(w, '[data-cd-open="R1"] .cd-due');
  ok(due1 && /Quá hạn 2 ngày/.test(due1.textContent) && due1.classList.contains("cd-due-late"), "qua han 50 gio -> 'Qua han 2 ngay' mau do: " + (due1 && due1.textContent));
  ok($(w, '[data-cd-open="R1"]').classList.contains("cd-card-late"), "the qua han co vien do");
  const due2 = $(w, '[data-cd-open="R2"] .cd-due');
  ok(due2 && /^Hạn \d\d\/\d\d/.test(due2.textContent) && due2.classList.contains("cd-due-ok"), "han con xa -> 'Han dd/mm' mau trung tinh");
  ok(!$(w, '[data-cd-open="R3"] .cd-due'), "khong co han -> khong ve nhan han");
  const sum = $(w, ".cd-late-sum");
  ok(sum && /^1 phiếu đã quá hạn/.test(sum.textContent), "dong tom tat so phieu qua han o dau danh sach");
}
{ // 2) han hom nay / ngay mai
  const { w } = boot(); await flush();
  const inst = $(w, "[data-ec-cho-duyet]").__ecCd;
  const d = new Date(); d.setHours(23, 58, 0, 0);
  const today = `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} 23:58:00`;
  inst.rows = [Object.assign(ROWS()[1], { due_at: today })]; inst.paint();
  const t = $(w, ".cd-due");
  ok(t && /Hạn hôm nay 23:58/.test(t.textContent) && t.classList.contains("cd-due-soon"), "han trong ngay -> 'Han hom nay HH:MM': " + (t && t.textContent));
  ok(!$(w, ".cd-late-sum"), "khong co phieu qua han -> khong co dong tom tat");
}
{ // 3) so tien dam tren the, ke ca khi nam o o thu 4
  const { w } = boot(); await flush();
  const m1 = $(w, '[data-cd-open="R1"] .cd-chip-money');
  ok(m1 && /185\.400\.000/.test(m1.textContent), "o so tien duoc lam dam");
  const m3 = $(w, '[data-cd-open="R3"] .cd-chip-money');
  ok(m3 && /90\.500\.000/.test(m3.textContent) && $(w, '[data-cd-open="R3"]').querySelectorAll(".cd-chip").length === 3, "tien o vi tri 4 van len the (3 o)");
}
{ // 4) so tien lon: bam Duyet lan 1 -> doi nut + hoi xac nhan, KHONG goi server; lan 2 moi duyet
  const { w, calls } = boot(); await flush();
  $(w, '[data-cd-open="R1"] .cd-title').click(); await flush();
  const btn = $(w, '.cd-sheet [data-cd-do="approve"]');
  btn.click(); await flush();
  ok(!calls.some((c) => c[0] === "quick_decide"), "lan 1: chua goi quick_decide");
  ok(/Xác nhận duyệt 185\.400\.000/.test(btn.textContent) && btn.classList.contains("cd-armed"), "nut doi thanh 'Xac nhan duyet <so tien>': " + btn.textContent);
  const msg = $(w, "[data-cd-msg]");
  ok(/Số tiền 185\.400\.000/.test(msg.textContent) && msg.classList.contains("cd-msg-info"), "loi nhac xac nhan (khong phai mau loi)");
  btn.click(); await flush();
  const q = calls.find((c) => c[0] === "quick_decide");
  ok(q && q[1].request_name === "R1" && q[1].action === "approve", "lan 2: quick_decide approve");
}
{ // 5) tu choi khoan lon: khong bi hoi xac nhan so tien (chi can ly do)
  const { w, calls } = boot(); await flush();
  $(w, '[data-cd-open="R1"] .cd-title').click(); await flush();
  $(w, "#cd-cmt").value = "Sai so tien";
  $(w, '.cd-sheet [data-cd-do="reject"]').click(); await flush();
  ok(calls.some((c) => c[0] === "quick_decide" && c[1].action === "reject"), "tu choi co ly do -> gui ngay");
}
{ // 6) so tien nho: mot lan bam la duyet
  const { w, calls } = boot(); await flush();
  $(w, '[data-cd-open="R2"] .cd-title').click(); await flush();
  $(w, '.cd-sheet [data-cd-do="approve"]').click(); await flush();
  ok(calls.some((c) => c[0] === "quick_decide" && c[1].request_name === "R2"), "duoi nguong: duyet ngay");
}
{ // 7) Duyet & Ky khoan lon cung phai xac nhan
  const { w, calls } = boot(); await flush();
  $(w, '[data-cd-open="R3"] .cd-title').click(); await flush();
  const b = $(w, '.cd-sheet [data-cd-do="approve_sign"]');
  b.click(); await flush();
  ok(!calls.some((c) => c[0] === "quick_decide") && /Xác nhận duyệt & ký 90\.500\.000/.test(b.textContent), "Duyet & Ky lan 1 -> xac nhan");
  b.click(); await flush();
  ok(calls.some((c) => c[0] === "quick_decide" && c[1].action === "approve_sign"), "Duyet & Ky lan 2 -> approve_sign");
}
{ // 8) du lieu nguoi dung trong tieu de / nhan han khong thanh HTML
  const { w } = boot(); await flush();
  const inst = $(w, "[data-ec-cho-duyet]").__ecCd;
  inst.rows = [Object.assign(ROWS()[0], { title: "<img src=x onerror=alert(1)>", summary: [{ label: "Số tiền", value: "<b>1</b>" }] })]; inst.paint();
  ok(!$(w, ".cd-card img") && !$(w, ".cd-card .cd-chip b"), "tieu de / tom tat duoc escape");
}
ok(/\.cd-card-late\{/.test(CSS) && /\.cd-due-late\{/.test(CSS) && /\.cd-btn\.cd-armed\{/.test(CSS), "CSS co kieu cho qua han / nut xac nhan");
console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
