// Promotion "huong 2" (27/11/2026, Hoan chot): Lead de xuat cho cap duoi KHONG thay / KHONG nhap luong;
// nguoi duyet dau tien co quyen xem luong dien luong trong khoi Hanh dong / hop Duyet truoc khi duyet.
//   node ecentric_workspace/approval_center/tests/frontend/test_promotion_lead_salary.mjs
import { JSDOM } from "jsdom";
import { pageSource } from "./_page_source.mjs";
import fs from "fs"; import path from "path"; import { fileURLToPath } from "url";
const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = pageSource("promotion");
const [markup, rest] = HTML.split('<script id="ec-promotion">');
const JS = rest.replace(/<\/script>\s*$/, "");
const PUB = path.join(__dir, "..", "..", "..", "public", "js");
const MONEY = fs.readFileSync(path.join(PUB, "ec_money.bundle.js"), "utf8");
const SUMMARY = fs.readFileSync(path.join(PUB, "ec_summary.bundle.js"), "utf8");
let fails = 0;
const ok = (c, n) => { console.log((c ? "  ok: " : "  FAIL: ") + n); if (!c) fails++; };
const flush = () => new Promise(r => setTimeout(r, 5));
const ROWS = [{ name: "E-X1", employee_name: "X1 cap duoi", department: "ECO", salary_visible: 0 },
              { name: "E-V", employee_name: "V xem duoc", department: "ECO", salary_visible: 1 }];
function detail(over) {
  return Object.assign({
    business: { name: "EC-PROM-2026-00009", request_title: "Promotion - X1", full_name: "X1", promoted_employee: "E-X1",
      department: "ECO", current_position: "Staff", proposed_position: "Senior", current_salary: null, proposed_salary: null,
      incentives: null, justification: "gioi", effective_date_of_promotion: "2026-12-01", requested_by: "phuong@x", salary_pending: 1 },
    approval: { name: "AR-9", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Direct Manager Review", approval_mode: "Any One", level_status: "In Progress" },
             { level_no: 2, level_name: "CnB Review", approval_mode: "Any One", level_status: "Pending" }],
    approvers: [{ level_no: 1, approver: "linh@x", status: "Pending" }], attachments: [], timeline: [],
    extra: { auto_apply: true, salary_input: { pending: true, can_fill: true, required: true } },
    capabilities: { can_approve: true, can_reject: true, can_request_information: true } }, over || {});
}
function boot(opts) {
  opts = opts || {}; const calls = []; const order = [];
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", url: "https://x.test/approvals/promotion" + (opts.q || "?tab=create") });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    const m = o.method.split(".").pop(); calls.push([m, o.args]); order.push(m);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "phuong@x", employee_name: "Phuong", employee: "E-PHUONG", department: "ECO", company: "C" }, form_options: { designations: ["Senior"] } } });
    if (m === "promotion_candidates") return Promise.resolve({ message: { rows: ROWS } });
    if (m === "promotion_employee") { const v = o.args.employee === "E-V";
      return Promise.resolve({ message: { employee: o.args.employee, full_name: v ? "V" : "X1", department: "ECO", current_position: "Staff",
        salary_visible: v ? 1 : 0, base_salary: v ? 20000000 : null, salary_from: v ? "2026-01-01" : null } }); }
    if (m === "save_draft") return Promise.resolve({ message: { name: "EC-PROM-2026-00009", capabilities: {} } });
    if (m === "get_detail") return Promise.resolve({ message: opts.detail || detail() });
    if (m === "fill_salary" || m === "approve") return Promise.resolve({ message: { saved: true, detail: detail() } });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  } };
  w.eval(MONEY); w.eval(SUMMARY); w.eval(JS);
  return { w, calls, order, last: (m) => { const c = calls.filter(x => x[0] === m); return c.length ? c[c.length - 1][1] : null; } };
}
const pick = async (w, emp) => { const sel = w.document.querySelector('select[data-model="promoted_employee"]');
  sel.value = emp; sel.dispatchEvent(new w.Event("input", { bubbles: true })); await flush(); await flush(); };

