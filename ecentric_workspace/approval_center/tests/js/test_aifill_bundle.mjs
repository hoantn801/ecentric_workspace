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

// ---- 5. G2 — cổng nhận tệp ở client ------------------------------------------
// Panel có Ô THẢ TỆP CỦA RIÊNG NÓ. Bản đầu 17/09 đi bòn danh sách tệp từ DOM của form —
// sai, vì mục "TÀI LIỆU & KÝ SỐ" của form chỉ mở SAU KHI lưu nháp (nên lúc cần AI điền thì
// chưa có chỗ nào thả tệp), và mục đó phục vụ ký số chứ không phải AI.
{
  const { refuseReason } = nap("/approvals/payment-request");
  const EXTS = ["pdf", "png", "jpg", "jpeg", "txt"];
  const f = (name, size) => ({ name, size });

  la(refuseReason(f("hoa-don.pdf", 1000), [], 5, EXTS) === null, "PDF binh thuong -> nhan");
  la(refuseReason(f("anh.PNG", 1000), [], 5, EXTS) === null, "duoi VIET HOA van nhan");

  // Office phải có câu trả lời RIÊNG: "xuất ra PDF" khác hẳn "không đọc được".
  const office = refuseReason(f("hop-dong.docx", 1000), [], 5, EXTS);
  la(office && office.includes("PDF"), "Office -> bao xuat ra PDF, khong phai 'khong doc duoc'");
  const la_ = refuseReason(f("chay.exe", 1000), [], 5, EXTS);
  la(la_ && !la_.includes("PDF"), "kieu la -> cau tra loi khac Office");

  la(refuseReason(f("to.pdf", 11 * 1024 * 1024), [], 5, EXTS) !== null, "qua 10MB -> bo");
  la(refuseReason(f("rong.pdf", 0), [], 5, EXTS) !== null, "tep rong -> bo");
  la(refuseReason(f("khongduoi", 100), [], 5, EXTS) !== null, "khong co duoi -> bo");

  const day = [1, 2, 3, 4, 5].map((n) => ({ name: "t" + n + ".pdf", size: 10 }));
  la(refuseReason(f("them.pdf", 100), day, 5, EXTS) !== null, "qua tran 5 tep -> bo");
  la(refuseReason(f("them.pdf", 100), day.slice(0, 4), 5, EXTS) === null, "con cho -> nhan");

  // Thả nhầm hai lần cùng một tệp là chuyện thường; tính tiền hai lần thì không.
  la(refuseReason(f("a.pdf", 500), [{ name: "a.pdf", size: 500 }], 5, EXTS) !== null,
     "trung ten VA trung kich thuoc -> da co roi");
  la(refuseReason(f("a.pdf", 501), [{ name: "a.pdf", size: 500 }], 5, EXTS) === null,
     "trung ten nhung KHAC kich thuoc -> van la tep khac");
  la(refuseReason(null, [], 5, EXTS) !== null, "khong co tep -> khong no");
}

// ---- 6. G2 — khối tệp phải nói rõ tệp này KHÔNG phải chứng từ của phiếu --------
{
  const { filesHtml, kb } = nap("/approvals/payment-request");

  const rong = filesHtml([], 5, false);
  la(rong.includes("ec-aifill-drop"), "chua co tep -> van phai co O THA TEP");
  la(rong.includes("Thêm chứng từ"),
     "noi thang: chung tu cua phieu dinh kem o buoc khac, dung de nguoi dung tu doan");

  const mot = filesHtml([{ name: "hoa-don.pdf", size: 2048 }], 5, false);
  la(mot.includes("hoa-don.pdf"), "co ten tep");
  la(mot.includes("data-rm=\"0\""), "co nut bo tep");
  la(mot.includes("ec-aifill-drop"), "van con o tha de them tep nua");

  const day = [1, 2, 3, 4, 5].map((n) => ({ name: "t" + n + ".pdf", size: 10 }));
  la(filesHtml(day, 5, false).includes("disabled"), "du tran -> o tha bi khoa");

  la(filesHtml([], 5, true).includes("Đang tải"), "dang tai -> noi ra");

  la(kb(2048) === "2 KB" && kb(2097152) === "2.0 MB", "kich thuoc doc duoc");
  la(kb(0) === "", "khong co kich thuoc -> khong in '0'");
}

