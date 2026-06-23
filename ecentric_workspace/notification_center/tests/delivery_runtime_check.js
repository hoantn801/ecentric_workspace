// Runtime proof for Notification Delivery v1 frontend (toast/sound/desktop/prefs/dedupe).
// Executes the REAL asset against a mini-DOM with frappe.realtime, Web Notification API,
// AudioContext, requestAnimationFrame and timers. Fires realtime 'ec_notification' events
// and asserts toast/sound/desktop behaviour + per-event dedupe + preference gating.
//   node ecentric_workspace/notification_center/tests/delivery_runtime_check.js
'use strict';
const fs=require('fs'); const path=require('path');
const SRC=fs.readFileSync(path.join(__dirname,'..','..','public','js','notification_center.js'),'utf8');
let failures=0; function ok(c,m){ if(!c){failures++;console.error('FAIL: '+m);} else {console.log('ok  - '+m);} }

// ---- selector engine ----
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
    this.style={}; this.classList=mkCL(); this._tc=''; this.id=''; this._l=[]; this.onclick=null; this._inlineHandler=null; }
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


function makeEnv(opts){
  opts=opts||{};
  const head=new El('head'); const body=new El('body'); head.nodeType=body.nodeType='el';
  const byId={}; const reg=c=>{ if(c.id)byId[c.id]=c; };
  const _h=head.appendChild.bind(head); head.appendChild=c=>{reg(c);return _h(c);};
  const _b=body.appendChild.bind(body); body.appendChild=c=>{reg(c);return _b(c);};
  const docCaps=[],docPd=[],docKd=[];
  const document={ nodeType:'doc', readyState:'complete', head, body, hidden:!!opts.hidden,
    createElement:t=>new El(t), getElementById:id=>byId[id]||null,
    addEventListener:(t,fn,cap)=>{ if(t==='click'&&cap)docCaps.push(fn); else if(t==='pointerdown'&&cap)docPd.push(fn); else if(t==='keydown')docKd.push(fn); },
    querySelector:s=>body._find(s,false), querySelectorAll:s=>body._find(s,true) };
  body.parentNode=document; head.parentNode=document;
  const observers=[];
  function MutationObserver(cb){ this.cb=cb; observers.push(this); }
  MutationObserver.prototype.observe=function(){ this.active=true; };
  MutationObserver.prototype.disconnect=function(){ this.active=false; };
  function DOMParser(){} DOMParser.prototype.parseFromString=function(str){ const b=new El('body'); b._tc=stripHtml(str); return {body:b}; };

  let soundCount=0;
  function Osc(){ var o={type:'',frequency:{value:0},connect(){},start(){ if(o.frequency.value>600&&o.frequency.value<720) soundCount++; },stop(){}}; return o; }
  function Gain(){ return {gain:{setValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){}}; }
  function AudioContext(){ this.currentTime=0; this.destination={};
    this.createOscillator=Osc; this.createGain=Gain; }

  const desktops=[];
  function Notif(title,o){ this.title=title; this.opts=o||{}; this.onclick=null; this.close=()=>{}; desktops.push(this); }
  Notif.permission=opts.permission||'default';
  Notif.requestPermission=function(cb){ if(cb) cb(Notif.permission); return undefined; };

  const _sockH={};
  const _socket={ connected:false, on:(ev,fn)=>{ (_sockH[ev]=_sockH[ev]||[]).push(fn); }, off:()=>{} };
  const realtime={ socket:_socket, connect:()=>{ _socket.connected=true; }, on:(ev,fn)=>_socket.on(ev,fn) };
  const calls=[]; const env={};
  env._prefs={ sound_enabled:1, desktop_enabled:0, teams_enabled:0, quiet_hours_enabled:0,
               quiet_hours_start:null, quiet_hours_end:null, minimum_severity:'info', enabled_event_types:'', _exists:false };
  env._unread=0; env._items=[];
  const frappe={ realtime, call:o=>{ calls.push(o); const m=o.method||''; const cb=o.callback;
    if(m.indexOf('get_preferences')>=0){ cb&&cb({message:{success:true,preferences:env._prefs}}); }
    else if(m.indexOf('set_preferences')>=0){ const a=o.args||{}; Object.keys(a).forEach(k=>{ if(a[k]!=null){ env._prefs[k]=a[k]; } }); env._prefs._exists=true; cb&&cb({message:{success:true,preferences:env._prefs}}); }
    else if(m.indexOf('get_unread_count')>=0){ cb&&cb({message:{success:true,unread:env._unread}}); }
    else if(m.indexOf('get_notifications')>=0){ cb&&cb({message:{success:true,unread:env._unread,items:env._items}}); }
    else { cb&&cb({message:{success:true}}); } } };

  const winListeners=[];
  const win={ location:{pathname:'/home',href:''}, getComputedStyle:()=>({position:'relative'}),
    addEventListener:(t,fn)=>winListeners.push({t,fn}),
    localStorage:{_s:{},getItem(k){return k in this._s?this._s[k]:null;},setItem(k,v){this._s[k]=String(v);}},
    requestAnimationFrame:fn=>{ fn(); return 1; },
    frappe, MutationObserver, DOMParser, AudioContext, Notification:Notif };
  win.window=win;

  Object.assign(env,{ document, win, body, calls, observers, desktops,
    soundCount:()=>soundCount,
    setHidden:b=>{ document.hidden=b; },
    setPermission:p=>{ Notif.permission=p; },
    setPrefs:o=>{ Object.assign(env._prefs,o); if(o&&Object.keys(o).length) env._prefs._exists=true; },
    setUnread:n=>{ env._unread=n; },
    unlock:()=>{ winListeners.filter(l=>l.t==='click').forEach(l=>l.fn({})); },
    fireRealtime:p=>{ (_sockH['ec_notification']||[]).forEach(fn=>fn(p)); },
    fireClick:el=>{ const ev={type:'click',target:el,stopPropagation(){},preventDefault(){}}; (el._l||[]).filter(l=>l.t==='click').forEach(l=>l.fn(ev)); },
    toastRoot:()=>document.getElementById('ec-nc-toasts'),
    toastCount:()=>{ const r=document.getElementById('ec-nc-toasts'); return r?r.children.filter(c=>c.classList.contains('on')).length:0; },
    toasts:()=>{ const r=document.getElementById('ec-nc-toasts'); return r?r.children:[]; } });
  return env;
}
function run(env){ new Function('window','document','console',SRC)(env.win,env.document,console); }
function hhmm(d){ return ('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2); }
function evt(o){ return Object.assign({ event_id:'E', event_type:'task_assigned', severity:'action_required',
  title:'T', message:'m', action_url:'/app/task/T1', created_at:'2026-06-22 09:00:00', unread:1,
  item:{name:'NL', subject:'T', message:'m', action_url:'/app/task/T1'} }, o); }

// ===== A) initial load shows NO toast/sound; foreground non-urgent toast, plain text =====
(function(){
  const env=makeEnv(); run(env);
  ok(env.toastCount()===0,'init: no toast on load (only realtime triggers)');
  ok(env.soundCount()===0,'init: no sound on load');
  ok(env.calls.some(c=>(c.method||'').indexOf('get_preferences')>=0),'init: loads preferences');
  env.unlock();
  env.fireRealtime(evt({event_id:'E1', title:'<b>Việc mới</b>', message:'<i>nội dung</i>'}));
  ok(env.toastCount()===1,'realtime: one toast appears');
  const t=env.toasts()[0];
  ok(t.querySelector('.ec-nc-toast-ttl').textContent==='Việc mới','toast: title is plain text (HTML stripped)');
  ok(t.querySelector('.ec-nc-toast-msg').textContent==='nội dung','toast: body is plain text');
  ok(env.soundCount()===1,'realtime: sound plays once (sound on, unlocked)');
  ok(env.desktops.length===0,'foreground non-urgent: no desktop notification');
})();

// ===== B) per-event dedupe: same event_id never re-toasts/re-sounds =====
(function(){
  const env=makeEnv(); run(env); env.unlock();
  env.fireRealtime(evt({event_id:'D1'}));
  env.fireRealtime(evt({event_id:'D1'}));   // duplicate
  ok(env.toastCount()===1,'dedupe: duplicate event_id -> still one toast');
  ok(env.soundCount()===1,'dedupe: duplicate event_id -> sound only once');
})();

// ===== C) toast cap = max 3 =====
(function(){
  const env=makeEnv(); run(env); env.unlock();
  ['c1','c2','c3','c4','c5'].forEach(id=>env.fireRealtime(evt({event_id:id})));
  ok(env.toastCount()===3,'cap: at most 3 toasts visible');
})();

// ===== D) sound gating: pref off, quiet hours, urgent bypass =====
(function(){
  const env=makeEnv(); env.setPrefs({sound_enabled:0}); run(env); env.unlock();
  env.fireRealtime(evt({event_id:'s1'}));
  ok(env.soundCount()===0,'sound off: no sound when sound_enabled=0');
})();
(function(){
  const now=new Date(); const start=new Date(now.getTime()-60*60000); const end=new Date(now.getTime()+60*60000);
  const env=makeEnv();
  env.setPrefs({sound_enabled:1, quiet_hours_enabled:1, quiet_hours_start:hhmm(start), quiet_hours_end:hhmm(end)});
  run(env); env.unlock();
  env.fireRealtime(evt({event_id:'q1', severity:'action_required'}));
  ok(env.soundCount()===0,'quiet hours: non-urgent makes no sound');
  env.fireRealtime(evt({event_id:'q2', severity:'urgent'}));
  ok(env.soundCount()===1,'quiet hours: urgent bypasses and sounds');
})();

// ===== E) desktop: background-only, opt-in + permission; urgent in foreground =====
(function(){
  const env=makeEnv({hidden:true, permission:'granted'}); env.setPrefs({desktop_enabled:1}); run(env); env.unlock();
  env.fireRealtime(evt({event_id:'k1', title:'<b>Desk</b>'}));
  ok(env.desktops.length===1,'desktop: background + granted + opted-in -> notification');
  ok(env.desktops[0].title==='Desk','desktop: title plain text');
  env.desktops[0].onclick && env.desktops[0].onclick();
  ok(env.win.location.href==='/app/task/T1','desktop: click navigates to action_url');
})();
(function(){
  const env=makeEnv({hidden:false, permission:'granted'}); env.setPrefs({desktop_enabled:1}); run(env); env.unlock();
  env.fireRealtime(evt({event_id:'f1', severity:'action_required'}));
  ok(env.desktops.length===0,'desktop: foreground non-urgent -> no desktop');
  env.fireRealtime(evt({event_id:'f2', severity:'urgent'}));
  ok(env.desktops.length===1,'desktop: urgent shows even in foreground');
})();
(function(){
  const env=makeEnv({hidden:true, permission:'denied'}); env.setPrefs({desktop_enabled:1}); run(env); env.unlock();
  env.fireRealtime(evt({event_id:'d1'}));
  ok(env.desktops.length===0,'desktop: permission denied -> no desktop (toast fallback)');
  ok(env.toastCount()===1,'desktop denied: toast fallback still shown');
})();

// ===== F) preferences panel: "Bật thông báo trên máy tính" requests permission + saves =====
(function(){
  const env=makeEnv({permission:'granted'}); run(env);
  const btn=env.document.getElementById('ec-nc-pop-root').querySelector('#ec-pref-desktop-btn');
  ok(!!btn,'prefs: desktop enable button present');
  env.fireClick(btn);
  ok(env.calls.some(c=>(c.method||'').indexOf('set_preferences')>=0 && c.args && c.args.desktop_enabled===1),
     'prefs: enabling desktop saves desktop_enabled=1 after permission granted');
})();

// ===== G) toast click navigates to action_url =====
(function(){
  const env=makeEnv(); run(env); env.unlock();
  env.fireRealtime(evt({event_id:'g1', action_url:'/app/task/G1', item:{name:'NLg',subject:'T',message:'m',action_url:'/app/task/G1'}}));
  env.fireClick(env.toasts()[0]);
  ok(env.win.location.href==='/app/task/G1','toast: click navigates to action_url');
})();

// ===== H) native-inbox event (update_badge:false): toast fires; badge re-synced via
//        get_unread_count (NOT incremented from payload) -> no double badge =====
(function(){
  const env=makeEnv(); run(env); env.unlock();
  const uc=()=>env.calls.filter(c=>(c.method||'').indexOf('get_unread_count')>=0).length;
  const b1=uc();
  env.fireRealtime({event_id:'NB1', event_type:'task_assigned', severity:'action_required',
    title:'Giao viec', message:'m', action_url:'/app/task/T1',
    update_badge:false, inbox_managed_by_native:true, unread:99, unread_count:99});
  ok(env.toastCount()===1,'native-inbox: toast fires');
  ok(uc()===b1+1,'native-inbox: badge re-synced via get_unread_count (no payload increment)');
  const b2=uc();
  env.fireRealtime({event_id:'NB2', event_type:'mention', severity:'info', title:'x', message:'y',
    unread_count:5, item:{name:'NLn',subject:'x',message:'y',action_url:'/app/task/T2'}});
  ok(uc()===b2,'normal event: no get_unread_count (badge from payload)');
})();

if(failures){ console.error('\n'+failures+' FAILURE(S)'); process.exit(1); }
console.log('\nALL DELIVERY RUNTIME CHECKS PASSED');
process.exit(0);
