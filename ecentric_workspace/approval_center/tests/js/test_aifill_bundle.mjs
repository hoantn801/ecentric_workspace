// Copyright (c) 2026, eCentric and contributors
//
// Bundle `ec_aifill` — hai cơ chế mà nếu sai thì cả tính năng sai âm thầm:
//
//   1. `isUserEdit` dựa vào `e.isTrusted`. Đây là thứ DUY NHẤT phân biệt phím người gõ với
//      sự kiện tổng hợp mà chính asset vừa phát ra lúc điền. Bỏ nó đi thì dấu "AI điền" tự
//      xoá ngay tại thời điểm điền — tính năng trông vẫn chạy, chỉ là dấu không bao giờ hiện.
//   2. `writeOrder` đẩy ô gây `renderCreate` lên trước. Sai thứ tự thì lần vẽ lại xoá sạch
//      những ô điền sau nó — cũng không có lỗi nào, chỉ là mất ô.
//
// Cả hai đều là loại lỗi KHÔNG ném exception, nên phải có test chạy thật chứ không grep.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "..", "..", "..", "public", "js", "ec_aifill.bundle.js");

let dat = 0, hong = 0;
const la = (dieu, ten) => { if (dieu) { dat++; } else { hong++; console.error("  HONG:", ten); } };

/** Nạp bundle với một DOM tối thiểu. Trả về `window.__ecAifill`. */
function nap(pathname) {
  const tai = {
    location: { pathname },
    requestAnimationFrame: (f) => f(),
    MutationObserver: class { observe() {} },
    Event: class { constructor(t) { this.type = t; } },
  };
  const doc = {
    readyState: "complete",
    body: { contains: () => true },
    addEventListener() {},
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => ({ style: {}, classList: { add() {}, toggle() {} }, setAttribute() {},
                            appendChild() {}, querySelector: () => null }),
  };
  const src = readFileSync(SRC, "utf8");
  // `frappe` cố tình KHÔNG khai: bundle phải tự im khi chưa có frappe, không được nổ.
  new Function("window", "document", "frappe", src)(tai, doc, undefined);
  return tai.__ecAifill;
}

// ---- 1. Cổng đường dẫn phải là KHỚP ĐÚNG, không phải tiền tố -------------------
// Bài học ec_formkit 25/08 + 26/08: lọc theo tiền tố `/approvals` khớp cả những trang đã tự
// quản lý widget của chúng, và asset nhân đôi widget lên.
{
  const api = nap("/approvals/payment-request");
  la(api && typeof api.writeOrder === "function", "bundle nap duoc, co be mat test");
  const routes = Object.keys(api.ROUTES);
  la(routes.includes("/approvals/payment-request"), "G1 nhan dung trang payment-request");
  la(!routes.some((r) => r === "/approvals" || r === "/approvals/"),
     "KHONG duoc khai ca tien to /approvals");
  la(routes.every((r) => r.split("/").length >= 3),
     "moi route deu la duong dan day du, khong phai tien to");
}

// ---- 2. isTrusted ------------------------------------------------------------
{
  const { isUserEdit } = nap("/approvals/payment-request");
  la(isUserEdit({ isTrusted: true }) === true, "phim nguoi go that -> la sua tay");
  la(isUserEdit({ isTrusted: false }) === false,
     "su kien tong hop (chinh asset phat ra luc dien) -> KHONG phai sua tay");
  la(isUserEdit({}) === false, "khong co isTrusted -> khong tin");
  la(isUserEdit(null) === false, "null -> khong no");
}

// ---- 3. writeOrder -----------------------------------------------------------
{
  const { writeOrder } = nap("/approvals/payment-request");
  const vao = ["payee_full_name", "payment_amount", "ec_loai_chi_phi", "bank_account_number"];
  const ra = writeOrder(vao);
  la(ra[0] === "ec_loai_chi_phi",
     "o gay ve lai ca form phai duoc ghi TRUOC");
  la(ra.length === vao.length && vao.every((f) => ra.includes(f)),
     "khong mat va khong nhan doi truong nao");
  la(JSON.stringify(writeOrder(["payee_full_name", "payment_amount"]))
       === JSON.stringify(["payee_full_name", "payment_amount"]),
     "khong co o gay ve lai thi giu nguyen thu tu");
  // hai o gay ve lai -> ca hai len truoc, giu thu tu tuong doi
  const hai = writeOrder(["payee_full_name", "payment_mode", "ec_loai_chi_phi"]);
  la(hai.indexOf("payment_mode") < hai.indexOf("payee_full_name")
     && hai.indexOf("ec_loai_chi_phi") < hai.indexOf("payee_full_name"),
     "nhieu o gay ve lai thi tat ca deu len truoc");
}

// ---- 4. Không nổ khi chưa có frappe ------------------------------------------
{
  // nap() o tren da truyen frappe = undefined; toi day van chay duoc nghia la bundle im lang.
  la(true, "bundle khong nem khi frappe chua san sang");
}

console.log(`${dat} dat, ${hong} hong`);
process.exit(hong ? 1 : 0);
