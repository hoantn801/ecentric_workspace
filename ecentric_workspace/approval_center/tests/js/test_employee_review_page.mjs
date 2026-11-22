// Danh gia nhan su 23/11/2026 (HR Dot 2): form /approvals/employee-review + hang cho C&B
// /ec-hr/danh-gia-nhan-su + ket qua khao sat moc /khao-sat/ca-nhan.
//     NODE_PATH=/tmp/node_modules node ecentric_workspace/approval_center/tests/js/test_employee_review_page.mjs
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

const TC = [{ tieu_chi: "Kết quả công việc", mo_ta: "KPI" }, { tieu_chi: "Thái độ" }];
const LEVELS = [{ level_no: 1, level_name: "Nhân viên tự đánh giá", level_status: "Approved" },
  { level_no: 2, level_name: "Line Manager đánh giá", level_status: "In Progress" },
  { level_no: 3, level_name: "CEO duyệt", level_status: "Pending" }];
function det(over) {
  const base = { business: { name: "EC-EVAL-2026-00001", request_title: "Đánh giá thử việc - Nguyễn Thị D", review_type: "Thử việc",
      ten_nhan_vien: "Nguyễn <b>D</b>", loai_hop_dong: "Thử việc", hd_tu_ngay: "2026-11-02", hd_den_ngay: "2026-12-31",
      line_manager: "lm@x", employee_user: "nv@x", nv_nhan_xet: "Em cố gắng" },
    approval: { name: "AR", approval_status: "Pending", current_level: 2 }, levels: LEVELS, approvers: [], attachments: [], timeline: [],
    extra: { danh_gia: { tieu_chi: TC, nv_diem: { 0: { diem: 4 }, 1: { diem: 5 } }, xem_lm: 1, cap_cua_toi: 2, la_nv: 0, la_cnb: 0,
      lm_nhap_o_cap_ceo: 0, lich_su_hd: [{ loai_hop_dong: "Thử việc", tu_ngay: "2026-11-02", den_ngay: "2026-12-31" }],
      lua_chon: { ket_qua: [{ value: "Đạt", enabled: true, ly_do: "" }, { value: "Không đạt", enabled: true, ly_do: "" },
        { value: "Gia hạn", enabled: false, ly_do: "Thời gian thử việc 60 ngày đã chạm trần 60 ngày (Điều 25)" }],
        thoi_han: [{ value: "12 tháng", enabled: true }, { value: "Không xác định thời hạn", enabled: true }],
        can_thoi_han_khi: ["Đạt"], gia_han_toi_da: null, can_ngay_gia_han: false, ghi_chu: ["Trần thử việc của vị trí: 60 ngày."] },
      khao_sat: [{ title: "Khảo sát thử việc - mốc 1", submitted: true, so_cau_an: 1, answers: [{ title: "Hướng dẫn đủ?", value: "4" }] }],
      ho_so: null } },
    capabilities: { can_request_information: true, can_cancel: false } };
  const d = JSON.parse(JSON.stringify(base));
  (over || ((x) => x))(d); return d;
}
function boot(url, DET, onCall) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url });
  const w = dom.window; w.__calls = [];
  w.frappe = { csrf_token: "x", call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args, o.type]);
    if (onCall) { const r = onCall(m, o.args); if (r) return r; }
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { my_requests: true, my_approvals: true, all: true }, context: {}, form_options: {} } });
    if (m === "get_detail") return Promise.resolve({ message: DET });
    return Promise.resolve({ message: { rows: [], detail: DET } }); } };
  w.eval(JS); return w;
}
const URL = "https://x.test/approvals/employee-review?id=EC-EVAL-2026-00001";

