/* Khay (jsdom):  node ecentric_workspace/public/js/tests/test_ec_khay.js <duong-dan-repo>
 *
 * Kiem: ham PURE, pham vi chay (chi trang ERP co vo shell), kill switch, va luong xin nghi
 * tu cau chat -> the nhap -> bam Gui -> goi DUNG endpoint co san `ec_hr_leave_apply` voi
 * dung tham so. Mang la gia, nhung dieu phoi fetch/CSRF/Shadow DOM la that.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs");
const js=fs.readFileSync((process.argv[2]||".")+"/ecentric_workspace/public/js/ec_khay.bundle.js","utf8");
const c={}; const ok=(k,v)=>{c[k]=!!v;};

function mk(url, html, routes){
  const dom=new JSDOM(html,{runScripts:"outside-only",pretendToBeVisual:true,url:url});
  const w=dom.window; const log=[];
  w.fetch=(u,o)=>{ o=o||{}; const m=String(u).replace(/^\/api\/method\//,"").split("?")[0];
    let body=null; try{ body=o.body&&typeof o.body==="string"?JSON.parse(o.body):o.body; }catch(e){}
    log.push({m:m,method:o.method||"GET",body:body,headers:o.headers||{}});
    const h=routes[m]; const res=h?h(body):{status:404,j:{}};
    return Promise.resolve({ok:res.status<400,status:res.status,json:()=>Promise.resolve(res.j)}); };
  w.eval(js);
  return {w:w,log:log};
}
const tick=(n)=>new Promise(r=>setTimeout(r,n||30));
const shell='<aside data-ec-shell="1"></aside><main>trang</main>';

(async()=>{
  // ---- PURE
  const e0=mk("https://x/none","<p>x</p>",{}); const P=e0.w.__ecKhayPure;
  ok("viDate Thu Ba", P.viDate("2026-09-29")==="Thứ Ba 29/09/2026");
  ok("viDate chuoi la giu nguyen", P.viDate("abc")==="abc");
  ok("leaveRange nua ngay chieu", P.leaveRange({from_date:"2026-10-02",to_date:"2026-10-02",half_day:1,half_day_part:"afternoon"})==="Thứ Sáu 02/10/2026 (buổi chiều)");
  ok("leaveRange nhieu ngay", P.leaveRange({from_date:"2026-10-01",to_date:"2026-10-02",half_day:0})==="Thứ Năm 01/10/2026 → Thứ Sáu 02/10/2026");
  ok("tep >7MB bi chan", /7MB/.test(P.fileRefuse({name:"a.pdf",size:8*1024*1024},[])));
  ok("tep hop le", P.fileRefuse({name:"a.pdf",size:10},[])===null);
  ok("toi da 5 tep", !!P.fileRefuse({name:"a.pdf",size:10},[1,2,3,4,5]));
  const sm=JSON.stringify([JSON.stringify({message:"Ban da co don nghi trung khoang ngay nay: <b>HR-LAP-1</b>"})]);
  ok("loi that cua server", P.serverError({_server_messages:sm})==="Ban da co don nghi trung khoang ngay nay: HR-LAP-1");
  ok("lich su chi luot chu", JSON.stringify(P.historyOf([{role:"user",text:"a"},{role:"leave"},{role:"bot",text:"b"},{role:"typing"}]))===JSON.stringify([{role:"user",text:"a"},{role:"model",text:"b"}]));
  ok("ten model: gemini luong openai", P.modelLabel("gemini-3-8-flash-openai")==="Gemini 3.8 Flash");
  ok("ten model: gpt", P.modelLabel("gpt-6-luna")==="GPT-6 Luna");
  ok("ten model: grok", P.modelLabel("grok-4-7")==="Grok 4.7");
  ok("ten model: rong", P.modelLabel("")==="");
  ok("mdLite thoat HTML", P.mdLite("<i>x</i> **dam**")==="&lt;i&gt;x&lt;/i&gt; <b>dam</b>");
  ok("khong chay o /app", !P.shouldRun(new JSDOM(shell).window.document,"/app/todo"));
  ok("khong chay khi trang tu tu choi", !P.shouldRun(new JSDOM(shell+'<div data-ec-no-khay></div>').window.document,"/x"));
  ok("chay khi co vo shell", P.shouldRun(new JSDOM(shell).window.document,"/viec-cua-toi"));
  ok("chay khi co thanh tab nhan su", P.shouldRun(new JSDOM('<div class="ec-tabwrap"></div>').window.document,"/ec-hr/leave"));

  // ---- pham vi: trang khong co vo shell -> KHONG goi mang
  const e1=mk("https://x/khao-sat","<p>trang le</p>",{});
  await tick(); ok("trang ngoai ERP khong goi boot", e1.log.length===0 && !e1.w.document.getElementById("ec-khay-host"));

  // ---- kill switch
  const e2=mk("https://x/viec-cua-toi",shell,{"ecentric_workspace.platform.ai.khay.boot":()=>({status:200,j:{message:{enabled:false}}})});
  await tick(); ok("enabled:false thi khong ve gi", !e2.w.document.getElementById("ec-khay-host"));
  ok("enabled:false thi GIU chat cu", !e2.w.document.getElementById("ec-khay-retire-old-chat"));
  {
    const home=shell+'<button id="ec-chat-fab">cu</button><div id="ec-chat-panel"></div>';
    const eo=mk("https://x/",home,{"ecentric_workspace.platform.ai.khay.boot":()=>({status:200,j:{message:{enabled:true,name:"eC Mate",can_leave:true}}})});
    await tick(50);
    const cs=(id)=>eo.w.getComputedStyle(eo.w.document.getElementById(id)).display;
    ok("co eC Mate thi AN nut chat cu", cs("ec-chat-fab")==="none");
    ok("co eC Mate thi AN khung chat cu", cs("ec-chat-panel")==="none");
    ok("eC Mate van hien", !!eo.w.document.getElementById("ec-khay-host"));
    ok("an cu chi chen 1 lan", eo.w.__ecKhayPure.retireOldChat(eo.w.document)===false && eo.w.document.querySelectorAll("#ec-khay-retire-old-chat").length===1);
    const en=mk("https://x/",home,{"ecentric_workspace.platform.ai.khay.boot":()=>({status:200,j:{message:{enabled:false}}})});
    await tick(50);
    ok("khong co eC Mate thi chat cu van hien", en.w.getComputedStyle(en.w.document.getElementById("ec-chat-fab")).display!=="none");
  }

  // ---- luong xin nghi
  let token=0;
  const routes={
    "get_csrf":()=>({status:200,j:{message:{csrf_token:"T"+(++token)}}}),
    "ecentric_workspace.platform.ai.khay.boot":()=>({status:200,j:{message:{enabled:true,first_name:"Hoàn",can_leave:true,can_payment:true,payment_route:"/approvals/payment-request"}}}),
    "ecentric_workspace.platform.ai.khay.intent":(b)=>({status:200,j:{message:{action:"leave",reply:"Soạn xong",options:[],
      leave:{leave_type:"Annual Leave",from_date:"2026-09-29",to_date:"2026-09-29",half_day:0,half_day_date:"",half_day_part:"",reason:"việc gia đình",past:false}}}}),
    "ec_hr_leave_data":()=>({status:200,j:{message:{types:[{name:"Annual Leave",lwp:0,bal:7.5}]}}}),
    "ec_hr_leave_apply":(b)=> token<2 ? {status:400,j:{exc_type:"CSRFTokenError"}} : {status:200,j:{message:{name:"HR-LAP-2026-00099",days:1,status:"Open"}}}
  };
  const e3=mk("https://x/viec-cua-toi",shell,routes);
  await tick(50);
  const host=e3.w.document.getElementById("ec-khay-host"); ok("ve Khay tren trang ERP", !!host);
  const R=host.shadowRoot;
  R.querySelector(".fab").click(); await tick();
  ok("mo khung chat", !R.querySelector(".pan").hidden);
  ok("loi chao co ten + goi y", /Chào Hoàn/.test(R.querySelector(".ms").textContent) && R.querySelectorAll("[data-say]").length===3);
  R.querySelector("textarea").value="cho minh nghi mai nhe";
  R.querySelector("form").dispatchEvent(new e3.w.Event("submit",{cancelable:true})); await tick(80);
  const intentCall=e3.log.filter(x=>x.m==="ecentric_workspace.platform.ai.khay.intent")[0];
  ok("goi intent kem trang dang o", intentCall && intentCall.body.message==="cho minh nghi mai nhe" && intentCall.body.page==="/viec-cua-toi");
  ok("POST co CSRF tuoi", intentCall && intentCall.headers["X-Frappe-CSRF-Token"]==="T1");
  const card=R.querySelector(".card");
  ok("the don nghi hien loai + ngay", card && /Phép năm/.test(card.textContent) && /Thứ Ba 29\/09\/2026/.test(card.textContent));
  ok("so du phep tu ec_hr_leave_data", /7,5 ngày/.test(card.textContent));
  R.querySelector('[data-act="leave-send"]').click(); await tick(120);
  const applies=e3.log.filter(x=>x.m==="ec_hr_leave_apply");
  ok("CSRF hong thi xin token moi va thu lai DUNG mot lan", applies.length===2 && applies[1].headers["X-Frappe-CSRF-Token"]==="T2");
  ok("gui dung tham so cho ec_hr_leave_apply", applies[1] && applies[1].body.leave_type==="Annual Leave" && applies[1].body.from_date==="2026-09-29" && applies[1].body.to_date==="2026-09-29" && applies[1].body.reason==="việc gia đình");
  ok("the chuyen sang Da gui + ma don", /Đã gửi/.test(R.querySelector(".card").textContent) && /HR-LAP-2026-00099/.test(R.querySelector(".ms").textContent));
  ok("khong con nut Gui tren don da gui", !R.querySelector('[data-act="leave-send"]'));

  // ---- loi nghiep vu cua server hien nguyen van, nut gui lai duoc
  const r4=Object.assign({},routes,{"ec_hr_leave_apply":()=>({status:417,j:{_server_messages:sm}})});
  const e4=mk("https://x/viec-cua-toi",shell,r4); await tick(50);
  const R4=e4.w.document.getElementById("ec-khay-host").shadowRoot;
  R4.querySelector(".fab").click(); await tick();
  R4.querySelector("textarea").value="nghi mai";
  R4.querySelector("form").dispatchEvent(new e4.w.Event("submit",{cancelable:true})); await tick(80);
  R4.querySelector('[data-act="leave-send"]').click(); await tick(80);
  ok("loi trung ngay hien dung cau server", /trung khoang ngay nay: HR-LAP-1/.test(R4.querySelector(".note.bad")&&R4.querySelector(".note.bad").textContent));
  ok("con nut gui de thu lai", !!R4.querySelector('[data-act="leave-send"]'));

  // ---- ten tro ly + tro chuyen tra loi thang (khong goi tra cuu)
  const r5=Object.assign({},routes,{
    "ecentric_workspace.platform.ai.khay.boot":()=>({status:200,j:{message:{enabled:true,name:"eC Mate",first_name:"Hoàn",can_leave:true,can_payment:false}}}),
    "ecentric_workspace.platform.ai.khay.intent":()=>({status:200,j:{message:{action:"answer",needs_data:false,reply:"Chào bạn, mình đây!",options:[],model:"gemini-3-8-flash-openai"}}}),
    "gemini_chat":()=>({status:200,j:{message:{success:true,reply:"TRA CUU"}}})});
  const e5=mk("https://x/viec-cua-toi",shell,r5); await tick(50);
  const R5=e5.w.document.getElementById("ec-khay-host").shadowRoot;
  ok("ten hien tren dau khung", R5.querySelector(".hd b").textContent==="eC Mate" && /eC Mate/.test(R5.querySelector(".fab").getAttribute("aria-label")));
  ok("khong con chu Khay tren giao dien", !/Khay/.test(R5.innerHTML.replace(/<style>[\s\S]*?<\/style>/,"")));
  R5.querySelector(".fab").click(); await tick();
  R5.querySelector("textarea").value="alo";
  R5.querySelector("form").dispatchEvent(new e5.w.Event("submit",{cancelable:true})); await tick(80);
  ok("tro chuyen: tra loi thang tu intent", /Chào bạn, mình đây!/.test(R5.querySelector(".ms").textContent));
  ok("tro chuyen: co dong Tra loi boi", /Trả lời bởi Gemini 3\.8 Flash/.test(R5.querySelector(".ms").textContent));
  ok("tro chuyen: KHONG goi them gemini_chat", !e5.log.some(x=>x.m==="gemini_chat"));
  const r6=Object.assign({},r5,{"ecentric_workspace.platform.ai.khay.intent":()=>({status:200,j:{message:{action:"answer",needs_data:true,reply:"",options:[]}}})});
  const e6=mk("https://x/viec-cua-toi",shell,r6); await tick(50);
  const R6=e6.w.document.getElementById("ec-khay-host").shadowRoot;
  R6.querySelector(".fab").click(); await tick();
  R6.querySelector("textarea").value="team tuan nay the nao";
  R6.querySelector("form").dispatchEvent(new e6.w.Event("submit",{cancelable:true})); await tick(120);
  ok("can so lieu: goi gemini_chat va hien ket qua", e6.log.some(x=>x.m==="gemini_chat") && /TRA CUU/.test(R6.querySelector(".ms").textContent));

  // ---- moi form Approval Center (29/09): khong tep -> AI dien tu cau chat, dung form server chon
  const r7=Object.assign({},r5,{
    "ecentric_workspace.platform.ai.khay.intent":()=>({status:200,j:{message:{action:"approval",approval_code:"PURCHASE_REQUEST",
      approval_title:"Purchase Request",route:"/approvals/purchase-request",labels:{item:"Mặt hàng"},reply:"",model:"grok-4-7"}}}),
    "ecentric_workspace.approval_center.api.ai_formfill.suggest":()=>({status:200,j:{message:{fields:{item:"2 màn hình Dell"},sources:{},model:"gemini-3-8-flash-openai"}}}),
    "ecentric_workspace.approval_center.api.ai_formfill.create_draft":()=>({status:200,j:{message:{name:"EC-PUR-2026-00001",missing:[]}}})});
  const e7=mk("https://x/viec-cua-toi",shell,r7); await tick(50);
  const R7=e7.w.document.getElementById("ec-khay-host").shadowRoot;
  R7.querySelector(".fab").click(); await tick();
  R7.querySelector("textarea").value="minh can mua 2 man hinh Dell";
  R7.querySelector("form").dispatchEvent(new e7.w.Event("submit",{cancelable:true})); await tick(120);
  const sg=e7.log.find(x=>/ai_formfill.suggest/.test(x.m));
  ok("form bat ky: goi suggest dung ma form server chon", sg && sg.body.approval_code==="PURCHASE_REQUEST");
  ok("form bat ky: khong tep thi dien tu cau chat", sg && sg.body.note==="minh can mua 2 man hinh Dell" && sg.body.files==="[]");
  ok("form bat ky: the mang ten form", /Purchase Request/.test(R7.querySelector(".card .ch").textContent));
  ok("form bat ky: hien o AI dien", /2 màn hình Dell/.test(R7.querySelector(".card").textContent));
  ok("form bat ky: Tu dien tro dung trang form", R7.querySelector(".card .btn.s").getAttribute("href")==="/approvals/purchase-request");
  ok("form bat ky: Dien boi model", /Điền bởi Gemini 3\.8 Flash/.test(R7.querySelector(".ms").textContent));
  R7.querySelector('[data-act="pay-draft"]').click(); await tick(60);
  const cd=e7.log.find(x=>/create_draft/.test(x.m));
  ok("form bat ky: tao nhap dung ma form", cd && cd.body.approval_code==="PURCHASE_REQUEST" && JSON.parse(cd.body.fields).item==="2 màn hình Dell");
  const r8=Object.assign({},r7,{"ecentric_workspace.approval_center.api.ai_formfill.suggest":()=>({status:200,j:{message:{fields:{},sources:{}}}})});
  const e8=mk("https://x/viec-cua-toi",shell,r8); await tick(50);
  const R8=e8.w.document.getElementById("ec-khay-host").shadowRoot;
  R8.querySelector(".fab").click(); await tick();
  R8.querySelector("textarea").value="tao phieu";
  R8.querySelector("form").dispatchEvent(new e8.w.Event("submit",{cancelable:true})); await tick(120);
  ok("form bat ky: AI khong dien duoc o nao thi noi ro, khong co nut tao nhap rong",
     /chưa điền được ô nào/.test(R8.querySelector(".card").textContent) && !R8.querySelector('[data-act="pay-draft"]'));

  // mat linh vat nhin theo chuot (29/09): nhom .look trong svg cua nut dich ve phia con tro
  const fsvg=R8.querySelector(".fab svg"), look=fsvg && fsvg.querySelector(".look");
  ok("mat linh vat: co nhom .look boc hai mat", !!look && look.querySelectorAll(".lid").length===2);
  fsvg.getBoundingClientRect=()=>({left:1000,top:500,width:80,height:80,right:1080,bottom:580});
  e8.w.document.dispatchEvent(new e8.w.MouseEvent("pointermove",{clientX:0,clientY:540,bubbles:true})); await tick(40);
  const tr=(look&&look.getAttribute("transform"))||"", mt=/translate\((-?[\d.]+) (-?[\d.]+)\)/.exec(tr);
  ok("mat linh vat: nhin sang trai khi chuot o ben trai", !!mt && parseFloat(mt[1])<-1.5 && Math.abs(parseFloat(mt[2]))<0.5);
  e8.w.document.dispatchEvent(new e8.w.MouseEvent("pointermove",{clientX:1040,clientY:2000,bubbles:true})); await tick(40);
  const mt2=/translate\((-?[\d.]+) (-?[\d.]+)\)/.exec(look.getAttribute("transform")||"");
  ok("mat linh vat: nhin xuong, khong qua 2.2", !!mt2 && parseFloat(mt2[2])>1 && parseFloat(mt2[2])<=2.2);

  // keo nut sang cho khac (29/09): keo > 6px thi doi vi tri + nho, KHONG mo khung; bam thuong van mo
  const fab8=R8.querySelector(".fab"), W8=e8.w;
  const wasOpen=!R8.querySelector(".pan").hidden;
  if (wasOpen) { fab8.click(); await tick(); }
  fab8.getBoundingClientRect=()=>({left:W8.innerWidth-94,top:W8.innerHeight-94,right:W8.innerWidth-14,bottom:W8.innerHeight-14,width:80,height:80});
  Object.defineProperty(fab8,"offsetWidth",{value:80}); Object.defineProperty(fab8,"offsetHeight",{value:80});
  fab8.dispatchEvent(new W8.MouseEvent("pointerdown",{clientX:500,clientY:500,button:0,bubbles:true}));
  ok("chong mat: chua keo thi mat thuong, khong keu", !fab8.classList.contains("dizzy") && R8.querySelector(".dz") && R8.querySelector(".oops").textContent==="Oopss...");
  W8.dispatchEvent(new W8.MouseEvent("pointermove",{clientX:400,clientY:300,bubbles:true}));
  ok("chong mat: dang keo thi lac lu + mat @@ + keu Oopss", fab8.classList.contains("dizzy") && fab8.classList.contains("drag"));
  W8.dispatchEvent(new W8.MouseEvent("pointerup",{clientX:400,clientY:300,bubbles:true}));
  ok("chong mat: tha ra thi het keo nhung con choang mot chut", !fab8.classList.contains("drag") && fab8.classList.contains("dizzy"));
  await tick(1000);
  ok("chong mat: ~1s sau thi tinh lai", !fab8.classList.contains("dizzy"));
  fab8.click(); await tick();
  ok("keo nut: doi vi tri (sang trai 100, len 200)", fab8.style.right==="114px" && fab8.style.bottom==="214px");
  ok("keo nut: nho vi tri", JSON.parse(W8.localStorage.getItem("ec_khay_fab_pos")||"{}").right===114);
  ok("keo nut: tha ra khong mo khung", R8.querySelector(".pan").hidden===true);
  fab8.click(); await tick();
  ok("keo nut: bam thuong van mo khung", R8.querySelector(".pan").hidden===false);
  fab8.dispatchEvent(new W8.MouseEvent("pointerdown",{clientX:500,clientY:500,button:0,bubbles:true}));
  W8.dispatchEvent(new W8.MouseEvent("pointermove",{clientX:-5000,clientY:9000,bubbles:true}));
  W8.dispatchEvent(new W8.MouseEvent("pointerup",{bubbles:true}));
  fab8.dispatchEvent(new W8.MouseEvent("pointerdown",{clientX:500,clientY:500,button:0,bubbles:true}));
  W8.dispatchEvent(new W8.MouseEvent("pointermove",{clientX:450,clientY:450,bubbles:true}));
  W8.dispatchEvent(new W8.MouseEvent("pointercancel",{bubbles:true})); await tick(1000);
  ok("chong mat: cam ung bi huy cung tinh lai", !fab8.classList.contains("dizzy") && !fab8.classList.contains("drag"));
  ok("keo nut: khong ra ngoai khung nhin", parseFloat(fab8.style.right)<=W8.innerWidth-84 && parseFloat(fab8.style.bottom)>=4);

  let all=true; Object.keys(c).forEach(k=>{console.log((c[k]?"PASS":"FAIL")+" - "+k); if(!c[k]) all=false;});
  console.log(all?"ALL_PASS":"SOME_FAIL"); process.exit(all?0:1);
})();
