/* Combobox sat day man hinh thi mo len tren (01/10/2026, o "+ Them brand" trang Phan bo
 * cong viec bi cat mat danh sach).
 *   node ecentric_workspace/public/js/tests/test_ec_formkit_flip.js <duong-dan-repo>
 */
const {JSDOM}=require("jsdom"); const fs=require("fs");
const js=fs.readFileSync((process.argv[2]||".")+"/ecentric_workspace/public/js/ec_formkit.bundle.js","utf8");
const opts=Array.from({length:12},(_,i)=>`<option value="B${i}">Brand ${i}</option>`).join("");
const html=`<div id="r1"><select id="s1"><option value="">— Chọn —</option>${opts}</select></div>`;
const dom=new JSDOM(html,{runScripts:"outside-only",pretendToBeVisual:true,
                          url:"https://team.ecentric.vn/approvals/booking-request"});
const w=dom.window; w.eval(js);
setTimeout(()=>{
  const c={};
  const wrap=w.document.querySelector(".ec-cb");
  const btn=wrap.querySelector(".ec-cb-display"), panel=wrap.querySelector(".ec-cb-panel");
  Object.defineProperty(w,"innerHeight",{value:800,configurable:true});
  // sat day: o nam o 700-740, duoi chi con ~48px, tren con ~690px
  wrap.getBoundingClientRect=()=>({top:700,bottom:740,left:0,right:300,width:300,height:40});
  btn.click();
  c["sat day -> mo len tren"]= !panel.hidden && panel.classList.contains("ec-cb-up");
  btn.click();
  // giua man hinh: du cho ben duoi -> mo xuong nhu cu
  wrap.getBoundingClientRect=()=>({top:100,bottom:140,left:0,right:300,width:300,height:40});
  btn.click();
  c["du cho -> mo xuong"]= !panel.hidden && !panel.classList.contains("ec-cb-up");
  btn.click();
  // ca hai phia deu chat: chon phia rong hon va co chieu cao vua cho
  Object.defineProperty(w,"innerHeight",{value:420,configurable:true});
  wrap.getBoundingClientRect=()=>({top:190,bottom:230,left:0,right:300,width:300,height:40});
  Object.defineProperty(panel,"scrollHeight",{value:320,configurable:true});
  btn.click();
  c["hai phia chat -> chon phia rong + co chieu cao"]= panel.classList.contains("ec-cb-up")===false
    && /^1[0-9]{2}px$/.test(panel.style.maxHeight);
  let ok=true;
  for (const [k,v] of Object.entries(c)) { console.log((v?"PASS":"FAIL")+" - "+k); if(!v) ok=false; }
  console.log(ok?"ALL_PASS":"SOME_FAIL"); process.exitCode=ok?0:1;
},50);
