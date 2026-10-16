// Copyright (c) 2026, eCentric and contributors
//
// Tab "Tat ca" - sap xep + loc NGAY TREN HEADER COT (16/10/2026, PO Hoan duyet mockup).
//
// Bo test nay chay bundle THAT trong jsdom (kem ec_money THAT) va giu:
//   1. Bam nhan cot -> gui sort {col, dir}; bam lai -> dao chieu; cot chu A->Z truoc, cot
//      tien/ngay cao->thap truoc. Mac dinh (ngay gui moi -> cu) thi KHONG gui sort.
//   2. Pheu mo o noi neo duoi header; o noi DONG trong markup ban dau; Esc / bam ra ngoai
//      dong ma KHONG ap dung; "Bỏ lọc" xoa loc cot; "Áp dụng" gui DANH SACH gia tri.
//   3. "1.500.000" go vao o so tien -> 1500000 gui len (khong phai 1.5, khong phai chuoi).
//   4. Chip tom tat dung trang thai; "Xoá lọc" tra ve mac dinh (ca thu tu).
//   5. Export gui DUNG bo loc + thu tu cua bang (mot ham boLoc).
//   6. <= 640px: o noi thanh tam day (class, jsdom khong co layout).
//   7. Moi gia tri tu server / nguoi dung deu duoc thoat HTML.
//   8. Form khong khai gi -> 5 cot nhu cu, khong cot nao sap xep sai.
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

const XAU = 'Bad"><img src=x onerror=1>';
const OPTS_CR = {
  statuses: [{ value: "Pending", label: "Chờ duyệt" }, { value: "Completed", label: "Hoàn tất" },
             { value: "Rejected", label: "Từ chối" }],
  departments: ["Finance", "Ops", XAU],
  requesters: [{ value: "a@e.c", label: "An" }, { value: "b@e.c", label: "Bình" }],
  amount: { field: "contract_value", label: "Giá trị" },
  columns: [
    { label: "Legal entity / Brand", fieldname: "brand", kind: "text", sort: "x:brand", filter: true },
    { label: "Loại hợp đồng", fieldname: "contract_type", kind: "select", sort: "x:contract_type", filter: true },
  ],
  extra_filters: [
    { fieldname: "brand", label: "Legal entity / Brand", options: ["ACME", XAU] },
    { fieldname: "contract_type", label: "Loại HĐ", options: ["Dịch vụ", "Mua bán", "Thuê"] },
  ],
  sort_cols: ["submitted", "status", "title", "amount", "x:brand", "x:contract_type"],
};
const ROW = {
  name: "EC-APR-2026-00001", reference_name: "EC-CTR-2026-00001", title: "HĐ ACME",
  status: "Pending", status_label: "Chờ duyệt", amount: 25000000, approvers: [],
  extra: { brand: "ACME <b>Corp</b>", contract_type: "Mua bán" },
};

