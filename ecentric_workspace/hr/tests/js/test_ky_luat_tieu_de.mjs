// /ky-luat + tab Ky luat /tong-quan - TIEU DE the vang / ho so (Hoan chot 23/11/2026).
// Kiem: o tieu de trong form tao (payload gui `title`), cot dau danh sach la Tieu de (loc theo tieu de),
// popup chi tiet ve tieu de + nut "Sua tieu de" CHI khi server cho (actions.retitle) va gui dung
// notice_retitle / case_retitle; ho so cu (khong tieu de) mo form sua hien goi y giu tieu de tu sinh;
// /tong-quan ve tieu de lam link.
//     NODE_PATH=/tmp/node_modules node ecentric_workspace/hr/tests/js/test_ky_luat_tieu_de.mjs
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
const render = (tpl, ctx) => execFileSync("python3", ["-c", RENDER, APP, tpl, JSON.stringify(ctx)]).toString();

function bootCfg(isHr) {
  return { tab: "the-vang", open: "", is_hr: isHr, can_issue: true, meeting_notice_days: 5, title_max: 140,
    title_placeholder: "Đi trễ nhiều lần tháng 11",
    employees: [{ value: "EMP-NV", label: "Nhan Vien · EMP-NV" }], rules: [{ value: "R1", label: "Di muon" }],
    cards: { "Thẻ đỏ": ["Khiển trách"], "Thẻ đen": ["Kéo dài thời hạn nâng lương", "Cách chức", "Sa thải"] },
    grounds: [{ value: "1", label: "x" }], blocks: ["b"], present: ["Có mặt"] };
}
function ctxFor(tab, isHr) {
  return { tab, title: "Kỷ luật", legal_note: "NĐ 145/2020", yellow_note: "Thẻ vàng là nhắc nhở nội bộ", ekl_css: "/x.css", ekl_js: "/x.js",
    ekl_shell_mount: "", ekl_topbar: "",
    tabs: [{ key: "the-vang", label: "Thẻ vàng", active: tab === "the-vang", href: "?tab=the-vang" }, { key: "ho-so", label: "Hồ sơ", active: tab === "ho-so", href: "?tab=ho-so" }],
    perm: { is_hr: isHr, can_issue: true, has_team: !isHr },
    notices: [{ name: "TV-1", title: "Đi trễ nhiều lần tháng 11", title_auto: 0, employee_name: "Nhan Vien", behavior: "Di muon", incident_date: "2026-11-20", reply_due: "2026-11-26", status: "Chờ phản hồi", mine: 0 },
      { name: "TV-2", title: "Thẻ vàng - Ve som - 18/11/2026", title_auto: 1, employee_name: "Khac", behavior: "Ve som", incident_date: "2026-11-18", reply_due: "2026-11-21", status: "Đã đọc", mine: 0 }],
    cases: [{ name: "KL-1", title: "Hồ sơ kỷ luật - Khiển trách - 10/11/2026", title_auto: 1, employee_name: "Nhan Vien", card: "Thẻ đỏ", penalty: "Khiển trách", violation_date: "2026-11-10", meeting_date: "", limitation_effective_end: "2027-05-10", status: "Đang lập", mine: 0 }],
    boot_json: JSON.stringify(Object.assign(bootCfg(isHr), { tab })) };
}
function boot(tab, handlers, isHr = true) {
  const html = render("www/ky_luat/index.html", ctxFor(tab, isHr));
  const dom = new JSDOM("<!DOCTYPE html><html>" + html.replace(/<script src=[^>]*><\/script>/g, "") + "</html>",
    { runScripts: "outside-only", url: "https://x.test/ky-luat?tab=" + tab });
  const w = dom.window; const calls = [];
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
const submit = (w, f) => f.dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true }));

