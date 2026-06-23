// Runtime proof for Notification Center realtime CONNECTION RECOVERY.
// Executes the REAL asset against a mini-DOM with a rich Socket.IO mock (socket + Manager),
// fake timers, Web Notification API and AudioContext. Drives disconnect / reconnect_attempt /
// reconnect / reconnect_failed and asserts: one bound handler, one manual connect when idle,
// no connect while reconnecting, bounded watchdog reconnect after give-up, no duplicate handler
// across reconnect cycles, one event -> one toast/sound/desktop, mute gating, update_badge=false.
//   node ecentric_workspace/notification_center/tests/realtime_recovery_check.js
'use strict';
const fs=require('fs'); const path=require('path');
const SRC=fs.readFileSync(path.join(__dirname,'..','..','public','js','notification_center.js'),'utf8');
let failures=0; function ok(c,m){ if(!c){failures++;console.error('FAIL: '+m);} else {console.log('ok  - '+m);} }

// ---- fake timers (asset uses bare setTimeout/clearTimeout/setInterval) ----
let timers=[]; let tid=0;
const realST=global.setTimeout, realCT=global.clearTimeout, realSI=global.setInterval, realCI=global.clearInterval;
global.setTimeout=(fn,ms)=>{ const id=++tid; timers.push({id,fn,ms,kind:'to'}); return id; };
global.clearTimeout=(id)=>{ timers=timers.filter(t=>t.id!==id); };
global.setInterval=(fn,ms)=>{ const id=++tid; timers.push({id,fn,ms,kind:'iv'}); return id; };
global.clearInterval=(id)=>{ timers=timers.filter(t=>t.id!==id); };
function pendingTimeouts(){ return timers.filter(t=>t.kind==='to'); }
function fireDueTimeouts(){ const due=pendingTimeouts(); due.forEach(t=>{ timers=timers.filter(x=>x.id!==t.id); t.fn(); }); }
function restoreTimers(){ global.setTimeout=realST; global.clearTimeout=realCT; global.setInterval=realSI; global.clearInterval=realCI; }

// ---- selector engine (subset; supports tag/#id/.class/[attr="v"]) ----
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

// ---- rich Socket.IO mock: socket + Manager (io) ----
function makeSocket(opts){ opts=opts||{};
  const H={}, M={};
  const io={ on:(e,f)=>{(M[e]=M[e]||[]).push(f);}, emit:(e,...a)=>{(M[e]||[]).forEach(f=>f(...a));} };
  const s={ connected:!!opts.connected, io, connectCalls:0,
    on:(e,f)=>{(H[e]=H[e]||[]).push(f);},
    off:(e,f)=>{ if(H[e]) H[e]=H[e].filter(x=>x!==f); },
    connect(){ this.connectCalls++; if(!opts.connectFails){ this.connected=true; (H['connect']||[]).forEach(f=>f()); } },
    emit:(e,...a)=>{(H[e]||[]).forEach(f=>f(...a));},
    listeners:e=>(H[e]||[]).slice() };
  return s;
}

