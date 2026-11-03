// QA 03/11/2026 (t2_forms) - logic 2 form GBS (/gbs-so-form-v2, /gbs-po-form-v2): chay CA trang
// main_section.html trong jsdom, gia lap fetch, roi bam nut that.
//     node ecentric_workspace/approval_center/tests/js/test_gbs_forms_logic.mjs
// Moi phep o day da HONG tren main 359c41f (truoc ban sua) - xem qa_0311/t2_forms.md.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let JSDOM, VirtualConsole;
try { ({ JSDOM, VirtualConsole } = require("jsdom")); }
catch (e) {
  // Khong co jsdom = KHONG CHAY DUOC (khac voi hong). Bao ro, khong gia vo "dat".
  console.log("BO QUA (khong chay phep nao): thieu goi jsdom - cai jsdom hoac dat NODE_PATH roi chay lai");
  process.exit(0);
}

const here = dirname(fileURLToPath(import.meta.url));
const LP = join(here, "..", "..", "..", "legacy_pages");
const SO = readFileSync(join(LP, "gbs_so_form_v2", "main_section.html"), "utf8");
const PO = readFileSync(join(LP, "gbs_po_form_v2", "main_section.html"), "utf8");

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function load(html, url, routes, opts = {}) {
  const calls = [], alerts = [], errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => errors.push(String((e && e.message) || e)));
  const dom = new JSDOM("<!DOCTYPE html><html><head></head><body>" + html + "</body></html>", {
    url, runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      w.Response = globalThis.Response;
      w.alert = (m) => alerts.push(String(m));
      w.confirm = (m) => { alerts.push("CONFIRM:" + m); return true; };
      w.HTMLElement.prototype.scrollIntoView = function () {};
      w.frappe = { session: { user: "kam@ecentric.vn" }, csrf_token: "t" };
      for (const [k, v] of Object.entries(opts.session || {})) w.sessionStorage.setItem(k, v);
      for (const [k, v] of Object.entries(opts.local || {})) w.localStorage.setItem(k, v);
      w.fetch = (u, o) => {
        const url = typeof u === "string" ? u : (u && u.url) || "";
        calls.push({ url, body: o && o.body, method: (o && o.method) || "GET" });
        for (const [re, fn] of routes) {
          if (!re.test(url)) continue;
          const r = fn(url, o) || {};
          const status = r.__status || 200;
          const body = JSON.stringify(r.__status ? r.body : r);
          const resp = () => new globalThis.Response(body, { status, headers: { "Content-Type": "application/json" } });
          return r.__delay ? new Promise((res) => setTimeout(() => res(resp()), r.__delay)) : Promise.resolve(resp());
        }
        return Promise.resolve(new globalThis.Response(JSON.stringify({ message: {} }), { status: 200 }));
      };
    },
  });
  return { dom, w: dom.window, d: dom.window.document, calls, alerts, errors, close: () => dom.window.close() };
}
const BRAND = [/web_lookup/, (u, o) => (JSON.parse(o.body).type === "brand"
  ? { success: true, items: [{ id: "WIL", title: "Wilmar", brand_name: "Wilmar", finance_email: "f@x" }] }
  : { success: true, items: [] })];
const click = (env, el) => el.dispatchEvent(new env.w.MouseEvent("click", { bubbles: true, cancelable: true }));
const posted = (env, re) => env.calls.filter((c) => re.test(c.url) && c.method === "POST");
function addOpt(env, id, v) { const s = env.d.getElementById(id); const o = env.d.createElement("option"); o.value = v; o.textContent = v; s.appendChild(o); s.value = v; }
function fillRow(env, code, qty, rate) {
  const tr = [...env.d.querySelectorAll("#itemsBody tr")].pop();
  tr.querySelector(".item-code").value = code;
  tr.querySelector(".item-qty").value = String(qty);
  tr.querySelector(".item-rate").value = String(rate);
}

