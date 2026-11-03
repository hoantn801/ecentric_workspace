// UX 03/11/2026 (ux_so) - form tao/sua SO GBS (/gbs-so-form-v2): kiem tra gom loi canh truong, trang thai
// nut, chan roi trang, luu/khoi phuc nhap, nho lua chon theo brand, ban phim (uu tien, combobox).
// Nap CA trang main_section.html trong jsdom, gia lap fetch, bam nut that.
//     node ecentric_workspace/approval_center/tests/js/test_gbs_so_form_ux.mjs
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
// Hen gio con treo cua trang (vd loadClients().then(...)) chay SAU khi dong window -> 'document' undefined.
// Do la tieng on luc don dep cua jsdom, khong phai loi trang: bo qua de khong lam sap ca bo test.
process.on("unhandledRejection", () => {});
let JSDOM, VirtualConsole;
try { ({ JSDOM, VirtualConsole } = require("jsdom")); }
catch (e) {
  console.log("BO QUA (khong chay phep nao): thieu goi jsdom - cai jsdom hoac dat NODE_PATH roi chay lai");
  process.exit(0);
}

const here = dirname(fileURLToPath(import.meta.url));
const SO_PATH = join(here, "..", "..", "..", "legacy_pages", "gbs_so_form_v2", "main_section.html");
const SO = readFileSync(SO_PATH, "utf8");

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function load(url, routes, opts = {}) {
  const calls = [], alerts = [], confirms = [], errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => { const m = String((e && e.message) || e); if (!/navigation/i.test(m)) errors.push(m); });
  const dom = new JSDOM("<!DOCTYPE html><html><head></head><body>" + SO + "</body></html>", {
    url, runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    beforeParse(w) {
      w.Response = globalThis.Response;
      w.alert = (m) => alerts.push(String(m));
      w.confirm = (m) => { confirms.push(String(m)); return opts.confirm !== false; };
      w.HTMLElement.prototype.scrollIntoView = function () { w.__scrolled = this; };
      w.frappe = { session: { user: "kam@ecentric.vn" }, csrf_token: "t" };
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
  return { w: dom.window, d: dom.window.document, calls, alerts, confirms, errors, close: () => dom.window.close() };
}
const BRAND = [/web_lookup/, (u, o) => (JSON.parse(o.body).type === "brand"
  ? { success: true, items: [{ id: "WIL", title: "Wilmar", brand_name: "Wilmar" }] } : { success: true, items: [] })];
const LOOKUPS = [/gbs_list_so_lookups/, () => ({ message: { success: true, order_types: ["Sales"], price_lists: [{ name: "Standard Selling" }],
  taxes_templates: [{ name: "GBS - VAT 8%", tax_rate: 8 }], stores: [] } })];
const BUDGET = [/ec_so_budget_check/, () => ({ message: { has_mso: true, mso: "MSO-1", used_ops: 0, budget_ops: 1e12, used_fee: 0, budget_fee: 1e12 } })];
const EC_LK = [/ec_so_lookups/, () => ({ message: { items: [{ item_code: "REV-1", item_name: "Phi", item_group: "Phí agency EC" }],
  customers_all: [{ name: "CUS-X", customer_name: "K" }], contracts: [], cust_brands: [{ name: "CUS-WIL", ec_brand: "WIL" }] } })];
const click = (env, el) => el.dispatchEvent(new env.w.MouseEvent("click", { bubbles: true, cancelable: true }));
const key = (env, el, k) => el.dispatchEvent(new env.w.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
const posted = (env, re) => env.calls.filter((c) => re.test(c.url) && c.method === "POST");
const $ = (env, id) => env.d.getElementById(id);
function addOpt(env, id, v) { const s = $(env, id); const o = env.d.createElement("option"); o.value = v; o.textContent = v; s.appendChild(o); }
function pick(env, id, v) { addOpt(env, id, v); const s = $(env, id); s.value = v; s.dispatchEvent(new env.w.Event("change", { bubbles: true })); }
function fillRow(env, code, qty, rate) {
  const tr = [...env.d.querySelectorAll("#itemsBody tr")].pop();
  tr.querySelector(".item-code").value = code;
  tr.querySelector(".item-qty").value = String(qty);
  tr.querySelector(".item-rate").value = String(rate);
}
const toast = (env) => ($(env, "toastText").textContent || "");
const hasErr = (env, id) => { const f = $(env, id) && $(env, id).closest(".field"); return !!(f && f.classList.contains("has-error")); };

// ---------------------------------------------------------------- A65: khong them khoi script/style id moi
console.log("A65 / markup");
{
  const tags = SO.match(/<(script|style) id="ec-[^"]*"/g) || [];
  ok(tags.length <= 21, "khong them <script|style id=\"ec-...\"> moi (dang co " + tags.length + ", moc 21)");
  ok(!/<(script|style) id="ec-[^"]*ux/i.test(SO), "khong co khoi id 'ux' chen them");
  const env = load("https://t.example/gbs-so-form-v2?mode=gbsrev", [BRAND, LOOKUPS]);
  ok(!env.d.documentElement.hasAttribute("data-ec-so-draft"), "khong co nhap -> khong hien thanh khoi phuc");
  ok(env.d.querySelectorAll("#ec-pri-wrap button.ec-pri-opt[role=radio]").length === 2, "muc uu tien la 2 nut radio (Tab duoc)");
  ok(!/Status/.test(env.d.querySelector(".form-section").textContent), "bo o 'Status: Pending' (chi doc, khong co tac dung)");
  env.close();
  const env2 = load("https://t.example/gbs-so-form-v2", [BRAND], { local: { ec_gbs_so_draft_v1: JSON.stringify({ v: 1, fields: {}, items: [] }) } });
  ok(env2.d.documentElement.getAttribute("data-ec-so-draft") === "1", "co nhap -> <html data-ec-so-draft> dat TU DAU TRANG (truoc khi ve)");
  env2.close();
  const env3 = load("https://t.example/gbs-so-form-v2?edit=GBS-SO-1", [BRAND], { local: { ec_gbs_so_draft_v1: "{}" } });
  ok(env3.d.documentElement.hasAttribute("data-ec-so-edit") && !env3.d.documentElement.hasAttribute("data-ec-so-draft"), "che do sua: an Luu nhap/khoi phuc nhap");
  env3.close();
}

// ---------------------------------------------------------------- GBS: form trong -> 1 lan bao het
console.log("GBS thu Brand: kiem tra gom");
{
  const env = load("https://t.example/gbs-so-form-v2?mode=gbsrev", [BRAND, LOOKUPS, BUDGET,
    [/submit_gbs_so/, () => ({ __delay: 100, message: { success: true, name: "GBS-SO-77" } })]]);
  await sleep(1800);
  $(env, "ec-price-list").value = "";
  click(env, $(env, "submitBtn"));
  await sleep(200);
  ok(posted(env, /submit_gbs_so/).length === 0, "form trong khong duoc gui");
  ok(env.alerts.length === 0, "khong con alert() tung cai mot (" + env.alerts.join(" | ") + ")");
  const t = toast(env);
  ok(/Còn \d+ mục cần sửa/.test(t) && /Tiêu đề/.test(t) && /Khách hàng/.test(t) && /Project/.test(t) && /Order Type/.test(t) && /Chứng từ/.test(t),
     "toast liet ke MOT lan moi muc thieu (" + t + ")");
  ok(hasErr(env, "title") && hasErr(env, "brand") && hasErr(env, "customer") && hasErr(env, "set_warehouse") && hasErr(env, "project")
     && hasErr(env, "ec-order-type") && hasErr(env, "ec-price-list"), "to do tung o thieu");
  ok($(env, "title").closest(".field").querySelector(".error-msg").textContent === "Nhập tiêu đề", "chu loi ngay duoi o");
  ok($(env, "ecItemsErr").classList.contains("ec-show") && $(env, "uploadZone").classList.contains("ec-has-err"), "bao loi dong hang + dinh kem");
  ok(env.w.__scrolled === $(env, "title").closest(".field"), "cuon toi o loi dau tien");
  ok(env.d.activeElement === $(env, "title"), "focus o loi dau tien");
  $(env, "title").value = "SO test";
  $(env, "title").dispatchEvent(new env.w.Event("input", { bubbles: true }));
  ok(!hasErr(env, "title"), "go vao o -> het to do o do");
  // dien du -> gui that, nut dang gui / da gui + link phieu
  pick(env, "brand", "WIL"); pick(env, "customer", "CUS-1"); pick(env, "set_warehouse", "WH-1"); pick(env, "project", "PRJ-1");
  pick(env, "ec-order-type", "Sales"); pick(env, "ec-price-list", "Standard Selling");
  fillRow(env, "IT-1", 2, "1.000");
  env.w._ecAttachments = [{ name: "a.pdf", size: 1, mime: "application/pdf", content_base64: "AA==" }];
  await sleep(800);   // MSO check
  click(env, $(env, "submitBtn"));
  await sleep(10);
  const btn = $(env, "submitBtn");
  ok(btn.disabled && /Đang gửi/.test(btn.textContent), "dang gui: nut khoa + chu 'Dang gui' (" + btn.textContent.trim() + ")");
  await sleep(400);
  ok(posted(env, /submit_gbs_so/).length === 1, "du thong tin -> gui 1 lan (toast: " + toast(env) + " | alerts: " + env.alerts.join("|") + ")");
  ok(/Đã gửi: GBS-SO-77/.test(btn.textContent), "gui xong: nut hien ma phieu (" + btn.textContent.trim() + ")");
  const a = $(env, "toast").querySelector("a.ec-toast-link");
  ok(a && /\/approval\?id=GBS-SO-77&type=gbs_so/.test(a.getAttribute("href")), "toast co link mo phieu");
  const mem = JSON.parse(env.w.localStorage.getItem("ec_gbs_so_mem_v1") || "{}");
  ok(mem["gbsrev|WIL"] && mem["gbsrev|WIL"].customer === "CUS-1" && mem["gbsrev|WIL"].project === "PRJ-1", "nho khach/project theo brand sau khi gui thanh cong");
  env.close();
}

// ---------------------------------------------------------------- so EC: form trong + gui that
console.log("Brand truc tiep (so EC)");
{
  const env = load("https://t.example/gbs-so-form-v2?mode=direct", [BRAND, EC_LK, BUDGET,
    [/create_so_from_form/, () => ({ __delay: 100, message: { success: true, name: "SAL-ORD-5", ec_in_out_budget: "In Budget" } })]]);
  await sleep(1800);
  click(env, $(env, "submitBtn"));
  await sleep(200);
  ok(posted(env, /create_so_from_form/).length === 0, "form trong khong tao SO");
  const t = toast(env);
  ok(/Tiêu đề/.test(t) && /Brand/.test(t) && /Dòng hàng/.test(t) && /Chứng từ/.test(t), "liet ke het muc thieu (" + t + ")");
  ok(!hasErr(env, "customer") && !hasErr(env, "project"), "so EC khong doi Khach/Project (truong cua GBS)");
  ok(/Còn/.test($(env, "ecUniBadge").textContent), "badge che do cung bao");
  $(env, "title").value = "Booking fee";
  pick(env, "brand", "WIL");
  fillRow(env, "REV-1", 1, "2.000.000");
  env.w._ecRawFiles = { "a.pdf": { name: "a.pdf" } };
  await sleep(1200);
  click(env, $(env, "submitBtn"));
  await sleep(5);
  const btn = $(env, "submitBtn");
  ok(btn.disabled && /Đang tạo SO/.test(btn.textContent), "dang tao: nut khoa + chu (" + btn.textContent.trim() + ")");
  await sleep(400);
  ok(posted(env, /create_so_from_form/).length === 1, "du thong tin -> tao SO (" + $(env, "ecUniBadge").textContent + ")");
  ok(/Đã tạo: SAL-ORD-5/.test(btn.textContent), "tao xong: nut hien ma (" + btn.textContent.trim() + ")");
  const a = $(env, "toast").querySelector("a.ec-toast-link");
  ok(a && /\/approval\?id=SAL-ORD-5&type=so/.test(a.getAttribute("href")), "toast co link mo phieu");
  ok(!$(env, "ecUniBadge").textContent.startsWith("Còn"), "badge khong con loi cu");
  env.close();
}
{ // tao loi -> nut tro lai nguyen nhan + icon
  const env = load("https://t.example/gbs-so-form-v2?mode=direct", [BRAND, EC_LK, BUDGET,
    [/create_so_from_form/, () => ({ __status: 417, body: { exception: "frappe.exceptions.ValidationError: Thieu nguoi duyet" } })]]);
  await sleep(1800);
  $(env, "title").value = "Booking fee"; pick(env, "brand", "WIL"); fillRow(env, "REV-1", 1, "2.000.000");
  env.w._ecRawFiles = { "a.pdf": { name: "a.pdf" } };
  await sleep(1200);
  const btn = $(env, "submitBtn");
  click(env, btn);
  await sleep(400);
  ok(!btn.disabled && /Submit yêu cầu/.test(btn.textContent) && btn.querySelector("svg") && !btn.classList.contains("loading"), "loi -> nut mo lai, dung nhan + icon");
  ok(/Thieu nguoi duyet/.test($(env, "ecUniBadge").textContent), "loi may chu van hien");
  env.close();
}

// ---------------------------------------------------------------- nhap + roi trang
console.log("Luu nhap / khoi phuc / roi trang");
{
  const env = load("https://t.example/gbs-so-form-v2?mode=direct", [BRAND, EC_LK, BUDGET]);
  await sleep(1500);
  const ev = () => { const e = new env.w.Event("beforeunload", { cancelable: true }); env.w.dispatchEvent(e); return e.defaultPrevented; };
  ok(!ev(), "chua nhap gi -> roi trang khong hoi");
  env.w.ecSoUx.markDirty();
  ok(ev(), "dang nhap do -> trinh duyet hoi truoc khi roi trang");
  $(env, "title").value = "Nhap SO";
  pick(env, "brand", "WIL");
  fillRow(env, "REV-1", 3, "1.500.000");
  click(env, $(env, "btnDraft"));
  ok(!/Không lưu được/.test(toast(env)) && /Đã lưu nháp/.test(toast(env)), "Luu nhap khong con loi 'Cannot read properties of null' (" + toast(env) + ")");
  const dr = JSON.parse(env.w.localStorage.getItem("ec_gbs_so_draft_v1"));
  ok(dr && dr.fields.title === "Nhap SO" && dr.fields.brand === "WIL" && dr.items.length === 1 && dr.items[0].rate === "1.500.000", "nhap luu tieu de, brand, dong hang");
  ok(env.w.localStorage.getItem("mso_draft") === null, "khong ghi de nhap cua form MSO");
  ok(!ev(), "vua luu nhap -> roi trang khong hoi");
  env.w.ecSoUx.markDirty();
  click(env, $(env, "btnCancel"));
  ok(env.confirms.length === 1, "Huy khi dang nhap -> hoi 1 lan");
  env.close();
  const env0 = load("https://t.example/gbs-so-form-v2?mode=direct", [BRAND, EC_LK, BUDGET]);
  await sleep(600);
  click(env0, $(env0, "btnCancel"));
  ok(env0.confirms.length === 0, "Huy khi chua nhap -> khong hoi");
  env0.close();

  const env2 = load("https://t.example/gbs-so-form-v2?mode=direct", [BRAND, EC_LK, BUDGET], { local: { ec_gbs_so_draft_v1: JSON.stringify(dr) } });
  await sleep(1500);
  ok(env2.d.documentElement.getAttribute("data-ec-so-draft") === "1", "mo lai trang -> thanh khoi phuc nhap");
  click(env2, $(env2, "ecSoDraftRestore"));
  await sleep(600);
  const rows = [...env2.d.querySelectorAll("#itemsBody tr")];
  ok($(env2, "title").value === "Nhap SO" && $(env2, "brand").value === "WIL", "khoi phuc tieu de + brand");
  ok(rows.length === 1 && rows[0].querySelector(".item-code").value === "REV-1" && rows[0].querySelector(".item-qty").value === "3", "khoi phuc dong hang");
  ok(!env2.d.documentElement.hasAttribute("data-ec-so-draft"), "khoi phuc xong an thanh");
  click(env2, $(env2, "ecSoDraftDiscard"));
  ok(env2.w.localStorage.getItem("ec_gbs_so_draft_v1") === null, "Bo nhap -> xoa nhap");
  env2.close();
}

// ---------------------------------------------------------------- nho theo brand
console.log("Nho lua chon theo brand");
{
  const mem = JSON.stringify({ "gbsrev|WIL": { customer: "CUS-1", project: "PRJ-1" } });
  const env = load("https://t.example/gbs-so-form-v2?mode=gbsrev", [BRAND, LOOKUPS, BUDGET], { local: { ec_gbs_so_mem_v1: mem } });
  await sleep(1500);
  addOpt(env, "customer", "CUS-1"); addOpt(env, "project", "PRJ-1"); addOpt(env, "project", "PRJ-2");
  $(env, "project").value = "PRJ-2";     // nguoi dung da chon truoc -> khong de
  pick(env, "brand", "WIL");
  await sleep(50);
  ok($(env, "customer").value === "CUS-1", "chon brand -> dien san khach cua lan truoc");
  ok($(env, "project").value === "PRJ-2", "o nguoi dung da chon thi giu nguyen");
  ok(!$(env, "ecSoMemHint").hidden && /theo SO trước của brand WIL/.test($(env, "ecSoMemHint").textContent), "ghi ro da dien san");
  env.close();
  const env2 = load("https://t.example/gbs-so-form-v2?edit=GBS-SO-1", [BRAND, LOOKUPS], { local: { ec_gbs_so_mem_v1: mem } });
  await sleep(300);
  addOpt(env2, "customer", "CUS-1");
  pick(env2, "brand", "WIL");
  await sleep(50);
  ok($(env2, "customer").value === "", "che do sua: khong dien san");
  env2.close();
}

// ---------------------------------------------------------------- ban phim
console.log("Ban phim");
{
  const env = load("https://t.example/gbs-so-form-v2?mode=gbsrev", [BRAND, LOOKUPS]);
  await sleep(1500);
  const n = env.d.querySelector('.ec-pri-opt[data-pri="Normal"]');
  n.focus();
  key(env, n, "ArrowRight");
  const u = env.d.querySelector('.ec-pri-opt[data-pri="Urgent"]');
  ok($(env, "priority").value === "Urgent" && u.getAttribute("aria-checked") === "true" && n.getAttribute("tabindex") === "-1" && env.d.activeElement === u,
     "mui ten doi muc uu tien + aria-checked + roving tabindex");
  const disp = $(env, "brand").previousElementSibling.querySelector(".ec-cb-display");
  const panel = $(env, "brand").previousElementSibling.querySelector(".ec-cb-panel");
  click(env, disp);
  await sleep(60);
  ok(!panel.hidden, "bam o brand -> mo danh sach");
  const q = panel.querySelector(".ec-cb-search");
  key(env, q, "Escape");
  await sleep(60);
  ok(panel.hidden && env.d.activeElement === disp, "Esc dong danh sach, focus ve o, KHONG mo lai");
  click(env, disp);
  await sleep(60);
  key(env, q, "Enter");
  await sleep(60);
  ok(panel.hidden && $(env, "brand").value === "WIL" && env.d.activeElement === disp, "Enter chon muc dau, dong danh sach, focus ve o");
  click(env, disp);
  await sleep(60);
  ok(!panel.hidden && env.d.activeElement === q, "mo lai danh sach, focus o tim");
  $(env, "campaignNo").focus();       // Tab sang o khac
  await sleep(20);
  ok(panel.hidden, "Tab ra khoi o -> danh sach tu dong (truoc day treo mo)");
  env.close();
}

// ---------------------------------------------------------------- sua & gui lai: khong doi luong
console.log("Sua & gui lai giu nguyen");
{
  const doc = { name: "GBS-SO-1", status: "Cần sửa", so_title: "T", department: "Service", brand_code: "WIL", customer: "CUS-1",
    transaction_date: "2026-11-01", delivery_date: "2026-11-05", set_warehouse: "WH-1", attachment_url: "https://sp/cu.pdf",
    items: [{ item_code: "IT-1", qty: 2, rate: 1000 }] };
  const env = load("https://t.example/gbs-so-form-v2?edit=GBS-SO-1", [BRAND, LOOKUPS,
    [/\/api\/resource\/GBS(%20| )Sales(%20| )Order\//, () => ({ data: doc })],
    [/resubmit_gbs_so/, () => ({ message: { success: true, status: "Pending", current_level: 1, revision_count: 1 } })]]);
  await sleep(2700);
  env.w.ecSoUx.markDirty();
  click(env, $(env, "submitBtn"));
  await sleep(300);
  ok(posted(env, /resubmit_gbs_so/).length === 1, "Sua & gui lai van gui (khong bi kiem tra tao moi chan) (" + env.alerts.join("|") + ")");
  const e = new env.w.Event("beforeunload", { cancelable: true }); env.w.dispatchEvent(e);
  ok(!e.defaultPrevented, "gui lai xong -> khong hoi roi trang");
  env.close();
}

console.log("  " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
