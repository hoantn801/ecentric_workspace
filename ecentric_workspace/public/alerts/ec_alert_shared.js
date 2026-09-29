// Copyright (c) 2026, eCentric and contributors
// Alert Center - thu vien dung chung window.AL (goi API, format, badge, scope). Asset cua app tu 29/09/2026 (brief NHIEU_LOP/brief_alert_center.md);
// truoc do nam inline trong Web Page duoi dang <script id="ec-alert-shared">.
// Trang nap file nay qua /assets/ecentric_workspace/alerts/ec_alert_shared.js?v=<sha>. Sua file nay thi chay
//   python -m ecentric_workspace.alerts.site_pages.assets --stamp
// roi bump BASELINE_SHA256 cua trang doi + them patch resync (test bat neu quen).
window.AL=(function(){
"use strict";
var METHOD_PREFIX="ecentric_workspace.alerts.";
// 29/09/2026 (NHIEU_LOP): moi loi goi di qua window.ecApi.post (public/js/ec_api.js, nap cho
// moi trang web qua hooks web_include_js). ecApi xin CSRF TUOI tu /api/method/get_csrf va thu
// lai DUNG mot lan khi gap CSRFTokenError -- nen trang KHONG con can khoi
// <script id="ec-csrf-fetch-patch"> boc window.fetch nua. Van POST JSON nhu truoc, nen phia
// server nhan dung kieu du lieu (dict/list/so) nhu cu.
function friendlyError(e){var j=(e&&e.body)||{};var msg=(e&&e.message)||"Error";
try{if(j._server_messages){var arr=JSON.parse(j._server_messages);msg=arr.map(function(s){return JSON.parse(s).message;}).join("; ");}else if(j.exception){msg=String(j.exception).split(":").pop();}}catch(_e){}
if(e&&e.csrf)msg="Phi\u00ean \u0111\u0103ng nh\u1eadp \u0111\u00e3 \u0111\u1ed5i - b\u1ea5m Ctrl+Shift+R \u0111\u1ec3 t\u1ea3i l\u1ea1i trang.";
var err=new Error(msg);err.status=e&&e.status;err.body=j;return err;}
function call(m,args){if(!window.ecApi)return Promise.reject(new Error("ecApi ch\u01b0a n\u1ea1p - b\u1ea5m Ctrl+Shift+R \u0111\u1ec3 t\u1ea3i l\u1ea1i trang."));
return window.ecApi.post(METHOD_PREFIX+m,args||{}).catch(function(e){throw friendlyError(e);});}
// Dong pham vi (#al-scope-line / #ih-scope-line): CSS giu san 1 dong cao 24px (khong nhay khi
// chu ve). Chu dai qua thi cat "..." - day du nam trong title.
function scopeLine(el,text){if(!el)return;el.textContent=text;el.title=text;}
function $(id){return document.getElementById(id);}
function esc(s){var d=document.createElement("div");d.textContent=(s==null?"":String(s));return d.innerHTML;}
var fmtN=new Intl.NumberFormat("vi-VN");
function money(v){return (v==null||v==="")?"-":fmtN.format(Math.round(v));}
function dt(v){if(!v)return "-";return String(v).slice(5,16);}
function toast(m){var t=$("al-toast");t.textContent=m;t.hidden=false;setTimeout(function(){t.hidden=true;},2800);}
function badge(v,map,fb){if(!v)return "-";return '<span class="al-badge '+(map[v]||fb||"al-b-info")+'">'+esc(v)+'</span>';}
function sevBadge(v){return badge(v,{Critical:"al-b-critical",Warning:"al-b-warning",Info:"al-b-info"});}
function stBadge(v){return badge(v,{"Open":"al-b-open","In Review":"al-b-review","Resolved":"al-b-resolved","Ignored":"al-b-ignored"});}
function actBadge(v){return badge(v,{"Dry Run":"al-b-dryrun","Pending":"al-b-pending","Skipped":"al-b-skipped","Success":"al-b-resolved","Failed":"al-b-critical","Cancelled":"al-b-ignored","Processing":"al-b-pending"});}
function polBadge(v){return badge(v,{"Draft":"al-b-draft","Active":"al-b-active","Paused":"al-b-paused","Expired":"al-b-expired","Inactive":"al-b-ignored"});}
function fillUser(route){fetch("/api/method/frappe.auth.get_logged_user",{credentials:"include"}).then(function(r){return r.json();}).then(function(j){var u=j.message||"";if(u==="Guest"){window.location.href="/login?redirect-to="+route;return;}var card=$("al-user-card");if(card){var nm=card.querySelector(".user-name"),av=card.querySelector(".avatar");if(nm)nm.textContent=u.split("@")[0];if(av)av.textContent=(u[0]||"?").toUpperCase();}}).catch(function(){});}
function noAccess(){document.querySelector(".content").innerHTML='<div class="al-noaccess"><h2>Alert Center</h2><p>T\u00e0i kho\u1ea3n c\u1ee7a b\u1ea1n ch\u01b0a \u0111\u01b0\u1ee3c g\u00e1n brand n\u00e0o trong Brand. Li\u00ean h\u1ec7 System Manager.</p></div>';}
function initScope(route,cb){fillUser(route);loadFieldHelp();call("api_alerts.my_scope").then(function(scope){cb(scope);}).catch(function(e){if(e.status===403){noAccess();}else{toast("L\u1ed7i: "+e.message);}});}
function dateStr(d){function p(n){return (n<10?"0":"")+n;}return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
function stHealth(s){var m={"Ready":"al-st-ready","Blocked":"al-st-blocked","Warning":"al-st-warning","Delayed":"al-st-warning","Running":"al-st-running","Scheduler Enabled":"al-st-sched","Manual Pull Required":"al-st-manual","Not Configured":"al-st-manual"};return '<span class="al-st '+(m[s]||"al-st-warning")+'">'+esc(s)+'</span>';}
function daysAgo(n){var d=new Date();d.setDate(d.getDate()-n);return dateStr(d);}
function fillBrandSelect(sel,scope,opts){opts=opts||{};if(!sel)return;sel.innerHTML="";
  if(opts.allOption){var a=document.createElement("option");a.value="";a.textContent=opts.allOption;sel.appendChild(a);}
  var brands=Object.keys((scope&&scope.brands)||{});
  if(opts.extra&&brands.indexOf(opts.extra)<0)brands.push(opts.extra);
  brands.forEach(function(b){var o=document.createElement("option");o.value=b;o.textContent=b;sel.appendChild(o);});
  if(!brands.length&&!opts.allOption){var d=document.createElement("option");d.value="";d.textContent=opts.emptyText||"Kh\u00f4ng c\u00f3 brand trong scope";d.disabled=true;sel.appendChild(d);}
  if(opts.value)sel.value=opts.value;}
var RULE_LABELS={"below_min":"Th\u1ea5p h\u01a1n gi\u00e1 t\u1ed1i thi\u1ec3u","above_high":"Cao h\u01a1n ng\u01b0\u1ee1ng c\u1ea3nh b\u00e1o","severe_price_drop":"Gi\u1ea3m gi\u00e1 nghi\u00eam tr\u1ecdng","possible_missing_zero":"Nghi thi\u1ebfu s\u1ed1 0","missing_brand_mapping":"Thi\u1ebfu c\u1ea5u h\u00ecnh brand","missing_policy":"Thi\u1ebfu Price Policy","ingestion_api_failed":"L\u1ed7i \u0111\u1ed3ng b\u1ed9 d\u1eef li\u1ec7u","missing_integration_credential":"Thi\u1ebfu th\u00f4ng tin k\u1ebft n\u1ed1i","stock_lock_api_failed":"L\u1ed7i x\u1eed l\u00fd Stock Safety"};
// EC Field Description adapter: ONE cached, defensive read of the custom DocType
// (DB-only; not in app source). Records keyed "alert.rule.<code>" with a label /
// description OVERRIDE the built-in fallback labels; if the DocType, fields, or
// permission are unavailable the read fails silently and the fallback is used.
var FIELD_HELP={};
function fieldHelp(key){return FIELD_HELP[key]||null;}
function loadFieldHelp(){return fetch("/api/method/frappe.client.get_list?doctype=EC%20Field%20Description&fields=[%22name%22,%22label%22,%22description%22]&limit_page_length=0",{credentials:"include",headers:{Accept:"application/json"}}).then(function(r){return r.ok?r.json():null;}).then(function(j){var rows=(j&&j.message)||[];rows.forEach(function(x){if(x&&x.name)FIELD_HELP[x.name]={label:x.label||"",help:x.description||""};});}).catch(function(){});}
function ruleLabel(c){var h=FIELD_HELP["alert.rule."+c];return (h&&h.label)||RULE_LABELS[c]||c||"-";}
function ruleCell(c){if(!c)return "-";var l=ruleLabel(c);if(l===c)return esc(c);return '<span title="'+esc(c)+'">'+esc(l)+'</span>';}
// Relabel a <select> of raw rule_code options to business labels in place. The
// option VALUE stays the raw code (backend filter unchanged); only the visible
// text becomes the business label, with the raw code kept in a title tooltip.
// E1 FIX: an <option> with no value attribute returns its TEXT as .value, so
// relabelling the text used to make the select submit the localized label as the
// rule_code ("Rule Code cannot be ..."). Pin the raw code onto o.value FIRST so
// the canonical code is always what gets sent, then change only the display text.
function relabelRuleOptions(sel){if(!sel)return;Array.prototype.forEach.call(sel.options,function(o){var raw=o.value;if(!raw)return;o.value=raw;var l=ruleLabel(raw);if(l&&l!==raw){o.textContent=l;o.title=raw;}});}
return {call:call,scopeLine:scopeLine,$:$,esc:esc,money:money,dt:dt,toast:toast,sevBadge:sevBadge,stBadge:stBadge,actBadge:actBadge,polBadge:polBadge,initScope:initScope,daysAgo:daysAgo,dateStr:dateStr,fillBrandSelect:fillBrandSelect,stHealth:stHealth,ruleLabel:ruleLabel,ruleCell:ruleCell,relabelRuleOptions:relabelRuleOptions,fieldHelp:fieldHelp,loadFieldHelp:loadFieldHelp};
})();
