// Headless tests for the Resignation Request page (Node + jsdom). Fulfillment form (L1 = Direct Manager Review, HR fulfillment).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "resignation.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-resignation">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));

const FO = {
  resignation_for: ["Myself", "Request for the others"],
  resignation_reasons: ["Unsuitable environment", "Have another direction", "Cultural Environment", "Personal Matters (Family, Myself,...)"],
  ratings: ["5 (Very satisfied)", "4 (Satisfied)", "3 (Neutral)", "2 (Dissatisfied)", "1 (Very dissatisfied)"],
  recommend_options: ["Yes", "No", "Maybe"],
};
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-RESN-2026-00001", request_title: "Resignation Request_ODS_Nguyen Van A",
      resignation_for: "Myself", employee_email: "a@company.com", personal_email: "a@gmail.com",
      last_working_day: "2026-08-15", resignation_reason: "Have another direction",
      workplace_environment_rating: "4 (Satisfied)", benefit_policy_rating: "4 (Satisfied)",
      corporate_culture_rating: "5 (Very satisfied)", recommend_to_friend: "Yes",
      final_message: "Thanks all", requested_by: "u@x", department: "D", fulfillment_status: "Not Started" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "mgr@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    fulfillment: { status: "Not Started" },
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true, can_complete: true } }, over || {});
}

