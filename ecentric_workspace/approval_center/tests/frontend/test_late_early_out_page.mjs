// Headless tests for the Late in - Early out page (Node + jsdom).
// Single approval level ("Direct Manager Review") -> Completed. No fulfillment. Auto-title, no request_title input.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "late_early_out.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-late-early-out">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = { check_times: ["10 AM", "11 AM", "12 PM", "1 PM", "2 PM", "3 PM", "4 PM", "5 PM", "Other"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-LTEO-2026-00001", request_title: "Late/Early - 2026-08-01 - 10 AM",
      applied_date: "2026-08-01", check_time: "10 AM", check_time_other: "", reason: "Kẹt xe",
      requested_by: "u@x", requester_name: "U", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "mgr@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/late-in-early-out?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-LTEO-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-LTEO-2026-00001", request_title: "Late/Early - 2026-08-01 - 10 AM", applied_date: "2026-08-01",
        check_time: "10 AM", check_time_other: "", approval_status: "Pending", current_level: 1,
        current_level_name: "Direct Manager Review", total_levels: 1,
        creation: "2026-07-06 09:00", requested_at: "2026-07-06 09:00", requester_name: "U",
        modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-LTEO-2026-00001", request_title: "Late/Early - 2026-08-01 - 10 AM", requested_by: "u@x",
        requester_name: "U", applied_date: "2026-08-01", check_time: "10 AM", check_time_other: "",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 1, my_status: "Pending",
        creation: "2026-07-06 09:00", requested_at: "2026-07-06 09:00" } ] : [
      { name: "EC-LTEO-2026-00002", request_title: "Old", requested_by: "u@x", requester_name: "U",
        applied_date: "2026-07-01", check_time: "Other", check_time_other: "9:30 AM",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 1, my_status: "Approved",
        creation: "2026-07-01 08:00", requested_at: "2026-07-01 08:00" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  const LEO = () => w.LateEarlyOut;
  const cb = () => w.document.getElementById("lteo-body").innerHTML;
  ok(!!w.LateEarlyOut, "LateEarlyOut exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");

  // create fields render
  ["applied_date", "check_time", "reason"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!w.document.querySelector('[data-model="request_title"]'), "NO request_title input (auto-title)");
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders");
  ok(!!w.document.getElementById("lteo-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("lteo-process-preview");
    ok(pv.querySelectorAll(".step").length === 3, "preview has 3 steps");
    ok(/Direct Manager review/.test(pv.innerHTML), "preview single-level step Direct Manager review"); }

  // conditional check_time_other: hidden by default, shown + required when Other
  ok(!w.document.querySelector('[data-model="check_time_other"]'), "check_time_other hidden when not Other");
  LEO().state.draft = { applied_date: "2026-08-01", check_time: "Other", reason: "x" };
  LEO().render(); await flush();
  ok(!!w.document.querySelector('[data-model="check_time_other"]'), "check_time_other appears when check_time=Other");
  { const e = LEO().validateSubmit() || {};
    ok(e.check_time_other, "check_time_other required when Other"); }
  LEO().state.draft.check_time_other = "9:30 AM";
  ok(LEO().validateSubmit() === null, "valid when Other + check_time_other filled");

  // required fields + attachment optional
  LEO().state.draft = {};
  { const e = LEO().validateSubmit() || {};
    ok(e.applied_date && e.check_time && e.reason, "validateSubmit requires applied_date/check_time/reason"); }
  LEO().state.draft = { applied_date: "2026-08-01", check_time: "10 AM", reason: "Kẹt xe" };
  ok(LEO().validateSubmit() === null, "valid draft without attachment passes (attachment optional)");
  ok(!(LEO().validateSubmit() || {}).request_attachment, "attachment not required");

  // title preview in summary
  LEO().render(); await flush();
  { const sm = w.document.getElementById("lteo-summary").innerHTML;
    ok(/Late\/Early - 2026-08-01 - 10 AM/.test(sm), "client title preview shown in summary"); }

  // save_draft carries fields
  w.document.getElementById("lteo-save").click(); await flush(); await flush();
  ok(calls.save_draft && /applied_date/.test(calls.save_draft.payload) && /check_time/.test(calls.save_draft.payload) && /reason/.test(calls.save_draft.payload), "save_draft payload carries fields");

  // My Requests: LIST STANDARD headers + formatted date
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/late-in-early-out?tab=my-requests"); w.LateEarlyOut.route(); await flush(); await flush();
  { const html = w.document.getElementById("lteo-body").innerHTML;
    const ths = Array.prototype.map.call(w.document.querySelectorAll("#lteo-body thead th"), t => t.textContent);
    ok(ths[0] === "Ngày request", "My Requests FIRST header is 'Ngày request'");
    ok(ths.indexOf("Người request") >= 0, "My Requests has 'Người request' header");
    ok(/06\/07\/2026 09:00/.test(html), "My Requests shows formatted date (fmtDT)");
    ok(/Bước 2\/3 · Direct Manager Review/.test(html), "My Requests shows single-level step label"); }

  // Need my approval processed list still shows current status/step
  w.history.pushState({}, "", "/approvals/late-in-early-out?tab=my-approvals"); w.LateEarlyOut.route(); await flush(); await flush();
  { const done = w.document.getElementById("ap-done").innerHTML;
    ok(/Bước 3\/3 · Hoàn tất/.test(done) && /Đã duyệt/.test(done), "processed list shows current status/step (Hoàn tất)");
    ok(/9:30 AM/.test(done), "Giờ cell shows check_time_other when Other"); }

  // Detail via get_detail shows title
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/late-in-early-out?id=EC-LTEO-2026-00001"); w.LateEarlyOut.route(); await flush(); await flush();
  ok(!!calls.get_detail, "detail loaded via api.late_early_out.get_detail");
  ok(/Late\/Early - 2026-08-01 - 10 AM/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail shows request_title prominently");
  { const rh = w.LateEarlyOut.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Direct Manager Review/.test(rh) && /Hoàn tất/.test(rh), "runtime stepper single-level"); }

  // approve modal comment optional
  w.LateEarlyOut.doApprove("EC-LTEO-2026-00001", detail()); await flush();
  { const ov = w.document.querySelector(".ec-lteo-overlay");
    ok(!!ov, "approve modal opens");
    ok(/không bắt buộc/.test(ov.innerHTML), "approve modal comment is optional"); }

  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.late_early_out."/.test(JS), "uses Late in - Early out whitelisted API");
  ok(/#ec-lteo-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  ok(/\.lteo-formwrap\{max-width:none\}|\.lteo-formwrap\{ max-width:none; \}/.test(HTML), "formwrap max-width:none");

  console.log(fails === 0 ? "\nALL LATE EARLY OUT PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
