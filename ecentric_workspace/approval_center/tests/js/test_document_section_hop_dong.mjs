// Copyright (c) 2026, eCentric and contributors
// PR-E (23/11/2026): khoi "Tai lieu & ky so" DUNG CHUNG - che do Hop dong (#ctr-esign-slot) va
// che do DNTT (khong slot) chay THAT ma nguon trong node:vm voi DOM gia.
//   A. DNTT: goi API bang payment_request_name nhu cu, khong co business_*.
//   B. Hop dong: doc bang fetch GET (khong frappe.call), tham so business_doctype/business_name,
//      khoi gan VAO slot + class ecd-ctr, KHONG co nut Go, VAN co o "Bo chung tu".
//   C. Hop dong chua co ho so ky ("chua duoc cau hinh ky so") -> khoi AN, khong bang loi.
//   D. Trang Hop dong KHONG co slot (danh sach / tao moi, URL ?id=CTR-1) -> khong goi gi.
//   E. ctr:detail-rendered: slot moi -> gan lai khoi + tai lai.
//   F. Hop dong: phan loai "Bo chung tu" gui business_doctype/business_name.
//   G. quy trinh "khong_ky_cong" -> khoi an.
//   H. QC 23/11: ho so ky dang tat (esign_enabled=false) -> khoi an im lang.
//   I. QC 23/11: target() null o trang Hop dong khong slot -> mo drawer / luu o ky khong goi API.
//   J. QC vong 2: chua cau hinh -> DUNG o 1 GET; ve lai trang (phieu khac) -> 0 GET.
//   K. QC vong 2: esign_enabled=false -> chi 1 GET (khong hoi signer_plan / readiness).
//   L. QC vong 2: hidden_documents>0 -> dong bao so tep an; DNTT (0) -> khong bao.
//   M. QC vong 2: loi quyen (403) -> cau "khong co quyen", khong phai "loi he thong".
import fs from "fs"; import vm from "vm";
import { fileURLToPath } from "url"; import path from "path";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(HERE, "..", "..", "..", "platform", "esign", "ui", "document_signing_section.html"), "utf8");
const SRC = HTML.match(/<script id="ec-docsign-script">([\s\S]*?)<\/script>/)[1];

let els = {};
function mkEl(id){ const el={id,_html:"",textContent:"",_attrs:{},_children:[],parentNode:null,
  _cls:new Set(),
  style:{display:id==="ec-docsign"?"none":""},disabled:false,checked:false,value:"",files:[],
  getAttribute(k){return (k in this._attrs)?this._attrs[k]:null;}, setAttribute(k,v){this._attrs[k]=String(v);},
  appendChild(c){c.parentNode=this;this._children.push(c);return c;}, click(){if(this.onclick)this.onclick();},
  insertBefore(c){c.parentNode=this;this._children.unshift(c);return c;}, firstChild:null,
  querySelectorAll(sel){return qsa(this,sel);} };
  el.classList={add:(c)=>el._cls.add(c),remove:(c)=>el._cls.delete(c),contains:(c)=>el._cls.has(c)};
  Object.defineProperty(el,"innerHTML",{get(){return this._html;},set(v){this._html=String(v);}});
  return el; }
const _cache={};
function qsa(el,sel){ const attr=sel.replace(/[\[\]]/g,""); const html=els["ecdRows"]?els["ecdRows"]._html:"";
  const key=attr+"|"+html; if(_cache[key])return _cache[key];   // cung phan tu giua wire() va test
  const re=new RegExp(attr+'="([^"]*)"',"g"); const out=[]; let m;
  while((m=re.exec(html))){const fe=mkEl("_"+attr+"_"+out.length); fe._attrs[attr]=m[1]; out.push(fe);} _cache[key]=out; return out; }

const STATE={ editable:true, can_classify:true, needs_review:false, current_package_status:null,
  signer_plan:{resolved:true,slot_key_version:1,summary:{required_slots:2}},
  summary:{documents:2,requires_signature:1,supporting_documents:1},
  documents:[
    {document_ref:"f1",display_name:"HD_ky.pdf",file_url:"/private/files/hd.pdf",duplicate_count:1,
     requires_signature:true,classification_source:"default",signature_file:null,direct_signing_supported:true,
     required_signer_slots:2,setup_state:"not_configured",legacy_placement_count:0},
    {document_ref:"f2",display_name:"CCCD.png",file_url:"/private/files/c.png",duplicate_count:1,
     requires_signature:false,classification_source:"digital_signature_file",signature_file:"DSF1",
     direct_signing_supported:false,required_signer_slots:0,setup_state:"supporting_document",legacy_placement_count:0} ] };
