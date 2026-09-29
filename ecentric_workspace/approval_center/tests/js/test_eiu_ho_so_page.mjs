// Employee Info Update 29/09/2026: danh sach truong tu ho so, dien san gia tri hien tai,
// o "New value" theo kieu truong, bang ket qua ghi ho so. Chay THAT script trang tren jsdom.
//     node ecentric_workspace/approval_center/tests/js/test_eiu_ho_so_page.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const HTML = readFileSync(join(here, "..", "..", "features", "employee_info_update", "ui", "main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-employee-info-update">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 5)); };
const FO = { fields_to_update: ["Bank account", "Date of birth", "Marital status", "License plate", "Other"],
  field_types: { "Bank account": { type: "Data", options: [] }, "Date of birth": { type: "Date", options: [] },
    "Marital status": { type: "Select", options: ["Single", "Married"] }, "License plate": { type: "Data", options: [] } } };

function boot(url, detail, cv) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url });
  const w = dom.window; w.__calls = [];
  w.frappe = { csrf_token: "x", call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args]);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true },
      context: { user: "u@ecentric.vn", employee_name: "U" }, form_options: FO } });
    if (m === "get_form_options") return Promise.resolve({ message: FO });
    if (m === "current_value_of") return Promise.resolve({ message: cv || { value: "0123", readable: true, auto_apply: true } });
    if (m === "get_detail") return Promise.resolve({ message: detail });
    return Promise.resolve({ message: { rows: [], total: 0 } }); } };
  w.eval(JS); return w;
}
const pick = (w, k, v) => { const el = w.document.querySelector('[data-model="' + k + '"]'); el.value = v; el.dispatchEvent(new w.Event("change", { bubbles: true })); };

{ const w = boot("https://x.test/approvals/employee-information-update");
  await flush(); const d = w.document;
  const opts = [...d.querySelectorAll('[data-model="field_to_update"] option')].map((o) => o.value).filter(Boolean);
  ok(opts.join("|") === FO.fields_to_update.join("|"), "danh sach truong lay tu server (ho so)");
  ok(d.querySelector('[data-model="employee_email"]').value === "u@ecentric.vn", "mac dinh email cua chinh minh");
  pick(w, "field_to_update", "Bank account"); await flush();
  const c = w.__calls.filter((x) => x[0] === "current_value_of");
  ok(c.length === 1 && c[0][1].field_to_update === "Bank account" && c[0][1].employee_email === "u@ecentric.vn", "chon truong -> hoi gia tri hien tai");
  const cv = d.querySelector('[data-model="current_value"]');
  ok(cv.value === "0123" && cv.readOnly, "dien san + khoa current value khi doc duoc");
  ok(/tự ghi/.test(d.getElementById("eiu-cv-hint").textContent), "bao se tu ghi vao ho so");
  pick(w, "field_to_update", "Date of birth"); await flush();
  ok(d.querySelector('[data-model="new_value"]').type === "date", "truong ngay -> o chon ngay");
  pick(w, "field_to_update", "Marital status"); await flush();
  ok(d.querySelector('[data-model="new_value"]').tagName === "SELECT", "truong lua chon -> select");
  pick(w, "field_to_update", "Other"); await flush();
  ok(/tay/.test(d.getElementById("eiu-cv-hint").textContent), "Other -> C&B cap nhat tay");
  ok(w.__calls.filter((x) => x[0] === "current_value_of").length === 3, "Other khong hoi gia tri");
}
{ const w = boot("https://x.test/approvals/employee-information-update", null, { value: "", readable: false, auto_apply: true });
  await flush(); pick(w, "employee_email", "khac@ecentric.vn"); pick(w, "field_to_update", "Bank account"); await flush();
  const cv = w.document.querySelector('[data-model="current_value"]');
  ok(!cv.readOnly && cv.value === "", "khong duoc xem -> de trong, tu nhap"); }
function det(ap, extra) { return { business: { name: "EIU-1", employee_email: "u@x", field_to_update: "Bank account", current_value: "1", new_value: "2" },
  approval: { name: "AR", approval_status: ap, current_level: 0 }, levels: [], approvers: [], attachments: [], timeline: [], extra, capabilities: {} }; }
{ const w = boot("https://x.test/approvals/employee-information-update?id=EIU-1", det("Approved", { auto_apply: true, applied_at: "x", apply_result: "Đã ghi vào hồ sơ HR-EMP-1: Bank account" }));
  await flush(); ok(/Đã ghi vào hồ sơ HR-EMP-1/.test(w.document.getElementById("eiu-body").innerHTML), "chi tiet: da ghi ho so"); }
{ const w = boot("https://x.test/approvals/employee-information-update?id=EIU-1", det("Approved", { auto_apply: true, apply_result: "LỖI khi ghi <b>x</b>" }));
  await flush(); const h = w.document.getElementById("eiu-body").innerHTML;
  ok(/banner err/.test(h) && /&lt;b&gt;/.test(h), "chi tiet: loi ghi -> banner do, escape"); }
console.log(`${oks} dat, ${fails} hong`);
process.exit(fails ? 1 : 0);
