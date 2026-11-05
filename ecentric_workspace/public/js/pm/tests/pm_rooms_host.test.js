/* pm_rooms_host.test.js — host /pm (pm_app.html) gắn Phòng họp: route #rooms + tab "Phòng họp" trong #schedule.
 * Chạy: NODE_PATH=<node_modules có jsdom> node ecentric_workspace/public/js/pm/tests/pm_rooms_host.test.js
 * Kiểm: #rooms tải lười pm_rooms.css cùng ?v= với pm_redesign.js rồi vẽ PMRooms (mode page) + breadcrumb "Phòng họp";
 * thiếu asset -> câu đang tải, không vỡ; #schedule có tab Lịch tuần | Phòng họp, đổi tab không đổi hash, dùng cùng PMRooms
 * (mode tab); rời màn -> component dừng; không thêm thẻ <script>/<link> cố định, không Jinja. */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..", "..");
const HTML = fs.readFileSync(path.join(ROOT, "pm", "frontend", "pm_app.html"), "utf8");
/* phiên bản asset do finalize đóng dấu: đọc từ thẻ pm_redesign.js, không ghi cứng */
const VER = (HTML.match(/pm_redesign\.js\?v=([0-9a-f]{10})/) || [])[1];
const RJS = fs.readFileSync(path.join(ROOT, "public", "js", "pm", "pm_rooms.js"), "utf8");
const res = [], ok = (n, c, x) => res.push({ n, c: !!c, x });
const tick = ms => new Promise(r => setTimeout(r, ms || 30));
const D0 = "2026-11-05";
const DAY = { date: D0, now: D0 + " 10:15:00", sync_on: true, rooms: ["5.1", "1.1", "1.2", "1.3", "5.2"].map((c, i) => ({ name: "r" + i, code: c, title: "P" + i, label: c + " - P" + i, bookings: [] })) };
function boot(hash, withAsset) {
  const errors = [], calls = [], vc = new VirtualConsole();
  vc.on("error", (...a) => errors.push(a.map(String).join(" ")));
  vc.on("jsdomError", e => { if (!/Could not load (script|link)|Not implemented/.test(String(e && e.message))) errors.push("jsdomError " + (e && e.message)); });
  const dom = new JSDOM(HTML, { url: "https://team.ecentric.vn/pm" + hash, runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc, beforeParse(w) {
    w.document.cookie = "user_id=me%40ecentric.vn; path=/";
    w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: {} }), text: () => Promise.resolve("{}") });
    w.frappe = { csrf_token: "x", call: o => { calls.push(o.method.replace("ecentric_workspace.pm.api.", "")); setTimeout(() => {
      const m = o.method.replace("ecentric_workspace.pm.api.", "");
      const msg = m === "rooms.day" ? DAY : m === "rooms.mine" ? { rows: [], sync_on: true } : m === "schedule.week" ? { blocks: [], backlog: [], meetings: [] } : m === "frappe.auth.get_logged_user" ? "me@ecentric.vn" : {};
      o.callback && o.callback({ message: msg }); }, 0); } };
    w.scrollTo = () => { }; w.Element.prototype.scrollIntoView = function () { };
    if (withAsset) w.eval(RJS);   /* giả lập asset đã tải */
  } });
  return { w: dom.window, d: dom.window.document, errors, calls };
}
(async () => {
  let b = boot("#rooms", true); await tick(200);
  const v = b.d.getElementById("pm-view");
  ok("#rooms → PMRooms mode page trong #pm-view (5 phòng + 3 ô tóm tắt + Phòng bạn đã đặt)", v.querySelectorAll(".pmrm--page .pmrm-row").length === 5 && v.querySelectorAll(".pmrm-tile").length === 3 && /Phòng bạn đã đặt/.test(v.textContent));
  ok("#rooms: tiêu đề bằng head() của host, hash giữ #rooms, breadcrumb Phòng họp", (v.querySelector(".pm-head h1") || {}).textContent === "Phòng họp" && b.w.location.hash === "#rooms" && (b.d.getElementById("pm-crumb") ? b.d.getElementById("pm-crumb").textContent === "Phòng họp" : true));
  const css = b.d.querySelector("link[data-pmrm-css]");
  ok("CSS tải lười đúng 1 lần, cùng ?v= với pm_redesign.js", css && css.getAttribute("href") === "/assets/ecentric_workspace/css/pm/pm_rooms.css?v=" + VER && b.d.querySelectorAll("link[data-pmrm-css]").length === 1);
  ok("host truyền api của trang (frappe.call): gọi rooms.day + rooms.mine", b.calls.indexOf("rooms.day") >= 0 && b.calls.indexOf("rooms.mine") >= 0);
  const ctl = b.w._pmRoomsCtl;
  b.w.location.hash = "#mywork"; await tick(120);
  ok("rời #rooms → component dừng (destroy), không còn gốc .pmrm", ctl && ctl._state.dead === true && !b.w._pmRoomsCtl && !b.d.querySelector(".pmrm"));
  ok("không lỗi console (#rooms)", b.errors.length === 0, b.errors.slice(0, 2).join(" | "));
  b.w.close();

  b = boot("#rooms", false); await tick(120);
  ok("#rooms khi asset chưa tải → 'Đang tải lịch phòng họp…', script pm_rooms.js cùng ?v=, không vỡ", /Đang tải lịch phòng họp/.test(b.d.getElementById("pm-view").textContent) && !!b.d.querySelector('script[src="/assets/ecentric_workspace/js/pm/pm_rooms.js?v=' + VER + '"]'));
  b.w.close();

  b = boot("#schedule", true); await tick(200);
  const tabs = () => Array.from(b.d.querySelectorAll(".sch-tabs [role=tab]"));
  ok("#schedule: tablist Lịch tuần | Phòng họp, mặc định Lịch tuần, lưới tuần cũ vẫn vẽ", tabs().map(t => t.textContent).join("|") === "Lịch tuần|Phòng họp" && tabs()[0].getAttribute("aria-selected") === "true" && !!b.d.getElementById("sch-days") && b.calls.indexOf("schedule.week") >= 0);
  b.d.getElementById("sch-tab-rooms").click(); await tick(150);
  ok("bấm tab Phòng họp → cùng PMRooms (mode tab) trong #sch-rooms, hash vẫn #schedule, focus ở tab", !!b.d.querySelector("#sch-rooms .pmrm--tab") && b.d.querySelectorAll("#sch-rooms .pmrm-row").length === 5 && b.w.location.hash === "#schedule" && b.d.activeElement === b.d.getElementById("sch-tab-rooms") && b.d.getElementById("sch-tab-rooms").getAttribute("aria-selected") === "true");
  const n0 = b.calls.filter(x => x === "schedule.week").length;
  b.d.getElementById("sch-tab-cal").click(); await tick(150);
  ok("bấm Lịch tuần → về lưới tuần (tải lại schedule.week), PMRooms dừng", !!b.d.getElementById("sch-days") && b.calls.filter(x => x === "schedule.week").length === n0 + 1 && !b.d.querySelector(".pmrm") && !b.w._pmRoomsCtl);
  b.d.querySelector(".sch-tabs").dispatchEvent(new b.w.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })); await tick(150);
  ok("phím mũi tên trên tablist đổi tab", !!b.d.querySelector("#sch-rooms .pmrm--tab"));
  ok("không lỗi console (#schedule)", b.errors.length === 0, b.errors.slice(0, 2).join(" | "));
  b.w.close();

  ok("pm_app.html: không thêm <script src>/<link> cố định cho pm_rooms, đúng 2 dấu ?v=, không Jinja", !!VER && !/<(script|link)[^>]+pm_rooms/.test(HTML) && (HTML.split("?v=" + VER).length - 1) === 2 && !/\{\{|\{%|\{#/.test(HTML) && (HTML.match(/hd==="new"/g) || []).length === 1);

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
