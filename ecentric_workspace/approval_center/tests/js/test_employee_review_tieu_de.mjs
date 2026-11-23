// Danh gia nhan su - TIEU DE TUY CHINH (Hoan chot 23/11/2026): o "Tieu de (tuy chinh)" chi hien voi C&B
// tren NHAP (server tra extra.danh_gia.sua_tieu_de), placeholder = tieu de tu sinh; Luu nhap / Gui ngay
// gui custom_title; phieu da gui / NV / LM khong co o. Hang cho C&B hien cot Tieu de.
//     NODE_PATH=/tmp/node_modules node ecentric_workspace/approval_center/tests/js/test_employee_review_tieu_de.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
function split(path) {
  const HTML = readFileSync(join(APP, path), "utf8");
  const m = HTML.match(/<script(?: id="ec-[^"]+")?>/g);
  const tag = m[m.length - 1];
  const i = HTML.lastIndexOf(tag);
  return [HTML.slice(0, i), HTML.slice(i + tag.length).replace(/<\/script>\s*$/, "")];
}
const [markup, JS] = split("approval_center/features/employee_review/ui/main_section.html");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 5)); };
const AUTO = "Đánh giá thử việc - Nguyễn Thị D - đến 31/12/2026";

function det(over) {
  const d = { business: { name: "EC-EVAL-2026-00001", request_title: AUTO, review_type: "Thử việc", ten_nhan_vien: "Nguyễn Thị D",
      hd_den_ngay: "2026-12-31", auto_draft: 1, auto_submit_on: "2026-12-17", custom_title: "", ghi_chu_cnb: "" },
    approval: { name: null, approval_status: "Draft", current_level: 0 }, levels: [], approvers: [], attachments: [], timeline: [],
    extra: { danh_gia: { tieu_chi: [], nv_diem: {}, xem_lm: 1, cap_cua_toi: 0, la_nv: 0, la_cnb: 1, lm_nhap_o_cap_ceo: 0,
      lich_su_hd: [], lua_chon: null, khao_sat: [], ho_so: null, tieu_de_tu_sinh: AUTO, sua_tieu_de: 1 } },
    capabilities: {} };
  (over || (() => {}))(d); return d;
}
function boot(DET) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url: "https://x.test/approvals/employee-review?id=EC-EVAL-2026-00001" });
  const w = dom.window; w.__calls = [];
  w.frappe = { csrf_token: "x", call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args, o.type]);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { my_requests: true }, context: {}, form_options: {} } });
    if (m === "get_detail") return Promise.resolve({ message: DET });
    return Promise.resolve({ message: { name: "EC-EVAL-2026-00001", detail: DET } }); } };
  w.eval(JS); return w;
}

// 1. C&B tren nhap: o tieu de, placeholder = tu sinh, Luu nhap gui custom_title (da trim).
{ const w = boot(det()); await flush();
  const d = w.document; const inp = d.getElementById("er-ct");
  ok(!!inp, "C&B nhap: co o Tieu de (tuy chinh)");
  ok(inp && inp.getAttribute("placeholder") === AUTO && inp.value === "", "placeholder = tieu de tu sinh, gia tri rong");
  ok(inp && inp.getAttribute("maxlength") === "140", "maxlength 140");
  ok(/Tiêu đề \(tuỳ chỉnh\)/.test(d.getElementById("er-body").innerHTML), "nhan o dung chu");
  inp.value = "  Đánh giá cuối thử việc - D  ";
  d.querySelector('[data-act="savedraft"]').click(); await flush();
  const c = w.__calls.find((x) => x[0] === "save_draft");
  const p = c && JSON.parse(c[1].payload);
  ok(p && p.custom_title === "Đánh giá cuối thử việc - D" && "ghi_chu_cnb" in p, "save_draft gui custom_title + ghi chu");
  ok(w.__calls.findIndex((x) => x[0] === "nhan_nhap") < w.__calls.findIndex((x) => x[0] === "save_draft"), "nhan nhap truoc khi luu"); }

