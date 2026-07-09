// Headless jsdom tests for the LivestreamSupplies page (Batch 7). Standalone Approval Center page,
// no Desk shim, API/service layer only. Auto-title in summary/list/detail; typed buttons.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "livestream_supplies.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-lvs">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const calls = {};
let w;
function detail(over) {
  return Object.assign({
    business: { name: "LVS-2026-00001", supplies:"Camera", request_type:"Request supplies", quantity:2, start_date:"2026-08-01", end_date:"2026-08-02", request_title:"Livestream Supplies - Request supplies - Camera", requester_name: "U", requested_by: "u@x", creation: "2026-07-08 09:00" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1, status_label: "Dang phe duyet" },
    levels: [], approvers: [], attachments: [], timeline: [],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot() {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/livestream-supplies?tab=create" });
  const win = dom.window;
  win.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U" }, is_system_manager: false, form_options: {} } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "LVS-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [ Object.assign({ name: "LVS-2026-00001", approval_status: "Pending", current_level: 1, current_level_name: "L1", total_levels: 1, creation: "2026-07-08 09:00", requested_at: "2026-07-08 09:00", requester_name: "U" }, detail().business) ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [ Object.assign({ name: "LVS-2026-00001", approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 1, my_status: "Pending", creation: "2026-07-08 09:00", requested_at: "2026-07-08 09:00", requester_name: "U" }, detail().business) ] : []) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: detail() });
    if (m.endsWith("approve")) return Promise.resolve({ message: { detail: detail({ approval: { approval_status: "Approved", status_label: "Da duyet" } }) } });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  } };
  win.eval(JS);
  return win;
}
const LV = () => w.LivestreamSupplies;
function nav(tab){ w.history.pushState({}, "", "/approvals/livestream-supplies?tab=" + tab); LV().route(); }
async function run() {
  w = boot(); await flush(); await flush();
  ok(!!w.LivestreamSupplies, "LivestreamSupplies exposed");
  ok(!!w.document.querySelector('[data-model="supplies"]'), "supplies field renders");
  ok(!!w.document.querySelector('[data-model="request_type"]'), "request_type field renders");
  ok(!!w.document.querySelector('[data-model="quantity"]'), "quantity field renders");
  ok(!!w.document.querySelector('[data-model="justification"]'), "justification field renders");
  ok(!!w.document.querySelector('[data-model="start_date"]'), "start_date field renders");
  ok(!!w.document.querySelector('[data-model="end_date"]'), "end_date field renders");
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders (optional)");
  LV().state.draft = { supplies:"Camera", request_type:"Request supplies", quantity:2, justification:"live", start_date:"2026-08-01", end_date:"2026-08-02" }; LV().render(); await flush();
  ok(w.document.getElementById("lvs-summary").innerHTML.indexOf("Livestream Supplies - Request supplies - Camera") >= 0, "auto title shown in summary");
  ok(LV().titlePreview({ supplies:"Camera", request_type:"Request supplies", quantity:2, justification:"live", start_date:"2026-08-01", end_date:"2026-08-02" }) === "Livestream Supplies - Request supplies - Camera", "titlePreview builds auto title");
  LV().state.draft = { supplies:"Camera", request_type:"Request supplies", quantity:2, justification:"live", start_date:"2026-08-01", end_date:"2026-08-02" };
  var sb = w.document.getElementById("lvs-submit"); sb.click(); await flush(); await flush();
  ok(!!calls.save_draft && !!calls.submit_request, "submit works without attachment (save_draft+submit_request called)");
  ok(!calls.save_draft.request_attachment, "attachment not required in submit payload");
  nav("my-requests"); await flush(); await flush();
  { var lb = w.document.getElementById("lvs-body").innerHTML;
    ok(lb.indexOf("Ngày request") >= 0 && lb.indexOf("Ngày request") < lb.indexOf("Mã"), "list: Ngày request is first column");
    ok(lb.indexOf("Người request") >= 0, "list: Người request column present");
    ok(lb.indexOf("Tiêu đề") >= 0, "list: auto title column present"); }
  w.history.pushState({}, "", "/approvals/livestream-supplies?id=LVS-2026-00001"); LV().route(); await flush(); await flush();
  { var db = w.document.getElementById("lvs-body").innerHTML;
    ok(db.indexOf("Livestream Supplies - Request supplies - Camera") >= 0, "detail shows auto title"); }
  ok(JS.indexOf('"ecentric_workspace.approval_center.api.livestream_supplies."') >= 0, "uses livestream_supplies whitelisted API namespace");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/livestream-supplies?id=LVS-2026-00001"); LV().route(); await flush(); await flush();
  LV().doApprove("LVS-2026-00001", detail()); await flush();
  { var ov = w.document.querySelector(".ec-lvs-overlay"); ok(!!ov, "approve modal opens");
    var reqd = /Ghi ch[^<]*<span class="req">/.test(ov.innerHTML);
    ok(reqd === true, "approve modal comment requiredness matches spec (true)"); }

  // qty>0 and end>=start validation
  { w=boot(); await flush(); await flush(); nav("create"); await flush();
    LV().state.draft={ supplies:"Cam", request_type:"Request supplies", quantity:0, justification:"j", start_date:"2026-08-02", end_date:"2026-08-01" };
    var e=LV().validateSubmit()||{};
    ok(e.quantity, "LVS: quantity>0 required"); ok(e.end_date, "LVS: end_date>=start_date enforced"); }

  console.log(fails === 0 ? "\nALL LIVESTREAMSUPPLIES PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