async function dung(opts, { money = true, listLoi = false, rong = 1024 } = {}) {
  const dom = new JSDOM('<!doctype html><html><head></head><body><div id="b"></div><p id="ngoai">x</p></body></html>',
    { runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  Object.defineProperty(w, "innerWidth", { value: rong, configurable: true });
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
  const lists = () => goi.filter((g) => g.m === "list_all");
  const lastList = () => JSON.parse(lists().at(-1).a.filters);
  const d = w.document;
  const th = (k) => d.querySelector(`.ec-at-tb thead th[data-col="${k}"]`);
  const sx = (k) => th(k) && th(k).querySelector(".ec-at-sx");
  const pheu = (k) => th(k) && th(k).querySelector(".ec-at-pheu");
  const pop = () => d.querySelector(".ec-at-pop");
  const chips = () => [...d.querySelectorAll(".ec-at-chip-t")].map((x) => x.textContent);
  return { w, d, goi, lists, lastList, fetches, th, sx, pheu, pop, chips };
}

function go(w, el, v) {          // go phim: input (EcMoney dinh dang lai)
  el.value = v;
  el.dispatchEvent(new w.Event("input", { bubbles: true }));
}
function tick(pop, nhom, giaTri) {
  for (const i of pop.querySelectorAll(`.ec-at-nhom[data-nhom="${nhom}"] input[type=checkbox]`)) {
    i.checked = giaTri.includes(i.value);
  }
}
const phim = (w, el, key) => el.dispatchEvent(new w.KeyboardEvent("keydown", { key, bubbles: true }));

// ---- 8. form khong khai gi -> y nhu cu ----------------------------------------------------
{
  const { d, lastList, th, sx, pheu } = await dung({ statuses: [], departments: [], requesters: [] });
  la(d.querySelectorAll(".ec-at-tb thead th").length === 5, "form khong khai van phai 5 cot");
  la(JSON.stringify(lastList()) === "{}", "mac dinh gui bo loc thua: " + JSON.stringify(lastList()));
  la(th("amount").textContent === "Số tiền", "nhan cot so tien mac dinh doi");
  la(!sx("amount") && !pheu("amount"), "form khong co so tien thi cot tien khong duoc sap/loc");
  la(sx("submitted") && sx("status"), "ngay gui + trang thai luon sap duoc");
  la(!sx("title"), "server khong noi 'title' sap duoc thi khong duoc cho bam");
  la(!pheu("cho") && !sx("cho"), "'Đang chờ ai' khong sap, khong pheu");
  la(!d.querySelector(".ec-at-bar select") && !d.querySelector(".ec-at-more") && !d.querySelector(".ec-at-mo"),
     "thanh tren con o chon / hang 'Bộ lọc thêm' cu");
}

const H = await dung(OPTS_CR);
// ---- markup ban dau: o noi dong, chip an, mac dinh ngay gui moi -> cu -------------------
{
  const { w, d, th, pop } = H;
  const p = pop();
  la(p && p.hasAttribute("hidden") && w.getComputedStyle(p).display === "none",
     "o noi phai DONG ngay trong markup (hidden + CSS khong de mat)");
  la(d.querySelector(".ec-at-nen").hasAttribute("hidden"), "nen toi cua tam day phai an san");
  la(d.querySelector(".ec-at-chips").hasAttribute("hidden"), "khong co loc thi hang chip phai an");
  la(th("submitted").classList.contains("ec-at-on") && th("submitted").getAttribute("aria-sort") === "descending",
     "mac dinh phai danh dau cot ngay gui moi -> cu");
  la(th("submitted").querySelector(".ec-at-mui").textContent === "▼", "mui ten mac dinh");
  la(th("x:brand").getAttribute("aria-sort") === "none", "cot khac phai aria-sort=none");
  const nhan = [...d.querySelectorAll(".ec-at-tb thead th .ec-at-hl")].map((x) => x.textContent);
  la(nhan.join("|") === "Mã · ngày gửi|Tiêu đề · người đề nghị|Legal entity / Brand|Loại hợp đồng|Giá trị|Trạng thái · bước|Đang chờ ai",
     "nhan / thu tu cot sai: " + nhan.join("|"));
  const td = [...d.querySelectorAll(".ec-at-row td")];
  la(td.length === 7, "dong khong du o cho cot them");
  la(td[2].textContent === "ACME <b>Corp</b>" && !td[2].querySelector("b"), "gia tri cot them khong duoc thoat HTML");
  la(td[4].textContent.includes("25.000.000"), "so tien hien sai");
  la(!d.querySelector(".ec-at-bar select, .ec-at-bar input[type=date]"), "thanh tren chi con tim kiem + nut");
}

// ---- 1. bam header sap xep --------------------------------------------------------------
{
  const { lastList, sx, th, lists } = H;
  const n0 = lists().length;
  sx("x:brand").click();
  la(JSON.stringify(lastList().sort) === '{"col":"x:brand","dir":"asc"}', "cot chu bam lan dau phai A->Z: " + JSON.stringify(lastList().sort));
  la(lists().length === n0 + 1, "bam header phai tai lai dung mot lan");
  la(th("x:brand").classList.contains("ec-at-on") && !th("submitted").classList.contains("ec-at-on"),
     "cot dang sap phai doi mau, cot cu thoi");
  la(th("x:brand").querySelector(".ec-at-mui").textContent === "▲", "mui ten A->Z phai la ▲");
  sx("x:brand").click();
  la(JSON.stringify(lastList().sort) === '{"col":"x:brand","dir":"desc"}', "bam lan hai phai dao chieu");
  la(th("x:brand").getAttribute("aria-sort") === "descending", "aria-sort khong doi");
  sx("amount").click();
  la(JSON.stringify(lastList().sort) === '{"col":"amount","dir":"desc"}', "cot tien bam lan dau phai cao->thap");
  sx("title").click();
  la(JSON.stringify(lastList().sort) === '{"col":"title","dir":"asc"}', "cot tieu de A->Z");
  sx("status").click();
  la(JSON.stringify(lastList().sort) === '{"col":"status","dir":"asc"}', "cot trang thai");
  sx("submitted").click();
  la(!("sort" in lastList()) && H.th("submitted").getAttribute("aria-sort") === "descending",
     "cot ngay bam lan dau phai moi->cu (= mac dinh, khong gui sort): " + JSON.stringify(lastList()));
  sx("submitted").click();
  la(JSON.stringify(lastList().sort) === '{"col":"submitted","dir":"asc"}', "bam lai cot ngay phai cu->moi");
  sx("submitted").click();
  la(!("sort" in lastList()), "quay ve mac dinh (moi -> cu) van gui sort thua: " + JSON.stringify(lastList()));
}

// ---- 2. pheu + o noi -------------------------------------------------------------------
{
  const { w, d, pheu, pop, lastList, lists, chips } = H;
  pheu("x:contract_type").click();
  const p = pop();
  la(!p.hasAttribute("hidden"), "bam pheu khong mo o noi");
  la(pheu("x:contract_type").getAttribute("aria-expanded") === "true", "pheu thieu aria-expanded");
  la(!p.classList.contains("ec-at-sheet"), "1024px khong duoc la tam day");
  const hg = [...p.querySelectorAll(".ec-at-hg")].map((b) => b.textContent);
  la(hg.join("|") === "A → Z|Z → A", "nut chieu cot chu sai: " + hg);
  la(p.querySelectorAll('.ec-at-nhom[data-nhom="x:contract_type"] input[type=checkbox]').length === 3, "thieu o tick gia tri");
  la(!p.querySelector(".ec-at-tim"), "danh sach <= 8 khong can o tim");
  // Esc dong, khong ap dung
  const n0 = lists().length;
  tick(p, "x:contract_type", ["Dịch vụ"]);
  phim(w, d, "Escape");
  la(p.hasAttribute("hidden") && lists().length === n0, "Esc phai dong ma KHONG ap dung");
  la(d.activeElement === pheu("x:contract_type"), "Esc phai tra focus ve pheu");
  // Bam ra ngoai dong, khong ap dung
  pheu("x:contract_type").click();
  tick(pop(), "x:contract_type", ["Dịch vụ"]);
  d.getElementById("ngoai").dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true }));
  la(pop().hasAttribute("hidden") && lists().length === n0, "bam ra ngoai phai dong ma KHONG ap dung");
  // Tick nhieu + Ap dung
  pheu("x:contract_type").click();
  la(![...pop().querySelectorAll("input[type=checkbox]")].some((i) => i.checked), "dau tick chua ap dung con sot lai");
  tick(pop(), "x:contract_type", ["Dịch vụ", "Mua bán"]);
  pop().querySelector(".ec-at-ap").click();
  la(JSON.stringify(lastList().extra) === '{"contract_type":["Dịch vụ","Mua bán"]}', "ap dung khong gui danh sach: " + JSON.stringify(lastList()));
  la(pop().hasAttribute("hidden"), "ap dung xong phai dong o noi");
  la(pheu("x:contract_type").classList.contains("ec-at-co"), "pheu cot dang loc phai doi mau");
  la(!pheu("x:brand").classList.contains("ec-at-co"), "pheu cot khong loc khong duoc doi mau");
  la(chips().includes("Loại HĐ: Dịch vụ, Mua bán"), "chip loc sai: " + chips());
  la(d.querySelector(".ec-at-reset").textContent === "Xoá lọc (1)", "dem loc sai");
  // Mo lai: tick con giu; Bo loc xoa
  pheu("x:contract_type").click();
  la([...pop().querySelectorAll("input:checked")].map((i) => i.value).join() === "Dịch vụ,Mua bán", "mo lai khong giu dau tick");
  pop().querySelector(".ec-at-bo").click();
  la(!("extra" in lastList()), "Bỏ lọc khong xoa loc cot");
  la(!pheu("x:contract_type").classList.contains("ec-at-co") && d.querySelector(".ec-at-reset").textContent === "Xoá lọc",
     "Bỏ lọc xong pheu/so dem van con");
  // nut chieu trong o noi: ap dung ngay, giu dau tick vua chon
  pheu("x:contract_type").click();
  tick(pop(), "x:contract_type", ["Thuê"]);
  pop().querySelector('.ec-at-hg[data-dir="desc"]').click();
  la(JSON.stringify(lastList().sort) === '{"col":"x:contract_type","dir":"desc"}' &&
     JSON.stringify(lastList().extra) === '{"contract_type":["Thuê"]}', "nut chieu trong o noi sai: " + JSON.stringify(lastList()));
  la(pop().hasAttribute("hidden"), "bam nut chieu xong phai dong");
  la(chips().includes("Loại hợp đồng: Z → A"), "chip thu tu sai: " + chips());
}

