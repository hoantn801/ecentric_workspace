// Headless tests for the Asset Damage or Loss page (Node + jsdom).
// Form: 2 approval levels (Operation Review Any One -> CEO), NO fulfillment, COMMENTS REQUIRED ON,
// many fields incl. conditional *_other fields and a multi-select (recommended_actions checkboxes).
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "asset_damage_loss.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-asset-damage-loss">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const FO = {
  asset_types: ["Laptop", "Desktop computer", "Monitor", "Mobile device", "Printer", "RAM", "Other"],
  incident_types: ["Damage", "Loss", "Theft", "Other"],
  recommended_actions: ["Repair", "Replace", "Write-off", "Further investigation", "Other"] };
const calls = {};
function detail(over) {
  return Object.assign({
    business: { name: "EC-ADLR-2026-00001", request_title: "Laptop hong - 2026-07", asset_type: "Laptop",
      asset_code: "LT-01", incident_type: "Damage", incident_description: "fell", incident_date: "2026-07-01",
      incident_location: "HQ", physical_damage: "cracked", data_compromised: "none", impact_on_operations: "minor",
      estimated_repair_cost: 1000000, estimated_value_lost_stolen_asset: 0, recommended_actions: "Repair, Replace",
      requested_by: "u@x", department: "D" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Operation Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "CEO Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "ops@x", status: "Pending" }],
    attachments: [], timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    process_preview: [], capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(over) {
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/asset-damage-loss?tab=create" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method; calls[m.split(".").pop()] = o.args;
    ok(/ecentric_workspace\.approval_center\.api\.asset_damage_loss\./.test(m), "call uses asset_damage_loss NS: " + m.split(".").pop());
    if (m.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@x", employee_name: "U", employee: "EMP-1", department: "D", company: "C" },
      is_system_manager: false, form_options: FO } });
    if (m.endsWith("save_draft")) return Promise.resolve({ message: { name: "EC-ADLR-2026-00001", capabilities: {} } });
    if (m.endsWith("submit_request")) return Promise.resolve({ message: { approval_request: "AR-1", submitted: true, detail: detail() } });
    if (m.endsWith("approve")) return Promise.resolve({ message: { detail: detail() } });
    if (m.endsWith("list_my_requests")) return Promise.resolve({ message: { rows: [
      { name: "EC-ADLR-2026-00001", request_title: "Laptop hong", asset_type: "Laptop", incident_type: "Damage",
        incident_date: "2026-07-01", approval_status: "Pending", current_level: 1,
        current_level_name: "Operation Review", total_levels: 2, modified: "2026-07-06 09:00",
        creation: "2026-07-06 09:00", requested_at: "2026-07-06 09:00", requester_name: "U Nguyen" } ], total: 1 } });
    if (m.endsWith("list_need_my_approval")) return Promise.resolve({ message: { rows: (o.args.section === "pending" ? [
      { name: "EC-ADLR-2026-00001", request_title: "Laptop hong", requested_by: "u@x", incident_type: "Damage",
        approval_status: "Pending", current_level: 1, level_no: 1, total_levels: 2, my_status: "Pending",
        creation: "2026-07-06 09:00", requested_at: "2026-07-06 09:00", requester_name: "U Nguyen" } ] : [
      { name: "EC-ADLR-2026-00002", request_title: "Old", requested_by: "u@x", incident_type: "Loss",
        approval_status: "Approved", current_level: 0, level_no: 1, total_levels: 2, my_status: "Approved" } ]) } });
    if (m.endsWith("get_detail")) return Promise.resolve({ message: (over && over.detail) || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  }};
  w.eval(JS);
  return w;
}
async function run() {
  let w = boot(); await flush(); await flush();
  const cb = () => w.document.getElementById("adlr-body").innerHTML;
  ok(!!w.AssetDamageLoss, "AssetDamageLoss exposed");
  ok(w.document.querySelectorAll(".tab").length === 3, "three tabs rendered (no fulfillment)");
  // key fields render
  ["request_title", "asset_type", "asset_code", "incident_type", "incident_description", "incident_date",
   "incident_location", "witnesses", "physical_damage", "data_compromised", "impact_on_operations",
   "estimated_repair_cost", "estimated_value_lost_stolen_asset"].forEach(function (f) {
    ok(!!w.document.querySelector('[data-model="' + f + '"]'), f + " field renders"); });
  ok(!!w.document.querySelector('[data-upload="request_attachment"]'), "attachment upload renders");
  // impact_on_operations must be a TEXTAREA, not a date input
  { const el = w.document.querySelector('[data-model="impact_on_operations"]');
    ok(el && el.tagName === "TEXTAREA", "impact_on_operations is a TEXTAREA (not date input)"); }
  // recommended_actions checkboxes render (multi-select)
  { const boxes = w.document.querySelectorAll('[data-checks="recommended_actions"] input[type="checkbox"]');
    ok(boxes.length === 5, "recommended_actions renders 5 checkboxes"); }
  // 3-step preview, named, no SLA
  { const pv = w.document.getElementById("adlr-process-preview");
    ok(!!pv, "process preview renders");
    ok(pv.querySelectorAll(".step").length === 3, "preview has 3 steps");
    ok(/Tạo yêu cầu/.test(pv.innerHTML) && /Operation review/.test(pv.innerHTML) && /CEO review/.test(pv.innerHTML), "preview steps named Tao yeu cau / Operation review / CEO review");
    ok(!/SLA/i.test(pv.innerHTML), "preview has no SLA"); }
  ok(!/\bSLA\b/.test(HTML), "no SLA concept anywhere in page");
  // conditional: setting asset_type Other reveals + requires asset_type_other
  { w.AssetDamageLoss.state.draft = { asset_type: "Other" };
    w.AssetDamageLoss.render();
    ok(!!w.document.querySelector('[data-model="asset_type_other"]'), "asset_type Other reveals asset_type_other field");
    const e = w.AssetDamageLoss.validateSubmit() || {};
    ok(!!e.asset_type_other, "asset_type Other requires asset_type_other"); }
  // validateSubmit: required set incl >=1 action + attachment; negative cost rejected; full valid passes
  w.AssetDamageLoss.state.draft = {};
  { const e = w.AssetDamageLoss.validateSubmit() || {};
    ok(e.request_title && e.asset_type && e.asset_code && e.incident_type && e.incident_description && e.incident_date
       && e.incident_location && e.physical_damage && e.data_compromised && e.impact_on_operations, "validateSubmit requires the required set");
    ok(!!e.recommended_actions, "validateSubmit requires >=1 recommended action");
    ok(!e.request_attachment, "A3: validateSubmit does NOT require attachment (optional)"); }
  const fullDraft = () => ({ request_title: "T", asset_type: "Laptop", asset_code: "0", incident_type: "Damage",
    incident_description: "desc", incident_date: "2026-07-01", incident_location: "HQ", physical_damage: "pd",
    data_compromised: "none", impact_on_operations: "impact", estimated_repair_cost: 0,
    estimated_value_lost_stolen_asset: 0, recommended_actions: "Repair", request_attachment: "/f" });
  w.AssetDamageLoss.state.draft = Object.assign(fullDraft(), { estimated_repair_cost: -5 });
  ok((w.AssetDamageLoss.validateSubmit() || {}).estimated_repair_cost, "negative repair cost blocked");
  w.AssetDamageLoss.state.draft = fullDraft();
  ok(w.AssetDamageLoss.validateSubmit() === null, "full valid draft passes");
  // A3: evidence attachment OPTIONAL — valid draft with NO request_attachment still passes
  { const noAtt = fullDraft(); delete noAtt.request_attachment; w.AssetDamageLoss.state.draft = noAtt;
    ok(w.AssetDamageLoss.validateSubmit() === null, "A3: draft without request_attachment passes validateSubmit"); }
  // multi-select: checking two boxes stores comma-joined string
  w = boot(); await flush(); await flush();
  { const boxes = w.document.querySelectorAll('[data-checks="recommended_actions"] input[type="checkbox"]');
    boxes[0].checked = true; boxes[0].dispatchEvent(new w.Event("change", { bubbles: true }));
    const boxes2 = w.document.querySelectorAll('[data-checks="recommended_actions"] input[type="checkbox"]');
    boxes2[1].checked = true; boxes2[1].dispatchEvent(new w.Event("change", { bubbles: true }));
    const ra = (w.AssetDamageLoss.state.draft || {}).recommended_actions;
    ok(ra === "Repair, Replace", "recommended_actions stored as comma-joined string: " + ra); }
  // A2: checkbox visual checked state persists across the conditional (Other) re-render
  w = boot(); await flush(); await flush();
  { let boxes = w.document.querySelectorAll('[data-checks="recommended_actions"] input[type="checkbox"]');
    boxes[0].checked = true; boxes[0].dispatchEvent(new w.Event("change", { bubbles: true }));
    boxes = w.document.querySelectorAll('[data-checks="recommended_actions"] input[type="checkbox"]');
    boxes[1].checked = true; boxes[1].dispatchEvent(new w.Event("change", { bubbles: true }));
    // toggle the last box ("Other") to force the conditional re-render (reveals recommended_actions_other)
    boxes = w.document.querySelectorAll('[data-checks="recommended_actions"] input[type="checkbox"]');
    const other = boxes[boxes.length - 1];
    other.checked = true; other.dispatchEvent(new w.Event("change", { bubbles: true }));
    ok(!!w.document.querySelector('[data-model="recommended_actions_other"]'), "A2: Other toggle re-renders and reveals recommended_actions_other");
    const after = w.document.querySelectorAll('[data-checks="recommended_actions"] input[type="checkbox"]');
    ok(after[0].checked && after[1].checked, "A2: first two recommended-action boxes remain visually checked across the conditional re-render"); }
  // save_draft payload carries asset_type + incident_type
  w = boot(); await flush(); await flush();
  w.AssetDamageLoss.state.draft = fullDraft();
  w.document.getElementById("adlr-save").click(); await flush(); await flush();
  ok(calls.save_draft && /asset_type/.test(calls.save_draft.payload) && /incident_type/.test(calls.save_draft.payload), "save_draft payload carries asset_type + incident_type");
  // submit_request called with draft name
  w = boot(); await flush(); await flush();
  w.AssetDamageLoss.state.draft = fullDraft();
  w.document.getElementById("adlr-submit").click(); await flush(); await flush(); await flush();
  ok(calls.submit_request && calls.submit_request.name === "EC-ADLR-2026-00001", "submit_request called with draft name");
  // My Requests columns + step label
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/asset-damage-loss?tab=my-requests"); w.AssetDamageLoss.route(); await flush(); await flush();
  ok(/EC-ADLR-2026-00001/.test(cb()) && /Bước 2\/4 · Operation Review/.test(cb()), "My Requests shows step label");
  ok(/Loại tài sản/.test(cb()) && /Loại sự cố/.test(cb()) && /Ngày sự cố/.test(cb()), "My Requests columns adapted");
  { const ths = Array.prototype.map.call(w.document.querySelectorAll("#adlr-list th"), function (t) { return t.textContent.trim(); });
    ok(ths[0] === "Ngày request", "My Requests first header is 'Ngày request'");
    ok(ths.indexOf("Người request") >= 0, "My Requests has 'Người request' header"); }
  { const rowTxt = (w.document.querySelector("#adlr-list tbody tr") || {}).textContent || "";
    ok(/\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}/.test(rowTxt), "My Requests row shows dd/MM/yyyy HH:mm date");
    ok(/U Nguyen/.test(rowTxt), "My Requests row shows requester name"); }
  // detail loads via get_detail + runtime stepper
  w = boot(); await flush(); await flush();
  w.history.pushState({}, "", "/approvals/asset-damage-loss?id=EC-ADLR-2026-00001"); w.AssetDamageLoss.route(); await flush(); await flush();
  ok(calls.get_detail && calls.get_detail.name === "EC-ADLR-2026-00001", "detail loads via api.asset_damage_loss.get_detail");
  ok(/class="stepper"/.test(cb()) && !/Không tải được yêu cầu/.test(cb()), "detail renders runtime stepper, no not-found");
  { const rh = w.AssetDamageLoss.buildStepper(detail()); ok(/Đã gửi/.test(rh) && /Operation Review/.test(rh) && /CEO Review/.test(rh), "runtime stepper Operation Review -> CEO Review"); }
  ok(/Laptop hong - 2026-07/.test(cb()), "A4: detail body shows request_title heading");
  // approve modal REQUIRES a comment
  w = boot(); await flush(); await flush();
  { w.AssetDamageLoss.doApprove("EC-ADLR-2026-00001", detail());
    const ov = w.document.querySelector(".ec-adlr-overlay");
    ok(!!ov, "approve modal opens");
    ok(/<span class="req">\*<\/span>/.test(ov.querySelector(".ec-adlr-modal-b").innerHTML), "approve comment labelled required (*)");
    const before = calls.approve; // remember prior
    ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(w.document.querySelector(".ec-adlr-overlay"), "empty approve comment keeps modal open (rejected)");
    ok(calls.approve === before, "empty approve comment does NOT call approve");
    // now provide a comment
    ov.querySelector("#m-cmt").value = "looks good"; ov.querySelector("[data-ok]").click(); await flush(); await flush();
    ok(calls.approve && calls.approve.name === "EC-ADLR-2026-00001" && calls.approve.comment === "looks good", "approve called with {name, comment}"); }
  // guardrails
  ok(!/<button (?![^>]*type=)[^>]*>/.test(HTML), "every button has type");
  ok(!/frappe\.db\.get_doc|frappe\.db\.get_value|frappe\.client/.test(JS), "no Desk-style shim in script");
  ok(/"ecentric_workspace.approval_center.api.asset_damage_loss."/.test(JS), "uses Asset Damage Loss whitelisted API");
  ok(/upload_file/.test(JS) && /EC Asset Damage Loss Request/.test(JS), "attachment upload wired to upload_file with correct doctype");
  ok(/#ec-adlr-root .content\{[^}]*max-width:1200px[^}]*margin:0 auto/.test(HTML), "balanced width .content");
  ok(/#ec-adlr-root .adlr-formwrap\{[^}]*max-width:none/.test(HTML), "balanced width .adlr-formwrap");
  ok(/@media \(max-width:1024px\)/.test(HTML), "responsive media query present");
  console.log(fails === 0 ? "\nALL ASSET DAMAGE LOSS PAGE TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
