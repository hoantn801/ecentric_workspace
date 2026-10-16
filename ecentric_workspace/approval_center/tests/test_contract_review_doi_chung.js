/* Trang /approvals/contract-review - the "Bản đối chứng" (jsdom), 16/10/2026:
 *   node ecentric_workspace/approval_center/tests/test_contract_review_doi_chung.js <repo>
 * Khoá: có bản đối chứng thì vẽ thẻ riêng (KHÔNG lẫn vào Đính kèm), giữ thứ tự server gửi
 * (mới nhất trước), có link PDF + bản gốc, cảnh báo khi tệp sửa giữa lúc quyết định và lúc
 * chụp, escape mọi chuỗi; không có bản nào thì không vẽ thẻ.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const html=fs.readFileSync(path.join(REPO,"ecentric_workspace/approval_center/features/contract_review/ui/main_section.html"),"utf8");
const boot={tabs:{},context:{user:"vy@e.c",employee_name:"Vy"},form_options:{brands:[],departments:[],contract_types:[],request_types:[]}};
function det(doiChung){ return {business:{name:"CTR-1",request_title:"HĐ ABC",requested_by:"vy@e.c"},
  approval:{name:"AR-1",approval_status:"Pending",current_level:3},levels:[],approvers:[],timeline:[],
  attachments:[{name:"F1",file_name:"Hop dong ABC.docx",file_url:"/private/files/Hop dong ABC.docx",owner:"vy@e.c",creation:"2026-10-13 09:00:00"}],
  doi_chung:doiChung,capabilities:{}}; }
const DS=[
  {level_no:2,actor:"lien.vu@e.c",actor_name:"Vũ Liên",action:"Rejected",action_label:"khi từ chối cấp 2",
   action_time:"2026-10-15 08:00:00",source_file_name:"Hop dong ABC.docx",docx_file_url:"/private/files/[Đối chứng] b.docx",
   pdf_file_url:"/private/files/[Đối chứng] b.pdf",sua_sau_quyet_dinh:false},
  {level_no:1,actor:"x@e.c",actor_name:'<img src=x onerror="window.__xss=1">',action:"Approved",action_label:"sau duyệt cấp 1",
   action_time:"2026-10-14 10:20:00",source_file_name:"Hop dong ABC.docx",docx_file_url:"/private/files/[Đối chứng] a.docx",
   pdf_file_url:null,sua_sau_quyet_dinh:true,sp_last_modified:"2026-10-14 10:20:40",sp_last_modified_by:"lien.vu@e.c"}];
function mo(doiChung){ return new Promise(function(res){
  const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://x/approvals/contract-review?id=CTR-1"});
  const w=dom.window;
  w.frappe={call:function(o){
    if(/get_bootstrap/.test(o.method)) return Promise.resolve({message:boot});
    if(/get_detail/.test(o.method)) return Promise.resolve({message:det(doiChung)});
    return Promise.resolve({message:{}}); }};
  let t=0;(function poll(){ const b=w.document.getElementById("ctr-body");
    if(!(b&&/Đính kèm/.test(b.innerHTML))){ if(t++>120) return res({w:w,b:"",x:"not ready"}); return setTimeout(poll,25); }
    res({w:w,b:b.innerHTML}); })(); }); }
const c={}; let failed=0;
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
(async function(){
  const a=await mo(DS);
  const b=a.b;
  const iCard=b.indexOf("<h3>Bản đối chứng</h3>");
  chk("co the Ban doi chung", iCard>0);
  chk("the rieng, nam SAU the Dinh kem", iCard>b.indexOf("<h3>Đính kèm</h3>"));
  const card=b.slice(iCard);
  chk("giu thu tu server (moi nhat truoc)", card.indexOf("Khi từ chối cấp 2")>=0 && card.indexOf("Khi từ chối cấp 2")<card.indexOf("Sau duyệt cấp 1"));
  chk("link PDF + ban goc DOCX", /\[Đối chứng\] b\.pdf"[^>]*>PDF</.test(card) && /\[Đối chứng\] b\.docx"[^>]*>DOCX</.test(card));
  chk("thieu PDF thi chi con ban goc", /\[Đối chứng\] a\.docx"[^>]*>DOCX</.test(card) && !/a\.pdf/.test(card));
  chk("canh bao sua giua quyet dinh va luc chup", /sau quyết định nhưng trước lúc chụp/.test(card) && /bởi lien\.vu@e\.c/.test(card));
  chk("escape ten nguoi", !a.w.__xss && /&lt;img/.test(card));
  chk("ban doi chung KHONG lan vao Dinh kem", !/\[Đối chứng\]/.test(b.slice(b.indexOf("<h3>Đính kèm</h3>"), iCard)));
  const e=await mo([]);
  chk("khong co ban nao thi khong ve the", e.b && !/Bản đối chứng/.test(e.b));
  Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k));
  console.log(failed?"SOME_FAIL":"ALL_PASS"); process.exit(failed?1:0);
})();
