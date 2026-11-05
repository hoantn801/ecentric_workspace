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

  // RSVP state. Graph `responseStatus.response` values: none | notResponded | organizer |
  // accepted | tentativelyAccepted | declined. Every answered value must render as answered:
  // treating only 'accepted' as answered put the Nhan / Tu choi buttons back on a meeting
  // you had already marked tentative ("bam lai no khong luu").
  var RSVP_STATUS={ accept:'accepted', decline:'declined', tentative:'tentativelyAccepted' };
  function respLabel(r, isOrg){
    if(isOrg || r==='organizer') return 'B\u1ea1n l\u00e0 ch\u1ee7 tr\u00ec';
    if(r==='accepted') return '\u0110\u00e3 nh\u1eadn';
    if(r==='declined') return '\u0110\u00e3 t\u1eeb ch\u1ed1i';
    if(r==='tentativelyAccepted') return '\u0110\u00e3 t\u1ea1m nh\u1eadn';
    return '';
  }
  // Remember an answer in the data every surface renders from (_last), then repaint them.
  // Without this the hero card / timeline popover kept the pre-answer copy: re-focusing the
  // event or reopening the popover showed the buttons again as if nothing had been saved.
  function applyRsvp(evId, status){
    if(!_last) return;
    (_last.meetings||[]).forEach(function(mt){ if(mt && mt.id===evId) mt.response=status; });
    var panel=findPanel();
    if(panel) render(panel, _last);
    // Home v2 owns the timeline (window.ecTimelineOwnsEvents): its chips carry no RSVP
    // state, and re-firing 'ec-cal-today' would rebuild them under the open popover (its
    // anchor chip detached -> popover jumps). Only our own strip needs repainting.
    if(!window.ecTimelineOwnsEvents) renderTimeline(_last);
  }
  function rsvpFail(btn, code){
    if(btn) btn.removeAttribute('disabled');
    var wrap=btn && btn.closest('.ec-lhn-btns'); if(!wrap) return;
    var e=wrap.querySelector('.ec-lhn-err'); if(!e){ e=document.createElement('div'); e.className='ec-lhn-err'; e.style.cssText='flex:1;text-align:center;font-size:11px;color:#B42318;padding:6px 0;'; wrap.appendChild(e);}
    e.textContent='Kh\u00f4ng g\u1eedi \u0111\u01b0\u1ee3c ('+(code||'l\u1ed7i')+')';
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
      if(!m.ok){ rsvpFail(btn, m.code); return; }
      var status=m.status || RSVP_STATUS[resp] || 'accepted';
      // The popover (white card) is not repainted by render(): show the answer in place,
      // in a colour readable on white (the old #CECBF6 label was near-invisible there).
      var wrap=btn && btn.closest('.ec-lhn-btns');
      if(wrap && wrap.closest('#ec-lhn-pop')){
        wrap.innerHTML='<span style="flex:1;text-align:center;font-size:12px;color:#0F6E56;padding:7px 0;">'+respLabel(status)+'</span>';
      }
      applyRsvp(evId, status);
    }).catch(function(){ rsvpFail(btn, 'm\u1ea1ng'); });
  }
  window._ecLhnRsvp = rsvp;

  // ---------------------------------------------------------------------------
  // Public API for the home page (owned by the layout script). It calls these
  // instead of reaching into this widget's DOM:
  //   window.ecCalToday(cb)      -> today's data {meetings, blocks, due_unscheduled, ...}
  //   window.ecCalFocus(key)     -> promote one event into the hero card + scroll to it.
  //        key: event id | {id} | {title/subject} | {start} | plain title string.
  //        returns true when an event matched, false otherwise (caller can fall back).
  //   window.ecCalEvents()       -> the normalised event list currently displayed.
  // Events also carry data-ev-id / data-ev-key on their rows so the host can address them.
  // ---------------------------------------------------------------------------
  var _last=null, _focus=null;

  function evKey(it){ return it.id || ((it.kind||'')+'|'+(it.start||'')+'|'+(it.subject||'')); }

  function buildItems(d){
    var items=[];
    (d.meetings||[]).forEach(function(m){ items.push({ kind:'m', start:m.start, end:m.end, subject:m.subject, id:m.id, join:m.join_url, loc:m.location, resp:m.response, org:!!m.is_organizer, cancelled:!!m.is_cancelled }); });
    (d.blocks||[]).forEach(function(b){ items.push({ kind:'b', start:b.start, end:b.end, subject:b.subject, loc:b.project, state:b.state, id:b.name }); });
    items.sort(function(a,b){ return (pdt(a.start)||0) - (pdt(b.start)||0); });
    return items;
  }

  function matchItem(it, key){
    if(key===null||key===undefined||key==='') return false;
    if(typeof key==='string'){
      return it.id===key || evKey(it)===key ||
             String(it.subject||'').toLowerCase()===key.toLowerCase();
    }
    if(key.id && it.id) return it.id===key.id;
    var t=key.title||key.subject;
    if(t && String(it.subject||'').toLowerCase()!==String(t).toLowerCase()) return false;
    if(key.start && String(it.start||'').slice(0,16)!==String(key.start).replace('T',' ').slice(0,16)) return false;
    return !!(t||key.start);
  }

  window.ecCalEvents=function(){ return _last? buildItems(_last).map(function(it){
    return { key:evKey(it), id:it.id||'', kind:it.kind, subject:it.subject,
             start:it.start, end:it.end, location:it.loc||'', join_url:it.join||'',
             response:it.resp||'' }; }) : []; };

  window.ecCalToday=function(cb){
    if(_last && typeof cb==='function'){ cb(_last); return; }
    return fetchToday().then(function(m){ if(typeof cb==='function') cb(m); return m; });
  };

  window.ecCalFocus=function(key){
    _focus=key||null;
    var panel=findPanel();
    var hit=false, list=_last?buildItems(_last):[];
    for(var i=0;i<list.length;i++){ if(matchItem(list[i], _focus)){ hit=true; break; } }
    if(panel && _last) render(panel, _last);
    if(panel && hit){
      try{ panel.scrollIntoView({behavior:'smooth', block:'center'}); }catch(e){ panel.scrollIntoView(); }
      var hero=panel.querySelector('.ec-lhn-hero');
      if(hero){ hero.style.transition='box-shadow .25s';
        hero.style.boxShadow='0 0 0 3px rgba(127,119,221,.55)';
        setTimeout(function(){ hero.style.boxShadow=''; }, 1400); }
    }
    if(!hit) _focus=null;
    return hit;
  };

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
    var items = buildItems(d);

    var nd = pdt(now)||new Date();
    // Which event goes in the hero card? By default the next one still ahead; when the
    // host page asks for a specific event (window.ecCalFocus) that one is promoted, so
    // clicking an event elsewhere on the page lands on the right meeting.
    var hero=null, upcoming=[], past=[], i;
    if(_focus){
      for(i=0;i<items.length;i++){ if(matchItem(items[i], _focus)){ hero=items[i]; break; } }
    }
    items.forEach(function(it){
      if(it===hero) return;
      var e=pdt(it.end); var future = !e || e>nd;
      if(future && !hero){ hero=it; } else if(future){ upcoming.push(it); } else { past.push(it); } });
    if(_focus && hero && upcoming.indexOf(hero)<0){
      // a focused past event must not also be listed below as "da qua"
      var pi=past.indexOf(hero); if(pi>=0) past.splice(pi,1);
    }

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
        var hLbl = hero.cancelled ? '\u0110\u00e3 hu\u1ef7' : respLabel(hero.resp, hero.org);
        if(hLbl){
          h += '<div class="ec-lhn-btns"><div style="flex:1;text-align:center;font-size:12px;color:#CECBF6;padding:8px 0;">'+hLbl+'</div>'+
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
      var attrs = ' data-ev-key="'+esc(evKey(it))+'"'+(it.id?(' data-ev-id="'+esc(it.id)+'"'):'');
      var bar = isM ? '#7F77DD' : '#1D9E75';
      var ico = isM ? (it.join?('<a class="ec-lhn-ic" href="'+esc(it.join)+'" target="_blank" rel="noopener" title="Tham gia"><i class="ti ti-video"></i></a>'):'')
                    : '<i class="ti ti-clock-play ec-lhn-ic" style="color:#1D9E75"></i>';
      var sub = isM ? (it.loc?esc(it.loc):'') : (it.state==='\u0110\u00e3 x\u00e1c nh\u1eadn'?'\u0111\u00e3 x\u00e1c nh\u1eadn':'vi\u1ec7c \u0111\u00e3 x\u1ebfp');
      h += '<div class="ec-lhn-row"'+attrs+'>'+
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

  // ---- "Dong thoi gian hom nay" strip (.ec2-tlwrap, owned by the home layout script) ----
  // That widget renders an empty axis; we supply the events. Axis spans 08:00 -> 18:00,
  // so left% = (minutes - 480) / 600 * 100, clamped. Meetings ride the top lane, scheduled
  // work the bottom one. Rendering is idempotent: our own nodes are removed first, and the
  // host widget's markup is never modified beyond hiding its empty-state label.
  var TL_START=480, TL_END=1080;
  function tlWrap(){ return document.querySelector('.ec2-tlwrap'); }
  function mins(s){ var d=pdt(s); return d? (d.getHours()*60+d.getMinutes()) : null; }
  function pct(m){ var p=(m-TL_START)/(TL_END-TL_START)*100; return Math.max(0, Math.min(100, p)); }

  function renderTimeline(d){
    var wrap=tlWrap(); if(!wrap) return;
    var body=wrap.querySelector('.ec2-tlbody') || wrap;
    var old=body.querySelectorAll('.ec-lhn-ev'), oi;
    for(oi=0; oi<old.length; oi++){ old[oi].parentNode.removeChild(old[oi]); }
    var items=[];
    (d.meetings||[]).forEach(function(m){ items.push({kind:'m',start:m.start,end:m.end,subject:m.subject,id:m.id,join:m.join_url,loc:m.location,resp:m.response,org:!!m.is_organizer,cancelled:!!m.is_cancelled}); });
    (d.blocks||[]).forEach(function(b){ items.push({kind:'b',start:b.start,end:b.end,subject:b.subject,loc:b.project}); });
    var empty=wrap.querySelector('.ec2-tlempty');
    if(empty){ empty.style.display = items.length ? 'none' : ''; }
    if(!items.length) return;

    // Keep only what falls inside the visible window, then pack overlapping events into
    // lanes (greedy): two meetings at the same hour must not sit on top of each other --
    // with a fixed meeting/work lane the later one hid the earlier one completely.
    var vis=[];
    items.forEach(function(it){
      var s=mins(it.start), e=mins(it.end);
      if(s===null||e===null) return;
      if(e<=TL_START || s>=TL_END) return;
      it._s=s; it._e=e; vis.push(it);
    });
    if(!vis.length) return;
    vis.sort(function(a,b){ return a._s-b._s || a._e-b._e; });
    var laneEnd=[];
    vis.forEach(function(it){
      var li=-1, i;
      for(i=0;i<laneEnd.length;i++){ if(laneEnd[i]<=it._s){ li=i; break; } }
      if(li<0){ laneEnd.push(it._e); li=laneEnd.length-1; } else { laneEnd[li]=it._e; }
      it._lane=li;
    });
    var n=Math.max(1, laneEnd.length), GAP=4, PAD=4;
    var laneH=Math.max(15, Math.floor((64-2*PAD-(n-1)*GAP)/n));

    vis.forEach(function(it){
      var l=pct(it._s), w=Math.max(1.2, pct(it._e)-l);
      var isM=it.kind==='m';
      var el=document.createElement('div');
      el.className='ec-lhn-ev '+(isM?'ec-lhn-ev-m':'ec-lhn-ev-b');
      el.style.cssText='position:absolute;left:'+l+'%;width:'+w+'%;'+
        'top:'+(PAD+it._lane*(laneH+GAP))+'px;height:'+laneH+'px;'+
        'border-radius:5px;padding:0 7px;line-height:'+laneH+'px;'+
        'overflow:hidden;white-space:nowrap;text-overflow:ellipsis;cursor:pointer;'+
        'font-size:'+(laneH<20?11:12)+'px;font-weight:600;box-sizing:border-box;'+
        (isM?'background:#EEEDFE;color:#3C3489;border-left:3px solid #7F77DD;'
            :'background:#E1F5EE;color:#0F6E56;border-left:3px solid #1D9E75;');
      el.textContent=it.subject||(isM?'Họp':'Việc');
      el.title=(it.subject||'')+' · '+hhmm(it.start)+'–'+hhmm(it.end)+(it.loc?(' · '+it.loc):'');
      el.onclick=function(ev){ ev.stopPropagation(); openPop(wrap, el, it); };
      body.appendChild(el);
    });
  }

  // Click an event -> small popover keeping the RSVP actions available now that the
  // separate "Lich hom nay" panel is going away.
  function closePop(){ var p=document.getElementById('ec-lhn-pop'); if(p&&p.parentNode) p.parentNode.removeChild(p); }
  document.addEventListener('click', closePop);
  function openPop(wrap, anchor, it){
    closePop();
    var pop=document.createElement('div');
    pop.id='ec-lhn-pop';
    var lf=anchor.offsetLeft, tp=anchor.offsetTop+30;
    pop.style.cssText='position:absolute;z-index:50;left:'+lf+'px;top:'+tp+'px;min-width:220px;max-width:300px;'+
      'background:#fff;border:1px solid #e5e7eb;border-radius:10px;box-shadow:0 8px 24px rgba(16,24,40,.12);padding:11px 12px;';
    var h='<div style="font-size:13px;font-weight:600;color:#111827;line-height:1.35;margin-bottom:3px;">'+esc(it.subject||'')+'</div>'+
      '<div style="font-size:12px;color:#6b7280;margin-bottom:'+(it.kind==='m'?'10px':'0')+';">'+hhmm(it.start)+'–'+hhmm(it.end)+(it.loc?(' · '+esc(it.loc)):'')+'</div>';
    if(it.kind==='m'){
      h+='<div class="ec-lhn-btns" style="display:flex;gap:6px;">';
      if(it.join){ h+='<a class="ec-lhn-btn ec-lhn-btn-join" style="flex:1;text-align:center;font-size:12px;padding:7px 0;border-radius:7px;background:#7F77DD;color:#fff;font-weight:600;text-decoration:none;" href="'+esc(it.join)+'" target="_blank" rel="noopener">Tham gia</a>'; }
      var pLbl = it.cancelled ? 'Đã huỷ' : respLabel(it.resp, it.org);
      if(it.id && !pLbl){
        h+='<button class="ec-lhn-btn" style="flex:1;font-size:12px;padding:7px 0;border-radius:7px;border:1px solid #d1d5db;background:#fff;color:#374151;cursor:pointer;" onclick="_ecLhnRsvp(\''+esc(it.id).replace(/'/g,"\\'")+'\',\'accept\',this)">Nhận</button>'+
           '<button class="ec-lhn-btn" style="flex:1;font-size:12px;padding:7px 0;border-radius:7px;border:1px solid #d1d5db;background:#fff;color:#374151;cursor:pointer;" onclick="_ecLhnRsvp(\''+esc(it.id).replace(/'/g,"\\'")+'\',\'decline\',this)">Từ chối</button>';
      } else if(pLbl){ h+='<span style="flex:1;text-align:center;font-size:12px;color:'+((it.org||it.resp==='organizer'||it.cancelled)?'#6b7280':'#0F6E56')+';padding:7px 0;">'+pLbl+'</span>'; }
      h+='</div>';
    }
    pop.innerHTML=h;
    pop.onclick=function(e){ e.stopPropagation(); };
    wrap.appendChild(pop);
  }

  function fetchToday(){
    return fetch('/api/method/ecentric_workspace.pm.api.schedule.today', {
      method:'POST', credentials:'include',
      headers:{ 'Content-Type':'application/json',
                'X-Frappe-CSRF-Token': (window.frappe && frappe.csrf_token) || '' },
      body: JSON.stringify({})
    }).then(function(r){ return r.json(); })
      .then(function(d){ var m=(d&&d.message)||null; if(m) _last=m; return m; });
  }

  function load(){
    var panel=findPanel(), wrap=tlWrap();
    if(!panel && !wrap) return;                    // neither surface on this page
    fetchToday().then(function(m){ if(!m) return;
        if(panel) render(panel, m);
        // The timeline strip belongs to the home layout script. If it renders its own
        // events (window.ecTimelineOwnsEvents), stay out of its DOM entirely; otherwise
        // keep painting it so the strip isn't empty.
        if(!window.ecTimelineOwnsEvents) renderTimeline(m);
        try{ document.dispatchEvent(new CustomEvent('ec-cal-today', {detail:m})); }catch(e){}
      })
      .catch(function(e){ console.warn('[ec-lhn] load err', e); });
  }

  // ---- Card "Phong hop" (05/11/2026): CHI xem trong / ban luc nay, dat phong o /pm#rooms. ----
  // Khung (header + 5 dong xuong) nam san trong main_section.html ([data-ec-rooms]); o day chi DIEN
  // noi dung vao [data-ec-rooms-list] + badge, khong dung lai bo cuc. Du lieu: pm.api.rooms.day()
  // (cache 60 s phia server, dung chung voi trang Phong hop). Gio la chuoi gio dia phuong cua site:
  // tinh bang phut, "bay gio" = now cua server + thoi gian da troi o client.
  var RM_H0=480, RM_H1=1140, RM_REFRESH=60000, _rmBusy=false;
  function rmPad(n){ return (n<10?'0':'')+n; }
  function rmHm(m){ return m>=1440 ? '24:00' : rmPad(Math.floor(m/60))+':'+rmPad(m%60); }
  function rmMin(s){ var x=/(\d{2}):(\d{2})/.exec(String(s||'').slice(11)); return x ? (+x[1])*60+(+x[2]) : null; }
  function rmSpan(b, day){
    var s0=String(b.start||''), e0=String(b.end||''); if(s0.length<16||e0.length<16) return null;
    var ds=s0.slice(0,10), de=e0.slice(0,10); if(ds>day||de<day) return null;
    var s=ds<day?0:rmMin(s0), e=de>day?1440:rmMin(e0);
    if(b.all_day){ s=0; e=1440; }
    return (s===null||e===null||e<=s) ? null : {s:s, e:e};
  }
  function rmPct(m){ return (Math.max(RM_H0, Math.min(RM_H1, m))-RM_H0)/(RM_H1-RM_H0)*100; }
  // busy (gop cac lich lien nhau) | soon (trong, <=30 phut nua co nguoi) | free | off
  function rmState(list, n){
    var cur=null, i;
    for(i=0;i<list.length;i++){ if(list[i].s<=n && n<list[i].e){ cur=list[i]; break; } }
    if(cur){ var end=cur.e; list.forEach(function(x){ if(x.s<=end && x.e>end) end=x.e; }); return {k:'busy', until:end}; }
    var next=null; for(i=0;i<list.length;i++){ if(list[i].s>n){ next=list[i]; break; } }
    if(next && next.s-n<=30) return {k:'soon', until:next.s};
    return {k:'free', until: next ? next.s : null};
  }
  function rmText(st){
    if(st.k==='off') return 'Chưa kết nối';
    if(st.k==='busy') return st.until>=1440 ? 'Bận cả ngày' : 'Bận đến '+rmHm(st.until);
    return st.until!==null ? 'Trống đến '+rmHm(st.until) : 'Trống cả ngày';
  }
  function rmNote(card, text){
    var ul=card.querySelector('[data-ec-rooms-list]'), bd=card.querySelector('[data-ec-rooms-badge]');
    if(bd) bd.textContent='';
    if(ul){ ul.setAttribute('aria-busy','false'); ul.innerHTML='<li class="ec2-rm-note">'+esc(text)+'</li>'; }
  }
  function rmPaint(card, d){
    var ul=card.querySelector('[data-ec-rooms-list]'), bd=card.querySelector('[data-ec-rooms-badge]');
    if(!ul) return;
    var rooms=(d && d.rooms) || [];
    var live=rooms.filter(function(r){ return !r.error; });
    if(!d || !d.sync_on || !rooms.length || !live.length){ rmNote(card, 'Chưa kết nối lịch phòng'); return; }
    var day=String(d.now||'').slice(0,10) || d.date;
    var n=rmMin(d.now); if(n===null) n=0;
    n+=Math.floor((Date.now()-(d._at||Date.now()))/60000);
    var free=0, h='';
    rooms.forEach(function(r){
      var list=[];
      (r.bookings||[]).forEach(function(b){ var sp=rmSpan(b, day); if(sp) list.push(sp); });
      list.sort(function(a,b){ return a.s-b.s || a.e-b.e; });
      var st=r.error ? {k:'off'} : rmState(list, n);
      if(!r.error && st.k!=='busy') free++;
      var bars=list.filter(function(x){ return x.e>RM_H0 && x.s<RM_H1; }).map(function(x){
        return '<i'+(x.s<=n && n<x.e ? ' class="ec2-rm-cur"' : '')+' style="left:'+rmPct(x.s)+'%;width:'+(rmPct(x.e)-rmPct(x.s))+'%"></i>'; }).join('');
      var pin=(n>=RM_H0 && n<=RM_H1) ? '<b style="left:'+rmPct(n)+'%"></b>' : '';
      var name=r.title || r.label || r.code || r.name, txt=rmText(st);
      h+='<li><a class="ec2-rm-row" href="/pm#rooms" title="'+esc((r.label||name)+': '+txt)+'" aria-label="'+esc((r.label||name)+': '+txt)+'">'+
         '<span class="ec2-rm-code">'+esc(r.code||'')+'</span><span class="ec2-rm-name">'+esc(name)+'</span>'+
         '<span class="ec2-rm-st ec2-rm-st--'+st.k+'">'+txt+'</span>'+
         '<span class="ec2-rm-bar" aria-hidden="true">'+bars+pin+'</span></a></li>';
    });
    ul.setAttribute('aria-busy','false');
    ul.innerHTML=h;
    if(bd) bd.textContent=free+'/'+rooms.length+' trống';
  }
  function rmLoad(){
    var card=document.querySelector('[data-ec-rooms]');
    if(!card || _rmBusy) return;
    _rmBusy=true;
    fetch('/api/method/ecentric_workspace.pm.api.rooms.day', {
      method:'POST', credentials:'include',
      headers:{ 'Content-Type':'application/json',
                'X-Frappe-CSRF-Token': (window.frappe && frappe.csrf_token) || '' },
      body: JSON.stringify({})
    }).then(function(r){ return r.json().then(function(j){ return {ok:r.ok, status:r.status, j:j}; }, function(){ return {ok:false, status:r.status, j:{}}; }); })
      .then(function(x){
        _rmBusy=false;
        var m=x.j && x.j.message;
        if(!x.ok || !m){ rmNote(card, x.status===403 ? 'Chưa có quyền xem lịch phòng' : 'Chưa kết nối lịch phòng'); return; }
        m._at=Date.now(); card._ecRooms=m; rmPaint(card, m);
      })
      .catch(function(){ _rmBusy=false; rmNote(card, 'Chưa kết nối lịch phòng'); });
  }
  function rmInit(){
    if(!document.querySelector('[data-ec-rooms]')) return;
    rmLoad();
    setInterval(function(){ if(!document.hidden) rmLoad(); }, RM_REFRESH);
  }
  window._ecRoomsCard = { load: rmLoad, paint: rmPaint };

  function init(){
    var tries=0;
    var iv=setInterval(function(){
      if(findPanel() || tlWrap()){ clearInterval(iv); load(); }
      if(++tries>40) clearInterval(iv);
    }, 200);
  }
  if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded', function(){ init(); rmInit(); }); } else { init(); rmInit(); }
  console.log('[ec-lich-hom-nay] installed');
})();
