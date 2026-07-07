// Headless tests for the HR Activity page (Node + jsdom). Form #8 (3-level, no fulfillment).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "hr_activity.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-hr-activity">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = { activity_types: ["Double day", "Quarterly team bonding", "Holiday and anniversary", "Company trip", "Year-end party", "Medical checkup", "Monthly L&D", "Other"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-HRAC-2026-00001", request_title: "Company trip - 2026-09", activity_type: "Company trip",
      start_date: "2026-09-01", end_date: "2026-09-03", estimated_budget: 5000000, detail: "trip", participants: "all",
      justification: "morale", vendor_trainer_partner_info: "vendor X", requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "HR Manager Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "HOF Review", approval_mode: "Any One", level_status: "Pending" },
             { level_no: 3, level_name: "CEO Review", approval_mode: "Any One", level_status: "Pending" }],
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
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-HRAC-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-HRAC-2026-00001", request_title: "Company trip", activity_type: "Company trip", start_date: "2026-09-01",
        end_date: "2026-09-03", estimated_budget: 5000000, approval_status: "Pending", current_level: 1,
        current_level_name: "HR Manager Review", total_levels: 3, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-HRAC-2026-00001", request_title: "Company trip", requested_by: "u@x", activity_type: "Company trip",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 3, my_status: "Pending" } ] : [
      { name: "EC-HRAC-2026-00002", request_title: "Old", requested_by: "u@x", activity_type: "Company trip",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 3, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.HRActivity, "HRActivity exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  const cb = () => w.document.getElementById("hrac-body").innerHTML;
  ["request_title", "activity_type", "start_date", "end_date", "estimated_budget", "detail", "participants", "justification", "vendor_trainer_partner_info"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders");
  ok(!!w.document.getElementById("hrac-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("hrac-process-preview");
    ok(pv.querySelectorAll(".step").length === 5, "preview has 5 steps");
    ok(/HR Manager duyệt/.test(pv.innerHTML) && /HOF duyệt/.test(pv.innerHTML) && /CEO duyệt/.test(pv.innerHTML), "preview steps HR Manager/HOF/CEO"); }
  ok(/Company trip/.test(cb()) && /Monthly L&amp;D|Monthly L&D/.test(cb()) && />Other</.test(cb()), "activity_type options render");
  w.HRActivity.state.draft = {};
  { const e = w.HRActivity.validateSubmit() || {};
    ok(e.activity_type && e.detail && e.estimated_budget && e.vendor_trainer_partner_info && e.request_attachment, "validateSubmit requires key fields + attachment"); }
  w.HRActivity.state.draft = { request_title: "T", activity_type: "Company trip", detail: "d", start_date: "2026-09-05", end_date: "2026-09-01", estimated_budget: 100, participants: "p", justification: "j", vendor_trainer_partner_info: "v", request_attachment: "/f" };
  ok((w.HRActivity.validateSubmit() || {}).end_date, "end before start blocked");
  w.HRActivity.state.draft.end_date = "2026-09-10"; w.HRActivity.state.draft.estimated_budget = -5;
  ok((w.HRActivity.validateSubmit() || {}).estimated_budget, "negative budget blocked");
  w.HRActivity.state.draft.estimated_budget = 100;
  ok(w.HRActivity.validateSubmit() === null, "valid form passes");
  w.document.getElementById("hrac-save").click(); await flush(); await flush();
  ok(calls.save_draft && /activity_type/.test(calls.save_draft.payload) && /estimated_budget/.test(calls.save_draft.payload), "save_draft payload carries fields");
  // My Requests + approvals (current status)
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/hr-activity?tab=my-requests"); w.HRActivity.route(); await flush(); await flush();
  ok(/EC-HRAC-2026-00001/.test(cb()) && /Bước 2\/5 · HR Manager Review/.test(cb()), "My Requests shows step label");
  w.history.pushState({}, "", "/approvals/hr-activity?tab=my-approvals"); w.HRActivity.route(); await flush(); await flush();
  { const done = w.document.getElementById("ap-done").innerHTML;
    ok(/Bước 5\/5 · Hoàn tất/.test(done) && /Đã duyệt/.test(done), "processed list shows current status/step (Hoàn tất)"); }
  // detail runtime stepper
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/hr-activity?id=EC-HRAC-2026-00001"); w.HRActivity.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper, no not-found");
  { const rh = w.HRActivity.buildStepper(detail()); ok(/Đã gửi/.test(rh) && /HR Manager Review/.test(rh) && /CEO Review/.test(rh), "runtime stepper multi-level"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.hr_activity."/.test(JS), "uses HR Activity whitelisted API");
  ok(/#ec-hrac-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  console.log(fails === 0 ? "\nALL HR ACTIVITY PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