function makeEnv(opts){ opts=opts||{}; timers.length=0;   // isolate fake timers per test
  const head=new El('head'); const body=new El('body'); head.nodeType=body.nodeType='el';
  const byId={}; const reg=c=>{ if(c.id)byId[c.id]=c; };
  const _h=head.appendChild.bind(head); head.appendChild=c=>{reg(c);return _h(c);};
  const _b=body.appendChild.bind(body); body.appendChild=c=>{reg(c);return _b(c);};
  // a real bell so the badge mounts (for the update_badge test)
  const bell=new El('button'); bell.setAttribute('data-ec-notification-bell','1'); body.appendChild(bell);
  const docCaps=[];
  const document={ nodeType:'doc', readyState:'complete', head, body, hidden:!!opts.hidden,
    createElement:t=>new El(t), getElementById:id=>byId[id]||null,
    addEventListener:(t,fn,cap)=>{ if(t==='click'&&cap)docCaps.push(fn); },
    querySelector:s=>body._find(s,false), querySelectorAll:s=>body._find(s,true) };
  body.parentNode=document; head.parentNode=document;
  function MutationObserver(cb){ this.cb=cb; } MutationObserver.prototype.observe=function(){}; MutationObserver.prototype.disconnect=function(){};
  function DOMParser(){} DOMParser.prototype.parseFromString=function(str){ const b=new El('body'); b._tc=stripHtml(str); return {body:b}; };
  let soundCount=0;
  function Osc(){ return {type:'',frequency:{value:0},connect(){},start(){},stop(){}}; }
  function Gain(){ return {gain:{setValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){}}; }
  function AudioContext(){ soundCount++; this.currentTime=0; this.state='running'; this.destination={};
    this.createOscillator=Osc; this.createGain=Gain; this.resume=()=>{}; }
  const desktops=[];
  function Notif(title,o){ this.title=title; this.opts=o||{}; this.onclick=null; this.close=()=>{}; desktops.push(this); }
  Notif.permission=opts.permission||'default';
  Notif.requestPermission=function(cb){ if(cb) cb(Notif.permission); return undefined; };

  const socket=makeSocket(opts);
  const realtime={ socket, connect:()=>{ /* no-op: faithful to lazy_connect not reviving a dead socket */ }, on:(e,f)=>socket.on(e,f) };
  const calls=[]; const env={};
  env._prefs={ sound_enabled:1, desktop_enabled:0, teams_enabled:0, quiet_hours_enabled:0,
               quiet_hours_start:null, quiet_hours_end:null, minimum_severity:'info', enabled_event_types:'', _exists:false };
  env._unread=0; env._items=[];
  const frappe={ realtime, call:o=>{ calls.push(o); const m=o.method||''; const cb=o.callback;
    if(m.indexOf('get_preferences')>=0){ cb&&cb({message:{success:true,preferences:env._prefs}}); }
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
  Object.assign(env,{ document, win, body, bell, socket, calls, desktops,
    soundCount:()=>soundCount,
    setMuted:()=>{ win.localStorage.setItem('ec_notif_muted','1'); },
    unlock:()=>{ winListeners.filter(l=>l.t==='click').forEach(l=>l.fn({})); },
    fireRealtime:p=>{ socket.listeners('ec_notification').forEach(fn=>fn(p)); },
    handlerCount:()=>socket.listeners('ec_notification').length,
    badgeText:()=>{ const b=bell.querySelector('.ec-nc-badge'); return b?b.textContent:null; },
    toastCount:()=>{ const r=document.getElementById('ec-nc-toasts'); return r?r.children.filter(c=>c.classList.contains('on')).length:0; },
    pendingTimeouts });
  return env;
}
function run(env){ new Function('window','document','console',SRC)(env.win,env.document,console); }

let ev;
// 1) handler bound exactly once + one manual connect at idle startup
ev=makeEnv({connected:false}); run(ev);
ok(ev.handlerCount()===1,'1: ec_notification handler bound exactly once at init');
ok(ev.socket.connectCalls===1,'2: disconnected+inactive at startup -> exactly one manual socket.connect()');
ok(ev.socket.connected===true,'   socket becomes connected after the manual connect');

// 3) actively reconnecting -> watchdog must NOT start another connect
ev=makeEnv({connected:false}); run(ev);
const base=ev.socket.connectCalls;            // =1 after init
ev.socket.connected=false; ev.socket.emit('disconnect','transport close');
ev.socket.io.emit('reconnect_failed');        // arm watchdog (reconnecting=false here)
ev.socket.io.emit('reconnect_attempt');       // native retry resumes -> reconnecting=true
fireDueTimeouts();                            // watchdog ticks while reconnecting
ok(ev.socket.connectCalls===base,'3: while actively reconnecting, watchdog does NOT call connect');

// 4) native attempts exhausted -> bounded watchdog reconnect (success path)
ev=makeEnv({connected:false}); run(ev);
const b4=ev.socket.connectCalls;
ev.socket.connected=false; ev.socket.emit('disconnect','transport close');
ev.socket.io.emit('reconnect_failed');        // give-up -> startWatchdog
fireDueTimeouts();                            // tick -> connect() succeeds -> 'connect' -> stop
ok(ev.socket.connectCalls===b4+1,'4: after reconnect_failed the watchdog issues one connect');
ok(ev.socket.connected===true,'   watchdog reconnect succeeded');
ok(ev.pendingTimeouts().length===0,'   watchdog stopped after success (no pending timer)');

// 4b) bounded: connect keeps failing -> attempts capped, never an infinite loop
ev=makeEnv({connected:false, connectFails:true}); run(ev);  // connect() never sets connected
// init tried once (fails). Arm + drive the watchdog to exhaustion.
ev.socket.io.emit('reconnect_failed');
let guard=0; while(ev.pendingTimeouts().length && guard<100){ fireDueTimeouts(); guard++; }
ok(guard<100,'4b: watchdog is bounded (no infinite loop)');
ok(ev.socket.connectCalls<=1+6,'4b: total connect attempts capped at WD_MAX (+startup)');
ok(ev.pendingTimeouts().length===0,'4b: watchdog timer chain ends');

// 5) repeated disconnect/reconnect cycles -> still exactly one handler, one toast
ev=makeEnv({connected:false}); run(ev); ev.unlock();
for(let i=0;i<5;i++){ ev.socket.connected=false; ev.socket.emit('disconnect','transport close');
  ev.socket.io.emit('reconnect_attempt'); ev.socket.io.emit('reconnect');
  ev.socket.connected=true; ev.socket.emit('connect'); }
ok(ev.handlerCount()===1,'5: no duplicate ec_notification handler after 5 reconnect cycles');
ev.fireRealtime({event_id:'E5',title:'x',severity:'info'});
ok(ev.toastCount()===1,'5: one event after reconnects -> exactly one toast (no duplicate)');

// 6) one event -> one toast + one sound
ev=makeEnv({connected:false}); run(ev); ev.unlock();
ev.fireRealtime({event_id:'E6',title:'t',severity:'info'});
ok(ev.toastCount()===1,'6: one event -> one toast');
ok(ev.soundCount()===1,'6: one event -> one sound');

// 7) desktop granted + opted-in -> one desktop notification
ev=makeEnv({connected:false,permission:'granted',hidden:true}); ev._prefs.desktop_enabled=1; run(ev); ev.unlock();
ev.fireRealtime({event_id:'E7',title:'t',severity:'info',action_url:'/app/task/T7'});
ok(ev.desktops.length===1,'7: desktop granted+opt-in -> one desktop notification');
ok(ev.desktops[0]&&typeof ev.desktops[0].onclick==='function','7: desktop has onclick -> opens action_url');

// 8) muted -> toast remains, sound does not run
ev=makeEnv({connected:false}); ev.setMuted(); run(ev); ev.unlock();
ev.fireRealtime({event_id:'E8',title:'t',severity:'info'});
ok(ev.toastCount()===1,'8: muted -> toast still shows');
ok(ev.soundCount()===0,'8: muted -> no sound');

// 9) update_badge=false -> badge not incremented from payload
ev=makeEnv({connected:false}); run(ev); ev.unlock();
ev.fireRealtime({event_id:'E9',title:'t',severity:'info',update_badge:false,unread:9,item:{name:'N9'}});
ok(ev.badgeText()!=='9','9: update_badge=false -> badge NOT set to payload unread');
ok(ev.toastCount()===1,'9: update_badge=false -> toast still fires');

restoreTimers();
console.log(failures? ('\nFAILURES: '+failures) : '\nALL PASS');
process.exit(failures?1:0);
