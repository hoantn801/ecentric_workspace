/* Hop dong KOL/KOC tren /approvals/contract-review (jsdom), 11/11/2026:
 *   node ecentric_workspace/approval_center/tests/test_contract_review_kol_page.js <repo>
 * Khoa: chon loai KOL thi hien bo the SO / creator / dich vu / so tien / ho so; gia tri hop
 * dong khong nhap tay; chon creator ca nhan chi cho kieu nhap ca nhan; so tien hien lai TU
 * SERVER (kol_preview_amounts) chu khong tinh o JS; validate rieng cho KOL; tao creator trung
 * thi phai xac nhan lan hai; ke toan thay tab Creator (ma MISA); chi tiet ve khoi KOL + BBNT.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const html=fs.readFileSync(path.join(REPO,"ecentric_workspace/approval_center/features/contract_review/ui/main_section.html"),"utf8");
const KOL="KOL/KOC / Creator (EC)";
const boot={tabs:{},context:{user:"vy@e.c",employee_name:"Vy",department:"E-commerce - EC"},
  form_options:{brands:[{value:"FCV",label:"FCV"}],departments:[{value:"E-commerce - EC",label:"E-commerce"}],
    contract_types:["Purchase / Mua vào (EC)",KOL],request_kinds:["Existing","New"],
    request_types:["Template from EC / Mẫu theo khung EC","Template from partner / Mẫu theo khung đối tác"],
    kol_service_types:["Livestream","Video","Livestream + Video","Hoa hồng affiliate"],kol_platforms:["TikTok","Shopee"],
    kol_payment_schedules:["Thanh toán sau nghiệm thu","Cọc trước"],kol_advance_percents:["20","30","40","50"]}};
const calls=[]; let createTries=0; let genFail=false; let curDetail=null;
function make(url){
  const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:url});
  const w=dom.window;
  w.frappe={call:function(o){ calls.push(o.method.split(".").pop()+" "+JSON.stringify(o.args||{}));
    const m=o.method.split(".").pop();
    if(m==="get_bootstrap") return Promise.resolve({message:boot});
    if(m==="kol_me") return Promise.resolve({message:{is_finance:true}});
    if(m==="kol_list_templates") return Promise.resolve({message:{rows:[{name:"HDDV ca nhan",kind:"Hợp đồng",creator_type:"Cá nhân",service_type:"Tất cả",platform:"Tất cả",has_advance:0},
      {name:"HDDV ca nhan coc",kind:"Hợp đồng",creator_type:"Cá nhân",service_type:"Tất cả",platform:"Tất cả",has_advance:1},
      {name:"HDDV cong ty Shopee",kind:"Hợp đồng",creator_type:"Công ty",service_type:"Livestream",platform:"Shopee",has_advance:0},
      {name:"HDDV HKD video",kind:"Hợp đồng",creator_type:"Hộ kinh doanh",service_type:"Video",platform:"Tất cả",has_advance:0}]}});
    if(m==="kol_search_sales_orders") return Promise.resolve({message:{rows:[{value:"SAL-ORD-2026-00156",label:"SAL-ORD-2026-00156 (GBS GBS-SO-1)",brand:"FCV",revenue:50000000,date:"2026-11-01"}],
      missing:[{gbs:"GBS-SO-9",reason:"GBS SO này chưa có dòng phí EC nên chưa có SO đối ứng"}]}});
    if(m==="kol_search_creators") return Promise.resolve({message:{rows:[{name:"SUP-1",supplier_name:"Nguyễn Thanh Phụng",ec_cr_type:"Cá nhân",misa_label:"KH01"}]}});
    if(m==="kol_preview_amounts") return Promise.resolve({message:{ok:true,amounts:{gross:10000000,pit:1000000,vat:0,payable:9000000,contract_value:10000000,advance:0,payable_words:"Chín triệu đồng"}}});
    if(m==="kol_preview_dates") return Promise.resolve({message:(o.args||{}).air_dates==="05-06/12"?{ok:false,error:"'05-06/12' là khoảng ngày: ghi từng ngày"}:{ok:true,dates:["05/12/2026"],sign_date:"04/12/2026",contract_no:"05122026/HDDV/ECENTRIC-NTP.FCV"}});
    if(m==="kol_preview_contract") return Promise.resolve({message:{ok:false,error:"Chọn creator để xem trước <b>x</b>"}});
    if(m==="kol_creator_gaps") return Promise.resolve({message:{labels:["địa chỉ"]}});
    if(m==="kol_create_creator"){ createTries++; return Promise.resolve({message:createTries===1?{needs_confirm:true,message:"Có thể đã có creator này: A (mã KH KH01) trùng tên."}:{needs_confirm:false,name:"SUP-2"}}); }
    if(m==="kol_generate_contract"&&genFail) return Promise.reject({message:"Mẫu HD lỗi"});
    if(m==="kol_get_creator") return Promise.resolve({message:{name:"SUP-2",supplier_name:"Trần B",ec_cr_type:"Công ty",misa_label:"Đang cập nhật",can_see_pii:true,tax_id:"0101234567",ec_phone:"0912345678",ec_cr_email:"b@x.vn",ec_cr_party_code:"TB",ec_bank_account_no:"0011",ec_bank_name:"VCB"}});
    if(m==="kol_missing_misa") return Promise.resolve({message:{rows:[{name:"SUP-2",supplier_name:"Trần B",ec_cr_type:"Công ty",tax_id:"0101",owner:"vy@e.c",creation:"2026-11-11"}]}});
    if(m==="kol_pending_checks") return Promise.resolve({message:{rows:[{kind:"Hợp đồng",name:"EC-CTR-2026-00101",contract_no:"X/HDDV",creator_name:"Trần B",requested_by:"vy@e.c",at:"2026-11-11 10:00:00"}]}});
    if(m==="get_detail") return Promise.resolve({message:curDetail||detail});
    return Promise.resolve({message:{}});
  }};
  return w;
}
const detail={business:{name:"EC-CTR-2026-00100",contract_type:KOL,request_type:"Template from EC / Mẫu theo khung EC",request_kind:"New",
  so_label:"SAL-ORD-2026-00156",creator_name:"Nguyễn Thanh Phụng",creator_type:"Cá nhân",service_type:"Livestream",amount_type:"Thực nhận sau TNCN",
  amount_input:9000000,gross_amount:10000000,pit_amount:1000000,payable_amount:9000000,payment_schedule:"Cọc trước",advance_percent:30,advance_amount:2700000,
  contract_no:"15032026/HDDV/ECENTRIC-NTP.FCV",contract_file:"/private/files/HDDV.docx",revenue_warning:"Tổng hợp đồng KOL/KOC trên SO này vượt doanh thu EC",
  signing_status:"Đã ký đủ",ai_qc_status:"Cần xem",ai_qc_at:"2026-11-11 10:00:00",
  ai_qc_result:JSON.stringify({data_checks:[{field:"CCCD",value_present:false}],signable:"OK",ai:{template_deviations:["Bỏ điều khoản phạt"],risky_clauses:[{clause:"Thanh toán 100% trước",risk:"rủi ro",severity:"Cao"}],summary:"x"}})},
  approval:{approval_status:"Approved"},capabilities:{},levels:[],approvers:[],timeline:[],attachments:[],
  extra:{kol:{can_manage:true,can_ai:true,approved:true,signed:true,funding:{cap:2700000,used:0,remaining:2700000},
    calc:[{label:"Giá trị trước thuế (gross)",how:"9.000.000 ÷ (1 − 10%)",amount:10000000,strong:true},{label:"<b>x</b>",how:"",amount:1}],
    acceptances:[{name:"r1",idx:1,description:"Livestream T12",acceptance_date:"2026-12-05",amount:6300000,status:"Nháp",bbnt_file:"/private/files/BBNT.docx",
      calc:[{label:"Thực nhận đợt này",how:"",amount:6300000}]}]}}};
const c={}; let failed=0;
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
// PO 17/11: ban du PII tai qua POST (nguoi tao creator + Ke toan), nguoi duyet xem ban che; STK doi;
// thanh ly; tao phieu moi tu phieu tu choi; KOL khong chon "dieu chinh".
function po1711Part(){
  curDetail=JSON.parse(JSON.stringify(detail));
  curDetail.business.contract_file=null; curDetail.extra.kol.acceptances[0].bbnt_file=null; curDetail.extra.kol.acceptances[0].has_signed=true;
  Object.assign(curDetail.extra.kol,{can_manage:false,is_finance:false,can_download_full:false,can_preview:true,payee_changed:true,closed:null}); curDetail.business.has_contract_file=true;
  const w8=make("https://x/approvals/contract-review?id=EC-CTR-2026-00100");
  wait(w8,function(){ return w8.document.getElementById("kol-detail"); },function(){
    const b=w8.document.getElementById("ctr-body").innerHTML;
    chk("nguoi duyet: khong co link / nut tai ban du, co ban da che", !/data-kol="dl"/.test(b)&&!/HDDV\.docx|BBNT\.docx/.test(b)&&/data-kol="preview"/.test(b)&&/che thông tin cá nhân/.test(b));
    chk("nguoi duyet: thay canh bao STK doi nhung khong co nut xac nhan / thanh ly", /Tài khoản nhận tiền của creator đã đổi/.test(b)&&!/data-kol="payeeok"/.test(b)&&!/data-kol="closehd"/.test(b));
    chk("nguoi duyet: dot co ban ky thi ghi 'da co ban ky'", /đã có bản ký/.test(b));
    { const K=w8.ContractReviewKOL, d=JSON.parse(JSON.stringify(curDetail));
      d.extra.kol.can_preview=false; chk("nguoi xem khong duyet: khong co nut ban che (server se tu choi)", !/data-kol="preview"/.test(K.detailHTML(d)));
      d.extra.kol.approved=false; d.approval={approval_status:"Pending"}; chk("chua duyet xong: khong hien canh bao STK / nut xac nhan", !/Tài khoản nhận tiền của creator đã đổi/.test(K.detailHTML(d)));
      const d2=JSON.parse(JSON.stringify(detail)); d2.extra.kol.can_manage=true; d2.extra.kol.closed={at:"2026-11-17",by:"f",reason:"x"};
      chk("da thanh ly: dot nhap khong con nut Danh dau da gui ky", !/data-kol="sendacc"/.test(K.detailHTML(d2)));
      const h2=K.detailHTML(Object.assign(JSON.parse(JSON.stringify(d2)),{business:Object.assign({},d2.business,{revenue_warning:"W"})}));
      d2.extra.kol.closed.reason="Creator huỷ booking.";
      const h3=K.detailHTML(d2);
      chk("da thanh ly: banner dung dau, khong 2 dau cham, van xoa duoc dot nhap cuoi", h2.indexOf("đã thanh lý")<h2.indexOf(">W<")&&!/booking\.\./.test(h3)&&/data-kol="delacc"/.test(h3));
      chk("da thanh ly: thanh tien trinh khong con 'chua len dot'", /Đã thanh lý · Hoàn tất/.test(w8.ContractReview.buildStepper(Object.assign({},d2,{approval:{name:"R",approval_status:"Approved"}})))&&!/chưa lên đợt/.test(w8.ContractReview.buildStepper(Object.assign({},d2,{approval:{name:"R",approval_status:"Approved"}}))));
      { const d6=JSON.parse(JSON.stringify(detail)); d6.approval={approval_status:"Approved"};
        Object.assign(d6.extra.kol,{can_manage:true,is_finance:true,approved:true,signed:false,closed:{at:"2026-11-17",by:"f",reason:"x"}}); d6.business.signing_status="Chưa ký";
        const h6=K.detailHTML(d6);
        chk("thanh ly truoc khi ky: khong con o tai ban ky; Ke toan co nut Mo lai", !/kol-signed-f/.test(h6)&&/data-kol="reopenhd"/.test(h6)); }
      const d5=JSON.parse(JSON.stringify(detail)); d5.approval={approval_status:"Draft"}; d5.business.has_contract_file=true; d5.business.contract_file=null;
      Object.assign(d5.extra.kol,{can_manage:true,can_download_full:false,approved:false,signed:false});
      chk("nguoi lap nhap: goi y tai sau khi gui + nut Xem truoc, khong noi 'kiem tra tep .docx'", /Gửi phiếu xong bạn tải được/.test(K.detailHTML(d5))&&!/kiểm tra tệp \.docx/.test(K.detailHTML(d5))); }
    curDetail=JSON.parse(JSON.stringify(detail));
    curDetail.extra.kol.acceptances[0].signed_file="/private/files/bbnt ky.pdf";
    Object.assign(curDetail.extra.kol,{is_finance:true,can_download_full:true,payee_changed:true,closed:null}); curDetail.business.creator="SUP-1";
    const w9=make("https://x/approvals/contract-review?id=EC-CTR-2026-00100");
    const posted=[]; let dlFail=false; w9.URL.createObjectURL=function(){ return "blob:x"; }; w9.URL.revokeObjectURL=function(){};
    w9.fetch=function(u,o){ const rec={action:u,method:o.method,csrf:(o.headers||{})["X-Frappe-CSRF-Token"]}; o.body.forEach(function(v,k){ rec[k]=v; }); posted.push(rec);
      if(dlFail) return Promise.resolve({ok:false,status:403,headers:{get:function(){ return "application/json"; }},json:function(){ return Promise.resolve({_server_messages:JSON.stringify([JSON.stringify({message:"Bản đủ thông tin cá nhân creator chỉ người lập phiếu (sau khi gửi), người tạo creator hoặc Kế toán tải được."})])}); }});
      return Promise.resolve({ok:true,status:200,headers:{get:function(){ return 'attachment; filename="HDDV.docx"'; }},blob:function(){ return Promise.resolve(new w9.Blob(["x"])); }}); };
    wait(w9,function(){ return w9.document.getElementById("kol-detail"); },function(){
      const b9=w9.document.getElementById("ctr-body").innerHTML;
      chk("ke toan: nut tai hop dong + BBNT + ban ky, khong co href toi tep", (b9.match(/data-kol="dl"/g)||[]).length>=3&&!/href="\/private\/files/.test(b9));
      w9.document.querySelector('[data-kol="dl"]').click();
      chk("tai: POST toi kol_download_file kem header csrf + ten tep", posted.length===1&&/kol_download_file$/.test(posted[0].action)&&/post/i.test(posted[0].method)&&posted[0].file_url==="/private/files/HDDV.docx"&&posted[0].name==="EC-CTR-2026-00100"&&"csrf" in posted[0]);
      setTimeout(function(){
      const d1=w9.document.querySelector('[data-kol="dl"]');
      chk("tai xong: nut mo lai, chu tra ve", d1&&!d1.disabled&&/Tải hợp đồng/.test(d1.textContent));
      dlFail=true; d1.click();
      setTimeout(function(){
      chk("tai bi tu choi: o lai trang + toast loi tieng Viet", /người tạo creator hoặc Kế toán/.test((w9.document.getElementById("ctr-toast")||{}).textContent||"")&&!w9.document.querySelector('[data-kol="dl"]').disabled);
      chk("ke toan: co nut Xem thong tin creator canh nut xac nhan STK", !!w9.document.querySelector('[data-kol="viewcr"]'));
      w9.document.querySelector('[data-kol="payeeok"]').click();
      chk("xac nhan STK: hoi lai truoc (chua goi server)", !calls.some(x=>/^kol_confirm_payee /.test(x))&&/Các đợt sau sẽ chi vào tài khoản này/.test((w9.document.querySelector(".ec-ctr-overlay")||{}).textContent||""));
      w9.document.querySelector(".ec-ctr-overlay [data-ok]").click();
      setTimeout(function(){
        chk("ke toan xac nhan STK: goi kol_confirm_payee", calls.some(x=>/^kol_confirm_payee /.test(x))&&!w9.document.querySelector(".ec-ctr-overlay"));
        w9.document.querySelector('[data-kol="closehd"]').click();
        setTimeout(function(){
          const ov=w9.document.querySelector(".ec-ctr-overlay"); ov.querySelector("[data-ok]").click();
          setTimeout(function(){
            chk("thanh ly: bat buoc ly do", !calls.some(x=>/^kol_close_contract/.test(x)));
            ov.querySelector("#kol-close-r").value="creator huy booking"; ov.querySelector("[data-ok]").click();
            setTimeout(function(){
              chk("thanh ly: goi kol_close_contract kem ly do", calls.some(x=>/^kol_close_contract .*creator huy booking/.test(x)));
              curDetail=JSON.parse(JSON.stringify(detail));
              Object.assign(curDetail.extra.kol,{is_finance:true,can_download_full:true,closed:{at:"2026-11-17 10:00:00",by:"fin@e.c",reason:"dung <b>x</b>"}});
              const w10=make("https://x/approvals/contract-review?id=EC-CTR-2026-00100");
              wait(w10,function(){ return w10.document.getElementById("kol-detail"); },function(){
                const b10=w10.document.getElementById("ctr-body").innerHTML;
                chk("da thanh ly: banner (escape ly do), khong them dot / khong thanh ly lai", /Hợp đồng đã thanh lý/.test(b10)&&/dung &lt;b&gt;x/.test(b10)&&!/data-kol="addacc"/.test(b10)&&!/data-kol="closehd"/.test(b10));
                curDetail=JSON.parse(JSON.stringify(detail)); curDetail.business.requested_by="vy@e.c"; curDetail.approval={name:"R9",approval_status:"Rejected"};
                const w11=make("https://x/approvals/contract-review?id=EC-CTR-2026-00100");
                wait(w11,function(){ return w11.document.querySelector('[data-act="clone"]'); },function(){
                  w11.document.querySelector('[data-act="clone"]').click();
                  setTimeout(function(){ w11.document.querySelector(".ec-ctr-overlay [data-ok]").click();
                    setTimeout(function(){ chk("tu choi: nut Tao phieu moi goi clone_request", calls.some(x=>/^clone_request .*EC-CTR-2026-00100/.test(x)));
                      rulesPart(); },120); },80);
                });
              });
            },150);
          },80);
        },80);
      },150);
      },120);
      },120);
    });
  });
}
// Luat mau tool cu tren form (12/11): HKD / Shopee khong coc, chon coc tu dien 40%, danh sach mau loc theo
// loai creator + nen tang + coc, nen tang ngoai TikTok/Shopee bi chan voi mau EC.
function rulesPart(){
  const w7=make("https://x/approvals/contract-review");
  wait(w7,function(){ return w7.ContractReview&&w7.document.querySelector('[data-model="contract_type"]'); },function(){
    const rk=w7.document.querySelector('[data-model="request_kind"]'); rk.value="Existing"; fire(w7,rk,"change");
    const ct=w7.document.querySelector('[data-model="contract_type"]'); ct.value=KOL; fire(w7,ct,"change");
    setTimeout(function(){
      { const rk2=w7.document.querySelector('[data-model="request_kind"]'), ex=Array.from(rk2.options).filter(o=>o.value==="Existing")[0];
        chk("KOL: tu ve Hop dong moi + khoa lua chon dieu chinh", w7.ContractReview.state.draft.request_kind==="New"&&rk2.value==="New"&&ex.disabled); }
      w7.ContractReviewKOL.pickCreator({name:"SUP-H",supplier_name:"Hộ KD A",ec_cr_type:"Hộ kinh doanh"});
      setTimeout(function(){
        const ps=w7.document.querySelector('[data-model="payment_schedule"]');
        chk("HKD: khong co lua chon Coc truoc", !Array.from(ps.options).some(o=>o.value==="Cọc trước")&&/không cọc/.test(w7.document.getElementById("ctr-body").innerHTML));
        const tpl=Array.from(w7.document.querySelectorAll("#kol-tpl option")).map(o=>o.value).filter(Boolean);
        chk("mau: chi hien mau cua loai creator dang chon", tpl.join("|")==="HDDV HKD video");
        w7.ContractReviewKOL.pickCreator({name:"SUP-1",supplier_name:"Nguyễn A",ec_cr_type:"Cá nhân"});
        setTimeout(function(){
          const ps2=w7.document.querySelector('[data-model="payment_schedule"]'); ps2.value="Cọc trước"; fire(w7,ps2,"change");
          setTimeout(function(){
            chk("chon Coc truoc: tu dien 40% + ghi co so tinh coc", w7.ContractReview.state.draft.advance_percent==="40"&&w7.document.querySelector('[data-model="advance_percent"]').value==="40"&&/số creator thực nhận/.test(w7.document.getElementById("ctr-body").innerHTML));
            const tpl2=Array.from(w7.document.querySelectorAll("#kol-tpl option")).map(o=>o.value).filter(Boolean);
            chk("mau: coc thi chi mau co coc", tpl2.join("|")==="HDDV ca nhan coc");
            const pf=w7.document.querySelector('[data-model="platform"]'); pf.innerHTML+='<option>Facebook</option>'; pf.value="Facebook"; fire(w7,pf,"change");
            setTimeout(function(){
              const errs=w7.ContractReview.validateSubmit()||{};
              chk("nen tang Facebook + mau EC: bao dung mau creator", /Mẫu EC chỉ có TikTok/.test(errs.platform||""));
              const ad=w7.document.querySelector('[data-model="air_dates"]'); ad.value="05-06/12"; fire(w7,ad,"input");
              setTimeout(function(){
                chk("ngay dang khoang '05-06/12': bao loi ro tu server", /khoảng ngày/.test(w7.document.getElementById("kol-dates-pv").innerHTML));
                done();
              },450);
            },120);
          },120);
        },150);
      },150);
    },100);
  });
}
function done(){ Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k)); console.log(failed?"SOME_FAIL":"ALL_PASS"); process.exit(failed?1:0); }
function wait(w,cond,cb,n){ n=n||0; if(cond()||n>80) return cb(); setTimeout(function(){ wait(w,cond,cb,n+1); },25); }
function fire(w,el,ev){ el.dispatchEvent(new w.Event(ev,{bubbles:true})); }

const w=make("https://x/approvals/contract-review");
wait(w,function(){ return w.ContractReview&&w.document.querySelector('[data-model="contract_type"]'); },function(){
  const ct=w.document.querySelector('[data-model="contract_type"]'); ct.value=KOL; fire(w,ct,"change");
  setTimeout(function(){
    const b=w.document.getElementById("ctr-body").innerHTML;
    chk("chon KOL hien the creator + dich vu + so tien + ho so, KHONG con o SO (SO chon o DNTT)", !/kol-so-q/.test(b)&&/kol-cr-q/.test(b)&&/data-model="service_type"/.test(b)&&/data-model="amount_input"/.test(b)&&/Hồ sơ hợp đồng/.test(b)&&/chọn ở đề nghị thanh toán/.test(b));
    chk("gia tri hop dong khong nhap tay", !w.document.querySelector('[data-model="contract_value"]'));
    const errs=w.ContractReview.validateSubmit()||{};
    chk("validate KOL: doi brand/creator/dich vu/tien/ngay thuc hien, khong doi SO/gia tri/muc dich", !errs.sales_order&&errs.brand&&errs.creator&&errs.service_type&&errs.amount_input&&errs.air_dates&&!errs.contract_value&&!errs.justification);
    chk("ke toan thay tab Creator (ma MISA)", /Creator \(mã MISA\)/.test(w.document.getElementById("ctr-tabs").innerHTML));
    const br=w.document.querySelector('[data-model="brand"]'); br.value="FCV"; fire(w,br,"change");
    setTimeout(function(){
      chk("chon brand truc tiep tren hop dong", w.ContractReview.state.draft.brand==="FCV");
      w.ContractReviewKOL.pickCreator({name:"SUP-1",supplier_name:"Nguyễn Thanh Phụng",ec_cr_type:"Cá nhân"});
      setTimeout(function(){
        chk("chon creator: bao creator con thieu gi cho hop dong (nhan, khong gia tri)", /Creator còn thiếu cho hợp đồng: <b>địa chỉ<\/b>/.test(w.document.getElementById("ctr-body").innerHTML));
        const ad=w.document.querySelector('[data-model="air_dates"]'); ad.value="05/12"; fire(w,ad,"input");
        const at=w.document.querySelector('[data-model="amount_type"]');
        const opts=Array.from(at.options).map(o=>o.value).filter(Boolean);
        chk("creator ca nhan chi cho kieu nhap ca nhan", opts.join("|")==="Thực nhận sau TNCN|Gross trước TNCN" && !!w.document.querySelector('[data-model="pit_rate"]'));
        chk("so ngay thanh toan: o trong, goi y mac dinh 35 cho ca nhan", w.document.querySelector('[data-model="payment_term_days"]').value===""&&/Mặc định 35 ngày/.test(w.document.querySelector('[data-model="payment_term_days"]').placeholder));
        at.value="Thực nhận sau TNCN"; fire(w,at,"change");
        const am=w.document.querySelector('[data-model="amount_input"]'); am.value="9000000"; fire(w,am,"input");
        setTimeout(function(){
          chk("so tien lay tu server (kol_preview_amounts)", calls.some(x=>/^kol_preview_amounts .*"creator_type":"Cá nhân"/.test(x)) && /Chín triệu đồng/.test(w.document.getElementById("kol-amounts").innerHTML));
          chk("ngay thuc hien: xem truoc ngay doc duoc + ngay ky + so HD (tu server)", /Đọc được: <b>05\/12\/2026<\/b>/.test(w.document.getElementById("kol-dates-pv").innerHTML)&&/04\/12\/2026/.test(w.document.getElementById("kol-dates-pv").innerHTML)&&/05122026\/HDDV/.test(w.document.getElementById("kol-dates-pv").innerHTML));
          // tao creator: lan dau bi hoi lai, lan hai moi tao
          w.ContractReviewKOL.creatorModal();
          const ov=w.document.querySelector(".ec-ctr-overlay");
          ov.querySelector("#kc-supplier_name").value="Trần B"; ov.querySelector("#kc-ec_cr_party_code").value="TB";
          ov.querySelector("[data-ok]").click();
          chk("thieu CCCD / STK: bao loi NGAY TRONG modal, khong goi server", /Còn thiếu: CCCD, số tài khoản, ngân hàng/.test(ov.querySelector("#kc-msg").innerHTML) && !calls.some(x=>/^kol_create_creator/.test(x)));
          ov.querySelector("#kc-ec_cr_cccd").value="079123456789"; ov.querySelector("#kc-ec_bank_account_no").value="0011"; ov.querySelector("#kc-ec_bank_name").value="VCB";
          setTimeout(function(){ ov.querySelector("[data-ok]").click(); },20);
          setTimeout(function(){
            chk("tao creator trung mem: hoi lai, chua dong, nut doi thanh 'Vẫn tạo creator mới'", !!w.document.querySelector(".ec-ctr-overlay") && /trùng tên/.test(ov.querySelector("#kc-msg").innerHTML) && /Vẫn tạo creator mới/.test(ov.querySelector("[data-ok]").textContent));
            // sua du lieu sau canh bao -> phai hoi lai tu dau
            const pc=ov.querySelector("#kc-ec_cr_party_code"); pc.value="TB2"; fire(w,pc,"input");
            chk("sua du lieu sau canh bao: bo xac nhan", /^Tạo creator$/.test(ov.querySelector("[data-ok]").textContent));
            pc.value="TB"; createTries=0;
            ov.querySelector("[data-ok]").click();
            setTimeout(function(){ chk("sau khi sua: hoi lai lan nua", /Vẫn tạo creator mới/.test(ov.querySelector("[data-ok]").textContent)); ov.querySelector("[data-ok]").click();
            setTimeout(function(){
              chk("xac nhan lan hai: goi confirm_soft=1 va chon creator moi", calls.some(x=>/kol_create_creator .*"confirm_soft":1/.test(x)) && w.ContractReview.state.draft.creator==="SUP-2");
              chk("tieu de tu dong KOL theo brand + creator", /^HĐ KOL\/KOC - FCV - /.test(w.ContractReview.state.draft.request_title||""));
              chk("nut gui doi thanh 'Tạo hợp đồng & gửi' (mau EC)", /Tạo hợp đồng &amp; gửi|Tạo hợp đồng & gửi/.test(w.document.getElementById("ctr-submit").innerHTML));
              // PO 12/11: nut xem truoc (mau EC) mo hop thoai, loi server hien ra (esc), khong tai trinh xem tu CDN.
              var pvb=w.document.getElementById("kol-pv-btn"); chk("co nut Xem truoc hop dong (mau EC)", !!pvb);
              if(pvb){ pvb.click(); setTimeout(function(){ var mo=w.document.querySelector(".kol-pv-modal");
                chk("xem truoc: hop thoai + bao loi server da esc", !!mo&&/Chọn creator để xem trước/.test(mo.textContent)&&!mo.querySelector("#kol-pv-doc b"));
                chk("xem truoc: goi kol_preview_contract kem du lieu dang go", calls.some(x=>/kol_preview_contract .*fields/.test(x)));
                var x=mo&&mo.querySelector("[data-x]"); if(x) x.click();
                detailPart(); },120); } else detailPart();
            },150); },150);
          },150);
        },400);
      },100);
    },400);
  },100);
});

function detailPart(){
  const w2=make("https://x/approvals/contract-review?id=EC-CTR-2026-00100");
  let evt=null; w2.document.addEventListener("ctr:detail-rendered",function(e){ evt=e.detail; });
  wait(w2,function(){ return w2.document.getElementById("kol-detail"); },function(){
    const b=w2.document.getElementById("ctr-body").innerHTML;
    chk("chi tiet: khoi KOL + canh bao doanh thu + so HD", /Hợp đồng KOL\/KOC/.test(b)&&/vượt doanh thu EC/.test(b)&&/15032026\/HDDV/.test(b));
    chk("chi tiet: AI QC hien so lieu lech + dieu khoan rui ro", /Không thấy trong tệp/.test(b)&&/Bỏ điều khoản phạt/.test(b)&&/Thanh toán 100% trước/.test(b));
    chk("chi tiet: BBNT + tran chi + nut tao BBNT", /Livestream T12/.test(b)&&/Được phép chi/.test(b)&&/data-kol="sendacc"/.test(b)&&!/kol-accf-/.test(b)&&/data-kol="addacc"/.test(b));
    // PO 12/11: bang tinh tung buoc cho Ke toan (hop dong + tung dot), nhan duoc esc.
    // Chang 3b ky so (chot 12/11): cho gan khoi ky so + su kien cho thanh phan dung chung.
    const slot=w2.document.getElementById("ctr-esign-slot");
    chk("chi tiet: co cho gan khoi Ky so, dat truoc the BBNT", !!slot&&slot.getAttribute("data-business-name")==="EC-CTR-2026-00100"&&b.indexOf('id="ctr-esign-slot"')<b.indexOf("Nghiệm thu (BBNT)"));
    { const CR=w2.ContractReview, keep=CR.state.draft;
      CR.state.draft={request_title:"HĐ LĐ",request_kind:"New",contract_type:"Labor / Hợp đồng lao động (EC)",request_type:"Template from EC / Mẫu theo khung EC",justification:"Tuyển dụng",request_details:"x"};
      const e1=CR.validateSubmit()||{}; CR.state.draft.contract_type="Purchase / Mua vào (EC)"; const e2=CR.validateSubmit()||{};
      chk("HD lao dong: khong bat brand / gia tri (loai khac van bat)", !e1.brand&&!e1.contract_value&&!!e2.brand&&!!e2.contract_value);
      CR.state.draft=keep; }
    chk("chi tiet: phat su kien ctr:detail-rendered", !!evt&&evt.business_doctype==="EC Contract Review Request"&&evt.business_name==="EC-CTR-2026-00100");
    // Thiet ke ban 2 (12/11 11:49): khoi hien tu luc lap phieu; chi sua duoc khi phieu con o nguoi lap.
    chk("su kien: phieu da duyet -> can_edit=false", !!evt&&evt.can_edit===false&&evt.approval_status!=="Draft");
    chk("chi tiet: bang tinh hop dong + dot", /Bảng tính chi tiết/.test(b)&&/9\.000\.000 ÷ \(1 − 10%\)/.test(b)&&/Bảng tính đợt này/.test(b)&&b.indexOf("<b>x</b>")<0);
    // QC3: dot NHAP chua co nut Hoan tat - phai qua "Danh dau da gui ky" (kiem thieu + tao lai BBNT) truoc.
    chk("BBNT nhap: chua cho Hoan tat (bo qua buoc kiem)", !/data-kol="doneacc"/.test(b));
    chk("da duyet: khong con nut tao lai hop dong", !/data-kol="gen"/.test(b));
    // PO 12/11: thanh tien trinh HD KOL noi them Ky HD -> Nghiem thu -> Thanh toan; duyet thay ghi ten.
    { const CR=w2.ContractReview, d2=JSON.parse(JSON.stringify(detail)); d2.approval={name:"R0",approval_status:"Approved"};
      const hs=CR.buildStepper(d2);
      chk("tien trinh KOL: co 3 buoc sau duyet, trang thai dung", /Ký hợp đồng[\s\S]*Đã ký đủ/.test(hs)&&/Nghiệm thu \(BBNT\)[\s\S]*Hoàn tất 0\/1 đợt/.test(hs)&&/Thanh toán \(ĐNTT\)[\s\S]*Đã lập ĐNTT/.test(hs)&&/Hoàn tất<\/div>[\s\S]*Chờ/.test(hs));
      // QC 15/11 vong 3: "con X" chi khi con tien CHUA LEN DOT (khong phai chua nghiem thu); thieu du lieu KOL thi khong "Hoan tat".
      const d3=JSON.parse(JSON.stringify(d2)); d3.extra.kol.acceptance_remaining=0;
      chk("tien trinh KOL: het tien chua len dot thi khong ghi 'con 0'", !/còn 0/.test(CR.buildStepper(d3)));
      d3.extra.kol.acceptance_remaining=500000;
      chk("tien trinh KOL: con tien chua len dot thi ghi ro", /chưa lên đợt/.test(CR.buildStepper(d3)));
      const d4=JSON.parse(JSON.stringify(d2)); delete d4.extra.kol;
      chk("tien trinh KOL: thieu du lieu vong doi thi Hoan tat chua xong", /Hoàn tất<\/div>[\s\S]*Chờ/.test(CR.buildStepper(d4)));
      d2.approval.approval_status="Rejected"; chk("tien trinh KOL: phieu tu choi khong ve buoc sau duyet", !/Ký hợp đồng/.test(CR.buildStepper(d2))); }
    { const CR=w2.ContractReview;
      const h=CR.buildStepper({business:{contract_type:"Purchase / Mua vào (EC)"},approval:{name:"R1",approval_status:"Approved"},
        levels:[{level_no:4,level_name:"CEO Review",level_status:"Approved"}],approvers:[{level_no:4,approver:"lam@e.c",status:"Pending"}],
        timeline:[{action:"Approved",level_no:4,actor:"hoan<b>@e.c"}]});
      chk("duyet thay: ghi ten nguoi bam (escape), form khac khong co buoc KOL", /Duyệt thay bởi hoan&lt;b&gt;@e\.c/.test(h)&&!/Ký hợp đồng/.test(h)); }
    chk("da duyet + da ky: khong con the mo (kol-later)", !/kol-later/.test(b));
    chk("BBNT: nut Hoan tat mo modal (khong o tep trong bang) + nut Xoa dot nhap", /data-kol="delacc"/.test(b));
    creatorsTab();
  });
}
function creatorsTab(){
  const w3=make("https://x/approvals/contract-review?tab=creators");
  wait(w3,function(){ return /Trần B/.test((w3.document.getElementById("ctr-body")||{}).innerHTML||""); },function(){
    const b=w3.document.getElementById("ctr-body").innerHTML;
    chk("tab Creator: danh sach chua co ma + o nhap ma + xuat CSV", /Trần B/.test(b)&&/data-misa="SUP-2"/.test(b)&&/kol-csv/.test(b));
    chk("tab Creator: hang cho kiem ban ky cho ke toan", /Chờ kiểm tra bản ký/.test(b)&&/EC-CTR-2026-00101/.test(b));
    draftPart();
  });
}

// QC vong 2: nut Tao hop dong loi thi phai mo lai + bao loi (truoc: TypeError, nut khoa vinh vien);
// Sua creator chi gui truong DA DOI (truoc: gui "" cho MST / SDT / email -> xoa trang).
function draftPart(){
  curDetail=JSON.parse(JSON.stringify(detail));
  curDetail.business.creator="SUP-2"; curDetail.business.contract_file=null; curDetail.approval={approval_status:"Draft"};
  curDetail.extra.kol.approved=false; curDetail.extra.kol.signed=false;
  genFail=true;
  const w4=make("https://x/approvals/contract-review?id=EC-CTR-2026-00100");
  wait(w4,function(){ return w4.document.querySelector('[data-kol="gen"]'); },function(){
    const g=w4.document.querySelector('[data-kol="gen"]'); g.click();
    setTimeout(function(){
      const g2=w4.document.querySelector('[data-kol="gen"]');
      chk("tao hop dong loi: nut mo lai, chu tra ve, co bao loi", g2&&!g2.disabled&&/Tạo hợp đồng từ mẫu/.test(g2.textContent));
      { const bd=w4.document.getElementById("ctr-body").innerHTML;
        chk("nhap: the Ky HD + Nghiem thu hien mo truoc (kol-later)", (bd.match(/card kol-later/g)||[]).length===2&&/Mở sau khi phiếu duyệt xong/.test(bd)); }
      w4.document.querySelector('[data-kol="editcr"]').click();
      setTimeout(function(){
        const ov=w4.document.querySelector(".ec-ctr-overlay");
        chk("sua creator: dien san MST / SDT / email", ov&&ov.querySelector("#kc-tax_id").value==="0101234567"&&ov.querySelector("#kc-ec_phone").value==="0912345678");
        ov.querySelector("#kc-ec_phone").value="0988000111";
        ov.querySelector("[data-ok]").click();
        setTimeout(function(){
          const up=calls.filter(x=>/^kol_update_creator/.test(x)).pop()||"";
          chk("sua creator: chi gui truong da doi", /"data":"\{\\"ec_phone\\":\\"0988000111\\"\}"/.test(up));
          reviewPart();
        },150);
      },150);
    },150);
  });
}

// Ban ky cho kiem (anh Hoan 11/11: can ke toan hoac may kiem): ke toan thay nut xac nhan / tra lai,
// chua mo nghiem thu; nguoi tao thuong khong thay nut xac nhan.
function reviewPart(){
  genFail=false;
  curDetail=JSON.parse(JSON.stringify(detail));
  curDetail.business.signing_status="Chờ kiểm tra"; curDetail.business.signed_file="/private/files/ky.pdf";
  curDetail.business.sign_check_note="- Tìm thấy 0 chữ ký số, cần ít nhất 2";
  curDetail.extra.kol.signed=false; curDetail.extra.kol.is_finance=true;
  const w5=make("https://x/approvals/contract-review?id=EC-CTR-2026-00100");
  wait(w5,function(){ return /Chờ Kế toán kiểm/.test((w5.document.getElementById("ctr-body")||{}).innerHTML||""); },function(){
    const b=w5.document.getElementById("ctr-body").innerHTML;
    chk("ban ky cho kiem: ke toan co nut xac nhan + tra lai, ly do may kiem", /data-kol="vsignok"/.test(b)&&/data-kol="vsignno"/.test(b)&&/0 chữ ký số/.test(b));
    chk("ban ky cho kiem: chua mo nghiem thu / tran chi", !/Được phép chi/.test(b));
    w5.document.querySelector('[data-kol="vsignok"]').click();
    setTimeout(function(){
      chk("ke toan xac nhan: goi kol_verify_signed ok=1", calls.some(x=>/^kol_verify_signed .*"ok":1/.test(x)));
      curDetail.extra.kol.is_finance=false;
      const w6=make("https://x/approvals/contract-review?id=EC-CTR-2026-00100");
      wait(w6,function(){ return /Chờ Kế toán kiểm/.test((w6.document.getElementById("ctr-body")||{}).innerHTML||""); },function(){
        chk("nguoi tao: khong co nut xac nhan ban ky", !/data-kol="vsignok"/.test(w6.document.getElementById("ctr-body").innerHTML));
        po1711Part();
      });
    },150);
  });
}
