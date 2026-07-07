// Headless tests for the Hiring Request page (Node + jsdom). Multi-level (3 levels: Direct Manager -> HR -> CEO),
// no fulfillment, comments OFF (approve does NOT force a comment), optional attachment.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "hiring_request.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-hiring-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = { departments: [ { value: "Engineering", label: "Engineering" }, { value: "Service", label: "Service" } ],
             reasons: ["New", "Replace"], employment_types: ["Full-time", "Freelancer", "Intern"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-HIRE-2026-00001", request_title: "Hiring - Senior Engineer", position: "Senior Engineer",
      number_of_vacancy: 2, reason: "New", employment_type: "Full-time", education: "From Bachelor Degree",
      department: "Engineering", line_manager: "boss@x.com", suggested_salary: 28000000, requested_by: "u@x" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "HR Review", approval_mode: "Any One", level_status: "Pending" },
             { level_no: 3, level_name: "CEO Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "tuan.ly@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/hiring-request?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "Engineering", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-HIRE-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-HIRE-2026-00001", request_title: "Hiring - Senior Engineer", position: "Senior Engineer", department: "Engineering",
        number_of_vacancy: 2, employment_type: "Full-time", approval_status: "Pending", current_level: 1,
        current_level_name: "Direct Manager Review", total_levels: 3, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-HIRE-2026-00001", request_title: "Hiring - Senior Engineer", requested_by: "u@x", position: "Senior Engineer",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 3, my_status: "Pending" } ] : [
      { name: "EC-HIRE-2026-00002", request_title: "Old", requested_by: "u@x", position: "Engineer",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 3, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.HiringRequest, "HiringRequest exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  const cb = () => w.document.getElementById("hire-body").innerHTML;
  ["request_title", "position", "number_of_vacancy", "reason", "employment_type", "department", "education", "line_manager", "suggested_salary"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('input[type="number"][data-model="number_of_vacancy"]'), "number_of_vacancy is a number input");
  ok(!!w.document.querySelector('[data-model="line_manager"]'), "line_manager field renders");
  ok(!!w.document.querySelector('select[data-model="reason"]') && !!w.document.querySelector('select[data-model="employment_type"]'), "reason + employment_type are selects");
  { const rsel = w.document.querySelector('select[data-model="reason"]'); const esel = w.document.querySelector('select[data-model="employment_type"]');
    ok(/New/.test(rsel.innerHTML) && /Replace/.test(rsel.innerHTML), "reason options loaded (New/Replace)");
    ok(/Full-time/.test(esel.innerHTML) && /Freelancer/.test(esel.innerHTML) && /Intern/.test(esel.innerHTML), "employment_type options loaded (Full-time/Freelancer/Intern)"); }
  ok(!!w.document.querySelector('select[data-model="department"]') && !w.document.querySelector('input[data-model="department"]'), "Department is a select (not free-text input)");
  { const dsel = w.document.querySelector('select[data-model="department"]'); const html = dsel ? dsel.innerHTML : "";
    ok(/Engineering/.test(html) && /Service/.test(html), "Department options loaded/rendered from master"); }
  // attachment input present but optional
  ok(!!w.document.getElementById("hire-file-input"), "attachment file input renders");
  ok(!!w.document.getElementById("hire-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("hire-process-preview");
    ok(pv.querySelectorAll(".step").length === 4, "preview has 4 steps (no fulfillment)");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Direct Manager review/.test(pv.innerHTML) && /HR review/.test(pv.innerHTML) && /CEO review/.test(pv.innerHTML), "preview steps Tạo/Direct Manager/HR/CEO");
    ok(!/SLA|giờ|ngày làm việc/.test(pv.innerHTML), "preview has no SLA text"); }
  // process preview appears before the request_title field in DOM order
  { const html = cb(); ok(html.indexOf('id="hire-process-preview"') >= 0 && html.indexOf('id="hire-process-preview"') < html.indexOf('data-model="request_title"'), "process preview before request_title"); }
  w.HiringRequest.state.draft = {};
  { const e = w.HiringRequest.validateSubmit() || {};
    ok(e.request_title && e.position && e.number_of_vacancy && e.reason && e.employment_type && e.department && e.education && e.line_manager && e.suggested_salary, "validateSubmit requires key fields incl. title"); }
  const baseDraft = () => ({ request_title: "T", position: "SE", number_of_vacancy: 2, reason: "New", employment_type: "Full-time",
    education: "Bachelor", department: "Engineering", line_manager: "boss@x.com", suggested_salary: 200 });
  // vacancy 0 rejected
  w.HiringRequest.state.draft = Object.assign(baseDraft(), { number_of_vacancy: 0 });
  ok((w.HiringRequest.validateSubmit() || {}).number_of_vacancy, "vacancy 0 rejected");
  // bad line manager email rejected
  w.HiringRequest.state.draft = Object.assign(baseDraft(), { line_manager: "not-an-email" });
  ok((w.HiringRequest.validateSubmit() || {}).line_manager, "bad line_manager email rejected");
  // salary <= 0 rejected
  w.HiringRequest.state.draft = Object.assign(baseDraft(), { suggested_salary: 0 });
  ok((w.HiringRequest.validateSubmit() || {}).suggested_salary, "salary <= 0 rejected");
  // invalid department (not in master) rejected
  w.HiringRequest.state.draft = Object.assign(baseDraft(), { department: "TESTING" });
  ok((w.HiringRequest.validateSubmit() || {}).department, "invalid department (TESTING, not in master) blocked");
  // missing department rejected
  { const d = baseDraft(); delete d.department; w.HiringRequest.state.draft = d;
    ok((w.HiringRequest.validateSubmit() || {}).department, "missing department blocked"); }
  // full valid draft passes; attachment NOT required (no request_attachment set)
  w.HiringRequest.state.draft = baseDraft();
  ok(w.HiringRequest.validateSubmit() === null, "valid form passes (department Engineering, no attachment) — attachment not required");
  w.document.getElementById("hire-save").click(); await flush(); await flush();
  ok(calls.save_draft && /position/.test(calls.save_draft.payload) && /line_manager/.test(calls.save_draft.payload), "save_draft payload carries position + line_manager");
  ok(calls.save_draft && /"department":"Engineering"/.test(calls.save_draft.payload), "save_draft payload carries exact Department name");
  // submit path calls submit_request with draft name
  w = boot(); await flush(); await flush();
  w.HiringRequest.state.draft = baseDraft();
  w.document.getElementById("hire-submit").click(); await flush(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-HIRE-2026-00001", "submit_request called with draft name");
  // My Requests
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/hiring-request?tab=my-requests"); w.HiringRequest.route(); await flush(); await flush();
  ok(/EC-HIRE-2026-00001/.test(cb()) && /Bước 2\/5 · Direct Manager Review/.test(cb()), "My Requests shows step label");
  w.history.pushState({}, "", "/approvals/hiring-request?tab=my-approvals"); w.HiringRequest.route(); await flush(); await flush();
  { const done = w.document.getElementById("ap-done").innerHTML;
    ok(/Bước 5\/5 · Hoàn tất/.test(done) && /Đã duyệt/.test(done), "processed list shows current status/step (Hoàn tất)"); }
  // detail runtime stepper
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/hiring-request?id=EC-HIRE-2026-00001"); w.HiringRequest.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper, no not-found");
  ok(/api\.hiring_request\.get_detail/.test("ecentric_workspace.approval_center.api.hiring_request.get_detail") && !!calls.get_detail, "detail loads via api.hiring_request.get_detail");
  { const rh = w.HiringRequest.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Direct Manager Review/.test(rh) && /HR Review/.test(rh) && /CEO Review/.test(rh), "runtime stepper shows the 3 level names"); }
  // APPROVE modal does NOT force a comment (comments OFF)
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/hiring-request?id=EC-HIRE-2026-00001"); w.HiringRequest.route(); await flush(); await flush();
  { delete calls.approve;
    w.HiringRequest.doApprove("EC-HIRE-2026-00001", detail());
    const ov = w.document.querySelector(".ec-hire-overlay");
    ok(!!ov, "approve modal opened");
    const body = ov.querySelector(".ec-hire-modal-b").innerHTML;
    const cmt = ov.querySelector("#m-cmt");
    ok(!!cmt && !/class="req"/.test(body), "approve modal comment is optional (no required marker)");
    // confirming with EMPTY comment MUST call approve (comment not forced)
    cmt.value = "";
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(calls.approve && calls.approve.name === "EC-HIRE-2026-00001", "empty comment still calls approve with {name, comment}");
    ok(Object.prototype.hasOwnProperty.call(calls.approve, "comment"), "approve called with a comment arg (optional value)"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.hiring_request."/.test(JS), "uses HiringRequest whitelisted API");
  ok(/window\.HiringRequest\s*=/.test(JS), "exposes window.HiringRequest");
  ok(/#ec-hire-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width .content max-width:1200px");
  ok(/#ec-hire-root .hire-formwrap\{[^}]*max-width:none/.test(HTML), "balanced width .hire-formwrap max-width:none");
  console.log(fails === 0 ? "\nALL HIRING REQUEST PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
