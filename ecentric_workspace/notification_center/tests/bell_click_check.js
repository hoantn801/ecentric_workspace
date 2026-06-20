// Runtime proof for the Notification Center global asset (delegated capture design).
// Executes the REAL asset against a mini-DOM that models: capture+bubble event
// propagation, closest(), the onclick property + inline onclick attribute, target &
// document-delegated listeners, a MutationObserver, and DOMParser. Proves:
//   * badge matrix 0/1/9/10+
//   * single badge + single dropdown + single capture listener (even on reinstall)
//   * /home plain click opens dropdown, fires NO legacy handler; modifier/middle native
//   * /approval bell rendered AFTER init still works (the production bug) and legacy
//     handlers attached before OR after the asset never fire on a plain click
//   * header RERENDER after install: badge remounts, no duplicate badge/dropdown/listener
//   * Frappe Desk /app inert; public no-bell page inert
//   * notification HTML is rendered as SAFE PLAIN TEXT (no tags, via textContent)
//   node ecentric_workspace/notification_center/tests/bell_click_check.js
'use strict';
const fs = require('fs');
const path = require('path');
const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'public', 'js', 'notification_center.js'), 'utf8');
let failures = 0;
function ok(c, m){ if(!c){ failures++; console.error('FAIL: '+m);} else { console.log('ok  - '+m);} }

// ----------------------- selector engine (small but real) -----------------------
function parseCompound(s){
  const c = { tag:null, id:null, classes:[], attrs:[] };
  s = s.trim();
  const re = /([#.][\w-]+)|(\[[^\]]+\])|([\w*]+)/g; let m;
  while((m=re.exec(s))){
    const tok=m[0];
    if(tok[0]==='#') c.id=tok.slice(1);
    else if(tok[0]==='.') c.classes.push(tok.slice(1));
    else if(tok[0]==='['){ const mm=/\[([\w-]+)([*^$]?=)"([^"]*)"\]/.exec(tok); if(mm) c.attrs.push({n:mm[1],op:mm[2],v:mm[3]}); }
    else if(tok!=='*') c.tag=tok.toLowerCase();
  }
  return c;
}
function matchCompound(el, c){
  if(!el || el.nodeType==='doc') return false;
  if(c.tag && (el.tagName||'').toLowerCase()!==c.tag) return false;
  if(c.id && el.id!==c.id) return false;
  for(const cl of c.classes){ if(!el.classList.contains(cl)) return false; }
  for(const a of c.attrs){ const v=el.getAttribute?el.getAttribute(a.n):null; if(v==null) return false;
    if(a.op==='*='){ if(String(v).indexOf(a.v)<0) return false; } else if(String(v)!==a.v) return false; }
  return true;
}
function matchSelector(el, sel){
  return sel.split(',').some(branch=>{
    const parts=branch.trim().split(/\s+/).map(parseCompound);
    const last=parts[parts.length-1];
    if(!matchCompound(el,last)) return false;
    let i=parts.length-2, n=el.parentNode;
    while(i>=0){ let found=false; while(n){ if(matchCompound(n,parts[i])){found=true;n=n.parentNode;break;} n=n.parentNode; } if(!found) return false; i--; }
    return true;
  });
}

function mkClassList(){ const set=new Set(); return {
  add:(...c)=>c.forEach(x=>x&&set.add(x)), remove:(...c)=>c.forEach(x=>set.delete(x)),
  toggle:(c,on)=>{const v=on===undefined?!set.has(c):!!on; v?set.add(c):set.delete(c); return v;},
  contains:c=>set.has(c) }; }

class El{
  constructor(tag){ this.tagName=(tag||'div').toUpperCase(); this.children=[]; this.parentNode=null;
    this.attrs={}; this.style={}; this.classList=mkClassList(); this._tc=''; this.id='';
    this._l=[]; this.onclick=null; this._inlineHandler=null; }
  set className(v){ this._cn=v; String(v||'').split(/\s+/).filter(Boolean).forEach(c=>this.classList.add(c)); }
  get className(){ return this._cn||''; }
  setAttribute(k,v){ this.attrs[k]=String(v); if(k==='id') this.id=String(v); }
  getAttribute(k){ return this.attrs[k]===undefined?null:this.attrs[k]; }
  removeAttribute(k){ delete this.attrs[k]; }
  set textContent(v){ this._tc=String(v); this.children=[]; }
  get textContent(){ if(this.children.length) return this.children.map(c=>c.textContent).join(''); return this._tc; }
  set innerHTML(v){ this._html=v; this.children=[]; const re=/id="([^"]+)"/g; let m;
    while((m=re.exec(v))){ const e=new El('div'); e.setAttribute('id',m[1]); this.appendChild(e);} }
  get innerHTML(){ return this._html||''; }
  get firstChild(){ return this.children[0]||null; }
  appendChild(c){ c.parentNode=this; this.children.push(c); return c; }
  removeChild(c){ const i=this.children.indexOf(c); if(i>=0) this.children.splice(i,1); c.parentNode=null; return c; }
  replaceChild(n,o){ const i=this.children.indexOf(o); if(i>=0){ this.children[i]=n; n.parentNode=this; o.parentNode=null;} return o; }
  contains(n){ if(n===this) return true; return this.children.some(c=>c.contains&&c.contains(n)); }
  closest(sel){ let n=this; while(n&&n.nodeType!=='doc'){ if(matchSelector(n,sel)) return n; n=n.parentNode; } return null; }
  addEventListener(t,fn){ (this._l).push({t,fn}); }
  focus(){}
  getBoundingClientRect(){ return {bottom:40,right:200,top:10,left:180}; }
  querySelector(s){ return this._find(s,false); }
  querySelectorAll(s){ return this._find(s,true); }
  _find(s,all){ const acc=[]; const walk=n=>n.children.forEach(c=>{ if(matchSelector(c,s)) acc.push(c); walk(c);}); walk(this); return all?acc:(acc[0]||null); }
}

