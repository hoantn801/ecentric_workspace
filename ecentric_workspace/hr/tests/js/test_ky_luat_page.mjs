// /ky-luat (hr/ky_luat) + tab "Ky luat" tren ho so nhan su /tong-quan (Dot 3 HR, 23/11/2026).
// Trang /ky-luat la template Jinja: test render that bang jinja2 (base template gia), chay
// ec_ky_luat.js trong jsdom voi ecApi gia. Kiem: loc bang, form the vang gui dung payload,
// loi theo truong do o, the -> hinh thuc, popup chi tiet ve nut theo `actions` server tra.
//     NODE_PATH=/tmp/node_modules node ecentric_workspace/hr/tests/js/test_ky_luat_page.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 15; i++) await new Promise((r) => setTimeout(r, 2)); };

const RENDER = `
import json, sys, jinja2
app, tpl, ctx = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
base = "{% block style %}{% endblock %}<body>{% block content %}{% endblock %}{% block script %}{% endblock %}</body>"
env = jinja2.Environment(loader=jinja2.ChoiceLoader([jinja2.DictLoader({"base.html": base}), jinja2.FileSystemLoader(app)]), autoescape=False)
ctx["base_template_path"] = "base.html"
print(env.get_template(tpl).render(**ctx))
`;
function render(tpl, ctx) { return execFileSync("python3", ["-c", RENDER, APP, tpl, JSON.stringify(ctx)]).toString(); }

const BOOT = { tab: "the-vang", open: "", is_hr: true, can_issue: true, meeting_notice_days: 5,
  employees: [{ value: "EMP-NV", label: "Nhan Vien · EMP-NV" }],
  rules: [{ value: "R1", label: "Di muon", sample: 1 }],
  cards: { "Thẻ đỏ": ["Khiển trách"], "Thẻ đen": ["Kéo dài thời hạn nâng lương", "Cách chức", "Sa thải"] },
  grounds: [{ value: "1", label: "Trom cap" }], blocks: ["Nữ mang thai, nghỉ thai sản, nuôi con dưới 12 tháng"],
  present: ["Có mặt", "Vắng mặt dù đã được thông báo"] };
function ctxFor(tab) {
  return { tab, title: "Kỷ luật", legal_note: "Ghi chú pháp lý: HR/pháp chế xác nhận NĐ 145/2020 nguyên văn trước khi dùng thật.",
    yellow_note: "Thẻ vàng là nhắc nhở nội bộ", ekl_css: "/x.css", ekl_js: "/x.js", ekl_shell_mount: "", ekl_topbar: "",
    tabs: [{ key: "the-vang", label: "Thẻ vàng", active: tab === "the-vang", href: "?tab=the-vang" }, { key: "ho-so", label: "Hồ sơ kỷ luật", active: tab === "ho-so", href: "?tab=ho-so" }],
    perm: { is_hr: true, can_issue: true, has_team: false },
    notices: [{ name: "TV-1", employee_name: "Nhan Vien", behavior: "Di muon", incident_date: "2026-11-20", reply_due: "2026-11-26", status: "Chờ phản hồi", mine: 0 },
      { name: "TV-2", employee_name: "Khac", behavior: "Ve som", incident_date: "2026-11-21", reply_due: "2026-11-27", status: "Đã đọc", mine: 1 }],
    cases: [{ name: "KL-1", employee_name: "Nhan Vien", card: "Thẻ đỏ", penalty: "Khiển trách", violation_date: "2026-11-10", meeting_date: "", limitation_effective_end: "2027-05-10", status: "Đang lập", mine: 0 }],
    boot_json: JSON.stringify(Object.assign({}, BOOT, { tab })) };
}

function boot(tab, handlers) {
  const html = render("www/ky_luat/index.html", ctxFor(tab));
  const dom = new JSDOM("<!DOCTYPE html><html>" + html.replace(/<script src=[^>]*><\/script>/g, "") + "</html>",
    { runScripts: "outside-only", url: "https://x.test/ky-luat?tab=" + tab });
  const w = dom.window;
  const calls = [];
  w.confirm = () => true;
  w.ecApi = {
    get: (m, a) => { calls.push(["get", m, a]); return Promise.resolve((handlers.get || (() => ({ success: true, data: {} })))(m, a)); },
    post: (m, a) => { calls.push(["post", m, a]); return Promise.resolve((handlers.post || (() => ({ success: true, data: { name: "X" } })))(m, a)); },
    csrfToken: () => Promise.resolve("t"),
  };
  w.eval(readFileSync(join(APP, "public", "js", "ec_ky_luat.js"), "utf8"));
  w.EcKyLuat.navigate = (u) => calls.push(["assign", u]);
  return { w, calls, html };
}
const $ = (w, q) => w.document.querySelector(q);
const click = (w, el) => el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));

