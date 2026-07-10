// Headless tests for the upgraded /approvals/dashboard (ECharts-based). Node + jsdom.
// ECharts itself isn't loaded in jsdom; we stub window.ECCharts to record options + click
// handlers, so we can verify chart config, drill-down wiring and instance safety without a canvas.
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "approvals_dashboard.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-approval-dashboard">');
const JS = rest.replace(/<\/script>\s*$/, "");

let fails = 0;
function ok(c, n){ if(c){ console.log("  ok:", n); } else { console.log("  FAIL:", n); fails++; } }
const flush = () => new Promise(r => setTimeout(r, 5));

const OPTIONS = { scope_mode:"admin", can_export:true, categories:["FINANCE_BUDGET"],
  types:[{v:"PAYMENT_REQUEST",label:"Payment Request"}], departments:["Finance - EC"],
  statuses:["Draft","Pending","Information Required","Completed","Rejected","Cancelled"],
  sla_states:["breached","configured_policy","operational_default","unavailable"] };
const DASH = {
  kpis:{ total:42, pending:7, completed:30, rejected:3, cancelled:2, information_required:1, sla_breached:2, avg_approval_seconds:93600, avg_approval_sample:30 },
  comparison:{ total:{current:42,previous:35,delta:7,pct:20,direction:"up"},
    pending:{current:7,previous:10,delta:-3,pct:-30,direction:"down"},
    completed:{current:30,previous:24,delta:6,pct:25,direction:"up"},
    rejected:{current:3,previous:2,delta:1,pct:50,direction:"up"},
    avg_approval_seconds:{current:93600,previous:72000,delta:21600,pct:30,direction:"up"},
    completion_rate:{current:71,previous:80,delta:-9,pct:-11,direction:"down"} },
  status_distribution:[{status:"Completed",count:30},{status:"Pending",count:7},{status:"Rejected",count:3}],
  status_mix:{ total:42, segments:[{status:"Completed",count:30,percent:71.4},{status:"Pending",count:7,percent:16.7},{status:"Rejected",count:3,percent:7.1}] },
  volume_trend:{ granularity:"day", buckets:[
    {label:"2026-07-01",total:5,completed:3,pending:1,rejected:1},
    {label:"2026-07-02",total:8,completed:6,pending:2,rejected:0}] },
  sla_compliance:{ compliant:5, breached:2, configured_policy:3, operational_default:4, unavailable:0, trend:[{label:"2026-07-01",compliant_pct:80},{label:"2026-07-02",compliant_pct:100}] },
  pending_by_type:[{label:"Payment Request",count:5,approval_type:"PAYMENT_REQUEST"}],
  pending_by_department:[{label:"Finance - EC",count:4}],
  pending_by_approver:[{label:"lien.vu@x",count:12,oldest_pending_seconds:500000},{label:"hof@x",count:3,oldest_pending_seconds:80000}],
  department_performance:[{department:"Finance - EC",volume:20,avg_duration_seconds:90000,breaches:2}],
  aging_buckets:[{bucket:"<1d",count:2},{bucket:"1-2d",count:2},{bucket:"3-5d",count:1},{bucket:">5d",count:2}],
  bottleneck_levels:[{level:"Finance review",volume:9,avg_completed_seconds:180000,median_seconds:150000,p90_seconds:400000,avg_pending_seconds:90000,active_pending:2,overdue_count:1,trend_pct:15.0}],
  funnel:[{stage:"Đã gửi",count:42},{stage:"Đang duyệt",count:7},{stage:"Cần bổ sung",count:1},{stage:"Hoàn tất",count:30},{stage:"Từ chối/Hủy",count:5}],
  longest_pending:[],
  attention:[
    { name:"EC-APR-2026-00007", type:"Payment Request", approval_type:"PAYMENT_REQUEST", requester:"a@x", department:"Finance - EC", status:"Pending", status_label:"Pending", current_level:2, current_level_name:"Finance review", submitted_at:"2026-07-01 09:00:00", pending_age_seconds:520000, sla_source:"operational_default", sla_due_at:"2026-07-02 09:00:00", sla_breached:true, detail_route:"/approvals/payment-request?id=PAYR-0007" },
    { name:"EC-APR-2026-00008", type:"Payment Request", approval_type:"PAYMENT_REQUEST", requester:"b@x", department:"Finance - EC", status:"Information Required", status_label:"Information Required", current_level:1, current_level_name:"Direct Manager", submitted_at:"2026-07-05 09:00:00", pending_age_seconds:100000, sla_source:"configured_policy", sla_due_at:"", sla_breached:false, detail_route:"/approvals/payment-request?id=PAYR-0008" } ],
  insights:[
    {code:"pending_swing",severity:"warning",statement:"Hồ sơ chờ xử lý giảm -30% so với kỳ trước.",metric:"10 → 7",filter:{status:"Pending",view:"open"}},
    {code:"top_breach_department",severity:"critical",statement:"Phòng ban 'Finance - EC' đang dẫn đầu về số hồ sơ quá hạn SLA.",metric:"2 hồ sơ quá hạn",filter:{department:"Finance - EC",sla_state:"breached",view:"open"}} ],
  scope_mode:"admin"
};
const TIMELINE = { header:{name:"EC-APR-2026-00007",approval_type:"PAYMENT_REQUEST",approval_status:"Pending",reference_doctype:"EC Payment Request",reference_name:"PAYR-0007"},
  actions:[{seq:1,actor:"a@x",action:"Submitted",comment:"",action_time:"2026-07-01 09:00:00",new_status:"Pending"},
           {seq:2,actor:"mgr@x",action:"Approved",comment:"ok",action_time:"2026-07-01 12:00:00",new_status:"Pending"}] };

