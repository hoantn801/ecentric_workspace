// Copyright (c) 2026, eCentric and contributors
//
// 16/09: p200 mo lai thanh tab tren 28 form, `test_tabs_all_features.mjs` xanh voi 118
// assertion - va tren production BAM TAB KHONG DOI GI. URL doi thanh `?tab=my-requests`,
// man hinh van o form "Tao moi", khong loi console, khong goi API nao.
//
// Vi sao bo test cu khong bat duoc: ca 118 assertion deu chi hoi "renderTabs co ve du nut
// khong". Khong assertion nao bam vao nut roi kiem ket qua. No do THU DA VIET RA, khong do
// HANH VI nguoi dung can. Do la lo hong that su, khong phai thieu vai dong.
//
// Bo test nay chay THAT chuoi dinh tuyen cat ra tu chinh trang:
//     handler [data-tab]  ->  go()  ->  route()  ->  readRoute()  ->  state.tab
// DOM bi gia lap (nut + o chua), vi loi KHONG nam o DOM; moi mat xich con lai la ma that
// cat tu main_section.html. Hai loi that deu bi bat:
//   * 27 form: readRoute doc `t` roi vut di  -> state.tab ket o "create"
//   * booking_request: khong gan listener   -> khong cat duoc handler, do ngay o buoc cat
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const FEAT = join(here, "..", "..", "features");

/** Cat mot khoi bat dau tu `from` theo cap ngoac nhon can bang. */
function khoi(src, from) {
  const bd = src.indexOf("{", from);
  if (bd < 0) return null;
  let sau = 0;
  for (let j = bd; j < src.length; j++) {
    if (src[j] === "{") sau++;
    else if (src[j] === "}") { sau--; if (!sau) return src.slice(bd, j + 1); }
  }
  return null;
}
function ham(src, ten) {
  const i = src.indexOf("function " + ten + "(");
  if (i < 0) return null;
  const args = src.slice(i + ("function " + ten).length, src.indexOf(")", i) + 1);
  const than = khoi(src, i);
  return than ? "function " + ten + args + than : null;
}
/** Cat dung ham xu ly click cua thanh tab: neo vao `closest("[data-tab]")` roi lui ve
 *  `function(...)` gan nhat truoc no. Khong grep - phai lay duoc THAN ham that. */
function handlerTab(src) {
  const neo = src.indexOf('closest("[data-tab]")');
  if (neo < 0) return null;
  const truoc = src.lastIndexOf("function", neo);
  if (truoc < 0) return null;
  const args = src.slice(truoc + "function".length, src.indexOf(")", truoc) + 1);
  const than = khoi(src, truoc);
  return than ? "(function " + args.trim() + than + ")" : null;
}

const forms = readdirSync(FEAT).filter((d) => !d.startsWith("_") && !d.startsWith("."));
let dat = 0;
const hong = [];

for (const f of forms) {
  let src;
  try { src = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8"); } catch { continue; }
  if (!src.includes("function renderTabs(")) continue;

  const fnReadRoute = ham(src, "readRoute");
  const fnTabAllowed = ham(src, "tabAllowed");
  const fnGo = ham(src, "go");
  const fnRoute = ham(src, "route");
  const fnHandler = handlerTab(src);

  // Thieu bat ky mat xich nao = tab khong the chay. booking_request truot O DAY truoc khi sua.
  const thieu = [];
  if (!fnReadRoute) thieu.push("readRoute");
  if (!fnTabAllowed) thieu.push("tabAllowed");
  if (!fnGo) thieu.push("go");
  if (!fnRoute) thieu.push("route");
  if (!fnHandler) thieu.push("handler [data-tab] (khong gan listener?)");
  if (thieu.length) { hong.push(`${f}: thieu ${thieu.join(", ")}`); continue; }

  /** Dung mot the gioi toi thieu roi chay chuoi that. Tra ve state sau khi "bam". */
  function bam(tabBam, quyen) {
    const src2 = `
      "use strict";
      const state = { mode:"", id:null, tab:"create", page:3, unc:{},
                      boot:{ tabs:${JSON.stringify(quyen)} } };
      let search = "";
      const window = {
        location: { get search(){ return search; }, pathname:"/approvals/x" },
        history: { pushState(_a,_b,url){ search = url.includes("?") ? url.slice(url.indexOf("?")) : ""; },
                   replaceState(_a,_b,url){ this.pushState(_a,_b,url); } },
        addEventListener(){}
      };
      let veLai = 0;
      function render(){ veLai++; }        // khong ve that - ta do state, khong do pixel
      ${fnTabAllowed}
      ${fnReadRoute}
      ${fnRoute}
      ${fnGo}
      const nut = { disabled:false, getAttribute:(k)=> k==="data-tab" ? ${JSON.stringify(tabBam)} : null };
      const e = { target: { closest:(sel)=> sel==="[data-tab]" ? nut : null } };
      (${fnHandler})(e);
      return { tab: state.tab, page: state.page, veLai, search };
    `;
    return new Function(src2)();
  }

  // 1. Bam "Yeu cau cua toi" PHAI doi man hinh. Day la phep do that su cua dot nay.
  const r1 = bam("my-requests", { my_approvals: true });
  if (r1.tab !== "my-requests")
    hong.push(`${f}: bam my-requests nhung state.tab = "${r1.tab}" (dinh tuyen khong dung tham so URL)`);
  else dat++;
  if (r1.veLai < 1) hong.push(`${f}: bam tab nhung render() khong duoc goi lan nao`); else dat++;
  // Doi tab phai ve trang 1, neu khong se giu so trang cua danh sach truoc.
  if (r1.page !== 0) hong.push(`${f}: doi tab nhung state.page = ${r1.page}, phai ve 0`); else dat++;

  // 2. Tab khong duoc phep KHONG duoc tin, du URL ghi gi: `tabAllowed` phai that su chan.
  const r2 = bam("my-approvals", { my_approvals: false });
  if (r2.tab === "my-approvals")
    hong.push(`${f}: vao duoc tab my-approvals du server bao khong co quyen`);
  else dat++;

  // 3. Con duoc phep thi phai vao duoc - neu khong, phep chan o (2) chi la "cam tat".
  const r3 = bam("my-approvals", { my_approvals: true });
  if (r3.tab !== "my-approvals")
    hong.push(`${f}: co quyen my-approvals nhung van khong vao duoc (state.tab="${r3.tab}")`);
  else dat++;

  // 4. Tab bia dat tren URL phai roi ve "create", khong duoc de state.tab thanh rac.
  const r4 = bam("khong-ton-tai", { my_approvals: true });
  if (r4.tab !== "create")
    hong.push(`${f}: tab bia dat cho ra state.tab = "${r4.tab}", phai la "create"`);
  else dat++;
}

for (const h of hong) console.log("  HONG: " + h);
const soForm = forms.filter((f) => {
  try { return readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8").includes("function renderTabs("); }
  catch { return false; }
}).length;
if (soForm < 28) { console.log(`  HONG: chi thay ${soForm} form co renderTabs, cho doi >= 28`); hong.push("so form"); }
console.log(`${dat} dat, ${hong.length} hong (${soForm} form)`);
process.exit(hong.length ? 1 : 0);
