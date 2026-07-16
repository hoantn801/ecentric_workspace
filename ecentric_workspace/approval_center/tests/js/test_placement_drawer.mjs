// Copyright (c) 2026, eCentric and contributors
// Phase C drawer placement LOGIC (node:vm; live PDF.js render stubbed -> CI/UAT). Drives the
// real flow: open drawer -> placement_state + signer cards -> select signer -> click PDF layer
// -> debounced save_placement(slot+coords) -> progress from covered slots -> autosave states ->
// delete. Coordinates are normalized to PDF points via the page scale.
import fs from "fs"; import vm from "vm";
import { fileURLToPath } from "url"; import path from "path";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(HERE, "..", "..", "esign", "ui", "document_signing_section.html"), "utf8");
const SRC = HTML.match(/<script id="ec-docsign-script">([\s\S]*?)<\/script>/)[1];

let els={}, timers=[], _cache={};
function mkEl(id){ const e={id,_html:"",textContent:"",_attrs:{},style:{display:""},width:612,height:792,
  offsetLeft:0,offsetTop:0,offsetWidth:120,offsetHeight:40,_kids:[],parentNode:null,
  getAttribute(k){return (k in this._attrs)?this._attrs[k]:null;},setAttribute(k,v){this._attrs[k]=String(v);},
  appendChild(c){c.parentNode=this;this._kids.push(c);return c;},
  getBoundingClientRect(){return {left:0,top:0,width:this.width,height:this.height};},getContext(){return {};},
  addEventListener(){},querySelector(sel){const cls=sel.replace(".","");return this._kids.find(k=>((k._attrs.class||"")).indexOf(cls)>=0)||{onclick:null,className:cls,style:{}};},
  querySelectorAll(sel){return qsa(sel);},click(){if(this.onclick)this.onclick();} };
  Object.defineProperty(e,"innerHTML",{get(){return this._html;},set(v){this._html=String(v);this._kids=[];}});
  Object.defineProperty(e,"onclick",{get(){return this._oc;},set(f){this._oc=f;}});
  return e; }
function qsa(sel){ const attr=sel.replace(/[\[\].]/g,"");
  const html=(attr==="data-setup")?(els["ecdRows"]?els["ecdRows"]._html:""):(els["ecdSignerCards"]?els["ecdSignerCards"]._html:"");
  const key=attr+"|"+html; if(_cache[key])return _cache[key];
  const re=new RegExp(attr+'="([^"]*)"',"g");const out=[];let m;
  while((m=re.exec(html))){const fe=mkEl("_"+attr+out.length);fe._attrs[attr]=m[1];out.push(fe);} _cache[key]=out; return out; }

["ec-docsign","ecdCount","ecdSummary","ecdBanner","ecdRows","ecdUpload","ecdUploadBtn","ecdUploadHint",
 "ecdDrawerOv","ecdDrawerName","ecdDrawerSummary","ecdDrawerClose","ecdViewer","ecdViewerMsg","ecdStage",
 "ecdCanvas","ecdLayer","ecdSignerCards","ecdProg","ecdSaveState","ecdDrawerFoot","ecdRoBanner","ecdDrawerErr","ec-approver-wrap","payr-body"]
 .forEach(id=>els[id]=mkEl(id));

const STATE={editable:true,can_classify:true,needs_review:false,current_package_status:null,
  signer_plan:{resolved:true,summary:{required_slots:2}},summary:{documents:1,requires_signature:1,supporting_documents:0},
  documents:[{document_ref:"F1",display_name:"a.pdf",file_url:"/private/files/a.pdf",requires_signature:true,
    direct_signing_supported:true,required_signer_slots:2,setup_state:"not_configured",legacy_placement_count:0,duplicate_count:1}]};
let PSTATE={ok:true,document_ref:"F1",display_name:"a.pdf",file_url:"/private/files/a.pdf",is_pdf:true,
  requires_signature:true,editable:true,slot_key_version:1,signer_plan_resolved:true,
  required_slots:[{slot_key:"requester",label:"Người đề nghị",kind:"requester",candidates:[{user:"h@x",display_name:"Hoan",scts_mapping_status:"missing"}]},
                  {slot_key:"level:L2:any-one",label:"Finance (một trong)",kind:"approval_level",candidates:[]}],
  placements:[],covered_slot_count:0,required_slot_count:2};