// 1. LM o cap 2: form ket qua, Gia han bi khoa kem ly do Dieu 25, nut Gui CEO, khong Tu choi.
{ const w = boot(URL, det()); await flush();
  const d = w.document, h = d.getElementById("er-body").innerHTML;
  const gh = d.querySelector('input[name="er-kq"][value="Gia hạn"]');
  ok(!!gh && gh.disabled, "Gia han bi khoa khi cham tran");
  ok(/chạm trần 60 ngày \(Điều 25\)/.test(h), "hien ly do Dieu 25");
  ok(/chỉ hiện với nhân viên/.test(h), "canh bao nhan xet an voi NV toi khi CEO duyet");
  ok(!!d.querySelector('[data-act="lmsend"]') && !!d.querySelector('[data-act="back"]'), "nut Gui CEO + Tra lai NV");
  ok(!d.querySelector('[data-act="reject"]'), "khong co Tu choi");
  ok([...d.querySelectorAll("input.ro")].some((i) => i.value === "Nguyễn <b>D</b>"), "ten hien dung chu (escape)");
  ok(/mốc 1/.test(h) && /1 câu thuộc nhóm/.test(h), "khao sat moc kem so cau bi an");
  // validate client: thieu nhan xet / thoi han
  ok(/Vui lòng chọn kết quả/.test(w.EmployeeReview.validateLm(w.EmployeeReview.collectLm(), det().extra.danh_gia)), "chua chon ket qua");
  d.querySelector('input[name="er-kq"][value="Đạt"]').checked = true;
  d.querySelector('input[name="er-kq"][value="Đạt"]').dispatchEvent(new w.Event("change"));
  ok(d.getElementById("er-th-wrap").style.display === "", "chon Dat -> hien o thoi han HD");
  ok(d.getElementById("er-gh-wrap").style.display === "none", "khong hien ngay gia han");
  d.getElementById("er-nx").value = "Hoàn thành tốt KPI thử việc";
  ok(/thời hạn/.test(w.EmployeeReview.validateLm(w.EmployeeReview.collectLm(), det().extra.danh_gia)), "Dat ma chua chon thoi han -> chan");
  d.getElementById("er-th").value = "12 tháng";
  d.querySelector('[data-act="lmsend"]').click(); await flush();
  const c = w.__calls.find((x) => x[0] === "nop_danh_gia_lm");
  ok(!!c && JSON.parse(c[1].payload).lm_thoi_han_hd === "12 tháng" && c[2] === "POST", "gui nop_danh_gia_lm (POST) kem thoi han"); }

// 2. NV o cap 2: KHONG thay form / noi dung LM, khong thay khao sat.
{ const w = boot(URL, det((x) => { const g = x.extra.danh_gia; g.xem_lm = 0; g.cap_cua_toi = 0; g.la_nv = 1; delete g.lua_chon; g.khao_sat = [];
    x.business.lm_nhan_xet = undefined; })); await flush();
  const d = w.document, h = d.getElementById("er-body").innerHTML;
  ok(!d.querySelector('input[name="er-kq"]') && !d.getElementById("er-nx"), "NV khong co o LM");
  ok(/sẽ hiện với bạn sau khi CEO duyệt/.test(h), "banner an voi NV");
  ok(!/Khảo sát mốc/.test(h), "NV khong thay khoi khao sat");
  ok(!d.querySelector('[data-act="lmsend"]'), "NV khong co nut Gui CEO"); }

// 3. NV o cap 1: cham diem bat buoc, gui nop_tu_danh_gia.
{ const w = boot(URL, det((x) => { const g = x.extra.danh_gia; g.xem_lm = 0; g.cap_cua_toi = 1; g.la_nv = 1; g.nv_diem = {}; x.approval.current_level = 1; })); await flush();
  const d = w.document;
  ok(d.querySelectorAll("[data-nv-diem]").length === 2, "o cham diem tung tieu chi");
  d.querySelector('[data-act="selfsend"]').click(); await flush();
  ok(!w.__calls.find((x) => x[0] === "nop_tu_danh_gia"), "thieu diem -> khong goi server");
  d.querySelectorAll("[data-nv-diem]").forEach((s) => { s.value = "4"; });
  d.querySelector('[data-act="selfsend"]').click(); await flush();
  const c = w.__calls.find((x) => x[0] === "nop_tu_danh_gia");
  ok(!!c && JSON.parse(c[1].payload).nv_diem["1"].diem === "4", "gui tu danh gia"); }

