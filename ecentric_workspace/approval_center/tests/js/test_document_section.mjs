// Copyright (c) 2026, eCentric and contributors
// Phase A2 (shell-reconciled + hardened) unified section behaviour - node:vm DOM stub.
// Verifies: renders A1 docs + B1 plan; classify string-boolean + confirm; drawer shell; native
// multi-upload; representative-pointer call after upload; server-state approver reveal
// (#ec-approver-wrap hidden for requester, revealed otherwise); unsaved-request UX; mounts into
// the business-content region (#payr-body parent) not the shell nav.
import fs from "fs"; import vm from "vm";
import { fileURLToPath } from "url"; import path from "path";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(HERE, "..", "..", "esign", "ui", "document_signing_section.html"), "utf8");
const SRC = HTML.match(/<script id="ec-docsign-script">([\s\S]*?)<\/script>/)[1];

let els = {};
function mkEl(id){ const el={id,_html:"",textContent:"",_attrs:{},_children:[],parentNode:null,
  style:{display:id==="ec-docsign"?"none":(id==="ec-approver-wrap"?"none":"")},disabled:false,checked:false,value:"",files:[],
  getAttribute(k){return (k in this._attrs)?this._attrs[k]:null;}, setAttribute(k,v){this._attrs[k]=String(v);},
  appendChild(c){c.parentNode=this;this._children.push(c);return c;}, click(){if(this.onclick)this.onclick();},
  querySelectorAll(sel){return qsa(this,sel);} };
  Object.defineProperty(el,"innerHTML",{get(){return this._html;},set(v){this._html=String(v);}});
  Object.defineProperty(el,"onclick",{get(){return this._oc;},set(f){this._oc=f;}});
  Object.defineProperty(el,"onchange",{get(){return this._ochg;},set(f){this._ochg=f;}});
  return el; }
const _cache={};
function qsa(el,sel){ const attr=sel.replace(/[\[\]]/g,""); const html=els["ecdRows"]?els["ecdRows"]._html:"";
  const key=attr+"|"+html; if(_cache[key])return _cache[key];
  const re=new RegExp(attr+'="([^"]*)"',"g"); const out=[]; let m;
  while((m=re.exec(html))){const fe=mkEl("_"+attr+"_"+out.length); fe._attrs[attr]=m[1]; out.push(fe);} _cache[key]=out; return out; }

const STATE_REQ={ editable:true, can_classify:true, needs_review:false, current_package_status:null,
  signer_plan:{resolved:true,slot_key_version:1,summary:{required_slots:5}},
  summary:{documents:2,requires_signature:1,supporting_documents:1},
  documents:[
    {document_ref:"a605",display_name:"De_nghi.pdf",file_url:"/private/files/a.pdf",duplicate_count:2,
     requires_signature:true,classification_source:"default",signature_file:null,direct_signing_supported:true,
     required_signer_slots:5,setup_state:"not_configured",legacy_placement_count:0},
    {document_ref:"bbb",display_name:"Hoa_don.png",file_url:"/private/files/b.png",duplicate_count:1,
     requires_signature:false,classification_source:"digital_signature_file",signature_file:"DSF1",
     direct_signing_supported:false,required_signer_slots:0,setup_state:"supporting_document",legacy_placement_count:0} ] };
const STATE_APPROVER=Object.assign({},STATE_REQ,{can_classify:false,editable:false});
const PLAN={resolved:true,slot_key_version:1,summary:{required_slots:5},
  slots:[{slot_key:"requester",kind:"requester",candidates:[{user:"hoan@x",display_name:"Hoan",scts_mapping_status:"verified"}]},
         {slot_key:"level:L2:any-one",kind:"approval_level",level_no:2,level_name:"Finance",approval_mode:"Any One",
          candidates:[{user:"lien@x",display_name:"Lien",scts_mapping_status:"missing"}]}]};