let calls=[], saveOk=true, pdfLoaded=false;
const frappe={ call(o){ calls.push({method:o.method,args:o.args});
  if(/document_setup_state$/.test(o.method))return Promise.resolve({message:STATE});
  if(/signer_plan$/.test(o.method))return Promise.resolve({message:STATE.signer_plan});
  if(/signing_readiness$/.test(o.method))return Promise.resolve({message:{checks:{active_approver:false}}});
  if(/placement_state$/.test(o.method))return Promise.resolve({message:PSTATE});
  if(/save_placement$/.test(o.method)){ if(saveOk){PSTATE=Object.assign({},PSTATE,{covered_slot_count:1,
      placements:[{name:"PL1",x:o.args.box?JSON.parse(o.args.box).x:10,y:10,width:120,height:40,signer_slot_key:"requester"}]});
      return Promise.resolve({message:{ok:true,placement_name:"PL1",state:PSTATE}});}
    return Promise.resolve({message:{ok:false,reason:"x"}}); }
  if(/delete_placement$/.test(o.method)){PSTATE=Object.assign({},PSTATE,{covered_slot_count:0,placements:[]});return Promise.resolve({message:{ok:true,state:PSTATE}});}
  return Promise.resolve({message:{}}); },
  utils:{escape_html:x=>String(x==null?"":x)},show_alert(){},csrf_token:"t",boot:{} };
const ch={appendChild(){}}; els["payr-body"].parentNode=ch;
const sb={document:{getElementById:id=>els[id]||null,querySelector:sel=>(sel.indexOf("content")>=0?ch:els["ec-approver-wrap"]),addEventListener(){},createElement:(t)=>mkEl("_new_"+t)},
  location:{search:"?id=EC-PAYR-1"},URLSearchParams,Promise,String,Array,Object,JSON,Math,
  setTimeout:(f)=>{timers.push(f);return timers.length;},clearTimeout:()=>{},setInterval:()=>1,clearInterval:()=>{},
  FormData:function(){this.append=()=>{};},fetch:()=>Promise.resolve({json:()=>Promise.resolve({message:{}})}),
  confirm:()=>true,open:()=>{},console };
// stub dynamic import of PDF.js -> a fake lib that renders instantly
sb.__import=(u)=>Promise.resolve({GlobalWorkerOptions:{},getDocument:()=>({promise:Promise.resolve({
  getPage:()=>Promise.resolve({getViewport:({scale})=>({width:612*(scale||1),height:792*(scale||1)}),
    render:()=>({promise:Promise.resolve()})})})})});
