// Copyright (c) 2026, eCentric and contributors
//
// Tab "Tat ca" - loc them (16/10/2026, Finance gop y tren Contract Review, PO duyet).
//
// Bo test nay chay bundle THAT trong jsdom (kem ec_money THAT) va giu:
//   1. Thu tu gui len la KHOA (sort), mac dinh thi khong gui gi - server doi chieu danh
//      sach trang; bundle khong bao gio gui ten cot.
//   2. "1.500.000" go vao o so tien -> 1500000 gui len (khong phai 1.5, khong phai chuoi).
//   3. Cot rieng tung form do SERVER khai (get_all_filters.columns) ve ra dung, co thoat HTML.
//   4. "Xoa loc" xoa CA thu tu, so tien, loc rieng - va so dem o tren nut ve 0.
//   5. Export gui DUNG bo loc cua bang (mot ham boLoc).
//   6. 390px: hang "Bo loc them" thu gon mac dinh; o chon khong day hang tran ngang.
//   7. Form khong khai gi -> man hinh y nhu cu (5 cot, khong nut "Bo loc them").
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const PUB = join(here, "..", "..", "..", "public");
const SRC = readFileSync(join(PUB, "js", "ec_alltab.bundle.js"), "utf8");
const MONEY = readFileSync(join(PUB, "js", "ec_money.bundle.js"), "utf8");
const CSS = readFileSync(join(PUB, "css", "ec_alltab.bundle.css"), "utf8");

let dat = 0;
const hong = [];
const la = (dk, mo) => { if (dk) dat++; else hong.push(mo); };
const cho = () => new Promise((r) => setTimeout(r, 0));

const OPTS_CR = {
  statuses: [{ value: "Pending", label: "Chờ duyệt" }], departments: ["Finance"],
  requesters: [{ value: "a@e.c", label: "An" }],
  amount: { field: "contract_value", label: "Giá trị" },
  columns: [
    { label: "Legal entity / Brand", fieldname: "brand", kind: "text" },
    { label: "Loại hợp đồng", fieldname: "contract_type", kind: "select" },
  ],
  extra_filters: [
    { fieldname: "brand", label: "Legal entity / Brand", options: ["ACME", 'Bad"><img src=x onerror=1>'] },
    { fieldname: "contract_type", label: "Loại hợp đồng", options: ["Sales / Bán ra (EC)"] },
  ],
};
const ROW = {
  name: "EC-APR-2026-00001", reference_name: "EC-CTR-2026-00001", title: "HĐ ACME",
  status: "Pending", status_label: "Chờ duyệt", amount: 25000000, approvers: [],
  extra: { brand: "ACME <b>Corp</b>", contract_type: "Sales / Bán ra (EC)" },
};

