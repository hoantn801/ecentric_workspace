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
    "ecentric_workspace.platform.ai.khay.intent":()=>({status:200,j:{message:{action:"answer",needs_data:false,reply:"Chào bạn, mình đây!",options:[]}}}),
    "gemini_chat":()=>({status:200,j:{message:{success:true,reply:"TRA CUU"}}})});
  const e5=mk("https://x/viec-cua-toi",shell,r5); await tick(50);
  const R5=e5.w.document.getElementById("ec-khay-host").shadowRoot;
  ok("ten hien tren dau khung", R5.querySelector(".hd b").textContent==="eC Mate" && /eC Mate/.test(R5.querySelector(".fab").getAttribute("aria-label")));
  ok("khong con chu Khay tren giao dien", !/Khay/.test(R5.innerHTML.replace(/<style>[\s\S]*?<\/style>/,"")));
  R5.querySelector(".fab").click(); await tick();
  R5.querySelector("textarea").value="alo";
  R5.querySelector("form").dispatchEvent(new e5.w.Event("submit",{cancelable:true})); await tick(80);
  ok("tro chuyen: tra loi thang tu intent", /Chào bạn, mình đây!/.test(R5.querySelector(".ms").textContent));
  ok("tro chuyen: KHONG goi them gemini_chat", !e5.log.some(x=>x.m==="gemini_chat"));
  const r6=Object.assign({},r5,{"ecentric_workspace.platform.ai.khay.intent":()=>({status:200,j:{message:{action:"answer",needs_data:true,reply:"",options:[]}}})});
  const e6=mk("https://x/viec-cua-toi",shell,r6); await tick(50);
  const R6=e6.w.document.getElementById("ec-khay-host").shadowRoot;
  R6.querySelector(".fab").click(); await tick();
  R6.querySelector("textarea").value="team tuan nay the nao";
  R6.querySelector("form").dispatchEvent(new e6.w.Event("submit",{cancelable:true})); await tick(120);
  ok("can so lieu: goi gemini_chat va hien ket qua", e6.log.some(x=>x.m==="gemini_chat") && /TRA CUU/.test(R6.querySelector(".ms").textContent));

  let all=true; Object.keys(c).forEach(k=>{console.log((c[k]?"PASS":"FAIL")+" - "+k); if(!c[k]) all=false;});
  console.log(all?"ALL_PASS":"SOME_FAIL"); process.exit(all?0:1);
})();
