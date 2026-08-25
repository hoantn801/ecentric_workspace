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
  <input type="file" multiple data-upload="request_attachment"><div class="hint" id="att-name"></div>
</div>`;
const dom=new JSDOM(html,{runScripts:"outside-only",pretendToBeVisual:true});
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
 const inp=w.document.querySelector('input[type="file"]');
 const dz=w.document.querySelector(".ec-dz");
 c["o file thanh vung keo tha"]= !!dz && inp.style.display==="none" && /Kéo thả tệp/.test(dz.textContent);
 c["ghi chu nhieu tep"]= /nhiều tệp/.test(dz.textContent);
 let ok=true; Object.keys(c).forEach(k=>{console.log((c[k]?"PASS":"FAIL")+" - "+k); if(!c[k])ok=false;});
 console.log(ok?"ALL_PASS":"SOME_FAIL");
},150);
