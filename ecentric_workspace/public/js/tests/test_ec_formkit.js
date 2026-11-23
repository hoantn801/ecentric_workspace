/* Kiểm thử ec_formkit (jsdom, không cần site):
 *   node ecentric_workspace/public/js/tests/test_ec_formkit.js <đường-dẫn-repo>
 * Bảo đảm combobox chỉ GHI VÀO <select> gốc rồi phát input+change (không tự giữ state),
 * và vùng kéo-thả chỉ bọc <input type=file> chứ không thay thế nó.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs");
const js=fs.readFileSync((process.argv[2]||".")+"/ecentric_workspace/public/js/ec_formkit.bundle.js","utf8");
const html=`<div id="ec-dtgt-root">
  <select data-model="brand">
    <option value="">— Chọn brand —</option>
    <option value="AND-VN">AND-VN — Andros</option>
    <option value="BBT-VN">BBT-VN — Bong Bach Tuyet</option>
    <option value="FCV-VN">FCV-VN — Cafe Viet</option>
    <option value="FES-VN">FES-VN — Cafepho Group</option>
    <option value="HNW-VN">HNW-VN — Honeywell</option>
    <option value="LOF-VN">LOF-VN — Lof Viet Nam</option>
  </select>
  <div id="o1"><input type="file" multiple id="tu-do"><div class="hint" id="att-name"></div></div>
  <!-- O RIENG: enhanceFile con mot luat "canh no da co .ec-dz thi thoi". De chung mot the cha
       voi o tren thi o nay bi bo qua vi luat DO, va phep kiem "data-upload" thanh vo nghia -
       dot bien xoa luat data-upload van song. Tach ra thi moi do dung thu minh dang do. -->
  <div id="o2"><input type="file" multiple data-upload="request_attachment" id="trang-tu-quan"></div>
  <!-- Danh sach NGAN NGOAI form (bo loc, bang) giu <select> goc. -->
  <select id="ngan"><option></option><option>A</option><option>B</option></select>
  <!-- 24/11/2026: danh sach ngan TRONG o nhap form (.fld) dung combobox chung, an o tim. -->
  <div class="fld" id="fld-ngan"><select id="ngan-form" data-model="employment_type"><option value="">— Chọn loại hình —</option><option value="Full-time">Full-time</option><option value="Intern">Intern</option></select></div>
  <table><tbody><tr><td>
    <select id="in-table" data-ec-no-formkit>
      <option value=""></option><option>TikTok</option><option>Facebook</option>
      <option>Instagram</option><option>YouTube</option><option>Threads</option><option>Khác</option>
    </select>
  </td></tr></tbody></table>
</div>`;
// PHAI dat url: `scan()` chi chay khi duong dan bat dau bang /approvals (them boi
// hotfix/formkit-scope). Thieu url thi jsdom chay o about:blank -> khong nang cap gi ->
// `btn.click()` nem TypeError, va bai test nay da CHET IM LANG tu luc do. Xem
// test_ec_formkit_scope.js: no truyen url nen van xanh, che mat viec bai nay da hong.
const dom=new JSDOM(html,{runScripts:"outside-only",pretendToBeVisual:true,
                          url:"https://team.ecentric.vn/approvals/booking-request"});
const w=dom.window; w.eval(js);
setTimeout(()=>{
 const c={};
 const sel=w.document.querySelector("select");
 const wrap=w.document.querySelector(".ec-cb");
 c["boc select thanh combobox"]= !!wrap && wrap.contains(sel) && sel.style.display==="none";
 const btn=w.document.querySelector(".ec-cb-display");
 c["nut hien placeholder"]= btn && /Chọn brand/.test(btn.textContent);
 btn.click();
 const panel=w.document.querySelector(".ec-cb-panel");
 c["mo panel + o tim kiem"]= panel && !panel.hidden && !!panel.querySelector(".ec-cb-search");
 // TRANG TU KHAI QUYEN SO HUU: mot <select> trong o bang khong dung duoc combobox (bang tim
 // bung ra de len hang duoi va bi vien bang cat). Khong co luat nay thi cai select 7 muc kia
 // bi nang cap va bang KOL/KOC cua Booking Request khong dung duoc.
 const inTable=w.document.querySelector("#in-table");
 c["data-ec-no-formkit: KHONG nang cap select"]= !!inTable && !inTable.closest(".ec-cb")
   && inTable.style.display!=="none";
 c["dem ket qua"]= /7 kết quả|6 kết quả/.test(w.document.querySelector(".ec-cb-count").textContent);
 // tìm
 const s=panel.querySelector(".ec-cb-search"); s.value="cafe"; s.dispatchEvent(new w.Event("input"));
 const rows=[...w.document.querySelectorAll(".ec-cb-option")];
 c["loc theo tu khoa"]= rows.length===2 && rows.every(r=>/Cafe/i.test(r.textContent));
 // chọn
 let gotInput=false, gotChange=false;
 sel.addEventListener("input",()=>gotInput=true); sel.addEventListener("change",()=>gotChange=true);
 rows[0].click();
 c["chon -> ghi vao select"]= sel.value==="FCV-VN";
 c["phat input+change"]= gotInput && gotChange;
 c["dong panel + hien nhan"]= panel.hidden && /Cafe Viet/.test(btn.textContent);
 // dropzone
 const inp=w.document.querySelector("#tu-do");
 const dz=w.document.querySelector(".ec-dz");
 c["o file thanh vung keo tha"]= !!dz && inp.style.display==="none" && /Kéo thả tệp/.test(dz.textContent);
 c["ghi chu nhieu tep"]= !!dz && /nhiều tệp/.test(dz.textContent);
 // `data-upload` = trang tu quan ly viec tai tep. Boc them mot dropzone nua se tao HAI vung
 // keo-tha chong nhau - dung loi da gap o Payment Request 26/08. Bai test cu khong co o nay
 // nen luat do khong duoc canh o dau ca.
 // 24/11/2026: o `data-upload` (trang tu quan viec tai tep) NAY CUNG duoc vung keo-tha chung
 // (Hoan: "mot so form chi la mot nut tai tep rat xau"). Van chi MOT vung cho moi o, o goc giu
 // nguyen trong DOM (an) de handler 'change' cua trang chay nhu cu.
 const tuQuan=w.document.querySelector("#trang-tu-quan");
 let tqChange=0; tuQuan.addEventListener("change",()=>tqChange++);
 const dz2=w.document.querySelector("#o2 .ec-dz");
 c["data-upload: co vung keo-tha chung, o goc an + con trong DOM"]= !!dz2 && tuQuan.style.display==="none"
   && w.document.querySelectorAll(".ec-dz").length===2 && dz2.nextElementSibling===tuQuan;
 let clicked=0; tuQuan.click=()=>clicked++; dz2.click();
 c["bam vung keo-tha -> mo hop chon tep cua o goc"]= clicked===1;
 // select ngan trong form
 const nf=w.document.querySelector("#ngan-form");
 const nwrap=nf.closest(".ec-cb");
 c["select ngan TRONG form -> combobox gon (an o tim)"]= !!nwrap && nwrap.classList.contains("ec-cb-compact") && nf.style.display==="none";
 let nfChange=0; nf.addEventListener("change",()=>nfChange++);
 nwrap.querySelector(".ec-cb-display").click();
 const nopt=[...nwrap.querySelectorAll(".ec-cb-option")].find(o=>o.getAttribute("data-val")==="Intern");
 nopt.click();
 c["chon -> gia tri + change"]= nf.value==="Intern" && nfChange===1 && /Intern/.test(nwrap.querySelector(".ec-cb-display").textContent);
 nf.value="Full-time"; w.document.body.dispatchEvent(new w.MouseEvent("click",{bubbles:true}));
 setTimeout(()=>{
 c["trang gan .value bang code -> o hien thi cap nhat"]= /Full-time/.test(nwrap.querySelector(".ec-cb-display").textContent);
 nf.selectedIndex=0; w.document.body.dispatchEvent(new w.Event("input",{bubbles:true}));
 setTimeout(()=>{
 c["gan selectedIndex -> ve placeholder"]= /Chọn loại hình/.test(nwrap.querySelector(".ec-cb-display").textContent);
 c["select ngan: van doc .value dung"]= nf.value==="";
 const ngan=w.document.querySelector("#ngan");
 c["danh sach ngan (<6 muc) giu select goc"]= !!ngan && !ngan.closest(".ec-cb")
   && ngan.style.display!=="none";
 let ok=true; Object.keys(c).forEach(k=>{console.log((c[k]?"PASS":"FAIL")+" - "+k); if(!c[k])ok=false;});
 console.log(ok?"ALL_PASS":"SOME_FAIL");
 // MA THOAT, khong chi dong chu. Thieu dong nay thi bai test in "SOME_FAIL" ma van
 // thoat 0 - run_js.sh dem no la XANH, va 15/09 chinh no lam phep kiem dot bien cua
 // Claude bao "dot bien song sot" trong khi that ra bai test da bat dung loi.
 process.exit(ok?0:1);
 },100); },100);
},150);
