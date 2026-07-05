// Headless tests for the Document Request page (Node + jsdom). Form #4 (Owner dept + 3-level + fulfillment).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "document_request.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-document-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));

const FO = { request_types: ["Create", "Modify", "Recall"],
  departments: [{ value: "ADMIN-DEPT", label: "Administration" }, { value: "FIN-DEPT", label: "Finance" }] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-DOCR-2026-00001", request_title: "Create - Onboarding SOP", request_type: "Create",
      document_name: "Onboarding SOP", owner_department: "ADMIN-DEPT", detail: "need it",
      expected_response_date: "2026-07-25", requested_by: "u@x", department: "D", fulfillment_status: "Not Started" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Department Owner Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "Operation Review", approval_mode: "Any One", level_status: "Pending" },
             { level_no: 3, level_name: "CEO Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "owner@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    fulfillment: { status: "Not Started" },
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/document-request?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true, fulfillment: (over && over.fulfillment) || false },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-DOCR-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-DOCR-2026-00001", request_title: "Create - Onboarding SOP", request_type: "Create", document_name: "Onboarding SOP",
        owner_department: "ADMIN-DEPT", fulfillment_status: "Assigned", approval_status: "Approved", current_level: 0,
        total_levels: 3, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-DOCR-2026-00001", request_title: "Create - Onboarding SOP", requested_by: "u@x", request_type: "Create",
        document_name: "Onboarding SOP", level_no: 1, level_name: "Department Owner Review", total_levels: 3, my_status: "Pending" } ] : []) } });
    if (m.endsWith("list_fulfillment_queue")) return Promise.resolve({ message: { rows: [
      { name: "EC-DOCR-2026-00001", request_title: "Create - Onboarding SOP", requested_by: "u@x", request_type: "Create",
        document_name: "Onboarding SOP", owner_department: "ADMIN-DEPT", fulfillment_status: "Assigned", fulfillment_owner: null } ] } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}

async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.DocumentRequest, "DocumentRequest exposed");
  ok(w.document.querySelectorAll(".tab").length === 4, "four tabs rendered (incl. fulfillment)");
  const cb = () => w.document.getElementById("docr-body").innerHTML;

  ["request_title", "request_type", "document_name", "owner_department", "detail"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders (optional)");
  ok(w.document.querySelector('select[data-model="owner_department"]') &&
     /Administration/.test(w.document.querySelector('select[data-model="owner_department"]').innerHTML) &&
     /Finance/.test(w.document.querySelector('select[data-model="owner_department"]').innerHTML),
     "Owner Department dropdown renders options from Department DocType");

  ok(!!w.document.getElementById("docr-process-preview"), "process preview card renders");
  { const html = cb(); ok(html.indexOf('id="docr-process-preview"') < html.indexOf('data-model="request_title"'), "preview renders before request_title"); }
  { const pv = w.document.getElementById("docr-process-preview");
    ok(pv.querySelectorAll(".step").length === 6, "preview has exactly 6 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Owner duyệt/.test(pv.innerHTML) && /Operation duyệt/.test(pv.innerHTML) && /CEO duyệt/.test(pv.innerHTML) && /Operation xử lý/.test(pv.innerHTML) && /Hoàn tất/.test(pv.innerHTML), "preview steps: Tạo/Owner/Operation/CEO/Operation xử lý/Hoàn tất");
    ok(!/SLA/i.test(pv.innerHTML), "preview shows no misleading SLA text"); }

  ok(/>Create</.test(cb()) && />Modify</.test(cb()) && />Recall</.test(cb()), "request_type options render (Create/Modify/Recall)");

  w.DocumentRequest.state.draft = {};
  ok(!!(w.DocumentRequest.validateSubmit() || {}).request_title, "validateSubmit: title required");
  ok(!!(w.DocumentRequest.validateSubmit() || {}).owner_department, "validateSubmit: owner required");
  w.DocumentRequest.state.draft = { request_title: "T", request_type: "Create", document_name: "SOP",
    owner_department: "ADMIN-DEPT", detail: "d" };
  ok(w.DocumentRequest.validateSubmit() === null, "valid form passes validateSubmit");
  ok(w.DocumentRequest.suggestTitle({ request_type: "Create", document_name: "SOP" }) === "Create - SOP", "title auto-suggest format");

  w.document.getElementById("docr-save").click(); await flush(); await flush();
  ok(calls.save_draft && /owner_department/.test(calls.save_draft.payload) && /ADMIN-DEPT/.test(calls.save_draft.payload), "save_draft payload carries owner_department");

  w = boot(); await flush(); await flush();
  w.DocumentRequest.state.draft = { request_title: "T", request_type: "Create", document_name: "SOP",
    owner_department: "ADMIN-DEPT", detail: "d" }; w.DocumentRequest.state.titleTouched = true;
  w.document.getElementById("docr-submit").click(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-DOCR-2026-00001", "submit_request called with draft name");

  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/document-request?tab=my-requests"); w.DocumentRequest.route(); await flush(); await flush();
  ok(/EC-DOCR-2026-00001/.test(cb()) && /Bước 5\/6 · Operation xử lý/.test(cb()), "My Requests list renders with 6-step Operation label");

  w.history.pushState({}, "", "/approvals/document-request?tab=my-approvals"); w.DocumentRequest.route(); await flush(); await flush();
  ok(/Cần tôi xử lý/.test(cb()) && !!w.document.querySelector('[data-quick="approve"]'), "Need My Approval renders with quick actions");

  w = boot({ fulfillment: true }); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/document-request?tab=fulfillment"); w.DocumentRequest.route(); await flush(); await flush();
  ok(/EC-DOCR-2026-00001/.test(cb()) && !!w.document.querySelector('[data-claim]'), "Operation Fulfillment queue renders with claim button");

  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/document-request?id=EC-DOCR-2026-00001"); w.DocumentRequest.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()), "detail renders the runtime stepper");
  { const rh = w.DocumentRequest.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Department Owner Review/.test(rh) && /Operation Review/.test(rh) && /CEO Review/.test(rh) && /Operation xử lý/.test(rh), "runtime stepper: Owner + Operation + CEO + Operation xử lý"); }

  w = boot({ detail: detail({ approval: { name: "AR-1", approval_status: "Information Required", current_level: 1, information_requested_from_level: 1 },
    approvers: [{ level_no: 1, approver: "owner@x", status: "Information Requested", comment: "cần thêm" }],
    capabilities: { can_edit: true } }) }); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/document-request?id=EC-DOCR-2026-00001"); w.DocumentRequest.route(); await flush(); await flush();
  w.DocumentRequest.startEditResubmit(w.DocumentRequest.state.detail); await flush();
  { const eb = cb(); ok(/Cần bổ sung thông tin/.test(eb) && /class="stepper"/.test(eb) && /class="step info"/.test(eb), "resubmit/edit form shows banner + runtime stepper with info level"); }

  w = boot(); await flush(); await flush();
  ok((w.DocumentRequest.completionErrors({}) || {}).fulfillment_summary, "complete requires fulfillment_summary");
  ok(w.DocumentRequest.completionErrors({ fulfillment_summary: "done" }) === null, "complete passes with summary");
  w.DocumentRequest.doComplete("EC-DOCR-2026-00001", detail()); await flush();
  ok(!!w.document.querySelector(".ec-docr-overlay #c-summary"), "fulfillment complete modal renders with summary field");

  ok(/#ec-docr-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced centered content width");
  ok(/#ec-docr-root .docr-formwrap\{[^}]*max-width:none/.test(HTML), "form wrapper aligns under header/tabs");
  ok(/@media \(max-width:1024px\)/.test(HTML), "responsive rule preserved");

  console.log(fails === 0 ? "\nALL DOCUMENT REQUEST PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