{ // 1) danh sach: cot dau = Tieu de, tieu de tu sinh mo hon, loc theo tieu de
  const { w } = boot("the-vang", {}); await flush();
  ok($(w, ".ekl-tbl thead th").textContent === "Tiêu đề", "the vang: cot dau la Tieu de");
  const rows = [...w.document.querySelectorAll("[data-ekl-rows] tr")];
  ok(rows[0].querySelector("td").textContent.trim() === "Đi trễ nhiều lần tháng 11", "dong 1 hien tieu de da nhap");
  ok(rows[1].querySelector("td").classList.contains("is-auto"), "tieu de tu sinh danh dau is-auto");
  const q = $(w, "[data-ekl-q]"); q.value = "nhiều lần"; q.dispatchEvent(new w.Event("input", { bubbles: true }));
  ok(!rows[0].hidden && rows[1].hidden, "tim theo tieu de");
  const b = boot("ho-so", {}); await flush();
  ok($(b.w, ".ekl-tbl thead th").textContent === "Tiêu đề", "ho so: cot dau la Tieu de");
}
{ // 2) form the vang: o tieu de bat buoc + placeholder, gui payload.title
  const { w, calls } = boot("the-vang", {}); await flush();
  click(w, $(w, '[data-ekl-open-form="notice"]'));
  const t = $(w, "#ekl-n-title");
  ok(!!t && t.getAttribute("maxlength") === "140" && /Đi trễ nhiều lần tháng 11/.test(t.getAttribute("placeholder")), "o tieu de the vang + placeholder");
  ok(t.closest(".ekl-fld").querySelector(".ekl-req"), "dau * bat buoc");
  t.value = "Đi trễ 3 lần"; $(w, "#ekl-n-emp").value = "EMP-NV"; $(w, "#ekl-n-beh").value = "Di muon";
  $(w, "#ekl-n-date").value = "2026-11-20"; $(w, "#ekl-n-content").value = "Nhac";
  submit(w, $(w, '[data-ekl-form="notice"]')); await flush();
  const p = calls.find((c) => c[0] === "post");
  ok(p && /issue_notice$/.test(p[1]) && p[2].payload.title === "Đi trễ 3 lần", "issue_notice gui title");
}
{ // 3) loi server theo truong title -> to do o tieu de
  const { w } = boot("the-vang", { post: () => ({ success: false, message: "Nhập tiêu đề", data: { errors: { title: "Nhập tiêu đề" } } }) }); await flush();
  click(w, $(w, '[data-ekl-open-form="notice"]'));
  submit(w, $(w, '[data-ekl-form="notice"]')); await flush();
  ok($(w, "#ekl-n-title").closest(".ekl-fld").classList.contains("is-invalid"), "o tieu de to do khi server bao loi");
}
{ // 4) form lap ho so (HR): co o tieu de, gui title; khong hien goi y "ho so cu"
  const { w, calls } = boot("ho-so", {}); await flush();
  click(w, $(w, '[data-ekl-open-form="case"]'));
  const f = $(w, '[data-ekl-form="case"]');
  const t = f.querySelector('[name="title"]');
  ok(!!t && !t.closest("[hidden]"), "form lap ho so co o tieu de");
  ok(f.querySelector("[data-ekl-title-hint]").hidden, "tao moi: khong hien goi y ho so cu");
  ok(!f.querySelector('label[for="ekl-c-title"] .ekl-req').hidden, "tao moi: tieu de co dau *");
  t.value = "Vắng 2 ngày";
  submit(w, f); await flush();
  const p = calls.find((c) => c[0] === "post");
  ok(p && /create_case$/.test(p[1]) && p[2].payload.title === "Vắng 2 ngày", "create_case gui title");
}
{ // 5) LM de xuat: van co o tieu de
  const { w, calls } = boot("ho-so", {}, false); await flush();
  click(w, $(w, '[data-ekl-open-form="propose"]'));
  const f = $(w, '[data-ekl-form="case"]');
  f.querySelector('[name="title"]').value = "Đề xuất A";
  submit(w, f); await flush();
  const p = calls.find((c) => c[0] === "post");
  ok(p && /propose_case$/.test(p[1]) && p[2].payload.title === "Đề xuất A", "propose_case gui title");
}
{ // 6) chi tiet ho so cu, buoc lap: tieu de tu sinh + nut Sua (form) hien goi y giu tieu de tu sinh
  const data = { name: "KL-1", title: "", display_title: "Hồ sơ kỷ luật - Khiển trách - 10/11/2026", title_auto: 1, display_status: "Đang lập",
    card: "Thẻ đỏ", penalty: "Khiển trách", actions: { edit: true, retitle: false }, logs: [] };
  const { w, calls } = boot("ho-so", { get: () => ({ success: true, data }) }); await flush();
  click(w, $(w, 'tr[data-name="KL-1"]')); await flush();
  const box = $(w, "[data-ekl-detail]");
  ok(/Hồ sơ kỷ luật - Khiển trách - 10\/11\/2026/.test(box.querySelector(".ekl-dtitle").textContent), "chi tiet hien tieu de du phong");
  ok(/tiêu đề tự sinh/.test(box.textContent), "ghi chu tieu de tu sinh");
  ok(!box.querySelector('[data-ekl-act="retitle"]'), "buoc lap: khong co nut Sua tieu de rieng");
  click(w, box.querySelector('[data-ekl-act="edit"]')); await flush();
  const f = $(w, '[data-ekl-form="case"]');
  ok(!f.querySelector("[data-ekl-title-hint]").hidden, "sua ho so cu: goi y giu tieu de tu sinh");
  ok(f.querySelector('[name="title"]').value === "", "o tieu de trong (khong chep tieu de du phong vao)");
  submit(w, f); await flush();
  const p = calls.find((c) => c[0] === "post");
  ok(p && /update_case$/.test(p[1]) && p[2].payload.title === "", "update_case gui title rong = giu cu");
}
{ // 7) ho so da thong bao hop: nut Sua tieu de -> case_retitle
  const data = { name: "KL-1", title: "Vắng 2 ngày", display_title: "Vắng 2 ngày", title_auto: 0, display_status: "Đã thông báo họp",
    actions: { retitle: true }, logs: [] };
  const { w, calls } = boot("ho-so", { get: () => ({ success: true, data }) }); await flush();
  click(w, $(w, 'tr[data-name="KL-1"]')); await flush();
  click(w, $(w, '[data-ekl-detail] [data-ekl-act="retitle"]')); await flush();
  const step = $(w, '[data-ekl-form="step"]');
  const inp = step.querySelector('[name="title"]');
  ok(!!inp && inp.value === "Vắng 2 ngày" && inp.getAttribute("maxlength") === "140", "form sua tieu de dien san");
  inp.value = "Vắng 2 ngày không phép";
  submit(w, step); await flush();
  const p = calls.find((c) => c[0] === "post");
  ok(p && /case_retitle$/.test(p[1]) && p[2].name === "KL-1" && p[2].title === "Vắng 2 ngày không phép", "gui case_retitle");
}
{ // 8) the vang: nut Sua tieu de theo actions.retitle -> notice_retitle; khong co thi khong ve
  const mk = (retitle) => ({ name: "TV-1", title: "Đi trễ", display_title: "Đi trễ", status: "Chờ phản hồi", note: "x",
    actions: { retitle, read: !retitle }, logs: [] });
  let { w, calls } = boot("the-vang", { get: () => ({ success: true, data: mk(true) }) }); await flush();
  click(w, $(w, 'tr[data-name="TV-1"]')); await flush();
  ok(/Đi trễ/.test($(w, "[data-ekl-detail] .ekl-dtitle").textContent), "chi tiet the vang hien tieu de");
  click(w, $(w, '[data-ekl-detail] [data-ekl-act="nretitle"]')); await flush();
  const step = $(w, '[data-ekl-form="step"]'); step.querySelector('[name="title"]').value = "Đi trễ 4 lần";
  submit(w, step); await flush();
  const p = calls.find((c) => c[0] === "post");
  ok(p && /notice_retitle$/.test(p[1]) && p[2].title === "Đi trễ 4 lần", "gui notice_retitle");
  ({ w } = boot("the-vang", { get: () => ({ success: true, data: mk(false) }) }, false)); await flush();
  click(w, $(w, 'tr[data-name="TV-1"]')); await flush();
  ok(!$(w, '[data-ekl-detail] [data-ekl-act="nretitle"]'), "NV / da phan hoi: khong co nut Sua tieu de");
}
{ // 9) escape tieu de
  const data = { name: "TV-1", title: "<img src=x onerror=alert(1)>", display_title: "<img src=x onerror=alert(1)>", status: "Chờ phản hồi", actions: {}, logs: [] };
  const { w } = boot("the-vang", { get: () => ({ success: true, data }) }); await flush();
  click(w, $(w, 'tr[data-name="TV-1"]')); await flush();
  ok(!$(w, "[data-ekl-detail] img"), "tieu de duoc escape");
}

