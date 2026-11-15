/* pm_mywork_host.test.js — host #mywork (pm_app.html showMyTasks) = "Việc cần làm" (PMQueue, 15/11/2026).
 * Chạy: NODE_PATH=<node_modules có jsdom> node ecentric_workspace/public/js/pm/tests/pm_mywork_host.test.js
 * Kiểm: có PMR thật + asset pm_queue -> #mywork vẽ PMQueue (tiêu đề + breadcrumb "Việc cần làm", queue.list qua api của host,
 * CSS tải lười cùng ?v=), không lỗi console; pmr:changed của PMR làm mới hàng đợi tại chỗ (không vẽ lại khung);
 * rời màn -> destroy; xương khi asset đang tải; tải asset lỗi -> màn cũ (dự phòng) cho cả phiên; PMR cũ (không có
 * _pure.parseDue) -> màn cũ; không thêm <script>/<link> cố định cho pm_queue, không Jinja, không đổi ?v=. */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..", "..");
const HTML = fs.readFileSync(path.join(ROOT, "pm", "frontend", "pm_app.html"), "utf8");
const PMRJS = fs.readFileSync(path.join(ROOT, "public", "js", "pm", "pm_redesign.js"), "utf8");
const QJS = fs.readFileSync(path.join(ROOT, "public", "js", "pm", "pm_queue.js"), "utf8");
const VER = (HTML.match(/pm_redesign\.js\?v=([0-9a-f]{10})/) || [])[1];
const USER = "me@ecentric.vn", res = [], ok = (n, c, x) => res.push({ n, c: !!c, x });
const p2 = n => (n < 10 ? "0" : "") + n, off = n => { const d = new Date(); d.setDate(d.getDate() + n); return d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate()); };
const T1 = { name: "T1", subject: "Bao cao thang 9", workflow_state: "In Progress", project: "P1", exp_end_date: off(-1), owner: "boss@ecentric.vn", _assign: JSON.stringify([USER]) };
const T3 = { name: "T3", subject: "Goi khach", workflow_state: "To Do", exp_end_date: off(2), owner: USER, _assign: JSON.stringify([USER]) };
const Q = tab => ({ today: off(0), now: "09:00", tab, counts: { late: 1, today: 0, tomorrow: 0, week: 0, later: 0, none: 0 }, asks: [], personal_hidden: 1,
  buckets: [{ key: "late", label: "Quá hạn" }, { key: "today", label: "Hôm nay" }, { key: "tomorrow", label: "Ngày mai" }, { key: "week", label: "Còn lại tuần này" }, { key: "later", label: "Tuần sau trở đi" }, { key: "none", label: "Chưa có hạn" }],
  rows: tab === "give" ? [] : [{ name: "T1", subject: "Bao cao thang 9", workflow_state: "In Progress", priority: "High", due: off(-1), due_time: null, bucket: "late", rank: 1, giver: "boss@ecentric.vn", giver_name: "Huong Le", self: false, assignees: [{ user: USER, name: "Me", opened: true }], project: "P1", project_name: "Du an Mot" }] });
