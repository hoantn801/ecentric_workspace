// Copyright (c) 2026, eCentric and contributors
// Alert Center - trang Integration Health /alerts/integration-health. Asset cua app tu 29/09/2026 (brief NHIEU_LOP/brief_alert_center.md);
// truoc do nam inline trong Web Page duoi dang <script id="ec-alert-health">.
// Trang nap file nay qua /assets/ecentric_workspace/alerts/ec_alert_health.js?v=<sha>. Sua file nay thi chay
//   python -m ecentric_workspace.alerts.site_pages.assets --stamp
// roi bump BASELINE_SHA256 cua trang doi + them patch resync (test bat neu quen).
(function(){
"use strict";
var A=window.AL,$=A.$;
var S={sm:false,rows:[],th:{}};

function yn(v){return v?'<span class="al-st al-st-ready">yes</span>':'<span class="al-st al-st-blocked">no</span>';}
function cred(v){if(v==="Active")return '<span class="al-badge al-b-active">Active</span>';return '<span class="al-badge al-b-warning">'+A.esc(v||"-")+'</span>';}

function init(){
  A.initScope("/alerts/integration-health",function(scope){
    S.sm=!!scope.supervisor;
    A.scopeLine($("ih-scope-line"),S.sm?"System Manager - xem t\u1ea5t c\u1ea3 brand.":"Hi\u1ec3n th\u1ecb c\u00e1c brand trong ph\u1ea1m vi c\u1ee7a b\u1ea1n.");
    load();
  });
  $("ih-refresh").onclick=load;
  $("ih-d-close").onclick=close;
  $("al-overlay").onclick=close;
}

function load(){
  $("ih-rows").innerHTML='<tr><td colspan="17"><div class="al-empty">\u0110ang t\u1ea3i...</div></td></tr>';
  A.call("api_brands.list_brand_readiness").then(render).catch(function(e){A.toast("L\u1ed7i: "+e.message);});
}

// Frontend readiness classification (truthful, from the existing payload):
// a brand with NO integration settings reads "Not Configured" rather than the
// backend's "Blocked" (which is meant for a configured-but-failing brand).
function ihStatus(r){if(!r.bis_exists&&(r.status==="Blocked"||!r.status))return "Not Configured";return r.status;}
function render(d){
  S.rows=d.brands||[]; S.th=d.thresholds||{};
  var c={ready:0,blocked:0,warning:0,manual:0};
  S.rows.forEach(function(r){var s=ihStatus(r);
    if(s==="Not Configured")c.manual++; else if(s==="Blocked")c.blocked++;
    else if(s==="Warning"||s==="Delayed"||s==="Manual Pull Required")c.warning++; else c.ready++;});
  $("ih-c-ready").textContent=c.ready;$("ih-c-blocked").textContent=c.blocked;
  $("ih-c-warning").textContent=c.warning;$("ih-c-manual").textContent=c.manual;
  if(d.capacity){var cap=d.capacity;$("ih-cap-panel").hidden=false;
    var pct=Math.min(100,Math.round(cap.log_plus_item/cap.archive_review_trigger*100));
    $("ih-cap-text").textContent="Log+Item: "+A.money(cap.log_plus_item)+" / "+A.money(cap.archive_review_trigger);
    $("ih-cap-pct").textContent=pct+"%";
    var fill=$("ih-cap-fill");fill.style.width=pct+"%";
    fill.className=cap.archive_review_due?"al-cap-fill warn":"al-cap-fill";
    $("ih-cap-help").textContent=cap.archive_review_due?"\u0110\u00e3 ch\u1ea1m ng\u01b0\u1ee1ng review 2M - l\u00ean k\u1ebf ho\u1ea1ch archive (v\u1eabn ch\u1ec9 \u0111o, ch\u01b0a xo\u00e1).":"Ch\u1ec9 \u0111o l\u01b0\u1eddng; ch\u01b0a c\u00f3 code archive/xo\u00e1.";
  }
  var html=S.rows.map(function(r,i){
    var run=r.running?'<span class="al-run-dot" title="running"></span>':"";
    return '<tr data-i="'+i+'">'+
      '<td><strong>'+A.esc(r.brand)+'</strong></td>'+
      '<td>'+A.stHealth(ihStatus(r))+run+'</td>'+
      '<td>'+A.esc((r.action&&r.action.label)||"-")+'</td>'+
      '<td title="'+A.esc(r.kam_owner||"")+'">'+A.esc(r.kam_owner||"-")+'</td>'+
      '<td>'+A.esc(r.ba_status||"-")+'</td>'+
      '<td>'+yn(r.bis_exists)+'</td>'+
      '<td>'+cred(r.credential_status)+'</td>'+
      '<td>'+yn(A.money(r.enabled)!=="-"&&Number(r.enabled)===1)+'</td>'+
      '<td>'+yn(Number(r.dry_run_stock_lock)===1)+'</td>'+
      '<td>'+A.dt(r.last_sync_at)+'</td>'+
      '<td>'+(r.consecutive_failures||0)+'</td>'+
      '<td>'+yn(r.in_allowlist)+'</td>'+
      '<td>'+A.esc(r.last_run_state||"-")+'</td>'+
      '<td>'+((r.counts&&r.counts.alerts_open)||0)+'</td>'+
      '<td>'+A.money((r.counts&&r.counts.order_log)||0)+'</td>'+
      '<td>'+A.money((r.counts&&r.counts.order_item)||0)+'</td>'+
      '<td>'+(r.counts&&r.counts.policies_active!=null?r.counts.policies_active:0)+'</td>'+
    '</tr>';
  }).join("");
  $("ih-rows").innerHTML=html||'<tr><td colspan="17"><div class="al-empty">Kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u kh\u1edbp b\u1ed9 l\u1ecdc.</div></td></tr>';
  $("ih-rows").querySelectorAll("tr[data-i]").forEach(function(tr){
    tr.onclick=function(){openDrawer(S.rows[+tr.getAttribute("data-i")].brand);};});
}

function openDrawer(brand){
  $("ih-d-title").textContent=brand;
  $("ih-d-body").innerHTML='<div class="al-empty">\u0110ang t\u1ea3i...</div>';
  $("ih-drawer").hidden=false;$("al-overlay").hidden=false;
  A.call("api_brands.brand_readiness",{brand:brand}).then(function(r){renderDrawer(brand,r);})
   .catch(function(e){$("ih-d-body").innerHTML='<div class="al-empty">'+A.esc(e.message)+'</div>';});
}

function blockerList(bl){
  if(!bl||!bl.length)return '<div class="al-help">Kh\u00f4ng c\u00f3 blocker.</div>';
  return '<ul class="al-blk">'+bl.map(function(b){
    return '<li class="'+(b.severity==="blocker"?"blocker":"warning")+'">'+A.esc(b.label)+'</li>';}).join("")+'</ul>';
}

function kv(label,val){return '<dt>'+A.esc(label)+'</dt><dd>'+A.esc(val==null||val===""?"-":val)+'</dd>';}

function renderDrawer(brand,r){
  var bis=r.bis||{}; var cov=r.coverage||{}; var cnt=r.counts||{}; var ba=r.brand_approver||{};
  var run=r.running?'<span class="al-run-dot"></span>':"";
  var parts=[];
  parts.push('<div style="margin-bottom:8px">'+A.stHealth(r.status)+run+'</div>');
  parts.push('<div class="al-action-box">&#8594; '+A.esc((r.action&&r.action.label)||"-")+'</div>');
  parts.push('<div class="al-fsec">Blockers / c\u1ea3nh b\u00e1o</div>'+blockerList(r.blockers));
  parts.push('<div class="al-fsec">Scope (Brand)</div><dl class="al-kv">'+
    kv("Brand",ba.status)+kv("KAM owner",ba.kam_owner)+
    kv("Manager",ba.manager_email)+kv("Leader",ba.leader_email)+'</dl>');
  parts.push('<div class="al-fsec">T\u00edch h\u1ee3p Omisell (BIS - kh\u00f4ng l\u1ed9 key)</div><dl class="al-kv">'+
    kv("BIS",r.bis_exists?"yes":"no")+kv("enabled",bis.enabled)+
    kv("credential_status",bis.credential_status)+kv("dry_run_stock_lock",bis.dry_run_stock_lock)+
    kv("base_url",bis.base_url)+kv("last_sync_at",bis.last_sync_at)+
    kv("consecutive_failures",bis.consecutive_failures)+
    kv("scheduler allowlist",r.in_allowlist?"yes":"no")+kv("last run",r.last_run_state)+'</dl>');
  parts.push('<div class="al-fsec">D\u1eef li\u1ec7u & coverage</div><dl class="al-kv">'+
    kv("Order Log",A.money(cnt.order_log||0))+kv("Order Item",A.money(cnt.order_item||0))+
    kv("Alerts (open)",cnt.alerts_open||0)+kv("Alerts (total)",cnt.alerts_total||0)+
    kv("Active policies",cnt.policies_active||0)+
    kv("Policy coverage",cov.pct==null?"n/a":(cov.pct+"% ("+cov.covered+"/"+cov.distinct_skus+", "+cov.days+"d)"))+'</dl>');
  // links (everyone)
  parts.push('<div class="al-fsec">Li\u00ean k\u1ebft</div><div class="al-drawer-actions" style="border:0;padding:0">'+
    '<a class="al-btn" href="/alerts/policies?brand='+encodeURIComponent(brand)+'">Xem policies</a>'+
    '<a class="al-btn" href="/alerts#al-alert-list">Xem alerts</a>'+
    (S.sm?'<a class="al-btn" href="/app/ec-brand-integration-settings/new?brand='+encodeURIComponent(brand)+'">T\u1ea1o/s\u1eeda BIS</a>':'')+
    '</div>');
  // diagnostic actions (SM only, read-only)
  if(S.sm){
    parts.push('<div class="al-fsec">Ch\u1ea9n \u0111o\u00e1n (read-only, SM)</div><div class="al-drawer-actions" style="border:0;padding:0">'+
      '<button class="al-btn" id="ih-prev"'+((r.bis_exists&&bis.base_url)?"":" disabled")+' title="'+((r.bis_exists&&bis.base_url)?"":"C\u1ea7n base_url trong BIS tr\u01b0\u1edbc khi preview/pull")+'">Ch\u1ea1y preview</button>'+
      '<button class="al-btn" id="ih-pstat">Xem pull_status</button></div>'+
      '<div class="al-help" id="ih-diag-out"></div>');
    // gated (no auto-write) snippets
    parts.push('<div class="al-fsec">H\u00e0nh \u0111\u1ed9ng c\u1ea7n thao t\u00e1c th\u1ee7 c\u00f4ng (gated)</div>'+
      '<div class="al-help">Manual pull ch\u1ea1y qua runbook (kh\u00f4ng trigger t\u1eeb trang n\u00e0y):</div>'+
      '<div class="al-snippet">.\\onboard_lof_pull.ps1 -Brand '+A.esc(brand)+' -Confirm</div>'+
      '<div class="al-help">Th\u00eam v\u00e0o scheduler = s\u1eeda site_config tr\u00ean FC dashboard (gated, G4 s\u1ebd t\u1ef1 \u0111\u1ed9ng):</div>'+
      '<div class="al-snippet">ec_alerts_scheduled_pull_brands: [..., "'+A.esc(brand)+'"]</div>');
  }
  $("ih-d-body").innerHTML=parts.join("");
  if(S.sm){
    var pv=$("ih-prev"); if(pv)pv.onclick=function(){runPreview(brand);};
    var ps=$("ih-pstat"); if(ps)ps.onclick=function(){runStatus(brand);};
  }
}

function runPreview(brand){
  $("ih-diag-out").textContent="\u0110ang ch\u1ea1y...";
  A.call("api_omisell.pull_preview",{brand:brand,hours:1}).then(function(p){
    $("ih-diag-out").textContent="would_list = "+(p.would_list==null?"?":p.would_list)+" ["+(p.window?p.window.join(" -> "):"")+"]";
  }).catch(function(e){$("ih-diag-out").textContent="L\u1ed7i: "+e.message;});
}
function runStatus(brand){
  $("ih-diag-out").textContent="\u0110ang ch\u1ea1y...";
  A.call("api_omisell.pull_status",{brand:brand}).then(function(s){
    var lr=s.last_run||{};
    $("ih-diag-out").textContent="state="+(lr.state||"none")+" running="+(s.running_since?"yes":"no")+
      " breaker="+(s.consecutive_failures||0)+" last_sync="+(s.last_sync_at||"-");
  }).catch(function(e){$("ih-diag-out").textContent="L\u1ed7i: "+e.message;});
}

function close(){$("ih-drawer").hidden=true;$("al-overlay").hidden=true;}

if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",init);}else{init();}
})();