function stubECharts(w){
  const captured = {};   // elId -> {options:[], handlers:{}}
  function rec(el){ const id=el.id; captured[id]=captured[id]||{options:[],handlers:{}}; return captured[id]; }
  w.ECCharts = {
    ok:()=>true,
    setOption:(el,opt,notMerge)=>{ const r=rec(el); r.options.push(opt); r.lastNotMerge=notMerge; return {}; },
    ensure:(el)=>{ const r=rec(el); return { on:(e,cb)=>{ r.handlers[e]=cb; }, off:()=>{ r.handlers={}; } }; },
    attachResize:()=>{}, dispose:()=>{}, disposeAll:()=>{}
  };
  w.ECChartTheme = { palette:()=>["#2C3DA6","#10b981","#FFC000","#EF7CAF","#dc2626","#6b7280"], tooltip:(x)=>Object.assign({trigger:"item"},x||{}) };
  return captured;
}
function mockFrappe(w, over){ const calls=[]; w.frappe={ call:(o)=>{ calls.push(o); const m=o.method.split(".").pop();
  if(over&&over[m]) return over[m](o);
  if(m==="get_filter_options") return Promise.resolve({message:OPTIONS});
  if(m==="get_dashboard") return Promise.resolve({message:DASH});
  if(m==="get_request_timeline") return Promise.resolve({message:TIMELINE});
  return Promise.resolve({message:{}}); } }; return calls; }
function boot(){ const dom=new JSDOM('<!DOCTYPE html><html><body>'+markup+'</body></html>',{runScripts:"outside-only",pretendToBeVisual:true,url:"https://x.test/approvals/dashboard"}); return { dom, w:dom.window }; }