// ---------------------------------------------------------------- PO ?from_so=
console.log("PO tu SO (?from_so=)");
{ // sessionStorage con payload cua SO KHAC -> khong duoc dien du lieu SO cu
  const stale = JSON.stringify({ parent_so: "GBS-SO-A", so: { so_title: "SO A", brand_code: "AAA" }, items: [{ item_code: "ITEM-A", qty: 2, rate: 1000 }], item_codes: ["ITEM-A"] });
  const env = load(PO, "https://t.example/gbs-po-form-v2?from_so=GBS-SO-B", [BRAND,
    [/gbs_so_create_po_helper/, () => ({ message: { success: true, so: { so_title: "SO B", brand_code: "WIL" }, items: [{ item_code: "ITEM-B", qty: 1, rate: 5 }] } })]],
    { session: { gbs_po_from_so: stale } });
  await sleep(2600);
  const codes = [...env.d.querySelectorAll("#itemsBody .item-code")].map((e) => e.value).filter(Boolean);
  ok(env.d.getElementById("title").value === "SO B — PO", "payload sessionStorage cua SO khac phai bi bo (title=" + env.d.getElementById("title").value + ")");
  ok(codes.join() === "ITEM-B", "items phai lay tu SO trong URL, khong lay ITEM-A cua SO cu (" + codes + ")");
  env.close();
}
{ // ?from_so= chen HTML -> khong duoc thanh the that (XSS)
  const evil = '<img src=x id=pwn onerror="window.__pwn=1">';
  const pl = JSON.stringify({ parent_so: evil, so: { so_title: "X" }, items: [], item_codes: [] });
  const env = load(PO, "https://t.example/gbs-po-form-v2?from_so=" + encodeURIComponent(evil), [BRAND], { session: { gbs_po_from_so: pl } });
  await sleep(1200);
  ok(!env.d.getElementById("pwn"), "from_so trong banner phai duoc escape");
  ok((env.d.querySelector(".ec-from-so-banner") || {}).textContent.indexOf("<img") >= 0, "banner hien nguyen van chuoi");
  env.close();
}
{ // from_so = SO so EC, mo lai trang (khong con sessionStorage) -> khong bao "Loi load SO"
  const env = load(PO, "https://t.example/gbs-po-form-v2?from_so=SAL-ORD-2026-00001", [BRAND]);
  await sleep(1500);
  ok(!env.alerts.some((a) => /Lỗi load SO/.test(a)), "SO so EC: khong goi helper GBS roi bao loi (" + env.alerts.join("|") + ")");
  env.close();
}

// ---------------------------------------------------------------- PO GBS submit
console.log("PO GBS: nut Submit");
async function poGbsReady(routes) {
  const env = load(PO, "https://t.example/gbs-po-form-v2?mode=gbsbuy", [BRAND, ...routes]);
  await sleep(900);
  env.d.getElementById("title").value = "PO test";
  addOpt(env, "brand", "WIL"); addOpt(env, "supplier", "SUP-1"); addOpt(env, "project", "PRJ-1"); addOpt(env, "department", "Service");
  env.w._ecAttachments = [{ name: "a.pdf", size: 1, mime: "application/pdf", content_base64: "AA==" }];
  return env;
}
{
  const env = await poGbsReady([]);
  fillRow(env, "ITEM-1", 0, "1.000");
  click(env, env.d.getElementById("submitBtn"));
  await sleep(300);
  ok(posted(env, /submit_gbs_po/).length === 0, "SL = 0 phai bi chan truoc khi gui");
  ok(/số lượng phải lớn hơn 0/.test(env.d.getElementById("toastText").textContent), "bao ro dong nao SL <= 0");
  env.close();
}
{
  const env = await poGbsReady([[/submit_gbs_po/, () => ({ __status: 417, body: { exc_type: "ValidationError", _server_messages: JSON.stringify([JSON.stringify({ message: "Supplier SUP-1 bi khoa" })]) } })]]);
  fillRow(env, "ITEM-1", 2, "1.000");
  const btn = env.d.getElementById("submitBtn");
  click(env, btn);
  await sleep(500);
  ok(posted(env, /submit_gbs_po/).length === 1, "gui 1 lan");
  ok(/Supplier SUP-1 bi khoa/.test(env.d.getElementById("toastText").textContent), "loi Frappe 417 phai hien _server_messages, khong 'Submit failed' (" + env.d.getElementById("toastText").textContent + ")");
  ok(!btn.disabled && /Submit yêu cầu/.test(btn.textContent) && btn.querySelector("svg"), "nut mo lai voi nhan + icon goc");
  const body = JSON.parse(posted(env, /submit_gbs_po/)[0].body);
  ok(body.brand_name === "Wilmar", "brand_name la ten brand, khong phai 'MA — Ten' (" + body.brand_name + ")");
  env.close();
}

