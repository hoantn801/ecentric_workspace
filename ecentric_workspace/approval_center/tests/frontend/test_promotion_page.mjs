// Headless tests for the Promotion page (Node + jsdom). Multi-level (4 levels), no fulfillment, comments-required-on-approve.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "promotion.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-promotion">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = {};
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-PROM-2026-00001", request_title: "Promotion - A", full_name: "Nguyen Van A",
      department: "Engineering", current_position: "Engineer", proposed_position: "Senior Engineer",
      current_salary: 20000000, proposed_salary: 28000000, incentives: "bonus",
      justification: "great work", effective_date_of_promotion: "2026-09-01", requested_by: "u@x" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "CnB Review", approval_mode: "Any One", level_status: "Pending" },
             { level_no: 3, level_name: "HOF Review", approval_mode: "Any One", level_status: "Pending" },
             { level_no: 4, level_name: "CEO Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "tuan.ly@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/promotion?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "Engineering", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-PROM-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-PROM-2026-00001", request_title: "Promotion - A", full_name: "Nguyen Van A", proposed_position: "Senior Engineer",
        effective_date_of_promotion: "2026-09-01", approval_status: "Pending", current_level: 1,
        current_level_name: "Direct Manager Review", total_levels: 4, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-PROM-2026-00001", request_title: "Promotion - A", requested_by: "u@x", full_name: "Nguyen Van A",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 4, my_status: "Pending" } ] : [
      { name: "EC-PROM-2026-00002", request_title: "Old", requested_by: "u@x", full_name: "B",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 4, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.Promotion, "Promotion exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  const cb = () => w.document.getElementById("prom-body").innerHTML;
  ["request_title", "full_name", "department", "current_position", "proposed_position", "current_salary", "proposed_salary", "incentives", "justification", "effective_date_of_promotion"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.getElementById("prom-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("prom-process-preview");
    ok(pv.querySelectorAll(".step").length === 5, "preview has 5 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Direct Manager review/.test(pv.innerHTML) && /CnB review/.test(pv.innerHTML) && /HOF review/.test(pv.innerHTML) && /CEO review/.test(pv.innerHTML), "preview steps Tạo/Direct Manager/CnB/HOF/CEO");
    ok(!/SLA|giờ|ngày làm việc/.test(pv.innerHTML), "preview has no SLA text"); }
  // process preview appears before the request_title field in DOM order
  { const html = cb(); ok(html.indexOf('id="prom-process-preview"') >= 0 && html.indexOf('id="prom-process-preview"') < html.indexOf('data-model="request_title"'), "process preview before request_title"); }
  w.Promotion.state.draft = {};
  { const e = w.Promotion.validateSubmit() || {};
    ok(e.request_title && e.full_name && e.department && e.current_position && e.proposed_position && e.justification && e.current_salary && e.proposed_salary && e.effective_date_of_promotion, "validateSubmit requires key fields"); }
  // negative salary blocked
  w.Promotion.state.draft = { request_title: "T", full_name: "A", department: "D", current_position: "E", proposed_position: "SE", justification: "j", current_salary: 100, proposed_salary: -5, effective_date_of_promotion: "2026-09-01" };
  ok((w.Promotion.validateSubmit() || {}).proposed_salary, "negative salary blocked");
  // non-numeric salary blocked
  w.Promotion.state.draft.proposed_salary = "abc";
  ok((w.Promotion.validateSubmit() || {}).proposed_salary, "non-numeric salary blocked");
  // valid full draft passes
  w.Promotion.state.draft.proposed_salary = 28000000;
  ok(w.Promotion.validateSubmit() === null, "valid form passes");
  w.document.getElementById("prom-save").click(); await flush(); await flush();
  ok(calls.save_draft && /full_name/.test(calls.save_draft.payload) && /proposed_salary/.test(calls.save_draft.payload), "save_draft payload carries full_name + proposed_salary");
  // submit path calls submit_request with draft name
  w = boot(); await flush(); await flush();
  w.Promotion.state.draft = { request_title: "T", full_name: "A", department: "D", current_position: "E", proposed_position: "SE", justification: "j", current_salary: 100, proposed_salary: 200, effective_date_of_promotion: "2026-09-01" };
  w.document.getElementById("prom-submit").click(); await flush(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-PROM-2026-00001", "submit_request called with draft name");
  // My Requests + approvals (current status)
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/promotion?tab=my-requests"); w.Promotion.route(); await flush(); await flush();
  ok(/EC-PROM-2026-00001/.test(cb()) && /Bước 2\/6 · Direct Manager Review/.test(cb()), "My Requests shows step label");
  w.history.pushState({}, "", "/approvals/promotion?tab=my-approvals"); w.Promotion.route(); await flush(); await flush();
  { const done = w.document.getElementById("ap-done").innerHTML;
    ok(/Bước 6\/6 · Hoàn tất/.test(done) && /Đã duyệt/.test(done), "processed list shows current status/step (Hoàn tất)"); }
  // detail runtime stepper
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/promotion?id=EC-PROM-2026-00001"); w.Promotion.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper, no not-found");
  ok(/api\.promotion\.get_detail/.test("ecentric_workspace.approval_center.api.promotion.get_detail") && !!calls.get_detail, "detail loads via api.promotion.get_detail");
  { const rh = w.Promotion.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Direct Manager Review/.test(rh) && /CnB Review/.test(rh) && /HOF Review/.test(rh) && /CEO Review/.test(rh), "runtime stepper shows the 4 level names"); }
  // APPROVE modal requires a comment
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/promotion?id=EC-PROM-2026-00001"); w.Promotion.route(); await flush(); await flush();
  { delete calls.approve;
    w.Promotion.doApprove("EC-PROM-2026-00001", detail());
    const ov = w.document.querySelector(".ec-prom-overlay");
    ok(!!ov, "approve modal opened");
    // required marker near the comment textarea
    const body = ov.querySelector(".ec-prom-modal-b").innerHTML;
    const cmt = ov.querySelector("#m-cmt");
    ok(!!cmt && /class="req"/.test(body) && /nhận xét/i.test(body), "approve modal has required comment field (#m-cmt with req marker)");
    // confirming with empty comment must NOT call approve
    cmt.value = "";
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(!calls.approve, "empty comment does not call approve");
    // filling comment then confirming calls approve with {name, comment}
    const ov2 = w.document.querySelector(".ec-prom-overlay");
    ov2.querySelector("#m-cmt").value = "Đồng ý thăng chức";
    ov2.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(calls.approve && calls.approve.name === "EC-PROM-2026-00001" && /thăng chức/.test(calls.approve.comment || ""), "non-empty comment calls approve with {name, comment}"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.promotion."/.test(JS), "uses Promotion whitelisted API");
  ok(/#ec-prom-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  console.log(fails === 0 ? "\nALL PROMOTION PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