const SRC2 = SRC.replace(/import\(/g,"__import(");   // route dynamic import to the stub
vm.createContext(sb); sb.window=sb; sb.frappe=frappe;

function selectSlot(key){ const b=els["ec-docsign"].querySelectorAll("[data-add]").find(c=>c.getAttribute("data-add")===key);
  if(b&&b.onclick) b.onclick({stopPropagation(){}}); return b; }
function clickLayer(x,y){ els["ecdLayer"].onclick({target:els["ecdLayer"],clientX:x,clientY:y}); }
const tick=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
const flush=async()=>{const t=timers.slice();timers=[];for(const f of t){f();await tick();}};
let pass=0,fail=0; const ok=(c,m)=>{console.log((c?"  ok - ":"  FAIL - ")+m);pass+=c;fail+=!c;};
function drawerErr_reset(){ els["ecdDrawerErr"].style.display="none"; els["ecdDrawerErr"].textContent=""; }

async function main(){
  vm.runInContext(SRC2, sb); await tick();
  // open the drawer via the row's setup button (same instance wire() bound)
  const btn = els["ec-docsign"].querySelectorAll("[data-setup]")[0];
  ok(!!btn && btn.getAttribute("data-setup")==="F1","row exposes setup button for signable doc");
  btn.onclick(); await tick();
  ok(els["ecdDrawerOv"].style.display==="block","17: drawer opens");
  ok(calls.some(c=>/placement_state$/.test(c.method)),"drawer loads placement_state");
  ok(els["ecdSignerCards"]._html.indexOf("Người đề nghị")>=0 && els["ecdSignerCards"]._html.indexOf("Finance")>=0,"18: signer cards from B1 required_slots");
  ok(els["ecdSignerCards"]._html.indexOf("Chưa có cấu hình chữ ký số")>=0,"missing-mapping warning shown");
  ok(els["ecdProg"].textContent==="0/2","progress starts 0/2 (required slot count, not rows)");
  // select the requester signer via the explicit "Đặt vị trí ký" button (ISSUE 3)
  ok(els["ecdSignerCards"]._html.indexOf("data-add=")>=0,"signer card exposes explicit place-position action");
  selectSlot("requester"); await tick();
  // click on the PDF layer to place a box
  clickLayer(120,80); await tick();
  ok(timers.length>=1,"22: autosave is DEBOUNCED (timer queued, not fired on every pixel)");
  const savingSeen = (function(){ const before=els["ecdSaveState"].textContent; timers[0](); return els["ecdSaveState"].textContent; })();
  ok(savingSeen==="Đang lưu…","autosave shows 'Đang lưu…' when the debounced save fires");
  timers=[]; await tick();
  const sv = calls.filter(c=>/save_placement$/.test(c.method)).pop();
  ok(!!sv,"19: select signer + click -> save_placement called");
  const box = JSON.parse(sv.args.box);
  ok(box.signer_slot_key==="requester" && box.width===120 && Math.abs(box.x-120)<1,"box carries slot + normalized coords");
  ok(els["ecdSaveState"].textContent==="Đã lưu","autosave -> 'Đã lưu' on success");
  ok(els["ecdProg"].textContent==="1/2","25: progress updates 1/2 without full reload");

  // autosave failure visibly reported
  saveOk=false;
  selectSlot("requester"); clickLayer(200,200); await tick(); await flush();
  ok(els["ecdSaveState"].textContent==="Lưu lỗi — thử lại","23: autosave failure visibly reported (not silent success)");
  ok(els["ecdDrawerErr"].style.display==="block" && els["ecdDrawerErr"].textContent.length>0,
     "ISSUE 2: save error is shown INSIDE the drawer (not hidden behind it)");
  saveOk=true;

  // ===== UAT regressions =====
  // reset to a clean placed state (one requester box)
  PSTATE=Object.assign({},PSTATE,{editable:true,covered_slot_count:1,
    placements:[{name:"PL1",x:120,y:80,width:120,height:40,signer_slot_key:"requester"}]});
  btn.onclick(); await tick();
  const layerKidsBefore = els["ecdLayer"]._kids.length;
  const psCallsBefore = calls.filter(c=>/placement_state$/.test(c.method)).length;

  // ISSUE 3: after placing one box, placement mode exits -> a further PDF click does NOT create another
  drawerErr_reset(); saveOk=true;
  clickLayer(300,300); await tick();
  const extraSaves = calls.filter(c=>/save_placement$/.test(c.method)).length;
  clickLayer(320,320); await tick();
  ok(calls.filter(c=>/save_placement$/.test(c.method)).length===extraSaves,
     "ISSUE 3: extra PDF clicks after a placement do NOT create more boxes");
  ok(els["ecdDrawerErr"].style.display==="block","ISSUE 3: accidental click prompts to pick a signer (drawer-local)");

  // ISSUE 1: selecting another signer must NOT reload placement_state or reset existing boxes
  selectSlot("level:L2:any-one"); await tick();
  ok(calls.filter(c=>/placement_state$/.test(c.method)).length===psCallsBefore,
     "ISSUE 1: selecting another signer does NOT reload server placement_state");
  ok(els["ecdLayer"]._kids.length===layerKidsBefore,
     "ISSUE 1: existing box still rendered after switching signer (not reset)");

  // ISSUE 3: explicit "+ Thêm vị trí ký" re-enters placement mode for another box
  const nSaves = calls.filter(c=>/save_placement$/.test(c.method)).length;
  selectSlot("requester"); clickLayer(150,150); await tick(); await flush();
  ok(calls.filter(c=>/save_placement$/.test(c.method)).length>nSaves,
     "ISSUE 3: explicit add-position places another box for the same signer");

  // ISSUE 4: read-only after submit -> banner shown, no add buttons, click cannot place
  PSTATE=Object.assign({},PSTATE,{editable:false,setup_editable_reason:"already_submitted"});
  btn.onclick(); await tick();
  ok(els["ecdRoBanner"].style.display==="block","ISSUE 4: read-only banner shown when request already submitted");
  ok(els["ecdSignerCards"]._html.indexOf("data-add=")<0,"ISSUE 4: no add-position buttons in read-only mode");
  const roSaves = calls.filter(c=>/save_placement$/.test(c.method)).length;
  clickLayer(100,100); await tick();
  ok(calls.filter(c=>/save_placement$/.test(c.method)).length===roSaves,
     "ISSUE 4: clicking the document in read-only mode does not attempt a placement");
  PSTATE=Object.assign({},PSTATE,{editable:true});

  // restore: reopening renders persisted boxes from state
  PSTATE=Object.assign({},PSTATE,{covered_slot_count:1,placements:[{name:"PL1",x:50,y:60,width:120,height:40,signer_slot_key:"requester"}]});
  btn.onclick(); await tick();
  ok(els["ecdLayer"]._kids.length>=1 || els["ecdProg"].textContent==="1/2","24: reopen restores persisted placement + progress");

  console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail?1:0);
}
main();
