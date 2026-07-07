// Headless tests for the Special Bonus page (Node + jsdom). Multi-level (4 levels), no fulfillment, comments Off (approve comment optional).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "special_bonus.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-special-bonus">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = { departments: [ { value: "Engineering", label: "Engineering" }, { value: "Service", label: "Service" } ] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-SPBN-2026-00001", request_title: "Special Bonus - Project X",
      department: "Engineering", project_name: "Project X", reasons: "great work",
      total_bonus: 5000000, request_attachment: "/files/x.pdf", requested_by: "u@x" },
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
    { runScripts: "outside-only", url: "https://x.test/approvals/special-bonus?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "Engineering", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-SPBN-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-SPBN-2026-00001", request_title: "Special Bonus - Project X", department: "Engineering", project_name: "Project X",
        total_bonus: 5000000, approval_status: "Pending", current_level: 1,
        current_level_name: "Direct Manager Review", total_levels: 4, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-SPBN-2026-00001", request_title: "Special Bonus - Project X", requested_by: "u@x", project_name: "Project X",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 4, my_status: "Pending" } ] : [
      { name: "EC-SPBN-2026-00002", request_title: "Old", requested_by: "u@x", project_name: "Y",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 4, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.SpecialBonus, "SpecialBonus exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  const cb = () => w.document.getElementById("spbn-body").innerHTML;
  ["request_title", "department", "project_name", "reasons", "total_bonus"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload control renders");
  ok(!!w.document.querySelector('select[data-model="department"]') && !w.document.querySelector('input[data-model="department"]'), "Department is a select (not free-text input)");
  { const dsel = w.document.querySelector('select[data-model="department"]'); const html = dsel ? dsel.innerHTML : "";
    ok(/Engineering/.test(html) && /Service/.test(html), "Department options loaded/rendered from master"); }
  ok(!!w.document.getElementById("spbn-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("spbn-process-preview");
    ok(pv.querySelectorAll(".step").length === 5, "preview has 5 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Direct Manager review/.test(pv.innerHTML) && /CnB review/.test(pv.innerHTML) && /HOF review/.test(pv.innerHTML) && /CEO review/.test(pv.innerHTML), "preview steps Tạo/Direct Manager/CnB/HOF/CEO");
    ok(!/SLA|giờ|ngày làm việc/.test(pv.innerHTML), "preview has no SLA text"); }
  { const html = cb(); ok(html.indexOf('id="spbn-process-preview"') >= 0 && html.indexOf('id="spbn-process-preview"') < html.indexOf('data-model="request_title"'), "process preview before request_title"); }
  // validateSubmit — empty draft requires key fields
  w.SpecialBonus.state.draft = {};
  { const e = w.SpecialBonus.validateSubmit() || {};
    ok(e.request_title && e.department && e.project_name && e.reasons && e.total_bonus && e.request_attachment, "validateSubmit requires title/department/project/reasons/total_bonus/attachment"); }
  // invalid department blocked
  w.SpecialBonus.state.draft = { request_title: "T", department: "TESTING", project_name: "P", reasons: "r", total_bonus: 100, request_attachment: "/files/x.pdf" };
  ok((w.SpecialBonus.validateSubmit() || {}).department, "invalid department (not in master) blocked");
  // missing department blocked
  w.SpecialBonus.state.draft = { request_title: "T", project_name: "P", reasons: "r", total_bonus: 100, request_attachment: "/files/x.pdf" };
  ok((w.SpecialBonus.validateSubmit() || {}).department, "missing department blocked");
  // negative bonus blocked
  w.SpecialBonus.state.draft = { request_title: "T", department: "Engineering", project_name: "P", reasons: "r", total_bonus: -5, request_attachment: "/files/x.pdf" };
  ok((w.SpecialBonus.validateSubmit() || {}).total_bonus, "negative total_bonus blocked");
  // missing attachment blocked
  w.SpecialBonus.state.draft = { request_title: "T", department: "Engineering", project_name: "P", reasons: "r", total_bonus: 100 };
  ok((w.SpecialBonus.validateSubmit() || {}).request_attachment, "missing attachment blocked");
  // valid full draft passes
  w.SpecialBonus.state.draft = { request_title: "T", department: "Engineering", project_name: "P", reasons: "r", total_bonus: 5000000, request_attachment: "/files/x.pdf" };
  ok(w.SpecialBonus.validateSubmit() === null, "valid form passes");
  w.document.getElementById("spbn-save").click(); await flush(); await flush();
  ok(calls.save_draft && /project_name/.test(calls.save_draft.payload) && /total_bonus/.test(calls.save_draft.payload), "save_draft payload carries project_name + total_bonus");
  ok(calls.save_draft && /"department":"Engineering"/.test(calls.save_draft.payload), "save_draft payload carries exact Department name");
  // submit path calls submit_request with draft name
  w = boot(); await flush(); await flush();
  w.SpecialBonus.state.draft = { request_title: "T", department: "Engineering", project_name: "P", reasons: "r", total_bonus: 100, request_attachment: "/files/x.pdf" };
  w.document.getElementById("spbn-submit").click(); await flush(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-SPBN-2026-00001", "submit_request called with draft name");
  // My Requests + approvals
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/special-bonus?tab=my-requests"); w.SpecialBonus.route(); await flush(); await flush();
  ok(/EC-SPBN-2026-00001/.test(cb()) && /Bước 2\/6 · Direct Manager Review/.test(cb()), "My Requests shows step label");
  w.history.pushState({}, "", "/approvals/special-bonus?tab=my-approvals"); w.SpecialBonus.route(); await flush(); await flush();
  { const done = w.document.getElementById("ap-done").innerHTML;
    ok(/Bước 6\/6 · Hoàn tất/.test(done) && /Đã duyệt/.test(done), "processed list shows current status/step (Hoàn tất)"); }
  // detail runtime stepper
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/special-bonus?id=EC-SPBN-2026-00001"); w.SpecialBonus.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper, no not-found");
  ok(/api\.special_bonus\.get_detail/.test("ecentric_workspace.approval_center.api.special_bonus.get_detail") && !!calls.get_detail, "detail loads via api.special_bonus.get_detail");
  { const rh = w.SpecialBonus.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Direct Manager Review/.test(rh) && /CnB Review/.test(rh) && /HOF Review/.test(rh) && /CEO Review/.test(rh), "runtime stepper shows the 4 level names"); }
  // APPROVE modal — comments OFF: comment optional, empty comment proceeds
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/special-bonus?id=EC-SPBN-2026-00001"); w.SpecialBonus.route(); await flush(); await flush();
  { delete calls.approve;
    w.SpecialBonus.doApprove("EC-SPBN-2026-00001", detail());
    const ov = w.document.querySelector(".ec-spbn-overlay");
    ok(!!ov, "approve modal opened");
    const cmt = ov.querySelector("#m-cmt");
    // comments Off: the comment field must NOT carry a required marker
    const label = cmt ? cmt.closest(".fld").querySelector("label") : null;
    ok(!!cmt && label && !/class="req"/.test(label.innerHTML), "approve modal comment is optional (no required marker)");
    // confirming with empty comment MUST call approve (comments Off)
    cmt.value = "";
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(calls.approve && calls.approve.name === "EC-SPBN-2026-00001" && (calls.approve.comment === "" || calls.approve.comment == null), "empty comment still calls approve with {name, comment}"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.special_bonus."/.test(JS), "uses SpecialBonus whitelisted API");
  ok(/#ec-spbn-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  console.log(fails === 0 ? "\nALL SPECIAL BONUS PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