let calls=[],uploads=[];
function mk(opts){ opts=opts||{};
  els={}; ["ec-docsign","ecdCount","ecdSummary","ecdBanner","ecdRows","ecdUpload","ecdUploadBtn","ecdUploadHint",
    "ecdDrawerOv","ecdDrawerName","ecdDrawerSummary","ecdDrawerClose","ecdViewer","ecdSignerCards","ecdDrawerFoot",
    "ecdViewerMsg","ecdStage","ecdCanvas","ecdLayer","ecdProg","ecdSaveState",
    "ec-approver-wrap","payr-body"].forEach(id=>els[id]=mkEl(id));
  const contentHost=mkEl("content-host"); els["payr-body"].parentNode=contentHost; els["ec-docsign"].parentNode=mkEl("body");
  calls=[];uploads=[];
  const state=opts.state||STATE_REQ;
  const frappe={ call(o){ calls.push({method:o.method,args:o.args,type:o.type});
      if(/document_setup_state$/.test(o.method))return Promise.resolve({message:state});
      if(/signer_plan$/.test(o.method))return Promise.resolve({message:PLAN});
      if(/set_document_requires_signature$/.test(o.method))return Promise.resolve({message:opts.setResp||{ok:true}});
      if(/signing_readiness$/.test(o.method))return Promise.resolve({message:opts.readiness||{checks:{active_approver:false}}});
      if(/set_representative_attachment$/.test(o.method)){ if(opts.ptrThrow) return Promise.reject(new Error("x")); return Promise.resolve({message:opts.ptrResp||{ok:true,changed:true}}); }
      if(/placement_state$/.test(o.method))return Promise.resolve({message:{ok:true,is_pdf:false,file_url:"/x.pdf",required_slot_count:2,covered_slot_count:0,required_slots:[{slot_key:"requester",label:"Người đề nghị",candidates:[]},{slot_key:"L2",label:"Finance",candidates:[]}],placements:[]}});
      return Promise.resolve({message:{}}); },
    utils:{escape_html:x=>String(x==null?"":x)},show_alert(){},csrf_token:"t",boot:{} };
  const sb={ document:{ getElementById:id=>els[id]||null,
      querySelector:sel=>(sel.indexOf("content")>=0?contentHost:els["ec-approver-wrap"]) },
    location:{ search: opts.search!==undefined?opts.search:"?id=EC-PAYR-2026-00012" },
    URLSearchParams,Promise,String,Array,Object,setInterval:()=>1,clearInterval:()=>{},
    FormData:function(){this._d={};this.append=(k,v)=>{this._d[k]=v;};},
    fetch:(url,o)=>{uploads.push({url,o});return Promise.resolve({json:()=>Promise.resolve({message:{file_url:"/private/files/up.pdf"}})});},
    confirm:()=>true,open:()=>{},console };
  sb.__import=()=>Promise.resolve({GlobalWorkerOptions:{},getDocument:()=>({promise:Promise.resolve({getPage:()=>Promise.resolve({getViewport:({scale})=>({width:612*(scale||1),height:792*(scale||1)}),render:()=>({promise:Promise.resolve()})})})})});
  vm.createContext(sb); sb.window=sb; sb.frappe=frappe; sb.contentHost=contentHost;
  return {sb,els,contentHost}; }

const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
let pass=0,fail=0; const ok=(c,m)=>{console.log((c?"  ok - ":"  FAIL - ")+m);pass+=c;fail+=!c;};

