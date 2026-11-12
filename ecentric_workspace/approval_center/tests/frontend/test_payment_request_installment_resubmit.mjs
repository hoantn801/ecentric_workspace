// Hoi quy 12/11/2026 (EC-PAYR-2026-00652): "Bo sung & gui lai" dot 2 phai biet dot 1 da de nghi bao
// nhieu (extra.installments) - truoc day startEditResubmit bo qua, form tuong da tra 0d -> doi nhap
// dot 3 va chan gui. Node + jsdom: node test_payment_request_installment_resubmit.mjs
import { JSDOM } from "jsdom";
import { pageSource } from "./_page_source.mjs";
const HTML = pageSource("payment_request");
const [markup, rest] = HTML.split('<script id="ec-payment-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const D2 = { name: "EC-PAYR-2026-00652", payment_mode: "Installment", installment_no: 2, installment_of: "EC-PAYR-2026-00646",
  total_amount: 220208000, payment_amount: 170208000, payment_date: "2026-11-11", next_installment_amount: 0,
  next_installment_date: null, reason: "Dot 2", payee_full_name: "Ngoi Sao", account_bank: "ACB", bank_account_number: "166566866",
  has_purchase_request: "No", no_purchase_request_reason: "x", is_cost_valid: "Yes", details_and_attachments_correct: "Yes",
  request_attachment: "/files/a.pdf", requested_by: "u@x" };
function det(business) {
  return { business, approval: { name: "AR-2", approval_status: "Information Required", current_level: 2, information_requested_from_level: 2 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review" }, { level_no: 2, level_name: "Finance Review" }],
    approvers: [{ level_no: 2, approver: "fin@x", status: "Information Requested", comment: "bo sung" }],
    attachments: [], timeline: [], process_preview: [], capabilities: { can_edit: true, can_resubmit: true },
    extra: { installments: { root: "EC-PAYR-2026-00646", installment_no: 2, total: 220208000, remaining_after_this: 0,
      chain: [{ name: "EC-PAYR-2026-00646", installment_no: 1, payment_amount: 50000000, approval_status: "Approved", is_current: false },
              { name: "EC-PAYR-2026-00652", installment_no: 2, payment_amount: 170208000, approval_status: "Information Required", is_current: true }] } } };
}
function boot() {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/payment-request?id=EC-PAYR-2026-00652" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "Service", company: "C" }, is_system_manager: false,
      form_options: { yes_no: ["Yes", "No"] } } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: det(Object.assign({}, D2)) });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  for (const how of ["startEditResubmit", "startEditDraft"]) {
    const w = boot(); await flush(); await flush();
    w.PaymentRequest[how](det(Object.assign({}, D2))); await flush(); await flush();
    const plan = w.document.getElementById("payr-inst-plan");
    ok(!!plan, how + ": co khoi Ke hoach chia dot");
    const txt = plan ? plan.textContent : "";
    const sum = w.document.querySelector('#payr-inst-plan input.ro[readonly]:not([data-model])');
    ok(sum && /50\.000\.000đ \/ 0đ/.test(sum.value), how + ": dot truoc 50.000.000d / con lai 0d (thay: " + (sum && sum.value) + ")");
    ok(!/đợt 3/i.test(txt), how + ": khong doi nhap dot 3");
    ok(/đợt cuối/.test(txt), how + ": bao day la dot cuoi");
    ok(Number(w.PaymentRequest.state.draft._paid_before) === 50000000, how + ": _paid_before = 50.000.000");
  }
  console.log(fails ? "\n" + fails + " FAIL" : "\nTAT CA DAT");
  process.exit(fails ? 1 : 0);
}
run();
