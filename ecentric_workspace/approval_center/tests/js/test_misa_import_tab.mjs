// Copyright (c) 2026, eCentric and contributors
// Nhap ma MISA hang loat (PO 24/11/2026), tab "Creator (mã MISA)" tren /approvals/contract-review:
//   * Xuat CSV co cot khoa ma_erp DAU TIEN va cot ma_misa TRONG cuoi (lam mau de dien);
//   * Nhap file: chon tep -> gui base64 len kol_misa_preview (JS KHONG tu parse/kiem) -> bang xem truoc
//     voi tong theo trang thai; nut "Xac nhan N dong hop le" chi gui cac dong Khop (cap name/code);
//   * dang luu: nut khoa, bam lan hai KHONG goi lai; loi server -> bao loi + mo lai nut;
//   * xong: bao so da luu + dong loi kem ly do, lam moi danh sach; tep sai duoi -> khong goi server.
//     node ecentric_workspace/approval_center/tests/js/test_misa_import_tab.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const HTML = readFileSync(join(here, "..", "..", "features", "contract_review", "ui", "main_section.html"), "utf8");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async (n = 20) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 5)); };
const LABELS = { khop: "Khớp", ma_trong: "Mã trống", sai_dinh_dang: "Mã sai định dạng", trung_creator_khac: "Mã đã gán cho creator khác",
  da_luu: "Đã lưu", loi: "Lỗi khi lưu" };
const PREVIEW = { filename: "ma.csv", total: 4, valid: 2, counts: { khop: 2, ma_trong: 1, trung_creator_khac: 1 }, labels: LABELS,
  rows: [{ line: 2, name: "SUP-2", supplier_name: "Trần <b>B", code: "KH0002", status: "khop", label: "Khớp", message: "" },
         { line: 3, name: "SUP-3", supplier_name: "Lê C", code: "", status: "ma_trong", label: "Mã trống", message: "Mã khách hàng MISA không được để trống." },
         { line: 4, name: "SUP-4", supplier_name: "D", code: "KH0001", status: "trung_creator_khac", label: "Mã đã gán cho creator khác", message: "Mã KH0001 đã gán cho creator SUP-1." },
         { line: 5, name: "Phạm Thị Dung", supplier_name: "Phạm Thị Dung", code: "KH0005", status: "khop", label: "Khớp", message: "" }] };

function make(opts) {
  const dom = new JSDOM(HTML, { runScripts: "dangerously", pretendToBeVisual: true, url: "https://x/approvals/contract-review?tab=creators" });
  const w = dom.window;
  w.__calls = []; w.__blobs = [];
  w.URL.createObjectURL = (b) => { w.__blobs.push(b); return "blob:x"; };
  w.HTMLAnchorElement.prototype.click = function () {};
  w.frappe = { call: (o) => {
    const m = o.method.split(".").pop(); w.__calls.push([m, o.args || {}, o.type]);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: {}, context: { user: "kt@x" }, form_options: {} } });
    if (m === "kol_me") return Promise.resolve({ message: { is_finance: true } });
    if (m === "kol_pending_checks") return Promise.resolve({ message: { rows: [] } });
    if (m === "kol_missing_misa") return Promise.resolve({ message: { rows: [{ name: "SUP-2", supplier_name: "Trần B", ec_cr_type: "Cá nhân", tax_id: "=1+1", owner: "a@x", creation: "2026-11-20" }] } });
    if (m === "kol_misa_preview") return opts.previewFail ? Promise.reject({ message: "Tệp thiếu cột ma_misa." }) : Promise.resolve({ message: PREVIEW });
    if (m === "kol_misa_apply") {
      if (opts.applyFail) return Promise.reject({ message: "Chỉ Kế toán (EC Finance) được làm việc này." });
      return new Promise((res) => setTimeout(() => res({ message: { total: 2, saved: 1, skipped: 0, errors: 1, counts: { da_luu: 1, loi: 1 }, labels: LABELS,
        rows: [{ line: 2, name: "SUP-2", code: "KH0002", status: "da_luu", label: "Đã lưu", message: "" },
               { line: 5, name: "Phạm Thị Dung", code: "KH0005", status: "loi", label: "Lỗi khi lưu", message: "Supplier bị khoá" }] } }), 40));
    }
    return Promise.resolve({ message: {} });
  } };
  return w;
}
async function ready(w) { for (let i = 0; i < 100 && !w.document.getElementById("kol-imp"); i++) await flush(1); await flush(); }
function pick(w, name, text) {
  const inp = w.document.getElementById("kol-imp-file");
  const f = new w.File([text], name, { type: "text/csv" });
  Object.defineProperty(inp, "files", { value: [f], configurable: true });
  inp.dispatchEvent(new w.Event("change"));
}
const n = (w, m) => w.__calls.filter((c) => c[0] === m).length;

// 1) Xuat CSV: ma_erp dau, ma_misa trong cuoi, van chong cong thuc
{ const w = make({}); await ready(w);
  w.document.getElementById("kol-csv").click();
  const csv = await new Promise((res) => { const fr = new w.FileReader(); fr.onload = () => res(fr.result); fr.readAsText(w.__blobs[0]); });
  const lines = csv.replace(/^﻿/, "").trim().split("\n");
  ok(lines[0] === "ma_erp,ten,loai,mst,cccd,sdt,email,dia_chi,ma_misa", "csv: tieu de co ma_misa cuoi, ma_erp dau");
  const cells = lines[1].split('","');
  ok(/^"SUP-2"/.test(lines[1]) && cells.length === 9 && cells[8] === '"', "csv: dong co ma_erp dau + du 9 o, o ma_misa cuoi trong");
  ok(/"'=1\+1"/.test(lines[1]), "csv: van chong cong thuc");
  ok(w.document.getElementById("kol-imp") && w.document.getElementById("kol-imp-file").getAttribute("accept").includes(".xlsx"), "co nut Nhap file nhan .csv/.xlsx"); }

