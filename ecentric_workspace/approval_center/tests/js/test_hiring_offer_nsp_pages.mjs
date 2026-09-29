// Copyright (c) 2026, eCentric and contributors
//
// Chuoi tuyen dung 28/09/2026 - chay THAT script cua 3 trang (Hiring / Offer / New Staff
// Preparation) va popup trang chu tren jsdom, frappe.call gia. Do HANH VI (bam roi xem man hinh
// / API duoc goi voi tham so nao), khong chi "co ve nut khong".
//     node ecentric_workspace/approval_center/tests/js/test_hiring_offer_nsp_pages.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const FEAT = join(here, "..", "..", "features");
const PUB = join(here, "..", "..", "..", "public", "js");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = () => new Promise((r) => setTimeout(r, 5));
const flushAll = async () => { for (let i = 0; i < 6; i++) await flush(); };

function page(feat, scriptId, url, handlers) {
  const html = readFileSync(join(FEAT, feat, "ui", "main_section.html"), "utf8");
  const [markup, rest] = html.split('<script id="' + scriptId + '">');
  const js = rest.replace(/<\/script>\s*$/, "");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>",
    { runScripts: "outside-only", url });
  const w = dom.window;
  w.__calls = [];
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method.split(".").pop();
    w.__calls.push([m, o.args]);
    const h = handlers[m];
    if (h) { try { const v = h(o.args); return v && v.then ? v.then((x) => ({ message: x })) : Promise.resolve({ message: v }); } catch (e) { return Promise.reject(e); } }
    return Promise.resolve({ message: { rows: [], total: 0 } });
  } };
  w.confirm = () => true;
  w.eval(js);
  return w;
}
const called = (w, m) => w.__calls.filter((c) => c[0] === m);

// ============================== OFFER ==============================
const BOOT = (tabs) => ({ tabs: Object.assign({ create: true, my_requests: true, my_approvals: true, all: true }, tabs || {}),
  context: { user: "rec@x", employee_name: "Rec" }, form_options: {} });
const PREFILL = { hiring_request: "EC-HIRE-2026-00009", hiring_title: "Hiring - Data Intern", position: "Data Intern",
  employment_type: "Intern", line_manager: "lm@x", department: "Operation - EC", number_of_vacancy: 2, offered: 2 };
function offerDetail(over) {
  return Object.assign({
    business: { name: "EC-OFFR-2026-00001", request_title: "Offer - A - Data Intern - Operation - EC", candidate_name: "A",
      position: "Data Intern", department: "Operation - EC", employment_type: "Intern", line_manager: "lm@x",
      onboard_date: "2026-10-10", probation_end_date: "2027-01-10", mobile_phone: "0900", company_laptop: 1,
      compensation: "15.000.000 <b>VND</b>", note: "", resume: "/private/files/cv.pdf", requested_by: "rec@x",
      hiring_request: "EC-HIRE-2026-00009" },
    approval: { name: "AR-1", approval_status: "Approved", current_level: 0 },
    levels: [], approvers: [], attachments: [], timeline: [],
    extra: { hiring: { name: "EC-HIRE-2026-00009", request_title: "Hiring", route: "/approvals/hiring-request?id=EC-HIRE-2026-00009" },
             new_staff_preparation: null, can_retry_nsp: true },
    capabilities: {} }, over || {});
}

