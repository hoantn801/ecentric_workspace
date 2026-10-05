// Copyright (c) 2026, eCentric and contributors
// ec_chat.js - khay Tin nhan tren thanh tren ERP (mockup C, PO chot 05/10/2026).
//
// SO HUU: hanh vi cua o [data-ec-shell-chat-slot="1"] ma shell ve (fallback.render_chat_slot /
// ec_shell.js renderHeaderRight). Shell chi ve markup; file nay lo huy hieu + khay.
//   * Huy hieu: tong tin chua doc cua NGUOI NAY tren Raven (chat/api.get_unread_total).
//   * Bam o (man >= 641px): mo khay 380px duoi o, liet ke cuoc tro chuyen gan nhat
//     (chat/api.get_inbox). Man hep hoac Ctrl/Cmd-click: de lien ket di thang /chat.
//   * Moi dong la lien ket /chat?c=<kenh> -> trang A mo dung kenh trong Raven.
//   * Goc phai duoi KHONG dung: cho cua eC Mate.
// Du lieu: chi qua API cua app nay, doc DUOI PHIEN; Raven tu loc kenh rieng / DM.
// KHONG MutationObserver: shell phat su kien 'ec-shell:header-rendered' moi lan ve lai.
(function () {
  'use strict';
  if (window._ecChatInstalled) return;
  window._ecChatInstalled = true;

  var UNREAD_URL = '/api/method/ecentric_workspace.chat.api.get_unread_total';
  var INBOX_URL = '/api/method/ecentric_workspace.chat.api.get_inbox';
  // 2 phut khi tab dang mo: 82 nguoi x 1 lan / 2 phut. Tin moi den ngay nho realtime cua Raven
  // ('raven:unread_channel_count_updated'); vong hoi chi la luoi an toan khi socket chua noi.
  var POLL_MS = 120000;
  var NARROW_PX = 640;
  var SLOT = '[data-ec-shell-chat-slot="1"]';
  // o Tin nhan tren thanh tren + huy hieu muc "Chat noi bo" o menu trai (badge_source
  // 'chat.unread' trong shell/nav.py; shell bo qua khoa nay, file nay to no).
  var BADGE = '[data-ec-shell-chat-badge="1"], [data-ec-shell-badge="chat.unread"]';

  var S = { total: null, open: false, panel: null, filter: 'unread', cache: {}, loading: false, timer: null };

  // ---------------------------------------------------------------- pure --
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function badgeText(n) {
    n = Number(n) || 0;
    return n <= 0 ? '' : (n > 9 ? '9+' : String(n));
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  // 'YYYY-MM-DD HH:MM:SS(.f)' (gio site) -> nhan ngan. `now` truyen vao de test tat dinh.
  function timeLabel(ts, now) {
    var m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(String(ts || ''));
    if (!m) return '';
    now = now || new Date();
    var today = now.getFullYear() + '-' + pad2(now.getMonth() + 1) + '-' + pad2(now.getDate());
    var y = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
    var yest = y.getFullYear() + '-' + pad2(y.getMonth() + 1) + '-' + pad2(y.getDate());
    var day = m[1] + '-' + m[2] + '-' + m[3];
    if (day === today) return m[4] + ':' + m[5];
    if (day === yest) return 'Hôm qua';
    return m[3] + '/' + m[2];
  }

  var ICON = {
    lock: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>',
    hash: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/></svg>'
  };

  function avatarHtml(it) {
    if (it.kind === 'dm') {
      if (it.avatar) return '<img class="ec-chat-av" src="' + esc(it.avatar) + '" alt="" loading="lazy">';
      return '<span class="ec-chat-av ec-chat-av-txt" aria-hidden="true">' + esc(it.initials) + '</span>';
    }
    return '<span class="ec-chat-av ec-chat-av-ch" aria-hidden="true">' + (it.is_private ? ICON.lock : ICON.hash) + '</span>';
  }

  function rowHtml(it, now) {
    var unread = Number(it.unread) || 0;
    return '<a class="ec-chat-row' + (unread ? ' ec-chat-row-unread' : '') + '" href="' + esc(it.href) + '">' +
      avatarHtml(it) +
      '<span class="ec-chat-row-main">' +
        '<span class="ec-chat-row-top">' +
          '<span class="ec-chat-row-title">' + esc(it.title) + '</span>' +
          '<span class="ec-chat-row-time">' + esc(timeLabel(it.last_at, now)) + '</span>' +
        '</span>' +
        '<span class="ec-chat-row-prev">' + (esc(it.preview) || '&nbsp;') + '</span>' +
      '</span>' +
      (unread ? '<span class="ec-chat-count" aria-label="' + unread + ' tin chưa đọc">' + esc(badgeText(unread)) + '</span>' : '') +
    '</a>';
  }

  // Than khay theo trang thai. `st` = {loading, error, data}. Ham THUAN (test duoc).
  function bodyHtml(st, filter, now) {
    if (st.loading) {
      return '<div class="ec-chat-sk" aria-hidden="true"><i></i><i></i><i></i></div>' +
             '<p class="ec-chat-sr" role="status">Đang tải tin nhắn…</p>';
    }
    if (st.error) {
      return '<div class="ec-chat-empty" role="alert"><p>' + esc(st.error) + '</p>' +
             '<button type="button" class="ec-chat-btn" data-ec-chat-retry="1">Thử lại</button></div>';
    }
    var d = st.data || {};
    if (d.state && d.state !== 'ok') {
      return '<div class="ec-chat-empty"><p>' + esc(d.message || '') + '</p></div>';
    }
    var items = d.items || [];
    if (!items.length) {
      return '<div class="ec-chat-empty"><p>' +
             (filter === 'unread' ? 'Không có tin chưa đọc.' : 'Chưa có cuộc trò chuyện nào.') + '</p></div>';
    }
    var h = '<div class="ec-chat-list">';
    for (var i = 0; i < items.length; i++) h += rowHtml(items[i], now);
    return h + '</div>';
  }

  function panelHtml(st, filter, now) {
    function chip(key, label) {
      return '<button type="button" class="ec-chat-chip" data-ec-chat-filter="' + key + '" aria-pressed="' +
             (filter === key ? 'true' : 'false') + '">' + label + '</button>';
    }
    return '<div class="ec-chat-head">' +
             '<h2 class="ec-chat-h" id="ec-chat-h">Tin nhắn</h2>' +
             '<div class="ec-chat-chips">' + chip('unread', 'Chưa đọc') + chip('all', 'Tất cả') + '</div>' +
           '</div>' +
           '<div class="ec-chat-body" data-ec-chat-body="1">' + bodyHtml(st, filter, now) + '</div>' +
           '<a class="ec-chat-foot" href="/chat">Mở Chat nội bộ</a>';
  }

  // ------------------------------------------------------------- network --
  function getJson(url) {
    return fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        var m = res.body && res.body.message;
        if (!res.ok || !m || m.success !== true) {
          throw new Error((m && m.message) || 'Không tải được tin nhắn. Thử lại sau ít phút.');
        }
        return m.data || {};
      });
  }

  // ---------------------------------------------------------------- badge --
  function paintBadge() {
    var nodes = document.querySelectorAll(BADGE);
    var txt = badgeText(S.total);
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = txt;
      nodes[i].hidden = !txt;
    }
    var slot = document.querySelector(SLOT);
    if (slot) slot.setAttribute('aria-label', txt ? ('Tin nhắn, ' + S.total + ' chưa đọc') : 'Tin nhắn');
  }

  function refreshTotal() {
    if (!document.querySelector(SLOT)) return Promise.resolve();
    return getJson(UNREAD_URL)
      .then(function (d) { S.total = (d.state === 'ok') ? (Number(d.total) || 0) : 0; paintBadge(); })
      .catch(function () { /* giu so cu; huy hieu la phu tro, khong bao loi o day */ });
  }

  // ----------------------------------------------------------------- panel --
  function slotEl() { return document.querySelector(SLOT); }

  function place() {
    var slot = slotEl();
    if (!slot || !S.panel) return;
    var r = slot.getBoundingClientRect();
    var w = Math.min(380, window.innerWidth - 16);
    var left = Math.max(8, Math.min(r.right - w, window.innerWidth - w - 8));
    S.panel.style.top = Math.round(r.bottom + 6) + 'px';
    S.panel.style.left = Math.round(left) + 'px';
    S.panel.style.width = w + 'px';
  }

  function paintPanel() {
    if (!S.panel) return;
    var st = S.cache[S.filter] || { loading: true };
    S.panel.innerHTML = panelHtml(st, S.filter, new Date());
  }

  function loadFilter(filter, force) {
    if (!force && S.cache[filter] && !S.cache[filter].error) { paintPanel(); return; }
    S.cache[filter] = { loading: true };
    paintPanel();
    getJson(INBOX_URL + (filter === 'unread' ? '?unread_only=1' : ''))
      .then(function (d) {
        S.cache[filter] = { data: d };
        if (typeof d.total_unread === 'number') { S.total = d.total_unread; paintBadge(); }
      })
      .catch(function (e) { S.cache[filter] = { error: (e && e.message) || 'Không tải được tin nhắn.' }; })
      .then(function () { if (S.filter === filter) paintPanel(); });
  }

  function openPanel() {
    var slot = slotEl();
    if (!slot) return;
    closePanel();
    S.open = true;
    S.cache = {};                                    // moi lan mo: so lieu moi
    S.filter = (S.total > 0) ? 'unread' : 'all';
    var p = document.createElement('div');
    p.className = 'ec-chat-pop';
    p.setAttribute('role', 'dialog');
    p.setAttribute('aria-labelledby', 'ec-chat-h');
    p.setAttribute('data-ec-chat-pop', '1');
    document.body.appendChild(p);
    S.panel = p;
    slot.setAttribute('aria-expanded', 'true');
    place();
    loadFilter(S.filter, true);
    var first = p.querySelector('[data-ec-chat-filter]');
    if (first) first.focus();
  }

  function closePanel(returnFocus) {
    if (S.panel && S.panel.parentNode) S.panel.parentNode.removeChild(S.panel);
    S.panel = null;
    var wasOpen = S.open;
    S.open = false;
    var slot = slotEl();
    if (slot) {
      slot.setAttribute('aria-expanded', 'false');
      if (returnFocus && wasOpen) slot.focus();
    }
  }

  // ---------------------------------------------------------------- events --
  function onClick(ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    var slot = t.closest(SLOT);
    if (slot) {
      // man hep, phim bo tro, nut giua: de lien ket /chat chay nhu thuong
      if (window.innerWidth <= NARROW_PX || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || ev.button) return;
      ev.preventDefault();
      if (S.open) closePanel(); else openPanel();
      return;
    }
    if (!S.open) return;
    var inPanel = t.closest('[data-ec-chat-pop="1"]');
    if (!inPanel) { closePanel(); return; }
    var f = t.closest('[data-ec-chat-filter]');
    if (f) {
      S.filter = f.getAttribute('data-ec-chat-filter');
      loadFilter(S.filter, false);
      var again = S.panel && S.panel.querySelector('[data-ec-chat-filter="' + S.filter + '"]');
      if (again) again.focus();
      return;
    }
    if (t.closest('[data-ec-chat-retry]')) { loadFilter(S.filter, true); }
  }

  function onKey(ev) {
    if (S.open && (ev.key === 'Escape' || ev.key === 'Esc')) closePanel(true);
  }

  var _rt = null;
  function onRealtime() {
    // Raven phat 'raven:unread_channel_count_updated' cho dung nguoi nhan; gom nhieu tin lien
    // tiep thanh MOT lan goi.
    if (_rt) clearTimeout(_rt);
    _rt = setTimeout(function () {
      _rt = null;
      refreshTotal();
      if (S.open) loadFilter(S.filter, true);
    }, 1500);
  }

  function bindRealtime() {
    try {
      if (window.frappe && frappe.realtime && typeof frappe.realtime.on === 'function') {
        frappe.realtime.on('raven:unread_channel_count_updated', onRealtime);
      }
    } catch (e) { /* khong co realtime: con vong hoi 2 phut */ }
  }

  function startPoll() {
    if (S.timer) return;
    S.timer = setInterval(function () {
      if (document.visibilityState === 'visible' && slotEl()) refreshTotal();
    }, POLL_MS);
  }

  function boot() {
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', function () { if (S.open) place(); });
    // shell ve lai vung phai thanh tren -> huy hieu moi trong; to lai tu so da biet
    document.addEventListener('ec-shell:header-rendered', function () {
      if (S.total == null) refreshTotal(); else paintBadge();
      startPoll();
    });
    if (slotEl()) { refreshTotal(); startPoll(); }
    bindRealtime();
  }

  // ham thuan cho test (khong phu thuoc DOM that)
  window.ECChat = { badgeText: badgeText, timeLabel: timeLabel, bodyHtml: bodyHtml, panelHtml: panelHtml, rowHtml: rowHtml, esc: esc };

  var path = (window.location && window.location.pathname) || '';
  if (path === '/app' || path.indexOf('/app/') === 0) return;   // khong bao gio tren Desk
  if (path === '/raven' || path.indexOf('/raven/') === 0) return; // trong chinh Raven
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
