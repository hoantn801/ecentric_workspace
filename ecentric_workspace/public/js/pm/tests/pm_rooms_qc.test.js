/* pm_rooms_qc.test.js — Phòng họp: lỗi QC 05/11/2026 (mỗi lỗi một test tái hiện). Chạy: NODE_PATH=<node_modules có jsdom> node pm_rooms_qc.test.js
 * 1. Chuỗi vừa đặt: khi mine() đã trả các buổi (series_id = id chuỗi) thì bản tạm "chờ phòng nhận" phải biến mất
 *    (trước: khối + dòng bị nhân đôi mãi mãi, ô "Bạn đặt hôm nay" đếm sai).
 * 2. Dòng tạm của chuỗi vừa đặt mang id seriesMaster: chỉ có "Huỷ cả chuỗi" / sửa cả chuỗi (trước: "Huỷ buổi này" huỷ cả chuỗi,
 *    "Chỉ buổi này" dời cả chuỗi).
 * 3. Giới hạn đặt trước 180 ngày tính từ HÔM NAY (phòng Exchange), cả ngày họp lẻ lẫn ngày kết thúc lặp.
 * 4. Lặp hằng tháng ngày 29–31: tháng ngắn rơi vào ngày cuối tháng (như Outlook); hằng ngày 180 ngày = 181 buổi (không cắt ở 130).
 * 5. join_url không phải https -> không thành link (chặn javascript:). */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_rooms.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "css", "pm", "pm_rooms.css"), "utf8");
const res = [];
const ok = (n, c, x) => res.push({ n, c: !!c, x });
const tick = ms => new Promise(r => setTimeout(r, ms || 0));
const flush = async () => { for (let i = 0; i < 6; i++) await tick(0); };
const D0 = "2026-11-05";   /* thứ Năm */
const add = (d, n) => { const t = new Date(Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10) + n)); return t.toISOString().slice(0, 10); };

function setup(h) {
  const dom = new JSDOM("<!doctype html><body><div id=ec-pm-root><div id=v></div></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#rooms", pretendToBeVisual: true });
  const w = dom.window, calls = [], toasts = [], errs = [];
  w.console.error = (...a) => errs.push(a.join(" "));
  w.fetch = () => Promise.reject(new Error("no network"));
  w.eval(JS);
  const H = Object.assign({
    "rooms.day": a => ({ date: a.date || D0, now: D0 + " 10:15:00", sync_on: true, rooms: [
      { name: "cabin", code: "5.2", title: "Cabin", label: "5.2 - Cabin", bookings: [] },
      { name: "phong", code: "5.1", title: "Phong", label: "5.1 - Phong", bookings: [] }] }),
    "rooms.mine": () => ({ sync_on: true, rows: [] }),
    "rooms.booking_state": () => ({ state: "pending" }),
    "rooms.cancel": () => ({ ok: true, state: "cancelled", scope: "series" }),
    "rooms.update": a => ({ ok: true, event_id: a.event_id, scope: a.scope, room: "cabin", label: "5.2 - Cabin", start: a.start, end: a.end, state: "pending" }),
    "assignment.list_assignable": () => ({ rows: [] })
  }, h || {});
  const api = (method, args) => {
    const m = method.replace("ecentric_workspace.pm.api.", "");
    calls.push({ m, a: args });
    try { const fn = H[m]; if (!fn) return Promise.reject(new Error("no " + m)); return Promise.resolve(fn(args || {})); } catch (e) { return Promise.reject(e); }
  };
  const ctl = w.PMRooms.render(w.document.getElementById("v"), { api, toast: (m, bad) => toasts.push({ m, bad: !!bad }), mode: "page", pollMs: [5, 5, 5, 5] });
  const $ = s => w.document.querySelector(s), $$ = s => Array.from(w.document.querySelectorAll(s));
  const lane = n => $(`.pmrm-lane[data-room="${n}"]`);
  const clickAt = (n, hhmm) => { const l = lane(n); l.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1100, height: 58, right: 1100, bottom: 58 });
    const [hh, mm] = hhmm.split(":").map(Number); l.dispatchEvent(new w.MouseEvent("click", { bubbles: true, clientX: ((hh * 60 + mm) - 480) / 660 * 1100 + 1 })); };
  const f = k => $(`.pmrm-scrim [data-f="${k}"]`);
  const setv = (k, v) => { const i = f(k); i.value = v; i.dispatchEvent(new w.Event(k === "subject" ? "input" : "change", { bubbles: true })); };
  const submit = () => $(".pmrm-scrim form").dispatchEvent(new w.Event("submit", { cancelable: true }));
  const warn = () => { const x = $(".pmrm-scrim [data-warn]"); return x && !x.hidden ? x.textContent : ""; };
  return { w, ctl, calls, toasts, errs, $, $$, lane, clickAt, f, setv, submit, warn };
}