// 4. Nhap cua C&B: nut Gui ngay / Nhan nhap / Huy nhap + ngay tu gui; o ghi chu data-model.
{ const w = boot(URL, det((x) => { x.approval = { name: null, approval_status: "Draft", current_level: 0 }; x.levels = [];
    x.business.auto_draft = 1; x.business.auto_submit_on = "2026-12-17"; const g = x.extra.danh_gia; g.la_cnb = 1; g.cap_cua_toi = 0; delete g.lua_chon; })); await flush();
  const d = w.document, h = d.getElementById("er-body").innerHTML;
  ok(/17\/12\/2026/.test(h), "hien ngay tu gui");
  ok(!!d.querySelector('[data-act="submitdraft"]') && !!d.querySelector('[data-act="claim"]') && !!d.querySelector('[data-act="dropdraft"]'), "nut nhap C&B");
  ok(!!d.querySelector('textarea[data-model="ghi_chu_cnb"]'), "o ghi chu C&B");
  d.querySelector('[data-act="submitdraft"]').click(); await flush();
  const names = w.__calls.map((x) => x[0]);
  ok(names.indexOf("nhan_nhap") >= 0 && names.indexOf("save_draft") > names.indexOf("nhan_nhap")
     && names.indexOf("submit_request") > names.indexOf("save_draft"), "nhan nhap -> luu -> gui"); }

// 5. CEO: LM = CEO -> nhap phan LM tai cap CEO, khong co nut Tra lai quan ly.
{ const w = boot(URL, det((x) => { x.approval.current_level = 3; const g = x.extra.danh_gia; g.cap_cua_toi = 3; g.lm_nhap_o_cap_ceo = 1; })); await flush();
  const d = w.document;
  ok(!!d.querySelector('[data-act="lmsave"]') && !!d.querySelector('[data-act="approve"]'), "CEO luu phan LM + duyet");
  ok(!d.querySelector('[data-act="back"]'), "khong tra lai chinh minh"); }

// 6. Sau CEO: C&B xac nhan cap nhat ho so.
{ const w = boot(URL, det((x) => { x.approval = { name: "AR", approval_status: "Approved", current_level: 0 }; const g = x.extra.danh_gia; g.cap_cua_toi = 0; g.la_cnb = 1;
    g.ho_so = { trang_thai: "Chờ C&B xác nhận", co_the_xac_nhan: 1, de_xuat: { kieu: "them_dong", employment_type: "Full-time",
      dong_moi: { loai_hop_dong: "HĐLĐ lần 1", tu_ngay: "2027-01-01", den_ngay: "2027-12-31", khong_thoi_han: 0 }, ghi_chu: "Thêm HĐLĐ lần 1" } };
    x.business.lm_ket_qua = "Đạt"; x.business.lm_nhan_xet = "Tốt"; })); await flush();
  const d = w.document;
  ok(d.getElementById("hs-tu").value === "2027-01-01" && d.getElementById("hs-den").value === "2027-12-31", "de xuat dien san ngay");
  d.querySelector('[data-act="hoso"]').click(); await flush();
  d.querySelector(".ec-er-overlay [data-ok]").click(); await flush();
  const c = w.__calls.find((x) => x[0] === "xac_nhan_ho_so");
  ok(!!c && JSON.parse(c[1].payload).tu_ngay === "2027-01-01", "goi xac_nhan_ho_so"); }

