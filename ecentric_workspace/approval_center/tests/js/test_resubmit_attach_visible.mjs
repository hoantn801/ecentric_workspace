// Copyright (c) 2026, eCentric and contributors
// Màn hình "Chỉnh sửa & gửi lại" phải có CHỖ ĐỂ ĐÍNH KÈM.
//
// 30/08: Hoàn bấm Chỉnh sửa & gửi lại để bổ sung chứng từ theo yêu cầu của Kế toán, và trên
// màn hình không có một bề mặt tải lên nào. Hai luật gặp nhau:
//
//   * document_signing_section.html ẩn ô `request_attachment` cũ ("một bề mặt tải lên duy nhất");
//   * bề mặt còn lại — "+ Tải tài liệu" — bị vô hiệu khi gói ký còn Locked, mà sau khi bị
//     trả lại thì nó CHÍNH LÀ Locked (bản mới chỉ được tạo BÊN TRONG thao tác Gửi lại).
//
// Ô vẫn nằm trong DOM, chỉ display:none. Vì thế nó trông như lỗi backend suốt một đêm.
//
// Test này kiểm CSS bằng cách dựng đúng cây DOM của hai chế độ rồi hỏi trình so khớp chọn
// luật nào — không grep chuỗi CSS.
import fs from "fs";
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
  throw new Error("khong tim thay document_signing_section.html");
})();
const HTML = fs.readFileSync(PAGE, "utf8");

let pass = 0, fail = 0;
const ok = (c, msg) => { if (c) pass++; else { fail++; console.log("  FAIL: " + msg); } };

console.log("O dinh kem tren man hinh gui lai");

// BỎ CHÚ THÍCH TRƯỚC KHI BÓC. Chú thích của chính bản sửa này có nhắc tên `#payr-resubmit`,
// nên nếu để nguyên thì phép kiểm "bộ chọn phải neo vào #payr-resubmit" sẽ khớp với lời văn
// giải thích chứ không phải với luật CSS — và nó ĐÃ khớp như vậy: đổi bộ chọn sang `.card`
// mà test vẫn xanh. Một phép kiểm đọc trúng lời bình luận của chính nó thì không kiểm gì cả.
const CSS = HTML.replace(/\/\*[\s\S]*?\*\//g, " ");

// Bóc mọi luật đụng tới ô đính kèm, giữ NGUYÊN THỨ TỰ (thứ tự quyết định luật nào thắng).
const rules = [];
const re = /([^{}]*\[data-upload="request_attachment"\][^{}]*)\{([^}]*)\}/g;
let m;
while ((m = re.exec(CSS)) !== null) {
  rules.push({ selector: m[1].replace(/\s+/g, " ").trim(), body: m[2].trim() });
}
ok(rules.length >= 2,
   "phai co it nhat HAI luat: mot an, mot mo lai o che do sua (dang " + rules.length + ")");

const hideRule = rules.find(r => /display\s*:\s*none/.test(r.body));
const showRule = rules.find(r => /display\s*:\s*(flex|block)/.test(r.body));
ok(!!hideRule, "van con luat an o che do BINH THUONG (mot be mat tai len duy nhat)");
ok(!!showRule, "phai co luat mo lai o o che do sua");

if (hideRule && showRule) {
  // Luật mở phải đứng SAU và phải chặt hơn, nếu không nó không thắng nổi `!important` kia.
  ok(rules.indexOf(showRule) > rules.indexOf(hideRule),
     "luat mo phai dung SAU luat an");
  ok(/!important/.test(showRule.body),
     "luat an dung !important nen luat mo cung phai co, khong thi vo tac dung");
  // Neo phải là thứ CHỈ tồn tại ở chế độ sửa. `#payr-resubmit` là nút "Gửi lại", chỉ được
  // dựng trong nhánh `editing` của main_section.html.
  ok(/#payr-resubmit/.test(showRule.selector),
     "phai neo vao dau hieu RIENG cua che do sua, khong phai mot lop chung chung");
  // Luật mở KHÔNG được rộng hơn: nó chỉ đúng bên trong form đang sửa.
  ok(/payr-formwrap/.test(showRule.selector),
     "gioi han trong khung form, khong mo tran ra ca trang");
}

// Neo phải thật sự tồn tại trong trang - nếu ai đó đổi tên nút, luật CSS trên thành vô nghĩa
// và ô lại biến mất trong im lặng.
const MAIN = (() => {
  for (const r of ["../../features/payment_request/ui/main_section.html",
                   "../../../features/payment_request/ui/main_section.html",
                   "../../../approval_center/features/payment_request/ui/main_section.html"]) {
    const p = path.join(HERE, r);
    if (fs.existsSync(p)) return fs.readFileSync(p, "utf8");
  }
  return null;
})();
ok(MAIN !== null, "doc duoc main_section.html (neu khong, phep kiem duoi day dang mu)");
if (MAIN) {
  ok(/id="payr-resubmit"/.test(MAIN),
     'neo #payr-resubmit phai co that trong main_section.html');
  ok(/class="payr-formwrap"/.test(MAIN),
     'khung .payr-formwrap phai co that');
  // Và nút đó CHỈ được dựng ở chế độ sửa - nếu nó có mặt cả ở chế độ tạo thì luật CSS sẽ
  // mo o dinh kem ca o man hinh tao moi, tuc pha vo "mot be mat tai len duy nhat".
  const editingBranch = MAIN.split("var actions = editing")[1] || "";
  const created = editingBranch.split(":")[0] || "";
  ok(/payr-resubmit/.test(created),
     'nut "Gui lai" phai nam o NHANH editing, khong phai nhanh tao moi');
}

console.log("  " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
