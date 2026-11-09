/* pm_rooms.js — Phòng họp (05/11/2026, demo v2 PO duyệt). Asset tĩnh, /pm tải lười khi mở #rooms
 * hoặc tab "Phòng họp" trong #schedule (pm_app.html pmRoomsAssets, cùng ?v= với pm_redesign.js).
 * Một global: window.PMRooms.render(container, {api, errOf, toast, head, mode:"page"|"tab"}) -> {refresh, destroy}.
 *   api(method, args) -> Promise (host /pm truyền api() của trang); thiếu thì tự POST /api/method kèm CSRF.
 *   mode "page" = trang #rooms (3 ô tóm tắt + lưới + "Phòng bạn đã đặt"); "tab" = tab trong #schedule (chỉ lưới).
 * Dữ liệu: ecentric_workspace.pm.api.rooms.{day, mine, book, update, booking_state, cancel} + assignment.list_assignable.
 * v2 (06/11/2026, PO "đặt trên Teams hay ERP đơn giản y hệt nhau"): bấm khối "Bạn đặt" / nút Sửa = CÙNG hộp đặt phòng ở chế độ
 *   sửa (chỉ gửi trường đã đổi, họp lặp hỏi Chỉ buổi này / Cả chuỗi); kéo khối (chuột) sang giờ / phòng khác = update, lỗi thì
 *   trả lại chỗ cũ; ô Lặp lại + Đến ngày (≤180 ngày, đếm buổi như server); mời khách ngoài bằng email (chip khác màu).
 * Nguồn sự thật là lịch Exchange của từng phòng: client chỉ kiểm trùng để báo sớm, server quyết định cuối.
 * Giờ là chuỗi giờ địa phương của site ("YYYY-MM-DD HH:MM:SS"): tính bằng phút, không qua Date của trình duyệt.
 * Mọi chuỗi từ server đi qua esc(). Sửa giao diện: chỉ sửa file này + pm_rooms.css. */
