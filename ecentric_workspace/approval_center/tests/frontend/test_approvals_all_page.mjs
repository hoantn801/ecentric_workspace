// Headless tests for /approvals/all-requests (Node + jsdom). Governed cross-form list.
import { JSDOM } from "jsdom";
import { pageSource } from "./_page_source.mjs";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = pageSource("all_requests");
const [markup, rest] = HTML.split('<script id="ec-approval-all">');
const JS = rest.replace(/<\/script>\s*$/,"");
let fails=0; function ok(c,n){ if(c) console.log("  ok:",n); else { console.log("  FAIL:",n); fails++; } }
const flush=()=>new Promise(r=>setTimeout(r,5));
const OPTIONS={ scope_mode:"admin", categories:["FINANCE_BUDGET"], types:[{v:"PAYMENT_REQUEST",label:"Payment Request"}], departments:["Finance - EC"], statuses:["Draft","Pending","Information Required","Completed","Rejected","Cancelled"] };
function page(rows,total){ return { rows, total, start:0, page_length:50, scope_mode:"admin" }; }
const ROWS=[
  { name:"EC-APR-2026-00007", type:"Payment Request", approval_type:"PAYMENT_REQUEST", requester:"a@x", department:"Finance - EC", status:"Pending", status_label:"Pending", current_level:2, current_level_name:"Finance review", submitted_at:"2026-07-01 09:00:00", sla_breached:true, detail_route:"/approvals/payment-request?id=PAYR-0007" },
  { name:"EC-APR-2026-00008", type:"Leave", approval_type:"LEAVE_REQUEST", requester:"b@x", department:"Ops", status:"Completed", status_label:"Completed", current_level:0, current_level_name:"", submitted_at:"2026-07-05 09:00:00", sla_breached:false, detail_route:"/approvals/leave?id=LV-1" }];
function mockFrappe(w, over){ const calls=[]; w.frappe={ call:(o)=>{ calls.push(o); const m=o.method.split(".").pop();
  if(over&&over[m]) return over[m](o);
  if(m==="get_filter_options") return Promise.resolve({message:OPTIONS});
  if(m==="list_requests") return Promise.resolve({message:page(ROWS,2)});
  return Promise.resolve({message:{}}); } }; return calls; }
function boot(){ const dom=new JSDOM('<!DOCTYPE html><html><body>'+markup+'</body></html>',{runScripts:"outside-only",pretendToBeVisual:true,url:"https://x.test/approvals/all-requests"}); return {dom,w:dom.window}; }

async function run(){
  ok(/data-ec-shell="1"/.test(HTML), "opts into shared ec-shell (sidebar consistent)");
  ok(/ec-shell-crumb-current">Tất cả yêu cầu/.test(HTML), "shell breadcrumb = Tất cả yêu cầu");
  ok(/ec-shell-active" href="\/approvals\/all-requests"/.test(HTML), "nav active on this page");
  ok(!/EC-APR-2026-00007/.test(markup), "no hardcoded request data in page");

  let { w }=boot(); let calls=mockFrappe(w); w.eval(JS); await flush(); await flush();
  ok(!!w.ApprovalAll, "window.ApprovalAll exposed");
  ok(calls.some(c=>c.method.endsWith("list_requests")), "calls governed list_requests");
  ok(/Toàn tổ chức/.test(w.document.getElementById("apl-scope").textContent), "scope badge shows resolved mode");
  const rows=w.document.querySelectorAll('#apl-body tbody tr');
  ok(rows.length===2, "renders request rows");
  ok(/Quá hạn/.test(rows[0].textContent), "SLA-breached flagged");
  ok(/1–2 \/ 2/.test(w.document.querySelector('#apl-body .pager .info').textContent), "pagination info shows range/total");
  ok(!!w.document.querySelector('#apl-body a.open-link[href="/approvals/payment-request?id=PAYR-0007"]'), "row links to existing form detail route");

  // pagination: next disabled when all shown
  ok(w.document.getElementById("apl-next").disabled, "next disabled when total fits one page");

  // pagination next fires when more pages
  { let { w:w2 }=boot(); const c2=mockFrappe(w2,{ list_requests:()=>Promise.resolve({message:{rows:ROWS,total:120,start:0,page_length:50,scope_mode:"admin"}}) });
    w2.eval(JS); await flush(); await flush();
    const nx=w2.document.getElementById("apl-next"); ok(nx && !nx.disabled, "next enabled when more pages");
    const before=c2.length; nx.click(); await flush();
    const last=c2[c2.length-1]; ok(last.method.endsWith("list_requests") && last.args.start===50, "next requests start=50"); }

  // search triggers governed reload with search term
  { let before=calls.length; const s=w.document.getElementById("f-search"); s.value="payr";
    s.dispatchEvent(new w.KeyboardEvent("keydown",{key:"Enter"})); await flush(); await flush();
    const last=calls[calls.length-1]; ok(last.method.endsWith("list_requests") && last.args.search==="payr", "search Enter passes search term to governed API"); }

  // apply passes filters
  { w.document.getElementById("f-status").value="Pending"; let before=calls.length;
    w.document.getElementById("apl-apply").click(); await flush(); await flush();
    const last=calls[calls.length-1]; const f=JSON.parse(last.args.filters||"{}");
    ok(f.status==="Pending", "apply passes status filter to governed API"); }

  // empty + error
  { let { w:w3 }=boot(); mockFrappe(w3,{ list_requests:()=>Promise.resolve({message:page([],0)}) }); w3.eval(JS); await flush(); await flush();
    ok(/Không có yêu cầu/.test(w3.document.body.textContent), "friendly empty state"); }
  { let { w:w4 }=boot(); w4.frappe={ call:(o)=>o.method.endsWith("list_requests")?Promise.reject(new Error("boom")):Promise.resolve({message:OPTIONS}) };
    w4.eval(JS); await flush(); await flush();
    ok(/Không tải được dữ liệu/.test(w4.document.body.textContent) && !/boom|Traceback/.test(w4.document.body.textContent), "friendly error, no traceback"); }

  console.log(fails===0?"\nALL APPROVALS ALL PAGE TESTS PASSED":"\n"+fails+" FAIL");
  process.exit(fails===0?0:1);
}
run();
