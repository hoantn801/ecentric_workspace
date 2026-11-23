/* Kiem thu ec_people_picker (jsdom, khong can site), 24/11/2026:
 *   node ecentric_workspace/public/js/tests/test_ec_people_picker.js [duong-dan-repo]
 * O chon nguoi chi DIEN EMAIL vao chinh o goc + phat input/change; ten nguoi luon duoc esc().
 */
const {JSDOM}=require("jsdom"); const fs=require("fs");
const js=fs.readFileSync((process.argv[2]||".")+"/ecentric_workspace/public/js/ec_people_picker.bundle.js","utf8");
const html=`<div class="fld"><input id="lm" type="email" data-model="line_manager" data-ec-people></div>
<div class="fld"><input id="cc" data-model="cc_to" data-ec-people="multi" value="a@x.vn"></div>
<div class="fld"><input id="plain" data-model="x"></div>`;
const dom=new JSDOM(html,{runScripts:"outside-only",url:"https://team.ecentric.vn/approvals/hiring-request"});
const w=dom.window; const calls=[];
w.frappe={call:(o)=>{calls.push(o); return Promise.resolve({message:[
  {user:"linh.vuong@ecentric.vn",full_name:"Linh <b>Vương</b>",department:"Data - EC"},
  {user:"luc.nguyen@ecentric.vn",full_name:"Lực Nguyễn",department:""}]});}};
w.eval(js);
const c={}; const d=w.document;
const wait=(ms)=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  await wait(100);
  const lm=d.getElementById("lm");
  c["o mot nguoi duoc boc, o goc van la o go"]= !!lm.closest(".ec-pp") && lm.style.display!=="none";
  c["o thuong khong bi dung"]= !d.getElementById("plain").closest(".ec-pp");
  let inp=0, chg=0; lm.addEventListener("input",()=>inp++); lm.addEventListener("change",()=>chg++);
  lm.value="l"; lm.dispatchEvent(new w.Event("input",{bubbles:true})); await wait(300);
  c["1 ky tu -> chua goi danh ba"]= calls.length===0;
  lm.value="li"; lm.dispatchEvent(new w.Event("input",{bubbles:true})); await wait(300);
  const call=calls[0];
  c["2 ky tu -> GET search_users"]= !!call && /approval_center\.api\.people\.search_users$/.test(call.method) && call.type==="GET" && call.args.q==="li";
  const drop=lm.closest(".ec-pp").querySelector(".ec-pp-drop");
  c["hien 2 goi y, ten duoc escape"]= !drop.hidden && drop.querySelectorAll(".ec-pp-opt").length===2 && drop.innerHTML.indexOf("<b>Vương</b>")<0;
  lm.dispatchEvent(new w.KeyboardEvent("keydown",{key:"ArrowDown",bubbles:true}));
  c["mui ten xuong chon muc 2"]= drop.querySelectorAll(".ec-pp-opt")[1].classList.contains("on");
  const before=inp;
  lm.dispatchEvent(new w.KeyboardEvent("keydown",{key:"Enter",bubbles:true}));
  c["Enter -> dien email vao o goc + phat input/change"]= lm.value==="luc.nguyen@ecentric.vn" && inp===before+1 && chg===1;
  await wait(300);
  c["sau khi chon khong goi lai danh ba"]= calls.length===1 && drop.hidden;
  c["hien ten + phong ban duoi o"]= /Lực Nguyễn/.test(lm.closest(".ec-pp").querySelector(".ec-pp-who").textContent);
  lm.value="li"; lm.dispatchEvent(new w.Event("input",{bubbles:true})); await wait(300);
  lm.dispatchEvent(new w.KeyboardEvent("keydown",{key:"Escape",bubbles:true}));
  c["Esc dong goi y"]= drop.hidden;
  // nhieu nguoi
  const cc=d.getElementById("cc"); const host=cc.closest(".ec-pp-multi");
  c["o nhieu nguoi: o goc an, chip tu gia tri cu"]= !!host && cc.style.display==="none" && host.querySelectorAll(".ec-pp-chip").length===1;
  let ccIn=0; cc.addEventListener("input",()=>ccIn++);
  const q=host.querySelector(".ec-pp-q"); q.value="lu"; q.dispatchEvent(new w.Event("input",{bubbles:true})); await wait(300);
  host.querySelector(".ec-pp-opt").dispatchEvent(new w.MouseEvent("mousedown",{bubbles:true,cancelable:true}));
  c["chon -> them chip, o goc 'a, b' + phat input"]= cc.value==="a@x.vn, linh.vuong@ecentric.vn" && ccIn===1 && host.querySelectorAll(".ec-pp-chip").length===2;
  c["chip ten duoc escape"]= !host.querySelector(".ec-pp-chip b") && /Linh <b>Vương<\/b>/.test(host.querySelectorAll(".ec-pp-chip")[1].textContent);
  q.value="khach@ngoai.com"; q.dispatchEvent(new w.KeyboardEvent("keydown",{key:"Enter",bubbles:true}));
  c["Enter email hop le -> them"]= /khach@ngoai\.com$/.test(cc.value);
  host.querySelector('[data-rm="a@x.vn"]').click();
  c["bo chip"]= cc.value==="linh.vuong@ecentric.vn, khach@ngoai.com";
  q.value=""; q.dispatchEvent(new w.KeyboardEvent("keydown",{key:"Backspace",bubbles:true}));
  c["Backspace o trong -> xoa chip cuoi"]= cc.value==="linh.vuong@ecentric.vn";
  let ok=true; Object.keys(c).forEach(k=>{console.log((c[k]?"PASS":"FAIL")+" - "+k); if(!c[k])ok=false;});
  console.log(ok?"ALL_PASS":"SOME_FAIL");
  process.exit(ok?0:1);
})();
