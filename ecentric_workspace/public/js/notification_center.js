// Copyright (c) 2026, eCentric and contributors
// Notification Center (app-owned asset, ERP-wide GLOBAL loader).
//
// Loaded on EVERY website-rendered eCentric page via the `web_include_js` hook
// (hooks.py) -- NOT per-page, NOT via a DB patch per page, and NEVER on Frappe Desk
// (/app/*). The homepage additionally still carries the legacy per-page <script>
// loader; the single-install guard below makes that a harmless no-op (no duplicate
// listener / badge / dropdown).
//
// There is exactly ONE bell on every shell page: the native eCentric header bell
//   .topbar-actions a.icon-btn[href="/app/notification-log"]  (svg #i-bell + .dot)
// This asset does NOT render its own bell. It ADOPTS the native bell (stripping any
// legacy "feature-in-development" handler), shows a live unread badge on it, and
// opens a system-styled dropdown whose items use the server-built action_url
// (resolver lives in notification_center.resolvers).
//
// All API calls go through frappe.call with the CORRECT http type (GET vs POST) to
// match the backend @frappe.whitelist(methods=[...]). subject/message/source escaped.
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

  // ---- locate the existing native bell (no new bell is ever created) -----
  function findBell() {
    var b = document.querySelector('.topbar-actions a.icon-btn[href*="notification-log"]');
    if (b) return b;
    // fallback: a topbar icon-btn whose svg references the #i-bell symbol
    var btns = document.querySelectorAll('.topbar-actions a.icon-btn, .topbar-actions button.icon-btn');
    for (var i = 0; i < btns.length; i++) {
      var u = btns[i].querySelector('use');
      var href = u ? (u.getAttribute('href') || u.getAttribute('xlink:href') || '') : '';
      if (/i-bell/.test(href)) return btns[i];
    }
    return null;
  }

  // Adopt the native bell: replace it with a clean clone so ANY legacy handler bound
  // to it (inline onclick="...feature-in-development..." or addEventListener) is
  // dropped. The clone keeps href/markup so Ctrl/Cmd/middle-click still open
  // /app/notification-log natively. We then own the (single) click handler.
  function adoptBell(orig) {
    var clone = orig.cloneNode(true);
    clone.removeAttribute('onclick');
    clone.setAttribute('data-ec-nc', '1');
    if (orig.parentNode) { orig.parentNode.replaceChild(clone, orig); return clone; }
    return orig;
  }

  var S = { items: [], unread: 0, open: false, interacted: false };
  var bell, badgeEl, pop, listEl;

  // ---- styles: gathered in classes, reusing the /home design tokens --------
  function injectCss() {
    if (document.getElementById('ec-nc-css')) return;
    var st = document.createElement('style');
    st.id = 'ec-nc-css';
    st.textContent =
      // unread count badge anchored to the bell's top-right corner (absolute -> no
      // header shift). 1-9 = ~16px circle; 9+ = ~21px pill (.ec-nc-badge--pill);
      // 9-10px semibold; ~2px white ring; existing --pink token; hidden when 0.
      '.ec-nc-badge{position:absolute;top:-4px;right:-4px;min-width:16px;height:16px;padding:0;border-radius:8px;background:var(--pink,#EF7CAF);color:#fff;font-size:9.5px;font-weight:600;line-height:16px;text-align:center;border:2px solid #fff;display:none;pointer-events:none;box-sizing:border-box;font-family:inherit;}' +
      '.ec-nc-badge.on{display:block;}' +
      '.ec-nc-badge--pill{min-width:21px;padding:0 4px;}' +
      // dropdown/popover: white card, light gray border, soft shadow, system radius
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
      '.ec-nc-subj{font-size:13px;font-weight:600;color:var(--gray-900,#111827);line-height:1.35;}' +
      '.ec-nc-msg{font-size:11.5px;color:var(--gray-600,#6b7280);line-height:1.4;margin-top:2px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}' +
      '.ec-nc-empty{padding:30px 16px;text-align:center;color:var(--gray-500,#6b7280);font-size:13px;}' +
      '.ec-nc-ft{display:flex;align-items:stretch;border-top:1px solid var(--gray-100,#f1f2f4);}' +
      '.ec-nc-ft > *{flex:1;text-align:center;padding:10px;font-size:12.5px;font-weight:600;color:var(--navy,#2C3DA6);background:none;border:none;cursor:pointer;text-decoration:none !important;font-family:inherit;}' +
      '.ec-nc-ft > *:hover{background:var(--gray-50,#f7f8fb);}' +
      '.ec-nc-ft .ec-nc-sep{flex:0 0 1px;padding:0;background:var(--gray-100,#f1f2f4);}';
    document.head.appendChild(st);
  }

  // ---- badge mounted onto the native bell (static .dot hidden) -------------
  // Idempotent: remove any prior badge first so a re-render never stacks badges.
  function mountBadge() {
    var dot = bell.querySelector('.dot');
    if (dot) { dot.style.display = 'none'; }      // replace the placeholder dot
    var prev = bell.querySelector('.ec-nc-badge');
    if (prev && prev.parentNode) { prev.parentNode.removeChild(prev); }
    badgeEl = document.createElement('span');
    badgeEl.className = 'ec-nc-badge';
    badgeEl.setAttribute('aria-hidden', 'true');
    bell.appendChild(badgeEl);                    // .icon-btn is position:relative
  }

  function buildPop() {
    // Idempotent: drop any prior dropdown so navigation/re-render never duplicates it.
    var prev = document.getElementById('ec-nc-pop-root');
    if (prev && prev.parentNode) { prev.parentNode.removeChild(prev); }
    pop = document.createElement('div');
    pop.className = 'ec-nc-pop';
    pop.id = 'ec-nc-pop-root';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', 'Thông báo');
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

  // 0 -> fully hidden; 1-9 -> circle; >9 -> '9+' pill (capped, no header shift).
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

  function renderList() {
    if (!listEl) return;
    if (!S.items.length) {
      listEl.innerHTML = '<div class="ec-nc-empty">Chưa có thông báo nào</div>';
      return;
    }
    listEl.innerHTML = S.items.map(function (it, i) {
      // action_url is server-built; the href is NEVER raw subject/message content.
      return '<a class="ec-nc-item' + (it.is_read ? '' : ' unread') + '" data-i="' + i + '"' +
        ' tabindex="0" href="' + esc(it.action_url || '#') + '">' +
        '<div class="ec-nc-r1">' +
          (it.is_read ? '' : '<span class="ec-nc-udot"></span>') +
          '<span class="ec-nc-src">' + esc(it.source_label || '') + '</span>' +
          '<span class="ec-nc-time">' + esc(ago(it.created_at)) + '</span>' +
        '</div>' +
        '<div class="ec-nc-subj">' + esc(it.subject || '') + '</div>' +
        (it.message ? '<div class="ec-nc-msg">' + esc(it.message) + '</div>' : '') +
      '</a>';
    }).join('');
    Array.prototype.forEach.call(listEl.querySelectorAll('.ec-nc-item'), function (a) {
      a.addEventListener('click', function (ev) { ev.preventDefault(); onItemClick(S.items[+a.getAttribute('data-i')]); });
      a.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onItemClick(S.items[+a.getAttribute('data-i')]); }
      });
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
    var go = function () {
      if (it.action_url) { window.location.href = it.action_url; }   // server-built URL only
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

  // ---- open / close / position (anchored to the real bell, no pixel hardcode)
  function position() {
    var r = bell.getBoundingClientRect();
    pop.style.top = (r.bottom + 8) + 'px';
    pop.style.right = Math.max(8, (window.innerWidth - r.right)) + 'px';
  }
  function toggle() { S.open ? close() : open(); }
  function open() {
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

  // first real interaction unlocks sound (browser autoplay policy)
  ['click', 'keydown'].forEach(function (e) {
    window.addEventListener(e, function () { S.interacted = true; }, { once: true });
  });

  function init() {
    var native = findBell();
    if (!native) { console.warn('[ec-notification-center] native header bell not found; no bell rendered'); return; }
    bell = adoptBell(native);   // strips the legacy "feature-in-development" handler
    injectCss();
    mountBadge();
    buildPop();
    bell.addEventListener('click', function (ev) {
      // Only hijack a PLAIN left click. Ctrl/Cmd/Shift/Alt + any non-primary button
      // fall through to the native href (/app/notification-log) -> open-in-new-tab,
      // middle-click and "open in new tab" all keep their native behaviour.
      if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) { return; }
      ev.preventDefault();
      // stop bubbling so any legacy DOCUMENT-level delegated handler (the old
      // "feature-in-development" toast) can never also fire on a plain left-click.
      ev.stopPropagation();
      if (ev.stopImmediatePropagation) { ev.stopImmediatePropagation(); }
      S.interacted = true;
      toggle();
    });
    // dismissal: click outside + Esc; reposition-safe by closing on scroll/resize
    document.addEventListener('click', function (ev) {
      if (S.open && !pop.contains(ev.target) && !bell.contains(ev.target)) close();
    });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && S.open) { close(); bell.focus && bell.focus(); } });
    window.addEventListener('resize', function () { if (S.open) close(); });
    window.addEventListener('scroll', function () { if (S.open) close(); }, true);
    refreshCount();
    if (!wireRealtime()) { setInterval(refreshCount, POLL_MS); }
    console.log('[ec-notification-center] installed (global loader, reuses native bell)');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