function stripHtml(str){
  let s=String(str).replace(/<[^>]*>/g,'');
  s=s.replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,'&');
  return s;
}

function makeEnv(pathname){
  const head=new El('head'); const body=new El('body');
  head.nodeType=body.nodeType='el';
  const byId={}; const docCaps=[]; const docBubs=[];
  const reg=c=>{ if(c.id) byId[c.id]=c; };
  const _h=head.appendChild.bind(head); head.appendChild=c=>{reg(c);return _h(c);};
  const _b=body.appendChild.bind(body); body.appendChild=c=>{reg(c);return _b(c);};
  let theBellQuery=()=>null;
  const document={ nodeType:'doc', readyState:'complete', head, body,
    createElement:t=>new El(t), getElementById:id=>byId[id]||null,
    addEventListener:(t,fn,cap)=>{ if(t==='click'){ (cap?docCaps:docBubs).push(fn); } },
    querySelector:s=> (s.indexOf('notification-log')>=0 ? theBellQuery() : null),
    querySelectorAll:()=>[], _docCaps:docCaps, _docBubs:docBubs };
  body.parentNode=document; head.parentNode=document;
  const observers=[];
  function MutationObserver(cb){ this.cb=cb; observers.push(this); }
  MutationObserver.prototype.observe=function(){ this.active=true; };
  MutationObserver.prototype.disconnect=function(){ this.active=false; };
  function DOMParser(){}
  DOMParser.prototype.parseFromString=function(str){ const b=new El('body'); b._tc=stripHtml(str); return {body:b}; };
  const calls=[]; let unread=3; let items=[];
  const win={ location:{pathname}, addEventListener:()=>{},
    localStorage:{_s:{},getItem(k){return k in this._s?this._s[k]:null;},setItem(k,v){this._s[k]=String(v);}},
    frappe:{ call:o=>{ calls.push(o); const m=o.method||'';
      if(m.indexOf('get_unread_count')>=0&&o.callback) o.callback({message:{success:true,unread}});
      if(m.indexOf('get_notifications')>=0&&o.callback) o.callback({message:{success:true,unread,items}});
    }}, MutationObserver, DOMParser, AudioContext:null };
  win.window=win;
  return { document, win, body, calls, observers,
    setBellQuery:f=>{theBellQuery=f;},
    setUnread:n=>{unread=n;}, setItems:a=>{items=a;},
    fireObservers:()=>observers.forEach(o=>o.active&&o.cb([])),
    // dispatch a click with capture -> target -> bubble, honouring stop flags
    click:(target,init)=>{ init=init||{};
      const ev={type:'click',target,button:init.button||0,metaKey:!!init.metaKey,ctrlKey:!!init.ctrlKey,
        shiftKey:!!init.shiftKey,altKey:!!init.altKey,defaultPrevented:false,_stop:false,_imm:false,
        preventDefault(){this.defaultPrevented=true;},stopPropagation(){this._stop=true;},
        stopImmediatePropagation(){this._stop=true;this._imm=true;}};
      const path=[]; let n=target; while(n){path.push(n);n=n.parentNode;} // target..document
      // capture: document -> target
      for(const fn of docCaps.slice()){ fn(ev); if(ev._imm) return ev; }
      if(ev._stop) return ev;
      // target + bubble: target -> document
      for(const node of path){
        if(node.getAttribute && node.getAttribute('onclick') && node._inlineHandler) node._inlineHandler(ev);
        if(ev._imm) return ev;
        for(const l of (node._l||[]).slice()){ if(l.t==='click'){ l.fn(ev); if(ev._imm) return ev; } }
        if(node.onclick) node.onclick(ev);
        if(ev._stop) return ev;
        if(node===document) break;
      }
      for(const fn of docBubs.slice()){ if(ev._stop) break; fn(ev); }
      return ev; }
  };
}

