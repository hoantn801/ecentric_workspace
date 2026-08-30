// Copyright (c) 2026, eCentric and contributors
// MỘT bề mặt tải lên duy nhất — ô `request_attachment` cũ phải ở yên trong bóng tối.
//
// Bộ test này ra đời sáng 30/08 để canh một bản vá CSS mở lại ô cũ ở màn hình "Chỉnh sửa &
// gửi lại", khi phát hiện lúc bị trả lại thì cả hai bề mặt tải lên đều đóng.
//
// Bản vá đó ĐÃ BỊ GỠ trong cùng ngày, sau khi Hoàn hỏi đúng câu: sao lại để chỗ đó? Nó dựng
// lại chính bề mặt thứ hai mà thiết kế cố ý bỏ, và đặt ô tải tài liệu ra NGOÀI khối
// "TÀI LIỆU & KÝ SỐ" — nơi người dùng thực sự đi tìm.
//
// Cách làm đúng: mở nút "+ Tải tài liệu" khi phiếu ở trạng thái Cần bổ sung, tệp lên theo
// diện BỘ CHỨNG TỪ (không ký). Xem test_supporting_upload_when_sent_back.py.
//
// Giữ lại file này với nhiệm vụ ngược lại: bảo đảm không ai vô tình dựng lại bản vá cũ.
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

// BỎ CHÚ THÍCH TRƯỚC KHI BÓC. Chú thích ở trên nhắc đúng những chuỗi mà test này tìm; để
// nguyên thì phép kiểm khớp với lời văn của chính nó chứ không với CSS. Sáng 30/08 nó đã
// khớp như vậy thật: đổi bộ chọn mà test vẫn xanh.
const CSS = fs.readFileSync(PAGE, "utf8").replace(/\/\*[\s\S]*?\*\//g, " ");

let pass = 0, fail = 0;
const ok = (c, msg) => { if (c) pass++; else { fail++; console.log("  FAIL: " + msg); } };

console.log("Mot be mat tai len duy nhat");

const rules = [];
const re = /([^{}]*\[data-upload="request_attachment"\][^{}]*)\{([^}]*)\}/g;
let m;
while ((m = re.exec(CSS)) !== null) {
  rules.push({ selector: m[1].replace(/\s+/g, " ").trim(), body: m[2].trim() });
}

ok(rules.length === 1,
   "phai co DUNG MOT luat cham toi o cu (dang " + rules.length + ") - luat thu hai nghia la "
   + "ai do da mo lai be mat tai len thu hai");
ok(rules.length === 1 && /display\s*:\s*none/.test(rules[0].body),
   "luat do phai la luat AN");
ok(!/payr-formwrap:has\(#payr-resubmit\)/.test(CSS),
   "ban va 30/08 da bi go - khong duoc dung lai");

// Bề mặt đúng phải mở được khi bị trả lại. Nếu ai đó gỡ mất cờ này thì lại rơi vào bế tắc
// cũ: bị trả lại mà không có chỗ nào để đính kèm.
const HTML = fs.readFileSync(PAGE, "utf8");
ok(/STATE\.can_add_supporting/.test(HTML),
   'nut "+ Tai tai lieu" phai mo theo co can_add_supporting khi bi tra lai');
ok(/upBtn\.disabled = [^;]*supportOnly/.test(HTML),
   "co do phai that su duoc dung de bat nut, khong chi doc ra roi bo do");

console.log("  " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
