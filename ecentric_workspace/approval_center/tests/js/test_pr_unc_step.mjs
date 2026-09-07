// Copyright (c) 2026, eCentric and contributors
// Payment Request bước 6 "Finance xử lý UNC" trên form (07/09, Hoàn).
//
// Chạy CODE THẬT của trang qua vm. Kiểm: stepper có bước 6 đúng trạng thái theo det.fulfillment
// (Chờ nhận / Đang xử lý / Đã UNC / không áp dụng cho phiếu duyệt trước khi có bước này);
// "Hoàn tất" chỉ xanh khi UNC xong; thẻ UNC: Nhận xử lý khi can_claim, form file + Hoàn tất khi
// can_complete, link file khi Completed; Hoàn tất mà chưa tải file thì báo lỗi, KHÔNG gọi API;
// preview 6 bước; stepLabel N = cấp + 3.
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
const calls = [];
const toasts = [];
const win = { location: { pathname: "/approvals/payment-request", search: "?id=EC-PAYR-2026-00001&tab=detail", href: "" },
  addEventListener(){}, matchMedia: () => ({ matches: false, addEventListener(){} }),
  requestAnimationFrame: (f) => f(), setTimeout, clearTimeout, console, history: { pushState(){}, replaceState(){} },
  setInterval: () => 1, clearInterval(){} };
win.frappe = { csrf_token: "x", call: (o) => { calls.push({ method: o.method, args: o.args }); return Promise.resolve({ message: {} }); } };
const sandbox = { window: win, document: doc, console, setTimeout, clearTimeout, setInterval: win.setInterval,
  clearInterval: win.clearInterval, frappe: win.frappe, URLSearchParams, fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
  navigator: { userAgent: "node" }, FormData: function(){ this.append = () => {}; } };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
try { vm.runInContext(SRC, sandbox, { filename: "payment_request.js" }); }
catch (e) { console.log("BOOT ERROR: " + e.message); process.exit(1); }
const PR = win.PaymentRequest;
if (!PR || typeof PR.buildStepper !== "function" || typeof PR.uncSectionHTML !== "function") {
  console.log("FAIL: PaymentRequest.buildStepper/uncSectionHTML not exported"); process.exit(1); }
PR.state.boot = { tabs: {}, context: { user: "fin1@ec.vn" }, form_options: {} };

const LEVELS = [1, 2, 3, 4].map((n) => ({ level_no: n, level_name: "Cấp " + n, level_status: "Approved", approval_mode: "Any One" }));
function det(ff, cap, status) {
  return { business: { name: "EC-PAYR-2026-00001", requested_by: "req@ec.vn" },
    approval: { name: "EC-APR-1", approval_status: status || "Approved", current_level: 0 },
    levels: LEVELS, approvers: [], fulfillment: ff || {}, capabilities: cap || {}, attachments: [], timeline: [] };
}
function stepsOf(html) {
  const out = []; const re = /<div class="step ([a-z]+)"><div class="step-top"><div class="step-dot">[^<]*<\/div><div class="step-name">([^<]*)<\/div>/g; let m;
  while ((m = re.exec(html))) out.push({ state: m[1], name: m[2] });
  return out;
}

// --- 1. stepper: 6 bước + trạng thái bước UNC ---
let s = stepsOf(PR.buildStepper(det({ status: "Assigned", eligible_fulfillers: ["fin1@ec.vn", "fin2@ec.vn"], due_at: "2099-01-01 17:00:00" }, {})));
ok(s.length === 7, "Approved+Assigned: 7 ô (Đã gửi + 4 cấp + UNC + Hoàn tất), có " + s.length);
ok(s[5].name === "Finance xử lý UNC" && s[5].state === "current", "Assigned: bước UNC là current");
ok(s[6].name === "Hoàn tất" && s[6].state === "upcoming", "Assigned: Hoàn tất còn chờ");
let html = PR.buildStepper(det({ status: "Assigned", eligible_fulfillers: ["fin1@ec.vn", "fin2@ec.vn"], due_at: "2099-01-01 17:00:00" }, {}));
ok(/Chờ nhận: fin1@ec.vn hoặc fin2@ec.vn/.test(html), "Assigned: meta liệt kê người đủ điều kiện");
ok(/Hạn: /.test(html) && !/Quá hạn/.test(html), "Assigned: hạn tương lai không đỏ");
html = PR.buildStepper(det({ status: "In Progress", owner: "fin1@ec.vn", due_at: "2020-01-01 17:00:00" }, {}));
ok(/Đang xử lý: fin1@ec.vn/.test(html) && /Quá hạn/.test(html), "In Progress quá hạn: hiện owner + Quá hạn");
s = stepsOf(PR.buildStepper(det({ status: "Completed", completed_by: "fin1@ec.vn", completed_at: "2026-09-07 10:00:00" }, {})));
ok(s[5].state === "done" && s[6].state === "done", "Completed: UNC done + Hoàn tất done");
s = stepsOf(PR.buildStepper(det({}, {})));                         // phiếu duyệt trước khi có bước 6
ok(s[5].state === "skipped" && s[6].state === "done", "Phiếu cũ (không có trạng thái UNC): bước UNC 'không áp dụng', Hoàn tất done");
s = stepsOf(PR.buildStepper(det({ status: "Not Started" }, {}, "Pending")));
ok(s[5].state === "upcoming" && s[6].state === "upcoming", "Pending: UNC + Hoàn tất đều chờ");
// XSS: tên fulfiller do dữ liệu -> phải esc
html = PR.buildStepper(det({ status: "Assigned", eligible_fulfillers: ["<img src=x onerror=1>"] }, {}));
ok(html.indexOf("<img") < 0 && html.indexOf("&lt;img") >= 0, "meta esc tên người xử lý");

