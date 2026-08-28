// Copyright (c) 2026, eCentric and contributors
// Chữ ký phải LẤP ĐẦY ô, không phải một chấm mực nhỏ lọt thỏm giữa khung rộng.
//
// Báo 29/08: "cho cái chữ ký to lên, cái ngày tháng năm với ký scts gần lại chữ ký được
// không". Ảnh chụp cho thấy ảnh chữ ký ghim cứng 42% chiều ngang, khối chữ cố định 8px, hai
// phần bị `space-between` đẩy ra hai đầu — ô càng to thì chữ ký trong càng nhỏ và càng xa nhau.
//
// Cỡ chữ phải theo CHIỀU CAO Ô. CSS thuần không đọc được kích thước phần tử nên việc này do
// _fitSig() làm; test này chạy đúng hàm đó, không grep.
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

const m = HTML.match(/function _fitSig\(boxEl, node\)\s*\{[\s\S]*?\n  \}/);
if (!m) { console.log("  FAIL: khong tim thay _fitSig"); process.exit(1); }

const sandbox = { Math, console };
vm.createContext(sandbox);
vm.runInContext(m[0] + "\nglobalThis._fitSig = _fitSig;", sandbox, { filename: "fitsig.js" });
const fit = sandbox._fitSig;

let pass = 0, fail = 0;
const ok = (c, msg) => { if (c) pass++; else { fail++; console.log("  FAIL: " + msg); } };
const px = (s) => parseFloat(String(s || "").replace("px", ""));

// Nút giả tối thiểu: chỉ cần một chỗ để ghi style.fontSize.
const node = () => ({ style: {} });

console.log("Co chu ky theo chieu cao o");

// --- ô cao thì chữ to theo -------------------------------------------------
let small = node(), big = node();
fit({ offsetHeight: 60 }, small);
fit({ offsetHeight: 200 }, big);
ok(px(big.style.fontSize) > px(small.style.fontSize),
   "o cao gap 3 -> chu phai to hon (" + small.style.fontSize + " vs " + big.style.fontSize + ")");

// --- ô nhỏ vẫn phải đọc được ------------------------------------------------
let tiny = node();
fit({ offsetHeight: 12 }, tiny);
ok(px(tiny.style.fontSize) >= 6, "o rat nho -> khong duoi san 6px (dang " + tiny.style.fontSize + ")");

// --- ô rất to không được để chữ phình vô hạn --------------------------------
let huge = node();
fit({ offsetHeight: 2000 }, huge);
ok(px(huge.style.fontSize) <= 15, "o rat to -> khong vuot tran 15px (dang " + huge.style.fontSize + ")");

// --- 4 dòng chữ phải VỪA trong ô, đây mới là điều thật sự cần đúng ----------
// Khoi chu co 4 dong, line-height 1.2. Tran ra ngoai o la loi hien thi thay duoc bang mat.
for (const h of [40, 80, 120, 200, 400]) {
  const n = node();
  fit({ offsetHeight: h }, n);
  const used = px(n.style.fontSize) * 1.2 * 4;
  ok(used <= h, "o cao " + h + " -> 4 dong chu cao " + used.toFixed(1) + " phai <= " + h);
}

// --- ô chưa dựng lên thì để nguyên, không ghi 0px ---------------------------
let unmounted = node();
fit({ offsetHeight: 0 }, unmounted);
ok(!unmounted.style.fontSize,
   "o chua co chieu cao -> KHONG duoc dat 0px (chu se bien mat)");
let nothing = node();
fit(null, nothing);
ok(!nothing.style.fontSize, "khong co o -> khong no, khong dat gi");

// --- CSS phải gom ảnh và chữ vào nhau ---------------------------------------
ok(/\.ecd-box \.sigprev\{[^}]*justify-content:center/.test(HTML),
   "anh va khoi chu phai dinh vao nhau o giua, khong day ra hai dau");
ok(/\.ecd-box \.sigprev img\{[^}]*height:100%/.test(HTML),
   "anh chu ky lay het chieu cao o");
ok(!/\.ecd-box \.sigprev img\{[^}]*flex:0 0 42%/.test(HTML),
   "khong ghim cung 42% chieu ngang nua");

console.log("  " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
