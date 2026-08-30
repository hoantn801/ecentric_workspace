// Copyright (c) 2026, eCentric and contributors
// Biểu tượng trong banner phải mang kích thước NGAY TRÊN THẺ.
//
// 31/08: banner "Cần bổ sung thông tin" hiện với icon lơ lửng giữa thẻ và chữ dồn sát mép
// phải. Icon là <svg> nội tuyến lấy kích thước từ `#ec-payr-root .icon{width:18px}` — một
// luật CÓ PHẠM VI. Chỗ nào banner render ngoài tổ tiên đó thì luật không với tới, SVG rơi về
// mặc định 300x150px của trình duyệt, và một khối rộng 300px đẩy câu chữ chạy ngang thẻ.
//
// Một thành phần không nên phụ thuộc vào việc nó được gắn ở đâu trong cây DOM.
import fs from "fs";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = (() => {
  for (const r of ["../../features/payment_request/ui/main_section.html",
                   "../../../features/payment_request/ui/main_section.html"]) {
    const p = path.join(HERE, r);
    if (fs.existsSync(p)) return p;
  }
  throw new Error("khong tim thay main_section.html");
})();
const HTML = fs.readFileSync(PAGE, "utf8");

let pass = 0, fail = 0;
const ok = (c, msg) => { if (c) pass++; else { fail++; console.log("  FAIL: " + msg); } };

console.log("Kich thuoc bieu tuong banner");

const icons = HTML.match(/<svg[^>]*class="icon"[^>]*>/g) || [];
ok(icons.length > 0, "khong tim thay bieu tuong nao - phep kiem dang mu");

icons.forEach(function (tag, i) {
  ok(/\bwidth="\d+"/.test(tag) && /\bheight="\d+"/.test(tag),
     "bieu tuong #" + (i + 1) + " thieu width/height tren THE: " + tag.slice(0, 70));
  ok(/flex\s*:\s*none/.test(tag),
     "bieu tuong #" + (i + 1) + " phai co flex:none, khong thi no co the bi keo gian");
});

// Luat CSS co pham vi VAN nen ton tai - no phu cho cac cho khac trong trang - nhung khong
// duoc la thu DUY NHAT quyet dinh kich thuoc.
ok(/#ec-payr-root \.icon\{[^}]*width:18px/.test(HTML),
   "van giu luat CSS cu lam mac dinh cho phan con lai cua trang");

console.log("  " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