// 2. Gui ngay: luu (co custom_title) roi moi submit.
{ const w = boot(det((x) => { x.business.custom_title = "Tiêu đề cũ"; x.business.request_title = "Tiêu đề cũ"; })); await flush();
  const d = w.document;
  ok(d.getElementById("er-ct").value === "Tiêu đề cũ", "dien san tieu de tuy chinh da luu");
  d.getElementById("er-ct").value = "";
  d.querySelector('[data-act="submitdraft"]').click(); await flush();
  const names = w.__calls.map((x) => x[0]);
  const c = w.__calls.find((x) => x[0] === "save_draft");
  ok(c && JSON.parse(c[1].payload).custom_title === "", "xoa tieu de -> gui rong (quay ve tu sinh)");
  ok(names.indexOf("submit_request") > names.indexOf("save_draft"), "luu roi moi gui"); }

// 3. Server khong cho sua (phieu da gui / khong phai C&B): khong co o, payload khong co custom_title.
{ const w = boot(det((x) => { x.extra.danh_gia.sua_tieu_de = 0; })); await flush();
  const d = w.document;
  ok(!d.getElementById("er-ct"), "sua_tieu_de=0: khong ve o");
  d.querySelector('[data-act="savedraft"]').click(); await flush();
  const c = w.__calls.find((x) => x[0] === "save_draft");
  ok(c && !("custom_title" in JSON.parse(c[1].payload)), "khong gui khoa custom_title khi khong co o"); }
{ const w = boot(det((x) => { x.approval = { name: "AR", approval_status: "Pending", current_level: 1 };
    x.levels = [{ level_no: 1, level_name: "NV", level_status: "In Progress" }];
    Object.assign(x.extra.danh_gia, { sua_tieu_de: 0, la_cnb: 0, la_nv: 1, xem_lm: 0, cap_cua_toi: 1 });
    x.business.request_title = "Đánh giá đặc biệt"; })); await flush();
  const d = w.document;
  ok(!d.getElementById("er-ct"), "NV / phieu da gui: khong co o tieu de");
  ok(/Đánh giá đặc biệt/.test(d.getElementById("er-body").innerHTML), "tieu de (tuy chinh) hien o dau phieu"); }

// 4. Escape placeholder / gia tri.
{ const w = boot(det((x) => { x.extra.danh_gia.tieu_de_tu_sinh = '"><img src=x>'; x.business.custom_title = "<b>x</b>"; })); await flush();
  const d = w.document;
  ok(!d.querySelector("#er-body img") && d.getElementById("er-ct").value === "<b>x</b>", "escape placeholder + gia tri"); }

// 5. Hang cho C&B: cot Tieu de o 3 tab co phieu.
{ const [qm, qjs] = split("hr/pages/danh_gia_nhan_su/main_section.html");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + qm + "</body></html>", { runScripts: "outside-only", url: "https://x.test/ec-hr/danh-gia-nhan-su" });
  const w = dom.window;
  w.frappe = { call: (o) => { const m = o.method.split(".").pop();
    if (m === "hang_cho") return Promise.resolve({ message: {
      nhap: [{ name: "EV1", request_title: "Đánh giá cuối thử việc <i>A</i>", ten_nhan_vien: "A", review_type: "Thử việc", hd_den_ngay: "2026-12-31", auto_submit_on: "2026-12-17", requested_by: "cnb@x" }],
      thieu_du_lieu: [], thieu_ngay: [],
      cho_ho_so: [{ name: "EV2", request_title: "Đánh giá HĐ - B", ten_nhan_vien: "B", review_type: "Hợp đồng" }],
      dang_chay: [{ name: "EV3", request_title: "", ten_nhan_vien: "C", review_type: "Thực tập", buoc: "LM" }] } });
    return Promise.resolve({ message: {} }); } };
  w.eval(qjs); await flush();
  const d = w.document; const body = () => d.getElementById("er-body");
  ok(body().querySelector("thead th").textContent === "Tiêu đề", "nhap: cot dau Tieu de");
  ok(body().querySelector("tbody td b").textContent === "Đánh giá cuối thử việc <i>A</i>" && !body().querySelector("tbody i"), "nhap: hien tieu de (escape)");
  d.querySelector('[data-tab="cho_ho_so"]').click();
  ok(/Đánh giá HĐ - B/.test(body().innerHTML) && body().querySelector("thead th").textContent === "Tiêu đề", "cho ho so: cot Tieu de");
  d.querySelector('[data-tab="dang_chay"]').click();
  ok(body().querySelector("tbody td b").textContent === "EV3", "dang chay: thieu tieu de -> hien ma phieu"); }

console.log(`${oks} dat, ${fails} hong`);
process.exit(fails ? 1 : 0);