function api(m, a) {
  m = m.replace("ecentric_workspace.pm.api.", "");
  return ({ "queue.list": Q(a && a.tab), "dashboard.my_tasklist": { attention: [T1], week: [T3], nodue: [], done: [] }, "dashboard.control_center": { is_leader: true }, "recurrence.list": { rows: [] },
    "tasks.list": { rows: [T1, T3] }, "timer.get_active": { active: false }, "projects.list": { rows: [{ name: "P1", project_name: "Du an Mot" }] },
    "assignment.list_assignable": { rows: [{ email: "boss@ecentric.vn", full_name: "Huong Le" }] }, "frappe.auth.get_logged_user": USER })[m] || {};
}
function boot(o) {
  o = o || {};
  const errors = [], calls = [], vc = new VirtualConsole();
  vc.on("error", (...a) => errors.push(a.map(String).join(" ")));
  vc.on("jsdomError", e => { if (!/Could not load (script|link)|Not implemented/.test(String(e && e.message))) errors.push("jsdomError " + (e && e.message)); });
  const dom = new JSDOM(HTML, { url: "https://team.ecentric.vn/pm" + (o.hash == null ? "#mywork" : o.hash), runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc, beforeParse(w) {
    w.document.cookie = "user_id=" + encodeURIComponent(USER) + "; path=/";
    w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: {} }), text: () => Promise.resolve("{}") });
    w.frappe = { csrf_token: "x", call: x => { calls.push({ m: x.method.replace("ecentric_workspace.pm.api.", ""), a: x.args || {} }); setTimeout(() => x.callback && x.callback({ message: api(x.method, x.args) }), 0); } };
    w.scrollTo = () => { }; w.Element.prototype.scrollIntoView = function () { };
    if (o.pmr !== "none") w.eval(PMRJS);
    if (o.pmr === "old") delete w.PMR._pure;   /* asset PMR cũ: chưa lộ parseDue */
    if (o.queue) w.eval(QJS);                   /* giả lập pm_queue.js đã tải */
  } });
  return { w: dom.window, d: dom.window.document, errors, calls };
}
const tick = ms => new Promise(r => setTimeout(r, ms || 30));
(async () => {
  let b = boot({ queue: true }); await tick(200);
  let v = b.d.getElementById("pm-view");
  ok("#mywork → PMQueue trong #pm-view (tiêu đề head() của host 'Việc cần làm', dòng việc theo queue.list)", !!v.querySelector(".pmq") && (v.querySelector(".pm-head h1") || {}).textContent === "Việc cần làm" && !!v.querySelector('.pmq-row[data-name="T1"]'));
  ok("breadcrumb 'Việc cần làm', menu fallback cũng đổi nhãn", (b.d.getElementById("pm-crumb") || {}).textContent === "Việc cần làm" && /Việc cần làm/.test((b.d.querySelector('.ec-shell-fallback a[href="/pm#mywork"]') || {}).textContent || ""));
  ok("đọc qua api của host (frappe.call) cả 2 tab; không gọi bộ dữ liệu màn cũ", b.calls.filter(c => c.m === "queue.list").length === 2 && !b.calls.some(c => c.m === "dashboard.my_tasklist"));
  const css = b.d.querySelector("link[data-pmq-css]");
  ok("CSS pm_queue tải lười đúng 1 lần, cùng ?v= với pm_redesign.js", !!css && css.getAttribute("href") === "/assets/ecentric_workspace/css/pm/pm_queue.css?v=" + VER && b.d.querySelectorAll("link[data-pmq-css]").length === 1);
  ok("hàng đợi đặt cờ leader (control_center) vì màn cũ không còn làm việc đó", b.calls.some(c => c.m === "dashboard.control_center"));
  const ctl = b.w._pmQueueCtl, root0 = ctl && ctl.root, n0 = b.calls.filter(c => c.m === "queue.list").length;
  b.d.dispatchEvent(new b.w.CustomEvent("pmr:changed", { detail: { task: "T1" } }));
  await tick(1300);
  ok("pmr:changed (từ ngăn việc của PMR) → hàng đợi tự làm mới tại chỗ, không vẽ lại khung", b.w._pmQueueCtl === ctl && v.querySelector(".pmq") === root0 && b.calls.filter(c => c.m === "queue.list").length > n0);
  b.d.querySelector('.pmq-row[data-name="T1"] .pmq-open').click(); await tick(60);
  ok("bấm dòng → ngăn chi tiết bên phải (tasks.get), không đổi hash", !b.d.querySelector("[data-drawer]").hidden && b.calls.some(c => c.m === "tasks.get") && b.w.location.hash === "#mywork");
  b.d.querySelector('[data-act="full"]').click(); await tick(60);
  ok("Mở đầy đủ → openTask của host (hash #task/T1, ngăn PMR)", b.w.location.hash === "#task/T1");
  ok("không lỗi console", b.errors.length === 0, b.errors.slice(0, 2).join(" | "));
  b.w.location.hash = "#received"; await tick(150);
  ok("rời #mywork → PMQueue destroy, không còn .pmq", ctl._state.dead === true && !b.w._pmQueueCtl && !b.d.querySelector(".pmq"));
  b.w.close();

  b = boot({}); await tick(120);
  v = b.d.getElementById("pm-view");
  const sc = b.d.querySelector('script[src="/assets/ecentric_workspace/js/pm/pm_queue.js?v=' + VER + '"]');
  ok("asset đang tải → xương cùng khung (tiêu đề + ô giao việc + 6 dòng), thẻ script pm_queue.js cùng ?v=", /Việc cần làm/.test(v.textContent) && v.querySelectorAll(".pmq-boot-row").length === 6 && !!sc && v.querySelector(".pmq-boot").getAttribute("aria-busy") === "true");
  sc.dispatchEvent(new b.w.Event("error")); await tick(200);
  ok("tải asset lỗi → giữ màn cũ làm dự phòng", !!v.querySelector('.pmr-md-g [data-task="T1"], .mw-done[data-task="T1"]') && b.calls.some(c => c.m === "dashboard.my_tasklist"));
  b.w.location.hash = "#received"; await tick(60); b.w.location.hash = "#mywork"; await tick(200);
  ok("...và cả phiên không thử lại hàng đợi (không xương, vẫn màn cũ)", !b.d.querySelector(".pmq-boot") && !b.d.querySelector(".pmq") && b.d.querySelectorAll('script[src*="pm_queue.js"]').length === 1);
  b.w.close();

  b = boot({ pmr: "old", queue: true }); await tick(200);
  ok("PMR cũ (chưa có _pure.parseDue) → màn cũ, không vỡ", !b.d.querySelector(".pmq") && b.calls.some(c => c.m === "dashboard.my_tasklist") && b.errors.length === 0, b.errors.slice(0, 2).join(" | "));
  b.w.close();

  ok("pm_app.html: không <script>/<link> cố định cho pm_queue, đúng 2 dấu ?v=, không Jinja, không khối ec- mới",
    !!VER && !/<(script|link)[^>]+pm_queue/.test(HTML) && (HTML.split("?v=" + VER).length - 1) === 2 && !/\{\{|\{%|\{#/.test(HTML) && !/<(script|style)[^>]+id="ec-[^"]*queue/.test(HTML) && (HTML.match(/hd==="new"/g) || []).length === 1);

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
