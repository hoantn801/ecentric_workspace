// Headless tests for the Leave page (Node + jsdom). Single-level (Direct Manager Review), no fulfillment.
// Auto-title: no request_title input; server generates title, page shows computed preview.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "leave.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-leave">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = { leave_types: ["Annual", "Sick", "Errand", "Maternity", "Paternity", "Marriage", "Bereavement"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-LEAVE-2026-00001", request_title: "Leave - Annual - 2026-08-01 to 2026-08-03",
      leave_type: "Annual", start_date: "2026-08-01", end_date: "2026-08-03", duration_days: 3, remarks: "Nghi phep nam",
      requester_name: "Nguyen Van A", requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "mgr@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/leave?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "Nguyen Van A", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-LEAVE-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-LEAVE-2026-00001", request_title: "Leave - Annual - 2026-08-01 to 2026-08-03", leave_type: "Annual",
        start_date: "2026-08-01", end_date: "2026-08-03", duration_days: 3, requester_name: "Nguyen Van A",
        requested_at: "2026-07-06 09:00", creation: "2026-07-06 09:00", approval_status: "Pending", current_level: 1,
        current_level_name: "Direct Manager Review", total_levels: 1, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-LEAVE-2026-00001", request_title: "Leave - Annual - 2026-08-01 to 2026-08-03", requester_name: "Nguyen Van A",
        requested_by: "u@x", leave_type: "Annual", start_date: "2026-08-01", end_date: "2026-08-03", duration_days: 3,
        requested_at: "2026-07-06 09:00", creation: "2026-07-06 09:00", approval_status: "Pending", current_level: 1,
        level_no: 1, total_levels: 1, my_status: "Pending" } ] : [
      { name: "EC-LEAVE-2026-00002", request_title: "Leave - Sick - 2026-06-01 to 2026-06-01", requester_name: "Nguyen Van A",
        requested_by: "u@x", leave_type: "Sick", start_date: "2026-06-01", end_date: "2026-06-01", duration_days: 1,
        requested_at: "2026-06-01 08:00", creation: "2026-06-01 08:00", approval_status: "Approved", current_level: 0,
        level_no: 1, total_levels: 1, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.LeaveRequest, "LeaveRequest exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  const cb = () => w.document.getElementById("leave-body").innerHTML;

  ["leave_type", "start_date", "end_date", "duration_days", "remarks"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders");
  ok(!w.document.querySelector('[data-model="request_title"]'), "NO request_title input");
  { const dd = w.document.querySelector('[data-model="duration_days"]');
    ok(dd.getAttribute("step") === "0.5" && dd.getAttribute("min") === "0.5", "duration input step/min 0.5"); }
  ok(/Maternity/.test(w.document.querySelector('[data-model="leave_type"]').innerHTML), "leave_type options from FO");

  ok(!!w.document.getElementById("leave-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("leave-process-preview");
    ok(pv.querySelectorAll(".step").length === 3, "preview has 3 steps (single level)");
    ok(/Direct Manager review/.test(pv.innerHTML), "preview step Direct Manager review"); }

  w.LeaveRequest.state.draft = {};
  { const e = w.LeaveRequest.validateSubmit() || {};
    ok(e.leave_type && e.start_date && e.end_date && e.duration_days, "validateSubmit requires key fields"); }
  ok(!(w.LeaveRequest.validateSubmit() || {}).request_attachment, "attachment optional (not required)");
  w.LeaveRequest.state.draft = { leave_type: "Annual", start_date: "2026-08-05", end_date: "2026-08-01", duration_days: 2 };
  ok(!!(w.LeaveRequest.validateSubmit() || {}).end_date, "end_date before start_date blocked");
  w.LeaveRequest.state.draft = { leave_type: "Annual", start_date: "2026-08-01", end_date: "2026-08-03", duration_days: 0 };
  ok(!!(w.LeaveRequest.validateSubmit() || {}).duration_days, "duration 0 blocked");
  w.LeaveRequest.state.draft = { leave_type: "Annual", start_date: "2026-08-01", end_date: "2026-08-03", duration_days: 3 };
  ok(w.LeaveRequest.validateSubmit() === null, "valid form passes with no attachment (attachment optional)");

  w.LeaveRequest.render();
  { const title = w.LeaveRequest.computedTitle({ leave_type: "Annual", start_date: "2026-08-01", end_date: "2026-08-03" });
    ok(title === "Leave - Annual - 2026-08-01 to 2026-08-03", "computedTitle format correct"); }
  { const sum = w.document.getElementById("leave-summary");
    ok(sum && /Leave - Annual - 2026-08-01 to 2026-08-03/.test(sum.innerHTML), "computed title preview shown in summary"); }

  w.document.getElementById("leave-save").click(); await flush(); await flush();
  ok(calls.save_draft && /leave_type/.test(calls.save_draft.payload) && /duration_days/.test(calls.save_draft.payload), "save_draft payload carries leave fields");

  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/leave?tab=my-requests"); w.LeaveRequest.route(); await flush(); await flush();
  { const html = cb();
    const firstTh = w.document.querySelector("#leave-list table.tbl thead th");
    ok(firstTh && /Ngày request/.test(firstTh.textContent), "My Requests FIRST header = Ngay request");
    ok(/Người request/.test(html), "My Requests has Nguoi request header");
    ok(/06\/07\/2026 09:00/.test(html), "My Requests shows formatted date row");
    ok(/EC-LEAVE-2026-00001/.test(html) && /Bước 2\/3 · Direct Manager Review/.test(html), "My Requests shows step label"); }

  w.history.pushState({}, "", "/approvals/leave?tab=my-approvals"); w.LeaveRequest.route(); await flush(); await flush();
  { const pend = w.document.getElementById("ap-pending").innerHTML;
    ok(/Ngày request/.test(pend) && /Người request/.test(pend), "Pending table uses list standard headers");
    const done = w.document.getElementById("ap-done").innerHTML;
    ok(/Bước 3\/3 · Hoàn tất/.test(done) && /Đã duyệt/.test(done), "processed list shows current status/step (Hoan tat)"); }

  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/leave?id=EC-LEAVE-2026-00001"); w.LeaveRequest.route(); await flush(); await flush();
  ok(!!calls.get_detail, "detail loads via api.leave.get_detail");
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper, no not-found");
  ok(/Leave - Annual - 2026-08-01 to 2026-08-03/.test(cb()), "detail shows request_title prominently");
  { const rh = w.LeaveRequest.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Direct Manager Review/.test(rh) && /Hoàn tất/.test(rh), "runtime stepper single-level"); }

  w.LeaveRequest.doApprove("EC-LEAVE-2026-00001", detail());
  { const ov = w.document.querySelector(".ec-leave-overlay");
    ok(!!ov, "approve modal opens");
    ok(ov && /không bắt buộc/i.test(ov.innerHTML) && !/<span class="req">/.test(ov.querySelector(".ec-leave-modal-b").innerHTML), "approve modal comment optional (no required marker)"); }

  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.leave."/.test(JS), "uses Leave whitelisted API");
  ok(/#ec-leave-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  ok(/#ec-leave-root .leave-formwrap\{[^}]*max-width:none/.test(HTML), "leave-formwrap max-width none");

  // A1 (Batch-7): friendly backend message extracted from Frappe error shapes, not only e.message
  { var _mgr="Không xác định được Quản lý trực tiếp của bạn. Vui lòng liên hệ HR/Admin để cập nhật báo cáo cho user trước khi gửi yêu cầu.";
    var _sm={ responseJSON:{ _server_messages: JSON.stringify([ JSON.stringify({ message:_mgr, title:"Message" }) ]) } };
    ok(/Quản lý trực tiếp/.test(w.LeaveRequest.mapErr(_sm)), "A1: friendly _server_messages surfaced (not generic)");
    ok(w.LeaveRequest.mapErr(_sm) !== "Đã có lỗi. Vui lòng thử lại.", "A1: does not fall back to generic toast");
    ok(/Quản lý trực tiếp/.test(w.LeaveRequest.mapErr({ responseJSON:{ exception:"frappe.exceptions.ValidationError: "+_mgr } })), "A1: exception shape also extracted"); }

  console.log(fails === 0 ? "\nALL LEAVE PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