// ---- 7. Asset KHÔNG được tự nuôi MutationObserver của chính nó -----------------
// SỰ CỐ 17/09/2026 trên production: `renderFiles` ghi `innerHTML` mỗi lần observer chạy;
// cái ghi đó LÀ một mutation trong `document.body` → observer chạy lại → treo cả trang.
// Trang /approvals/payment-request chỉ còn mỗi panel, form biến mất.
// Hai cơ chế chặn, mỗi cái đủ một mình, và cả hai đều phải có test.
{
  const { filesHtml, fromUs } = nap("/approvals/payment-request");

  // (a) HTML phải TẤT ĐỊNH — đó là thứ cho phép so chuỗi để khỏi ghi lại.
  const ds = [{ name: "a.pdf", size: 100 }];
  la(filesHtml(ds, 5, false) === filesHtml(ds, 5, false),
     "cung dau vao -> cung mot chuoi HTML (so chuoi moi dung duoc)");
  la(filesHtml([], 5, false) === filesHtml([], 5, false), "truong hop rong cung tat dinh");
  la(filesHtml(ds, 5, false) !== filesHtml([], 5, false),
     "co tep va khong co tep phai KHAC nhau");
  la(filesHtml(ds, 5, true) !== filesHtml(ds, 5, false),
     "dang tai hay khong phai ra HTML KHAC - neu khong, nho dem nuot mat trang thai");

  // (b) Mutation do chính panel này gây ra thì bỏ qua.
  const panel = { contains: (n) => n === "trong-panel" };
  la(fromUs([{ target: "trong-panel" }], panel) === true,
     "mutation trong panel -> BO QUA (khong chay lai vong ve)");
  la(fromUs([{ target: "ngoai-panel" }], panel) === false,
     "mutation ngoai panel -> phai xu ly");
  la(fromUs([{ target: "trong-panel" }, { target: "ngoai-panel" }], panel) === false,
     "lan lon thi van phai xu ly - bo sot mot lan ve cua trang la hong dau AI dien");
  la(fromUs([], panel) === false, "danh sach rong -> khong coi la cua minh");
  la(fromUs([{ target: "x" }], null) === false, "chua co panel -> khong no");
}

// ---- 8. G2 — bản đồ hoàn thành: ô bắt buộc nào còn trống ----------------------
// Đọc dấu `*` mà CHÍNH TRANG đã vẽ, không theo danh sách cứng: danh sách cứng lệch khỏi
// form là lệch âm thầm. Và chỉ tính ô ĐANG HIỆN — `request_attachment` là ô bắt buộc bị
// khối ký số ẩn đi, tô đỏ nó là chỉ vào hư không (đúng cái ngõ cụt BOT 12 của trang).
{
  function o({ req = true, value = "", hien = true, type = "text", checked = false }) {
    const el = { value, type, checked, offsetParent: hien ? {} : null };
    const lab = { querySelector: (s) => (s === ".req" && req ? {} : null) };
    return {
      querySelector: (s) => (s === "label" ? lab : el),
      classList: { _v: [], contains(c) { return this._v.includes(c); },
                   add(c) { this._v.push(c); } },
    };
  }
  function nap2(boxes) {
    const tai = { location: { pathname: "/approvals/payment-request" },
      requestAnimationFrame: (f) => f(), MutationObserver: class { observe() {} },
      Event: class { constructor(t) { this.type = t; } } };
    const doc = { readyState: "complete", body: { contains: () => true },
      addEventListener() {}, querySelector: () => null,
      querySelectorAll: (s) => (s === "[data-fld]" ? boxes : []),
      createElement: () => ({ style: {}, classList: { add() {}, toggle() {} },
                              setAttribute() {}, appendChild() {}, querySelector: () => null }) };
    const src = readFileSync(SRC, "utf8");
    new Function("window", "document", "frappe", src)(tai, doc, undefined);
    return tai.__ecAifill;
  }

  const trong = o({});
  const dayDu = o({ value: "Trần Hoàn" });
  const khongBatBuoc = o({ req: false });
  const an = o({ hien: false });
  const tick = o({ type: "checkbox", checked: false });

  const ra = nap2([trong, dayDu, khongBatBuoc, an, tick]).missingRequired();
  la(ra.includes(trong), "o bat buoc va trong -> con thieu");
  la(!ra.includes(dayDu), "o da co gia tri -> khong con thieu");
  la(!ra.includes(khongBatBuoc), "o KHONG bat buoc va trong -> khong tinh la thieu");
  la(!ra.includes(an), "o bat buoc nhung DANG AN -> khong to do, khong chi vao hu khong");
  la(ra.includes(tick), "o tick bat buoc chua tick -> con thieu");
  la(ra.length === 2, "dung hai o, khong nhieu hon");

  // Khoảng trắng không phải là đã điền.
  la(nap2([o({ value: "   " })]).missingRequired().length === 1,
     "chi co khoang trang -> van la con thieu");
}

console.log(`${dat} dat, ${hong} hong`);
process.exit(hong ? 1 : 0);
