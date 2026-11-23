// Copyright (c) 2026, eCentric and contributors
//
// HR v2 (23/11/2026) - Nghi viec / Offer / New Staff Preparation: chay THAT script trang tren jsdom,
// frappe.call gia. Do hanh vi: nut nao hien, bam thi API nao duoc goi voi tham so nao.
//     node ecentric_workspace/approval_center/tests/js/test_hr_v2_pages.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const FEAT = join(here, "..", "..", "features");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = () => new Promise((r) => setTimeout(r, 5));
const flushAll = async () => { for (let i = 0; i < 8; i++) await flush(); };

function page(feat, scriptId, url, handlers) {
  const html = readFileSync(join(FEAT, feat, "ui", "main_section.html"), "utf8");
  const [markup, rest] = html.split('<script id="' + scriptId + '">');
  const js = rest.replace(/<\/script>\s*$/, "");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url });
  const w = dom.window;
  w.__calls = [];
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method.split(".").pop();
    w.__calls.push([m, o.args]);
    const h = handlers[m];
    if (h) { try { const v = h(o.args); return Promise.resolve({ message: v }); } catch (e) { return Promise.reject(e); } }
    return Promise.resolve({ message: { rows: [], total: 0 } });
  } };
  w.confirm = () => true;
  w.eval(js);
  return w;
}
const called = (w, m) => w.__calls.filter((c) => c[0] === m);
const BOOT = (tabs) => ({ tabs: Object.assign({ create: true, my_requests: true, my_approvals: true }, tabs || {}),
  context: { user: "a@ec.vn", employee_name: "A", department: "Ops" },
  form_options: { resignation_for: ["Myself"], resignation_reasons: ["Personal"], ratings: [], recommend_options: [] } });
const SRC = readFileSync(join(FEAT, "resignation", "ui", "main_section.html"), "utf8");

