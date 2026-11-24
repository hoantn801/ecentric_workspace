/* pm_home_rooms_card.test.js — card "Phòng họp" trên trang chủ (05/11/2026). Chạy trên main_section.html THẬT
 * + pm_home_calendar.js thật, fetch giả. Chạy: NODE_PATH=<node_modules có jsdom> node pm_home_rooms_card.test.js
 * Kiểm: card nằm giữa "Truy cập nhanh" và "Chính sách & Quy định", khung 5 dòng xương có sẵn (không nhảy bố cục),
 * điền trạng thái Trống / Bận (gộp lịch liền nhau) / sắp có người / Chưa kết nối + thanh 08–19 + vạch giờ, badge x/5 trống,
 * bấm dòng → /pm#rooms, tự làm mới 60 s, lỗi / SYNC_OFF / 403 → một dòng nhẹ, widget Lịch hôm nay vẫn chạy. */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");
const APP = path.join(__dirname, "..", "..", "..", "..");
const SRC = fs.readFileSync(path.join(APP, "public", "js", "pm_home_calendar.js"), "utf8");
const PAGE = fs.readFileSync(path.join(APP, "legacy_pages", "home", "main_section.html"), "utf8");
const res = [], ok = (n, c, x) => res.push({ n, c: !!c, x });
const tick = () => new Promise(r => setTimeout(r, 0));
const flush = async () => { for (let i = 0; i < 8; i++) await tick(); };
const D0 = "2026-11-05";
const bk = (s, e, who) => ({ start: D0 + " " + s + ":00", end: D0 + " " + e + ":00", who, mine: false, uid: who + s, all_day: false });
function day() {
  return { date: D0, now: D0 + " 10:15:00", sync_on: true, rooms: [
    { name: "phong", code: "5.1", title: "Phong", label: "5.1 - Phong", bookings: [bk("09:30", "10:30", "A"), bk("10:30", "11:00", "B"), bk("14:00", "16:00", "C")] },
    { name: "hoa", code: "1.1", title: "Hoả", label: "1.1 - Hoả", bookings: [bk("11:00", "12:00", "D")] },
    { name: "tho", code: "1.2", title: "Th<b>ổ</b>", label: "1.2 - Thổ", bookings: [bk("10:30", "11:30", "E")] },
    { name: "thuy", code: "1.3", title: "Thuỷ", label: "1.3 - Thuỷ", error: "ROOM_NOT_FOUND", bookings: [] },
    { name: "cabin", code: "5.2", title: "Cabin", label: "5.2 - Cabin", bookings: [] }] };
}

function boot(reply) {
  const errors = [], calls = [], ivs = [], vc = new VirtualConsole();
  vc.on("error", (...a) => errors.push(a.map(String).join(" ")));
  vc.on("jsdomError", e => { if (!/Not implemented|Could not parse CSS/.test(String(e && e.message))) errors.push("jsdomError " + (e && e.message)); });
  const dom = new JSDOM(PAGE, { url: "https://team.ecentric.vn/home", runScripts: "outside-only", pretendToBeVisual: true, virtualConsole: vc });
  const w = dom.window;
  w.frappe = { csrf_token: "x" };
  w.Element.prototype.scrollIntoView = function () { };
  const si = w.setInterval.bind(w);
  w.setInterval = (fn, ms) => { if (ms === 60000) { ivs.push(fn); return 0; } return si(fn, ms); };
  w.fetch = (url, opt) => {
    calls.push({ url, method: opt && opt.method, body: JSON.parse((opt && opt.body) || "{}") });
    if (/rooms\.day$/.test(url)) return reply();
    let msg = null;
    if (/schedule\.today$/.test(url)) msg = { date: D0, now: D0 + " 10:15:00", sync_on: true, meetings: [], blocks: [], due_unscheduled: 0 };
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: msg }) });
  };
  w.eval(SRC);
  return { w, d: w.document, errors, calls, ivs };
}
const okReply = data => () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: data }) });

