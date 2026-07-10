// Headless behavior tests for /approvals/dashboard (Node + jsdom).
// Verifies eCentric shell, filters, KPI cards, charts, action table, drill-down and states.
// The frontend is NOT the security boundary; it renders only what the governed API returns.
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

const OPTIONS = { scope_mode:"admin", can_export:true,
  categories:["FINANCE_BUDGET","HR"], types:[{v:"PAYMENT_REQUEST",label:"Payment Request"}],
  departments:["Finance - EC"], statuses:["Draft","Pending","Information Required","Completed","Rejected","Cancelled"],
  sla_states:["breached","configured_policy","operational_default","unavailable"] };
const DASH = {
  kpis:{ total:42, pending:7, completed:30, rejected:3, cancelled:2, information_required:1, sla_breached:2, avg_approval_seconds:93600, avg_approval_sample:30 },
  status_distribution:[{status:"Completed",count:30},{status:"Pending",count:7},{status:"Rejected",count:3}],
  pending_by_type:[{label:"Payment Request",count:5,approval_type:"PAYMENT_REQUEST"}],
  pending_by_department:[{label:"Finance - EC",count:4}],
  pending_by_approver:[{label:"lien.vu@x",count:3}],
  aging_buckets:[{bucket:"<1d",count:2},{bucket:"1-2d",count:3},{bucket:"3-5d",count:1},{bucket:">5d",count:1}],
  bottleneck_levels:[{level:"Finance review",avg_completed_seconds:180000,avg_pending_seconds:90000,completed_sample:9,pending_count:2}],
  longest_pending:[],
  attention:[
    { name:"EC-APR-2026-00007", type:"Payment Request", approval_type:"PAYMENT_REQUEST", requester:"a@x",
      department:"Finance - EC", status:"Pending", status_label:"Pending", current_level:2, current_level_name:"Finance review",
      submitted_at:"2026-07-01 09:00:00", pending_age_seconds:520000, sla_source:"operational_default",
      sla_breached:true, detail_route:"/approvals/payment-request?id=PAYR-0007" },
    { name:"EC-APR-2026-00008", type:"Payment Request", approval_type:"PAYMENT_REQUEST", requester:"b@x",
      department:"Finance - EC", status:"Information Required", status_label:"Information Required", current_level:1,
      current_level_name:"Direct Manager", submitted_at:"2026-07-05 09:00:00", pending_age_seconds:100000,
      sla_source:"configured_policy", sla_breached:false, detail_route:"/approvals/payment-request?id=PAYR-0008" }
  ],
  scope_mode:"admin"
};

function mockFrappe(w, over){
  const calls = [];
  w.frappe = { call: (opts) => { calls.push(opts);
    const m = opts.method.split(".").pop();
    if(over && over[m]) return over[m](opts);
    if(m === "get_filter_options") return Promise.resolve({ message: OPTIONS });
    if(m === "get_dashboard") return Promise.resolve({ message: DASH });
    if(m === "drilldown") return Promise.resolve({ message: { rows: [], scope_mode:"admin" } });
    return Promise.resolve({ message: {} });
  }};
  return calls;
}
function boot(){
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts:"outside-only", pretendToBeVisual:true, url:"https://x.test/approvals/dashboard" });
  return { dom, w: dom.window };
}

