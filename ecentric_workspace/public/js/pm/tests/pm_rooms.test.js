/* pm_rooms.test.js — Phòng họp (asset pm_rooms.js). Chạy: NODE_PATH=<node_modules có jsdom> node pm_rooms.test.js
 * API giả (không mạng): day / mine / book / booking_state / cancel / list_assignable.
 * Kiểm: đủ phòng + trạng thái lúc này, khối bận / bạn đặt / chờ phòng nhận, kiểm trùng ở client, đặt -> POST rooms.book đúng
 * tham số -> hỏi booking_state -> đổi trạng thái, lỗi server hiện đúng thông điệp, chặn bấm 2 lần, huỷ có xác nhận,
 * Esc + trả focus, Enter trên làn, phòng ROOM_NOT_FOUND / SYNC_OFF không vỡ, tải lỗi có Thử lại, chế độ tab. */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_rooms.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "css", "pm", "pm_rooms.css"), "utf8");
const res = [];
const ok = (n, c, x) => res.push({ n, c: !!c, x });
const tick = (ms) => new Promise(r => setTimeout(r, ms || 0));
const flush = async () => { for (let i = 0; i < 6; i++) await tick(0); };

const D0 = "2026-11-05";
const bk = (s, e, who, extra) => Object.assign({ start: D0 + " " + s + ":00", end: D0 + " " + e + ":00", who, mine: false, uid: "u-" + who + s, all_day: false }, extra || {});
function dayData(date) {
  const today = !date || date === D0;
  return {
    date: date || D0, now: D0 + " 10:15:00", sync_on: true,
    rooms: [
      { name: "phong", code: "5.1", title: "Phong", label: "5.1 - Phong", floor: "Lầu 5", note: "Phòng lớn", capacity: 12,
        bookings: today ? [bk("09:30", "10:30", "Nguyễn Khánh Huyền"), bk("10:30", "11:00", "Lê Hương"), bk("14:00", "16:00", "Ban giám đốc")] : [] },
      { name: "hoa", code: "1.1", title: "Hoả", label: "1.1 - Hoả", floor: "Lầu 1", note: "Lớn", capacity: 8,
        bookings: today ? [bk("08:30", "09:30", "Trần Hoàn", { mine: true, uid: "u-mine1" }), bk("11:00", "12:00", "Đặng Vũ")] : [] },
      { name: "tho", code: "1.2", title: "Thổ", label: "1.2 - Thổ", floor: "Lầu 1", note: "Vừa", capacity: 6,
        bookings: today ? [bk("10:30", "11:30", "<img src=x onerror=alert(1)>")] : [] },
      { name: "thuy", code: "1.3", title: "Thuỷ", label: "1.3 - Thuỷ", floor: "Lầu 1", note: "Nhỏ", capacity: 4, error: "ROOM_NOT_FOUND", bookings: [] },
      { name: "cabin", code: "5.2", title: "Cabin", label: "5.2 - Cabin", floor: "Lầu 5", note: "Cách âm", capacity: 2, bookings: [] }]
  };
}
function mineData() {
  return { sync_on: true, rows: [
    { event_id: "ev1", uid: "u-mine1", room: "hoa", label: "1.1 - Hoả", start: D0 + " 08:30:00", end: D0 + " 09:30:00", subject: "1-1 với <b>Thái</b>", state: "accepted", join_url: "https://teams.microsoft.com/l/meetup-join/x" },
    { event_id: "ev2", uid: "u-p2", room: "cabin", label: "5.2 - Cabin", start: D0 + " 15:00:00", end: D0 + " 15:30:00", subject: "Gọi khách", state: "pending", join_url: "" }] };
}
const smErr = msg => { const e = new Error("HTTP 417"); e._server_messages = JSON.stringify([JSON.stringify({ message: msg, indicator: "red" })]); return e; };