// --- 2. thẻ UNC ---
ok(PR.uncCardVisible(det({ status: "Assigned" }, {})) === true, "card hiện khi Assigned");
ok(PR.uncCardVisible(det({}, {})) === false, "card ẩn cho phiếu cũ không có trạng thái");
ok(PR.uncCardVisible(det({ status: "Assigned" }, {}, "Pending")) === false, "card ẩn khi chưa Approved");
html = PR.uncSectionHTML(det({ status: "Assigned", eligible_fulfillers: ["fin1@ec.vn"] }, { can_claim: true }));
ok(/data-act="unc-claim"/.test(html) && !/data-upload="unc"/.test(html), "Assigned + can_claim: nút Nhận xử lý, chưa có form");
html = PR.uncSectionHTML(det({ status: "Assigned" }, { can_claim: false }));
ok(!/unc-claim/.test(html) && /không thuộc nhóm Finance/.test(html), "Assigned + không đủ điều kiện: không có nút, có giải thích");
html = PR.uncSectionHTML(det({ status: "In Progress", owner: "fin1@ec.vn" }, { can_complete: true }));
ok(/data-upload="unc"/.test(html) && /data-act="unc-complete"/.test(html) && /Bắt buộc/.test(html), "In Progress + can_complete: form file UNC (bắt buộc) + Hoàn tất");
html = PR.uncSectionHTML(det({ status: "In Progress", owner: "fin1@ec.vn" }, { can_complete: false }));
ok(!/unc-complete/.test(html) && /Chỉ người đã nhận xử lý/.test(html), "In Progress + người khác: không có form");
html = PR.uncSectionHTML(det({ status: "Completed", completed_by: "fin1@ec.vn", completed_attachment: "/private/files/unc.pdf", summary: "UNC 123" }, {}));
ok(/href="\/private\/files\/unc\.pdf"/.test(html) && /UNC 123/.test(html) && /fin1@ec\.vn/.test(html), "Completed: link file UNC + số UNC + người xử lý");

// --- 3. Hoàn tất chưa có file: báo lỗi, không gọi API ---
PR.state.unc = {};
const before = calls.length;
PR.doUncComplete("EC-PAYR-2026-00001");
const t = els["ec-payr-toast"] || Object.values(els).find((e) => /file UNC/.test(e.textContent || ""));
ok(calls.length === before, "chưa tải file: KHÔNG gọi complete_fulfillment");
ok(!!t && /đính kèm file UNC/.test(t.textContent), "chưa tải file: toast nói rõ cần file UNC");

// --- 4. preview + stepLabel ---
ok(/Finance xử lý UNC/.test(SRC.match(/function processPreviewHTML\(\)[\s\S]*?return /)[0]), "preview quy trình có bước 6");
ok(PR.stepLabel({ total_levels: 4, approval_status: "Approved", fulfillment_status: "Assigned" }) === "Bước 6/7 · Finance xử lý UNC", "stepLabel Assigned = 6/7 UNC");
ok(PR.stepLabel({ total_levels: 4, approval_status: "Approved", fulfillment_status: "Completed" }) === "Bước 7/7 · Hoàn tất", "stepLabel Completed = 7/7");
ok(PR.stepLabel({ total_levels: 4, approval_status: "Pending", current_level: 2, current_level_name: "Finance review" }) === "Bước 3/7 · Finance review", "stepLabel Pending N=7");

console.log(`${pass} đạt, ${fail} hỏng`);
if (pass < 24) { console.log("HONG: so phep kiem thap bat thuong (" + pass + ")"); process.exit(1); }
process.exit(fail ? 1 : 0);