const PLAN={resolved:true,slot_key_version:1,summary:{required_slots:2},slots:[]};

function mk(opts){ opts=opts||{};
  els={}; ["ec-docsign","ecdCount","ecdSummary","ecdBanner","ecdRows","ecdUpload","ecdUploadBtn","ecdUploadHint",
    "ecdDrawerOv","ecdDrawerName","ecdDrawerSummary","ecdDrawerClose","ecdViewer","ecdSignerCards",
    "ecdViewerMsg","ecdStage","ecdCanvas","ecdLayer","ecdProg","ecdSaveState","ecdRoBanner","ecdDrawerErr",
    "ecdPlaceHint","ecdTrySign"].forEach(id=>els[id]=mkEl(id));
  if(opts.pr){ els["ec-payr-root"]=mkEl("ec-payr-root"); els["payr-body"]=mkEl("payr-body");
    els["payr-body"].parentNode=mkEl("content-host"); }
  if(opts.ctr){ els["ec-ctr-root"]=mkEl("ec-ctr-root"); }
  if(opts.slot){ const s=mkEl("ctr-esign-slot"); s._attrs["data-business-doctype"]="EC Contract Review Request";
    s._attrs["data-business-name"]=opts.slot; els["ctr-esign-slot"]=s; }
  els["ec-docsign"].parentNode=mkEl("body");
  const calls=[], fetches=[], handlers={};
  const frappe={ call(o){ calls.push({method:o.method,args:o.args,type:o.type});
      if(/document_setup_state$/.test(o.method))return Promise.resolve({message:STATE});
      if(/signer_plan$/.test(o.method))return Promise.resolve({message:PLAN});
      if(/signing_readiness$/.test(o.method))return Promise.resolve({message:{checks:{}}});
      return Promise.resolve({message:{ok:true}}); },
    utils:{escape_html:x=>String(x==null?"":x)},show_alert(){},csrf_token:"t",boot:{} };
  const sb={ document:{ getElementById:id=>els[id]||null,
      querySelector:sel=>(els["payr-body"]?els["payr-body"].parentNode:null),
      addEventListener(ev,f){ (handlers[ev]=handlers[ev]||[]).push(f); },
      createElement:t=>mkEl("_new_"+t), documentElement:{classList:{add(){},remove(){},contains(){return false;}}} },
    location:{ search: opts.search!==undefined?opts.search:"?id=EC-PAYR-2026-00012" },
    URLSearchParams,Promise,String,Array,Object,JSON,encodeURIComponent,
    setInterval:()=>1,clearInterval:()=>{},
    fetch:(url,o)=>{ fetches.push({url,o});
      if(opts.forbidden) return Promise.resolve({ok:false,status:403,json:()=>Promise.resolve(
        {exc_type:"PermissionError",_server_messages:JSON.stringify([JSON.stringify({message:"Không được phép"})])})});
      if(opts.notConfigured) return Promise.resolve({ok:false,status:417,json:()=>Promise.resolve(
        {exc_type:"ValidationError",_server_messages:JSON.stringify([JSON.stringify({message:"Loại chứng từ này chưa được cấu hình ký số."})])})});
      let msg={};
      if(/document_setup_state/.test(url)) msg=opts.state||STATE; else if(/signer_plan/.test(url)) msg=PLAN;
      else if(/signing_readiness/.test(url)) msg={checks:{}};
      return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve({message:msg})}); },
    confirm:()=>true,open:()=>{},console,
    CustomEvent:function(t,o){this.type=t;this.detail=(o||{}).detail;}, addEventListener(){}, dispatchEvent(){} };
  vm.createContext(sb); sb.window=sb; sb.frappe=frappe;
  vm.runInContext(SRC.replace(/import\(/g,"__import("), sb);
  return {sb,els,calls,fetches,handlers}; }

const tick=async()=>{for(let i=0;i<32;i++)await Promise.resolve();};
let pass=0,fail=0; const ok=(c,m)=>{console.log((c?"  ok - ":"  FAIL - ")+m);pass+=c;fail+=!c;};