// 2) Chon tep -> xem truoc tu server, xac nhan chi gui dong Khop, chong bam 2 lan, ket qua + lam moi
{ const w = make({}); await ready(w);
  const loadsBefore = n(w, "kol_missing_misa");
  pick(w, "ma.csv", "ma_erp,ma_misa\nSUP-2,KH0002\n"); await flush();
  const pc = w.__calls.find((c) => c[0] === "kol_misa_preview");
  ok(pc && pc[1].filename === "ma.csv" && /^data:.*;base64,/.test(pc[1].content) && pc[2] === "POST", "xem truoc: gui tep base64 qua POST");
  ok(pc && Buffer.from(pc[1].content.split(",")[1], "base64").toString() === "ma_erp,ma_misa\nSUP-2,KH0002\n", "xem truoc: noi dung tep nguyen ven");
  const box = w.document.getElementById("kol-imp-box");
  ok(/Khớp: 2/.test(box.textContent) && /Mã trống: 1/.test(box.textContent) && /Mã đã gán cho creator khác: 1/.test(box.textContent), "xem truoc: dem tong theo trang thai");
  ok(/Trần &lt;b&gt;B/.test(box.innerHTML) && !/<b>B/.test(box.innerHTML), "xem truoc: escape ten creator");
  ok(/Mã KH0001 đã gán cho creator SUP-1/.test(box.textContent), "xem truoc: ly do tung dong");
  const okBtn = box.querySelector('[data-imp="ok"]');
  ok(okBtn && /Xác nhận 2 dòng hợp lệ/.test(okBtn.textContent) && !okBtn.disabled, "nut Xac nhan 2 dong hop le");
  ok(n(w, "kol_misa_apply") === 0, "chua xac nhan thi chua ghi");
  okBtn.click(); okBtn.click(); await flush(2);
  ok(okBtn.disabled && /Đang lưu 2 dòng/.test(okBtn.textContent), "dang luu: nut khoa + chu dang luu");
  box.querySelector('[data-imp="ok"]').click();
  await flush(30);
  ok(n(w, "kol_misa_apply") === 1, "bam nhieu lan chi goi kol_misa_apply 1 lan");
  const ac = w.__calls.find((c) => c[0] === "kol_misa_apply");
  const sent = JSON.parse(ac[1].rows);
  ok(JSON.stringify(sent) === JSON.stringify([{ line: 2, name: "SUP-2", code: "KH0002" }, { line: 5, name: "Phạm Thị Dung", code: "KH0005" }]),
     "xac nhan: chi gui dong Khop, chi cap line/name/code (khong gui trang thai)");
  ok(ac[1].filename === "ma.csv" && ac[2] === "POST", "xac nhan: POST kem ten tep");
  ok(/Đã lưu 1 mã MISA/.test(box.textContent) && /Supplier bị khoá/.test(box.textContent) && /1 dòng không lưu được/.test(box.textContent), "ket qua: so da luu + dong loi va ly do");
  ok(n(w, "kol_missing_misa") > loadsBefore, "xong thi lam moi danh sach chua co ma");
  ok(/err/.test(w.document.getElementById("ctr-toast").className), "co dong loi -> toast do");
  box.querySelector('[data-imp="cancel"]').click();
  ok(box.innerHTML === "", "Dong: an khung ket qua"); }

// 3) Loi server khi xac nhan -> bao loi, mo lai nut, bam lai duoc
{ const w = make({ applyFail: true }); await ready(w);
  pick(w, "ma.xlsx", "PK"); await flush();
  const box = w.document.getElementById("kol-imp-box");
  box.querySelector('[data-imp="ok"]').click(); await flush();
  const b = box.querySelector('[data-imp="ok"]');
  ok(b && !b.disabled && /Xác nhận 2 dòng/.test(b.textContent), "loi luu: nut mo lai");
  ok(/Chỉ Kế toán/.test(w.document.getElementById("ctr-toast").textContent), "loi luu: bao loi server");
  b.click(); await flush();
  ok(n(w, "kol_misa_apply") === 2, "loi luu: bam lai duoc"); }

// 4) Loi xem truoc + tep sai duoi
{ const w = make({ previewFail: true }); await ready(w);
  pick(w, "ma.csv", "x"); await flush();
  const box = w.document.getElementById("kol-imp-box");
  ok(/Tệp thiếu cột ma_misa/.test(box.textContent) && !box.querySelector('[data-imp="ok"]'), "loi xem truoc: bao ro, khong co nut xac nhan");
  ok(!w.document.getElementById("kol-imp").disabled && w.document.getElementById("kol-imp").textContent === "Nhập file", "loi xem truoc: nut Nhap file mo lai");
  const before = n(w, "kol_misa_preview");
  pick(w, "ma.pdf", "x"); await flush();
  ok(n(w, "kol_misa_preview") === before && /\.csv hoặc \.xlsx/.test(w.document.getElementById("ctr-toast").textContent), "tep sai duoi: khong goi server, bao loi"); }

// 5) Khong co dong hop le -> nut Xac nhan khoa
{ const w = make({}); await ready(w);
  const K = w.ContractReviewKOL;
  const h = K.impPreviewHTML({ filename: "a.csv", total: 1, valid: 0, counts: { ma_trong: 1 }, labels: LABELS, rows: [PREVIEW.rows[1]] });
  ok(/data-imp="ok" disabled/.test(h) && /Xác nhận 0 dòng/.test(h), "0 dong hop le: nut xac nhan khoa"); }

console.log(oks + " dat, " + fails + " hong");
process.exit(fails ? 1 : 0);
