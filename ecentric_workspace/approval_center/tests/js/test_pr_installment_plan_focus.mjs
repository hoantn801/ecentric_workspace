// Copyright (c) 2026, eCentric and contributors
// Payment Request — khối "Kế hoạch chia đợt" vẽ lại KHÔNG được làm mất focus; đợt 1 > tổng phải
// báo vượt chứ không đọc nhầm thành "đợt cuối" (Hoàn 08/09). Cần DOM thật (focus/activeElement)
// nên chạy bằng jsdom — cài NGOÀI repo (memory: cấm quét node_modules vào commit):
//   npm i jsdom --prefix C:\dev\_jsdom   (Windows)  |  npm i jsdom --prefix /tmp/jsd (sandbox)
// Không có jsdom thì báo BỎ QUA rõ ràng và exit 0 — không giả xanh, không giả đỏ.
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { createRequire } from "module";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = path.join(HERE, "..", "..", "features", "payment_request", "ui", "main_section.html");
let JSDOM = null;
for (const base of [process.env.EC_JSDOM_PREFIX, "C:\\dev\\_jsdom", "/tmp/jsd", path.join(HERE, "..", "..", "..", "..", "..", "_jsdom")].filter(Boolean)) {
  try { JSDOM = createRequire(path.join(base, "package.json"))("jsdom").JSDOM; break; } catch (e) {}
}
if (!JSDOM) { console.log("BO QUA: khong tim thay jsdom (cai: npm i jsdom --prefix C:\\dev\\_jsdom)"); process.exit(0); }
const h=fs.readFileSync(PAGE,"utf8"); const SRC=h.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
const dom=new JSDOM('<!doctype html><html><body><div id="ec-payr-root"><div id="payr-tabs"></div><div id="payr-body"></div><div id="payr-toast"></div></div></body></html>',{runScripts:"outside-only",url:"https://x.test/approvals/payment-request"});
const w=dom.window; w.frappe={csrf_token:"x",call:(o)=>{ if(/get_bootstrap$/.test(o.method)) return Promise.resolve({message:{tabs:{},context:{user:"u",employee_name:"H"},form_options:{yes_no:["Yes","No"]}}}); return Promise.resolve({message:{}}); }};
w.eval(SRC); await new Promise(r=>setTimeout(r,50));
const PR=w.PaymentRequest; PR.state.boot={tabs:{},context:{user:"u",employee_name:"H"},form_options:{yes_no:["Yes","No"]}}; PR.state.draft={payment_mode:"Installment"}; PR.renderCreate(w.document.getElementById("payr-body"));
const q=(s)=>w.document.querySelector(s);
function type(sel,val){ const el=q(sel); el.focus(); el.value=val; el.dispatchEvent(new w.Event("input",{bubbles:true})); }
let pass=0,fail=0; const ok=(c,m)=>{ if(c)pass++; else {fail++; console.log("FAIL "+m);} };
type('[data-model="total_amount"]',"2");
ok(w.document.activeElement && w.document.activeElement.getAttribute("data-model")==="total_amount","gõ tổng: focus vẫn ở ô tổng sau khi khối vẽ lại");
type('[data-model="total_amount"]',"2000000");
ok(q('[data-model="total_amount"]').value==="2.000.000","tổng hiện có dấu chấm ngăn cách");
ok(PR.state.draft.total_amount===2000000,"model giữ SỐ 2000000 (không phải chuỗi có dấu chấm)");
// go tiep vao chuoi da dinh dang: chi lay chu so
type('[data-model="total_amount"]',"2.000.0005");
ok(PR.state.draft.total_amount===20000005 && q('[data-model="total_amount"]').value==="20.000.005","gõ thêm vào chuỗi đã định dạng: parse chữ số, định dạng lại");
type('[data-model="total_amount"]',"2000000");
type('[data-model="payment_amount"]',"1200000");
ok(w.document.activeElement.getAttribute("data-model")==="payment_amount","gõ số tiền đợt 1 (ngoài khối): focus giữ");
ok(q('[data-model="next_installment_amount"]').value==="800.000","đợt kế = 800.000 (có dấu chấm)");
ok(PR.state.draft.payment_amount===1200000,"model số tiền đợt 1 = 1200000");
type('[data-model="payment_amount"]',"5000000");
ok(/vượt phần còn lại/.test(q("#payr-inst-plan").textContent) && !/đợt cuối/.test(q("#payr-inst-plan").textContent),"đợt 1 > tổng: báo vượt, không nói 'đợt cuối'");
ok(!q('[data-model="next_installment_amount"]'),"vượt tổng: không hiện ô đợt kế");
type('[data-model="payment_amount"]',"2000000");
ok(/đợt cuối/.test(q("#payr-inst-plan").textContent),"đợt 1 = tổng: đợt cuối");
type('[data-model="payment_amount"]',"1000000");
type('[data-model="next_installment_amount"]',"300000"); // dang go trong khoi
ok(w.document.activeElement.getAttribute("data-model")==="next_installment_amount","gõ đợt kế (trong khối): focus giữ");
type('[data-model="total_amount"]',"3000000");
ok(w.document.activeElement.getAttribute("data-model")==="total_amount","đổi tổng lần nữa: focus vẫn ở tổng");
console.log(pass+" đạt, "+fail+" hỏng");
if (pass < 12) { console.log("HONG: so phep kiem thap bat thuong (" + pass + ")"); process.exit(1); }
process.exit(fail?1:0);
