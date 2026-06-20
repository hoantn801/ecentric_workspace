// Runtime proof for the Notification Center asset (dual-shell delegated capture).
// Executes the REAL asset against a mini-DOM with a small but real selector engine
// (closest/querySelector), capture+bubble propagation, onclick property + inline
// onclick attribute, MutationObserver and DOMParser. Fixtures mirror the ACTUAL
// production DOM:
//   /home     bell = <a class="icon-btn" href="/app/notification-log"><svg><use #i-bell></svg><span class="dot">
//   /approval bell = <button class="icon-btn" title="Thông báo" onclick="alert('...tính năng đang phát triển')"><svg><path></svg><span class="dot">
//   + sibling settings <button class="icon-btn" title="Cài đặt"> (must NEVER match)
//   + a page-content bell <a href="/app/notification-log"> outside the header (must NEVER match)
//   node ecentric_workspace/notification_center/tests/bell_click_check.js
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

function makeEnv(pathname){
  const head=new El('head'); const body=new El('body'); head.nodeType=body.nodeType='el';
  const byId={}; const docCaps=[]; const docBubs=[];
  const reg=c=>{ if(c.id)byId[c.id]=c; };
  const _h=head.appendChild.bind(head); head.appendChild=c=>{reg(c);return _h(c);};
  const _b=body.appendChild.bind(body); body.appendChild=c=>{reg(c);return _b(c);};
  const document={ nodeType:'doc', readyState:'complete', head, body,
    createElement:t=>new El(t), getElementById:id=>byId[id]||null,
    addEventListener:(t,fn,cap)=>{ if(t==='click'){ (cap?docCaps:docBubs).push(fn); } },
    querySelector:s=>body._find(s,false), querySelectorAll:s=>body._find(s,true),
    _docCaps:docCaps,_docBubs:docBubs };
  body.parentNode=document; head.parentNode=document;
  const observers=[];
  function MutationObserver(cb){ this.cb=cb; observers.push(this); }
  MutationObserver.prototype.observe=function(){ this.active=true; };
  MutationObserver.prototype.disconnect=function(){ this.active=false; };
  function DOMParser(){} DOMParser.prototype.parseFromString=function(str){ const b=new El('body'); b._tc=stripHtml(str); return {body:b}; };
  const calls=[]; let unread=3; let items=[];
  const win={ location:{pathname}, addEventListener:()=>{}, getComputedStyle:()=>({position:'relative'}),
    localStorage:{_s:{},getItem(k){return k in this._s?this._s[k]:null;},setItem(k,v){this._s[k]=String(v);}},
    frappe:{ call:o=>{ calls.push(o); const m=o.method||'';
      if(m.indexOf('get_unread_count')>=0&&o.callback)o.callback({message:{success:true,unread}});
      if(m.indexOf('get_notifications')>=0&&o.callback)o.callback({message:{success:true,unread,items}}); }},
    MutationObserver, DOMParser, AudioContext:null };
  win.window=win;
  return { document, win, body, calls, observers,
    setUnread:n=>{unread=n;}, setItems:a=>{items=a;}, fireObservers:()=>observers.forEach(o=>o.active&&o.cb([])),
    click:(target,init)=>{ init=init||{};
      const ev={type:'click',target,button:init.button||0,metaKey:!!init.metaKey,ctrlKey:!!init.ctrlKey,
        shiftKey:!!init.shiftKey,altKey:!!init.altKey,defaultPrevented:false,_stop:false,_imm:false,
        preventDefault(){this.defaultPrevented=true;},stopPropagation(){this._stop=true;},
        stopImmediatePropagation(){this._stop=true;this._imm=true;}};
      const pathArr=[]; let n=target; while(n){pathArr.push(n);n=n.parentNode;}
      for(const fn of docCaps.slice()){ fn(ev); if(ev._imm)return ev; } if(ev._stop)return ev;
      for(const node of pathArr){ if(node.getAttribute&&node.getAttribute('onclick')&&node._inlineHandler)node._inlineHandler(ev);
        if(ev._imm)return ev; for(const l of (node._l||[]).slice()){ if(l.t==='click'){ l.fn(ev); if(ev._imm)return ev; } }
        if(node.onclick)node.onclick(ev); if(ev._stop)return ev; if(node===document)break; }
      for(const fn of docBubs.slice()){ if(ev._stop)break; fn(ev); } return ev; } };
}
function run(env){ new Function('window','document','console',SRC)(env.win,env.document,console); }

