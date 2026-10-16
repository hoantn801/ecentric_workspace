// Copyright (c) 2026, eCentric and contributors
// Nut "Them tep" o buoc duyet (16/10/2026): co can_add_attachment -> co nut tren MOI form (qua
// EcRemind.buttonHTML, khong sua trang) + popup hub; chon tep -> hop xac nhan -> upload_file
// (is_private=1, KHONG doctype/docname) -> reporting.actions.add_attachment(request_name, file_url)
// -> trang ve lai chi tiet. Loi -> thong bao ro, nut "Thu lai". Khong quyen -> khong nut.
//     node ecentric_workspace/approval_center/tests/js/test_addfile_button_all_forms.mjs
import { JSDOM } from "jsdom";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, "..", "..", "..");
const FEAT = join(here, "..", "..", "features");
const REMIND = readFileSync(join(ROOT, "public", "js", "ec_remind.bundle.js"), "utf8");
const ADDF = readFileSync(join(ROOT, "public", "js", "ec_addfile.bundle.js"), "utf8");
const SKIP = new Set(["brand_weight"]);   // UI rieng, khong co khu nut duyet chung (nhu test remind)
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 5)); };
const DET = (cap) => ({ business: { name: "R-1", requested_by: "req@x", request_title: "T", approval_request: "AR" },
  approval: { name: "AR", approval_status: "Pending", current_level: 2 }, request: { name: "AR", approval_status: "Pending", current_level: 2 },
  levels: [{ level_no: 2, level_name: "Finance", level_status: "In Progress" }],
  approvers: [{ level_no: 2, approver: "fin1@x", status: "Pending" }], attachments: [], timeline: [], extra: {}, items: [],
  capabilities: cap });
const CAP = { can_approve: true, can_reject: true, can_add_attachment: true, add_attachment_request: "AR" };

function mockFetch(w, mode) {
  w.__fetch = [];
  w.fetch = (url, opts) => {
    w.__fetch.push([url, opts]);
    const res = (status, body) => Promise.resolve({ status, ok: status < 400, json: () => Promise.resolve(body) });
    if (url === "/api/method/upload_file") {
      if (mode === "upload413") return res(413, {});
      return res(200, { message: { file_url: "/private/files/Plan_Vinasoy.xlsx" } });
    }
    if (url.endsWith("reporting.actions.add_attachment")) {
      if (mode === "deny") return res(403, { _server_messages: JSON.stringify([JSON.stringify(
        { message: "Chỉ người đang xử lý phiếu ở bước hiện tại mới thêm được tệp." })]) });
      return res(200, { message: { file_name: "Plan_Vinasoy.xlsx", business_name: "R-1" } });
    }
    return res(404, {});
  };
}
function boot(html, route, det, mode) {
  const i = html.search(/<script[^>]*id="ec-[^"]+"[^>]*>/);
  const markup = html.slice(0, i);
  const js = html.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/" + route + "?id=R-1" });
  const w = dom.window; w.__calls = [];
  w.frappe = { csrf_token: "tok", session: { user: "fin1@x" }, call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args]);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true, all: true }, context: { user: "fin1@x" }, form_options: {}, options: {} } });
    if (m === "get_detail" || m === "get_request_detail") return Promise.resolve({ message: det });
    return Promise.resolve({ message: { rows: [], total: 0, data: [] } }); } };
  mockFetch(w, mode);
  w.eval(REMIND); w.eval(ADDF);
  try { w.eval(js); } catch (e) { return { w, err: e }; }
  return { w };
}
function pick(w, name) {
  const inp = w.document.querySelector("input[data-ec-addfile]");
  const f = new w.File(["abc"], name || "Plan_Vinasoy.xlsx");
  Object.defineProperty(inp, "files", { configurable: true, value: [f] });
  inp.dispatchEvent(new w.Event("change", { bubbles: true }));
  return inp;
}
const detailCalls = (w) => w.__calls.filter((c) => c[0] === "get_detail" || c[0] === "get_request_detail").length;

