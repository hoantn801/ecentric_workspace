// Copyright (c) 2026, eCentric and contributors
//
// Hub /approvals/all-requests: nut "Excel" / "CSV" tren thanh loc (27/11/2026, Ke toan).
//
// Chay TRANG THAT (main_section.html) + asset dung chung THAT (ec_alltab, ec_approval_ui) trong
// jsdom. Giu:
//   1. Nut nam san trong markup (khong ve sau), khong emoji, icon SVG net manh .ec-btn-ic.
//   2. Bam -> MOT POST toi reporting.api.export_requests, co CSRF, gui DUNG tab + bo loc + o tim
//      kiem nhu list_requests - KHONG gui danh sach ma phieu.
//   3. Dang tai: nut bam doi "Dang xuat…", ca hai nut khoa, bam lan hai khong goi them.
//   4. Xong: tai voi ten tep cua server (Content-Disposition), nut tro lai nguyen (ca icon).
//   5. Loi server (vuot tran) -> toast NGUYEN VAN cau tieng Viet; loi mang -> cau huong dan
//      tieng Viet cua EcApprovalUI; nut tro lai.
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
const HTML = readFileSync(join(APP, "approval_center", "ui", "all_requests", "main_section.html"), "utf8");
const ALLTAB = readFileSync(join(APP, "public", "js", "ec_alltab.bundle.js"), "utf8");
const UI = readFileSync(join(APP, "public", "js", "ec_approval_ui.bundle.js"), "utf8");

let dat = 0;
const hong = [];
const la = (dk, mo) => { if (dk) dat++; else hong.push(mo); };
const cho = (ms) => new Promise((r) => setTimeout(r, ms || 0));
const METHOD = "ecentric_workspace.approval_center.reporting.api.export_requests";

// ---- 0. markup ---------------------------------------------------------------------------
const nutX = (HTML.match(/<button[^>]*id="apl-xlsx"[\s\S]*?<\/button>/) || [""])[0];
const nutC = (HTML.match(/<button[^>]*id="apl-csv"[\s\S]*?<\/button>/) || [""])[0];
la(nutX && nutC, "hai nut Excel / CSV phai nam san trong markup");
la(/>Excel<\/button>$/.test(nutX) && />CSV<\/button>$/.test(nutC), "nhan nut la 'Excel' / 'CSV'");
la(/<svg class="ec-btn-ic"[^>]*stroke-width="1\.8"/.test(nutX) && /<svg class="ec-btn-ic"/.test(nutC),
   "icon la SVG net manh .ec-btn-ic");
la(!/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(nutX + nutC), "khong emoji trong nut");
la(/<div class="filters">[\s\S]*id="apl-xlsx"[\s\S]*<\/div>\s*<div class="card" id="apl-body">/.test(HTML),
   "nut nam tren thanh loc, tren bang");
la(!/<script id="ec-(?!approval-all")/.test(HTML), "khong them khoi <script id=ec-...> moi vao trang");

// ---- moi truong ----------------------------------------------------------------------------
function dung(fetchImpl) {
  const dom = new JSDOM(HTML.replace(/<script id="ec-approval-all">/, "<script>window.__noBoot=1;</script><script id=\"ec-approval-all\">"), {
    runScripts: "outside-only", pretendToBeVisual: true,
    url: "https://team.x/approvals/all-requests?box=fulfil",
  });
  const w = dom.window;
  const st = {};
  Object.defineProperty(w, "localStorage", { value: { getItem: (k) => (k in st ? st[k] : null), setItem: (k, v) => { st[k] = String(v); } } });
  const lan = [];
  w.frappe = {
    csrf_token: "TOK123",
    call(o) {
      if (/get_filter_options/.test(o.method)) {
        return Promise.resolve({ message: { scope_mode: "department", categories: ["Tài chính"],
          types: [{ v: "PAYMENT_REQUEST", label: "Đề nghị thanh toán" }],
          departments: ["Finance - EC", "Ops - EC"], statuses: ["Pending", "Completed"] } });
      }
      if (/list_requests/.test(o.method)) {
        return Promise.resolve({ message: { rows: [{ name: "EC-APR-1", type: "Đề nghị thanh toán",
          status: "Pending", status_label: "Pending", submitted_at: "2026-11-20 09:00:00",
          requester_info: { name: "An" }, sent_to: [] }], total: 1 } });
      }
      return Promise.resolve({ message: {} });
    },
  };
  w.fetch = (url, init) => { lan.push({ url, init }); return fetchImpl(url, init); };
  const tai = [];
  w.URL.createObjectURL = () => "blob:x";
  w.URL.revokeObjectURL = () => {};
  w.HTMLAnchorElement.prototype.click = function () { tai.push({ href: this.href, download: this.download }); };
  w.eval(UI);
  w.eval(ALLTAB);
  w.eval(HTML.match(/<script id="ec-approval-all">([\s\S]*?)<\/script>/)[1]);
  return { w, d: w.document, lan, tai };
}
function traLoi(body, init) {
  const h = new Map(Object.entries(Object.assign({ "Content-Disposition": "attachment; filename=\"tat-ca-yeu-cau_cho-toi-xu-ly_20261127-0930.xlsx\"" }, (init || {}).headers || {})));
  return {
    ok: (init || {}).status ? (init.status < 400) : true,
    status: (init || {}).status || 200,
    headers: { get: (k) => h.get(k) || null },
    blob: () => Promise.resolve(body),
    text: () => Promise.resolve(typeof body === "string" ? body : ""),
  };
}

