/* Popup chi tiết trên trang "Tất cả yêu cầu" (jsdom):
 *   node ecentric_workspace/approval_center/tests/test_hub_detail_modal.js <đường-dẫn-repo>
 * Bảo đảm: bỏ cột Thao tác ngoài danh sách, bấm dòng mở popup, popup nạp qua
 * reporting.actions.get_request_detail, thao tác nằm TRONG popup, lý do nhập tại chỗ
 * (không dùng window.prompt) và sau khi duyệt thì nhảy sang hồ sơ kế tiếp.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const html=fs.readFileSync(path.join(REPO,"ecentric_workspace/approval_center/ui/all_requests/main_section.html"),"utf8");
// Kiểm tra tĩnh TRƯỚC khi dựng DOM: id lớp phủ do JS tạo phải trùng id được CSS tô.
// Lệch id thì popup mất position:fixed và rơi xuống cuối trang — đã xảy ra trên production.
const ovId=(html.match(/ov\.id\s*=\s*"([^"]+)"/)||[])[1];
if(!ovId) throw new Error("Không tìm thấy nơi JS đặt id cho lớp phủ popup");
if(html.indexOf("#"+ovId+"{")<0 && html.indexOf("#"+ovId+" {")<0)
  throw new Error('Lop phu JS tao id="'+ovId+'" nhung CSS khong co rule #'+ovId+' -> popup se mat position:fixed');
if(!new RegExp("#"+ovId+"\\{[^}]*position:fixed").test(html.replace(/\s*\n\s*/g,"")))
  throw new Error("Rule #"+ovId+" thieu position:fixed");
const wrapRule=(html.match(/\.ec-apl-wrap\{[^}]*\}/)||[""])[0].replace(/\s+/g," ");
if(!/margin:\s*auto/.test(wrapRule))
  throw new Error("Khung popup thieu margin:auto -> se dinh goc tren trai: "+wrapRule);
const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://x/approvals/all-requests"});
const w=dom.window;
function row(n,t){ return {name:n,type:"Asset Request",approval_type:"ASSET_REQUEST",status:"Pending",status_label:"Pending",
  submitted_at:"2026-08-25 10:00:00",department:"Ops",current_level:2,current_level_name:"Direct Manager",
  detail_route:"/approvals/asset-request?id=X",requester:"a@e.c",requester_info:{name:"An Le"},sent_to:[],can_approve:true,_t:t}; }
const rows=[row("EC-APR-1","Trả laptop"),row("EC-APR-2","Mua màn hình")];
const detailLean={ business:{request_title:"Xin cấp tài khoản",requested_by:"b@e.c",creation:"2026-08-25 08:00:00"},
  approval:{current_level:1,approval_status:"Pending"}, levels:[{level_no:1,level_name:"Duyệt"}],
  display_fields:[{label:"Số lượng",value:1,fieldtype:"Int"}], attachments:[], timeline:[],
  capabilities:{}, type_title:"System Request" };
const detail={ business:{request_title:"Trả lại laptop cũ",requested_by:"vy@e.c",department:"E-commerce - EC",creation:"2026-08-25 09:00:00"},
  approval:{current_level:2,approval_status:"Pending"},
  levels:[{level_no:1,level_name:"Đã gửi",level_status:"Completed"},{level_no:2,level_name:"Direct Manager"},{level_no:3,level_name:"Operation"}],
  display_fields:[{label:"Số tiền",value:2500000,fieldtype:"Currency"},{label:"Số lượng",value:1,fieldtype:"Int"},
                  {label:"Lý do",value:"Máy hỏng bàn phím",fieldtype:"Small Text"},
                  {label:"Loại tài sản",value:"Laptop",fieldtype:"Select"},{label:"Cấu hình",value:"Lenovo i5",fieldtype:"Data"},
                  {label:"Mục đích",value:"Trả máy",fieldtype:"Select"},{label:"Nhà cung cấp",value:"FPT",fieldtype:"Link"},
                  {label:"Dự án",value:"ERP",fieldtype:"Link"},{label:"Mức ưu tiên",value:"Cao",fieldtype:"Select"},
                  {label:"Ghi chú",value:"x",fieldtype:"Data"},{label:"Địa điểm",value:"HN",fieldtype:"Data"}],
  attachments:[{file_name:"bien-ban.pdf",file_url:"/private/files/bien-ban.pdf"}],
  timeline:[{action:"Approved",actor:"an.le",creation:"2026-08-25 09:30:00",comment:"OK"},
            {action:"Skipped",actor:"Administrator",creation:"2026-08-25 09:31:00"}],
  capabilities:{can_approve:true,can_reject:true,can_request_information:true},
  type_title:"Asset Request", detail_route:"/approvals/asset-request?id=X" };