function setup(o) {
  o = o || {};
  const dom = new JSDOM("<!doctype html><body><div id=ec-pm-root><div id=v></div></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#rooms", pretendToBeVisual: true });
  const w = dom.window, calls = [], toasts = [], errs = [];
  w.console.error = (...a) => errs.push(a.join(" "));
  w.fetch = () => { calls.push({ m: "FETCH" }); return Promise.reject(new Error("no network")); };
  w.eval(JS);
  const H = Object.assign({
    "rooms.day": a => dayData(a.date),
    "rooms.mine": () => mineData(),
    "rooms.book": a => ({ ok: true, event_id: "evN", uid: "uN", room: a.room, label: "5.1 - Phong", start: a.start, end: a.end, subject: a.subject, state: "pending", join_url: "" }),
    "rooms.booking_state": () => ({ state: "accepted" }),
    "rooms.cancel": () => ({ ok: true, state: "cancelled" }),
    "assignment.list_assignable": () => ({ rows: [{ email: "lan.nguyen@ecentric.vn", full_name: "Nguyễn Lan" }, { email: "vu.dang@ecentric.vn", full_name: "Đặng Vũ" }] })
  }, o.h || {});
  const api = (method, args) => {
    const m = method.replace("ecentric_workspace.pm.api.", "");
    calls.push({ m, a: args });
    try { const fn = H[m]; if (!fn) return Promise.reject(new Error("no " + m)); const v = fn(args || {}, calls); return v && typeof v.then === "function" ? v : Promise.resolve(v); }
    catch (e) { return Promise.reject(e); }
  };
  const c = w.document.getElementById("v");
  const ctl = w.PMRooms.render(c, { api, toast: (m, bad) => toasts.push({ m, bad: !!bad }), head: (t, s, r) => `<div class="pm-head"><h1>${t}</h1><p>${s}</p>${r || ""}</div>`, mode: o.mode || "page", pollMs: [5, 5, 5, 5] });
  const $ = s => w.document.querySelector(s), $$ = s => Array.from(w.document.querySelectorAll(s));
  const lane = name => $(`.pmrm-lane[data-room="${name}"]`);
  const rect = l => { l.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1100, height: 58, right: 1100, bottom: 58 }); return l; };
  const xOf = hhmm => { const [h, m] = hhmm.split(":").map(Number); return ((h * 60 + m) - 480) / 660 * 1100 + 1; };
  const clickAt = (name, hhmm) => { const l = rect(lane(name)); l.dispatchEvent(new w.MouseEvent("click", { bubbles: true, clientX: xOf(hhmm) })); };
  const f = k => $(`.pmrm-scrim [data-f="${k}"]`);
  const setv = (k, v) => { const i = f(k); i.value = v; i.dispatchEvent(new w.Event(k === "subject" || k === "who" ? "input" : "change", { bubbles: true })); };
  const key = (elm, k) => elm.dispatchEvent(new w.KeyboardEvent("keydown", { key: k, bubbles: true }));
  const count = m => calls.filter(x => x.m === m).length;
  return { w, c, ctl, calls, toasts, errs, $, $$, lane, clickAt, f, setv, key, count };
}

