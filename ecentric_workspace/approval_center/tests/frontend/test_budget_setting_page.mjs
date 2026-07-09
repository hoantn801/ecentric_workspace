// Headless tests for the Budget Setting page (Node + jsdom). Two-level review (HOF -> CEO),
// comments-required-on-approve, adaptive currency labels, attachment required.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "budget_setting.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-budget-setting">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = {
  departments: [ { value: "Engineering", label: "Engineering" }, { value: "Service", label: "Service" } ],
  budget_period_types: ["Annual", "Monthly"],
  yes_no: ["Yes", "No"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-BUDG-2026-00001", request_title: "Budget Setting - Annual - Engineering - 2027",
      budget_period_type: "Annual", period_start: "2027-01-01", department: "Engineering",
      approved_budget_current_period: 1000000000, actual_spending_current_period: 800000000,
      forecast_budget_next_period: 1200000000, forecast_justification: "growth plan",
      has_financial_risks: "No", financial_risk_details: "", additional_notes_comments: "n/a",
      request_attachment: "/files/budget.xlsx", requested_by: "u@x" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "HOF Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "CEO Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "hof@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-08 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/budget-setting?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "Engineering", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-BUDG-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-BUDG-2026-00001", request_title: "Budget Setting - Annual - Engineering - 2027",
        budget_period_type: "Annual", period_start: "2027-01-01", department: "Engineering",
        forecast_budget_next_period: 1200000000, approval_status: "Pending", current_level: 1,
        current_level_name: "HOF Review", total_levels: 2, modified: "2026-07-08 09:00",
        creation: "2026-07-08 09:00", requested_at: "2026-07-08 09:00", requester_name: "Emp Requester A" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-BUDG-2026-00001", request_title: "Budget Setting - Annual - Engineering - 2027", requested_by: "u@x",
        budget_period_type: "Annual", period_start: "2027-01-01", department: "Engineering", forecast_budget_next_period: 1200000000,
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 2, my_status: "Pending",
        creation: "2026-07-07 08:30", requested_at: "2026-07-07 08:30", requester_name: "Emp Requester A" } ] : [
      { name: "EC-BUDG-2026-00002", request_title: "Old", requested_by: "u@x", budget_period_type: "Monthly",
        approval_status: "Approved", current_level: 0, level_no: 2, total_levels: 2, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
function validDraft(over) {
  return Object.assign({ budget_period_type: "Annual", period_start: "2027-01-01", department: "Engineering",
    approved_budget_current_period: 1000000000, actual_spending_current_period: 800000000,
    forecast_budget_next_period: 1200000000, forecast_justification: "growth plan",
    has_financial_risks: "No", request_attachment: "/files/budget.xlsx" }, over || {});
}
async function run() {
  let w = boot(); await flush(); await flush();
  const cb = () => w.document.getElementById("budg-body").innerHTML;
  // shell + branding
  ok(!!w.document.querySelector(".ec-sidebar"), "eCentric shell .ec-sidebar present");
  ok(/Approval Center/.test(markup), "Approval Center header present");
  ok(/eCentric/.test(markup), "eCentric brand present");
  ok(!/Powered by ERPNext/i.test(HTML), "no 'Powered by ERPNext'");
  ok(/\.web-footer,\s*footer\.web-footer\s*\{\s*display:none/.test(HTML) || /\.web-footer, footer\.web-footer \{ display:none !important/.test(HTML), "web-footer hidden");
  ok(!!w.BudgetSetting, "window.BudgetSetting exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered");
  { const tt = w.document.getElementById("budg-tabs").innerHTML;
    ok(/Tạo mới/.test(tt) && /Yêu cầu của tôi/.test(tt) && /Cần tôi duyệt/.test(tt), "tabs: Tạo mới | Yêu cầu của tôi | Cần tôi duyệt"); }
  // create fields
  ["budget_period_type", "period_start", "department", "approved_budget_current_period", "actual_spending_current_period",
   "forecast_budget_next_period", "forecast_justification", "has_financial_risks", "additional_notes_comments"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('select[data-model="department"]') && !w.document.querySelector('input[data-model="department"]'), "Department is a select (from master)");
  { const dsel = w.document.querySelector('select[data-model="department"]');
    ok(/Engineering/.test(dsel.innerHTML) && /Service/.test(dsel.innerHTML), "Department options from master"); }
  ok(!!w.document.querySelector('[data-model="forecast_budget_next_period"]'), "forecast_budget_next_period field renders");
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "request_attachment file upload renders");
  ok(!w.document.querySelector('[data-model="request_title"]'), "NO request_title input");
  // process preview: 3 steps, no SLA
  { const pv = w.document.getElementById("budg-process-preview");
    ok(!!pv, "process preview renders");
    ok(pv.querySelectorAll(".step").length === 3, "preview has 3 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /HOF review/.test(pv.innerHTML) && /CEO review/.test(pv.innerHTML), "preview steps Tạo yêu cầu/HOF review/CEO review");
    ok(!/SLA|giờ|ngày làm việc/.test(pv.innerHTML), "preview has no SLA text"); }
  // ADAPTIVE LABELS
  w.BudgetSetting.state.draft = { budget_period_type: "Annual" };
  w.BudgetSetting.render(); await flush();
  ok(/current year/.test(cb()), "Annual -> label contains 'current year'");
  ok(/next year/.test(cb()), "Annual -> forecast label 'next year'");
  { const sel = w.document.querySelector('select[data-model="budget_period_type"]');
    sel.value = "Monthly"; sel.dispatchEvent(new w.Event("input", { bubbles: true })); }
  await flush(); await flush();
  ok(/current month/.test(cb()), "switching to Monthly -> label contains 'current month'");
  ok(/next month/.test(cb()), "Monthly -> forecast label 'next month'");
  ok(!/current year/.test(cb()), "Monthly no longer shows 'current year'");
  // financial_risk_details visibility
  w.BudgetSetting.state.draft = { has_financial_risks: "Yes", budget_period_type: "Annual" };
  w.BudgetSetting.render(); await flush();
  ok(!!w.document.querySelector('[data-model="financial_risk_details"]'), "financial_risk_details visible when Yes");
  w.BudgetSetting.state.draft = { has_financial_risks: "No", budget_period_type: "Annual" };
  w.BudgetSetting.render(); await flush();
  ok(!w.document.querySelector('[data-model="financial_risk_details"]'), "financial_risk_details hidden when not Yes");
  // validateSubmit
  w.BudgetSetting.state.draft = {};
  { const e = w.BudgetSetting.validateSubmit() || {};
    ok(e.budget_period_type && e.period_start && e.department && e.approved_budget_current_period && e.actual_spending_current_period && e.forecast_budget_next_period && e.forecast_justification && e.has_financial_risks && e.request_attachment, "validateSubmit requires the full set"); }
  // negative amount blocked
  w.BudgetSetting.state.draft = validDraft({ forecast_budget_next_period: -5 });
  ok((w.BudgetSetting.validateSubmit() || {}).forecast_budget_next_period, "negative amount blocked");
  // invalid department
  w.BudgetSetting.state.draft = validDraft({ department: "TESTING" });
  ok((w.BudgetSetting.validateSubmit() || {}).department, "invalid department (not in master) blocked");
  // Annual period not Jan 1
  w.BudgetSetting.state.draft = validDraft({ budget_period_type: "Annual", period_start: "2027-03-01" });
  ok((w.BudgetSetting.validateSubmit() || {}).period_start, "Annual period_start not Jan 1 rejected");
  // Monthly period not day 1
  w.BudgetSetting.state.draft = validDraft({ budget_period_type: "Monthly", period_start: "2027-03-15" });
  ok((w.BudgetSetting.validateSubmit() || {}).period_start, "Monthly period_start not day 1 rejected");
  // Monthly day 1 accepted
  w.BudgetSetting.state.draft = validDraft({ budget_period_type: "Monthly", period_start: "2027-03-01" });
  ok(!(w.BudgetSetting.validateSubmit() || {}).period_start, "Monthly period_start day 1 accepted");
  // attachment required
  w.BudgetSetting.state.draft = validDraft({ request_attachment: "" });
  ok((w.BudgetSetting.validateSubmit() || {}).request_attachment, "attachment required");
  // financial_risk_details required when Yes
  w.BudgetSetting.state.draft = validDraft({ has_financial_risks: "Yes", financial_risk_details: "" });
  ok((w.BudgetSetting.validateSubmit() || {}).financial_risk_details, "financial_risk_details required when Yes");
  // valid Annual draft passes
  w.BudgetSetting.state.draft = validDraft();
  ok(w.BudgetSetting.validateSubmit() === null, "valid Annual draft passes");
  // save_draft carries fields
  w = boot(); await flush(); await flush();
  w.BudgetSetting.state.draft = validDraft();
  w.document.getElementById("budg-save").click(); await flush(); await flush();
  ok(calls.save_draft && /"department":"Engineering"/.test(calls.save_draft.payload) && /forecast_budget_next_period/.test(calls.save_draft.payload), "save_draft payload carries department + forecast");
  // submit path
  w = boot(); await flush(); await flush();
  w.BudgetSetting.state.draft = validDraft();
  w.document.getElementById("budg-submit").click(); await flush(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-BUDG-2026-00001", "submit_request called with draft name");
  // My Requests columns
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/budget-setting?tab=my-requests"); w.BudgetSetting.route(); await flush(); await flush();
  { const ths = w.document.querySelectorAll("#budg-body table.tbl thead th");
    ok(ths.length > 0 && ths[0].textContent.trim() === "Ngày request", "My Requests first column is Ngày request");
    ok(Array.prototype.some.call(ths, function (t) { return t.textContent.trim() === "Người request"; }), "My Requests has Người request column");
    ok(Array.prototype.some.call(ths, function (t) { return t.textContent.trim() === "Kỳ"; }), "My Requests has Kỳ (period type) column");
    ok(Array.prototype.some.call(ths, function (t) { return t.textContent.trim() === "Dự báo kỳ sau"; }), "My Requests has Dự báo kỳ sau column");
    ok(/08\/07\/2026 09:00/.test(cb()), "My Requests row shows dd/MM/yyyy HH:mm date");
    ok(/Emp Requester A/.test(cb()), "My Requests row shows requester name");
    ok(/Bước 2\/4 · HOF Review/.test(cb()), "My Requests shows step label"); }
  // detail via get_detail shows period type + forecast
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/budget-setting?id=EC-BUDG-2026-00001"); w.BudgetSetting.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper");
  ok(!!calls.get_detail, "detail loads via api.budget_setting.get_detail");
  ok(/Annual/.test(cb()), "detail shows budget period type");
  ok(/1200000000/.test(cb()), "detail shows forecast budget next period");
  { const rh = w.BudgetSetting.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /HOF Review/.test(rh) && /CEO Review/.test(rh), "runtime stepper shows HOF + CEO levels"); }
  // APPROVE modal requires a comment
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/budget-setting?id=EC-BUDG-2026-00001"); w.BudgetSetting.route(); await flush(); await flush();
  { delete calls.approve;
    w.BudgetSetting.doApprove("EC-BUDG-2026-00001", detail());
    const ov = w.document.querySelector(".ec-budg-overlay");
    ok(!!ov, "approve modal opened");
    const body = ov.querySelector(".ec-budg-modal-b").innerHTML;
    const cmt = ov.querySelector("#m-cmt");
    ok(!!cmt && /class="req"/.test(body) && /nhận xét/i.test(body), "approve modal has required comment field");
    cmt.value = "";
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(!calls.approve, "empty comment does not call approve");
    const ov2 = w.document.querySelector(".ec-budg-overlay");
    ov2.querySelector("#m-cmt").value = "Đồng ý ngân sách";
    ov2.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(calls.approve && calls.approve.name === "EC-BUDG-2026-00001" && /ngân sách/.test(calls.approve.comment || ""), "non-empty comment calls approve with {name, comment}"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.budget_setting."/.test(JS), "uses Budget Setting whitelisted API");
  ok(/#ec-budg-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  console.log(fails === 0 ? "\nALL BUDGET SETTING PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
