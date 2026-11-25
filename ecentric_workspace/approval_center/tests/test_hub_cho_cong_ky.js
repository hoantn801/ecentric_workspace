/* Cua so xem nhanh "Tat ca yeu cau" khi buoc "Duyet & Ky" dang cho cong (25/11/2026, anh Lam, 00135):
 *   node ecentric_workspace/approval_center/tests/test_hub_cho_cong_ky.js <duong-dan-repo>
 * Server (get_request_detail) da tat can_approve + tra esign_wait -> cua so KHONG co nut "Duyet & Ky",
 * co dong "dang cho CMC xac nhan", tu mo lai; cong xac nhan xong -> het dong cho + bao mot lan.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const html=fs.readFileSync(path.join(REPO,"ecentric_workspace/approval_center/ui/all_requests/main_section.html"),"utf8");
const timers=[];
const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://x/approvals/all-requests",
  beforeParse(win){ const real=win.setTimeout.bind(win);
    win.setTimeout=function(fn,ms){ if(ms===5000||ms===30000){ timers.push({fn:fn,ms:ms}); return 9999+timers.length; } return real(fn,ms); }; }});
const w=dom.window;
const row={name:"EC-APR-9",type:"Contract Review",approval_type:"CONTRACT_REVIEW",status:"Pending",status_label:"Pending",
  submitted_at:"2026-11-24 16:48:00",department:"Ops",current_level:5,current_level_name:"CEO Review",
  detail_route:"/approvals/contract-review?id=EC-CTR-1",requester:"h@e.c",requester_info:{name:"Hoan"},sent_to:[],can_approve:true,requires_signature:true};
function det(wait){ return { business:{request_title:"HĐ KOL thử",requested_by:"h@e.c",creation:"2026-11-24 16:48:00"},
  approval:{name:"EC-APR-9",current_level:wait?5:5,approval_status:"Pending"}, levels:[{level_no:5,level_name:"CEO Review"}],
  display_fields:[], attachments:[], timeline:[], business_doctype:"EC Contract Review Request", business_name:"EC-CTR-1",
  capabilities: wait?{can_approve:false,can_reject:false,can_request_information:false,requires_signature:true}
                    :{can_approve:false,requires_signature:false},
  esign_wait: wait?{status:"Accepted",accepted_at:"2026-11-25 14:05:10",manual:false}:undefined,
  type_title:"Contract Review" }; }
let waitNow=true, nDetail=0;
w.alert=function(){};
w.frappe={call:function(o){
  if(/get_filter_options/.test(o.method)) return Promise.resolve({message:{scope_mode:"admin",categories:[],departments:[],types:[],statuses:[]}});
  if(/list_requests/.test(o.method)) return Promise.resolve({message:{rows:[row],total:1}});
  if(/get_request_detail/.test(o.method)){ nDetail++; return Promise.resolve({message:det(waitNow)}); }
  return Promise.resolve({message:{}});
}};
let failed=0; const c={};
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
function tick(fn){ setTimeout(fn,150); }
let t=0;(function poll(){ if(!w.ApprovalAll){ if(t++>60){console.log("not ready");process.exit(1);} return setTimeout(poll,20); }
w.ApprovalAll.boot(); tick(function(){
  w.ApprovalAll.openDetail("EC-APR-9");
  tick(function(){
    const box=w.document.querySelector("#ec-apl-ov .ec-apl-wrap"), h=box?box.innerHTML:"";
    chk("co dong dang cho cong", /ec-apl-wait/.test(h) && /đang chờ CMC xác nhận/.test(h) && /14:05/.test(h));
    chk("khong co nut Duyet & Ky", !/data-a="approve_sign"/.test(h) && !/data-a="approve"/.test(h));
    chk("khong co nut Tu choi / Yeu cau bo sung", !/data-a="reject"/.test(h) && !/data-a="info"/.test(h));
    chk("hen gio tu mo lai 5s", timers.length===1 && timers[0].ms===5000);
    waitNow=false; const before=nDetail; timers.shift().fn();
    tick(function(){
      const h2=w.document.querySelector("#ec-apl-ov .ec-apl-wrap").innerHTML;
      chk("tu mo lai chi tiet", nDetail===before+1);
      chk("cong xac nhan xong -> het dong cho", !/ec-apl-wait/.test(h2));
      const toast=w.document.getElementById("ec-apl-toast");
      chk("bao cong da xac nhan", toast && /Cổng ký đã xác nhận/.test(toast.textContent));
      chk("khong hen gio nua", timers.length===0);
      console.log(JSON.stringify(c,null,1)); console.log(failed?"FAILED "+failed:"ALL_PASS"); process.exit(failed?1:0);
    });
  });
}); })();