{
  const w = page("offer_request", "ec-offer-request", "https://x.test/approvals/offer-request", { get_bootstrap: () => BOOT() });
  await flushAll();
  const body = w.document.getElementById("offr-body").innerHTML;
  ok(/Offer được tạo từ Hiring Request/.test(body), "offer: vao tab tao khong co ?hiring -> chi duong, khong ve form");
  ok(!w.document.querySelector('[data-model="candidate_name"]'), "offer: khong co o nhap khi thieu hiring");
  ok(called(w, "hiring_prefill").length === 0, "offer: khong goi prefill khi thieu hiring");
}
{
  const w = page("offer_request", "ec-offer-request", "https://x.test/approvals/offer-request?hiring=EC-HIRE-2026-00009",
    { get_bootstrap: () => BOOT(), hiring_prefill: () => PREFILL,
      save_draft: (a) => ({ name: "EC-OFFR-2026-00001", capabilities: {} }), submit_request: () => ({ submitted: true }),
      get_detail: () => offerDetail({ approval: { name: "AR-1", approval_status: "Pending", current_level: 1 } }) });
  await flushAll();
  const d = w.document;
  ok(called(w, "hiring_prefill").length === 1 && called(w, "hiring_prefill")[0][1].hiring === "EC-HIRE-2026-00009",
     "offer: goi hiring_prefill dung ma Hiring");
  ok(/Data Intern/.test(d.getElementById("offr-body").innerHTML) && /lm@x/.test(d.getElementById("offr-body").innerHTML),
     "offer: hien vi tri + line manager tu Hiring");
  ok(!d.querySelector('[data-model="position"]') && !d.querySelector('[data-model="line_manager"]'),
     "offer: vi tri / line manager KHONG phai o nhap (khong chon duoc nguoi duyet)");
  ok(d.querySelector('[data-model="hiring_request"]').value === "EC-HIRE-2026-00009", "offer: hiring_request gan an trong form");
  ok(/đã offer đủ/.test(d.getElementById("offr-body").innerHTML), "offer: canh bao da offer du N vi tri");
  // bam Gui khi trong -> loi tai o, khong goi API
  d.getElementById("offr-submit").click(); await flushAll();
  ok(called(w, "save_draft").length === 0, "offer: thieu truong -> khong luu");
  ok(d.querySelector('[data-fld="compensation"]').classList.contains("invalid") &&
     d.querySelector('[data-fld="resume"]').classList.contains("invalid"), "offer: bao loi o luong + CV");
  const set = (k, v) => { const el = d.querySelector('[data-model="' + k + '"]'); el.value = v; el.dispatchEvent(new w.Event("input", { bubbles: true })); };
  set("candidate_name", "Nguyen Van A"); set("mobile_phone", "0900"); set("onboard_date", "2026-10-10");
  set("probation_end_date", "2026-10-01"); set("compensation", "15tr");
  const hv = d.querySelector('[data-model="resume"]'); hv.value = "/private/files/cv.pdf";
  w.OfferRequest.state.draft.resume = "/private/files/cv.pdf";
  const cb = d.querySelector('[data-model="company_laptop"]'); cb.checked = true; cb.dispatchEvent(new w.Event("change", { bubbles: true }));
  ok(w.OfferRequest.state.draft.company_laptop === 1, "offer: tick laptop -> 1");
  ok(/^Offer - Nguyen Van A - Data Intern - Operation - EC$/.test(w.OfferRequest.state.draft.request_title), "offer: tu goi y tieu de");
  d.getElementById("offr-submit").click(); await flushAll();
  ok(called(w, "save_draft").length === 0 && d.querySelector('[data-fld="probation_end_date"]').classList.contains("invalid"),
     "offer: het thu viec truoc onboard -> chan");
  set("probation_end_date", "2027-01-10");
  d.getElementById("offr-submit").click(); await flushAll();
  const sv = called(w, "save_draft");
  ok(sv.length === 1, "offer: du truong -> luu");
  const payload = sv.length ? JSON.parse(sv[0][1].payload) : {};
  ok(payload.hiring_request === "EC-HIRE-2026-00009" && payload.compensation === "15tr" && payload.company_laptop === 1,
     "offer: payload mang dung du lieu");
  ok(!("position" in payload) || payload.position === undefined, "offer: payload khong tu dat vi tri");
  ok(called(w, "submit_request").length === 1, "offer: gui sau khi luu");
}
{
  const w = page("offer_request", "ec-offer-request", "https://x.test/approvals/offer-request?id=EC-OFFR-2026-00001",
    { get_bootstrap: () => BOOT(), get_detail: () => offerDetail(), retry_new_staff_preparation: () => ({ new_staff_preparation: "EC-NSP-2026-00001" }) });
  await flushAll();
  const html = w.document.getElementById("offr-body").innerHTML;
  ok(/15\.000\.000 &lt;b&gt;VND&lt;\/b&gt;/.test(html), "offer: chi tiet hien luong (da escape)");
  ok(/Tạo lại New Staff Preparation/.test(html), "offer: da duyet ma chua co NSP -> nut tao lai");
  w.document.querySelector('[data-act="retrynsp"]').click(); await flushAll();
  ok(called(w, "retry_new_staff_preparation").length === 1, "offer: bam tao lai -> goi API");
}