async function main(){
  // A. DNTT
  let h=mk({pr:true}); await tick();
  const reads=h.calls.filter(c=>/document_setup_state$|signer_plan$|signing_readiness$/.test(c.method));
  ok(reads.length===3 && reads.every(c=>c.args.payment_request_name==="EC-PAYR-2026-00012"),
     "A: DNTT doc 3 lenh bang payment_request_name");
  ok(reads.every(c=>!("business_doctype" in c.args) && !("business_name" in c.args)),"A: DNTT khong gui business_*");
  ok(h.fetches.length===0,"A: DNTT khong dung fetch de doc");
  ok(h.els["ec-docsign"].parentNode===h.els["payr-body"].parentNode,"A: DNTT gan vao vung noi dung (#payr-body parent)");
  ok(!h.els["ec-docsign"].classList.contains("ecd-ctr"),"A: DNTT khong co class ecd-ctr");
  ok(h.els["ecdRows"]._html.indexOf('data-remove="')>=0,"A: DNTT dang lap phieu van co nut Go");

  // B. Hop dong co slot
  h=mk({ctr:true,slot:"CTR-0001",search:"?id=CTR-0001"}); await tick();
  ok(h.calls.filter(c=>/document_setup_state$|signer_plan$|signing_readiness$/.test(c.method)).length===0,
     "B: Hop dong KHONG doc qua frappe.call (khong bat hop thoai loi)");
  ok(h.fetches.length===3 && h.fetches.every(f=>f.url.indexOf("business_doctype=EC%20Contract%20Review%20Request")>=0
       && f.url.indexOf("business_name=CTR-0001")>=0 && f.url.indexOf("payment_request_name")<0),
     "B: Hop dong doc bang business_doctype/business_name");
  ok(h.els["ec-docsign"].parentNode===h.els["ctr-esign-slot"],"B: khoi gan VAO #ctr-esign-slot");
  ok(h.els["ec-docsign"].classList.contains("ecd-ctr"),"B: class ecd-ctr (CSS an o tai tep)");
  ok(h.els["ec-docsign"].style.display==="block","B: khoi hien");
  ok(h.els["ecdRows"]._html.indexOf('data-remove="')<0,"B: Hop dong KHONG co nut Go");
  ok(h.els["ecdRows"]._html.indexOf('data-support="')>=0,"B: Hop dong VAN co o Bo chung tu");
  ok(/\.ec-docsign\.ecd-ctr \.ecd-up\{display:none\}/.test(HTML),"B: CSS an be mat tai tep o che do Hop dong");

  // C. chua cau hinh ky so
  h=mk({ctr:true,slot:"CTR-0002",notConfigured:true}); await tick();
  ok(h.els["ec-docsign"].style.display==="none","C: chua co ho so ky -> khoi an");
  ok(!h.els["ec-docsign"]._children.some(c=>c.id==="ecdLoadErr"),"C: khong chen bang loi");

  // D. trang Hop dong khong slot
  h=mk({ctr:true,search:"?id=CTR-0003"}); await tick();
  ok(h.calls.length===0 && h.fetches.length===0,"D: Hop dong khong slot -> khong goi API (khong roi ve DNTT)");
  ok(h.els["ec-docsign"].style.display==="none","D: khoi an");

  // E. ctr:detail-rendered -> slot moi
  h=mk({ctr:true,search:"?id=CTR-0004"}); await tick();
  const s=mkEl("ctr-esign-slot"); s._attrs["data-business-doctype"]="EC Contract Review Request";
  s._attrs["data-business-name"]="CTR-0004"; els["ctr-esign-slot"]=s;
  (h.handlers["ctr:detail-rendered"]||[]).forEach(f=>f({detail:{business_doctype:"EC Contract Review Request",
    business_name:"CTR-0004",approval_status:"Draft",esign_flow:"kol_wf09"}}));
  await tick();
  ok((h.handlers["ctr:detail-rendered"]||[]).length===1,"E: nghe ctr:detail-rendered tren document");
  ok(h.els["ec-docsign"].parentNode===s && h.fetches.length===3,"E: su kien -> gan vao slot + tai");
  const s2=mkEl("ctr-esign-slot"); s2._attrs=Object.assign({},s._attrs); els["ctr-esign-slot"]=s2;
  (h.handlers["ctr:detail-rendered"]||[]).forEach(f=>f({detail:{business_doctype:"EC Contract Review Request",
    business_name:"CTR-0004",approval_status:"Pending",esign_flow:"kol_wf09"}}));
  ok(h.els["ec-docsign"].parentNode===s2,"E: ve lai the chi tiet (slot moi) -> gan lai NGAY, khong cho mang");
  await tick();

  // F. phan loai o che do Hop dong
  h=mk({ctr:true,slot:"CTR-0005"}); await tick();
  const chk=h.els["ec-docsign"].querySelectorAll("[data-support]")[0]; chk.checked=true; chk.onchange(); await tick();
  const setC=h.calls.filter(c=>/set_document_requires_signature$/.test(c.method));
  ok(setC.length===1 && setC[0].args.business_name==="CTR-0005" && !("payment_request_name" in setC[0].args),
     "F: phan loai gui business_* (khong payment_request_name)");

  // G. khong ky tren cong
  h=mk({ctr:true,search:"?id=CTR-0006"}); await tick();
  const s3=mkEl("ctr-esign-slot"); s3._attrs["data-business-doctype"]="EC Contract Review Request";
  s3._attrs["data-business-name"]="CTR-0006"; els["ctr-esign-slot"]=s3;
  (h.handlers["ctr:detail-rendered"]||[]).forEach(f=>f({detail:{business_doctype:"EC Contract Review Request",
    business_name:"CTR-0006",approval_status:"Draft",esign_flow:"khong_ky_cong"}}));
  await tick();
  ok(h.fetches.length===0 && h.els["ec-docsign"].style.display==="none","G: khong_ky_cong -> khong tai, khoi an");

  // H. ho so ky dang tat
  h=mk({ctr:true,slot:"CTR-0007",state:Object.assign({},STATE,{esign_enabled:false})}); await tick();
  ok(h.els["ec-docsign"].style.display==="none","H: esign_enabled=false -> khoi an");
  ok(!h.els["ec-docsign"]._children.some(c=>c.id==="ecdLoadErr"),"H: khong bang loi");
  h=mk({ctr:true,slot:"CTR-0008",state:Object.assign({},STATE,{esign_enabled:true})}); await tick();
  ok(h.els["ec-docsign"].style.display==="block","H: esign_enabled=true -> khoi hien");

  // I. khong slot: target() null -> khong goi gi khi bam (vd nut con sot lai)
  h=mk({ctr:true,slot:"CTR-0009"}); await tick();
  delete els["ctr-esign-slot"];                               // roi trang chi tiet (danh sach)
  const b0=h.calls.length, f0=h.fetches.length;
  const chk2=h.els["ec-docsign"].querySelectorAll("[data-support]")[0]; chk2.checked=true; chk2.onchange(); await tick();
  ok(h.calls.length===b0 && h.fetches.length===f0,"I: khong slot -> phan loai KHONG goi API (khong roi ve payment_request_name)");
  ok(!h.calls.some(c=>c.args && c.args.payment_request_name),"I: khong lenh nao mang payment_request_name");

  // J. chua cau hinh: 1 GET, roi khong goi lai
  h=mk({ctr:true,slot:"CTR-0010",notConfigured:true}); await tick();
  ok(h.fetches.length===1,"J: chua cau hinh -> dung o 1 GET (khong 3)");
  const s4=mkEl("ctr-esign-slot"); s4._attrs["data-business-doctype"]="EC Contract Review Request";
  s4._attrs["data-business-name"]="CTR-0011"; els["ctr-esign-slot"]=s4;
  (h.handlers["ctr:detail-rendered"]||[]).forEach(f=>f({detail:{business_doctype:"EC Contract Review Request",
    business_name:"CTR-0011",approval_status:"Draft",esign_flow:"kol_wf09"}}));
  await tick();
  ok(h.fetches.length===1 && h.els["ec-docsign"].style.display==="none","J: phieu khac -> khong GET them, khoi van an");

  // K. ho so tat -> 1 GET
  h=mk({ctr:true,slot:"CTR-0012",state:Object.assign({},STATE,{esign_enabled:false})}); await tick();
  ok(h.fetches.length===1 && /document_setup_state/.test(h.fetches[0].url),"K: esign_enabled=false -> chi 1 GET");

  // L. tep an
  h=mk({ctr:true,slot:"CTR-0013",state:Object.assign({},STATE,{esign_enabled:true,hidden_documents:2})}); await tick();
  ok(h.els["ecdBanner"].innerHTML.indexOf("Có 2 tệp bạn không có quyền xem chi tiết.")>=0,"L: bao so tep an");
  h=mk({pr:true}); await tick();
  ok(h.els["ecdBanner"].innerHTML.indexOf("không có quyền xem chi tiết")<0,"L: DNTT (hidden 0) -> khong bao");

  // M. loi quyen
  h=mk({ctr:true,slot:"CTR-0014",forbidden:true}); await tick();
  const le=h.els["ec-docsign"]._children.find(c=>c.id==="ecdLoadErr");
  ok(!!le && le.textContent.indexOf("Bạn không có quyền xem phần Tài liệu & ký số")===0
     && le.textContent.indexOf("lỗi hệ thống")<0,"M: 403 -> cau khong co quyen");

  console.log(`\n${pass} dat, ${fail} hong`); process.exit(fail?1:0);
}
main().catch(e=>{console.error(e);process.exit(1);});
