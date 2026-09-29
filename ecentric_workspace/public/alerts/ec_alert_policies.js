// Copyright (c) 2026, eCentric and contributors
// Alert Center - trang Price Setup /alerts/policies. Asset cua app tu 29/09/2026 (brief NHIEU_LOP/brief_alert_center.md);
// truoc do nam inline trong Web Page duoi dang <script id="ec-alert-policies">.
// Trang nap file nay qua /assets/ecentric_workspace/alerts/ec_alert_policies.js?v=<sha>. Sua file nay thi chay
//   python -m ecentric_workspace.alerts.site_pages.assets --stamp
// roi bump BASELINE_SHA256 cua trang doi + them patch resync (test bat neu quen).
(function(){
"use strict";
var A=window.AL,$=A.$;
var S={start:0,pageLen:50,total:0,scope:null,rows:[],current:null,
       caps:null,capsAll:false,prev:null,prevContent:null,missingLoaded:false};
// ----- permission caps (BACKEND is the source of truth, never role text) -----
function cap(brand){if(S.capsAll)return{can_manage:true,can_activate:true};
return (S.caps&&S.caps[brand])||{can_manage:false,can_activate:false};}
function loadCaps(){return A.call("api_policies.policy_caps",{}).then(function(r){
S.capsAll=!!r.all_brands;S.caps=r.caps||{};
$("pl-new").disabled=!(S.capsAll||Object.keys(S.caps).some(function(b){return S.caps[b].can_manage;}));}).catch(function(){});}
// applyCaps refreshes Save enablement (lifecycle moved to the table, RC5-2).
function applyCaps(brand){refreshFooter();}
function curStatus(){return (S.current&&S.current.status)||"Draft";}
// RC5-2: the drawer has NO lifecycle buttons anymore; refreshFooter only gates the
// Save button by the brand edit capability.
function refreshFooter(){var c=cap($("e-brand").value);
$("pl-save").disabled=!c.can_manage;
$("pl-save").textContent=(!S.current||curStatus()==="Draft")?"L\u01b0u":"L\u01b0u thay \u0111\u1ed5i";}
// RC5-2: per-row Status SWITCH in the Price Setup table. ON == Active. The switch
// reflects BACKEND TRUTH ONLY: a user flip is snapped back to the current truth and
// disabled, the transition is attempted, and ONLY a successful reload renders the
// new state. A conflict / validation failure keeps the prior status and shows the
// exact business error. Turning ON (Activate) needs activate rights; turning OFF
// (Pause) needs manage rights.
function statusLabel(st){return {Active:"\u0110ang b\u1eadt",Paused:"T\u1ea1m d\u1eebng",Draft:"Nh\u00e1p"}[st]||A.esc(st||"-");}
function statusToggle(r){var on=(r.status==="Active");var c=cap(r.brand);
var canFlip=on?c.can_manage:c.can_activate;
return '<label class="al-switch'+(canFlip?'':' al-switch-dis')+'" title="'+A.esc(r.status||"")+'">'+
  '<input type="checkbox" class="pl-tog" data-name="'+A.esc(r.name)+'" data-status="'+A.esc(r.status||"Draft")+'"'+(on?' checked':'')+(canFlip?'':' disabled')+'>'+
  '<span class="al-switch-sl"></span></label> <span class="al-switch-tx">'+statusLabel(r.status)+'</span>';}
// RC6-2: IN-PLACE toggle - update only the clicked row (switch + label + in-memory
// row object); never rebuild the table, so scroll position and filters are kept. A
// per-name guard blocks rapid double-clicks. KPI/coverage counts refresh in the
// background (they do not touch the policy table).
function togglePolicyStatus(cb){var name=cb.getAttribute("data-name"),cur=cb.getAttribute("data-status");
S.toggling=S.toggling||{};if(S.toggling[name])return;        // no duplicate transitions
S.toggling[name]=1;
var next=cb.checked?"Active":"Paused";
cb.checked=(cur==="Active");cb.disabled=true;                // show truth until confirmed
var td=cb.closest("td"),tx=td?td.querySelector(".al-switch-tx"):null;
A.call("api_policies.set_policy_status",{name:name,status:next}).then(function(res){
  var st=(res&&res.status)||next;                            // reflect the REAL status
  var row=null,i;for(i=0;i<(S.rows||[]).length;i++){if(S.rows[i].name===name){row=S.rows[i];break;}}
  if(row)row.status=st;
  cb.setAttribute("data-status",st);cb.checked=(st==="Active");cb.title=st;
  if(tx)tx.textContent=statusLabel(st);
  var c=cap(row?row.brand:""),on=(st==="Active");cb.disabled=!(on?c.can_manage:c.can_activate);
  delete S.toggling[name];A.toast("\u0110\u00e3 l\u01b0u.");
  loadMissing();loadCoverageSummary();                       // background counts only
}).catch(function(e){
  cb.checked=(cur==="Active");cb.disabled=false;cb.setAttribute("data-status",cur);
  if(tx)tx.textContent=statusLabel(cur);
  delete S.toggling[name];A.toast(e.message);                // exact backend error; switch stays OFF
});}
// ----- per-brand missing-policy summary (unknown/not-loaded -> '-', confirmed 0 -> '0') -----
function loadMissing(){var box=$("pl-missing-rows");
A.call("api_policies.missing_policy_summary",{}).then(function(res){S.missingLoaded=true;var sum=res.summary||{};
var brands=(S.scope&&S.scope.supervisor)?Object.keys(sum):(S.scope&&S.scope.brands?Object.keys(S.scope.brands):[]);
if(!brands.length){box.innerHTML='<span class="al-empty">-</span>';return;}
box.innerHTML=brands.sort().map(function(b){var n=(b in sum)?sum[b]:0;
return '<button class="al-chip '+(n>0?"warn":"ok")+'" data-mbrand="'+A.esc(b)+'" title="B\u1ea5m \u0111\u1ec3 xem SKU thi\u1ebfu Active policy"><span>'+A.esc(b)+'</span><span class="al-chip-n">'+n+'</span></button>';}).join("");
}).catch(function(){box.innerHTML='<span class="al-empty">-</span>';});}
// ----- compact coverage summary (Covered / Missing / Coverage pct) -----
// 29/09/2026 (NHIEU_LOP): MOT loi goi api_sku_catalog.policy_coverage_summary cho moi brand
// trong pham vi (truoc: policy_missing_skus x N brand, 21 lan tren live). Server dung CUNG
// dinh nghia voi coverage_report (services.policy_coverage): missing = SKU distinct thieu
// policy, checked = SKU distinct co don trong 30 ngay -- chi gop lai trong 2 cau SQL.
// Denominator = total distinct ordered seller_sku in the 30d window; if there are NO orders,
// pct shows n/a (never a fabricated denominator). The cards keep their "-" until data lands.
function loadCoverageSummary(){
var brands=Object.keys((S.scope&&S.scope.brands)||{});S.covBrands=brands;
var cov=$("pl-cov-covered"),mis=$("pl-cov-missing"),pct=$("pl-cov-pct");
if(!brands.length){cov.textContent="0";mis.textContent="0";pct.textContent="n/a";return;}
A.call("api_sku_catalog.policy_coverage_summary",{brands:brands,days:30}).then(function(r){
var tc=+(r&&r.checked)||0,tm=+(r&&r.missing)||0;
var covered=Math.max(0,tc-tm);
cov.textContent=covered;mis.textContent=tm;
pct.textContent=tc?(Math.round(1000*(tc-tm)/tc)/10+"%"):"n/a";}).catch(function(){cov.textContent=mis.textContent=pct.textContent="-";});}
function openMissingView(){var brands=S.covBrands||[];
if(brands.length===1){openCoverageFor(brands[0]);return;}
var d=$("pl-cov-bybrand");if(d){d.open=true;if(!S.missingLoaded)loadMissing();d.scrollIntoView({behavior:"smooth",block:"nearest"});}}
// ----- bulk import workbench helpers -----
function actChip(a,detail){var col={Create:"#16a34a",Update:"#2563eb",Skip:"#6b7280",Conflict:"#d97706",Invalid:"#dc2626"}[a]||"#6b7280";
var t=(a==="Update"&&detail)?(" \u2192 "+A.esc(detail)):((a==="Conflict"&&detail)?(" ("+A.esc(detail)+")"):"");
return '<span style="font-weight:600;color:'+col+'">'+a+'</span>'+t;}
function selectedLines(){var out=[];Array.prototype.forEach.call(document.querySelectorAll("#csv-rows .csv-pick:checked"),function(cb){out.push(+cb.getAttribute("data-line"));});return out;}
function refreshImportBtn(){$("csv-import").disabled=(!S.prev)||selectedLines().length===0;}
function toggleSrc(){var paste=$("imp-src-paste").checked;$("csv-paste").style.display=paste?"block":"none";$("csv-file").style.display=paste?"none":"block";}
function invalidatePreview(){S.prev=null;S.prevContent=null;$("csv-import").disabled=true;
if($("csv-rows").innerHTML)$("csv-summary").innerHTML="N\u1ed9i dung \u0111\u00e3 \u0111\u1ed5i - b\u1ea5m Preview l\u1ea1i tr\u01b0\u1edbc khi Import.";}
function importContent(cb){if($("imp-src-paste").checked){cb($("csv-paste").value||"");return;}
var f=$("csv-file").files[0];if(!f){cb(null);return;}var rd=new FileReader();rd.onload=function(){cb(rd.result);};rd.readAsText(f,"utf-8");}
function showLifecycle(msg,res){var lc=res&&res.lifecycle;
if(lc&&((lc.closed&&lc.closed.length)||lc.policy_status==="Active")){
var n=(lc.closed||[]).length;var rem=(lc.remaining_missing==null?"-":lc.remaining_missing);
A.toast(msg+" \u00b7 \u0110\u00e3 \u0111\u00f3ng missing_policy: "+n+" \u00b7 SKU c\u00f2n thi\u1ebfu: "+rem);}else{A.toast(msg);}}
function loadConflicts(rows){var brands={};(rows||[]).forEach(function(r){if(r.brand)brands[r.brand]=1;});
Object.keys(brands).forEach(function(b){A.call("api_policies.policy_conflicts",{brand:b}).then(function(res){var f=(res&&res.flags)||{};
Object.keys(f).forEach(function(nm){var el=document.querySelector('.al-conf-badge[data-conf="'+nm.replace(/["\\]/g,"")+'"]');if(!el)return;var tags=f[nm];
// RC7-A: the "overridden"/"fallback" badge encoded the legacy Shop+Platform scope
// hierarchy (Shop is no longer part of the canonical identity), so it is removed as
// misleading. Only the genuine "duplicate" conflict warning remains beside the SKU.
if(tags.indexOf("duplicate")>=0){el.innerHTML='<span class="al-badge al-b-critical" title="C\u00f3 Active policy kh\u00e1c tr\u00f9ng y h\u1ec7t scope + ch\u1ed3ng hi\u1ec7u l\u1ef1c. Inactivate b\u1edbt 1.">TR\u00d9NG</span>';}});}).catch(function(){});});}
function getStatuses(){var out=[];Array.prototype.forEach.call(document.querySelectorAll(".f-status-cb:checked"),function(cb){out.push(cb.value);});return out;}
function setStatuses(arr){var set={};(arr||[]).forEach(function(v){set[v]=1;});Array.prototype.forEach.call(document.querySelectorAll(".f-status-cb"),function(cb){cb.checked=!!set[cb.value];});}
function filters(){var f={};
[["f-brand","brand"],["f-platform","platform"]].forEach(function(p){var v=$(p[0]).value;if(v)f[p[1]]=v;});
var st=getStatuses();if(st.length)f.status=st;          // multi-select -> backend OR ("in")
var sku=$("f-sku").value.trim();if(sku)f.seller_sku=sku;
var o=$("f-owner").value.trim();if(o)f.owner_user=o;return f;}
// ----- URL filter-state persistence (status multi-select + brand/platform/sku/owner) -----
// All filter state lives in the query string so a refresh, copied link, or browser
// back/forward restores exactly what the operator was looking at. Toggle/edit refreshes
// call load() directly (never touch the controls), so they preserve the selection.
var PLURLF=[["brand","f-brand"],["platform","f-platform"],["seller_sku","f-sku"],["owner_user","f-owner"]];
function readUrlFilters(){var q;try{q=new URLSearchParams(window.location.search);}catch(e){return;}
PLURLF.forEach(function(p){var el=$(p[1]);if(el)el.value=q.get(p[0])||"";});
setStatuses((q.get("status")||"").split(",").filter(Boolean));}
function writeUrlFilters(push){var q;try{q=new URLSearchParams();}catch(e){return;}
PLURLF.forEach(function(p){var el=$(p[1]);var v=el?(el.value||"").trim():"";if(v)q.set(p[0],v);});
var st=getStatuses();if(st.length)q.set("status",st.join(","));
var s=q.toString();var url=window.location.pathname+(s?"?"+s:"")+window.location.hash;
try{if(push)window.history.pushState({plFilter:1},"",url);else window.history.replaceState({plFilter:1},"",url);}catch(e){}}
function applyFiltersNav(){S.start=0;writeUrlFilters(true);load();}            // push -> back/forward
function clearFiltersNav(){["f-brand","f-platform","f-sku","f-owner"].forEach(function(id){var el=$(id);if(el)el.value="";});setStatuses([]);S.start=0;writeUrlFilters(false);load();}
function polScope(r){var t=(r.seller_sku||r.item)?"SKU-specific":r.shop?"Shop Policy":(r.platform&&r.platform!=="All")?"Platform Policy":"Brand fallback";return '<span class="al-badge al-b-info" title="\u01afu ti\u00ean: SKU > Shop > Platform > Brand">'+t+'</span>';}
function load(){var tb=$("pl-rows");tb.innerHTML='<tr><td colspan="10" class="al-empty">\u0110ang t\u1ea3i...</td></tr>';
A.call("api_policies.list_policies",{filters:filters(),start:S.start,page_len:S.pageLen}).then(function(res){S.rows=res.rows;S.total=res.total;
if(!res.rows.length){tb.innerHTML='<tr><td colspan="10" class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</td></tr>';}
else{tb.innerHTML=res.rows.map(function(r,i){return '<tr data-i="'+i+'">'+
'<td>'+A.esc(r.brand)+'</td>'+
'<td>'+statusToggle(r)+'</td>'+
'<td>'+A.esc(r.platform)+'</td><td title="'+A.esc(r.seller_sku||r.item||"")+'">'+A.esc(r.seller_sku||r.item||"-")+' <span class="al-conf-badge" data-conf="'+A.esc(r.name)+'"></span></td><td title="'+A.esc(r.product_name||"")+'">'+A.esc(r.product_name||"-")+'</td>'+
'<td>'+A.money(r.min_price)+'</td><td>'+A.money(r.target_price)+'</td><td>'+A.money(r.reference_price)+'</td>'+
'<td title="'+A.esc(r.owner_user||"")+'">'+A.esc(r.owner_user||"-")+'</td><td>'+A.esc((r.effective_from||"")+(r.effective_to?(" \u2192 "+r.effective_to):""))+'</td></tr>';}).join("");loadConflicts(res.rows);}
var from=S.total?S.start+1:0;$("pl-count").textContent=from+"-"+Math.min(S.start+S.pageLen,S.total)+" / "+S.total;
$("pl-prev").disabled=S.start<=0;$("pl-next").disabled=S.start+S.pageLen>=S.total;}).catch(function(e){tb.innerHTML='<tr><td colspan="10" class="al-empty">L\u1ed7i: '+A.esc(e.message)+'</td></tr>';});}
// RC4-5: only safe business facts are submitted. The Rules-owned thresholds
// (high_alert_percent / severe_drop_percent), the effective-period fields and ERP
// Item are intentionally NOT in this list, so save() never sends them (legacy
// values are preserved untouched). ERP Item is mirrored separately for the scope
// preview only.
// RC5-3: "shop" is NOT submitted (removed from the normal flow). A legacy shop is
// preserved because save() never sends the field, so the backend keeps the stored
// value. e-shop is mirrored separately (hidden) for the live scope preview.
var FIELDS=["platform","seller_sku","product_name","min_price","reference_price","target_price","owner_user"];
function openDrawer(r){S.current=r||null;
$("pl-d-title").textContent=r?r.name:"New Policy";
A.fillBrandSelect($("e-brand"),S.scope,{extra:(r&&r.brand)||null,value:(r&&r.brand)||null});
FIELDS.forEach(function(k){var el=$("e-"+k);if(el)el.value=(r&&r[k]!=null)?r[k]:"";});
// ERP Item + legacy Shop kept only for the scope preview / read-only display
// (hidden, never submitted -> the stored values are preserved untouched).
var it=$("e-item");if(it)it.value=(r&&r.item!=null)?r.item:"";
var sh=$("e-shop");if(sh)sh.value=(r&&r.shop!=null)?r.shop:"";
var lg=$("e-shop-legacy");if(lg){var has=!!(r&&r.shop);lg.hidden=!has;if(has)$("e-shop-legacy-val").textContent=r.shop;}
$("pl-d-status").innerHTML=A.polBadge(curStatus());
applyCaps($("e-brand").value);
refreshDeleteBtn(r);
updateScopePreview();applyFieldHelp($("pl-drawer"));
$("al-overlay").hidden=false;$("pl-drawer").hidden=false;}
// RC7-A: show the Delete control only when the safe-delete contract could allow it
// (the backend re-enforces it): existing record, NOT Active, and either Draft (with
// manage rights) or a retired status with admin/supervisor scope. A new (unsaved)
// policy or an Active one shows no Delete.
function delReasonText(code){return {active_no_delete:"\u0110ang Active \u2014 kh\u00f4ng th\u1ec3 xo\u00e1; t\u1ea1m d\u1eebng tr\u01b0\u1edbc.",dependency_unknown:"Kh\u00f4ng x\u00e1c minh \u0111\u01b0\u1ee3c ph\u1ee5 thu\u1ed9c l\u1ecbch s\u1eed \u2014 t\u1eeb ch\u1ed1i xo\u00e1 (an to\u00e0n).",admin_only:"Ch\u1ec9 System Manager m\u1edbi xo\u00e1 v\u0129nh vi\u1ec5n.",has_dependents:"C\u00f2n alert l\u1ecbch s\u1eed ph\u1ee5 thu\u1ed9c."}[code]||(code||"");}
function refreshDeleteBtn(r){var btn=$("pl-delete");if(!btn)return;btn.hidden=true;btn.disabled=true;btn.removeAttribute("title");
if(!r||!r.name)return;                       // new (unsaved) policy -> nothing to delete
// RC7-A: the UI NEVER infers delete eligibility from status. The Delete control stays
// VISIBLE for a saved policy but DISABLED while checking and when the backend says
// can_delete=false, with the backend delete_reason shown as the tooltip.
btn.hidden=false;btn.title="";
A.call("api_policies.policy_delete_capability",{name:r.name}).then(function(res){
  if(!(S.current&&S.current.name===r.name))return;
  var ok=!!(res&&res.can_delete);btn.disabled=!ok;
  btn.title=ok?"":delReasonText(res&&res.delete_reason);
}).catch(function(e){if(S.current&&S.current.name===r.name){btn.disabled=true;btn.title=(e&&e.message)||"";}});}
// RC7-A: permanent delete via the SAFE backend API (never a frontend-only delete).
// The backend re-checks the full contract (admin-only for retired statuses + open
// dependent-alert rejection); the UI just confirms + removes the row on success.
function deletePolicy(){if(!S.current)return;var name=S.current.name;
if(!window.confirm("Xo\u00e1 v\u0129nh vi\u1ec5n policy n\u00e0y? H\u00e0nh \u0111\u1ed9ng kh\u00f4ng th\u1ec3 ho\u00e0n t\u00e1c. (Backend ch\u1eb7n n\u1ebfu c\u00f2n alert ph\u1ee5 thu\u1ed9c.)"))return;
$("pl-delete").disabled=true;
A.call("api_policies.delete_policy",{name:name}).then(function(){
  A.toast("\u0110\u00e3 xo\u00e1 policy.");closeDrawer();
  S.rows=(S.rows||[]).filter(function(x){return x.name!==name;});
  load();loadMissing();loadCoverageSummary();
}).catch(function(e){$("pl-delete").disabled=false;A.toast(e.message);});}
// ===== RC7-C Gift Exemptions (compact management; in-place status toggle) =====
function gxStatusToggle(r){var on=(r.status==="Active");
return '<label class="al-switch" title="'+A.esc(r.status||"")+'"><input type="checkbox" class="gx-tog" data-name="'+A.esc(r.name)+'" data-status="'+A.esc(r.status||"Active")+'"'+(on?' checked':'')+'><span class="al-switch-sl"></span></label> <span class="al-switch-tx">'+A.esc(r.status||"")+'</span>';}
function gxEff(r){var a=r.effective_from||"",b=r.effective_to||"";return (a||b)?(A.esc(a||"\u2026")+" \u2192 "+A.esc(b||"\u2026")):"\u2014";}
// derived-state chip (reflects the operational lifecycle, not just Active/Inactive).
function gxChip(state){var m={active:["al-b-active","\u0110ang b\u1eadt"],inactive:["al-b-ignored","\u0110\u00e3 t\u1eaft"]};var x=m[state]||["al-b-info",A.esc(state||"")];return '<span class="al-badge '+x[0]+'">'+x[1]+'</span>';}
function gxFilters(){S.gx=S.gx||{state:"active",start:0,pageLen:20};
var f={lifecycle_state:S.gx.state};var b=$("gx-f-brand").value;if(b)f.brand=b;
var p=$("gx-f-platform").value;if(p)f.platform=p;var s=$("gx-f-sku").value.trim();if(s)f.seller_sku=s;
return f;}
function loadExemptions(){var tb=$("gx-rows");if(!tb)return;S.gx=S.gx||{state:"active",start:0,pageLen:20};
tb.innerHTML='<tr><td colspan="7" class="al-empty">\u0110ang t\u1ea3i...</td></tr>';
A.call("api_exemptions.list_exemptions",{filters:gxFilters(),start:S.gx.start,page_length:S.gx.pageLen}).then(function(res){
S.exRows=res.rows||[];var c=res.counts||{};
["active","inactive","all"].forEach(function(k){var el=$("gx-c-"+k);if(el)el.textContent=(c[k]||0);});
Array.prototype.forEach.call(document.querySelectorAll("#gx-tabs .gx-tab"),function(bt){bt.classList.toggle("primary",bt.getAttribute("data-gxs")===S.gx.state);});
if(!S.exRows.length){tb.innerHTML='<tr><td colspan="7" class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</td></tr>';}
else{tb.innerHTML=S.exRows.map(function(r,i){return '<tr data-xi="'+i+'">'+
'<td>'+A.esc(r.brand)+'</td><td>'+A.esc(r.platform||"All")+'</td><td>'+A.esc(r.seller_sku)+'</td>'+
'<td>'+A.esc(r.reason||"-")+'</td><td>'+gxEff(r)+'</td><td>'+gxChip(r.lifecycle)+'</td><td>'+gxStatusToggle(r)+'</td></tr>';}).join("");}
var total=res.total||0,from=total?S.gx.start+1:0,to=Math.min(S.gx.start+S.gx.pageLen,total);
$("gx-count").textContent=from+"\u2013"+to+" / "+total+" exemptions";
$("gx-prev").disabled=S.gx.start<=0;$("gx-next").disabled=S.gx.start+S.gx.pageLen>=total;
}).catch(function(e){tb.innerHTML='<tr><td colspan="7" class="al-empty">L\u1ed7i: '+A.esc(e.message)+'</td></tr>';});}
// tab switch resets to page 1; filter apply resets to page 1; create/edit/toggle keep
// the current page + filters (loadExemptions reuses S.gx + the filter inputs unchanged).
function gxSetTab(state){S.gx=S.gx||{state:"active",start:0,pageLen:20};S.gx.state=state;S.gx.start=0;loadExemptions();}
function gxApplyFilters(){S.gx=S.gx||{state:"active",start:0,pageLen:20};S.gx.start=0;loadExemptions();}
function gxClearFilters(){$("gx-f-brand").value="";$("gx-f-platform").value="";$("gx-f-sku").value="";gxApplyFilters();}
function openExemption(r){S.exCurrent=r||null;$("gx-m-title").textContent=r?A.esc(r.seller_sku):"+ Th\u00eam exemption";
A.fillBrandSelect($("gx-brand"),S.scope,{extra:(r&&r.brand)||null,value:(r&&r.brand)||null});
// Reason is fixed (Gift / Freebie, read-only); no date fields. Only these are editable.
["platform","seller_sku","status","notes"].forEach(function(k){var el=$("gx-"+k);if(!el)return;
el.value=(r&&r[k]!=null&&r[k]!=="")?r[k]:(k==="status"?"Active":(k==="platform"?"All":""));});
$("gx-modal").hidden=false;$("al-overlay").hidden=false;}
function closeExemption(){$("gx-modal").hidden=true;$("al-overlay").hidden=true;}
function saveExemption(){var d={brand:$("gx-brand").value,platform:$("gx-platform").value,seller_sku:$("gx-seller_sku").value.trim(),reason:"Gift / Freebie",status:$("gx-status").value,notes:$("gx-notes").value.trim()};
if(!d.brand||!d.seller_sku){A.toast("C\u1ea7n Brand + Seller SKU.");return;}
A.call("api_exemptions.save_exemption",{exemption:d,name:S.exCurrent?S.exCurrent.name:null}).then(function(){A.toast("\u0110\u00e3 l\u01b0u.");closeExemption();loadExemptions();loadCoverageSummary();}).catch(function(e){A.toast(e.message);});}
function toggleExemption(cb){var name=cb.getAttribute("data-name"),cur=cb.getAttribute("data-status");
S.gxToggling=S.gxToggling||{};if(S.gxToggling[name])return;S.gxToggling[name]=1;
var next=cb.checked?"Active":"Inactive";cb.checked=(cur==="Active");cb.disabled=true;
var td=cb.closest("td"),tx=td?td.querySelector(".al-switch-tx"):null;
A.call("api_exemptions.set_exemption_status",{name:name,status:next}).then(function(res){var st=(res&&res.status)||next;
var row=null,i;for(i=0;i<(S.exRows||[]).length;i++){if(S.exRows[i].name===name){row=S.exRows[i];break;}}if(row)row.status=st;
cb.setAttribute("data-status",st);cb.checked=(st==="Active");cb.disabled=false;if(tx)tx.textContent=st;
delete S.gxToggling[name];A.toast("\u0110\u00e3 l\u01b0u.");loadCoverageSummary();
}).catch(function(e){cb.checked=(cur==="Active");cb.disabled=false;delete S.gxToggling[name];A.toast(e.message);});}
// Live scope preview (informational only; backend resolution unchanged).
function updateScopePreview(){var sp=$("e-scope-preview");if(!sp)return;var t=sp.querySelector(".al-sp-text");if(!t)return;
var b=$("e-brand").value||"(brand)",pf=$("e-platform").value,sh=$("e-shop").value.trim(),sk=($("e-seller_sku").value.trim()||$("e-item").value.trim());
var scope,msg;
if(sk){scope="SKU-specific";msg=b+" \u2192 SKU "+sk;}
else if(sh){scope="Shop Policy";msg=b+" \u2192 shop "+sh;}
else if(pf&&pf!=="All"){scope="Platform Policy";msg=b+" \u2192 "+pf;}
else{scope="Brand fallback";msg="t\u1ea5t c\u1ea3 "+b;}
t.textContent=scope+" \u2014 "+msg;}
// Upgrade info-icon tooltips from EC Field Description when a record exists.
function applyFieldHelp(root){var els=(root||document).querySelectorAll("[data-help]");Array.prototype.forEach.call(els,function(el){var h=A.fieldHelp(el.getAttribute("data-help"));if(h&&h.help){el.title=h.help;el.setAttribute("aria-label",h.help);}});}
function closeDrawer(){$("al-overlay").hidden=true;$("pl-drawer").hidden=true;}
function save(){var data={brand:$("e-brand").value};
FIELDS.forEach(function(k){var v=$("e-"+k).value;if(v!=="")data[k]=v;});
A.call("api_policies.save_policy",{policy:data,name:S.current?S.current.name:null}).then(function(res){showLifecycle("\u0110\u00e3 l\u01b0u.",res);closeDrawer();load();loadMissing();loadCoverageSummary();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
// RC5-2: drawer-driven setStatus is gone; status transitions are driven by the
// per-row table switch (togglePolicyStatus -> api_policies.set_policy_status).
function dlTemplate(){A.call("api_policies.csv_template").then(function(t){
var a=document.createElement("a");a.href="data:text/csv;charset=utf-8,"+encodeURIComponent(t.content);a.download=t.filename;document.body.appendChild(a);a.click();a.remove();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
function openCsv(){$("csv-file").value="";$("csv-paste").value="";$("csv-rows").innerHTML="";$("csv-stats").textContent="";$("csv-summary").textContent="";$("csv-errbox").value="";$("csv-result").innerHTML="";$("csv-import").disabled=true;S.prev=null;S.prevContent=null;
$("imp-src-file").checked=true;toggleSrc();
$("al-overlay").hidden=false;$("pl-csv-modal").hidden=false;}
function preview(){importContent(function(text){
if(text==null){A.toast("Ch\u1ecdn file CSV ho\u1eb7c d\u00e1n d\u1eef li\u1ec7u.");return;}
S.prevContent=text;S.prev=null;var src=$("imp-src-paste").checked?"paste":"csv";
A.call("api_policies.preview_policy_csv",{content:text,source:src}).then(function(res){
if(res.file_errors){$("csv-stats").innerHTML='<span style="color:#dc2626">'+A.esc(res.file_errors.join("; "))+'</span>';$("csv-rows").innerHTML="";$("csv-summary").textContent="";$("csv-import").disabled=true;return;}
S.prev=res;var errs=[];
$("csv-rows").innerHTML=res.rows.map(function(r){var sel=(r.action==="Create"||r.action==="Update");var rw=r.row||{};
if(r.errors&&r.errors.length)errs=errs.concat(r.errors);
return '<tr data-line="'+r.line+'">'+
'<td>'+(sel?'<input type="checkbox" class="csv-pick" data-line="'+r.line+'" checked>':'')+'</td>'+
'<td>'+r.line+'</td><td>'+actChip(r.action,r.detail)+'</td>'+
'<td>'+A.esc(rw.brand||"")+'</td><td>'+A.esc(rw.platform||"")+'</td><td>'+(r.is_gift?"YES":"-")+'</td>'+
'<td>'+A.esc(rw.seller_sku||rw.item||"")+'</td><td>'+A.esc(r.is_gift?"-":(rw.status||"Draft"))+'</td>'+
'<td class="r">'+A.esc(rw.min_price||"")+'</td>'+
'<td style="white-space:normal;color:#dc2626">'+A.esc((r.errors||[]).join("; "))+'</td></tr>';}).join("");
var c=res.counts||{};
$("csv-stats").textContent="";
$("csv-summary").innerHTML="T\u1ed5ng "+res.rows.length+" \u00b7 Create "+(c.create||0)+" \u00b7 Update "+(c.update||0)+" \u00b7 Skip "+(c.skip||0)+" \u00b7 Conflict "+(c.conflict||0)+" \u00b7 Invalid "+(c.invalid||0)+" \u00b7 Gift "+((c.exemption_created||0)+(c.exemption_reactivated||0)+(c.already_exists||0));
$("csv-errbox").value=errs.join("\n");$("csv-all").checked=true;refreshImportBtn();
}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});});}
function doImport(){if(!S.prev||!S.prevContent)return;var lines=selectedLines();if(!lines.length){A.toast("Ch\u1ecdn \u00edt nh\u1ea5t 1 d\u00f2ng \u0111\u1ec3 import.");return;}
$("csv-import").disabled=true;var src=$("imp-src-paste").checked?"paste":"csv";
A.call("api_policies.import_policy_csv",{content:S.prevContent,source:src,lines:JSON.stringify(lines)}).then(function(r){
var c=r.counts||{};
// RC7: upload summary distinguishes POLICY vs EXEMPTION outcomes.
var html="Policy t\u1ea1o: "+(c.policy_created||0)+" \u00b7 Policy c\u1eadp nh\u1eadt: "+(c.policy_updated||0)+
  " \u00b7 Exemption t\u1ea1o: "+(c.exemption_created||0)+" \u00b7 Exemption b\u1eadt l\u1ea1i: "+(c.exemption_reactivated||0)+
  " \u00b7 \u0110\u00e3 c\u00f3: "+(c.already_exists||0)+" \u00b7 B\u1ecf qua: "+(c.skipped||0)+
  " \u00b7 L\u1ed7i d\u1eef li\u1ec7u: "+(c.invalid||0)+" \u00b7 L\u1ed7i: "+(c.failed||0);
if(r.closed_alerts)html+=" \u00b7 \u0110\u00e3 \u0111\u00f3ng missing_policy: "+r.closed_alerts;
var fails=r.errors||[];
if(fails.length){html+='<div class="al-tbl-wrap" style="max-height:140px;overflow:auto;margin-top:6px"><table class="al-tbl"><thead><tr><th>#</th><th>H\u00e0nh \u0111\u1ed9ng</th><th>L\u1ed7i</th></tr></thead><tbody>'+
fails.map(function(f){return '<tr><td>'+f.line+'</td><td>'+A.esc(f.action)+'</td><td style="white-space:normal">'+A.esc((f.errors||[]).join("; "))+'</td></tr>';}).join("")+'</tbody></table></div>';}
$("csv-result").innerHTML=html;A.toast("Import xong: ");
load();loadMissing();refreshImportBtn();   // partial: keep modal + rows open
}).catch(function(e){A.toast("L\u1ed7i: "+e.message);$("csv-import").disabled=false;});}
function copyErrs(){var box=$("csv-errbox");box.select();try{document.execCommand("copy");A.toast("\u0110\u00e3 copy l\u1ed7i v\u00e0o clipboard.");}catch(e){}}
function openSkuSearch(){var b=$("e-brand").value;if(!b){A.toast("Ch\u1ecdn Brand tr\u01b0\u1edbc.");return;}
$("pl-sku-scope").textContent=b+" / "+($("e-platform").value||"All")+" / "+($("e-shop").value||"-");
$("pl-sku-kw").value=$("e-seller_sku").value||"";$("pl-sku-rows").innerHTML="";
$("pl-sku-modal").hidden=false;$("al-overlay").hidden=false;doSkuSearch();}
function doSkuSearch(){var b=$("e-brand").value;var args={brand:b,keyword:$("pl-sku-kw").value,limit:30};
var pf=$("e-platform").value;if(pf&&pf!=="All")args.platform=pf;var sh=$("e-shop").value;if(sh)args.shop=sh;
A.call("api_sku_catalog.search_skus",args).then(function(res){var rows=res.rows||[];S.skuRows=rows;
$("pl-sku-rows").innerHTML=rows.length?rows.map(function(x,i){return '<tr data-si="'+i+'"><td>'+A.esc(x.seller_sku)+'</td><td>'+A.esc(x.product_name||"-")+'</td><td class="r">'+A.money(x.rsp_price)+'</td><td>'+A.esc(x.platform||"-")+'</td><td>'+A.esc(x.shop||"-")+'</td></tr>';}).join(""):'<tr><td colspan="5" class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</td></tr>';}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
function selectSku(x){$("e-seller_sku").value=x.seller_sku||"";if(x.product_name)$("e-product_name").value=x.product_name;
if(x.rsp_price!=null&&x.rsp_price!=="")$("e-target_price").value=x.rsp_price;
if(x.platform&&!$("e-platform").value)$("e-platform").value=x.platform;
if(x.shop&&!$("e-shop").value)$("e-shop").value=x.shop;
$("pl-sku-modal").hidden=true;$("al-overlay").hidden=true;A.toast("\u0110\u00e3 ch\u1ecdn SKU.");}
function ensureCovBrand(brand){var sel=$("pl-cov-brand");
var has=Array.prototype.some.call(sel.options,function(o){return o.value===brand;});
if(!has){var o=document.createElement("option");o.value=brand;o.textContent=brand;sel.appendChild(o);}
sel.value=brand;}
function openCoverageFor(brand){if(!brand)return;
A.fillBrandSelect($("pl-cov-brand"),S.scope,{});   // base options (scoped users)
ensureCovBrand(brand);                              // guarantee clicked brand present+selected (supervisor)
$("pl-cov-summary").textContent="";$("pl-cov-rows").innerHTML="";
$("pl-cov-modal").hidden=false;$("al-overlay").hidden=false;loadCoverage();}
function loadCoverage(){var b=$("pl-cov-brand").value;if(!b){A.toast("Ch\u1ecdn Brand tr\u01b0\u1edbc.");return;}
A.call("api_sku_catalog.policy_missing_skus",{brand:b,days:30,limit:200}).then(function(res){S.cov=res;
$("pl-cov-summary").innerHTML="Coverage: <b>"+(res.coverage_pct==null?"n/a":res.coverage_pct+"%")+"</b> &middot; Thi\u1ebfu policy: <b>"+res.missing_count+"</b> / "+res.checked;
var rows=res.missing||[];$("pl-cov-rows").innerHTML=rows.length?rows.map(function(x){return '<tr><td><input type="checkbox" class="cov-pick" data-csku="'+A.esc(x.seller_sku)+'"></td><td>'+A.esc(x.seller_sku)+'</td><td>'+A.esc(x.product_name||"-")+'</td><td class="r">'+A.money(x.rsp_price)+'</td><td class="r">'+(x.order_lines||0)+'</td><td>'+A.esc(A.dt(x.last_order))+'</td></tr>';}).join(""):'<tr><td colspan="6" class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</td></tr>';$("cov-all").checked=false;}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
function covSelected(){var out=[];Array.prototype.forEach.call(document.querySelectorAll("#pl-cov-rows .cov-pick:checked"),function(cb){out.push(cb.getAttribute("data-csku"));});return out;}
function openCovBulk(){var sel=covSelected();if(!sel.length){A.toast("Ch\u1ecdn \u00edt nh\u1ea5t m\u1ed9t SKU.");return;}
$("cov-bulk-info").textContent=sel.length+" SKU \u00b7 "+($("pl-cov-brand").value||"");
$("cb-platform").value="All";
$("cov-bulk-modal").hidden=false;$("al-overlay").hidden=false;}
function closeCovBulk(){$("cov-bulk-modal").hidden=true;}
function saveCovBulk(){var sel=covSelected();if(!sel.length){A.toast("Ch\u1ecdn \u00edt nh\u1ea5t m\u1ed9t SKU.");return;}
var dflt={brand:$("pl-cov-brand").value,platform:$("cb-platform").value,reason:"Gift / Freebie",status:"Active"};
var items=sel.map(function(s){return {seller_sku:s};});$("cb-save").disabled=true;
A.call("api_exemptions.bulk_save_exemptions",{exemptions:items,defaults:dflt}).then(function(res){$("cb-save").disabled=false;
var rmap={};(res.results||[]).forEach(function(r){rmap[r.seller_sku]=r;});
// successful rows cleared (unchecked + dimmed); failed rows remain selected + tooltip.
Array.prototype.forEach.call(document.querySelectorAll("#pl-cov-rows .cov-pick"),function(cb){var r=rmap[cb.getAttribute("data-csku")];if(!r)return;var tr=cb.closest("tr");if(r.ok){cb.checked=false;if(tr)tr.style.opacity=".45";}else{cb.checked=true;if(tr)tr.title=r.error||"";}});
$("cov-all").checked=false;closeCovBulk();
A.toast("T\u1ea1o exemption: th\u00e0nh c\u00f4ng "+(res.created||0)+"/"+((res.created||0)+(res.failed||0))+(res.failed?(" \u00b7 fail "+res.failed):""));
loadExemptions();loadCoverageSummary();
}).catch(function(e){$("cb-save").disabled=false;A.toast(e.message);});}
// Missing-policy export uses the SAME backend canonical-schema helper as the template
// download (api_policies.missing_policy_csv -> policy_csv.template_csv_with_rows), so the
// two downloads share one column contract and cannot drift. Brand/platform/seller_sku/
// product_name are pre-filled server-side; the operator fills min_price etc.
function exportCovTemplate(){var b=$("pl-cov-brand").value;if(!b){A.toast("Ch\u1ecdn Brand tr\u01b0\u1edbc.");return;}
A.call("api_policies.missing_policy_csv",{brand:b}).then(function(t){
var blob=new Blob(["\ufeff"+t.content],{type:"text/csv;charset=utf-8;"});var url=URL.createObjectURL(blob);var a=document.createElement("a");a.href=url;a.download=t.filename;document.body.appendChild(a);a.click();document.body.removeChild(a);setTimeout(function(){URL.revokeObjectURL(url);},1000);A.toast("\u0110\u00e3 xu\u1ea5t CSV.");}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
function init(){A.initScope("/alerts/policies",function(scope){S.scope=scope;
A.scopeLine($("al-scope-line"),scope.supervisor?"Supervisor scope: all brands":("Brands: "+Object.keys(scope.brands).join(", ")));
var bsel=$("f-brand");Object.keys(scope.brands||{}).forEach(function(b){var o=document.createElement("option");o.value=b;o.textContent=b;bsel.appendChild(o);});
var gxb=$("gx-f-brand");if(gxb)Object.keys(scope.brands||{}).forEach(function(b){var o=document.createElement("option");o.value=b;o.textContent=b;gxb.appendChild(o);});
readUrlFilters();   // restore brand/platform/sku/owner/status from the URL BEFORE first load
load();loadCaps();loadMissing();loadCoverageSummary();loadExemptions();applyFieldHelp($("pl-missing-panel"));});
$("pl-cov-kpis").addEventListener("click",function(ev){if(ev.target.closest('[data-cov="missing"]'))openMissingView();});
$("pl-cov-kpis").addEventListener("keydown",function(ev){if((ev.key==="Enter"||ev.key===" ")&&ev.target.closest('[data-cov="missing"]')){ev.preventDefault();openMissingView();}});
$("pl-apply").onclick=applyFiltersNav;
$("pl-clear").onclick=clearFiltersNav;
// back/forward restores the filter state from the URL (no new history entry).
window.addEventListener("popstate",function(){readUrlFilters();S.start=0;load();});
$("pl-prev").onclick=function(){S.start=Math.max(0,S.start-S.pageLen);load();};
$("pl-next").onclick=function(){S.start+=S.pageLen;load();};
$("pl-rows").addEventListener("click",function(ev){if(ev.target.closest(".al-switch"))return;var tr=ev.target.closest("tr[data-i]");if(tr)openDrawer(S.rows[+tr.getAttribute("data-i")]);});
$("pl-new").onclick=function(){openDrawer(null);};
$("pl-d-close").onclick=closeDrawer;
$("al-overlay").onclick=function(){closeDrawer();$("pl-csv-modal").hidden=true;$("pl-sku-modal").hidden=true;$("pl-cov-modal").hidden=true;$("gx-modal").hidden=true;$("cov-bulk-modal").hidden=true;};
// RC7-C gift exemptions bindings
$("gx-new").onclick=function(){openExemption(null);};
$("gx-save").onclick=saveExemption;
$("gx-cancel").onclick=closeExemption;
$("gx-rows").addEventListener("change",function(ev){var cb=ev.target;if(cb&&cb.classList&&cb.classList.contains("gx-tog"))toggleExemption(cb);});
$("gx-rows").addEventListener("click",function(ev){if(ev.target.closest(".al-switch"))return;var tr=ev.target.closest("tr[data-xi]");if(tr&&S.exRows)openExemption(S.exRows[+tr.getAttribute("data-xi")]);});
$("gx-tabs").addEventListener("click",function(ev){var b=ev.target.closest(".gx-tab");if(b)gxSetTab(b.getAttribute("data-gxs"));});
$("gx-f-apply").onclick=gxApplyFilters;
$("gx-f-clear").onclick=gxClearFilters;
$("gx-f-sku").addEventListener("keydown",function(e){if(e.key==="Enter")gxApplyFilters();});
$("gx-prev").onclick=function(){S.gx.start=Math.max(0,S.gx.start-S.gx.pageLen);loadExemptions();};
$("gx-next").onclick=function(){S.gx.start+=S.gx.pageLen;loadExemptions();};
$("e-sku-search").onclick=openSkuSearch;
$("pl-sku-go").onclick=doSkuSearch;
$("pl-sku-kw").addEventListener("keydown",function(e){if(e.key==="Enter")doSkuSearch();});
$("pl-sku-cancel").onclick=function(){$("pl-sku-modal").hidden=true;$("al-overlay").hidden=true;};
$("pl-sku-rows").addEventListener("click",function(ev){var tr=ev.target.closest("tr[data-si]");if(tr&&S.skuRows)selectSku(S.skuRows[+tr.getAttribute("data-si")]);});
$("pl-cov-go").onclick=loadCoverage;
$("pl-cov-cancel").onclick=function(){$("pl-cov-modal").hidden=true;$("al-overlay").hidden=true;};
$("pl-cov-export").onclick=exportCovTemplate;
// RC7-C bulk gift exemption from the missing-policy SKU list
$("cov-all").onclick=function(){var on=$("cov-all").checked;Array.prototype.forEach.call(document.querySelectorAll("#pl-cov-rows .cov-pick"),function(cb){cb.checked=on;});};
$("cov-bulk").onclick=openCovBulk;
$("cb-save").onclick=saveCovBulk;
$("cb-cancel").onclick=closeCovBulk;
$("pl-save").onclick=save;
$("pl-cancel").onclick=closeDrawer;
$("pl-delete").onclick=deletePolicy;
// RC5-2: per-row Status switch drives lifecycle (Activate/Pause) from the table.
$("pl-rows").addEventListener("change",function(ev){var cb=ev.target;if(cb&&cb.classList&&cb.classList.contains("pl-tog"))togglePolicyStatus(cb);});
$("pl-template").onclick=dlTemplate;
$("pl-upload").onclick=openCsv;
$("csv-preview").onclick=preview;
$("csv-import").onclick=doImport;
$("csv-cancel").onclick=function(){$("pl-csv-modal").hidden=true;$("al-overlay").hidden=true;};
$("csv-copy").onclick=copyErrs;
$("imp-src-file").onclick=function(){toggleSrc();invalidatePreview();};
$("imp-src-paste").onclick=function(){toggleSrc();invalidatePreview();};
$("csv-paste").addEventListener("input",invalidatePreview);
$("csv-file").addEventListener("change",invalidatePreview);
$("csv-all").onclick=function(){var on=$("csv-all").checked;Array.prototype.forEach.call(document.querySelectorAll("#csv-rows .csv-pick"),function(cb){cb.checked=on;});refreshImportBtn();};
$("csv-rows").addEventListener("change",function(ev){if(ev.target.classList&&ev.target.classList.contains("csv-pick"))refreshImportBtn();});
$("pl-missing-rows").addEventListener("click",function(ev){var el=ev.target.closest("[data-mbrand]");if(!el)return;openCoverageFor(el.getAttribute("data-mbrand"));});
$("e-brand").addEventListener("change",function(){applyCaps($("e-brand").value);});
["e-brand","e-platform","e-shop","e-seller_sku","e-item"].forEach(function(id){var el=$(id);if(el){el.addEventListener("change",updateScopePreview);el.addEventListener("input",updateScopePreview);}});}
if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",init);}else{init();}
})();