// ---- 10) /tong-quan: tieu de lam link trong tab Ky luat
{
  const HTML = readFileSync(join(APP, "hr", "pages", "tong_quan", "main_section.html"), "utf8");
  const i = HTML.indexOf('<div class="ecq"'); const s = HTML.indexOf('<script id="ec-tongquan-js">');
  const js = HTML.slice(s).replace(/^<script[^>]*>/, "").split("</script>")[0];
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + HTML.slice(i, s) + "</body></html>", { runScripts: "outside-only", url: "https://x.test/tong-quan#nhan-su/danh-sach" });
  const w = dom.window;
  const env = (data) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: { success: true, data } }) });
  w.fetch = (url) => {
    if (/get_hr_overview/.test(url)) return env({ stats: { active: 1 }, directory: [{ name: "EMP-NV", employee_name: "Nhan Vien", department: "D", dept: "D", missing: [] }], by_dept: [], todo: [] });
    if (/get_hr_profile/.test(url)) return env({ name: "EMP-NV", employee_name: "Nhan Vien", org: [], erp_url: "/app/employee/EMP-NV" });
    if (/employee_discipline/.test(url)) return env({ employee: "EMP-NV", route: "/ky-luat", active: [],
      cases: [{ name: "KL-1", title: "Vắng <b>2</b> ngày", card: "Thẻ đỏ", penalty: "Khiển trách", status: "Đã ban hành", violation_date: "2026-11-10" }],
      notices: [{ name: "TV-1", title: "Thẻ vàng - Di muon - 20/11/2026", behavior: "Di muon", incident_date: "2026-11-20", status: "Đã đọc" }] });
    return env({});
  };
  w.eval(js); await flush();
  const tr = w.document.querySelector('#tq-body tr[data-name="EMP-NV"]'); tr && click(w, tr); await flush();
  const tab = w.document.querySelector('#tq-ptabs [data-p="discipline"]'); tab && click(w, tab); await flush();
  const panel = w.document.getElementById("tq-panel");
  const a1 = panel && panel.querySelector('a[href="/ky-luat?tab=ho-so&ma=KL-1"]');
  const a2 = panel && panel.querySelector('a[href="/ky-luat?tab=the-vang&ma=TV-1"]');
  ok(a1 && a1.textContent === "Vắng <b>2</b> ngày", "tong-quan: tieu de ho so lam link (escape)");
  ok(a2 && a2.textContent === "Thẻ vàng - Di muon - 20/11/2026", "tong-quan: tieu de the vang lam link");
  ok(panel && /Khiển trách/.test(panel.textContent) && /Thẻ vàng \(nội bộ\)/.test(panel.textContent), "tong-quan: van ve hinh thuc / loai the");
}

console.log((fails ? "HONG" : "OK") + ": " + oks + " dat, " + fails + " hong");
process.exit(fails ? 1 : 0);
