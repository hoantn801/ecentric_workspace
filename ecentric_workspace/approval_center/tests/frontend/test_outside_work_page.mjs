// Headless tests for the Outside Work page (Node + jsdom). Form #2.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "outside_work.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-outside-work">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));

function boot(ctx) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/outside-work?tab=create" });
  const w = dom.window;
  w.frappe = { call: (o) => {
    if (o.method.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: ctx || { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C", manager_user: "m@x", manager_resolvable: true },
      is_system_manager: false, form_options: { work_types: ["Key live", "Campaign", "Business trip", "Other"] } } });
    if (o.method.endsWith("check_overlap")) return Promise.resolve({ message: { count: 0 } });
    if (o.method.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-OWRK-2026-00001", request_title: "Trip", work_type: "Business trip", start_date: "2026-08-01", end_date: "2026-08-03", duration_days: 3, approval_status: "Pending", current_level: 1, current_level_name: "Direct Manager", total_levels: 1, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (o.method.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-OWRK-2026-00001", request_title: "Trip", requested_by: "u@x", work_type: "Business trip", start_date: "2026-08-01", end_date: "2026-08-03", level_no: 1, level_name: "Direct Manager", total_levels: 1, my_status: "Pending" } ] : []) } });
    if (o.method.endsWith("get_detail")) return Promise.resolve({ message: {
      business: { name: "EC-OWRK-2026-00001", request_title: "Trip", work_type: "Business trip", start_date: "2026-08-01", end_date: "2026-08-03", duration_days: 3, direct_manager: "m@x", remarks: "team trip", requested_by: "u@x", department: "D" },
      approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
      levels: [{ level_no: 1, level_name: "Direct Manager", approval_mode: "Any One", level_status: "In Progress" }],
      approvers: [{ level_no: 1, approver: "m@x", status: "Pending" }], attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
      process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } } });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}