// ---- tieu de · nguoi de nghi: hai nhom ------------------------------------------------
{
  const { pheu, pop, lastList, chips } = H;
  pheu("title").click();
  const p = pop();
  const nhom = [...p.querySelectorAll(".ec-at-nhom legend")].map((x) => x.textContent);
  la(nhom.join("|") === "Người đề nghị|Phòng ban", "o noi tieu de phai co hai nhom: " + nhom);
  la(!p.querySelector("img") && [...p.querySelectorAll('.ec-at-nhom[data-nhom="department"] input')].some((i) => i.value === XAU),
     "gia tri phong ban khong duoc thoat HTML");
  tick(p, "requester", ["a@e.c", "b@e.c"]);
  tick(p, "department", ["Ops"]);
  p.querySelector(".ec-at-ap").click();
  const f = lastList();
  la(JSON.stringify(f.requester) === '["a@e.c","b@e.c"]' && JSON.stringify(f.department) === '["Ops"]',
     "nguoi de nghi / phong ban phai gui danh sach (user id): " + JSON.stringify(f));
  la(chips().includes("Người đề nghị: An, Bình"), "chip nguoi de nghi phai hien TEN, khong hien email: " + chips());
  la(chips().includes("Phòng ban: Ops"), "chip phong ban");
}