// ============================== NEW STAFF PREPARATION ==============================
function nspDetail(over) {
  return Object.assign({
    business: { name: "EC-NSP-2026-00001", request_title: "New Staff Preparation - A - Data Intern - Operation", candidate_name: "Nguyen Van A",
      position: "Data Intern", department: "Operation - EC", line_manager: "lm@x", onboard_date: "2026-10-10",
      probation_end_date: "2027-01-10", mobile_phone: "0900", company_laptop: 1, note: "", welcome_intro: "Em <i>chào</i>",
      offer_request: "EC-OFFR-2026-00001", requested_by: "rec@x" },
    approval: { name: "AR-9", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Chuẩn bị onboard", approval_mode: "Each Group", level_status: "In Progress" }],
    approvers: [], attachments: [], timeline: [],
    extra: { greeting: "Dear all, we're going to welcome...", department_label: "Operation", offer_route: "/approvals/offer-request?id=EC-OFFR-2026-00001",
             can_edit_welcome: true,
             groups: [{ group: "Lead HR", done: true, by: "tuan@x", at: "2026-10-01 10:00", note: "ok", members: ["tuan@x"] },
                      { group: "Operation", done: false, by: null, at: null, note: null, members: ["dong@x"] }] },
    capabilities: { can_approve: true, can_reject: false, can_request_information: true } }, over || {});
}
{
  const w = page("new_staff_preparation", "ec-new-staff-preparation", "https://x.test/approvals/new-staff-preparation",
    { get_bootstrap: () => BOOT({ create: false }), list_need_my_approval: () => ({ rows: [] }) });
  await flushAll();
  const tabs = [...w.document.querySelectorAll(".tab")].map((t) => t.getAttribute("data-tab"));
  ok(!tabs.includes("create"), "nsp: khong co tab tao yeu cau");
  ok(w.NewStaffPreparation.state.tab === "my-approvals", "nsp: mac dinh vao Cho toi xu ly");
  ok(called(w, "list_need_my_approval").length >= 1, "nsp: nap danh sach cho toi xu ly");
}
{
  const w = page("new_staff_preparation", "ec-new-staff-preparation", "https://x.test/approvals/new-staff-preparation?id=EC-NSP-2026-00001",
    { get_bootstrap: () => BOOT({ create: false }), get_detail: () => nspDetail(), approve: (a) => ({ detail: nspDetail() }),
      update_welcome: () => ({ ok: true }) });
  await flushAll();
  const d = w.document, html = d.getElementById("nsp-body").innerHTML;
  ok(/Lead HR/.test(html) && /Đã chuẩn bị/.test(html) && /Operation/.test(html) && /Đang chuẩn bị/.test(html), "nsp: checklist tung nhom");
  ok(/Em &lt;i&gt;chào&lt;\/i&gt;/.test(html), "nsp: loi gioi thieu hien va da escape");
  ok(/NGUYEN VAN A/.test(html), "nsp: ten in hoa trong thiep xem truoc");
  ok(!!d.querySelector('[data-act="approve"]') && /Đã chuẩn bị xong/.test(d.querySelector('[data-act="approve"]').textContent), "nsp: nut Da chuan bi xong");
  ok(!d.querySelector('[data-act="reject"]'), "nsp: KHONG co nut Tu choi");
  ok(!/compensation|Mức lương/.test(html), "nsp: khong co gi ve luong");
  d.querySelector('[data-act="approve"]').click(); await flushAll();
  const ok1 = d.querySelector(".ec-nsp-overlay [data-ok]");
  ok(!!ok1, "nsp: bam -> hop xac nhan");
  if (ok1) { ok1.click(); await flushAll(); }
  ok(called(w, "approve").length === 1 && called(w, "approve")[0][1].name === "EC-NSP-2026-00001", "nsp: xac nhan -> goi approve");
  d.querySelector('[data-act="editwelcome"]').click(); await flushAll();
  const ov = d.querySelector(".ec-nsp-overlay");
  ov.querySelector("#m-intro").value = "Xin chao"; ov.querySelector("#m-date").value = "2026-10-12";
  ov.querySelector("[data-ok]").click(); await flushAll();
  const uw = called(w, "update_welcome");
  ok(uw.length === 1 && uw[0][1].welcome_intro === "Xin chao" && uw[0][1].onboard_date === "2026-10-12", "nsp: sua loi gioi thieu + ngay -> update_welcome");
}

// ============================== HIRING ==============================
function hireDetail(over) {
  return Object.assign({
    business: { name: "EC-HIRE-2026-00009", request_title: "Hiring - Data Intern", position: "Data Intern", number_of_vacancy: 2,
      department: "Operation - EC", requested_by: "mgr@x", fulfillment_status: "In Progress", fulfillment_owner: "rec@x" },
    approval: { name: "AR-5", approval_status: "Approved", current_level: 0 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review", level_status: "Approved" }], approvers: [], attachments: [], timeline: [],
    extra: { offers: [{ name: "EC-OFFR-2026-00001", candidate_name: "A", onboard_date: "2026-10-10", approval_status: "Approved" }],
             vacancy: 2, offered: 1, can_create_offer: true, offer_route: "/approvals/offer-request?hiring=EC-HIRE-2026-00009" },
    capabilities: { can_complete: true } }, over || {});
}
{
  const w = page("hiring_request", "ec-hiring-request", "https://x.test/approvals/hiring-request?id=EC-HIRE-2026-00009",
    { get_bootstrap: () => BOOT({ fulfillment: true }), get_detail: () => hireDetail(), complete_fulfillment: () => ({ completed: true, detail: hireDetail() }) });
  await flushAll();
  const d = w.document, html = d.getElementById("hire-body").innerHTML;
  const link = [...d.querySelectorAll("a")].find((a) => /Tạo Offer/.test(a.textContent));
  ok(!!link && link.getAttribute("href") === "/approvals/offer-request?hiring=EC-HIRE-2026-00009", "hiring: nut Tao Offer tro dung ?hiring=");
  ok(/1\/2 vị trí/.test(html) && /EC-OFFR-2026-00001/.test(html), "hiring: dem da offer x/N + bang offer");
  ok(/HR tuyển dụng/.test(d.getElementById("d-stepper").innerHTML), "hiring: stepper co buoc HR tuyen dung");
  const tabs = [...d.querySelectorAll(".tab")].map((t) => t.getAttribute("data-tab"));
  ok(tabs.includes("fulfillment"), "hiring: tab Toi xu ly cho EC Recruiter");
  d.querySelector('[data-act="complete"]').click(); await flushAll();
  const ov = d.querySelector(".ec-hire-overlay");
  ov.querySelector("[data-ok]").click(); await flushAll();
  ok(called(w, "complete_fulfillment").length === 0, "hiring: hoan tat khong ghi chu -> khong goi");
  ov.querySelector("#m-cmt").value = "Du 2/2"; ov.querySelector("[data-ok]").click(); await flushAll();
  const cf = called(w, "complete_fulfillment");
  ok(cf.length === 1 && JSON.parse(cf[0][1].payload).fulfillment_summary === "Du 2/2", "hiring: hoan tat co ghi chu -> goi API");
}
{
  const w = page("hiring_request", "ec-hiring-request", "https://x.test/approvals/hiring-request?id=EC-HIRE-2026-00009",
    { get_bootstrap: () => BOOT(), get_detail: () => hireDetail({ extra: { offers: [], vacancy: 2, offered: 0, can_create_offer: false,
      offer_route: "/approvals/offer-request?hiring=EC-HIRE-2026-00009" },
      capabilities: {} }) });
  await flushAll();
  ok(![...w.document.querySelectorAll("a")].some((a) => /Tạo Offer/.test(a.textContent)), "hiring: khong phai nguoi tuyen -> khong co Tao Offer");
}

// ============================== POPUP TRANG CHU ==============================
async function popup(rows, seen) {
  const dom = new JSDOM("<!DOCTYPE html><html><head></head><body><button id='b'>x</button></body></html>",
    { runScripts: "outside-only", url: "https://x.test/home" });
  const w = dom.window;
  if (seen) w.localStorage.setItem("ec_welcome_seen_" + seen, "1");
  w.__fetch = 0;
  w.fetch = async () => { w.__fetch++; return { ok: true, json: async () => ({ message: { rows } }) }; };
  w.eval(readFileSync(join(PUB, "ec_welcome_popup.js"), "utf8"));
  await flushAll();
  return w;
}
{
  const rows = [{ name: "NSP-1", candidate_name: "Nguyen <b>A</b>", position: "Intern", department: "Service", welcome_intro: "Hi <script>x</script>" }];
  const w = await popup(rows);
  const ov = w.document.getElementById("ec-welcome-popup");
  ok(!!ov && ov.getAttribute("role") === "dialog", "popup: hien khi co nhan vien moi");
  ok(ov && /NGUYEN &LT;B&GT;A&LT;\/B&GT;|NGUYEN &lt;B&gt;A&lt;\/B&gt;/.test(ov.innerHTML) && !ov.querySelector("script"), "popup: escape ten + loi gioi thieu");
  ov.querySelector("[data-ecw-close]").click();
  ok(!w.document.getElementById("ec-welcome-popup"), "popup: bam dong -> tat");
  ok(w.localStorage.getItem("ec_welcome_seen_NSP-1") === "1", "popup: nho da xem");
  const w2 = await popup(rows, "NSP-1");
  ok(!w2.document.getElementById("ec-welcome-popup"), "popup: da xem roi -> khong hien lai");
  const w3 = await popup([]);
  ok(!w3.document.getElementById("ec-welcome-popup") && w3.__fetch === 1, "popup: khong co ai -> khong hien");
  const w4 = await popup(rows);
  w4.document.dispatchEvent(new w4.KeyboardEvent("keydown", { key: "Escape" }));
  ok(!w4.document.getElementById("ec-welcome-popup"), "popup: Esc -> tat");
}

console.log(`${oks} dat, ${fails} hong`);
process.exit(fails ? 1 : 0);
