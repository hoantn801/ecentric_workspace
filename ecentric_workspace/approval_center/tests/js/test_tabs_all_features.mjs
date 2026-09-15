// Copyright (c) 2026, eCentric and contributors
//
// 15/09: ca 28 form chi ve MOT tab ("Tao yeu cau"), trong khi backend van tinh quyen cho bon
// tab va gui xuong `state.boot.tabs`, con `tabAllowed` + `render()` van dieu huong duoc. Tuc
// la luat dung, ma khong co cua vao - chi toi duoc bang cach go tay `?tab=my-requests`.
// Dung ho "ham khong ai goi": mot manh chuc nang bi bo quen, khong ai thay de bao.
//
// Bo test nay quet CA 28 form va giu ba dieu:
//   1. Thanh tab lay `state.boot.tabs` lam nguon - cung nguon voi `tabAllowed`, khong tu che
//      mot danh sach thu hai roi hai ben troi nhau.
//   2. KHONG form nao bat mot tab ma chinh no khong co ham ve (goi ham ma - dung loi 08/09
//      "6 form giong 90% KHONG 100%").
//   3. Nguoc lai: form nao dieu huong toi mot tab thi tab do phai co duong bam vao.
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const FEAT = join(here, "..", "..", "features");
const forms = readdirSync(FEAT).filter((d) => !d.startsWith("_") && !d.startsWith("."));

/** Cat than mot ham theo cap ngoac nhon - de doi chieu DUNG doan ma, khong phai ca file. */
function thanHam(src, ten) {
  const i = src.indexOf("function " + ten + "(");
  if (i < 0) return null;
  let sau = 0; const bd = src.indexOf("{", i);
  for (let j = bd; j < src.length; j++) {
    if (src[j] === "{") sau++;
    else if (src[j] === "}") { sau--; if (!sau) return src.slice(bd, j + 1); }
  }
  return null;
}

const TAB = [
  { key: "my-requests", nhan: "Yêu cầu của tôi", ham: "renderMyRequests" },
  { key: "my-approvals", nhan: "Chờ tôi duyệt", ham: "renderMyApprovals" },
  { key: "fulfillment", nhan: "Tôi xử lý", ham: "renderFulfillment" },
];

let dat = 0;
const hong = [];
let coTabs = 0;

for (const f of forms) {
  let src;
  try { src = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8"); }
  catch { continue; }
  if (!src.includes("function renderTabs(")) continue;
  coTabs++;

  // 1. nguon du lieu - PHAI kiem TRONG THAN renderTabs, khong phai tren ca file.
  //    `tabAllowed` cung co dong doc `state.boot.tabs`, nen tim tren ca file thi renderTabs
  //    co the thoi doc ma phep kiem van xanh (do that: dot bien sua dung renderTabs van song).
  const than = thanHam(src, "renderTabs");
  if (!than) hong.push(`${f}: khong cat duoc than renderTabs`);
  else if (!/state\.boot\s*&&\s*state\.boot\.tabs/.test(than))
    hong.push(`${f}: renderTabs khong doc state.boot.tabs`);
  else dat++;

  if (!src.includes('["my-requests","Yêu cầu của tôi",true]'))
    hong.push(`${f}: thieu tab "Yeu cau cua toi" - tab nay ai cung duoc xem`);
  else dat++;

  for (const t of TAB) {
    const bat = src.includes(`"${t.key}","${t.nhan}"`);
    const coHam = src.includes(`function ${t.ham}(`);
    const dieuHuong = src.includes(`state.tab==="${t.key}"`);
    // 2. bat tab ma khong co ham ve
    if (bat && !coHam) hong.push(`${f}: bat tab ${t.key} nhung KHONG co ${t.ham}`);
    else if (bat) dat++;
    // 3. dieu huong toi tab ma khong co nut bam
    if (dieuHuong && !bat) hong.push(`${f}: render() di toi ${t.key} nhung khong co nut bam`);
  }
}

// Con dem chong "bo test chet am tham": suite nay tung xanh voi 0 form neu duong dan doi.
if (coTabs < 25) hong.push(`chi quet duoc ${coTabs} form co renderTabs - phep do hong, khong phai ma sach`);

hong.forEach((h) => console.log("FAIL - " + h));
console.log(`${dat} phep dat, ${hong.length} hong (${coTabs} form co thanh tab)`);
process.exit(hong.length ? 1 : 0);
