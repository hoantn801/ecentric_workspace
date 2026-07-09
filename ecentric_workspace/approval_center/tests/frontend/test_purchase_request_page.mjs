// Headless tests for the Purchase Request page (Node + jsdom).
// Multi-level (4 levels: Direct Manager -> Finance -> HOF -> CEO), no fulfillment, comment optional on approve,
// auto-generated title, required attachment upload.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "purchase_request.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-purchase-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = {
  departments: [ { value: "Engineering", label: "Engineering" }, { value: "Service", label: "Service" } ],
  payment_terms: ["Pay in advance 100%", "Pay within 7 days", "Pay within 14 days", "Pay within 30 days", "Other"],
  supplier_types: ["Existing supplier", "New supplier"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-PURR-2026-00001", request_title: "Purchase Request - Engineering - 5000000",
      department: "Engineering", justification: "Need laptops", purchase_details: "Dell XPS x2",
      payment_amount: 5000000, payment_term: "Pay within 30 days", supplier_type: "Existing supplier",
      supplier_name: "Dell Vietnam", new_supplier_information: "", additional_notes_comments: "12-month warranty",
      estimated_purchase_date: "2026-09-01", estimated_delivery_date: "2026-09-15", requested_by: "u@x" },
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
    { runScripts: "outside-only", url: "https://x.test/approvals/purchase-request?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "Engineering", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-PURR-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-PURR-2026-00001", request_title: "Purchase Request - Engineering - 5000000", department: "Engineering",
        payment_amount: 5000000, payment_term: "Pay within 30 days", approval_status: "Pending", current_level: 1,
        current_level_name: "Direct Manager Review", total_levels: 4, modified: "2026-07-06 09:00",
        creation: "2026-07-06 09:00", requested_at: "2026-07-06 09:00", requester_name: "Emp Requester A" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-PURR-2026-00001", request_title: "Purchase Request - Engineering - 5000000", requested_by: "u@x",
        department: "Engineering", payment_amount: 5000000, payment_term: "Pay within 30 days",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 4, my_status: "Pending",
        creation: "2026-07-05 08:30", requested_at: "2026-07-05 08:30", requester_name: "Emp Requester A" } ] : [
      { name: "EC-PURR-2026-00002", request_title: "Old", requested_by: "u@x", department: "Service",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 4, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  // shell / branding
  ok(!!w.document.querySelector(".ec-sidebar"), "ec-sidebar present");
  ok(/Approval Center/.test(w.document.querySelector(".topbar").textContent), "Approval Center header present");
  ok(!/Powered by ERPNext/i.test(HTML), "Powered by ERPNext NOT in markup");
  ok(/\.web-footer[^{]*\{[^}]*display:none/.test(HTML), "web-footer hidden via CSS");
  ok(!!w.PurchaseRequest, "window.PurchaseRequest exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered");
  { const tt = w.document.getElementById("purr-tabs").textContent;
    ok(/Tạo yêu cầu/.test(tt) && /Yêu cầu của tôi/.test(tt) && /Cần tôi duyệt/.test(tt), "tab labels present"); }
  const cb = () => w.document.getElementById("purr-body").innerHTML;
  // create fields render
  ["department", "justification", "purchase_details", "payment_amount", "payment_term", "supplier_type",
   "supplier_name", "additional_notes_comments", "estimated_purchase_date", "estimated_delivery_date"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "request_attachment file input renders");
  ok(/Bắt buộc/.test(cb()), "attachment helper 'Bắt buộc' shown");
  ok(/Please input item description, unit, quantity, and unit price\./.test(cb()), "purchase_details helper shown");
  ok(!!w.document.querySelector('[data-model="payment_amount"]'), "[data-model=payment_amount] present");
  // Department must be a SELECT (not free-text input) + options render
  ok(!!w.document.querySelector('select[data-model="department"]') && !w.document.querySelector('input[data-model="department"]'), "Department is a select (not free-text)");
  { const dsel = w.document.querySelector('select[data-model="department"]'); const html = dsel ? dsel.innerHTML : "";
    ok(/Engineering/.test(html) && /Service/.test(html), "Department options render from master"); }
  // payment_term options render
  { const psel = w.document.querySelector('select[data-model="payment_term"]');
    ok(psel && /Pay within 30 days/.test(psel.innerHTML) && /Other/.test(psel.innerHTML), "payment_term options render"); }
  // conditional fields hidden initially, appear on model change (re-render pattern)
  ok(!w.document.querySelector('[data-model="payment_term_other"]'), "payment_term_other hidden when not Other");
  ok(!w.document.querySelector('[data-model="new_supplier_information"]'), "new_supplier_information hidden when not New supplier");
  { const ps = w.document.querySelector('select[data-model="payment_term"]'); ps.value = "Other";
    ps.dispatchEvent(new w.Event("input", { bubbles: true })); }
  ok(!!w.document.querySelector('[data-model="payment_term_other"]'), "payment_term_other appears when payment_term=Other");
  { const ss = w.document.querySelector('select[data-model="supplier_type"]'); ss.value = "New supplier";
    ss.dispatchEvent(new w.Event("input", { bubbles: true })); }
  ok(!!w.document.querySelector('[data-model="new_supplier_information"]'), "new_supplier_information appears when supplier_type=New supplier");
  // process preview: 5 steps, named, no SLA
  ok(!!w.document.getElementById("purr-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("purr-process-preview");
    ok(pv.querySelectorAll(".step").length === 5, "preview has 5 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Direct Manager review/.test(pv.innerHTML) && /Finance review/.test(pv.innerHTML) && /HOF review/.test(pv.innerHTML) && /CEO review/.test(pv.innerHTML), "preview steps Tạo/Direct Manager/Finance/HOF/CEO");
    ok(!/SLA|giờ|ngày làm việc/.test(pv.innerHTML), "preview has no SLA text"); }
  // validateSubmit — required set
  w = boot(); await flush(); await flush();
  w.PurchaseRequest.state.draft = {};
  { const e = w.PurchaseRequest.validateSubmit() || {};
    ok(e.department && e.justification && e.purchase_details && e.payment_amount && e.payment_term && e.supplier_type && e.supplier_name && e.additional_notes_comments && e.estimated_purchase_date && e.estimated_delivery_date && e.request_attachment, "validateSubmit requires the full set"); }
  const base = () => ({ department: "Engineering", justification: "j", purchase_details: "pd", payment_amount: 5000000,
    payment_term: "Pay within 30 days", supplier_type: "Existing supplier", supplier_name: "Dell",
    additional_notes_comments: "warranty", estimated_purchase_date: "2026-09-01", estimated_delivery_date: "2026-09-15",
    request_attachment: "/files/quote.pdf" });
  // invalid department
  { const d = base(); d.department = "NOPE"; w.PurchaseRequest.state.draft = d;
    ok((w.PurchaseRequest.validateSubmit() || {}).department, "invalid department (not in master) blocked"); }
  // payment_amount must be > 0
  { const d = base(); d.payment_amount = 0; w.PurchaseRequest.state.draft = d;
    ok((w.PurchaseRequest.validateSubmit() || {}).payment_amount, "payment_amount <= 0 blocked"); }
  // delivery before purchase date
  { const d = base(); d.estimated_delivery_date = "2026-08-01"; w.PurchaseRequest.state.draft = d;
    ok((w.PurchaseRequest.validateSubmit() || {}).estimated_delivery_date, "delivery before purchase date blocked"); }
  // attachment required
  { const d = base(); d.request_attachment = ""; w.PurchaseRequest.state.draft = d;
    ok((w.PurchaseRequest.validateSubmit() || {}).request_attachment, "attachment required"); }
  // payment_term_other required when Other
  { const d = base(); d.payment_term = "Other"; d.payment_term_other = ""; w.PurchaseRequest.state.draft = d;
    ok((w.PurchaseRequest.validateSubmit() || {}).payment_term_other, "payment_term_other required when Other"); }
  // full valid draft passes
  { w.PurchaseRequest.state.draft = base();
    ok(w.PurchaseRequest.validateSubmit() === null, "valid full draft passes"); }
  // auto-title
  ok(w.PurchaseRequest.computeTitle({ department: "Engineering", payment_amount: 5000000 }) === "Purchase Request - Engineering - 5000000", "computeTitle auto-generates title");
  // save_draft payload
  w = boot(); await flush(); await flush();
  w.PurchaseRequest.state.draft = base();
  w.document.getElementById("purr-save").click(); await flush(); await flush();
  ok(calls.save_draft && /"department":"Engineering"/.test(calls.save_draft.payload), "save_draft payload carries exact department name");
  ok(calls.save_draft && /purchase_details/.test(calls.save_draft.payload), "save_draft payload carries purchase_details");
  // submit path calls submit_request with draft name
  w = boot(); await flush(); await flush();
  w.PurchaseRequest.state.draft = base();
  w.document.getElementById("purr-submit").click(); await flush(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-PURR-2026-00001", "submit_request called with draft name");
  // My Requests list columns
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/purchase-request?tab=my-requests"); w.PurchaseRequest.route(); await flush(); await flush();
  { const ths = w.document.querySelectorAll("#purr-body table.tbl thead th");
    ok(ths.length > 0 && ths[0].textContent.trim() === "Ngày request", "My Requests first column is Ngày request");
    ok(Array.prototype.some.call(ths, function (t) { return t.textContent.trim() === "Người request"; }), "My Requests has Người request column");
    ok(Array.prototype.some.call(ths, function (t) { return t.textContent.trim() === "Phòng ban"; }), "My Requests has Phòng ban column");
    ok(Array.prototype.some.call(ths, function (t) { return t.textContent.trim() === "Số tiền"; }), "My Requests has Số tiền column");
    ok(Array.prototype.some.call(ths, function (t) { return t.textContent.trim() === "Điều khoản"; }), "My Requests has Điều khoản column");
    ok(/06\/07\/2026 09:00/.test(cb()), "My Requests row shows dd/MM/yyyy HH:mm date");
    ok(/Emp Requester A/.test(cb()), "My Requests row shows requester name"); }
  // detail runtime stepper + title
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/purchase-request?id=EC-PURR-2026-00001"); w.PurchaseRequest.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper, no not-found");
  ok(!!calls.get_detail, "detail loads via api.purchase_request.get_detail");
  ok(/Purchase Request - Engineering - 5000000/.test(cb()), "detail shows request title");
  { const rh = w.PurchaseRequest.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Direct Manager Review/.test(rh) && /Finance Review/.test(rh) && /HOF Review/.test(rh) && /CEO Review/.test(rh), "runtime stepper shows the 4 level names"); }
  // APPROVE modal does NOT force a comment
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/purchase-request?id=EC-PURR-2026-00001"); w.PurchaseRequest.route(); await flush(); await flush();
  { delete calls.approve;
    w.PurchaseRequest.doApprove("EC-PURR-2026-00001", detail());
    const ov = w.document.querySelector(".ec-purr-overlay");
    ok(!!ov, "approve modal opened");
    const body = ov.querySelector(".ec-purr-modal-b").innerHTML;
    ok(!/class="req"/.test(body), "approve modal comment is NOT marked required");
    // confirming with empty comment SHOULD still call approve
    ov.querySelector("#m-cmt").value = "";
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(calls.approve && calls.approve.name === "EC-PURR-2026-00001", "empty comment still calls approve (comment optional)"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.purchase_request."/.test(JS), "uses PurchaseRequest whitelisted API");
  ok(/#ec-purr-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  console.log(fails === 0 ? "\nALL PURCHASE REQUEST PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
