// Copyright (c) 2026, eCentric and contributors
// Payment Request — thanh toán chia đợt trên form (07/09, Hoàn).
//
// CODE THẬT qua vm. Kiểm: form tạo mới có chọn hình thức; chọn "Chia đợt" mới hiện tổng / đợt kế;
// đợt kế tự tính = tổng − đợt này; validateSubmit chặn vượt tổng / thiếu ngày đợt kế / ngày không
// sau đợt này; đợt cuối không đòi đợt kế; chi tiết: chuỗi các đợt (chip), thẻ chia đợt với nút
// "Tạo đề nghị đợt k+1" chỉ khi can_create_next, link đợt kế khi đã có; gộp 6 bước khi đợt xong
// và đã có đợt kế; đợt 2 draft không đổi được hình thức.
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = path.join(HERE, "..", "..", "features", "payment_request", "ui", "main_section.html");
if (!fs.existsSync(PAGE)) throw new Error("main_section.html not found: " + PAGE);
const SRC = fs.readFileSync(PAGE, "utf8").match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };

function mkEl(id) {
  return { id, _html: "", textContent: "", style: {}, value: "", disabled: false, _attrs: {}, hidden: false,
    children: [], classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    getAttribute(k){ return k in this._attrs ? this._attrs[k] : null; },
    setAttribute(k, v){ this._attrs[k] = String(v); },
    appendChild(c){ this.children.push(c); return c; }, removeChild(){}, remove(){}, replaceWith(){},
    addEventListener(){}, removeEventListener(){}, querySelectorAll(){ return []; },
    querySelector(){ return null; }, closest(){ return null; }, focus(){}, scrollIntoView(){},
    get innerHTML(){ return this._html; }, set innerHTML(v){ this._html = String(v); } };
}
const els = {};
const doc = { readyState: "loading", getElementById: (id) => els[id] || (els[id] = mkEl(id)),
  createElement: (t) => mkEl(t), querySelectorAll: () => [], querySelector: () => null,
  addEventListener(){}, body: mkEl("body"), head: mkEl("head") };
const win = { location: { pathname: "/approvals/payment-request", search: "", href: "" },
  addEventListener(){}, matchMedia: () => ({ matches: false, addEventListener(){} }),
  requestAnimationFrame: (f) => f(), setTimeout, clearTimeout, console, history: { pushState(){}, replaceState(){} },
  setInterval: () => 1, clearInterval(){} };
win.frappe = { csrf_token: "x", call: () => Promise.resolve({ message: {} }) };
const sandbox = { window: win, document: doc, console, setTimeout, clearTimeout, setInterval: win.setInterval,
  clearInterval: win.clearInterval, frappe: win.frappe, URLSearchParams, fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
  navigator: { userAgent: "node" }, FormData: function(){ this.append = () => {}; } };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
try { vm.runInContext(SRC, sandbox, { filename: "payment_request.js" }); }
catch (e) { console.log("BOOT ERROR: " + e.message); process.exit(1); }
const PR = win.PaymentRequest;
if (!PR || typeof PR.formCardsHTML !== "function" || typeof PR.instCardHTML !== "function") {
  console.log("FAIL: PaymentRequest.formCardsHTML/instCardHTML not exported"); process.exit(1); }
PR.state.boot = { tabs: {}, context: { user: "req@ec.vn", employee_name: "Hoàn" }, form_options: { yes_no: ["Yes", "No"] } };
const C = PR.state.boot.context, FO = PR.state.boot.form_options;