async function run() {
  // ---- 1. Lead chon cap duoi khong xem duoc luong: an o luong, ghi chu, tom tat khong dem luong
  { const { w, last } = boot(); await flush(); await flush();
    const sel = w.document.querySelector('select[data-model="promoted_employee"]');
    ok(!!sel && /X1 cap duoi/.test(sel.innerHTML) && /V xem duoc/.test(sel.innerHTML), "danh sach gom cap duoi + nguoi xem duoc luong");
    await pick(w, "E-X1");
    const body = w.document.getElementById("prom-body");
    ok(!body.querySelector('[data-model="current_salary"]') && !body.querySelector('[data-model="proposed_salary"]'), "an 2 o luong khi salary_visible=0");
    ok(!body.querySelector('[data-model="incentives"]'), "an o dai ngo (server cung khong nhan)");
    ok(/Lương do quản lý có quyền \/ C&amp;B điền khi duyệt|Lương do quản lý có quyền \/ C&B điền khi duyệt/.test(body.innerHTML), "ghi chu 'Luong do quan ly co quyen / C&B dien khi duyet'");
    const sum = w.document.getElementById("prom-summary");
    ok(!!sum && !/Lương/.test(sum.innerHTML), "tom tat A1 khong liet ke o luong");
    const st = w.EcSummary.status({ draft: w.Promotion.state.draft, hero: [], groups: [] }, w.document.querySelector(".prom-formwrap"));
    ok(!st.missing.some(m => /current_salary|proposed_salary/.test(m.field)), "tom tat khong dem 2 o luong la thieu");
    Object.assign(w.Promotion.state.draft, { request_title: "T", proposed_position: "Senior", justification: "j", effective_date_of_promotion: "2026-12-01" });
    ok(!w.Promotion.validateSubmit(), "validateSubmit qua khi khong co luong (Lead)");
    w.Promotion.state.draft.current_salary = 123; w.Promotion.state.draft.incentives = "x";
    w.document.getElementById("prom-save").click(); await flush(); await flush();
    const p = JSON.parse(last("save_draft").payload);
    ok(!("current_salary" in p) && !("proposed_salary" in p) && !("incentives" in p), "payload luu nhap khong gui luong");
    ok(!/20\.000\.000/.test(body.innerHTML), "khong lo luong tham khao"); }
  // ---- 2. Nguoi xem duoc luong: nhu cu
  { const { w } = boot(); await flush(); await flush();
    await pick(w, "E-V");
    const body = w.document.getElementById("prom-body");
    ok(!!body.querySelector('input[data-money][data-model="current_salary"]') && !!body.querySelector('[data-model="proposed_salary"]'), "salary_visible=1: van nhap luong");
    ok(!body.querySelector('[data-fld="_salary_note"]'), "khong hien ghi chu");
    Object.assign(w.Promotion.state.draft, { request_title: "T", proposed_position: "Senior", justification: "j", effective_date_of_promotion: "2026-12-01" });
    ok((w.Promotion.validateSubmit() || {}).current_salary, "salary_visible=1: van bat buoc luong"); }
  // ---- 3. Nguoi duyet co quyen: o dien luong trong khoi Hanh dong + hop Duyet
  { const { w, last, order } = boot({ q: "?id=EC-PROM-2026-00009" }); await flush(); await flush(); await flush();
    const box = w.document.getElementById("prom-salfill");
    ok(!!box && !!box.querySelector('input[data-money]#prom-fill-cur') && !!box.querySelector("#prom-fill-new"), "khoi Hanh dong co o dien luong (data-money)");
    ok(/Chờ người duyệt có quyền xem lương điền/.test(w.document.getElementById("prom-body").innerHTML), "o luong chi tiet: cho nguoi duyet dien");
    const cur = box.querySelector("#prom-fill-cur"); cur.value = "30000000"; cur.dispatchEvent(new w.Event("input", { bubbles: true }));
    ok(cur.value === "30.000.000", "dinh dang dau cham dung chung");
    box.querySelector('[data-act="fillsalary"]').click(); await flush();
    ok(!last("fill_salary"), "thieu luong de xuat -> khong goi fill_salary");
    const nw = box.querySelector("#prom-fill-new"); nw.value = "36000000"; nw.dispatchEvent(new w.Event("input", { bubbles: true }));
    box.querySelector('[data-act="fillsalary"]').click(); await flush(); await flush();
    const f = last("fill_salary");
    ok(f && f.name === "EC-PROM-2026-00009" && f.current_salary === 30000000 && f.proposed_salary === 36000000, "Luu luong -> fill_salary(so)");
    // hop Duyet khi required: co o luong, bat buoc truoc approve
    w.Promotion.doApprove("EC-PROM-2026-00009", detail());
    let ov = w.document.querySelector(".ec-prom-overlay");
    ok(!!ov.querySelector("#m-sal-cur") && !!ov.querySelector("#m-sal-new"), "hop Duyet co o luong khi required");
    ov.querySelector("#m-cmt").value = "ok"; ov.querySelector("#m-sal-cur").value = ""; ov.querySelector("#m-sal-new").value = "";
    const nApprove = order.filter(x => x === "approve").length;
    ov.querySelector("[data-ok]").click(); await flush();
    ok(order.filter(x => x === "approve").length === nApprove, "chua dien luong -> khong goi approve");
    ov = w.document.querySelector(".ec-prom-overlay");
    ov.querySelector("#m-sal-cur").value = "31.000.000"; ov.querySelector("#m-sal-new").value = "37.000.000";
    order.length = 0;
    ov.querySelector("[data-ok]").click(); await flush(); await flush(); await flush();
    ok(order.indexOf("fill_salary") >= 0 && order.indexOf("approve") > order.indexOf("fill_salary"), "dien luong roi moi approve");
    ok(last("fill_salary").proposed_salary === 37000000, "so tu hop Duyet"); }
  // ---- 4. Lead mo chi tiet: khong o dien, khong so
  { const d = detail({ business: Object.assign(detail().business, { salary_hidden: 1, salary_pending: 0 }),
      extra: { salary_input: { pending: false, can_fill: false, required: false } }, capabilities: { can_cancel: true } });
    const { w } = boot({ q: "?id=EC-PROM-2026-00009", detail: d }); await flush(); await flush(); await flush();
    const html = w.document.getElementById("prom-body").innerHTML;
    ok(!w.document.getElementById("prom-salfill") && /Ẩn - bạn không có quyền xem lương/.test(html), "Lead: an luong, khong o dien");
    w.Promotion.doApprove("EC-PROM-2026-00009", d);
    ok(!w.document.querySelector(".ec-prom-overlay #m-sal-cur"), "khong required -> hop Duyet khong co o luong"); }
  // ---- 5. Nguoi duyet KHONG quyen o cap trung gian: chi ghi chu
  { const d = detail({ extra: { salary_input: { pending: true, can_fill: false, required: false } } });
    d.business.salary_hidden = 1;
    const { w } = boot({ q: "?id=EC-PROM-2026-00009", detail: d }); await flush(); await flush(); await flush();
    const html = w.document.getElementById("prom-body").innerHTML;
    ok(!w.document.getElementById("prom-salfill") && /Lương sẽ do người duyệt có quyền xem lương/.test(html), "cap trung gian: khong o dien, co ghi chu"); }
  console.log(fails === 0 ? "\nALL PROMOTION LEAD SALARY TESTS PASSED" : "\n" + fails + " FAILED");
  process.exit(fails === 0 ? 0 : 1);
}
run();
