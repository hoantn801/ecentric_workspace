// Copyright (c) 2026, eCentric and contributors
// Alert Center - trang Dashboard /alerts. Asset cua app tu 29/09/2026 (brief NHIEU_LOP/brief_alert_center.md);
// truoc do nam inline trong Web Page duoi dang <script id="ec-alert-center">.
// Trang nap file nay qua /assets/ecentric_workspace/alerts/ec_alert_overview.js?v=<sha>. Sua file nay thi chay
//   python -m ecentric_workspace.alerts.site_pages.assets --stamp
// roi bump BASELINE_SHA256 cua trang doi + them patch resync (test bat neu quen).
(function(){
"use strict";
var A=window.AL,$=A.$;
var S={start:0,pageLen:50,total:0,scope:null,rows:[],current:null,noteAction:null,sel:{},occ:[]};
// UX polish 2026-06-10: rules with no price context render "-" instead of 0
var NOPRICE={missing_policy:1,missing_brand_mapping:1};
function pmoney(r,v){return NOPRICE[r.rule_code]?"-":A.money(v);}
function pgap(r){if(NOPRICE[r.rule_code])return "-";return r.gap_percent!=null?A.esc(Math.round(r.gap_percent))+"%":"-";}
function occBadge(n){n=n||0;return '<span class="al-occ-n'+(n>1?" multi":"")+'">'+n+'</span>';}
// Context filters = the visible/advanced controls (date, brand, severity,
// status, search, platform, rule, owner). Feeds the KPI overview + aggregates.
function filters(){var f={};
[["f-severity","severity"],["f-status","status"],["f-rule_code","rule_code"],["f-brand","brand"],["f-platform","platform"]].forEach(function(p){var el=$(p[0]);var v=el?el.value:"";if(v)f[p[1]]=v;});
var sku=$("f-sku").value.trim();if(sku)f.seller_sku=sku;
var ow=$("f-owner");var o=ow?ow.value.trim():"";if(o)f.owner_user=o;
var a=$("f-from").value,b=$("f-to").value;if(a)f.from_date=a;if(b)f.to_date=b;return f;}
// KPI-card drill = an extra filter layer applied to the ALERTS LIST only, so a
// card click narrows the list without rewriting the overview cards. Backend
// accepts a status list (IN) and setup_only (Setup Issues view).
var KPI_DRILL={open:{status:["Open","In Review"]},critical:{status:["Open","In Review"],severity:"Critical"},warning:{status:["Open","In Review"],severity:"Warning"},resolved:{status:["Closed","Resolved"]}};
function listFilters(){var f=filters();
if(S.kpi==="setup"){delete f.rule_code;f.setup_only=1;return f;}
var d=KPI_DRILL[S.kpi];if(d){Object.keys(d).forEach(function(k){f[k]=d[k];});}return f;}
function presetDays(){var el=$("f-preset");if(!el)return 14;var v=el.value;return v===""?null:parseInt(v,10);}
function syncPresetDates(){var d=presetDays();if(d!=null){$("f-from").value=A.daysAgo(d);$("f-to").value=A.dateStr(new Date());}}
function setDefaultRange(){var el=$("f-preset");if(el)el.value="14";$("f-from").value=A.daysAgo(14);$("f-to").value=A.dateStr(new Date());}
function syncKpiActive(){Array.prototype.forEach.call(document.querySelectorAll("#al-kpis .stat-card.kpi"),function(c){var on=(c.getAttribute("data-kpi")===S.kpi);c.classList.toggle("kpi-active",on);if(c.hasAttribute("aria-pressed"))c.setAttribute("aria-pressed",on?"true":"false");});
var op=$("al-mode-op"),su=$("al-mode-setup");if(op&&su){var isS=(S.kpi==="setup");op.classList.toggle("primary",!isS);su.classList.toggle("primary",isS);}}
function setMode(setup){if(setup){S.kpi="setup";}else if(S.kpi==="setup"){S.kpi=null;}syncKpiActive();S.start=0;loadRows();renderChips();}
function applyKpi(key){if(!key)return;
if(key==="locks"){window.location.href="/alerts/locks";return;}
S.kpi=(S.kpi===key)?null:key;syncKpiActive();S.start=0;loadRows();renderChips();
// a KPI drill shows the full work queue -> switch to the Alerts subview
if(S.kpi&&window.location.hash!=="#al-alert-list"){window.location.hash="al-alert-list";}}
var KPI_LABEL={open:"\u0110ang m\u1edf",critical:"Critical",warning:"Warning",resolved:"Resolved",setup:"V\u1ea5n \u0111\u1ec1 c\u1ea5u h\u00ecnh"};
function renderChips(){var box=$("al-fchips");if(!box)return;var items=[];
function add(lbl,val,clear){items.push({lbl:lbl,val:val,clear:clear});}
if(S.kpi&&KPI_LABEL[S.kpi])add("Th\u1ebb KPI",KPI_LABEL[S.kpi],function(){S.kpi=null;syncKpiActive();});
[["f-brand","Brand"],["f-severity","Severity"],["f-status","Status"],["f-platform","Platform"],["f-rule_code","Rule"],["f-owner","Owner"]].forEach(function(p){var el=$(p[0]);if(el&&el.value)add(p[1],el.value,function(){el.value="";});});
var sk=$("f-sku").value.trim();if(sk)add("T\u00ecm SKU",sk,function(){$("f-sku").value="";});
var pd=$("f-preset")?$("f-preset").value:"14";if(pd!=="14")add("Kho\u1ea3ng th\u1eddi gian",pd===""?"Tu\u1ef3 ch\u1ec9nh":(pd+" ng\u00e0y"),function(){$("f-preset").value="14";syncPresetDates();});
box.innerHTML="";if(!items.length){box.hidden=true;return;}box.hidden=false;
items.forEach(function(it){var sp=document.createElement("span");sp.className="al-fchip";var t=document.createElement("span");t.innerHTML=A.esc(it.lbl)+': <b>'+A.esc(String(it.val))+'</b>';sp.appendChild(t);
if(it.clear){var b=document.createElement("button");b.type="button";b.setAttribute("aria-label","B\u1ecf l\u1ecdc");b.textContent="\u00d7";b.onclick=function(){it.clear();S.start=0;reload();};sp.appendChild(b);}box.appendChild(sp);});
var clr=document.createElement("button");clr.type="button";clr.className="al-fchip-clear al-btn";clr.textContent="Xo\u00e1 l\u1ecdc";clr.onclick=clearAll;box.appendChild(clr);}
function clearAll(){S.kpi=null;["f-severity","f-status","f-rule_code","f-brand","f-platform"].forEach(function(id){var el=$(id);if(el)el.value="";});$("f-sku").value="";var ow=$("f-owner");if(ow)ow.value="";setDefaultRange();syncKpiActive();S.start=0;reload();}
function toggleAdv(){var a=$("al-adv");if(!a)return;var hidden=a.hasAttribute("hidden");if(hidden)a.removeAttribute("hidden");else a.setAttribute("hidden","");var t=$("al-adv-toggle");if(t)t.setAttribute("aria-expanded",hidden?"true":"false");}
// Bar width is relative to the largest bucket: 0 -> no fill; a positive value
// -> at least a visible minimum width; the max bucket -> 100%. Per-row `cls`
// (e.g. SLA aging age0..age3) overrides the group class for progressive colour.
function bars(el,rows,cls){var max=0;rows.forEach(function(r){if(r.n>max)max=r.n;});
el.innerHTML=rows.length?rows.map(function(r){var w=(r.n>0)?Math.max(8,Math.round(r.n*100/(max||1))):0;return '<div class="al-bar-row"><span class="al-bar-key" title="'+A.esc(r.key)+'">'+A.esc(r.key)+'</span><span class="al-bar-track"><span class="al-bar-fill '+(r.cls||cls||"")+'" style="width:'+w+'%"></span></span><span class="al-bar-n">'+r.n+'</span></div>';}).join(""):'<div class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</div>';}
// ===== Charts: containers + API data + AlertCharts calls ======================
// Palettes, styling, option construction and the generic chart lifecycle live in
// the shared ERP assets (ECChartTheme / ECCharts / AlertCharts). This builder
// only: fetches data, does a MINIMAL page-specific transform, calls AlertCharts,
// and wires the resulting filter/drill-down callback. If the asset bundle failed
// to load entirely (no AlertCharts), a minimal page-level table fallback shows.
var DONUT_FILT={brand:"f-brand",platform:"f-platform",rule:"f-rule_code"};
function applyDimFilter(filtId,raw){var el=$(filtId);if(el){el.value=raw;S.start=0;reload();}}
function rawFB(boxId,fbId,html){var b=$(boxId),fb=$(fbId);if(b)b.style.display="none";if(fb){fb.hidden=false;fb.innerHTML=html;}}
// 29/09/2026 (NHIEU_LOP): MOT loi goi cho ca 3 donut (truoc la 3 lan by_dimension).
var DONUTS=[["brand","al-ch-brand","al-ch-brand-fb","Theo brand"],["platform","al-ch-platform","al-ch-platform-fb","Theo platform"],["rule_code","al-ch-rule","al-ch-rule-fb","Theo rule"]];
function loadCharts(f){function draw(by){DONUTS.forEach(function(c){var dim=(c[0]==="rule_code")?"rule":c[0];drawDonut(dim,c[1],c[2],c[3],(by&&by[c[0]])||[]);});}
A.call("api_dashboard.by_dimensions",{dims:DONUTS.map(function(c){return c[0];}),filters:f}).then(function(r){draw((r&&r.dims)||{});}).catch(function(){draw({});});}
function drawDonut(dim,boxId,fbId,label,rows){
if(window.AlertCharts){AlertCharts.renderDistributionDonut($(boxId),dim,rows,{
label:label,totalLabel:"T\u1ed5ng alert",otherLabel:"Kh\u00e1c",noneLabel:"(kh\u00f4ng c\u00f3)",
labelFor:(dim==="rule")?function(k){return A.ruleLabel(k);}:null,
fallbackEl:$(fbId),onClick:function(raw){applyDimFilter(DONUT_FILT[dim],raw);}});return;}
// asset bundle unavailable -> minimal page fallback (top 4 categories)
var tot=rows.reduce(function(s,x){return s+x.n;},0);
rawFB(boxId,fbId,tot?('<table class="al-tbl al-chart-fbt"><tbody>'+rows.slice(0,4).map(function(x){return '<tr><td>'+A.esc(dim==="rule"?A.ruleLabel(x.key):(x.key||"(kh\u00f4ng c\u00f3)"))+'</td><td class="r"><b>'+x.n+'</b></td></tr>';}).join("")+'</tbody></table>'):'<div class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</div>');}
function trendDays(){var el=$("ov-trend-days");return el?(parseInt(el.value,10)||14):14;}
function loadTrend(f){A.call("api_dashboard.trend",{filters:f,days:trendDays()}).then(function(r){drawTrend(r.rows||[]);}).catch(function(){drawTrend([]);});}
function drawTrend(rows){
// TRUTHFUL series only: api_dashboard.trend returns New / Resolved / Ignored per
// day (no per-day severity split and no historical backlog exist), so none are
// fabricated. The series/option assembly lives in AlertCharts.renderTrend.
if(window.AlertCharts){AlertCharts.renderTrend($("al-ch-trend"),rows,{
labels:{"new":"M\u1edbi",resolved:"Resolved",ignored:"Ignored",date:"Ng\u00e0y",title:"Xu h\u01b0\u1edbng c\u1ea3nh b\u00e1o"},
fallbackEl:$("al-ch-trend-fb"),onPointClick:function(day){$("f-preset").value="";$("f-from").value=day;$("f-to").value=day;S.start=0;reload();window.location.hash="al-alert-list";}});return;}
rawFB("al-ch-trend","al-ch-trend-fb",(rows&&rows.length)?('<table class="al-tbl al-chart-fbt"><thead><tr><th>Ng\u00e0y</th><th class="r">M\u1edbi</th><th class="r">Resolved</th><th class="r">Ignored</th></tr></thead><tbody>'+rows.map(function(d){return '<tr><td>'+A.esc(d.day)+'</td><td class="r">'+d.new+'</td><td class="r">'+d.resolved+'</td><td class="r">'+d.ignored+'</td></tr>';}).join("")+'</tbody></table>'):'<div class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</div>');}
function loadDash(){var f=filters();
A.call("api_dashboard.kpis",{filters:f}).then(function(c){$("al-c-open").textContent=c.open;$("al-c-critical").textContent=c.critical;$("al-c-warning").textContent=c.warning;$("al-c-setup").textContent=(c.setup_issues!=null?c.setup_issues:c.missing_policy);$("al-c-lockrev").textContent=c.lock_pending_review;$("al-c-resolved").textContent=c.resolved;}).catch(function(){});
loadCharts(f);loadTrend(f);
A.call("api_dashboard.top_skus",{filters:f,limit:10}).then(function(r){var tb=$("dash-topsku");tb.innerHTML=r.rows.length?r.rows.map(function(x){return '<tr><td>'+A.esc(x.seller_sku)+'</td><td>'+A.esc(x.brand||"-")+'</td><td><b>'+x.n+'</b></td><td>'+A.esc(A.dt(x.latest))+'</td></tr>';}).join(""):'<tr><td colspan="4" class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</td></tr>';}).catch(function(){});
A.call("api_dashboard.aging",{filters:f}).then(function(b){bars($("dash-aging"),[{key:"< 4h",n:b.lt_4h||0,cls:"age0"},{key:"4-24h",n:b.h4_24||0,cls:"age1"},{key:"1-3 ng\u00e0y",n:b.d1_3||0,cls:"age2"},{key:"> 3 ng\u00e0y",n:b.gt_3d||0,cls:"age3"}]);}).catch(function(){});}
function loadRows(){S.listStale=false;var tb=$("al-rows");tb.innerHTML='<tr><td colspan="14" class="al-empty">\u0110ang t\u1ea3i...</td></tr>';
A.call("api_alerts.list_alerts",{filters:listFilters(),start:S.start,page_len:S.pageLen}).then(function(res){S.rows=res.rows;S.total=res.total;S.sel={};syncBulk();
if(!res.rows.length){tb.innerHTML='<tr><td colspan="14" class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</td></tr>';}
else{tb.innerHTML=res.rows.map(function(r,i){return '<tr data-i="'+i+'">'+
'<td class="al-chk-col"><input type="checkbox" class="al-row-chk" data-name="'+A.esc(r.name)+'"></td>'+
'<td>'+A.esc(A.dt(r.last_seen_at||r.detected_at))+'</td>'+
'<td>'+A.sevBadge(r.severity)+'</td><td>'+A.stBadge(r.status)+'</td><td>'+A.ruleCell(r.rule_code)+'</td>'+
'<td>'+A.esc(r.brand||"-")+'</td><td>'+A.esc(r.platform||"-")+'</td><td>'+A.esc(r.shop||"-")+'</td><td>'+A.esc(r.seller_sku||r.item||"-")+'</td>'+
'<td>'+pmoney(r,r.effective_check_price!=null?r.effective_check_price:r.actual_price)+'</td><td>'+pmoney(r,r.min_price)+'</td><td>'+pgap(r)+'</td>'+
'<td>'+A.esc(r.recommended_action||"-")+'</td><td>'+A.esc(r.owner_user||"-")+'</td></tr>';}).join("");}
$("al-chk-all").checked=false;
var from=S.total?S.start+1:0;$("al-count").textContent=from+"-"+Math.min(S.start+S.pageLen,S.total)+" / "+S.total;$("al-prev").disabled=S.start<=0;$("al-next").disabled=S.start+S.pageLen>=S.total;}).catch(function(e){tb.innerHTML='<tr><td colspan="14" class="al-empty">L\u1ed7i: '+A.esc(e.message)+'</td></tr>';});}
function syncBulk(){var n=Object.keys(S.sel||{}).length;$("al-bulk-n").textContent=n;$("al-bulkbar").hidden=(n===0);}
function bulkStatus(status){var names=Object.keys(S.sel||{});if(!names.length)return;
var note=null;if(status!=="In Review"){note=window.prompt("Ghi ch\u00fa (b\u1eaft bu\u1ed9c cho Resolve/Ignore):");if(note===null)return;if(!note.trim()){A.toast("C\u1ea7n nh\u1eadp ghi ch\u00fa.");return;}}
A.call("api_alerts.bulk_set_status",{names:names,new_status:status,note:note}).then(function(res){A.toast("\u0110\u00e3 c\u1eadp nh\u1eadt "+(res.ok?res.ok.length:0)+" / "+names.length);S.sel={};reload();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
// 29/09/2026 (NHIEU_LOP): danh sach alert (#al-alert-list) AN o che do Tong quan -> chi tai
// khi dang mo; neu dang an thi danh dau "cu" de applyHashNav tai lai luc mo (1 lan, khong trung).
function listShown(){return window.location.hash==="#al-alert-list";}
function reload(){loadDash();if(listShown())loadRows();else S.listStale=true;renderChips();}
function openDrawer(r){S.current=r;S.occ=[];$("al-d-title").textContent=r.name;
var occn=r.occurrence_count||0;
$("al-d-sub").innerHTML=A.stBadge(r.status)+' &middot; '+A.esc(r.seller_sku||r.item||"-")+' &middot; '+A.ruleCell(r.rule_code)+' '+A.sevBadge(r.severity)+(occn>1?' <span class="al-case-pill">'+occn+' \u0111\u01a1n vi ph\u1ea1m</span>':'');
function kvdl(rows){return '<dl class="al-kv al-kv-wide">'+rows.map(function(p){return "<dt>"+p[0]+"</dt><dd>"+p[1]+"</dd>";}).join("")+'</dl>';}
var dSummary=[["Rule",A.ruleCell(r.rule_code)],["Severity",A.sevBadge(r.severity)],["Status",A.stBadge(r.status)],["\u0110\u1ec1 xu\u1ea5t x\u1eed l\u00fd",A.esc(r.recommended_action||"-")]];
var dEvidence=[["Gi\u00e1 check",pmoney(r,r.effective_check_price!=null?r.effective_check_price:r.actual_price)],["Min",pmoney(r,r.min_price)],["Baseline / Reference",pmoney(r,r.baseline_price)],["Gap",pgap(r)]];
var dScope=[["Brand",A.esc(r.brand||"-")],["Platform",A.esc(r.platform||"-")],["Shop",A.esc(r.shop||"-")],["SKU",A.esc(r.seller_sku||r.item||"-")],["Ti\u00eau \u0111\u1ec1",A.esc(r.title)]];
// Raw price_components_used string lives ONLY in Technical Details (and CSV) -
// business users see the friendly breakdown rows, not the raw code string.
var dTech=[["Rule code (raw)",A.esc(r.rule_code)],["Th\u00e0nh ph\u1ea7n gi\u00e1",A.esc(r.price_components_used||"-")],["Ref doctype",A.esc(r.reference_doctype||"-")],["Ref name",A.esc(r.reference_name||"-")],["Owner",A.esc(r.owner_user||"-")],["S\u1ed1 \u0111\u01a1n vi ph\u1ea1m",occBadge(occn)],["Ph\u00e1t hi\u1ec7n \u0111\u1ea7u",A.esc(A.dt(r.first_seen_at||r.detected_at))],["L\u1ea7n g\u1ea7n nh\u1ea5t",A.esc(A.dt(r.last_seen_at||r.detected_at))],["Action",A.actBadge(r.action_status)]];
$("al-d-kv").innerHTML='<div class="al-fsec">T\u00f3m t\u1eaft</div>'+kvdl(dSummary)+'<div class="al-fsec">B\u1eb1ng ch\u1ee9ng gi\u00e1</div>'+kvdl(dEvidence)+'<div class="al-fsec">Ph\u1ea1m vi</div>'+kvdl(dScope)+'<details class="al-tech"><summary class="al-fsec" style="cursor:pointer">Chi ti\u1ebft k\u1ef9 thu\u1eadt</summary>'+kvdl(dTech)+'</details>';
refreshAlertFooter(r.status);
$("al-d-occ").innerHTML='<div class="al-help">\u0110ang t\u1ea3i...</div>';
A.call("api_alerts.alert_occurrences",{alert:r.name,page_len:50}).then(function(res){renderOcc(res.rows||[],res.total||0);}).catch(function(e){$("al-d-occ").innerHTML='<div class="al-help">L\u1ed7i: '+A.esc(e.message)+'</div>';});
$("al-d-acts").innerHTML="";A.call("api_actions.list_for_alert",{alert:r.name}).then(function(rows){if(!rows||!rows.length)return;$("al-d-acts").innerHTML='<div class="al-actrows"><b>Actions</b><br>'+rows.map(function(a2){return A.esc(a2.name)+" "+A.actBadge(a2.status)+" "+A.esc(a2.lock_reason||a2.error_message||"");}).join("<br>")+"</div>";}).catch(function(){});
$("al-overlay").hidden=false;$("al-drawer").hidden=false;}
function brk(label,val,cls){return '<tr><td>'+label+'</td><td class="r '+(cls||"")+'">'+(val?("-"+A.money(val)):A.money(0))+'</td></tr>';}
// B2: the price-calculation panel is sourced from the SELECTED EC Alert Occurrence
// row (defaults to the latest violating occurrence = rows[0]). Every value comes
// from that row; nothing is fabricated and the alert-summary values are not used
// once a row is selected. CSV export stays based on the FULL list (S.occ).
function renderCalc(o){if(!o)return;
$("al-calc").innerHTML='<div class="al-fsec">C\u00e1ch t\u00ednh gi\u00e1 check &middot; M\u00e3 \u0111\u01a1n Omisell '+A.esc(o.external_order_id||"-")+'</div><div class="al-breakdown"><table>'+
'<tr><td>RSP</td><td class="r">'+A.money(o.rsp_price)+'</td></tr>'+
brk("Seller discount",o.seller_discount_amount,"minus")+
brk("Seller voucher",o.seller_voucher_amount,"minus")+
brk("Platform discount",o.platform_discount_amount,"minus")+
brk("Platform voucher",o.platform_voucher_amount,"minus")+
'<tr class="eff"><td>= Gi\u00e1 check hi\u1ec7u l\u1ef1c</td><td class="r">'+A.money(o.effective_check_price)+'</td></tr>'+
'<tr><td>Min</td><td class="r">'+A.money(o.min_price_at_check)+'</td></tr>'+
'<tr><td>Baseline / Reference</td><td class="r">'+A.money(o.baseline_price_at_check)+'</td></tr>'+
'<tr><td>Gap</td><td class="r">'+(o.gap_percent!=null?A.esc(Math.round(o.gap_percent))+"%":"-")+'</td></tr>'+
'</table><div class="al-help" title="'+A.esc(o.price_components_used||"")+'">'+A.esc(A.dt(o.order_datetime))+' &middot; '+A.esc(o.order_status||"-")+'</div></div>';}
function selectOcc(i){if(!S.occ||!S.occ[i])return;S.selOcc=i;renderCalc(S.occ[i]);
var bd=$("al-occ-body");if(bd)Array.prototype.forEach.call(bd.querySelectorAll("tr[data-oi]"),function(tr){tr.classList.toggle("al-occ-sel",+tr.getAttribute("data-oi")===i);});}
function renderOcc(rows,total){
S.occ=rows||[];S.selOcc=0;
if(!rows.length){$("al-d-occ").innerHTML='<div class="al-fsec">B\u1eb1ng ch\u1ee9ng theo \u0111\u01a1n</div><div class="al-help">Ch\u01b0a c\u00f3 occurrence cho case n\u00e0y.</div>';return;}
var head='<tr><th>M\u00e3 \u0111\u01a1n Omisell</th><th>Th\u1eddi gian</th><th>Tr\u1ea1ng th\u00e1i</th><th>SKU</th><th class="r">RSP</th><th class="r">Seller discount</th><th class="r">Seller voucher</th><th class="r">Platform discount</th><th class="r">Platform voucher</th><th class="r">Gi\u00e1 check hi\u1ec7u l\u1ef1c</th><th class="r">Min</th><th class="r">Gap</th><th>Rule</th></tr>';
var body=rows.map(function(x,i){return '<tr class="al-occ-row'+(i===0?" al-occ-sel":"")+'" data-oi="'+i+'" tabindex="0" role="button" aria-label="Ch\u1ecdn \u0111\u01a1n '+A.esc(x.external_order_id||"-")+'">'+
'<td>'+A.esc(x.external_order_id||"-")+'</td><td>'+A.esc(A.dt(x.order_datetime))+'</td><td>'+A.esc(x.order_status||"-")+'</td>'+
'<td title="'+A.esc(x.product_name||"")+'">'+A.esc(x.seller_sku||"-")+'</td>'+
'<td class="r">'+A.money(x.rsp_price)+'</td><td class="r">'+A.money(x.seller_discount_amount)+'</td><td class="r">'+A.money(x.seller_voucher_amount)+'</td><td class="r">'+A.money(x.platform_discount_amount)+'</td><td class="r">'+A.money(x.platform_voucher_amount)+'</td>'+
'<td class="r"><b>'+A.money(x.effective_check_price)+'</b></td><td class="r">'+A.money(x.min_price_at_check)+'</td><td class="r">'+(x.gap_percent!=null?A.esc(Math.round(x.gap_percent))+"%":"-")+'</td>'+
'<td title="'+A.esc(x.price_components_used||"")+'">'+A.ruleCell(x.rule_code)+' '+A.sevBadge(x.severity)+'</td></tr>';}).join("");
$("al-d-occ").innerHTML='<div id="al-calc" class="al-calc"></div><div class="al-occ-wrap'+(total>1?" hl":"")+'"><div class="al-occ-head"><div class="al-fsec" style="margin:0">B\u1eb1ng ch\u1ee9ng theo \u0111\u01a1n ('+total+')</div><div><button class="al-btn" id="al-occ-export">Xu\u1ea5t CSV</button> <button class="al-btn" id="al-occ-copy">Copy CSV</button></div></div><div class="al-tbl-wrap"><table class="al-occ-tbl"><thead>'+head+'</thead><tbody id="al-occ-body">'+body+'</tbody></table></div></div>';
renderCalc(rows[0]); // default selection = latest violating occurrence
var bd=$("al-occ-body");if(bd){bd.addEventListener("click",function(ev){var tr=ev.target.closest("tr[data-oi]");if(tr)selectOcc(+tr.getAttribute("data-oi"));});
bd.addEventListener("keydown",function(ev){if(ev.key!=="Enter"&&ev.key!==" "&&ev.key!=="Spacebar")return;var tr=ev.target.closest("tr[data-oi]");if(tr){ev.preventDefault();selectOcc(+tr.getAttribute("data-oi"));}});}
var ex=$("al-occ-export");if(ex)ex.onclick=exportOccCsv;var cp=$("al-occ-copy");if(cp)cp.onclick=copyOccCsv;}
var OCC_CSV_COLS=["external_order_id","order_datetime","order_status","seller_sku","product_name","rsp_price","seller_discount_amount","seller_voucher_amount","platform_discount_amount","platform_voucher_amount","effective_check_price","min_price_at_check","baseline_price_at_check","gap_percent","rule_code","severity","detected_at","price_components_used"];
function occCsv(){var rows=S.occ||[];var q=function(v){v=(v==null?"":String(v));if(/[",\n]/.test(v))v='"'+v.replace(/"/g,'""')+'"';return v;};
var lines=[OCC_CSV_COLS.join(",")];rows.forEach(function(x){lines.push(OCC_CSV_COLS.map(function(c){return q(x[c]);}).join(","));});return lines.join("\n");}
function exportOccCsv(){if(!S.current||!(S.occ&&S.occ.length)){A.toast("Ch\u01b0a c\u00f3 occurrence cho case n\u00e0y.");return;}
var blob=new Blob(["\ufeff"+occCsv()],{type:"text/csv;charset=utf-8;"});var url=URL.createObjectURL(blob);
var a=document.createElement("a");a.href=url;a.download="alert_occurrences_"+S.current.name+".csv";document.body.appendChild(a);a.click();document.body.removeChild(a);
setTimeout(function(){URL.revokeObjectURL(url);},1000);A.toast("\u0110\u00e3 xu\u1ea5t CSV.");}
function copyOccCsv(){if(!(S.occ&&S.occ.length)){A.toast("Ch\u01b0a c\u00f3 occurrence cho case n\u00e0y.");return;}var csv=occCsv();
if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(csv).then(function(){A.toast("\u0110\u00e3 copy CSV.");}).catch(function(){A.toast("L\u1ed7i: ");});}else{A.toast("L\u1ed7i: ");}}
function closeDrawer(){$("al-overlay").hidden=true;$("al-drawer").hidden=true;S.current=null;}
function setStatus(status){if(!S.current)return;
if(status==="In Review"){A.call("api_alerts.set_status",{alert:S.current.name,new_status:status}).then(function(){A.toast("\u0110\u00e3 c\u1eadp nh\u1eadt.");closeDrawer();reload();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});return;}
S.noteAction=status;$("al-note-title").textContent=status;$("al-note-text").value="";$("al-note-modal").hidden=false;$("al-overlay").hidden=false;}
function confirmNote(){var note=$("al-note-text").value.trim();if(!note){A.toast("C\u1ea7n nh\u1eadp ghi ch\u00fa.");return;}
A.call("api_alerts.set_status",{alert:S.current.name,new_status:S.noteAction,note:note}).then(function(){$("al-note-modal").hidden=true;A.toast("\u0110\u00e3 c\u1eadp nh\u1eadt.");closeDrawer();reload();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
// Lifecycle footer visibility by state: Open -> Claim (primary); In Review ->
// Resolve (primary); Ignore lives in the More menu for active cases; terminal
// cases have no primary action. (Automation Pause is NOT here - it belongs to
// Stock Safety / Automation Pauses only.)
// RC4-4: Open -> Claim + Ignore; In Review -> Resolve + Ignore; terminal -> none.
function refreshAlertFooter(st){var claim=$("al-d-claim"),res=$("al-d-resolve"),ig=$("al-d-ignore");
var active=(st==="Open"||st==="In Review");
if(claim)claim.hidden=(st!=="Open");
if(res)res.hidden=(st!=="In Review");
if(ig)ig.hidden=!active;}
function loadRecent(){var tb=$("ov-recent-rows");if(!tb)return;
A.call("api_alerts.list_alerts",{filters:{severity:"Critical",status:["Open","In Review"]},start:0,page_len:5}).then(function(res){var rows=res.rows||[];S.recent=rows;
tb.innerHTML=rows.length?rows.map(function(r,i){return '<tr class="al-rowlink" data-ri="'+i+'" tabindex="0" role="button" aria-label="M\u1edf alert '+A.esc(r.name)+'"><td>'+A.esc(A.dt(r.last_seen_at||r.detected_at))+'</td><td>'+A.sevBadge(r.severity)+'</td><td>'+A.esc(r.brand||"-")+'</td><td>'+A.esc(r.seller_sku||r.item||"-")+'</td><td>'+A.ruleCell(r.rule_code)+'</td><td>'+pgap(r)+'</td><td>'+A.stBadge(r.status)+'</td></tr>';}).join(""):'<tr><td colspan="7" class="al-empty">Kh\u00f4ng c\u00f3 c\u1ea3nh b\u00e1o nghi\u00eam tr\u1ecdng \u0111ang m\u1edf.</td></tr>';}).catch(function(){tb.innerHTML='<tr><td colspan="7" class="al-empty">-</td></tr>';});}
function openRecent(i){var r=(S.recent||[])[i];if(r)openDrawer(r);}
function applyHashNav(){
  var atList=(window.location.hash==="#al-alert-list");
  // Overview (no hash) vs Alerts (#al-alert-list) subviews on /alerts.
  var links=document.querySelectorAll(".ec-sidebar a.nav-item");
  links.forEach(function(a){var hrefp=(a.getAttribute("href")||"");
    if(hrefp==="/alerts"){a.classList.toggle("active",!atList);}
    else if(hrefp.indexOf("#al-alert-list")>=0){a.classList.toggle("active",atList);}});
  var ov=$("ov-dash"),rec=$("ov-recent"),note=$("al-snapshot-note"),list=$("al-alert-list"),tr=$("ov-trend");
  if(ov)ov.hidden=atList;if(rec)rec.hidden=atList;if(note)note.hidden=atList;if(list)list.hidden=!atList;if(tr)tr.hidden=atList;
  if(atList){if(S.listStale)loadRows();if(list)list.scrollIntoView({behavior:"smooth",block:"start"});}else{loadRecent();setTimeout(function(){if(window.ECCharts)ECCharts.resizeAll();},60);}
}
function init(){setDefaultRange();
A.initScope("/alerts",function(scope){S.scope=scope;
A.scopeLine($("al-scope-line"),scope.supervisor?"Supervisor scope: all brands":("Brands: "+Object.keys(scope.brands).join(", ")));
var bsel=$("f-brand");Object.keys(scope.brands||{}).forEach(function(b){var o=document.createElement("option");o.value=b;o.textContent=b;bsel.appendChild(o);});
A.relabelRuleOptions($("f-rule_code"));
syncKpiActive();renderChips();
reload();
applyHashNav();});
window.addEventListener("hashchange",applyHashNav);
var _va=$("ov-viewall");if(_va)_va.onclick=function(){window.location.hash="al-alert-list";};
var _rr=$("ov-recent-rows");if(_rr){_rr.addEventListener("click",function(ev){var tr=ev.target.closest("tr[data-ri]");if(tr)openRecent(+tr.getAttribute("data-ri"));});
_rr.addEventListener("keydown",function(ev){if(ev.key!=="Enter"&&ev.key!==" "&&ev.key!=="Spacebar")return;var tr=ev.target.closest("tr[data-ri]");if(tr){ev.preventDefault();openRecent(+tr.getAttribute("data-ri"));}});}
var _mo=$("al-mode-op");if(_mo)_mo.onclick=function(){setMode(false);};
var _ms=$("al-mode-setup");if(_ms)_ms.onclick=function(){setMode(true);};
$("al-apply").onclick=function(){S.start=0;reload();};
$("al-clear").onclick=clearAll;
$("f-preset").onchange=function(){syncPresetDates();S.start=0;reload();};
$("al-adv-toggle").onclick=toggleAdv;
$("al-kpis").addEventListener("click",function(ev){var c=ev.target.closest(".stat-card.kpi");if(c)applyKpi(c.getAttribute("data-kpi"));});
$("al-kpis").addEventListener("keydown",function(ev){if(ev.key!=="Enter"&&ev.key!==" "&&ev.key!=="Spacebar")return;var c=ev.target.closest(".stat-card.kpi");if(c){ev.preventDefault();applyKpi(c.getAttribute("data-kpi"));}});
// Charts: one debounced window-resize listener (owned by ECCharts; idempotent);
// reload only the trend when the 7/14/30-day preset changes.
if(window.ECCharts)ECCharts.attachResize();
var _td=$("ov-trend-days");if(_td)_td.onchange=function(){loadTrend(filters());};
$("al-refresh").onclick=reload;
$("al-prev").onclick=function(){S.start=Math.max(0,S.start-S.pageLen);loadRows();};
$("al-next").onclick=function(){S.start+=S.pageLen;loadRows();};
$("al-rows").addEventListener("click",function(ev){if(ev.target.classList.contains("al-row-chk"))return;var tr=ev.target.closest("tr[data-i]");if(tr)openDrawer(S.rows[+tr.getAttribute("data-i")]);});
$("al-rows").addEventListener("change",function(ev){var c=ev.target;if(!c.classList.contains("al-row-chk"))return;var nm=c.getAttribute("data-name");if(c.checked)S.sel[nm]=1;else delete S.sel[nm];syncBulk();
var all=Array.prototype.slice.call(document.querySelectorAll(".al-row-chk"));$("al-chk-all").checked=all.length>0&&all.every(function(x){return x.checked;});});
$("al-chk-all").onchange=function(){var on=$("al-chk-all").checked;document.querySelectorAll(".al-row-chk").forEach(function(c){c.checked=on;var nm=c.getAttribute("data-name");if(on)S.sel[nm]=1;else delete S.sel[nm];});syncBulk();};
$("al-bulk-review").onclick=function(){bulkStatus("In Review");};
$("al-bulk-resolve").onclick=function(){bulkStatus("Resolved");};
$("al-bulk-ignore").onclick=function(){bulkStatus("Ignored");};
$("al-d-close").onclick=closeDrawer;
$("al-overlay").onclick=function(){closeDrawer();$("al-note-modal").hidden=true;};
$("al-d-claim").onclick=function(){setStatus("In Review");};
$("al-d-resolve").onclick=function(){setStatus("Closed");};
$("al-d-ignore").onclick=function(){setStatus("Ignored");};
$("al-note-ok").onclick=confirmNote;$("al-note-cancel").onclick=function(){$("al-note-modal").hidden=true;};}
if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",init);}else{init();}
})();
