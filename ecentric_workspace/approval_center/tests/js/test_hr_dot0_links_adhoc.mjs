// Copyright (c) 2026, eCentric and contributors
// Dot 0 HR (23/11/2026): (1) khoi "Gan phieu duyet" (ec_approval_links.bundle.js) noi vao
// EcAddFile.buttonHTML -> hien tren MOI form khong sua trang; chip phieu rieng tu khong lo tieu de;
// gan phieu rieng tu bat buoc chon quyen doc; (2) form Phe duyet dot xuat: muc Gap bat buoc ly do,
// gui -> save_draft + submit_request; tra lai bo sung -> resubmit; the "Tai lieu & phieu lien quan".
//     node ecentric_workspace/approval_center/tests/js/test_hr_dot0_links_adhoc.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, "..", "..", "..");
const FEAT = join(here, "..", "..", "features");
const REMIND = readFileSync(join(ROOT, "public", "js", "ec_remind.bundle.js"), "utf8");
const ADDF = readFileSync(join(ROOT, "public", "js", "ec_addfile.bundle.js"), "utf8");
const LINKS = readFileSync(join(ROOT, "public", "js", "ec_approval_links.bundle.js"), "utf8");
const ADHOC = readFileSync(join(FEAT, "adhoc_approval", "ui", "main_section.html"), "utf8");
const SVRF = readFileSync(join(FEAT, "service_referral", "ui", "main_section.html"), "utf8");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setTimeout(r, 5)); };

const CHIPS = [
  { request: "APR-T", code: "EC-ADHOC-2026-00015", title: null, private: true, can_open: false, detail_url: null,
    status: "Approved", status_label: "Đã duyệt", bad: false, shared: false, used_elsewhere: 2, link: "LK-1", can_unlink: false },
  { request: "APR-R", code: "EC-PURR-2026-00231", title: "ĐNMH <b>thiết bị</b>", private: false, can_open: true,
    detail_url: "/approvals/purchase-request?id=EC-PURR-2026-00231", status: "Rejected", status_label: "Bị từ chối",
    bad: true, override_reason: "", link: "LK-2", can_unlink: true }];
const CAP = (over) => Object.assign({ can_approve: true, can_reject: true, can_request_information: true,
  approval_links: CHIPS, can_link_approval: true, approval_link_host: { doctype: "EC Payment Request", name: "R-1" } }, over || {});

function mockFetch(w) {
  w.__fetch = [];
  w.fetch = (url, opts) => {
    w.__fetch.push([url, opts]);
    const res = (status, body) => Promise.resolve({ status, ok: status < 400, json: () => Promise.resolve(body) });
    if (url.indexOf("search_linkable") >= 0) return res(200, { message: { rows: [
      { request: "APR-P", code: "EC-ADHOC-2026-00099", title: "Tăng ngân sách", private: true, can_attach: true,
        status: "Approved", status_label: "Đã duyệt", already_linked: false, used_elsewhere: 0 }] } });
    if (url.indexOf("link_approval") >= 0) return res(200, { message: { duplicate: false, chips: [CHIPS[0]] } });
    if (url.indexOf("list_approval_links") >= 0) return res(200, { message: { approval_links: [], can_link_approval: true } });
    return res(404, {});
  };
}

function boot(html, route, det, calls) {
  const i = html.search(/<script[^>]*id="ec-[^"]+"[^>]*>/);
  const markup = html.slice(0, i);
  const js = html.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/" + route });
  const w = dom.window; w.__calls = calls || [];
  w.frappe = { csrf_token: "tok", session: { user: "req@x" }, call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args]);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, all: true }, context: { user: "req@x", employee_name: "A" }, form_options: { urgency_levels: ["Bình thường", "Gấp"] } } });
    if (m === "get_detail") return Promise.resolve({ message: det });
    if (m === "save_draft") return Promise.resolve({ message: { name: "EC-ADHOC-1" } });
    if (m === "search_cc_users") return Promise.resolve({ message: [
      { user: "ketoan@x", full_name: "Kế Toán", department: "Finance - EC" },
      { user: "linh@x", full_name: "Linh <b>V</b>", department: "" }] });
    return Promise.resolve({ message: { rows: [], total: 0 } }); } };
  w.confirm = () => true;
  mockFetch(w);
  w.eval(REMIND); w.eval(ADDF); w.eval(LINKS);
  w.eval(js);
  return w;
}
const DET = (cap, biz, ap) => ({ business: Object.assign({ name: "R-1", requested_by: "req@x", request_title: "T" }, biz || {}),
  approval: Object.assign({ name: "AR", approval_status: "Pending", current_level: 1 }, ap || {}),
  levels: [{ level_no: 1, level_name: "CEO duyệt", level_status: "In Progress" }],
  approvers: [{ level_no: 1, approver: "ceo@x", status: "Pending" }], attachments: [], timeline: [],
  capabilities: cap, privacy: { private: true, watchers: [{ user: "w@x", name: "W" }], access_log: [{ user: "sm@x", via: "System Manager", accessed_at: "2026-11-23 10:05:00" }] } });

