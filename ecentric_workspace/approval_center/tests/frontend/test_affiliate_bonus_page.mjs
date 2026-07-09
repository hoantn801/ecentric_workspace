// Headless tests for the Affiliate Bonus page (Node + jsdom). Two-level chain (Vinh -> CEO), attachment required.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "affiliate_bonus.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-affiliate-bonus">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = {};
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-AFBN-2026-00001", request_title: "Affiliate Bonus - 2026-09 - 5000000",
      service_month: "2026-09-01", total_amount: 5000000, budget: 20000000, detail: "Minigame + revenue push, 12 KOCs",
      requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Vinh Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "CEO Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "vinh@x", status: "Pending" },
                { level_no: 2, approver: "ceo@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/affiliate-bonus-request?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-AFBN-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-AFBN-2026-00001", request_title: "Affiliate Bonus - 2026-09 - 5000000", service_month: "2026-09-01",
        total_amount: 5000000, budget: 20000000, approval_status: "Pending", current_level: 1,
        current_level_name: "Vinh Review", total_levels: 2, requester_name: "U",
        creation: "2026-07-06 09:00", requested_at: "2026-07-06 09:00", modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-AFBN-2026-00001", request_title: "Affiliate Bonus - 2026-09 - 5000000", requested_by: "u@x",
        requester_name: "U", service_month: "2026-09-01", total_amount: 5000000, budget: 20000000,
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 2, my_status: "Pending",
        creation: "2026-07-06 09:00", requested_at: "2026-07-06 09:00" } ] : [
      { name: "EC-AFBN-2026-00002", request_title: "Affiliate Bonus - 2026-08 - 3000000", requested_by: "u@x",
        requester_name: "U", service_month: "2026-08-01", total_amount: 3000000, budget: 10000000,
        approval_status: "Approved", current_level: 0, level_no: 2, total_levels: 2, my_status: "Approved",
        creation: "2026-06-30 09:00", requested_at: "2026-06-30 09:00" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();

  // shell + branding
  ok(!!w.document.querySelector(".ec-sidebar"), "eCentric shell sidebar present");
  ok(/Approval Center/.test(w.document.querySelector(".topbar").innerHTML), "Approval Center header present");
  ok(/eCentric/.test(markup), "eCentric brand present");
  ok(!/Powered by ERPNext/i.test(HTML), "no Powered by ERPNext");

  ok(!!w.AffiliateBonus, "window.AffiliateBonus exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered");
  { const tabs = w.document.querySelector("#afbn-tabs").innerHTML;
    ok(/Tạo mới/.test(tabs) && /Yêu cầu của tôi/.test(tabs) && /Cần tôi duyệt/.test(tabs), "tab labels correct"); }

  // create fields render
  ["service_month", "total_amount", "budget", "detail"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders");
  ok(!w.document.querySelector('[data-model="request_title"]'), "NO request_title input");

  // process preview 3 steps, no SLA
  { const pv = w.document.getElementById("afbn-process-preview");
    ok(!!pv, "process preview renders");
    ok(pv.querySelectorAll(".step").length === 3, "preview has 3 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Vinh Review/i.test(pv.innerHTML) && /CEO Review/i.test(pv.innerHTML), "preview steps Tạo yêu cầu / Vinh review / CEO review");
    ok(!/SLA|Hạn:|Quá hạn/.test(pv.innerHTML), "no SLA in preview"); }

  // validateSubmit
  w.AffiliateBonus.state.draft = {};
  { const e = w.AffiliateBonus.validateSubmit() || {};
    ok(e.service_month && e.total_amount && e.budget && e.detail && e.request_attachment, "validateSubmit requires full set incl attachment"); }
  w.AffiliateBonus.state.draft = { service_month: "2026-09-15", total_amount: 5000000, budget: 20000000, detail: "x", request_attachment: "/files/a.pdf" };
  ok((w.AffiliateBonus.validateSubmit() || {}).service_month, "rejects service_month not day 1");
  w.AffiliateBonus.state.draft = { service_month: "2026-09-01", total_amount: 0, budget: 20000000, detail: "x", request_attachment: "/files/a.pdf" };
  ok((w.AffiliateBonus.validateSubmit() || {}).total_amount, "rejects total_amount 0");
  w.AffiliateBonus.state.draft = { service_month: "2026-09-01", total_amount: 5000000, budget: -1, detail: "x", request_attachment: "/files/a.pdf" };
  ok((w.AffiliateBonus.validateSubmit() || {}).budget, "rejects budget -1");
  w.AffiliateBonus.state.draft = { service_month: "2026-09-01", total_amount: 5000000, budget: 20000000, detail: "x" };
  ok((w.AffiliateBonus.validateSubmit() || {}).request_attachment, "requires attachment");
  w.AffiliateBonus.state.draft = { service_month: "2026-09-01", total_amount: 5000000, budget: 20000000, detail: "Minigame", request_attachment: "/files/a.pdf" };
  ok(w.AffiliateBonus.validateSubmit() === null, "valid draft passes");

  // title preview in summary
  w.AffiliateBonus.render();
  { const sm = w.document.getElementById("afbn-summary");
    ok(/Affiliate Bonus - 2026-09 - 5000000/.test(sm.innerHTML), "title preview in summary");
    ok(/Vinh Review → CEO Review/.test(sm.innerHTML), "summary flow Vinh -> CEO"); }
  ok(w.AffiliateBonus.computedTitle({ service_month: "2026-09-01", total_amount: 5000000 }) === "Affiliate Bonus - 2026-09 - 5000000", "computedTitle format");

  // save draft carries fields
  w.document.getElementById("afbn-save").click(); await flush(); await flush();
  ok(calls.save_draft && /service_month/.test(calls.save_draft.payload) && /total_amount/.test(calls.save_draft.payload) && /budget/.test(calls.save_draft.payload), "save_draft payload carries fields");

  // My Requests: first header + requester + formatted date
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/affiliate-bonus-request?tab=my-requests"); w.AffiliateBonus.route(); await flush(); await flush();
  { const list = w.document.getElementById("afbn-list").innerHTML;
    const ths = Array.prototype.map.call(w.document.querySelectorAll("#afbn-list th"), function (x) { return x.textContent; });
    ok(ths[0] === "Ngày request", "My Requests first header is Ngày request");
    ok(ths.indexOf("Người request") >= 0, "My Requests has Người request column");
    ok(ths.indexOf("Tháng DV") >= 0 && ths.indexOf("Tổng tiền") >= 0 && ths.indexOf("Ngân sách") >= 0, "My Requests has Tháng DV/Tổng tiền/Ngân sách columns");
    ok(/06\/07\/2026/.test(list), "My Requests shows formatted date");
    ok(/EC-AFBN-2026-00001/.test(list), "My Requests shows request code"); }

  // Need My Approval processed
  w.history.pushState({}, "", "/approvals/affiliate-bonus-request?tab=my-approvals"); w.AffiliateBonus.route(); await flush(); await flush();
  { const done = w.document.getElementById("ap-done").innerHTML; ok(/Đã duyệt/.test(done), "processed list shows status"); }

  // detail via get_detail shows title, two-level runtime stepper
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/affiliate-bonus-request?id=EC-AFBN-2026-00001"); w.AffiliateBonus.route(); await flush(); await flush();
  { const cb = w.document.getElementById("afbn-body").innerHTML;
    ok(/Affiliate Bonus - 2026-09 - 5000000/.test(cb) && !/Không tải được yêu cầu/.test(cb), "detail via get_detail shows title");
    ok(calls.get_detail, "detail calls api.affiliate_bonus.get_detail"); }
  { const rh = w.AffiliateBonus.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Vinh Review/.test(rh) && /CEO Review/.test(rh) && /Hoàn tất/.test(rh), "runtime stepper two-level (Vinh + CEO)"); }

  // approve modal optional comment
  { w.AffiliateBonus.doApprove("EC-AFBN-2026-00001", detail());
    const ov = w.document.querySelector(".ec-afbn-overlay");
    ok(!!ov && /không bắt buộc/i.test(ov.innerHTML), "approve modal comment optional");
    const x = ov.querySelector("[data-x]"); if (x) x.click(); }

  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.affiliate_bonus."/.test(JS), "uses Affiliate Bonus whitelisted API NS");
  ok(/#ec-afbn-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width CSS");

  console.log(fails === 0 ? "\nALL AFFILIATE BONUS PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
