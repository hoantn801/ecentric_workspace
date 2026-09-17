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

// ---- 5. G2 — đọc danh sách tệp từ DOM của trang -------------------------------
// Asset KHÔNG đọc `state.draft._attachments` của trang: biến đó là nội bộ của trang và đổi
// lúc nào không ai biết. DOM `.ec-file > a[href]` mới là hợp đồng giữa hai bên.
function goc(hrefs) {
  const nut = hrefs.map(([href, text]) => ({
    getAttribute: (k) => (k === "href" ? href : null),
    textContent: text,
  }));
  return { querySelectorAll: () => nut };
}

{
  const { readAttachments, ATTACH_SEL } = nap("/approvals/payment-request");
  la(!!ATTACH_SEL.PAYMENT_REQUEST, "G2 khai selector dinh kem cho payment-request");

  const ra = readAttachments(goc([
    ["/private/files/hoa-don.pdf", "hoa-don.pdf"],
    ["/files/anh.png", "anh.png"],
  ]));
  la(ra.length === 2, "doc duoc ca tep rieng tu lan tep cong khai");
  la(ra[0].url === "/private/files/hoa-don.pdf" && ra[0].name === "hoa-don.pdf",
     "lay dung url va ten hien thi");

  // Trùng url: trang có thể vẽ cùng một tệp ở hai chỗ (danh sách + ô Attach).
  la(readAttachments(goc([
       ["/private/files/a.pdf", "a.pdf"],
       ["/private/files/a.pdf", "a.pdf"],
     ])).length === 1, "khu trung theo url");

  // Link KHÔNG phải tệp trong kho (link ngoài, link Desk) phải bị bỏ — nếu lọt thì server
  // trả "not_found" và người dùng thấy một lỗi vô nghĩa cho thứ họ không hề chọn.
  la(readAttachments(goc([
       ["https://vidu.com/a.pdf", "ngoai"],
       ["/app/file/FILE-1", "desk"],
       ["/private/files/that.pdf", "that.pdf"],
     ])).length === 1, "chi nhan duong dan trong kho tep cua Frappe");

  la(readAttachments(null).length === 0, "khong co DOM -> khong no");
}

// ---- 6. G2 — tệp nào thực sự được gửi lên ------------------------------------
{
  const { pickedUrls } = nap("/approvals/payment-request");
  const ds = ["a", "b", "c", "d", "e", "f"].map((x) => ({ url: "/private/files/" + x + ".pdf" }));

  la(pickedUrls(ds, {}, 5).length === 5,
     "quá tran thi CAT o client, khong gui thua roi de server bo");
  la(JSON.stringify(pickedUrls(ds.slice(0, 2), {}, 5))
       === JSON.stringify(["/private/files/a.pdf", "/private/files/b.pdf"]),
     "mac dinh la BAT: dinh kem vao phieu thi gan nhu luon muon AI doc");

  const bo = {};
  bo[ds[0].url] = false;
  la(pickedUrls(ds.slice(0, 3), bo, 5).length === 2, "bo tick thi khong gui tep do");
  la(pickedUrls(ds.slice(0, 3), bo, 5).indexOf(ds[0].url) === -1,
     "tep bi bo tick khong duoc lot vao danh sach");

  // Cắt theo trần phải chạy SAU khi bỏ tick, nếu không thì bỏ một tệp ở đầu danh sách lại
  // không kéo được tệp thứ 6 lên thay.
  const bo2 = {};
  bo2[ds[0].url] = false;
  la(pickedUrls(ds, bo2, 5).length === 5, "bo mot tep thi tep ke tiep duoc lay bu");

  la(pickedUrls(null, {}, 5).length === 0, "danh sach rong -> khong no");
}

console.log(`${dat} dat, ${hong} hong`);
process.exit(hong ? 1 : 0);
