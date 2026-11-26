// Copyright (c) 2026, eCentric and contributors
// Gan phieu duyet cho NGUOI LAP phieu (26/11/2026). Truoc do 0 EC Approval Link tren site: cac trang chi
// goi EcAddFile.buttonHTML o panel nguoi duyet -> phieu nhap / form tao moi khong co nut.
//   (1) chi tiet phieu NHAP cua nguoi gui: khoi "Phieu duyet dinh kem" + nut (theo capability server);
//       khong quyen + khong chip -> khong ve gi.
//   (2) form TAO MOI: nut trong the Tom tat A1; bam -> save_draft (duong luu nhap cua trang) -> get_detail
//       -> mo hop chon; form KHONG chuyen trang, du lieu giu nguyen; luu loi -> trang bao loi, khong mo hop.
//   (3) sua de gui lai (Can bo sung): khoi chip + nut tren form sua.
//   (4) thong diep chan gui khi phieu gan bi tu choi / huy KHONG bi bo loc loi cua trang nuot mat.
//     node ecentric_workspace/approval_center/tests/js/test_gan_phieu_nguoi_lap.mjs
import { JSDOM } from "jsdom";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, "..", "..", "..");
const FEAT = join(here, "..", "..", "features");
const rd = (p) => readFileSync(join(ROOT, "public", "js", p), "utf8");
const REMIND = rd("ec_remind.bundle.js"), ADDF = rd("ec_addfile.bundle.js"), LINKS = rd("ec_approval_links.bundle.js");
const SUMMARY = rd("ec_summary.bundle.js"), UI = rd("ec_approval_ui.bundle.js");
// booking_request: form rieng (khong saveDraft / khong the Tom tat) - xem bao cao; brand_weight khong phai form duyet.
const SKIP = new Set(["brand_weight", "booking_request"]);
// Khong co nhanh "nhap" rieng trong panel hanh dong (nhap di qua nhanh chung co EcRemind.buttonHTML).
const NO_DRAFT_BRANCH = new Set(["livestream_supplies"]);
// Khong co form tao moi theo thiet ke (tao tu phieu khac / da chuyen sang Trung tam Du lieu): chi co form sua.
const NO_CREATE = new Set(["clearance_request", "data_request", "new_staff_preparation", "employee_review"]);
const CREATE_QS = { offer_request: "?hiring=HR-1" };   // Offer chi tao tu Hiring Request da duyet
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async (k) => { for (let i = 0; i < (k || 14); i++) await new Promise((r) => setTimeout(r, 4)); };
const LINK_ERR = "Vui lòng xử lý phiếu gắn kèm EC-ADHOC-2026-00012 trước khi gửi: phiếu đó đã bị từ chối / huỷ. "
  + "Ghi lý do vẫn dùng ở chip phiếu (người duyệt sẽ thấy) hoặc gỡ phiếu đó.";
const srvErr = (msg) => { const sm = JSON.stringify([JSON.stringify({ message: msg })]);
  return { _server_messages: sm, responseJSON: { _server_messages: sm, exc_type: "ValidationError" }, status: 417, exc_type: "ValidationError" }; };
const HOST = { doctype: "EC Test Request", name: "R-1" };
const CHIP = { request: "APR-9", code: "EC-ADHOC-2026-00009", title: "Tăng <b>ngân sách</b>", private: false, can_open: true,
  detail_url: "/approvals/adhoc-approval?id=EC-ADHOC-2026-00009", status: "Approved", status_label: "Đã duyệt", bad: false,
  link: "LK-9", can_unlink: true };