let promptUsed=false;
w.prompt=function(){ promptUsed=true; return "x"; };
w.alert=function(){};
w.frappe={call:function(o){
  if(/get_filter_options/.test(o.method)) return Promise.resolve({message:{scope_mode:"admin",categories:[],departments:[],types:[],statuses:[]}});
  if(/list_requests/.test(o.method)) return Promise.resolve({message:{rows:rows,total:2}});
  if(/get_request_detail/.test(o.method)){ w.__detailFor=o.args.request_name;
    return Promise.resolve({message: w.__lean?detailLean:detail}); }
  if(/actions\./.test(o.method)){ w.__action=o; return Promise.resolve({message:{ok:true}}); }
  return Promise.resolve({message:{}});
}};
const c={}; let failed=0;
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
function tick(fn,ms){ setTimeout(fn,ms||120); }
let t=0;(function poll(){ if(!w.ApprovalAll){ if(t++>60){console.log("not ready");process.exit(1);} return setTimeout(poll,20); }
w.ApprovalAll.boot(); tick(function(){
  const body=w.document.getElementById("apl-body").innerHTML;
  chk("bo cot Thao tac ngoai danh sach", !/Thao tác/.test(body) && !/data-qa=/.test(body));
  const tr=w.document.querySelector("#apl-body tbody tr[data-req]");
  chk("row co data-req", !!tr);
  tr.click();
  // header phải hiện NGAY trong nhịp đồng bộ, trước khi API chi tiết kịp trả về
  const boxNow=w.document.querySelector(".ec-apl-wrap").innerHTML;
  chk("header dung ngay tu du lieu dong", /Asset Request/.test(boxNow) && /An Le/.test(boxNow)
      && /Chờ duyệt/.test(boxNow) && /ec-apl-skel/.test(boxNow));
  // Dòng danh sách không mang tiêu đề thật -> lúc chờ phải để vệt xám, KHÔNG điền tạm tên loại
  // rồi thay chữ (đổi chữ giữa chừng chính là cái nháy Hoàn thấy).
  const titleSlot=w.document.querySelector('[data-h="title"]');
  chk("cho tai: tieu de la vet xam, khong phai chu tam",
      !!titleSlot.querySelector(".ec-apl-skel") && titleSlot.textContent.trim()==="");
  // Giữ NGUYÊN phần tử thẻ khi dữ liệu về; dựng lại sẽ chạy lại hiệu ứng trượt -> nháy.
  w.__cardWhileLoading = w.document.querySelector(".ec-apl-modal");
  tick(function(){
    const ov=w.document.getElementById("ec-apl-ov");
    chk("mo popup", ov && !ov.hidden);
    // id của lớp phủ PHẢI khớp rule CSS, nếu không popup mất position:fixed và rơi xuống cuối trang
    chk("lop phu gan vao body", ov.parentNode===w.document.body);
    chk("lop phu co bien mau rieng", /#ec-apl-ov\{[^}]*--navy:/.test(html.replace(/\s*\n\s*/g,"")));
    chk("goi API chi tiet dung ma", w.__detailFor==="EC-APR-1");
    const box=ov.querySelector(".ec-apl-wrap"), h=box.innerHTML;
    chk("header gon: khong nhoi ma vao", /ec-apl-av/.test(h)&&/Trả lại laptop cũ/.test(h)
        && !/ec-apl-mh[\s\S]*?EC-APR-1[\s\S]*?ec-apl-mb/.test(h));
    chk("ma yeu cau nam duoi chan popup", /ec-apl-mf[\s\S]*class="code">EC-APR-1</.test(h));
    chk("lich su la THE RIENG ben phai", /<aside class="ec-apl-aside">[\s\S]*Lịch sử xử lý/.test(h)
        && !/ec-apl-modal[\s\S]*Lịch sử xử lý[\s\S]*<\/div><aside/.test(h));
    chk("co the phai thi bo gioi han hep", !box.classList.contains("solo"));
    chk("khong dung lai the khi du lieu ve",
        w.document.querySelector(".ec-apl-modal")===w.__cardWhileLoading);
    chk("tieu de that da thay vet xam",
        w.document.querySelector('[data-h="title"]').textContent.trim()==="Trả lại laptop cũ");
    chk("2 the la anh em, khong long nhau",
        box.children.length===2 && box.children[0].className==="ec-apl-modal"
        && box.children[1].className==="ec-apl-aside");
    chk("dai thong tin quyet dinh", /ec-apl-hl/.test(h)&&/2\.500\.000/.test(h)&&/Số lượng/.test(h));
    chk("ngay gui nam tren header", /Gửi 25\/08\/2026/.test(h));
    chk("nhan trang thai tren header", /class="pill Pending"/.test(h));
    chk("mo ta dai trai ngang", /wide/.test(h));
    chk("hien du truong, khong gap", !/Xem thêm/.test(h)&&/Địa điểm/.test(h)&&/Mức ưu tiên/.test(h)
        &&!/hidden/.test(h.replace(/id="apl-note"[^>]*hidden[^>]*/,"")));
    chk("tieu diem nam trong popup", w.document.activeElement===box);
    chk("chi the trai co chan nut", box.querySelectorAll(".ec-apl-mf").length===1
        && box.querySelector(".ec-apl-aside .ec-apl-mf")===null);
    chk("ten nguoi gui thay cho email", /An Le/.test(h)&&!/vy@e\.c/.test(h));
    chk("stepper co buoc hien tai", /ec-apl-step cur/.test(h)&&/ec-apl-step done/.test(h)&&/Direct Manager/.test(h));
    chk("noi dung + dinh kem + lich su", /Máy hỏng bàn phím/.test(h)&&/bien-ban\.pdf/.test(h)&&/Lịch sử xử lý/.test(h));
    chk("khong co lich su thi 1 cot", true);
    chk("moc lich su dich sang tieng Viet", /Đã duyệt/.test(h)&&!/>Approved</.test(h)&&!/>Skipped</.test(h));
    chk("nut duyet/tu choi/bo sung", /class="btn approve"/.test(h)&&/class="btn reject"/.test(h)&&/data-a="info"/.test(h));
    chk("nut chuyen ho so ‹ ›", /data-step="-1"/.test(h)&&/data-step="1"/.test(h));
    chk("nut lui bi khoa o ho so dau", /data-step="-1"[^>]*disabled/.test(h));
    // Từ chối -> ô nhập tại chỗ, chặn rỗng, không dùng prompt
    box.querySelector('[data-a="reject"]').click();
    tick(function(){
      const note=box.querySelector("#apl-note");
      chk("tu choi mo o nhap trong popup", note && !note.hidden && !promptUsed);
      note.querySelector("#apl-note-ok").click();
      chk("chan gui khi ly do rong", !w.__action && !note.querySelector("#apl-note-err").hidden);
      note.querySelector("#apl-note-in").value=" thiếu biên bản ";
      note.querySelector("#apl-note-ok").click();
      tick(function(){
        chk("gui kem ly do da trim", w.__action && /actions\.reject/.test(w.__action.method)
             && w.__action.args.comment==="thiếu biên bản");
        chk("tu dong sang ho so ke tiep", w.__detailFor==="EC-APR-2");
        chk("chuyen ho so khong dung lai the",
            w.document.querySelector(".ec-apl-modal")===w.__cardWhileLoading);
        const tt=w.document.getElementById("ec-apl-toast");
        chk("bao ket qua sau thao tac", tt && !tt.hidden && /Đã từ chối EC-APR-1/.test(tt.textContent)
            && tt.getAttribute("aria-live")==="polite");
        w.__lean=true; w.ApprovalAll.openDetail("EC-APR-2");
        tick(function(){
          const g=w.document.querySelector(".ec-apl-wrap").innerHTML;
          chk("1 o le thi khong dung dai noi bat", !/ec-apl-hl/.test(g)&&/Số lượng/.test(g));
          chk("khong co dinh kem thi an muc", !/Đính kèm/.test(g));
          chk("khong co lich su thi an muc", !/Lịch sử xử lý/.test(g));
          chk("mot the thi bo gon be ngang", w.document.querySelector(".ec-apl-wrap").classList.contains("solo"));
          chk("khong co lich su thi khong dung the phai", !/ec-apl-aside/.test(g)
              && w.document.querySelector(".ec-apl-wrap").children.length===1);
          Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k));
          console.log(failed?"SOME_FAIL":"ALL_PASS");
          process.exit(failed?1:0);
        },160);
        return;
        Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k));
        console.log(failed?"SOME_FAIL":"ALL_PASS");
        process.exit(failed?1:0);
      },160);
    },120);
  },200);
},160); })();
