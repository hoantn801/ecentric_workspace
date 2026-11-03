/* pm_mywork_host.test.js — host "Việc của tôi" (pm_app.html showMyTasks) + PMR.render.myDay (u2 03/11/2026).
 * Chạy: NODE_PATH=<node_modules có jsdom> node ecentric_workspace/public/js/pm/tests/pm_mywork_host.test.js
 * Kiểm: có PMR thật → #mywork vẽ ô ghi nhanh + nhóm theo hạn (không còn bảng Focus cũ), không lỗi console, việc nhật ký cá nhân vẫn ẩn;
 * PMR cũ không có render.myDay → giữ bảng Focus + nút Xong như trước. */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..", "..");
const HTML = fs.readFileSync(path.join(ROOT, "pm", "frontend", "pm_app.html"), "utf8");
const PMRJS = fs.readFileSync(path.join(ROOT, "public", "js", "pm", "pm_redesign.js"), "utf8");
const USER = "me@ecentric.vn", res = [], ok = (n, c, x) => res.push({ n, c: !!c, x });
const p2 = n => (n < 10 ? "0" : "") + n, off = n => { const d = new Date(); d.setDate(d.getDate() + n); return d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate()); };
const T1 = { name: "T1", subject: "Bao cao thang 9", workflow_state: "In Progress", project: "P1", exp_end_date: off(-1), owner: "boss@ecentric.vn", _assign: JSON.stringify([USER]) };
const T2 = { name: "T2", subject: "Worklog ca nhan", workflow_state: "In Progress", project: "WL1", exp_end_date: off(-1), _assign: JSON.stringify([USER]) };
const T3 = { name: "T3", subject: "Goi khach", workflow_state: "To Do", exp_end_date: off(2), owner: USER, _assign: JSON.stringify([USER]) };
function api(m, a) {
  m = m.replace("ecentric_workspace.pm.api.", "");
  return ({ "dashboard.my_tasklist": { attention: [T1, T2], week: [T3], nodue: [], done: [] }, "dashboard.control_center": { is_leader: false }, "recurrence.list": { rows: [] },
    "tasks.list": { rows: a && a.include_personal ? [T1, T2, T3] : [T1, T3] }, "timer.get_active": { active: false },
    "projects.list": { rows: [{ name: "P1", project_name: "Du an Mot" }, { name: "WL1", project_name: "ERP - Worklog", ec_personal_log: 1 }] },
    "assignment.list_assignable": { rows: [{ email: "boss@ecentric.vn", full_name: "Huong Le" }] }, "frappe.auth.get_logged_user": USER })[m] || {};
}
function boot(pmr) {
  const errors = [], vc = new VirtualConsole();
  vc.on("error", (...a) => errors.push(a.map(String).join(" ")));
  vc.on("jsdomError", e => { if (!/Could not load (script|link)|Not implemented/.test(String(e && e.message))) errors.push("jsdomError " + (e && e.message)); });
  const dom = new JSDOM(HTML, { url: "https://team.ecentric.vn/pm#mywork", runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc, beforeParse(w) {
    w.document.cookie = "user_id=" + encodeURIComponent(USER) + "; path=/";
    w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: {} }), text: () => Promise.resolve("{}") });
    w.frappe = { csrf_token: "x", call: o => setTimeout(() => o.callback && o.callback({ message: api(o.method, o.args) }), 0) };
    w.scrollTo = () => { }; w.Element.prototype.scrollIntoView = function () { };
    if (pmr === "real") w.eval(PMRJS);
    if (pmr === "old") { w.eval(PMRJS); delete w.PMR.render.myDay; }   /* asset cũ (trước u2) chưa có myDay */
  } });
  return { w: dom.window, errors };
}
const tick = ms => new Promise(r => setTimeout(r, ms || 30));
(async () => {
  let b = boot("real"); await tick(150);
  const v = b.w.document.getElementById("pm-view");
  ok("có PMR.render.myDay → #mywork có ô ghi nhanh việc của tôi", !!v.querySelector(".pmr-qa-in") && /Việc cần làm/.test(v.textContent));
  ok("nhóm theo hạn: T1 ở Quá hạn, T3 ở Sắp tới; không còn bảng Focus cũ", !!v.querySelector('.pmr-md-g[data-g="late"] [data-task="T1"]') && !!v.querySelector('.pmr-md-g[data-g="soon"] [data-task="T3"]') && !v.querySelector(".mw-done"));
  ok("việc nhật ký cá nhân vẫn ẩn (host lọc trước khi đưa cho myDay)", !v.querySelector('[data-task="T2"]') && /Đang ẩn 1 việc nhật ký cá nhân/.test(v.textContent));
  ok("thẻ đếm Quá hạn của host vẫn đúng (1)", (v.querySelector('.stat-card[data-mw-filter="overdue"] .stat-value') || {}).textContent === "1");
  ok("không lỗi console", b.errors.length === 0, b.errors.slice(0, 2).join(" | "));
  b.w.close();
  b = boot("old"); await tick(150);
  const v2 = b.w.document.getElementById("pm-view");
  ok("PMR cũ (không có myDay) → giữ bảng Focus + nút Xong như trước", !!v2.querySelector('.mw-done[data-task="T1"]') && /Cần xử lý hôm nay/.test(v2.textContent) && !v2.querySelector(".pmr-qa-in"));
  b.w.close();
  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
