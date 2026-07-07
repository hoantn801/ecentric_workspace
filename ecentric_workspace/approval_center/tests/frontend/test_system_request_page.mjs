// Headless tests for the System Request page (Node + jsdom). Form #3 (with fulfillment).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "system_request.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-system-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));

const FO = {
  request_types: ["License, account", "Access, permission", "Initiative, solution", "Lark Approvals", "Other"],
  priorities: ["Low", "Normal", "High", "Urgent"],
};
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-SYSR-2026-00001", request_title: "Access, permission - CRM", request_type: "Access, permission",
      priority: "High", requester_expected_resolution_date: "2026-07-20", operation_expected_completion_date: "",
      operation_note: "", description: "need access", requested_by: "u@x", department: "D", fulfillment_status: "Not Started" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Operation Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "hoan@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    fulfillment: { status: "Not Started" },
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}

function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/data-request?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true, fulfillment: (over && over.fulfillment) || false },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-SYSR-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-SYSR-2026-00001", request_title: "Access CRM", request_type: "Access, permission", priority: "High",
        requester_expected_resolution_date: "2026-07-20", operation_expected_completion_date: "", fulfillment_status: "Assigned",
        approval_status: "Approved", current_level: 0, total_levels: 1, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-SYSR-2026-00001", request_title: "Access CRM", requested_by: "u@x", request_type: "Access, permission",
        priority: "High", level_no: 1, level_name: "Operation Review", current_level: 1, current_level_name: "Operation Review",
        approval_status: "Pending", fulfillment_status: "Not Started", total_levels: 1, my_status: "Pending" } ] : [
      { name: "EC-SYSR-2026-00002", request_title: "Old CRM", requested_by: "u@x", request_type: "Access, permission",
        priority: "High", level_no: 1, acted_level_name: "Operation Review", current_level: 0, current_level_name: null,
        approval_status: "Approved", fulfillment_status: "Completed", total_levels: 1, my_status: "Approved" } ]) } });
    if (m.endsWith("list_fulfillment_queue")) return Promise.resolve({ message: { rows: [
      { name: "EC-SYSR-2026-00001", request_title: "Access CRM", requested_by: "u@x", request_type: "Access, permission",
        priority: "High", requester_expected_resolution_date: "2026-07-20", fulfillment_status: "Assigned", fulfillment_owner: null } ] } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}

async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.SystemRequest, "SystemRequest exposed");
  ok(w.document.querySelectorAll(".tab").length === 4, "four tabs rendered (incl. fulfillment)");

  const cb = () => w.document.getElementById("sysr-body").innerHTML;
  // all fields render
  ["request_title", "request_type", "priority", "requester_expected_resolution_date", "description"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders");
  });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders (optional)");

  // process preview before Tieu de, exactly 4 steps
  ok(!!w.document.getElementById("sysr-process-preview"), "process preview card renders");
  { const html = cb(); ok(html.indexOf('id="sysr-process-preview"') < html.indexOf('data-model="request_title"'), "preview renders before request_title"); }
  { const pv = w.document.getElementById("sysr-process-preview");
    ok(pv.querySelectorAll(".step").length === 4, "preview has exactly 4 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Operation review/.test(pv.innerHTML) && /Operation xử lý/.test(pv.innerHTML) && /Hoàn tất/.test(pv.innerHTML), "preview steps: Tạo/Operation review/Operation xử lý/Hoàn tất");
    ok(!/SLA/i.test(pv.innerHTML), "preview shows no misleading SLA text"); }

  // options render
  ok(/License, account/.test(cb()) && /Lark Approvals/.test(cb()) && />Other</.test(cb()), "request_type options render");
  ok(/>Low</.test(cb()) && />Urgent</.test(cb()), "priority options render");


  // validateSubmit
  w.SystemRequest.state.draft = {};
  ok(!!(w.SystemRequest.validateSubmit() || {}).request_title, "validateSubmit: title required");
  w.SystemRequest.state.draft = { request_title: "T", request_type: "Access, permission", description: "d",
    priority: "High", requester_expected_resolution_date: "2026-07-20" };
  ok(w.SystemRequest.validateSubmit() === null, "valid form passes validateSubmit");
  ok(w.SystemRequest.suggestTitle({ request_type: "Access, permission", requester_expected_resolution_date: "2026-07-20" }) === "Access, permission - 2026-07-20", "title auto-suggest format");

  // draft save payload
  w.document.getElementById("sysr-save").click(); await flush(); await flush();
  ok(calls.save_draft && /request_type/.test(calls.save_draft.payload) && /priority/.test(calls.save_draft.payload), "save_draft payload carries request_type + priority");

  // submit payload
  w = boot(); await flush(); await flush();
  w.SystemRequest.state.draft = { request_title: "T", request_type: "Access, permission", description: "d",
    priority: "High", requester_expected_resolution_date: "2026-07-20" };
  w.SystemRequest.state.titleTouched = true;
  w.document.getElementById("sysr-submit").click(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-SYSR-2026-00001", "submit_request called with draft name");

  // My Requests
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?tab=my-requests"); w.SystemRequest.route(); await flush(); await flush();
  ok(/EC-SYSR-2026-00001/.test(cb()) && /Bước 3\/4 · Operation xử lý/.test(cb()), "My Requests list renders with fulfillment step label");

  // Need My Approval
  w.history.pushState({}, "", "/approvals/data-request?tab=my-approvals"); w.SystemRequest.route(); await flush(); await flush();
  ok(/Cần tôi xử lý/.test(cb()) && !!w.document.querySelector('[data-quick="approve"]'), "Need My Approval renders with quick actions");

  // Fulfillment queue (fulfiller)
  w = boot({ fulfillment: true }); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?tab=fulfillment"); w.SystemRequest.route(); await flush(); await flush();
  ok(/EC-SYSR-2026-00001/.test(cb()) && !!w.document.querySelector('[data-claim]'), "Data Fulfillment queue renders with claim button");

  // detail runtime stepper (fulfillment step present)
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?id=EC-SYSR-2026-00001"); w.SystemRequest.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()), "detail renders the runtime stepper");
  { const rh = w.SystemRequest.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Operation xử lý/.test(rh) && /Operation Review/.test(rh), "runtime stepper: Đã gửi + Operation Review + Operation xử lý"); }

  // request info / resubmit banner + runtime stepper
  w = boot({ detail: detail({ approval: { name: "AR-1", approval_status: "Information Required", current_level: 1, information_requested_from_level: 1 },
    approvers: [{ level_no: 1, approver: "linh@x", status: "Information Requested", comment: "cần thêm chi tiết" }],
    capabilities: { can_edit: true } }) }); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?id=EC-SYSR-2026-00001"); w.SystemRequest.route(); await flush(); await flush();
  w.SystemRequest.startEditResubmit(w.SystemRequest.state.detail); await flush();
  { const eb = cb(); ok(/Cần bổ sung thông tin/.test(eb) && /class="stepper"/.test(eb) && /class="step info"/.test(eb), "resubmit/edit form shows banner + runtime stepper with info level"); }

  // fulfillment complete modal
  w = boot(); await flush(); await flush();
  ok((w.SystemRequest.completionErrors({}) || {}).fulfillment_summary, "complete requires fulfillment_summary");
  ok(w.SystemRequest.completionErrors({ fulfillment_summary: "done" }) === null, "complete passes with summary");
  w.SystemRequest.doComplete("EC-SYSR-2026-00001", detail()); await flush();
  ok(!!w.document.querySelector(".ec-sysr-overlay #c-summary"), "fulfillment complete modal renders with summary field");

  // balanced container
  // ===== UAT round 3: no Desk-style shim; detail loads via the whitelisted API only =====
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style frappe.db.get_doc / frappe.client shim in the System Request page script");
  ok(/"ecentric_workspace.approval_center.api.system_request."/.test(JS), "actions/detail call the System Request whitelisted API namespace");
  { // detail load uses get_detail (the API), never a generic client get
    let usedApi = false, usedClient = false; const w4 = boot(); w4.frappe.call = ((orig) => (o) => {
      if (o.method === "ecentric_workspace.approval_center.api.system_request.get_detail") usedApi = true;
      if (/frappe\.client|frappe\.db/.test(o.method)) usedClient = true; return orig(o); })(w4.frappe.call);
    await flush(); await flush();
    w4.history.pushState({}, "", "/approvals/system-request?id=EC-SYSR-2026-00001"); w4.SystemRequest.route(); await flush(); await flush();
    ok(usedApi && !usedClient, "detail loads via api.system_request.get_detail, not a generic client get"); }

  // ===== UAT round 2: not-found popup / null addEventListener / POST-/ =====
  // Issue C: every button has type="button" so none can trigger a native form submit (POST / -> 404 popup)
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every <button> has an explicit type attribute (no native submit)");
  ok(!/<button [^>]*type="submit"/.test(HTML), "no submit-type buttons in System Request markup");

  // Issue A: loading a valid detail renders it and never shows the not-found empty state, no duplicate fetch
  { let n = 0; const w2 = boot(); await flush(); await flush();
    w2.frappe.call = ((orig) => (o) => { if (o.method.endsWith("get_detail")) n++; return orig(o); })(w2.frappe.call);
    w2.history.pushState({}, "", "/approvals/system-request?id=EC-SYSR-2026-00001"); w2.SystemRequest.route(); await flush(); await flush();
    const body = w2.document.getElementById("sysr-body").innerHTML;
    ok(/class="stepper"/.test(body), "valid detail renders on load");
    ok(!/Không tải được yêu cầu/.test(body), "no inline/blocking not-found on a successful detail load");
    ok(n === 1, "detail load fires exactly one get_detail (no racing duplicate loads)"); }

  // Issue B: initializing in detail-mode DOM (create-form-only elements absent) must not throw
  ok((() => { try { const w3 = boot(); return !!w3.SystemRequest; } catch (e) { return false; } })(), "script boots without throwing (null-safe bindings)");

  // ===== UAT polish =====
  // Issue 2: Complete modal must NOT contain the Operation expected completion date field
  w = boot(); await flush(); await flush();
  w.SystemRequest.doComplete("EC-SYSR-2026-00001", detail()); await flush();
  ok(!!w.document.querySelector(".ec-sysr-overlay #c-summary"), "complete modal has summary field");
  ok(!!w.document.querySelector(".ec-sysr-overlay #c-opnote"), "complete modal keeps Operation note");
  ok(!w.document.querySelector(".ec-sysr-overlay #c-opdate"), "complete modal no longer has expected completion date");
  { const ov = w.document.querySelector(".ec-sysr-overlay [data-x]"); if (ov) ov.click(); }

  // Issue 2: detail still shows operation_expected_completion_date if already set
  w = boot({ detail: detail({ business: Object.assign({}, detail().business, { operation_expected_completion_date: "2026-09-01" }) }) });
  await flush(); await flush();
  w.history.pushState({}, "", "/approvals/system-request?id=EC-SYSR-2026-00001"); w.SystemRequest.route(); await flush(); await flush();
  ok(/2026-09-01/.test(w.document.getElementById("sysr-body").innerHTML), "detail shows existing Operation expected completion date");

  // Issue 3: processed (history) row shows CURRENT status/step (Hoàn tất), not stale Operation Review
  ok(w.SystemRequest.stepLabel({ approval_status: "Approved", fulfillment_status: "Completed", total_levels: 1 }) === "Bước 4/4 · Hoàn tất", "completed row step label = Bước 4/4 · Hoàn tất");
  ok(/Hoàn tất/.test(w.SystemRequest.badge({ approval_status: "Approved", fulfillment_status: "Completed" })), "completed row badge shows Hoàn tất");
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/system-request?tab=my-approvals"); w.SystemRequest.route(); await flush(); await flush();
  { const done = w.document.getElementById("ap-done").innerHTML;
    ok(/Bước 4\/4 · Hoàn tất/.test(done) && /Hoàn tất/.test(done), "Tôi đã xử lý shows current Completed status/step");
    ok(!/Bước 2\/4 · Operation Review/.test(done), "no stale Bước 2/4 · Operation Review in processed list"); }

  // Issue 1: successful action redraws detail from returned payload (no extra fetch, no not-found)
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/system-request?id=EC-SYSR-2026-00001"); w.SystemRequest.route(); await flush(); await flush();
  let fetched = 0; const origCall = w.frappe.call;
  w.frappe.call = (o) => { if (o.method.endsWith("get_detail")) fetched++; return origCall(o); };
  w.SystemRequest.applyDetail({ detail: detail({ approval: { name: "AR-1", approval_status: "Approved", current_level: 0 }, fulfillment: { status: "Assigned" } }) });
  await flush();
  ok(fetched === 0, "applyDetail redraws from returned detail without an extra get_detail fetch");
  ok(/class="stepper"/.test(w.document.getElementById("sysr-body").innerHTML), "detail stays rendered after action (no not-found empty state)");
  ok(!/Không tải được yêu cầu/.test(w.document.getElementById("sysr-body").innerHTML), "no 'not found' empty state after successful action");

  // Issue 4: compact table action buttons
  ok(/#ec-sysr-root .tbl td .btn\{[^}]*padding:5px 10px/.test(HTML), "table action buttons use a compact padding");
  ok(/#ec-sysr-root .tbl td\{[^}]*vertical-align:middle/.test(HTML), "table cells vertically center the action buttons");

  ok(/#ec-sysr-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced centered content width");
  ok(/#ec-sysr-root .sysr-formwrap\{[^}]*max-width:none/.test(HTML), "form wrapper aligns under header/tabs");
  ok(/@media \(max-width:1024px\)/.test(HTML), "responsive rule preserved");

  // Cleanup B: operation date now lives in the Operation Review approval modal (System Request L1 = Operation Review)
  w = boot(); await flush(); await flush();
  w.SystemRequest.doApprove("EC-SYSR-2026-00001", detail()); await flush();
  ok(!!w.document.querySelector(".ec-sysr-overlay #m-opdate"), "Operation Review approve modal includes expected completion date");
  { const ov = w.document.querySelector(".ec-sysr-overlay [data-x]"); if (ov) ov.click(); }
  ok(!/data-act="setopdate"/.test(HTML), "separate set-operation-date action removed from System Request");

  console.log(fails === 0 ? "\nALL SYSTEM REQUEST PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