async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.OutsideWork, "OutsideWork exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment tab)");

  // create form: all fields + work type options + duration helper
  const cb = () => w.document.getElementById("owrk-body").innerHTML;
  ok(!!w.document.querySelector('[data-model="request_title"]'), "request_title field renders");
  ok(!!w.document.querySelector('[data-model="work_type"]'), "work_type field renders");
  ok(!!w.document.querySelector('[data-model="start_date"]') && !!w.document.querySelector('[data-model="end_date"]'), "start/end date fields render");
  ok(!!w.document.querySelector('[data-model="duration_days"]'), "duration_days field renders");
  ok(!!w.document.querySelector('[data-model="remarks"]'), "remarks field renders");
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders (optional)");
  ok(/Key live/.test(cb()) && /Campaign/.test(cb()) && /Business trip/.test(cb()) && /Other/.test(cb()), "work_type options render");
  ok(/Nhập 0.5 nếu là nửa ngày\./.test(cb()), "duration helper appears");

  // 3-day warning appears but submit stays possible (non-blocking)
  const near = new Date(); near.setDate(near.getDate() + 1);
  const iso = near.toISOString().slice(0, 10);
  w.OutsideWork.state.draft = { start_date: iso, end_date: iso };
  w.OutsideWork.apply3Day(); await flush();
  ok(/nên được gửi trước ít nhất 3 ngày/.test(w.document.getElementById("owrk-3day").innerHTML), "3-day warning appears when start_date < 3 days");
  ok(!w.OutsideWork.validateSubmit || (w.OutsideWork.validateSubmit({}) && !("start_date_within_3" in (w.OutsideWork.validateSubmit() || {}))), "3-day warning does not block submit (not a validation error)");

  // validateSubmit
  w.OutsideWork.state.draft = {};
  ok(!!(w.OutsideWork.validateSubmit() || {}).request_title, "validateSubmit: title required");
  w.OutsideWork.state.draft = { request_title: "T", work_type: "Other", start_date: "2026-08-01", end_date: "2026-07-01", duration_days: 1, remarks: "r" };
  ok(!!(w.OutsideWork.validateSubmit() || {}).end_date, "validateSubmit: end before start blocked");
  w.OutsideWork.state.draft = { request_title: "T", work_type: "Other", start_date: "2026-08-01", end_date: "2026-08-02", duration_days: 0, remarks: "r" };
  ok(!!(w.OutsideWork.validateSubmit() || {}).duration_days, "validateSubmit: duration must be > 0");
  w.OutsideWork.state.draft = { request_title: "T", work_type: "Other", start_date: "2026-08-01", end_date: "2026-08-02", duration_days: 0.5, remarks: "r" };
  ok(w.OutsideWork.validateSubmit() === null, "valid form (incl. 0.5 duration) passes validateSubmit");

  // suggestTitle
  ok(w.OutsideWork.suggestTitle({ work_type: "Business trip", start_date: "2026-08-01", end_date: "2026-08-03" }) === "Business trip - 2026-08-01 → 2026-08-03", "title auto-suggest format");

  // missing direct manager blocks submit
  w = boot({ user: "u@x", employee: "EMP-1", department: "D", company: "C", manager_user: null, manager_resolvable: false });
  await flush(); await flush();
  ok(/Bạn chưa có Quản lý trực tiếp/.test(w.document.getElementById("owrk-body").innerHTML), "missing manager shows friendly blocking alert");
  ok(w.document.getElementById("owrk-submit").disabled === true, "missing manager disables submit");

  // My Requests + Need My Approval render
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/outside-work?tab=my-requests"); w.OutsideWork.route(); await flush(); await flush();
  ok(/EC-OWRK-2026-00001/.test(w.document.getElementById("owrk-body").innerHTML) && /Bước 2\/3 · Direct Manager/.test(w.document.getElementById("owrk-body").innerHTML), "My Requests list renders with step label");
  w.history.pushState({}, "", "/approvals/outside-work?tab=my-approvals"); w.OutsideWork.route(); await flush(); await flush();
  ok(/Cần tôi xử lý/.test(w.document.getElementById("owrk-body").innerHTML) && !!w.document.querySelector('[data-quick="approve"]'), "Need My Approval renders with quick actions");

  // stepper: draft preview + runtime
  ok((w.OutsideWork.buildStepper({ approval: {}, process_preview: [{ level_no: 1, level_name: "Direct Manager" }] }).match(/class="step /g) || []).length === 3, "draft stepper = 3 steps (Tạo yêu cầu + Direct Manager + Hoàn tất)");
  const rh = w.OutsideWork.buildStepper({ approval: { name: "AR-1", approval_status: "Pending", current_level: 1 }, levels: [{ level_no: 1, level_name: "Direct Manager", approval_mode: "Any One", level_status: "In Progress" }], approvers: [{ level_no: 1, approver: "m@x", status: "Pending" }] });
  ok(/class="step done"/.test(rh) && /Đã gửi/.test(rh) && /class="step current"/.test(rh) && /Direct Manager/.test(rh), "runtime stepper: Đã gửi done + Direct Manager current");

  // detail renders + modals (namespaced) via delegated actions
  w.history.pushState({}, "", "/approvals/outside-work?id=EC-OWRK-2026-00001"); w.OutsideWork.route(); await flush(); await flush();
  ok(/class="stepper"/.test(w.document.getElementById("owrk-body").innerHTML), "detail renders the runtime stepper");
  const findAct = (a) => [...w.document.querySelectorAll('[data-act="' + a + '"]')][0];
  ok(!!findAct("approve"), "detail action panel renders Duyệt when can_approve");
  findAct("approve").click(); await flush();
  ok(!!w.document.querySelector(".ec-owrk-modal") && !w.document.querySelector(".modal") && /Duyệt yêu cầu/.test(w.document.body.innerHTML), "approve opens a namespaced .ec-owrk-modal (not generic .modal)");
  w.document.querySelector(".ec-owrk-overlay [data-x]").click();
  findAct("reject").click(); await flush();
  ok(/Từ chối yêu cầu/.test(w.document.body.innerHTML), "reject modal opens");
  w.document.querySelector(".ec-owrk-overlay [data-ok]").click(); await flush();
  ok(!!w.document.querySelector(".ec-owrk-overlay"), "empty reject reason blocks confirm (modal stays)");
  w.document.querySelector(".ec-owrk-overlay [data-x]").click();

  // resubmit (Information Required) shows banner + runtime stepper
  const irDet = { business: { name: "EC-OWRK-2026-00001", request_title: "Trip", work_type: "Business trip", start_date: "2026-08-01", end_date: "2026-08-03", duration_days: 3, remarks: "r" },
    approval: { name: "AR-1", approval_status: "Information Required", current_level: 1, information_requested_from_level: 1 },
    levels: [{ level_no: 1, level_name: "Direct Manager", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "m@x", status: "Information Requested", comment: "bổ sung" }], process_preview: [], capabilities: { can_edit: true } };
  w.OutsideWork.startEditResubmit(irDet); await flush();
  const eb = w.document.getElementById("owrk-body").innerHTML;
  ok(/class="stepper"/.test(eb) && /Đã gửi/.test(eb) && /class="step info"/.test(eb), "resubmit/edit form shows runtime stepper with info level");
  ok(/Cần bổ sung thông tin/.test(eb) && /bổ sung/.test(eb) && !!w.document.querySelector('[data-model="request_title"]'), "resubmit form shows info banner + editable form");

  // no raw DB error surfaced
  ok(w.OutsideWork.mapErr({ message: "pymysql.err.IntegrityError: (1062, ...)" }) === "Không thể thực hiện do dữ liệu không hợp lệ. Vui lòng kiểm tra lại hoặc liên hệ quản trị viên.", "raw DB error -> friendly generic message");
  ok(w.OutsideWork.mapErr({ message: "Bạn chưa có Quản lý trực tiếp trong hệ thống." }) === "Bạn chưa có Quản lý trực tiếp trong hệ thống.", "friendly VN message passes through");

  console.log(fails === 0 ? "\nALL OUTSIDE WORK PAGE TESTS PASSED" : ("\nFAILURES: " + fails));
  process.exit(fails === 0 ? 0 : 1);
}
run();