(async () => {
  /* ---------- 1. hiển thị */
  let T = setup(); await flush();
  const rows = T.$$(".pmrm-row");
  ok("render: 5 phòng, nhãn + tầng/ghi chú/sức chứa", rows.length === 5 && /5\.1 - Phong/.test(rows[0].textContent) && /Lầu 5 · Phòng lớn · 12 người/.test(rows[0].textContent));
  const stOf = i => rows[i].querySelector(".pmrm-room .pmrm-st");
  ok("trạng thái: Phong bận (gộp lịch liền nhau) đến 11:00", stOf(0).textContent === "Bận đến 11:00" && stOf(0).classList.contains("pmrm-st--busy"));
  ok("trạng thái: Hoả trống đến 11:00 (còn 45')", stOf(1).textContent === "Trống đến 11:00" && stOf(1).classList.contains("pmrm-st--free"));
  ok("trạng thái: Thổ ≤30' nữa có người → cam", stOf(2).textContent === "Trống đến 10:30" && stOf(2).classList.contains("pmrm-st--soon"));
  ok("ROOM_NOT_FOUND: Chưa kết nối, làn không bấm được, có lý do", stOf(3).textContent === "Chưa kết nối" && !T.lane("thuy") && /chưa được tạo trên Microsoft 365/.test(rows[3].textContent) && rows[3].querySelector(".pmrm-lane--off[aria-disabled=true]"));
  ok("trạng thái: Cabin trống cả ngày (lịch chờ phòng nhận không tính bận)", stOf(4).textContent === "Trống cả ngày");
  ok("ô tóm tắt: 3/5 phòng đang trống", T.$("[data-t-free]").textContent.replace(/\s/g, "") === "3/5phòng");
  ok("ô tóm tắt: trống sớm nhất tiếp theo = 5.1 - Phong lúc 11:00", /5\.1 - Phong/.test(T.$("[data-t-next]").textContent) && /lúc 11:00/.test(T.$("[data-t-next]").textContent));
  ok("ô tóm tắt: bạn đặt hôm nay = 2 cuộc (đã nhận + chờ nhận)", T.$("[data-t-mine]").textContent.replace(/\s/g, "") === "2cuộc");
  ok("khối có người đặt: xám, ghi tên người đặt + giờ", T.lane("phong").querySelectorAll(".pmrm-blk--busy").length === 3 && /Nguyễn Khánh Huyền/.test(T.lane("phong").textContent) && /09:30–10:30/.test(T.lane("phong").textContent));
  const mineBlk = T.lane("hoa").querySelector(".pmrm-blk--mine");
  ok("khối bạn đặt: navy nhạt, tên cuộc họp lấy từ mine() theo uid (đã esc)", mineBlk && mineBlk.textContent.indexOf("1-1 với <b>Thái</b>") === 0 && !mineBlk.querySelector("b"));
  const pend = T.lane("cabin").querySelector(".pmrm-blk--pend");
  ok("khối chờ phòng nhận (từ mine(), chưa có trong lịch phòng): vàng đứt nét", pend && /Gọi khách/.test(pend.textContent) && /chờ phòng nhận/.test(pend.textContent));
  ok("esc tên người đặt từ server (không sinh thẻ)", !T.lane("tho").querySelector("img") && /<img src=x/.test(T.lane("tho").textContent));
  ok("vạch giờ hiện tại trên mọi làn đang nối", T.$$(".pmrm-lane[data-room] .pmrm-now").length === 4);
  ok("làn: role=button, tabindex=0, aria-label có tên phòng", ["phong", "hoa", "tho", "cabin"].every(n => T.lane(n).getAttribute("role") === "button" && T.lane(n).tabIndex === 0 && /Đặt phòng/.test(T.lane(n).getAttribute("aria-label"))));
  const ml = T.$$(".pmrm-mrow");
  ok("Phòng bạn đã đặt: 2 dòng, chấm + chữ trạng thái, link Teams mở tab mới", ml.length === 2 && /Phòng đã nhận/.test(ml[0].textContent) && /Chờ phòng nhận/.test(ml[1].textContent) && ml[0].querySelector('a[target="_blank"][rel="noopener"]').getAttribute("href").indexOf("https://teams.microsoft.com/") === 0);
  ok("nút + Đặt phòng bật khi có dữ liệu", !T.$('[data-act="book"]').disabled);

  /* ---------- 2. kiểm trùng ở client */
  T.clickAt("phong", "14:30"); await flush();
  ok("bấm giờ đã có người đặt → báo, không mở hộp", !T.$(".pmrm-scrim") && /đã có người đặt/.test((T.toasts[T.toasts.length - 1] || {}).m || ""));
  T.clickAt("phong", "08:30"); await flush();
  ok("bấm giờ đã qua → báo, không mở hộp", !T.$(".pmrm-scrim") && /đã qua/.test(T.toasts[T.toasts.length - 1].m));
  T.lane("phong").focus();
  T.clickAt("phong", "12:10"); await flush();
  ok("bấm chỗ trống 12:10 → hộp đặt mở: phòng, ngày, 12:00–13:00 (bước 30')", T.$(".pmrm-scrim") && T.f("room").value === "phong" && T.f("date").value === D0 && T.f("start").value === "12:00" && T.f("end").value === "13:00" && T.f("start").getAttribute("step") === "1800");
  ok("hộp: role=dialog aria-modal, focus vào ô tên cuộc họp", T.$(".pmrm-dlg[role=dialog][aria-modal=true]") && T.w.document.activeElement === T.f("subject"));
  T.setv("end", "14:30");
  const warn = T.$(".pmrm-scrim [data-warn]");
  ok("kiểm trùng ngay ở client: báo giờ + người đặt, khoá nút Đặt", !warn.hidden && /14:00–16:00/.test(warn.textContent) && /Ban giám đốc/.test(warn.textContent) && T.$(".pmrm-scrim [data-submit]").disabled);
  T.setv("end", "11:30");
  ok("giờ kết thúc trước giờ bắt đầu → báo", /Giờ kết thúc phải sau giờ bắt đầu/.test(warn.textContent));
  T.setv("end", "13:00");
  ok("hết trùng → bỏ cảnh báo, mở nút", warn.hidden && !T.$(".pmrm-scrim [data-submit]").disabled);
  T.key(T.$(".pmrm-dlg"), "Escape"); await flush();
  ok("Esc đóng hộp, trả focus về làn phòng", !T.$(".pmrm-scrim") && T.w.document.activeElement === T.lane("phong"));

  /* ---------- 3. đặt phòng */
  T.clickAt("phong", "12:00"); await flush();
  T.$(".pmrm-scrim [data-submit]").click(); await flush();
  ok("thiếu tên cuộc họp → báo, không gọi server", T.count("rooms.book") === 0 && /Ghi tên cuộc họp/.test(T.$(".pmrm-scrim [data-warn]").textContent));
  T.setv("subject", "Họp <kế hoạch>");
  T.f("who").dispatchEvent(new T.w.Event("focus")); await flush();
  T.setv("who", "lan"); await flush();
  ok("mời người: gợi ý theo tên (bỏ dấu) từ list_assignable", T.count("assignment.list_assignable") === 1 && T.$$(".pmrm-scrim [data-opt]").length === 1 && /Nguyễn Lan/.test(T.$(".pmrm-scrim .pmrm-opts").textContent));
  T.key(T.f("who"), "Enter"); await flush();
  T.setv("who", "khach@doitac.vn"); T.key(T.f("who"), "Enter"); await flush();
  ok("Enter chọn người / thêm email gõ tay thành chip, không gửi form", T.$$(".pmrm-scrim .pmrm-chip").length === 2 && T.count("rooms.book") === 0);
  T.$(".pmrm-scrim [data-submit]").click(); T.$(".pmrm-scrim [data-submit]").click();
  T.$(".pmrm-scrim form").dispatchEvent(new T.w.Event("submit", { cancelable: true }));
  await flush(); await tick(2);
  const b1 = T.calls.filter(x => x.m === "rooms.book");
  ok("bấm 3 lần → chỉ 1 lần POST rooms.book", b1.length === 1);
  ok("rooms.book đúng tham số (room, start/end đủ giây, subject, attendees JSON, teams=1)", b1[0] && JSON.stringify(b1[0].a) === JSON.stringify({ room: "phong", start: D0 + " 12:00:00", end: D0 + " 13:00:00", subject: "Họp <kế hoạch>", attendees: JSON.stringify(["lan.nguyen@ecentric.vn", "khach@doitac.vn"]), teams: 1 }), b1[0] && JSON.stringify(b1[0].a));
  await flush();
  T = T; // giữ instance
  ok("đặt xong: đóng hộp + thông báo chờ phòng xác nhận", !T.$(".pmrm-scrim") && T.toasts.some(t => /chờ phòng xác nhận/.test(t.m)));
  await tick(40); await flush();
  ok("hỏi booking_state(event_id) rồi báo Phòng đã nhận", T.calls.some(x => x.m === "rooms.booking_state" && x.a.event_id === "evN") && T.toasts.some(t => /5\.1 - Phong đã nhận/.test(t.m)));
  T.ctl.destroy();

  /* đặt → chờ → phòng nhận: trạng thái đổi trên lưới + danh sách */
  let st = ["pending", "pending", "accepted"], booked = false;
  T = setup({ h: {
    "rooms.book": a => { booked = true; return { ok: true, event_id: "evP", uid: "uP", room: a.room, label: "5.2 - Cabin", start: a.start, end: a.end, subject: a.subject, state: "pending", join_url: "https://teams.microsoft.com/l/p" }; },
    "rooms.booking_state": () => ({ state: st.shift() || "accepted" }),
    "rooms.mine": () => { const m = mineData(); if (booked && !st.length) m.rows.push({ event_id: "evP", uid: "uP", room: "cabin", label: "5.2 - Cabin", start: D0 + " 17:00:00", end: D0 + " 18:00:00", subject: "Họp P", state: "accepted", join_url: "https://teams.microsoft.com/l/p" }); return m; } } });
  await flush();
  T.clickAt("cabin", "17:00"); await flush();
  T.setv("subject", "Họp P"); T.$(".pmrm-scrim form").dispatchEvent(new T.w.Event("submit", { cancelable: true })); await flush();
  const pb = T.lane("cabin").querySelectorAll(".pmrm-blk--pend");
  ok("vừa đặt: khối 'chờ phòng nhận' trên lưới + dòng 'Chờ phòng nhận' trong danh sách", Array.from(pb).some(x => /Họp P/.test(x.textContent)) && T.$$(".pmrm-mrow").some(r => /Họp P/.test(r.textContent) && /Chờ phòng nhận/.test(r.textContent)));
  await tick(60); await flush();
  ok("hỏi lại nhiều lần đến khi phòng nhận → khối thành 'bạn đặt', dòng 'Phòng đã nhận'", T.count("rooms.booking_state") === 3 && Array.from(T.lane("cabin").querySelectorAll(".pmrm-blk--mine")).some(x => /Họp P/.test(x.textContent)) && T.$$(".pmrm-mrow").some(r => /Họp P/.test(r.textContent) && /Phòng đã nhận/.test(r.textContent)));
  T.ctl.destroy();

  /* phòng từ chối */
  T = setup({ h: { "rooms.booking_state": () => ({ state: "declined" }) } }); await flush();
  T.clickAt("cabin", "17:00"); await flush();
  T.setv("subject", "Trùng"); T.$(".pmrm-scrim form").dispatchEvent(new T.w.Event("submit", { cancelable: true })); await flush(); await tick(30); await flush();
  ok("phòng từ chối → thông báo lỗi 'từ chối (trùng giờ)', dòng 'Phòng từ chối', khối chờ biến mất", T.toasts.some(t => t.bad && /từ chối \(trùng giờ\)/.test(t.m)) && T.$$(".pmrm-mrow").some(r => /Trùng/.test(r.textContent) && /Phòng từ chối/.test(r.textContent)) && !Array.from(T.lane("cabin").querySelectorAll(".pmrm-blk")).some(x => /Trùng/.test(x.textContent)));
  T.ctl.destroy();

  /* lỗi server: hiện đúng thông điệp server */
  T = setup({ h: { "rooms.book": () => Promise.reject(smErr("Phòng 5.1 - Phong đã có người đặt 12:00–13:00 (Lê Hương).")) } }); await flush();
  T.clickAt("phong", "12:00"); await flush();
  T.setv("subject", "X"); T.$(".pmrm-scrim form").dispatchEvent(new T.w.Event("submit", { cancelable: true })); await flush();
  ok("lỗi server (_server_messages) → hiện nguyên văn trong hộp, hộp vẫn mở, nút bật lại", T.$(".pmrm-scrim") && T.$(".pmrm-scrim [data-warn]").textContent === "Phòng 5.1 - Phong đã có người đặt 12:00–13:00 (Lê Hương)." && !T.$(".pmrm-scrim [data-submit]").disabled && T.$(".pmrm-scrim [data-submit]").textContent === "Đặt phòng");
  T.ctl.destroy();
  T = setup({ h: { "rooms.book": () => Promise.reject(new Error("frappe.exceptions.ValidationError: Không đặt được giờ đã qua.")) } }); await flush();
  T.clickAt("hoa", "12:00"); await flush();
  T.setv("subject", "X"); T.$(".pmrm-scrim form").dispatchEvent(new T.w.Event("submit", { cancelable: true })); await flush();
  ok("lỗi kiểu fetch dự phòng ('...ValidationError: msg') → chỉ hiện msg", T.$(".pmrm-scrim [data-warn]").textContent === "Không đặt được giờ đã qua.");
  T.ctl.destroy();

  /* ---------- 4. huỷ có xác nhận */
  T = setup(); await flush();
  T.$('[data-act="cancel"][data-ev="ev1"]').click(); await flush();
  ok("bấm Huỷ → hỏi xác nhận, chưa gọi server", T.count("rooms.cancel") === 0 && /Huỷ lịch này\?/.test(T.$('[data-ev-row="ev1"]').textContent) && T.w.document.activeElement === T.$('[data-act="cancel-no"]'));
  T.$('[data-act="cancel-no"]').click(); await flush();
  ok("Giữ → bỏ xác nhận, focus về nút Huỷ", !T.$(".pmrm-cf") && T.w.document.activeElement === T.$('[data-act="cancel"][data-ev="ev1"]'));
  T.$('[data-act="cancel"][data-ev="ev1"]').click(); await flush();
  T.key(T.$('[data-act="cancel-no"]'), "Escape"); await flush();
  ok("Esc cũng bỏ xác nhận", !T.$(".pmrm-cf") && T.count("rooms.cancel") === 0);
  T.$('[data-act="cancel"][data-ev="ev1"]').click(); await flush();
  T.$('[data-act="cancel-yes"]').click(); T.$('[data-act="cancel-yes"]').click(); await flush();
  ok("xác nhận → 1 lần POST rooms.cancel(event_id), dòng biến mất, thông báo đã huỷ", T.calls.filter(x => x.m === "rooms.cancel").length === 1 && T.calls.find(x => x.m === "rooms.cancel").a.event_id === "ev1" && !T.$('[data-ev-row="ev1"]') && T.toasts.some(t => /Đã huỷ/.test(t.m)));
  T.ctl.destroy();
  T = setup({ h: { "rooms.cancel": () => Promise.reject(smErr("Chỉ người đặt mới huỷ được phòng này.")) } }); await flush();
  T.$('[data-act="cancel"][data-ev="ev2"]').click(); await flush(); T.$('[data-act="cancel-yes"]').click(); await flush();
  ok("huỷ lỗi → báo đúng thông điệp server, dòng còn nguyên", T.toasts.some(t => t.bad && /Chỉ người đặt mới huỷ được phòng này\./.test(t.m)) && T.$('[data-ev-row="ev2"]') && T.$('[data-act="cancel"][data-ev="ev2"]'));
  T.ctl.destroy();

  /* ---------- 5. bàn phím, ngày, tải lỗi */
  T = setup(); await flush();
  T.lane("cabin").focus(); T.key(T.lane("cabin"), "Enter"); await flush();
  ok("Enter trên làn → mở hộp ở giờ trống gần nhất (10:30–11:30)", T.$(".pmrm-scrim") && T.f("room").value === "cabin" && T.f("start").value === "10:30" && T.f("end").value === "11:30");
  T.$('.pmrm-scrim [data-act="close"]').click(); await flush();
  ok("nút Huỷ trong hộp: đóng + trả focus", !T.$(".pmrm-scrim") && T.w.document.activeElement === T.lane("cabin"));
  T.$('[data-day="1"]').click(); await flush();
  ok("bấm Mai → day(date=ngày mai), nút Mai được chọn, không có vạch giờ hiện tại", T.calls.some(x => x.m === "rooms.day" && x.a.date === "2026-11-06") && T.$('[data-day="1"]').getAttribute("aria-pressed") === "true" && !T.$(".pmrm-now"));
  ok("ngày khác hôm nay: ô tóm tắt vẫn tính theo hôm nay", T.$("[data-t-free]").textContent.replace(/\s/g, "") === "3/5phòng");
  T.ctl.destroy();

  let fail = 1;
  T = setup({ h: { "rooms.day": a => (fail-- > 0 ? Promise.reject(smErr("Bạn không có quyền vào Quản lý công việc.")) : dayData(a.date)) } }); await flush();
  ok("tải lỗi → thông điệp server + nút Thử lại, không vỡ", /Bạn không có quyền vào Quản lý công việc\./.test(T.$("[data-tl]").textContent) && T.$('[data-act="retry"]'));
  T.$('[data-act="retry"]').click(); await flush();
  ok("Thử lại → tải được lưới", T.$$(".pmrm-row").length === 5);
  T.ctl.destroy();

  /* ---------- 6. SYNC_OFF */
  T = setup({ h: { "rooms.day": () => { const d = dayData(); d.sync_on = false; d.rooms.forEach(r => { r.error = "SYNC_OFF"; r.bookings = []; }); return d; }, "rooms.mine": () => ({ rows: [], sync_on: false }) } });
  await flush();
  ok("SYNC_OFF: 5 làn 'Chưa kết nối', không làn bấm được, nút Đặt khoá, có thông báo gọn", T.$$(".pmrm-lane--off").length === 5 && !T.$(".pmrm-lane[data-room]") && T.$('[data-act="book"]').disabled && !T.$("[data-msg]").hidden && /Chưa kết nối lịch Teams/.test(T.$("[data-msg]").textContent));
  ok("SYNC_OFF: ô tóm tắt không vỡ, danh sách rỗng có câu", /Chưa kết nối/.test(T.$("[data-t-free]").textContent) && /chưa đặt phòng nào/.test(T.$("[data-mine]").textContent));
  ok("không lỗi console, không fetch ra ngoài khi có api", T.errs.length === 0 && T.count("FETCH") === 0, T.errs.join(" | "));
  T.ctl.destroy();

  /* ---------- 7. chế độ tab + tự dừng khi bị thay */
  T = setup({ mode: "tab" }); await flush();
  ok("mode tab: chỉ lưới + nút Đặt, không ô tóm tắt / danh sách, có link sang #rooms", T.$$(".pmrm-row").length === 5 && !T.$(".pmrm-bento") && !T.$("[data-mine]") && T.$('[data-act="book"]') && T.$('a[href="/pm#rooms"]'));
  T.$('[data-act="book"]').click(); await flush();
  ok("mode tab: + Đặt phòng mở hộp ở phòng có giờ trống sớm nhất (Hoả 10:30–11:00)", T.$(".pmrm-scrim") && T.f("room").value === "hoa" && T.f("start").value === "10:30" && T.f("end").value === "11:00");
  const n0 = T.calls.length;
  T.c.innerHTML = ""; await T.ctl.refresh(); await flush();
  ok("gốc bị host thay → tự dừng (không gọi server, hộp đã gỡ)", T.calls.length === n0 && !T.$(".pmrm-scrim"));

  /* ---------- 8. tĩnh */
  ok("asset: không ký tự Jinja, một global PMRooms, có esc", !/\{\{|\{%|\{#/.test(JS) && /root\.PMRooms = /.test(JS));
  ok("CSS: mobile ≤640px (ô nhập 16px), lưới cuộn ngang, namespace .pmrm-", /@media \(max-width:640px\)/.test(CSS) && /font-size:16px/.test(CSS) && /\.pmrm-tl\{overflow-x:auto/.test(CSS) && !/(^|\})\s*(body|html|\.panel)\s*\{/.test(CSS));

  let bad = 0;
  res.forEach(r => { if (!r.c) bad++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - bad}/${res.length} passed`);
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
