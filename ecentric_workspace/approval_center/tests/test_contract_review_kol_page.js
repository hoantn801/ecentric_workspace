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
    if(m==="kol_list_templates") return Promise.resolve({message:{rows:[{name:"HDDV ca nhan",kind:"Hợp đồng"}]}});
    if(m==="kol_search_sales_orders") return Promise.resolve({message:{rows:[{value:"SAL-ORD-2026-00156",label:"SAL-ORD-2026-00156 (GBS GBS-SO-1)",brand:"FCV",revenue:50000000,date:"2026-11-01"}],
      missing:[{gbs:"GBS-SO-9",reason:"GBS SO này chưa có dòng phí EC nên chưa có SO đối ứng"}]}});
    if(m==="kol_search_creators") return Promise.resolve({message:{rows:[{name:"SUP-1",supplier_name:"Nguyễn Thanh Phụng",ec_cr_type:"Cá nhân",misa_label:"KH01"}]}});
    if(m==="kol_preview_amounts") return Promise.resolve({message:{ok:true,amounts:{gross:10000000,pit:1000000,vat:0,payable:9000000,contract_value:10000000,advance:0,payable_words:"Chín triệu đồng chẵn"}}});
    if(m==="kol_create_creator"){ createTries++; return Promise.resolve({message:createTries===1?{needs_confirm:true,message:"Có thể đã có creator này: A (mã KH KH01) trùng tên."}:{needs_confirm:false,name:"SUP-2"}}); }
    if(m==="kol_generate_contract"&&genFail) return Promise.reject({message:"Mẫu HD lỗi"});
    if(m==="kol_get_creator") return Promise.resolve({message:{name:"SUP-2",supplier_name:"Trần B",ec_cr_type:"Công ty",misa_label:"Đang cập nhật",can_see_pii:true,tax_id:"0101234567",ec_phone:"0912345678",ec_cr_email:"b@x.vn",ec_cr_party_code:"TB",ec_bank_account_no:"0011",ec_bank_name:"VCB"}});
    if(m==="kol_missing_misa") return Promise.resolve({message:{rows:[{name:"SUP-2",supplier_name:"Trần B",ec_cr_type:"Công ty",tax_id:"0101",owner:"vy@e.c",creation:"2026-11-11"}]}});
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
    acceptances:[{name:"r1",idx:1,description:"Livestream T12",acceptance_date:"2026-12-05",amount:6300000,status:"Nháp",bbnt_file:"/private/files/BBNT.docx"}]}}};
const c={}; let failed=0;
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
function done(){ Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k)); console.log(failed?"SOME_FAIL":"ALL_PASS"); process.exit(failed?1:0); }
function wait(w,cond,cb,n){ n=n||0; if(cond()||n>80) return cb(); setTimeout(function(){ wait(w,cond,cb,n+1); },25); }
function fire(w,el,ev){ el.dispatchEvent(new w.Event(ev,{bubbles:true})); }

