// Copyright (c) 2026, eCentric and contributors
// Kéo ô ký ra sát mép phải: phải ĐẨY VÀO TRONG, không được bóp nhỏ lại.
//
// Bản trước ép x tới tận (W - minW) - cho cạnh TRÁI của ô chạy ra gần mép phải trang - rồi
// mới cắt chiều rộng cho vừa phần còn lại, nên ô co lại còn 20 điểm. Người dùng kéo ô vào
// lề phải và thấy nó "nhảy sang trái và thu nhỏ lại" (báo 28/08).
//
// Kích thước là thứ người dùng đã chọn; vị trí mới là thứ cần sửa.
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOTS = ["../../../platform/esign/ui", "../../platform/esign/ui",
               "../../../../platform/esign/ui"];
const PAGE = (() => {
  for (const r of ROOTS) {
    const p = path.join(HERE, r, "document_signing_section.html");
    if (fs.existsSync(p)) return p;
  }
  throw new Error("khong tim thay document_signing_section.html; da thu: " + ROOTS.join(", "));
})();
const HTML = fs.readFileSync(PAGE, "utf8");

const m = HTML.match(/function _clampBox\(box\)\s*\{[\s\S]*?\n  \}/);
if (!m) { console.log("  FAIL: khong tim thay _clampBox"); process.exit(1); }

const sandbox = { DRW: { pagePt: [595, 842] }, Math, console };
vm.createContext(sandbox);
vm.runInContext(m[0] + "\nglobalThis._clampBox = _clampBox;", sandbox, { filename: "clamp.js" });
const clamp = sandbox._clampBox;

let pass = 0, fail = 0;
const ok = (c, msg) => { if (c) pass++; else { fail++; console.log("  FAIL: " + msg); } };

console.log("Clamp o ky");

// --- kéo sát mép phải: giữ nguyên kích thước, đẩy vào trong ------------------
let b = clamp({ x: 900, y: 100, width: 240, height: 120 });
ok(b.width === 240, "keo sat mep phai -> GIU nguyen chieu rong 240 (dang " + b.width + ")");
ok(b.x === 595 - 240, "keo sat mep phai -> day vao trong, x = W - w (dang " + b.x + ")");
ok(b.x + b.width <= 595, "o nam tron trong trang");

// --- kéo sát đáy -------------------------------------------------------------
b = clamp({ x: 10, y: 5000, width: 240, height: 120 });
ok(b.height === 120, "keo sat day -> GIU nguyen chieu cao");
ok(b.y === 842 - 120, "keo sat day -> y = H - h");

// --- kéo ra ngoài lề trái/trên ----------------------------------------------
b = clamp({ x: -80, y: -40, width: 240, height: 120 });
ok(b.x === 0 && b.y === 0, "khong cho ra ngoai le trai/tren");
ok(b.width === 240 && b.height === 120, "ra ngoai le trai cung khong bop nho");

// --- ô TO HƠN trang thì mới thu nhỏ -----------------------------------------
b = clamp({ x: 0, y: 0, width: 9999, height: 9999 });
ok(b.width === 595 && b.height === 842, "o to hon trang -> thu ve vua trang");
ok(b.x === 0 && b.y === 0, "o vua trang thi nam o goc");

// --- kích thước tối thiểu ----------------------------------------------------
b = clamp({ x: 10, y: 10, width: 1, height: 1 });
ok(b.width >= 20 && b.height >= 12, "van giu kich thuoc toi thieu");

// --- ô nằm gọn giữa trang: không đụng vào -----------------------------------
b = clamp({ x: 100, y: 200, width: 240, height: 120 });
ok(b.x === 100 && b.y === 200 && b.width === 240 && b.height === 120,
   "o nam gon giua trang thi khong duoc sua gi");

// --- giá trị âm / rác --------------------------------------------------------
b = clamp({ x: 50, y: 50, width: -240, height: -120 });
ok(b.width === 240 && b.height === 120, "chieu rong am -> lay tri tuyet doi");

console.log("  " + pass + " passed, " + fail + " failed");
if (fail) process.exit(1);