// ============================== NGHI VIEC ==============================
ok(!/data-act="reject"/.test(SRC) && !/data-quick="reject"/.test(SRC), "resn: nguon trang khong con nut Tu choi");
function resnDetail(over, extra) {
  return Object.assign({
    business: { name: "EC-RESN-2026-00010", request_title: "t", resignation_for: "Myself", employee_email: "a@ec.vn",
      personal_email: "a@gmail.com", last_working_day: "2026-12-10", resignation_reason: "Personal",
      earliest_valid_last_day: "2026-12-23", requested_by: "a@ec.vn", fulfillment_status: "Not Started",
      workplace_environment_rating: null, survey_hidden: 1 },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Quản lý trực tiếp", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "CnB/HR xác nhận", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "lm@x", status: "Pending" }], attachments: [], timeline: [],
    fulfillment: { status: "Not Started" },
    extra: Object.assign({ can_withdraw: true, early_leave_requested: 1, earliest_valid_last_day: "2026-12-23",
      notice_rule: "HĐ xác định thời hạn 12–36 tháng: báo trước ít nhất 30 ngày (Điều 35.1.b)" }, extra || {}),
    capabilities: { can_approve: true, can_reject: true, can_request_information: true, can_cancel: true } }, over || {});
}
{
  const w = page("resignation", "ec-resignation", "https://x.test/approvals/resignation?id=EC-RESN-2026-00010",
    { get_bootstrap: () => BOOT(), get_detail: () => resnDetail(),
      withdraw: (a) => ({ withdrawn: true, detail: resnDetail({}, { can_withdraw: false, withdrawn_at: "2026-11-23 10:00:00", withdrawal_reason: a.reason }) }) });
  await flushAll();
  const d = w.document, html = d.getElementById("resn-body").innerHTML;
  ok(!d.querySelector('[data-act="reject"]'), "resn: chi tiet KHONG co nut Tu choi du capabilities.can_reject=true");
  ok(/Trả lại điều chỉnh/.test(html) && !!d.querySelector('[data-act="reqinfo"]'), "resn: nut Tra lai dieu chinh");
  ok(!!d.querySelector('[data-act="withdraw"]'), "resn: nut Rut don");
  ok(!d.querySelector('[data-act="cancel"]'), "resn: co Rut don thi an Huy yeu cau (mot nut)");
  ok(/Xin nghỉ sớm hơn hạn báo trước/.test(html) && /23\/12\/2026/.test(html), "resn: bang xin nghi som + ngay som nhat");
  ok(/chỉ người nghỉ việc và nhóm HR xem được/.test(html) && !/Môi trường làm việc/.test(html), "resn: danh gia cu bi an voi LM");
  ok(/Bàn giao \(Clearance\)/.test(d.getElementById("d-stepper").innerHTML), "resn: tien trinh co buoc Clearance");
  ok(!/HR xử lý/.test(d.getElementById("d-stepper").innerHTML), "resn: don V2 khong con buoc HR xu ly");
  d.querySelector('[data-act="withdraw"]').click(); await flushAll();
  const okb = d.querySelector(".ec-resn-overlay [data-ok]");
  okb.click(); await flushAll();
  ok(called(w, "withdraw").length === 0, "resn: rut don khong ly do -> khong goi API");
  d.querySelector(".ec-resn-overlay #m-cmt").value = "Đổi ý";
  d.querySelector(".ec-resn-overlay [data-ok]").click(); await flushAll();
  const c = called(w, "withdraw");
  ok(c.length === 1 && c[0][1].reason === "Đổi ý" && c[0][1].name === "EC-RESN-2026-00010", "resn: rut don goi API dung tham so");
  ok(/Đơn đã được rút/.test(d.getElementById("resn-body").innerHTML), "resn: sau rut don hien bang da rut");
}
{ // don cu (V1) da vao hang doi HR + nguoi xem la HR: thay danh gia + buoc HR xu ly
  const w = page("resignation", "ec-resignation", "https://x.test/approvals/resignation?id=EC-RESN-2026-00003",
    { get_bootstrap: () => BOOT(), get_detail: () => resnDetail({
        business: { name: "EC-RESN-2026-00003", employee_email: "a@ec.vn", last_working_day: "2026-09-22",
          workplace_environment_rating: "4 (Satisfied)", final_message: "cảm ơn", fulfillment_status: "Completed" },
        approval: { name: "AR-3", approval_status: "Approved", current_level: 0 },
        fulfillment: { status: "Completed", summary: "ok" }, capabilities: {} }, { can_withdraw: false, early_leave_requested: 0, notice_rule: null }) });
  await flushAll();
  const d = w.document, html = d.getElementById("resn-body").innerHTML;
  ok(/Môi trường làm việc/.test(html) && /cảm ơn/.test(html), "resn cu: HR van thay danh gia");
  ok(/HR xử lý/.test(d.getElementById("d-stepper").innerHTML) && /Xử lý HR \(đơn cũ\)/.test(html), "resn cu: con buoc HR xu ly");
  ok(!d.querySelector('[data-act="withdraw"]'), "resn cu: khong co Rut don");
}
{ // tao don: khong con the Danh gia; ngay som nhat tu may chu; ngay qua khu bi chan
  const w = page("resignation", "ec-resignation", "https://x.test/approvals/resignation?tab=create",
    { get_bootstrap: () => BOOT(), get_notice_info: (a) => ({ known: true, earliest: "2026-12-23", rule: "báo trước 30 ngày" }),
      save_draft: () => ({ name: "EC-RESN-2026-00011" }), submit_request: () => ({}) , get_detail: () => resnDetail() });
  await flushAll();
  const d = w.document;
  ok(!d.querySelector('[data-model="workplace_environment_rating"]') && !d.querySelector('[data-model="final_message"]'), "resn tao: khong hoi danh gia tren don");
  ok(/Khảo sát nghỉ việc được gửi riêng/.test(d.getElementById("resn-body").innerHTML), "resn tao: bao khao sat gui rieng");
  const set = (k, v) => { const el = d.querySelector('[data-model="' + k + '"]'); el.value = v; el.dispatchEvent(new w.Event("input", { bubbles: true })); };
  set("employee_email", "a@ec.vn"); await flushAll();
  ok(called(w, "get_notice_info").length >= 1 && called(w, "get_notice_info")[0][1].employee_email === "a@ec.vn", "resn tao: hoi ngay som nhat theo email");
  set("last_working_day", "2026-12-01"); await flushAll();
  ok(/Sớm hơn hạn báo trước/.test(d.getElementById("resn-notice").innerHTML) && /23\/12\/2026/.test(d.getElementById("resn-notice").innerHTML), "resn tao: canh bao som hon han");
  set("last_working_day", "2026-12-30"); await flushAll();
  ok(!/Sớm hơn hạn/.test(d.getElementById("resn-notice").innerHTML), "resn tao: du han -> khong canh bao");
  set("request_title", "t"); set("resignation_for", "Myself"); set("personal_email", "a@gmail.com"); set("resignation_reason", "Personal");
  set("last_working_day", "2020-01-01");
  d.getElementById("resn-submit").click(); await flushAll();
  ok(called(w, "save_draft").length === 0 && d.querySelector('[data-fld="last_working_day"]').classList.contains("invalid"), "resn tao: ngay qua khu -> chan");
  set("last_working_day", "2099-12-30");
  d.getElementById("resn-submit").click(); await flushAll();
  ok(called(w, "save_draft").length === 1 && called(w, "submit_request").length === 1, "resn tao: khong can danh gia van gui duoc");
}

