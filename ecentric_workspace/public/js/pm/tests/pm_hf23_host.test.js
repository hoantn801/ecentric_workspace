/* pm_hf23_host.test.js — hotfix 23 (PO 27/11/2026), các màn host của /pm (pm_app.html) theo mockup v2:
 *   - Chi tiết dự án: không nút "← Dự án"; nhãn tiếng Việt (không "High", không "2026-11-27 15:00", "N việc con"); việc cha đã
 *     xong gom "N việc đã xong" (bấm mở); 10 việc cha / trang (việc con đi kèm); bấm cả dòng -> openTask có nav theo thứ tự đang
 *     hiện; menu ⋯ chỉ khi can_manage (Hoàn thành / Huỷ / màu / Xoá khi can_delete) -> projects.set_status / set_color.
 *   - Lịch & phòng họp: lớp bật/tắt (Việc / Teams / Phòng đã đặt), T2–T6 + "Hiện cuối tuần", mở sẵn 8:00 + "Cả ngày",
 *     bấm ô trống -> popover 2 lựa chọn: Họp + đặt phòng (phòng trống đúng giờ, gửi rooms.book qua hộp đặt phòng PMRooms) /
 *     Giờ làm một việc (schedule.place).
 *   - Timesheet: số kiểu VN, bỏ chữ "native Timesheet", bộ lọc tự áp dụng (không nút Lọc / Xoá lọc), chọn nhanh khoảng,
 *     bảng theo người phân trang phía server, Xuất Excel gọi timesheet.export_xlsx cùng bộ lọc (có lỗi -> toast).
 * Chạy: NODE_PATH=<node_modules có jsdom> node ecentric_workspace/public/js/pm/tests/pm_hf23_host.test.js */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..", "..");
const HTML = fs.readFileSync(path.join(ROOT, "pm", "frontend", "pm_app.html"), "utf8");
const PMRJS = fs.readFileSync(path.join(ROOT, "public", "js", "pm", "pm_redesign.js"), "utf8");
const RJS = fs.readFileSync(path.join(ROOT, "public", "js", "pm", "pm_rooms.js"), "utf8");
const USER = "me@ecentric.vn", res = [], ok = (n, c, x) => res.push({ n, c: !!c, x });
const tick = ms => new Promise(r => setTimeout(r, ms || 30));
const p2 = n => (n < 10 ? "0" : "") + n;
const ymd = d => d.getFullYear() + "-" + p2(d.getMonth() + 1) + "-" + p2(d.getDate());
const off = n => { const d = new Date(); d.setDate(d.getDate() + n); return ymd(d); };
const monday = (() => { const t = new Date(); t.setHours(0, 0, 0, 0); t.setDate(t.getDate() - ((t.getDay() + 6) % 7)); return t; })();
const wd = (i, hm) => { const d = new Date(monday); d.setDate(d.getDate() + i); return ymd(d) + " " + hm + ":00"; };

/* ---- dữ liệu giả ---- */
const TASKS = [];
for (let i = 1; i <= 12; i++) TASKS.push({ name: "A" + i, subject: "Việc mở " + i, workflow_state: i === 2 ? "In Progress" : "To Do", priority: i === 1 ? "High" : "Medium", exp_end_date: off(i === 1 ? -2 : i), pm_end_time: i === 1 ? "15:00:00" : null, _assign: JSON.stringify(i % 2 ? [USER] : []), project: "P1" });
TASKS.push({ name: "K1", subject: "Con 1", workflow_state: "To Do", parent_task: "A1", project: "P1", _assign: "[]" }, { name: "K2", subject: "Con 2", workflow_state: "Done", parent_task: "A1", project: "P1", _assign: "[]" });
for (let i = 1; i <= 3; i++) TASKS.push({ name: "D" + i, subject: "Đã xong " + i, workflow_state: "Done", priority: "High", exp_end_date: off(-10), project: "P1", _assign: "[]" });
const DETAIL = can => ({ project: { name: "P1", project_name: "Affiliate Internal", status: "Open", ec_manager: "boss@ecentric.vn", ec_department: "Service - EC", color_key: "violet" },
  total: TASKS.length, risk: { active: 13, overdue: 1, review: 0, no_assignee: 6, no_due: 1, completed: 4 }, progress: 22, health: "hi", health_text: "1 việc quá hạn trên 13 việc đang mở",
  can_manage: can, can_delete: false });