// ---------------------------------------------------------------- PO ecbuy
console.log("PO Mua ngoai (so EC)");
{
  let wf = 0;
  const env = load(PO, "https://t.example/gbs-po-form-v2?mode=ecbuy", [BRAND,
    [/ec_so_lookups/, () => ({ message: { items: [{ item_code: "EC-1", item_name: "Phi", stock_uom: "Nos" }], suppliers: [{ name: "SUP-EC", supplier_name: "A <b>& B</b>" }], recent_sos: [{ name: "SAL-ORD-1", customer: "C", ec_channel: "Direct", grand_total: 1 }] } })],
    [/ec_po_budget_check/, () => ({ message: { has_so: true, used: 0, so_total: 1e9 } })],
    [/\/api\/resource\/Purchase Order\/PUR-1/, () => ({ data: { name: "PUR-1", modified: "2" } })],
    [/\/api\/resource\/Purchase Order/, () => ({ data: { name: "PUR-1", modified: "1" } })],
    [/apply_workflow/, () => (++wf === 1 ? { __status: 417, body: { exception: "frappe.exceptions.ValidationError: Thieu nguoi duyet" } } : { message: { name: "PUR-1", ec_in_out_budget: "In Budget" } })]]);
  await sleep(1800);
  ok(!env.d.querySelector("#ecSupplier b"), "ten NCC tu server phai duoc escape trong <option>");
  env.d.getElementById("title").value = "Mua KOC";
  env.d.getElementById("ecSupplier").value = "SUP-EC";
  env.d.getElementById("ecSoRef").value = "SAL-ORD-1";
  fillRow(env, "EC-1", 1, "0");
  const btn = env.d.getElementById("submitBtn");
  click(env, btn);
  await sleep(300);
  ok(posted(env, /\/api\/resource\/Purchase Order/).length === 0 && /Thiếu SL hoặc giá/.test(env.d.getElementById("ecUniBadge").textContent),
     "dong co ma item nhung gia 0 phai bi chan, khong bo qua im lang");
  fillRow(env, "EC-1", 1, "1.000");
  click(env, btn);
  await sleep(400);
  ok(/chưa gửi duyệt/.test(env.d.getElementById("ecUniBadge").textContent) && !btn.disabled, "trinh duyet loi -> bao PO da tao + mo lai nut");
  click(env, btn);
  await sleep(500);
  ok(posted(env, /\/api\/resource\/Purchase Order/).length === 1, "bam lai sau loi trinh duyet KHONG tao PO thu hai (POST=" + posted(env, /\/api\/resource\/Purchase Order/).length + ")");
  ok(wf === 2 && /Đã tạo \+ gửi duyệt PO sổ EC: PUR-1/.test(env.d.getElementById("ecUniBadge").textContent), "lan 2 chi trinh duyet lai PUR-1");
  env.close();
}

// ---------------------------------------------------------------- SO so EC (Brand truc tiep)
console.log("SO Brand truc tiep (so EC)");
{
  const env = load(SO, "https://t.example/gbs-so-form-v2?mode=direct", [BRAND,
    [/ec_so_lookups/, () => ({ message: { items: [{ item_code: "REV-1", item_name: "Phi" }], customers_all: [{ name: "CUS-X", customer_name: "K" }, { name: 'CUS-Q" data-pwn="1', customer_name: "A & B" }], contracts: [], cust_brands: [] } })],
    [/gbs_list_so_lookups/, () => ({ message: { success: true, stores: [{ name: 'V1" data-pwn="2', store_name: "S" }], price_lists: [], taxes_templates: [], order_types: [] } })],
    [/create_so_from_form/, () => ({ message: { success: true, name: "SAL-ORD-9" } })]]);
  await sleep(1800);
  ok(!env.d.querySelector("#ecExtCustomer [data-pwn]"), "ma khach co dau \" khong duoc pha thuoc tinh <option>");
  click(env, env.d.querySelector('.ec-uni-btn[data-m="gbsrev"]'));
  await sleep(200);
  ok(!env.d.querySelector("#ec-store [data-pwn]") && env.d.getElementById("ec-store").options.length > 1, "ma store tu boxme co dau \" khong duoc pha thuoc tinh <option>");
  click(env, env.d.querySelector('.ec-uni-btn[data-m="direct"]'));
  await sleep(200);
  env.d.getElementById("ecExtSvc").checked = true;
  env.d.getElementById("ecExtCustomer").value = "CUS-X";
  env.d.getElementById("title").value = "Booking fee";
  fillRow(env, "REV-1", 1, "0");
  click(env, env.d.getElementById("submitBtn"));
  await sleep(300);
  ok(posted(env, /create_so_from_form/).length === 0 && /Thi\u1ebfu SL ho\u1eb7c gi\u00e1/.test(env.d.getElementById("ecUniBadge").textContent),
     "dong co ma item nhung gia 0 phai bi chan, khong bo qua im lang (" + env.d.getElementById("ecUniBadge").textContent + ")");
  env.close();
}

