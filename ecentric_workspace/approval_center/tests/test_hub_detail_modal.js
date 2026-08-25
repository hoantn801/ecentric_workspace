/* Popup chi tiết trên trang "Tất cả yêu cầu" (jsdom):
 *   node ecentric_workspace/approval_center/tests/test_hub_detail_modal.js <đường-dẫn-repo>
 * Bảo đảm: bỏ cột Thao tác ngoài danh sách, bấm dòng mở popup, popup nạp qua
 * reporting.actions.get_request_detail, và thao tác nằm TRONG popup rồi tự đóng + tải lại.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs");
const REPO=process.argv[2]||".";
const html=fs.readFileSync(REPO+"/ecentric_workspace/approval_center/ui/all_requests/main_section.html","utf8");
const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,resources:"usable",url:"https://x/approvals/all-requests"});
const w=dom.window;
const rows=[{name:"EC-APR-1",type:"Asset Request",approval_type:"ASSET_REQUEST",status:"Pending",status_label:"Pending",
  submitted_at:"2026-08-25 10:00:00",department:"Ops",current_level:2,current_level_name:"Direct Manager",
  detail_route:"/approvals/asset-request?id=EC-ASSR-6",requester:"a@e.c",requester_info:{name:"A B"},sent_to:[],can_approve:true}];
const detail={ business:{request_title:"Return Laptop", requested_by:"vy@e.c", department:"E-commerce - EC"},
  approval:{current_level:2, approval_status:"Pending"},
  levels:[{level_no:1,level_name:"Đã gửi",level_status:"Completed"},{level_no:2,level_name:"Direct Manager Review",level_status:"In Progress"},{level_no:3,level_name:"Operation Review"}],
  display_fields:[{label:"Loại yêu cầu",value:"Return old asset",fieldtype:"Select"},{label:"Số lượng",value:1,fieldtype:"Int"}],
  attachments:[{file_name:"bao-gia.pdf",file_url:"/private/files/bao-gia.pdf"}],
  timeline:[{action:"Đã gửi",actor:"vy@e.c",creation:"2026-08-25 09:00:00"}],
  capabilities:{can_approve:true,can_reject:true,can_request_information:true},
  type_title:"Asset Request", detail_route:"/approvals/asset-request?id=EC-ASSR-6" };
w.frappe={call:function(o){
  if(/get_filter_options/.test(o.method)) return Promise.resolve({message:{scope_mode:"admin",categories:[],departments:[],types:[],statuses:[]}});
  if(/list_requests/.test(o.method)) return Promise.resolve({message:{rows:rows,total:1}});
  if(/get_request_detail/.test(o.method)){ w.__detailArgs=o.args; return Promise.resolve({message:detail}); }
  if(/actions\./.test(o.method)){ w.__action=o; return Promise.resolve({message:{ok:true}}); }
  return Promise.resolve({message:{}});
}};
w.prompt=()=> "ly do test";
let t=0;(function poll(){ if(w.ApprovalAll){ w.ApprovalAll.boot(); setTimeout(function(){
  const c={};
  const body=w.document.getElementById("apl-body").innerHTML;
  c["bo cot Thao tac"]= !/Thao tác/.test(body) && !/data-qa=/.test(body);
  const tr=w.document.querySelector("#apl-body tbody tr[data-req]");
  c["row co data-req"]= !!tr;
  tr.click();
  setTimeout(function(){
    const ov=w.document.getElementById("apl-ov");
    c["mo popup"]= ov && !ov.hidden;
    c["goi API chi tiet dung ma"]= w.__detailArgs && w.__detailArgs.request_name==="EC-APR-1";
    const box=ov.querySelector(".ec-apl-modal").innerHTML;
    c["hien tieu de + ma"]= /Return Laptop/.test(box) && /EC-APR-1/.test(box);
    c["hien tien trinh"]= /Direct Manager Review/.test(box) && /ec-apl-step cur/.test(box);
    c["hien thong tin + dinh kem + lich su"]= /Return old asset/.test(box) && /bao-gia\.pdf/.test(box) && /Lịch sử/.test(box);
    c["co nut thao tac trong popup"]= /data-a="approve"/.test(box) && /data-a="reject"/.test(box) && /data-a="info"/.test(box);
    c["co link mo trang day du"]= /Mở trang đầy đủ/.test(box);
    // bấm Duyệt trong popup
    ov.querySelector('[data-a="approve"]').click();
    setTimeout(function(){
      c["duyet goi API xuyen form"]= w.__action && /actions\.approve/.test(w.__action.method) && w.__action.args.request_name==="EC-APR-1";
      c["popup dong sau thao tac"]= w.document.getElementById("apl-ov").hidden;
      let ok=true;Object.keys(c).forEach(k=>{console.log((c[k]?"PASS":"FAIL")+" - "+k); if(!c[k])ok=false;});
      console.log(ok?"ALL_PASS":"SOME_FAIL");
    },120);
  },200);
},150); return;} if(t++>60){console.log("not ready");return;} setTimeout(poll,20);})();