// --- 1. form tạo mới ---
let h = PR.formCardsHTML({ payment_mode: "Full" }, C, FO);
ok(/data-model="payment_mode"/.test(h) && /Chia đợt/.test(h), "form có chọn hình thức thanh toán");
ok(!/data-model="total_amount"/.test(h) && !/data-model="next_installment_date"/.test(h), "100%: không hiện tổng / đợt kế");
h = PR.formCardsHTML({ payment_mode: "Installment", total_amount: 10000, payment_amount: 4000 }, C, FO);
ok(/data-model="total_amount"/.test(h), "chia đợt: hiện tổng giá trị");
ok(/Số tiền đợt 1/.test(h), "chia đợt: nhãn số tiền đợt 1");
ok(/data-model="next_installment_amount" value="6000"/.test(h), "đợt kế tự tính 10000−4000=6000");
ok(/data-model="next_installment_date"/.test(h), "chia đợt: hỏi ngày dự kiến đợt kế");
h = PR.formCardsHTML({ payment_mode: "Installment", total_amount: 10000, payment_amount: 10000 }, C, FO);
ok(/đợt cuối/.test(h) && !/data-model="next_installment_date"/.test(h), "đợt này = hết tổng → đợt cuối, không hỏi đợt kế");
h = PR.formCardsHTML({ payment_mode: "Installment", total_amount: 10000, payment_amount: 5000, installment_no: 2, installment_of: "EC-PAYR-2026-00001", _paid_before: 5000 }, C, FO);
ok(/data-model="payment_mode" disabled/.test(h) && /Đợt 2 của phiếu EC-PAYR-2026-00001/.test(h), "đợt 2: không đổi hình thức, ghi rõ phiếu gốc");
ok(/Số tiền đợt 2/.test(h) && /readonly/.test(h.split('data-model="total_amount"')[0].slice(-80) + h.split('data-model="total_amount"')[1].slice(0, 80)), "đợt 2: tổng chỉ đọc");
ok(PR.installmentRemaining({ total_amount: 10000, payment_amount: 5000, _paid_before: 5000 }) === 0, "còn lại tính cả phần đợt trước");

// --- 2. validateSubmit ---
const base = { reason: "x", payment_amount: 4000, payment_date: "2026-09-10", payee_full_name: "A", account_bank: "B", bank_account_number: "1",
  has_purchase_request: "No", no_purchase_request_reason: "r", is_cost_valid: "Yes", details_and_attachments_correct: "Yes", request_attachment: "/private/files/a.pdf" };
PR.state.draft = Object.assign({}, base, { payment_mode: "Full" });
ok(PR.validateSubmit() === null, "100% hợp lệ");
PR.state.draft = Object.assign({}, base, { payment_mode: "Installment" });
let e = PR.validateSubmit(); ok(e && e.total_amount, "chia đợt thiếu tổng → lỗi total_amount");
PR.state.draft = Object.assign({}, base, { payment_mode: "Installment", total_amount: 3000 });
e = PR.validateSubmit(); ok(e && /vượt/.test(e.payment_amount || ""), "đợt này > tổng → lỗi");
PR.state.draft = Object.assign({}, base, { payment_mode: "Installment", total_amount: 10000 });
e = PR.validateSubmit(); ok(e && e.next_installment_date && !e.next_installment_amount, "thiếu ngày đợt kế → lỗi; số tiền đợt kế tự mặc định không lỗi");
PR.state.draft = Object.assign({}, base, { payment_mode: "Installment", total_amount: 10000, next_installment_date: "2026-09-10" });
e = PR.validateSubmit(); ok(e && /sau ngày/.test(e.next_installment_date || ""), "ngày đợt kế không sau đợt này → lỗi");
PR.state.draft = Object.assign({}, base, { payment_mode: "Installment", total_amount: 10000, next_installment_amount: 9000, next_installment_date: "2026-10-10" });
e = PR.validateSubmit(); ok(e && e.next_installment_amount, "đợt kế > còn lại → lỗi");
PR.state.draft = Object.assign({}, base, { payment_mode: "Installment", total_amount: 10000, next_installment_amount: 3000, next_installment_date: "2026-10-10" });
ok(PR.validateSubmit() === null, "chia 3 đợt hợp lệ");
PR.state.draft = Object.assign({}, base, { payment_mode: "Installment", total_amount: 10000, payment_amount: 5000, _paid_before: 5000 });
ok(PR.validateSubmit() === null, "đợt cuối (đã có 5000 trước) hợp lệ, không đòi đợt kế");
PR.state.draft = Object.assign({}, base, { payment_mode: "Installment", total_amount: 10000, payment_amount: 6000, _paid_before: 5000 });
e = PR.validateSubmit(); ok(e && /vượt/.test(e.payment_amount || ""), "đợt 2 vượt phần còn lại (đã trả 5000) → lỗi");

