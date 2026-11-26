/* PO 26/11/2026: nut "Mo online (Word)" tren khoi hop dong KOL (/approvals/contract-review), jsdom:
 *   NODE_PATH=... node ecentric_workspace/approval_center/tests/test_contract_review_kol_online.js <repo>
 * Khoa: nut CHI hien theo co server `can_open_online` (nguoi duyet / CC / nguoi theo doi khong thay);
 * bam -> POST kol_open_online {name} -> window.open(url,"_blank","noopener"); dang mo thi khoa nut
 * (bam 2 lan chi 1 request); loi (chua co ban online / khong co quyen) hien toast, nut mo lai.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const html=fs.readFileSync(path.join(REPO,"ecentric_workspace/approval_center/features/contract_review/ui/main_section.html"),"utf8");
const KOL="KOL/KOC / Creator (EC)";
const boot={tabs:{},context:{user:"vy@e.c",employee_name:"Vy",department:"E-commerce - EC"},
  form_options:{brands:[],departments:[],contract_types:[KOL],request_kinds:["New"],
    request_types:["Template from EC / Mẫu theo khung EC"],kol_service_types:[],kol_platforms:[],kol_payment_schedules:[],kol_advance_percents:[]}};
const MISSING="Hợp đồng chưa có bản online — Kế toán / IT đang cấu hình; tạm thời dùng Tải về.";
function detailFor(kol){ return {business:{name:"EC-CTR-2026-00200",contract_type:KOL,request_type:"Template from EC / Mẫu theo khung EC",request_kind:"New",
    creator_name:"A",contract_no:"X/HDDV",contract_file:kol.can_download_full?"/private/files/HDDV.docx":null,has_contract_file:true,signing_status:"Chưa ký"},
  approval:{approval_status:"Pending"},capabilities:{},levels:[],approvers:[],timeline:[],attachments:[],
  extra:{kol:Object.assign({can_manage:false,can_ai:false,approved:false,signed:false,acceptances:[],calc:[],funding:{}},kol)}}; }
function make(det,onOpen){
  const calls=[], opened=[];
  const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://x/approvals/contract-review?id=EC-CTR-2026-00200"});
  const w=dom.window;
  w.open=function(u,t,f){ opened.push([u,t,f]); return null; };
  w.frappe={csrf_token:"t",call:function(o){ const m=o.method.split(".").pop(); calls.push({m:m,args:o.args||{},type:o.type});
    if(m==="get_bootstrap") return Promise.resolve({message:boot});
    if(m==="kol_me") return Promise.resolve({message:{is_finance:false}});
    if(m==="get_detail") return Promise.resolve({message:det});
    if(m==="kol_open_online") return onOpen(o);
    return Promise.resolve({message:{}}); }};
  return {w:w,calls:calls,opened:opened};
}
const c={}; let failed=0;
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
function done(){ Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k)); console.log(failed?"SOME_FAIL":"ALL_PASS"); process.exit(failed?1:0); }
function wait(cond,cb,n){ n=n||0; if(cond()||n>120) return cb(); setTimeout(function(){ wait(cond,cb,n+1); },25); }
function body(w){ return (w.document.getElementById("ctr-body")||{}).innerHTML||""; }
function btn(w){ return w.document.querySelector('[data-kol="online"]'); }

// 1. Co server tat: nguoi duyet (Truong phong / CEO), CC, nguoi theo doi -> khong co nut; nguoi duoc ban du
// nhung chua co ban SharePoint -> chi co Tai ve.
function partFlags(next){
  const K=make(detailFor({can_download_full:false,can_preview:true,can_open_online:false}),()=>Promise.reject({}));
  wait(()=>/kol-detail/.test(body(K.w)),function(){
    chk("nguoi duyet / CC: khong co nut Mo online, van co ban che", !btn(K.w)&&/data-kol="preview"/.test(body(K.w)));
    const Kw=K.w.ContractReviewKOL;
    chk("co can_download_full nhung server chua co ban SP: khong co nut, van co Tai ve",
      !/data-kol="online"/.test(Kw.detailHTML(detailFor({can_download_full:true,can_open_online:false})))&&/data-kol="dl"/.test(Kw.detailHTML(detailFor({can_download_full:true,can_open_online:false}))));
    chk("co can_open_online: co nut 'Mo online (Word)' canh Tai ve", /data-kol="online"[^>]*>Mở online \(Word\)</.test(Kw.detailHTML(detailFor({can_download_full:true,can_open_online:true})))&&/data-kol="dl"/.test(Kw.detailHTML(detailFor({can_download_full:true,can_open_online:true}))));
    { const d=detailFor({can_download_full:true,can_open_online:true}); d.extra.kol.calc=[{label:"Thực nhận",how:"",amount:9000000,kind:"base"},{label:"Tổng",how:"",amount:10000000,kind:"total"}];
      chk("co bang tinh: nut Mo online nam o hang cuoi bang tinh cung nut tai", /kol-rc-foot[\s\S]*data-kol="online"/.test(Kw.detailHTML(d))); }
    chk("khong dung emoji tren nut", !/[\u{1F300}-\u{1FAFF}☀-➿]/u.test(Kw.detailHTML(detailFor({can_download_full:true,can_open_online:true})).match(/<button[^>]*data-kol="online"[^>]*>[^<]*<\/button>/)[0]));
    next();
  });
}

// 2. Bam: POST dung endpoint, khoa nut khi dang mo (bam 2 lan = 1 request), mo tab moi noopener.
function partClick(next){
  let resolve; const K=make(detailFor({can_download_full:true,can_open_online:true}),()=>new Promise(r=>{ resolve=r; }));
  wait(()=>btn(K.w),function(){
    const b=btn(K.w); b.click(); b.click();
    setTimeout(function(){
      const oc=K.calls.filter(x=>x.m==="kol_open_online");
      chk("bam: goi kol_open_online dung 1 lan (chong bam 2 lan)", oc.length===1);
      chk("bam: gui POST, chi {name}", oc[0]&&oc[0].type==="POST"&&JSON.stringify(oc[0].args)==='{"name":"EC-CTR-2026-00200"}');
      chk("dang mo: nut khoa + chu 'Dang mo'", b.disabled&&/Đang mở/.test(b.textContent));
      resolve({message:{url:"https://sp/share/abc"}});
      setTimeout(function(){
        chk("xong: window.open(url,'_blank','noopener')", K.opened.length===1&&K.opened[0][0]==="https://sp/share/abc"&&K.opened[0][1]==="_blank"&&K.opened[0][2]==="noopener");
        chk("xong: nut mo lai, chu tra ve", !b.disabled&&/Mở online \(Word\)/.test(b.textContent));
        next();
      },60);
    },60);
  });
}

// 3. Loi: chua co ban online / khong co quyen -> toast loi ro, nut mo lai, khong mo tab.
function partError(next){
  const K=make(detailFor({can_download_full:true,can_open_online:true}),()=>Promise.reject({message:MISSING}));
  wait(()=>btn(K.w),function(){
    const b=btn(K.w); b.click();
    setTimeout(function(){
      const t=K.w.document.getElementById("ctr-toast");
      chk("loi: toast hien cau loi server", t&&/chưa có bản online/.test(t.textContent)&&/err/.test(t.className));
      chk("loi: khong mo tab, nut mo lai", K.opened.length===0&&!b.disabled&&/Mở online \(Word\)/.test(b.textContent));
      const K2=make(detailFor({can_download_full:true,can_open_online:true}),()=>Promise.resolve({message:{}}));
      wait(()=>btn(K2.w),function(){
        btn(K2.w).click();
        setTimeout(function(){
          const t2=K2.w.document.getElementById("ctr-toast");
          chk("server khong tra url: bao chua co ban online, khong mo tab", K2.opened.length===0&&/chưa có bản online/.test(t2.textContent)&&!btn(K2.w).disabled);
          next();
        },60);
      });
    },60);
  });
}

partFlags(()=>partClick(()=>partError(done)));