// ---- 1. gui dung tab + bo loc, loading, chong bam hai lan, ten tep ---------------------------
{
  let giai;
  const { w, d, lan, tai } = dung(() => new Promise((r) => { giai = r; }));
  await cho(20);
  d.getElementById("f-department").value = "Finance - EC";
  d.getElementById("f-status").value = "Pending";
  d.getElementById("f-from").value = "2026-11-01";
  d.getElementById("f-to").value = "2026-11-30";
  d.getElementById("f-search").value = "PAYR";
  const x = d.getElementById("apl-xlsx"), c = d.getElementById("apl-csv");
  const htmlCu = x.innerHTML;
  x.click();
  la(lan.length === 1, "bam Excel -> dung MOT request (co " + lan.length + ")");
  const r = lan[0] || { init: { headers: {} } };
  la(r.url === "/api/method/" + METHOD, "goi dung endpoint export_requests: " + r.url);
  la(r.init.method === "POST", "tai la POST (endpoint ghi vet)");
  la(r.init.headers["X-Frappe-CSRF-Token"] === "TOK123", "POST kem CSRF token");
  const b = JSON.parse(r.init.body || "{}");
  la(b.box === "fulfil", "gui tab dang dung (fulfil tu ?box=): " + b.box);
  la(b.fmt === "xlsx", "Excel -> fmt xlsx");
  la(b.search === "PAYR", "gui o tim kiem");
  const f = JSON.parse(b.filters || "{}");
  la(f.department === "Finance - EC" && f.status === "Pending" && f.date_from === "2026-11-01" && f.date_to === "2026-11-30",
     "gui du bo loc dang chon: " + b.filters);
  la(JSON.stringify(b) === JSON.stringify(w.ApprovalAll.exportArgs("xlsx")), "cung bo tham so voi exportArgs");
  la(!/EC-APR-1/.test(r.init.body) && !("names" in b) && !("rows" in b), "KHONG gui danh sach ma phieu");
  la(Object.keys(b).sort().join(",") === "box,filters,fmt,search", "chi gui box/filters/search/fmt, khong gui user: " + Object.keys(b));
  // dang tai
  la(x.disabled && c.disabled, "dang tai: ca hai nut bi khoa");
  la(x.textContent === "Đang xuất…", "dang tai: nut doi chu 'Đang xuất…'");
  la(x.getAttribute("aria-busy") === "true", "dang tai: aria-busy");
  x.click(); c.click();
  la(lan.length === 1, "bam lan hai trong luc tai khong goi them request");
  // Goi thang (vd phim tat / ma khac goi exportFile) khi dang tai cung khong gui lan hai.
  const lai = await w.ApprovalAll.exportFile(x);
  la(lai === false && lan.length === 1, "goi exportFile khi dang tai -> bo qua, khong request moi");
  giai(traLoi("BLOB"));
  await cho(10);
  la(tai.length === 1 && tai[0].download === "tat-ca-yeu-cau_cho-toi-xu-ly_20261127-0930.xlsx",
     "tai voi ten tep cua server: " + JSON.stringify(tai));
  la(!x.disabled && !c.disabled, "xong: nut mo lai");
  la(x.innerHTML === htmlCu && x.querySelector("svg.ec-btn-ic"), "xong: nut tro lai nguyen (ca icon)");
  la(!x.hasAttribute("aria-busy"), "xong: bo aria-busy");
}