{ // 1) markup: ghi chu phap ly, khong o tien, khong script/style inline
  const { html } = boot("the-vang", {}); await flush();
  ok(/NĐ 145\/2020/.test(html), "ghi chu phap ly hien tren trang");
  ok(!/<style/.test(html) && !/<script>(?!\s*$)/.test(html), "khong co khoi style/script inline");
  ok(!/name="[a-z_]*(tien|fine|amount|phat)[a-z_]*"/.test(html), "khong co o tien phat");
}
{ // 2) loc bang
  const { w } = boot("the-vang", {}); await flush();
  const q = $(w, "[data-ekl-q]"); q.value = "ve som"; q.dispatchEvent(new w.Event("input", { bubbles: true }));
  const rows = [...w.document.querySelectorAll("[data-ekl-rows] tr")];
  ok(rows[0].hidden && !rows[1].hidden, "tim kiem loc dong");
  q.value = ""; q.dispatchEvent(new w.Event("input", { bubbles: true }));
  const m = $(w, "[data-ekl-mine]"); m.checked = true; m.dispatchEvent(new w.Event("change", { bubbles: true }));
  ok(rows[0].hidden && !rows[1].hidden, "chi cua toi");
}
{ // 3) gui the vang: payload + loi theo truong
  let reply = { success: false, message: "Nhập hành vi.", data: { errors: { behavior: "Nhập hành vi." } } };
  const { w, calls } = boot("the-vang", { post: () => reply }); await flush();
  click(w, $(w, '[data-ekl-open-form="notice"]'));
  ok(!$(w, '[data-ekl-form-ov="notice"]').hidden, "mo form the vang");
  ok($(w, "#ekl-n-emp").options.length === 2, "danh sach nhan vien tu boot");
  $(w, "#ekl-n-emp").value = "EMP-NV"; $(w, "#ekl-n-date").value = "2026-11-20"; $(w, "#ekl-n-content").value = "Nhac";
  $(w, '[data-ekl-form="notice"]').dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true })); await flush();
  const post = calls.find((c) => c[0] === "post");
  ok(post && /issue_notice$/.test(post[1]) && post[2].payload.employee === "EMP-NV" && post[2].payload.content === "Nhac", "goi issue_notice dung payload");
  ok($(w, "#ekl-n-beh").closest(".ekl-fld").classList.contains("is-invalid"), "o loi duoc to do");
  ok(/Nhập hành vi/.test($(w, '[data-ekl-form="notice"] [data-ekl-err]').textContent), "hien loi server");
  reply = { success: true, data: { name: "TV-9", hint: "" } };
  $(w, '[data-ekl-form="notice"]').dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true })); await flush();
  ok(calls.some((c) => c[0] === "assign" && /ma=TV-9/.test(c[1])), "thanh cong -> tai lai mo dung the");
}
{ // 4) form ho so: the -> hinh thuc + o phu
  const { w } = boot("ho-so", {}); await flush();
  click(w, $(w, '[data-ekl-open-form="case"]'));
  const f = $(w, '[data-ekl-form="case"]');
  const card = f.querySelector('[name="card"]'); card.value = "Thẻ đen"; card.dispatchEvent(new w.Event("change", { bubbles: true }));
  const pen = f.querySelector('[name="penalty"]');
  ok([...pen.options].map((o) => o.value).join("|") === "|Kéo dài thời hạn nâng lương|Cách chức|Sa thải", "the den -> 3 hinh thuc");
  pen.value = "Sa thải"; pen.dispatchEvent(new w.Event("change", { bubbles: true }));
  ok(!f.querySelector('[data-ekl-show="Sa thải"]').hidden && f.querySelector('[data-ekl-show="Cách chức"]').hidden, "sa thai -> hien can cu D125");
  card.value = "Thẻ đỏ"; card.dispatchEvent(new w.Event("change", { bubbles: true }));
  ok(pen.value === "Khiển trách" && pen.options.length === 1, "the do -> chi khien trach");
}
{ // 5) popup chi tiet ve nut theo actions
  const data = { name: "KL-1", display_status: "Đang lập", employee_name: "Nhan Vien", card: "Thẻ đỏ", penalty: "Khiển trách",
    earliest_meeting: "2026-11-30", is_union_member: "1", check: { errors: [], warnings: ["Còn 10 ngày tới hết thời hiệu"] },
    actions: { notify: true, edit: true, cancel: true, postpone: true }, logs: [{ action: "Lập hồ sơ", actor: "hr", at: "2026-11-23 09:00:00" }] };
  const { w, calls } = boot("ho-so", { get: () => ({ success: true, data }), post: () => ({ success: true, data: { name: "KL-1" } }) }); await flush();
  click(w, $(w, 'tr[data-name="KL-1"]')); await flush();
  const box = $(w, "[data-ekl-detail]");
  ok(/Còn 10 ngày/.test(box.textContent), "canh bao thoi hieu hien");
  ok(box.querySelector('[data-ekl-act="notify"]') && !box.querySelector('[data-ekl-act="submit"]'), "chi nut duoc phep");
  click(w, box.querySelector('[data-ekl-act="notify"]')); await flush();
  const step = $(w, '[data-ekl-form="step"]');
  ok(step.querySelector('[name="meeting_date"]').getAttribute("min") === "2026-11-30", "ngay hop min = ngay som nhat server tinh");
  ok(/đại diện công đoàn/.test(step.textContent), "nhac gui dai dien cong doan khi la doan vien");
  step.dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true })); await flush();
  const p = calls.find((c) => c[0] === "post");
  ok(p && /notify_meeting$/.test(p[1]) && p[2].name === "KL-1" && p[2].meeting_date === "2026-11-30", "gui notify_meeting");
}

