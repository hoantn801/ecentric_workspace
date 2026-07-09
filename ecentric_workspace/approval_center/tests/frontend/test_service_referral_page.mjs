// Headless jsdom tests for the Service Referral page (Batch 7, rebuilt on the eCentric shell).
// Single-level "Referral Review" (Any One: Linh / Vinh), comments off, auto-title (no request_title input).
// Verifies the shell regression fix: .ec-sidebar + Approval Center header, no "Powered by ERPNext",
// 3 tabs, Any-One pool visible in summary + detail, standard list columns, typed buttons, no Desk shim.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "service_referral.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-service-referral">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const calls = {};
let w;
function detail(over) {
  return Object.assign({
    business: { name: "EC-SVRF-2026-00001", request_title: "Service Referral - ACME - BrandX",
      client: "ACME", brand: "BrandX", contact_name: "John", contact_phone_number: "+84 090-111 222",
      contact_email: "john@acme.com", estimated_contract_value: 1000, justification: "Strong lead",
      requester_name: "U", requested_by: "u@x", department: "D", creation: "2026-07-08 09:00" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Referral Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "linh@x", status: "Pending" },
                { level_no: 1, approver: "vinh@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-08 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function listRow() {
  return { name: "EC-SVRF-2026-00001", request_title: "Service Referral - ACME - BrandX", client: "ACME", brand: "BrandX",
    estimated_contract_value: 1000, approval_status: "Pending", current_level: 1, current_level_name: "Referral Review",
    total_levels: 1, creation: "2026-07-08 09:00", requested_at: "2026-07-08 09:00", requester_name: "U" };
}
function boot() {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/service-referral?tab=create" });
  const win = dom.window;
  win.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", department: "D" }, is_system_manager: false, form_options: {} } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-SVRF-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [ listRow() ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [ Object.assign(listRow(), { level_no: 1, my_status: "Pending" }) ] : []) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: detail() });
    if (m.endsWith("approve")) return Promise.resolve({ message: { detail: detail({ approval: { approval_status: "Approved" } }) } });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  } };
  win.eval(JS);
  return win;
}
const LV = () => w.ServiceReferral;
function nav(tab){ w.history.pushState({}, "", "/approvals/service-referral?tab=" + tab); LV().route(); }
async function run() {
  w = boot(); await flush(); await flush();
  ok(!!w.ServiceReferral, "ServiceReferral exposed");

  // ---- shell regression fix ----
  ok(!!w.document.querySelector("#ec-svrf-root .ec-sidebar"), "eCentric sidebar (.ec-sidebar) present");
  ok(/Approval Center/.test(w.document.querySelector(".topbar").textContent), "Approval Center header/breadcrumb present");
  ok(HTML.indexOf("Powered by ERPNext") < 0, 'no "Powered by ERPNext" in markup');
  ok(/\.web-footer\s*\{[^}]*display:none/.test(HTML), ".web-footer hidden via CSS");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs render (Tao moi | Yeu cau cua toi | Can toi duyet)");

  // ---- create fields ----
  ["client", "brand", "contact_name", "contact_phone_number", "contact_email", "estimated_contract_value", "justification"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders (optional)");
  ok(!w.document.querySelector('[data-model="request_title"]'), "NO request_title input (auto-title)");

  // ---- summary: auto-title + Any-One pool ----
  LV().state.draft = { client: "ACME", brand: "BrandX", contact_name: "John", estimated_contract_value: 1000 }; LV().render(); await flush();
  const sum = () => w.document.getElementById("svrf-summary").innerHTML;
  ok(sum().indexOf("Service Referral - ACME - BrandX") >= 0, "auto title shown in summary");
  ok(LV().titlePreview({ client: "ACME", brand: "BrandX" }) === "Service Referral - ACME - BrandX", "titlePreview builds auto title");
  ok(/Linh\s*\/\s*Vinh/.test(sum()), "summary flow row shows Any-One pool (Linh / Vinh)");

  // ---- validation ----
  LV().state.draft = {};
  { const e = LV().validateSubmit() || {};
    ok(e.client && e.brand && e.contact_name && e.estimated_contract_value, "validateSubmit requires client/brand/contact_name/value"); }
  LV().state.draft = { client: "A", brand: "B", contact_name: "C", estimated_contract_value: -5 };
  ok((LV().validateSubmit() || {}).estimated_contract_value, "negative estimated_contract_value rejected");
  LV().state.draft = { client: "A", brand: "B", contact_name: "C", estimated_contract_value: 1, contact_email: "bad" };
  ok((LV().validateSubmit() || {}).contact_email, "invalid contact_email blocked");
  LV().state.draft = { client: "ACME", brand: "BrandX", contact_name: "John", estimated_contract_value: 1000 };
  ok(LV().validateSubmit() === null, "valid draft passes (attachment optional, no email)");
  ok(!(LV().validateSubmit() || {}).request_attachment, "attachment not required");

  // ---- submit without attachment ----
  w = boot(); await flush(); await flush();
  LV().state.draft = { client: "ACME", brand: "BrandX", contact_name: "John", estimated_contract_value: 1000 };
  w.document.getElementById("svrf-submit").click(); await flush(); await flush();
  ok(!!calls.save_draft && !!calls.submit_request, "submit works without attachment (save_draft + submit_request called)");
  ok(/client/.test(calls.save_draft.payload) && /estimated_contract_value/.test(calls.save_draft.payload), "save_draft payload carries fields");
  ok(!/request_attachment/.test(calls.save_draft.payload), "attachment absent from payload when not uploaded");

  // ---- My Requests: standard columns ----
  w = boot(); await flush(); await flush();
  nav("my-requests"); await flush(); await flush();
  { const lb = w.document.getElementById("svrf-body").innerHTML;
    ok(lb.indexOf("Ngày request") >= 0 && lb.indexOf("Ngày request") < lb.indexOf("Mã"), "My Requests: 'Ngày request' is first header");
    ok(lb.indexOf("Người request") >= 0, "My Requests: 'Người request' header present");
    ok(lb.indexOf("Client") >= 0 && lb.indexOf("Brand") >= 0 && lb.indexOf("Giá trị") >= 0, "My Requests: Client/Brand/Giá trị headers present");
    ok(lb.indexOf("Service Referral - ACME - BrandX") >= 0, "My Requests: auto-title in row");
    ok(/08\/07\/2026 09:00/.test(lb), "My Requests: formatted date via fmtDT"); }

  // ---- detail: title + Any-One pool in stepper ----
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/service-referral?id=EC-SVRF-2026-00001"); LV().route(); await flush(); await flush();
  { const db = w.document.getElementById("svrf-body").innerHTML;
    ok(db.indexOf("Service Referral - ACME - BrandX") >= 0, "detail (get_detail) shows request_title");
    ok(/class="stepper"/.test(db) && !/Không tải được yêu cầu/.test(db), "detail renders runtime stepper, no not-found");
    ok(/Referral Review/.test(db) && /Any One/.test(db) && /linh@x\s*\/\s*vinh@x/.test(db), "detail lists Any-One approver pool (linh / vinh)"); }
  { const rh = LV().buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Referral Review/.test(rh) && /Hoàn tất/.test(rh), "runtime stepper single-level (Đã gửi / Referral Review / Hoàn tất)"); }

  // ---- approve modal: comment optional ----
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/service-referral?id=EC-SVRF-2026-00001"); LV().route(); await flush(); await flush();
  LV().doApprove("EC-SVRF-2026-00001", detail()); await flush();
  { const ov = w.document.querySelector(".ec-svrf-overlay"); ok(!!ov, "approve modal opens");
    const reqd = /Ghi ch[^<]*<span class="req">/.test(ov.innerHTML);
    ok(reqd === false, "approve modal comment is OPTIONAL (no req marker)"); }

  // ---- guardrails ----
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every <button> has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(JS.indexOf('"ecentric_workspace.approval_center.api.service_referral."') >= 0, "uses service_referral whitelisted API namespace");
  ok(!/call\("(resubmit|cancel|admin_approve_current_level)"/.test(JS), "no out-of-contract backend method calls");
  ok(/#ec-svrf-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width CSS present");
  ok(/@media \(max-width:1024px\)/.test(HTML), "responsive @media (max-width:1024px) present");

  console.log(fails === 0 ? "\nALL SERVICE REFERRAL PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