// ---- trang thai -----------------------------------------------------------------------
{
  const { pheu, pop, lastList, chips } = H;
  pheu("status").click();
  const nhan = [...pop().querySelectorAll(".ec-at-ck span")].map((x) => x.textContent);
  la(nhan.join() === "Chờ duyệt,Hoàn tất,Từ chối", "trang thai phai nhan tieng Viet: " + nhan);
  tick(pop(), "status", ["Completed", "Rejected"]);
  pop().querySelector(".ec-at-ap").click();
  la(JSON.stringify(lastList().status) === '["Completed","Rejected"]', "trang thai gui gia tri goc (tieng Anh)");
  la(chips().includes("Trạng thái: Hoàn tất, Từ chối"), "chip trang thai: " + chips());
}

// ---- 3. so tien -----------------------------------------------------------------------
{
  const { w, pheu, pop, lastList, chips } = H;
  pheu("amount").click();
  const p = pop();
  la([...p.querySelectorAll(".ec-at-hg")].map((b) => b.textContent).join("|") === "Thấp → cao|Cao → thấp", "nut chieu cot tien");
  const lo = p.querySelector('[data-k="amount_min"]'), hi = p.querySelector('[data-k="amount_max"]');
  la(lo.hasAttribute("data-money") && lo.getAttribute("inputmode") === "numeric", "o so tien phai dung asset dung chung");
  go(w, lo, "1.500.000");
  go(w, hi, "20000000");
  la(hi.value === "20.000.000", "o so tien khong dinh dang dau cham khi go: " + hi.value);
  p.querySelector(".ec-at-ap").click();
  la(lastList().amount_min === 1500000 && lastList().amount_max === 20000000,
     "1.500.000 phai thanh 1500000: " + JSON.stringify(lastList()));
  la(chips().includes("Giá trị: 1.500.000 – 20.000.000"), "chip so tien: " + chips());
  pheu("amount").click();
  go(w, pop().querySelector('[data-k="amount_max"]'), "");
  pop().querySelector(".ec-at-ap").click();
  la(!("amount_max" in lastList()) && chips().includes("Giá trị: 1.500.000 – …"), "dau bo trong phai la …: " + chips());
  const gia = { value: "1.500.000", hasAttribute: () => true };
  const cu = w.EcMoney; w.EcMoney = undefined;
  la(w.EcAllTab._docTien(gia) === 1500000, "khong co EcMoney: 1.500.000 doc sai");
  w.EcMoney = cu;
}

