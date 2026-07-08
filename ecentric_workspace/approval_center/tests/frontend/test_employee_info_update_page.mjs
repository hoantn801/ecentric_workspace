// Headless jsdom tests for the EmployeeInfoUpdate page (Batch 7). Standalone Approval Center page,
// no Desk shim, API/service layer only. Auto-title in summary/list/detail; typed buttons.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "employee_info_update.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-eiu">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const calls = {};
let w;
function detail(over) {
  return Object.assign({
    business: { name: "EIU-2026-00001", employee_email:"a@b.com", field_to_update:"Bank account", current_value:"x", new_value:"y", request_title:"Employee Info Update - a@b.com - Bank account", requester_name: "U", requested_by: "u@x", creation: "2026-07-08 09:00" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1, status_label: "Dang phe duyet" },
    levels: [], approvers: [], attachments: [], timeline: [],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot() {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/employee-information-update?tab=create" });
  const win = dom.window;
  win.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U" }, is_system_manager: false, form_options: {} } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EIU-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [ Object.assign({ name: "EIU-2026-00001", approval_status: "Pending", current_level: 1, current_level_name: "L1", total_levels: 1, creation: "2026-07-08 09:00", requested_at: "2026-07-08 09:00", requester_name: "U" }, detail().business) ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [ Object.assign({ name: "EIU-2026-00001", approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 1, my_status: "Pending", creation: "2026-07-08 09:00", requested_at: "2026-07-08 09:00", requester_name: "U" }, detail().business) ] : []) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: detail() });
    if (m.endsWith("approve")) return Promise.resolve({ message: { detail: detail({ approval: { approval_status: "Approved", status_label: "Da duyet" } }) } });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  } };
  win.eval(JS);
  return win;
}
const LV = () => w.EmployeeInfoUpdate;
function nav(tab){ w.history.pushState({}, "", "/approvals/employee-information-update?tab=" + tab); LV().route(); }
async function run() {
  w = boot(); await flush(); await flush();
  ok(!!w.EmployeeInfoUpdate, "EmployeeInfoUpdate exposed");
  ok(!!w.document.querySelector('[data-model="employee_email"]'), "employee_email field renders");
  ok(!!w.document.querySelector('[data-model="field_to_update"]'), "field_to_update field renders");
  ok(!!w.document.querySelector('[data-model="current_value"]'), "current_value field renders");
  ok(!!w.document.querySelector('[data-model="new_value"]'), "new_value field renders");
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders (optional)");
  LV().state.draft = { employee_email:"a@b.com", field_to_update:"Bank account", current_value:"x", new_value:"y" }; LV().render(); await flush();
  ok(w.document.getElementById("eiu-summary").innerHTML.indexOf("Employee Info Update - a@b.com - Bank account") >= 0, "auto title shown in summary");
  ok(LV().titlePreview({ employee_email:"a@b.com", field_to_update:"Bank account", current_value:"x", new_value:"y" }) === "Employee Info Update - a@b.com - Bank account", "titlePreview builds auto title");
  LV().state.draft = { employee_email:"a@b.com", field_to_update:"Bank account", current_value:"x", new_value:"y" };
  var sb = w.document.getElementById("eiu-submit"); sb.click(); await flush(); await flush();
  ok(!!calls.save_draft && !!calls.submit_request, "submit works without attachment (save_draft+submit_request called)");
  ok(!calls.save_draft.request_attachment, "attachment not required in submit payload");
  nav("my-requests"); await flush(); await flush();
  { var lb = w.document.getElementById("eiu-body").innerHTML;
    ok(lb.indexOf("Ngày request") >= 0 && lb.indexOf("Ngày request") < lb.indexOf("Mã"), "list: Ngày request is first column");
    ok(lb.indexOf("Người request") >= 0, "list: Người request column present");
    ok(lb.indexOf("Tiêu đề") >= 0, "list: auto title column present"); }
  w.history.pushState({}, "", "/approvals/employee-information-update?id=EIU-2026-00001"); LV().route(); await flush(); await flush();
  { var db = w.document.getElementById("eiu-body").innerHTML;
    ok(db.indexOf("Employee Info Update - a@b.com - Bank account") >= 0, "detail shows auto title"); }
  ok(JS.indexOf('"ecentric_workspace.approval_center.api.employee_info_update."') >= 0, "uses employee_info_update whitelisted API namespace");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/employee-information-update?id=EIU-2026-00001"); LV().route(); await flush(); await flush();
  LV().doApprove("EIU-2026-00001", detail()); await flush();
  { var ov = w.document.querySelector(".ec-eiu-overlay"); ok(!!ov, "approve modal opens");
    var reqd = /Ghi ch[^<]*<span class="req">/.test(ov.innerHTML);
    ok(reqd === false, "approve modal comment requiredness matches spec (false)"); }

  // bilingual VN helper for field_to_update
  { w=boot(); await flush(); await flush(); nav("create"); await flush();
    var sel=w.document.querySelector('[data-model="field_to_update"]'); sel.value="Bank account";
    sel.dispatchEvent(new w.Event("change")); await flush();
    var vh=w.document.querySelector('[data-vn="field_to_update"]');
    ok(vh && /Tài khoản ngân hàng/.test(vh.textContent), "EIU: field_to_update shows Vietnamese helper"); }

  console.log(fails === 0 ? "\nALL EMPLOYEEINFOUPDATE PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
