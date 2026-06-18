// Copyright (c) 2026, eCentric and contributors
// Notification Center bell (app-owned asset, ERP-wide foundation).
//
// Loaded by:
//   <script id="ec-notification-center"
//           src="/assets/ecentric_workspace/js/notification_center.js" defer></script>
// injected into the homepage Web Page by
//   ecentric_workspace.notification_center.patches.p001_homepage_notification_bell.
//
// Contract:
//   * All API calls go through frappe.call (auth + CSRF + JSON handled by Frappe).
//   * NO route building here — item.action_url is the single source of truth
//     (resolver lives in ecentric_workspace.notification_center.resolvers).
//   * subject / message are ALWAYS escaped via esc() before insertion (XSS).
//   * Sound only plays after a real user interaction (browser autoplay policy);
//     a mute toggle is part of the design and persists in localStorage.
//   * Realtime is opportunistic: if frappe.realtime exists we subscribe to
//     'ec_notification'; otherwise we poll the unread count.
(function () {
  'use strict';
  if (window._ecNotifCenterInstalled) { return; }
  window._ecNotifCenterInstalled = true;

  var LIST_LIMIT = 20;
  var POLL_MS = 60000;
  var MUTE_KEY = 'ec_notif_muted';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
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

  // ---- state -------------------------------------------------------------
  var S = { items: [], unread: 0, open: false, interacted: false };

  // ---- styles ------------------------------------------------------------
  function injectCss() {
    if (document.getElementById('ec-nc-css')) return;
    var st = document.createElement('style');
    st.id = 'ec-nc-css';
    st.textContent =
      '#ec-nc-bell{position:fixed;top:14px;right:18px;z-index:9998;width:40px;height:40px;border-radius:50%;background:#fff;border:1px solid #e5e7eb;box-shadow:0 1px 4px rgba(0,0,0,.12);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px;color:#374151;}' +
      '#ec-nc-bell:hover{border-color:#2C3DA6;}' +
      '#ec-nc-badge{position:absolute;top:-4px;right:-4px;min-width:18px;height:18px;padding:0 4px;border-radius:9px;background:#dc2626;color:#fff;font-size:11px;font-weight:700;line-height:18px;text-align:center;display:none;}' +
      '#ec-nc-badge.on{display:block;}' +
      '#ec-nc-pop{position:fixed;top:60px;right:18px;z-index:9999;width:360px;max-width:92vw;max-height:72vh;background:#fff;border:1px solid #e5e7eb;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.18);display:none;flex-direction:column;overflow:hidden;}' +
      '#ec-nc-pop.on{display:flex;}' +
      '.ec-nc-head{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid #eef0f3;}' +
      '.ec-nc-head h4{margin:0;font-size:13.5px;font-weight:700;color:#111827;flex:1;}' +
      '.ec-nc-act{font-size:11.5px;color:#2C3DA6;font-weight:600;cursor:pointer;background:none;border:none;padding:2px 4px;}' +
      '.ec-nc-list{overflow-y:auto;}' +
      '.ec-nc-item{display:block;padding:10px 12px;border-bottom:1px solid #f2f3f5;cursor:pointer;text-decoration:none !important;color:inherit;background:#fff;}' +
      '.ec-nc-item:hover{background:#f7f8fb;}' +
      '.ec-nc-item.unread{background:#eef3ff;}' +
      '.ec-nc-item.unread:hover{background:#e3ecff;}' +
      '.ec-nc-row1{display:flex;align-items:center;gap:8px;margin-bottom:3px;}' +
      '.ec-nc-src{padding:1px 7px;border-radius:8px;background:#eef0fb;color:#2C3DA6;font-weight:600;font-size:10px;letter-spacing:.4px;}' +
      '.ec-nc-dot{width:8px;height:8px;border-radius:50%;background:#2C3DA6;}' +
      '.ec-nc-time{margin-left:auto;color:#6b7280;font-size:11px;}' +
      '.ec-nc-subj{font-size:13px;font-weight:600;color:#111827;line-height:1.35;}' +
      '.ec-nc-msg{font-size:11.5px;color:#6b7280;line-height:1.4;margin-top:2px;white-space:normal;}' +
      '.ec-nc-empty{padding:28px 16px;text-align:center;color:#6b7280;font-size:13px;}';
    document.head.appendChild(st);
  }

  // ---- DOM ---------------------------------------------------------------
  var bellEl, badgeEl, popEl, listEl;

  function build() {
    injectCss();
    bellEl = document.createElement('button');
    bellEl.id = 'ec-nc-bell';
    bellEl.type = 'button';
    bellEl.setAttribute('aria-label', 'Thông báo');
    bellEl.innerHTML = '\u{1F514}<span id="ec-nc-badge"></span>';
    badgeEl = bellEl.querySelector('#ec-nc-badge');

    popEl = document.createElement('div');
    popEl.id = 'ec-nc-pop';
    popEl.innerHTML =
      '<div class="ec-nc-head">' +
        '<h4>Thông báo</h4>' +
        '<button class="ec-nc-act" id="ec-nc-mute" type="button"></button>' +
        '<button class="ec-nc-act" id="ec-nc-allread" type="button">Đánh dấu tất cả đã đọc</button>' +
      '</div>' +
      '<div class="ec-nc-list" id="ec-nc-list"></div>';
    listEl = popEl.querySelector('#ec-nc-list');

    document.body.appendChild(bellEl);
    document.body.appendChild(popEl);

    bellEl.addEventListener('click', function () { S.interacted = true; toggle(); });
    popEl.querySelector('#ec-nc-allread').addEventListener('click', markAll);
    popEl.querySelector('#ec-nc-mute').addEventListener('click', function () {
      setMuted(!isMuted()); renderMute();
    });
    document.addEventListener('click', function (ev) {
      if (S.open && !popEl.contains(ev.target) && !bellEl.contains(ev.target)) close();
    });
    renderMute();
  }

  function renderMute() {
    var b = popEl && popEl.querySelector('#ec-nc-mute');
    if (b) b.textContent = isMuted() ? '\u{1F507} Bật âm' : '\u{1F514} Tắt âm';
  }

  function renderBadge() {
    if (!badgeEl) return;
    if (S.unread > 0) { badgeEl.textContent = S.unread > 99 ? '99+' : S.unread; badgeEl.classList.add('on'); }
    else { badgeEl.classList.remove('on'); }
  }

  function renderList() {
    if (!listEl) return;
    if (!S.items.length) {
      listEl.innerHTML = '<div class="ec-nc-empty">Chưa có thông báo nào</div>';
      return;
    }
    listEl.innerHTML = S.items.map(function (it, i) {
      // action_url comes from the server resolver. NO route building here.
      return '<a class="ec-nc-item' + (it.is_read ? '' : ' unread') + '" data-i="' + i + '"' +
        ' href="' + esc(it.action_url || '#') + '">' +
        '<div class="ec-nc-row1">' +
          (it.is_read ? '' : '<span class="ec-nc-dot"></span>') +
          '<span class="ec-nc-src">' + esc(it.source_label || '') + '</span>' +
          '<span class="ec-nc-time">' + esc(ago(it.created_at)) + '</span>' +
        '</div>' +
        '<div class="ec-nc-subj">' + esc(it.subject || '') + '</div>' +
        (it.message ? '<div class="ec-nc-msg">' + esc(it.message) + '</div>' : '') +
      '</a>';
    }).join('');
    Array.prototype.forEach.call(listEl.querySelectorAll('.ec-nc-item'), function (a) {
      a.addEventListener('click', function (ev) {
        ev.preventDefault();
        onItemClick(S.items[+a.getAttribute('data-i')]);
      });
    });
  }

  // ---- API ---------------------------------------------------------------
  // httpType MUST match the backend @frappe.whitelist(methods=[...]) — calling a GET
  // endpoint with POST (frappe.call's default) reproduces the Action Center 403.
  //   get_notifications / get_unread_count -> 'GET'
  //   mark_read / mark_all_read            -> 'POST'
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
    var go = function () {
      var url = it.action_url;
      if (url) { window.location.href = url; }       // server-built URL only
      else { close(); }
    };
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

  // ---- open/close + sound ------------------------------------------------
  function toggle() { S.open ? close() : open(); }
  function open() { S.open = true; popEl.classList.add('on'); refresh(); }
  function close() { S.open = false; popEl.classList.remove('on'); }

  function ting() {
    if (isMuted() || !S.interacted) return;   // respect mute + autoplay policy
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

  // ---- realtime / poll ---------------------------------------------------
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

  // mark first real interaction (needed to allow sound later)
  ['click', 'keydown'].forEach(function (e) {
    window.addEventListener(e, function () { S.interacted = true; }, { once: true });
  });

  function init() {
    build();
    refreshCount();
    if (!wireRealtime()) {
      setInterval(refreshCount, POLL_MS);     // fallback when realtime is unavailable
    }
    console.log('[ec-notification-center] installed (asset)');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
