// Runtime proof for the Notification Center two-note CHIME (reused-AudioContext lifecycle).
// Executes the REAL asset with a controllable AudioContext that records every scheduled note
// (frequency / start / stop) and gain ramp, so we can assert: two oscillator starts per chime,
// note order ~660 then ~880 Hz, peak gain <= 0.07, total span 300-450 ms, suspended->resume
// before scheduling, closed->recreate, muted->silent, one event->one chime, reconnect->no
// duplicate, and AudioContext failure never blocks the toast.
//   node ecentric_workspace/notification_center/tests/sound_recovery_check.js
'use strict';
const fs=require('fs'); const path=require('path');
const SRC=fs.readFileSync(path.join(__dirname,'..','..','public','js','notification_center.js'),'utf8');
let failures=0; function ok(c,m){ if(!c){failures++;console.error('FAIL: '+m);} else {console.log('ok  - '+m);} }

// ---- selector engine (subset) ----
function parseCompound(s){ const c={tag:null,id:null,classes:[],attrs:[]}; s=s.trim();
  const re=/([#.][\w-]+)|(\[[^\]]+\])|([\w*]+)/g; let m;
  while((m=re.exec(s))){ const t=m[0];
    if(t[0]==='#')c.id=t.slice(1); else if(t[0]==='.')c.classes.push(t.slice(1));
    else if(t[0]==='['){ const mm=/\[([\w-]+)([*^$]?=)"([^"]*)"\]/.exec(t); if(mm)c.attrs.push({n:mm[1],op:mm[2],v:mm[3]}); }
    else if(t!=='*')c.tag=t.toLowerCase(); }
  return c; }
function matchCompound(el,c){ if(!el||el.nodeType==='doc')return false;
  if(c.tag&&(el.tagName||'').toLowerCase()!==c.tag)return false;
  if(c.id&&el.id!==c.id)return false;
  for(const cl of c.classes){ if(!el.classList.contains(cl))return false; }
  for(const a of c.attrs){ const v=el.getAttribute?el.getAttribute(a.n):null; if(v==null)return false;
    if(a.op==='*='){ if(String(v).indexOf(a.v)<0)return false; } else if(String(v)!==a.v)return false; }
  return true; }
function matchSelector(el,sel){ return sel.split(',').some(b=>{ const parts=b.trim().split(/\s+/).map(parseCompound);
  if(!matchCompound(el,parts[parts.length-1]))return false; let i=parts.length-2,n=el.parentNode;
  while(i>=0){ let f=false; while(n){ if(matchCompound(n,parts[i])){f=true;n=n.parentNode;break;} n=n.parentNode; } if(!f)return false; i--; } return true; }); }
function mkCL(){ const set=new Set(); return { add:(...c)=>c.forEach(x=>x&&set.add(x)), remove:(...c)=>c.forEach(x=>set.delete(x)),
  toggle:(c,on)=>{const v=on===undefined?!set.has(c):!!on; v?set.add(c):set.delete(c); return v;}, contains:c=>set.has(c) }; }
class El{ constructor(tag){ this.tagName=(tag||'div').toUpperCase(); this.children=[]; this.parentNode=null; this.attrs={};
    this.style={}; this.classList=mkCL(); this._tc=''; this.id=''; this._l=[]; this.onclick=null; }
  set className(v){ this._cn=v; String(v||'').split(/\s+/).filter(Boolean).forEach(c=>this.classList.add(c)); }
  get className(){ return this._cn||''; }
  setAttribute(k,v){ this.attrs[k]=String(v); if(k==='id')this.id=String(v); }
  getAttribute(k){ return this.attrs[k]===undefined?null:this.attrs[k]; }
  removeAttribute(k){ delete this.attrs[k]; }
  set textContent(v){ this._tc=String(v); this.children=[]; }
  get textContent(){ if(this.children.length)return this.children.map(c=>c.textContent).join(''); return this._tc; }
  set innerHTML(v){ this._html=v; this.children=[]; const re=/id="([^"]+)"/g; let m; while((m=re.exec(v))){ const e=new El('div'); e.setAttribute('id',m[1]); this.appendChild(e);} }
  get innerHTML(){ return this._html||''; }
  get firstChild(){ return this.children[0]||null; }
  appendChild(c){ c.parentNode=this; this.children.push(c); return c; }
  removeChild(c){ const i=this.children.indexOf(c); if(i>=0)this.children.splice(i,1); c.parentNode=null; return c; }
  contains(n){ if(n===this)return true; return this.children.some(c=>c.contains&&c.contains(n)); }
  closest(sel){ let n=this; while(n&&n.nodeType!=='doc'){ if(matchSelector(n,sel))return n; n=n.parentNode; } return null; }
  addEventListener(t,fn){ this._l.push({t,fn}); }
  focus(){} getBoundingClientRect(){ return {bottom:40,right:200,top:10,left:180}; }
  querySelector(s){ return this._find(s,false); }
  querySelectorAll(s){ return this._find(s,true); }
  _find(s,all){ const acc=[]; const walk=n=>n.children.forEach(c=>{ if(matchSelector(c,s))acc.push(c); walk(c);}); walk(this); return all?acc:(acc[0]||null); } }
function stripHtml(str){ let s=String(str).replace(/<[^>]*>/g,'');
  return s.replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,'&'); }

