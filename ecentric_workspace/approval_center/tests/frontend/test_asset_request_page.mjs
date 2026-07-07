// Headless tests for the Asset Request page (Node + jsdom). Form #3 (with fulfillment).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "asset_request.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-asset-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));

const FO = {
  request_types: ["Request new asset", "Return old asset"],
  asset_types: ["Laptop", "Desktop computer", "Monitor", "Mobile device", "Printer", "RAM", "Other"],
  purposes: ["New employee", "Replacement of damaged or obsolete asset", "Additional asset for current use", "Offboarding", "Laptop Allowance", "Other"],
};
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-ASSR-2026-00001", request_title: "Request new asset - Laptop", request_type: "Request new asset",
      asset_type: "Laptop", purpose_of_request: "New employee", quantity: 1, specifications: "16GB", justification: "need it",
      requested_needed_date: "2026-07-20", operation_expected_completion_date: "", operation_note: "",
      requested_by: "u@x", department: "D", direct_manager: "m@x", fulfillment_status: "Not Started" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "Operation Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "m@x", status: "Pending" }],
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
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C", manager_user: "m@x", manager_resolvable: true },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-ASSR-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-ASSR-2026-00001", request_title: "New Laptop", request_type: "Request new asset", asset_type: "Laptop",
        quantity: 1, requested_needed_date: "2026-07-20", operation_expected_completion_date: "", fulfillment_status: "Assigned",
        approval_status: "Approved", current_level: 0, total_levels: 2, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-ASSR-2026-00001", request_title: "New Laptop", requested_by: "u@x", request_type: "Request new asset",
        asset_type: "Laptop", quantity: 1, level_no: 1, level_name: "Direct Manager Review", total_levels: 2, my_status: "Pending" } ] : []) } });
    if (m.endsWith("list_fulfillment_queue")) return Promise.resolve({ message: { rows: [
      { name: "EC-ASSR-2026-00001", request_title: "New Laptop", requested_by: "u@x", request_type: "Request new asset",
        asset_type: "Laptop", quantity: 1, requested_needed_date: "2026-07-20", fulfillment_status: "Assigned", fulfillment_owner: null } ] } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}

async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.AssetRequest, "AssetRequest exposed");
  ok(w.document.querySelectorAll(".tab").length === 4, "four tabs rendered (incl. fulfillment)");

  const cb = () => w.document.getElementById("assr-body").innerHTML;
  // all fields render
  ["request_title", "request_type", "asset_type", "purpose_of_request", "quantity", "specifications", "justification"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders");
  });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders (optional)");

  // process preview before Tieu de, exactly 4 steps
  ok(!!w.document.getElementById("assr-process-preview"), "process preview card renders");
  { const html = cb(); ok(html.indexOf('id="assr-process-preview"') < html.indexOf('data-model="request_title"'), "preview renders before request_title"); }
  { const pv = w.document.getElementById("assr-process-preview");
    ok(pv.querySelectorAll(".step").length === 5, "preview has exactly 5 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Direct Manager duyệt/.test(pv.innerHTML) && /Operation duyệt/.test(pv.innerHTML) && /Operation xử lý/.test(pv.innerHTML) && /Hoàn tất/.test(pv.innerHTML), "preview steps: Tạo/Direct Manager/Operation/Operation xử lý/Hoàn tất");
    ok(!/SLA/i.test(pv.innerHTML), "preview shows no misleading SLA text"); }

  // options render
  ok(/Request new asset/.test(cb()) && /Return old asset/.test(cb()), "request_type options render");
  ok(/>Laptop</.test(cb()) && />RAM</.test(cb()) && /New employee/.test(cb()), "asset_type + purpose options render");


  // validateSubmit
  w.AssetRequest.state.draft = {};
  ok(!!(w.AssetRequest.validateSubmit() || {}).request_title, "validateSubmit: title required");
  w.AssetRequest.state.draft = { request_title: "T", request_type: "Request new asset", asset_type: "Laptop",
    purpose_of_request: "New employee", quantity: 2, specifications: "16GB", justification: "need it" };
  ok(w.AssetRequest.validateSubmit() === null, "valid form passes validateSubmit");
  w.AssetRequest.state.draft.quantity = 0;
  ok((w.AssetRequest.validateSubmit() || {}).quantity, "validateSubmit: quantity must be > 0");
  ok(w.AssetRequest.suggestTitle({ request_type: "Request new asset", asset_type: "Laptop" }) === "Request new asset - Laptop", "title auto-suggest format");

  // draft save payload
  w.document.getElementById("assr-save").click(); await flush(); await flush();
  ok(calls.save_draft && /asset_type/.test(calls.save_draft.payload) && /specifications/.test(calls.save_draft.payload), "save_draft payload carries asset_type + specifications");

  // submit payload
  w = boot(); await flush(); await flush();
  w.AssetRequest.state.draft = { request_title: "T", request_type: "Request new asset", asset_type: "Laptop",
    purpose_of_request: "New employee", quantity: 2, specifications: "16GB", justification: "need it" };
  w.AssetRequest.state.titleTouched = true;
  w.document.getElementById("assr-submit").click(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-ASSR-2026-00001", "submit_request called with draft name");

  // My Requests
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?tab=my-requests"); w.AssetRequest.route(); await flush(); await flush();
  ok(/EC-ASSR-2026-00001/.test(cb()) && /Bước 4\/5 · Operation xử lý/.test(cb()), "My Requests list renders with fulfillment step label");

  // Need My Approval
  w.history.pushState({}, "", "/approvals/data-request?tab=my-approvals"); w.AssetRequest.route(); await flush(); await flush();
  ok(/Cần tôi xử lý/.test(cb()) && !!w.document.querySelector('[data-quick="approve"]'), "Need My Approval renders with quick actions");

  // Fulfillment queue (fulfiller)
  w = boot({ fulfillment: true }); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?tab=fulfillment"); w.AssetRequest.route(); await flush(); await flush();
  ok(/EC-ASSR-2026-00001/.test(cb()) && !!w.document.querySelector('[data-claim]'), "Data Fulfillment queue renders with claim button");

  // detail runtime stepper (fulfillment step present)
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?id=EC-ASSR-2026-00001"); w.AssetRequest.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()), "detail renders the runtime stepper");
  { const rh = w.AssetRequest.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Direct Manager Review/.test(rh) && /Operation Review/.test(rh) && /Operation xử lý/.test(rh), "runtime stepper: Đã gửi + Direct Manager + Operation + Operation xử lý"); }

  // request info / resubmit banner + runtime stepper
  w = boot({ detail: detail({ approval: { name: "AR-1", approval_status: "Information Required", current_level: 1, information_requested_from_level: 1 },
    approvers: [{ level_no: 1, approver: "linh@x", status: "Information Requested", comment: "cần thêm chi tiết" }],
    capabilities: { can_edit: true } }) }); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/data-request?id=EC-ASSR-2026-00001"); w.AssetRequest.route(); await flush(); await flush();
  w.AssetRequest.startEditResubmit(w.AssetRequest.state.detail); await flush();
  { const eb = cb(); ok(/Cần bổ sung thông tin/.test(eb) && /class="stepper"/.test(eb) && /class="step info"/.test(eb), "resubmit/edit form shows banner + runtime stepper with info level"); }

  // fulfillment complete modal
  w = boot(); await flush(); await flush();
  ok((w.AssetRequest.completionErrors({}) || {}).fulfillment_summary, "complete requires fulfillment_summary");
  ok(w.AssetRequest.completionErrors({ fulfillment_summary: "done" }) === null, "complete passes with summary");
  w.AssetRequest.doComplete("EC-ASSR-2026-00001", detail()); await flush();
  ok(!!w.document.querySelector(".ec-assr-overlay #c-summary"), "fulfillment complete modal renders with summary field");

  // balanced container
  ok(/#ec-assr-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced centered content width");
  ok(/#ec-assr-root .assr-formwrap\{[^}]*max-width:none/.test(HTML), "form wrapper aligns under header/tabs");
  ok(/@media \(max-width:1024px\)/.test(HTML), "responsive rule preserved");

  // Cleanup B: operation date in Operation Review (L2) approve modal; complete modal without it
  w = boot(); await flush(); await flush();
  w.AssetRequest.doApprove("EC-ASSR-2026-00001", detail({ approval: { name: "AR-1", approval_status: "Pending", current_level: 2 } })); await flush();
  ok(!!w.document.querySelector(".ec-assr-overlay #m-opdate"), "Operation Review approve modal includes expected completion date");
  { const ov = w.document.querySelector(".ec-assr-overlay [data-x]"); if (ov) ov.click(); }
  ok(!/data-act="setopdate"/.test(HTML), "separate set-operation-date action removed from Asset Request");
  w.AssetRequest.doComplete("EC-ASSR-2026-00001", detail()); await flush();
  ok(!w.document.querySelector(".ec-assr-overlay #c-opdate"), "Asset complete modal has no operation expected date");
  { const ov = w.document.querySelector(".ec-assr-overlay [data-x]"); if (ov) ov.click(); }

  console.log(fails === 0 ? "\nALL ASSET REQUEST PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