function mockFetch(w) {
  w.__fetch = [];
  w.fetch = (url, opts) => {
    w.__fetch.push([url, opts]);
    const res = (status, body) => Promise.resolve({ status, ok: status < 400, json: () => Promise.resolve(body) });
    if (url.indexOf("search_linkable") >= 0) return res(200, { message: { rows: [
      { request: "APR-9", code: "EC-ADHOC-2026-00009", title: "Tăng ngân sách", private: false, can_attach: true,
        status: "Approved", status_label: "Đã duyệt", already_linked: false, used_elsewhere: 0 }] } });
    if (url.indexOf("link_approval") >= 0) return res(200, { message: { duplicate: false, chips: [CHIP] } });
    return res(404, {});
  };
}
const DET = (cap, ap, biz) => ({ business: Object.assign({ name: "R-1", requested_by: "req@x", request_title: "T" }, biz || {}),
  approval: ap || {}, request: ap || {}, levels: ap && ap.name ? [{ level_no: 1, level_name: "Quản lý", level_status: ap.approval_status === "Information Required" ? "Information Requested" : "In Progress" }] : [],
  approvers: ap && ap.name ? [{ level_no: 1, approver: "mgr@x", status: ap.approval_status === "Information Required" ? "Information Requested" : "Pending", comment: "bổ sung" }] : [],
  attachments: [], timeline: [], extra: {}, items: [], process_preview: [], capabilities: cap });
const DRAFT_CAP = (over) => Object.assign({ can_submit: true, can_edit: true, can_cancel: true, approval_links: [],
  can_link_approval: true, approval_link_host: HOST }, over || {});

function boot(html, url, opts) {
  opts = opts || {};
  const i = html.search(/<script[^>]*id="ec-[^"]+"[^>]*>/);
  const markup = html.slice(0, i);
  const js = html.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url: "https://x.test/" + url });
  const w = dom.window; w.__calls = [];
  w.HTMLElement.prototype.scrollIntoView = function () {};
  w.frappe = { csrf_token: "tok", session: { user: "req@x" }, call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args]);
    const h = opts.handlers && opts.handlers[m];
    if (h) return h(o.args);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true, all: true },
      context: { user: "req@x", employee: "EMP-1", employee_name: "Người Gửi", department: "Ops", manager_resolvable: true, manager: "mgr@x" },
      form_options: {}, options: {} } });
    if (m === "get_detail" || m === "get_request_detail") return Promise.resolve({ message: opts.det || DET(DRAFT_CAP()) });
    if (m === "save_draft") return Promise.resolve({ message: { name: "R-NEW" } });
    return Promise.resolve({ message: { rows: [], total: 0, data: [] } }); } };
  w.confirm = () => true;
  mockFetch(w);
  w.eval(UI); w.eval(REMIND); w.eval(ADDF); w.eval(LINKS); w.eval(SUMMARY);
  w.eval(js);
  return w;
}
const PREFILL = { hiring_prefill: () => Promise.resolve({ message: { hiring_request: "HR-1", position: "Dev" } }) };
const toasts = (w) => Array.from(w.document.querySelectorAll('[id$="-toast"],[class*="toast"]')).map((t) => t.textContent).join(" | ");

// ---- 0. asset: formHTML ------------------------------------------------------------------------
{
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", { runScripts: "outside-only" });
  const w = dom.window; mockFetch(w); w.eval(UI); w.eval(LINKS); w.eval(SUMMARY);
  const L = w.EcApprovalLinks, call = () => Promise.resolve({});
  const a = L.formHTML({ name: null, call, save: () => Promise.resolve() });
  ok(/data-ec-aplk-create/.test(a) && /Gắn phiếu duyệt/.test(a), "form moi -> nut gan (tu luu nhap)");
  ok(L.formHTML({ name: null }) === "", "khong co call/save -> khong ve");
  ok(L.formHTML({ name: "R-2", call, cap: { approval_links: [], can_link_approval: false, approval_link_host: HOST } }) === "",
    "co ma + server noi khong quyen + khong chip -> khong ve gi");
  const c = L.formHTML({ name: "R-3", call, cap: { approval_links: [CHIP], can_link_approval: false, approval_link_host: { doctype: "X", name: "R-3" } } });
  ok(/ec-aplk-chip/.test(c) && !/data-ec-aplk-open/.test(c) && !/data-ec-aplk-create/.test(c), "khong quyen nhung co chip -> chip chi xem");
  ok(c.indexOf("<b>ngân sách</b>") < 0, "tieu de chip escape");
  const d = L.formHTML({ name: "R-4", call, cap: { approval_links: [], can_link_approval: true, approval_link_host: { doctype: "X", name: "R-4" } } });
  ok(/data-ec-aplk-open/.test(d) && /data-ec-aplk-dt="X"/.test(d), "co quyen -> blockHTML(cap) cua server");
  const card = w.EcSummary.cardHTML("s", '<div class="actions"></div>', a);
  ok(/class="ec-sum-x"/.test(card) && card.indexOf("ec-sum-x") < card.indexOf("ec-sum-f"), "the Tom tat: khoi phu nam giua tom tat va thanh nut");
  ok(!/ec-sum-x/.test(w.EcSummary.cardHTML("s", "")), "khong khoi phu -> markup cu");
}

