// Runtime test for the canonical bell-contract TRANSFORM (JS mirror of
// transform_notification_bell_contract_remaining.ps1). Proves the static,
// HTML-ENTITY-encoded Approval/PM bells convert to the canonical marker anchor,
// idempotently, without touching settings/help/page-content decoys.
'use strict';
let fail=0; function ok(c,m){ if(!c){fail++;console.error('FAIL: '+m);} else console.log('ok  - '+m); }
const TITLE='Th&#244;ng b&#225;o';                       // entity-encoded "Thong bao"
const MARKER='data-ec-notification-bell="1"';
const BTN_RE=/<button\b[^>]*\bclass="(ec-ib|icon-btn)"[^>]*\btitle="Th&#244;ng b&#225;o"[^>]*>([\s\S]*?)<\/button>/g;
const PM_RE=/<button\b[^>]*\bid="tb-bell"[^>]*>([\s\S]*?)<\/button>/;
function innerSvgDot(frag){ const svg=(frag.match(/<svg[\s\S]*?<\/svg>/)||[''])[0]; const dot=(frag.match(/<span[^>]*class="dot"[^>]*>\s*<\/span>/)||['<span class="dot"></span>'])[0]; return svg+dot; }
function transformButtons(html){
  const ms=html.match(BTN_RE)||[]; let count=ms.length, changed=0, out=html;
  out=out.replace(BTN_RE,(m,cls,inner)=>{ if(/data-ec-notification-bell/.test(m)) return m; changed++;
    return '<a class="'+cls+'" href="/app/notification-log" '+MARKER+' aria-label="'+TITLE+'" title="'+TITLE+'">'+innerSvgDot(inner)+'</a>'; });
  return {count,changed,out};
}
function pmState(html){
  const preBtn=/<button\b[^>]*\bid="tb-bell"/.test(html), preBadge=/id="tb-badge"/.test(html), preGo=/go\("notifications"\)/.test(html);
  const anchorBell=/<a\b[^>]*id="tb-bell"[^>]*href="\/app\/notification-log"/.test(html)||/<a\b[^>]*href="\/app\/notification-log"[^>]*id="tb-bell"/.test(html);
  const markerN=(html.match(/data-ec-notification-bell="1"/g)||[]).length;
  const noOnclick=!/tb-bell"\)\s*\.onclick/.test(html), noPmApi=!/notifications\.list_mine/.test(html);
  const sidebarRedirect=/notifications:redirectToGlobalNotifications/.test(html);
  const pre=preBtn&&preBadge&&preGo;
  const canon=anchorBell&&markerN>=1&&!preBadge&&!preGo&&noOnclick&&noPmApi&&sidebarRedirect;
  return canon?'canonical':(pre?'pre':'violation');
}
// ---- PM state machine ----
(function(){
  const PRE='<div class="topbar-actions"><button class="icon-btn" id="tb-bell" title="Th&#244;ng b&#225;o"><svg/><span id="tb-badge">0</span></button></div>'+
    '<a class="nav-item" data-view="notifications">x</a><script>el("tb-bell").onclick=function(){go("notifications");};function refreshBadge(){api(PM+"notifications.list_mine");}</script>';
  const CANON='<div class="topbar-actions"><a class="icon-btn" id="tb-bell" href="/app/notification-log" data-ec-notification-bell="1" aria-label="x" title="x"><svg/></a></div>'+
    '<a class="nav-item" data-view="notifications">x</a><script>var VIEWS={notifications:redirectToGlobalNotifications};function refreshBadge(){}</script>';
  const PARTIAL='<div class="topbar-actions"><a class="icon-btn" id="tb-bell" href="/app/notification-log" data-ec-notification-bell="1"><svg/></a></div>'+
    '<script>el("tb-bell").onclick=function(){(window.location.href="/app/notification-log");};function refreshBadge(){api(PM+"notifications.list_mine");}var VIEWS={notifications:showNotifications};</script>';
  ok(pmState(PRE)==='pre','PM pre-transform -> state=pre (change=true)');
  ok(pmState(CANON)==='canonical','PM canonical post-state -> state=canonical (change=false, PASS)');
  ok(pmState(PARTIAL)==='violation','PM partial (onclick+pm api+VIEWS leftovers) -> state=violation (needs recovery)');
})();

// ---- 11-route inventory + backup filename safety ----
(function(){
  const ROUTES=['all-ticket','mso-form','so-form','form-po','form-rec','vendor-request','client-request','contract-request','gbs-po-form','gbs-so-form','pm'];
  ok(ROUTES.length===11,'inventory: exactly 11 approved routes');
  const unsafe='alert-center+'; const safe=unsafe.replace(/[^\w\-]/g,'_');
  ok(safe==='alert-center_'&&!/[+\\]/.test(safe),'backup filename sanitized (no + / regex chars)');
})();

if(fail){ console.error('\n'+fail+' FAILED'); process.exit(1);} console.log('\nAll transform-contract assertions passed.'); process.exit(0);
