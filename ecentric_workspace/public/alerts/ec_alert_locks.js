// Copyright (c) 2026, eCentric and contributors
// Alert Center - trang Locks /alerts/locks. Asset cua app tu 29/09/2026 (brief NHIEU_LOP/brief_alert_center.md);
// truoc do nam inline trong Web Page duoi dang <script id="ec-alert-locks">.
// Trang nap file nay qua /assets/ecentric_workspace/alerts/ec_alert_locks.js?v=<sha>. Sua file nay thi chay
//   python -m ecentric_workspace.alerts.site_pages.assets --stamp
// roi bump BASELINE_SHA256 cua trang doi + them patch resync (test bat neu quen).
(function(){
"use strict";
var A=window.AL,$=A.$;
var S={start:0,pageLen:50,total:0,scope:null,rows:[],pauses:[],current:null};
var DS1="&#8212;(DS1)";
function ds1(v){return (v==null||v===""||v===0)?DS1:A.esc(A.money(v));}
// Truthful review labels: review_action performs NO Omisell write (DS1 gate
// closed), so an "Approved" record is approved FOR SIMULATION only - never a
// live inventory lock. Raw enum kept in the title tooltip.
var RV_LABEL={"Pending Review":"Ch\u1edd duy\u1ec7t","Approved":"Duy\u1ec7t cho m\u00f4 ph\u1ecfng","Rejected":"T\u1eeb ch\u1ed1i"};
function rvBadge(v){return v?('<span class="al-badge '+({"Pending Review":"al-b-pending","Approved":"al-b-active","Rejected":"al-b-critical"}[v]||"al-b-info")+'" title="'+A.esc(v)+'">'+A.esc(RV_LABEL[v]||v)+'</span>'):"-";}
// Truthful outcome labels for the action's processing status. DS1 is closed and
// no executor is wired to this UI, so every state here is a SIMULATION. "Live"
// is reserved for a future real executor and only when backend proof exists
// (no such proof today) - current DS1-disabled records always read Simulation.
var SS_LABEL={"Dry Run":"M\u00f4 ph\u1ecfng","Success":"M\u00f4 ph\u1ecfng ho\u00e0n t\u1ea5t","Pending":"Ch\u1edd x\u1eed l\u00fd","Processing":"\u0110ang x\u1eed l\u00fd","Skipped":"B\u1ecf qua","Failed":"L\u1ed7i (m\u00f4 ph\u1ecfng)","Cancelled":"\u0110\u00e3 hu\u1ef7"};
function ssStatusBadge(r){var s=r.status;var cls={"Dry Run":"al-b-dryrun","Pending":"al-b-pending","Skipped":"al-b-skipped","Success":"al-b-resolved","Failed":"al-b-critical","Cancelled":"al-b-ignored","Processing":"al-b-pending"}[s]||"al-b-info";return '<span class="al-badge '+cls+'" title="'+A.esc(s||"-")+'">'+A.esc(SS_LABEL[s]||s||"-")+'</span>';}
function filters(){var f={};[["f-brand","brand"],["f-review_status","review_status"],["f-status","status"]].forEach(function(p){var v=$(p[0]).value;if(v)f[p[1]]=v;});
var sku=$("f-sku").value.trim();if(sku)f.seller_sku=sku;return f;}
// 29/09/2026 (NHIEU_LOP): 4 the KPI + bang hang doi ve cung MOT loi goi api_actions.lock_queue
// (truoc: list_actions x5 moi lan, va init chay 3 lot -> 14 lan tren live).
var KPI_IDS={"Pending Review":"lk-c-pending","Approved":"lk-c-approved","Rejected":"lk-c-rejected","Skipped":"lk-c-skipped"};
function paintCounts(c){if(!c)return;Object.keys(KPI_IDS).forEach(function(k){if(c[k]!=null)$(KPI_IDS[k]).textContent=c[k];});}
function load(){S.loaded=true;var tb=$("lk-rows");tb.innerHTML='<tr><td colspan="12" class="al-empty">\u0110ang t\u1ea3i...</td></tr>';
A.call("api_actions.lock_queue",{filters:filters(),start:S.start,page_len:S.pageLen}).then(function(res){S.rows=res.rows;S.total=res.total;paintCounts(res.counts);
if(!res.rows.length){tb.innerHTML='<tr><td colspan="12" class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</td></tr>';}
else{tb.innerHTML=res.rows.map(function(r,i){return '<tr data-i="'+i+'">'+
'<td>'+A.esc(r.name)+'</td><td>'+A.esc(r.alert||"-")+'</td><td>'+A.esc(r.brand)+'</td><td>'+A.esc(r.platform||"-")+'</td><td>'+A.esc(r.shop||"-")+'</td><td>'+A.esc(r.seller_sku||r.item||"-")+'</td>'+
'<td>'+ds1(r.locked_quantity)+'</td><td>'+A.esc(A.dt(r.lock_until))+'</td><td>'+A.esc(r.release_strategy||"-")+'</td>'+
'<td>'+rvBadge(r.review_status)+'</td><td>'+A.esc(r.reviewed_by?(r.reviewed_by+" "+A.dt(r.reviewed_at)):"-")+'</td><td>'+ssStatusBadge(r)+'</td></tr>';}).join("");}
var from=S.total?S.start+1:0;$("lk-count").textContent=from+"-"+Math.min(S.start+S.pageLen,S.total)+" / "+S.total;
$("lk-prev").disabled=S.start<=0;$("lk-next").disabled=S.start+S.pageLen>=S.total;}).catch(function(e){tb.innerHTML='<tr><td colspan="12" class="al-empty">L\u1ed7i: '+A.esc(e.message)+'</td></tr>';});}
function loadPauses(){A.call("api_pauses.list_pauses",{}).then(function(rows){S.pauses=rows;var tb=$("pz-rows");
if(!rows.length){tb.innerHTML='<tr><td colspan="10" class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</td></tr>';return;}
tb.innerHTML=rows.map(function(z,i){return '<tr>'+
'<td>'+A.esc(z.brand)+'</td><td>'+A.esc(z.platform||"All")+'</td><td>'+A.esc(z.shop||"-")+'</td><td>'+A.esc(z.seller_sku||z.item||"-")+'</td>'+
'<td>'+A.esc(A.dt(z.pause_from))+'</td><td>'+A.esc(A.dt(z.pause_until))+'</td>'+
'<td><span class="al-badge '+({Active:"al-b-active",Expired:"al-b-expired",Cancelled:"al-b-ignored"}[z.status]||"al-b-info")+'">'+A.esc(z.status)+'</span></td>'+
'<td>'+A.esc(z.paused_by||"-")+'</td><td style="white-space:normal">'+A.esc(z.reason||"-")+'</td>'+
'<td>'+(z.status==="Active"?('<button class="al-btn" data-pz="'+i+'">Hu\u1ef7 pause</button>'):"")+'</td></tr>';}).join("");}).catch(function(){});}
function kvdl(rows){return '<dl class="al-kv">'+rows.map(function(p){return "<dt>"+p[0]+"</dt><dd>"+p[1]+"</dd>";}).join("")+'</dl>';}
function openDrawer(r){S.current=r;$("lk-d-title").textContent=r.name;
var trig=[["Alert ngu\u1ed3n",A.esc(r.alert||"-")],["Brand",A.esc(r.brand)],["Platform",A.esc(r.platform||"-")],["Shop",A.esc(r.shop||"-")],["SKU",A.esc(r.seller_sku||r.item||"-")],["L\u00fd do lock",A.esc(r.lock_reason||"-")]];
var reqa=[["SL \u0111\u1ec1 xu\u1ea5t kho\u00e1",ds1(r.locked_quantity)],["Lock until",A.esc(A.dt(r.lock_until))],["Release strategy",A.esc(r.release_strategy||"-")],["Release required",r.release_required?"Yes":"-"]];
var rev=[["K\u1ebft qu\u1ea3 m\u00f4 ph\u1ecfng",ssStatusBadge(r)],["Review",rvBadge(r.review_status)],["Duy\u1ec7t b\u1edfi / l\u00fac",A.esc(r.reviewed_by?(r.reviewed_by+" / "+A.dt(r.reviewed_at)):"-")],["Ghi ch\u00fa duy\u1ec7t",A.esc(r.review_note||"-")]];
var tech=[["Actual stock before",ds1(r.actual_stock_before)],["Available before",ds1(r.available_stock_before)],["Buffer before",ds1(r.buffer_stock_before)],["Buffer after",ds1(r.buffer_stock_after)],["API response",A.esc(r.api_response||"-")]];
$("lk-d-kv").innerHTML='<div class="al-fsec">Trigger & b\u1eb1ng ch\u1ee9ng</div>'+kvdl(trig)+'<div class="al-fsec">H\u00e0nh \u0111\u1ed9ng \u0111\u1ec1 xu\u1ea5t</div>'+kvdl(reqa)+'<div class="al-action-box">Simulation Mode \u2014 kh\u00f4ng c\u00f3 c\u1eadp nh\u1eadt t\u1ed3n n\u00e0o g\u1eedi sang Omisell.</div><div class="al-fsec">Quy\u1ebft \u0111\u1ecbnh duy\u1ec7t</div>'+kvdl(rev)+'<details class="al-tech"><summary class="al-fsec" style="cursor:pointer">Chi ti\u1ebft k\u1ef9 thu\u1eadt</summary>'+kvdl(tech)+'</details>';
var can=(r.status==="Dry Run"||r.status==="Pending"||r.status==="Skipped");
$("lk-approve").disabled=!can;$("lk-reject").disabled=!can;
$("al-overlay").hidden=false;$("lk-drawer").hidden=false;}
function closeDrawer(){$("al-overlay").hidden=true;$("lk-drawer").hidden=true;}
function review(decision,note){A.call("api_actions.review_action",{name:S.current.name,decision:decision,note:note||null}).then(function(){A.toast("\u0110\u00e3 c\u1eadp nh\u1eadt.");
$("lk-approve-modal").hidden=true;$("lk-reject-modal").hidden=true;closeDrawer();load();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
function openPauseModal(){var br=$("z-brand");br.innerHTML="";
Object.keys((S.scope&&S.scope.brands)||{}).forEach(function(b){var o=document.createElement("option");o.value=b;o.textContent=b;br.appendChild(o);});
function fmt(d){function p(n){return (n<10?"0":"")+n;}return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+"T"+p(d.getHours())+":"+p(d.getMinutes());}
var now=new Date();$("z-from").value=fmt(now);$("z-until").value=fmt(new Date(now.getTime()+2*3600*1000));$("z-sku").value="";$("z-reason").value="";
$("al-overlay").hidden=false;$("pz-modal").hidden=false;}
function createPause(){A.call("api_pauses.create_pause",{brand:$("z-brand").value,platform:$("z-platform").value,seller_sku:$("z-sku").value||null,pause_from:$("z-from").value.replace("T"," ")+":00",pause_until:$("z-until").value.replace("T"," ")+":00",reason:$("z-reason").value}).then(function(){
$("pz-modal").hidden=true;$("al-overlay").hidden=true;A.toast("\u0110\u00e3 t\u1ea1o automation pause.");loadPauses();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
function setStockTab(tab,reviewStatus){
["pending","history","pauses"].forEach(function(t){var b=$("ss-tab-"+t);if(b){b.classList.toggle("primary",t===tab);b.setAttribute("aria-selected",t===tab?"true":"false");}});
var q=$("ss-queue"),p=$("ss-pauses");
if(tab==="pauses"){if(q)q.hidden=true;if(p)p.hidden=false;loadPauses();setHash("stock-pauses");return;}
if(p)p.hidden=true;if(q)q.hidden=false;
$("f-review_status").value=(tab==="history")?(reviewStatus||""):"Pending Review";
$("ss-queue-title").textContent=(tab==="history")?"L\u1ecbch s\u1eed action":"H\u00e0ng \u0111\u1ee3i review (dry-run)";
S.start=0;load();
setHash((tab==="history")?"stock-history":"stock-pending");}
// replaceState doi hash KHONG ban "hashchange" -> khong chay lai restoreTab (truoc day moi lan
// mo trang bi tai 2 lan vi chinh dong gan hash nay). Back/forward va link #... van qua hashchange.
function setHash(h){if(window.location.hash==="#"+h)return;try{window.history.replaceState(window.history.state,"",window.location.pathname+window.location.search+"#"+h);}catch(e){window.location.hash=h;}}
function restoreTab(){var h=window.location.hash;setStockTab(h==="#stock-pauses"?"pauses":(h==="#stock-history"?"history":"pending"));}
function init(){A.initScope("/alerts/locks",function(scope){S.scope=scope;
A.scopeLine($("al-scope-line"),scope.supervisor?"Supervisor scope: all brands":("Brands: "+Object.keys(scope.brands).join(", ")));
var bsel=$("f-brand");Object.keys(scope.brands||{}).forEach(function(b){var o=document.createElement("option");o.value=b;o.textContent=b;bsel.appendChild(o);});
restoreTab();if(!S.loaded)load();});
["pending","history","pauses"].forEach(function(t){var b=$("ss-tab-"+t);if(b)b.onclick=function(){setStockTab(t);};});
$("ss-tabs").addEventListener("keydown",function(ev){if(ev.key==="Enter"||ev.key===" "||ev.key==="Spacebar"){var b=ev.target.closest("[role=tab]");if(b){ev.preventDefault();b.click();}}});
$("ss-kpis").addEventListener("click",function(ev){var c=ev.target.closest(".stat-card[data-ss]");if(!c)return;var p=c.getAttribute("data-ss").split("|");if(p[0]==="history"){setStockTab("history",p[1]||"");}else setStockTab("pending");});
$("ss-kpis").addEventListener("keydown",function(ev){if(ev.key==="Enter"||ev.key===" "||ev.key==="Spacebar"){var c=ev.target.closest(".stat-card[data-ss]");if(c){ev.preventDefault();c.click();}}});
window.addEventListener("hashchange",restoreTab);
$("lk-apply").onclick=function(){S.start=0;load();};
$("lk-refresh").onclick=function(){load();loadPauses();};
$("lk-prev").onclick=function(){S.start=Math.max(0,S.start-S.pageLen);load();};
$("lk-next").onclick=function(){S.start+=S.pageLen;load();};
$("lk-rows").addEventListener("click",function(ev){var tr=ev.target.closest("tr[data-i]");if(tr)openDrawer(S.rows[+tr.getAttribute("data-i")]);});
$("lk-d-close").onclick=closeDrawer;
$("al-overlay").onclick=function(){closeDrawer();$("lk-approve-modal").hidden=true;$("lk-reject-modal").hidden=true;$("pz-modal").hidden=true;};
$("lk-approve").onclick=function(){$("lk-ap-note").value="";$("lk-approve-modal").hidden=false;$("al-overlay").hidden=false;};
$("lk-reject").onclick=function(){$("lk-rj-note").value="";$("lk-reject-modal").hidden=false;$("al-overlay").hidden=false;};
$("lk-ap-ok").onclick=function(){review("Approve",$("lk-ap-note").value.trim());};
$("lk-ap-cancel").onclick=function(){$("lk-approve-modal").hidden=true;};
$("lk-rj-ok").onclick=function(){var n=$("lk-rj-note").value.trim();if(!n){A.toast("C\u1ea7n nh\u1eadp ghi ch\u00fa.");return;}review("Reject",n);};
$("lk-rj-cancel").onclick=function(){$("lk-reject-modal").hidden=true;};
$("lk-open-alert").onclick=function(){if(S.current&&S.current.alert)window.open("/alerts","_blank");};
$("pz-new").onclick=openPauseModal;
$("pz-ok").onclick=createPause;
$("pz-cancel").onclick=function(){$("pz-modal").hidden=true;$("al-overlay").hidden=true;};
$("pz-rows").addEventListener("click",function(ev){var b=ev.target.closest("button[data-pz]");if(!b)return;
var z=S.pauses[+b.getAttribute("data-pz")];
A.call("api_pauses.cancel_pause",{name:z.name}).then(function(){A.toast("\u0110\u00e3 c\u1eadp nh\u1eadt.");loadPauses();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});});}
if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",init);}else{init();}
})();
