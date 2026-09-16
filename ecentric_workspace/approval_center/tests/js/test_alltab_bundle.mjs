// Copyright (c) 2026, eCentric and contributors
//
// Tab "Tat ca" dung chung (16/09, Hoan): mot bundle phuc vu ca 28 form.
//
// Bo test nay giu bon dieu, moi dieu deu tung la mot loi that o dau do trong he nay:
//   1. Mot dong PHAI mang du thong tin de quyet dinh - do la CA LY DO tab nay ton tai.
//      "Nhin vao khong can bam chi tiet cung du thong tin ra quyet dinh" (Hoan).
//   2. Khong bao gio noi chuoi HTML tu du lieu ma khong thoat. Tieu de phieu do NGUOI DUNG
//      go, va no di thang vao innerHTML.
//   3. Export phai di bang POST. Frappe hoan tac moi ghi trong request GET - tep van tai
//      duoc nhung dong vet bien mat (do duoc 15/09, da tra gia).
//   4. Ket qua ve CHAM cua mot luot loc cu khong duoc ghi de ket qua moi. Go nhanh trong o
//      tim kiem la cach de nhat de thay bang hien sai du lieu ma khong ai bao loi.
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = readFileSync(join(here, "..", "..", "..", "public", "js", "ec_alltab.bundle.js"), "utf8");
const FEAT = join(here, "..", "..", "features");

const w = {};
new Function("window", SRC)(w);
const AT = w.EcAllTab;

let dat = 0;
const hong = [];
const la = (dk, mo) => { if (dk) dat++; else hong.push(mo); };

// ---- 1. mot dong mang du thu de quyet dinh ---------------------------------------------
const v = {
  name: "EC-PAYR-2026-00044", submitted_at: "2026-09-07 11:49:00",
  title: "Thanh toán camera CMC", requester_info: { name: "Đông Diệp Hữu" },
  requester: "dong@e.c", department: "Operation", amount: 17366400, currency: "VND",
  status: "Pending", status_label: "Chờ duyệt", current_level: 3, total_levels: 7,
  current_level_name: "Finance review", sla_breached: true,
  approvers: [{ name: "Vũ Vinh", status: "Pending" }, { name: "Ai Đó", status: "Approved" }],
};
const h = AT._dongHTML(v);
for (const [nhan, can] of [
  ["so tien", "17.366.400"], ["tieu de", "Thanh toán camera CMC"],
  ["nguoi de nghi", "Đông Diệp Hữu"], ["phong ban", "Operation"],
  ["trang thai", "Chờ duyệt"], ["buoc may tren may", "3/7"],
  ["ten buoc", "Finance review"], ["dang cho ai", "Vũ Vinh"],
  ["canh bao qua han", "quá hạn SLA"], ["ma phieu", "00044"],
]) la(h.includes(can), `dong thieu ${nhan} (${can})`);

// Chi nguoi CON DANG CHO moi duoc liet ke. Ke ca nguoi da duyet vao "dang cho ai" la noi
// sai mot su that ma nguoi doc khong co cach nao kiem lai tu man hinh.
la(!h.includes("Ai Đó"), "liet ke ca nguoi DA duyet vao cot 'dang cho ai'");

// Ma phieu day du phai con trong title de ai can doc chinh xac van lay duoc.
la(h.includes('title="EC-PAYR-2026-00044"'), "cat ma phieu ma khong giu ban day du o title");

// ---- 2. thoat HTML --------------------------------------------------------------------
const doc = AT._dongHTML({
  name: "X", title: '<img src=x onerror=alert(1)>', approvers: [],
  requester_info: { name: '"><script>bad()</script>' }, status: "Pending",
});
la(!doc.includes("<img src=x"), "tieu de do nguoi dung go duoc noi THANG vao HTML");
la(!doc.includes("<script>"), "ten nguoi de nghi khong duoc thoat");

// ---- 3. trang thai khong ro rang van phai ve duoc --------------------------------------
const trong = AT._dongHTML({ name: "Y", approvers: [] });
la(trong.includes("<tr"), "dong khong du truong thi vo ca bang");
la(trong.includes("—"), "o rong khong co dau cho biet la rong");
la(AT._tien(null) === "" && AT._tien("") === "", "so tien rong tra ve chuoi rac");
la(AT._tien("khong-phai-so").length > 0, "so tien khong hop le lam vo o");