async function run(){
  // shell + no ERPNext footer
  ok(/\.web-footer[^}]*display:none/.test(HTML) || /web-footer.*display:none/.test(HTML), "ERPNext footer hidden (no 'Powered by ERPNext')");
  ok(/ec-sidebar/.test(HTML) && /Approval Center/.test(HTML), "eCentric shell + Approval Center breadcrumb present");
  ok(!/EC-APR-2026-00007/.test(markup), "no hardcoded request data in page source (data-driven)");

  // loading -> success
  let { w } = boot();
  let calls = mockFrappe(w);
  w.eval(JS); await flush(); await flush(); await flush();
  ok(!!w.ApprovalDashboard, "window.ApprovalDashboard exposed");
  ok(calls.some(c=>c.method.endsWith("get_filter_options")), "calls get_filter_options");
  ok(calls.some(c=>c.method.endsWith("get_dashboard")), "calls get_dashboard");

  // scope badge
  ok(/Toàn tổ chức/.test(w.document.getElementById("apd-scope").textContent), "scope badge shows resolved mode (admin)");

  // filters populated from options
  ok(w.document.querySelectorAll('#f-type option').length === 2, "type filter populated from options");
  ok(w.document.querySelectorAll('#f-status option').length === 7, "status filter populated (6 + All)");

  // KPI cards
  const kpis = w.document.querySelectorAll('.kpi');
  ok(kpis.length === 6, "6 KPI cards render");
  ok(/42/.test(w.document.querySelector('.kpis').textContent), "Total KPI value rendered");
  ok(/2/.test(w.document.querySelector('.kpi.breach').textContent), "SLA Breached KPI highlighted");
  ok(/26|ngày|giờ/.test(w.document.querySelector('.kpis').textContent), "Average approval time formatted");

  // charts (bars)
  ok(w.document.querySelectorAll('.card .bar-row').length >= 6, "chart bars render across cards");
  ok(/Tồn đọng theo phòng ban/.test(w.document.body.textContent), "pending-by-department chart present");
  ok(/Phân bố tuổi hồ sơ/.test(w.document.body.textContent), "aging buckets chart present");
  ok(/Điểm nghẽn/.test(w.document.body.textContent), "bottleneck section present");

  // action table
  const rows = w.document.querySelectorAll('#apd-attention tbody tr');
  ok(rows.length === 2, "action table renders attention rows");
  ok(/Quá hạn/.test(rows[0].textContent), "SLA-breached row flagged");
  ok(!!w.document.querySelector('#apd-attention a.open-link[href="/approvals/payment-request?id=PAYR-0007"]'),
     "row 'Open' links to existing form detail route (no duplicate detail UI)");

  // drill-down: clicking Pending KPI applies a governed filter and reloads
  { let before = calls.length;
    const pendingKpi = Array.prototype.find.call(w.document.querySelectorAll('.kpi'), e => /Chờ xử lý/.test(e.textContent));
    pendingKpi.click(); await flush(); await flush();
    ok(calls.length > before, "clicking a KPI triggers a governed reload (drill-down)");
    ok(w.document.getElementById("f-status").value === "Pending", "KPI drill-down set the status filter"); }

  // chart drill-down: clicking a status bar sets filter
  { let before = calls.length;
    const bar = w.document.querySelector('.bar-row[data-filter]');
    bar.click(); await flush(); await flush();
    ok(calls.length > before, "clicking a chart bar triggers a governed reload"); }

  // empty state
  { let { w:w2 } = boot();
    mockFrappe(w2, { get_dashboard: () => Promise.resolve({ message: Object.assign({}, DASH, { attention:[], pending_by_type:[] }) }) });
    w2.eval(JS); await flush(); await flush(); await flush();
    ok(/Không có hồ sơ cần chú ý/.test(w2.document.body.textContent), "friendly empty state for action table"); }

  // error state (no raw traceback)
  { let { w:w3 } = boot();
    w3.frappe = { call: (o) => o.method.endsWith("get_dashboard") ? Promise.reject(new Error("boom")) : Promise.resolve({ message: OPTIONS }) };
    w3.eval(JS); await flush(); await flush(); await flush();
    ok(/Không tải được dữ liệu/.test(w3.document.body.textContent), "friendly error state");
    ok(!/boom|Traceback/.test(w3.document.body.textContent), "no raw error/traceback leaked"); }

  console.log(fails === 0 ? "\nALL APPROVALS DASHBOARD PAGE TESTS PASSED" : "\n" + fails + " FAILURE(S)");
  process.exit(fails === 0 ? 0 : 1);
}
run();
