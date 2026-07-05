// Headless tests for the Data Request page (Node + jsdom). Form #3 (with fulfillment).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "data_request.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-data-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));

const FO = {
  request_types: ["Data accuracy, visualization, retrieval", "Client onboarding", "Client offboarding",
    "Historical data crawling", "New BI report", "Data training", "Access", "Other"],
  urgencies: ["U0: as soon as possible", "U1: within next 24 hours", "U2: within next 3 days", "U3: non-urgent / nice to have"],
  importances: ["I0: large-scale impact, critical customer request, critical data loss or corruption",
    "I1: major impact to >2 customers, any major data loss or corruption",
    "I2: minor impact to >2 customers, possible workaround",
    "I3: known bug, little impact, single customer issue"],
};
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-DATA-2026-00001", request_title: "New BI report", request_type: "New BI report",
      expected_resolution_date: "2026-07-20", urgency: "U2: within next 3 days",
      importance: "I2: minor impact to >2 customers, possible workaround", detailed_description: "need a report",
      requested_by: "u@x", department: "D", fulfillment_status: "Not Started" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Data Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "linh@x", status: "Pending" }],
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
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-DATA-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-DATA-2026-00001", request_title: "New BI report", request_type: "New BI report", urgency: "U2: within next 3 days",
        expected_resolution_date: "2026-07-20", fulfillment_status: "Assigned", approval_status: "Approved", current_level: 0,
        total_levels: 1, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-DATA-2026-00001", request_title: "New BI report", requested_by: "u@x", request_type: "New BI report",
        expected_resolution_date: "2026-07-20", level_no: 1, level_name: "Data Review", total_levels: 1, my_status: "Pending" } ] : []) } });
    if (m.endsWith("list_fulfillment_queue")) return Promise.resolve({ message: { rows: [
      { name: "EC-DATA-2026-00001", request_title: "New BI report", requested_by: "u@x", request_type: "New BI report",
        expected_resolution_date: "2026-07-20", fulfillment_status: "Assigned", fulfillment_owner: null } ] } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}

async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.DataRequest, "DataRequest exposed");
  ok(w.document.querySelectorAll(".tab").length === 4, "four tabs rendered (incl. fulfillment)");

  const cb = () => w.document.getElementById("dreq-body").innerHTML;
  // all fields render
  ["request_title", "request_type", "expected_resolution_date", "urgency", "importance", "detailed_description"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders");
  });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders (optional)");

  // process preview before Tieu de, exactly 4 steps
  ok(!!w.document.getElementById("dreq-process-preview"), "process preview card renders");
  { const html = cb(); ok(html.indexOf('id="dreq-process-preview"') < html.indexOf('data-model="request_title"'), "preview renders before request_title"); }
  { const pv = w.document.getElementById("dreq-process-preview");
    ok(pv.querySelectorAll(".step").length === 4, "preview has exactly 4 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Data review/.test(pv.innerHTML) && /Data xử lý/.test(pv.innerHTML) && /Hoàn tất/.test(pv.innerHTML), "preview steps: Tạo/Data review/Data xử lý/Hoàn tất");
    ok(!/SLA/i.test(pv.innerHTML), "preview shows no misleading SLA text"); }

  // options render
  ok(/New BI report/.test(cb()) && /Historical data crawling/.test(cb()) && /Access/.test(cb()), "request_type options render");
  ok(/U0: as soon as possible/.test(cb()) && /U3: non-urgent/.test(cb()), "urgency options render");
  ok(/I0: large-scale impact/.test(cb()) && /I3: known bug/.test(cb()), "importance options render");

  // validateSubmit
  w.DataRequest.state.draft = {};
  ok(!!(w.DataRequest.validateSubmit() || {}).request_title, "validateSubmit: title required");
  w.DataRequest.state.draft = { request_title: "T", request_type: "Access", detailed_description: "d",
    expected_resolution_date: "2026-07-20", urgency: "U2: within next 3 days", importance: "I2: minor impact to >2 customers, possible workaround" };
  ok(w.DataRequest.validateSubmit() === null, "valid form passes validateSubmit");
  ok(w.DataRequest.suggestTitle({ request_type: "New BI report", expected_resolution_date: "2026-07-20" }) === "New BI report - 2026-07-20", "title auto-suggest format");

  // draft save payload
  w.document.getElementById("dreq-save").click(); await flush(); await flush();
  ok(calls.save_draft && /request_type/.test(calls.save_draft.payload) && /Access/.test(calls.save_draft.payload), "save_draft payload carries request_type");

  // submit payload
  w = boot(); await flush(); await flush();
  w.DataRequest.state.draft = { request_title: "T", request_type: "Access", detailed_description: "d",
    expected_resolution_date: "2026-07-20", urgency: "U2: within next 3 days", importance: "I2: minor impact to >2 customers, possible workaround" };
  w.DataRequest.state.titleTouched = true;
  w.document.getElementById("dreq-submit").click(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-DATA-2026-00001", "submit_request called with draft name");

  // My Requests
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?tab=my-requests"); w.DataRequest.route(); await flush(); await flush();
  ok(/EC-DATA-2026-00001/.test(cb()) && /Bước 3\/4 · Data xử lý/.test(cb()), "My Requests list renders with fulfillment step label");

  // Need My Approval
  w.history.pushState({}, "", "/approvals/data-request?tab=my-approvals"); w.DataRequest.route(); await flush(); await flush();
  ok(/Cần tôi xử lý/.test(cb()) && !!w.document.querySelector('[data-quick="approve"]'), "Need My Approval renders with quick actions");

  // Fulfillment queue (fulfiller)
  w = boot({ fulfillment: true }); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?tab=fulfillment"); w.DataRequest.route(); await flush(); await flush();
  ok(/EC-DATA-2026-00001/.test(cb()) && !!w.document.querySelector('[data-claim]'), "Data Fulfillment queue renders with claim button");

  // detail runtime stepper (fulfillment step present)
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?id=EC-DATA-2026-00001"); w.DataRequest.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()), "detail renders the runtime stepper");
  { const rh = w.DataRequest.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Data xử lý/.test(rh) && /Data Review/.test(rh), "runtime stepper: Đã gửi + Data Review + Data xử lý"); }

  // request info / resubmit banner + runtime stepper
  w = boot({ detail: detail({ approval: { name: "AR-1", approval_status: "Information Required", current_level: 1, information_requested_from_level: 1 },
    approvers: [{ level_no: 1, approver: "linh@x", status: "Information Requested", comment: "cần thêm chi tiết" }],
    capabilities: { can_edit: true } }) }); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?id=EC-DATA-2026-00001"); w.DataRequest.route(); await flush(); await flush();
  w.DataRequest.startEditResubmit(w.DataRequest.state.detail); await flush();
  { const eb = cb(); ok(/Cần bổ sung thông tin/.test(eb) && /class="stepper"/.test(eb) && /class="step info"/.test(eb), "resubmit/edit form shows banner + runtime stepper with info level"); }

  // fulfillment complete modal
  w = boot(); await flush(); await flush();
  ok((w.DataRequest.completionErrors({}) || {}).fulfillment_summary, "complete requires fulfillment_summary");
  ok(w.DataRequest.completionErrors({ fulfillment_summary: "done" }) === null, "complete passes with summary");
  w.DataRequest.doComplete("EC-DATA-2026-00001", detail()); await flush();
  ok(!!w.document.querySelector(".ec-dreq-overlay #c-summary"), "fulfillment complete modal renders with summary field");

  // balanced container
  ok(/#ec-dreq-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced centered content width");
  ok(/#ec-dreq-root .dreq-formwrap\{[^}]*max-width:none/.test(HTML), "form wrapper aligns under header/tabs");
  ok(/@media \(max-width:1024px\)/.test(HTML), "responsive rule preserved");

  console.log(fails === 0 ? "\nALL DATA REQUEST PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
