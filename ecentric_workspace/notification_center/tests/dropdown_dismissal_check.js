// Runtime test: dropdown dismissal must survive scrollbar/scroll/wheel/inner clicks,
// and close only on a real outside pointer or Escape. Runs the REAL asset.
'use strict';
const fs=require('fs'); const path=require('path');
const SRC=fs.readFileSync(path.join(__dirname,'..','..','public','js','notification_center.js'),'utf8');
let fail=0; const ok=(c,m)=>{ if(!c){fail++;console.error('FAIL: '+m);} else console.log('ok  - '+m); };

function mkCL(){const s=new Set();return{add:(...c)=>c.forEach(x=>x&&s.add(x)),remove:(...c)=>c.forEach(x=>s.delete(x)),toggle:(c,o)=>{const v=o===undefined?!s.has(c):!!o;v?s.add(c):s.delete(c);return v;},contains:c=>s.has(c)};}
class El{constructor(t){this.tagName=(t||'div').toUpperCase();this.children=[];this.parentNode=null;this.attrs={};this.style={};this.classList=mkCL();this.id='';this._tc='';this._l=[];this.onclick=null;}
  set className(v){this._cn=v;String(v||'').split(/\s+/).filter(Boolean).forEach(c=>this.classList.add(c));} get className(){return this._cn||'';}
  setAttribute(k,v){this.attrs[k]=String(v);if(k==='id')this.id=String(v);} getAttribute(k){return this.attrs[k]===undefined?null:this.attrs[k];} removeAttribute(k){delete this.attrs[k];}
  set textContent(v){this._tc=String(v);this.children=[];} get textContent(){return this.children.length?this.children.map(c=>c.textContent).join(''):this._tc;}
  set innerHTML(v){this._html=v;this.children=[];const re=/id="([^"]+)"/g;let m;while((m=re.exec(v))){const e=new El('div');e.setAttribute('id',m[1]);this.appendChild(e);}}
  get innerHTML(){return this._html||'';} get firstChild(){return this.children[0]||null;}
  appendChild(c){c.parentNode=this;this.children.push(c);return c;} removeChild(c){const i=this.children.indexOf(c);if(i>=0)this.children.splice(i,1);c.parentNode=null;return c;}
  contains(n){if(n===this)return true;return this.children.some(c=>c.contains&&c.contains(n));}
  matchesSel(sel){ sel=sel.trim();
    if(sel.charAt(0)==='['){const m=/\[([\w-]+)="([^"]*)"\]/.exec(sel);return m?this.getAttribute(m[1])===m[2]:false;}
    if(sel.charAt(0)==='#')return this.id===sel.slice(1);
    if(sel.charAt(0)==='.')return this.classList.contains(sel.slice(1));
    return this.tagName.toLowerCase()===sel.toLowerCase(); }
  closest(sel){let n=this;while(n&&n.matchesSel){if(sel.split(',').some(s=>n.matchesSel(s)))return n;n=n.parentNode;}return null;}
  addEventListener(t,fn){this._l.push({t,fn});}
  getBoundingClientRect(){return{bottom:40,right:200,top:10,left:180};}
  querySelector(s){return this._find(s,false);} querySelectorAll(s){return this._find(s,true);}
  _find(s,all){const acc=[];const walk=n=>n.children.forEach(c=>{if(c.matchesSel&&c.matchesSel(s))acc.push(c);walk(c);});walk(this);return all?acc:(acc[0]||null);}
}
function makeEnv(){
  const head=new El('head'),body=new El('body');head.nodeType=body.nodeType='el';
  const byId={};const cap={},bub={};const reg=c=>{if(c.id)byId[c.id]=c;};
  const _b=body.appendChild.bind(body);body.appendChild=c=>{reg(c);return _b(c);};
  const _h=head.appendChild.bind(head);head.appendChild=c=>{reg(c);return _h(c);};
  let theBell=null;
  const document={nodeType:'doc',readyState:'complete',head,body,createElement:t=>new El(t),getElementById:id=>byId[id]||null,
    addEventListener:(t,fn,c)=>{(c?(cap[t]=cap[t]||[]):(bub[t]=bub[t]||[])).push(fn);},
    querySelector:s=>(/notification-bell/.test(s)||/notification-log/.test(s))?theBell:body._find(s,false),
    querySelectorAll:s=>body._find(s,true),_cap:cap,_bub:bub};
  body.parentNode=document;head.parentNode=document;
  const wl={};const observers=[];
  function MO(cb){this.cb=cb;observers.push(this);} MO.prototype.observe=function(){this.active=true;};MO.prototype.disconnect=function(){this.active=false;};
  function DP(){} DP.prototype.parseFromString=function(str){const b=new El('body');b._tc=String(str).replace(/<[^>]*>/g,'');return{body:b};};
  const win={location:{pathname:'/all-ticket'},innerWidth:1200,addEventListener:(t,fn)=>{(wl[t]=wl[t]||[]).push(fn);},
    getComputedStyle:()=>({position:'relative'}),localStorage:{_s:{},getItem(k){return k in this._s?this._s[k]:null;},setItem(k,v){this._s[k]=String(v);}},
    frappe:{call:o=>{if(o.callback)o.callback({message:{success:true,unread:5,items:[]}});}},MutationObserver:MO,DOMParser:DP,AudioContext:null};
  win.window=win;
  return {document,win,body,wl,
    setBell:b=>{theBell=b;},
    fire:(type,phaseList,ev)=>{ (phaseList||[]).slice().forEach(fn=>fn(ev)); },
    clickBell:(bell)=>{ const tgt=bell.querySelector('svg')||bell; const path=[]; let n=tgt; while(n){path.push(n);n=n.parentNode;}
      const ev={type:'click',target:tgt,button:0,metaKey:0,ctrlKey:0,shiftKey:0,altKey:0,defaultPrevented:false,composedPath:()=>path,preventDefault(){this.defaultPrevented=true;},stopPropagation(){},stopImmediatePropagation(){}};
      (cap.click||[]).slice().forEach(fn=>fn(ev)); return ev; },
    pointerDown:(tgt)=>{ const path=[];let n=tgt;while(n){path.push(n);n=n.parentNode;}
      const ev={type:'pointerdown',target:tgt,composedPath:()=>path}; (cap.pointerdown||[]).slice().forEach(fn=>fn(ev)); },
    scroll:()=>{ (wl.scroll||[]).slice().forEach(fn=>fn({type:'scroll'})); },
    wheel:()=>{ (wl.wheel||[]).slice().forEach(fn=>fn({type:'wheel'})); /* asset has none -> no close */ },
    keydown:(key)=>{ const ev={type:'keydown',key}; (bub.keydown||[]).slice().forEach(fn=>fn(ev)); },
    capCount:t=>(cap[t]||[]).length };
}
function run(env){ new Function('window','document','console',SRC)(env.win,env.document,console); }
function buildBell(env){ const tb=new El('div');tb.className='topbar-actions';env.body.appendChild(tb);
  const a=new El('a');a.className='icon-btn';a.setAttribute('href','/app/notification-log');a.setAttribute('data-ec-notification-bell','1');
  const svg=new El('svg');a.appendChild(svg);const dot=new El('span');dot.className='dot';a.appendChild(dot);tb.appendChild(a);env.setBell(a);return a; }