(async () => {
  /* ---------- 1 + 2: chuỗi vừa đặt */
  let synced = false, booked = false;
  const occ = (i, d) => ({ event_id: "O" + i, uid: "uO" + i, room: "cabin", label: "5.2 - Cabin", start: d + " 16:00:00", end: d + " 17:00:00",
    subject: "Giao ban tuần", state: "accepted", join_url: "", recurring: true, series_id: "M9", guests: [] });
  let T = setup({
    "rooms.book": a => { booked = true; return { ok: true, event_id: "M9", uid: "uM9", room: a.room, label: "5.2 - Cabin", start: a.start, end: a.end, subject: a.subject, state: "pending", recurring: true, join_url: "" }; },
    "rooms.day": a => ({ date: a.date || D0, now: D0 + " 10:15:00", sync_on: true, rooms: [
      { name: "cabin", code: "5.2", title: "Cabin", label: "5.2 - Cabin", bookings: synced && (!a.date || a.date === D0) ? [{ start: D0 + " 16:00:00", end: D0 + " 17:00:00", who: "Tôi", mine: true, uid: "uO0", all_day: false }] : [] },
      { name: "phong", code: "5.1", title: "Phong", label: "5.1 - Phong", bookings: [] }] }),
    "rooms.mine": () => ({ sync_on: true, rows: synced ? [occ(0, D0), occ(1, add(D0, 7))] : [] })
  });
  await flush();
  T.clickAt("cabin", "16:00"); await flush();
  T.setv("subject", "Giao ban tuần"); T.setv("repeat", "weekly"); T.setv("until", add(D0, 7));
  T.submit(); await flush();
  ok("đặt chuỗi → gọi rooms.book (repeat=weekly)", booked && T.calls.some(x => x.m === "rooms.book" && x.a.repeat === "weekly"));
  ok("trước khi đồng bộ: 1 khối chờ + 1 dòng chuỗi", T.lane("cabin").querySelectorAll(".pmrm-blk").length === 1 && T.$$(".pmrm-mrow").length === 1);
  /* 2. dòng tạm (id = seriesMaster): chỉ Huỷ cả chuỗi */
  T.$('[data-act="cancel"][data-ev="M9"]').click(); await flush();
  ok("dòng tạm của chuỗi: không có 'Huỷ buổi này' (id là cả chuỗi)", !T.$('[data-act="cancel-yes"][data-scope="occurrence"]') && T.$('[data-act="cancel-yes"][data-scope="series"]'), T.$(".pmrm-cf") && T.$(".pmrm-cf").textContent);
  T.$('[data-act="cancel-no"]').click(); await flush();
  T.$('[data-act="edit"][data-ev="M9"]').click(); await flush();
  const occR = T.$('.pmrm-scrim [data-f="scope"][value="occurrence"]'), serR = T.$('.pmrm-scrim [data-f="scope"][value="series"]');
  ok("sửa dòng tạm của chuỗi: chỉ 'Cả chuỗi' (Chỉ buổi này tắt)", serR && serR.checked && (!occR || occR.disabled));
  T.setv("start", "16:30"); T.setv("end", "17:30"); T.submit(); await flush();
  const up = T.calls.filter(x => x.m === "rooms.update");
  ok("… lưu → update(scope=series)", up.length === 1 && up[0].a.scope === "series", up[0] && JSON.stringify(up[0].a));
  T.ctl.destroy();

  synced = false; booked = false;
  T = setup({
    "rooms.book": a => { booked = true; return { ok: true, event_id: "M9", uid: "uM9", room: a.room, label: "5.2 - Cabin", start: a.start, end: a.end, subject: a.subject, state: "pending", recurring: true, join_url: "" }; },
    "rooms.booking_state": () => { synced = true; return { state: "accepted" }; },
    "rooms.day": a => ({ date: a.date || D0, now: D0 + " 10:15:00", sync_on: true, rooms: [
      { name: "cabin", code: "5.2", title: "Cabin", label: "5.2 - Cabin", bookings: synced && (!a.date || a.date === D0) ? [{ start: D0 + " 16:00:00", end: D0 + " 17:00:00", who: "Tôi", mine: true, uid: "uO0", all_day: false }] : [] },
      { name: "phong", code: "5.1", title: "Phong", label: "5.1 - Phong", bookings: [] }] }),
    "rooms.mine": () => ({ sync_on: true, rows: synced ? [occ(0, D0), occ(1, add(D0, 7))] : [] })
  });
  await flush();
  T.clickAt("cabin", "16:00"); await flush();
  T.setv("subject", "Giao ban tuần"); T.setv("repeat", "weekly"); T.setv("until", add(D0, 7));
  T.submit(); await flush(); await tick(30); await flush();
  const blks = T.lane("cabin").querySelectorAll(".pmrm-blk");
  ok("sau khi phòng nhận + mine() có các buổi: lưới chỉ 1 khối (không nhân đôi bản tạm)", blks.length === 1, blks.length + " khối");
  ok("… danh sách: đúng 2 buổi, không còn dòng tạm M9", T.$$(".pmrm-mrow").length === 2 && !T.$('[data-ev-row="M9"]'), T.$$(".pmrm-mrow").map(r => r.getAttribute("data-ev-row")).join(","));
  ok("… ô 'Bạn đặt hôm nay' = 1 cuộc", T.$("[data-t-mine]").textContent.replace(/\s/g, "") === "1cuộc", T.$("[data-t-mine]").textContent);
  ok("… đã báo phòng nhận", T.toasts.some(t => /đã nhận/.test(t.m)));
  T.ctl.destroy();

  /* ---------- 3. giới hạn 180 ngày tính từ hôm nay */
  T = setup(); await flush();
  T.clickAt("cabin", "16:00"); await flush();
  ok("ô Ngày: max = hôm nay + 180", T.f("date").max === add(D0, 180), T.f("date").max);
  T.setv("subject", "Xa"); T.setv("date", add(D0, 190)); await flush();
  ok("ngày họp quá 180 ngày → báo, khoá nút", /180 ngày/.test(T.warn()) && T.$(".pmrm-scrim [data-submit]").disabled, T.warn());
  T.setv("date", add(D0, 30)); await flush();
  T.setv("repeat", "weekly"); await flush();
  ok("lặp: Đến ngày max = hôm nay + 180 (không phải ngày họp + 180)", T.f("until").max === add(D0, 180), T.f("until").max);
  T.setv("until", add(D0, 200)); await flush();
  ok("lặp đến quá hôm nay + 180 → báo, khoá nút", /180 ngày/.test(T.warn()) && T.$(".pmrm-scrim [data-submit]").disabled, T.warn());
  T.$('.pmrm-scrim [data-act="close"]').click(); await flush();
  T.clickAt("cabin", "16:00"); await flush();
  T.setv("subject", "Xa"); T.setv("date", add(D0, 170)); T.setv("repeat", "weekly"); await flush();
  ok("ngày mặc định 'Đến ngày' không vượt hôm nay + 180", T.f("until").value <= add(D0, 180) && !T.warn(), T.f("until").value + " / " + T.warn());
  T.ctl.destroy();

  /* ---------- 4. đếm buổi khớp server */
  const W = new JSDOM("", { runScripts: "outside-only" }).window; W.eval(JS);
  ok("hằng tháng ngày 31: tháng ngắn rơi vào ngày cuối tháng", JSON.stringify(W.PMRooms._occurrences("2026-10-31", "monthly", "2027-03-31")) ===
    JSON.stringify(["2026-10-31", "2026-11-30", "2026-12-31", "2027-01-31", "2027-02-28", "2027-03-31"]), JSON.stringify(W.PMRooms._occurrences("2026-10-31", "monthly", "2027-03-31")));
  ok("hằng ngày 180 ngày = 181 buổi (không cắt ở 130)", W.PMRooms._occurrences(D0, "daily", add(D0, 180)).length === 181);
  ok("2 tuần một lần qua năm mới", JSON.stringify(W.PMRooms._occurrences("2026-12-21", "biweekly", "2027-01-31")) === JSON.stringify(["2026-12-21", "2027-01-04", "2027-01-18"]));

  /* ---------- 5. join_url */
  T = setup({ "rooms.mine": () => ({ sync_on: true, rows: [
    { event_id: "e1", uid: "u1", room: "cabin", label: "5.2 - Cabin", start: D0 + " 15:00:00", end: D0 + " 16:00:00", subject: "A", state: "accepted", join_url: "javascript:alert(1)" },
    { event_id: "e2", uid: "u2", room: "phong", label: "5.1 - Phong", start: D0 + " 15:00:00", end: D0 + " 16:00:00", subject: "B", state: "accepted", join_url: "https://teams.microsoft.com/l/x" }] }) });
  await flush();
  ok("join_url javascript: không thành link; https vẫn là link", !T.$('[data-ev-row="e1"] a') && T.$('[data-ev-row="e2"] a[href^="https://teams"]'));
  T.ctl.destroy();

  ok("CSS: ô Ngày khác trên thanh cũng 16px trên mobile (iOS không phóng to)", /@media \(max-width:640px\)\{[^@]*\.pmrm-pick input[^}]*font-size:16px/.test(CSS));

  let bad = 0;
  res.forEach(r => { if (!r.c) bad++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - bad}/${res.length} passed`);
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