const WEEK = { blocks: [{ name: "B1", task: "A1", start: wd(1, "10:00"), end: wd(1, "11:00"), state: "Dự kiến" }, { name: "B2", task: "A2", start: wd(2, "06:00"), end: wd(2, "07:00"), state: "Dự kiến" }],
  backlog: [{ name: "A3", subject: "Việc mở 3", exp_end_date: off(-1) }, { name: "A4", subject: "Việc mở 4" }], subjects: { A1: "Việc mở 1", A2: "Việc mở 2" }, meta: {},
  meetings: [{ id: "EV-ROOM", subject: "Họp phòng", start: wd(0, "09:00"), end: wd(0, "10:00"), is_organizer: true, location: "1.1 - Hoà" },
    { id: "EV-T", subject: "Daily", start: wd(3, "09:00"), end: wd(3, "09:30"), is_organizer: false, response: "accepted" }] };
const DAYD = date => ({ date, now: off(0) + " 08:00:00", sync_on: true, rooms: [
  { name: "R1", code: "1.1", label: "1.1 - Hoà", capacity: 8, bookings: [] },
  { name: "R2", code: "1.2", label: "1.2 - Thổ", capacity: 6, bookings: [{ start: date + " 09:30:00", end: date + " 10:30:00", who: "Ai đó", uid: "u1" }] }] });
const REPORT = a => ({ rows: [{ owner: USER, task: "A1", project: "P1", hours: 1307.62, from_time: off(0) + " 09:00:00" }], total_hours: 1307.62, by_day: { [off(0)]: 1307.62 },
  by_project: [{ project: "P1", project_name: "Affiliate Internal", hours: 1307.62 }], top_tasks: [{ task: "A1", subject: "Việc mở 1", hours: 1307.62 }],
  people: [{ user: USER, full_name: "Tôi Đây", hours: 1307.62, logs: 1, days: 1, top_tasks: [{ task: "A1", subject: "Việc mở 1", hours: 1307.62 }] }], people_total: 9, _args: a });

