// Headless tests for the Payment Request page (Node + jsdom). Multi-level (4 levels:
// Direct Manager -> Finance -> HOF -> CEO), no fulfillment, attachment REQUIRED, comments OPTIONAL on approve.
// has_purchase_request toggles purchase_request (Approved PRs) vs no_purchase_request_reason.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "payment_request.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-payment-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = { yes_no: ["Yes", "No"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-PAYR-2026-00001", request_title: "Payment Request - Nguyen Van A - 5000000",
      payee_full_name: "Nguyen Van A", payment_amount: 5000000, payment_date: "2026-08-01",
      account_bank: "Vietcombank", bank_account_number: "0123456789", reason: "Thanh toan dich vu",
      has_purchase_request: "No", no_purchase_request_reason: "Mua nho le", is_cost_valid: "Yes",
      details_and_attachments_correct: "Yes", department: "Service", requested_by: "u@x" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "Finance Review", approval_mode: "Any One", level_status: "Pending" },
             { level_no: 3, level_name: "HOF Review", approval_mode: "Any One", level_status: "Pending" },
             { level_no: 4, level_name: "CEO Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "tuan.ly@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/payment-request?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "Service", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("list_approved_purchase_requests")) return Promise.resolve({ message: { rows: [
      { value: "EC-PURR-2026-00001", label: "PR one" } ] } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-PAYR-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-PAYR-2026-00001", request_title: "Payment Request - Nguyen Van A - 5000000", payee_full_name: "Nguyen Van A",
        payment_amount: 5000000, payment_date: "2026-08-01", approval_status: "Pending", current_level: 1,
        current_level_name: "Direct Manager Review", total_levels: 4, modified: "2026-07-06 09:00",
        creation: "2026-07-06 09:00", requested_at: "2026-07-06 09:00", requester_name: "Emp Requester A" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-PAYR-2026-00001", request_title: "Payment Request - Nguyen Van A - 5000000", requested_by: "u@x",
        payee_full_name: "Nguyen Van A", payment_amount: 5000000, payment_date: "2026-08-01",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 4, my_status: "Pending",
        creation: "2026-07-05 08:30", requested_at: "2026-07-05 08:30", requester_name: "Emp Requester A" } ] : [
      { name: "EC-PAYR-2026-00002", request_title: "Old", requested_by: "u@x", payee_full_name: "B",
        payment_amount: 10, approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 4, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
const validDraft = () => ({ reason: "Thanh toan", payment_amount: 5000000, payment_date: "2026-08-01",
  payee_full_name: "Nguyen Van A", account_bank: "VCB", bank_account_number: "0123456789",
  has_purchase_request: "No", no_purchase_request_reason: "Mua nho le", is_cost_valid: "Yes",
  details_and_attachments_correct: "Yes", request_attachment: "/files/proof.pdf" });

async function run() {
  let w = boot(); await flush(); await flush();
  const cb = () => w.document.getElementById("payr-body").innerHTML;
  // shell + header
  ok(!!w.document.querySelector(".ec-sidebar"), "eCentric sidebar (.ec-sidebar) present");
  ok(/Approval Center/.test(w.document.querySelector(".topbar").textContent), "topbar has Approval Center breadcrumb");
  ok(/eCentric/.test(w.document.querySelector(".brand-name").textContent), "eCentric brand shown");
  ok(!/Powered by ERPNext/i.test(HTML), "no 'Powered by ERPNext' in page");
  ok(!!w.PaymentRequest, "window.PaymentRequest exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  { const tt = Array.prototype.map.call(w.document.querySelectorAll(".tab"), t => t.textContent.trim());
    ok(tt[0] === "Tạo mới" && tt[1] === "Yêu cầu của tôi" && tt[2] === "Cần tôi duyệt", "tabs Tạo mới | Yêu cầu của tôi | Cần tôi duyệt"); }
  // create fields
  ok(!!w.document.querySelector('[data-model="payee_full_name"]'), "payee_full_name field renders");
  ok(!!w.document.querySelector('[data-model="has_purchase_request"]'), "has_purchase_request field renders");
  ["reason", "payment_amount", "payment_date", "account_bank", "bank_account_number", "is_cost_valid", "details_and_attachments_correct"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "request_attachment file upload renders");
  ok(/Bắt buộc/.test(cb()), "attachment helper 'Bắt buộc' shown");
  ok(!w.document.querySelector('[data-model="request_title"]'), "NO request_title input rendered");
  // process preview: 5 steps, before payee field, no SLA
  ok(!!w.document.getElementById("payr-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("payr-process-preview");
    ok(pv.querySelectorAll(".step").length === 5, "preview has 5 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Direct Manager review/.test(pv.innerHTML) && /Finance review/.test(pv.innerHTML) && /HOF review/.test(pv.innerHTML) && /CEO review/.test(pv.innerHTML), "preview steps Tạo/Direct Manager/Finance/HOF/CEO");
    ok(!/SLA|giờ|ngày làm việc/.test(pv.innerHTML), "preview has no SLA text"); }
  { const html = cb(); ok(html.indexOf('id="payr-process-preview"') >= 0 && html.indexOf('id="payr-process-preview"') < html.indexOf('data-model="payee_full_name"'), "process preview before payment fields"); }
  // conditional re-render: set has_purchase_request to "No"
  { const sel = w.document.querySelector('[data-model="has_purchase_request"]');
    sel.value = "No"; sel.dispatchEvent(new w.Event("change")); }
  await flush();
  ok(!!w.document.querySelector('[data-model="no_purchase_request_reason"]'), "No -> no_purchase_request_reason field shown");
  ok(!w.document.querySelector('[data-model="purchase_request"]'), "No -> purchase_request hidden");
  { const f = w.document.querySelector('[data-fld="no_purchase_request_reason"]');
    ok(!!f && /class="req"/.test(f.innerHTML), "no_purchase_request_reason marked required"); }
  // set has_purchase_request to "Yes" -> loads PR options + requires purchase_request
  { const sel = w.document.querySelector('[data-model="has_purchase_request"]');
    sel.value = "Yes"; sel.dispatchEvent(new w.Event("change")); }
  await flush(); await flush();
  ok(!!calls.list_approved_purchase_requests, "Yes -> list_approved_purchase_requests called");
  ok(!!w.document.querySelector('[data-model="purchase_request"]'), "Yes -> purchase_request field shown");
  ok(!w.document.querySelector('[data-model="no_purchase_request_reason"]'), "Yes -> no_purchase_request_reason hidden");
  { const prsel = w.document.querySelector('[data-model="purchase_request"]');
    ok(prsel && /EC-PURR-2026-00001/.test(prsel.innerHTML) && /PR one/.test(prsel.innerHTML), "purchase_request options populated from Approved PRs"); }
  // validateSubmit conditional
  w.PaymentRequest.state.draft = Object.assign(validDraft(), { has_purchase_request: "Yes", purchase_request: "", no_purchase_request_reason: "" });
  ok((w.PaymentRequest.validateSubmit() || {}).purchase_request, "Yes requires purchase_request");
  w.PaymentRequest.state.draft = Object.assign(validDraft(), { has_purchase_request: "No", no_purchase_request_reason: "" });
  ok((w.PaymentRequest.validateSubmit() || {}).no_purchase_request_reason, "No requires no_purchase_request_reason");
  // details_and_attachments_correct must be Yes
  w.PaymentRequest.state.draft = Object.assign(validDraft(), { details_and_attachments_correct: "No" });
  ok((w.PaymentRequest.validateSubmit() || {}).details_and_attachments_correct, "details_and_attachments_correct=No blocks submit");
  // required set + attachment + amount>0
  w.PaymentRequest.state.draft = {};
  { const e = w.PaymentRequest.validateSubmit() || {};
    ok(e.reason && e.payment_amount && e.payment_date && e.payee_full_name && e.account_bank && e.bank_account_number && e.has_purchase_request && e.is_cost_valid && e.details_and_attachments_correct && e.request_attachment, "validateSubmit requires full mandatory set + attachment"); }
  w.PaymentRequest.state.draft = Object.assign(validDraft(), { payment_amount: 0 });
  ok((w.PaymentRequest.validateSubmit() || {}).payment_amount, "payment_amount must be > 0");
  w.PaymentRequest.state.draft = Object.assign(validDraft(), { request_attachment: "" });
  ok((w.PaymentRequest.validateSubmit() || {}).request_attachment, "attachment required");
  // full valid draft passes
  w.PaymentRequest.state.draft = validDraft();
  ok(w.PaymentRequest.validateSubmit() === null, "full valid draft (No + reason, details Yes, attachment) passes");
  // suggestTitle format
  ok(w.PaymentRequest.suggestTitle({ payee_full_name: "Nguyen Van A", payment_amount: 5000000 }) === "Payment Request - Nguyen Van A - 5000000", "auto-title format");
  // save_draft carries payee_full_name
  w = boot(); await flush(); await flush();
  w.PaymentRequest.state.draft = validDraft();
  w.document.getElementById("payr-save").click(); await flush(); await flush();
  ok(calls.save_draft && /payee_full_name/.test(calls.save_draft.payload) && /Nguyen Van A/.test(calls.save_draft.payload), "save_draft payload carries payee_full_name");
  // submit path calls submit_request with draft name
  w = boot(); await flush(); await flush();
  w.PaymentRequest.state.draft = validDraft();
  w.document.getElementById("payr-submit").click(); await flush(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-PAYR-2026-00001", "submit_request called with draft name");
  // My Requests columns
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/payment-request?tab=my-requests"); w.PaymentRequest.route(); await flush(); await flush();
  { const ths = w.document.querySelectorAll("#payr-body table.tbl thead th");
    ok(ths.length > 0 && ths[0].textContent.trim() === "Ngày request", "My Requests first column is Ngày request");
    ok(Array.prototype.some.call(ths, t => t.textContent.trim() === "Người request"), "My Requests has Người request column");
    ok(Array.prototype.some.call(ths, t => t.textContent.trim() === "Người nhận"), "My Requests has Người nhận column");
    ok(/06\/07\/2026 09:00/.test(cb()), "My Requests row shows dd/MM/yyyy HH:mm date");
    ok(/Emp Requester A/.test(cb()) && /Nguyen Van A/.test(cb()), "My Requests row shows requester + payee"); }
  // detail runtime stepper via api.payment_request.get_detail
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/payment-request?id=EC-PAYR-2026-00001"); w.PaymentRequest.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper");
  ok(!!calls.get_detail, "detail loads via api.payment_request.get_detail");
  { const rh = w.PaymentRequest.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Direct Manager Review/.test(rh) && /Finance Review/.test(rh) && /HOF Review/.test(rh) && /CEO Review/.test(rh), "runtime stepper shows the 4 level names"); }
  // APPROVE modal: comment OPTIONAL
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/payment-request?id=EC-PAYR-2026-00001"); w.PaymentRequest.route(); await flush(); await flush();
  { delete calls.approve;
    w.PaymentRequest.doApprove("EC-PAYR-2026-00001", detail());
    const ov = w.document.querySelector(".ec-payr-overlay");
    ok(!!ov, "approve modal opened");
    const cmt = ov.querySelector("#m-cmt");
    ok(!!cmt, "approve modal has comment field");
    // confirming with EMPTY comment must still call approve (optional)
    cmt.value = "";
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(calls.approve && calls.approve.name === "EC-PAYR-2026-00001", "empty comment still calls approve (comment optional)"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.payment_request."/.test(JS), "uses Payment Request whitelisted API");
  ok(/#ec-payr-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  console.log(fails === 0 ? "\nALL PAYMENT REQUEST PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
