/* Bảng + thanh lọc trang "Tất cả yêu cầu" (jsdom):
 *   node ecentric_workspace/approval_center/tests/test_hub_table_filters.js <đường-dẫn-repo>
 * Bảo đảm: mỗi ô một dòng có tooltip đầy đủ, cột kéo giãn được và nhớ bề rộng,
 * bộ lọc tự áp dụng khi đổi (không còn nút "Áp dụng").
 */
const {JSDOM}=require("jsdom"); const fs=require("fs"); const path=require("path");
const REPO=process.argv[2]||path.join(__dirname,"..","..","..");
const FILE=path.join(REPO,"ecentric_workspace/approval_center/ui/all_requests/main_section.html");
const html=fs.readFileSync(FILE,"utf8");
if(/id="apl-apply"/.test(html)) throw new Error('Van con nut "Ap dung" - bo loc chua tu ap dung');
if(!/table-layout:fixed/.test(html)) throw new Error("Bang thieu table-layout:fixed -> khong khoa duoc be rong cot");
const tdRule=(html.match(/#ec-apl-root tbody td[^{]*\{[^}]*\}/)||[""])[0];
if(!/white-space:nowrap/.test(tdRule) || !/text-overflow:ellipsis/.test(tdRule))
  throw new Error("Rule cho tbody td thieu nowrap/ellipsis -> chu se xuong dong nhieu hang: "+tdRule);

const store={};
const dom=new JSDOM(html,{runScripts:"dangerously",pretendToBeVisual:true,url:"https://x/approvals/all-requests"});
const w=dom.window;
Object.defineProperty(w,"localStorage",{value:{
  getItem:k=>(k in store?store[k]:null), setItem:(k,v)=>{store[k]=String(v);}, removeItem:k=>{delete store[k];}}});
const rows=[{name:"EC-APR-2026-00080",type:"Asset Request",approval_type:"ASSET_REQUEST",status:"Pending",
  status_label:"Pending",submitted_at:"2026-08-25 18:21:00",department:"E-commerce Operation - EC",
  current_level:1,current_level_name:"Direct Manager Review",detail_route:"/x",requester:"vy@e.c",
  requester_info:{name:"Vy Nguyen Ngoc Tuong",user:"vy@e.c"},
  sent_to:[{name:"Phuc Tran",user:"p@e.c"},{name:"Dong Diep",user:"d@e.c"}]}];
let calls=[];
w.frappe={call:function(o){
  if(/get_filter_options/.test(o.method)) return Promise.resolve({message:{scope_mode:"admin",
    categories:["IT"],departments:["Media - EC"],types:[{code:"ASSET_REQUEST",title:"Asset"}],statuses:["Pending"]}});
  if(/list_requests/.test(o.method)){ calls.push(o.args); return Promise.resolve({message:{rows:rows,total:1}}); }
  return Promise.resolve({message:{}});
}};
const c={}; let failed=0;
function chk(k,v){ c[k]=!!v; if(!v) failed++; }
let t=0;(function poll(){ if(!w.ApprovalAll){ if(t++>60){console.log("not ready");process.exit(1);} return setTimeout(poll,20); }
w.ApprovalAll.boot();
setTimeout(function(){
  const table=w.document.querySelector("#apl-body table");
  chk("bang co colgroup khoa be rong", !!table.querySelector("colgroup col"));
  const tds=table.querySelectorAll("tbody td");
  chk("moi o co tooltip day du", tds[6].getAttribute("title")==="E-commerce Operation - EC"
      && tds[7].getAttribute("title")==="Direct Manager Review" && tds[1].getAttribute("title")==="EC-APR-2026-00080");
  chk("cot nguoi gui tooltip la ten", tds[4].getAttribute("title")==="Vy Nguyen Ngoc Tuong");
  chk("cot nguoi nhan tooltip liet ke ten", tds[5].getAttribute("title")==="Phuc Tran, Dong Diep");
  chk("o trong hien dau gach", w.ApprovalAll.render && tds[7].getAttribute("title")!=="");
  const th=table.querySelectorAll("thead th")[1], grip=th.querySelector(".rs");
  chk("moi cot co tay keo", !!grip && table.querySelectorAll("thead th .rs").length===9);
  // kéo cột "Mã" rộng thêm 40px
  Object.defineProperty(th,"offsetWidth",{value:158,configurable:true});
  grip.dispatchEvent(new w.MouseEvent("mousedown",{clientX:200,bubbles:true}));
  w.document.dispatchEvent(new w.MouseEvent("mousemove",{clientX:240,bubbles:true}));
  w.document.dispatchEvent(new w.MouseEvent("mouseup",{bubbles:true}));
  chk("keo la doi be rong cot", th.style.width==="198px");
  chk("nho be rong cho lan sau", JSON.parse(store["ec_apl_colw"]||"[]")[1]===198);

  calls=[];
  const sel=w.document.getElementById("f-department");
  chk("select co gan tu ap dung", typeof sel.onchange==="function");
  sel.value="Media - EC"; if(typeof sel.onchange==="function") sel.onchange();
  chk("doi bo loc la tu tai lai", calls.length===1
      && JSON.parse(calls[0].filters||"{}").department==="Media - EC");
  chk("hien nut xoa loc khi dang loc", !w.document.getElementById("apl-reset").hidden);

  calls=[];
  const q=w.document.getElementById("f-search");
  q.value="laptop"; q.dispatchEvent(new w.Event("input"));
  chk("go phim chua goi ngay", calls.length===0);
  setTimeout(function(){
    chk("go xong 400ms moi goi 1 lan", calls.length===1 && calls[0].search==="laptop");
    w.document.getElementById("apl-reset").click();
    setTimeout(function(){
      chk("xoa loc thi tra ve rong", !w.document.getElementById("f-department").value
          && !w.document.getElementById("f-search").value
          && w.document.getElementById("apl-reset").hidden);
      Object.keys(c).forEach(k=>console.log((c[k]?"PASS":"FAIL")+" - "+k));
      console.log(failed?"SOME_FAIL":"ALL_PASS");
      process.exit(failed?1:0);
    },60);
  },520);
},260); })();