// ---- 1-3. moi form ---------------------------------------------------------------------------
const feats = readdirSync(FEAT).filter((f) => existsSync(join(FEAT, f, "ui", "main_section.html")) && !SKIP.has(f)).sort();
ok(feats.length >= 31, "du form (" + feats.length + ")");
for (const f of feats) {
  const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
  const route = "approvals/" + f.replace(/_/g, "-");

  // (1) chi tiet nhap cua nguoi gui
  if (!NO_DRAFT_BRANCH.has(f)) {
    let w = boot(html, route + "?id=R-1", { det: DET(DRAFT_CAP(), {}, f === "employee_review" ? { la_cnb: 1 } : null) });
    await flush();
    const box = w.document.querySelector(".ec-aplk[data-ec-aplk-name='R-1']");
    if (f === "employee_review") {
      // nhap Danh gia NS chi hien nut cho C&B (x.la_cnb) - kiem rieng ben duoi
    } else {
      ok(!!box && !!box.querySelector("[data-ec-aplk-open]"), f + ": chi tiet nhap -> khoi + nut Gan phieu duyet");
      ok(!!w.document.querySelector('[data-act="submitdraft"]'), f + ": van con nut Gui cua nhap");
    }
    w = boot(html, route + "?id=R-1", { det: DET(DRAFT_CAP({ can_link_approval: false })) });
    await flush();
    ok(!w.document.querySelector(".ec-aplk"), f + ": nhap nhung server noi khong quyen -> khong khoi");
  }

  // (2) form tao moi
  {
    const w = boot(html, route + (CREATE_QS[f] || ""), { handlers: PREFILL });
    await flush();
    const btn = w.document.querySelector("#ec-sum [data-ec-aplk-create]");
    if (NO_CREATE.has(f)) { ok(!btn, f + ": khong co form tao theo thiet ke -> khong nut"); continue; }
    ok(!!btn, f + ": form tao moi co nut Gan phieu duyet trong the Tom tat");
    if (!btn) continue;
    const firstInput = w.document.querySelector('#ec-sum ~ * textarea[data-model], textarea[data-model]:not([readonly]), input[data-model][type="text"]:not([readonly]), input[data-model]:not([type]):not([readonly])');
    if (firstInput) { firstInput.value = "Giữ nguyên"; firstInput.dispatchEvent(new w.Event("input", { bubbles: true })); }
    btn.click();
    await flush(24);
    const sd = w.__calls.filter((x) => x[0] === "save_draft");
    ok(sd.length === 1 && !sd[0][1].name, f + ": bam -> save_draft (khong name) qua duong luu nhap cua trang");
    ok(w.__calls.some((x) => x[0] === "get_detail" && x[1].name === "R-NEW"), f + ": lay capability tu get_detail cua phieu vua luu");
    ok(!w.__calls.some((x) => x[0] === "submit_request"), f + ": khong gui phieu");
    ok(!!w.document.querySelector(".ec-aplk-overlay"), f + ": mo hop chon phieu");
    const sl = w.__fetch.find((x) => x[0].indexOf("search_linkable") >= 0);
    ok(sl && /host_name=R-1/.test(sl[0]), f + ": hop chon dung host server tra ve");
    ok(!/[?&]id=/.test(w.location.search) && !!w.document.querySelector("#ec-sum"), f + ": van o form (khong chuyen sang chi tiet)");
    if (firstInput && firstInput.isConnected) ok(firstInput.value === "Giữ nguyên", f + ": du lieu dang nhap giu nguyen");
    // chon + gan -> chip hien trong form
    const ov = w.document.querySelector(".ec-aplk-overlay");
    if (ov) {
      ov.querySelector("tr[data-i='0']").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
      ov.querySelector("[data-ok]").click();
      await flush();
      ok(w.document.querySelectorAll("#ec-sum .ec-aplk-chip").length === 1, f + ": gan xong -> chip hien trong form");
      // Luu nhap lan sau dung lai ma phieu (khong tao phieu thu 2)
      const save = Array.from(w.document.querySelectorAll("button")).find((b) => /^Lưu nháp$/.test(b.textContent.trim()));
      if (save) { save.click(); await flush(); const sd2 = w.__calls.filter((x) => x[0] === "save_draft");
        ok(sd2.length === 2 && sd2[1][1].name === "R-NEW", f + ": Luu nhap sau do ghi vao cung phieu R-NEW"); }
    }
  }
  // (2b) luu nhap loi -> trang bao loi, khong mo hop, nut mo lai
  {
    const w = boot(html, route + (CREATE_QS[f] || ""), { handlers: Object.assign({ save_draft: () => Promise.reject(srvErr("Vui lòng nhập Tiêu đề hợp lệ.")) }, PREFILL) });
    await flush();
    const btn = w.document.querySelector("#ec-sum [data-ec-aplk-create]");
    if (btn) {
      btn.click(); await flush(24);
      ok(!w.document.querySelector(".ec-aplk-overlay") && !w.__calls.some((x) => x[0] === "get_detail"), f + ": luu loi -> khong mo hop");
      // ai_topup doi loi tieu de thanh cau rieng cua no (cung duong nut Luu nhap) -> chi can co bao loi.
      ok(f === "ai_topup" ? /Vui lòng/.test(toasts(w)) : /Tiêu đề hợp lệ/.test(toasts(w)), f + ": luu loi -> bao loi nhu nut Luu nhap (" + toasts(w).slice(0, 80) + ")");
      ok(!/Đã lưu nháp/.test(toasts(w)), f + ": luu loi -> khong bao da luu");
      ok(btn.isConnected && !btn.disabled && /Gắn phiếu duyệt/.test(btn.textContent), f + ": nut tro lai binh thuong");
    }
  }
  // (2c) server noi khong gan duoc -> khong mo hop, bao ro
  {
    const w = boot(html, route + (CREATE_QS[f] || ""), { det: DET(DRAFT_CAP({ can_link_approval: false })), handlers: PREFILL });
    await flush();
    const btn = w.document.querySelector("#ec-sum [data-ec-aplk-create]");
    if (btn) {
      btn.click(); await flush(24);
      ok(!w.document.querySelector(".ec-aplk-overlay"), f + ": server khong cho -> khong mo hop");
      ok(/không gắn được phiếu duyệt/.test(toasts(w)), f + ": server khong cho -> bao ro");
    }
  }
}