// ---- ngay gui --------------------------------------------------------------------------
{
  const { pheu, pop, lastList, chips } = H;
  pheu("submitted").click();
  const p = pop();
  la([...p.querySelectorAll(".ec-at-hg")].map((b) => b.textContent).join("|") === "Cũ → mới|Mới → cũ", "nut chieu cot ngay");
  p.querySelector('[data-k="date_from"]').value = "2026-10-16";
  p.querySelector('[data-k="date_to"]').value = "2026-10-01";
  p.querySelector(".ec-at-ap").click();
  la(lastList().date_from === "2026-10-01" && lastList().date_to === "2026-10-16", "go nguoc hai dau ngay phai dao lai");
  la(chips().includes("Ngày gửi: 01/10/2026 – 16/10/2026"), "chip ngay: " + chips());
}

// ---- 5. export cung bo loc + thu tu ----------------------------------------------------
{
  const { d, lastList, fetches } = H;
  d.querySelector('.ec-at-x[data-fmt="xlsx"]').click();
  la(fetches.length === 1, "bam Excel khong goi export");
  const body = JSON.parse(fetches[0].o.body);
  la(body.filters === JSON.stringify(lastList()), "export gui bo loc KHAC bang: " + body.filters);
  la(JSON.parse(body.filters).sort.col === "x:contract_type", "export mat thu tu");
}

// ---- chip x bo tung o ------------------------------------------------------------------
{
  const { d, lastList } = H;
  const x = [...d.querySelectorAll(".ec-at-chip-x")].find((b) => b.getAttribute("data-bo") === "status");
  x.click();
  la(!("status" in lastList()) && "requester" in lastList(), "bam x tren chip phai bo DUNG o do");
}