(function (root) {
"use strict";
if (root.PMRooms) return;

const NS = "ecentric_workspace.pm.api.";
const H0 = 8 * 60, H1 = 19 * 60, SPAN = H1 - H0, STEP = 30;
const REFRESH_MS = 60000, POLL_MS = [2000, 4000, 8000, 16000];   /* hỏi phòng ~30 s sau khi đặt */
const WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const WDN = ["Chủ nhật", "thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy"];
const REPEATS = ["none", "daily", "weekdays", "weekly", "biweekly", "monthly"];
const MAX_SERIES_DAYS = 180, MAX_OCC = 200, MAX_GUESTS = 50, REP_DAYS = 28;   /* = rooms._MAX_SERIES_DAYS / _MAX_OCCURRENCES / _MAX_GUESTS.
   180 = BookingWindowInDays của phòng, tính từ HÔM NAY (rooms._horizon): cả ngày họp lẻ lẫn ngày kết thúc lặp. */
const EMAIL = /^[^@\s,;<>"']+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/;              /* = rooms._EMAIL */
const EXT_TIP = "Người ngoài công ty sẽ nhận lời mời Teams qua email";
const OFF_TEXT = { SYNC_OFF: "Chưa bật đồng bộ lịch Teams", ROOM_NOT_FOUND: "Phòng chưa được tạo trên Microsoft 365" };
let UID = 0;

const pad = n => (n < 10 ? "0" : "") + n;
const esc = s => (s == null ? "" : String(s)).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const hm = m => (m >= 1440 ? "24:00" : pad(Math.floor(m / 60)) + ":" + pad(m % 60));
const toMin = t => { const x = /^(\d{1,2}):(\d{2})/.exec(t || ""); return x ? (+x[1]) * 60 + (+x[2]) : null; };
const pct = m => ((Math.max(H0, Math.min(H1, m)) - H0) / SPAN * 100);
function ymdAdd(ymd, n) {
  const p = ymd.split("-").map(Number), t = new Date(Date.UTC(p[0], p[1] - 1, p[2] + n));
  return t.getUTCFullYear() + "-" + pad(t.getUTCMonth() + 1) + "-" + pad(t.getUTCDate());
}
const wday = ymd => { const p = ymd.split("-").map(Number); return WD[new Date(Date.UTC(p[0], p[1] - 1, p[2])).getUTCDay()]; };
const dm = ymd => ymd.slice(8, 10) + "/" + ymd.slice(5, 7);
const dow = ymd => { const p = ymd.split("-").map(Number); return new Date(Date.UTC(p[0], p[1] - 1, p[2])).getUTCDay(); };
function dayDiff(a, b) { const u = x => { const p = x.split("-").map(Number); return Date.UTC(p[0], p[1] - 1, p[2]); }; return Math.round((u(b) - u(a)) / 86400000); }
function repText(rep, day) {
  const w = WDN[dow(day)];
  return ({ none: "Không lặp lại", daily: "Hằng ngày", weekdays: "Các ngày trong tuần (T2–T6)", weekly: "Hằng tuần vào " + w,
            biweekly: "2 tuần một lần vào " + w, monthly: "Hằng tháng ngày " + (+day.slice(8, 10)) })[rep] || "";
}
/* các ngày họp của một kiểu lặp, khớp rooms._occurrences (tuần tính từ T2; hằng tháng ngày 29–31 rơi vào ngày cuối của tháng ngắn như Outlook) */
function occurrences(first, rep, until) {
  if (!rep || rep === "none") return [first];
  const out = [], d0 = dow(first), mon0 = ymdAdd(first, -((d0 + 6) % 7)), dom0 = +first.slice(8, 10);
  for (let d = first; d <= until && out.length < MAX_OCC; d = ymdAdd(d, 1)) {
    const w = dow(d);
    let ok = false;
    if (rep === "daily") ok = true;
    else if (rep === "weekdays") ok = w >= 1 && w <= 5;
    else if (rep === "weekly" || rep === "biweekly") ok = w === d0 && (rep === "weekly" || Math.floor(dayDiff(mon0, ymdAdd(d, -((w + 6) % 7))) / 7) % 2 === 0);
    else if (rep === "monthly") ok = +d.slice(8, 10) === Math.min(dom0, lastDom(d));
    if (ok) out.push(d);
  }
  return out;
}
function lastDom(ymd) { const p = ymd.split("-").map(Number); return new Date(Date.UTC(p[0], p[1], 0)).getUTCDate(); }
const safeUrl = u => (/^https:\/\//i.test(String(u || "")) ? String(u) : "");   /* chỉ link https (join_url) */
function localYmd() { const d = new Date(); return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
/* một lịch -> {s, e} phút tính từ 00:00 của ngày `day` (cắt ở 0 / 1440), null nếu không chạm ngày đó */
function spanOn(b, day) {
  const s0 = String(b.start || ""), e0 = String(b.end || "");
  if (s0.length < 16 || e0.length < 16) return null;
  const ds = s0.slice(0, 10), de = e0.slice(0, 10);
  if (ds > day || de < day) return null;
  let s = ds < day ? 0 : toMin(s0.slice(11, 16)), e = de > day ? 1440 : toMin(e0.slice(11, 16));
  if (b.all_day) { s = 0; e = 1440; }
  return e > s ? { s, e } : null;
}
function fold(s) { return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d"); }
function cleanMsg(s) { return String(s).replace(/<[^>]*>/g, " ").replace(/^\s*[\w.]*(Error|Exception):\s*/, "").replace(/\s+/g, " ").trim(); }
function serverMsg(sm) {
  try {
    const arr = typeof sm === "string" ? JSON.parse(sm) : sm;
    for (let i = 0; i < (arr || []).length; i++) {
      let o = arr[i];
      if (typeof o === "string") { try { o = JSON.parse(o); } catch (_) { o = { message: o }; } }
      const m = o && (o.message || o.title);
      if (m) return cleanMsg(m);
    }
  } catch (_) { /* không phải danh sách thông báo */ }
  return "";
}
/* fetch dự phòng khi trang chủ không truyền api: POST JSON + CSRF, lỗi mang _server_messages của Frappe */
function csrf() { return (root.frappe && root.frappe.csrf_token) || root.csrf_token || ((document.cookie.match(/csrf_token=([^;]+)/) || [])[1]) || ""; }
async function fetchApi(method, args) {
  const r = await fetch("/api/method/" + method, { method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-Frappe-CSRF-Token": csrf() },
    body: JSON.stringify(args || {}) });
  let j = {};
  try { j = await r.json(); } catch (_) { /* thân rỗng */ }
  if (!r.ok || j.exc_type) {
    const e = new Error(j.exception || ("HTTP " + r.status));
    e._server_messages = j._server_messages; e.status = r.status; throw e;
  }
  return j.message;
}

/* 09/11/2026: lần mở đầu trang /pm#rooms báo "Invalid Request" (HTTP 400). Đọc lịch đi POST kèm
   CSRF, nhưng lúc trang vừa tải frappe chưa sẵn -> token rỗng -> Frappe từ chối; bấm "Thử lại" mới
   được. Hàm CHỈ ĐỌC (server cho GET) hỏng thì tự thử lại bằng GET (không cần CSRF).
   Ghi (book/update/cancel) giữ nguyên POST + CSRF. */
const READ_GET = { "rooms.day": 1, "rooms.mine": 1, "rooms.detail": 1, "rooms.booking_state": 1 };
async function getApi(method, args) {
  const qs = Object.keys(args || {}).filter(k => args[k] != null)
    .map(k => encodeURIComponent(k) + "=" + encodeURIComponent(args[k])).join("&");
  const r = await fetch("/api/method/" + method + (qs ? "?" + qs : ""), { method: "GET", credentials: "include",
    headers: { Accept: "application/json" } });
  let j = {};
  try { j = await r.json(); } catch (_) { /* thân rỗng */ }
  if (!r.ok || j.exc_type) {
    const e = new Error(j.exception || ("HTTP " + r.status));
    e._server_messages = j._server_messages; e.status = r.status; throw e;
  }
  return j.message;
}

function render(el, opts) {
  opts = opts || {};
  if (el._pmrm) el._pmrm.destroy();
  const mode = opts.mode === "tab" ? "tab" : "page";
  const POLLS = Array.isArray(opts.pollMs) && opts.pollMs.length ? opts.pollMs : POLL_MS;   /* pollMs: chỉ để test */
  const me = ++UID, idp = "pmrm" + me + "-";
  const S = { date: null, today: null, cache: {}, mine: [], mineErr: "", pending: {}, err: "", loading: false,
              nowMin: null, nowAt: 0, seq: 0, dead: false, stale: false, timers: [], people: null, peopleP: null,
              confirm: null, dlg: null, gone: {}, moving: null, noClick: false };   /* gone: event_id / uid vừa huỷ (Graph / lịch phòng có thể trễ vài giây) */
  const call = (m, a) => {
    const go = typeof opts.api === "function" ? () => opts.api(NS + m, a || {}) : () => fetchApi(NS + m, a);
    if (!READ_GET[m]) return go();
    /* đọc hỏng (vd 400 CSRF lúc trang vừa tải) -> thử lại một lần bằng GET; GET cũng hỏng thì báo lỗi gốc */
    return Promise.resolve().then(go).catch(e => getApi(NS + m, a || {}).catch(() => { throw e; }));
  };
  function msgOf(e) {
    if (!e) return "Đã có lỗi, thử lại.";
    const sm = e._server_messages || (e.responseJSON && e.responseJSON._server_messages);
    let m = sm ? serverMsg(sm) : "";
    if (!m && typeof e.message === "string" && e.message.trim()) {
      const t = e.message.trim();
      m = t.charAt(0) === "[" ? serverMsg(t) : "";
      if (!m && t.charAt(0) !== "{" && t.charAt(0) !== "[") m = cleanMsg(t);
    }
    if (!m && typeof opts.errOf === "function") { try { m = cleanMsg(opts.errOf(e) || ""); } catch (_) { m = ""; } }
    return m || "Đã có lỗi, thử lại.";
  }
  /* gốc đã bị màn khác thay (host ghi đè #pm-view) -> tự dừng: không hỏi server, không toast nữa */
  function alive() { if (!S.dead && R && !R.isConnected) destroy(); return !S.dead; }
  function later(ms, fn) { const t = setTimeout(() => { S.timers = S.timers.filter(x => x !== t); if (alive()) fn(); }, ms); S.timers.push(t); return t; }

  /* ---------------- khung (trạng thái đầu nằm trong markup: xương 5 dòng, ô tóm tắt "—") */
  const bookBtn = '<button type="button" class="pmrm-btn pmrm-btn--pri" data-act="book" disabled>+ Đặt phòng</button>';
  const seg = '<div class="pmrm-seg" role="group" aria-label="Chọn ngày">' +
    '<button type="button" data-day="0" aria-pressed="true">Hôm nay</button><button type="button" data-day="1" aria-pressed="false">Mai</button>' +
    '<button type="button" data-day="2" aria-pressed="false">Ngày kia</button></div>' +
    '<label class="pmrm-btn pmrm-pick">Ngày khác <input type="date" data-pick aria-label="Chọn ngày khác"></label>';
  const legend = '<div class="pmrm-legend" aria-hidden="true"><span><i class="pmrm-sw pmrm-sw--busy"></i>Có người đặt</span>' +
    '<span><i class="pmrm-sw pmrm-sw--mine"></i>Bạn đặt</span><span><i class="pmrm-sw pmrm-sw--pend"></i>Chờ phòng nhận</span></div>';
  let skel = "";
  for (let i = 0; i < 5; i++) skel += '<div class="pmrm-skel"><i></i><b></b></div>';
  const head = mode === "page"
    ? (typeof opts.head === "function" ? opts.head("Phòng họp", "Lịch phòng họp văn phòng, lấy trực tiếp từ Teams/Outlook.", bookBtn)
      : '<div class="pmrm-ttl"><div><h1>Phòng họp</h1><p>Lịch phòng họp văn phòng, lấy trực tiếp từ Teams/Outlook.</p></div>' + bookBtn + "</div>")
    : "";
  const tile = (k, attr) => '<div class="pmrm-panel pmrm-tile"><span class="pmrm-k">' + k + '</span><div class="pmrm-big" ' + attr + ">—</div></div>";
  el.innerHTML = '<div class="pmrm pmrm--' + mode + '" data-pmrm>' + head +
    (mode === "page" ? '<div class="pmrm-bento">' + tile("Đang trống", "data-t-free") + tile("Trống sớm nhất tiếp theo", 'data-t-next') + tile("Bạn đặt hôm nay", "data-t-mine") + "</div>" : "") +
    '<div class="pmrm-panel pmrm-tlp"><div class="pmrm-bar">' + seg + '<span class="pmrm-sp"></span>' + legend + (mode === "tab" ? bookBtn : "") + "</div>" +
    '<div class="pmrm-msg" data-msg role="alert" hidden></div>' +
    '<div class="pmrm-tl" data-tl role="region" aria-label="Lịch phòng họp" aria-busy="true">' + skel + "</div></div>" +
    '<p class="pmrm-hint">Bấm chỗ trống để đặt (bước 30 phút), hoặc chọn một phòng rồi nhấn Enter. Đặt trên Teams/Outlook cũng hiện ở đây; đặt ở đây thì Teams của bạn và người được mời cũng có lịch + link họp.' +
    (mode === "tab" ? ' <a class="pmrm-link" href="/pm#rooms">Phòng bạn đã đặt →</a>' : "") + "</p>" +
    (mode === "page" ? '<section class="pmrm-panel pmrm-minep" aria-labelledby="' + idp + 'mh"><div class="pmrm-ph"><h2 class="pmrm-pt" id="' + idp + 'mh">Phòng bạn đã đặt</h2></div><div data-mine aria-live="polite"><p class="pmrm-empty">Đang tải…</p></div></section>' : "") +
    '<div class="pmrm-toast" role="status" aria-live="polite"></div></div>';
  const R = el.querySelector("[data-pmrm]");
  const $ = (s, r) => (r || R).querySelector(s), $$ = (s, r) => Array.prototype.slice.call((r || R).querySelectorAll(s));

  function toast(m, bad) {
    if (typeof opts.toast === "function") { try { opts.toast(m, !!bad); return; } catch (_) { /* rơi xuống toast riêng */ } }
    const t = $(".pmrm-toast"); if (!t) return;
    t.textContent = m; t.className = "pmrm-toast pmrm-toast--on" + (bad ? " pmrm-toast--err" : "");
    clearTimeout(S.toastT); S.toastT = setTimeout(() => { t.className = "pmrm-toast"; }, bad ? 5000 : 2600);
  }

  /* ---------------- dữ liệu */
  const nowMin = () => (S.nowMin == null ? null : S.nowMin + Math.floor((Date.now() - S.nowAt) / 60000));
  const dayData = d => S.cache[d] || null;
  const roomsOf = d => ((dayData(d) || {}).rooms) || [];
  const roomBy = (name, d) => roomsOf(d || S.date).find(r => r.name === name) || roomsOf(S.today).find(r => r.name === name) || null;
  /* bản tạm đã có trong mine(): cùng event_id, hoặc (chuỗi vừa đặt) các buổi mang series_id = id của chuỗi */
  const inMine = p => S.mine.some(x => x.event_id === p.event_id || (p.master && x.series_id === p.event_id));
  const mineBy = () => { const m = {}; S.mine.forEach(x => { if (x.uid) m[x.uid] = x; }); return m; };
  /* các khối của một phòng trong một ngày: busy (người khác) | mine (bạn, phòng đã nhận) | pend (chờ phòng nhận) */
  function items(r, day) {
    if (!r) return [];
    const mb = mineBy(), out = [], seen = {};
    (r.bookings || []).forEach(b => {
      if (b.uid && S.gone[b.uid]) return;
      const sp = spanOn(b, day); if (!sp) return;
      const m = b.mine ? mb[b.uid] : null;
      /* lịch của bạn đã đổi giờ / phòng (mine() hoặc bản vừa sửa là chuẩn) -> bỏ khối cũ trong lịch phòng, vẽ theo mine ở dưới.
       * Khác phòng chỉ tính khi đang chờ phòng nhận (vừa đổi phòng): cuộc họp đặt 2 phòng đã nhận vẫn hiện ở cả 2 làn. */
      if (m && (m.start !== b.start || m.end !== b.end || (m.room !== r.name && m.state === "pending"))) return;
      if (b.uid) seen[b.uid] = 1;
      const loc = b.mine ? Object.keys(S.pending).map(k => S.pending[k]).find(p => p.uid && p.uid === b.uid) : null;
      const subj = (m && m.subject) || (loc && loc.subject) || "";
      out.push({ s: sp.s, e: sp.e, kind: b.mine ? ((m && m.state === "pending") ? "pend" : "mine") : "busy",
                 who: b.who || "", subject: subj, uid: b.uid || "", event_id: (m && m.event_id) || (loc && loc.event_id) || "",
                 rec: !!((m && m.recurring) || (loc && loc.recurring)) });
    });
    const extra = S.mine.filter(x => x.room === r.name && x.state !== "declined" && !(x.uid && seen[x.uid]));
    Object.keys(S.pending).forEach(k => {
      const p = S.pending[k];
      if (!p.series && p.room === r.name && p.state !== "declined" && !(p.uid && seen[p.uid]) && !inMine(p)) extra.push(p);
    });
    extra.forEach(x => {
      const sp = spanOn(x, day); if (!sp) return;
      if (x.uid) seen[x.uid] = 1;
      out.push({ s: sp.s, e: sp.e, kind: x.state === "accepted" ? "mine" : "pend", who: "", subject: x.subject || "", uid: x.uid || "", event_id: x.event_id || "", rec: !!x.recurring });
    });
    return out.sort((a, b) => a.s - b.s || a.e - b.e);
  }
  /* skip(x) = bỏ qua chính cuộc họp đang sửa / đang kéo */
  const clashOf = (r, day, s, e, skip) => items(r, day).find(x => x.s < e && s < x.e && !(skip && skip(x))) || null;
  /* một cuộc của bạn theo event_id: mine() trước, rồi bản vừa đặt (chưa có trong mine) */
  const rowById = id => (id && (S.mine.find(x => x.event_id === id) || (S.pending[id] && !S.pending[id].series ? S.pending[id] : null))) || null;
  /* lúc này: busy (đến khi hết chuỗi lịch liền nhau) | soon (trống, ≤30' nữa có người) | free | off */
  function nowState(r) {
    if (!r || r.error) return { k: "off" };
    const n = nowMin(); if (n == null) return { k: "off" };
    const list = items(r, S.today).filter(x => x.kind !== "pend");
    const cur = list.find(x => x.s <= n && n < x.e);
    if (cur) { let end = cur.e; list.forEach(x => { if (x.s <= end && x.e > end) end = x.e; }); return { k: "busy", until: end, who: cur.kind === "busy" ? cur.who : "Bạn" }; }
    const next = list.find(x => x.s > n);
    if (next && next.s - n <= 30) return { k: "soon", until: next.s };
    return { k: "free", until: next ? next.s : null };
  }
  function stText(st) {
    if (st.k === "off") return "Chưa kết nối";
    if (st.k === "busy") return st.until >= 1440 ? "Bận cả ngày" : "Bận đến " + hm(st.until);
    return st.until != null ? "Trống đến " + hm(st.until) : "Trống cả ngày";
  }
  const stDot = (st, extra) => '<span class="pmrm-st pmrm-st--' + st.k + (extra ? " " + extra : "") + '">' + stText(st) + "</span>";
  const offText = code => OFF_TEXT[code] || ("Chưa đọc được lịch phòng (" + code + ")");

  /* ---------------- vẽ */
  function paintTiles() {
    if (mode !== "page") return;
    const rooms = roomsOf(S.today), live = rooms.filter(r => !r.error);
    const sts = live.map(r => ({ r, st: nowState(r) }));
    const free = sts.filter(x => x.st.k !== "busy").length;
    $("[data-t-free]").innerHTML = rooms.length ? (live.length ? '<span class="pmrm-num">' + free + "</span><small>/" + rooms.length + " phòng</small>" : '<span class="pmrm-dim">Chưa kết nối</span>') : "—";
    const busy = sts.filter(x => x.st.k === "busy").sort((a, b) => a.st.until - b.st.until)[0];
    $("[data-t-next]").innerHTML = !live.length ? "—" : busy
      ? esc(busy.r.label) + ' <span class="pmrm-st pmrm-st--free">lúc ' + hm(busy.st.until) + "</span>"
      : '<span class="pmrm-st pmrm-st--free">Mọi phòng đang trống</span>';
    const keys = {};
    rooms.forEach(r => items(r, S.today).forEach(x => { if (x.kind !== "busy") keys[x.uid || x.event_id || (r.name + x.s)] = 1; }));
    $("[data-t-mine]").innerHTML = '<span class="pmrm-num">' + Object.keys(keys).length + "</span><small> cuộc</small>";
  }
  function paintGrid() {
    const tl = $("[data-tl]"), d = dayData(S.date);
    tl.setAttribute("aria-busy", S.loading ? "true" : "false");
    tl.classList.toggle("pmrm-tl--loading", !!(S.loading && d));
    tl.setAttribute("aria-label", "Lịch phòng họp " + (S.date ? wday(S.date) + " " + dm(S.date) : ""));
    if (!d) {
      if (S.err) tl.innerHTML = '<div class="pmrm-fail"><p>Chưa tải được lịch phòng: ' + esc(S.err) + '</p><button type="button" class="pmrm-btn" data-act="retry">Thử lại</button></div>';
      return;
    }
    if (!d.rooms || !d.rooms.length) { tl.innerHTML = '<p class="pmrm-empty">Chưa có phòng họp nào được cấu hình.</p>'; return; }
    const today = S.date === S.today, n = nowMin();
    let hrs = "";
    for (let h = H0; h <= H1; h += 60) hrs += '<span style="left:' + pct(h) + '%">' + hm(h) + "</span>";
    let h = '<div class="pmrm-in"><div class="pmrm-hd" aria-hidden="true"><div></div><div class="pmrm-hours">' + hrs + "</div></div>";
    d.rooms.forEach(r => {
      const meta = [r.floor, r.note, r.capacity ? r.capacity + " người" : ""].filter(Boolean).map(esc).join(" · ");
      const st = today ? nowState(r) : null;
      h += '<div class="pmrm-row"><div class="pmrm-room"><b>' + esc(r.label || r.code || r.name) + "</b>" + (meta ? "<small>" + meta + "</small>" : "") + (st ? stDot(st, "pmrm-st--sm") : "") + "</div>";
      if (r.error) {
        h += '<div class="pmrm-lane pmrm-lane--off" aria-disabled="true"><span class="pmrm-offtxt"><span class="pmrm-st pmrm-st--off">Chưa kết nối</span> ' + esc(offText(r.error)) + "</span></div></div>";
        return;
      }
      const list = items(r, S.date);
      const blocks = list.filter(x => x.e > H0 && x.s < H1).map(x => {
        const t = hm(x.s) + "–" + hm(x.e), ed = x.kind !== "busy" && !!x.event_id;
        const main = x.kind === "busy" ? (x.who || "Đã có người đặt") : (x.subject || "Bạn đặt");
        const tip = x.kind === "busy" ? "Đã có người đặt: " + main + " · " + t : main + " · " + t + (x.kind === "pend" ? " · chờ phòng nhận" : "") + (x.rec ? " · lặp lại" : "") +
          (ed ? " · bấm để sửa" + (x.rec ? "" : ", kéo để đổi giờ / phòng") : "");
        const attrs = ed ? ' data-ev="' + esc(x.event_id) + '"' + (x.rec ? " data-rec" : "") + ' role="button" tabindex="0" aria-label="' + esc("Sửa cuộc họp " + main + ", " + t + (x.rec ? ", lặp lại" : "")) + '"' : "";
        return '<div class="pmrm-blk pmrm-blk--' + x.kind + (ed ? " pmrm-blk--edit" : "") + (S.moving && S.moving === x.event_id ? " pmrm-blk--busyop" : "") + '" data-kind="' + x.kind + '" data-uid="' + esc(x.uid) + '"' + attrs + ' style="left:' + pct(x.s) + "%;width:calc(" + (pct(x.e) - pct(x.s)) + '% - 2px)" title="' + esc(tip) + '">' +
          (x.rec ? '<i class="pmrm-rep" aria-hidden="true">↻</i>' : "") + esc(main) + "<small>" + t + (x.kind === "pend" ? " · chờ phòng nhận" : "") + (x.rec ? " · Lặp lại" : "") + "</small></div>";
      }).join("");
      const nowLine = today && n != null && n >= H0 && n <= H1 ? '<div class="pmrm-now" style="left:' + pct(n) + '%" aria-hidden="true"></div>' : "";
      const lbl = "Đặt phòng " + (r.label || r.code) + ", " + (today ? "hôm nay" : wday(S.date) + " " + dm(S.date)) + (list.length ? ", đã có " + list.length + " lịch" : ", còn trống");
      h += '<div class="pmrm-lane" role="button" tabindex="0" data-room="' + esc(r.name) + '" aria-label="' + esc(lbl) + '">' + blocks + nowLine + '<div class="pmrm-ghost" aria-hidden="true"></div></div></div>';
    });
    tl.innerHTML = h + "</div>";
  }
  function mineRows() {
    const lim = S.today ? ymdAdd(S.today, 14) : "";   /* mine() có thể tải xa hơn khi xem ngày xa: danh sách vẫn 14 ngày tới */
    const rows = S.mine.filter(x => !lim || String(x.start).slice(0, 10) < lim);
    Object.keys(S.pending).forEach(k => { const p = S.pending[k]; if (!p.series && !inMine(p) && !rows.some(x => x.event_id === p.event_id || (p.uid && x.uid === p.uid))) rows.push(p); });
    return rows.sort((a, b) => String(a.start).localeCompare(String(b.start)));
  }
  const PILL = { accepted: ["ok", "Phòng đã nhận"], pending: ["wait", "Chờ phòng nhận"], declined: ["no", "Phòng từ chối"] };
  function paintMine() {
    if (mode !== "page") return;
    const box = $("[data-mine]"); if (!box) return;
    const rows = mineRows();
    if (!rows.length) {
      box.innerHTML = S.mineErr ? '<p class="pmrm-empty pmrm-empty--err">Chưa tải được danh sách: ' + esc(S.mineErr) + "</p>"
        : (S.mineLoaded ? '<p class="pmrm-empty">Bạn chưa đặt phòng nào trong 14 ngày tới.</p>' : '<p class="pmrm-empty">Đang tải…</p>');
      return;
    }
    box.innerHTML = rows.map(x => {
      const p = PILL[x.state] || PILL.pending, d = String(x.start).slice(0, 10);
      const when = (d === S.today ? "Hôm nay" : d === (S.today && ymdAdd(S.today, 1)) ? "Mai" : wday(d) + " " + dm(d));
      const id = esc(x.event_id || ""), nm = esc(x.subject || "lịch");
      const g = Array.isArray(x.guests) ? x.guests : [], ext = g.filter(y => y && y.external).length;
      const act = S.confirm === x.event_id
        ? (x.recurring
          ? '<span class="pmrm-cf" role="group" aria-label="Xác nhận huỷ cuộc họp lặp lại"><span>Huỷ cuộc họp lặp lại?</span>' + (x.master ? "" : '<button type="button" class="pmrm-btn pmrm-btn--danger" data-act="cancel-yes" data-scope="occurrence" data-ev="' + id + '">Huỷ buổi này</button>') + '<button type="button" class="pmrm-btn pmrm-btn--danger" data-act="cancel-yes" data-scope="series" data-ev="' + id + '">Huỷ cả chuỗi</button><button type="button" class="pmrm-btn" data-act="cancel-no">Giữ</button></span>'
          : '<span class="pmrm-cf" role="group" aria-label="Xác nhận huỷ"><span>Huỷ lịch này?</span><button type="button" class="pmrm-btn pmrm-btn--danger" data-act="cancel-yes" data-ev="' + id + '">Huỷ phòng</button><button type="button" class="pmrm-btn" data-act="cancel-no">Giữ</button></span>')
        : (x.event_id ? '<span class="pmrm-acts"><button type="button" class="pmrm-btn" data-act="edit" data-ev="' + id + '" aria-label="Sửa ' + nm + '">Sửa</button>' +
          '<button type="button" class="pmrm-btn" data-act="cancel" data-ev="' + id + '" aria-label="Huỷ ' + nm + '">Huỷ</button></span>' : "");
      return '<div class="pmrm-mrow" data-ev-row="' + id + '"><div class="pmrm-mmain"><b>' + esc(x.subject || "(Không tên)") + "</b><small>" + esc(x.label || x.room) + " · " + when + ' <span class="pmrm-num">' + esc(String(x.start).slice(11, 16)) + "–" + esc(String(x.end).slice(11, 16)) + "</span>" +
        (x.recurring ? ' · <span class="pmrm-rep">↻ Lặp lại</span>' : "") +
        (g.length ? ' · <span data-guests><span class="pmrm-num">' + g.length + "</span> người mời" + (ext ? ' (<span class="pmrm-ext" title="' + EXT_TIP + '">' + ext + " khách ngoài</span>)" : "") + "</span>" : "") +
        (safeUrl(x.join_url) ? ' · <a class="pmrm-link" href="' + esc(safeUrl(x.join_url)) + '" target="_blank" rel="noopener">Mở Teams</a>' : "") + "</small></div>" +
        '<span class="pmrm-st pmrm-st--' + p[0] + '">' + p[1] + "</span>" + act + "</div>";
    }).join("");
  }
  function paintBar() {
    const dd = dayData(S.date) || dayData(S.today), off = !!dd && !dd.sync_on;
    $$('[data-act="book"]').forEach(b => { b.disabled = off || !dayData(S.date) || !roomsOf(S.date).some(r => !r.error); });
    const off0 = S.today ? [0, 1, 2].map(i => ymdAdd(S.today, i)) : [];
    let any = false;
    $$("[data-day]").forEach(b => { const on = off0[+b.getAttribute("data-day")] === S.date; any = any || on; b.setAttribute("aria-pressed", on ? "true" : "false"); });
    const pk = $("[data-pick]"); if (pk) { pk.value = any ? "" : (S.date || ""); pk.closest(".pmrm-pick").classList.toggle("pmrm-pick--on", !any && !!S.date); }
    const msg = $("[data-msg]");
    let m = "";
    if (S.err && dayData(S.date)) m = "Chưa làm mới được lịch phòng: " + esc(S.err) + ' <button type="button" class="pmrm-link" data-act="retry">Thử lại</button>';
    else if (off) m = "Chưa kết nối lịch Teams: chưa xem / đặt phòng được. Báo quản trị hệ thống nếu cần gấp.";
    msg.innerHTML = m; msg.hidden = !m;
  }
  function paint() { if (S.dead) return; paintBar(); paintTiles(); paintGrid(); paintMine(); }

  /* ---------------- tải */
  async function refresh() {
    if (!alive()) return;
    const my = ++S.seq, want = S.date;
    S.loading = true; S.err = ""; paintGrid();
    const jobs = [call("rooms.day", want ? { date: want } : {})];
    const needToday = mode === "page" && S.today && want && want !== S.today;
    jobs.push(needToday ? call("rooms.day", { date: S.today }) : Promise.resolve(null));
    const md = mineDays();
    jobs.push(call("rooms.mine", md > 14 ? { days: md } : {}));
    const res = await Promise.all(jobs.map(p => p.then(v => ({ v }), e => ({ e }))));
    if (!alive() || my !== S.seq) return;
    S.loading = false;
    const d = res[0];
    if (d.e || !d.v) { S.err = msgOf(d.e); }
    else {
      const v = d.v;
      S.cache[v.date] = v;
      if (v.now) { S.today = String(v.now).slice(0, 10); S.nowMin = toMin(String(v.now).slice(11, 16)); S.nowAt = Date.now(); }
      if (!S.date) S.date = v.date;
    }
    if (res[1] && res[1].v) S.cache[res[1].v.date] = res[1].v;
    const m = res[2];
    if (m.e) S.mineErr = msgOf(m.e);
    else { S.mineErr = ""; S.mineLoaded = true; S.mine = ((m.v && m.v.rows) || []).filter(x => x && x.event_id && !S.gone[x.event_id]); }
    /* đơn vừa đặt đã có trong lịch Outlook (mine) -> bỏ bản tạm; phòng đã trả lời thì báo luôn */
    Object.keys(S.pending).forEach(k => {
      const p = S.pending[k], x = S.mine.find(r => r.event_id === p.event_id || ((p.series || p.master) && r.series_id === p.event_id)); if (!x) return;
      if (p.state === "pending" && x.state !== "pending") announce(p, x.state);
      if (x.state === p.state || x.state !== "pending") delete S.pending[k];
    });
    S.stale = false;
    paint();
  }
  /* xem ngày xa hơn 14 ngày -> tải mine() đủ xa để khối "Bạn đặt" ngày đó vẫn sửa được (server tối đa 60) */
  function mineDays() { return S.today && S.date ? Math.max(14, Math.min(60, dayDiff(S.today, S.date) + 1)) : 14; }
  async function ensureDay(d) {
    if (S.cache[d]) return S.cache[d];
    try { const v = await call("rooms.day", { date: d }); if (v && v.date) S.cache[v.date] = v; return v; } catch (_) { return null; }
  }
  function setDate(d) {
    if (!d || d === S.date) return;
    S.date = d; S.confirm = null; paint(); refresh();
  }

  /* ---------------- chọn giờ */
  function slotAt(lane, clientX) {
    const b = lane.getBoundingClientRect(), w = b.width || 1;
    return H0 + Math.max(0, Math.min(1, (clientX - b.left) / w)) * SPAN;
  }
  /* giờ thô trên làn -> {s, e} (bước 30', mặc định 1 giờ, dừng ở lịch kế tiếp / 19:00) hoặc {err} */
  function slotFor(r, day, raw) {
    let s = Math.max(H0, Math.min(H1 - STEP, Math.floor(raw / STEP) * STEP));
    if (day === S.today) {
      const n = nowMin();
      if (n != null) {
        if (s + STEP <= n) return { err: "Giờ này đã qua." };
        if (s < n) s = Math.ceil(n / STEP) * STEP;
        if (s > H1 - STEP) return { err: "Giờ này đã qua." };
      }
    }
    const hit = clashOf(r, day, s, s + STEP);
    if (hit) return { err: hit.kind === "busy" ? "Giờ này phòng đã có người đặt (" + (hit.who || "đã đặt") + ")." : "Bạn đã đặt phòng này giờ này." };
    let e = Math.min(s + 60, H1);
    items(r, day).forEach(x => { if (x.s >= s + STEP && x.s < e) e = x.s; });
    return { s, e };
  }
  function firstFree(r, day) {
    const n = day === S.today ? nowMin() : null;
    let from = n != null ? Math.max(H0, Math.ceil(n / STEP) * STEP) : Math.max(H0, 9 * 60);
    for (let s = from; s <= H1 - STEP; s += STEP) { const x = slotFor(r, day, s); if (!x.err) return x; }
    return null;
  }

  /* ---------------- hộp đặt phòng = hộp sửa (ed = một dòng của mine() / bản vừa đặt) */
  function openBook(roomName, day, s, e, ed) {
    closeDlg(true);
    let rooms = roomsOf(day).length ? roomsOf(day) : roomsOf(S.date);
    if (ed && ed.room && !rooms.some(r => r.name === ed.room)) rooms = [{ name: ed.room, label: ed.label || ed.room }].concat(rooms);   /* phòng đã tắt vẫn giữ được */
    const last = document.activeElement;
    const host = el.closest("#ec-pm-root") || document.body;
    const sc = document.createElement("div");
    sc.className = "pmrm-scrim";
    const opt = rooms.map(r => '<option value="' + esc(r.name) + '"' + (r.error ? " disabled" : "") + (r.name === roomName ? " selected" : "") + ">" + esc(r.label || r.code) +
      ([r.floor, r.note].filter(Boolean).length ? " · " + esc([r.floor, r.note].filter(Boolean).join(", ")) : "") + (r.error ? " (chưa kết nối)" : "") + "</option>").join("");
    const scope = ed && ed.recurring
      ? '<fieldset class="pmrm-scope"><legend>Cuộc họp lặp lại, sửa:</legend>' +
        /* ed.master = dòng tạm của chuỗi vừa đặt (id là seriesMaster): chỉ sửa được cả chuỗi đến khi lịch đồng bộ */
        '<label><input type="radio" name="' + idp + 'sc" value="occurrence" data-f="scope"' + (ed.master ? " disabled" : " checked") + '> Chỉ buổi này</label>' +
        '<label><input type="radio" name="' + idp + 'sc" value="series" data-f="scope"' + (ed.master ? " checked" : "") + '> Cả chuỗi</label>' +
        '<p class="pmrm-sub" data-scope-note hidden>Cả chuỗi: đổi phòng, tên, người mời và giờ trong ngày cho mọi buổi; giữ nguyên ngày.</p></fieldset>' : "";
    const repeat = ed ? "" : '<div class="pmrm-row2"><div class="pmrm-fld"><label for="' + idp + 'rp">Lặp lại</label><select id="' + idp + 'rp" data-f="repeat">' +
      REPEATS.map(k => '<option value="' + k + '">' + esc(repText(k, day || S.date || "2026-01-01")) + "</option>").join("") + "</select></div>" +
      '<div class="pmrm-fld" data-until hidden><label for="' + idp + 'u">Đến ngày</label><input id="' + idp + 'u" type="date" data-f="until"></div></div>' +
      '<p class="pmrm-rsum" data-rsum aria-live="polite" hidden></p>';
    const teamsOn = !ed || !!(ed.join_url || ed.teams);
    sc.innerHTML = '<form class="pmrm-dlg" role="dialog" aria-modal="true" aria-labelledby="' + idp + 'dt" novalidate>' +
      '<header><h2 id="' + idp + 'dt">' + (ed ? "Sửa cuộc họp" : "Đặt phòng họp") + '</h2><button type="button" class="pmrm-x" data-act="close" aria-label="Đóng">×</button></header>' +
      '<div class="pmrm-body">' +
      '<div class="pmrm-fld"><label for="' + idp + 't">Tên cuộc họp</label><input id="' + idp + 't" data-f="subject" maxlength="200" autocomplete="off" required placeholder="Ví dụ: Review kế hoạch tháng 12"></div>' +
      '<div class="pmrm-fld"><label for="' + idp + 'd">Mô tả (không bắt buộc)</label><textarea id="' + idp + 'd" data-f="desc" rows="3" maxlength="4000" placeholder="Nội dung, agenda, tài liệu cần chuẩn bị…"></textarea><small class="pmrm-hint" data-desc-note hidden></small></div>' +
      '<div class="pmrm-fld"><label for="' + idp + 'r">Phòng</label><select id="' + idp + 'r" data-f="room">' + opt + "</select></div>" +
      '<div class="pmrm-row3"><div class="pmrm-fld"><label for="' + idp + 'd">Ngày</label><input id="' + idp + 'd" type="date" data-f="date" required></div>' +
      '<div class="pmrm-fld"><label for="' + idp + 's">Từ</label><input id="' + idp + 's" type="time" step="1800" data-f="start" required></div>' +
      '<div class="pmrm-fld"><label for="' + idp + 'e">Đến</label><input id="' + idp + 'e" type="time" step="1800" data-f="end" required></div></div>' +
      scope + repeat +
      '<div class="pmrm-warn" data-warn role="alert" hidden></div>' +
      '<div class="pmrm-fld"><label for="' + idp + 'w">Mời thêm (không bắt buộc)</label><div class="pmrm-chips" data-chips></div>' +
      '<div class="pmrm-combo"><input id="' + idp + 'w" data-f="who" autocomplete="off" placeholder="Gõ tên, hoặc email rồi Enter" role="combobox" aria-expanded="false" aria-autocomplete="list" aria-controls="' + idp + 'wl" aria-describedby="' + idp + 'wx">' +
      '<ul class="pmrm-opts" id="' + idp + 'wl" role="listbox" aria-label="Người được mời" hidden></ul></div>' +
      '<p class="pmrm-sub" id="' + idp + 'wx" data-exthint hidden>' + EXT_TIP + ".</p></div>" +
      '<label class="pmrm-check"><input type="checkbox" data-f="teams"' + (teamsOn ? " checked" : "") + (ed ? ' disabled title="Đổi kiểu họp Teams trên Teams / Outlook"' : "") + "> Kèm link họp Teams</label>" +
      '<div class="pmrm-note">' + (ed ? "Đổi giờ hoặc phòng thì phòng xác nhận lại. Người được mời nhận lịch cập nhật trên Teams / Outlook."
        : "Phòng trống thì tự nhận ngay. Lịch vào Outlook/Teams của bạn và người được mời; huỷ ở đây hay trên Teams đều được.") + "</div>" +
      "</div><footer><button type=\"button\" class=\"pmrm-btn\" data-act=\"close\">Huỷ</button><button type=\"submit\" class=\"pmrm-btn pmrm-btn--pri\" data-submit>" + (ed ? "Lưu thay đổi" : "Đặt phòng") + "</button></footer></form>";
    host.appendChild(sc);
    const f = k => sc.querySelector('[data-f="' + k + '"]');
    const D = S.dlg = { sc, last, room: roomName, who: [], busy: false, active: -1, opts: [], ed: ed || null, untilSet: false };
    if (!f("room").value || f("room").selectedOptions && f("room").selectedOptions[0] && f("room").selectedOptions[0].disabled) {
      const ok = rooms.find(r => !r.error); if (ok) f("room").value = ok.name;
    }
    const s0 = s != null ? s : 13 * 60;
    f("date").value = day || S.date; f("start").value = hm(s0); f("end").value = hm(e != null ? e : Math.min(s0 + 60, 23 * 60 + 30));
    if (S.today && !ed) f("date").min = S.today;
    if (S.today) f("date").max = ymdAdd(S.today, MAX_SERIES_DAYS);
    if (ed) {
      f("subject").value = ed.subject || "";
      D.who = (Array.isArray(ed.guests) ? ed.guests : []).filter(g => g && g.email).map(g => ({ email: g.email, full_name: g.name || g.full_name || g.email, external: g.external }));
      /* so với bản gốc để chỉ gửi trường đã đổi */
      D.orig = { subject: f("subject").value.trim(), room: f("room").value, date: f("date").value, start: f("start").value, end: f("end").value, who: D.who.map(p => p.email).sort().join(",") };
      /* mô tả nằm trong nội dung lời mời (body): tải riêng, chưa tải xong thì khoá ô và không gửi */
      const dEl = f("desc"), note = sc.querySelector("[data-desc-note]");
      dEl.readOnly = true; dEl.placeholder = "Đang tải mô tả…"; D.orig.desc = null;
      call("rooms.detail", { event_id: ed.event_id }).then(r => {
        if (S.dlg !== D) return;
        dEl.value = (r && r.description) || ""; D.orig.desc = dEl.value.trim(); dEl.placeholder = "Nội dung, agenda, tài liệu cần chuẩn bị…";
        if (r && r.editable === false) { note.textContent = "Mô tả này được viết trên Teams/Outlook: sửa ở đó."; note.hidden = false; }
        else dEl.readOnly = false;
      }, () => { if (S.dlg !== D) return; dEl.placeholder = "Chưa tải được mô tả (sửa trên Teams/Outlook)."; });
      const skip = {};   /* chính cuộc này (+ các buổi khác cùng chuỗi) không tính là trùng */
      S.mine.concat(Object.keys(S.pending).map(k => S.pending[k])).forEach(x => {
        if (x.event_id === ed.event_id || (ed.series_id && x.series_id === ed.series_id)) { if (x.uid) skip["u" + x.uid] = 1; if (x.event_id) skip["e" + x.event_id] = 1; }
      });
      if (ed.uid) skip["u" + ed.uid] = 1;
      skip["e" + ed.event_id] = 1;
      D.skip = x => !!((x.uid && skip["u" + x.uid]) || (x.event_id && skip["e" + x.event_id]));
    }
    sc.addEventListener("click", ev => {
      if (ev.target === sc) return closeDlg();
      const a = ev.target.closest("[data-act],[data-rm],[data-opt]"); if (!a) return;
      if (a.getAttribute("data-act") === "close") closeDlg();
      else if (a.hasAttribute("data-rm")) { D.who = D.who.filter(p => p.email !== a.getAttribute("data-rm")); chips(); check(); f("who").focus(); }
      else if (a.hasAttribute("data-opt")) pick(D.opts[+a.getAttribute("data-opt")]);
    });
    sc.addEventListener("mousedown", ev => { if (ev.target.closest("[data-opt]")) ev.preventDefault(); });
    sc.addEventListener("change", ev => {
      if (ev.target === f("until")) D.untilSet = true;
      if (ev.target.closest("[data-f]") && ev.target !== f("who")) check();
    });
    sc.addEventListener("input", ev => {
      if (ev.target === f("who")) { const v = f("who").value; if (/[,;]/.test(v) && v.indexOf("@") >= 0) addTyped(v); else suggest(); }
      else if (ev.target.closest('[data-f="start"],[data-f="end"],[data-f="date"],[data-f="until"]')) { if (ev.target === f("until")) D.untilSet = true; check(); }
    });
    sc.addEventListener("keydown", ev => {
      if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); if (!sc.querySelector(".pmrm-opts").hidden) return hideOpts(); return closeDlg(); }
      if (ev.target === f("who")) return whoKey(ev);
      if (ev.key === "Tab") {   /* giữ focus trong hộp */
        const list = Array.prototype.slice.call(sc.querySelectorAll("input,select,button")).filter(x => !x.disabled && !x.closest("[hidden]"));
        const i = list.indexOf(document.activeElement);
        if (ev.shiftKey && i <= 0) { ev.preventDefault(); list[list.length - 1].focus(); }
        else if (!ev.shiftKey && i === list.length - 1) { ev.preventDefault(); list[0].focus(); }
      }
    });
    f("who").addEventListener("focus", loadPeople);
    sc.querySelector("form").addEventListener("submit", ev => { ev.preventDefault(); submit(); });
    /* khách ngoài = email không thuộc danh sách nội bộ (server cũng báo external trong mine()) */
    const isExt = p => (p.external === true || p.external === false) ? p.external : !!S.people && !S.people.some(x => x.email === p.email);
    function chips() {
      let anyExt = false;
      sc.querySelector("[data-chips]").innerHTML = D.who.map(p => {
        const ext = !p.bad && isExt(p), nm = p.full_name || p.email;
        anyExt = anyExt || ext;
        return '<span class="pmrm-chip' + (p.bad ? " pmrm-chip--bad" : ext ? " pmrm-chip--ext" : "") + '"' +
          (p.bad ? ' title="Email không hợp lệ"' : ext ? ' title="' + EXT_TIP + '"' : "") + ">" + esc(nm) +
          (p.bad ? "<small>Email sai</small>" : ext ? "<small>Khách ngoài</small>" : "") +
          '<button type="button" data-rm="' + esc(p.email) + '" aria-label="Bỏ ' + esc(nm) + '">×</button></span>';
      }).join("");
      sc.querySelector("[data-exthint]").hidden = !anyExt;
    }
    function hideOpts() { const ul = sc.querySelector(".pmrm-opts"); ul.hidden = true; f("who").setAttribute("aria-expanded", "false"); f("who").removeAttribute("aria-activedescendant"); D.active = -1; }
    function suggest() {
      const ul = sc.querySelector(".pmrm-opts"), q = fold(f("who").value.trim());
      if (!q) return hideOpts();
      if (!S.people) { ul.innerHTML = '<li class="pmrm-optx">' + (S.peopleErr ? "Chưa tải được danh sách người. Gõ đủ email rồi Enter." : "Đang tải danh sách…") + "</li>"; ul.hidden = false; return; }
      const taken = D.who.map(p => p.email);
      D.opts = S.people.filter(p => taken.indexOf(p.email) < 0 && (fold(p.full_name).indexOf(q) >= 0 || fold(p.email).indexOf(q) >= 0)).slice(0, 8);
      D.active = D.opts.length ? 0 : -1;
      ul.innerHTML = D.opts.length ? D.opts.map((p, i) => '<li role="option" id="' + idp + "o" + i + '" data-opt="' + i + '" aria-selected="' + (i === D.active) + '">' + esc(p.full_name) + "<small>" + esc(p.email) + "</small></li>").join("")
        : '<li class="pmrm-optx">' + (q.indexOf("@") >= 0 ? "Không phải người trong công ty: Enter để mời làm khách ngoài." : "Không thấy ai. Gõ đủ email rồi Enter.") + "</li>";
      ul.hidden = false; f("who").setAttribute("aria-expanded", "true");
      if (D.active >= 0) f("who").setAttribute("aria-activedescendant", idp + "o" + D.active); else f("who").removeAttribute("aria-activedescendant");
    }
    function pick(p) {
      if (!p || D.who.some(x => x.email === p.email)) return;
      D.who.push(p); f("who").value = ""; hideOpts(); chips(); check();
    }
    /* chữ gõ / dán (một hay nhiều email, cách bằng dấu phẩy / chấm phẩy / khoảng trắng) -> chip; email sai vẫn thành chip đỏ để thấy ngay */
    function addTyped(v) {
      String(v).split(/[,;\s]+/).filter(Boolean).forEach(t => {
        const em = t.toLowerCase();
        if (D.who.some(x => x.email === em || x.email === t)) return;
        const known = (S.people || []).find(p => p.email === em);
        D.who.push(known || (EMAIL.test(em) ? { email: em, full_name: em } : { email: t, full_name: t, bad: true }));
      });
      f("who").value = ""; hideOpts(); chips(); check();
    }
    function whoKey(ev) {
      const ul = sc.querySelector(".pmrm-opts");
      if ((ev.key === "ArrowDown" || ev.key === "ArrowUp") && D.opts.length && !ul.hidden) {
        ev.preventDefault(); D.active = (D.active + (ev.key === "ArrowDown" ? 1 : D.opts.length - 1)) % D.opts.length;
        $$("[data-opt]", ul).forEach((li, i) => li.setAttribute("aria-selected", String(i === D.active)));
        f("who").setAttribute("aria-activedescendant", idp + "o" + D.active);
      } else if ((ev.key === "Enter" || ev.key === ",") && !ev.isComposing) {
        const v = f("who").value.trim();
        if (ev.key === "Enter") ev.preventDefault();
        if (!v) return;
        if (!ul.hidden && D.active >= 0 && D.opts[D.active]) { ev.preventDefault(); pick(D.opts[D.active]); }
        else if (v.indexOf("@") >= 0) { ev.preventDefault(); addTyped(v); }
      } else if (ev.key === "Backspace" && !f("who").value && D.who.length) { D.who.pop(); chips(); check(); }
    }
    D.f = f; D.chips = chips; D.addTyped = addTyped;
    chips();
    check();
    sc.querySelector('[data-f="subject"]').focus();
  }
  function openEdit(id) {
    const x = rowById(id);
    if (!x) return toast("Không tìm thấy cuộc họp này. Tải lại trang rồi thử lại.", true);
    openBook(x.room, String(x.start).slice(0, 10), toMin(String(x.start).slice(11, 16)), toMin(String(x.end).slice(11, 16)), x);
  }
  async function loadPeople() {
    if (S.people || S.peopleP) return;
    S.peopleP = call("assignment.list_assignable", {}).then(r => { S.people = ((r && r.rows) || []).filter(p => p && p.email); },
      () => { S.peopleErr = true; }).then(() => {
        S.peopleP = null;
        if (!S.dlg) return;
        S.dlg.chips();
        if (S.dlg.f("who").value.trim()) S.dlg.sc.querySelector('[data-f="who"]').dispatchEvent(new Event("input", { bubbles: true }));
      });
  }
  function closeDlg(quiet) {
    const D = S.dlg; if (!D) return;
    S.dlg = null;
    if (D.sc.parentNode) D.sc.parentNode.removeChild(D.sc);
    if (quiet) return;
    let back = D.last && D.last.isConnected ? D.last : null;
    if (!back && D.ed) back = $$("[data-ev]").find(x => x.getAttribute("data-ev") === D.ed.event_id && x.tabIndex >= 0) || null;
    if (!back && D.room) back = $$(".pmrm-lane[data-room]").find(x => x.getAttribute("data-room") === D.room) || null;
    if (back && back.focus) back.focus();
  }
  const horizon = () => (S.today ? ymdAdd(S.today, MAX_SERIES_DAYS) : "");   /* = rooms._horizon() */
  const dmy = ymd => dm(ymd) + "/" + ymd.slice(0, 4);
  const scopeOf = D => { const x = D.sc.querySelector('[data-f="scope"]:checked'); return x ? x.value : "occurrence"; };
  const lcFirst = t => t.charAt(0).toLowerCase() + t.slice(1);
  /* kiểm ở client bằng dữ liệu đã tải (server vẫn kiểm lại khi đặt / sửa, kể cả từng buổi của chuỗi) */
  function check() {
    const D = S.dlg; if (!D) return false;
    const f = D.f, w = D.sc.querySelector("[data-warn]"), ed = D.ed, series = !!ed && scopeOf(D) === "series";
    if (ed && ed.recurring) {   /* cả chuỗi: giữ ngày, chỉ đổi giờ trong ngày */
      if (series) f("date").value = D.orig.date;
      f("date").disabled = series;
      D.sc.querySelector("[data-scope-note]").hidden = !series;
    }
    const day = f("date").value, s = toMin(f("start").value), e = toMin(f("end").value);
    D.room = f("room").value;
    const rp = f("repeat") ? f("repeat").value : "none", sum = D.sc.querySelector("[data-rsum]");
    if (f("repeat")) {
      if (day) {
        Array.prototype.forEach.call(f("repeat").options, o => { o.textContent = repText(o.value, day); });
        const hz = horizon() || ymdAdd(day, MAX_SERIES_DAYS);
        f("until").min = day; f("until").max = hz;
        if (!D.untilSet || !f("until").value) { const u = ymdAdd(day, REP_DAYS); f("until").value = u > hz ? (hz < day ? day : hz) : u; }
      }
      D.sc.querySelector("[data-until]").hidden = rp === "none";
      sum.hidden = true;
    }
    const moved = !ed || day !== D.orig.date || f("start").value.slice(0, 5) !== D.orig.start || f("end").value.slice(0, 5) !== D.orig.end;
    const recheck = !ed || moved || D.room !== D.orig.room;
    const bad = D.who.filter(p => p.bad);
    let m = "";
    if (!day || s == null || e == null) m = "Chọn ngày và giờ họp.";
    else if (e <= s) m = "Giờ kết thúc phải sau giờ bắt đầu.";
    else if (e - s > 600) m = "Một lần đặt tối đa 10 giờ.";
    else if (moved && !series && S.today && (day < S.today || (day === S.today && nowMin() != null && s < nowMin() - 5))) m = "Không đặt được giờ đã qua.";
    else if (moved && !series && horizon() && day > horizon()) m = "Phòng chỉ nhận đặt trước tối đa " + MAX_SERIES_DAYS + " ngày (đến " + dmy(horizon()) + ").";
    else if (bad.length) m = "Email không hợp lệ: " + bad[0].email + ". Sửa lại hoặc bỏ email này.";
    else if (D.who.length > MAX_GUESTS) m = "Mời tối đa " + MAX_GUESTS + " người.";
    else if (rp === "weekdays" && [0, 6].indexOf(new Date(day + "T00:00:00").getDay()) >= 0) m = "Lặp các ngày trong tuần: ngày họp đầu phải từ thứ Hai đến thứ Sáu.";
    else if (rp !== "none" && !f("until").value) m = "Chọn ngày kết thúc lặp lại.";
    else if (rp !== "none" && f("until").value < day) m = "Ngày kết thúc lặp lại phải sau ngày họp đầu tiên.";
    else if (rp !== "none" && horizon() && f("until").value > horizon()) m = "Lặp lại tối đa đến " + dmy(horizon()) + ": phòng chỉ nhận đặt trước " + MAX_SERIES_DAYS + " ngày.";
    else if (!recheck) { /* không đổi giờ / phòng: không cần kiểm trùng */ }
    else if (!S.cache[day]) { ensureDay(day).then(() => { if (S.dlg === D) check(); }); }
    else {
      const r = (S.cache[day].rooms || []).find(x => x.name === D.room);
      if (r && r.error) m = "Phòng này chưa kết nối lịch: " + offText(r.error) + ".";
      else {
        const c = r ? clashOf(r, day, s, e, D.skip) : null;
        if (c) m = c.kind === "busy" ? "Phòng đã có người đặt " + hm(c.s) + "–" + hm(c.e) + " (" + (c.who || "đã đặt") + "). Chọn giờ hoặc phòng khác." : "Bạn đã đặt phòng này " + hm(c.s) + "–" + hm(c.e) + ".";
      }
    }
    if (!m && rp !== "none" && day) {
      const until = f("until").value, n = occurrences(day, rp, until).length;
      sum.textContent = "Lặp " + lcFirst(repText(rp, day)) + " đến " + dm(until) + " · " + n + " buổi"; sum.hidden = false;
      D.count = n;
    }
    w.textContent = m; w.hidden = !m;
    D.sc.querySelector("[data-submit]").disabled = !!m || D.busy;
    return !m;
  }
  function busyBtn(D, on) {
    const btn = D.sc.querySelector("[data-submit]"), idle = D.ed ? "Lưu thay đổi" : "Đặt phòng";
    D.busy = on; btn.disabled = on; btn.textContent = on ? (D.ed ? "Đang lưu…" : "Đang đặt…") : idle;
    if (on) btn.setAttribute("aria-busy", "true"); else btn.removeAttribute("aria-busy");
  }
  async function submit() {
    const D = S.dlg; if (!D || D.busy) return;
    const f = D.f, w = D.sc.querySelector("[data-warn]"), subject = f("subject").value.trim();
    if (!subject) { w.textContent = "Ghi tên cuộc họp."; w.hidden = false; f("subject").focus(); return; }
    if (f("who").value.trim().indexOf("@") >= 0) D.addTyped(f("who").value.trim());   /* email gõ dở chưa Enter */
    if (!check()) return;
    if (D.ed) return submitEdit(D, subject);
    const rp = f("repeat").value;
    const day = f("date").value, args = { room: f("room").value, start: day + " " + f("start").value.slice(0, 5) + ":00", end: day + " " + f("end").value.slice(0, 5) + ":00",
      subject, attendees: JSON.stringify(D.who.map(p => p.email)), teams: f("teams").checked ? 1 : 0,
      txn: D.txn || (D.txn = "erp-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10)) };   /* một id mỗi lần mở hộp: bấm lại sau timeout không tạo 2 cuộc họp */
    if (f("desc").value.trim()) args.description = f("desc").value.trim();
    if (rp !== "none") { args.repeat = rp; args.repeat_until = f("until").value; }
    busyBtn(D, true);
    let res;
    try { res = await call("rooms.book", args); }
    catch (e) {
      if (S.dlg !== D) return;
      busyBtn(D, false); w.textContent = msgOf(e); w.hidden = false; return;
    }
    if (S.dead) return;
    if (!res || !res.event_id) {
      if (S.dlg === D) { busyBtn(D, false); w.textContent = "Chưa đặt được phòng, thử lại."; w.hidden = false; }
      return;
    }
    const guests = D.who.map(p => ({ email: p.email, name: p.full_name || p.email, external: p.external != null ? !!p.external : !!S.people && !S.people.some(x => x.email === p.email) }));
    const p = Object.assign({}, res, { state: res.state || "pending", subject: res.subject || subject, guests, teams: args.teams, recurring: !!res.recurring || rp !== "none" });
    if (p.recurring) { p.series_id = p.event_id; p.master = true; }   /* id = seriesMaster: thay bằng các buổi khi mine() có (series_id) */
    S.pending[p.event_id] = p;
    closeDlg();
    if (p.start && String(p.start).slice(0, 10) !== S.date) S.date = String(p.start).slice(0, 10);
    paint();
    toast(rp !== "none" ? "Đã gửi lịch lặp lại (" + (D.count || 1) + " buổi), chờ phòng xác nhận…" : "Đã gửi lịch, chờ phòng xác nhận…");
    poll(p, 0);
  }
  /* sửa: chỉ gửi trường đã đổi; họp lặp gửi scope (occurrence | series) */
  async function submitEdit(D, subject) {
    const f = D.f, w = D.sc.querySelector("[data-warn]"), ed = D.ed, o = D.orig, series = ed.recurring && scopeOf(D) === "series";
    const day = f("date").value, args = { event_id: ed.event_id };
    if (subject !== o.subject) args.subject = subject;
    if (f("room").value !== o.room) args.room = f("room").value;
    if (day !== o.date || f("start").value.slice(0, 5) !== o.start || f("end").value.slice(0, 5) !== o.end) {
      args.start = day + " " + f("start").value.slice(0, 5) + ":00"; args.end = day + " " + f("end").value.slice(0, 5) + ":00";
    }
    const emails = D.who.map(p => p.email);
    if (emails.slice().sort().join(",") !== o.who) args.attendees = JSON.stringify(emails);
    if (o.desc != null && !f("desc").readOnly && f("desc").value.trim() !== o.desc) args.description = f("desc").value.trim();
    if (Object.keys(args).length === 1) { closeDlg(); toast("Không có gì thay đổi."); return; }
    if (ed.recurring) args.scope = series ? "series" : "occurrence";
    busyBtn(D, true);
    let res;
    try { res = await call("rooms.update", args); }
    catch (e) {
      if (S.dlg !== D) return;
      busyBtn(D, false); w.textContent = msgOf(e); w.hidden = false; return;
    }
    if (S.dead) return;
    if (!res || !res.ok) {
      if (S.dlg === D) { busyBtn(D, false); w.textContent = "Chưa lưu được thay đổi, thử lại."; w.hidden = false; }
      return;
    }
    closeDlg();
    if (res.unchanged) { toast("Không có gì thay đổi."); return; }
    const guests = args.attendees ? D.who.map(p => ({ email: p.email, name: p.full_name || p.email, external: p.external != null ? !!p.external : !!S.people && !S.people.some(x => x.email === p.email) })) : null;
    const p = applyEdit(ed, args, res, series, guests);
    if (args.start && !series && day !== S.date) S.date = day;
    paint();
    toast(p ? (series ? "Đã lưu cả chuỗi, chờ phòng xác nhận…" : "Đã lưu, chờ phòng xác nhận…") : (series ? "Đã lưu thay đổi cho cả chuỗi." : "Đã lưu thay đổi."));
  }
  /* ghi thay đổi vào bản tại chỗ (đến khi mine() tải lại); đổi giờ / phòng -> chờ phòng nhận + hỏi booking_state như khi đặt */
  function applyEdit(ed, args, res, series, guests) {
    const rows = S.mine.filter(x => x.event_id === ed.event_id || (series && ed.series_id && x.series_id === ed.series_id));
    const pd = S.pending[ed.event_id];
    if (pd && !pd.series && rows.indexOf(pd) < 0) rows.push(pd);
    if (!rows.length) rows.push(ed);
    const rm = args.room ? roomBy(args.room, String(args.start || ed.start).slice(0, 10)) : null;
    rows.forEach(x => {
      if (args.room) { x.room = res.room || args.room; x.label = res.label || (rm && rm.label) || x.label; }
      if (args.subject != null) x.subject = args.subject;
      if (guests) x.guests = guests;
      if (args.start) {
        if (series) { x.start = String(x.start).slice(0, 10) + args.start.slice(10); x.end = String(x.end).slice(0, 10) + args.end.slice(10); }
        else { x.start = args.start; x.end = args.end; }
      }
      if (res.state === "pending") x.state = "pending";
    });
    if (res.state !== "pending") return null;
    const id = res.event_id || ed.event_id;
    const p = series ? Object.assign({}, rows[0], { event_id: id, uid: "", series: true, state: "pending" }) : Object.assign({}, rows[0], { state: "pending" });
    S.pending[id] = p;
    poll(p, 0);
    return p;
  }
  function announce(p, st) {
    if (st === "accepted") toast((p.label || "Phòng") + " đã nhận · lịch đã vào Teams của bạn");
    else if (st === "declined") toast((p.label || "Phòng") + " từ chối (trùng giờ). Chọn giờ hoặc phòng khác.", true);
  }
  function poll(p, i) {
    if (i >= POLLS.length) {
      if (S.pending[p.event_id] && S.pending[p.event_id].state === "pending") toast("Phòng chưa trả lời. Lịch vẫn ở Outlook của bạn; xem lại trạng thái sau ít phút.");
      return;
    }
    later(POLLS[i], async () => {
      let st = null;
      try { st = ((await call("rooms.booking_state", { event_id: p.event_id })) || {}).state; } catch (_) { st = null; }
      if (S.dead || !S.pending[p.event_id]) return;
      if (st === "accepted" || st === "declined") { announce(p, st); p.state = st; paint(); refresh(); }
      else if (st === "cancelled") { delete S.pending[p.event_id]; paint(); refresh(); }
      else poll(p, i + 1);
    });
  }
  async function doCancel(btn, id, scope) {
    if (!id || btn.disabled) return;
    const grp = btn.closest(".pmrm-cf"), row = rowById(id), series = scope === "series" && !!(row && row.series_id);
    $$("button", grp).forEach(b => { b.disabled = true; });
    btn.textContent = "Đang huỷ…"; btn.setAttribute("aria-busy", "true");
    try { await call("rooms.cancel", row && row.recurring ? { event_id: id, scope: series ? "series" : "occurrence" } : { event_id: id }); }
    catch (e) {
      if (S.dead) return;
      toast("Chưa huỷ được: " + msgOf(e), true); S.confirm = null; paintMine();
      const again = $$('[data-act="cancel"]').find(x => x.getAttribute("data-ev") === id); if (again) again.focus();
      return;
    }
    if (S.dead) return;
    const dead = series ? S.mine.filter(x => x.series_id === row.series_id) : [S.mine.find(x => x.event_id === id) || S.pending[id]];
    dead.forEach(x => { if (!x) return; S.gone[x.event_id] = 1; if (x.uid) S.gone[x.uid] = 1; delete S.pending[x.event_id]; });
    S.gone[id] = 1; S.confirm = null; delete S.pending[id];
    if (series) delete S.pending[row.series_id];
    S.mine = S.mine.filter(x => !S.gone[x.event_id]);
    toast(series ? "Đã huỷ cả chuỗi · phòng và người được mời nhận thông báo huỷ" : "Đã huỷ · phòng và người được mời nhận thông báo huỷ");
    paint(); refresh();
  }

  /* ---------------- sự kiện (uỷ quyền trên gốc) */
  let ghost = null;
  function hideGhost() { if (ghost) { ghost.style.display = "none"; ghost = null; } }
  function onClick(ev) {
    if (S.noClick) { S.noClick = false; return; }   /* click sinh ra sau khi thả khối kéo */
    const t = ev.target.closest("[data-act],[data-day],.pmrm-lane[data-room]"); if (!t || !R.contains(t)) return;
    const act = t.getAttribute("data-act");
    if (t.hasAttribute("data-day")) { if (S.today) setDate(ymdAdd(S.today, +t.getAttribute("data-day"))); return; }
    if (act === "retry") return refresh();
    if (act === "book") {
      if (t.disabled) return;
      /* phòng có giờ trống sớm nhất (cùng giờ thì theo thứ tự phòng) */
      const rs = roomsOf(S.date).filter(r => !r.error);
      let best = null;
      rs.forEach(r => { const x = firstFree(r, S.date); if (x && (!best || x.s < best.x.s)) best = { r, x }; });
      return best ? openBook(best.r.name, S.date, best.x.s, best.x.e) : openBook(rs[0] && rs[0].name, S.date, null, null);
    }
    if (act === "cancel") { S.confirm = t.getAttribute("data-ev"); paintMine(); const no = $('[data-act="cancel-no"]'); if (no) no.focus(); return; }
    if (act === "cancel-no") { const id = S.confirm; S.confirm = null; paintMine(); const b = $$('[data-act="cancel"]').find(x => x.getAttribute("data-ev") === id); if (b) b.focus(); return; }
    if (act === "cancel-yes") return doCancel(t, t.getAttribute("data-ev"), t.getAttribute("data-scope"));
    if (act === "edit") return openEdit(t.getAttribute("data-ev"));
    if (t.classList.contains("pmrm-lane")) {
      const r = roomBy(t.getAttribute("data-room"), S.date); if (!r || r.error) return;
      const blk = ev.target.closest(".pmrm-blk");
      if (blk) {
        const k = blk.getAttribute("data-kind");
        if (blk.hasAttribute("data-ev")) { if (S.moving === blk.getAttribute("data-ev")) return; return openEdit(blk.getAttribute("data-ev")); }
        return toast(k === "busy" ? "Giờ này đã có người đặt." : k === "pend" ? "Đang chờ phòng nhận lịch của bạn." : "Lịch của bạn. Sửa hoặc huỷ trên Teams / Outlook.");
      }
      const x = slotFor(r, S.date, slotAt(t, ev.clientX));
      if (x.err) return toast(x.err);
      openBook(r.name, S.date, x.s, x.e);
    }
  }
  function onKey(ev) {
    const t = ev.target;
    if (ev.key === "Escape" && drag) { ev.preventDefault(); return cancelDrag(); }
    if ((ev.key === "Enter" || ev.key === " ") && t.classList && t.classList.contains("pmrm-blk") && t.hasAttribute("data-ev")) { ev.preventDefault(); return openEdit(t.getAttribute("data-ev")); }
    if (ev.key === "Escape" && S.confirm) { ev.preventDefault(); const id = S.confirm; S.confirm = null; paintMine(); const b = $$('[data-act="cancel"]').find(x => x.getAttribute("data-ev") === id); if (b) b.focus(); return; }
    if ((ev.key === "Enter" || ev.key === " ") && t.classList && t.classList.contains("pmrm-lane") && t.hasAttribute("data-room")) {
      ev.preventDefault();
      const r = roomBy(t.getAttribute("data-room"), S.date); if (!r || r.error) return;
      const x = firstFree(r, S.date);
      if (!x) return toast("Phòng đã kín lịch trong ngày này.");
      openBook(r.name, S.date, x.s, x.e);
    }
  }
  function onMove(ev) {
    if (drag) return;
    const lane = ev.target.closest && ev.target.closest(".pmrm-lane[data-room]");
    if (!lane || ev.target.closest(".pmrm-blk")) return hideGhost();
    const r = roomBy(lane.getAttribute("data-room"), S.date); if (!r) return hideGhost();
    const x = slotFor(r, S.date, slotAt(lane, ev.clientX));
    const g = lane.querySelector(".pmrm-ghost");
    if (ghost && ghost !== g) hideGhost();
    if (x.err || !g) return hideGhost();
    ghost = g; g.style.display = "block"; g.style.left = pct(x.s) + "%"; g.style.width = "calc(" + (pct(x.e) - pct(x.s)) + "% - 2px)"; g.textContent = "+ " + hm(x.s);
  }
  /* ---------------- kéo khối "Bạn đặt" (chuột) sang giờ / phòng khác = rooms.update, bước 30'. Họp lặp lại, bàn phím, màn
   * cảm ứng: dùng hộp Sửa. Thả là đổi ngay (lạc quan), server từ chối thì trả khối về chỗ cũ + báo đúng thông điệp. */
  let drag = null;
  function onDown(ev) {
    if (ev.button !== 0 || S.moving || S.dlg) return;
    const blk = ev.target.closest && ev.target.closest(".pmrm-blk--edit");
    if (!blk || blk.hasAttribute("data-rec") || !R.contains(blk)) return;
    const x = rowById(blk.getAttribute("data-ev")), lane = blk.closest(".pmrm-lane[data-room]"), sp = x && spanOn(x, S.date);
    if (!x || x.recurring || !lane || !sp) return;
    drag = { blk, x, lane, x0: ev.clientX, y0: ev.clientY, s: sp.s, e: sp.e, on: false, to: null };
    document.addEventListener("mousemove", onDrag);
    document.addEventListener("mouseup", onDrop);
  }
  function laneAt(y) { return $$(".pmrm-lane[data-room]").find(l => { const b = l.getBoundingClientRect(); return y >= b.top && y < b.bottom; }) || null; }
  function onDrag(ev) {
    const g = drag; if (!g) return;
    if (!g.on && Math.abs(ev.clientX - g.x0) < 5 && Math.abs(ev.clientY - g.y0) < 5) return;
    if (!g.on) { g.on = true; g.blk.classList.add("pmrm-blk--drag"); hideGhost(); }
    ev.preventDefault();
    const lane = laneAt(ev.clientY) || g.lane, w = g.lane.getBoundingClientRect().width || 1, len = g.e - g.s;
    const s = Math.max(H0, Math.min(H1 - len, g.s + Math.round((ev.clientX - g.x0) / w * SPAN / STEP) * STEP)), e = s + len;
    const r = roomBy(lane.getAttribute("data-room"), S.date), skip = y => y.event_id === g.x.event_id || (!!g.x.uid && y.uid === g.x.uid);
    let err = "";
    if (!r || r.error) err = "phòng chưa kết nối";
    else if (S.date === S.today && nowMin() != null && s < nowMin() - 5) err = "giờ đã qua";
    else { const c = clashOf(r, S.date, s, e, skip); if (c) err = "trùng " + hm(c.s) + "–" + hm(c.e); }
    g.to = { room: r ? r.name : "", label: r ? r.label : "", s, e, err };
    const gh = lane.querySelector(".pmrm-ghost");
    if (ghost && ghost !== gh) hideGhost();
    if (!gh) return;
    ghost = gh; gh.style.display = "block"; gh.style.left = pct(s) + "%"; gh.style.width = "calc(" + (pct(e) - pct(s)) + "% - 2px)";
    gh.classList.toggle("pmrm-ghost--bad", !!err); gh.textContent = hm(s) + "–" + hm(e) + (err ? " · " + err : "");
  }
  function endDrag() {
    document.removeEventListener("mousemove", onDrag); document.removeEventListener("mouseup", onDrop);
    if (drag && drag.blk) drag.blk.classList.remove("pmrm-blk--drag");
    if (ghost) ghost.classList.remove("pmrm-ghost--bad");
    hideGhost();
  }
  function cancelDrag() { const on = drag && drag.on; endDrag(); drag = null; if (on) { S.noClick = true; setTimeout(() => { S.noClick = false; }, 0); } }
  function onDrop() {
    const g = drag; endDrag(); drag = null;
    if (!g || !g.on) return;   /* chỉ là bấm -> onClick mở hộp Sửa */
    S.noClick = true; setTimeout(() => { S.noClick = false; }, 0);
    const to = g.to;
    if (!to || (to.room === g.x.room && to.s === g.s)) return;
    if (to.err) return toast("Không chuyển được: " + to.err + ".", true);
    moveTo(g.x, to);
  }
  async function moveTo(x, to) {
    if (S.moving || !alive()) return;
    const day = String(x.start).slice(0, 10), prev = { room: x.room, label: x.label, start: x.start, end: x.end, state: x.state };
    const args = { event_id: x.event_id, start: day + " " + hm(to.s) + ":00", end: day + " " + hm(to.e) + ":00" };
    if (to.room !== x.room) args.room = to.room;
    Object.assign(x, { room: to.room, label: to.label || x.label, start: args.start, end: args.end, state: "pending" });
    S.moving = x.event_id; paint();
    let res;
    try { res = await call("rooms.update", args); }
    catch (e) {
      S.moving = null; if (S.dead) return;
      Object.assign(x, prev); paint();
      toast("Chưa chuyển được: " + msgOf(e) + " Lịch giữ nguyên như cũ.", true); return;
    }
    S.moving = null; if (S.dead) return;
    if (!res || !res.ok) { Object.assign(x, prev); paint(); toast("Chưa chuyển được, lịch giữ nguyên như cũ.", true); return; }
    const p = applyEdit(x, args, res, false, null);
    paint();
    toast("Đã chuyển sang " + (res.label || to.label || "phòng mới") + " " + hm(to.s) + "–" + hm(to.e) + (p ? ", chờ phòng xác nhận…" : "."));
  }
  function onChange(ev) { if (ev.target.hasAttribute && ev.target.hasAttribute("data-pick") && ev.target.value) setDate(ev.target.value); }
  function onVis() { if (!document.hidden && S.stale) refresh(); }
  R.addEventListener("click", onClick);
  R.addEventListener("keydown", onKey);
  R.addEventListener("mousemove", onMove);
  R.addEventListener("mousedown", onDown);
  R.addEventListener("mouseleave", hideGhost);
  R.addEventListener("change", onChange);
  document.addEventListener("visibilitychange", onVis);
  const iv = setInterval(() => {
    if (!alive()) return;
    if (document.hidden) { S.stale = true; return; }
    if (!S.dlg) refresh(); else paintGrid();
  }, REFRESH_MS);
  function destroy() {
    if (S.dead) return;
    S.dead = true; clearInterval(iv); S.timers.forEach(clearTimeout); S.timers = [];
    document.removeEventListener("visibilitychange", onVis);
    endDrag(); drag = null;
    closeDlg(true);
    if (el._pmrm === ctl) el._pmrm = null;
  }
  const ctl = { refresh, destroy, _state: S };
  el._pmrm = ctl;
  refresh();
  return ctl;
}

root.PMRooms = { render, _spanOn: spanOn, _esc: esc, _occurrences: occurrences };
})(window);