function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/resignation?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true, fulfillment: (over && over.fulfillment) || false },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-RESN-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-RESN-2026-00001", request_title: "Resignation A", resignation_for: "Myself",
        resignation_reason: "Have another direction", last_working_day: "2026-08-15", fulfillment_status: "Completed",
        approval_status: "Approved", current_level: 0, total_levels: 1, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-RESN-2026-00001", request_title: "Resignation A", requested_by: "u@x", resignation_for: "Myself",
        resignation_reason: "Have another direction", level_no: 1, level_name: "Direct Manager Review", current_level: 1,
        current_level_name: "Direct Manager Review", approval_status: "Pending", fulfillment_status: "Not Started",
        total_levels: 1, my_status: "Pending" } ] : [
      { name: "EC-RESN-2026-00002", request_title: "Resignation B", requested_by: "u@x", resignation_for: "Myself",
        resignation_reason: "Personal Matters (Family, Myself,...)", level_no: 1, acted_level_name: "Direct Manager Review",
        current_level: 0, current_level_name: null, approval_status: "Approved", fulfillment_status: "Completed",
        total_levels: 1, my_status: "Approved" } ]) } });
    if (m.endsWith("list_fulfillment_queue")) return Promise.resolve({ message: { rows: [
      { name: "EC-RESN-2026-00001", request_title: "Resignation A", requested_by: "u@x", resignation_for: "Myself",
        resignation_reason: "Have another direction", last_working_day: "2026-08-15", fulfillment_status: "Assigned", fulfillment_owner: null } ] } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}

async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.Resignation, "Resignation exposed");
  ok(w.document.querySelectorAll(".tab").length === 4, "four tabs rendered (incl. fulfillment)");

  const cb = () => w.document.getElementById("resn-body").innerHTML;
  // all create fields render
  ["request_title", "resignation_for", "employee_email", "personal_email", "last_working_day", "resignation_reason",
   "workplace_environment_rating", "benefit_policy_rating", "corporate_culture_rating", "recommend_to_friend", "final_message"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders");
  });
  // no attachment field on create
  ok(!w.document.querySelector('[data-upload]'), "no attachment upload on create form");

  // process preview before request_title, exactly 4 steps
  ok(!!w.document.getElementById("resn-process-preview"), "process preview card renders");
  { const html = cb(); ok(html.indexOf('id="resn-process-preview"') < html.indexOf('data-model="request_title"'), "preview renders before request_title"); }
  { const pv = w.document.getElementById("resn-process-preview");
    ok(pv.querySelectorAll(".step").length === 4, "preview has exactly 4 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Direct Manager review/.test(pv.innerHTML) && /HR xử lý/.test(pv.innerHTML) && /Hoàn tất/.test(pv.innerHTML), "preview steps: Tạo/Direct Manager review/HR xử lý/Hoàn tất");
    ok(!/SLA/i.test(pv.innerHTML), "preview shows no misleading SLA text"); }

  // options render
  ok(/Myself/.test(cb()) && /Request for the others/.test(cb()), "resignation_for options render");
  ok(/Have another direction/.test(cb()) && /Cultural Environment/.test(cb()), "resignation_reason options render");
  ok(/5 \(Very satisfied\)/.test(cb()) && /1 \(Very dissatisfied\)/.test(cb()), "rating options render");

  // validateSubmit
  w.Resignation.state.draft = {};
  ok(!!(w.Resignation.validateSubmit() || {}).request_title, "validateSubmit: title required");
  const goodDraft = { request_title: "T", resignation_for: "Myself", employee_email: "a@company.com",
    personal_email: "a@gmail.com", last_working_day: "2026-08-15", resignation_reason: "Have another direction",
    workplace_environment_rating: "4 (Satisfied)", benefit_policy_rating: "4 (Satisfied)", corporate_culture_rating: "5 (Very satisfied)" };
  // bad email
  w.Resignation.state.draft = Object.assign({}, goodDraft, { employee_email: "not-an-email" });
  ok(!!(w.Resignation.validateSubmit() || {}).employee_email, "validateSubmit rejects a bad email");
  // missing rating
  w.Resignation.state.draft = Object.assign({}, goodDraft, { benefit_policy_rating: "" });
  ok(!!(w.Resignation.validateSubmit() || {}).benefit_policy_rating, "validateSubmit rejects a missing rating");
  // full valid
  w.Resignation.state.draft = Object.assign({}, goodDraft);
  ok(w.Resignation.validateSubmit() === null, "valid form passes validateSubmit");
  ok(w.Resignation.suggestTitle({ resignation_reason: "Have another direction", last_working_day: "2026-08-15" }) === "Have another direction - 2026-08-15", "title auto-suggest format");

  // draft save payload carries resignation_for + employee_email
  w.document.getElementById("resn-save").click(); await flush(); await flush();
  ok(calls.save_draft && /resignation_for/.test(calls.save_draft.payload) && /employee_email/.test(calls.save_draft.payload), "save_draft payload carries resignation_for + employee_email");

  // submit payload
  w = boot(); await flush(); await flush();
  w.Resignation.state.draft = Object.assign({}, goodDraft);
  w.Resignation.state.titleTouched = true;
  w.document.getElementById("resn-submit").click(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-RESN-2026-00001", "submit_request called with draft name");

  // My Requests
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/resignation?tab=my-requests"); w.Resignation.route(); await flush(); await flush();
  ok(/EC-RESN-2026-00001/.test(cb()) && /Bước 4\/4 · Hoàn tất/.test(cb()), "My Requests list renders with fulfillment step label for completed row");

  // Need My Approval
  w.history.pushState({}, "", "/approvals/resignation?tab=my-approvals"); w.Resignation.route(); await flush(); await flush();
  ok(/Cần tôi xử lý/.test(cb()) && !!w.document.querySelector('[data-quick="approve"]'), "Need My Approval renders with quick actions");

  // Fulfillment queue (fulfiller)
  w = boot({ fulfillment: true }); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/resignation?tab=fulfillment"); w.Resignation.route(); await flush(); await flush();
  ok(/EC-RESN-2026-00001/.test(cb()) && !!w.document.querySelector('[data-claim]'), "fulfillment queue renders with claim button");

  // detail runtime stepper
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/resignation?id=EC-RESN-2026-00001"); w.Resignation.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()), "detail renders the runtime stepper");
  { const rh = w.Resignation.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /HR xử lý/.test(rh) && /Direct Manager Review/.test(rh), "runtime stepper: Đã gửi + Direct Manager Review + HR xử lý"); }

  // request info / resubmit banner + runtime stepper
  w = boot({ detail: detail({ approval: { name: "AR-1", approval_status: "Information Required", current_level: 1, information_requested_from_level: 1 },
    approvers: [{ level_no: 1, approver: "mgr@x", status: "Information Requested", comment: "cần thêm chi tiết" }],
    capabilities: { can_edit: true } }) }); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/resignation?id=EC-RESN-2026-00001"); w.Resignation.route(); await flush(); await flush();
  w.Resignation.startEditResubmit(w.Resignation.state.detail); await flush();
  { const eb = cb(); ok(/Cần bổ sung thông tin/.test(eb) && /class="stepper"/.test(eb) && /class="step info"/.test(eb), "resubmit/edit form shows banner + runtime stepper with info level"); }

  // fulfillment complete modal + completionErrors
  w = boot(); await flush(); await flush();
  ok((w.Resignation.completionErrors({}) || {}).fulfillment_summary, "completionErrors requires fulfillment_summary");
  ok(w.Resignation.completionErrors({ fulfillment_summary: "done" }) === null, "completionErrors passes with fulfillment_summary");
  w.Resignation.doComplete("EC-RESN-2026-00001", detail()); await flush();
  ok(!!w.document.querySelector(".ec-resn-overlay #c-summary"), "complete modal renders #c-summary");
  ok(!w.document.querySelector(".ec-resn-overlay #c-opnote"), "complete modal does NOT render #c-opnote");
  ok(!w.document.querySelector(".ec-resn-overlay #c-link"), "complete modal does NOT render #c-link");
  ok(!w.document.querySelector(".ec-resn-overlay #c-opdate"), "complete modal does NOT render #c-opdate");
  { const ov = w.document.querySelector(".ec-resn-overlay [data-x]"); if (ov) ov.click(); }

  // doApprove modal: comment box, NO operation date
  w = boot(); await flush(); await flush();
  w.Resignation.doApprove("EC-RESN-2026-00001", detail()); await flush();
  ok(!!w.document.querySelector(".ec-resn-overlay #m-cmt"), "approve modal renders a comment box");
  ok(!w.document.querySelector(".ec-resn-overlay #m-opdate"), "approve modal has NO expected completion date (#m-opdate)");
  { const ov = w.document.querySelector(".ec-resn-overlay [data-x]"); if (ov) ov.click(); }

  // step label + badge for completed row
  ok(w.Resignation.stepLabel({ approval_status: "Approved", fulfillment_status: "Completed", total_levels: 1 }) === "Bước 4/4 · Hoàn tất", "completed row step label = Bước 4/4 · Hoàn tất");
  ok(/Hoàn tất/.test(w.Resignation.badge({ approval_status: "Approved", fulfillment_status: "Completed" })), "completed row badge shows Hoàn tất");

  // no Desk-style shim; detail loads via the whitelisted API only
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style frappe.db.get_doc / frappe.client shim");
  ok(/"ecentric_workspace.approval_center.api.resignation."/.test(JS), "calls the Resignation whitelisted API namespace");
  { let usedApi = false, usedClient = false; const w4 = boot(); w4.frappe.call = ((orig) => (o) => {
      if (o.method === "ecentric_workspace.approval_center.api.resignation.get_detail") usedApi = true;
      if (/frappe\.client|frappe\.db/.test(o.method)) usedClient = true; return orig(o); })(w4.frappe.call);
    await flush(); await flush();
    w4.history.pushState({}, "", "/approvals/resignation?id=EC-RESN-2026-00001"); w4.Resignation.route(); await flush(); await flush();
    ok(usedApi && !usedClient, "detail loads via api.resignation.get_detail, not a generic client get"); }

  // every button has explicit type
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every <button> has an explicit type attribute (no native submit)");
  ok(!/<button [^>]*type="submit"/.test(HTML), "no submit-type buttons in Resignation markup");

  // valid detail renders, no not-found, single fetch
  { let n = 0; const w2 = boot(); await flush(); await flush();
    w2.frappe.call = ((orig) => (o) => { if (o.method.endsWith("get_detail")) n++; return orig(o); })(w2.frappe.call);
    w2.history.pushState({}, "", "/approvals/resignation?id=EC-RESN-2026-00001"); w2.Resignation.route(); await flush(); await flush();
    const body = w2.document.getElementById("resn-body").innerHTML;
    ok(/class="stepper"/.test(body), "valid detail renders on load");
    ok(!/Không tải được yêu cầu/.test(body), "no inline/blocking not-found on a successful detail load");
    ok(n === 1, "detail load fires exactly one get_detail (no racing duplicate loads)"); }

  // boots without throwing
  ok((() => { try { const w3 = boot(); return !!w3.Resignation; } catch (e) { return false; } })(), "script boots without throwing (null-safe bindings)");

  // balanced width CSS assertions
  ok(/#ec-resn-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced centered content width");
  ok(/#ec-resn-root .resn-formwrap\{[^}]*max-width:none/.test(HTML), "form wrapper aligns under header/tabs");
  ok(/@media \(max-width:1024px\)/.test(HTML), "responsive rule preserved");
  ok(/#ec-resn-root .tbl td .btn\{[^}]*padding:5px 10px/.test(HTML), "table action buttons use a compact padding");
  ok(/#ec-resn-root .tbl td\{[^}]*vertical-align:middle/.test(HTML), "table cells vertically center the action buttons");

  console.log(fails === 0 ? "\nALL RESIGNATION PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
