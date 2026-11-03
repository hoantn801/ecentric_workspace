// UX 03/11/2026 (ux_po) - form /gbs-po-form-v2: chay CA trang main_section.html trong jsdom, gia lap
// fetch, bam nut that. Kiem nhung thay doi UX: khoa loai PO khi tao tu SO, ban nhap rieng cua PO
// (khong doc nhap MSO), chot truoc-gui bao loi canh truong mot lan, trang thai dang gui / thanh cong
// co link, nho NCC lan truoc, khung "Them items tu SO khac" (chip SO + go SO + loi trong khung),
// toast khong bi an som, chot roi trang, va A65 (khong them khoi <script|style id="ec-...">).
//     node ecentric_workspace/approval_center/tests/js/test_gbs_po_form_ux.mjs
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let JSDOM, VirtualConsole;
try { ({ JSDOM, VirtualConsole } = require("jsdom")); }
catch (e) {
  console.log("BO QUA (khong chay phep nao): thieu goi jsdom - cai jsdom hoac dat NODE_PATH roi chay lai");
  process.exit(0);
}

const here = dirname(fileURLToPath(import.meta.url));
const PO = readFileSync(join(here, "..", "..", "..", "legacy_pages", "gbs_po_form_v2", "main_section.html"), "utf8");

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function load(url, routes, opts = {}) {
  const calls = [], alerts = [], errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => { const m = String((e && e.message) || e); if (!/navigation/i.test(m)) errors.push(m); });
  const dom = new JSDOM("<!DOCTYPE html><html><head></head><body>" + PO + "</body></html>", {
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
  const w = dom.window, d = w.document;
  return { w, d, calls, alerts, errors, $: (id) => d.getElementById(id), html: d.documentElement, close: () => w.close() };
}
const BRAND = [/web_lookup/, (u, o) => (JSON.parse(o.body).type === "brand"
  ? { success: true, items: [{ id: "WIL", title: "Wilmar", brand_name: "Wilmar", finance_email: "f@x" }, { id: "FRI", title: "Friso", brand_name: "Friso" }] }
  : { success: true, items: [] })];
// Thieu phan tu (vd chay tren ban cu) = 1 phep hong, khong lam vo ca bo test.
const click = (env, el) => { if (!el) { fail++; console.log("  FAIL: khong co phan tu de bam"); return; } el.dispatchEvent(new env.w.MouseEvent("click", { bubbles: true, cancelable: true })); };
const fire = (env, el, t) => el.dispatchEvent(new env.w.Event(t, { bubbles: true }));
const posted = (env, re) => env.calls.filter((c) => re.test(c.url) && c.method === "POST");
function addOpt(env, id, v, text) { const s = env.$(id); const o = env.d.createElement("option"); o.value = v; o.textContent = text || v; s.appendChild(o); return s; }
function lastRow(env) { return [...env.d.querySelectorAll("#itemsBody tr")].pop(); }
function fillRow(env, code, qty, rate) {
  const tr = lastRow(env);
  tr.querySelector(".item-code").value = code;
  tr.querySelector(".item-qty").value = String(qty);
  tr.querySelector(".item-rate").value = String(rate);
  fire(env, tr.querySelector(".item-qty"), "input");
}
const toast = (env) => env.$("toastText").textContent;

// ------------------------------------------------------------------ A65: khong them khoi ec-*
console.log("A65");
{
  const KNOWN = new Set(["ec-attachment-fix", "ec-attachment-preflight", "ec-csrf-fetch-patch", "ec-gbs-field-tooltips",
    "ec-gbs-form-edit-resubmit", "ec-gbs-form-polish", "ec-gbs-item-code-optimize", "ec-gbs-po-extra-fields",
    "ec-gbs-po-from-so", "ec-gbs-po-item-tax", "ec-gbs-po-vat-summary", "ec-gbs-post-submit-anon-attach",
    "ec-gbs-priority-picker", "ec-gbs-rate-input-fix", "ec-gbs-searchable-dropdowns", "ec-gbs-service-dates",
    "ec-gbs-uom-fix", "ec-gbs-upload-remove-sync", "ec-gbs-upload-session", "ec-po-unified", "ec-polish-overrides"]);
  const ids = [...PO.matchAll(/<(?:script|style) id="(ec-[^"]+)"/g)].map((m) => m[1]);
  ok(ids.every((i) => KNOWN.has(i)), "khong them khoi <script|style id=\"ec-...\"> moi: " + ids.filter((i) => !KNOWN.has(i)));
  ok(PO.includes('id="ecAddSoBox"') && PO.includes("window._ecPoTagRowSo = tagRowSo;") && PO.includes("sales_order: tr.getAttribute('data-so')"),
    "giu 3 moc p227 (PO nhieu SO)");
  ok(!/\{\{|\{%/.test(PO), "khong co cu phap Jinja");
}

// ------------------------------------------------------------------ Loai PO: khoa khi tao tu SO
console.log("Loai PO");
{
  const pl = JSON.stringify({ parent_so: "GBS-SO-B", so: { so_title: "SO B", brand_code: "WIL" }, items: [{ item_code: "IT-B", qty: 1, rate: 5 }], item_codes: ["IT-B"] });
  const env = load("https://t.example/gbs-po-form-v2?from_so=GBS-SO-B", [BRAND], { session: { gbs_po_from_so: pl }, local: { ec_po_last_mode: "ecbuy" } });
  await sleep(1200);
  ok(env.html.getAttribute("data-ec-po-mode") === "gbsbuy" && env.html.getAttribute("data-ec-po-mode-lock") === "1" && env.html.getAttribute("data-ec-po-flow") === "from_so",
    "tao tu SO GBS: dat san che do gbsbuy + co khoa tren <html> truoc khi ve");
  const ecBtn = env.d.querySelector('.ec-uni-btn[data-m="ecbuy"]');
  ok(ecBtn && ecBtn.getAttribute("aria-disabled") === "true", "nut loai PO kia mang aria-disabled");
  click(env, ecBtn && ecBtn.querySelector(".ec-uni-btn-t"));
  await sleep(150);
  ok(env.html.getAttribute("data-ec-po-mode") === "gbsbuy", "bam 'Mua ngoai' khi dang tao tu SO KHONG doi loai PO");
  ok(/không đổi được loại PO/.test((env.$("ecUniBadge") || {}).textContent), "bao ly do khong doi duoc");
  ok(env.w.ecPoLeaveGuard && !env.w.ecPoLeaveGuard.isDirty(), "dien san tu SO (code) khong tinh la 'dang nhap do'");
  env.close();
}
{
  const env = load("https://t.example/gbs-po-form-v2?mode=ecbuy", [BRAND]);
  await sleep(1000);
  ok(!env.html.hasAttribute("data-ec-po-mode-lock"), "phieu moi: khong khoa");
  const gb = env.d.querySelector('.ec-uni-btn[data-m="gbsbuy"]');
  click(env, gb.querySelector(".ec-uni-btn-s"));   // bam trung dong chu phu
  await sleep(200);
  ok(env.html.getAttribute("data-ec-po-mode") === "gbsbuy" && gb.getAttribute("aria-pressed") === "true", "bam chu trong nut van doi che do + aria-pressed");
  const td = env.d.querySelector("#itemsBody .item-tax").parentNode;
  ok(td.style.display === "", "cot VAT theo dong hien lai khi sang GBS mua (bam trung span)");
  click(env, env.d.querySelector('.ec-uni-btn[data-m="ecbuy"] .ec-uni-btn-t'));
  await sleep(200);
  ok(td.style.display === "none", "cot VAT theo dong an khi sang Mua ngoai (bam trung span)");
  env.close();
}

// ------------------------------------------------------------------ Ban nhap
console.log("Ban nhap");
{
  const env = load("https://t.example/gbs-po-form-v2?mode=gbsbuy", [BRAND], { local: { mso_draft: JSON.stringify({ title: "Nhap MSO cu", department: "HR" }) } });
  await sleep(1000);
  ok(env.$("title").value === "" && env.$("department").value !== "HR", "form PO KHONG dien nhap MSO cu (mso_draft)");
  env.$("title").value = "PO nap tien T12";
  env.$("department").value = "Service";
  fillRow(env, "IT-1", 3, "1.500");
  if (env.w._ecPoTagRowSo) env.w._ecPoTagRowSo(lastRow(env), "GBS-SO-7");
  click(env, env.$("btnDraft"));
  await sleep(100);
  const saved = JSON.parse(env.w.localStorage.getItem("ec_gbs_po_draft_v1") || "null");
  ok(saved && saved.f && saved.f.title === "PO nap tien T12" && saved.items.length === 1 && saved.items[0].so === "GBS-SO-7" && saved.mode === "gbsbuy",
    "Luu nhap luu tieu de + dong item (ke ca SO cua dong) + loai PO");
  ok(!/Không lưu được/.test(toast(env)) && /Đã lưu nháp/.test(toast(env)), "Luu nhap bao thanh cong (truoc day luon loi): " + toast(env));
  env.close();

  const env2 = load("https://t.example/gbs-po-form-v2", [BRAND], { local: { ec_gbs_po_draft_v1: JSON.stringify(saved || {}), ec_po_last_mode: "ecbuy" } });
  await sleep(1200);
  ok(env2.html.getAttribute("data-ec-po-draft") === "1", "co nhap -> thanh 'Khoi phuc nhap' hien tu lan ve dau (<html data-ec-po-draft>)");
  ok(/PO nap tien T12/.test((env2.$("ecDraftText") || {}).textContent) && /1 dòng item/.test((env2.$("ecDraftText") || {}).textContent), "thanh nhap ghi tieu de + so dong");
  click(env2, env2.$("btnDraftRestore"));
  await sleep(700);
  const r = lastRow(env2);
  ok(env2.html.getAttribute("data-ec-po-mode") === "gbsbuy", "khoi phuc ve dung loai PO cua nhap");
  ok(env2.$("title").value === "PO nap tien T12" && env2.$("department").value === "Service", "khoi phuc tieu de + phong ban");
  ok(r.querySelector(".item-code").value === "IT-1" && r.querySelector(".item-qty").value === "3" && r.querySelector(".item-rate").value === "1.500" && r.getAttribute("data-so") === "GBS-SO-7",
    "khoi phuc dong item + SO cua dong");
  ok(!env2.html.hasAttribute("data-ec-po-draft"), "khoi phuc xong an thanh nhap");
  env2.close();

  const env3 = load("https://t.example/gbs-po-form-v2?edit=GBS-PO-1", [BRAND], { local: { ec_gbs_po_draft_v1: JSON.stringify(saved) } });
  await sleep(300);
  ok(!env3.html.hasAttribute("data-ec-po-draft") && env3.html.getAttribute("data-ec-po-flow") === "edit", "dang sua phieu: khong moi khoi phuc nhap");
  env3.close();

  const env4 = load("https://t.example/gbs-po-form-v2", [BRAND], { local: { ec_gbs_po_draft_v1: JSON.stringify(saved) } });
  await sleep(800);
  click(env4, env4.$("btnDraftDiscard"));
  ok(!env4.w.localStorage.getItem("ec_gbs_po_draft_v1") && !env4.html.hasAttribute("data-ec-po-draft"), "Bo nhap xoa nhap + an thanh");
  env4.close();
}

// ------------------------------------------------------------------ Chot truoc-gui: 1 lan, canh truong
console.log("Bao loi canh truong");
{
  const env = load("https://t.example/gbs-po-form-v2?mode=gbsbuy", [BRAND]);
  await sleep(1000);
  click(env, env.$("submitBtn"));
  await sleep(200);
  ok(posted(env, /submit_gbs_po/).length === 0, "form trong: khong gui");
  ok(!env.alerts.some((a) => /Project/.test(a)), "khong con alert 'Vui long chon Project' (bao 1 lan cung cac loi khac)");
  const t = toast(env);
  ok(/Tiêu đề/.test(t) && /Brand/.test(t) && /Nhà cung cấp/.test(t) && /Project/.test(t) && /file chứng từ/.test(t), "toast liet ke DU cac muc thieu trong 1 lan: " + t);
  ok(env.$("title").closest(".field").classList.contains("has-error"), "o Tieu de do + thong bao canh truong");
  ok(env.$("supplier").previousElementSibling.querySelector(".ec-cb-display").classList.contains("ec-invalid"), "combobox NCC do (o nguoi dung nhin thay, khong phai select an)");
  ok(env.$("project").closest(".field").classList.contains("has-error"), "o Project do");
  ok(env.$("attachmentRequiredWarn").style.display === "block", "khung file bao thieu chung tu");
  ok(env.d.activeElement === env.$("title"), "focus vao loi DAU TIEN tren trang (Tieu de)");
  env.$("title").value = "PO x"; fire(env, env.$("title"), "input");
  ok(!env.$("title").closest(".field").classList.contains("has-error"), "go vao o -> het do");
  env.close();
}
{ // ngay can hang < ngay giao dich -> do o Ngay can hang
  const env = load("https://t.example/gbs-po-form-v2?mode=gbsbuy", [BRAND]);
  await sleep(1000);
  env.$("title").value = "PO";
  addOpt(env, "brand", "WIL").value = "WIL"; addOpt(env, "supplier", "SUP-1").value = "SUP-1"; addOpt(env, "project", "PRJ").value = "PRJ";
  env.w._ecAttachments = [{ name: "a.pdf" }];
  fillRow(env, "IT-1", 1, "1.000");
  env.$("transaction_date").value = "2026-11-10"; env.$("schedule_date").value = "2026-11-01";
  click(env, env.$("submitBtn"));
  await sleep(200);
  ok(posted(env, /submit_gbs_po/).length === 0 && env.$("schedule_date").closest(".field").classList.contains("has-error"), "ngay can hang truoc ngay giao dich: do o Ngay can hang, khong gui");
  ok(/không được trước/.test((env.$("schedule_date").closest(".field").querySelector(".error-msg") || {}).textContent || ""), "loi ghi ngay canh o");
  env.close();
}

// ------------------------------------------------------------------ Gui: dang gui -> thanh cong co link, nho NCC
console.log("Gui GBS mua");
{
  const env = load("https://t.example/gbs-po-form-v2?mode=gbsbuy", [BRAND,
    [/submit_gbs_po/, () => ({ __delay: 300, message: { success: true, name: "GBS-PO-9" } })]],
    { local: { ec_gbs_po_draft_v1: JSON.stringify({ v: 1, ts: 1, mode: "gbsbuy", f: { title: "x" }, items: [] }) } });
  await sleep(1000);
  env.$("title").value = "PO test";
  addOpt(env, "brand", "WIL").value = "WIL"; addOpt(env, "supplier", "SUP-1", "NCC Mot (SUP-1)").value = "SUP-1"; addOpt(env, "project", "PRJ").value = "PRJ";
  env.w._ecAttachments = [{ name: "a.pdf", size: 1, mime: "application/pdf", content_base64: "AA==" }];
  fillRow(env, "IT-1", 2, "1.000");
  if (env.w.ecPoLeaveGuard) env.w.ecPoLeaveGuard.mark();
  const btn = env.$("submitBtn");
  click(env, btn);
  await sleep(100);
  ok(btn.disabled && btn.classList.contains("loading") && /Đang gửi/.test(btn.textContent) && btn.querySelector("svg.spin"), "dang gui: khoa nut + icon quay + 'Dang gui'");
  await sleep(500);
  ok(posted(env, /submit_gbs_po/).length === 1, "gui dung 1 lan");
  ok(/Đã tạo PO GBS GBS-PO-9/.test(toast(env)), "thong bao tieng Viet: " + toast(env));
  const a = env.$("toastLink") || { hidden: true, getAttribute: () => "" };
  ok(!a.hidden && /id=GBS-PO-9/.test(a.getAttribute("href")) && /type=gbs_po/.test(a.getAttribute("href")), "toast co link 'Mo phieu' toi phieu vua tao");
  const last = JSON.parse(env.w.localStorage.getItem("ec_po_last_sup_gbsbuy") || "null");
  ok(last && last.v === "SUP-1" && last.t === "NCC Mot (SUP-1)", "nho NCC vua dung (theo loai PO)");
  ok(!env.w.localStorage.getItem("ec_gbs_po_draft_v1"), "tao xong thi xoa ban nhap");
  ok(env.w.ecPoLeaveGuard && !env.w.ecPoLeaveGuard.isDirty(), "tao xong khong hoi 'roi trang'");
  env.close();
}

// ------------------------------------------------------------------ Dung lai NCC lan truoc
console.log("NCC lan truoc");
{
  const env = load("https://t.example/gbs-po-form-v2?mode=gbsbuy", [BRAND], { local: { ec_po_last_sup_gbsbuy: JSON.stringify({ v: "SUP-1", t: "NCC Mot (SUP-1)" }) } });
  await sleep(300);
  ok(env.html.getAttribute("data-ec-po-lastsup-gbsbuy") === "1", "co NCC lan truoc -> nut hien tu lan ve dau");
  const chip = env.$("ecLastSupGbs");
  ok(/NCC Mot \(SUP-1\)/.test((chip || {}).textContent), "nut ghi ten NCC lan truoc");
  ok(env.$("supplier").value === "", "KHONG tu chon NCC (chi goi y)");
  click(env, chip);
  await sleep(300);
  addOpt(env, "supplier", "SUP-1", "NCC Mot (SUP-1)");   // danh sach boxme ve sau
  await sleep(400);
  ok(env.$("supplier").value === "SUP-1", "bam nut -> chon NCC khi danh sach ve");
  env.close();
}

// ------------------------------------------------------------------ Them items tu SO khac
console.log("Them items tu SO khac");
{
  const env = load("https://t.example/gbs-po-form-v2?mode=gbsbuy", [BRAND,
    [/GBS Sales Order/, () => ({ data: [{ name: "GBS-SO-2", so_title: "Nap tien", gbs_status: "Approved" }] })],
    [/gbs_so_create_po_helper/, (u, o) => {
      const so = JSON.parse(o.body).so_name;
      if (so === "GBS-SO-X") return { message: { success: true, so: { brand_code: "FRI", gbs_status: "Approved" }, items: [{ item_code: "Z", qty: 1, rate: 1 }] } };
      return { message: { success: true, so: { brand_code: "WIL", gbs_status: "Approved" }, items: [{ item_code: "A", qty: 1, rate: 1000 }, { item_code: "B", qty: 2, rate: 500 }] } };
    }]]);
  await sleep(1000);
  const btn = env.$("btnAddSo"), panel = env.$("ecAddSoPanel");
  ok(env.w.getComputedStyle(panel).display === "none", "khung chon SO dong luc dau that su an (truoc: CSS display:flex de len [hidden])");
  click(env, btn);
  await sleep(50);
  ok(!panel.hidden && btn.getAttribute("aria-expanded") === "true", "mo khung + aria-expanded");
  ok(env.$("ecAddSoSel").disabled && /Chọn Brand/.test(env.$("ecAddSoSel").options[0].textContent), "chua co brand: o chon SO khoa + huong dan chon Brand");
  env.$("ecAddSoCode").value = "GBS-SO-1";
  env.$("ecAddSoCode").dispatchEvent(new env.w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await sleep(300);
  const rows = [...env.d.querySelectorAll('#itemsBody tr[data-so="GBS-SO-1"]')];
  ok(rows.length === 2, "Enter trong o ma SO -> them 2 dong cua SO");
  ok(env.$("brand").value === "WIL", "PO chua co brand -> dien Brand theo SO");
  const msgEl = () => env.$("ecAddSoMsg") || { className: "", textContent: "" };
  ok(msgEl().className === "ec-ok" && /Đã thêm 2 dòng/.test(msgEl().textContent), "bao ket qua ngay trong khung: " + msgEl().textContent);
  await sleep(200);
  const sel = env.$("ecAddSoSel");
  ok(!sel.disabled && sel.options.length === 2 && /1 SO cùng brand/.test(sel.options[0].textContent), "co brand -> goi y SO cung brand da duyet (" + sel.options[0].textContent + ")");
  const chip = env.d.querySelector('#ecSoList .ec-so-chip');
  ok(chip && /GBS-SO-1/.test(chip.textContent) && /2 dòng/.test(chip.textContent) && chip.querySelector(".ec-so-rm"), "chip SO: ma + so dong + nut Go");
  env.$("ecAddSoCode").value = "GBS-SO-X";
  click(env, env.$("btnAddSoGo"));
  await sleep(300);
  ok(msgEl().className === "ec-err" && /thuộc brand FRI/.test(msgEl().textContent) && !env.alerts.some((a) => /SO/.test(a) && !/^CONFIRM/.test(a)),
    "SO khac brand: bao loi trong khung, khong alert");
  click(env, chip && chip.querySelector(".ec-so-rm"));
  await sleep(100);
  ok(env.d.querySelectorAll('#itemsBody tr[data-so]').length === 0 && env.d.querySelectorAll("#itemsBody tr").length === 1, "Go SO: xoa het dong cua SO, giu 1 dong trong");
  ok(env.$("ecSoList").textContent.trim() === "", "danh sach SO trong sau khi go");
  env.close();
}
{ // SO goc (?from_so=) khong co nut Go
  const pl = JSON.stringify({ parent_so: "GBS-SO-B", so: { so_title: "SO B", brand_code: "WIL" }, items: [{ item_code: "IT-B", qty: 1, rate: 5 }], item_codes: ["IT-B"] });
  const env = load("https://t.example/gbs-po-form-v2?from_so=GBS-SO-B", [BRAND], { session: { gbs_po_from_so: pl } });
  await sleep(2600);
  const chip = env.d.querySelector('#ecSoList .ec-so-chip');
  ok(chip && /SO gốc/.test(chip.textContent) && !chip.querySelector(".ec-so-rm"), "SO goc: nhan 'SO goc', khong co nut Go");
  env.close();
}

// ------------------------------------------------------------------ Mua ngoai: do canh truong
console.log("Mua ngoai (so EC)");
{
  const env = load("https://t.example/gbs-po-form-v2?mode=ecbuy", [BRAND,
    [/ec_so_lookups/, () => ({ message: { items: [{ item_code: "EC-1", item_name: "Phi" }], suppliers: [{ name: "SUP-EC", supplier_name: "NCC EC" }], recent_sos: [] } })]]);
  await sleep(1500);
  click(env, env.$("submitBtn"));
  await sleep(150);
  ok(env.$("ecSupplier").previousElementSibling.querySelector(".ec-cb-display").classList.contains("ec-invalid") && /Nhà cung cấp \(EC\)/.test(env.$("ecUniBadge").textContent),
    "thieu NCC (EC): do combobox + bao");
  env.close();
}

// ------------------------------------------------------------------ Toast + roi trang + uu tien
console.log("Toast / roi trang / uu tien");
{
  const env = load("https://t.example/gbs-po-form-v2?mode=gbsbuy", [BRAND]);
  await sleep(600);
  const ev1 = new env.w.Event("beforeunload", { cancelable: true });
  env.w.dispatchEvent(ev1);
  ok(!ev1.defaultPrevented, "form chua sua: roi trang khong hoi");
  if (env.w.ecPoLeaveGuard) env.w.ecPoLeaveGuard.mark();
  const ev2 = new env.w.Event("beforeunload", { cancelable: true });
  env.w.dispatchEvent(ev2);
  ok(ev2.defaultPrevented, "dang nhap do: roi trang phai hoi");
  const urg = env.d.querySelector('.ec-pri-opt[data-pri="Urgent"]');
  ok(urg && urg.tagName === "BUTTON", "muc uu tien la nut that (ban phim)");
  click(env, urg);
  ok(urg && urg.getAttribute("aria-pressed") === "true" && env.$("priority").value === "Urgent", "chon Urgent: aria-pressed + o an");
  env.w.showGbsToast("mot", "success");
  await sleep(3000);
  env.w.showGbsToast("hai", "error");
  await sleep(2000);
  ok(env.$("toast").classList.contains("show") && toast(env) === "hai", "toast moi khong bi an som theo hen cua toast cu");
  ok(env.errors.length === 0, "khong loi JS khi tai trang: " + env.errors.slice(0, 3).join(" | "));
  env.close();
}

console.log("  " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