(async () => {
  /* ---------- markup (trạng thái đầu nằm trong nguồn trang) */
  let B = boot(() => new Promise(() => {}));   /* chưa trả lời: chỉ xem khung */
  const card = B.d.querySelector("[data-ec-rooms]");
  const panels = card ? Array.from(card.parentNode.children) : [];
  const titleOf = p => ((p.querySelector(".panel-title") || {}).textContent || "").trim();
  const i = panels.indexOf(card);
  ok("card có trong main_section.html, cùng cột, GIỮA Truy cập nhanh và Chính sách & Quy định", card && card.classList.contains("panel") && titleOf(panels[i - 1]) === "Truy cập nhanh" && /^Chính sách & Quy định/.test(titleOf(panels[i + 1])));
  ok("header: tiêu đề Phòng họp + badge rỗng + link Xem lịch → /pm#rooms", card && /^Phòng họp/.test(titleOf(card)) && card.querySelector("[data-ec-rooms-badge]").textContent === "" && card.querySelector('.panel-action[href="/pm#rooms"]').textContent.trim() === "Xem lịch →");
  const list = card.querySelector("[data-ec-rooms-list]");
  ok("khung giữ chỗ: 5 dòng xương trong markup, aria-busy", list.children.length === 5 && list.querySelectorAll(".ec2-rm-sk").length === 5 && list.getAttribute("aria-busy") === "true");
  const a0 = PAGE.indexOf('<div class="panel ec2-rooms" data-ec-rooms'), seg = PAGE.slice(a0, PAGE.indexOf("Chính sách & Quy định", a0));
  ok("phần thêm không có {{ {% {# và không có <script|style id=ec-…>", a0 > 0 && !/\{\{|\{%|\{#/.test(seg) && !/<(script|style)\b/.test(seg));
  ok("CSS card nằm trong stylesheet trang, cạnh khối .ec2-col; dòng thật = dòng xương = 54px, bỏ thanh 08–19", /\.ecentric-app \.ec2-col \.quick-grid\{grid-template-columns:repeat\(4,1fr\)\}\r?\n  \/\* ---- v2: card Phong hop/.test(PAGE) && /\.ec2-rm-list>li\{min-height:54px/.test(PAGE) && !/ec2-rm-foot|ec2-rm-bar/.test(PAGE));
  await flush(); await new Promise(r => setTimeout(r, 450)); await flush();
  ok("gọi rooms.day bằng POST một lần", B.calls.filter(c => /rooms\.day$/.test(c.url)).length === 1 && B.calls.find(c => /rooms\.day$/.test(c.url)).method === "POST");
  ok("widget Lịch hôm nay vẫn tải như cũ (schedule.today)", B.calls.some(c => /schedule\.today$/.test(c.url)));
  B.w.close();

  /* ---------- có dữ liệu */
  B = boot(okReply(day())); await flush();
  const c2 = B.d.querySelector("[data-ec-rooms]"), rows = Array.from(c2.querySelectorAll(".ec2-rm-row"));
  const st = r => r.querySelector(".ec2-rm-st");
  ok("5 dòng (bằng số dòng xương, không nhảy), mã mono + tên", rows.length === 5 && c2.querySelector("[data-ec-rooms-list]").children.length === 5 && rows[0].querySelector(".ec2-rm-code").textContent === "5.1" && rows[0].querySelector(".ec2-rm-name").textContent === "Phong");
  ok("Phong: đang họp, gộp lịch liền nhau → còn 45', đỏ", st(rows[0]).textContent === "Đang họp · còn 45'" && st(rows[0]).classList.contains("ec2-rm-st--busy"));
  const sub = r => r.querySelector(".ec2-rm-sub").textContent;
  ok("Phong: dòng phụ = cuộc họp đang diễn ra", sub(rows[0]) === "A · 09:30–10:30");
  ok("Hoả: Trống đến 11:00, xanh + dòng phụ lịch kế tiếp", st(rows[1]).textContent === "Trống đến 11:00" && st(rows[1]).classList.contains("ec2-rm-st--free") && sub(rows[1]) === "tiếp theo 11:00–12:00 · D");
  ok("Thổ: ≤30 phút nữa có người → Sắp họp, cam", st(rows[2]).textContent === "Sắp họp 10:30" && st(rows[2]).classList.contains("ec2-rm-st--soon"));
  ok("Thuỷ (ROOM_NOT_FOUND): Chưa kết nối, không vỡ", st(rows[3]).textContent === "Chưa kết nối" && st(rows[3]).classList.contains("ec2-rm-st--off"));
  ok("Cabin: Trống cả ngày + không có lịch hôm nay", st(rows[4]).textContent === "Trống cả ngày" && sub(rows[4]) === "không có lịch hôm nay");
  ok("badge: 3/5 trống", c2.querySelector("[data-ec-rooms-badge]").textContent === "3/5 trống");
  ok("bấm dòng → /pm#rooms (chỉ xem, không có nút đặt)", rows.every(r => r.getAttribute("href") === "/pm#rooms") && !c2.querySelector("button"));
  ok("esc tên phòng từ server", !rows[2].querySelector(".ec2-rm-name b") && rows[2].querySelector(".ec2-rm-name").textContent === "Th<b>ổ</b>");
  ok("tự làm mới mỗi 60 s (bỏ qua khi tab ẩn)", B.ivs.length === 1 && (() => { const n = B.calls.length; B.ivs[0](); return B.calls.length === n + 1; })());
  ok("không lỗi console", B.errors.length === 0, B.errors.join(" | "));
  B.w.close();

  /* ---------- 24/11 phương án A: chia tầng, số chỗ, lịch của bạn */
  const dF = day();
  dF.rooms[0].floor = "Lầu 5"; dF.rooms[1].floor = "Lầu 1"; dF.rooms[2].floor = "Lầu 1"; dF.rooms[3].floor = "Lầu 1"; dF.rooms[4].floor = "Lầu 5";
  dF.rooms[1].capacity = 8;
  dF.rooms[4].bookings = [Object.assign(bk("14:00", "14:30", "Hoàn"), { mine: true })];
  dF.rooms[0].bookings = [Object.assign(bk("10:00", "10:30", "Hoàn"), { mine: true })];
  B = boot(okReply(dF)); await flush();
  const lF = B.d.querySelector("[data-ec-rooms-list]"), fl = Array.from(lF.querySelectorAll(".ec2-rm-floor")).map(x => x.textContent);
  const rF = Array.from(lF.querySelectorAll(".ec2-rm-row"));
  ok("chia theo tầng: Lầu 1 (1.1, 1.2, 1.3) rồi Lầu 5 (5.1, 5.2)", fl.join("|") === "Lầu 1|Lầu 5" && rF.map(r => r.querySelector(".ec2-rm-code").textContent).join(",") === "1.1,1.2,1.3,5.1,5.2");
  ok("số chỗ ở dòng phụ", rF[0].querySelector(".ec2-rm-sub").textContent.indexOf("8 chỗ · ") === 0);
  ok("đang họp lịch của bạn → 'Bạn đang họp' màu navy", rF[3].querySelector(".ec2-rm-st").textContent === "Bạn đang họp" && rF[3].querySelector(".ec2-rm-st").classList.contains("ec2-rm-st--mine"));
  ok("lịch kế tiếp của bạn → 'Bạn đặt 14:00' + dòng phụ ghi Bạn", rF[4].querySelector(".ec2-rm-st").textContent === "Bạn đặt 14:00" && /14:00–14:30 · Bạn$/.test(rF[4].querySelector(".ec2-rm-sub").textContent));
  B.w.close();

  /* ---------- QC 05/11: quay lại tab sau khi ẩn lâu -> tải lại ngay (không đợi tới 60 s); lỗi thoáng qua sau khi đã có dữ liệu
   * -> giữ các dòng đang có (không sập thành một dòng "Chưa kết nối", không nhảy bố cục) */
  let fail = false;
  B = boot(() => fail ? Promise.reject(new Error("net")) : okReply(day())()); await flush();
  const nDay = () => B.calls.filter(c => /rooms\.day$/.test(c.url)).length;
  const n0 = nDay();
  const card3 = B.d.querySelector("[data-ec-rooms]");
  card3._ecRooms._at -= 5 * 60000;   /* dữ liệu đã cũ 5 phút (tab ẩn) */
  Object.defineProperty(B.d, "hidden", { configurable: true, get: () => false });
  B.d.dispatchEvent(new B.w.Event("visibilitychange")); await flush();
  ok("quay lại tab (dữ liệu > 60 s) → tải lại ngay", nDay() === n0 + 1, nDay() + " vs " + n0);
  B.d.dispatchEvent(new B.w.Event("visibilitychange")); await flush();
  ok("… vừa tải xong thì không tải lại lần nữa", nDay() === n0 + 1);
  fail = true; B.ivs[0](); await flush();
  const l3 = B.d.querySelector("[data-ec-rooms-list]");
  ok("lỗi mạng thoáng qua sau khi đã có dữ liệu → vẫn 5 dòng phòng, badge giữ", l3.querySelectorAll(".ec2-rm-row").length === 5 && B.d.querySelector("[data-ec-rooms-badge]").textContent === "3/5 trống", l3.textContent);
  B.w.close();

  /* ---------- lỗi / chưa kết nối */
  const off = day(); off.sync_on = false; off.rooms.forEach(r => { r.error = "SYNC_OFF"; r.bookings = []; });
  for (const [name, rep, want] of [
    ["SYNC_OFF", okReply(off), "Chưa kết nối lịch phòng"],
    ["HTTP 500", () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ exc_type: "X" }) }), "Chưa kết nối lịch phòng"],
    ["lỗi mạng", () => Promise.reject(new Error("net")), "Chưa kết nối lịch phòng"],
    ["403 (không có quyền PM)", () => Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ exc_type: "PermissionError" }) }), "Chưa có quyền xem lịch phòng"]]) {
    B = boot(rep); await flush();
    const l = B.d.querySelector("[data-ec-rooms-list]");
    ok(name + " → một dòng nhẹ '" + want + "', badge rỗng", l.children.length === 1 && l.textContent.trim() === want && B.d.querySelector("[data-ec-rooms-badge]").textContent === "" && l.getAttribute("aria-busy") === "false");
    B.w.close();
  }
  ok("JS: không ký tự Jinja, ES5 (không template literal / arrow)", !/\{\{|\{%|\{#/.test(SRC) && !/`/.test(SRC.replace(/\/\/.*$/gm, "")) && !/=>/.test(SRC));

  let bad = 0;
  res.forEach(r => { if (!r.c) bad++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - bad}/${res.length} passed`);
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