// --- 3. chi tiết: chuỗi + thẻ ---
function det(ib, ff, status) {
  return { business: { name: "EC-PAYR-A", payment_amount: 5000, requested_by: "req@ec.vn" },
    approval: { name: "AR", approval_status: status || "Approved", current_level: 0 },
    levels: [], approvers: [], fulfillment: ff || {}, capabilities: {}, attachments: [], timeline: [], extra: { installments: ib } };
}
const chain1 = [{ name: "EC-PAYR-A", installment_no: 1, payment_amount: 5000, payment_date: "2026-09-10", approval_status: "Approved", fulfillment_status: "Completed", completed_at: "2026-09-10 15:00:00", is_current: true }];
let d = det({ root: "EC-PAYR-A", installment_no: 1, total_amount: 10000, paid_amount: 5000, remaining_after_this: 5000,
  next_expected: { amount: 5000, date: "2026-10-10" }, next_request: null, can_create_next: true, chain: chain1 }, { status: "Completed" });
h = PR.instChainHTML(d);
ok(/inst-chip cur/.test(h) && /Đợt 1 ✓/.test(h) && /Đã UNC/.test(h), "chuỗi: đợt 1 hiện tại, đã UNC");
ok(/inst-chip plan/.test(h) && /Đợt 2 \(dự kiến\)/.test(h) && /2026-10-10/.test(h), "chuỗi: chip dự kiến đợt 2");
h = PR.instCardHTML(d);
ok(/data-act="next-installment"/.test(h) && /Tạo đề nghị đợt 2/.test(h), "thẻ: nút tạo đợt 2 khi can_create_next");
ok(/Còn lại sau đợt này/.test(h) && /5.000/.test(h), "thẻ: còn lại");
d.extra.installments.can_create_next = false; d.fulfillment = { status: "Assigned" };
h = PR.instCardHTML(d);
ok(!/data-act="next-installment"/.test(h) && /sau khi Finance xử lý UNC/.test(h), "chưa UNC: không có nút, giải thích");
ok(PR.instFolded(d) === false, "chưa có đợt kế: không gộp");
d = det({ root: "EC-PAYR-A", installment_no: 1, total_amount: 10000, paid_amount: 5000, remaining_after_this: 5000, next_expected: { amount: 5000, date: "2026-10-10" },
  next_request: "EC-PAYR-B", can_create_next: false,
  chain: chain1.concat([{ name: "EC-PAYR-B", installment_no: 2, payment_amount: 5000, payment_date: "2026-10-10", approval_status: "Pending", fulfillment_status: "Not Started", is_current: false }]) },
  { status: "Completed" });
h = PR.instChainHTML(d);
ok(/href="\?id=EC-PAYR-B&tab=detail"/.test(h) && /Đang duyệt/.test(h) && !/inst-chip plan/.test(h), "chuỗi: đợt 2 đã tạo → link + trạng thái, không còn chip dự kiến");
h = PR.instCardHTML(d);
ok(!/next-installment/.test(h) && /EC-PAYR-B/.test(h), "thẻ: đã có đợt 2 → link, không nút tạo");
ok(PR.instFolded(d) === true, "đợt 1 xong + có đợt 2 → gộp 6 bước");
// đợt 1 CHƯA UNC nhưng đã có đợt 2 (vd tạo bởi SM): không gộp — 6 bước vẫn cần nhìn thấy
d.fulfillment = { status: "In Progress" };
ok(PR.instFolded(d) === false, "đợt này chưa UNC xong → không gộp dù có đợt kế");
d.fulfillment = { status: "Completed" };
// XSS: mã phiếu / trạng thái đi qua esc (cả chip hiện tại lẫn chip link)
d.extra.installments.chain[1].name = "<img src=x>";
ok(PR.instChainHTML(d).indexOf("<img") < 0, "chuỗi esc mã phiếu (link)");
d.extra.installments.chain[0].name = "<img src=y>";
ok(PR.instChainHTML(d).indexOf("<img") < 0, "chuỗi esc mã phiếu (hiện tại)");
ok(PR.instChainHTML(det(null)) === "" && PR.instCardHTML(det(null)) === "", "phiếu 100%: không có chuỗi/thẻ");

console.log(`${pass} đạt, ${fail} hỏng`);
if (pass < 32) { console.log("HONG: so phep kiem thap bat thuong (" + pass + ")"); process.exit(1); }
process.exit(fail ? 1 : 0);