function makeEnv(opts){ opts=opts||{};
  const head=new El('head'); const body=new El('body'); head.nodeType=body.nodeType='el';
  const byId={}; const reg=c=>{ if(c.id)byId[c.id]=c; };
  const _h=head.appendChild.bind(head); head.appendChild=c=>{reg(c);return _h(c);};
  const _b=body.appendChild.bind(body); body.appendChild=c=>{reg(c);return _b(c);};
  const bell=new El('button'); bell.setAttribute('data-ec-notification-bell','1'); body.appendChild(bell);
  const document={ nodeType:'doc', readyState:'complete', head, body, hidden:!!opts.hidden,
    createElement:t=>new El(t), getElementById:id=>byId[id]||null,
    addEventListener:()=>{}, querySelector:s=>body._find(s,false), querySelectorAll:s=>body._find(s,true) };
  body.parentNode=document; head.parentNode=document;
  function MutationObserver(){} MutationObserver.prototype.observe=function(){}; MutationObserver.prototype.disconnect=function(){};
  function DOMParser(){} DOMParser.prototype.parseFromString=function(str){ const b=new El('body'); b._tc=stripHtml(str); return {body:b}; };

  // ---- recording AudioContext: notes (freq/start/stop) + gain ramp peaks ----
  const notes=[]; const gainPeaks=[]; const ctxs=[]; let willThrow=!!opts.audioThrow;
  function AudioContext(){
    if(willThrow){ throw new Error('AudioContext not allowed (error)'); }
    const c={ currentTime:0, destination:{}, state:(opts.startState||'running'), resumeCalls:0,
      createOscillator(){ const o={ type:'', frequency:{value:0}, connect(){},
        start(t){ notes.push({freq:o.frequency.value, start:t, stop:null, _o:o}); },
        stop(t){ for(let i=notes.length-1;i>=0;i--){ if(notes[i]._o===o){ notes[i].stop=t; break; } } } };
        return o; },
      createGain(){ return { gain:{ setValueAtTime(){}, exponentialRampToValueAtTime(v){ gainPeaks.push(v); },
        linearRampToValueAtTime(v){ gainPeaks.push(v); } }, connect(){} }; },
      resume(){ this.resumeCalls++; this.state='running'; return { then:(o)=>{ if(o)o(); return {then(){},catch(){}};}, catch(){} }; } };
    ctxs.push(c); return c;
  }
  const desktops=[];
  function Notif(title,o){ this.title=title; this.opts=o||{}; this.onclick=null; this.close=()=>{}; desktops.push(this); }
  Notif.permission=opts.permission||'default'; Notif.requestPermission=function(cb){ if(cb) cb(Notif.permission); };

  const _sockH={};
  const socket={ connected:true, io:{on:()=>{},emit:()=>{}},
    on:(e,f)=>{(_sockH[e]=_sockH[e]||[]).push(f);}, off:()=>{}, connect(){ this.connected=true; (_sockH['connect']||[]).forEach(f=>f()); },
    emit:(e,...a)=>{(_sockH[e]||[]).forEach(f=>f(...a));}, listeners:e=>(_sockH[e]||[]).slice() };
  const realtime={ socket, connect:()=>{}, on:(e,f)=>socket.on(e,f) };
  const env={};
  env._prefs={ sound_enabled:1, desktop_enabled:0, teams_enabled:0, quiet_hours_enabled:0,
               quiet_hours_start:null, quiet_hours_end:null, minimum_severity:'info', enabled_event_types:'', _exists:false };
  env._unread=0;
  const frappe={ realtime, call:o=>{ const m=o.method||''; const cb=o.callback;
    if(m.indexOf('get_preferences')>=0){ cb&&cb({message:{success:true,preferences:env._prefs}}); }
    else if(m.indexOf('get_unread_count')>=0){ cb&&cb({message:{success:true,unread:env._unread}}); }
    else if(m.indexOf('get_notifications')>=0){ cb&&cb({message:{success:true,unread:env._unread,items:[]}}); }
    else { cb&&cb({message:{success:true}}); } } };
  const winListeners=[];
  const win={ location:{pathname:'/home',href:''}, getComputedStyle:()=>({position:'relative'}),
    addEventListener:(t,fn)=>winListeners.push({t,fn}),
    localStorage:{_s:(opts.muted?{ec_notif_muted:'1'}:{}),getItem(k){return k in this._s?this._s[k]:null;},setItem(k,v){this._s[k]=String(v);}},
    requestAnimationFrame:fn=>{ fn(); return 1; },
    frappe, MutationObserver, DOMParser, AudioContext, Notification:Notif };
  win.window=win;
  Object.assign(env,{ document, win, socket, desktops, ctxs,
    noteStarts:()=>notes.length,
    notes:()=>notes,
    chimes:()=>notes.filter(n=>n.freq>600&&n.freq<720).length,   // count ~660 Hz lead notes
    gainMax:()=>gainPeaks.length?Math.max.apply(null,gainPeaks):0,
    spanMs:()=>{ if(!notes.length) return 0; const st=Math.min.apply(null,notes.map(n=>n.start));
                 const en=Math.max.apply(null,notes.map(n=>n.stop!=null?n.stop:n.start)); return (en-st)*1000; },
    ctxCount:()=>ctxs.length,
    unlock:()=>{ winListeners.filter(l=>l.t==='click').forEach(l=>l.fn({})); },
    fireRealtime:p=>{ socket.listeners('ec_notification').forEach(fn=>fn(p)); },
    reconnectCycle:()=>{ socket.connected=false; socket.emit('disconnect','transport close');
      socket.io.emit('reconnect_attempt'); socket.io.emit('reconnect'); socket.connected=true; socket.emit('connect'); },
    toastCount:()=>{ const r=document.getElementById('ec-nc-toasts'); return r?r.children.filter(c=>c.classList.contains('on')).length:0; } });
  return env;
}
function run(env){ new Function('window','document','console',SRC)(env.win,env.document,console); }