// ============================== OFFER ==============================
function offerDetail(over) {
  return Object.assign({
    business: { name: "EC-OFFR-2026-00002", candidate_name: "B", requested_by: "ta@x", compensation: "x",
      offered_salary: 15000000, new_staff_preparation: "EC-NSP-2026-00002" },
    approval: { name: "AR-8", approval_status: "Approved", current_level: 0 },
    levels: [], approvers: [], attachments: [], timeline: [],
    extra: { new_staff_preparation: "EC-NSP-2026-00002", nsp_route: "/x", can_mark_candidate: true,
             hof_rule_note: "Lương offer 15.000.000 ≤ mức đã duyệt trên Hiring 20.000.000 - bỏ cấp HOF" },
    capabilities: {} }, over || {});
}
{
  const w = page("offer_request", "ec-offer-request", "https://x.test/approvals/offer-request?id=EC-OFFR-2026-00002",
    { get_bootstrap: () => BOOT(), get_detail: () => offerDetail(), mark_candidate_status: () => ({ candidate_status: "Declined" }) });
  await flushAll();
  const d = w.document, html = d.getElementById("offr-body").innerHTML;
  ok(/bỏ cấp HOF/.test(html), "offer: hien can cu HOF");
  ok(!!d.querySelector('[data-act="declined"]') && !!d.querySelector('[data-act="offercancel"]'), "offer: nut Ung vien tu choi + Huy offer");
  d.querySelector('[data-act="declined"]').click(); await flushAll();
  d.querySelector(".ec-offr-overlay #m-cmt").value = "Nhận nơi khác";
  d.querySelector(".ec-offr-overlay [data-ok]").click(); await flushAll();
  const c = called(w, "mark_candidate_status");
  ok(c.length === 1 && c[0][1].kind === "Declined" && c[0][1].reason === "Nhận nơi khác", "offer: ghi nhan tu choi dung tham so");
}
{
  const w = page("offer_request", "ec-offer-request", "https://x.test/approvals/offer-request?id=EC-OFFR-2026-00002",
    { get_bootstrap: () => BOOT(), get_detail: () => offerDetail({ business: { name: "EC-OFFR-2026-00002", candidate_status: "Declined",
      candidate_status_reason: "Nhận nơi khác" }, extra: { can_mark_candidate: false } }) });
  await flushAll();
  const html = w.document.getElementById("offr-body").innerHTML;
  ok(/Ứng viên từ chối offer/.test(html) && !w.document.querySelector('[data-act="declined"]'), "offer: da ghi nhan -> bang + an nut");
  ok(!/Tạo lại New Staff Preparation/.test(html), "offer: ung vien tu choi -> khong moi tao lai NSP");
}
{
  const src = readFileSync(join(FEAT, "offer_request", "ui", "main_section.html"), "utf8");
  const tag = (src.match(/<input[^>]*data-model="offered_salary"[^>]*>/) || [""])[0];
  ok(/data-money/.test(tag) && !/type="number"/.test(tag), "offer: o luong offer la o tien data-money");
}

// ============================== NSP ==============================
function nspDetail(extra) {
  return { business: { name: "EC-NSP-2026-00002", candidate_name: "B", offer_request: "EC-OFFR-2026-00002", onboard_date: "2026-12-01" },
    approval: { name: "AR-9", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Chuẩn bị onboard", approval_mode: "Each Group", level_status: "In Progress" }],
    approvers: [], attachments: [], timeline: [],
    extra: Object.assign({ greeting: "", groups: [], can_pick_employee: true }, extra || {}), capabilities: {} };
}
{
  const w = page("new_staff_preparation", "ec-new-staff-preparation", "https://x.test/approvals/new-staff-preparation?id=EC-NSP-2026-00002",
    { get_bootstrap: () => BOOT({ create: false }), get_detail: () => nspDetail(),
      suggest_employees: () => [{ name: "HR-EMP-9", employee_name: "B", date_of_joining: "2026-12-01" }],
      pick_employee: () => ({ new_employee: "HR-EMP-9" }) });
  await flushAll();
  const d = w.document;
  ok(/Hồ sơ nhân viên/.test(d.getElementById("nsp-body").innerHTML) && !!d.querySelector('[data-act="pickemployee"]'), "nsp: nhom HR thay nut chon ho so");
  d.querySelector('[data-act="pickemployee"]').click(); await flushAll();
  ok(called(w, "suggest_employees").length === 1, "nsp: nap goi y ho so");
  const sel = d.querySelector(".ec-nsp-overlay #m-emp-sel"); sel.value = "HR-EMP-9";
  d.querySelector(".ec-nsp-overlay [data-ok]").click(); await flushAll();
  const c = called(w, "pick_employee");
  ok(c.length === 1 && c[0][1].employee === "HR-EMP-9", "nsp: chon ho so goi API dung ma");
}
{
  const w = page("new_staff_preparation", "ec-new-staff-preparation", "https://x.test/approvals/new-staff-preparation?id=EC-NSP-2026-00002",
    { get_bootstrap: () => BOOT({ create: false }), get_detail: () => nspDetail({ can_pick_employee: false }) });
  await flushAll();
  ok(!w.document.querySelector('[data-act="pickemployee"]'), "nsp: nguoi ngoai nhom HR khong thay nut chon ho so");
}

console.log("HR v2 pages: " + oks + " dat, " + fails + " hong");
process.exit(fails ? 1 : 0);
