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
//
// 18/09 — mô hình giả ở đây PHẢI giữ đúng ba hình dạng có thật trên form, vì bản đầu chỉ
// dựng được hình dạng thứ nhất và chính chỗ đó lọt lỗi:
//   (a) ô thường: <input data-model> nhìn thấy được;
//   (b) combobox `ec_formkit`: <select data-model> bị display:none, nút thay thế mới hiện;
//   (c) ô ngày `ec_datepicker`: <input type=date data-model> bị clip, nút thay thế mới hiện.
// (b) và (c) là "Brand liên quan", "Loại chi phí", "Ngày thanh toán", "Kỳ ghi nhận chi phí"
// — bốn ô hay bị bỏ sót nhất, và là bốn ô bản đầu KHÔNG tô.
{
  /** @param anCtrl  ô điều khiển bị giấu/clip (combobox + datepicker) nhưng KHỐI vẫn hiện.
   *  @param anBox   cả khối bị trang ẩn đi (khối ký số đóng).
   *  @param nhieu   có một <input> phụ trợ đứng TRƯỚC ô mang data-model. */
  function o({ req = true, value = "", anBox = false, anCtrl = false,
               type = "text", checked = false, nhieu = false }) {
    const el = { value, type, checked, offsetParent: anCtrl ? null : {},
                 getAttribute: (a) => (a === "data-model" ? "x" : null) };
    const phu = { value: "", type: "text", offsetParent: {},
                  getAttribute: () => null };
    const lab = { querySelector: (s) => (s === ".req" && req ? {} : null) };
    return {
      offsetParent: anBox ? null : {},
      querySelector: (s) => {
        if (s === "label") return lab;
        if (s === "[data-model]") return el;
        return nhieu ? phu : el;          // "ô đầu tiên trong khối" — phỏng đoán cũ
      },
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
  const an = o({ anBox: true });
  const tick = o({ type: "checkbox", checked: false });
  const combo = o({ anCtrl: true });                       // Brand liên quan chưa chọn
  const ngay = o({ anCtrl: true, type: "date" });          // Ngày thanh toán chưa chọn
  const comboDaChon = o({ anCtrl: true, value: "Abbott" });

  const ra = nap2([trong, dayDu, khongBatBuoc, an, tick, combo, ngay, comboDaChon])
    .missingRequired();
  la(ra.includes(trong), "o bat buoc va trong -> con thieu");
  la(!ra.includes(dayDu), "o da co gia tri -> khong con thieu");
  la(!ra.includes(khongBatBuoc), "o KHONG bat buoc va trong -> khong tinh la thieu");
  la(!ra.includes(an), "KHOI bi trang an di -> khong to do, khong chi vao hu khong");
  la(ra.includes(tick), "o tick bat buoc chua tick -> con thieu");
  la(ra.includes(combo), "combobox (select bi display:none) van bi bat khi con trong");
  la(ra.includes(ngay), "o ngay (input bi clip) van bi bat khi con trong");
  la(!ra.includes(comboDaChon), "combobox da chon -> khong con thieu");
  la(ra.length === 4, "dung bon o, khong nhieu hon");

  // Khoảng trắng không phải là đã điền.
  la(nap2([o({ value: "   " })]).missingRequired().length === 1,
     "chi co khoang trang -> van la con thieu");

  // Một asset khác chèn <input> phụ trợ vào trước thì "ô đầu tiên" trỏ nhầm chỗ.
  la(nap2([o({ value: "Trần Hoàn", nhieu: true })]).missingRequired().length === 0,
     "doc theo [data-model], khong doc theo o dau tien trong khoi");
}

// ---- 9. Bản đồ màu phải tô lên BỀ MẶT NGƯỜI DÙNG NHÌN THẤY ---------------------
// Sự cố 18/09: CSS tô `input`/`select`/`.ec-cb` — cả ba đều là thứ vô hình ở bốn ô dùng
// combobox/datepicker. `.ec-cb` là khung bọc KHÔNG có nền; nền nằm trên `.ec-cb-display`.
{
  const css = readFileSync(
    join(here, "..", "..", "..", "public", "css", "ec_aifill.bundle.css"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "");   // chú thích dính vào bộ chọn thì so sánh trượt
  // Có mặt trong file là chưa đủ: `.ec-cb-display:focus` cũng chứa đúng chuỗi đó mà lại
  // là luật TRUNG HOÀ màu. Phải hỏi: bộ chọn này có nằm trong luật ĐẶT NỀN không.
  const datNen = (bo) => css
    .split("}")
    .some((khoi) => {
      const [chon, than] = [khoi.split("{")[0] || "", khoi.split("{")[1] || ""];
      return chon.split(",").some((x) => x.trim() === bo) && /background:\s*rgba\(/.test(than);
    });
  for (const lop of ["lit", "gap"]) {
    la(datNen(`.ec-aifill-${lop} .ec-cb-display`),
       `${lop}: NEN to len nut combobox, khong to len khung bao`);
    la(datNen(`.ec-aifill-${lop} .ec-dp-field`),
       `${lop}: NEN to len nut chon ngay`);
  }
  la(!/\.ec-aifill-(lit|gap) \.ec-cb\{/.test(css),
     "KHONG con to len .ec-cb (khung bao khong co nen - ban cu)");
  la(css.includes("--ec-dp-muted") === false && css.includes(".ec-dp-empty .ec-dp-val"),
     "o ngay con trong: chu mo lay sac do, khong de mac dinh xam");
  la(css.includes(".ec-cb-display.ec-cb-placeholder"),
     "combobox chua chon: chu mo lay sac do");
}

// ---- 10. G2b — "Tạo hàng loạt" -----------------------------------------------
// Trần 10 là TRẦN QUYẾT ĐỊNH. Ô cam kết phải ghi RÕ SỐ PHIẾU (A61 §3) — con số đổi theo
// lô, không phải chữ chết. Và không có nút duyệt-tất-cả ở bất kỳ đâu (A61 §1).
{
  function nap3() {
    const tai = { location: { pathname: "/approvals/payment-request" },
      requestAnimationFrame: (f) => f(), MutationObserver: class { observe() {} },
      Event: class { constructor(t) { this.type = t; } } };
    const doc = { readyState: "complete", body: { contains: () => true },
      addEventListener() {}, querySelector: () => null, querySelectorAll: () => [],
      createElement: () => ({ style: {}, classList: { add() {}, toggle() {} },
                              setAttribute() {}, appendChild() {}, querySelector: () => null }) };
    new Function("window", "document", "frappe", readFileSync(SRC, "utf8"))(tai, doc, undefined);
    return tai.__ecAifill;
  }
  const A = nap3();
  const day = { payee_full_name: "Nguyễn Thanh Phụng", payment_amount: 3000000,
                account_bank: "Vietcombank", bank_account_number: "9857672398",
                payment_date: "2026-09-20", reason: "Booking video" };
  const dong = (f, x = {}) => Object.assign({ key: "r1", file: { name: "hd.pdf", size: 10 },
                                              fields: f }, x);

  la(A.money(3000000).replace(/\D/g, "") === "3000000", "tien giu nguyen chu so");
  la(A.money("") === "" && A.money(0) === "", "khong co tien -> chuoi rong, khong phai 0");
  la(A.money(3000000) !== "3000000", "tien co dau phan cach nhom");

  la(A.rowState(dong(day))[0] === "Sẵn sàng", "du o -> San sang");
  // A58: bản nháp chưa đi qua workflow nào -> KHÔNG được xanh.
  la(A.rowState(dong(day))[1] === "gray", "San sang la XAM, khong phai xanh (A58)");
  la(A.rowState(dong({ payee_full_name: "A" }))[0] === "Thiếu 5 ô", "dem dung so o con thieu");
  la(A.rowState(dong(day, { busy: true }))[0] === "Đang đọc…", "dang doc tep");
  la(A.rowState(dong(day, { err: "hong" }))[0] === "Lỗi", "loi thang tay, khong giau");
  la(A.rowState(dong(day, { name: "EC-PAYR-2026-00042" }))[1] === "ok",
     "Da tao nhap -> wash xanh: ban nhap CO THAT tren server, da xay ra roi");

  // Trần: dòng thứ 11 bị từ chối, và lý do nói theo QUYẾT ĐỊNH.
  A.S.maxDrafts = 10; A.S.fileExts = ["pdf"];
  A.B.rows = [];
  for (let i = 0; i < 10; i++) {
    A.B.rows.push({ key: "k" + i, file: { name: "f" + i + ".pdf", size: 5 }, fields: {} });
  }
  la(/10/.test(A.batchRefuse({ name: "f99.pdf", size: 5 }) || ""),
     "day 10 dong -> tu choi tep thu 11 va noi ro con so");
  A.B.rows = A.B.rows.slice(0, 2);
  la(A.batchRefuse({ name: "f1.pdf", size: 5 }) === "đã có rồi",
     "cung ten cung kich thuoc -> da co roi");

  A.B.rows = [dong(day)];
  la(A.flagsHtml(A.B.rows[0]) === "", "khong co co -> khong ve gi");
  A.B.rows[0].flags = { dup_in_batch: true, new_account: false, amount_off: true };
  const co = A.flagsHtml(A.B.rows[0]);
  la(/Trùng STK/.test(co) && /lệch xa/.test(co), "ve dung hai co dang bat");
  la(!/Số tài khoản mới/.test(co), "co dang TAT thi khong ve");

  A.B.busy = false; A.B.mo = null;
  const h1 = A.batchHtml();
  // 23/09 — màn này KHÔNG gửi nữa. Chỉ tạo bản nháp; người dùng tự mở phiếu và bấm Gửi.
  la(/Tạo 1 bản nháp/.test(h1), "nut ghi ro so BAN NHAP se tao");
  la(!/Gửi \d+ phiếu/.test(h1), "KHONG con nut gui ca lo");
  la(!/ec-aifill-cam/.test(h1),
     "KHONG con o cam ket: no la chu ky cho viec GUI, ma man nay khong gui");
  A.B.rows.push(dong(day, { key: "r2" }));
  la(/Tạo 2 bản nháp/.test(A.batchHtml()), "con so doi theo lo, khong phai chu chet");

  // A61 §1: màn này chỉ TẠO. Gom để quyết định là thứ khác hẳn.
  const moiHtml = A.batchHtml() + h1;
  la(!/duyệt tất cả|Duyệt tất cả|duyet tat ca/.test(moiHtml),
     "KHONG co nut duyet-tat-ca o bat ky dau (A61 §1)");

  // Dòng đã tạo nháp: hiện MÃ PHIẾU + đúng những ô còn thiếu.
  A.B.rows = [dong(day, { key: "r9", name: "EC-PAYR-2026-00232",
                          missing: [{ fieldname: "ec_brand", label: "Brand liên quan" },
                                    { fieldname: "is_cost_valid", label: "Chi phí hợp lệ?" }] })];
  const hRow = A.batchHtml();
  la(/EC-PAYR-2026-00232/.test(hRow), "hien ma phieu vua tao");
  la(/còn thiếu: Brand liên quan, Chi phí hợp lệ\?/.test(hRow),
     "noi RO o nao con thieu, dung nhan cua form");
  la(A.rowState(A.B.rows[0])[0] === "Đã tạo nháp", "trang thai dong = Da tao nhap");
  la(/chưa gửi cái nào/.test(hRow), "noi thang la he thong CHUA gui gi");

  // Câu lỗi thật của server, không phải "gửi không thành công".
  const e = { _server_messages: JSON.stringify([
    JSON.stringify({ message: "<div>Loại chi phí này gắn với một brand — vui lòng chọn brand.</div>" })]) };
  la(A.loiThat(e, "mac dinh") === "Loại chi phí này gắn với một brand — vui lòng chọn brand.",
     "boc duoc cau tieng Viet that tu _server_messages");
  la(A.loiThat({}, "mac dinh") === "mac dinh", "khong co gi thi moi roi ve cau mac dinh");

  // Trần nói ra HỆ QUẢ, không chỉ nói "hết chỗ".
  A.B.rows = [];
  for (let i = 0; i < 10; i++) {
    A.B.rows.push(dong(day, { key: "z" + i, file: { name: "z" + i + ".pdf", size: 5 } }));
  }
  la(/quyết định/.test(A.batchHtml()),
     "tran giai thich HE QUA - tran khong giai thich thi nguoi ta di tim cach lach");
}

// ---- 11. A58 trên bảng trạng thái dòng ---------------------------------------
{
  const css = readFileSync(
    join(here, "..", "..", "..", "public", "css", "ec_aifill.bundle.css"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "");
  const lay = (bo) => {
    for (const khoi of css.split("}")) {
      const chon = (khoi.split("{")[0] || "").trim();
      if (chon.split(",").some((x) => x.trim() === bo)) return khoi.split("{")[1] || "";
    }
    return "";
  };
  la(/#f3f4f6|--ec-af-line-soft/.test(lay(".ec-aifill-chip")), "San sang: nen xam");
  la(/#fff8e1/.test(lay(".ec-aifill-chip.is-warn")), "Thieu N o: nen amber");
  la(/#f0fdf4/.test(lay(".ec-aifill-chip.is-ok")),
     "Da tao nhap: nen xanh - ban nhap CO THAT tren server la mot trang thai da xay ra");
  for (const bo of [".ec-aifill-chip", ".ec-aifill-chip.is-warn", ".ec-aifill-chip.is-wait"]) {
    la(!/#f0fdf4|#166534|#bbf7d0/.test(lay(bo)),
       `${bo}: ban nhap KHONG duoc muon mau cua trang thai da duyet (A58)`);
  }
  la(/tabular-nums/.test(lay(".ec-aifill-row-amt")) && /text-align:\s*right/.test(lay(".ec-aifill-row-amt")),
     "cot tien can phai + tabular-nums de quet doc cot la so duoc");
}

// ---- 12. Mo lai phieu da co: dau tich lay tu SERVER -------------------------
// Bản đồ vàng/đỏ cũ sống trong bộ nhớ trình duyệt của đúng phiên chạy AI. Mở lại hôm sau
// là mất sạch. Hai hàm dưới là chỗ nối sang dấu tích server giữ trên dòng log.
{
  function nap4(search) {
    const tai = { location: { pathname: "/approvals/payment-request", search: search || "" },
      requestAnimationFrame: (f) => f(), MutationObserver: class { observe() {} },
      Event: class { constructor(t) { this.type = t; } } };
    const doc = { readyState: "complete", body: { contains: () => true },
      addEventListener() {}, querySelector: () => null, querySelectorAll: () => [],
      createElement: () => ({ style: {}, classList: { add() {}, toggle() {} },
                              setAttribute() {}, appendChild() {}, querySelector: () => null }) };
    new Function("window", "document", "frappe", readFileSync(SRC, "utf8"))(tai, doc, undefined);
    return tai.__ecAifill;
  }

  la(nap4("?id=EC-PAYR-2026-00232").draftId() === "EC-PAYR-2026-00232",
     "doc duoc ma phieu tren URL");
  la(nap4("?tab=detail&id=EC-PAYR-2026-00232").draftId() === "EC-PAYR-2026-00232",
     "doc duoc ma phieu khi con tham so khac");
  la(nap4("").draftId() === null, "khong co id -> null, khong no");
  la(nap4("?id=").draftId() === null, "id rong -> null");

  const A = nap4("?id=EC-PAYR-2026-00232");
  A.S.marks = { fields: ["payee_full_name", "payment_amount"],
                labels: { payee_full_name: "Người nhận", payment_amount: "Số tiền" } };
  const h = A.detailHtml();
  la(/AI đã điền 2 ô/.test(h), "man chi tiet noi ro SO O may da dien");
  la(/Người nhận/.test(h) && /Số tiền/.test(h), "liet ke dung nhan cua tung o");
  la(/số tiền và số tài khoản/.test(h), "chi thang cho nguoi duyet nen soi ky cho nao");
  // A58: "AI điền" là tình trạng công cụ, không phải trạng thái workflow.
  la(!/ec-aifill-chip is-ok|#f0fdf4/.test(h), "KHONG muon mau trang thai workflow (A58)");

  // Nhãn do server trả về -> phải escape, không nhét thẳng vào HTML.
  A.S.marks = { fields: ["x"], labels: { x: '<img src=x onerror=alert(1)>' } };
  la(!/<img/.test(A.detailHtml()), "nhan tu server duoc escape truoc khi ve");
}

// ---- 13. SU CO 25/09: panel ve mot lan roi nam rong -------------------------
// `render()` ve HAI hinh dang (form nhap / man chi tiet). `mount()` goi no dung mot lan,
// ngay khi `.tabs` xuat hien - truoc khi than form ve xong. Khong ai theo doi dieu kien
// do DOI, nen panel bi ghi rong va nam do vinh vien. Ca 78 nguoi mat panel.
{
  let coFld = false;                         // than form da ve chua
  const ghi = [];
  function nap5() {
    // Panel gia: `render()` co gan handler vao vai nut, nen querySelector phai tra ve
    // mot phan tu gia thay vi null - neu khong test chet vi ly do KHONG lien quan den
    // dieu dang kiem.
    const nut = () => ({ onclick: null, onchange: null, oninput: null, value: "",
                         classList: { add() {}, remove() {}, toggle() {} },
                         addEventListener() {}, querySelector: () => nut(),
                         querySelectorAll: () => [], click() {} });
    const panel = { classList: { toggle() {}, add() {}, remove() {} },
                    querySelector: () => nut(), querySelectorAll: () => [],
                    contains: () => false };
    Object.defineProperty(panel, "innerHTML", {
      get() { return this._h || ""; },
      set(v) { this._h = v; ghi.push(v); },
    });
    const tai = { location: { pathname: "/approvals/payment-request", search: "" },
      requestAnimationFrame: (f) => f(), MutationObserver: class { observe() {} },
      Event: class { constructor(t) { this.type = t; } } };
    const doc = { readyState: "complete",
      body: { contains: () => true },
      addEventListener() {},
      querySelector: (sel) => (sel === "[data-fld]" ? (coFld ? {} : null) : null),
      querySelectorAll: () => [],
      createElement: () => panel };
    new Function("window", "document", "frappe", readFileSync(SRC, "utf8"))(tai, doc, undefined);
    const A = tai.__ecAifill;
    A.S.panel = panel;
    return A;
  }

  const A = nap5();
  // Mount som: chua co o nhap nao -> panel rong. Day la trang thai da xay ra that.
  coFld = false; A.render();
  la(ghi[ghi.length - 1] === "", "mount som khi form chua ve -> panel rong (trang thai cu)");

  // Than form ve xong. `syncMode` PHAI ve lai.
  coFld = true; A.syncMode();
  la(ghi[ghi.length - 1] !== "", "form ve xong -> syncMode ve lai panel, KHONG de rong");
  la(/ec-aifill-run/.test(ghi[ghi.length - 1]), "ve dung khoi dien, co nut Dien vao form");

  // Goi lai khi hinh dang KHONG doi -> khong ve lai (tranh tu dap DOM cua chinh minh).
  const truoc = ghi.length;
  A.syncMode();
  la(ghi.length === truoc, "hinh dang khong doi -> KHONG ghi DOM lai");

  // Quay ve man chi tiet -> lai ve lai.
  coFld = false; A.syncMode();
  la(ghi.length > truoc, "doi sang man chi tiet -> ve lai");
}

console.log(`${dat} dat, ${hong} hong`);
process.exit(hong ? 1 : 0);
