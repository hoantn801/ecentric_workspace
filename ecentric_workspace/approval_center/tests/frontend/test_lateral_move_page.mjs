// Headless tests for the Employee Lateral Move page (Node + jsdom). 4-level, no fulfillment, comments required on approve.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "lateral_move.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-lateral-move">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const NEW_DEPTS = ["E-commerce Operation", "Service", "Business Development", "Product", "Finance and Accounting", "Operations", "Data & System", "Human Resources"];
const FO = { new_departments: NEW_DEPTS };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-LATM-2026-00001", request_title: "Lateral move - Product", new_position: "Senior PM",
      new_department: "Product", new_line_manager: "boss@x.test", start_date: "2026-09-01",
      transfer_reason: "grow the product org", requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Current Direct Manager Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "New Line Manager Review", approval_mode: "Any One", level_status: "Pending" },
             { level_no: 3, level_name: "HR Review", approval_mode: "Any One", level_status: "Pending" },
             { level_no: 4, level_name: "CEO Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "mgr@x.test", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/lateral-move?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D",
        current_department: "D", current_line_manager: "oldmgr@x.test", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("get_form_options")) return Promise.resolve({ message: FO });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-LATM-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-LATM-2026-00001", request_title: "Lateral move - Product", new_position: "Senior PM", new_department: "Product",
        start_date: "2026-09-01", approval_status: "Pending", current_level: 1,
        current_level_name: "Current Direct Manager Review", total_levels: 4, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-LATM-2026-00001", request_title: "Lateral move - Product", requested_by: "u@x", new_department: "Product",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 4, my_status: "Pending" } ] : [
      { name: "EC-LATM-2026-00002", request_title: "Old", requested_by: "u@x", new_department: "Product",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 4, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.LateralMove, "LateralMove exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  const cb = () => w.document.getElementById("latm-body").innerHTML;
  ["request_title", "new_position", "new_department", "new_line_manager", "transfer_reason", "start_date"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.getElementById("latm-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("latm-process-preview");
    ok(pv.querySelectorAll(".step").length === 5, "preview has 5 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Current Direct Manager review/.test(pv.innerHTML) && /New Line Manager review/.test(pv.innerHTML) && /HR review/.test(pv.innerHTML) && /CEO review/.test(pv.innerHTML), "preview steps named correctly");
    ok(!/SLA|Hạn xử lý|deadline/i.test(pv.innerHTML), "preview has no SLA"); }
  // preview appears before the request_title field in the DOM
  ok(cb().indexOf('latm-process-preview') < cb().indexOf('data-model="request_title"'), "process preview before request_title");
  // new_department select renders all 8 options
  { const sel = w.document.querySelector('[data-model="new_department"]');
    const opts = Array.prototype.map.call(sel.querySelectorAll("option"), o => o.value).filter(v => v);
    ok(opts.length === 8 && NEW_DEPTS.every(d => opts.indexOf(d) >= 0), "new_department shows the 8 options"); }
  // read-only requester context card shows current values
  ok(/oldmgr@x.test/.test(cb()) || /Line manager hiện tại/.test(cb()), "requester context card shows current_line_manager");
  // validation
  w.LateralMove.state.draft = {};
  { const e = w.LateralMove.validateSubmit() || {};
    ok(e.request_title && e.new_position && e.new_department && e.new_line_manager && e.transfer_reason && e.start_date, "validateSubmit requires all key fields"); }
  w.LateralMove.state.draft = { request_title: "T", new_position: "PM", new_department: "Product", new_line_manager: "not-an-email", transfer_reason: "r", start_date: "2026-09-01" };
  ok((w.LateralMove.validateSubmit() || {}).new_line_manager, "bad new_line_manager email blocked");
  w.LateralMove.state.draft.new_line_manager = "boss@x.test";
  ok(w.LateralMove.validateSubmit() === null, "valid form passes");
  w.document.getElementById("latm-save").click(); await flush(); await flush();
  ok(calls.save_draft && /new_position/.test(calls.save_draft.payload) && /new_line_manager/.test(calls.save_draft.payload), "save_draft payload carries new_position + new_line_manager");
  // submit_request called with draft name
  w = boot(); await flush(); await flush();
  w.LateralMove.state.draft = { request_title: "T", new_position: "PM", new_department: "Product", new_line_manager: "boss@x.test", transfer_reason: "r", start_date: "2026-09-01" };
  w.document.getElementById("latm-submit").click(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-LATM-2026-00001", "submit_request called with draft name");
  // My Requests
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/lateral-move?tab=my-requests"); w.LateralMove.route(); await flush(); await flush();
  ok(/EC-LATM-2026-00001/.test(cb()) && /Bước 2\/5 · Current Direct Manager Review/.test(cb()), "My Requests renders with step label");
  w.history.pushState({}, "", "/approvals/lateral-move?tab=my-approvals"); w.LateralMove.route(); await flush(); await flush();
  { const done = w.document.getElementById("ap-done").innerHTML;
    ok(/Bước 5\/5 · Hoàn tất/.test(done) && /Đã duyệt/.test(done), "processed list shows current status/step (Hoàn tất)"); }
  // detail runtime stepper
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/lateral-move?id=EC-LATM-2026-00001"); w.LateralMove.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper via get_detail, no not-found");
  ok(!!calls.get_detail && calls.get_detail.name === "EC-LATM-2026-00001", "detail loads via api.lateral_move.get_detail");
  { const rh = w.LateralMove.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Current Direct Manager Review/.test(rh) && /New Line Manager Review/.test(rh) && /HR Review/.test(rh) && /CEO Review/.test(rh), "runtime stepper shows the 4 level names"); }
  // APPROVE modal requires a comment
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/lateral-move?id=EC-LATM-2026-00001"); w.LateralMove.route(); await flush(); await flush();
  w.LateralMove.doApprove("EC-LATM-2026-00001", detail());
  { const ov = w.document.querySelector(".ec-latm-overlay");
    ok(!!ov, "approve modal opens");
    ok(/<span class="req">\*<\/span>/.test(ov.querySelector(".ec-latm-modal-b").innerHTML), "approve comment label marked required");
    delete calls.approve;
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(!calls.approve, "approve not called when comment empty");
    ov.querySelector("#m-cmt").value = "looks good";
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(calls.approve && calls.approve.name === "EC-LATM-2026-00001" && calls.approve.comment === "looks good", "approve called with {name, comment} when comment present"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.lateral_move."/.test(JS), "uses Lateral Move whitelisted API");
  ok(/#ec-latm-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  ok(/#ec-latm-root .latm-formwrap\{[^}]*max-width:none/.test(HTML), "formwrap max-width none");
  console.log(fails === 0 ? "\nALL LATERAL MOVE PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
