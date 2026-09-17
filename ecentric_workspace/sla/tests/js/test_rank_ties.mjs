// Copyright (c) 2026, eCentric and contributors
// Xep hang tren tab "Phong ban": CUNG TI LE THI CUNG HANG.
//
//     node ecentric_workspace/sla/tests/js/test_rank_ties.mjs
//
// Vi sao tam dong logic nay dang mot tep test rieng: thang 9 co hang chuc nguoi
// cung 100% (chi co nhom cham cong dang tinh diem). Neu danh so theo thu tu dong
// thi bang xep hang dung ra mot thu bac khong co that giua nhung nguoi bang diem
// nhau - va do la thu nguoi ta chup man hinh. Lan sua sau ai do doi mot dau `=`
// thanh `>` o day se khong lam trang bao loi, no chi lam bang xep hang noi doi.
//
// Chay tren CHINH ma nguon cua trang: rut ham `assignRanks` ra khoi
// main_section.html roi nap bang vm. Chep lai logic vao day de test thi test se
// van xanh sau khi trang doi.
import fs from "fs";
import vm from "vm";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = path.join(HERE, "..", "..", "pages", "scoreboard", "main_section.html");
if (!fs.existsSync(PAGE)) throw new Error("khong thay main_section.html: " + PAGE);
const SRC = fs.readFileSync(PAGE, "utf8");

// Cat dung than ham bang cach dem ngoac - khong dung regex tham lam, vi than ham
// co ngoac long nhau.
function extract(src, name) {
  const head = "function " + name + "(";
  const i = src.indexOf(head);
  if (i < 0) throw new Error("khong tim thay " + name + " trong trang");
  let j = src.indexOf("{", i), depth = 0, k = j;
  for (; k < src.length; k++) {
    if (src[k] === "{") depth++;
    else if (src[k] === "}") { depth--; if (depth === 0) break; }
  }
  return src.slice(i, k + 1);
}

const ctx = { module: {} };
vm.runInNewContext(extract(SRC, "assignRanks") + "; module.exports = assignRanks;", ctx);
const assignRanks = ctx.module.exports;

let pass = 0, fail = 0;
const ok = (cond, msg) => { if (cond) pass++; else { fail++; console.log("  FAIL: " + msg); } };
const mk = (rates) => rates.map((r, i) => ({ user: "u" + i, overall: { rate: r } }));
const ranks = (rates) => assignRanks(mk(rates)).map(r => r._rank);

// --- khong co hoa ---
ok(JSON.stringify(ranks([100, 90, 80])) === JSON.stringify([1, 2, 3]),
   "khong hoa thi 1,2,3");

// --- hoa o dau: ba nguoi cung nhat, nguoi ke la hang 4 ---
ok(JSON.stringify(ranks([100, 100, 100, 90])) === JSON.stringify([1, 1, 1, 4]),
   "ba nguoi cung 100% -> 1,1,1 va nguoi ke la 4 (khong phai 2)");

// --- hoa o giua ---
ok(JSON.stringify(ranks([100, 90, 90, 80])) === JSON.stringify([1, 2, 2, 4]),
   "hoa o giua -> 1,2,2,4");

// --- tat ca bang nhau: khong ai duoc la "hang 1" mot minh ---
ok(JSON.stringify(ranks([100, 100, 100])) === JSON.stringify([1, 1, 1]),
   "tat ca bang nhau thi tat ca cung hang 1");

// --- chua du mau: KHONG co hang, khong phai hang cuoi ---
ok(JSON.stringify(ranks([100, 90, null, null])) === JSON.stringify([1, 2, null, null]),
   "chua du mau -> khong co hang");

// --- toan bo chua du mau ---
ok(JSON.stringify(ranks([null, null])) === JSON.stringify([null, null]),
   "khong ai du mau thi khong ai co hang");

// --- 0% van la mot ti le, khong duoc coi nhu thieu mau ---
ok(JSON.stringify(ranks([100, 0, null])) === JSON.stringify([1, 2, null]),
   "0% la mot ti le that (khong duoc lot vao nhanh null)");

// --- danh sach rong ---
ok(JSON.stringify(ranks([])) === JSON.stringify([]), "danh sach rong");

// --- sua tai cho, giu nguyen thu tu backend da sap ---
const rows = mk([100, 100, 80]);
const same = assignRanks(rows);
ok(same === rows, "sua tai cho, tra ve chinh mang do");
ok(rows[0].user === "u0" && rows[2].user === "u2", "khong sap xep lai");

console.log((fail ? "FAILED" : "OK") + " - " + pass + " dung, " + fail + " sai");
process.exit(fail ? 1 : 0);
