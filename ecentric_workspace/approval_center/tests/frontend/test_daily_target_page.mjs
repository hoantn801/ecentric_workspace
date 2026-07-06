// Headless tests for the Daily Target page (Node + jsdom). Form #5 (2 processes by scope, no fulfillment).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "daily_target.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-daily-target">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = { scopes: ["Project level", "Consolidated / Total"], channels: ["Lazada", "Shopee", "TikTok Shop", "Other"],
  target_setting_types: ["Setting new target", "Revising current target"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-DTGT-2026-00001", request_title: "Project level - BrandX - 2026-08-01", request_scope: "Project level",
      brand: "BrandX", channels: "Shopee,Lazada", channel_other: "", target_month: "2026-08-01",
      target_setting_type: "Setting new target", justification: "attainable", requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Commercial Manager Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "linh.ngo@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/daily-target?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-DTGT-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-DTGT-2026-00001", request_title: "Project level - BrandX", request_scope: "Project level", brand: "BrandX",
        target_month: "2026-08-01", approval_status: "Pending", current_level: 1, current_level_name: "Commercial Manager Review",
        total_levels: 1, modified: "2026-07-06 09:00" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-DTGT-2026-00001", request_title: "Project level - BrandX", requested_by: "u@x", request_scope: "Project level",
        brand: "BrandX", level_no: 1, level_name: "Commercial Manager Review", total_levels: 1, my_status: "Pending" } ] : []) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  ok(!!w.DailyTarget, "DailyTarget exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  const cb = () => w.document.getElementById("dtgt-body").innerHTML;

  ["request_title", "request_scope", "brand", "target_month", "target_setting_type", "justification"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(w.document.querySelectorAll('[data-chan]').length === 4, "channel checkboxes render (Lazada/Shopee/TikTok/Other)");
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders (required)");

  ok(!!w.document.getElementById("dtgt-process-preview"), "process preview card renders");
  { const html = cb(); ok(html.indexOf('id="dtgt-process-preview"') < html.indexOf('data-model="request_title"'), "preview before request_title"); }
  // scope-based preview
  ok(w.DailyTarget.previewSteps("Project level")[1].name === "Commercial Manager duyệt", "Project scope preview -> Commercial Manager");
  ok(w.DailyTarget.previewSteps("Consolidated / Total")[1].name === "CEO duyệt", "Consolidated scope preview -> CEO");
  ok(w.DailyTarget.previewSteps("Project level").length === 3, "preview has 3 steps (Tạo/approver/Hoàn tất)");

  ok(/Project level/.test(cb()) && /Consolidated \/ Total/.test(cb()), "scope options render");
  ok(/Lazada/.test(cb()) && /Shopee/.test(cb()) && /TikTok Shop/.test(cb()), "channel options render");
  ok(/Setting new target/.test(cb()) && /Revising current target/.test(cb()), "target setting type options render");

  w.DailyTarget.state.draft = {};
  { const e = w.DailyTarget.validateSubmit() || {};
    ok(e.request_scope && e.brand && e.channels && e.target_month && e.target_setting_type && e.justification && e.request_attachment,
       "validateSubmit: all required incl attachment + channels"); }
  w.DailyTarget.state.draft = { request_title: "T", request_scope: "Project level", brand: "B", channels: "Shopee",
    target_month: "2026-08-15", target_setting_type: "Setting new target", justification: "j", request_attachment: "/f" };
  ok((w.DailyTarget.validateSubmit() || {}).target_month, "validateSubmit: non-first-of-month blocked");
  w.DailyTarget.state.draft.target_month = "2026-08-01";
  ok(w.DailyTarget.validateSubmit() === null, "valid form (first-of-month) passes");
  ok(w.DailyTarget.suggestTitle({ request_scope: "Project level", brand: "BrandX", target_month: "2026-08-01" }) === "Project level - BrandX - 2026-08-01", "title auto-suggest");

  w.document.getElementById("dtgt-save").click(); await flush(); await flush();
  ok(calls.save_draft && /request_scope/.test(calls.save_draft.payload) && /Shopee/.test(calls.save_draft.payload), "save_draft payload carries scope + channels");

  w = boot(); await flush(); await flush();
  w.DailyTarget.state.draft = { request_title: "T", request_scope: "Project level", brand: "B", channels: "Shopee",
    target_month: "2026-08-01", target_setting_type: "Setting new target", justification: "j", request_attachment: "/f" };
  w.DailyTarget.state.titleTouched = true;
  w.document.getElementById("dtgt-submit").click(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-DTGT-2026-00001", "submit_request called with draft name");

  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/daily-target?tab=my-requests"); w.DailyTarget.route(); await flush(); await flush();
  ok(/EC-DTGT-2026-00001/.test(cb()) && /Bước 2\/3 · Commercial Manager Review/.test(cb()), "My Requests list renders with step label");
  w.history.pushState({}, "", "/approvals/daily-target?tab=my-approvals"); w.DailyTarget.route(); await flush(); await flush();
  ok(/Cần tôi xử lý/.test(cb()) && !!w.document.querySelector('[data-quick="approve"]'), "Need My Approval renders");

  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/daily-target?id=EC-DTGT-2026-00001"); w.DailyTarget.route(); await flush(); await flush();
  ok(/class="stepper"/.test(cb()), "detail renders runtime stepper");
  { const rh = w.DailyTarget.buildStepper(detail());
    ok(/Đã gửi/.test(rh) && /Commercial Manager Review/.test(rh) && /Hoàn tất/.test(rh), "runtime stepper Đã gửi + level + Hoàn tất"); }

  w = boot({ detail: detail({ approval: { name: "AR-1", approval_status: "Information Required", current_level: 1, information_requested_from_level: 1 },
    approvers: [{ level_no: 1, approver: "linh.ngo@x", status: "Information Requested", comment: "thêm" }], capabilities: { can_edit: true } }) });
  await flush(); await flush();
  w.history.pushState({}, "", "/approvals/daily-target?id=EC-DTGT-2026-00001"); w.DailyTarget.route(); await flush(); await flush();
  w.DailyTarget.startEditResubmit(w.DailyTarget.state.detail); await flush();
  { const eb = cb(); ok(/Cần bổ sung thông tin/.test(eb) && /class="stepper"/.test(eb) && /class="step info"/.test(eb), "resubmit shows banner + runtime stepper with info"); }

  ok(/#ec-dtgt-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced centered width");
  ok(/#ec-dtgt-root .dtgt-formwrap\{[^}]*max-width:none/.test(HTML), "form wrapper aligns under header/tabs");

  console.log(fails === 0 ? "\nALL DAILY TARGET PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