let ev;
// 1) two oscillator starts per complete chime  +  7) one event -> one toast + one chime
ev=makeEnv({startState:'running'}); run(ev); ev.unlock();
ev.fireRealtime({event_id:'C1',title:'t',severity:'info'});
ok(ev.noteStarts()===2,'1: one event -> exactly two oscillator starts (two-note chime)');
ok(ev.chimes()===1,'8: one event -> exactly one chime');
ok(ev.toastCount()===1,'7: one event -> one toast alongside the chime');

// 2) note order ~660 Hz then ~880 Hz
const ns=ev.notes().slice().sort((a,b)=>a.start-b.start);
ok(ns[0]&&ns[0].freq>=600&&ns[0].freq<=720,'2: first note ~660 Hz ('+(ns[0]&&ns[0].freq)+')');
ok(ns[1]&&ns[1].freq>=800&&ns[1].freq<=960,'2: second note ~880 Hz ('+(ns[1]&&ns[1].freq)+')');
ok(ns[0].start<ns[1].start,'2: first note is scheduled before the second');

// 3) peak gain <= 0.07
ok(ev.gainMax()>0 && ev.gainMax()<=0.07,'3: peak gain <= 0.07 (is '+ev.gainMax()+')');

// 4) total chime duration between 300 and 450 ms
ok(ev.spanMs()>=300 && ev.spanMs()<=450,'4: total chime duration 300-450 ms (is '+ev.spanMs()+'ms)');

// 5) suspended context resumes before scheduling notes
ev=makeEnv({startState:'suspended'}); run(ev); ev.unlock();
ev.fireRealtime({event_id:'C5',title:'t',severity:'info'});
ok(ev.ctxs[0]&&ev.ctxs[0].resumeCalls===1,'5: suspended -> resume() called');
ok(ev.noteStarts()===2,'5: suspended -> chime scheduled (2 notes) after resume');

// 6) closed context is recreated
ev=makeEnv({startState:'running'}); run(ev); ev.unlock();
ev.fireRealtime({event_id:'C6a',title:'t',severity:'info'});
ev.ctxs[0].state='closed';
ev.fireRealtime({event_id:'C6b',title:'t',severity:'info'});
ok(ev.ctxCount()===2,'6: closed context -> a new context is created');
ok(ev.chimes()===2,'6: closed context -> recreate then chime again (2 chimes)');

// 7b) muted -> schedules no notes (and toast still shows)
ev=makeEnv({startState:'running',muted:true}); run(ev); ev.unlock();
ev.fireRealtime({event_id:'C7',title:'t',severity:'info'});
ok(ev.noteStarts()===0,'7(muted): muted event schedules no notes');
ok(ev.toastCount()===1,'7(muted): toast still shows when muted');

// 9) reconnect does not duplicate the chime
ev=makeEnv({startState:'running'}); run(ev); ev.unlock();
ev.fireRealtime({event_id:'R1',title:'t',severity:'info'});       // chime 1
for(let i=0;i<4;i++) ev.reconnectCycle();
ev.fireRealtime({event_id:'R1',title:'t',severity:'info'});       // same id -> dedupe, no chime
ok(ev.chimes()===1,'9: reconnect + same event id -> no duplicate chime');
ev.fireRealtime({event_id:'R2',title:'t',severity:'info'});       // new event -> chime 2
ok(ev.chimes()===2,'9: a new event after reconnect still chimes once');

// 10) sound failure (AudioContext throws) does not block the toast
ev=makeEnv({audioThrow:true}); run(ev); ev.unlock();
ev.fireRealtime({event_id:'C10',title:'t',severity:'info'});
ok(ev.noteStarts()===0,'10: AudioContext error -> no notes');
ok(ev.toastCount()===1,'10: AudioContext error does NOT block the toast');

console.log(failures? ('\nFAILURES: '+failures) : '\nALL PASS');
process.exit(failures?1:0);
