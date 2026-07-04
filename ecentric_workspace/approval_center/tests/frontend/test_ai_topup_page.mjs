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
      is_system_manager:false, form_options:{ai_tools:[{value:"T",label:"Tool"}],currencies:["VND"],account_modes:["Existing Account","New Account"],request_types:["Top-up"],billing_cycles:["Monthly"]} } });
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
  var mm=w.AITopup.modal("T","<div>x</div>",{}); ok(!!w.document.querySelector(".overlay"), "modal opens overlay"); mm.close(); ok(!w.document.querySelector(".overlay"), "modal closes");
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
  { var m=w.AITopup.modal("T","<input id=zz>",{}); ok(!!w.document.querySelector('.modal[role="dialog"][aria-modal="true"]'),"modal has role=dialog aria-modal"); m.close(); }
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
  w.AITopup.state.draft = { account_mode:"New Account", request_title:"T", ai_tool:"Claude", proposed_account_email:"e@x", proposed_account_manager:"m@x" };
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

  console.log(fails===0 ? "\nALL AI TOPUP PAGE TESTS PASSED" : ("\nFAILURES: "+fails));
  process.exit(fails===0?0:1);
}
run();