// ---- 1. Khoi chip tren mot form CU (service_referral) qua EcAddFile.buttonHTML ----------------
{
  const w = boot(SVRF, "approvals/service-referral?id=R-1", DET(CAP()));
  await flush();
  const box = w.document.querySelector(".ec-aplk");
  ok(!!box, "form cu co khoi Gan phieu duyet ma khong sua trang");
  const chips = box ? box.querySelectorAll(".ec-aplk-chip") : [];
  ok(chips.length === 2, "2 chip");
  ok(chips[0] && /Phiếu riêng tư/.test(chips[0].textContent) && !chips[0].querySelector("a"), "chip rieng tu: khong tieu de, khong link");
  ok(chips[0] && /Đã gắn vào 2 phiếu khác/.test(chips[0].textContent), "dem so lan dung lai");
  ok(chips[1] && chips[1].classList.contains("ec-aplk-chip--bad"), "chip phieu bi tu choi to do");
  ok(chips[1] && chips[1].innerHTML.indexOf("<b>thiết bị</b>") < 0, "tieu de duoc escape");
  ok(!!w.document.querySelector("[data-ec-aplk-reason]"), "nut ghi ly do cho phieu bi tu choi");
  ok(!!w.document.querySelector("[data-ec-aplk-unlink=\"LK-2\"]") && !w.document.querySelector("[data-ec-aplk-unlink=\"LK-1\"]"), "chi chip can_unlink co nut go");
  // Khong co quyen gan + khong chip -> khong ve gi
  const html0 = w.EcApprovalLinks.blockHTML({ approval_links: [], can_link_approval: false, approval_link_host: { doctype: "X", name: "Y" } });
  ok(html0 === "", "khong quyen + khong chip -> rong");

  // ---- mo hop chon, phieu rieng tu bat buoc chon quyen doc ----
  w.document.querySelector("[data-ec-aplk-open]").click();
  await flush();
  const ov = w.document.querySelector(".ec-aplk-overlay");
  ok(!!ov, "mo hop chon phieu");
  const searchCall = w.__fetch.find((f) => f[0].indexOf("search_linkable") >= 0);
  ok(searchCall && /host_doctype=EC%20Payment%20Request/.test(searchCall[0]) && /box=mine/.test(searchCall[0]), "tim phieu: dung host + pham vi Cua toi");
  const okBtn = ov.querySelector("[data-ok]");
  ok(okBtn.disabled, "chua chon -> nut Gan khoa");
  ov.querySelector("tr[data-i='0']").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  ok(!ov.querySelector(".ec-aplk-choice").hidden, "phieu rieng tu -> hien lua chon quyen doc");
  ok(okBtn.disabled, "chua chon quyen doc -> van khoa");
  const r1 = ov.querySelector("input[name=ec-aplk-share][value='1']");
  r1.checked = true; r1.dispatchEvent(new w.Event("change", { bubbles: true }));
  ok(!okBtn.disabled, "chon roi -> mo nut");
  okBtn.click();
  await flush();
  const linkCall = w.__fetch.find((f) => f[0].indexOf("link_approval") >= 0);
  const body = linkCall ? JSON.parse(linkCall[1].body) : {};
  ok(linkCall && linkCall[1].method === "POST" && body.share === "1" && body.target_request === "APR-P", "POST link_approval share=1");
  ok(!w.document.querySelector(".ec-aplk-overlay"), "dong hop sau khi gan");
  ok(w.document.querySelectorAll(".ec-aplk-chip").length === 1, "khoi ve lai theo ket qua server");
}

