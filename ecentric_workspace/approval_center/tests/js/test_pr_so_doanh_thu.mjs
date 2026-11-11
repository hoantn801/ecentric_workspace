// Copyright (c) 2026, eCentric and contributors
// DNTT nguon hop dong KOL/KOC: o "SO doanh thu" (12/11/2026, Hoan: SO gan vao payment request
// de Ke toan doi chieu). Chay CODE THAT cua trang qua vm. Kiem: o SO bat buoc khi nguon la hop
// dong KOL va CHI khi do; vuot doanh thu / SO chua co doanh thu / lech brand chi CANH BAO; nhan
// so du nguon KOL la "Duoc chi hien tai"; ten SO duoc esc.
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = path.join(HERE, "..", "..", "features", "payment_request", "ui", "main_section.html");
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
if (!PR || typeof PR.soHintHTML !== "function" || typeof PR.validateSubmit !== "function") {
  console.log("FAIL: PaymentRequest.soHintHTML/validateSubmit not exported"); process.exit(1); }
PR.state.boot = { tabs: {}, context: { user: "a@ec.vn" }, form_options: {} };
const KOL = "EC Contract Review Request";
const SO = { value: "SO-1", label: "SO-1 · Brand A", brand: "Brand A", revenue: 10000000, spent: 6000000 };

// --- 1. goi y SO ---
let h = PR.soHintHTML({});
ok(/Chưa chọn/.test(h) && /GBS SO/.test(h), "chua chon: huong dan go ma GBS SO");
PR.state._so = SO;
h = PR.soHintHTML({ ec_sales_order: "SO-1", payment_amount: 3000000, ec_brand: "Brand A" });
ok(/doanh thu EC 10\.000\.000đ/.test(h) && !/banner warn/.test(h), "trong doanh thu, cung brand: khong canh bao");
h = PR.soHintHTML({ ec_sales_order: "SO-1", payment_amount: 5000000, ec_brand: "Brand A" });
ok(/vượt doanh thu EC 1\.000\.000đ/.test(h) && /vẫn gửi được/i.test(h), "vuot doanh thu: chi canh bao, neu so vuot");
h = PR.soHintHTML({ ec_sales_order: "SO-1", payment_amount: 1, ec_brand: "Brand B" });
ok(/khác brand của đề nghị/.test(h), "SO lech brand voi de nghi: canh bao");
PR.state._so = Object.assign({}, SO, { revenue: 0 });
h = PR.soHintHTML({ ec_sales_order: "SO-1", payment_amount: 1 });
ok(/chưa ghi doanh thu EC/.test(h) && !/vượt doanh thu/.test(h), "SO chua co doanh thu: noi ro, khong bao 'vuot'");
PR.state._so = { value: "SO-2", label: "<img src=x>", revenue: 1, spent: 0 };
h = PR.soHintHTML({ ec_sales_order: "SO-2" });
ok(h.indexOf("<img") < 0 && h.indexOf("&lt;img") >= 0, "ten SO duoc esc");
PR.state._so = SO;
h = PR.soHintHTML({ ec_sales_order: "SO-9" });
ok(/Đã chọn: <b>SO-9<\/b>/.test(h), "SO dang gan khac SO da tai: chi hien ma (khong lay so cua SO khac)");

// --- 2. nhan so du nguon ---
PR.state._fundSummary = { total: 4000000, used: 0, remaining: 4000000 };
PR.state.draft = { funding_source_doctype: KOL, payment_amount: 1 };
ok(/Được chi hiện tại \(cọc \+ BBNT hoàn tất\)/.test(PR.fundingHintHTML()), "nguon KOL: nhan 'Duoc chi hien tai'");
PR.state.draft = { funding_source_doctype: "EC Purchase Request", payment_amount: 1 };
ok(/>Tổng: /.test(PR.fundingHintHTML()), "nguon khac: giu nhan 'Tong'");

// --- 3. bat buoc SO chi khi nguon la hop dong KOL ---
const base = { reason: "x", payment_amount: 1000, payment_date: "2026-12-01", payee_full_name: "A",
  account_bank: "VCB", bank_account_number: "1", has_purchase_request: "Yes", details_and_attachments_correct: "Yes",
  funding_source_name: "CR-1" };
PR.state.draft = Object.assign({}, base, { funding_source_doctype: KOL });
let v = PR.validateSubmit() || {};
ok(!!v.ec_sales_order, "nguon KOL chua chon SO: loi o SO");
PR.state.draft = Object.assign({}, base, { funding_source_doctype: KOL, ec_sales_order: "SO-1" });
v = PR.validateSubmit() || {};
ok(!v.ec_sales_order, "nguon KOL da chon SO: het loi o SO");
PR.state.draft = Object.assign({}, base, { funding_source_doctype: "EC Purchase Request", funding_source_name: "PURR-1" });
v = PR.validateSubmit() || {};
ok(!v.ec_sales_order, "nguon khac: khong doi SO");

// --- 4. o loi SO co trong danh sach truong de cuon / to do ---
ok(/var FIELD_IDS=\[[^\]]*"ec_sales_order"/.test(SRC), "FIELD_IDS co ec_sales_order (loi SO duoc to do / cuon toi)");

console.log(`${pass} dat, ${fail} hong`);
if (pass < 13) { console.log("HONG: so phep kiem thap bat thuong (" + pass + ")"); process.exit(1); }
process.exit(fail ? 1 : 0);