// ---- 4. export PHAI la POST -----------------------------------------------------------
const iTai = SRC.indexOf("function taiTep");
const than = SRC.slice(iTai, SRC.indexOf("\n  var HEN", iTai));
la(/method:\s*"POST"/.test(than), "export khong dung POST - vet ghi se bi Frappe hoan tac");
la(!/window\.open|location\.href\s*=/.test(than), "export mo URL GET thay vi POST");
la(/X-Frappe-CSRF-Token/.test(than), "POST thieu CSRF token");
la(/res\.ok/.test(than) && /res\.text\(\)/.test(than),
   "khong doc than loi cua server - tran dong la loi SUA DUOC, nguoi dung phai doc duoc no");

// ---- 5. client KHONG duoc gui approval_type -------------------------------------------
// Chi kiem MA, khong kiem chu thich: phep do dau khong phan biet duoc hai thu do se do
// vi mot cau giai thich - roi nguoi ta xoa cau giai thich cho test xanh, dung thu can giu.
const maKhongCT = SRC.replace(/\/\/[^\n]*/g, "");
la(!/["']approval_type["']/.test(maKhongCT),
   "bundle GUI approval_type len server - viec ghim form la cua server, client dung cham vao");
// Danh sach khoa loc phai GIONG NHAU giua man hinh va export. Lech nhau thi tep xuat ra
// khong khop cai nguoi ta dang nhin - va khong ai phat hien cho toi luc doi chieu so lieu.
const khoa = [...maKhongCT.matchAll(/\[\s*"status",\s*"department",\s*"requester",\s*"date_from",\s*"date_to"\s*\]/g)];
la(khoa.length === 2, `danh sach khoa loc xuat hien ${khoa.length} lan, cho doi 2 (bang + export)`);

// ---- 6. chong ket qua cu ghi de ket qua moi --------------------------------------------
{
  const i = SRC.indexOf("  function nap(st) {");
  const j = SRC.indexOf("\n  function taiTep", i);
  const nguon = SRC.slice(i, j);
  const cho = [];
  const fn = new Function("veThan", "ghi", nguon + "\n return nap;")(
    (st) => { if (!st.dangTai && !st.loi) ghiLai(st); }, null);
  function ghiLai(st) { cho.push(st.rows.map((r) => r.name).join(",")); }
  const treo = [];
  const st = {
    el: null, goi: () => new Promise((res) => treo.push(res)),
    f: {}, start: 0, len: 50, rows: [], total: 0, luot: 0,
  };
  fn(st);                       // luot 1 (cu)
  fn(st);                       // luot 2 (moi)
  treo[1]({ rows: [{ name: "MOI" }], total: 1 });
  treo[0]({ rows: [{ name: "CU" }], total: 9 });   // luot cu ve SAU
  await new Promise((r) => setTimeout(r, 0));
  la(st.rows.length === 1 && st.rows[0].name === "MOI",
     `ket qua cu ghi de ket qua moi (dang la ${JSON.stringify(st.rows)})`);
  la(st.total === 1, "tong cua luot cu ghi de tong cua luot moi");
}

// ---- 7. ca 28 form phai noi vao bundle, khong chep UI ----------------------------------
let soForm = 0;
for (const f of readdirSync(FEAT).filter((d) => !d.startsWith("_") && !d.startsWith("."))) {
  let s;
  try { s = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8"); } catch { continue; }
  if (!s.includes("function renderTabs(")) continue;
  soForm++;
  la(/t==="all"\|\|/.test(s), `${f}: tabAllowed khong cho phep tab "all"`);
  la(s.includes('if(tb.all) defs.push(["all","Tất cả",true]);'), `${f}: renderTabs thieu tab "Tất cả"`);
  la(s.includes('if(state.tab==="all") return renderAll(b);'), `${f}: render() thieu nhanh "all"`);
  la(s.includes("window.EcAllTab.render(b,{"), `${f}: khong goi bundle dung chung`);
  // Chep UI vao tung form la dung cach de tao ra dot sua 28 cho lan sau (xem 15/09).
  la(!s.includes("ec-at-tb"), `${f}: co dau vet chep HTML cua bang vao trang - phai nam trong bundle`);
}
la(soForm >= 28, `chi thay ${soForm} form co thanh tab, cho doi >= 28`);

for (const x of hong) console.log("  HONG: " + x);
console.log(`${dat} dat, ${hong.length} hong (${soForm} form)`);
process.exit(hong.length ? 1 : 0);
