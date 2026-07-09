// Headless tests for the Livestream Supplies page (Node + jsdom). Single-level (Sang Bui Review), approve comment REQUIRED.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "livestream_supplies.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-livestream-supplies">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = { request_types: ["Request supplies", "Return supplies"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-LVSP-2026-00001", request_title: "Livestream Supplies - Request supplies - Ring light",
      request_type: "Request supplies", supplies: "Ring light", quantity: 2, justification: "Cho buổi live",
      start_date: "2026-08-01", end_date: "2026-08-05", requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Sang Bui Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "sang.bui@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  Object.keys(calls).forEach(k => delete calls[k]);
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/livestream-supplies?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: {} } });
    if (m.endsWith("get_form_options")) return Promise.resolve({ message: FO });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-LVSP-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-LVSP-2026-00001", request_title: "Livestream Supplies - Request supplies - Ring light",
        request_type: "Request supplies", supplies: "Ring light", quantity: 2,
        approval_status: "Pending", current_level: 1, current_level_name: "Sang Bui Review", total_levels: 1,
        requester_name: "U", requested_by: "u@x", creation: "2026-07-06 09:00", requested_at: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-LVSP-2026-00001", request_title: "Livestream Supplies - Request supplies - Ring light",
        request_type: "Request supplies", supplies: "Ring light", quantity: 2, requester_name: "U", requested_by: "u@x",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 1, creation: "2026-07-06 09:00" } ] : [
      { name: "EC-LVSP-2026-00002", request_title: "Old", request_type: "Return supplies", supplies: "Tripod", quantity: 1,
        requester_name: "U", requested_by: "u@x", approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 1 } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    if (m.endsWith("approve")) return Promise.resolve({ message: { detail: detail({ approval: { name: "AR-1", approval_status: "Approved", current_level: 0 } }) } });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.LivestreamSupplies, "LivestreamSupplies exposed");
  // shell present
  ok(!!w.document.querySelector(".ec-sidebar"), "eCentric sidebar present");
  ok(/Approval Center<\/strong>|Approval Center \//.test(w.document.getElementById("ec-lvsp-root").innerHTML) || /Approval Center/.test(w.document.querySelector(".topbar").textContent), "Approval Center header/breadcrumb present");
  ok(!/Powered by ERPNext/.test(HTML), "no 'Powered by ERPNext' in markup");
  ok(/\.web-footer[^}]*display:none/.test(HTML), "web-footer hidden rule present");
  // tabs
  { const tabs = Array.prototype.map.call(w.document.querySelectorAll(".tab"), t => t.textContent);
    ok(tabs.length === 3, "three tabs rendered");
    ok(/Tạo mới/.test(tabs.join("|")) && /Yêu cầu của tôi/.test(tabs.join("|")) && /Cần tôi duyệt/.test(tabs.join("|")), "tab labels correct"); }
  const cb = () => w.document.getElementById("lvsp-body").innerHTML;
  ok(!!w.document.getElementById("lvsp-summary"), "summary exists");
  // create fields render
  ["request_type", "supplies", "quantity", "justification", "start_date", "end_date"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-model="supplies"]') && !!w.document.querySelector('[data-model="quantity"]'), "supplies + quantity fields present");
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders");
  ok(!w.document.querySelector('[data-model="request_title"]'), "NO request_title input");
  // request_type options populated from get_form_options
  ok(/Request supplies/.test(cb()) && /Return supplies/.test(cb()), "request_type options from get_form_options");
  // process preview 3 steps single-level
  { const pv = w.document.getElementById("lvsp-process-preview");
    ok(!!pv && pv.querySelectorAll(".step").length === 3, "preview has 3 steps");
    ok(/Sang Bui review/i.test(pv.innerHTML), "preview step Sang Bui review"); }

  // validation
  w.LivestreamSupplies.state.draft = {};
  { const e = w.LivestreamSupplies.validateSubmit() || {};
    ok(e.request_type && e.supplies && e.quantity && e.justification && e.start_date && e.end_date, "validateSubmit requires the full set"); }
  ok(!(w.LivestreamSupplies.validateSubmit() || {}).request_attachment, "attachment optional (not required)");
  w.LivestreamSupplies.state.draft = { request_type: "Request supplies", supplies: "Ring light", quantity: 0, justification: "x", start_date: "2026-08-01", end_date: "2026-08-05" };
  ok(!!(w.LivestreamSupplies.validateSubmit() || {}).quantity, "quantity 0 blocked");
  w.LivestreamSupplies.state.draft = { request_type: "Request supplies", supplies: "Ring light", quantity: 2, justification: "x", start_date: "2026-08-10", end_date: "2026-08-05" };
  ok(!!(w.LivestreamSupplies.validateSubmit() || {}).end_date, "end_date before start_date blocked");
  w.LivestreamSupplies.state.draft = { request_type: "Request supplies", supplies: "Ring light", quantity: 2, justification: "Cho buổi live", start_date: "2026-08-01", end_date: "2026-08-05" };
  ok(w.LivestreamSupplies.validateSubmit() === null, "valid full draft passes (no attachment)");
  w.document.getElementById("lvsp-save").click(); await flush(); await flush();
  ok(calls.save_draft && /supplies/.test(calls.save_draft.payload) && /quantity/.test(calls.save_draft.payload) && /request_title/.test(calls.save_draft.payload), "save_draft payload carries fields + auto request_title");

  // title preview in summary
  w = boot(); await flush(); await flush();
  w.LivestreamSupplies.state.draft = { request_type: "Request supplies", supplies: "Ring light" };
  w.LivestreamSupplies.renderCreate(w.document.getElementById("lvsp-body"));
  ok(/Livestream Supplies - Request supplies - Ring light/.test(w.document.getElementById("lvsp-summary").innerHTML), "title preview shown in summary");

  // My Requests header + date
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/livestream-supplies?tab=my-requests"); w.LivestreamSupplies.route(); await flush(); await flush();
  { const ths = Array.prototype.map.call(w.document.querySelectorAll("thead th"), t => t.textContent);
    ok(ths[0] === "Ngày request", "My Requests first header is 'Ngày request'");
    ok(ths.indexOf("Người request") >= 0, "My Requests has 'Người request' header");
    ok(ths.indexOf("Loại") >= 0 && ths.indexOf("Vật tư") >= 0 && ths.indexOf("Số lượng") >= 0, "list has Loại/Vật tư/Số lượng"); }
  ok(/06\/07\/2026/.test(cb()), "My Requests shows formatted date");
  ok(/EC-LVSP-2026-00001/.test(cb()) && /Bước 2\/3 · Sang Bui Review/.test(cb()), "My Requests shows step label");

  // detail via get_detail shows title
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/livestream-supplies?id=EC-LVSP-2026-00001"); w.LivestreamSupplies.route(); await flush(); await flush();
  ok(calls.get_detail && /class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail loads via get_detail with stepper");
  ok(/Livestream Supplies - Request supplies - Ring light/.test(cb()), "detail shows request_title prominently");

  // approve modal REQUIRES a comment
  w = boot(); await flush(); await flush();
  w.LivestreamSupplies.doApprove("EC-LVSP-2026-00001", detail()); await flush();
  { const ov = w.document.querySelector(".ec-lvsp-overlay");
    ok(!!ov, "approve modal opens");
    ok(/class="req"/.test(ov.innerHTML), "approve comment label marked required (*)");
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(!calls.approve, "empty comment does NOT call approve");
    ov.querySelector("#m-cmt").value = "Looks good"; ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(calls.approve && calls.approve.comment === "Looks good" && calls.approve.name === "EC-LVSP-2026-00001", "approve called with {name, comment}"); }

  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.livestream_supplies."/.test(JS), "uses Livestream Supplies whitelisted API");
  ok(/#ec-lvsp-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  console.log(fails === 0 ? "\nALL LIVESTREAM SUPPLIES PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
