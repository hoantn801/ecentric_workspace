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
      '.ec-nc-ft .ec-nc-sep{flex:0 0 1px;padding:0;background:var(--gray-100,#f1f2f4);}';
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
        '<button class="ec-nc-mute" id="ec-nc-mute" type="button"></button>' +
      '</div>' +
      '<div class="ec-nc-list" id="ec-nc-list"></div>' +
      '<div class="ec-nc-ft">' +
        '<button id="ec-nc-allread" type="button">Đánh dấu tất cả đã đọc</button>' +
        '<span class="ec-nc-sep"></span>' +
        '<a id="ec-nc-viewall" href="/app/notification-log">Xem tất cả thông báo</a>' +
      '</div>';
    document.body.appendChild(pop);
    listEl = pop.querySelector('#ec-nc-list');
    pop.querySelector('#ec-nc-allread').addEventListener('click', markAll);
    pop.querySelector('#ec-nc-mute').addEventListener('click', function () { setMuted(!isMuted()); renderMute(); });
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
  function wireRealtime() {
    if (window.frappe && window.frappe.realtime && typeof window.frappe.realtime.on === 'function') {
      window.frappe.realtime.on('ec_notification', function (data) {
        if (data && typeof data.unread === 'number') S.unread = data.unread;
        if (data && data.item) S.items.unshift(data.item);
        renderBadge(); if (S.open) renderList(); ting();
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
    refreshCount();
    if (!wireRealtime()) { setInterval(refreshCount, POLL_MS); }
    console.log('[ec-notification-center] installed (global delegated capture loader)');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
