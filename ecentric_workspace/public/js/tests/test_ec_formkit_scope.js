/* Ranh giới phạm vi của ec_formkit (jsdom):
 *   node ecentric_workspace/public/js/tests/test_ec_formkit_scope.js <đường-dẫn-repo>
 * Asset nạp toàn site nên PHẢI chỉ chạy trên /approvals/*. Các trang GBS SO/PO và All Tickets
 * đã có combobox + vùng kéo-thả riêng; nâng cấp chồng lên sẽ sinh hai ô chọn / hai vùng thả.
 */
const {JSDOM}=require("jsdom"); const fs=require("fs");
const js=fs.readFileSync((process.argv[2]||".")+"/ecentric_workspace/public/js/ec_formkit.bundle.js","utf8");
function mk(url, html){
  const dom=new JSDOM(html,{runScripts:"outside-only",pretendToBeVisual:true,url:url});
  dom.window.__ecFormkitInstalled=false;
  dom.window.eval(js);
  return dom.window;
}
const selHtml='<div id="ec-x-root"><select><option>a</option><option>b</option><option>c</option><option>d</option><option>e</option><option>f</option><option>g</option></select><input type="file"></div>';
const c={};
// 1) trang SO/PO -> KHÔNG đụng
const w1=mk("https://x/gbs-po-form-v2", selHtml);
// 2) trang All Tickets -> KHÔNG đụng
const w2=mk("https://x/approval", selHtml);
// 3) trang approval form -> CÓ nâng cấp
const w3=mk("https://x/approvals/daily-target", selHtml);
// 4) trang đã có dropzone riêng -> không chồng
const w4=mk("https://x/approvals/x", '<div id="ec-x-root"><div class="ec-dz">có sẵn</div><input type="file"></div>');
setTimeout(()=>{
  c["PO: khong tao combobox"]= !w1.document.querySelector(".ec-cb");
  c["PO: khong tao dropzone"]= !w1.document.querySelector(".ec-dz");
  c["All Tickets: khong dung"]= !w2.document.querySelector(".ec-cb") && !w2.document.querySelector(".ec-dz");
  c["approvals: co nang cap"]= !!w3.document.querySelector(".ec-cb") && !!w3.document.querySelector(".ec-dz");
  c["khong chong len dropzone san co"]= w4.document.querySelectorAll(".ec-dz").length===1;
  let ok=true;Object.keys(c).forEach(k=>{console.log((c[k]?"PASS":"FAIL")+" - "+k); if(!c[k])ok=false;});
  console.log(ok?"ALL_PASS":"SOME_FAIL");
},200);
