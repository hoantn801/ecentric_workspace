// Copyright (c) 2026, eCentric and contributors
//
// 15/09, Hoan bao bon van de tren form Booking Request:
//   1. O Brand khong giong SO/PO  -> vi no la <input list=datalist>, nam NGOAI `ec_formkit`.
//   2. Bang KOL/KOC "khong su dung duoc" -> <select> 7 muc trong o bang bi formkit nang thanh
//      combobox, bang tim bung ra de len hang duoi va bi vien bang cat.
//   3. Khong co cho dinh kem.
//   4. Thieu tien trinh duyet o dau form.
//
// Bo test nay DUNG THAT cac ham dung HTML cua trang (cat ra khoi main_section.html roi chay),
// khong grep nguon: grep chi chung minh co mot doan chu, khong chung minh duoc no ra dung thu.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = readFileSync(
  join(here, "..", "..", "features", "booking_request", "ui", "main_section.html"), "utf8");

function braceSlice(src, marker) {
  const i = src.indexOf(marker);
  if (i < 0) return null;
  let depth = 0; const start = src.indexOf("{", i + marker.length - 1);
  for (let j = start; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}") { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  return null;
}
function fnSrc(name) {
  const body = braceSlice(SRC, "function " + name + "(");
  if (!body) throw new Error("khong cat duoc ham " + name);
  const i = SRC.indexOf("function " + name + "(");
  const args = SRC.slice(i + ("function " + name).length, SRC.indexOf(")", i) + 1);
  return "function " + name + args + body;
}

// --- nen toi thieu de chay cac ham dung HTML --------------------------------------------
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function opt(list, cur) {
  return list.map((o) => {
    const v = o && o.value != null ? o.value : o;
    const l = o && o.label != null ? o.label : v;
    return '<option value="' + esc(v) + '"' + (String(v) === String(cur) ? " selected" : "") + ">" + esc(l) + "</option>";
  }).join("");
}
function fld(key, label, ctrl, req, err, hint) {
  return '<div class="fld' + (err ? " invalid" : "") + '" data-fld="' + key + '"><label>' + esc(label)
    + (req ? ' <span class="req">*</span>' : "") + "</label>" + ctrl
    + (err ? '<div class="err">' + esc(err) + "</div>" : "")
    + (hint ? '<div class="hint">' + hint + "</div>" : "") + "</div>";
}

const BRANDS = [
  { value: "AND-VN", label: "AND-VN — Andros" }, { value: "BBT-VN", label: "BBT-VN — Bong Bach Tuyet" },
  { value: "FCV-VN", label: "FCV-VN — Cafe Viet" }, { value: "FES-VN", label: "FES-VN — Cafepho" },
  { value: "HNW-VN", label: "HNW-VN — Honeywell" }, { value: "LOF-VN", label: "LOF-VN — Lof" },
  { value: "VTD-VN", label: "VTD-VN — Vinh Tien" },
];
let KOL = [];
const ctx = { esc, opt, fld, brandRows: () => BRANDS, kolRows: () => KOL, state: { draft: {} },
              renderStepsHTML: (st) => st.map((s) => '<div class="step ' + s.state + '">' + esc(s.name) + "</div>").join(""),
              previewSteps: () => [{ name: "Đã gửi", state: "done" }, { name: "Account Lead duyệt", state: "upcoming" },
                                   { name: "Booking xử lý", state: "upcoming" }, { name: "Hoàn tất", state: "upcoming" }],
              LEVELS_ALL: ["Account Lead duyệt"], CHI_DINH: "KOL/KOC Chỉ định" };
const code = [fnSrc("brandFieldHTML"), fnSrc("kolTableHTML"), fnSrc("tienVN"), fnSrc("soTien"),
              fnSrc("processPreviewHTML"),
              SRC.slice(SRC.indexOf('var BRAND_MOI'), SRC.indexOf("\n", SRC.indexOf('var BRAND_MOI')))].join("\n");
