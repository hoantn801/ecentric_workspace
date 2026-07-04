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
    if (o.method.endsWith("get_request_detail")) return Promise.resolve({ message: { business:{name:"R-1",ai_tool:"T",requested_amount:100,currency:"VND"}, approval:{approval_status:"Pending",current_level:2}, fulfillment:{status:"Not Started"},
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
  const det2 = { approval:{approval_status:"Pending",current_level:1}, fulfillment:{status:"Not Started"},
    levels:[{level_no:1,level_name:"Direct Manager",approval_mode:"Any One",level_status:"In Progress"},
            {level_no:2,level_name:"Finance",approval_mode:"Any One",level_status:"Pending"}],
    approvers:[{level_no:1,approver:"a@x",status:"Pending"},{level_no:1,approver:"b@x",status:"Pending"}] };
  const html2 = w.AITopup.buildStepper(det2);
  ok((html2.match(/class="step /g)||[]).length === 5, "2 levels -> 5 stepper steps (dynamic)");
  ok(/a@x hoặc b@x/.test(html2), "Any One shows eligible approvers with 'hoặc'");

  // 4 levels -> 7 steps (no hardcoded three)
  const det4 = { approval:{approval_status:"Pending",current_level:1}, fulfillment:{status:"Not Started"},
    levels:[1,2,3,4].map(n=>({level_no:n,level_name:"L"+n,approval_mode:"Any One",level_status:"Pending"})), approvers:[] };
  ok((w.AITopup.buildStepper(det4).match(/class="step /g)||[]).length === 7, "4 levels -> 7 steps");

  // approved level shows actual approver + skipped others
  const detS = { approval:{approval_status:"Pending",current_level:2}, fulfillment:{status:"Not Started"},
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
  ok((cbody().match(/class="rm-step"/g) || []).length === 6, "roadmap has exactly 6 steps");
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

  console.log(fails===0 ? "\nALL AI TOPUP PAGE TESTS PASSED" : ("\nFAILURES: "+fails));
  process.exit(fails===0?0:1);
}
run();