// ---- bundle don le -------------------------------------------------------------------------
{
  const dom = new JSDOM("<!DOCTYPE html><body></body>", { runScripts: "outside-only", url: "https://x.test/" });
  const w = dom.window; w.eval(REMIND); w.eval(ADDF);
  ok(w.EcAddFile.buttonHTML({}) === "", "khong quyen -> rong");
  ok(w.EcAddFile.buttonHTML({ can_add_attachment: true }) === "", "thieu ma phieu duyet -> rong");
  const h = w.EcAddFile.buttonHTML({ can_add_attachment: true, add_attachment_request: 'A"<x>' });
  ok(/data-ec-addfile="A&quot;&lt;x&gt;"/.test(h), "ma phieu duoc escape");
  ok(!/data-act=/.test(h), "nut khong mang data-act (handleActionClick cua trang bo qua)");
  ok(/Thêm tệp/.test(w.EcRemind.buttonHTML(CAP)), "EcRemind.buttonHTML noi nut Them tep");
  ok(!/Thêm tệp/.test(w.EcRemind.buttonHTML({ can_remind: true })), "nguoi gui chi thay Nhac");
}

// ---- moi form -------------------------------------------------------------------------------
const feats = readdirSync(FEAT).filter((f) => existsSync(join(FEAT, f, "ui", "main_section.html")) && !SKIP.has(f));
ok(feats.length >= 31, "du form: " + feats.length);
for (const f of feats) {
  const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
  const route = (readFileSync(join(FEAT, f, "infrastructure", "page_sync.py"), "utf8").match(/ROUTE = "([^"]+)"/) || [])[1];
  { // quyen + luong thanh cong
    const { w, err } = boot(html, route, DET(CAP)); await flush();
    ok(!err, f + ": trang chay duoc " + (err || ""));
    const lbl = w.document.querySelector("label.ec-addfile-btn");
    ok(!!lbl && /Thêm tệp/.test(lbl.textContent), f + ": co nut Them tep");
    if (!lbl) continue;
    ok(lbl.querySelector('input[type="file"][hidden][data-ec-addfile="AR"]'), f + ": input file an trong markup");
    const nCalls = w.__calls.length;
    lbl.click(); await flush();
    ok(w.__calls.length === nCalls, f + ": bam nut khong kich hoat hanh dong khac cua trang");
    const before = detailCalls(w);
    pick(w); await flush();
    const panel = w.document.querySelector(".ec-addfile-panel");
    ok(!!panel && /Plan_Vinasoy\.xlsx/.test(panel.textContent) && /không xoá được/.test(panel.textContent), f + ": hop xac nhan");
    ok(w.__fetch.length === 0, f + ": chua xac nhan thi chua tai len");
    panel.querySelector("[data-ec-addfile-ok]").click(); await flush();
    const up = w.__fetch[0], at = w.__fetch[1];
    ok(up && up[0] === "/api/method/upload_file" && up[1].method === "POST", f + ": upload_file POST");
    if (up) {
      const fd = up[1].body;
      ok(fd.get("is_private") === "1" && !fd.has("doctype") && !fd.has("docname"), f + ": upload rieng tu, khong doctype/docname");
      ok(up[1].headers["X-Frappe-CSRF-Token"] === "tok", f + ": co CSRF");
    }
    ok(at && /reporting\.actions\.add_attachment$/.test(at[0]) && at[1].method === "POST", f + ": goi add_attachment POST");
    if (at) {
      const b = JSON.parse(at[1].body);
      ok(b.request_name === "AR" && b.file_url === "/private/files/Plan_Vinasoy.xlsx", f + ": dung request_name + file_url");
    }
    ok(!w.document.querySelector(".ec-addfile-panel"), f + ": xong thi dong hop");
    const toastTxt = Array.prototype.map.call(w.document.querySelectorAll('[id$="-toast"]'), (t) => t.textContent).join("|");
    ok(/Đã thêm tệp Plan_Vinasoy\.xlsx/.test(toastTxt), f + ": bao thanh cong");
    ok(detailCalls(w) > before, f + ": trang ve lai chi tiet (popstate -> route)");
  }
  { // khong quyen -> khong nut
    const { w } = boot(html, route, DET({ can_approve: true })); await flush();
    ok(!w.document.querySelector(".ec-addfile-btn"), f + ": khong quyen -> khong nut");
  }
}