// ---- build the two REAL shells + decoys ----
function makeBell(kind){
  const legacy={inline:0,prop:0,addEL:0,deleg:0}; let bell;
  if(kind==='button'){
    bell=new El('button'); bell.className='icon-btn'; bell.setAttribute('title','Thông báo');
    bell.setAttribute('onclick',"alert('x')"); bell._inlineHandler=()=>legacy.inline++;
    const svg=new El('svg'); svg.appendChild(new El('path')); bell.appendChild(svg);
  } else {
    bell=new El('a'); bell.className='icon-btn'; bell.setAttribute('href','/app/notification-log');
    const svg=new El('svg'); const use=new El('use'); use.setAttribute('href','#i-bell'); svg.appendChild(use); bell.appendChild(svg);
  }
  bell.onclick=()=>legacy.prop++; bell.addEventListener('click',()=>legacy.addEL++);
  const dot=new El('span'); dot.className='dot'; bell.appendChild(dot);
  return {bell,legacy};
}
function addShell(env,kind,opts){ opts=opts||{};
  let tb=env.body.querySelector('.topbar-actions');
  if(!tb){ tb=new El('div'); tb.className='topbar-actions'; const topbar=new El('div'); topbar.className='topbar'; topbar.appendChild(tb); env.body.appendChild(topbar); }
  const {bell,legacy}=makeBell(kind); tb.appendChild(bell);
  env.document.addEventListener('click',e=>{ let t=e.target; while(t){ if(t===bell){legacy.deleg++;break;} t=t.parentNode; } },false);
  const settings=new El('button'); settings.className='icon-btn'; settings.setAttribute('title','Cài đặt');
  let setFired=0; settings.setAttribute('onclick',"alert('s')"); settings._inlineHandler=()=>setFired++; tb.appendChild(settings);
  let pc=null;
  if(opts.pageDecoy){ const art=new El('article'); art.className='web-page-content'; env.body.appendChild(art);
    pc=new El('a'); pc.className='icon-btn'; pc.setAttribute('href','/app/notification-log');
    const svg=new El('svg'); const use=new El('use'); use.setAttribute('href','#i-bell'); svg.appendChild(use); pc.appendChild(svg); art.appendChild(pc); }
  return {bell,legacy,settings,getSetFired:()=>setFired,pageDecoy:pc};
}
function badgeCount(bell){ return bell.querySelectorAll('.ec-nc-badge').length; }
function popOpen(env){ const p=env.document.getElementById('ec-nc-pop-root'); return !!(p&&p.classList.contains('on')); }
function popCount(env){ return env.body.querySelectorAll('.ec-nc-pop').length; }
function capCount(env){ return env.document._docCaps.length; }
function legacySum(l){ return l.inline+l.prop+l.addEL+l.deleg; }

// ===== 1) /home anchor shell: matrix, plain open + no legacy, modifier native, decoys ignored =====
(function(){
  const env=makeEnv('/home'); const sh=addShell(env,'anchor',{pageDecoy:true}); run(env);
  ok(badgeCount(sh.bell)===1,'/home: one badge on the anchor bell');
  ok(popCount(env)===1 && capCount(env)===1,'/home: one dropdown + one capture listener');
  const badge=sh.bell.querySelector('.ec-nc-badge');
  env.setUnread(1); const e1=env.click(sh.bell,{button:0});
  ok(popOpen(env)&&badge.textContent==='1'&&!badge.classList.contains('ec-nc-badge--pill'),'/home: unread1 circle + opens');
  ok(legacySum(sh.legacy)===0 && e1.defaultPrevented,'/home: plain click no legacy + preventDefault'); env.click(env.body,{});
  env.setUnread(10); env.click(sh.bell,{button:0}); ok(badge.textContent==='9+'&&badge.classList.contains('ec-nc-badge--pill'),'/home: unread10 -> 9+ pill'); env.click(env.body,{});
  env.setUnread(0); env.click(sh.bell,{button:0}); ok(badge.classList.contains('on')===false,'/home: unread0 hidden'); env.click(env.body,{});
  const ec=env.click(sh.bell,{button:0,ctrlKey:true}); ok(!popOpen(env)&&ec.defaultPrevented===false,'/home: anchor Ctrl-click keeps native nav');
  const em=env.click(sh.bell,{button:1}); ok(!popOpen(env)&&em.defaultPrevented===false,'/home: anchor middle-click keeps native');
  // decoys
  const es=env.click(sh.settings,{button:0}); ok(!popOpen(env),'/home: settings button NOT matched (no dropdown)');
  const ep=env.click(sh.pageDecoy,{button:0}); ok(!popOpen(env)&&ep.defaultPrevented===false,'/home: page-content bell OUTSIDE header NOT matched');
})();

