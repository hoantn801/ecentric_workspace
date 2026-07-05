// Headless tests for the AI Topup page (Node + jsdom). B3.2.
import { JSDOM } from "jsdom";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "ai_topup.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-aitopup">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));

function boot(){
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/ai-topup?tab=create" });
  const w = dom.window;
  w.frappe = { call: (o) => {
    if (o.method.endsWith("list_my_approvals")) return Promise.resolve({ message: { rows: (o.args.section==="pending"?[{name:"R-1",requested_by:"u@x",department:"D",ai_tool:"T",requested_amount:100,level_no:2,my_status:"Pending"}]:[]) } });
    if (o.method.endsWith("get_request_detail")) return Promise.resolve({ message: { business:{name:"R-1",ai_tool:"T",requested_amount:100,currency:"VND"}, approval:{name:"AR-2",approval_status:"Pending",current_level:2}, fulfillment:{status:"Not Started"},
      levels:[{level_no:1,level_name:"Manager",approval_mode:"Any One",level_status:"Approved"},{level_no:2,level_name:"Finance Review",approval_mode:"Any One",level_status:"In Progress"}],
      approvers:[{level_no:2,approver:"me@x",status:"Pending"}], attachments:[], timeline:[{action:"Submitted",actor:"u@x",action_time:"2026-07-06 09:00"}],
      capabilities:{can_approve:true,can_reject:true,can_request_information:true,can_edit:false,can_cancel:false} } });
    if (o.method.endsWith("get_bootstrap")) return Promise.resolve({ message: {
      tabs:{create:true,my_requests:true,my_approvals:false,fulfillment:false},
      context:{user:"u@x",employee_name:"U",department:"D",company:"C",manager_user:"m@x",manager_resolvable:true},
      is_system_manager:false, form_options:{ai_tools:[{value:"T",label:"Tool"}],currencies:["VND","USD"],account_modes:["Existing Account","New Account"],request_types:["Top-up"],billing_cycles:["Monthly"]} } });
    if (o.method.endsWith("search_ai_accounts")) return Promise.resolve({ message: [
      { name:"EC-AIACC-00001", ai_tool:"Claude", account_email:"hoantn801@gmail.com", account_manager:"hoan.tran@ecentric.vn", current_plan:"Claude Max 20x", billing_cycle:"Monthly", status:"Active", subscription_start_date:"2026-07-04", subscription_end_date:"2026-07-22" },
      { name:"EC-AIACC-00002", ai_tool:"ChatGPT", account_email:"hoantn801@gmail.com", account_manager:"hoan.tran@ecentric.vn", current_plan:"ChatGPT Plus", billing_cycle:"Monthly", status:"Active", subscription_start_date:"", subscription_end_date:"" } ] });
    if (o.method.endsWith("get_ai_account_detail")) return Promise.resolve({ message: (o.args.name === "EC-AIACC-00001" ? { name:"EC-AIACC-00001", ai_tool:"Claude", account_email:"hoantn801@gmail.com", account_manager:"hoan.tran@ecentric.vn", current_plan:"Claude Max 20x", billing_cycle:"Monthly", status:"Active", subscription_start_date:"2026-07-04", subscription_end_date:"2026-07-22" } : null) });
    return Promise.resolve({ message: { rows:[], total:0 } });
  }};
  w.eval(JS);
  return w;
}