// 7. Hang cho C&B.
{ const [qm, qjs] = split("hr/pages/danh_gia_nhan_su/main_section.html");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + qm + "</body></html>", { runScripts: "outside-only", url: "https://x.test/ec-hr/danh-gia-nhan-su" });
  const w = dom.window; w.__calls = [];
  w.frappe = { call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args, o.type]);
    if (m === "hang_cho") return Promise.resolve({ message: { nhap: [{ name: "EV1", ten_nhan_vien: "A <i>x</i>", review_type: "Thử việc", hd_den_ngay: "2026-12-31", auto_submit_on: "2026-12-17", requested_by: "cnb@x" }],
      thieu_du_lieu: [{ nhan_vien: "E2", ten: "B", loai: "Thử việc", den_ngay: "2026-12-20", ly_do: "Không có Line Manager" }],
      thieu_ngay: [{ nhan_vien: "E3", ten: "C", employment_type: "Probation", ngay_vao: "2026-11-02", ly_do: "Chưa có dòng hợp đồng hiện hành", goi_y_den_ngay: "2027-01-01" }],
      cho_ho_so: [], dang_chay: [] } });
    return Promise.resolve({ message: { name: "EV1" } }); } };
  w.eval(qjs); await flush();
  const d = w.document;
  ok(w.__calls[0][0] === "hang_cho" && w.__calls[0][2] === "GET", "tai hang cho bang GET");
  ok(/Nháp chờ gửi \(1\)/.test(d.getElementById("er-tabs").innerHTML) && /Thiếu ngày kết thúc \(1\)/.test(d.getElementById("er-tabs").innerHTML), "dem tung tab");
  ok(!d.querySelector("#er-body i"), "escape ten");
  d.querySelector('[data-tab="thieu_ngay"]').click();
  ok(/01\/01\/2027/.test(d.getElementById("er-body").innerHTML), "goi y ngay ket thuc thu viec");
  d.querySelector('[data-tab="thieu_du_lieu"]').click();
  ok(/Không có Line Manager/.test(d.getElementById("er-body").innerHTML), "ly do khong tao duoc phieu"); }

// 8. Trang ket qua khao sat moc (asset surveys).
{ const html = readFileSync(join(APP, "surveys", "pages", "ca_nhan", "main_section.html"), "utf8");
  ok(!/<script(?![^>]*\bsrc=)/.test(html) && !/<style/.test(html), "trang khao sat khong co khoi inline (A65)");
  const dom = new JSDOM("<!DOCTYPE html><html><body><div id=\"svy-root\" data-page=\"ca_nhan\"></div></body></html>", { runScripts: "outside-only", url: "https://x.test/khao-sat/ca-nhan" });
  const w = dom.window;
  w.ECSvy = { esc: (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" })[c]),
    byId: (i) => w.document.getElementById(i), param: (n) => new w.URLSearchParams(w.location.search).get(n) || "", fmtDate: (s) => s, fmtDt: (s) => s, friendly: () => "x",
    api: (m) => Promise.resolve(m === "ca_nhan_danh_sach" ? { rows: [{ name: "A1", title: "KS mốc 1", user_name: "NV <b>", assigned_on: "2026-11-09", due_date: "2026-11-12", trang_thai: "Đã nộp", quyen: "lm" }] }
      : { title: "KS", user_name: "NV", submitted: true, so_cau_an: 1, answers: [{ title: "Q1", value: "4" }] }) };
  w.eval(readFileSync(join(APP, "public", "surveys", "ec_survey_ca_nhan.js"), "utf8")); await flush();
  const h = w.document.getElementById("svy-root").innerHTML;
  ok(/KS mốc 1/.test(h) && /Quản lý trực tiếp/.test(h) && !/<b>/.test(h.replace(/<b>[^<]*<\/b>/g, "")), "danh sach + quyen + escape");
  w.document.querySelector("[data-open]").click(); await flush();
  ok(/1 câu thuộc nhóm/.test(w.document.getElementById("svy-root").innerHTML), "chi tiet bao so cau bi an"); }

console.log(`${oks} dat, ${fails} hong`);
process.exit(fails ? 1 : 0);