// ---- 2. CSV + doi tab -------------------------------------------------------------------------
{
  const { d, lan } = dung(() => Promise.resolve(traLoi("B", { headers: { "Content-Disposition": "attachment; filename*=UTF-8''tat-ca-yeu-cau_da-gui_20261127-0930.csv" } })));
  await cho(20);
  d.querySelector('#apl-tabs .tab[data-box="sent"]').click();
  await cho(5);
  d.getElementById("apl-csv").click();
  const b = JSON.parse((lan[0] || { init: { body: "{}" } }).init.body);
  la(b.fmt === "csv", "CSV -> fmt csv");
  la(b.box === "sent", "doi tab 'Đã gửi' -> gui box=sent: " + b.box);
  la(JSON.parse(b.filters) && Object.keys(JSON.parse(b.filters)).length === 0, "khong loc -> filters rong");
}
{
  const { d, lan } = dung(() => Promise.resolve(traLoi("B")));
  await cho(20);
  d.querySelector('#apl-tabs .tab[data-box="all"]').click();
  await cho(5);
  d.getElementById("apl-xlsx").click();
  la(JSON.parse(lan[0].init.body).box === "all", "tab 'Tất cả' -> box=all");
}

// ---- 3. loi server (vuot tran) -> toast nguyen van -------------------------------------------
{
  const CAU = "Tab và bộ lọc đang khớp 6123 yêu cầu, vượt mức 5000 cho một lần tải. Hãy thu hẹp khoảng ngày hoặc thêm bộ lọc rồi thử lại.";
  const sm = JSON.stringify([JSON.stringify({ message: CAU })]);
  const { d, tai } = dung(() => Promise.resolve(traLoi(JSON.stringify({ exc_type: "ValidationError", _server_messages: sm }), { status: 417 })));
  await cho(20);
  const x = d.getElementById("apl-xlsx");
  x.click();
  await cho(10);
  const t = d.getElementById("ec-apl-toast");
  la(t && !t.hidden && t.textContent === CAU, "vuot tran: toast dung cau server: " + (t && t.textContent));
  la(t && t.className === "err", "toast kieu loi");
  la(tai.length === 0, "loi thi khong tai gi");
  la(!x.disabled && x.textContent.trim() === "Excel", "loi: nut tro lai binh thuong");
}
// ---- 4. loi mang -> cau tieng Viet ---------------------------------------------------------
{
  const { d } = dung(() => Promise.reject(new TypeError("Failed to fetch")));
  await cho(20);
  d.getElementById("apl-csv").click();
  await cho(10);
  const t = d.getElementById("ec-apl-toast");
  la(t && /Mất kết nối/.test(t.textContent), "loi mang: cau huong dan tieng Viet: " + (t && t.textContent));
  la(!d.getElementById("apl-csv").disabled && !d.getElementById("apl-xlsx").disabled, "loi mang: nut mo lai");
}
// ---- 5. loi 500 ky thuat -> khong lo traceback --------------------------------------------
{
  const { d } = dung(() => Promise.resolve(traLoi(JSON.stringify({ exception: "pymysql.err.OperationalError: (1054, \"Unknown column\")", exc_type: "OperationalError" }), { status: 500 })));
  await cho(20);
  d.getElementById("apl-xlsx").click();
  await cho(10);
  const t = d.getElementById("ec-apl-toast");
  la(t && !/pymysql|1054/.test(t.textContent) && t.textContent.length > 0, "loi he thong: khong lo chi tiet ky thuat: " + (t && t.textContent));
}
// ---- 6. ten tep: hai dang header ------------------------------------------------------------
{
  const { w } = dung(() => Promise.resolve(traLoi("B")));
  const h = w.EcAllTab._tenTuHeader;
  la(h("attachment; filename=\"a b.xlsx\"") === "a b.xlsx", "doc filename=\"...\"");
  la(h("attachment; filename*=UTF-8''t%E1%BB%87p.csv") === "tệp.csv", "doc filename*=UTF-8''");
  la(h("attachment; filename=x.csv") === "x.csv", "doc filename=khong ngoac");
  la(h(null) === "", "khong co header -> rong");
}

hong.forEach((m) => console.log("  HONG: " + m));
console.log(dat + " dat, " + hong.length + " hong");
process.exit(hong.length ? 1 : 0);