// ===== 2) /approval BUTTON shell, bell rendered AFTER init (the production bug) =====
(function(){
  const env=makeEnv('/approval'); run(env);                       // no bell yet
  ok(capCount(env)===1,'/approval: capture listener installed before bell exists');
  const sh=addShell(env,'button',{}); env.fireObservers();        // header renders later
  ok(badgeCount(sh.bell)===1,'/approval: badge mounted on dynamic BUTTON bell (observer + getNotificationBellTarget)');
  const e=env.click(sh.bell,{button:0});
  ok(popOpen(env)===true,'/approval: plain click OPENS dropdown on button bell');
  ok(legacySum(sh.legacy)===0,'/approval: NO legacy "tinh nang dang phat trien" handler fires');
  ok(e.defaultPrevented===true,'/approval: plain click preventDefault');
  // button modifier click: suppress legacy too (no native target), do not open
  env.click(env.body,{}); const ec=env.click(sh.bell,{button:0,ctrlKey:true});
  ok(!popOpen(env) && legacySum(sh.legacy)===0,'/approval: Ctrl-click on button suppresses legacy, no dropdown');
  // settings decoy never matches
  const es=env.click(sh.settings,{button:0}); ok(!popOpen(env)&&sh.getSetFired()>0,'/approval: settings button NOT matched (its own handler runs, no dropdown)');
})();

// ===== 3) header RERENDER after install (button shell), legacy attached AFTER =====
(function(){
  const env=makeEnv('/approval'); addShell(env,'button',{}); run(env);
  const oldTopbar=env.body.querySelector('.topbar'); if(oldTopbar) env.body.removeChild(oldTopbar);
  const sh=addShell(env,'button',{}); env.fireObservers();
  ok(badgeCount(sh.bell)===1,'rerender: one badge on new bell');
  ok(popCount(env)===1 && capCount(env)===1,'rerender: one dropdown + one capture listener');
  const e=env.click(sh.bell,{button:0});
  ok(popOpen(env)===true && legacySum(sh.legacy)===0,'rerender: plain click opens + legacy attached AFTER never fires');
})();

// ===== 4) reinstall -> no duplicates =====
(function(){
  const env=makeEnv('/overview'); const sh=addShell(env,'anchor',{}); run(env); run(env);
  ok(badgeCount(sh.bell)===1 && popCount(env)===1 && capCount(env)===1,'reinstall: one badge/dropdown/capture-listener');
})();

// ===== 5) Desk + public inert =====
(function(){ const env=makeEnv('/app/build'); const sh=addShell(env,'button',{}); run(env);
  ok(sh.bell.querySelector('.ec-nc-badge')===null && capCount(env)===0 && env.calls.length===0,'/app/*: fully inert'); })();
(function(){ const env=makeEnv('/login'); let threw=false; try{run(env);}catch(e){threw=true;} ok(!threw,'/login (no bell): no error'); })();

// ===== 6) notification HTML -> safe plain text =====
(function(){
  const env=makeEnv('/home'); const sh=addShell(env,'anchor',{});
  env.setItems([{name:'N1',subject:'<strong>Hi</strong> &amp; <div>there</div>',message:'<br><b>Body</b> <script>x()<\/script>',source_label:'<i>WR</i>',action_url:'/weekly-update?week=2026-W26',is_read:0,created_at:'2026-06-20 08:00:00'}]);
  env.setUnread(1); run(env); env.click(sh.bell,{button:0});
  const list=env.document.getElementById('ec-nc-pop-root').querySelector('#ec-nc-list');
  const item=list.children[0];
  const subj=item.querySelector('.ec-nc-subj').textContent;
  const msg=item.querySelector('.ec-nc-msg').textContent;
  ok(subj.indexOf('<')<0&&subj.indexOf('>')<0,'plaintext: subject no angle brackets');
  ok(subj==='Hi & there','plaintext: subject decoded+stripped (got: '+subj+')');
  ok(msg.indexOf('<')<0&&msg==='Body x()','plaintext: message stripped (got: '+msg+')');
  ok(item.getAttribute('href')==='/weekly-update?week=2026-W26','plaintext: href = server action_url');
})();

if(failures){ console.error('\n'+failures+' assertion(s) FAILED'); process.exit(1); }
console.log('\nAll runtime assertions passed.'); process.exit(0);
