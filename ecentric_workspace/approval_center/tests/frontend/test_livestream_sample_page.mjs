// Headless tests for the Livestream Sample page (Node + jsdom). Form #8 (3-level, no fulfillment).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "livestream_sample.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-livestream-sample">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = {};
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-LVSM-2026-00001", request_title: "Sample - BrandX", brand: "BrandX",
      sample_detail: "SKU 123 x5", estimated_arrival_time: "2026-08-01", requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Sang Bui Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "sang.bui@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/hr-activity?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-LVSM-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-LVSM-2026-00001", request_title: "Sample BrandX", brand: "BrandX", estimated_arrival_time: "2026-08-01",
        approval_status: "Pending", current_level: 1, current_level_name: "Sang Bui Review", total_levels: 1,
        modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-LVSM-2026-00001", request_title: "Sample BrandX", requested_by: "u@x", brand: "BrandX",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 1, my_status: "Pending" } ] : [
      { name: "EC-LVSM-2026-00002", request_title: "Old", requested_by: "u@x", brand: "BrandY",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 1, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.LivestreamSample, "LivestreamSample exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  const cb = () => w.document.getElementById("lvsm-body").innerHTML;
  ["request_title", "brand", "sample_detail", "estimated_arrival_time"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders");
  ok(!!w.document.getElementById("lvsm-process-preview"), "process preview renders");
  { const pv = w.document.getElementById("lvsm-process-preview");
    ok(pv.querySelectorAll(".step").length === 3, "preview has 3 steps");
    ok(/Sang Bui duyệt/.test(pv.innerHTML), "preview step Sang Bui"); }

  w.LivestreamSample.state.draft = {};
  { const e = w.LivestreamSample.validateSubmit() || {};
    ok(e.brand && e.sample_detail && e.estimated_arrival_time, "validateSubmit requires key fields"); }
  ok(!(w.LivestreamSample.validateSubmit() || {}).request_attachment, "attachment optional (not required)");
  w.LivestreamSample.state.draft = { request_title: "T", brand: "BrandX", sample_detail: "SKU x5", estimated_arrival_time: "2026-08-01" };
  ok(w.LivestreamSample.validateSubmit() === null, "valid form passes (attachment optional)");
  w.document.getElementById("lvsm-save").click(); await flush(); await flush();
  ok(calls.save_draft && /brand/.test(calls.save_draft.payload) && /sample_detail/.test(calls.save_draft.payload), "save_draft payload carries fields");
  // My Requests + approvals (current status)
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/hr-activity?tab=my-requests"); w.LivestreamSample.route(); await flush(); await flush();
  ok(/EC-LVSM-2026-00001/.test(cb()) && /Bước 2\/3 · Sang Bui Review/.test(cb()), "My Requests shows step label");
  w.history.pushState({}, "", "/approvals/hr-activity?tab=my-approvals"); w.LivestreamSample.route(); await flush(); await flush();
  { const done = w.document.getElementById("ap-done").innerHTML;
    ok(/Bước 3\/3 · Hoàn tất/.test(done) && /Đã duyệt/.test(done), "processed list shows current status/step (Hoàn tất)"); }
  // detail runtime stepper
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/hr-activity?id=EC-LVSM-2026-00001"); w.LivestreamSample.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper, no not-found");
  { const rh = w.LivestreamSample.buildStepper(detail()); ok(/Đã gửi/.test(rh) && /Sang Bui Review/.test(rh) && /Hoàn tất/.test(rh), "runtime stepper single-level"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.livestream_sample."/.test(JS), "uses Livestream Sample whitelisted API");
  ok(/#ec-lvsm-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width");
  console.log(fails === 0 ? "\nALL LIVESTREAM SAMPLE PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
