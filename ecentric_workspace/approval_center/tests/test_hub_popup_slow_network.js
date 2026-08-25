/* Popup khi API chậm (jsdom):
 *   node ecentric_workspace/approval_center/tests/test_hub_popup_slow_network.js <repo>
 * API nhanh thì popup hiện thẳng nội dung thật (test kia lo). Chậm hơn ngưỡng thì PHẢI có
 * khung chờ, nếu không người dùng bấm mà màn hình đứng im, tưởng hỏng.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const html=fs.readFileSync(path.join(REPO,"ecentric_workspace/approval_center/ui/all_requests/main_section.html"),"utf8");
const ms=(html.match(/SKELETON_AFTER_MS\s*=\s*(\d+)/)||[])[1];
if(!ms) throw new Error("Khong tim thay nguong hien khung cho (SKELETON_AFTER_MS)");
if(Number(ms)<80 || Number(ms)>600) throw new Error("Nguong khung cho bat thuong: "+ms);
// hằng số phải được DÙNG ở chỗ hẹn giờ, không phải khai báo cho có
if(!/\},\s*SKELETON_AFTER_MS\s*\)/.test(html))
  throw new Error("Cho hien khung cho khong dung SKELETON_AFTER_MS -> co the dang mo ngay lap tuc");
const DELAY=Number(ms)+250;

const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://x/approvals/all-requests"});
const w=dom.window;
const rows=[{name:"EC-APR-9",type:"Asset Request",approval_type:"ASSET_REQUEST",status:"Pending",
  status_label:"Pending",submitted_at:"2026-08-25 10:00:00",department:"Ops",current_level:1,
  current_level_name:"Duyệt",detail_route:"/x",requester:"a@e.c",requester_info:{name:"An Le"},sent_to:[]}];
const detail={business:{request_title:"Hồ sơ chậm",requested_by:"a@e.c",creation:"2026-08-25 09:00:00"},
  approval:{current_level:1,approval_status:"Pending"},levels:[{level_no:1,level_name:"Duyệt"}],
  display_fields:[{label:"Số lượng",value:1,fieldtype:"Int"}],attachments:[],
  timeline:[{action:"Submitted",actor:"a@e.c",creation:"2026-08-25 09:00:00"}],
  capabilities:{},type_title:"Asset Request",detail_route:"/x"};
w.frappe={call:function(o){
  if(/get_filter_options/.test(o.method)) return Promise.resolve({message:{scope_mode:"admin",categories:[],departments:[],types:[],statuses:[]}});
  if(/list_requests/.test(o.method)) return Promise.resolve({message:{rows:rows,total:1}});
  if(/get_request_detail/.test(o.method))
    return new Promise(res=>setTimeout(()=>res({message:detail}), DELAY));
  return Promise.resolve({message:{}});
}};
const c={}; let failed=0;
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
let t=0;(function poll(){ if(!w.ApprovalAll){ if(t++>60){console.log("not ready");process.exit(1);} return setTimeout(poll,20); }
w.ApprovalAll.boot();
setTimeout(function(){
  w.document.querySelector("#apl-body tbody tr[data-req]").click();
  setTimeout(function(){   // đã qua ngưỡng, chưa có dữ liệu
    const ov=w.document.getElementById("ec-apl-ov");
    chk("mang cham: co hien khung cho", ov && !ov.hidden);
    chk("khung cho co vet xam o than", !!w.document.querySelector('[data-h="body"].loading'));
    chk("khung cho co san the phai", !!w.document.querySelector(".ec-apl-aside .ec-apl-skel-li"));
    chk("khung cho khong o che do hep",
        !w.document.querySelector(".ec-apl-wrap").classList.contains("solo"));
    chk("khung cho: tieu de la vet xam khong phai chu tam",
        !!w.document.querySelector('[data-h="title"] .ec-apl-skel'));
    const cardRef=w.document.querySelector(".ec-apl-modal");
    const asideRef=w.document.querySelector(".ec-apl-aside");
    setTimeout(function(){  // dữ liệu về
      chk("du lieu ve: khong dung lai the",
          w.document.querySelector(".ec-apl-modal")===cardRef
          && w.document.querySelector(".ec-apl-aside")===asideRef);
      chk("du lieu ve: bo trang thai cho",
          !w.document.querySelector('[data-h="body"].loading')
          && !w.document.querySelector(".ec-apl-skel-li"));
      chk("du lieu ve: hien tieu de that",
          w.document.querySelector('[data-h="title"]').textContent.trim()==="Hồ sơ chậm");
      Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k));
      console.log(failed?"SOME_FAIL":"ALL_PASS");
      process.exit(failed?1:0);
    }, 400);
  }, Number(ms)+80);
}, 200); })();
