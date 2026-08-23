// Home "Lich hom nay" widget: replaces the Outlook placeholder panel with today's
// meetings (Graph) + scheduled work blocks (EC PM Time Block) + a "chua xep gio" nudge.
// Data: ecentric_workspace.pm.api.schedule.today ; RSVP: ...schedule.rsvp.
// ES5, string-concat only (no template literals), no Jinja tokens.
(function(){
  'use strict';
  if (window._ecLhnInstalled) return;
  window._ecLhnInstalled = true;

  if (!document.getElementById('ec-lhn-css')) {
    var st = document.createElement('style');
    st.id = 'ec-lhn-css';
    st.textContent = [
      '.ec-lhn { padding:12px 14px 14px; }',
      '.ec-lhn-sub { font-size:12px; color:#6b7280; margin-bottom:12px; }',
      '.ec-lhn-hero { background:#26215C; border-radius:12px; padding:13px 14px; margin-bottom:13px; }',
      '.ec-lhn-hero-k { font-size:11px; color:#CECBF6; margin-bottom:4px; display:flex; align-items:center; gap:5px; letter-spacing:.02em; }',
      '.ec-lhn-hero-t { font-size:15px; font-weight:600; color:#fff; margin-bottom:2px; line-height:1.3; }',
      '.ec-lhn-hero-m { font-size:12px; color:#AFA9EC; margin-bottom:12px; }',
      '.ec-lhn-btns { display:flex; gap:7px; }',
      '.ec-lhn-btn { flex:1; text-align:center; font-size:12px; padding:8px 0; border-radius:8px; cursor:pointer; border:0; font-weight:600; text-decoration:none; display:block; }',
      '.ec-lhn-btn-join { background:#7F77DD; color:#fff; }',
      '.ec-lhn-btn-ghost { background:transparent; border:1px solid #534AB7; color:#CECBF6; font-weight:500; }',
      '.ec-lhn-btn[disabled] { opacity:.55; cursor:default; }',
      '.ec-lhn-legend { display:flex; gap:14px; margin-bottom:8px; }',
      '.ec-lhn-lg { font-size:11px; color:#6b7280; display:flex; align-items:center; gap:5px; }',
      '.ec-lhn-dot { width:8px; height:8px; border-radius:2px; display:inline-block; }',
      '.ec-lhn-row { display:flex; gap:10px; padding:9px 0; border-top:1px solid #f1f0f4; align-items:flex-start; }',
      '.ec-lhn-time { font-size:12px; color:#6b7280; width:82px; flex:none; padding-top:1px; }',
      '.ec-lhn-bar { width:3px; border-radius:2px; flex:none; align-self:stretch; }',
      '.ec-lhn-main { flex:1; min-width:0; }',
      '.ec-lhn-t { font-size:13px; font-weight:600; color:#111827; line-height:1.35; }',
      '.ec-lhn-s { font-size:12px; color:#9ca3af; margin-top:1px; }',
      '.ec-lhn-row.past .ec-lhn-t { color:#9ca3af; font-weight:500; }',
      '.ec-lhn-ic { font-size:16px; color:#7F77DD; flex:none; margin-top:1px; text-decoration:none; }',
      '.ec-lhn-nudge { display:flex; align-items:center; gap:10px; margin-top:12px; padding:10px 12px; background:#FAEEDA; border-radius:8px; cursor:pointer; text-decoration:none; }',
      '.ec-lhn-nudge-t { flex:1; font-size:12px; color:#633806; }',
      '.ec-lhn-nudge-a { font-size:12px; font-weight:600; color:#854F0B; white-space:nowrap; }',
      '.ec-lhn-foot { text-align:center; font-size:12px; color:#9ca3af; padding-top:10px; margin-top:2px; border-top:1px solid #f1f0f4; }',
      '.ec-lhn-empty { padding:22px 8px; text-align:center; color:#9ca3af; font-size:13px; }'
    ].join('\n');
    document.head.appendChild(st);
  }

  function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function pdt(s){ if(!s) return null; var d=new Date(String(s).replace(' ','T')); return isNaN(d.getTime())?null:d; }
  function hhmm(s){ var d=pdt(s); if(!d) return ''; function p(n){return (n<10?'0':'')+n;} return p(d.getHours())+':'+p(d.getMinutes()); }
  function findPanel(){
    var titles=document.querySelectorAll('.panel-title');
    for(var i=0;i<titles.length;i++){
      var t=(titles[i].textContent||'').trim().toLowerCase();
      if(t.indexOf('l\u1ecbch h\u00f4m nay')>=0 || (t.indexOf('l\u1ecbch')>=0 && t.indexOf('h\u00f4m nay')>=0)){
        return titles[i].closest('.panel');
      }
    }
    return null;
  }

  function countdown(start, end, now){
    var s=pdt(start), e=pdt(end), n=pdt(now)||new Date();
    if(!s) return '';
    if(e && n>=s && n<e) return '\u0111ang di\u1ec5n ra';
    var mins=Math.round((s-n)/60000);
    if(mins<0) return '';
    if(mins<60) return 'trong '+mins+' ph\u00fat';
    var h=Math.floor(mins/60), m=mins%60;
    return 'trong '+h+'h'+(m?(' '+m):'');
  }

  function rsvp(evId, resp, btn){
    if(btn){ btn.setAttribute('disabled','1'); }
    fetch('/api/method/ecentric_workspace.pm.api.schedule.rsvp', {
      method:'POST', credentials:'include',
      headers:{ 'Content-Type':'application/json',
                'X-Frappe-CSRF-Token': (window.frappe && frappe.csrf_token) || '' },
      body: JSON.stringify({ event_id: evId, response: resp })
    }).then(function(r){ return r.json(); }).then(function(d){
      var m=(d&&d.message)||{};
      var wrap=btn && btn.closest('.ec-lhn-btns');
      if(m.ok){
        if(wrap){ var lbl = resp==='accept'?'\u0110\u00e3 nh\u1eadn':(resp==='decline'?'\u0110\u00e3 t\u1eeb ch\u1ed1i':'\u0110\u00e3 t\u1ea1m nh\u1eadn');
          wrap.innerHTML='<div style="flex:1;text-align:center;font-size:12px;color:#CECBF6;padding:8px 0;">'+lbl+'</div>'; }
      } else {
        if(btn) btn.removeAttribute('disabled');
        if(wrap){ var e=wrap.querySelector('.ec-lhn-err'); if(!e){ e=document.createElement('div'); e.className='ec-lhn-err'; e.style.cssText='flex:1;text-align:center;font-size:11px;color:#F5C4B3;padding:6px 0;'; wrap.appendChild(e);} e.textContent='Kh\u00f4ng g\u1eedi \u0111\u01b0\u1ee3c ('+(m.code||'l\u1ed7i')+')'; }
      }
    }).catch(function(){ if(btn) btn.removeAttribute('disabled'); });
  }
  window._ecLhnRsvp = rsvp;

  function render(panel, d){
    var body = panel.querySelector('.ec-lhn');
    if(!body){ var hdr=panel.querySelector('.panel-header'); body=document.createElement('div'); body.className='ec-lhn';
      if(hdr && hdr.nextSibling){ panel.insertBefore(body, hdr.nextSibling); } else { panel.appendChild(body); } }
    // Remove the old "Se tich hop Outlook sau" placeholder (and any stale non-header,
    // non-widget children) so only the header + our widget body remain.
    var kids = panel.children;
    for(var ci=kids.length-1; ci>=0; ci--){ var k=kids[ci];
      if(k!==body && !(k.className && String(k.className).indexOf('panel-header')>=0)){ k.parentNode.removeChild(k); } }
    var act = panel.querySelector('.panel-action'); if(act){ act.href='/pm#schedule'; }

    var now = d.now;
    var items = [];
    (d.meetings||[]).forEach(function(m){ items.push({ kind:'m', start:m.start, end:m.end, subject:m.subject, id:m.id, join:m.join_url, loc:m.location, resp:m.response }); });
    (d.blocks||[]).forEach(function(b){ items.push({ kind:'b', start:b.start, end:b.end, subject:b.subject, loc:b.project, state:b.state }); });
    items.sort(function(a,b){ return (pdt(a.start)||0) - (pdt(b.start)||0); });

    var nd = pdt(now)||new Date();
    var hero=null, upcoming=[], past=[];
    items.forEach(function(it){ var e=pdt(it.end); var future = !e || e>nd;
      if(future && !hero){ hero=it; } else if(future){ upcoming.push(it); } else { past.push(it); } });

    var h = '';
    var nMeet=(d.meetings||[]).length, nBlock=(d.blocks||[]).length;
    h += '<div class="ec-lhn-sub">'+nMeet+' h\u1ecdp \u00b7 '+nBlock+' vi\u1ec7c \u0111\u00e3 x\u1ebfp gi\u1edd</div>';

    if(!items.length){
      h += '<div class="ec-lhn-empty">H\u00f4m nay ch\u01b0a c\u00f3 h\u1ecdp hay vi\u1ec7c \u0111\u00e3 x\u1ebfp gi\u1edd.</div>';
    }

    if(hero){
      var cd = countdown(hero.start, hero.end, now);
      if(hero.kind==='m'){
        h += '<div class="ec-lhn-hero">'+
          '<div class="ec-lhn-hero-k"><i class="ti ti-video"></i>H\u1eccP S\u1eaeP T\u1edaI'+(cd?(' \u00b7 '+cd):'')+'</div>'+
          '<div class="ec-lhn-hero-t">'+esc(hero.subject)+'</div>'+
          '<div class="ec-lhn-hero-m">'+hhmm(hero.start)+'\u2013'+hhmm(hero.end)+(hero.loc?(' \u00b7 '+esc(hero.loc)):(hero.join?' \u00b7 Microsoft Teams':''))+'</div>';
        if(hero.resp==='accepted' || hero.resp==='organizer'){
          h += '<div class="ec-lhn-btns"><div style="flex:1;text-align:center;font-size:12px;color:#CECBF6;padding:8px 0;">'+(hero.resp==='organizer'?'B\u1ea1n l\u00e0 ch\u1ee7 tr\u00ec':'\u0110\u00e3 nh\u1eadn')+'</div>'+
            (hero.join?('<a class="ec-lhn-btn ec-lhn-btn-join" style="flex:none;padding:8px 14px;" href="'+esc(hero.join)+'" target="_blank" rel="noopener">Tham gia</a>'):'')+'</div>';
        } else {
          h += '<div class="ec-lhn-btns">';
          if(hero.join){ h += '<a class="ec-lhn-btn ec-lhn-btn-join" href="'+esc(hero.join)+'" target="_blank" rel="noopener">Tham gia</a>'; }
          if(hero.id){
            h += '<button class="ec-lhn-btn ec-lhn-btn-ghost" onclick="_ecLhnRsvp(\''+esc(hero.id).replace(/'/g,"\\'")+'\',\'accept\',this)">Nh\u1eadn</button>'+
                 '<button class="ec-lhn-btn ec-lhn-btn-ghost" onclick="_ecLhnRsvp(\''+esc(hero.id).replace(/'/g,"\\'")+'\',\'decline\',this)">T\u1eeb ch\u1ed1i</button>';
          }
          h += '</div>';
        }
        h += '</div>';
      } else {
        h += '<div class="ec-lhn-hero">'+
          '<div class="ec-lhn-hero-k"><i class="ti ti-clock-play"></i>VI\u1ec6C S\u1eaeP T\u1edaI'+(cd?(' \u00b7 '+cd):'')+'</div>'+
          '<div class="ec-lhn-hero-t">'+esc(hero.subject)+'</div>'+
          '<div class="ec-lhn-hero-m">'+hhmm(hero.start)+'\u2013'+hhmm(hero.end)+(hero.loc?(' \u00b7 '+esc(hero.loc)):'')+'</div>'+
          '<div class="ec-lhn-btns"><a class="ec-lhn-btn ec-lhn-btn-join" href="/pm#schedule">M\u1edf l\u1ecbch l\u00e0m vi\u1ec7c</a></div>'+
        '</div>';
      }
    }

    if(nBlock>0 && (upcoming.length || hero)){
      h += '<div class="ec-lhn-legend">'+
        '<span class="ec-lhn-lg"><span class="ec-lhn-dot" style="background:#7F77DD"></span>H\u1ecdp</span>'+
        '<span class="ec-lhn-lg"><span class="ec-lhn-dot" style="background:#1D9E75"></span>Vi\u1ec7c \u0111\u00e3 x\u1ebfp gi\u1edd</span></div>';
    }

    upcoming.forEach(function(it){
      var isM = it.kind==='m';
      var bar = isM ? '#7F77DD' : '#1D9E75';
      var ico = isM ? (it.join?('<a class="ec-lhn-ic" href="'+esc(it.join)+'" target="_blank" rel="noopener" title="Tham gia"><i class="ti ti-video"></i></a>'):'')
                    : '<i class="ti ti-clock-play ec-lhn-ic" style="color:#1D9E75"></i>';
      var sub = isM ? (it.loc?esc(it.loc):'') : (it.state==='\u0110\u00e3 x\u00e1c nh\u1eadn'?'\u0111\u00e3 x\u00e1c nh\u1eadn':'vi\u1ec7c \u0111\u00e3 x\u1ebfp');
      h += '<div class="ec-lhn-row">'+
        '<div class="ec-lhn-time">'+hhmm(it.start)+'\u2013'+hhmm(it.end)+'</div>'+
        '<div class="ec-lhn-bar" style="background:'+bar+'"></div>'+
        '<div class="ec-lhn-main"><div class="ec-lhn-t">'+esc(it.subject)+'</div>'+(sub?('<div class="ec-lhn-s">'+sub+'</div>'):'')+'</div>'+
        ico+'</div>';
    });

    if(d.due_unscheduled>0){
      h += '<a class="ec-lhn-nudge" href="/pm#schedule">'+
        '<i class="ti ti-alarm" style="font-size:18px;color:#854F0B;"></i>'+
        '<div class="ec-lhn-nudge-t"><b style="font-weight:600;">'+d.due_unscheduled+' vi\u1ec7c \u0111\u1ebfn h\u1ea1n</b> h\u00f4m nay ch\u01b0a x\u1ebfp gi\u1edd</div>'+
        '<span class="ec-lhn-nudge-a">X\u1ebfp l\u1ecbch \u2192</span></a>';
    }

    if(past.length){
      h += '<div class="ec-lhn-foot">'+past.length+' m\u1ee5c \u0111\u00e3 qua</div>';
    }

    body.innerHTML = h;
  }

  function load(){
    var panel=findPanel(); if(!panel) return;
    fetch('/api/method/ecentric_workspace.pm.api.schedule.today', {
      method:'POST', credentials:'include',
      headers:{ 'Content-Type':'application/json',
                'X-Frappe-CSRF-Token': (window.frappe && frappe.csrf_token) || '' },
      body: JSON.stringify({})
    }).then(function(r){ return r.json(); })
      .then(function(d){ var m=(d&&d.message)||null; if(m) render(panel, m); })
      .catch(function(e){ console.warn('[ec-lhn] load err', e); });
  }

  function init(){
    var tries=0;
    var iv=setInterval(function(){
      var panel=findPanel();
      if(panel){ clearInterval(iv); load(); }
      if(++tries>30) clearInterval(iv);
    }, 200);
  }
  if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded', init); } else { init(); }
  console.log('[ec-lich-hom-nay] installed');
})();
