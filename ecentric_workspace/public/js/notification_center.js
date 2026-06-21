// Copyright (c) 2026, eCentric and contributors
// Notification Center (app-owned asset, ERP-wide GLOBAL loader).
//
// Loaded on EVERY website-rendered eCentric page via the `web_include_js` hook
// (hooks.py) -- NOT per-page, NOT via a DB patch per page, and NEVER on Frappe Desk.
//
// Click interception is a SINGLE document-level CAPTURE-phase delegated handler, so it
// works no matter WHEN the header/bell is rendered or re-rendered (dynamic pages such
// as /approval render the bell after this asset loads). Because it runs in the capture
// phase at document, stopImmediatePropagation() on a plain left-click prevents ANY
// legacy bell handler -- inline onclick, property handler, target listener OR a
// document-level delegated listener (the old "feature in development" toast) -- from
// ever firing, regardless of when it was attached. Modifier/middle clicks are left
// untouched so the native /app/notification-log navigation is preserved. A
// MutationObserver is used ONLY to (re)mount the badge/dropdown when the header
// (re)renders -- never for click interception.
//
// Notification subject/message are rendered as SAFE PLAIN TEXT (DOMParser -> textContent,
// whitespace-normalized) via textContent only -- never innerHTML with notification data.
//
// API calls use frappe.call with the CORRECT http type (GET vs POST) to match the
// backend @frappe.whitelist(methods=[...]).
(function () {
  'use strict';
  if (window._ecNotifCenterInstalled) { return; }
  // Never bind on Frappe Desk -- Desk owns its own native bell. The custom eCentric
  // shell pages live at website routes (/home, /overview, /approval, ...), never Desk.
  // Match ONLY the Desk root (/app or /app/...), never lookalikes like /approval.
  var _p = window.location.pathname || '';
  if (_p === '/app' || _p.indexOf('/app/') === 0) { return; }
  window._ecNotifCenterInstalled = true;

  var LIST_LIMIT = 20;
  var POLL_MS = 60000;
  var MUTE_KEY = 'ec_notif_muted';

  // ---- safe plain text: strip any HTML, decode entities, normalize whitespace -----
  function toPlainText(s) {
    if (s == null) return '';
    var str = String(s);
    try {
      if (window.DOMParser) {
        var doc = new window.DOMParser().parseFromString(str, 'text/html');
        if (doc && doc.body) str = doc.body.textContent;
      } else {
        str = str.replace(/<[^>]*>/g, '');
      }
    } catch (e) { str = str.replace(/<[^>]*>/g, ''); }
    return str.replace(/\s+/g, ' ').trim();
  }
  // Only allow a same-origin absolute path as a link target (server-built action_url).
  function safeActionUrl(u) {
    u = String(u == null ? '' : u);
    return /^\/(?!\/)/.test(u) ? u : '';
  }
  function isMuted() {
    try { return window.localStorage.getItem(MUTE_KEY) === '1'; } catch (e) { return false; }
  }
  function setMuted(v) {
    try { window.localStorage.setItem(MUTE_KEY, v ? '1' : '0'); } catch (e) {}
  }
  function ago(s) {
    if (!s) return '';
    var t = new Date(String(s).replace(' ', 'T') + 'Z');
    if (isNaN(t)) return '';
    var d = (Date.now() - t.getTime()) / 1000;
    if (d < 60) return 'vừa xong';
    if (d < 3600) return Math.floor(d / 60) + ' phút trước';
    if (d < 86400) return Math.floor(d / 3600) + ' giờ trước';
    return Math.floor(d / 86400) + ' ngày trước';
  }

  // ---- canonical Notification Bell contract -------------------------------
  // The ONE source of truth across EVERY ERP shell is the marker attribute
  //   data-ec-notification-bell="1"
  // No href / title / language / SVG / #i-bell / route heuristics are used.
  var BELL_SELECTOR = '[data-ec-notification-bell="1"]';
  // From a click target, return the bell element to act on (or null).
  function getNotificationBellTarget(node) {
    if (!node || !node.closest) return null;
    return node.closest(BELL_SELECTOR);
  }
  // Locate the current bell node for badge mount / observer (re-queried each time).
  function findBell() {
    return document.querySelector(BELL_SELECTOR);
  }

  var S = { items: [], unread: 0, open: false, interacted: false };
  var bell, badgeEl, pop, listEl, mo;
  // delivery v1 client state ------------------------------------------------
  var P = { sound_enabled: 1, desktop_enabled: 0, teams_enabled: 0, quiet_hours_enabled: 0,
            quiet_hours_start: null, quiet_hours_end: null, minimum_severity: 'info', enabled_event_types: '' };
  var SEV_RANK = { info: 0, action_required: 1, urgent: 2 };
  var TOAST_MAX = 3, toasts = [];
  var seen = {}, seenOrder = [], SEEN_KEY = 'ec_notif_seen';
  var prefCtl = {};

  // ---- styles: classes, reusing /home design tokens ------------------------
  function injectCss() {
    if (document.getElementById('ec-nc-css')) return;
    var st = document.createElement('style');
    st.id = 'ec-nc-css';
    st.textContent =
      '.ec-nc-badge{position:absolute;top:-4px;right:-4px;min-width:16px;height:16px;padding:0;border-radius:8px;background:var(--pink,#EF7CAF);color:#fff;font-size:9.5px;font-weight:600;line-height:16px;text-align:center;border:2px solid #fff;display:none;pointer-events:none;box-sizing:border-box;font-family:inherit;}' +
      '.ec-nc-badge.on{display:block;}' +
      '.ec-nc-badge--pill{min-width:21px;padding:0 4px;}' +
      '.ec-nc-pop{position:fixed;z-index:1000;width:360px;max-width:92vw;max-height:72vh;background:#fff;border:1px solid var(--gray-200,#e5e7eb);border-radius:12px;box-shadow:0 6px 24px rgba(0,0,0,.10);display:none;flex-direction:column;overflow:hidden;font-family:inherit;}' +
      '.ec-nc-pop.on{display:flex;}' +
      '.ec-nc-hd{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid var(--gray-100,#f1f2f4);}' +
      '.ec-nc-hd h4{margin:0;font-size:14px;font-weight:600;color:var(--gray-900,#111827);flex:1;}' +
      '.ec-nc-mute{background:none;border:none;cursor:pointer;color:var(--gray-500,#6b7280);font-size:12px;padding:2px 4px;border-radius:6px;}' +
      '.ec-nc-mute:hover{background:var(--gray-100,#eef0f3);}' +
      '.ec-nc-list{overflow-y:auto;}' +
      '.ec-nc-item{display:block;padding:11px 14px;border-bottom:1px solid var(--gray-100,#f1f2f4);text-decoration:none !important;color:inherit;cursor:pointer;}' +
      '.ec-nc-item:last-child{border-bottom:none;}' +
      '.ec-nc-item:hover{background:var(--gray-50,#f7f8fb);}' +
      '.ec-nc-item.unread{background:rgba(44,61,166,.045);}' +
      '.ec-nc-item:focus{outline:2px solid var(--navy,#2C3DA6);outline-offset:-2px;}' +
      '.ec-nc-r1{display:flex;align-items:center;gap:8px;margin-bottom:3px;}' +
      '.ec-nc-udot{width:7px;height:7px;border-radius:50%;background:var(--navy,#2C3DA6);flex-shrink:0;}' +
      '.ec-nc-src{font-size:10px;font-weight:700;letter-spacing:.4px;color:var(--navy,#2C3DA6);}' +
      '.ec-nc-time{margin-left:auto;font-size:11px;color:var(--gray-400,#9ca3af);}' +
      '.ec-nc-subj{font-size:13px;font-weight:600;color:var(--gray-900,#111827);line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}' +
      '.ec-nc-msg{font-size:11.5px;color:var(--gray-600,#6b7280);line-height:1.4;margin-top:2px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}' +
      '.ec-nc-empty{padding:30px 16px;text-align:center;color:var(--gray-500,#6b7280);font-size:13px;}' +
      '.ec-nc-ft{display:flex;align-items:stretch;border-top:1px solid var(--gray-100,#f1f2f4);}' +
      '.ec-nc-ft > *{flex:1;text-align:center;padding:10px;font-size:12.5px;font-weight:600;color:var(--navy,#2C3DA6);background:none;border:none;cursor:pointer;text-decoration:none !important;font-family:inherit;}' +
      '.ec-nc-ft > *:hover{background:var(--gray-50,#f7f8fb);}' +
      '.ec-nc-ft .ec-nc-sep{flex:0 0 1px;padding:0;background:var(--gray-100,#f1f2f4);}' +
      '#ec-nc-toasts{position:fixed;right:16px;bottom:16px;z-index:1100;display:flex;flex-direction:column;gap:10px;max-width:360px;width:92vw;pointer-events:none;}' +
      '.ec-nc-toast{position:relative;pointer-events:auto;background:#fff;border:1px solid var(--gray-200,#e5e7eb);border-left:4px solid var(--navy,#2C3DA6);border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.12);padding:11px 30px 11px 13px;opacity:0;transform:translateY(8px);transition:opacity .2s,transform .2s;font-family:inherit;}' +
      '.ec-nc-toast.on{opacity:1;transform:none;}' +
      '.ec-nc-toast--action_required{border-left-color:#FFB900;}' +
      '.ec-nc-toast--urgent{border-left-color:#D13438;}' +
      '.ec-nc-toast-ttl{font-size:13px;font-weight:600;color:var(--gray-900,#111827);line-height:1.35;}' +
      '.ec-nc-toast-msg{font-size:11.5px;color:var(--gray-600,#6b7280);margin-top:2px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}' +
      '.ec-nc-toast-meta{font-size:10.5px;color:var(--gray-400,#9ca3af);margin-top:4px;}' +
      '.ec-nc-toast-x{position:absolute;top:6px;right:8px;background:none;border:none;font-size:16px;line-height:1;color:var(--gray-400,#9ca3af);cursor:pointer;}' +
      '.ec-nc-prefs{display:none;padding:10px 14px;overflow-y:auto;}' +
      '.ec-nc-pop.prefs .ec-nc-list{display:none;}' +
      '.ec-nc-pop.prefs .ec-nc-prefs{display:block;}' +
      '.ec-nc-prow{display:flex;align-items:center;gap:8px;padding:7px 0;font-size:12.5px;color:var(--gray-800,#1f2937);}' +
      '.ec-nc-prow > span:first-child{flex:1;}' +
      '.ec-nc-prefbtn{display:block;width:100%;margin:6px 0;padding:8px;border:1px solid var(--navy,#2C3DA6);background:none;color:var(--navy,#2C3DA6);border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;font-family:inherit;}' +
      '.ec-nc-prefbtn:hover{background:var(--gray-50,#f7f8fb);}';
    document.head.appendChild(st);
  }

  // ---- badge mounted onto the current native bell (idempotent) -------------
  function mountBadge() {
    if (!bell) return;
    var dot = bell.querySelector('.dot');
    if (dot) { dot.style.display = 'none'; }
    if (window.getComputedStyle && window.getComputedStyle(bell).position === 'static') { bell.style.position = 'relative'; }
    var prev = bell.querySelector('.ec-nc-badge');
    if (prev && prev.parentNode) { prev.parentNode.removeChild(prev); }
    badgeEl = document.createElement('span');
    badgeEl.className = 'ec-nc-badge';
    badgeEl.setAttribute('aria-hidden', 'true');
    bell.appendChild(badgeEl);            // .icon-btn is position:relative
    renderBadge();
  }

  // Ensure the badge is mounted on the CURRENT bell (used by observer + on open).
  function ensureBadge() {
    var b = findBell();
    if (!b) return;
    if (b !== bell || !b.querySelector('.ec-nc-badge')) { bell = b; mountBadge(); }
  }

  function buildPop() {
    var prev = document.getElementById('ec-nc-pop-root');
    if (prev && prev.parentNode) { prev.parentNode.removeChild(prev); }
    pop = document.createElement('div');
    pop.className = 'ec-nc-pop';
    pop.id = 'ec-nc-pop-root';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', 'Thông báo');
    // Static chrome only -- contains NO notification data, so innerHTML here is safe.
    pop.innerHTML =
      '<div class="ec-nc-hd">' +
        '<h4>Thông báo</h4>' +
        '<button class="ec-nc-mute" id="ec-nc-prefs-btn" type="button" title="Cài đặt thông báo" aria-label="Cài đặt thông báo">\u2699</button>' +
        '<button class="ec-nc-mute" id="ec-nc-mute" type="button"></button>' +
      '</div>' +
      '<div class="ec-nc-list" id="ec-nc-list"></div>' +
      '<div class="ec-nc-prefs" id="ec-nc-prefs"></div>' +
      '<div class="ec-nc-ft">' +
        '<button id="ec-nc-allread" type="button">Đánh dấu tất cả đã đọc</button>' +
        '<span class="ec-nc-sep"></span>' +
        '<a id="ec-nc-viewall" href="/app/notification-log">Xem tất cả thông báo</a>' +
      '</div>';
    document.body.appendChild(pop);
    listEl = pop.querySelector('#ec-nc-list');
    pop.querySelector('#ec-nc-allread').addEventListener('click', markAll);
    pop.querySelector('#ec-nc-mute').addEventListener('click', function () { setMuted(!isMuted()); renderMute(); });
    pop.querySelector('#ec-nc-prefs-btn').addEventListener('click', function () {
      pop.classList.toggle('prefs'); if (pop.classList.contains('prefs')) renderPrefsPanel();
    });
    buildPrefsPanel();
    renderMute();
  }

  function renderMute() {
    var b = pop && pop.querySelector('#ec-nc-mute');
    if (b) b.textContent = isMuted() ? 'Bật âm' : 'Tắt âm';
  }

  // 0 -> hidden; 1-9 -> circle; >9 -> '9+' pill (capped, no header shift).
  function renderBadge() {
    if (!badgeEl) return;
    if (S.unread > 0) {
      var pill = S.unread > 9;
      badgeEl.textContent = pill ? '9+' : String(S.unread);
      badgeEl.classList.toggle('ec-nc-badge--pill', pill);
      badgeEl.classList.add('on');
    } else {
      badgeEl.classList.remove('on');
      badgeEl.classList.remove('ec-nc-badge--pill');
      badgeEl.textContent = '';
    }
  }

  // ---- list rendering: SAFE PLAIN TEXT only, via textContent (no innerHTML data) ----
  function renderList() {
    if (!listEl) return;
    while (listEl.firstChild) { listEl.removeChild(listEl.firstChild); }
    if (!S.items.length) {
      var em = document.createElement('div');
      em.className = 'ec-nc-empty';
      em.textContent = 'Chưa có thông báo nào';
      listEl.appendChild(em);
      return;
    }
    S.items.forEach(function (it, i) {
      var a = document.createElement('a');
      a.className = 'ec-nc-item' + (it.is_read ? '' : ' unread');
      a.setAttribute('tabindex', '0');
      a.setAttribute('href', safeActionUrl(it.action_url) || '#');   // server-built path only

      var r1 = document.createElement('div'); r1.className = 'ec-nc-r1';
      if (!it.is_read) { var ud = document.createElement('span'); ud.className = 'ec-nc-udot'; r1.appendChild(ud); }
      var src = document.createElement('span'); src.className = 'ec-nc-src'; src.textContent = toPlainText(it.source_label); r1.appendChild(src);
      var tm = document.createElement('span'); tm.className = 'ec-nc-time'; tm.textContent = ago(it.created_at); r1.appendChild(tm);
      a.appendChild(r1);

      var subj = document.createElement('div'); subj.className = 'ec-nc-subj'; subj.textContent = toPlainText(it.subject); a.appendChild(subj);
      var msgText = toPlainText(it.message);
      if (msgText) { var m = document.createElement('div'); m.className = 'ec-nc-msg'; m.textContent = msgText; a.appendChild(m); }

      a.addEventListener('click', function (ev) { ev.preventDefault(); onItemClick(S.items[i]); });
      a.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onItemClick(S.items[i]); }
      });
      listEl.appendChild(a);
    });
  }

  // ---- API (http type MUST match the backend whitelist methods) ------------
  function call(method, httpType, args, cb) {
    if (!(window.frappe && typeof window.frappe.call === 'function')) return;
    window.frappe.call({
      method: 'ecentric_workspace.notification_center.api.' + method,
      type: httpType,
      args: args || {},
      callback: function (r) { if (cb) cb(r && r.message); },
      error: function () {}
    });
  }

  function refresh() {
    call('get_notifications', 'GET', { limit: LIST_LIMIT }, function (msg) {
      if (!msg || !msg.success) return;
      S.items = msg.items || [];
      S.unread = msg.unread || 0;
      renderBadge();
      if (S.open) renderList();
    });
  }
  function refreshCount() {
    call('get_unread_count', 'GET', {}, function (msg) {
      if (!msg || !msg.success) return;
      S.unread = msg.unread || 0; renderBadge();
    });
  }
  function onItemClick(it) {
    if (!it) return;
    var url = safeActionUrl(it.action_url);
    var go = function () { if (url) { window.location.href = url; } else { close(); } };
    if (!it.is_read && it.name) {
      call('mark_read', 'POST', { notification_name: it.name }, function () {
        it.is_read = 1; if (S.unread > 0) S.unread -= 1; renderBadge(); renderList(); go();
      });
    } else { go(); }
  }
  function markAll() {
    call('mark_all_read', 'POST', {}, function () {
      S.items.forEach(function (it) { it.is_read = 1; });
      S.unread = 0; renderBadge(); renderList();
    });
  }

  // ---- open / close / position (anchored to the CURRENT bell) --------------
  function position() {
    if (!bell) return;
    var r = bell.getBoundingClientRect();
    pop.style.top = (r.bottom + 8) + 'px';
    pop.style.right = Math.max(8, (window.innerWidth - r.right)) + 'px';
  }
  function toggle() { S.open ? close() : open(); }
  function open() {
    ensureBadge();
    S.open = true; position(); pop.classList.add('on'); refresh();
    var first = pop.querySelector('.ec-nc-item, #ec-nc-allread');
    if (first && first.focus) { try { first.focus(); } catch (e) {} }
  }
  function close() { S.open = false; pop.classList.remove('on'); }

  // ---- sound (only after a real interaction; respects mute) ----------------
  function ting() {
    if (isMuted() || !S.interacted) return;
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      var ctx = new Ctx();
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.type = 'sine'; o.frequency.value = 880;
      g.gain.setValueAtTime(0.0001, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
      o.connect(g); g.connect(ctx.destination);
      o.start(); o.stop(ctx.currentTime + 0.36);
    } catch (e) {}
  }

  // ---- preferences (client mirror of EC Notification Preference) ----------
  function applyPrefs(pr) { if (!pr) return; for (var k in P) { if (pr[k] != null) P[k] = pr[k]; } }
  function loadPrefs() {
    call('get_preferences', 'GET', {}, function (msg) {
      if (msg && msg.success && msg.preferences) { applyPrefs(msg.preferences); renderPrefsPanel(); }
    });
  }
  function savePrefs(patch, cb) {
    call('set_preferences', 'POST', patch, function (msg) {
      if (msg && msg.success && msg.preferences) { applyPrefs(msg.preferences); }
      renderPrefsPanel(); if (cb) cb(msg);
    });
  }
  function fmtTime(t) { if (!t) return ''; var x = String(t).split(':'); if (x.length < 2) return ''; var h = parseInt(x[0], 10), m = parseInt(x[1], 10); if (isNaN(h) || isNaN(m)) return ''; return ('0' + h).slice(-2) + ':' + ('0' + m).slice(-2); }
  function toMin(t) { if (t == null) return null; var x = String(t).split(':'); if (x.length < 2) return null; var h = parseInt(x[0], 10), m = parseInt(x[1], 10); return (isNaN(h) || isNaN(m)) ? null : h * 60 + m; }
  // quiet hours, mirrors server logic incl. midnight crossing (start > end).
  function inQuiet() {
    if (!P.quiet_hours_enabled) return false;
    var sm = toMin(P.quiet_hours_start), em = toMin(P.quiet_hours_end);
    if (sm == null || em == null || sm === em) return false;
    var d = new Date(), n = d.getHours() * 60 + d.getMinutes();
    return sm < em ? (n >= sm && n < em) : (n >= sm || n < em);
  }

  // ---- per-event dedupe (persisted so reload/reconnect never re-alerts) ----
  function loadSeen() {
    try { var a = JSON.parse(window.localStorage.getItem(SEEN_KEY) || '[]'); if (a && a.length) { a.forEach(function (id) { if (id && !seen[id]) { seen[id] = true; seenOrder.push(id); } }); } } catch (e) {}
  }
  function persistSeen() { try { window.localStorage.setItem(SEEN_KEY, JSON.stringify(seenOrder.slice(-200))); } catch (e) {} }
  function markSeen(id) {
    if (!id) return false;            // no id -> cannot dedupe -> treat as not-fresh (no alert)
    if (seen[id]) return false;
    seen[id] = true; seenOrder.push(id);
    if (seenOrder.length > 500) { delete seen[seenOrder.shift()]; }
    persistSeen(); return true;
  }

  // ---- toast (corner, max 3, plain text, click -> action_url) --------------
  function ensureToastRoot() { var r = document.getElementById('ec-nc-toasts'); if (!r) { r = document.createElement('div'); r.id = 'ec-nc-toasts'; document.body.appendChild(r); } return r; }
  function pickTitle(d) { return toPlainText(d.title || (d.item && d.item.subject) || 'Thông báo'); }
  function pickMsg(d) { return toPlainText(d.message || (d.item && d.item.message) || ''); }
  function pickUrl(d) { return safeActionUrl(d.action_url || (d.item && d.item.action_url) || ''); }
  function dismissToast(el) {
    if (!el) return; var i = toasts.indexOf(el); if (i >= 0) toasts.splice(i, 1);
    if (el._timer) clearTimeout(el._timer); el.classList.remove('on');
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 250);
  }
  function showToast(d) {
    var root = ensureToastRoot();
    var sev = d.severity || 'info';
    var el = document.createElement('div');
    el.className = 'ec-nc-toast ec-nc-toast--' + sev;
    el.setAttribute('role', 'status');
    var ttl = document.createElement('div'); ttl.className = 'ec-nc-toast-ttl'; ttl.textContent = pickTitle(d); el.appendChild(ttl);
    var bt = pickMsg(d); if (bt) { var bd = document.createElement('div'); bd.className = 'ec-nc-toast-msg'; bd.textContent = bt; el.appendChild(bd); }
    var mt = document.createElement('div'); mt.className = 'ec-nc-toast-meta'; mt.textContent = ago(d.created_at) || 'vừa xong'; el.appendChild(mt);
    var x = document.createElement('button'); x.className = 'ec-nc-toast-x'; x.type = 'button'; x.setAttribute('aria-label', 'Đóng'); x.textContent = '\u00d7';
    x.addEventListener('click', function (ev) { ev.stopPropagation(); dismissToast(el); });
    el.appendChild(x);
    var url = pickUrl(d);
    if (url) { el.style.cursor = 'pointer'; el.addEventListener('click', function () { window.location.href = url; }); }
    root.appendChild(el); toasts.push(el);
    while (toasts.length > TOAST_MAX) { dismissToast(toasts[0]); }
    window.requestAnimationFrame ? window.requestAnimationFrame(function () { el.classList.add('on'); }) : el.classList.add('on');
    var life = (sev === 'urgent' || sev === 'action_required') ? 15000 : 8000;
    el._timer = setTimeout(function () { dismissToast(el); }, life);
  }

  // ---- desktop (Web Notification API; opt-in; background-only except urgent) -
  function desktopSupported() { return 'Notification' in window; }
  function desktopAllowed() { return desktopSupported() && window.Notification.permission === 'granted' && !!P.desktop_enabled; }
  function requestDesktopPermission(cb) {
    if (!desktopSupported()) { if (cb) cb(false); return; }
    try {
      var p2 = window.Notification.requestPermission(function (perm) { onPerm(perm); });
      if (p2 && p2.then) { p2.then(onPerm).catch(function () { if (cb) cb(false); }); }
    } catch (e) { if (cb) cb(false); }
    function onPerm(perm) { var ok = perm === 'granted'; if (ok) { savePrefs({ desktop_enabled: 1 }); } if (cb) cb(ok); }
  }
  function showDesktop(d) {
    var sev = d.severity || 'info';
    if (!document.hidden && sev !== 'urgent') return;   // foreground -> toast handles it (except urgent)
    if (!desktopAllowed()) return;                       // denied/unsupported -> fallback already shown (toast/inbox)
    try {
      var url = pickUrl(d);
      var n = new window.Notification(pickTitle(d), { body: pickMsg(d), tag: d.event_id || (d.item && d.item.name) || undefined });
      n.onclick = function () { try { window.focus(); } catch (e) {} if (url) { window.location.href = url; } n.close(); };
    } catch (e) {}
  }

  // ---- sound gating (prefs + quiet hours + minimum severity) ---------------
  function shouldSound(d) {
    if (isMuted() || !P.sound_enabled || !S.interacted) return false;
    var sev = d.severity || 'info';
    if (sev === 'urgent') return true;                  // urgent bypasses quiet/min
    if (inQuiet()) return false;
    if (SEV_RANK[sev] < SEV_RANK[P.minimum_severity || 'info']) return false;
    return true;
  }

  // ---- preferences panel UI -----------------------------------------------
  function buildPrefsPanel() {
    var panel = pop.querySelector('#ec-nc-prefs'); if (!panel) return; panel.innerHTML = '';
    function row(label) { var r = document.createElement('label'); r.className = 'ec-nc-prow'; var sp = document.createElement('span'); sp.textContent = label; r.appendChild(sp); return r; }
    function cbx() { var c = document.createElement('input'); c.type = 'checkbox'; return c; }
    var rs = row('Âm thanh'); prefCtl.sound = cbx(); rs.appendChild(prefCtl.sound); panel.appendChild(rs);
    prefCtl.sound.addEventListener('change', function () { savePrefs({ sound_enabled: prefCtl.sound.checked ? 1 : 0 }); });
    var rd = row('Thông báo trên máy tính'); prefCtl.desktop = cbx(); rd.appendChild(prefCtl.desktop); panel.appendChild(rd);
    prefCtl.desktop.addEventListener('change', function () {
      if (prefCtl.desktop.checked) { requestDesktopPermission(function (ok) { if (!ok) prefCtl.desktop.checked = false; renderPrefsPanel(); }); }
      else { savePrefs({ desktop_enabled: 0 }); }
    });
    var db = document.createElement('button'); db.type = 'button'; db.className = 'ec-nc-prefbtn'; db.id = 'ec-pref-desktop-btn'; db.textContent = 'Bật thông báo trên máy tính';
    db.addEventListener('click', function () { requestDesktopPermission(function () { renderPrefsPanel(); }); });
    panel.appendChild(db);
    var rt = row('Microsoft Teams'); prefCtl.teams = cbx(); rt.appendChild(prefCtl.teams); panel.appendChild(rt);
    prefCtl.teams.addEventListener('change', function () { savePrefs({ teams_enabled: prefCtl.teams.checked ? 1 : 0 }); });
    var rq = row('Giờ im lặng'); prefCtl.quiet = cbx(); rq.appendChild(prefCtl.quiet); panel.appendChild(rq);
    prefCtl.quiet.addEventListener('change', function () { savePrefs({ quiet_hours_enabled: prefCtl.quiet.checked ? 1 : 0 }); });
    var rqt = document.createElement('div'); rqt.className = 'ec-nc-prow';
    prefCtl.qs = document.createElement('input'); prefCtl.qs.type = 'time';
    prefCtl.qe = document.createElement('input'); prefCtl.qe.type = 'time';
    var ar = document.createElement('span'); ar.textContent = '\u2192';
    rqt.appendChild(prefCtl.qs); rqt.appendChild(ar); rqt.appendChild(prefCtl.qe); panel.appendChild(rqt);
    function saveQuiet() { savePrefs({ quiet_hours_start: prefCtl.qs.value || '', quiet_hours_end: prefCtl.qe.value || '' }); }
    prefCtl.qs.addEventListener('change', saveQuiet); prefCtl.qe.addEventListener('change', saveQuiet);
    var rm = row('Mức tối thiểu'); prefCtl.sev = document.createElement('select');
    [['info', 'Tất cả'], ['action_required', 'Cần xử lý'], ['urgent', 'Khẩn cấp']].forEach(function (o) { var op = document.createElement('option'); op.value = o[0]; op.textContent = o[1]; prefCtl.sev.appendChild(op); });
    rm.appendChild(prefCtl.sev); panel.appendChild(rm);
    prefCtl.sev.addEventListener('change', function () { savePrefs({ minimum_severity: prefCtl.sev.value }); });
  }
  function renderPrefsPanel() {
    if (!prefCtl.sound) return;
    prefCtl.sound.checked = !!P.sound_enabled;
    prefCtl.teams.checked = !!P.teams_enabled;
    prefCtl.quiet.checked = !!P.quiet_hours_enabled;
    prefCtl.sev.value = P.minimum_severity || 'info';
    prefCtl.qs.value = fmtTime(P.quiet_hours_start);
    prefCtl.qe.value = fmtTime(P.quiet_hours_end);
    var sup = desktopSupported(), granted = sup && window.Notification.permission === 'granted';
    prefCtl.desktop.checked = !!P.desktop_enabled && granted;
    prefCtl.desktop.disabled = !sup;
    var db = pop.querySelector('#ec-pref-desktop-btn');
    if (db) db.style.display = (sup && !granted) ? 'block' : 'none';
  }
  function wireRealtime() {
    if (window.frappe && window.frappe.realtime && typeof window.frappe.realtime.on === 'function') {
      window.frappe.realtime.on('ec_notification', function (data) {
        data = data || {};
        // badge + list reflect the latest state (insert deduped by Notification Log name)
        if (typeof data.unread === 'number') S.unread = data.unread;
        else if (typeof data.unread_count === 'number') S.unread = data.unread_count;
        var item = data.item;
        if (item && item.name) {
          var dup = false; for (var i = 0; i < S.items.length; i++) { if (S.items[i].name === item.name) { dup = true; break; } }
          if (!dup) S.items.unshift(item);
        }
        renderBadge(); if (S.open) renderList();
        // toast / sound / desktop fire ONCE per event id; never on reload/reconnect/poll
        var id = data.event_id || data.notification_name || (item && item.name);
        if (!markSeen(id)) return;
        showToast(data);
        if (shouldSound(data)) ting();
        showDesktop(data);
      });
      return true;
    }
    return false;
  }

  // ---- THE click interceptor: ONE document-level CAPTURE-phase delegated handler ----
  // Resilient to header (re)render; defeats any legacy handler attached before OR after
  // this asset, on the bell or delegated, because capture runs first at document.
  function onNotificationBellClick(ev) {
    var target = getNotificationBellTarget(ev.target);
    if (!target) return;                              // not a header bell -> ignore
    var isAnchor = target.tagName === 'A' && /notification-log/.test(target.getAttribute('href') || '');
    // PLAIN left click only is "hijacked". Ctrl/Cmd/Shift/Alt + any non-primary button:
    var plain = !(ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey);
    // Anchor + modifier/middle -> keep native /app/notification-log navigation; do not touch.
    if (isAnchor && !plain) { return; }
    // Otherwise WE own this click: plain-left on anchor/button, OR any click on a
    // href-less button (no native target). Suppress ANY legacy bell handler.
    ev.preventDefault();
    ev.stopPropagation();
    if (ev.stopImmediatePropagation) { ev.stopImmediatePropagation(); }
    if (plain) { bell = target; S.interacted = true; toggle(); }
  }

  // ---- MutationObserver: ONLY (re)mounts badge when the header (re)renders ---
  function startObserver() {
    if (mo || !window.MutationObserver) return;
    mo = new window.MutationObserver(function () {
      var b = findBell();
      if (b && (b !== bell || !b.querySelector('.ec-nc-badge'))) { bell = b; mountBadge(); }
    });
    mo.observe(document.body, { childList: true, subtree: true });
    // cleanup: never leak the observer past page life
    window.addEventListener('pagehide', function () { if (mo) { mo.disconnect(); mo = null; } }, { once: true });
  }

  // first real interaction unlocks sound (browser autoplay policy)
  ['click', 'keydown'].forEach(function (e) {
    window.addEventListener(e, function () { S.interacted = true; }, { once: true });
  });

  function init() {
    injectCss();
    buildPop();
    // single document-level CAPTURE handler -- the authoritative click interceptor
    document.addEventListener('click', onNotificationBellClick, true);
    // ---- robust dismissal: only a REAL outside pointer or Escape closes ----------
    // "inside" = bell OR dropdown, detected via composedPath() (preferred) then
    // contains() fallback. Scrollbar drag, wheel/scroll, pointer-move, text selection
    // and non-navigating inner clicks must NOT close. We never use blur or focus-out events, and
    // we never close on scroll -- scroll only RE-ANCHORS the fixed dropdown.
    function eventIsInside(ev) {
      var path = (ev.composedPath && ev.composedPath()) || null;
      if (path) { for (var i = 0; i < path.length; i++) { if (path[i] === pop || path[i] === bell) return true; } }
      var t = ev.target;
      return !!((pop && pop.contains(t)) || (bell && bell.contains(t)));
    }
    document.addEventListener('pointerdown', function (ev) {
      if (S.open && !eventIsInside(ev)) close();
    }, true);
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && S.open) { close(); if (bell && bell.focus) bell.focus(); } });
    // keep the position:fixed dropdown anchored on scroll/resize WITHOUT closing it
    // (closing on scroll was the bug: inner-list scroll dismissed the dropdown).
    window.addEventListener('resize', function () { if (S.open) position(); });
    window.addEventListener('scroll', function () { if (S.open) position(); }, true);
    // mount badge now if the bell already exists; the observer handles later renders
    bell = findBell();
    if (bell) { mountBadge(); } else { console.warn('[ec-notification-center] bell not present yet; observer will mount it'); }
    startObserver();
    loadSeen();
    loadPrefs();
    refreshCount();
    if (!wireRealtime()) { setInterval(refreshCount, POLL_MS); }
    console.log('[ec-notification-center] installed (global delegated capture loader)');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