// ---- 4. Xoa loc tra ve mac dinh ----------------------------------------------------------
{
  const { d, lastList, th, chips } = H;
  d.querySelector(".ec-at-reset").click();
  await cho();
  la(JSON.stringify(lastList()) === "{}", "Xoá lọc con sot: " + JSON.stringify(lastList()));
  la(th("submitted").classList.contains("ec-at-on") && th("submitted").getAttribute("aria-sort") === "descending",
     "Xoá lọc khong tra thu tu ve mac dinh");
  la(!d.querySelector(".ec-at-pheu.ec-at-co"), "Xoá lọc xong van con pheu dang loc");
  la(chips().length === 0 && d.querySelector(".ec-at-chips").hasAttribute("hidden"), "Xoá lọc xong van con chip");
  la(d.querySelector(".ec-at-reset").textContent === "Xoá lọc", "nut xoa loc van dem");
  // Xoa loc ve lai khung NHUNG khong duoc gan them listener: bam sap xep phai tai DUNG mot lan.
  const n = H.lists().length;
  H.sx("x:brand").click();
  la(H.lists().length === n + 1, "sau Xoá lọc, mot cu bam tai " + (H.lists().length - n) + " lan (listener bi gan trung)");
}

// ---- danh sach dai co o tim ------------------------------------------------------------
{
  const nhieu = Array.from({ length: 12 }, (_, i) => ({ value: "u" + i + "@e.c", label: i === 3 ? "Đông Diệp" : "Người " + i }));
  const { w, pheu, pop } = await dung(Object.assign({}, OPTS_CR, { requesters: nhieu }));
  pheu("title").click();
  const tim = pop().querySelector('.ec-at-nhom[data-nhom="requester"] .ec-at-tim');
  la(!!tim, "danh sach > 8 phai co o tim");
  la(!pop().querySelector('.ec-at-nhom[data-nhom="department"] .ec-at-tim'), "danh sach ngan khong can o tim");
  go(w, tim, "dong");
  const hien = [...pop().querySelectorAll('.ec-at-nhom[data-nhom="requester"] .ec-at-ck')].filter((l) => !l.hasAttribute("hidden"));
  la(hien.length === 1 && hien[0].textContent === "Đông Diệp", "tim khong dau phai ra 'Đông Diệp': " + hien.length);
}

// ---- 6. 390px: tam day ------------------------------------------------------------------
{
  const { d, pheu, pop } = await dung(OPTS_CR, { rong: 390 });
  pheu("amount").click();
  la(pop().classList.contains("ec-at-sheet"), "390px: o noi phai la tam day");
  la(!d.querySelector(".ec-at-nen").hasAttribute("hidden"), "390px: phai co nen toi");
  la(/\.ec-at-pop\.ec-at-sheet\{[^}]*position:fixed;[^}]*bottom:0;[^}]*max-height:70vh/.test(CSS),
     "CSS tam day thieu fixed/bottom/max-height 70vh");
  la(/\.ec-at-sheet \.ec-at-pop-chan button,[^{]*\{[^}]*height:44px/.test(CSS), "nut tam day phai >= 44px");
  d.querySelector(".ec-at-nen").click();
  la(pop().hasAttribute("hidden") && d.querySelector(".ec-at-nen").hasAttribute("hidden"), "bam nen toi phai dong");
  la(/\.ec-at-wrap\{[^}]*overflow:auto/.test(CSS), "bang rong khong cuon ngang trong khung");
}

// ---- 7. thoat HTML cua nhan cot + chip ----------------------------------------------------
{
  const o = Object.assign({}, OPTS_CR, {
    columns: [{ label: '<img src=x onerror=1>', fieldname: "brand", kind: "text", filter: true }],
    sort_cols: ["submitted", "x:brand"],
  });
  const { d, pheu, pop, chips } = await dung(o);
  la(!d.querySelector("thead img"), "nhan cot tu server khong duoc thoat HTML");
  pheu("x:brand").click();
  tick(pop(), "x:brand", [XAU]);
  pop().querySelector(".ec-at-ap").click();
  la(!d.querySelector(".ec-at-chips img") && chips().some((c) => c.includes(XAU)), "chip khong thoat HTML");
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