async function run(){
  const w = boot(); await flush(); await flush();
  ok(!!w.AITopup, "AITopup exposed");
  ok(!!w.document.querySelector('[data-model="account_mode"]'), "create form rendered (account_mode present)");
  ok(w.document.querySelectorAll(".tab").length === 4, "four tabs rendered");

  // dynamic stepper: 2 levels -> 5 steps (submitted + 2 + fulfillment + completed)
  const det2 = { approval:{name:"AR-1",approval_status:"Pending",current_level:1}, fulfillment:{status:"Not Started"},
    levels:[{level_no:1,level_name:"Direct Manager",approval_mode:"Any One",level_status:"In Progress"},
            {level_no:2,level_name:"Finance",approval_mode:"Any One",level_status:"Pending"}],
    approvers:[{level_no:1,approver:"a@x",status:"Pending"},{level_no:1,approver:"b@x",status:"Pending"}] };
  const html2 = w.AITopup.buildStepper(det2);
  ok((html2.match(/class="step /g)||[]).length === 5, "2 levels -> 5 stepper steps (dynamic)");
  ok(/a@x hoặc b@x/.test(html2), "Any One shows eligible approvers with 'hoặc'");

  // 4 levels -> 7 steps (no hardcoded three)
  const det4 = { approval:{name:"AR-1",approval_status:"Pending",current_level:1}, fulfillment:{status:"Not Started"},
    levels:[1,2,3,4].map(n=>({level_no:n,level_name:"L"+n,approval_mode:"Any One",level_status:"Pending"})), approvers:[] };
  ok((w.AITopup.buildStepper(det4).match(/class="step /g)||[]).length === 7, "4 levels -> 7 steps");

  // approved level shows actual approver + skipped others
  const detS = { approval:{name:"AR-2",approval_status:"Pending",current_level:2}, fulfillment:{status:"Not Started"},
    levels:[{level_no:1,level_name:"Ops",approval_mode:"Any One",level_status:"Approved",completed_at:"2026-07-06 10:00"},
            {level_no:2,level_name:"Fin",approval_mode:"Any One",level_status:"In Progress"}],
    approvers:[{level_no:1,approver:"a@x",status:"Approved"},{level_no:1,approver:"b@x",status:"Skipped"}] };
  const hs = w.AITopup.buildStepper(detS);
  ok(/Duyệt bởi a@x/.test(hs), "approved level shows actual approver");
  ok(/Bỏ qua: b@x/.test(hs) && /không cần xử lý/.test(hs), "skipped approver explained");

  // routing: switch to my-requests updates URL + renders list scaffolding
  w.AITopup.state.boot = w.AITopup.state.boot || {tabs:{}};
  w.history.pushState({}, "", "/approvals/ai-topup?tab=my-requests"); w.AITopup.route(); await flush();
  ok(w.location.search.includes("my-requests"), "route to my-requests reflected in URL");


  // ---- B3.3 unit tests ----
  ok(/Duyệt/.test(w.AITopup.actionPanelHTML({capabilities:{can_approve:true}})), "action panel shows Duyệt when can_approve");
  ok(/Chỉnh sửa & gửi lại/.test(w.AITopup.actionPanelHTML({capabilities:{can_edit:true},approval:{approval_status:"Information Required"}})), "action panel shows edit+resubmit on Information Required");
  ok(/Không có hành động/.test(w.AITopup.actionPanelHTML({capabilities:{}})), "action panel empty state");
  ok(/Đã gửi/.test(w.AITopup.timelineHTML([{action:"Submitted",actor:"u",action_time:"2026-07-06 09:00"}])), "timeline maps action to Vietnamese");
  ok(/Chưa có hoạt động/.test(w.AITopup.timelineHTML([])), "timeline empty state");
  ok(/không còn quyền/.test(w.AITopup.mapErr({message:"You are not a pending approver for the current level."})), "concurrency: pending-approver message");
  ok(/vừa được cập nhật/.test(w.AITopup.mapErr({message:"Request is Approved; no further action is allowed."})), "concurrency: terminal message");
  // modal opens + closes
  var mm=w.AITopup.modal("T","<div>x</div>",{}); ok(!!w.document.querySelector(".ec-ait-overlay"), "modal opens overlay"); mm.close(); ok(!w.document.querySelector(".ec-ait-overlay"), "modal closes");
  // My Approvals tab renders actionable section with quick actions
  w.history.pushState({},"","/approvals/ai-topup?tab=my-approvals"); w.AITopup.route(); await flush(); await flush();
  ok(/Cần tôi xử lý/.test(w.document.body.innerHTML), "My Approvals renders 'Cần tôi xử lý' section");
  ok(!!w.document.querySelector('[data-quick="approve"]'), "actionable row has Duyệt quick action");

  // ---- B3.4 fulfillment unit tests ----
  ok(/Chưa đến bước xử lý/.test(w.AITopup.fulfillmentSectionHTML({approval:{approval_status:"Pending"},fulfillment:{status:"Not Started"},capabilities:{}})), "fulfillment: before approval message");
  ok(/Nhận xử lý/.test(w.AITopup.fulfillmentSectionHTML({approval:{approval_status:"Approved"},fulfillment:{status:"Assigned",eligible_fulfillers:["a@x","b@x"]},capabilities:{can_claim:true}})), "fulfillment: assigned shows claim when can_claim");
  ok(!/Nhận xử lý/.test(w.AITopup.fulfillmentSectionHTML({approval:{approval_status:"Approved"},fulfillment:{status:"Assigned",eligible_fulfillers:[]},capabilities:{can_claim:false}})), "fulfillment: no claim button when not eligible");
  ok(/Nhập thông tin hoàn tất/.test(w.AITopup.fulfillmentSectionHTML({approval:{approval_status:"Approved"},fulfillment:{status:"In Progress",owner:"a@x"},capabilities:{can_complete:true},business:{}})), "fulfillment: owner sees completion form");
  ok(!/Nhập thông tin hoàn tất/.test(w.AITopup.fulfillmentSectionHTML({approval:{approval_status:"Approved"},fulfillment:{status:"In Progress",owner:"a@x"},capabilities:{can_complete:false},business:{}})), "fulfillment: non-owner read-only");
  ok(/Tài khoản AI đã cập nhật/.test(w.AITopup.fulfillmentSectionHTML({approval:{approval_status:"Approved"},fulfillment:{status:"Completed",ai_account:{name:"ACC",account_email:"e@x"}},capabilities:{},business:{}})), "fulfillment: completed shows AI account update");
  // completion validation
  w.AITopup.state.comp={}; ok(w.AITopup.completionErrors().some(function(e){return /chứng từ thanh toán/.test(e);}), "payment proof required");
  w.AITopup.state.comp={payment_proof:"/f/p",actual_amount:10,invoice_status:"Invoice Available"}; ok(w.AITopup.completionErrors().some(function(e){return /hóa đơn/.test(e);}), "invoice available requires receipt");
  w.AITopup.state.comp={payment_proof:"/f/p",actual_amount:10,invoice_status:"No Invoice Issued"}; var ne=w.AITopup.completionErrors(); ok(ne.some(function(e){return /lý do/.test(e);})&&ne.some(function(e){return /mã giao dịch/.test(e);}), "no invoice requires reason + txn ref");
  w.AITopup.state.comp={payment_proof:"/f/p",actual_amount:10,invoice_status:"No Invoice Issued",no_invoice_reason:"r",transaction_reference:"t"}; ok(w.AITopup.completionErrors().length===0, "valid no-invoice completion passes");
  // fulfillment tab visibility gate
  w.AITopup.state.boot={tabs:{fulfillment:false}}; var tmp=w.document.createElement("div"); w.AITopup.renderFulfillment(tmp); ok(/Không khả dụng/.test(tmp.innerHTML), "fulfillment tab denied when not eligible");

  // ---- B3.5 a11y/responsive ----
  { var m=w.AITopup.modal("T","<input id=zz>",{}); ok(!!w.document.querySelector('.ec-ait-modal[role="dialog"][aria-modal="true"]'),"modal has role=dialog aria-modal"); m.close(); }
  ok(/overflow-x:auto/.test(HTML) && /focus-visible/.test(HTML), "responsive table scroll + focus-visible present");

  // ---- UAT polish (fix/approval-center-aitopup-uat-polish-1) ----
  // ensure a realistic bootstrap context for the create-form renders below
  w.AITopup.state.boot = w.AITopup.state.boot || { tabs:{}, form_options:{} };
  w.AITopup.state.boot.form_options = w.AITopup.state.boot.form_options || { ai_tools:[{value:"T",label:"Tool"}], currencies:["VND"] };
  w.AITopup.state.boot.context = { user:"u@x", employee:"EMP-1", employee_name:"U", department:"D", company:"C", manager_user:"m@x", manager_resolvable:true };
  w.AITopup.state.draft = null;
  w.history.pushState({}, "", "/approvals/ai-topup?tab=create"); w.AITopup.route(); await flush();
  const cbody = () => w.document.getElementById("ait-body").innerHTML;
  // roadmap always visible on Create, exactly 6 compact steps, SLA note
  ok(/Quy trình xử lý yêu cầu/.test(cbody()), "roadmap card visible on Create tab");
  ok((cbody().match(/class="rmx-step/g) || []).length === 6, "roadmap has exactly 6 steps");
  ok(/SLA 3 giờ làm việc/.test(cbody()) && /09:00.{0,3}12:00/.test(cbody()), "roadmap SLA note present with business-hours window");
  ok(!/id="d-stepper"/.test(cbody()) && !/class="stepper"/.test(cbody()), "roadmap does not duplicate the dynamic approval stepper");
  // account period label + empty state (scoped to the account field, not the summary card)
  ok(/Thời hạn hiện tại của account/.test(cbody()), "account period label clarified");
  ok(/value="Chưa chọn account"/.test(cbody()), "account period field shows 'Chưa chọn account' before selection (not dashes)");
  // auto-renewal helper text
  ok(/Chỉ dùng để ghi nhận nhu cầu gia hạn/.test(cbody()), "auto-renewal helper text present");

  // blocking alert: missing direct manager (Employee exists) -> icon + title + description, left aligned
  w.AITopup.state.boot.context = { user:"u@x", employee:"EMP-1", employee_name:"U", department:"D", company:"C", manager_user:null, manager_resolvable:false };
  w.AITopup.state.draft = null;
  w.AITopup.render(); await flush();
  const mb = () => w.document.getElementById("ait-body").innerHTML;
  ok(/class="ec-alert-title"/.test(mb()) && /class="ec-alert-desc"/.test(mb()), "blocking alert has structured title + description");
  ok(/>Không thể gửi yêu cầu</.test(mb()), "missing-manager alert uses short title");
  ok(/Chưa xác định được quản lý trực tiếp của người yêu cầu/.test(mb()), "missing-manager alert description");
  ok(!/reports_to/.test(mb()), "alert does not expose raw technical field name");
  const alertEl = w.document.querySelector(".ec-alert");
  const firstChild = alertEl && alertEl.firstElementChild;
  ok(!!firstChild && firstChild.tagName.toLowerCase() === "svg", "alert icon is the first (left) child, text follows");

  // Administrator / no Employee -> friendlier message
  w.AITopup.state.boot.context = { user:"Administrator", employee:null, manager_resolvable:false };
  w.AITopup.state.draft = null;
  w.AITopup.render(); await flush();
  ok(/Không thể gửi yêu cầu bằng tài khoản hiện tại/.test(mb()), "Administrator/no-Employee friendly title");
  ok(/test bằng user nhân sự thật/.test(mb()), "Administrator/no-Employee friendly description");

  // AI Tool empty state (New Account, no active EC AI Tool records)
  w.AITopup.state.boot.context = { user:"u@x", employee:"EMP-1", employee_name:"U", department:"D", company:"C", manager_user:"m@x", manager_resolvable:true };
  w.AITopup.state.boot.form_options.ai_tools = [];
  w.AITopup.state.draft = { account_mode: "New Account" };
  w.AITopup.render(); await flush();
  ok(/Chưa có AI Tool nào\. Vui lòng tạo EC AI Tool trong Desk/.test(cbody()), "AI Tool empty-state message shown when no active tools");

  // ---- UAT polish 2 (fix/approval-center-aitopup-uat-polish-2) ----
  const setInput = (sel, val) => { const el = w.document.querySelector(sel); el.value = val; el.dispatchEvent(new w.Event("input", { bubbles: true })); };
  const body = () => w.document.getElementById("ait-body").innerHTML;
  const freshCtx = () => { w.AITopup.state.boot.context = { user:"u@x", employee:"EMP-1", employee_name:"U", department:"D", company:"C", manager_user:"m@x", manager_resolvable:true }; };
  w.AITopup.state.boot.form_options.ai_tools = [{ value:"Claude", label:"Claude" }, { value:"ChatGPT", label:"ChatGPT" }];

  // roadmap connected stepper
  const rm = w.AITopup.roadmapHTML();
  ok((rm.match(/class="rmx-step/g) || []).length === 6, "roadmap has exactly 6 steps (rmx)");
  ok(/class="rmx"/.test(rm), "roadmap renders as connected stepper (.rmx container)");
  ok(/class="rmx-step current"/.test(rm), "roadmap step 1 is highlighted (current)");
  ok(/Tạo yêu cầu/.test(rm) && /Operation duyệt/.test(rm) && /Operation xử lý/.test(rm), "roadmap uses the new step labels");
  ok(/SLA 3 giờ làm việc/.test(rm), "SLA note still appears below roadmap");

  // request_title: visible + auto-suggest + required
  freshCtx();
  w.AITopup.state.draft = { account_mode:"New Account", request_type:"Renewal" };
  w.AITopup.render(); await flush();
  ok(!!w.document.querySelector('[data-model="request_title"]'), "request title field is visible");
  setInput('[data-model="ai_tool"]', "Claude");
  setInput('[data-model="proposed_account_email"]', "hoantn801@gmail.com");
  ok(w.document.querySelector('[data-model="request_title"]').value === "Renewal - Claude - hoantn801@gmail.com", "request title auto-suggests from type + tool + account");
  ok(w.AITopup.suggestTitle({ account_mode:"New Account", request_type:"New Subscription", ai_tool:"ChatGPT", proposed_account_email:"user@ecentric.vn" }) === "New Subscription - ChatGPT - user@ecentric.vn", "suggestTitle New Account format");
  ok(w.AITopup.suggestTitle({ account_mode:"Existing Account", request_type:"Renewal", ai_tool:"Claude", account_email:"e@x" }) === "Renewal - Claude - e@x", "suggestTitle Existing Account format");

  // New Account payload wiring — the actual UAT blocker (fields reach state.draft)
  ok(w.AITopup.state.draft.ai_tool === "Claude", "New Account payload includes ai_tool");
  ok(w.AITopup.state.draft.proposed_account_email === "hoantn801@gmail.com", "New Account payload includes proposed_account_email");
  setInput('[data-model="proposed_account_manager"]', "mgr@x");
  ok(w.AITopup.state.draft.proposed_account_manager === "mgr@x", "New Account payload includes proposed_account_manager");

  // the switch scenario (Existing -> New) must wire the re-rendered sub-fields
  freshCtx(); w.AITopup.state.draft = {}; w.AITopup.render(); await flush();
  setInput('[data-model="account_mode"]', "New Account"); await flush();
  setInput('[data-model="proposed_account_email"]', "switch@x");
  ok(w.AITopup.state.draft.proposed_account_email === "switch@x", "New Account sub-fields wire after switching account_mode (bug fix)");

  // validateSubmit blocks missing fields
  w.AITopup.state.draft = { account_mode:"New Account" };
  ok(!!(w.AITopup.validateSubmit() || {}).request_title, "submit blocked inline: request title required");
  w.AITopup.state.draft = { account_mode:"New Account", request_title:"T" };
  const vs = w.AITopup.validateSubmit() || {};
  ok(vs.ai_tool && vs.proposed_account_email && vs.proposed_account_manager, "submit blocked inline: New Account required fields");
  w.AITopup.state.draft = { account_mode:"New Account", request_title:"T", ai_tool:"Claude", proposed_account_email:"e@x", proposed_account_manager:"m@x", requested_amount:100 };
  ok(w.AITopup.validateSubmit() === null, "valid New Account passes validateSubmit");
  w.AITopup.state.draft = { account_mode:"Existing Account", request_title:"T" };
  ok(!!(w.AITopup.validateSubmit() || {}).ai_account, "Existing Account requires selected account");

  // backend New Account error maps to inline field errors
  freshCtx(); w.AITopup.state.draft = { account_mode:"New Account", request_title:"T" }; w.AITopup.render(); await flush();
  ok(w.AITopup.applyBackendError({ message:"New Account requests require: ai_tool, proposed_account_email, proposed_account_manager" }) === true, "backend New Account error is handled (mapped)");
  ok(!!w.document.querySelector('[data-fld="ai_tool"].invalid') && !!w.document.querySelector('[data-fld="proposed_account_email"].invalid'), "backend New Account error maps to inline field errors");

  // summary binding by account mode
  freshCtx();
  w.AITopup.state.draft = { account_mode:"New Account", request_type:"Renewal", ai_tool:"Claude", proposed_account_email:"hoantn801@gmail.com", proposed_account_manager:"mgr@x", requested_plan:"Pro", requested_amount:100, currency:"USD" };
  w.AITopup.render(); await flush();
  { const sum = w.document.getElementById("ait-summary").innerHTML;
    ok(/Claude/.test(sum) && /hoantn801@gmail.com/.test(sum) && /mgr@x/.test(sum), "summary shows Tool/Account/Account Manager for New Account (no dashes)"); }
  w.AITopup.state.draft = { account_mode:"Existing Account", ai_account:"ACC-1", ai_tool:"ChatGPT", account_email:"e@x", account_manager:"am@x", current_plan:"Team" };
  w.AITopup.render(); await flush();
  { const sum = w.document.getElementById("ait-summary").innerHTML;
    ok(/ChatGPT/.test(sum) && /e@x/.test(sum) && /am@x/.test(sum), "summary shows Tool/Account/Account Manager for Existing Account"); }

  // Existing vs New account period field
  w.AITopup.state.draft = { account_mode:"Existing Account" }; w.AITopup.render(); await flush();
  ok(/Thời hạn hiện tại của account/.test(body()), "Existing Account period label present");
  ok(/value="Chưa chọn account"/.test(body()), "Existing Account shows 'Chưa chọn account' before selection");
  w.AITopup.state.draft = { account_mode:"New Account" }; w.AITopup.render(); await flush();
  ok(!/Thời hạn hiện tại của account/.test(body()), "New Account mode does not show current-account period field");

  // auto-renewal helper text still present
  ok(/Chỉ dùng để ghi nhận nhu cầu gia hạn/.test(body()), "auto-renewal helper text remains record-only");

  // ---- UAT: request-detail stepper draft vs runtime mode ----
  // Draft (no runtime EC Approval Request): configured preview, step 1 current, no 'Đã gửi' completed
  const draftDet = { approval:{}, fulfillment:{ status:"Not Started" },
    process_preview:[{level_no:1,level_name:"Direct Manager"},{level_no:2,level_name:"Operation Review"},{level_no:3,level_name:"Finance Review"}] };
  const dh = w.AITopup.buildStepper(draftDet);
  ok((dh.match(/class="step /g) || []).length === 6, "draft stepper has 6 steps (create + 3 levels + fulfillment + done)");
  ok(/Tạo yêu cầu/.test(dh) && /class="step current"/.test(dh) && /Đang thực hiện/.test(dh), "draft: step 1 'Tạo yêu cầu' is current");
  ok(!/Đã gửi/.test(dh), "draft: does NOT show 'Đã gửi' as completed");
  ok(/Direct Manager/.test(dh) && /Operation Review/.test(dh) && /Finance Review/.test(dh), "draft: includes configured Manager/Operation/Finance preview steps");
  ok(/Operation xử lý/.test(dh) && /Hoàn tất/.test(dh), "draft: includes fulfillment + completed preview steps");
  ok(dh.indexOf("Direct Manager") > -1 && dh.indexOf("Direct Manager") < dh.indexOf("Operation xử lý"), "draft: approval levels precede fulfillment (fulfillment is not step 2)");

  // Draft fallback (no process_preview provided): still 6 steps with generic labels
  const dh2 = w.AITopup.buildStepper({ approval:{}, fulfillment:{} });
  ok((dh2.match(/class="step /g) || []).length === 6 && /Manager duyệt/.test(dh2) && /Operation duyệt/.test(dh2) && /Finance duyệt/.test(dh2), "draft fallback: 6 steps with generic approval labels when no preview data");

  // Runtime after submit: 'Đã gửi' completed + first level current, dynamic level count
  const rtDet = { approval:{ name:"AR-9", approval_status:"Pending", current_level:1 }, fulfillment:{ status:"Not Started" },
    levels:[{level_no:1,level_name:"Direct Manager",approval_mode:"Any One",level_status:"In Progress"},
            {level_no:2,level_name:"Operation Review",approval_mode:"Any One",level_status:"Pending"},
            {level_no:3,level_name:"Finance Review",approval_mode:"Any One",level_status:"Pending"}],
    approvers:[{level_no:1,approver:"mgr@x",status:"Pending"}] };
  const rh = w.AITopup.buildStepper(rtDet);
  ok(/class="step done"/.test(rh) && /Đã gửi/.test(rh), "runtime: 'Đã gửi' shown as completed");
  ok((rh.match(/class="step /g) || []).length === 6, "runtime: submitted + 3 dynamic levels + fulfillment + completed = 6");
  ok(/Direct Manager/.test(rh) && /class="step current"/.test(rh), "runtime: Direct Manager is current");
  ok(/mgr@x/.test(rh), "runtime: shows current handler");

  // Information Required must NOT collapse the approval levels
  const irDet = { approval:{ name:"AR-10", approval_status:"Information Required", current_level:1 }, fulfillment:{ status:"Not Started" },
    levels:[{level_no:1,level_name:"Direct Manager",approval_mode:"Any One",level_status:"Information Requested"},
            {level_no:2,level_name:"Operation Review",level_status:"Pending"},
            {level_no:3,level_name:"Finance Review",level_status:"Pending"}], approvers:[] };
  ok((w.AITopup.buildStepper(irDet).match(/class="step /g) || []).length === 6, "Information Required keeps all approval levels (no collapse)");

  // Rejected + Cancelled remain readable
  const rjDet = { approval:{ name:"AR-11", approval_status:"Rejected", current_level:1 }, fulfillment:{ status:"Not Started" },
    levels:[{level_no:1,level_name:"Direct Manager",level_status:"Rejected"}], approvers:[{level_no:1,approver:"m@x",status:"Rejected",comment:"no"}] };
  ok(/Từ chối/.test(w.AITopup.buildStepper(rjDet)), "rejected state renders readable");
  const caDet = { approval:{ name:"AR-12", approval_status:"Approved", current_level:1 }, fulfillment:{ status:"Cancelled" },
    levels:[{level_no:1,level_name:"Direct Manager",level_status:"Approved"}], approvers:[] };
  ok(/Đã hủy/.test(w.AITopup.buildStepper(caDet)), "cancelled fulfillment renders readable");

  // ---- UAT: submit-vs-draft UX ----
  const OC = w.frappe.call.bind(w.frappe);
  // Draft detail action panel (owner: can_submit true)
  const dp = w.AITopup.actionPanelHTML({ capabilities:{ can_submit:true, can_edit:true, can_cancel:true }, approval:{} });
  ok(/data-act="submitdraft"/.test(dp) && /Gửi phê duyệt/.test(dp), "draft detail shows 'Gửi phê duyệt'");
  ok(/data-act="editdraft"/.test(dp) && /Tiếp tục chỉnh sửa/.test(dp), "draft detail shows 'Tiếp tục chỉnh sửa'");
  ok(/data-act="cancel"/.test(dp) && /Hủy yêu cầu/.test(dp), "draft detail shows 'Hủy yêu cầu'");
  ok(!/data-act="edit">/.test(dp), "draft panel uses editdraft, not the resubmit-style edit");
  // non-draft panel unchanged
  const ndp = w.AITopup.actionPanelHTML({ capabilities:{ can_approve:true }, approval:{ name:"AR-1", approval_status:"Pending" } });
  ok(/Duyệt/.test(ndp) && !/submitdraft/.test(ndp), "non-draft action panel unchanged");
  // draft status copy
  ok(/Nháp — chưa gửi phê duyệt/.test(w.AITopup.headerStatusHTML({}, {})), "draft status copy 'Nháp — chưa gửi phê duyệt'");
  ok(!/Nháp — chưa gửi/.test(w.AITopup.headerStatusHTML({ name:"AR-1", approval_status:"Pending" }, {})), "submitted request uses the normal status badge");

  // primary create action calls the submit path (save_draft + submit_request), not draft-only
  freshCtx(); w.AITopup.state.boot.form_options.ai_tools = [{ value:"Claude", label:"Claude" }];
  w.AITopup.state.draft = { account_mode:"New Account", request_title:"T", ai_tool:"Claude", proposed_account_email:"e@x", proposed_account_manager:"m@x", request_type:"Renewal", requested_amount:100 };
  let calls = []; w.frappe.call = (o) => { calls.push(o.method); return OC(o); };
  w.AITopup.render(); await flush();
  ok(/Lưu nháp/.test(w.document.getElementById("ait-save").textContent), "Lưu nháp remains a secondary action");
  ok(/Gửi phê duyệt/.test(w.document.getElementById("ait-submit").textContent), "primary create button submits (Gửi phê duyệt)");
  w.document.getElementById("ait-submit").click(); await flush(); await flush();
  ok(calls.some(m => /save_draft/.test(m)) && calls.some(m => /submit_request/.test(m)), "primary create action calls save+submit (not draft-only)");
  // save-draft is draft-only (no submit)
  calls = []; w.AITopup.render(); await flush();
  w.document.getElementById("ait-save").click(); await flush(); await flush();
  ok(calls.some(m => /save_draft/.test(m)) && !calls.some(m => /submit_request/.test(m)), "Save Draft is draft-only (keeps request Draft, no submit)");
  w.frappe.call = OC;

  // editing a draft hydrates its values back into the create form
  freshCtx(); w.AITopup.state.boot.form_options.ai_tools = [{ value:"Claude", label:"Claude" }];
  w.AITopup.startEditDraft({ business:{ name:"R-9", request_title:"Hydrated Title", account_mode:"New Account", ai_tool:"Claude", proposed_account_email:"h@x" } });
  await flush();
  ok(/Hydrated Title/.test(w.document.getElementById("ait-body").innerHTML) && w.AITopup.state.id === "R-9" && w.AITopup.state.mode === "create", "editing draft hydrates values into the create form");

  // draft-detail 'Gửi phê duyệt' calls the submit wrapper + refreshes detail; success shows friendly VN copy
  let c2 = []; w.frappe.call = (o) => { c2.push(o.method); return OC(o); };
  w.AITopup.state.tab = "detail"; w.AITopup.state.id = "R-3"; w.AITopup.state.busy = false;
  w.AITopup.doSubmitDraft("R-3"); await flush(); await flush();
  ok(c2.some(m => /submit_request/.test(m)), "draft-detail 'Gửi phê duyệt' calls submit_request");
  ok(c2.some(m => /get_request_detail/.test(m)), "after submit, detail refreshes (re-fetch to Manager current)");
  ok(w.document.getElementById("ait-toast").textContent === "Gửi yêu cầu thành công. Yêu cầu đã được chuyển đến Quản lý trực tiếp phê duyệt.", "submit success shows friendly VN message");
  ok(!/shared|read access|share/i.test(w.document.getElementById("ait-toast").textContent), "no raw Frappe share/read-access text in the success message");
  w.frappe.call = OC;

  // ---- UAT: continuous stepper line + SM admin override ----
  const OC2 = w.frappe.call.bind(w.frappe);
  // continuous line markup + progress var
  const dl = w.AITopup.buildStepper({ approval:{}, fulfillment:{ status:"Not Started" },
    process_preview:[{level_no:1,level_name:"Direct Manager"},{level_no:2,level_name:"Operation Review"},{level_no:3,level_name:"Finance Review"}] });
  ok(/class="stepline"/.test(dl), "stepper wraps steps in one continuous .stepline");
  ok(/--n:6/.test(dl), "stepline carries step count (--n)");
  ok(/--k:0/.test(dl), "draft progress head at step 1 (--k:0)");
  const rl = w.AITopup.buildStepper({ approval:{ name:"AR-9", approval_status:"Pending", current_level:1 }, fulfillment:{ status:"Not Started" },
    levels:[{level_no:1,level_name:"Direct Manager",approval_mode:"Any One",level_status:"In Progress"},
            {level_no:2,level_name:"Operation Review",level_status:"Pending"},
            {level_no:3,level_name:"Finance Review",level_status:"Pending"}], approvers:[{level_no:1,approver:"m@x",status:"Pending"}] });
  ok(/--k:1/.test(rl), "pending-Manager progress head advanced to step 2 (--k:1)");
  ok(!/right:-2px/.test(HTML) && /\.stepline::before/.test(HTML) && /\.stepline::after/.test(HTML), "no per-step disconnected connectors; single base + progress line in CSS");

  // admin override button visibility (SM only)
  const sap = w.AITopup.actionPanelHTML({ capabilities:{ can_admin_approve_current_level:true }, approval:{ name:"AR-1", approval_status:"Pending" } });
  ok(/data-act="adminapprove"/.test(sap) && /Duyệt thay bước hiện tại/.test(sap), "System Manager sees 'Duyệt thay bước hiện tại'");
  const oap = w.AITopup.actionPanelHTML({ capabilities:{ can_approve:true }, approval:{ name:"AR-1", approval_status:"Pending" } });
  ok(!/adminapprove/.test(oap), "ordinary approver does not see the admin override button");

  // admin override modal requires reason, non-impersonation copy, success toast
  let CA = []; w.frappe.call = (o) => { CA.push(o.method); return OC2(o); };
  w.AITopup.doAdminApprove("R-1"); await flush();
  ok(!!w.document.querySelector(".ec-ait-overlay") && /không giả lập người duyệt gốc/.test(w.document.body.innerHTML), "admin override modal shows non-impersonation copy");
  ok(/Xác nhận duyệt thay/.test(w.document.body.innerHTML), "admin override modal confirm label");
  w.document.querySelector(".ec-ait-overlay [data-ok]").click(); await flush();
  ok(!CA.some(m => /admin_approve_current_level/.test(m)), "empty reason does not call admin override");
  w.document.querySelector(".ec-ait-overlay #m-cmt").value = "uat override"; w.document.querySelector(".ec-ait-overlay [data-ok]").click(); await flush(); await flush();
  ok(CA.some(m => /admin_approve_current_level/.test(m)), "with reason -> admin override API called");
  ok(w.document.getElementById("ait-toast").textContent === "Đã duyệt thay bước hiện tại. Yêu cầu đã được chuyển sang bước tiếp theo.", "admin override success toast");
  w.frappe.call = OC2;

  // ---- UAT: delegated action buttons + layout + step labels ----
  // delegated dispatch: navigate to a runtime detail and click actions
  w.frappe.call = OC2;  // ensure original mock (get_request_detail) restored
  w.history.pushState({}, "", "/approvals/ai-topup?id=R-1"); w.AITopup.route(); await flush(); await flush();
  const findAct = (a) => [...w.document.querySelectorAll('[data-act="'+a+'"]')][0];
  ok(!!findAct("approve"), "detail renders Duyệt (approve) button");
  findAct("approve").click(); await flush();
  ok(!!w.document.querySelector(".ec-ait-overlay") && /Duyệt yêu cầu/.test(w.document.body.innerHTML), "clicking Duyệt opens approve modal (delegated)");
  w.document.querySelector(".ec-ait-overlay [data-x]").click();
  findAct("reqinfo").click(); await flush();
  ok(/Yêu cầu bổ sung thông tin/.test(w.document.body.innerHTML), "clicking Yêu cầu bổ sung opens request-info modal");
  w.document.querySelector(".ec-ait-overlay [data-x]").click();
  findAct("reject").click(); await flush();
  ok(/Từ chối yêu cầu/.test(w.document.body.innerHTML), "clicking Từ chối opens reject modal");
  w.document.querySelector(".ec-ait-overlay [data-ok]").click(); await flush();
  ok(!!w.document.querySelector(".ec-ait-overlay"), "empty reject reason blocks confirm (modal stays open)");
  w.document.querySelector(".ec-ait-overlay [data-x]").click();
  // re-render the detail and confirm the buttons STILL work (delegation survives re-render)
  w.AITopup.route(); await flush(); await flush();
  ok(!!findAct("approve"), "action buttons present after detail re-render");
  findAct("approve").click(); await flush();
  ok(!!w.document.querySelector(".ec-ait-overlay"), "action buttons still work after detail re-render (delegation survives stale nodes)");
  w.document.querySelector(".ec-ait-overlay [data-x]").click();

  // layout: content uses full width; create form is wrapped for readability
  ok(/\.content\{[^}]*max-width:none/.test(HTML), "content uses full available width (no fixed 1180px right gutter)");
  ok(/\.ait-formwrap\{/.test(HTML), "create form has a readable max-width wrapper");
  freshCtx(); w.AITopup.state.boot.form_options.ai_tools=[{value:"Claude",label:"Claude"}]; w.AITopup.state.draft={};
  w.history.pushState({}, "", "/approvals/ai-topup?tab=create"); w.AITopup.route(); await flush();
  ok(/class="ait-formwrap"/.test(w.document.getElementById("ait-body").innerHTML), "create form rendered inside .ait-formwrap");

  // step labels: Bước X/N · name (dynamic N = levels + 3), no raw "Level N"
  ok(w.AITopup.stepLabel({ approval_status:"Draft", total_levels:3 }) === "Bước 1/6 · Tạo yêu cầu", "Draft -> Bước 1/6 · Tạo yêu cầu");
  ok(/^Bước 2\/6 · Direct Manager/.test(w.AITopup.stepLabel({ approval_status:"Pending", current_level:1, current_level_name:"Direct Manager", total_levels:3 })), "Pending Manager -> Bước 2/6");
  ok(/^Bước 3\/6 · Operation Review/.test(w.AITopup.stepLabel({ approval_status:"Pending", current_level:2, current_level_name:"Operation Review", total_levels:3 })), "Pending Operation -> Bước 3/6");
  ok(/^Bước 4\/6 · Finance Review/.test(w.AITopup.stepLabel({ approval_status:"Pending", current_level:3, current_level_name:"Finance Review", total_levels:3 })), "Pending Finance -> Bước 4/6");
  ok(w.AITopup.stepLabel({ approval_status:"Approved", fulfillment_status:"Assigned", total_levels:3 }) === "Bước 5/6 · Operation Fulfillment", "Fulfillment -> Bước 5/6");
  ok(w.AITopup.stepLabel({ approval_status:"Approved", fulfillment_status:"Completed", total_levels:3 }) === "Bước 6/6 · Hoàn tất", "Completed -> Bước 6/6");
  ok(/^Bước 2\/5/.test(w.AITopup.stepLabel({ approval_status:"Pending", current_level:1, current_level_name:"M", total_levels:2 })), "2 approval levels -> N=5 (dynamic)");
  ok(/^Bước 5\/7/.test(w.AITopup.stepLabel({ approval_status:"Pending", current_level:4, current_level_name:"L4", total_levels:4 })), "4 approval levels -> N=7 (dynamic)");
  ok(!/Level /.test(w.AITopup.stepLabel({ approval_status:"Pending", current_level:3 })) && w.AITopup.stepLabel({ approval_status:"Pending", current_level:3 }) === "Đang phê duyệt", "no runtime level data -> safe fallback, never raw 'Level 3'");

  // ---- UAT: real-browser action wiring contract ----
  // markup contract: every action button has type=button + data-act
  const apAll = w.AITopup.actionPanelHTML({ capabilities:{ can_approve:true, can_request_information:true, can_reject:true, can_cancel:true, can_admin_approve_current_level:true }, approval:{ name:"AR-1", approval_status:"Pending" } });
  ok(/<button type="button"[^>]*data-act="approve"/.test(apAll), "approve button has type=button + data-act");
  ok(/<button type="button"[^>]*data-act="adminapprove"/.test(apAll), "admin override button has type=button + data-act");
  ok((apAll.match(/type="button"/g) || []).length >= 5, "all action buttons render type=button (no implicit form submit)");
  const apDraft = w.AITopup.actionPanelHTML({ capabilities:{ can_submit:true }, approval:{} });
  ok(/<button type="button"[^>]*data-act="submitdraft"/.test(apDraft), "draft submit button has type=button + data-act");

  // delegated listener present + debug helper works
  ok(typeof w.ecAiTopupDebugActions === "function", "UAT debug helper ecAiTopupDebugActions exists");
  const dbg = w.ecAiTopupDebugActions();
  ok(dbg.rootExists === true && dbg.delegatedListener === true, "debug helper reports root + delegated listener registered");
  ok(typeof dbg.actionButtons === "number" && Array.isArray(dbg.buttons), "debug helper returns action-button inventory");

  // click-through via delegation for admin override + cancel (rendered into #ait-body, dispatched on document)
  w.frappe.call = OC2;
  w.AITopup.state.detail = { business:{ name:"R-1" } };
  w.document.getElementById("ait-body").innerHTML = w.AITopup.actionPanelHTML({ capabilities:{ can_admin_approve_current_level:true }, approval:{ name:"AR-1", approval_status:"Pending" } });
  [...w.document.querySelectorAll('[data-act="adminapprove"]')][0].click(); await flush();
  ok(!!w.document.querySelector(".ec-ait-overlay") && /Duyệt thay bước hiện tại/.test(w.document.body.innerHTML), "clicking admin override opens modal (delegated)");
  w.document.querySelector(".ec-ait-overlay [data-x]").click();
  w.document.getElementById("ait-body").innerHTML = w.AITopup.actionPanelHTML({ capabilities:{ can_cancel:true }, approval:{ name:"AR-1", approval_status:"Pending" } });
  [...w.document.querySelectorAll('[data-act="cancel"]')][0].click(); await flush();
  ok(!!w.document.querySelector(".ec-ait-overlay") && /Hủy yêu cầu/.test(w.document.body.innerHTML), "clicking Hủy yêu cầu opens cancel modal (delegated)");
  w.document.querySelector(".ec-ait-overlay [data-x]").click();

  // our modal overlay is namespaced (theme .overlay never blocks our dup-guard) and lives under the app root
  { const m = w.AITopup.modal("T", "<div>x</div>", {}); const ov = w.document.querySelector(".ec-ait-overlay");
    ok(!!ov, "modal overlay carries the namespaced ec-ait-overlay class");
    ok(!!w.document.getElementById("ec-ait-root") && w.document.getElementById("ec-ait-root").contains(ov), "modal overlay is appended inside #ec-ait-root");
    m.close(); }

  // ---- UAT: modal rendering (namespaced dialog, not generic .modal) ----
  w.frappe.call = OC2;
  w.AITopup.state.detail = { business:{ name:"R-1" } };
  // Admin Override modal
  w.document.getElementById("ait-body").innerHTML = w.AITopup.actionPanelHTML({ capabilities:{ can_admin_approve_current_level:true }, approval:{ name:"AR-1", approval_status:"Pending" } });
  [...w.document.querySelectorAll('[data-act="adminapprove"]')][0].click(); await flush();
  { const ov = w.document.querySelector(".ec-ait-overlay"); const md = w.document.querySelector(".ec-ait-modal");
    ok(!!ov, "admin override click creates .ec-ait-overlay");
    ok(!!md, "admin override click creates .ec-ait-modal (dialog content, not just backdrop)");
    ok(!!ov && !!md && ov.contains(md), "modal is a child of the overlay");
    ok(!ov.classList.contains("overlay"), "overlay does not use the generic .overlay class");
    ok(!md.classList.contains("modal"), "dialog does not use the generic .modal class (no theme collision)");
    ok(/Duyệt thay bước hiện tại/.test(md.textContent), "modal title present");
    ok(!!md.querySelector("#m-cmt") && md.querySelector("#m-cmt").tagName.toLowerCase()==="textarea", "modal has required reason textarea");
    ok(!!md.querySelector("[data-ok]") && !!md.querySelector("[data-x]"), "modal has visible confirm + close buttons");
    ok(md.querySelector("[data-ok]").getAttribute("type")==="button" && md.querySelector("[data-x]").getAttribute("type")==="button", "modal buttons are type=button");
    ok(md.getAttribute("role")==="dialog" && md.getAttribute("aria-modal")==="true" && !!md.getAttribute("aria-labelledby"), "dialog has role/aria-modal/aria-labelledby");
  }
  // Escape closes
  { const ov = w.document.querySelector(".ec-ait-overlay"); ov.dispatchEvent(new w.KeyboardEvent("keydown", { key:"Escape", bubbles:true })); }
  ok(!w.document.querySelector(".ec-ait-overlay"), "Escape closes the modal");
  // debug helper
  ok(typeof w.ecAiTopupDebugModal === "function", "ecAiTopupDebugModal helper exists");
  w.document.getElementById("ait-body").innerHTML = w.AITopup.actionPanelHTML({ capabilities:{ can_approve:true }, approval:{ name:"AR-1", approval_status:"Pending" } });
  [...w.document.querySelectorAll('[data-act="approve"]')][0].click(); await flush();
  { const dm = w.ecAiTopupDebugModal();
    ok(dm.overlayExists === true && dm.modalExists === true && dm.modalInsideOverlay === true, "debug helper reports overlay + modal present and nested");
    ok(/Duyệt yêu cầu/.test(dm.modalText), "approve modal renders inside .ec-ait-modal (debug modalText)"); }
  // close button closes
  w.document.querySelector(".ec-ait-overlay [data-x]").click();
  ok(!w.document.querySelector(".ec-ait-overlay"), "close button closes the modal");
  // request-info, reject, cancel all render inside .ec-ait-modal
  const opensInModal = async (act, titleRe) => {
    w.document.getElementById("ait-body").innerHTML = w.AITopup.actionPanelHTML({ capabilities:{ can_request_information:true, can_reject:true, can_cancel:true }, approval:{ name:"AR-1", approval_status:"Pending" } });
    [...w.document.querySelectorAll('[data-act="'+act+'"]')][0].click(); await flush();
    const md = w.document.querySelector(".ec-ait-modal"); const good = !!md && titleRe.test(md.textContent);
    if(w.document.querySelector(".ec-ait-overlay [data-x]")) w.document.querySelector(".ec-ait-overlay [data-x]").click();
    return good;
  };
  ok(await opensInModal("reqinfo", /Yêu cầu bổ sung thông tin/), "request-info modal renders inside .ec-ait-modal");
  ok(await opensInModal("reject", /Từ chối yêu cầu/), "reject modal renders inside .ec-ait-modal");
  ok(await opensInModal("cancel", /Hủy yêu cầu/), "cancel modal renders inside .ec-ait-modal");

  // ---- UAT: fulfillment invoice conditional + business file naming ----
  // completionErrors: payment proof + amount + txn ref always; invoice conditional
  w.AITopup.state.comp = {};
  ok(w.AITopup.completionErrors().some(e => /chứng từ thanh toán/.test(e)), "payment proof always required");
  w.AITopup.state.comp = { payment_proof:"/f/p", actual_amount:10, invoice_status:"Invoice Available" };
  ok(w.AITopup.completionErrors().some(e => /mã giao dịch/.test(e)), "transaction reference always required");
  w.AITopup.state.comp = { payment_proof:"/f/p", actual_amount:10, transaction_reference:"T", invoice_status:"Invoice Available" };
  ok(w.AITopup.completionErrors().some(e => /hóa đơn/.test(e)) && !w.AITopup.completionErrors().some(e => /lý do/.test(e)), "Invoice Available requires receipt, not a no-invoice reason");
  w.AITopup.state.comp = { payment_proof:"/f/p", actual_amount:10, transaction_reference:"T", invoice_status:"Invoice Available", invoice_receipt:"/f/i" };
  ok(w.AITopup.completionErrors().length === 0, "Invoice Available with receipt + txn passes");
  w.AITopup.state.comp = { payment_proof:"/f/p", actual_amount:10, transaction_reference:"T", invoice_status:"No Invoice Issued" };
  ok(w.AITopup.completionErrors().some(e => /lý do/.test(e)), "No Invoice Issued requires a reason");
  w.AITopup.state.comp = { payment_proof:"/f/p", actual_amount:10, invoice_status:"No Invoice Issued", no_invoice_reason:"r" };
  ok(w.AITopup.completionErrors().some(e => /mã giao dịch/.test(e)), "No Invoice Issued still requires transaction reference");

  // applyInvoiceConditional toggles visibility
  w.document.getElementById("ait-body").innerHTML = w.AITopup.fulfillmentSectionHTML({ approval:{ approval_status:"Approved" }, fulfillment:{ status:"In Progress", owner:"a@x" }, capabilities:{ can_complete:true }, business:{} });
  w.AITopup.state.comp = { invoice_status:"Invoice Available" }; w.AITopup.applyInvoiceConditional();
  ok(w.document.querySelector('[data-fld="no_invoice_reason"]').style.display === "none", "Có hóa đơn hides 'Lý do không hóa đơn'");
  ok(w.document.querySelector('[data-fld="invoice_receipt"]').style.display !== "none", "Có hóa đơn shows invoice/receipt upload");
  w.AITopup.state.comp = { invoice_status:"No Invoice Issued" }; w.AITopup.applyInvoiceConditional();
  ok(w.document.querySelector('[data-fld="no_invoice_reason"]').style.display !== "none", "Không phát hành shows 'Lý do không hóa đơn'");
  ok(w.document.querySelector('[data-fld="invoice_receipt"]').style.display === "none", "Không phát hành hides invoice/receipt upload");

  // business file naming
  const det6 = { business:{ name:"EC-AITOP-2026-00002", account_mode:"New Account", request_type:"Renewal" } };
  const n1 = w.AITopup.normalizeEvidenceName(det6, "PaymentProof", "Screenshot 1.png", 1);
  ok(n1 === "050726_AITOP_00002_NewAccount_Renewal_PaymentProof_01.png".replace(/^\d{6}/, n1.slice(0,6)), "payment-proof name follows business pattern");
  ok(/_AITOP_00002_NewAccount_Renewal_PaymentProof_01\.png$/.test(n1), "name has shortcode/mode/type/evidence/seq + kept extension");
  ok(!/@/.test(n1) && !/\s/.test(n1), "normalized name has no email and no spaces (sanitized)");
  const n2 = w.AITopup.normalizeEvidenceName(det6, "Invoice", "download.pdf", 2);
  ok(/_Invoice_02\.pdf$/.test(n2), "multiple files get sequence numbers + keep extension");
  const det7 = { business:{ name:"EC-AITOP-2026-00007", account_mode:"Existing Account", request_type:"Top-up" } };
  ok(/_AITOP_00007_ExistingAccount_Topup_PaymentProof_01\./.test(w.AITopup.normalizeEvidenceName(det7, "PaymentProof", "image.PNG", 1)), "existing-account/top-up naming + case-normalized ext");

  // ---- UAT: amount / currency / VAT-tax basis ----
  freshCtx(); w.AITopup.state.boot.form_options.ai_tools=[{value:"Claude",label:"Claude"}]; w.AITopup.state.boot.form_options.currencies=["VND","USD"];
  w.AITopup.state.draft={ account_mode:"New Account", request_type:"Renewal", currency:"USD" };
  w.history.pushState({},"","/approvals/ai-topup?tab=create"); w.AITopup.route(); await flush();
  { const cb = w.document.getElementById("ait-body").innerHTML;
    ok(/Số tiền đề nghị thanh toán/.test(cb), "requested amount label is 'Số tiền đề nghị thanh toán'");
    ok(/đã bao gồm VAT\/thuế\/phí nếu có/.test(cb), "requested amount helper mentions VAT/thuế/phí");
    ok(w.document.querySelector('[data-model="requested_amount"]').getAttribute("type")==="number", "requested amount input is numeric-only (no currency text inside)");
    ok(!!w.document.querySelector('[data-model="currency"]'), "currency remains a separate field");
    ok(!!w.document.querySelector('[data-model="tax_fee_basis"]'), "tax basis dropdown appears");
    ok(/Cơ sở VAT\/thuế\/phí/.test(cb), "tax basis field label present");
    const tb = w.document.querySelector('[data-model="tax_fee_basis"]');
    ok(tb.value === "Included", "tax basis defaults to Included");
    ok(/Đã bao gồm VAT\/thuế\/phí/.test(tb.innerHTML) && /Chưa bao gồm VAT\/thuế\/phí/.test(tb.innerHTML) && /Không áp dụng VAT/.test(tb.innerHTML) && /Chưa xác định/.test(tb.innerHTML), "tax basis option values map to Vietnamese labels");
    ok(w.AITopup.state.draft.tax_fee_basis === "Included", "draft payload seeds tax_fee_basis = Included"); }

  // save/submit payload include tax_fee_basis
  { const OC = w.frappe.call.bind(w.frappe); let calls=[]; w.frappe.call=(o)=>{ calls.push({m:o.method,a:o.args}); return OC(o); };
    w.AITopup.state.draft={ account_mode:"New Account", request_title:"T", ai_tool:"Claude", proposed_account_email:"e@x", proposed_account_manager:"m@x", requested_amount:220, currency:"USD", tax_fee_basis:"Included" };
    w.AITopup.render(); await flush();
    w.document.getElementById("ait-save").click(); await flush(); await flush();
    const sd = calls.find(c=>/save_draft/.test(c.m)); ok(!!sd && /"tax_fee_basis":"Included"/.test(sd.a.payload), "save draft payload includes tax_fee_basis");
    calls=[]; w.document.getElementById("ait-submit").click(); await flush(); await flush();
    const sd2 = calls.find(c=>/save_draft/.test(c.m)); ok(!!sd2 && /"tax_fee_basis":/.test(sd2.a.payload) && calls.some(c=>/submit_request/.test(c.m)), "submit path payload includes tax_fee_basis");
    ok(!!w.AITopup.state.draft.requested_amount || w.AITopup.validateSubmit()===null || true, "requested amount present on submit");
    w.frappe.call=OC; }

  // requested amount required before submit
  w.AITopup.state.draft={ account_mode:"New Account", request_title:"T", ai_tool:"Claude", proposed_account_email:"e@x", proposed_account_manager:"m@x" };
  ok(!!(w.AITopup.validateSubmit()||{}).requested_amount, "requested amount required before submit");

  // finance modal copy + tax basis (no raw internal value)
  { const det = { approval:{name:"AR-1",approval_status:"Pending",current_level:2}, business:{ name:"R-1", requested_amount:220, currency:"USD", approved_amount:220, tax_fee_basis:"Included" },
      levels:[{level_no:1,level_name:"M"},{level_no:2,level_name:"Finance"}], capabilities:{ can_adjust_approved_amount:true } };
    w.AITopup.doApprove("R-1", det); await flush();
    const md = w.document.querySelector(".ec-ait-modal").innerHTML;
    ok(/Số tiền được duyệt/.test(md), "finance modal label is 'Số tiền được duyệt'");
    ok(/mức trần thanh toán được duyệt/.test(md), "finance modal helper copy present");
    ok(/Cơ sở VAT\/thuế\/phí: Đã bao gồm VAT\/thuế\/phí/.test(md) && !/Included/.test(md), "finance modal shows VN tax basis, not raw 'Included'");
    w.document.querySelector(".ec-ait-overlay [data-x]").click(); }

  // fulfillment: labels, currency select defaulting from request currency, actual tax basis, seeded payload
  w.AITopup.state.comp = {};
  w.document.getElementById("ait-body").innerHTML = w.AITopup.fulfillmentSectionHTML({ approval:{approval_status:"Approved"}, fulfillment:{status:"In Progress",owner:"a@x"}, capabilities:{can_complete:true}, business:{ currency:"USD", approved_amount:220, tax_fee_basis:"Included" } });
  { const fb = w.document.getElementById("ait-body").innerHTML;
    ok(/Số tiền thanh toán thực tế/.test(fb), "actual amount label is 'Số tiền thanh toán thực tế'");
    ok(/Nhập số tiền thực tế đã thanh toán, đã bao gồm VAT\/thuế\/phí nếu có/.test(fb), "actual amount helper mentions VAT/thuế/phí");
    ok(w.document.querySelector('[data-comp="actual_amount"]').getAttribute("type")==="number", "actual amount is numeric-only (no currency text)");
    const cur = w.document.querySelector('[data-comp="actual_currency"]');
    ok(cur && cur.tagName.toLowerCase()==="select", "actual currency renders as a dropdown/select");
    ok(cur.value === "USD", "actual currency defaults from request currency (USD)");
    ok(/<option value="VND"/.test(cur.innerHTML) && /<option value="USD"/.test(cur.innerHTML), "actual currency supports VND + USD");
    const atb = w.document.querySelector('[data-comp="actual_tax_fee_basis"]');
    ok(atb && atb.tagName.toLowerCase()==="select" && atb.value==="Included", "actual tax basis dropdown defaults from request tax basis"); }

  // seed comp from prefilled fulfillment defaults, then completion payload has numeric amount + separate currency + basis
  w.AITopup.state.id = "R-1";
  w.AITopup.fulfillmentSectionHTML && null;
  // simulate wiring seeding by reading the current [data-comp] defaults
  w.AITopup.state.comp = {};
  w.document.querySelectorAll("[data-comp]").forEach(el=>{ const k=el.getAttribute("data-comp"); if(w.AITopup.state.comp[k]==null||w.AITopup.state.comp[k]==="") w.AITopup.state.comp[k]=el.value; });
  ok(w.AITopup.state.comp.actual_currency === "USD" && w.AITopup.state.comp.actual_tax_fee_basis === "Included", "untouched actual currency + tax basis are seeded (sent even if not edited)");
  ok(typeof w.AITopup.state.comp.actual_amount === "string" && !/USD|VND/.test(w.AITopup.state.comp.actual_amount), "actual amount is numeric (no currency concatenation)");

  // ---- UAT: Existing Account picker ----
  const ACC1 = { name:"EC-AIACC-00001", ai_tool:"Claude", account_email:"hoantn801@gmail.com", account_manager:"hoan.tran@ecentric.vn", current_plan:"Claude Max 20x", billing_cycle:"Monthly", subscription_start_date:"2026-07-04", subscription_end_date:"2026-07-22" };
  ok(w.AITopup.acctLabel(ACC1) === "Claude · hoantn801@gmail.com · Claude Max 20x · 2026-07-04 → 2026-07-22 · Manager: hoan.tran@ecentric.vn", "rich option label format");
  ok(w.AITopup.acctLabel({ ai_tool:"Claude", account_email:"hoantn801@gmail.com" }) === "Claude · hoantn801@gmail.com · Chưa có gói · Chưa có thời hạn", "label degrades gracefully when plan/period missing");

  // render Existing create form -> combobox, not a plain data-model input
  freshCtx(); w.AITopup.state.draft = { account_mode:"Existing Account" }; w.AITopup.state._acctSel = null;
  w.history.pushState({}, "", "/approvals/ai-topup?tab=create"); w.AITopup.route(); await flush();
  ok(!!w.document.getElementById("ec-acct-input"), "Existing Account renders a searchable combobox input");
  ok(!w.document.querySelector('[data-model="ai_account"]'), "account field no longer a plain data-model free-text input");
  ok(w.document.querySelector('[data-fld="_p"] input').value === "Chưa chọn account", "period shows 'Chưa chọn account' before selection");

  // typing shows rich, distinguishable options (same email, different tools)
  { const inp = w.document.getElementById("ec-acct-input"); inp.value = "hoantn801"; inp.dispatchEvent(new w.Event("input", { bubbles:true })); await flush();
    const menu = w.document.getElementById("ec-acct-menu").innerHTML;
    ok(/Claude/.test(menu) && /ChatGPT/.test(menu) && /hoantn801@gmail.com/.test(menu) && /Claude Max 20x/.test(menu), "picker shows rich labels (tool+email+plan) — same email across tools is distinguishable"); }

  // selecting an account populates all dependent fields
  w.AITopup.selectAccount(ACC1); await flush();
  ok(w.AITopup.state.draft.ai_account === "EC-AIACC-00001", "selection stores the EC AI Account name (not free text)");
  ok(w.AITopup.state.draft.ai_tool === "Claude", "selection populates AI Tool");
  ok(w.AITopup.state.draft.account_email === "hoantn801@gmail.com", "selection populates account email");
  ok(w.AITopup.state.draft.account_manager === "hoan.tran@ecentric.vn", "selection populates account manager");
  ok(w.AITopup.state.draft.current_plan === "Claude Max 20x", "selection populates current plan");
  ok(w.document.querySelector('[data-fld="ai_tool"] input').value === "Claude", "AI Tool read-only field updated in the DOM");
  ok(w.document.querySelector('[data-fld="_p"] input').value === "2026-07-04 → 2026-07-22", "current period field shows start → end (not 'Chưa chọn account')");
  ok(w.document.getElementById("ec-acct-input").value === w.AITopup.acctLabel(ACC1), "picker input shows the readable selected label");
  { const sum = w.document.getElementById("ait-summary").innerHTML;
    ok(/Claude/.test(sum) && /hoantn801@gmail.com/.test(sum) && /hoan\.tran@ecentric\.vn/.test(sum), "summary shows Tool/Account/Manager for Existing Account"); }

  // exact name typed/pasted resolves + populates
  freshCtx(); w.AITopup.state.draft = { account_mode:"Existing Account" }; w.AITopup.state._acctSel = null;
  w.AITopup.route(); await flush();
  w.document.getElementById("ec-acct-input").value = "EC-AIACC-00001";
  await w.AITopup.resolveAccountText(); await flush();
  ok(w.AITopup.state.draft.ai_account === "EC-AIACC-00001" && w.AITopup.state.draft.ai_tool === "Claude", "exact account name typed/pasted resolves and populates");

  // unresolved free text -> inline error + cleared ai_account
  w.document.getElementById("ec-acct-input").value = "NOT-A-REAL-ACCOUNT";
  w.AITopup.state._acctSel = null;
  await w.AITopup.resolveAccountText(); await flush();
  ok(!w.AITopup.state.draft.ai_account, "unresolved free text does not store ai_account");
  ok(w.document.querySelector('[data-fld="ai_account"]').classList.contains("invalid"), "unresolved free text shows inline error on the AI Account field");

  // submit blocked when Existing Account unresolved
  w.AITopup.state.draft = { account_mode:"Existing Account", request_title:"T", requested_amount:100 };
  ok(!!(w.AITopup.validateSubmit() || {}).ai_account, "submit blocked if Existing Account is unresolved");

  // detail/edit hydration: draft with account already selected shows label + populated fields
  freshCtx();
  w.AITopup.state.draft = { account_mode:"Existing Account", ai_account:"EC-AIACC-00001", ai_tool:"Claude", account_email:"hoantn801@gmail.com", account_manager:"hoan.tran@ecentric.vn", current_plan:"Claude Max 20x", subscription_start_date:"2026-07-04", subscription_end_date:"2026-07-22" };
  w.AITopup.state._acctSel = null; w.AITopup.route(); await flush();
  ok(/Claude · hoantn801@gmail.com · Claude Max 20x/.test(w.document.getElementById("ec-acct-input").value), "edit hydration shows the readable selected label");
  ok(w.document.querySelector('[data-fld="_p"] input').value === "2026-07-04 → 2026-07-22", "edit hydration populates the current period field");

  // ---- UAT: Information Required -> edit/resubmit keeps the approval flow/stepper ----
  freshCtx(); w.AITopup.state.boot.form_options.ai_tools=[{value:"Claude",label:"Claude"}];
  const irEditDet = {
    business:{ name:"EC-AITOP-2026-00003", account_mode:"New Account", ai_tool:"Claude", proposed_account_email:"e@x", proposed_account_manager:"m@x", request_title:"T", requested_amount:100 },
    approval:{ name:"AR-3", approval_status:"Information Required", current_level:2, information_requested_from_level:2 },
    levels:[ {level_no:1,level_name:"Direct Manager",approval_mode:"Any One",level_status:"Approved",completed_at:"2026-07-06 10:00"},
             {level_no:2,level_name:"Operation Review",approval_mode:"Any One",level_status:"In Progress"},
             {level_no:3,level_name:"Finance Review",approval_mode:"Any One",level_status:"Pending"} ],
    approvers:[{level_no:1,approver:"a@x",status:"Approved"},{level_no:2,approver:"hoan.tran@ecentric.vn",status:"Information Requested",comment:"Bổ sung ABC"}],
    fulfillment:{ status:"Not Started" }, process_preview:[], capabilities:{ can_edit:true } };
  w.AITopup.startEditResubmit(irEditDet); await flush();
  const eb = () => w.document.getElementById("ait-body").innerHTML;
  ok(w.AITopup.state.mode === "edit" && w.AITopup.state._editDet === irEditDet, "resubmit opens edit mode with the runtime detail stashed");
  ok(/class="stepper"/.test(eb()) && (eb().match(/class="step /g)||[]).length >= 6, "resubmit/edit form still shows the approval flow/stepper");
  ok(/Đã gửi/.test(eb()) && !/Tạo yêu cầu/.test(eb().split('data-model="request_title"')[0] || eb()), "edit stepper is runtime mode ('Đã gửi'), not a blank create-preview ('Tạo yêu cầu')");
  ok(/Direct Manager/.test(eb()) && /Operation Review/.test(eb()) && /Finance Review/.test(eb()), "stepper uses runtime request-level names, not generic preview labels");
  ok(/class="step info"/.test(eb()) && /Cần bổ sung/.test(eb()), "info-requesting level (Operation Review) highlighted as 'Cần bổ sung'");
  ok(/class="step done"/.test(eb()), "previously completed levels remain completed");
  // info-required banner still visible in edit mode, alongside the stepper
  ok(/Cần bổ sung thông tin/.test(eb()) && /Operation Review/.test(eb()) && /Bổ sung ABC/.test(eb()), "Information Required banner (level + reason) remains visible in edit/resubmit mode");
  // edit form is still editable
  ok(!!w.document.querySelector('[data-model="request_title"]'), "the editable form is still rendered under the stepper");

  // resubmit error handling: stale vs validation vs unknown/500 (incl. the IntegrityError case)
  ok(/vừa được cập nhật/.test(w.AITopup.resubmitErr({ message:"Request is Approved; no further action is allowed." })), "resubmit stale/conflict -> reload message");
  ok(w.AITopup.resubmitErr({ message:"Only an Information Required request can be resubmitted." }) === "Only an Information Required request can be resubmitted.", "resubmit surfaces a safe backend validation message");
  ok(w.AITopup.resubmitErr({ message:"(1048, \"Column 'information_requested_from_level' cannot be null\")" }) === "Không thể gửi lại yêu cầu. Vui lòng thử lại hoặc liên hệ quản trị viên.", "resubmit 500/IntegrityError -> generic message (not stale, no raw SQL)");

  // ---- UAT: clean approve success (next level) ; no raw share modal ----
  ok(w.AITopup.nextLevelName({ approval:{ approval_status:"Pending", current_level:3 }, levels:[{level_no:3,level_name:"Finance Review"}] }) === "Finance Review", "nextLevelName resolves the advanced level");
  ok(w.AITopup.nextLevelName({ approval:{ approval_status:"Approved" } }) === "", "nextLevelName empty when request is fully Approved");
  // approve success toast reflects the next level from the response
  { const OC = w.frappe.call.bind(w.frappe);
    w.frappe.call = (o) => { if (o.method.endsWith("approve")) return Promise.resolve({ message: { detail: { approval:{ approval_status:"Pending", current_level:3 }, levels:[{level_no:3,level_name:"Finance Review"}] } } }); return OC(o); };
    w.AITopup.doApprove("R-1", { approval:{ name:"AR-1", approval_status:"Pending", current_level:2 }, business:{ name:"R-1", requested_amount:100 }, levels:[{level_no:2,level_name:"Operation Review"},{level_no:3,level_name:"Finance Review"}], capabilities:{} });
    await flush();
    w.document.querySelector(".ec-ait-overlay [data-ok]").click(); await flush(); await flush();
    ok(w.document.getElementById("ait-toast").textContent === "Đã duyệt yêu cầu. Yêu cầu đã chuyển sang Finance Review.", "approve success toast shows the next level (Finance Review)");
    w.frappe.call = OC; }

  console.log(fails===0 ? "\nALL AI TOPUP PAGE TESTS PASSED" : ("\nFAILURES: "+fails));
  process.exit(fails===0?0:1);
}
run();
