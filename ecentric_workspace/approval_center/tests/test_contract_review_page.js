/* Trang /approvals/contract-review (jsdom):
 *   node ecentric_workspace/approval_center/tests/test_contract_review_page.js <repo>
 * Khoá: form đủ trường hợp đồng, chọn "sẵn có" hiện ô tìm hợp đồng gốc, chọn gốc thì
 * tự điền + trường sửa tô vàng + preview đổi sang "3 cấp (CEO nhận CC)", validate chặn
 * thiếu trường, deadline hiển thị đúng 1/3 ngày làm việc.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const html=fs.readFileSync(path.join(REPO,"ecentric_workspace/approval_center/features/contract_review/ui/main_section.html"),"utf8");
const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://x/approvals/contract-review"});
const w=dom.window;
const boot={tabs:{},context:{user:"vy@e.c",employee_name:"Vy Nguyen",department:"E-commerce - EC"},
  form_options:{brands:[{value:"FES-VN",label:"FES-VN — Cafepho Group"},{value:"AND-VN",label:"AND-VN — Andros"}],
    departments:[{value:"E-commerce - EC",label:"E-commerce"},{value:"Media - EC",label:"Media"}],
    contract_types:["Purchase / Mua vào (EC)","Sales / Bán ra (EC)","Service / Dịch vụ (GBSxBrand)"],
    request_types:["Template from EC / Mẫu theo khung EC","Template from partner / Mẫu theo khung đối tác","New contract template / Hợp đồng mới"]}};
const prevContract={name:"EC-CTR-2026-00001",request_title:"HĐ Booking KOL FES",contract_type:"Sales / Bán ra (EC)",
  request_type:"Template from EC / Mẫu theo khung EC",brand:"FES-VN",justification:"Booking KOL",
  contract_value:100000000,contract_start_date:"2026-01-01",contract_end_date:"2026-06-30",
  request_details:"Điều khoản cũ"};
w.frappe={call:function(o){
  if(/get_bootstrap/.test(o.method)) return Promise.resolve({message:boot});
  if(/search_previous_contracts/.test(o.method))
    return Promise.resolve({message:{rows:[{value:"EC-CTR-2026-00001",label:"EC-CTR-2026-00001 — HĐ Booking KOL FES (FES-VN)"}]}});
  if(/get_previous_contract/.test(o.method)) return Promise.resolve({message:prevContract});
  return Promise.resolve({message:{}});
}};
const c={}; let failed=0;
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
function done(){ Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k));
  console.log(failed?"SOME_FAIL":"ALL_PASS"); process.exit(failed?1:0); }
let t=0;(function poll(){ if(!w.ContractReview){ if(t++>80){console.log("not ready");process.exit(1);} return setTimeout(poll,25); }
setTimeout(function(){
  const b=w.document.getElementById("ctr-body").innerHTML;
  chk("form co du truong hop dong", /contract_type/.test(b)&&/contract_value/.test(b)
      &&/request_details/.test(b)&&/Legal entity/.test(b));
  chk("brand co eCentric cho backoffice + brand list", /eCentric \(backoffice\)/.test(b)&&/FES-VN — Cafepho Group/.test(b));
  chk("department mac dinh theo nguoi gui, doi duoc", /data-model="department"/.test(b)&&/E-commerce/.test(b));
  chk("mac dinh la hop dong MOI: preview 4 cap + 3 ngay", /CEO duyệt/.test(b)&&/3 ngày làm việc/.test(b)
      && !/ctr-prev-q/.test(b));
  // validate chặn thiếu trường
  const errs=w.ContractReview.validateSubmit();
  chk("validate chan thieu truong", !!errs && !!errs.contract_type && !!errs.contract_value);
  // chuyển sang Existing
  const kind=w.document.querySelector('[data-model="request_kind"]');
  kind.value="Existing"; kind.dispatchEvent(new w.Event("change"));
  setTimeout(function(){
    const b2=w.document.getElementById("ctr-body").innerHTML;
    chk("existing: hien o tim hop dong goc + 1 ngay", /ctr-prev-q/.test(b2)&&/1 ngày làm việc/.test(b2));
    chk("existing chua chon goc -> van 4 cap", !w.ContractReview.willSkipCEO());
    chk("validate doi chon goc", !!(w.ContractReview.validateSubmit()||{}).previous_request);
    // chọn hợp đồng gốc
    w.ContractReview.pickPrev("EC-CTR-2026-00001");
    setTimeout(function(){
      const st=w.ContractReview.state.draft;
      chk("chon goc: tu dien form", st.contract_type===prevContract.contract_type
          && String(st.contract_value)===String(prevContract.contract_value)
          && st.brand==="FES-VN");
      chk("chua sua gi -> bo cap CEO (chi dieu chinh)", w.ContractReview.willSkipCEO());
      const b3=w.document.getElementById("ctr-body").innerHTML;
      chk("preview doi sang CC CEO", /CEO nhận thông báo, không cần duyệt/.test(b3));
      // sửa số tiền -> vẫn bỏ CEO, trường tô vàng
      const val=w.document.querySelector('[data-model="contract_value"]');
      val.value="200000000"; val.dispatchEvent(new w.Event("input"));
      setTimeout(function(){
        chk("doi so tien -> van bo CEO", w.ContractReview.willSkipCEO()
            && w.ContractReview.changedFields().indexOf("contract_value")>=0);
        const b4=w.document.getElementById("ctr-body").innerHTML;
        chk("truong sua duoc to vang", /hl-changed/.test(b4)&&/Giá trị hợp đồng/.test(b4));
        // đổi brand -> mất quyền bỏ cấp
        const br=w.document.querySelector('[data-model="brand"]');
        br.value="AND-VN"; br.dispatchEvent(new w.Event("change"));
        setTimeout(function(){
          chk("doi brand -> du 4 cap tro lai", !w.ContractReview.willSkipCEO());
          const b5=w.document.getElementById("ctr-body").innerHTML;
          chk("preview quay lai 4 cap", !/CEO nhận thông báo/.test(b5) && /CEO duyệt/.test(b5));
          done();
        },150);
      },150);
    },200);
  },150);
},400); })();
