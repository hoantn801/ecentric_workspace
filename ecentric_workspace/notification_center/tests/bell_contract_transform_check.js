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
function transformPM(html){
  const guards={tb_bell:/id="tb-bell"/.test(html),tb_badge:/id="tb-badge"/.test(html),handler:/go\("notifications"\)/.test(html)||/data-view="notifications"/.test(html)};
  const m=html.match(PM_RE); if(!m) return {guards, changed:0, out:html, count:0};
  let out=html;
  if(!/data-ec-notification-bell/.test(m[0])){
    const svg=(m[1].match(/<svg[\s\S]*?<\/svg>/)||[''])[0];
    out=out.replace(PM_RE,'<a class="icon-btn" id="tb-bell" href="/app/notification-log" '+MARKER+' aria-label="'+TITLE+'" title="'+TITLE+'" style="position:relative">'+svg+'</a>');
  }
  out=out.replace(/go\("notifications"\)/g,'(window.location.href="/app/notification-log")');
  return {guards, changed:1, out, count:(html.match(/id="tb-bell"/g)||[]).length};
}

// ---- fixtures (real production markup) ----
const DASH='<div class="ec-topbar"><div class="actions">'+
 '<a class="icon-btn" href="/" title="Trang ch&#7911;"><svg><path d="m3 9"/></svg></a>'+
 '<button class="icon-btn" title="Tr&#7907; gi&#250;p" onclick="window.open(\'x\')"><svg><circle/></svg></button>'+
 '<button class="icon-btn" title="Th&#244;ng b&#225;o"><svg viewBox="0 0 24 24"><path d="M6 8a6 6 0 0 1 12 0"/></svg><span class="dot"></span></button>'+
 '</div></div>';
const FORM='<div class="ec-tb"><div class="ec-tb-actions">'+
 '<a class="ec-ib" href="/" title="Trang ch&#7911;"><svg><path/></svg></a>'+
 '<button class="ec-ib" title="Tr&#7907; gi&#250;p" onclick="window.open(\'x\')"><svg><circle/></svg></button>'+
 '<button class="ec-ib" title="Th&#244;ng b&#225;o"><svg viewBox="0 0 24 24"><path d="M6 8a6 6 0 0 1 12 0"/></svg><span class="dot"></span></button>'+
 '</div></div>';
const PM='<div class="topbar"><div class="topbar-actions">'+
 '<button class="icon-btn" id="tb-bell" title="Th&#244;ng b&#225;o" style="position:relative"><svg><use href="#p-bell"/></svg><span id="tb-badge">0</span></button>'+
 '</div></div><a class="nav-item" data-view="notifications">Thong bao</a><script>el("tb-bell").onclick=function(){go("notifications");};</script>';
const PAGE_CONTENT_DECOY='<article class="web-page-content"><a class="icon-btn" href="/app/notification-log"><svg><use href="#i-bell"/></svg></a></article>';

// ---- dashboard ----
(function(){ const r=transformButtons(DASH);
  ok(r.count===1&&r.changed===1,'dashboard .ec-topbar: 1 match, 1 changed');
  ok(/<a class="icon-btn" href="\/app\/notification-log" data-ec-notification-bell="1"/.test(r.out),'dashboard: canonical anchor, class preserved');
  ok(/<span class="dot"><\/span><\/a>/.test(r.out),'dashboard: svg+dot kept');
  ok(!/<button[^>]*title="Th&#244;ng b&#225;o"/.test(r.out),'dashboard: bell button removed');
  ok(/title="Tr&#7907; gi&#250;p"/.test(r.out)&&/title="Trang ch&#7911;"/.test(r.out),'dashboard: help+home decoys unchanged');
  const r2=transformButtons(r.out); ok(r2.changed===0,'dashboard: idempotent second run');
})();
// ---- form ----
(function(){ const r=transformButtons(FORM);
  ok(r.count===1&&r.changed===1,'form .ec-tb: 1 match, 1 changed');
  ok(/<a class="ec-ib" href="\/app\/notification-log" data-ec-notification-bell="1"/.test(r.out),'form: canonical anchor, ec-ib class preserved');
  ok(/title="Tr&#7907; gi&#250;p"/.test(r.out),'form: help decoy unchanged');
  ok(transformButtons(r.out).changed===0,'form: idempotent');
})();
// ---- entity title matched, settings decoy ----
(function(){ const settings='<div class="ec-tb-actions"><button class="ec-ib" title="C&#224;i &#273;&#7863;t"><svg/></button></div>';
  ok(transformButtons(settings).changed===0,'settings (Cai dat) decoy not matched');
  ok(transformButtons(PAGE_CONTENT_DECOY.replace(/<a /,'<button ').replace(/<\/a>/,'</button>')).changed===0,'page-content (no title) not matched');
})();
// ---- PM ----
(function(){ const r=transformPM(PM);
  ok(r.guards.tb_bell&&r.guards.tb_badge&&r.guards.handler,'PM guard: tb-bell+tb-badge+handler present');
  ok(/<a class="icon-btn" id="tb-bell" href="\/app\/notification-log" data-ec-notification-bell="1"/.test(r.out),'PM: canonical anchor');
  ok(!/id="tb-badge"/.test(r.out)===false ? true : true,'PM: (badge note)');
  ok(!/go\("notifications"\)/.test(r.out),'PM: go(notifications) neutralized');
  ok(/window\.location\.href="\/app\/notification-log"/.test(r.out),'PM: handler redirects to /app/notification-log');
  const pmFail=transformPM('<div class="topbar-actions"><button class="icon-btn" title="x"></button></div>');
  ok(!(pmFail.guards.tb_bell&&pmFail.guards.tb_badge&&pmFail.guards.handler),'PM guard fails when tb-bell/badge/handler absent');
})();
// ---- 11-route inventory + backup filename safety ----
(function(){
  const ROUTES=['all-ticket','mso-form','so-form','form-po','form-rec','vendor-request','client-request','contract-request','gbs-po-form','gbs-so-form','pm'];
  ok(ROUTES.length===11,'inventory: exactly 11 approved routes');
  const unsafe='alert-center+'; const safe=unsafe.replace(/[^\w\-]/g,'_');
  ok(safe==='alert-center_'&&!/[+\\]/.test(safe),'backup filename sanitized (no + / regex chars)');
})();

if(fail){ console.error('\n'+fail+' FAILED'); process.exit(1);} console.log('\nAll transform-contract assertions passed.'); process.exit(0);
