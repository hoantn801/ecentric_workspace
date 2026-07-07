// Headless tests for the Employee Referral page (Node + jsdom). Form #8 (3-level, no fulfillment).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "employee_referral.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-employee-referral">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = { relationships: ["Friend", "Relative", "Former colleague", "Other"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-REFR-2026-00001", request_title: "Referral - Nguyen A", candidate_full_name: "Nguyen A",
      candidate_email: "a@x.com", position_applied_for: "Backend Dev", hiring_department: "Engineering",
      relationship_with_referrer: "Friend", referral_justification: "great fit", requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Careers Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "CEO Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "tuan.ly@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/hr-activity?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-REFR-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-REFR-2026-00001", request_title: "Referral A", candidate_full_name: "Nguyen A", position_applied_for: "Backend Dev",
        hiring_department: "Engineering", approval_status: "Pending", current_level: 1,
        current_level_name: "Careers Review", total_levels: 2, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-REFR-2026-00001", request_title: "Referral A", requested_by: "u@x", candidate_full_name: "Nguyen A",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 2, my_status: "Pending" } ] : [
      { name: "EC-REFR-2026-00002", request_title: "Old", requested_by: "u@x", candidate_full_name: "B",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 2, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.EmployeeReferral, "EmployeeReferral exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  const cb = () => w.document.getElementById("refr-body").innerHTML;
  ["request_title", "candidate_full_name", "candidate_email", "position_applied_for", "hiring_department", "relationship_with_referrer", "referral_justification"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders");
  ok(!!w.document.getElementById("refr-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("refr-process-preview");
    ok(pv.querySelectorAll(".step").length === 4, "preview has 4 steps");
    ok(/Careers duyệt/.test(pv.innerHTML) && /CEO duyệt/.test(pv.innerHTML), "preview steps Careers/CEO"); }
  ok(/Friend/.test(cb()) && /Former colleague/.test(cb()) && />Other</.test(cb()), "relationship options render");
  w.EmployeeReferral.state.draft = {};
  { const e = w.EmployeeReferral.validateSubmit() || {};
    ok(e.candidate_full_name && e.candidate_email && e.position_applied_for && e.request_attachment, "validateSubmit requires key fields + attachment"); }
  w.EmployeeReferral.state.draft = { request_title: "T", candidate_full_name: "A", candidate_email: "not-an-email",
    position_applied_for: "Dev", hiring_department: "Eng", relationship_with_referrer: "Friend", referral_justification: "j", request_attachment: "/f" };
  ok((w.EmployeeReferral.validateSubmit() || {}).candidate_email, "invalid email blocked");
  w.EmployeeReferral.state.draft.candidate_email = "a@x.com"; w.EmployeeReferral.state.draft.relationship_with_referrer = "Other";
  ok((w.EmployeeReferral.validateSubmit() || {}).relationship_other, "relationship Other requires relationship_other");
  w.EmployeeReferral.state.draft.relationship_with_referrer = "Friend";
  ok(w.EmployeeReferral.validateSubmit() === null, "valid form passes");
  w.document.getElementById("refr-save").click(); await flush(); await flush();
  ok(calls.save_draft && /candidate_full_name/.test(calls.save_draft.payload) && /relationship_with_referrer/.test(calls.save_draft.payload), "save_draft payload carries fields");
  // My Requests + approvals (current status)
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/hr-activity?tab=my-requests"); w.EmployeeReferral.route(); await flush(); await flush();
  ok(/EC-REFR-2026-00001/.test(cb()) && /Bước 2\/4 · Careers Review/.test(cb()), "My Requests shows step label");
  w.history.pushState({}, "", "/approvals/hr-activity?tab=my-approvals"); w.EmployeeReferral.route(); await flush(); await flush();
  { const done = w.document.getElementById("ap-done").innerHTML;
    ok(/Bước 4\/4 · Hoàn tất/.test(done) && /Đã duyệt/.test(done), "processed list shows current status/step (Hoàn tất)"); }
  // detail runtime stepper
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/hr-activity?id=EC-REFR-2026-00001"); w.EmployeeReferral.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper, no not-found");
  { const rh = w.EmployeeReferral.buildStepper(detail()); ok(/Đã gửi/.test(rh) && /Careers Review/.test(rh) && /CEO Review/.test(rh), "runtime stepper multi-level"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.employee_referral."/.test(JS), "uses Employee Referral whitelisted API");
  ok(/#ec-refr-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  console.log(fails === 0 ? "\nALL EMPLOYEE REFERRAL PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
