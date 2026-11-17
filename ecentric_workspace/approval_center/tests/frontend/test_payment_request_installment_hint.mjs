// Canh bao "ghi dot 1 / 50% nhung chon Thanh toan 100%" (17/11/2026). Node + jsdom:
//   node test_payment_request_installment_hint.mjs
import { JSDOM } from "jsdom";
import { pageSource } from "./_page_source.mjs";
const HTML = pageSource("payment_request");
const [markup, rest] = HTML.split('<script id="ec-payment-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 15));
let calls = [];
const FO = { yes_no: ["Yes", "No"] };
function detail(biz, status) {
  return { business: Object.assign({ name: "EC-PAYR-2026-00900", requested_by: "u@x" }, biz),
    approval: status ? { name: "AR-9", approval_status: status, current_level: 2, information_requested_from_level: 2 } : null,
    levels: [{ level_no: 1, level_name: "Direct Manager Review" }, { level_no: 2, level_name: "Finance Review" }],
    approvers: status ? [{ level_no: 2, approver: "fin@x", status: "Information Requested", comment: "bo sung" }] : [],
    attachments: [], timeline: [], process_preview: [],
    capabilities: status ? { can_edit: true, can_resubmit: true } : { can_submit: true, can_edit: true } };
}
function boot(url, det) {
  calls = [];
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>', { runScripts: "outside-only", url });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => { const m = o.method.split(".").pop(); calls.push(m);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "Service", company: "C" }, is_system_manager: false, form_options: FO } });
    if (m === "save_draft") return Promise.resolve({ message: { name: "EC-PAYR-2026-00900", capabilities: {} } });
    if (m === "submit_request") return Promise.resolve({ message: { approval_request: "AR-1", submitted: true } });
    if (m === "resubmit") return Promise.resolve({ message: { ok: true } });
    if (m === "get_detail") return Promise.resolve({ message: det || detail({}) });
    return Promise.resolve({ message: { rows: [], total: 0 } }); } };
  w.eval(JS);
  return w;
}
const VALID = { reason: "Thanh toán hợp đồng KOL đợt 1 - booking", request_title: "HĐ KOL", payment_amount: 270000000, payment_date: "2026-11-20",
  payee_full_name: "DMG", account_bank: "Techcombank", bank_account_number: "8885113688", has_purchase_request: "No",
  no_purchase_request_reason: "HĐ dịch vụ", is_cost_valid: "Yes", details_and_attachments_correct: "Yes",
  request_attachment: "/files/a.pdf", payment_mode: "Full", ec_vat_pct: "8", ec_ky_chi_phi: "2026-11-20", ec_loai_chi_phi: "OTHER" };
const modalEl = w => w.document.querySelector(".ec-payr-overlay");
async function run() {
  // 1. ham nhan dien
  let w = boot("https://x.test/approvals/payment-request?tab=create"); await flush(); await flush();
  const H = w.PaymentRequest.installmentHint;
  ok(H({ reason: "Thanh toán HĐ đợt 1 - booking KOL" }) === "đợt 1", "bat 'đợt 1'");
  ok(H({ request_title: "Thanh toán 50% hợp đồng" }) === "50%", "bat '50%'");
  ok(H({ reason: "đặt cọc" }) === "đặt cọc", "bat 'đặt cọc'");
  ok(H({ reason: "thanh toán đợt 1", payment_mode: "Installment" }) === "", "da chon chia dot -> khong hoi");
  ok(H({ reason: "đợt 2 của HĐ" }) === "" && H({ reason: "Lần 5 thuê GPU" }) === "" && H({ reason: "lần 10" }) === "", "khong bat đợt 2 / lần 5 / lần 10");
  ok(H({ reason: "Tạm ứng chi phí" }) === "" && H({ reason: "plan item" }) === "" && H({ reason: "150%" }) === "", "khong bat tạm ứng / plan item / 150%");
  ok(H({ reason: "đợt 1", installment_of: "EC-PAYR-1" }) === "", "phieu dot sau trong chuoi -> khong hoi");

  // 2. Gui nhap tu man chi tiet (duong gui chinh): hoi; "Sua phieu" -> mo form sua, tu chuyen sang Chia nhieu dot, khong gui
  const d2 = detail(Object.assign({}, VALID), null);
  w = boot("https://x.test/approvals/payment-request?id=EC-PAYR-2026-00900", d2); await flush(); await flush(); await flush();
  let sb = w.document.querySelector('[data-act="submitdraft"]');
  ok(!!sb, "man chi tiet nhap co nut Gui yeu cau");
  sb.click(); await flush();
  ok(!!modalEl(w), "Gui nhap -> hien hop hoi");
  ok(!calls.includes("submit_request"), "chua gui khi dang hoi");
  ok(/đợt 1/.test(modalEl(w).textContent) && /Chia nhiều đợt/.test(modalEl(w).textContent), "hop neu ro chu da bat + cach chon chia dot");
  ok(/Sửa phiếu/.test(modalEl(w).querySelector("[data-inst-switch]").textContent), "nut chuyen = Sua phieu");
  modalEl(w).querySelector("[data-inst-switch]").click(); await flush(); await flush(); await flush(); await flush();
  ok(!modalEl(w), "dong hop sau khi chon chuyen");
  ok(!calls.includes("submit_request"), "chon Sua phieu -> KHONG gui");
  ok(w.PaymentRequest.state.mode === "create" && w.PaymentRequest.state.draft.payment_mode === "Installment", "mo form sua nhap, da chuyen Installment");
  ok(!!w.document.querySelector('#ec-payr-root [data-model="total_amount"]'), "hien o Tong gia tri");

  // 3. Van gui 100% -> gui binh thuong
  const d3 = detail(Object.assign({}, VALID), null);
  w = boot("https://x.test/approvals/payment-request?id=EC-PAYR-2026-00900", d3); await flush(); await flush(); await flush();
  w.document.querySelector('[data-act="submitdraft"]').click(); await flush();
  modalEl(w).querySelector("[data-ok]").click(); await flush(); await flush();
  ok(calls.includes("submit_request"), "Van gui 100% -> submit_request");
  ok(!modalEl(w), "khong con hop hoi");

  // 4. ly do thuong -> khong hoi
  const d4 = detail(Object.assign({}, VALID, { reason: "Thanh toán dịch vụ tháng 11" }), null);
  w = boot("https://x.test/approvals/payment-request?id=EC-PAYR-2026-00900", d4); await flush(); await flush(); await flush();
  w.document.querySelector('[data-act="submitdraft"]').click(); await flush(); await flush();
  ok(!modalEl(w) && calls.includes("submit_request"), "ly do thuong -> gui thang");

  // 5. Bo sung & gui lai: hoi, Van gui -> resubmit
  const d5 = detail(Object.assign({}, VALID), "Information Required");
  w = boot("https://x.test/approvals/payment-request?id=EC-PAYR-2026-00900", d5); await flush(); await flush();
  w.PaymentRequest.startEditResubmit(d5); await flush();
  w.document.getElementById("payr-resubmit").click(); await flush();
  ok(!!modalEl(w) && !calls.includes("resubmit"), "gui lai -> hoi truoc");
  modalEl(w).querySelector("[data-ok]").click(); await flush(); await flush();
  ok(calls.includes("resubmit"), "Van gui 100% -> resubmit");

  console.log(fails ? "\n" + fails + " FAIL" : "\nTAT CA DAT");
  process.exit(fails ? 1 : 0);
}
run();