function popOpen(env){const p=env.document.getElementById('ec-nc-pop-root');return !!(p&&p.classList.contains('on'));}

const env=makeEnv(); const bell=buildBell(env); run(env);
ok(env.capCount('click')===1,'one document click-capture listener');
ok(env.capCount('pointerdown')===1,'one document pointerdown-capture (dismissal) listener');
const pop=env.document.getElementById('ec-nc-pop-root'); const list=pop&&pop.querySelector('#ec-nc-list');
ok(!!pop&&!!list,'dropdown + list built');

env.clickBell(bell); ok(popOpen(env),'plain click opens dropdown');
env.pointerDown(list); ok(popOpen(env),'pointerdown on inner scroll container -> stays open');
env.pointerDown(pop);  ok(popOpen(env),'pointerdown on dropdown body (scrollbar) -> stays open');
env.scroll();          ok(popOpen(env),'window scroll (inner-list scroll) -> stays open (re-anchor only)');
env.wheel();           ok(popOpen(env),'wheel -> stays open');
env.pointerDown(env.body); ok(!popOpen(env),'pointerdown OUTSIDE -> closes');
env.clickBell(bell); ok(popOpen(env),'reopen via bell');
env.keydown('Escape'); ok(!popOpen(env),'Escape -> closes');
env.clickBell(bell); ok(popOpen(env),'toggle: click bell opens');
env.clickBell(bell); ok(!popOpen(env),'toggle: click bell again closes');
// reinstall -> no duplicate listeners
run(env);
ok(env.capCount('click')===1 && env.capCount('pointerdown')===1,'reinstall: still single click + pointerdown listeners');

if(fail){console.error('\n'+fail+' FAILED');process.exit(1);} console.log('\nAll dismissal assertions passed.');process.exit(0);