async function dung(opts, { money = true, listLoi = false } = {}) {
  const dom = new JSDOM('<!doctype html><html><head></head><body><div id="b"></div></body></html>',
    { runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  const st = w.document.createElement("style");
  st.textContent = CSS;
  w.document.head.appendChild(st);
  if (money) w.eval(MONEY);
  w.eval(SRC);
  const goi = [];
  const call = (m, a) => {
    goi.push({ m, a });
    if (m === "get_all_filters") return Promise.resolve(opts);
    if (listLoi) return Promise.reject(new Error("Máy chủ lỗi"));
    return Promise.resolve({ rows: [ROW], total: 1, total_amount: 25000000 });
  };
  const fetches = [];
  w.fetch = (url, o) => { fetches.push({ url, o }); return new Promise(() => {}); };
  w.EcAllTab.render(w.document.getElementById("b"), { call, ns: "x.api." });
  await cho(); await cho();
  const lastList = () => JSON.parse(goi.filter((g) => g.m === "list_all").at(-1).a.filters);
  return { w, d: w.document, goi, lastList, fetches };
}

function doi(w, el, v) {
  el.value = v;
  el.dispatchEvent(new w.Event("change", { bubbles: true }));
}
function go(w, el, v) {          // go phim: input (EcMoney dinh dang lai) roi change
  el.value = v;
  el.dispatchEvent(new w.Event("input", { bubbles: true }));
  el.dispatchEvent(new w.Event("change", { bubbles: true }));
}

// ---- 7 truoc: form khong khai gi -> y nhu cu --------------------------------------------
{
  const { d, lastList } = await dung({ statuses: [], departments: [], requesters: [] });
  la(d.querySelectorAll(".ec-at-tb thead th").length === 5, "form khong khai van phai 5 cot");
  la(!d.querySelector(".ec-at-mo") && !d.querySelector(".ec-at-more"),
     "form khong co gi de loc them ma van hien nut 'Bộ lọc thêm'");
  const sx = d.querySelector('select[data-f="sort"]');
  la(sx && [...sx.options].map((o) => o.value).join() === "newest,oldest",
     "form khong co so tien thi khong duoc co sap xep theo so tien");
  la(JSON.stringify(lastList()) === "{}", "mac dinh gui bo loc thua: " + JSON.stringify(lastList()));
  la(d.querySelector(".ec-at-c-tien").textContent === "Số tiền", "nhan cot so tien mac dinh doi");
}

// ---- 3. cot rieng + nhan so tien do server khai -----------------------------------------
const H = await dung(OPTS_CR);
{
  const { d } = H;
  const th = [...d.querySelectorAll(".ec-at-tb thead th")].map((x) => x.textContent);
  la(th.length === 7, `cho 7 cot (5 + 2 khai), co ${th.length}`);
  la(th[2] === "Legal entity / Brand" && th[3] === "Loại hợp đồng", "cot them sai vi tri/nhan: " + th);
  la(th[4] === "Giá trị", "cot so tien phai mang nhan 'Giá trị' ma form khai");
  const td = [...d.querySelectorAll(".ec-at-row td")];
  la(td.length === 7, "dong khong du o cho cot them");
  la(td[2].textContent === "ACME <b>Corp</b>" && !td[2].querySelector("b"),
     "gia tri cot them khong duoc thoat HTML");
  la(td[4].textContent.includes("25.000.000"), "so tien hien sai");
  const opt = [...d.querySelectorAll('select[data-x="brand"] option')];
  la(opt.length === 3 && !d.querySelector('select[data-x="brand"] img'), "o loc brand khong thoat HTML");
}

// ---- 6. 390px: hang them thu gon mac dinh ----------------------------------------------
{
  const { w, d } = H;
  const hang = d.querySelector(".ec-at-more");
  const nut = d.querySelector(".ec-at-mo");
  la(hang && hang.hasAttribute("hidden"), "hang 'Bộ lọc thêm' phai thu gon NGAY trong markup");
  la(w.getComputedStyle(hang).display === "none", "CSS display:flex de mat thuoc tinh hidden");
  la(nut.getAttribute("aria-expanded") === "false" && nut.getAttribute("aria-controls") === hang.id,
     "nut mo hang thieu aria");
  nut.click();
  la(!hang.hasAttribute("hidden") && w.getComputedStyle(hang).display === "flex", "bam nut khong mo hang");
  la(nut.getAttribute("aria-expanded") === "true", "aria-expanded khong doi");
  la(/\.ec-at-more \.ec-at-f\{[^}]*max-width:100%/.test(CSS),
     "o chon trong hang them khong bi chan max-width:100% - gia tri dai se day tran 390px");
  const mq = CSS.slice(CSS.indexOf("@media (max-width:720px)"));
  la(/\.ec-at-khoang\{ flex-basis:100%; \}/.test(mq), "390px: khoang so tien khong xuong dong rieng");
  la(/\.ec-at-wrap\{[^}]*overflow:auto/.test(CSS), "bang rong khong cuon ngang trong khung");
}

// ---- 1. sap xep gui KHOA ---------------------------------------------------------------
{
  const { w, d, lastList } = H;
  const sx = d.querySelector('select[data-f="sort"]');
  la([...sx.options].map((o) => o.value).join() === "newest,oldest,amount_desc,amount_asc",
     "form co so tien phai co sap xep theo so tien");
  la(sx.options[2].textContent.startsWith("Giá trị"), "nhan sap xep phai theo nhan so tien cua form");
  doi(w, sx, "oldest");
  la(lastList().sort === "oldest", "doi thu tu khong gui sort len server");
  doi(w, sx, "newest");
  la(!("sort" in lastList()), "mac dinh van gui sort thua");
  doi(w, sx, "amount_desc");
  la(lastList().sort === "amount_desc", "sap xep so tien khong gui");
}

// ---- 2. so tien "1.500.000" -> 1500000 --------------------------------------------------
{
  const { w, d, lastList } = H;
  const lo = d.querySelector('input[data-f="amount_min"]');
  const hi = d.querySelector('input[data-f="amount_max"]');
  la(lo.hasAttribute("data-money") && hi.getAttribute("inputmode") === "numeric",
     "o so tien phai dung asset dung chung (data-money, inputmode numeric)");
  go(w, lo, "1.500.000");
  la(lastList().amount_min === 1500000, "1.500.000 phai thanh 1500000, dang la " + lastList().amount_min);
  go(w, hi, "20000000");
  la(hi.value === "20.000.000", "o so tien khong dinh dang dau cham khi go: " + hi.value);
  la(lastList().amount_max === 20000000, "amount_max sai");
  // Khong co EcMoney (trang khong nap asset) van phai doc dung.
  const gia = { value: "1.500.000", hasAttribute: () => true };
  const cu = w.EcMoney; w.EcMoney = undefined;
  la(w.EcAllTab._docTien(gia) === 1500000, "khong co EcMoney: 1.500.000 doc sai");
  la(w.EcAllTab._docTien({ value: "", hasAttribute: () => true }) === null, "o trong phai la null");
  w.EcMoney = cu;
}

// ---- loc rieng + so dem --------------------------------------------------------------
{
  const { w, d, lastList } = H;
  doi(w, d.querySelector('select[data-x="brand"]'), "ACME");
  la(JSON.stringify(lastList().extra) === '{"brand":"ACME"}', "loc brand khong gui: " + JSON.stringify(lastList()));
  const so = d.querySelector(".ec-at-so");
  la(so && !so.hasAttribute("hidden") && so.textContent === "2", "so dem hang them phai la 2 (so tien + brand)");
  doi(w, d.querySelector('select[data-f="status"]'), "Pending");
  la(d.querySelector(".ec-at-reset").textContent === "Xoá lọc (3)",
     "nut xoa loc phai dem 3 o dang bat: " + d.querySelector(".ec-at-reset").textContent);
}

// ---- 5. export cung bo loc -------------------------------------------------------------
{
  const { w, d, lastList, fetches } = H;
  d.querySelector('.ec-at-x[data-fmt="xlsx"]').click();
  la(fetches.length === 1, "bam Excel khong goi export");
  const body = JSON.parse(fetches[0].o.body);
  la(body.filters === JSON.stringify(lastList()), "export gui bo loc KHAC bang: " + body.filters);
  la(JSON.parse(body.filters).sort === "amount_desc", "export mat thu tu");
}

// ---- 4. Xoa loc xoa het --------------------------------------------------------------
{
  const { d, lastList } = H;
  d.querySelector(".ec-at-reset").click();
  await cho();
  la(JSON.stringify(lastList()) === "{}", "Xoá lọc con sot: " + JSON.stringify(lastList()));
  la(d.querySelector('select[data-f="sort"]').value === "newest", "Xoá lọc khong tra thu tu ve mac dinh");
  la(d.querySelector('input[data-f="amount_min"]').value === "", "Xoá lọc khong xoa o so tien");
  la(d.querySelector('select[data-x="brand"]').value === "", "Xoá lọc khong xoa loc brand");
  la(d.querySelector(".ec-at-so").hasAttribute("hidden"), "so dem van hien sau Xoá lọc");
  la(d.querySelector(".ec-at-reset").textContent === "Xoá lọc", "nut xoa loc van dem");
  la(!d.querySelector(".ec-at-more").hasAttribute("hidden"), "Xoá lọc tu dong dong hang nguoi dung dang mo");
}

// ---- loi tai: colspan theo so cot that -------------------------------------------------
{
  const { d } = await dung(OPTS_CR, { listLoi: true });
  await cho();
  const o = d.querySelector(".ec-at-trong");
  la(o && o.textContent === "Máy chủ lỗi" && o.getAttribute("colspan") === "7",
     "trang thai loi phai trai du 7 cot va noi nguyen van loi");
}

for (const x of hong) console.log("  HONG: " + x);
console.log(`${dat} dat, ${hong.length} hong`);
process.exit(hong.length ? 1 : 0);