function api(m, a, o) {
  m = m.replace("ecentric_workspace.pm.api.", "");
  const R = {
    "frappe.auth.get_logged_user": USER, "timer.get_active": { active: false }, "dashboard.control_center": { is_leader: false },
    "projects.detail": DETAIL(o.can !== false), "tasks.list": { rows: TASKS, user_names: { [USER]: "Tôi Đây", "boss@ecentric.vn": "Hương Lê" } },
    "projects.set_status": { name: "P1", status: a && a.status }, "projects.set_color": { name: "P1", color_key: a && a.color_key },
    "schedule.week": WEEK, "rooms.mine": { rows: [{ event_id: "EV-ROOM", label: "1.1 - Hoà", room: "R1", start: wd(0, "09:00"), end: wd(0, "10:00"), state: "accepted" }], sync_on: true },
    "rooms.day": DAYD((a && a.date) || off(0)), "rooms.book": { event_id: "NEW1", state: "pending", start: a && a.start, end: a && a.end, room: a && a.room },
    "rooms.booking_state": { state: "pending" }, "schedule.place": { name: "B9" }, "assignment.list_assignable": { rows: [] },
    "timesheet.report": REPORT(a), "projects.list": { rows: [{ name: "P1", project_name: "Affiliate Internal" }] }, "tasks.get": { task: { name: "A1", subject: "Việc mở 1", workflow_state: "To Do" } } };
  return R[m] === undefined ? {} : R[m];
}
function boot(hash, o) {
  o = o || {};
  const errors = [], calls = [], fetches = [], vc = new VirtualConsole();
  vc.on("error", (...a) => errors.push(a.map(String).join(" ")));
  vc.on("jsdomError", e => { if (!/Could not load (script|link)|Not implemented/.test(String(e && e.message))) errors.push("jsdomError " + (e && e.message)); });
  const dom = new JSDOM(HTML, { url: "https://team.ecentric.vn/pm" + hash, runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc, beforeParse(w) {
    w.document.cookie = "user_id=" + encodeURIComponent(USER) + "; path=/";
    w.fetch = (url, init) => { fetches.push({ url: String(url), init }); const bad = o.xlsxFail;
      return Promise.resolve({ ok: !bad, status: bad ? 403 : 200, headers: { get: k => (/content-type/i.test(k) ? (bad ? "application/json" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") : (/disposition/i.test(k) ? 'attachment; filename="timesheet_x.xlsx"' : null)) },
        json: () => Promise.resolve({}), text: () => Promise.resolve(bad ? JSON.stringify({ exc_type: "PermissionError", _server_messages: JSON.stringify([JSON.stringify({ message: "Không có quyền xuất" })]) }) : ""),
        blob: () => Promise.resolve(new w.Blob(["x"])) }); };
    w.URL.createObjectURL = () => "blob:x"; w.URL.revokeObjectURL = () => { };
    w.frappe = { csrf_token: "x", call: x => { const m = x.method.replace("ecentric_workspace.pm.api.", ""); calls.push({ m, a: x.args || {} }); setTimeout(() => x.callback && x.callback({ message: api(x.method, x.args, o) }), 0); } };
    w.scrollTo = () => { }; w.Element.prototype.scrollIntoView = function () { };
    const gb = w.Element.prototype.getBoundingClientRect;
    w.Element.prototype.getBoundingClientRect = function () { if (this.id === "sch-days") return { left: 0, top: 0, width: 500, height: 528, right: 500, bottom: 528, x: 0, y: 0 }; return gb.call(this); };
    w.eval(PMRJS); w.eval(RJS);
  } });
  return { w: dom.window, d: dom.window.document, errors, calls, fetches };
}
const txt = e => (e ? e.textContent.replace(/\s+/g, " ").trim() : "");
const mouse = (b, el, type, x, y) => el.dispatchEvent(new b.w.MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 }));

(async () => {
  /* ---------- Chi tiết dự án ---------- */
  let b = boot("#project/P1"); await tick(250);
  let v = b.d.getElementById("pm-view");
  ok("chi tiết dự án: không còn nút '← Dự án' (giữ breadcrumb), đầu trang có ô thư mục màu dự án + tên", !b.d.getElementById("pm-back") && !!v.querySelector(".pmh-pd-head .pmh-tile[style*='--pc:#6941c6']") && /Affiliate Internal/.test(txt(v.querySelector(".pmh-pd-head h1"))));
  ok("nhãn sức khoẻ có giải thích (health_text) + thanh %", /Rủi ro cao/.test(txt(v.querySelector(".pmh-risk"))) && /1 việc quá hạn trên 13/.test(txt(v.querySelector(".pmh-risk .pmh-tip"))) && /22%/.test(txt(v.querySelector(".pmh-bar"))));
  ok("số tổng là MỘT dải có vạch ngăn, bấm để lọc", v.querySelectorAll(".pmh-kpis > .pmh-kpi[data-card]").length === 6);
  const tbl = () => v.querySelector("#pd-ttbl");
  const T = txt(tbl());
  ok("bảng việc: nhãn tiếng Việt, không 'High', không '2026-..-.. 15:00', có 'Cao' + tờ lịch hạn", !/\bHigh\b/.test(T) && !/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(T) && /Cao/.test(T) && !!tbl().querySelector(".pmr-dt, .pmh-dt"));
  ok("'2 việc con' (không 'nv con'), viên trạng thái, người nhận có avatar + tên", /2 việc con/.test(T) && !/nv con/.test(T) && !!tbl().querySelector(".pmh-st--prog") && !!tbl().querySelector(".pmh-who .pmh-av") && /Tôi Đây/.test(T));
  const parents = () => Array.from(tbl().querySelectorAll(".pmh-r[data-task]")).map(r => r.getAttribute("data-task"));
  ok("10 việc cha / trang, việc con đi kèm việc cha (A1, K1, K2, A2 …)", parents().filter(n => /^A/.test(n)).length === 10 && parents().slice(0, 3).join() === "A1,K1,K2" && !!tbl().querySelector('[data-pgkey="pd"]'));
  ok("việc cha đã xong gom 1 dòng '3 việc đã xong' (chưa hiện D1..D3)", /Xem 3 việc đã xong/.test(txt(tbl().querySelector("#pd-showdone"))) && !parents().some(n => /^D/.test(n)));
  tbl().querySelector("#pd-showdone").click(); await tick(30);
  ok("bấm 'việc đã xong' → mở ra D1..D3", ["D1", "D2", "D3"].every(n => parents().indexOf(n) >= 0) && /Ẩn 3 việc đã xong/.test(txt(tbl().querySelector("#pd-showdone"))));
  const pgb = tbl().querySelector('[data-pgkey="pd"] [data-act="pg"][data-p="2"]'); pgb.click(); await tick(30);
  ok("trang 2: còn 2 việc cha (A11, A12)", parents().filter(n => /^A/.test(n)).join() === "A11,A12");
  let got = null; const orig = b.w.PMR.openTask; b.w.PMR.openTask = (n, o2) => { got = { n, o2 }; return null; };
  tbl().querySelector('.pmh-r[data-task="A11"] .pmh-tt').click(); await tick(30);
  ok("bấm cả dòng → openTask (hash #task/A11) kèm nav theo thứ tự đang hiện", !!got && got.n === "A11" && got.o2 && got.o2.nav && got.o2.nav.names.indexOf("A11") === 0 && got.o2.nav.names.indexOf("D1") > 0 && b.w.location.hash === "#task/A11");
  b.w.PMR.openTask = orig;
  ok("menu ⋯ (can_manage): Hoàn thành / Huỷ / màu, KHÔNG có Xoá khi can_delete=false", !!b.d.getElementById("pd-more") && !!v.querySelector('#pd-menu [data-s="Completed"]') && !!v.querySelector('#pd-menu [data-s="Cancelled"]') && v.querySelectorAll("#pd-menu .pmh-sw").length === 8 && !v.querySelector('#pd-menu [data-pdact="delete"]') && !!b.d.getElementById("pd-edit"));
  b.d.getElementById("pd-more").click(); await tick(10);
  ok("bấm ⋯ → menu hiện, aria-expanded", !b.d.getElementById("pd-menu").hidden && b.d.getElementById("pd-more").getAttribute("aria-expanded") === "true");
  v.querySelector('#pd-menu [data-s="Completed"]').click(); await tick(60);
  ok("Đánh dấu hoàn thành → projects.set_status(P1, Completed)", b.calls.some(c => c.m === "projects.set_status" && c.a.name === "P1" && c.a.status === "Completed"));
  await tick(150); v = b.d.getElementById("pm-view");
  b.d.getElementById("pd-more").click(); v.querySelector('#pd-menu .pmh-sw[data-c="teal"]').click(); await tick(60);
  ok("chọn màu → projects.set_color(P1, teal)", b.calls.some(c => c.m === "projects.set_color" && c.a.color_key === "teal"));
  await tick(150); v = b.d.getElementById("pm-view");
  v.querySelector('#pd-health [data-card="overdue"]').click(); await tick(150);
  ok("bấm số 'Quá hạn' → lọc danh sách phẳng (chỉ A1)", parents().join() === "A1" && v.querySelector('#pd-health [data-card="overdue"]').getAttribute("aria-pressed") === "true");
  ok("không lỗi console (chi tiết dự án)", b.errors.length === 0, b.errors.slice(0, 2).join(" | "));
  b.w.close();

  b = boot("#project/P1", { can: false }); await tick(250);
  ok("!can_manage → không nút Sửa, không menu ⋯ (vẫn Tạo việc)", !b.d.getElementById("pd-more") && !b.d.getElementById("pd-menu") && !b.d.getElementById("pd-edit") && !!b.d.getElementById("pm-newt"));
  b.w.close();

  /* ---------- Lịch & phòng họp ---------- */
  b = boot("#schedule"); await tick(300);
  v = b.d.getElementById("pm-view");
  ok("màn gộp: tiêu đề 'Lịch & phòng họp', lớp Việc / Teams / Phòng đã đặt đều bật", txt(v.querySelector(".pm-head h1")) === "Lịch & phòng họp" && ["task", "meet", "room"].every(k => (v.querySelector('[data-layer="' + k + '"]') || {}).getAttribute && v.querySelector('[data-layer="' + k + '"]').getAttribute("aria-pressed") === "true"));
  ok("mặc định T2–T6 (5 cột) và mở sẵn 8:00–19:00 (không dải 0h–7h)", v.querySelectorAll(".sch-hdr > div").length === 6 && v.querySelectorAll("#sch-days .sch-col").length === 5 && /^09:00/.test(txt(v.querySelector(".sch-hlab"))) && parseInt(b.d.getElementById("sch-body").style.height, 10) === 11 * 48);
  ok("khối việc 6:00 nằm ngoài khung → báo 'Có 1 lịch ngoài khung' + nút xem cả ngày", /Có 1 lịch ngoài khung/.test(txt(v.querySelector(".sch-hidnote"))) && v.querySelectorAll(".sch-blk").length === 1);
  ok("cuộc họp có id trong rooms.mine = Phòng đã đặt (xanh), cuộc khác = Teams", !!v.querySelector(".sch-mtg--room") && !!v.querySelector(".sch-mtg--meet") && b.calls.some(c => c.m === "rooms.mine"));
  ok("Chưa xếp lịch là một khối, mỗi việc một dòng có ô biểu tượng màu theo hạn", v.querySelectorAll(".sch-side.pmh-card .sch-pool-i").length === 2 && !!v.querySelector(".sch-pool-i--late .pmh-tile--late"));
  v.querySelector('[data-layer="task"]').click(); await tick(20); v = b.d.getElementById("pm-view");
  ok("tắt lớp Việc → ẩn khối việc, lưu lựa chọn", v.querySelectorAll(".sch-blk").length === 0 && JSON.parse(b.w.localStorage.getItem("pm_sch_layers")).task === false);
  v.querySelector('[data-layer="meet"]').click(); await tick(20); v = b.d.getElementById("pm-view");
  ok("tắt lớp Teams → còn họp phòng, ẩn họp Teams", !v.querySelector(".sch-mtg--meet") && !!v.querySelector(".sch-mtg--room"));
  v.querySelector('[data-layer="task"]').click(); await tick(20); v = b.d.getElementById("pm-view"); v.querySelector('[data-layer="meet"]').click(); await tick(20); v = b.d.getElementById("pm-view");
  b.d.getElementById("sch-wkend").click(); await tick(20); v = b.d.getElementById("pm-view");
  ok("'Hiện cuối tuần' → 7 cột", v.querySelectorAll("#sch-days .sch-col").length === 7 && b.d.getElementById("sch-wkend").getAttribute("aria-checked") === "true");
  b.d.getElementById("sch-fullday").click(); await tick(20); v = b.d.getElementById("pm-view");
  ok("'Cả ngày' → 0h–24h, khối 6:00 hiện ra, hết ghi chú ngoài khung", parseInt(b.d.getElementById("sch-body").style.height, 10) === 24 * 48 && v.querySelectorAll(".sch-blk").length === 2 && !v.querySelector(".sch-hidnote"));
  b.d.getElementById("sch-wkend").click(); await tick(10); b.d.getElementById("sch-fullday").click(); await tick(20); v = b.d.getElementById("pm-view");
  /* tuần sau (để giờ chọn chưa qua), bấm ô trống: T3 (cột 2 / 5, rộng 500) lúc 10:00 (y = 2 * 48) */
  b.d.getElementById("sch-next").click(); await tick(200); v = b.d.getElementById("pm-view");
  let days = b.d.getElementById("sch-days"), col = days.querySelectorAll(".sch-col")[1];
  mouse(b, col, "mousedown", 150, 96); mouse(b, b.d, "mouseup", 150, 96); await tick(300);
  let pop = b.d.querySelector(".sch-slotpop");
  ok("bấm ô trống → popover 2 lựa chọn (Họp + đặt phòng | Giờ làm một việc) + khung mới 10:00–11:00", !!pop && pop.querySelectorAll('[data-sp="kind"]').length === 2 && /Họp \+ đặt phòng/.test(txt(pop)) && /Giờ làm một việc/.test(txt(pop)) && /10:00–11:00/.test(txt(pop.querySelector("h5"))) && !!days.querySelector(".sch-draft"));
  ok("Họp: danh sách phòng đúng khung giờ (1.1 trống, 1.2 bận 9:30–10:30) qua rooms.day", !!pop.querySelector('.sch-room[data-r="R1"]:not([disabled])') && !!pop.querySelector('.sch-room[data-r="R2"][disabled]') && pop.querySelector('.sch-room[data-r="R1"]').getAttribute("aria-checked") === "true");
  pop.querySelector('[data-sp="ok"]').click(); await tick(20);
  ok("thiếu tiêu đề → báo lỗi trong popover, không gọi rooms.book", /Ghi tiêu đề/.test(txt(pop.querySelector(".sch-sp-err"))) && !b.calls.some(c => c.m === "rooms.book"));
  const ti = pop.querySelector("#sp-title"); ti.value = "Review kế hoạch"; ti.dispatchEvent(new b.w.Event("input", { bubbles: true }));
  const wh = pop.querySelector("#sp-who"); wh.value = "khach@ngoai.com"; wh.dispatchEvent(new b.w.Event("input", { bubbles: true }));
  pop.querySelector('[data-sp="ok"]').click(); await tick(300);
  const bk = b.calls.find(c => c.m === "rooms.book");
  ok("Đặt + gửi lời mời → CÙNG luồng PMRooms (rooms.book: phòng R1, giờ 10:00–11:00 ngày T3, tiêu đề, người mời, txn)", !!bk && bk.a.room === "R1" && bk.a.start === wd(8, "10:00") && bk.a.end === wd(8, "11:00") && bk.a.subject === "Review kế hoạch" && /khach@ngoai\.com/.test(bk.a.attendees) && /^erp-/.test(bk.a.txn || "") && !b.d.querySelector(".sch-slotpop"));
  days = b.d.getElementById("sch-days"); col = days.querySelectorAll(".sch-col")[3];
  mouse(b, col, "mousedown", 350, 144); mouse(b, b.d, "mousemove", 350, 240); mouse(b, b.d, "mouseup", 350, 240); await tick(100);
  pop = b.d.querySelector(".sch-slotpop");
  ok("kéo ô trống → khung dài hơn (11:00–13:00)", !!pop && /11:00–13:00/.test(txt(pop.querySelector("h5"))));
  pop.querySelector('[data-sp="kind"][data-k="work"]').click(); await tick(20);
  ok("Giờ làm một việc → chọn việc trong danh sách chưa xếp", !!pop.querySelector("#sp-task option[value='A3']") && /Xếp vào lịch/.test(txt(pop.querySelector('[data-sp="ok"]'))));
  pop.querySelector('[data-sp="ok"]').click(); await tick(100);
  const pl = b.calls.find(c => c.m === "schedule.place");
  ok("Xếp vào lịch → schedule.place(task, 11:00–13:00 T5)", !!pl && pl.a.task === "A3" && pl.a.start === wd(10, "11:00") && pl.a.end === wd(10, "13:00"));
  ok("không lỗi console (lịch)", b.errors.length === 0, b.errors.slice(0, 2).join(" | "));
  b.w.close();

  /* ---------- Timesheet ---------- */
  b = boot("#timesheet"); await tick(250);
  v = b.d.getElementById("pm-view");
  const tv = txt(v);
  ok("số giờ kiểu VN (1.307,6 giờ), không 1307.62, không chữ 'native Timesheet'", /1\.307,6 giờ/.test(tv) && !/1307\.6/.test(tv) && !/native Timesheet/.test(tv));
  ok("không còn nút Lọc / Xoá lọc; có chọn nhanh Tuần này / Tháng này / Tháng trước / Tuỳ chọn (mặc định Tháng này)", !b.d.getElementById("ts-apply") && !b.d.getElementById("ts-clear") && v.querySelectorAll("[data-tsr]").length === 4 && v.querySelector('[data-tsr="month"]').getAttribute("aria-pressed") === "true");
  const r0 = b.calls.filter(c => c.m === "timesheet.report");
  ok("báo cáo gọi kèm khoảng tháng này + people_len 7", r0.length === 1 && r0[0].a.from_date === off(0).slice(0, 8) + "01" && r0[0].a.people_len === 7 && r0[0].a.people_start === 0);
  ok("3 khối: giờ mỗi ngày (cột), giờ theo dự án (thanh có tên), bảng theo người có TÊN việc", !!v.querySelector(".pmh-cols s") && /Affiliate Internal/.test(txt(v.querySelector(".pmh-hb"))) && /Việc mở 1/.test(txt(v.querySelector("#ts-ppl"))) && !/TASK-|\bA1\b/.test(txt(v.querySelector("#ts-ppl table"))));
  const us = b.d.getElementById("ts-user"); us.value = USER; us.dispatchEvent(new b.w.Event("change", { bubbles: true })); await tick(150);
  ok("đổi Người → tự áp dụng (gọi lại report với user), không cần nút", b.calls.filter(c => c.m === "timesheet.report").some(c => c.a.user === USER));
  b.d.querySelector('[data-tsr="last"]').click(); await tick(150);
  const lm = new Date(); const a0 = new Date(lm.getFullYear(), lm.getMonth() - 1, 1), b0 = new Date(lm.getFullYear(), lm.getMonth(), 0);
  ok("Tháng trước → from/to của tháng trước, giữ bộ lọc người", b.calls.filter(c => c.m === "timesheet.report").some(c => c.a.from_date === ymd(a0) && c.a.to_date === ymd(b0) && c.a.user === USER));
  b.d.querySelector('#ts-ppl [data-act="pg"][data-p="2"]').click(); await tick(150);
  ok("bảng theo người trang 2 → report people_start=7 (phân trang phía server)", b.calls.filter(c => c.m === "timesheet.report").some(c => c.a.people_start === 7));
  b.d.getElementById("ts-xlsx").click();
  ok("Xuất Excel đang chạy → nút khoá + 'Đang xuất…'", b.d.getElementById("ts-xlsx").disabled && /Đang xuất/.test(txt(b.d.getElementById("ts-xlsx"))));
  await tick(120);
  const fx = b.fetches.find(f => /timesheet\.export_xlsx/.test(f.url));
  ok("Xuất Excel → GET timesheet.export_xlsx cùng bộ lọc (user, from_date, to_date), tải file, toast", !!fx && /user=me%40ecentric\.vn/.test(fx.url) && fx.url.indexOf("from_date=" + ymd(a0)) > 0 && !b.d.getElementById("ts-xlsx").disabled && /Đã xuất timesheet_x\.xlsx/.test(txt(b.d.getElementById("pm-toast"))));
  ok("không lỗi console (timesheet)", b.errors.length === 0, b.errors.slice(0, 2).join(" | "));
  b.w.close();
  b = boot("#timesheet", { xlsxFail: true }); await tick(250);
  b.d.getElementById("ts-xlsx").click(); await tick(150);
  ok("Xuất Excel lỗi quyền → toast lỗi có lời của server, nút mở lại", /Chưa xuất được Excel: Không có quyền xuất/.test(txt(b.d.getElementById("pm-toast"))) && !b.d.getElementById("ts-xlsx").disabled);
  b.w.close();

  ok("pm_app.html: không thêm <script id=\"ec-…\">/<style id=\"ec-…\"> mới, không Jinja, không ký tự ▾ trong bảng dự án",
    (HTML.match(/<(script|style)[^>]+id="ec-/g) || []).length === 0 && !/\{\{|\{%|\{#/.test(HTML) && !/pd-tcaret[^"]*"[^>]*>▾/.test(HTML));

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
