// Copyright (c) 2026, eCentric and contributors
// Alert Center - trang Rules /alerts/rules. Asset cua app tu 29/09/2026 (brief NHIEU_LOP/brief_alert_center.md);
// truoc do nam inline trong Web Page duoi dang <script id="ec-alert-rules">.
// Trang nap file nay qua /assets/ecentric_workspace/alerts/ec_alert_rules.js?v=<sha>. Sua file nay thi chay
//   python -m ecentric_workspace.alerts.site_pages.assets --stamp
// roi bump BASELINE_SHA256 cua trang doi + them patch resync (test bat neu quen).
(function(){
"use strict";
var A=window.AL,$=A.$;
var S={scope:null,rows:[],current:null,editing:{}};
var RFIELDS=["rule_code","platform","shop","seller_sku","item","severity_override","threshold_percent","severe_drop_percent","high_alert_percent","effective_from","effective_to"];
function tierOf(o){if(o.seller_sku||o.item)return "SKU";if(o.shop)return "Shop";if(o.platform&&o.platform!=="All")return "Platform";return "Brand";}
// ===== Canonical scope-precedence resolver (frontend mirror of the backend
// services/rule_overlay._match_score + find_rules). The threshold for a rule_code
// is taken from the MOST SPECIFIC matching rule (SKU 8 > Shop 4 > Platform 2 >
// Brand 1), resolved INDEPENDENTLY per rule_code. No merging, no implicit
// "stricter value". "All platforms" = the platform=All (Brand Default) row.
var RULE_THRESHOLD_FIELD={below_min:"threshold_percent",severe_price_drop:"severe_drop_percent",above_high:"high_alert_percent"};
function ruleMatchScore(r,ctx){var s=1;
if(r.platform&&r.platform!=="All"){if(!ctx.platform||r.platform!==ctx.platform)return null;s+=2;}
if(r.shop){if(!ctx.shop||r.shop!==ctx.shop)return null;s+=4;}
if(r.seller_sku||r.item){var skuOk=r.seller_sku&&ctx.seller_sku&&r.seller_sku===ctx.seller_sku;var itemOk=r.item&&ctx.item&&r.item===ctx.item;if(!(skuOk||itemOk))return null;s+=8;}
return s;}
function resolveRule(rules,ctx,code){var best=null,bs=-1;(rules||[]).forEach(function(r){if(r.rule_code!==code)return;if(r.status==="Paused")return;/* RC5-4: a paused override is NOT active in the resolver */var sc=ruleMatchScore(r,ctx);if(sc===null)return;if(sc>bs){bs=sc;best=r;}});return best;}
function resolveThreshold(rules,ctx,code){var r=resolveRule(rules,ctx,code);if(!r)return null;var f=RULE_THRESHOLD_FIELD[code];var v=(f&&r[f]!=null&&r[f]!=="")?r[f]:(r.threshold_percent!=null&&r.threshold_percent!==""?r.threshold_percent:null);return v==null?null:parseFloat(v);}
// threshold value of ONE rule row, by its rule_code's canonical field.
function ruleThrVal(r){if(!r)return null;var f=RULE_THRESHOLD_FIELD[r.rule_code];var v=(f&&r[f]!=null&&r[f]!=="")?r[f]:(r.threshold_percent!=null&&r.threshold_percent!==""?r.threshold_percent:null);return v==null?null:v;}
// Deterministic precedence self-test (50/60/70 example for ALL three rule codes;
// throws if precedence ever merges or picks the wrong tier). Runs once at load.
function rulePrecedenceSelfTest(){
function ds(p){return {rule_code:"severe_price_drop",platform:p.pf,seller_sku:p.sku,severe_drop_percent:p.t};}
var SD=[ds({pf:"All",t:50}),ds({pf:"Shopee",t:60}),{rule_code:"severe_price_drop",seller_sku:"SKU1",severe_drop_percent:70}];
function eq(a,b,m){if(a!==b)throw new Error("precedence "+m+": "+a+"!="+b);}
eq(resolveThreshold(SD,{platform:"Lazada"},"severe_price_drop"),50,"brand");
eq(resolveThreshold(SD,{platform:"Shopee"},"severe_price_drop"),60,"platform");
eq(resolveThreshold(SD,{platform:"Shopee",seller_sku:"SKU1"},"severe_price_drop"),70,"sku");
if(!(55>=resolveThreshold(SD,{platform:"Lazada"},"severe_price_drop")))throw new Error("55 must alert generic");
if(55>=resolveThreshold(SD,{platform:"Shopee"},"severe_price_drop"))throw new Error("55 must NOT alert Shopee");
if(55>=resolveThreshold(SD,{platform:"Shopee",seller_sku:"SKU1"},"severe_price_drop"))throw new Error("55 must NOT alert SKU");
var BM=[{rule_code:"below_min",platform:"All",threshold_percent:50},{rule_code:"below_min",platform:"Shopee",threshold_percent:60},{rule_code:"below_min",seller_sku:"SKU1",threshold_percent:70}];
eq(resolveThreshold(BM,{platform:"Lazada"},"below_min"),50,"bm-brand");eq(resolveThreshold(BM,{platform:"Shopee"},"below_min"),60,"bm-platform");eq(resolveThreshold(BM,{platform:"Shopee",seller_sku:"SKU1"},"below_min"),70,"bm-sku");
var AH=[{rule_code:"above_high",platform:"All",high_alert_percent:50},{rule_code:"above_high",platform:"Shopee",high_alert_percent:60},{rule_code:"above_high",seller_sku:"SKU1",high_alert_percent:70}];
eq(resolveThreshold(AH,{platform:"Lazada"},"above_high"),50,"ah-brand");eq(resolveThreshold(AH,{platform:"Shopee"},"above_high"),60,"ah-platform");eq(resolveThreshold(AH,{platform:"Shopee",seller_sku:"SKU1"},"above_high"),70,"ah-sku");
return true;}
function tierBadge(t){var m={SKU:"al-b-critical",Shop:"al-b-pending",Platform:"al-b-dryrun",Brand:"al-b-info"};var L={SKU:"SKU Exception",Shop:"Shop Override",Platform:"Platform Override",Brand:"Brand Default"};return '<span class="al-badge '+(m[t]||"al-b-info")+'" title="'+t+'">'+(L[t]||t)+'</span>';}
function ruBadge(v){return '<span class="al-badge '+({Draft:"al-b-draft",Active:"al-b-active",Paused:"al-b-paused"}[v]||"al-b-info")+'">'+A.esc(v)+'</span>';}
function filters(){var f={};[["f-brand","brand"],["f-rule_code","rule_code"],["f-status","status"]].forEach(function(p){var v=$(p[0]).value;if(v)f[p[1]]=v;});return f;}
function canActivate(){if(!S.scope)return false;if(S.scope.supervisor)return true;var b=$("r-brand")?$("r-brand").value:null;var role=b&&S.scope.brands?S.scope.brands[b]:null;return role==="manager"||role==="leader";}
function findRule(nm){for(var i=0;i<S.rows.length;i++){if(S.rows[i].name===nm)return S.rows[i];}return null;}
var BEHAVIORS=[["below_min","D\u01b0\u1edbi gi\u00e1 t\u1ed1i thi\u1ec3u"],["severe_price_drop","R\u1edbt gi\u00e1 m\u1ea1nh"],["above_high","V\u01b0\u1ee3t benchmark"]];
function ruleAction(r){return r.recommend_stock_lock?"Recommend Stock Safety":"Alert Only";}
function ruleThreshold(r){var t=(r.severe_drop_percent||r.high_alert_percent||r.threshold_percent);return (t!=null&&t!=="")?(A.esc(t)+"%"):"-";}
// E2 business editor: per brand, each behaviour shows the "All platforms" Brand
// Default threshold + an optional "Customize by platform" panel (Shopee/Lazada/
// TikTok). A platform with its own rule is OVERRIDDEN (replaces the brand default
// for that rule type only); otherwise it INHERITS the brand default. "All
// platforms" is purely the UI name for the platform=All Brand Default row - no
// new rule code / scope type is introduced.
var RU_PLATFORMS=["Shopee","Lazada","TikTok"];
function thrTxt(r){var v=ruleThrVal(r);return (v!=null&&v!=="")?(A.esc(v)+"%"):"-";}
// RC4-6: each (brand, behaviour) is edited INLINE in the card. The All-platforms
// row carries an editable threshold input + inline Save; each platform row carries
// its own inline input (inherited placeholder vs an explicit override) + Save and,
// when overridden, a Remove-customization that falls back to All platforms. No
// drawer. Exactly one threshold per behaviour; a platform input affects only that
// behaviour's rule_code; the backend remains the evaluation source of truth.
function renderDefaults(rows){var brands={};
// RC5-4: when duplicate rows of the same scope exist (legacy data), prefer a
// NON-Paused row so the renderer and the resolver can never disagree.
function better(cur,nr){if(!cur)return nr;if(cur.status==="Paused"&&nr.status!=="Paused")return nr;return cur;}
rows.forEach(function(r){var bb=(brands[r.brand]=brands[r.brand]||{});var cc=(bb[r.rule_code]=bb[r.rule_code]||{ov:{}});
if(!r.platform||r.platform==="All")cc.def=better(cc.def,r);else cc.ov[r.platform]=better(cc.ov[r.platform],r);});
var blist=Object.keys((S.scope&&S.scope.brands)||{});Object.keys(brands).forEach(function(b){if(blist.indexOf(b)<0)blist.push(b);});
var dd=$("ru-defaults");
if(!blist.length){dd.innerHTML='<div class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</div>';return;}
dd.innerHTML=blist.sort().map(function(b){var m=brands[b]||{};
var beh=BEHAVIORS.map(function(bh){var code=bh[0];var c=m[code]||{ov:{}};var dr=c.def;
var allActive=isActiveRule(dr)&&ruleThrVal(dr)!=null;var allVal=allActive?A.esc(ruleThrVal(dr)):"";
var allBadge=dr?ruBadge(dr.status):'<span class="al-badge al-b-ignored">Ch\u01b0a c\u1ea5u h\u00ecnh</span>';
// All-platforms (Brand Default) cell: always editable - it is the base value.
var allCell='<span class="ru-pf ru-pf-all">T\u1ea5t c\u1ea3 platform</span>'+
  '<input class="ru-i-all" type="number" step="0.01" min="0" max="100" value="'+allVal+'" placeholder="Ng\u01b0\u1ee1ng %"><span class="ru-unit">%</span>'+
  '<button class="al-btn primary ru-mini" data-save-all="1">L\u01b0u</button> '+allBadge;
// RC5-4 explicit per-platform STATE MACHINE: inherited (read-only "Ke thua X
// percent", only "Them tuy chinh", NO save) vs override editing/active (editable
// input, "Tuy chinh", "Luu" + "Bo tuy chinh").
var nOv=0;var ovHtml=RU_PLATFORMS.map(function(pf){var orr=c.ov[pf];var hasOv=isActiveRule(orr)&&ruleThrVal(orr)!=null;if(hasOv)nOv++;
var editing=hasOv||(S.editing&&S.editing[b+"|"+code+"|"+pf]);var mid,acts;
if(editing){
  mid='<span class="ru-mid"><input class="ru-i-pf" type="number" step="0.01" min="0" max="100" value="'+(hasOv?A.esc(ruleThrVal(orr)):"")+'" placeholder="Ng\u01b0\u1ee1ng %"><span class="ru-unit">%</span> <span class="al-badge al-b-dryrun" title="override">T\u00f9y ch\u1ec9nh</span></span>';
  // RC7-B: ONE primary action (Save). "Bo tuy chinh" demoted to a small destructive
  // icon so the row never shows two competing buttons / a far-right action cluster.
  acts='<span class="ru-acts"><button class="al-btn primary ru-mini" data-save-pf="'+pf+'">L\u01b0u</button><button class="al-btn ru-icon ru-danger" data-rm-pf="'+pf+'" title="B\u1ecf t\u00f9y ch\u1ec9nh" aria-label="B\u1ecf t\u00f9y ch\u1ec9nh">\u2715</button></span>';
}else{
  var inh=(allVal!==""?("K\u1ebf th\u1eeba "+allVal+"%"):("K\u1ebf th\u1eeba \u2014"));
  mid='<span class="ru-mid"><span class="ru-inh-val" title="k\u1ebf th\u1eeba Brand Default">'+inh+'</span></span>';
  acts='<span class="ru-acts"><button class="al-btn ru-mini" data-add-pf="'+pf+'">Th\u00eam t\u00f9y ch\u1ec9nh</button></span>';
}
return '<div class="ru-ovrow" data-pf="'+pf+'"><span class="ru-pf">'+pf+'</span>'+mid+acts+'</div>';}).join("");
var custLabel="T\u00f9y ch\u1ec9nh theo platform"+(nOv?(' <span class="al-chip-n">'+nOv+'</span>'):'');
return '<div class="ru-beh" data-brand="'+A.esc(b)+'" data-code="'+code+'"><div class="ru-beh-head"><div class="ru-beh-h">'+bh[1]+'</div><div class="ru-beh-all">'+allCell+'</div></div><details class="al-adv-sec ru-cust"'+(nOv?" open":"")+'><summary class="al-fsec" style="cursor:pointer;list-style:revert;margin:6px 0 4px">'+custLabel+'</summary><div class="ru-ovrows">'+ovHtml+'<div class="al-help">S\u1ebd d\u00f9ng l\u1ea1i gi\u00e1 tr\u1ecb All platforms</div></div></details></div>';}).join("");
return '<div class="ru-brand"><div class="ru-brand-h">'+A.esc(b)+'</div><div class="ru-brand-body">'+beh+'</div></div>';}).join("");}
function renderExceptions(exc){var tb=$("ru-rows");
if(!exc.length){tb.innerHTML='<tr><td colspan="12" class="al-empty">Kh\u00f4ng c\u00f3 exception n\u00e0o.</td></tr>';return;}
tb.innerHTML=exc.map(function(r){return '<tr data-rn="'+A.esc(r.name)+'">'+
'<td>'+A.ruleCell(r.rule_code)+'</td><td>'+tierBadge(tierOf(r))+'</td><td>'+A.esc(r.brand)+'</td><td>'+A.esc(r.platform||"All")+'</td><td>'+A.esc(r.shop||"-")+'</td><td>'+A.esc(r.seller_sku||r.item||"-")+'</td>'+
'<td>'+A.esc(r.severity_override||"-")+'</td><td>'+ruleThreshold(r)+'</td>'+
'<td>'+(r.recommend_stock_lock?'<span class="al-badge al-b-dryrun">Recommend Stock Safety</span>':"-")+'</td>'+
'<td>'+ruBadge(r.status)+'</td><td>'+A.esc(r.approved_by||"-")+'</td><td>'+A.esc((r.effective_from||"")+(r.effective_to?(" \u2192 "+r.effective_to):""))+'</td></tr>';}).join("");}
function load(){$("ru-defaults").innerHTML='<div class="al-empty">\u0110ang t\u1ea3i...</div>';$("ru-rows").innerHTML='<tr><td colspan="12" class="al-empty">\u0110ang t\u1ea3i...</td></tr>';
A.call("api_rules.list_rules",{filters:filters()}).then(function(res){S.rows=res.rows;
// E2: Brand Default (All) + Platform overrides feed the brand-card editor; Shop /
// SKU exceptions remain in the Advanced Exceptions table.
var defs=[],exc=[];res.rows.forEach(function(r){var t=tierOf(r);if(t==="Brand"||t==="Platform")defs.push(r);else exc.push(r);});
renderDefaults(defs);renderExceptions(exc);}).catch(function(e){$("ru-defaults").innerHTML='<div class="al-empty">L\u1ed7i: '+A.esc(e.message)+'</div>';});}
// EC Field Description adapter: override the static title/aria-label fallbacks
// with the live description when the doctype is present (loaded by initScope).
function applyFieldHelp(root){var els=(root||document).querySelectorAll("[data-help]");Array.prototype.forEach.call(els,function(el){var h=A.fieldHelp(el.getAttribute("data-help"));if(h&&h.help){el.title=h.help;el.setAttribute("aria-label",h.help);}});}
// E3 editor: a (brand, behaviour) unit = the All-platforms Brand Default rule +
// the Shopee/Lazada/TikTok override rules. The rule API (EDITABLE) only persists
// `threshold_percent`, so every behaviour writes that single field; the backend
// overlay maps it to the right behaviour by rule_code. The per-behaviour fields
// (severe_drop_percent/high_alert_percent) are doctype-only / read-fallback and
// are NOT in the rule API - writing them would need a backend change (out of
// scope). So the editor shows exactly ONE threshold input per behaviour.
var RU_OV_PF=["Shopee","Lazada","TikTok"];
var RULE_SAVE_THR_FIELD="threshold_percent"; // the only EDITABLE threshold field
function rulesFor(brand,code){return (S.rows||[]).filter(function(r){return r.brand===brand&&r.rule_code===code;});}
function brandDefaultRule(brand,code){var rs=rulesFor(brand,code);for(var i=0;i<rs.length;i++){if(!rs[i].platform||rs[i].platform==="All")return rs[i];}return null;}
function platformRule(brand,code,pf){var rs=rulesFor(brand,code);for(var i=0;i<rs.length;i++){if(rs[i].platform===pf&&!rs[i].shop&&!rs[i].seller_sku&&!rs[i].item)return rs[i];}return null;}
function isActiveRule(r){return !!r&&r.status!=="Paused";}
function upsertRule(brand,code,platform,thrVal,existing){var data={brand:brand,rule_code:code,platform:platform};
data[RULE_SAVE_THR_FIELD]=thrVal;return A.call("api_rules.save_rule",{rule:data,name:existing?existing.name:null});}
// Re-split + re-render from the in-memory rows (no fetch) - used when toggling the
// client-side "editing" state of an inherited platform row.
function rerender(){var defs=[],exc=[];(S.rows||[]).forEach(function(r){var t=tierOf(r);if(t==="Brand"||t==="Platform")defs.push(r);else exc.push(r);});
renderDefaults(defs);renderExceptions(exc);}
// RC4-6/RC5-4: re-FETCH canonical rule data then re-render (used after every write
// so the row reflects backend truth, never optimistic state).
function reloadRules(){return A.call("api_rules.list_rules",{filters:filters()}).then(function(res){S.rows=res.rows;rerender();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
// resolve the (brand, behaviour) a clicked inline control belongs to.
function behCtx(el){var beh=el.closest(".ru-beh");return beh?{brand:beh.getAttribute("data-brand"),code:beh.getAttribute("data-code"),beh:beh}:null;}
function _ekey(ctx,pf){return ctx.brand+"|"+ctx.code+"|"+pf;}
// Save the All-platforms (Brand Default) threshold for this behaviour.
function saveAll(ctx){var inp=ctx.beh.querySelector(".ru-i-all");var v=inp?inp.value:"";if(v===""){A.toast("Nh\u1eadp ng\u01b0\u1ee1ng All platforms tr\u01b0\u1edbc.");return;}
upsertRule(ctx.brand,ctx.code,"All",v,brandDefaultRule(ctx.brand,ctx.code)).then(function(){A.toast("\u0110\u00e3 l\u01b0u.");reloadRules();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
// RC5-4: "Them tuy chinh" on an inherited row -> switch THIS row to override-edit
// (editable input) without touching the backend; "Bo tuy chinh" before a save just
// cancels back to inherited.
function addPf(ctx,pf){S.editing[_ekey(ctx,pf)]=1;rerender();}
// Save a per-platform override: writes via save_rule (backend find-or-updates by
// scope identity, resuming a paused row), then WAITS for success and reloads the
// canonical data so the row renders as an override with the saved value.
function savePf(ctx,pf){var row=ctx.beh.querySelector('.ru-ovrow[data-pf="'+pf+'"]');var inp=row?row.querySelector(".ru-i-pf"):null;var v=inp?inp.value:"";
var existing=platformRule(ctx.brand,ctx.code,pf);
if(v===""){if(isActiveRule(existing)){rmPf(ctx,pf);}else{A.toast("Nh\u1eadp ng\u01b0\u1ee1ng override ho\u1eb7c b\u1ea5m B\u1ecf t\u00f9y ch\u1ec9nh.");}return;}
upsertRule(ctx.brand,ctx.code,pf,v,existing).then(function(){delete S.editing[_ekey(ctx,pf)];A.toast("\u0110\u00e3 l\u01b0u.");reloadRules();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
// Remove customization: if an active override exists, PAUSE it (the resolver then
// ignores it and the All-platforms Brand Default value applies again); if the row
// was only being edited (not yet saved), just cancel back to inherited.
function rmPf(ctx,pf){var orr=platformRule(ctx.brand,ctx.code,pf);delete S.editing[_ekey(ctx,pf)];
if(!isActiveRule(orr)||ruleThrVal(orr)==null){rerender();return;}
A.call("api_rules.set_rule_status",{name:orr.name,status:"Paused"}).then(function(){A.toast("\u0110\u00e3 l\u01b0u.");reloadRules();}).catch(function(e){A.toast("L\u1ed7i: "+e.message);});}
function init(){A.initScope("/alerts/rules",function(scope){S.scope=scope;
A.scopeLine($("al-scope-line"),scope.supervisor?"Supervisor scope: all brands":("Brands: "+Object.keys(scope.brands).join(", ")));
var bsel=$("f-brand");Object.keys(scope.brands||{}).forEach(function(b){var o=document.createElement("option");o.value=b;o.textContent=b;bsel.appendChild(o);});
A.relabelRuleOptions($("f-rule_code"));
try{rulePrecedenceSelfTest();}catch(e){if(window.console)console.error("rule precedence self-test FAILED:",e&&e.message);}
load();applyFieldHelp($("ru-tier-legend"));});
$("ru-apply").onclick=load;
// RC4-6: inline Save / Remove-customization handlers (no drawer).
$("ru-defaults").addEventListener("click",function(ev){
  var sa=ev.target.closest("[data-save-all]");if(sa){var c=behCtx(sa);if(c)saveAll(c);return;}
  var sp=ev.target.closest("[data-save-pf]");if(sp){var c2=behCtx(sp);if(c2)savePf(c2,sp.getAttribute("data-save-pf"));return;}
  var ap=ev.target.closest("[data-add-pf]");if(ap){var c4=behCtx(ap);if(c4)addPf(c4,ap.getAttribute("data-add-pf"));return;}
  var rp=ev.target.closest("[data-rm-pf]");if(rp){var c3=behCtx(rp);if(c3)rmPf(c3,rp.getAttribute("data-rm-pf"));return;}});
// Enter inside an inline threshold input triggers that row's Save.
$("ru-defaults").addEventListener("keydown",function(ev){if(ev.key!=="Enter")return;var t=ev.target;if(!t.classList)return;
  if(t.classList.contains("ru-i-all")){ev.preventDefault();var c=behCtx(t);if(c)saveAll(c);}
  else if(t.classList.contains("ru-i-pf")){ev.preventDefault();var row=t.closest(".ru-ovrow");var c2=behCtx(t);if(c2&&row)savePf(c2,row.getAttribute("data-pf"));}});}
if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",init);}else{init();}
})();