// ---- 3. sua de gui lai (Can bo sung): khoi chip tren form sua ---------------------------------
for (const f of ["leave", "payment_request", "adhoc_approval", "contract_review", "employee_review"]) {
  const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
  const ap = { name: "AR", approval_status: "Information Required", current_level: 1, information_requested_from_level: 1 };
  const cap = { can_edit: true, can_cancel: true, approval_links: [CHIP], can_link_approval: true, approval_link_host: HOST };
  const w = boot(html, "approvals/" + f.replace(/_/g, "-") + "?id=R-1", { det: DET(cap, ap) });
  await flush();
  const edit = w.document.querySelector('[data-act="edit"]');
  ok(!!edit, f + ": Can bo sung -> co nut sua");
  if (!edit) continue;
  edit.click(); await flush();
  const box = w.document.querySelector("#ec-sum .ec-aplk[data-ec-aplk-name='R-1']");
  ok(!!box && box.querySelectorAll(".ec-aplk-chip").length === 1 && !!box.querySelector("[data-ec-aplk-open]"), f + ": form sua de gui lai co chip + nut");
  ok(!w.document.querySelector("[data-ec-aplk-create]"), f + ": da co ma -> khong luu nhap lai");
}

// ---- 4. thong diep chan gui (approval_links.assert_host_submittable) qua bo loc loi cua tung trang --
{
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", { runScripts: "outside-only" });
  const w = dom.window; w.eval(UI);
  const grab = (src, name) => { const i = src.indexOf("function " + name + "("); if (i < 0) return "";
    let k = src.indexOf("{", i), depth = 0;
    for (let j = k; j < src.length; j++) { const ch = src[j]; if (ch === "{") depth++; else if (ch === "}") { depth--; if (!depth) return src.slice(i, j + 1); } }
    return ""; };
  for (const f of feats) {
    const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
    const fns = ["extractServerMsg", "mapErr", "friendlyErr", "resubmitErr"].map((n) => [n, grab(html, n)]).filter((x) => x[1]);
    const names = fns.map((x) => x[0]);
    if (!names.includes("resubmitErr") && !names.includes("mapErr")) continue;
    let fn;
    try { fn = w.eval("(function(){ function showFieldErrors(){} function validateSubmit(){return null;} " + fns.map((x) => x[1]).join("\n")
      + "; return { m: typeof mapErr==='function'?mapErr:null, f: typeof friendlyErr==='function'?friendlyErr:null, r: typeof resubmitErr==='function'?resubmitErr:null }; })()"); }
    catch (e) { ok(false, f + ": khong tach duoc ham loi: " + e.message); continue; }
    const e = srvErr(LINK_ERR);
    for (const k of ["m", "f", "r"]) if (fn[k]) {
      let out = ""; try { out = fn[k](e); } catch (x) { out = "THROW " + x.message; }
      ok(/phiếu gắn kèm EC-ADHOC-2026-00012/.test(out), f + ": " + ({ m: "mapErr", f: "friendlyErr", r: "resubmitErr" })[k] + " giu nguyen thong diep phieu gan (" + String(out).slice(0, 60) + ")");
    }
  }
  // nhap -> bam Gui o chi tiet -> server chan -> toast hien dung cau
  for (const f of ["leave", "payment_request", "purchase_request", "adhoc_approval"]) {
    const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
    const w2 = boot(html, "approvals/" + f.replace(/_/g, "-") + "?id=R-1", { handlers: { submit_request: () => Promise.reject(srvErr(LINK_ERR)) } });
    await flush();
    const b = w2.document.querySelector('[data-act="submitdraft"]');
    if (!b) { ok(false, f + ": khong thay nut Gui nhap"); continue; }
    b.click(); await flush();
    const mod = w2.document.querySelector('[class*="overlay"] [data-ok]');
    if (mod) { mod.click(); await flush(); }
    ok(/phiếu gắn kèm EC-ADHOC-2026-00012/.test(toasts(w2) + " " + w2.document.body.textContent), f + ": gui nhap bi chan -> nguoi gui thay cau huong dan");
  }
}

