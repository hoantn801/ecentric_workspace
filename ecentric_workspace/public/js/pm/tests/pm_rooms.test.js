/* pm_rooms.test.js — Phòng họp (asset pm_rooms.js). Chạy: NODE_PATH=<node_modules có jsdom> node pm_rooms.test.js
 * API giả (không mạng): day / mine / book / booking_state / cancel / list_assignable.
 * Kiểm: đủ phòng + trạng thái lúc này, khối bận / bạn đặt / chờ phòng nhận, kiểm trùng ở client, đặt -> POST rooms.book đúng
 * tham số -> hỏi booking_state -> đổi trạng thái, lỗi server hiện đúng thông điệp, chặn bấm 2 lần, huỷ có xác nhận,
 * Esc + trả focus, Enter trên làn, phòng ROOM_NOT_FOUND / SYNC_OFF không vỡ, tải lỗi có Thử lại, chế độ tab.
 * v2 (06/11): sửa từ khối & từ danh sách (chỉ gửi trường đổi), scope buổi / chuỗi, kiểm trùng bỏ qua chính mình, lặp lại
 * (tham số, tóm tắt số buổi, giới hạn 180 ngày), khách ngoài (chip, email sai, dán nhiều email), huỷ buổi / chuỗi, kéo thả
 * (trùng, thành công, họp lặp không kéo, server từ chối -> trả về chỗ cũ), lỗi server khi sửa. */
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
  ok("rooms.book đúng tham số (room, start/end đủ giây, subject, attendees JSON, teams=1, txn chống tạo trùng)", b1[0] && /^erp-[a-z0-9]+-[a-z0-9]+$/.test(b1[0].a.txn || "") && JSON.stringify(Object.assign({}, b1[0].a, { txn: undefined })) === JSON.stringify({ room: "phong", start: D0 + " 12:00:00", end: D0 + " 13:00:00", subject: "Họp <kế hoạch>", attendees: JSON.stringify(["lan.nguyen@ecentric.vn", "khach@doitac.vn"]), teams: 1 }), b1[0] && JSON.stringify(b1[0].a));
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

  /* ---------- 9. v2 (06/11): sửa / đổi giờ / đổi phòng, lặp lại, khách ngoài, kéo thả */
  const LBL = { phong: "5.1 - Phong", hoa: "1.1 - Hoả", tho: "1.2 - Thổ", cabin: "5.2 - Cabin" };
  const dayV2 = date => { const d = dayData(date); if (!date || date === D0) {
    d.rooms[4].bookings.push(bk("12:00", "13:00", "Trần Hoàn", { mine: true, uid: "u-e5" }));
    d.rooms[1].bookings.push(bk("16:00", "17:00", "Trần Hoàn", { mine: true, uid: "u-r1" })); } return d; };
  const mineV2 = () => { const m = mineData(); m.rows.forEach(r => { r.guests = []; r.recurring = false; r.series_id = ""; }); m.rows.push(
    { event_id: "ev5", uid: "u-e5", room: "cabin", label: "5.2 - Cabin", start: D0 + " 12:00:00", end: D0 + " 13:00:00", subject: "Sync dự án", state: "accepted", join_url: "https://teams.microsoft.com/l/5", recurring: false, series_id: "",
      guests: [{ email: "lan.nguyen@ecentric.vn", name: "Nguyễn Lan", external: false }, { email: "khach@doitac.vn", name: "Khách <A>", external: true }] },
    { event_id: "occ1", uid: "u-r1", room: "hoa", label: "1.1 - Hoả", start: D0 + " 16:00:00", end: D0 + " 17:00:00", subject: "Giao ban tuần", state: "accepted", join_url: "", recurring: true, series_id: "ser1", guests: [] }); return m; };
  function v2(h, extra) {
    const SV = { rows: mineV2().rows };
    const T2 = setup(Object.assign({ h: Object.assign({
      "rooms.day": a => dayV2(a.date),
      "rooms.mine": () => ({ sync_on: true, rows: JSON.parse(JSON.stringify(SV.rows)) }),
      "rooms.update": a => {
        const x = SV.rows.find(r => r.event_id === a.event_id), series = a.scope === "series";
        if (a.room) { x.room = a.room; x.label = LBL[a.room]; }
        if (a.subject != null) x.subject = a.subject;
        if (a.start) { x.start = a.start; x.end = a.end; }
        if (a.room || a.start) x.state = "pending";
        return { ok: true, event_id: series ? x.series_id : x.event_id, scope: a.scope || "occurrence", room: x.room, label: x.label, start: x.start, end: x.end, state: (a.room || a.start) ? "pending" : null };
      },
      "rooms.booking_state": () => ({ state: "pending" }),
      "rooms.book": a => ({ ok: true, event_id: "evR", uid: "uR", room: a.room, label: LBL[a.room], start: a.start, end: a.end, subject: a.subject, state: "pending", recurring: !!a.repeat, external: 0, join_url: "" })
    }, h || {}) }, extra || {}));
    T2.SV = SV;
    T2.w.HTMLElement.prototype.getBoundingClientRect = function () {
      const ls = Array.from(T2.w.document.querySelectorAll(".pmrm-lane[data-room]")), i = ls.indexOf(this);
      return i >= 0 ? { left: 0, top: i * 58, width: 1100, height: 58, right: 1100, bottom: i * 58 + 58 } : { left: 0, top: -999, width: 0, height: 0, right: 0, bottom: -999 };
    };
    return T2;
  }
  const blkOf = (T2, name, re) => Array.from(T2.lane(name).querySelectorAll(".pmrm-blk")).filter(b => re.test(b.textContent));
  const lastToast = T2 => (T2.toasts[T2.toasts.length - 1] || {});
  const submitDlg = T2 => T2.$(".pmrm-scrim form").dispatchEvent(new T2.w.Event("submit", { cancelable: true }));
  const updates = T2 => T2.calls.filter(x => x.m === "rooms.update");

  /* 9a. hiển thị */
  T = v2(); await flush();
  const r5 = T.$('[data-ev-row="ev5"]'), rr = T.$('[data-ev-row="occ1"]');
  ok("v2 danh sách: số người mời + khách ngoài, nhãn Lặp lại, nút Sửa + Huỷ", /2 người mời \(1 khách ngoài\)/.test(r5.textContent) && /Lặp lại/.test(rr.textContent) && r5.querySelector('[data-act="edit"][data-ev="ev5"]') && r5.querySelector('[data-act="cancel"]'));
  const b5 = blkOf(T, "cabin", /Sync dự án/);
  ok("v2 khối Bạn đặt: bấm được (role=button, tabindex, aria-label Sửa…), có data-ev", b5.length === 1 && b5[0].getAttribute("data-ev") === "ev5" && b5[0].getAttribute("role") === "button" && b5[0].tabIndex === 0 && /^Sửa cuộc họp Sync dự án, 12:00–13:00/.test(b5[0].getAttribute("aria-label")));
  const br = blkOf(T, "hoa", /Giao ban tuần/)[0];
  ok("v2 khối họp lặp: biểu tượng ↻ + nhãn 'Lặp lại', đánh dấu data-rec", br && br.hasAttribute("data-rec") && br.querySelector(".pmrm-rep") && /Lặp lại/.test(br.querySelector("small").textContent));
  ok("v2 khối người khác: không bấm sửa được", !T.lane("phong").querySelector(".pmrm-blk[data-ev]"));

  /* 9b. mở sửa từ khối: cùng hộp, điền sẵn */
  b5[0].click(); await flush();
  ok("sửa từ khối: tiêu đề 'Sửa cuộc họp', nút 'Lưu thay đổi'", T.$(".pmrm-dlg h2").textContent === "Sửa cuộc họp" && T.$(".pmrm-scrim [data-submit]").textContent === "Lưu thay đổi");
  ok("sửa: điền sẵn tên, phòng, ngày, giờ, Teams (khoá), không có ô Lặp lại / phạm vi", T.f("subject").value === "Sync dự án" && T.f("room").value === "cabin" && T.f("date").value === D0 && T.f("start").value === "12:00" && T.f("end").value === "13:00" && T.f("teams").checked && T.f("teams").disabled && !T.f("repeat") && !T.$(".pmrm-scope"));
  const ch = T.$$(".pmrm-scrim .pmrm-chip");
  ok("sửa: người mời thành chip, khách ngoài chip khác màu + 'Khách ngoài' + tooltip, tên esc", ch.length === 2 && !ch[0].classList.contains("pmrm-chip--ext") && ch[1].classList.contains("pmrm-chip--ext") && /Khách ngoài/.test(ch[1].textContent) && ch[1].getAttribute("title") === "Người ngoài công ty sẽ nhận lời mời Teams qua email" && /Khách <A>/.test(ch[1].textContent) && !ch[1].querySelector("a") && !T.$(".pmrm-scrim [data-exthint]").hidden);
  ok("kiểm trùng bỏ qua chính cuộc đang sửa (không cảnh báo, nút Lưu bật)", T.$(".pmrm-scrim [data-warn]").hidden && !T.$(".pmrm-scrim [data-submit]").disabled);
  T.setv("start", "14:30"); T.setv("end", "15:30");
  ok("sửa: vẫn kiểm trùng với cuộc khác (lịch chờ nhận 15:00–15:30 cùng phòng)", /Bạn đã đặt phòng này 15:00–15:30/.test(T.$(".pmrm-scrim [data-warn]").textContent) && T.$(".pmrm-scrim [data-submit]").disabled);
  T.setv("start", "12:00"); T.setv("end", "13:30");
  T.$(".pmrm-scrim [data-submit]").click(); T.$(".pmrm-scrim [data-submit]").click(); submitDlg(T); await flush();
  ok("đổi giờ: 1 lần POST rooms.update, CHỈ gửi start/end (không subject/room/attendees/scope)", updates(T).length === 1 && JSON.stringify(updates(T)[0].a) === JSON.stringify({ event_id: "ev5", start: D0 + " 12:00:00", end: D0 + " 13:30:00" }), JSON.stringify(updates(T).map(x => x.a)));
  const nb = blkOf(T, "cabin", /Sync dự án/);
  ok("lưu xong: hộp đóng, khối chuyển 'Chờ phòng nhận' ở giờ mới, khối cũ biến mất", !T.$(".pmrm-scrim") && nb.length === 1 && nb[0].classList.contains("pmrm-blk--pend") && /12:00–13:30/.test(nb[0].textContent) && /chờ phòng xác nhận/.test(lastToast(T).m));
  await tick(40); await flush();
  ok("lưu xong: hỏi booking_state(ev5) như khi đặt", T.calls.some(x => x.m === "rooms.booking_state" && x.a.event_id === "ev5"));
  await T.ctl.refresh(); await flush();
  ok("tải lại (lịch phòng còn giờ cũ, mine giờ mới): vẫn chỉ 1 khối ở giờ mới", blkOf(T, "cabin", /Sync dự án/).length === 1 && /12:00–13:30/.test(blkOf(T, "cabin", /Sync dự án/)[0].textContent));
  T.ctl.destroy();

  /* 9c. sửa từ danh sách: tên + người mời (khách ngoài, email sai), không đổi giờ -> không hỏi phòng */
  T = v2(); await flush();
  T.$('[data-act="edit"][data-ev="ev5"]').click(); await flush();
  ok("sửa từ nút Sửa trong danh sách: cùng hộp, điền sẵn", T.$(".pmrm-dlg h2").textContent === "Sửa cuộc họp" && T.f("subject").value === "Sync dự án" && T.$$(".pmrm-scrim .pmrm-chip").length === 2);
  T.setv("subject", "Sync dự án Q4");
  T.$('.pmrm-scrim [data-rm="lan.nguyen@ecentric.vn"]').click();
  T.f("who").dispatchEvent(new T.w.Event("focus")); await flush();
  T.setv("who", "sai@email"); T.key(T.f("who"), "Enter"); await flush();
  const badChip = T.$(".pmrm-scrim .pmrm-chip--bad");
  ok("email sai: chip đỏ ngay + báo 'Email không hợp lệ', khoá nút Lưu", badChip && /sai@email/.test(badChip.textContent) && /Email không hợp lệ: sai@email/.test(T.$(".pmrm-scrim [data-warn]").textContent) && T.$(".pmrm-scrim [data-submit]").disabled);
  badChip.querySelector("button").click(); await flush();
  ok("bỏ chip sai → hết cảnh báo", T.$(".pmrm-scrim [data-warn]").hidden && !T.$(".pmrm-scrim [data-submit]").disabled);
  T.setv("who", "ban@gmail.com"); T.key(T.f("who"), "Enter"); await flush();
  T.setv("who", "vu.dang@ecentric.vn"); T.key(T.f("who"), "Enter"); await flush();
  const cc = T.$$(".pmrm-scrim .pmrm-chip");
  ok("gõ email ngoài + Enter → chip 'Khách ngoài'; email nội bộ → chip thường tên người", cc.length === 3 && cc[1].classList.contains("pmrm-chip--ext") && /ban@gmail\.com/.test(cc[1].textContent) && !cc[2].classList.contains("pmrm-chip--ext") && /Đặng Vũ/.test(cc[2].textContent));
  submitDlg(T); await flush();
  ok("chỉ gửi trường đổi: subject + attendees (không start/end/room)", updates(T).length === 1 && JSON.stringify(updates(T)[0].a) === JSON.stringify({ event_id: "ev5", subject: "Sync dự án Q4", attendees: JSON.stringify(["khach@doitac.vn", "ban@gmail.com", "vu.dang@ecentric.vn"]) }), JSON.stringify(updates(T).map(x => x.a)));
  ok("đổi tên/người mời: khối vẫn 'Bạn đặt' (không chờ phòng), không hỏi booking_state, danh sách cập nhật", T.count("rooms.booking_state") === 0 && blkOf(T, "cabin", /Sync dự án Q4/)[0].classList.contains("pmrm-blk--mine") && /3 người mời \(2 khách ngoài\)/.test(T.$('[data-ev-row="ev5"]').textContent) && lastToast(T).m === "Đã lưu thay đổi.");
  T.$('[data-act="edit"][data-ev="ev5"]').click(); await flush();
  submitDlg(T); await flush();
  ok("không đổi gì → không gọi server, báo 'Không có gì thay đổi.'", updates(T).length === 1 && !T.$(".pmrm-scrim") && lastToast(T).m === "Không có gì thay đổi.");
  /* đổi phòng */
  T.$('[data-act="edit"][data-ev="ev5"]').click(); await flush();
  T.setv("room", "phong"); await flush();
  ok("đổi phòng: kiểm trùng phòng mới (12:00–13:00 Phong trống)", T.$(".pmrm-scrim [data-warn]").hidden);
  submitDlg(T); await flush();
  ok("đổi phòng: chỉ gửi room; khối sang làn Phong 'chờ phòng nhận', làn Cabin hết khối", JSON.stringify(updates(T)[1].a) === JSON.stringify({ event_id: "ev5", room: "phong" }) && blkOf(T, "phong", /Sync dự án Q4/).length === 1 && blkOf(T, "phong", /Sync dự án Q4/)[0].classList.contains("pmrm-blk--pend") && !blkOf(T, "cabin", /Sync/).length && /5\.1 - Phong/.test(T.$('[data-ev-row="ev5"]').textContent));
  T.ctl.destroy();

  /* 9d. họp lặp: Chỉ buổi này / Cả chuỗi */
  T = v2(); await flush();
  const brk = blkOf(T, "hoa", /Giao ban tuần/)[0]; brk.focus(); T.key(brk, "Enter"); await flush();
  const radios = T.$$('.pmrm-scrim [data-f="scope"]');
  ok("sửa họp lặp (Enter trên khối): hỏi Chỉ buổi này / Cả chuỗi, mặc định Chỉ buổi này, ô ngày mở", radios.length === 2 && radios[0].value === "occurrence" && radios[0].checked && /Chỉ buổi này/.test(T.$(".pmrm-scope").textContent) && /Cả chuỗi/.test(T.$(".pmrm-scope").textContent) && !T.f("date").disabled);
  T.setv("start", "11:30"); T.setv("end", "12:30");
  ok("buổi này: kiểm trùng ở client (Đặng Vũ 11:00–12:00)", /Đặng Vũ/.test(T.$(".pmrm-scrim [data-warn]").textContent));
  T.setv("start", "16:00"); T.setv("end", "17:00");
  T.setv("subject", "Giao ban (dời)"); submitDlg(T); await flush();
  ok("buổi này: gửi scope=occurrence + trường đổi", JSON.stringify(updates(T)[0].a) === JSON.stringify({ event_id: "occ1", subject: "Giao ban (dời)", scope: "occurrence" }), JSON.stringify(updates(T).map(x => x.a)));
  ok("Esc/đóng sau khi mở bằng bàn phím → focus về khối", (() => { const b = blkOf(T, "hoa", /Giao ban/)[0]; b.focus(); T.key(b, "Enter"); return !!T.$(".pmrm-scrim"); })());
  T.key(T.$(".pmrm-dlg"), "Escape"); await flush();
  ok("… Esc đóng hộp sửa, focus trả về khối đã mở", !T.$(".pmrm-scrim") && T.w.document.activeElement && T.w.document.activeElement.getAttribute("data-ev") === "occ1");
  T.$('[data-act="edit"][data-ev="occ1"]').click(); await flush();
  T.$$('.pmrm-scrim [data-f="scope"]')[1].checked = true; T.$$('.pmrm-scrim [data-f="scope"]')[1].dispatchEvent(new T.w.Event("change", { bubbles: true }));
  ok("Cả chuỗi: khoá ô ngày, hiện ghi chú chỉ đổi giờ trong ngày", T.f("date").disabled && !T.$(".pmrm-scrim [data-scope-note]").hidden);
  T.setv("start", "16:30"); T.setv("end", "17:30"); submitDlg(T); await flush();
  ok("Cả chuỗi: gửi start/end (giữ ngày) + scope=series", JSON.stringify(updates(T)[1].a) === JSON.stringify({ event_id: "occ1", start: D0 + " 16:30:00", end: D0 + " 17:30:00", scope: "series" }), JSON.stringify(updates(T)[1].a));
  await tick(40); await flush();
  ok("Cả chuỗi: khối chờ phòng nhận ở giờ mới, hỏi booking_state(id chuỗi), không vẽ thêm khối/dòng trùng", blkOf(T, "hoa", /Giao ban/).length === 1 && blkOf(T, "hoa", /Giao ban/)[0].classList.contains("pmrm-blk--pend") && /16:30–17:30/.test(blkOf(T, "hoa", /Giao ban/)[0].textContent) && T.calls.some(x => x.m === "rooms.booking_state" && x.a.event_id === "ser1") && T.$$('[data-ev-row="occ1"]').length === 1 && T.$$(".pmrm-mrow").length === 4 && /Đã lưu cả chuỗi/.test(T.toasts.map(t => t.m).join("|")));
  T.ctl.destroy();

  /* 9e. huỷ buổi / cả chuỗi */
  T = v2(); await flush();
  T.$('[data-act="cancel"][data-ev="occ1"]').click(); await flush();
  ok("huỷ họp lặp: hỏi 'Huỷ buổi này' / 'Huỷ cả chuỗi' / Giữ", /Huỷ cuộc họp lặp lại\?/.test(T.$('[data-ev-row="occ1"]').textContent) && T.$('[data-act="cancel-yes"][data-scope="occurrence"]') && T.$('[data-act="cancel-yes"][data-scope="series"]') && T.$('[data-act="cancel-no"]'));
  T.$('[data-act="cancel-yes"][data-scope="series"]').click(); T.$('[data-act="cancel-yes"][data-scope="occurrence"]').click(); await flush();
  const cs = T.calls.filter(x => x.m === "rooms.cancel");
  ok("Huỷ cả chuỗi: 1 lần POST cancel(event_id, scope=series), dòng + khối biến mất", cs.length === 1 && JSON.stringify(cs[0].a) === JSON.stringify({ event_id: "occ1", scope: "series" }) && !T.$('[data-ev-row="occ1"]') && !blkOf(T, "hoa", /Giao ban/).length && /Đã huỷ cả chuỗi/.test(lastToast(T).m));
  T.ctl.destroy();
  T = v2(); await flush();
  T.$('[data-act="cancel"][data-ev="occ1"]').click(); await flush();
  T.$('[data-act="cancel-yes"][data-scope="occurrence"]').click(); await flush();
  ok("Huỷ buổi này: cancel(event_id, scope=occurrence)", JSON.stringify(T.calls.filter(x => x.m === "rooms.cancel")[0].a) === JSON.stringify({ event_id: "occ1", scope: "occurrence" }) && !T.$('[data-ev-row="occ1"]'));
  T.$('[data-act="cancel"][data-ev="ev5"]').click(); await flush();
  ok("họp không lặp: vẫn câu cũ 'Huỷ lịch này?'", /Huỷ lịch này\?/.test(T.$('[data-ev-row="ev5"]').textContent) && !T.$('[data-scope="series"]'));
  T.ctl.destroy();

  /* 9f. lặp lại khi đặt */
  T = v2(); await flush();
  T.clickAt("cabin", "17:00"); await flush();
  const rpSel = T.f("repeat"), opts = Array.from(rpSel.options).map(o => o.textContent);
  ok("ô Lặp lại: 6 lựa chọn theo ngày (thứ Năm 05/11), mặc định Không lặp lại, ẩn Đến ngày", rpSel.value === "none" && JSON.stringify(opts) === JSON.stringify(["Không lặp lại", "Hằng ngày", "Các ngày trong tuần (T2–T6)", "Hằng tuần vào thứ Năm", "2 tuần một lần vào thứ Năm", "Hằng tháng ngày 5"]) && T.$(".pmrm-scrim [data-until]").hidden && T.$(".pmrm-scrim [data-rsum]").hidden, JSON.stringify(opts));
  T.setv("repeat", "weekly");
  ok("chọn Hằng tuần: hiện Đến ngày (mặc định +4 tuần, tối đa +180 ngày) + tóm tắt số buổi", !T.$(".pmrm-scrim [data-until]").hidden && T.f("until").value === "2026-12-03" && T.f("until").max === "2027-05-04" && T.$(".pmrm-scrim [data-rsum]").textContent === "Lặp hằng tuần vào thứ Năm đến 03/12 · 5 buổi", T.$(".pmrm-scrim [data-rsum]").textContent);
  T.setv("until", "2027-05-05");
  ok("quá 180 ngày (tính từ hôm nay) → báo, khoá nút Đặt", /180 ngày/.test(T.$(".pmrm-scrim [data-warn]").textContent) && T.$(".pmrm-scrim [data-submit]").disabled && T.$(".pmrm-scrim [data-rsum]").hidden);
  T.setv("until", "2026-11-01");
  ok("Đến ngày trước ngày họp → báo", /phải sau ngày họp đầu tiên/.test(T.$(".pmrm-scrim [data-warn]").textContent));
  T.setv("until", "2026-11-19"); T.setv("repeat", "weekdays");
  ok("đổi kiểu lặp: tóm tắt đếm lại (T2–T6 05/11→19/11 = 11 buổi), giữ ngày người dùng chọn", T.f("until").value === "2026-11-19" && T.$(".pmrm-scrim [data-rsum]").textContent === "Lặp các ngày trong tuần (T2–T6) đến 19/11 · 11 buổi", T.$(".pmrm-scrim [data-rsum]").textContent);
  T.setv("subject", "Daily standup"); submitDlg(T); await flush();
  const bkR = T.calls.filter(x => x.m === "rooms.book")[0];
  ok("đặt lặp lại: gửi repeat + repeat_until đúng", bkR && bkR.a.repeat === "weekdays" && bkR.a.repeat_until === "2026-11-19" && bkR.a.room === "cabin" && bkR.a.start === D0 + " 17:00:00", bkR && JSON.stringify(bkR.a));
  ok("đặt lặp lại: thông báo số buổi, khối chờ nhận có nhãn Lặp lại", T.toasts.some(t => /lặp lại \(11 buổi\)/.test(t.m)) && blkOf(T, "cabin", /Daily standup/).some(b => /Lặp lại/.test(b.textContent)));
  const occ = T.w.PMRooms._occurrences;
  ok("đếm buổi khớp server: hằng ngày 7, 2 tuần một lần 3, hằng tháng ngày 31 rơi vào ngày cuối tháng ngắn (như Outlook), hằng ngày 180 ngày = 181 buổi", occ(D0, "daily", "2026-11-11").length === 7 && occ(D0, "biweekly", "2026-12-03").join() === "2026-11-05,2026-11-19,2026-12-03" && occ("2026-01-31", "monthly", "2026-06-30").join() === "2026-01-31,2026-02-28,2026-03-31,2026-04-30,2026-05-31,2026-06-30" && occ(D0, "daily", "2027-05-04").length === 181);
  T.ctl.destroy();

  /* 9g. khách ngoài khi đặt: dán nhiều email */
  T = v2(); await flush();
  T.clickAt("cabin", "17:00"); await flush();
  T.f("who").dispatchEvent(new T.w.Event("focus")); await flush();
  T.setv("who", "a@x.vn, lan.nguyen@ecentric.vn; b@y.com.vn");
  const pc = T.$$(".pmrm-scrim .pmrm-chip");
  ok("dán nhiều email (phẩy / chấm phẩy) → nhiều chip; người nội bộ nhận ra theo email", pc.length === 3 && pc[0].classList.contains("pmrm-chip--ext") && /Nguyễn Lan/.test(pc[1].textContent) && !pc[1].classList.contains("pmrm-chip--ext") && pc[2].classList.contains("pmrm-chip--ext"));
  T.setv("who", "khach.moi@"); 
  ok("gõ email chưa đủ: gợi ý nói rõ Enter để mời khách ngoài", /khách ngoài/.test(T.$(".pmrm-scrim .pmrm-opts").textContent));
  T.setv("subject", "Gặp đối tác"); T.f("who").value = "doitac@abc.com"; submitDlg(T); await flush();
  const bkE = T.calls.filter(x => x.m === "rooms.book")[0];
  ok("email gõ dở chưa Enter vẫn được mời khi bấm Đặt, không gửi repeat khi không lặp", bkE && JSON.parse(bkE.a.attendees).join() === "a@x.vn,lan.nguyen@ecentric.vn,b@y.com.vn,doitac@abc.com" && !("repeat" in bkE.a));
  T.ctl.destroy();

  /* 9h. kéo thả */
  T = v2(); await flush();
  const yOf = name => T.$$(".pmrm-lane[data-room]").findIndex(l => l.getAttribute("data-room") === name) * 58 + 20;
  const mouse = (elm, type, x, y) => elm.dispatchEvent(new T.w.MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 }));
  const x12 = 4 * 100 + 1;   /* 12:00 = 240' từ 08:00 = 400px */
  let src = blkOf(T, "cabin", /Sync dự án/)[0];
  mouse(src, "mousedown", x12, yOf("cabin")); mouse(T.w.document, "mousemove", x12 + 60, yOf("cabin")); mouse(T.w.document, "mousemove", x12 + 200, yOf("phong"));
  const gh = T.lane("phong").querySelector(".pmrm-ghost");
  ok("kéo sang Phong 14:00 (trùng Ban giám đốc): bóng đỏ báo trùng, khối gốc mờ", gh.style.display === "block" && gh.classList.contains("pmrm-ghost--bad") && /trùng 14:00–16:00/.test(gh.textContent) && src.classList.contains("pmrm-blk--drag"));
  mouse(T.w.document, "mouseup", x12 + 200, yOf("phong")); src.click(); await flush();
  ok("thả vào chỗ trùng → không gọi server, báo lỗi, không mở hộp", updates(T).length === 0 && /Không chuyển được: trùng/.test(lastToast(T).m) && !T.$(".pmrm-scrim"));
  src = blkOf(T, "cabin", /Sync dự án/)[0];
  mouse(src, "mousedown", x12, yOf("cabin")); mouse(T.w.document, "mousemove", x12 + 100, yOf("phong")); mouse(T.w.document, "mouseup", x12 + 100, yOf("phong"));
  T.lane("phong").click(); await flush();
  ok("kéo sang Phong +1 giờ → update(event_id, start 13:00, end 14:00, room=phong), click sau khi thả không mở hộp", updates(T).length === 1 && JSON.stringify(updates(T)[0].a) === JSON.stringify({ event_id: "ev5", start: D0 + " 13:00:00", end: D0 + " 14:00:00", room: "phong" }) && !T.$(".pmrm-scrim"), JSON.stringify(updates(T).map(x => x.a)));
  ok("sau khi thả: khối ở làn Phong 13:00–14:00 'chờ phòng nhận', thông báo chuyển", blkOf(T, "phong", /Sync dự án/).length === 1 && /13:00–14:00/.test(blkOf(T, "phong", /Sync/)[0].textContent) && blkOf(T, "phong", /Sync/)[0].classList.contains("pmrm-blk--pend") && !blkOf(T, "cabin", /Sync/).length && /Đã chuyển sang 5\.1 - Phong 13:00–14:00/.test(lastToast(T).m));
  const rb = blkOf(T, "hoa", /Giao ban/)[0];
  mouse(rb, "mousedown", 8 * 100 + 1, yOf("hoa")); mouse(T.w.document, "mousemove", 8 * 100 + 120, yOf("hoa")); mouse(T.w.document, "mouseup", 8 * 100 + 120, yOf("hoa")); await flush();
  ok("họp lặp: không kéo được (dùng hộp Sửa)", updates(T).length === 1 && !rb.classList.contains("pmrm-blk--drag"));
  T.ctl.destroy();
  let rej = null;
  T = v2({ "rooms.update": () => new Promise((_, no) => { rej = no; }) }); await flush();
  src = blkOf(T, "cabin", /Sync dự án/)[0];
  mouse(src, "mousedown", x12, yOf("cabin")); mouse(T.w.document, "mousemove", x12 + 100, yOf("cabin")); mouse(T.w.document, "mouseup", x12 + 100, yOf("cabin")); await flush();
  ok("đang lưu khi kéo: khối hiện ở chỗ mới (mờ, chặn kéo / bấm lần 2)", blkOf(T, "cabin", /Sync/).length === 1 && /13:00–14:00/.test(blkOf(T, "cabin", /Sync/)[0].textContent) && blkOf(T, "cabin", /Sync/)[0].classList.contains("pmrm-blk--busyop"));
  blkOf(T, "cabin", /Sync/)[0].click(); await flush();
  ok("… bấm khối đang lưu không mở hộp", !T.$(".pmrm-scrim"));
  rej(smErr("Phòng 5.2 - Cabin đã có người đặt 13:00–14:00 (Lê Hương).")); await flush();
  ok("server từ chối → khối về chỗ cũ 12:00–13:00 'Bạn đặt', báo đúng thông điệp server", blkOf(T, "cabin", /Sync/).length === 1 && /12:00–13:00/.test(blkOf(T, "cabin", /Sync/)[0].textContent) && blkOf(T, "cabin", /Sync/)[0].classList.contains("pmrm-blk--mine") && lastToast(T).bad && /Phòng 5\.2 - Cabin đã có người đặt 13:00–14:00 \(Lê Hương\)\./.test(lastToast(T).m) && /giữ nguyên/.test(lastToast(T).m));
  T.ctl.destroy();

  /* 9i. lỗi server khi sửa + xem ngày xa */
  T = v2({ "rooms.update": () => Promise.reject(smErr("Chỉ người đặt mới sửa được cuộc họp này.")) }); await flush();
  T.$('[data-act="edit"][data-ev="ev5"]').click(); await flush();
  T.setv("subject", "Đổi tên"); submitDlg(T); await flush();
  ok("sửa lỗi server → hiện nguyên văn trong hộp, hộp mở, nút 'Lưu thay đổi' bật lại", T.$(".pmrm-scrim") && T.$(".pmrm-scrim [data-warn]").textContent === "Chỉ người đặt mới sửa được cuộc họp này." && !T.$(".pmrm-scrim [data-submit]").disabled && T.$(".pmrm-scrim [data-submit]").textContent === "Lưu thay đổi");
  T.key(T.$(".pmrm-dlg"), "Escape"); await flush();
  T.$("[data-pick]").value = "2026-11-25"; T.$("[data-pick]").dispatchEvent(new T.w.Event("change", { bubbles: true })); await flush();
  ok("xem ngày xa (25/11): mine() tải đủ xa (days=21) để khối của bạn ngày đó vẫn sửa được", T.calls.some(x => x.m === "rooms.mine" && x.a.days === 21));
  ok("v2: không lỗi console", T.errs.length === 0, T.errs.join(" | "));
  T.ctl.destroy();

  /* ---------- 10. mô tả (06/11) */
  T = v2(); await flush();
  T.$('[data-act="book"]').click(); await flush();
  ok("hộp đặt có ô 'Mô tả (không bắt buộc)' (textarea, 4000 ký tự)", T.f("desc") && T.f("desc").tagName === "TEXTAREA" && T.f("desc").maxLength === 4000 && /Mô tả/.test(T.$('label[for="' + T.f("desc").id + '"]').textContent));
  T.f("subject").value = "Review"; T.f("desc").value = "  Agenda:\n- KPI  ";
  T.setv("start", "17:00"); T.setv("end", "17:30");
  submitDlg(T); await flush();
  const bkd = T.calls.filter(x => x.m === "rooms.book").pop();
  ok("đặt: gửi description đã bỏ khoảng trắng đầu/cuối", bkd && bkd.a.description === "Agenda:\n- KPI", bkd && JSON.stringify(bkd.a));
  T.ctl.destroy();
  T = v2({ "rooms.detail": () => ({ description: "Cũ", editable: true }) }); await flush();
  T.$('[data-act="edit"][data-ev="ev5"]').click(); await flush();
  ok("sửa: tải mô tả qua rooms.detail rồi điền sẵn, cho sửa", T.calls.some(x => x.m === "rooms.detail" && x.a.event_id === "ev5") && T.f("desc").value === "Cũ" && !T.f("desc").readOnly);
  T.f("desc").value = "Mới"; submitDlg(T); await flush();
  ok("sửa: chỉ gửi description khi đổi", JSON.stringify(updates(T).pop().a) === JSON.stringify({ event_id: "ev5", description: "Mới" }), JSON.stringify(updates(T).map(x => x.a)));
  T.ctl.destroy();
  T = v2({ "rooms.detail": () => ({ description: "Viết trên Teams", editable: false }) }); await flush();
  T.$('[data-act="edit"][data-ev="ev5"]').click(); await flush();
  ok("sửa: mô tả viết trên Teams -> chỉ đọc + ghi chú sửa trên Teams, không gửi", T.f("desc").readOnly && /Teams\/Outlook/.test(T.$("[data-desc-note]").textContent) && !T.$("[data-desc-note]").hidden);
  T.ctl.destroy();
  T = v2({ "rooms.detail": () => new Promise(() => {}) }); await flush();
  T.$('[data-act="edit"][data-ev="ev5"]').click(); await flush();
  T.setv("start", "12:30"); T.setv("end", "13:30"); submitDlg(T); await flush();
  ok("sửa khi mô tả chưa tải xong: ô khoá, không gửi description (không xoá nhầm)", T.f && !("description" in (updates(T).pop() || { a: {} }).a));
  T.ctl.destroy();

  /* ---------- 11. mở thẳng /pm#rooms khi trang chưa tải xong (06/11): lỗi CSRF lần đầu -> tự thử lại */
  {
    let n = 0;
    const T3 = setup({ h: { "rooms.day": a => { n++; if (n === 1) { const e = new Error("Invalid Request"); e.status = 400; e.responseJSON = { exc_type: "CSRFTokenError" }; throw e; } return dayData(a.date); } } });
    await tick(700); await flush();
    ok("CSRF 'Invalid Request' lần đầu (trang chưa có csrf_token) -> tự thử lại, lịch phòng hiện đủ, không báo lỗi",
      n >= 2 && T3.$$(".pmrm-lane[data-room]").length === 4 && !/Chưa tải được/.test(T3.$("#v").textContent), "day calls=" + n + " lanes=" + T3.$$(".pmrm-lane[data-room]").length + " txt=" + (T3.$("#v").textContent.match(/Chưa tải được.{0,60}/) || [""])[0]);
    T3.ctl.destroy();
  }

  /* ---------- 8. tĩnh */
  ok("asset: không ký tự Jinja, một global PMRooms, có esc", !/\{\{|\{%|\{#/.test(JS) && /root\.PMRooms = /.test(JS));
  ok("CSS: mobile ≤640px (ô nhập 16px), lưới cuộn ngang, namespace .pmrm-", /@media \(max-width:640px\)/.test(CSS) && /font-size:16px/.test(CSS) && /\.pmrm-tl\{overflow-x:auto/.test(CSS) && !/(^|\})\s*(body|html|\.panel)\s*\{/.test(CSS));

  let bad = 0;
  res.forEach(r => { if (!r.c) bad++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - bad}/${res.length} passed`);
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
