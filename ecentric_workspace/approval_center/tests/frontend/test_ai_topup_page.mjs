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

  console.log(fails===0 ? "\nALL AI TOPUP PAGE TESTS PASSED" : ("\nFAILURES: "+fails));
  process.exit(fails===0?0:1);
}
run();