const make = new Function(...Object.keys(ctx),
  code + "; return {brandFieldHTML,kolTableHTML,processPreviewHTML,BRAND_MOI};");
const F = make(...Object.values(ctx));

const c = {};
// ---- 1. Brand -------------------------------------------------------------------------
const b0 = F.brandFieldHTML({}, {});
const b1_forModel = F.brandFieldHTML({ brand_is_new: 1, brand: "Acme" }, {});
c["Brand la <select> (de ec_formkit nang nhu SO/PO)"] = /<select[^>]*id="f-brand"/.test(b0);
c["Brand giu dung data-model=brand (mot truong = mot khoa)"] = /<select[^>]*data-model="brand"/.test(b0)
  && /id="f-brand-new"[^>]*data-model="brand"/.test(b1_forModel);
c["Brand KHONG con datalist"] = !/datalist/i.test(b0);
c["du 6 muc tro len => formkit se nang"] = (b0.match(/<option/g) || []).length >= 6;
c["co loi ra 'Them brand moi'"] = b0.includes(F.BRAND_MOI) && /Thêm brand mới/.test(b0);
c["chua chon brand moi thi CHUA hien o ten"] = !/id="f-brand-new"/.test(b0);
const b1 = F.brandFieldHTML({ brand_is_new: 1, brand: "Acme" }, {});
c["chon brand moi => hien o nhap ten"] = /id="f-brand-new"/.test(b1) && /value="Acme"/.test(b1);

// ---- 2. Bang KOL ----------------------------------------------------------------------
const k1 = F.kolTableHTML({ expected_budget: "10000000" });
c["bang rong co huong dan, khong bo trong"] = /Chưa có KOL\/KOC nào/.test(k1) && /Thêm dòng/.test(k1);
KOL = [{ kol_name: "A", kol_budget: "4000000" }, { kol_name: "B", kol_budget: "9000000" }];
const k2 = F.kolTableHTML({ expected_budget: "10000000" });
c["o Kenh tu khai KHONG dung formkit"] = /data-k="kol_channel"[^>]*data-ec-no-formkit/.test(k2);
c["cot ngan sach can phai (class num)"] = /<td class="num">/.test(k2);
c["cong tong ngan sach cac dong"] = /13\.000\.000/.test(k2);
c["bao khi vuot ngan sach du kien"] = /kol-sum over/.test(k2) && /vượt ngân sách/.test(k2);
const k3 = F.kolTableHTML({ expected_budget: "99000000" });   // cung 13tr nhung du kien 99tr
c["khong vuot thi KHONG bao do"] = !/kol-sum over/.test(k3);

// ---- 4. Tien trinh --------------------------------------------------------------------
const p = F.processPreviewHTML();
c["tien trinh ve bang stepper dung chung"] = /class="stepper"/.test(p) && /class="step /.test(p);
c["KHONG con danh sach <ol> chu"] = !/<ol/.test(p);

// ---- 3 + thu tu khoi (doc thang tren nguon, day la thu tu noi chuoi) -------------------
c["dinh kem: co o file, KHONG bat buoc"] =
  /id="book-att-input"/.test(SRC) && /fld\("request_attachment","Tệp đính kèm",[\s\S]{0,260}?false,null,/.test(SRC);
c["dinh kem: KHONG dat data-upload (de formkit boc dropzone)"] =
  !/data-upload="request_attachment"/.test(SRC);
c["dinh kem di theo payload"] = /_attachments:\(d\._attachments\|\|\[\]\)/.test(SRC);
c["tien trinh dung TRUOC cac the nhap"] =
  /b\.innerHTML = processPreviewHTML\(\) \+ formCardsHTML/.test(SRC);

let ok = true;
Object.keys(c).forEach((k) => { console.log((c[k] ? "PASS" : "FAIL") + " - " + k); if (!c[k]) ok = false; });
console.log(ok ? "ALL_PASS" : "SOME_FAIL");
process.exit(ok ? 0 : 1);