// ---- 5. Contract Review - Bang tinh chi tiet: dong Thuc nhan + cot thong so co nen card (PO 26/11) ----------
{
  const html = readFileSync(join(FEAT, "contract_review", "ui", "main_section.html"), "utf8");
  ok(/KOL\.rcRow\("kol-rc-row base",""/.test(html), "contract_review: dong Thuc nhan / So nhap mang lop base");
  const rule = (sel) => { const m = html.match(new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\{([^}]*)\\}")); return m ? m[1] : ""; };
  const base = rule("#ec-ctr-root .kol-rc-row.base");
  ok(/background:var\(--gray-/.test(base) && /border-radius:8px/.test(base) && !/padding/.test(base), "dong Thuc nhan: nen xam bo goc nhu dong thue, KHONG doi padding (so van thang cot)");
  const side = rule("#ec-ctr-root .kol-rc-side");
  ok(/background:var\(--gray-50\)/.test(side) && /border-radius:10px/.test(side) && /border:1px solid var\(--gray-200\)/.test(side) && !/border-left/.test(side), "cot thong so = card nen xam nhat bo goc");
  ok(!/gradient/i.test(base + side), "khong gradient");
  ok(/kol-rc-side'>?'?\+side\+foot|<div class="kol-rc-side">'\+side\+foot/.test(html), "ghi chu lam tron + nut tai nam cuoi card");
}

console.log((fails ? "FAIL" : "OK") + " test_gan_phieu_nguoi_lap: " + oks + " pass, " + fails + " fail");
process.exit(fails ? 1 : 0);