function run(env){ new Function('window','document','console',SRC)(env.win,env.document,console); }

// build a topbar bell with the FULL set of legacy handlers
function addBell(env){
  let tb=env.body.querySelector('.topbar-actions');
  if(!tb){ tb=new El('div'); tb.className='topbar-actions'; env.body.appendChild(tb); }
  const bell=new El('a'); bell.setAttribute('href','/app/notification-log'); bell.className='icon-btn';
  const dot=new El('span'); dot.className='dot'; bell.appendChild(dot);
  tb.appendChild(bell);
  const legacy={inline:0,prop:0,addEL:0,deleg:0};
  bell.setAttribute('onclick',"legacy()"); bell._inlineHandler=()=>legacy.inline++;
  bell.onclick=()=>legacy.prop++;
  bell.addEventListener('click',()=>legacy.addEL++);
  env.document.addEventListener('click',e=>{ let t=e.target; while(t){ if(t===bell){legacy.deleg++;break;} t=t.parentNode; } }, false);
  env.setBellQuery(()=>bell);
  return {bell,legacy};
}
function adoptedBadgeCount(bell){ return bell.querySelectorAll('.ec-nc-badge').length; }
function popOpen(env){ const p=env.document.getElementById('ec-nc-pop-root'); return !!(p&&p.classList.contains('on')); }
function popCount(env){ return env.body.children.filter(c=>c.classList.contains('ec-nc-pop')).length; }
function captureCount(env){ return env.document._docCaps.length; }

// ============ 1) /home: bell at init, badge matrix, plain/modifier clicks ============
(function(){
  const env=makeEnv('/home'); const {bell,legacy}=addBell(env); run(env);
  ok(adoptedBadgeCount(bell)===1,'/home: exactly one badge mounted');
  ok(popCount(env)===1,'/home: exactly one dropdown');
  ok(captureCount(env)===1,'/home: exactly one document capture click listener');
  const badge=bell.querySelector('.ec-nc-badge');
  env.setUnread(0); env.win.frappe.call({method:'x.get_unread_count',callback:r=>{}}); // noop feed
  // feed via the asset's own refreshCount path:
  function feed(n){ env.setUnread(n); env.document._docCaps; // trigger refreshCount by calling the asset path is internal;
    // simplest: directly invoke a fresh count callback through frappe.call interception already wired in open(); use poll:
  }
  // drive counts through realtime-less poll by calling refreshCount indirectly: open dropdown triggers refresh()
  // Use unread values then a click to refresh:
  env.setUnread(1); const e1=env.click(bell,{button:0}); ok(popOpen(env)&&badge.textContent==='1'&&!badge.classList.contains('ec-nc-badge--pill'),'/home: unread 1 -> circle "1", dropdown opens');
  ok(legacy.inline+legacy.prop+legacy.addEL+legacy.deleg===0,'/home: plain click fired NO legacy handler');
  ok(e1.defaultPrevented===true,'/home: plain click preventDefault (native nav cancelled)');
  // close
  env.click(env.body,{button:0});
  env.setUnread(9); env.click(bell,{button:0}); ok(badge.textContent==='9'&&!badge.classList.contains('ec-nc-badge--pill'),'/home: unread 9 -> circle "9"'); env.click(env.body,{});
  env.setUnread(10); env.click(bell,{button:0}); ok(badge.textContent==='9+'&&badge.classList.contains('ec-nc-badge--pill'),'/home: unread 10 -> "9+" pill'); env.click(env.body,{});
  env.setUnread(250); env.click(bell,{button:0}); ok(badge.textContent==='9+','/home: unread 250 -> capped "9+"'); env.click(env.body,{});
  env.setUnread(0); env.click(bell,{button:0}); ok(badge.classList.contains('on')===false,'/home: unread 0 -> badge hidden'); env.click(env.body,{});
  // modifier / middle keep native
  const ec=env.click(bell,{button:0,ctrlKey:true}); ok(popOpen(env)===false&&ec.defaultPrevented===false,'/home: Ctrl-click keeps native nav, no dropdown');
  const em=env.click(bell,{button:1}); ok(popOpen(env)===false&&em.defaultPrevented===false,'/home: middle-click keeps native nav, no dropdown');
})();