// ---------------------------------------------------------------- Sua & gui lai
console.log("Sua & gui lai");
function editDoc(dt, extra) {
  return Object.assign({ name: "X", status: "Cần sửa", title: "T", department: "Service", brand_code: "WIL",
    transaction_date: "2026-11-01", set_warehouse: "WH-1", attachment_url: "", items: [{ item_code: "IT-1", qty: 2, rate: 1000, warehouse: "WH-1" }] }, extra);
}
async function editEnv(html, url, doc, routes = []) {
  const env = load(html, url, [BRAND, [/\/api\/resource\/GBS(%20| )(Sales|Purchase)(%20| )Order\//, () => ({ data: doc })],
    [/resubmit_gbs_/, () => ({ message: { success: true, status: "Pending", current_level: 1, revision_count: 1 } })], ...routes]);
  await sleep(2600);
  return env;
}
{ // SO: priority + file moi + race thue
  const doc = editDoc("so", { so_title: "SO sua", customer: "CUS-1", delivery_date: "2026-11-05", priority: "", taxes_template: "VAT 10%", price_list: "PL-X" });
  const env = await editEnv(SO, "https://t.example/gbs-so-form-v2?edit=GBS-SO-1", doc,
    [[/gbs_list_so_lookups/, () => ({ __delay: 2200, message: { success: true, price_lists: [{ name: "Standard Selling" }], taxes_templates: [{ name: "GBS - VAT 8%", tax_rate: 8 }, { name: "VAT 10%", tax_rate: 10 }], order_types: [], stores: [] } })]]);
  await sleep(1200);
  ok(env.d.getElementById("ec-taxes-template").value === "VAT 10%", "lookups ve cham khong duoc de mac dinh 8% len thue cua phieu dang sua (" + env.d.getElementById("ec-taxes-template").value + ")");
  ok(env.d.getElementById("ec-price-list").value === "PL-X", "price list cua phieu giu nguyen");
  env.w._gbsUploadedFiles = { "moi.pdf": { status: "done", webUrl: "https://sp/moi.pdf" } };
  env.w._ecAttachments = [{ name: "moi.pdf", size: 1 }];   // ec-attachment-fix ghi song song khi chon file
  click(env, env.d.getElementById("submitBtn"));
  await sleep(300);
  const p = posted(env, /resubmit_gbs_so/);
  ok(p.length === 1, "resubmit duoc goi (" + env.alerts.join("|") + ")");
  if (p.length) {
    const b = JSON.parse(p[0].body);
    ok(b.priority === "Normal", "priority rong -> 'Normal', khong gui 'Medium' (" + b.priority + ")");
    ok(Array.isArray(b.attachment_urls_v2) && b.attachment_urls_v2[0] && b.attachment_urls_v2[0].webUrl === "https://sp/moi.pdf" && b.attachment_urls_v2[0].name === "moi.pdf",
       "file moi gui dang {name, webUrl} nhu luong tao moi (" + JSON.stringify(b.attachment_urls_v2) + ")");
  }
  env.close();
}
{ // SO: pill uu tien theo phieu
  const env = await editEnv(SO, "https://t.example/gbs-so-form-v2?edit=GBS-SO-2", editDoc("so", { customer: "CUS-1", delivery_date: "2026-11-05", priority: "Urgent", attachment_url: "https://sp/cu.pdf" }));
  const sel = env.d.querySelector("#ec-pri-wrap .ec-pri-selected");
  ok(sel && sel.getAttribute("data-pri") === "Urgent", "phieu Urgent -> pill hien Urgent");
  env.close();
}
{ // PO: ngay can hang truoc ngay giao dich + file dang tai -> chan
  const env = await editEnv(PO, "https://t.example/gbs-po-form-v2?edit=GBS-PO-1",
    editDoc("po", { po_title: "PO sua", supplier: "SUP-1", schedule_date: "2026-10-20", attachment_url: "https://sp/cu.pdf", items: [{ item_code: "IT-1", qty: 2, rate: 1000, sales_order: "GBS-SO-9" }] }));
  click(env, env.d.getElementById("submitBtn"));
  await sleep(300);
  ok(posted(env, /resubmit_gbs_po/).length === 0 && env.alerts.some((a) => /Ngày cần hàng/.test(a)), "ngay can hang < ngay giao dich phai bi chan o 'Sua & gui lai' (" + env.alerts.join("|") + ")");
  env.d.getElementById("schedule_date").value = "2026-11-20";
  env.w._gbsUploadedFiles = { "dang.pdf": { status: "uploading", progress: 40 } };
  click(env, env.d.getElementById("submitBtn"));
  await sleep(300);
  ok(posted(env, /resubmit_gbs_po/).length === 0, "file dang tai len -> chua gui lai");
  env.w._gbsUploadedFiles = {};
  click(env, env.d.getElementById("submitBtn"));
  await sleep(300);
  const p = posted(env, /resubmit_gbs_po/);
  ok(p.length === 1 && JSON.parse(p[0].body).items[0].sales_order === "GBS-SO-9", "gui lai giu SO cua tung dong");
  env.close();
}

console.log("  " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