async function main(){
  // A. requester + setup editable (can_classify true, active_approver false)
  let h=mk({readiness:{checks:{active_approver:false}}}); vm.runInContext(SRC.replace(/import\(/g,"__import("),h.sb); await tick();
  ok(h.els["ec-docsign"].parentNode===h.contentHost,"mounts into business-content region (#payr-body parent)");
  ok(h.els["ec-approver-wrap"].style.display==="none","A: requester setup -> unified visible, approver HIDDEN");
  ok(h.els["ecdCount"].textContent==="2 tài liệu","renders A1 docs");
  ok(h.els["ecdSummary"].textContent.indexOf("0/5")>=0,"honest 0/5 progress");
  ok(h.els["ecdRows"]._html.indexOf("Thiết lập chữ ký")>=0,"setup action for signable");

  // B. requester frozen but NOT current approver (can_classify false, active_approver false)
  h=mk({state:Object.assign({},STATE_APPROVER),readiness:{checks:{active_approver:false}}}); vm.runInContext(SRC.replace(/import\(/g,"__import("),h.sb); await tick();
  ok(h.els["ec-approver-wrap"].style.display==="none","B: frozen requester, not approver -> approver HIDDEN");

  // C. actual CURRENT approver (active_approver true)
  h=mk({state:Object.assign({},STATE_APPROVER),readiness:{checks:{active_approver:true}}}); vm.runInContext(SRC.replace(/import\(/g,"__import("),h.sb); await tick();
  ok(h.els["ec-approver-wrap"].style.display==="","C: active current approver -> approver REVEALED");

  // D. future/not-yet-current approver (active_approver false) -> hidden
  h=mk({state:Object.assign({},STATE_APPROVER),readiness:{checks:{active_approver:false}}}); vm.runInContext(SRC.replace(/import\(/g,"__import("),h.sb); await tick();
  ok(h.els["ec-approver-wrap"].style.display==="none","D: future approver (not current level) -> approver HIDDEN");

  // E. unrelated read-only user (active_approver false) -> hidden
  h=mk({state:{editable:false,can_classify:false,needs_review:false,summary:{documents:1,requires_signature:1,supporting_documents:0},documents:[],signer_plan:{resolved:true,summary:{required_slots:0}}},readiness:{checks:{active_approver:false}}}); vm.runInContext(SRC.replace(/import\(/g,"__import("),h.sb); await tick();
  ok(h.els["ec-approver-wrap"].style.display==="none","E: unrelated user -> approver HIDDEN");

  // F. default-hidden before/without a positive signal (no flash): wrapper stays none unless C
  h=mk({readiness:{checks:{}}}); vm.runInContext(SRC.replace(/import\(/g,"__import("),h.sb); await tick();
  ok(h.els["ec-approver-wrap"].style.display==="none","F: no active_approver signal -> stays hidden (no flash)");

  // classify string boolean + confirm retry
  h=mk({}); vm.runInContext(SRC.replace(/import\(/g,"__import("),h.sb); await tick();
  let seq=[{ok:false,confirmation_required:true,reason:"existing_placements"},{ok:true}],i=0;
  h.sb.frappe.call=(o)=>{calls.push({method:o.method,args:o.args});
    if(/document_setup_state$/.test(o.method))return Promise.resolve({message:STATE_REQ});
    if(/signer_plan$/.test(o.method))return Promise.resolve({message:PLAN});
    if(/set_document_requires_signature$/.test(o.method))return Promise.resolve({message:seq[i++]||{ok:true}});
    return Promise.resolve({message:{}});};
  const chk=h.els["ec-docsign"].querySelectorAll("[data-support]")[0]; chk.checked=true; chk.onchange(); await tick();
  const setC=calls.filter(c=>/set_document_requires_signature$/.test(c.method));
  ok(setC[0].args.requires_signature==="false","classify sends STRING boolean 'false'");
  ok(setC.length===2 && setC[1].args.confirm===1,"existing_placements -> confirm -> retry confirm=1");

  // drawer shell
  h=mk({}); vm.runInContext(SRC.replace(/import\(/g,"__import("),h.sb); await tick();
  h.els["ec-docsign"].querySelectorAll("[data-setup]")[0].onclick(); await tick();
  ok(h.els["ecdDrawerOv"].style.display==="block","drawer opens");
  ok(calls.some(c=>/placement_state$/.test(c.method)),"drawer loads placement_state (Phase C)");
  ok(h.els["ecdSignerCards"]._html.indexOf("Người đề nghị")>=0 && h.els["ecdSignerCards"]._html.indexOf("Finance")>=0,"signer cards from placement_state.required_slots");

  // native multi-upload + representative-pointer call
  h=mk({}); vm.runInContext(SRC.replace(/import\(/g,"__import("),h.sb); await tick();
  h.els["ecdUpload"].files=[{name:"x.pdf"},{name:"y.pdf"}];
  h.els["ecdUpload"].onchange({target:h.els["ecdUpload"]}); await tick();
  ok(uploads.length===2 && uploads.every(u=>u.url==="/api/method/upload_file"),"multi-upload POSTs each file");
  ok(calls.some(c=>/set_representative_attachment$/.test(c.method)),"representative-pointer set after upload");

  // pointer-failure semantics: File uploaded ok, pointer update fails -> warn + reload; no data loss
  h=mk({ptrResp:{ok:false,reason:"not_attached"}}); vm.runInContext(SRC.replace(/import\(/g,"__import("),h.sb); await tick();
  const stateCallsBefore = calls.filter(c=>/document_setup_state$/.test(c.method)).length;
  h.els["ecdUpload"].files=[{name:"p.pdf"}]; h.els["ecdUpload"].onchange({target:h.els["ecdUpload"]}); await tick();
  ok(uploads.length>=1,"pointer-fail: native upload still POSTed (File created)");
  ok(calls.some(c=>/set_representative_attachment$/.test(c.method)),"pointer-fail: pointer attempted");
  ok(calls.filter(c=>/document_setup_state$/.test(c.method)).length>stateCallsBefore,"pointer-fail: state RELOADED (A1 still shows the File; no delete)");

  // UNSAVED request: isolated clean sandbox (no cross-test state) -> disabled + message + no POST
  (function(){
    const e={}; ["ec-docsign","ecdCount","ecdSummary","ecdBanner","ecdRows","ecdUpload","ecdUploadBtn",
      "ecdUploadHint","ecdDrawerOv","ecdDrawerName","ecdDrawerSummary","ecdDrawerClose","ecdViewer",
      "ecdSignerCards","ecdDrawerFoot","ec-approver-wrap","payr-body"].forEach(id=>{
        e[id]={id,_html:"",textContent:"",_attrs:{},style:{display:""},disabled:false,files:[],parentNode:null,
          getAttribute(k){return (k in this._attrs)?this._attrs[k]:null;},setAttribute(k,v){this._attrs[k]=String(v);},
          appendChild(c){c.parentNode=this;},querySelectorAll(){return [];}};
        Object.defineProperty(e[id],"innerHTML",{get(){return this._html;},set(v){this._html=String(v);}});
        Object.defineProperty(e[id],"onchange",{get(){return this._c;},set(f){this._c=f;}});
        Object.defineProperty(e[id],"onclick",{get(){return this._k;},set(f){this._k=f;}}); });
    const ch={appendChild(){}}; e["payr-body"].parentNode=ch;
    let posted=0;
    const sbx={document:{getElementById:id=>e[id]||null,querySelector:()=>ch},location:{search:""},
      URLSearchParams,Promise,String,Array,Object,setInterval:()=>1,clearInterval:()=>{},
      FormData:function(){this.append=()=>{};},fetch:()=>{posted++;return Promise.resolve({json:()=>Promise.resolve({message:{}})});},
      confirm:()=>true,open:()=>{},console};
    vm.createContext(sbx); sbx.window=sbx; sbx.frappe={call:()=>Promise.resolve({message:{}}),utils:{escape_html:x=>x},show_alert(){},csrf_token:"t",boot:{}};
    vm.runInContext(SRC.replace(/import\(/g,"__import("),sbx);
    ok(e["ec-docsign"].style.display==="block","unsaved: section shown");
    ok(e["ecdBanner"]._html.indexOf("Vui lòng lưu nháp yêu cầu")>=0,"unsaved: shows save-first message");
    ok(e["ecdUploadBtn"].disabled===true,"unsaved: upload disabled");
    e["ecdUpload"].files=[{name:"z.pdf"}]; if(e["ecdUpload"].onchange) e["ecdUpload"].onchange({target:e["ecdUpload"]});
    ok(posted===0,"unsaved: upload handler cannot POST (no fake attached_to_name)");
  })();

  console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail?1:0);
}
main();