const w=make("https://x/approvals/contract-review");
wait(w,function(){ return w.ContractReview&&w.document.querySelector('[data-model="contract_type"]'); },function(){
  const ct=w.document.querySelector('[data-model="contract_type"]'); ct.value=KOL; fire(w,ct,"change");
  setTimeout(function(){
    const b=w.document.getElementById("ctr-body").innerHTML;
    chk("chon KOL hien the SO + creator + dich vu + so tien + ho so", /kol-so-q/.test(b)&&/kol-cr-q/.test(b)&&/data-model="service_type"/.test(b)&&/data-model="amount_input"/.test(b)&&/Hồ sơ hợp đồng/.test(b));
    chk("gia tri hop dong khong nhap tay", !w.document.querySelector('[data-model="contract_value"]'));
    const errs=w.ContractReview.validateSubmit()||{};
    chk("validate KOL: doi SO/creator/dich vu/tien, khong doi gia tri/muc dich", errs.sales_order&&errs.creator&&errs.service_type&&errs.amount_input&&!errs.contract_value&&!errs.justification);
    chk("ke toan thay tab Creator (ma MISA)", /Creator \(mã MISA\)/.test(w.document.getElementById("ctr-tabs").innerHTML));
    const q=w.document.getElementById("kol-so-q"); q.value="GBS"; fire(w,q,"input");
    setTimeout(function(){
      const list=w.document.getElementById("kol-so-list");
      chk("tim SO: hien SO doi ung + GBS SO chua co SO doi ung kem ly do", !list.hidden&&/SAL-ORD-2026-00156/.test(list.innerHTML)&&/chưa có dòng phí EC/.test(list.innerHTML));
      list.querySelector("[data-i]").click();
      chk("chon SO: luu SO doi ung + brand theo SO", w.ContractReview.state.draft.sales_order==="SAL-ORD-2026-00156"&&w.ContractReview.state.draft.brand==="FCV");
      w.ContractReviewKOL.pickCreator({name:"SUP-1",supplier_name:"Nguyễn Thanh Phụng",ec_cr_type:"Cá nhân"});
      setTimeout(function(){
        const at=w.document.querySelector('[data-model="amount_type"]');
        const opts=Array.from(at.options).map(o=>o.value).filter(Boolean);
        chk("creator ca nhan chi cho kieu nhap ca nhan", opts.join("|")==="Thực nhận sau TNCN|Gross trước TNCN" && !!w.document.querySelector('[data-model="pit_rate"]'));
        at.value="Thực nhận sau TNCN"; fire(w,at,"change");
        const am=w.document.querySelector('[data-model="amount_input"]'); am.value="9000000"; fire(w,am,"input");
        setTimeout(function(){
          chk("so tien lay tu server (kol_preview_amounts)", calls.some(x=>/^kol_preview_amounts .*"creator_type":"Cá nhân"/.test(x)) && /Chín triệu đồng chẵn/.test(w.document.getElementById("kol-amounts").innerHTML));
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
              detailPart();
            },150); },150);
          },150);
        },400);
      },100);
    },400);
  },100);
});

function detailPart(){
  const w2=make("https://x/approvals/contract-review?id=EC-CTR-2026-00100");
  wait(w2,function(){ return w2.document.getElementById("kol-detail"); },function(){
    const b=w2.document.getElementById("ctr-body").innerHTML;
    chk("chi tiet: khoi KOL + canh bao doanh thu + so HD", /Hợp đồng KOL\/KOC/.test(b)&&/vượt doanh thu EC/.test(b)&&/15032026\/HDDV/.test(b));
    chk("chi tiet: AI QC hien so lieu lech + dieu khoan rui ro", /Không thấy trong tệp/.test(b)&&/Bỏ điều khoản phạt/.test(b)&&/Thanh toán 100% trước/.test(b));
    chk("chi tiet: BBNT + tran chi + nut tao BBNT", /Livestream T12/.test(b)&&/Được phép chi/.test(b)&&/Đánh dấu đã gửi ký|Hoàn tất…/.test(b)&&!/kol-accf-/.test(b)&&/data-kol="addacc"/.test(b)&&/data-kol="doneacc"/.test(b));
    chk("da duyet: khong con nut tao lai hop dong", !/data-kol="gen"/.test(b));
    chk("BBNT: nut Hoan tat mo modal (khong o tep trong bang) + nut Xoa dot nhap", /data-kol="delacc"/.test(b));
    creatorsTab();
  });
}
function creatorsTab(){
  const w3=make("https://x/approvals/contract-review?tab=creators");
  wait(w3,function(){ return /Trần B/.test((w3.document.getElementById("ctr-body")||{}).innerHTML||""); },function(){
    const b=w3.document.getElementById("ctr-body").innerHTML;
    chk("tab Creator: danh sach chua co ma + o nhap ma + xuat CSV", /Trần B/.test(b)&&/data-misa="SUP-2"/.test(b)&&/kol-csv/.test(b));
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
      w4.document.querySelector('[data-kol="editcr"]').click();
      setTimeout(function(){
        const ov=w4.document.querySelector(".ec-ctr-overlay");
        chk("sua creator: dien san MST / SDT / email", ov&&ov.querySelector("#kc-tax_id").value==="0101234567"&&ov.querySelector("#kc-ec_phone").value==="0912345678");
        ov.querySelector("#kc-ec_phone").value="0988000111";
        ov.querySelector("[data-ok]").click();
        setTimeout(function(){
          const up=calls.filter(x=>/^kol_update_creator/.test(x)).pop()||"";
          chk("sua creator: chi gui truong da doi", /"data":"\{\\"ec_phone\\":\\"0988000111\\"\}"/.test(up));
          done();
        },150);
      },150);
    },150);
  });
}