// ---- 6) /tong-quan: tab Ky luat trong khung ho so
{
  const HTML = readFileSync(join(APP, "hr", "pages", "tong_quan", "main_section.html"), "utf8");
  const i = HTML.indexOf('<div class="ecq"'); const s = HTML.indexOf('<script id="ec-tongquan-js">');
  const js = HTML.slice(s).replace(/^<script[^>]*>/, "").split("</script>")[0];
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + HTML.slice(i, s) + "</body></html>", { runScripts: "outside-only", url: "https://x.test/tong-quan#nhan-su/danh-sach" });
  const w = dom.window; const urls = [];
  const env = (data) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: { success: true, data } }) });
  w.fetch = (url) => {
    urls.push(String(url));
    if (/get_hr_overview/.test(url)) return env({ stats: { active: 1 }, directory: [{ name: "EMP-NV", employee_name: "Nhan Vien", department: "D", dept: "D", missing: [] }], by_dept: [], todo: [] });
    if (/get_hr_profile/.test(url)) return env({ name: "EMP-NV", employee_name: "Nhan Vien", org: [], erp_url: "/app/employee/EMP-NV" });
    if (/employee_discipline/.test(url)) return env({ employee: "EMP-NV", route: "/ky-luat", hint: "3 thẻ vàng trong 90 ngày", active: [{}],
      cases: [{ name: "KL-1", card: "Thẻ đỏ", penalty: "Khiển trách", status: "Đã ban hành", violation_date: "2026-11-10", decision_date: "2026-11-30", expunge_due: "2027-02-28" }],
      notices: [{ name: "TV-1", behavior: "Di muon", incident_date: "2026-11-20", status: "Đã đọc" }] });
    return env({});
  };
  w.eval(js); await flush();
  const tr = w.document.querySelector('#tq-body tr[data-name="EMP-NV"]');
  ok(!!tr, "tong-quan: co dong nhan vien");
  tr && click(w, tr); await flush();
  const tab = w.document.querySelector('#tq-ptabs [data-p="discipline"]');
  ok(!!tab && tab.textContent === "Kỷ luật", "tong-quan: co tab Ky luat");
  tab && click(w, tab); await flush();
  const panel = w.document.getElementById("tq-panel");
  ok(urls.some((u) => /hr\.ky_luat\.controllers\.api\.employee_discipline\?employee=EMP-NV/.test(u)), "tong-quan: goi employee_discipline");
  ok(panel && /Khiển trách/.test(panel.textContent) && /Thẻ vàng \(nội bộ\)/.test(panel.textContent) && /3 thẻ vàng/.test(panel.textContent), "tong-quan: ve the vang + ho so + goi y");
  ok(panel && panel.querySelector('a[href="/ky-luat?tab=ho-so&ma=KL-1"]'), "tong-quan: link sang /ky-luat");
  ok(urls.filter((u) => /employee_discipline/.test(u)).length === 1, "tong-quan: tai mot lan");
}

console.log((fails ? "HONG" : "OK") + ": " + oks + " dat, " + fails + " hong");
process.exit(fails ? 1 : 0);
