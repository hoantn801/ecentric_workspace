// Headless tests for the Compensation Leave page (Node + jsdom). Single-level, no fulfillment, auto-title.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "compensation_leave.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-compensation-leave">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-CPLV-2026-00001", request_title: "Compensation Leave - 2026-08-10 to 2026-08-11",
      overtime_start_date: "2026-08-01", overtime_end_date: "2026-08-02", overtime_duration_days: 2,
      cl_start_date: "2026-08-10", cl_end_date: "2026-08-11", cl_duration_days: 2, remarks: "OT bu du an",
      requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "mgr@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/compensation-leave?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: {} } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-CPLV-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-CPLV-2026-00001", request_title: "Compensation Leave - 2026-08-10 to 2026-08-11",
        cl_start_date: "2026-08-10", cl_end_date: "2026-08-11", cl_duration_days: 2,
        approval_status: "Pending", current_level: 1, current_level_name: "Direct Manager Review", total_levels: 1,
        requester_name: "U", requested_at: "2026-07-06 09:00", creation: "2026-07-06 09:00", modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-CPLV-2026-00001", request_title: "Compensation Leave - 2026-08-10 to 2026-08-11", requester_name: "U", requested_by: "u@x",
        cl_start_date: "2026-08-10", cl_end_date: "2026-08-11", cl_duration_days: 2,
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 1, my_status: "Pending",
        requested_at: "2026-07-06 09:00", creation: "2026-07-06 09:00" } ] : [
      { name: "EC-CPLV-2026-00002", request_title: "Old", requester_name: "U", requested_by: "u@x",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 1, my_status: "Approved",
        requested_at: "2026-07-01 09:00", creation: "2026-07-01 09:00" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    if (m.endsWith("approve")) return Promise.resolve({ message: { detail: detail() } });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  const CL = w.CompensationLeave;
  ok(!!CL, "window.CompensationLeave exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  const body = () => w.document.getElementById("cplv-body").innerHTML;

  // create fields render (incl both duration fields), NO request_title
  ["overtime_start_date", "overtime_end_date", "overtime_duration_days", "cl_start_date", "cl_end_date", "cl_duration_days", "remarks"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-model="overtime_duration_days"]') && !!w.document.querySelector('[data-model="cl_duration_days"]'), "both duration fields render");
  ok(!w.document.querySelector('[data-model="request_title"]'), "NO request_title input");
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders");

  // process preview single-level
  { const pv = w.document.getElementById("cplv-process-preview");
    ok(!!pv && pv.querySelectorAll(".step").length === 3, "process preview has 3 steps");
    ok(/Direct Manager review/.test(pv.innerHTML) && !/SLA|Hạn/.test(pv.innerHTML), "preview shows Direct Manager review, no SLA"); }

  // title preview in summary (empty draft)
  ok(/Compensation Leave - /.test(w.document.getElementById("cplv-summary").innerHTML), "title preview shows in summary");

  // ---- validation ----
  CL.state.draft = {};
  { const e = CL.validateSubmit() || {};
    ok(e.overtime_start_date && e.overtime_end_date && e.overtime_duration_days && e.cl_start_date && e.cl_end_date && e.cl_duration_days && e.remarks,
      "validateSubmit requires all dates + both durations + remarks"); }
  ok(!(CL.validateSubmit() || {}).request_attachment, "attachment NOT required");

  // valid draft without attachment passes
  CL.state.draft = { overtime_start_date: "2026-08-01", overtime_end_date: "2026-08-02", overtime_duration_days: 2,
    cl_start_date: "2026-08-10", cl_end_date: "2026-08-11", cl_duration_days: 2, remarks: "ok" };
  ok(CL.validateSubmit() === null, "valid draft without attachment passes");

  // OT end < start blocked
  CL.state.draft = { overtime_start_date: "2026-08-05", overtime_end_date: "2026-08-01", overtime_duration_days: 1,
    cl_start_date: "2026-08-10", cl_end_date: "2026-08-11", cl_duration_days: 1, remarks: "ok" };
  ok(!!(CL.validateSubmit() || {}).overtime_end_date, "overtime end < start blocked");

  // CL end < start blocked
  CL.state.draft = { overtime_start_date: "2026-08-01", overtime_end_date: "2026-08-02", overtime_duration_days: 1,
    cl_start_date: "2026-08-15", cl_end_date: "2026-08-10", cl_duration_days: 1, remarks: "ok" };
  ok(!!(CL.validateSubmit() || {}).cl_end_date, "CL end < start blocked");

  // duration 0 blocked
  CL.state.draft = { overtime_start_date: "2026-08-01", overtime_end_date: "2026-08-02", overtime_duration_days: 0,
    cl_start_date: "2026-08-10", cl_end_date: "2026-08-11", cl_duration_days: 0, remarks: "ok" };
  { const e = CL.validateSubmit() || {}; ok(e.overtime_duration_days && e.cl_duration_days, "duration 0 blocked"); }

  // NO cross-validation: CL duration > OT duration AND CL dates before OT dates STILL passes
  CL.state.draft = { overtime_start_date: "2026-08-20", overtime_end_date: "2026-08-21", overtime_duration_days: 1,
    cl_start_date: "2026-08-01", cl_end_date: "2026-08-05", cl_duration_days: 5, remarks: "ok" };
  ok(CL.validateSubmit() === null, "no cross-validation: CL dur>OT & CL before OT still passes");

  // ---- My Requests list ----
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/compensation-leave?tab=my-requests"); w.CompensationLeave.route(); await flush(); await flush();
  { const ths = [...w.document.querySelectorAll("#cplv-list th")].map(t => t.textContent);
    ok(ths[0] === "Ngày request", "My Requests FIRST header is 'Ngày request'");
    ok(ths.indexOf("Người request") >= 0, "My Requests has 'Người request' header");
    ok(/\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/.test(w.document.getElementById("cplv-list").innerHTML), "My Requests shows formatted date (fmtDT)"); }

  // ---- approve modal comment optional ----
  w = boot(); await flush(); await flush();
  w.CompensationLeave.doApprove("EC-CPLV-2026-00001", detail()); await flush();
  { const ov = w.document.querySelector(".ec-cplv-overlay"); ok(!!ov, "approve modal opens");
    ok(!/\*/.test(ov.querySelector(".ec-cplv-modal-b label").innerHTML), "approve comment label not required (no *)");
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(!!calls.approve && (calls.approve.comment === "" || calls.approve.comment == null), "approve modal submits with empty comment (optional)"); }

  // ---- detail via get_detail shows title ----
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/compensation-leave?id=EC-CPLV-2026-00001"); w.CompensationLeave.route(); await flush(); await flush();
  ok(calls.get_detail && /Compensation Leave - 2026-08-10 to 2026-08-11/.test(body()) && !/Không tải được yêu cầu/.test(body()), "detail via get_detail shows request_title");
  { const rh = w.CompensationLeave.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Direct Manager Review/.test(rh) && /Hoàn tất/.test(rh), "runtime stepper single-level"); }

  // ---- guardrails ----
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.compensation_leave."/.test(JS), "uses Compensation Leave whitelisted API namespace");
  ok(/#ec-cplv-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced-width CSS present");

  // A1 (Batch-7): friendly backend message extracted from Frappe error shapes, not only e.message
  { var _mgr="Không xác định được Quản lý trực tiếp của bạn. Vui lòng liên hệ HR/Admin để cập nhật báo cáo cho user trước khi gửi yêu cầu.";
    var _sm={ responseJSON:{ _server_messages: JSON.stringify([ JSON.stringify({ message:_mgr, title:"Message" }) ]) } };
    ok(/Quản lý trực tiếp/.test(w.CompensationLeave.mapErr(_sm)), "A1: friendly _server_messages surfaced (not generic)");
    ok(w.CompensationLeave.mapErr(_sm) !== "Đã có lỗi. Vui lòng thử lại.", "A1: does not fall back to generic toast");
    ok(/Quản lý trực tiếp/.test(w.CompensationLeave.mapErr({ responseJSON:{ exception:"frappe.exceptions.ValidationError: "+_mgr } })), "A1: exception shape also extracted"); }

  console.log(fails === 0 ? "\nALL COMPENSATION LEAVE PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