async function run(){
  ok(/web-footer[^}]*display:none/.test(HTML), "ERPNext footer hidden (no 'Powered by ERPNext')");
  ok(/\.chart-box\{[^}]*height:260px/.test(HTML), "chart-box has fixed height (charts don't overflow)");
  ok(/\.card\{[^}]*overflow:hidden/.test(HTML), "cards clip overflow");
  ok(/assets\/ecentric_workspace\/charts\/vendor\/echarts\.min\.js/.test(HTML), "loads bundled ECharts from app assets (not a CDN)");
  ok(!/<script[^>]+src="https?:\/\/[^"]*(chart|echarts)/i.test(HTML), "chart lib not loaded from a public CDN");
  ok(!/EC-APR-2026-00007/.test(markup), "no hardcoded request data in page source");

  let { w } = boot(); const cap = stubECharts(w); let calls = mockFrappe(w);
  w.eval(JS); await flush(); await flush(); await flush();
  ok(!!w.ApprovalDashboard, "window.ApprovalDashboard exposed");
  ok(calls.some(c=>c.method.endsWith("get_dashboard")), "calls governed get_dashboard");

  // KPI + comparison deltas
  ok(w.document.querySelectorAll('.kpi').length===6, "6 KPI cards");
  ok(w.document.querySelectorAll('.kpi .delta').length>=4, "KPI comparison deltas rendered");
  ok(/vs kỳ trước/.test(w.document.body.textContent), "delta labeled vs previous period");

  // insights
  ok(w.document.querySelectorAll('#apd-insights .ins').length===2, "insights panel renders rule-based insights");
  ok(!!w.document.querySelector('#apd-insights .ins.critical'), "insight severity classes applied");

  // charts drawn via ECCharts.setOption (one per chart element)
  ["apd-trend","apd-statusmix","apd-sla","apd-aging","apd-approver","apd-dept","apd-funnel"].forEach(function(id){
    ok(cap[id] && cap[id].options.length>=1, "chart drawn: "+id);
  });
  ok(cap["apd-trend"].lastNotMerge===true, "setOption uses notMerge=true (dispose-safe update)");

  // option content correctness (built deterministically)
  const O = w.ApprovalDashboard.buildOptions(DASH);
  ok(O.trend.series.length===4, "trend is a 4-series multi-line chart");
  ok(O.statusmix.series[0].type==="pie", "status mix is a doughnut/pie");
  ok(O.funnel.series[0].type==="funnel", "funnel uses ECharts funnel type");
  ok(O.dept.series[0].type==="scatter", "department performance is scatter/bubble");
  ok(O.approver.series[0].type==="bar", "approver workload is a bar chart");

  // chart drill-down: status-mix click sets filter + reloads
  { let before=calls.length; cap["apd-statusmix"].handlers.click({data:{_status:"Pending"}}); await flush(); await flush();
    ok(calls.length>before, "status-mix click triggers governed reload");
    ok(w.document.getElementById("f-status").value==="Pending", "status-mix click set status filter"); }

  // aging click -> client-side table filter (governed rows only)
  { cap["apd-aging"] && cap["apd-aging"].handlers.click({data:{_bucket:">5d"}}); await flush();
    const rows=w.document.querySelectorAll('#apd-table tbody tr');
    ok(rows.length===1 && /EC-APR-2026-00007/.test(rows[0].textContent), "aging '>5d' click filters action table client-side"); }

  // action table: default order breached-first + signal + quick filters
  { const first=w.document.querySelector('#apd-table tbody tr'); ok(/Quá hạn/.test(first.textContent), "action table orders SLA-breached first"); }
  ok(w.document.querySelectorAll('#apd-tabs .qbtn').length===4, "4 action-table quick filters");
  ok(/Chờ Finance review|Chờ bổ sung|Quá hạn SLA/.test(w.document.querySelector('#apd-table .signal').textContent), "signal column present");

  // quick filter: Information Required
  { const infoBtn=Array.prototype.find.call(w.document.querySelectorAll('#apd-tabs .qbtn'),b=>/Cần bổ sung/.test(b.textContent));
    infoBtn.click(); await flush();
    const rows=w.document.querySelectorAll('#apd-table tbody tr');
    ok(rows.length===1 && /EC-APR-2026-00008/.test(rows[0].textContent), "quick filter 'Cần bổ sung' shows only Information Required"); }

  // drawer (read-only timeline)
  { const codeLink=w.document.querySelector('#apd-table a[data-drawer]'); codeLink.click(); await flush(); await flush();
    ok(calls.some(c=>c.method.endsWith("get_request_timeline")), "row opens governed timeline drawer");
    ok(!!w.document.querySelector('.drawer-ov .tl'), "drawer renders lifecycle timeline");
    ok(!/Traceback/.test(w.document.body.textContent), "no raw traceback in drawer"); }

  // insight drill-down applies governed filter
  { let before=calls.length; const ins=w.document.querySelector('#apd-insights .ins.clickable'); ins.click(); await flush(); await flush();
    ok(calls.length>before, "clicking an insight applies a governed drill-down"); }

  // reload re-renders charts safely (update path -> setOption called again)
  { const before=cap["apd-statusmix"].options.length; w.document.getElementById("apd-apply").click(); await flush(); await flush(); await flush();
    ok(cap["apd-statusmix"].options.length>before, "filter change re-renders chart via setOption (safe update)"); }

  // empty + error states
  { let { w:w2 }=boot(); stubECharts(w2); mockFrappe(w2,{ get_dashboard:()=>Promise.resolve({message:Object.assign({},DASH,{attention:[]})}) });
    w2.eval(JS); await flush(); await flush(); await flush();
    ok(/Không có hồ sơ cần chú ý/.test(w2.document.body.textContent), "friendly empty state for action table"); }
  { let { w:w3 }=boot(); stubECharts(w3); w3.frappe={ call:(o)=>o.method.endsWith("get_dashboard")?Promise.reject(new Error("boom")):Promise.resolve({message:OPTIONS}) };
    w3.eval(JS); await flush(); await flush(); await flush();
    ok(/Không tải được dữ liệu/.test(w3.document.body.textContent) && !/boom|Traceback/.test(w3.document.body.textContent), "friendly error state, no traceback"); }

  // graceful degrade when ECharts absent (no crash, fallback text)
  { let { w:w4 }=boot(); mockFrappe(w4); /* no ECCharts */ w4.eval(JS); await flush(); await flush(); await flush();
    ok(w4.document.querySelectorAll('.kpi').length===6, "renders KPIs/table even if ECharts unavailable");
    ok(!!w4.document.querySelector('.chart-fb'), "chart fallback message shown when ECharts missing"); }

  console.log(fails===0 ? "\nALL APPROVALS DASHBOARD PAGE TESTS PASSED" : "\n"+fails+" FAILURE(S)");
  process.exit(fails===0?0:1);
}
run();