// ---- loi + duoi cam (mot form dai dien) -----------------------------------------------------
{
  const f = "contract_review";
  const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
  const route = "approvals/contract-review";
  { const { w } = boot(html, route, DET(CAP), "deny"); await flush();
    pick(w); await flush();
    w.document.querySelector("[data-ec-addfile-ok]").click(); await flush();
    const p = w.document.querySelector(".ec-addfile-panel"), err = p && p.querySelector(".ec-addfile-err");
    ok(p && err && !err.hidden && /Chỉ người đang xử lý/.test(err.textContent), "loi server hien ro trong hop");
    const okb = p && p.querySelector("[data-ec-addfile-ok]");
    ok(okb && !okb.disabled && /Thử lại/.test(okb.textContent), "nut Thu lai bat lai"); }
  { const { w } = boot(html, route, DET(CAP), "upload413"); await flush();
    pick(w); await flush();
    w.document.querySelector("[data-ec-addfile-ok]").click(); await flush();
    ok(/quá lớn/.test(w.document.querySelector(".ec-addfile-err").textContent), "413 -> bao tep qua lon");
    ok(w.__fetch.length === 1, "upload hong thi khong goi add_attachment"); }
  { const { w } = boot(html, route, DET(CAP)); await flush();
    pick(w, "x.html"); await flush();
    const p = w.document.querySelector(".ec-addfile-panel");
    ok(p && !p.querySelector("[data-ec-addfile-ok]") && /không được phép/.test(p.textContent), "duoi cam -> khong co nut Them");
    p.querySelector("[data-ec-addfile-cancel]").click();
    ok(!w.document.querySelector(".ec-addfile-panel"), "Dong hop"); }
}

// ---- popup hub /approvals/all-requests -------------------------------------------------------
{
  const html = readFileSync(join(ROOT, "approval_center", "ui", "all_requests", "main_section.html"), "utf8");
  ok(/if\(window\.EcAddFile\) acts\.push\(EcAddFile\.buttonHTML\(cap\)\)/.test(html), "hub: nut trong hang nut popup");
  ok(/"Attachment Added":"Thêm tệp"/.test(html), "hub: nhan lich su tieng Viet");
  const i = html.search(/<script[^>]*id="ec-approval-all"[^>]*>/);
  const markup = html.slice(0, i);
  const js = html.slice(i).match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/approvals/all-requests" });
  const w = dom.window; w.__calls = [];
  const det = Object.assign(DET(CAP), { type_title: "Hợp đồng", business_name: "R-1", display_fields: [] });
  w.frappe = { csrf_token: "tok", call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args]);
    if (m === "get_request_detail") return Promise.resolve({ message: det });
    if (m === "list_requests") return Promise.resolve({ message: { total: 1, rows: [{ name: "AR", approval_request: "AR",
      request_title: "T", approval_type: "CTR", status: "Pending", approval_status: "Pending", requester_info: { name: "A" } }] } });
    return Promise.resolve({ message: {} }); } };
  mockFetch(w);
  w.eval(REMIND); w.eval(ADDF);
  let err = null; try { w.eval(js); } catch (e) { err = e; }
  ok(!err, "hub chay duoc " + (err || ""));
  await flush();
  const tr = w.document.querySelector("tbody tr[data-req]");
  ok(!!tr, "hub: co dong danh sach");
  if (tr) {
    tr.click(); await flush(); await flush();
    const lbl = w.document.querySelector("#ec-apl-ov label.ec-addfile-btn");
    ok(!!lbl, "hub: popup co nut Them tep");
    if (lbl) {
      const n0 = w.__calls.filter((c) => c[0] === "get_request_detail").length;
      let popstate = 0; w.addEventListener("popstate", () => popstate++);
      pick(w); await flush();
      w.document.querySelector("[data-ec-addfile-ok]").click(); await flush(); await flush();
      ok(w.__calls.filter((c) => c[0] === "get_request_detail").length > n0, "hub: them xong -> mo lai chi tiet");
      ok(popstate === 0, "hub: tu ve lai, khong phat popstate");
      ok(!w.document.getElementById("ec-addfile-toast"), "hub: da xu ly su kien -> asset khong bao trung");
      ok(/Đã thêm tệp Plan_Vinasoy\.xlsx vào AR/.test((w.document.getElementById("ec-apl-toast") || {}).textContent || ""), "hub: toast cua hub");
      ok(!w.document.getElementById("ec-apl-ov").hidden, "hub: popup van mo");
    }
  }
}
console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
