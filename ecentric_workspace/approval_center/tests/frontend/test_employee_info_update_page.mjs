// Headless tests for the Employee Information Update page (Node + jsdom).
// Single approval level "HR Review" -> Completed, comments off, auto-title (no request_title input).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "employee_info_update.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-employee-info-update">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = { fields_to_update: [] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-EIU-2026-00001", request_title: "Employee Info Update - u@x - Bank account",
      employee_email: "u@x", field_to_update: "Bank account", current_value: "111", new_value: "222",
      requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "HR Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "hr@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [{ level_no: 1, level_name: "HR Review" }],
    capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/employee-information-update?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("get_form_options")) return Promise.resolve({ message: FO });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-EIU-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-EIU-2026-00001", request_title: "Employee Info Update - u@x - Bank account", employee_email: "u@x",
        field_to_update: "Bank account", requester_name: "U", requested_at: "2026-07-06 09:00", creation: "2026-07-06 09:00",
        approval_status: "Pending", current_level: 1, current_level_name: "HR Review", total_levels: 1 } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-EIU-2026-00001", request_title: "Employee Info Update - u@x - Bank account", requester_name: "U",
        requested_by: "u@x", field_to_update: "Bank account", requested_at: "2026-07-06 09:00",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 1 } ] : [
      { name: "EC-EIU-2026-00002", request_title: "Old", requester_name: "U", requested_by: "u@x", field_to_update: "Mobile phone",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 1 } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    if (m.endsWith("approve")) return Promise.resolve({ message: { detail: detail() } });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.EmployeeInfoUpdate, "EmployeeInfoUpdate exposed");
  // shell: sidebar + Approval Center header/breadcrumb
  ok(!!w.document.querySelector(".ec-sidebar"), "eCentric sidebar (.ec-sidebar) renders");
  ok(/Approval Center/.test(w.document.querySelector(".topbar").innerHTML), "Approval Center header/breadcrumb present");
  ok(!/Powered by ERPNext/.test(w.document.body.innerHTML), "no 'Powered by ERPNext' in rendered markup");
  // tabs
  const tabs = Array.prototype.map.call(w.document.querySelectorAll(".tab"), t => t.textContent.trim());
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered");
  ok(tabs[0] === "Tạo mới" && tabs[1] === "Yêu cầu của tôi" && tabs[2] === "Cần tôi duyệt", "tabs: Tạo mới / Yêu cầu của tôi / Cần tôi duyệt");
  // create fields + summary + vnhelp
  ok(!!w.document.querySelector('[data-model="employee_email"]'), "employee_email field renders");
  { const f2 = w.document.querySelector('[data-model="field_to_update"]');
    ok(!!f2, "field_to_update field renders");
    const wrap = f2.closest('[data-fld="field_to_update"]');
    ok(!!wrap.querySelector(".vnhelp"), "field_to_update has a .vnhelp VN subtitle"); }
  ["current_value", "new_value"].forEach(f => ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"));
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders (optional)");
  ok(!!w.document.getElementById("eiu-summary"), "summary block exists");
  ok(!w.document.querySelector('[data-model="request_title"]'), "NO request_title input");
  ok(!!w.document.getElementById("eiu-process-preview") && w.document.querySelectorAll("#eiu-process-preview .step").length === 3, "single-level process preview (3 steps)");

  // validateSubmit
  w.EmployeeInfoUpdate.state.draft = {};
  { const e = w.EmployeeInfoUpdate.validateSubmit() || {};
    ok(e.employee_email && e.field_to_update && e.current_value && e.new_value, "validateSubmit requires the required set"); }
  w.EmployeeInfoUpdate.state.draft = { employee_email: "not-an-email", field_to_update: "Bank account", current_value: "111", new_value: "222" };
  ok((w.EmployeeInfoUpdate.validateSubmit() || {}).employee_email, "validateSubmit rejects bad email format");
  w.EmployeeInfoUpdate.state.draft = { employee_email: "u@x.com", field_to_update: "Other", current_value: "111", new_value: "222" };
  ok((w.EmployeeInfoUpdate.validateSubmit() || {}).field_to_update_other, "validateSubmit rejects Other without other-text");
  w.EmployeeInfoUpdate.state.draft = { employee_email: "u@x.com", field_to_update: "Bank account", current_value: "111", new_value: "222" };
  ok(w.EmployeeInfoUpdate.validateSubmit() === null, "valid full draft passes (no attachment)");
  ok(!(w.EmployeeInfoUpdate.validateSubmit() || {}).request_attachment, "attachment not required");

  // computed title preview
  ok(w.EmployeeInfoUpdate.titlePreview({ employee_email: "u@x", field_to_update: "Bank account" }) === "Employee Info Update - u@x - Bank account", "computed title preview correct");
  w.EmployeeInfoUpdate.state.draft = { employee_email: "u@x", field_to_update: "Bank account", current_value: "1", new_value: "2" };
  w.EmployeeInfoUpdate.render(); await flush();
  ok(/Employee Info Update - u@x - Bank account/.test(w.document.getElementById("eiu-summary").innerHTML), "computed title preview appears in summary");

  // save_draft carries fields
  w.EmployeeInfoUpdate.state.draft = { employee_email: "u@x.com", field_to_update: "Bank account", current_value: "111", new_value: "222" };
  w.document.getElementById("eiu-save").click(); await flush(); await flush();
  ok(calls.save_draft && /field_to_update/.test(calls.save_draft.payload) && /employee_email/.test(calls.save_draft.payload), "save_draft payload carries fields");

  // My Requests
  w = boot(); await flush(); await flush();
  const cb = () => w.document.getElementById("eiu-body").innerHTML;
  w.history.pushState({}, "", "/approvals/employee-information-update?tab=my-requests"); w.EmployeeInfoUpdate.route(); await flush(); await flush();
  { const ths = Array.prototype.map.call(w.document.querySelectorAll("#eiu-body table.tbl thead th"), t => t.textContent.trim());
    ok(ths[0] === "Ngày request", "My Requests FIRST header is 'Ngày request'");
    ok(ths.indexOf("Người request") >= 0, "My Requests has 'Người request' column");
    ok(/06\/07\/2026 09:00/.test(cb()), "My Requests shows a formatted date");
    ok(/EC-EIU-2026-00001/.test(cb()) && /Bước 2\/3 · HR Review/.test(cb()), "My Requests shows step label"); }

  // detail loads via get_detail and shows title
  w = boot(); await flush(); await flush();
  const cb2 = () => w.document.getElementById("eiu-body").innerHTML;
  w.history.pushState({}, "", "/approvals/employee-information-update?id=EC-EIU-2026-00001"); w.EmployeeInfoUpdate.route(); await flush(); await flush();
  ok(!!calls.get_detail && calls.get_detail.name === "EC-EIU-2026-00001", "detail loads via api.employee_info_update.get_detail");
  ok(/Employee Info Update - u@x - Bank account/.test(cb2()) && !/Không tải được yêu cầu/.test(cb2()), "detail shows the request title");
  ok(/class="stepper"/.test(cb2()), "detail renders runtime stepper");

  // approve modal comment optional
  w.EmployeeInfoUpdate.doApprove("EC-EIU-2026-00001", detail());
  { const ov = w.document.querySelector(".ec-eiu-overlay");
    ok(!!ov && /không bắt buộc/.test(ov.querySelector(".ec-eiu-modal-b").innerHTML), "approve modal comment optional");
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(calls.approve && calls.approve.name === "EC-EIU-2026-00001", "approve callable with empty comment"); }

  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.employee_info_update."/.test(JS), "uses Employee Info Update whitelisted API");
  ok(/#ec-eiu-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  ok(/\.web-footer[^{]*\{[^}]*display:none/.test(HTML), "web-footer hidden (Powered by ERPNext)");

  console.log(fails === 0 ? "\nALL EMPLOYEE INFO UPDATE PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
