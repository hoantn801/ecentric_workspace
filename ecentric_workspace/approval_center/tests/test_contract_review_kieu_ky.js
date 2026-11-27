/* Kieu ky cua doi tac tren /approvals/contract-review (jsdom), PO 27/11/2026 (KOL hay chi ky anh):
 *   node ecentric_workspace/approval_center/tests/test_contract_review_kieu_ky.js <repo>
 * Khoa: quy trinh co doi tac ky tren cong thi co o chon "Kieu ky cua doi tac" lay danh sach TU SERVER
 * (form_options.esign_partner_sign_types), mac dinh "Mac dinh cua cong ky"; chon thi vao ban nhap;
 * quy trinh khong co doi tac thi khong hien; chi tiet phieu ghi "Kieu ky: Ky anh".
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const html=fs.readFileSync(path.join(REPO,"ecentric_workspace/approval_center/features/contract_review/ui/main_section.html"),"utf8");
const LABOR="Labor / Hợp đồng lao động (EC)";
const boot={tabs:{},context:{user:"vy@e.c",employee_name:"Vy",department:"E-commerce - EC"},
  form_options:{brands:[{value:"FCV",label:"FCV"}],departments:[{value:"E-commerce - EC",label:"E-commerce"}],
    contract_types:["Purchase / Mua vào (EC)",LABOR],request_kinds:["Existing","New"],
    request_types:["Template from EC / Mẫu theo khung EC"],
    esign_flows:[["hd_lao_dong","Hợp đồng lao động (WF03)"],["khong_ky_cong","Không ký trên cổng"]],
    esign_flows_with_partner:["kol_wf09","hd_lao_dong"],esign_flow_defaults:[LABOR+"|hd_lao_dong"],
    esign_partner_sign_types:[["image","Ký ảnh"],["token","USB Token"],["esign","eSign (ký từ xa)"],["vnetid","VNeID"],["ekyc","eKYC"]]}};
const c={}; let failed=0;
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
function done(){ Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k));
  console.log(failed?"SOME_FAIL":"ALL_PASS"); process.exit(failed?1:0); }
const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://x/approvals/contract-review"});
const w=dom.window;
w.frappe={call:function(o){ if(/get_bootstrap/.test(o.method)) return Promise.resolve({message:boot});
  return Promise.resolve({message:{}}); }};
let t=0;(function poll(){ if(!w.ContractReview||!w.document.querySelector('[data-model="contract_type"]')){ if(t++>120){console.log("not ready");process.exit(1);} return setTimeout(poll,25); }
  const doc=w.document;
  chk("chua chon loai co doi tac ky: khong co o kieu ky", !doc.querySelector('[data-model="partner_sign_type"]'));
  const ct=doc.querySelector('[data-model="contract_type"]'); ct.value=LABOR; ct.dispatchEvent(new w.Event("change",{bubbles:true}));
  setTimeout(function(){
    const sel=doc.querySelector('select[data-model="partner_sign_type"]');
    chk("quy trinh co doi tac: hien o kieu ky", !!sel);
    if(sel){
      const opts=[].map.call(sel.options,o=>o.value+"="+o.textContent);
      chk("lua chon lay tu server + mac dinh cua cong dung dau", opts.join("|")==="=Mặc định của cổng ký|image=Ký ảnh|token=USB Token|esign=eSign (ký từ xa)|vnetid=VNeID|ekyc=eKYC");
      chk("mac dinh chon 'Mac dinh cua cong ky'", sel.value==="");
      sel.value="image"; sel.dispatchEvent(new w.Event("change",{bubbles:true})); sel.dispatchEvent(new w.Event("input",{bubbles:true}));
      chk("chon Ky anh vao ban nhap", (w.ContractReview.state.draft||{}).partner_sign_type==="image");
    }
    done();
  },150);
})();
