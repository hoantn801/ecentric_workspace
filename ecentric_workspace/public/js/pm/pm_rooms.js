/* pm_rooms.js — Phòng họp (05/11/2026, demo v2 PO duyệt). Asset tĩnh, /pm tải lười khi mở #rooms
 * hoặc tab "Phòng họp" trong #schedule (pm_app.html pmRoomsAssets, cùng ?v= với pm_redesign.js).
 * Một global: window.PMRooms.render(container, {api, errOf, toast, head, mode:"page"|"tab"}) -> {refresh, destroy}.
 *   api(method, args) -> Promise (host /pm truyền api() của trang); thiếu thì tự POST /api/method kèm CSRF.
 *   mode "page" = trang #rooms (3 ô tóm tắt + lưới + "Phòng bạn đã đặt"); "tab" = tab trong #schedule (chỉ lưới).
 * Dữ liệu: ecentric_workspace.pm.api.rooms.{day, mine, book, booking_state, cancel} + assignment.list_assignable.
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

function render(el, opts) {
  opts = opts || {};
  if (el._pmrm) el._pmrm.destroy();
  const mode = opts.mode === "tab" ? "tab" : "page";
  const POLLS = Array.isArray(opts.pollMs) && opts.pollMs.length ? opts.pollMs : POLL_MS;   /* pollMs: chỉ để test */
  const me = ++UID, idp = "pmrm" + me + "-";
  const S = { date: null, today: null, cache: {}, mine: [], mineErr: "", pending: {}, err: "", loading: false,
              nowMin: null, nowAt: 0, seq: 0, dead: false, stale: false, timers: [], people: null, peopleP: null,
              confirm: null, dlg: null, gone: {} };   /* gone: event_id / uid vừa huỷ (Graph / lịch phòng có thể trễ vài giây) */
  const call = (m, a) => (typeof opts.api === "function" ? opts.api(NS + m, a || {}) : fetchApi(NS + m, a));
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
  const mineBy = () => { const m = {}; S.mine.forEach(x => { if (x.uid) m[x.uid] = x; }); return m; };
  /* các khối của một phòng trong một ngày: busy (người khác) | mine (bạn, phòng đã nhận) | pend (chờ phòng nhận) */
  function items(r, day) {
    if (!r) return [];
    const mb = mineBy(), out = [], seen = {};
    (r.bookings || []).forEach(b => {
      if (b.uid && S.gone[b.uid]) return;
      const sp = spanOn(b, day); if (!sp) return;
      if (b.uid) seen[b.uid] = 1;
      const m = b.mine ? mb[b.uid] : null;
      const loc = b.mine ? Object.keys(S.pending).map(k => S.pending[k]).find(p => p.uid && p.uid === b.uid) : null;
      const subj = (m && m.subject) || (loc && loc.subject) || "";
      out.push({ s: sp.s, e: sp.e, kind: b.mine ? ((m && m.state === "pending") ? "pend" : "mine") : "busy",
                 who: b.who || "", subject: subj, uid: b.uid || "", event_id: (m && m.event_id) || (loc && loc.event_id) || "" });
    });
    const extra = S.mine.filter(x => x.room === r.name && x.state !== "declined" && !(x.uid && seen[x.uid]));
    Object.keys(S.pending).forEach(k => {
      const p = S.pending[k];
      if (p.room === r.name && p.state !== "declined" && !(p.uid && seen[p.uid]) && !S.mine.some(x => x.event_id === p.event_id)) extra.push(p);
    });
    extra.forEach(x => {
      const sp = spanOn(x, day); if (!sp) return;
      if (x.uid) seen[x.uid] = 1;
      out.push({ s: sp.s, e: sp.e, kind: x.state === "accepted" ? "mine" : "pend", who: "", subject: x.subject || "", uid: x.uid || "", event_id: x.event_id || "" });
    });
    return out.sort((a, b) => a.s - b.s || a.e - b.e);
  }
  const clashOf = (r, day, s, e) => items(r, day).find(x => x.s < e && s < x.e) || null;
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
        const t = hm(x.s) + "–" + hm(x.e);
        const main = x.kind === "busy" ? (x.who || "Đã có người đặt") : (x.subject || "Bạn đặt");
        const tip = x.kind === "busy" ? "Đã có người đặt: " + main + " · " + t : main + " · " + t + (x.kind === "pend" ? " · chờ phòng nhận" : "");
        return '<div class="pmrm-blk pmrm-blk--' + x.kind + '" data-kind="' + x.kind + '" data-uid="' + esc(x.uid) + '" style="left:' + pct(x.s) + "%;width:calc(" + (pct(x.e) - pct(x.s)) + '% - 2px)" title="' + esc(tip) + '">' +
          esc(main) + "<small>" + t + (x.kind === "pend" ? " · chờ phòng nhận" : "") + "</small></div>";
      }).join("");
      const nowLine = today && n != null && n >= H0 && n <= H1 ? '<div class="pmrm-now" style="left:' + pct(n) + '%" aria-hidden="true"></div>' : "";
      const lbl = "Đặt phòng " + (r.label || r.code) + ", " + (today ? "hôm nay" : wday(S.date) + " " + dm(S.date)) + (list.length ? ", đã có " + list.length + " lịch" : ", còn trống");
      h += '<div class="pmrm-lane" role="button" tabindex="0" data-room="' + esc(r.name) + '" aria-label="' + esc(lbl) + '">' + blocks + nowLine + '<div class="pmrm-ghost" aria-hidden="true"></div></div></div>';
    });
    tl.innerHTML = h + "</div>";
  }
  function mineRows() {
    const rows = S.mine.slice();
    Object.keys(S.pending).forEach(k => { const p = S.pending[k]; if (!rows.some(x => x.event_id === p.event_id || (p.uid && x.uid === p.uid))) rows.push(p); });
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
      const id = esc(x.event_id || "");
      const act = S.confirm === x.event_id
        ? '<span class="pmrm-cf" role="group" aria-label="Xác nhận huỷ"><span>Huỷ lịch này?</span><button type="button" class="pmrm-btn pmrm-btn--danger" data-act="cancel-yes" data-ev="' + id + '">Huỷ phòng</button><button type="button" class="pmrm-btn" data-act="cancel-no">Giữ</button></span>'
        : (x.event_id ? '<button type="button" class="pmrm-btn" data-act="cancel" data-ev="' + id + '" aria-label="Huỷ ' + esc(x.subject || "lịch") + '">Huỷ</button>' : "");
      return '<div class="pmrm-mrow" data-ev-row="' + id + '"><div class="pmrm-mmain"><b>' + esc(x.subject || "(Không tên)") + "</b><small>" + esc(x.label || x.room) + " · " + when + ' <span class="pmrm-num">' + esc(String(x.start).slice(11, 16)) + "–" + esc(String(x.end).slice(11, 16)) + "</span>" +
        (x.join_url ? ' · <a class="pmrm-link" href="' + esc(x.join_url) + '" target="_blank" rel="noopener">Mở Teams</a>' : "") + "</small></div>" +
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
    jobs.push(call("rooms.mine", {}));
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
      const p = S.pending[k], x = S.mine.find(r => r.event_id === p.event_id); if (!x) return;
      if (p.state === "pending" && x.state !== "pending") announce(p, x.state);
      if (x.state === p.state || x.state !== "pending") delete S.pending[k];
    });
    S.stale = false;
    paint();
  }
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

  /* ---------------- hộp đặt phòng */
  function openBook(roomName, day, s, e) {
    closeDlg(true);
    const rooms = roomsOf(day).length ? roomsOf(day) : roomsOf(S.date);
    const last = document.activeElement;
    const host = el.closest("#ec-pm-root") || document.body;
    const sc = document.createElement("div");
    sc.className = "pmrm-scrim";
    const opt = rooms.map(r => '<option value="' + esc(r.name) + '"' + (r.error ? " disabled" : "") + (r.name === roomName ? " selected" : "") + ">" + esc(r.label || r.code) +
      ([r.floor, r.note].filter(Boolean).length ? " · " + esc([r.floor, r.note].filter(Boolean).join(", ")) : "") + (r.error ? " (chưa kết nối)" : "") + "</option>").join("");
    sc.innerHTML = '<form class="pmrm-dlg" role="dialog" aria-modal="true" aria-labelledby="' + idp + 'dt" novalidate>' +
      '<header><h2 id="' + idp + 'dt">Đặt phòng họp</h2><button type="button" class="pmrm-x" data-act="close" aria-label="Đóng">×</button></header>' +
      '<div class="pmrm-body">' +
      '<div class="pmrm-fld"><label for="' + idp + 't">Tên cuộc họp</label><input id="' + idp + 't" data-f="subject" maxlength="200" autocomplete="off" required placeholder="Ví dụ: Review kế hoạch tháng 12"></div>' +
      '<div class="pmrm-fld"><label for="' + idp + 'r">Phòng</label><select id="' + idp + 'r" data-f="room">' + opt + "</select></div>" +
      '<div class="pmrm-row3"><div class="pmrm-fld"><label for="' + idp + 'd">Ngày</label><input id="' + idp + 'd" type="date" data-f="date" required></div>' +
      '<div class="pmrm-fld"><label for="' + idp + 's">Từ</label><input id="' + idp + 's" type="time" step="1800" data-f="start" required></div>' +
      '<div class="pmrm-fld"><label for="' + idp + 'e">Đến</label><input id="' + idp + 'e" type="time" step="1800" data-f="end" required></div></div>' +
      '<div class="pmrm-warn" data-warn role="alert" hidden></div>' +
      '<div class="pmrm-fld"><label for="' + idp + 'w">Mời thêm (không bắt buộc)</label><div class="pmrm-chips" data-chips></div>' +
      '<div class="pmrm-combo"><input id="' + idp + 'w" data-f="who" autocomplete="off" placeholder="Gõ tên hoặc email" role="combobox" aria-expanded="false" aria-autocomplete="list" aria-controls="' + idp + 'wl">' +
      '<ul class="pmrm-opts" id="' + idp + 'wl" role="listbox" aria-label="Người được mời" hidden></ul></div></div>' +
      '<label class="pmrm-check"><input type="checkbox" data-f="teams" checked> Kèm link họp Teams</label>' +
      '<div class="pmrm-note">Phòng trống thì tự nhận ngay. Lịch vào Outlook/Teams của bạn và người được mời; huỷ ở đây hay trên Teams đều được.</div>' +
      "</div><footer><button type=\"button\" class=\"pmrm-btn\" data-act=\"close\">Huỷ</button><button type=\"submit\" class=\"pmrm-btn pmrm-btn--pri\" data-submit>Đặt phòng</button></footer></form>";
    host.appendChild(sc);
    const f = k => sc.querySelector('[data-f="' + k + '"]');
    const D = S.dlg = { sc, last, room: roomName, who: [], busy: false, active: -1, opts: [] };
    if (!f("room").value || f("room").selectedOptions && f("room").selectedOptions[0] && f("room").selectedOptions[0].disabled) {
      const ok = rooms.find(r => !r.error); if (ok) f("room").value = ok.name;
    }
    const s0 = s != null ? s : 13 * 60;
    f("date").value = day || S.date; f("start").value = hm(s0); f("end").value = hm(e != null ? e : Math.min(s0 + 60, 23 * 60 + 30));
    if (S.today) f("date").min = S.today;
    sc.addEventListener("click", ev => {
      if (ev.target === sc) return closeDlg();
      const a = ev.target.closest("[data-act],[data-rm],[data-opt]"); if (!a) return;
      if (a.getAttribute("data-act") === "close") closeDlg();
      else if (a.hasAttribute("data-rm")) { D.who = D.who.filter(p => p.email !== a.getAttribute("data-rm")); chips(); f("who").focus(); }
      else if (a.hasAttribute("data-opt")) pick(D.opts[+a.getAttribute("data-opt")]);
    });
    sc.addEventListener("mousedown", ev => { if (ev.target.closest("[data-opt]")) ev.preventDefault(); });
    sc.addEventListener("change", ev => { if (ev.target.closest("[data-f]") && ev.target !== f("who")) check(); });
    sc.addEventListener("input", ev => { if (ev.target === f("who")) suggest(); else if (ev.target.closest('[data-f="start"],[data-f="end"]')) check(); });
    sc.addEventListener("keydown", ev => {
      if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); if (!sc.querySelector(".pmrm-opts").hidden) return hideOpts(); return closeDlg(); }
      if (ev.target === f("who")) return whoKey(ev);
      if (ev.key === "Tab") {   /* giữ focus trong hộp */
        const list = Array.prototype.slice.call(sc.querySelectorAll("input,select,button")).filter(x => !x.disabled);
        const i = list.indexOf(document.activeElement);
        if (ev.shiftKey && i <= 0) { ev.preventDefault(); list[list.length - 1].focus(); }
        else if (!ev.shiftKey && i === list.length - 1) { ev.preventDefault(); list[0].focus(); }
      }
    });
    f("who").addEventListener("focus", loadPeople);
    sc.querySelector("form").addEventListener("submit", ev => { ev.preventDefault(); submit(); });
    function chips() {
      sc.querySelector("[data-chips]").innerHTML = D.who.map(p => '<span class="pmrm-chip">' + esc(p.full_name || p.email) +
        '<button type="button" data-rm="' + esc(p.email) + '" aria-label="Bỏ ' + esc(p.full_name || p.email) + '">×</button></span>').join("");
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
        : '<li class="pmrm-optx">Không thấy ai. Gõ đủ email rồi Enter.</li>';
      ul.hidden = false; f("who").setAttribute("aria-expanded", "true");
      if (D.active >= 0) f("who").setAttribute("aria-activedescendant", idp + "o" + D.active); else f("who").removeAttribute("aria-activedescendant");
    }
    function pick(p) {
      if (!p || D.who.some(x => x.email === p.email)) return;
      D.who.push(p); f("who").value = ""; hideOpts(); chips();
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
        else if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) { ev.preventDefault(); const em = v.toLowerCase(); pick((S.people || []).find(p => p.email === em) || { email: em, full_name: em }); }
      } else if (ev.key === "Backspace" && !f("who").value && D.who.length) { D.who.pop(); chips(); }
    }
    D.f = f; D.chips = chips;
    check();
    sc.querySelector('[data-f="subject"]').focus();
  }
  async function loadPeople() {
    if (S.people || S.peopleP) return;
    S.peopleP = call("assignment.list_assignable", {}).then(r => { S.people = ((r && r.rows) || []).filter(p => p && p.email); },
      () => { S.peopleErr = true; }).then(() => { S.peopleP = null; if (S.dlg && S.dlg.f("who").value.trim()) S.dlg.sc.querySelector('[data-f="who"]').dispatchEvent(new Event("input", { bubbles: true })); });
  }
  function closeDlg(quiet) {
    const D = S.dlg; if (!D) return;
    S.dlg = null;
    if (D.sc.parentNode) D.sc.parentNode.removeChild(D.sc);
    if (quiet) return;
    let back = D.last && D.last.isConnected ? D.last : null;
    if (!back && D.room) back = $$(".pmrm-lane[data-room]").find(x => x.getAttribute("data-room") === D.room) || null;
    if (back && back.focus) back.focus();
  }
  /* kiểm ở client bằng dữ liệu đã tải (server vẫn kiểm lại khi đặt) */
  function check() {
    const D = S.dlg; if (!D) return false;
    const f = D.f, w = D.sc.querySelector("[data-warn]"), day = f("date").value, s = toMin(f("start").value), e = toMin(f("end").value);
    D.room = f("room").value;
    let m = "";
    if (!day || s == null || e == null) m = "Chọn ngày và giờ họp.";
    else if (e <= s) m = "Giờ kết thúc phải sau giờ bắt đầu.";
    else if (e - s > 600) m = "Một lần đặt tối đa 10 giờ.";
    else if (S.today && (day < S.today || (day === S.today && nowMin() != null && s < nowMin() - 5))) m = "Không đặt được giờ đã qua.";
    else if (!S.cache[day]) { ensureDay(day).then(() => { if (S.dlg === D) check(); }); }
    else {
      const r = (S.cache[day].rooms || []).find(x => x.name === D.room);
      if (r && r.error) m = "Phòng này chưa kết nối lịch: " + offText(r.error) + ".";
      else {
        const c = r ? clashOf(r, day, s, e) : null;
        if (c) m = c.kind === "busy" ? "Phòng đã có người đặt " + hm(c.s) + "–" + hm(c.e) + " (" + (c.who || "đã đặt") + "). Chọn giờ hoặc phòng khác." : "Bạn đã đặt phòng này " + hm(c.s) + "–" + hm(c.e) + ".";
      }
    }
    w.textContent = m; w.hidden = !m;
    D.sc.querySelector("[data-submit]").disabled = !!m || D.busy;
    return !m;
  }
  async function submit() {
    const D = S.dlg; if (!D || D.busy) return;
    const f = D.f, w = D.sc.querySelector("[data-warn]"), subject = f("subject").value.trim();
    if (!subject) { w.textContent = "Ghi tên cuộc họp."; w.hidden = false; f("subject").focus(); return; }
    if (!check()) return;
    const typed = f("who").value.trim();
    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(typed) && !D.who.some(p => p.email === typed.toLowerCase())) D.who.push({ email: typed.toLowerCase(), full_name: typed });
    const day = f("date").value, args = { room: f("room").value, start: day + " " + f("start").value.slice(0, 5) + ":00", end: day + " " + f("end").value.slice(0, 5) + ":00",
      subject, attendees: JSON.stringify(D.who.map(p => p.email)), teams: f("teams").checked ? 1 : 0 };
    const btn = D.sc.querySelector("[data-submit]");
    D.busy = true; btn.disabled = true; btn.textContent = "Đang đặt…"; btn.setAttribute("aria-busy", "true");
    let res;
    try { res = await call("rooms.book", args); }
    catch (e) {
      if (S.dlg !== D) return;
      D.busy = false; btn.textContent = "Đặt phòng"; btn.removeAttribute("aria-busy"); btn.disabled = false;
      w.textContent = msgOf(e); w.hidden = false; return;
    }
    if (S.dead) return;
    if (!res || !res.event_id) {
      if (S.dlg === D) { D.busy = false; btn.textContent = "Đặt phòng"; btn.removeAttribute("aria-busy"); btn.disabled = false; w.textContent = "Chưa đặt được phòng, thử lại."; w.hidden = false; }
      return;
    }
    const p = Object.assign({}, res, { state: res.state || "pending", subject: res.subject || subject });
    S.pending[p.event_id] = p;
    closeDlg();
    if (p.start && String(p.start).slice(0, 10) !== S.date) S.date = String(p.start).slice(0, 10);
    paint();
    toast("Đã gửi lịch, chờ phòng xác nhận…");
    poll(p, 0);
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
  async function doCancel(btn, id) {
    if (!id || btn.disabled) return;
    const grp = btn.closest(".pmrm-cf");
    $$("button", grp).forEach(b => { b.disabled = true; });
    btn.textContent = "Đang huỷ…"; btn.setAttribute("aria-busy", "true");
    try { await call("rooms.cancel", { event_id: id }); }
    catch (e) {
      if (S.dead) return;
      toast("Chưa huỷ được: " + msgOf(e), true); S.confirm = null; paintMine();
      const again = $$('[data-act="cancel"]').find(x => x.getAttribute("data-ev") === id); if (again) again.focus();
      return;
    }
    if (S.dead) return;
    const was = S.mine.find(x => x.event_id === id) || S.pending[id];
    S.gone[id] = 1; if (was && was.uid) S.gone[was.uid] = 1;
    S.confirm = null; delete S.pending[id];
    S.mine = S.mine.filter(x => x.event_id !== id);
    toast("Đã huỷ · phòng và người được mời nhận thông báo huỷ");
    paint(); refresh();
  }

  /* ---------------- sự kiện (uỷ quyền trên gốc) */
  let ghost = null;
  function hideGhost() { if (ghost) { ghost.style.display = "none"; ghost = null; } }
  function onClick(ev) {
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
    if (act === "cancel-yes") return doCancel(t, t.getAttribute("data-ev"));
    if (t.classList.contains("pmrm-lane")) {
      const r = roomBy(t.getAttribute("data-room"), S.date); if (!r || r.error) return;
      const blk = ev.target.closest(".pmrm-blk");
      if (blk) {
        const k = blk.getAttribute("data-kind");
        return toast(k === "busy" ? "Giờ này đã có người đặt." : k === "pend" ? "Đang chờ phòng nhận lịch của bạn." : "Lịch của bạn" + (mode === "page" ? ": huỷ ở mục Phòng bạn đã đặt bên dưới." : "."));
      }
      const x = slotFor(r, S.date, slotAt(t, ev.clientX));
      if (x.err) return toast(x.err);
      openBook(r.name, S.date, x.s, x.e);
    }
  }
  function onKey(ev) {
    const t = ev.target;
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
    const lane = ev.target.closest && ev.target.closest(".pmrm-lane[data-room]");
    if (!lane || ev.target.closest(".pmrm-blk")) return hideGhost();
    const r = roomBy(lane.getAttribute("data-room"), S.date); if (!r) return hideGhost();
    const x = slotFor(r, S.date, slotAt(lane, ev.clientX));
    const g = lane.querySelector(".pmrm-ghost");
    if (ghost && ghost !== g) hideGhost();
    if (x.err || !g) return hideGhost();
    ghost = g; g.style.display = "block"; g.style.left = pct(x.s) + "%"; g.style.width = "calc(" + (pct(x.e) - pct(x.s)) + "% - 2px)"; g.textContent = "+ " + hm(x.s);
  }
  function onChange(ev) { if (ev.target.hasAttribute && ev.target.hasAttribute("data-pick") && ev.target.value) setDate(ev.target.value); }
  function onVis() { if (!document.hidden && S.stale) refresh(); }
  R.addEventListener("click", onClick);
  R.addEventListener("keydown", onKey);
  R.addEventListener("mousemove", onMove);
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
    closeDlg(true);
    if (el._pmrm === ctl) el._pmrm = null;
  }
  const ctl = { refresh, destroy, _state: S };
  el._pmrm = ctl;
  refresh();
  return ctl;
}

root.PMRooms = { render, _spanOn: spanOn, _esc: esc };
})(window);