// ---- 2. Form Phe duyet dot xuat ------------------------------------------------------------
{
  const w = boot(ADHOC, "approvals/adhoc-approval", DET(CAP()));
  await flush();
  ok(/Phiếu riêng tư/.test(w.document.body.textContent), "trang noi ro phieu rieng tu");
  ok(/không thay/.test(w.document.querySelector("#adhc-private-note").textContent), "ghi chu khong thay cap duyet bat buoc");
  const box = w.document.getElementById("adhc-urgent-box");
  ok(box && box.hidden, "mac dinh Binh thuong -> an ly do gap");
  const sel = w.document.getElementById("adhc-urgency");
  sel.value = "Gấp"; sel.dispatchEvent(new w.Event("change", { bubbles: true }));
  ok(!w.document.getElementById("adhc-urgent-box").hidden, "chon Gap -> hien ly do");
  const t = w.document.getElementById("adhc-title"); t.value = "Tăng ngân sách"; t.dispatchEvent(new w.Event("input", { bubbles: true }));
  const c = w.document.getElementById("adhc-content"); c.value = "Nội dung"; c.dispatchEvent(new w.Event("input", { bubbles: true }));
  w.document.getElementById("adhc-submit").click();
  await flush();
  ok(!w.__calls.some((x) => x[0] === "save_draft"), "Gap thieu ly do -> khong goi server");
  ok(/Phiếu Gấp bắt buộc/.test(w.document.querySelector('[data-fld="urgency_reason"]').textContent), "bao loi tai o ly do");
  const r = w.document.getElementById("adhc-urgent-reason"); r.value = "brand chốt"; r.dispatchEvent(new w.Event("input", { bubbles: true }));
  w.document.getElementById("adhc-submit").click();
  await flush();
  const sd = w.__calls.find((x) => x[0] === "save_draft");
  ok(sd && JSON.parse(sd[1].payload).urgency === "Gấp", "save_draft mang muc Gap");
  ok(sd && !JSON.parse(sd[1].payload).cc_users, "khong CC -> khong gui cc_users");
  ok(w.__calls.some((x) => x[0] === "submit_request"), "gui -> submit_request");
}
{
  // O CC: go 1 ky tu khong tim; go 2+ ky tu -> search_cc_users; chon -> chip; luu nhap mang cc_users.
  const w = boot(ADHOC, "approvals/adhoc-approval", DET(CAP()));
  await flush();
  const q = w.document.getElementById("adhc-cc-q");
  ok(!!q, "co o CC");
  q.value = "k"; q.dispatchEvent(new w.Event("input", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300)); await flush();
  ok(!w.__calls.some((x) => x[0] === "search_cc_users"), "1 ky tu -> chua tim");
  q.value = "ke"; q.dispatchEvent(new w.Event("input", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300)); await flush();
  const sc = w.__calls.find((x) => x[0] === "search_cc_users");
  ok(sc && sc[1].q === "ke", "2 ky tu -> search_cc_users");
  const drop = w.document.getElementById("adhc-cc-drop");
  ok(drop && !drop.hidden && drop.querySelectorAll("[data-i]").length === 2, "hien 2 goi y");
  ok(drop.innerHTML.indexOf("<b>V</b>") < 0, "ten goi y duoc escape");
  drop.querySelector("[data-i='0']").dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true }));
  const chips = w.document.querySelectorAll("#adhc-cc-chips .cc-chip");
  ok(chips.length === 1 && /Kế Toán/.test(chips[0].textContent), "chon -> chip ten");
  q.value = "sep@cong.ty"; q.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  ok(w.document.querySelectorAll("#adhc-cc-chips .cc-chip").length === 2, "Enter email hop le -> them chip");
  ok(/Kế Toán/.test(w.document.getElementById("adhc-summary").textContent) || /ketoan@x/.test(w.document.getElementById("adhc-summary").textContent), "tom tat co CC");
  w.document.querySelector("[data-ccrm='sep@cong.ty']").click();
  ok(w.document.querySelectorAll("#adhc-cc-chips .cc-chip").length === 1, "bo chip");
  const t = w.document.getElementById("adhc-title"); t.value = "T"; t.dispatchEvent(new w.Event("input", { bubbles: true }));
  const c = w.document.getElementById("adhc-content"); c.value = "C"; c.dispatchEvent(new w.Event("input", { bubbles: true }));
  w.document.getElementById("adhc-save").click();
  await flush();
  const sd = w.__calls.find((x) => x[0] === "save_draft");
  ok(sd && JSON.parse(sd[1].payload).cc_users === "ketoan@x", "luu nhap mang cc_users");
}
{
  // Chi tiet: the Tai lieu & phieu lien quan co chip; khu Hanh dong KHONG ve chip lan hai.
  const det = DET(CAP({ can_approve: false, can_reject: false, can_request_information: false,
    can_edit: true }), { urgency: "Gấp", urgency_reason: "gấp", content: "C" }, { approval_status: "Information Required" });
  const w = boot(ADHOC, "approvals/adhoc-approval?id=R-1", det);
  await flush();
  ok(w.document.querySelectorAll(".ec-aplk").length === 1, "chip chi ve MOT lan (the tai lieu)");
  ok(/Người theo dõi/.test(w.document.body.textContent), "khoi nguoi theo doi");
  ok(/Nhật ký truy cập/.test(w.document.body.textContent), "nhat ky truy cap");
  ok(/4 giờ làm việc/.test(w.document.body.textContent), "han Gap 4 gio lam viec");
  const edit = w.document.querySelector('[data-act="edit"]');
  ok(!!edit, "Can bo sung -> nut Chinh sua & gui lai");
  edit.click();
  await flush();
  w.document.getElementById("adhc-submit").click();
  await flush();
  ok(w.__calls.some((x) => x[0] === "resubmit") && !w.__calls.some((x) => x[0] === "submit_request"), "gui lai -> resubmit");
}

console.log("JS: " + oks + " dat, " + fails + " hong");
if (fails) process.exit(1);