// ============ 2) /approval: bell rendered AFTER init (the production bug) ============
(function(){
  const env=makeEnv('/approval'); run(env);                 // NO bell yet at init
  ok(captureCount(env)===1,'/approval: capture listener installed before bell exists');
  const {bell,legacy}=addBell(env); env.fireObservers();     // header renders later
  ok(bell.querySelector('.ec-nc-badge'),'/approval: badge mounted on dynamically-rendered bell (observer)');
  const e=env.click(bell,{button:0});
  ok(popOpen(env)===true,'/approval: plain click opens dropdown on dynamic bell');
  ok(legacy.inline+legacy.prop+legacy.addEL+legacy.deleg===0,'/approval: NO legacy "feature in development" handler fires');
  ok(e.defaultPrevented===true,'/approval: plain click preventDefault');
})();

// ============ 3) legacy handler attached AFTER the asset, on a rerendered header =====
(function(){
  const env=makeEnv('/approval'); const first=addBell(env); run(env);
  // simulate header rerender: remove ONLY the old topbar (the dropdown is a body-level
  // singleton and must persist), then a brand new bell + NEW legacy handlers appear.
  const oldTb=env.body.querySelector('.topbar-actions'); if(oldTb) env.body.removeChild(oldTb);
  const {bell,legacy}=addBell(env); env.fireObservers();
  ok(bell.querySelectorAll('.ec-nc-badge').length===1,'rerender: exactly one badge on the new bell');
  ok(popCount(env)===1,'rerender: still exactly one dropdown');
  ok(captureCount(env)===1,'rerender: still exactly one capture listener');
  const e=env.click(bell,{button:0});
  ok(popOpen(env)===true,'rerender: plain click opens dropdown on new bell');
  ok(legacy.inline+legacy.prop+legacy.addEL+legacy.deleg===0,'rerender: legacy handler attached AFTER install never fires');
})();

// ============ 4) reinstall (asset loaded twice) -> no duplicates ============
(function(){
  const env=makeEnv('/overview'); const {bell}=addBell(env); run(env); run(env);
  ok(bell.querySelectorAll('.ec-nc-badge').length===1,'reinstall: one badge');
  ok(popCount(env)===1,'reinstall: one dropdown');
  ok(captureCount(env)===1,'reinstall: one capture listener (single-install guard)');
})();

// ============ 5) Frappe Desk + public no-bell inert ============
(function(){
  const env=makeEnv('/app/build'); const {bell}=addBell(env); run(env);
  ok(bell.querySelector('.ec-nc-badge')===null && captureCount(env)===0 && env.calls.length===0,'/app/*: asset fully inert (no badge, no listener, no API, no Desk bind)');
})();
(function(){
  const env=makeEnv('/login'); let threw=false; try{ run(env);}catch(e){threw=true;}
  ok(!threw,'/login (no bell): loads without error');
})();

// ============ 6) notification HTML -> safe plain text ============
(function(){
  const env=makeEnv('/home'); const {bell}=addBell(env);
  env.setItems([{name:'N1',subject:'<strong>Hi</strong> &amp; <div>there</div>',message:'<br><b>Body</b> <script>x()<\/script>',source_label:'<i>WR</i>',action_url:'/weekly-update?week=2026-W26',is_read:0,created_at:'2026-06-20 08:00:00'}]);
  env.setUnread(1); run(env);
  env.click(bell,{button:0});                       // open -> refresh -> renderList
  const list=env.document.getElementById('ec-nc-pop-root').querySelector('#ec-nc-list');
  const item=list.children[0];
  const subj=item.querySelector('.ec-nc-subj').textContent;
  const msg=item.querySelector('.ec-nc-msg').textContent;
  ok(subj.indexOf('<')<0 && subj.indexOf('>')<0,'plaintext: subject has no angle brackets');
  ok(subj==='Hi & there','plaintext: subject decoded+stripped to "Hi & there" (got: '+subj+')');
  ok(msg.indexOf('<')<0 && msg.indexOf('>')<0,'plaintext: message has no angle brackets');
  ok(msg==='Body x()','plaintext: message decoded+stripped to "Body x()" (got: '+msg+')');
  // href is the server action_url (same-origin path), not built/derived from content
  const href=item.getAttribute('href');
  ok(href==='/weekly-update?week=2026-W26','plaintext: item href = server action_url');
})();

if(failures){ console.error('\n'+failures+' assertion(s) FAILED'); process.exit(1); }
console.log('\nAll runtime assertions passed.');
process.exit(0);
