// Copyright (c) 2026, eCentric and contributors
// Action Center homepage widget (app-owned asset).
//
// UI polish revision:
//   - The whole card is the click target. No nested CTA button is rendered.
//     action_label is exposed via aria-label / title for accessibility.
//   - No underline anywhere on the card (normal / hover / focus).
//   - 3 compact lines per card: priority + source + time, title, subtitle.
//     title and subtitle are single-line with ellipsis.
//   - DISPLAY_LIMIT = 4. Footer "Xem thêm N việc →" only when total > 4.
//
// Loaded by:
//   <script id="ec-action-center-widget"
//           src="/assets/ecentric_workspace/js/action_center_widget.js"
//           defer></script>
// injected into the homepage Web Page by patch p001_homepage_action_center.
//
// API call uses frappe.call (handles auth + CSRF + JSON). NO URL building
// here -- item.action_url is the single source of truth (route resolver
// lives in ecentric_workspace.action_center.resolvers).
(function(){
  'use strict';
  if (window._ecActionCenterInstalled) { return; }
  window._ecActionCenterInstalled = true;

  // ---- CSS ---------------------------------------------------------------
  if (!document.getElementById('ec-action-center-css')) {
    var st = document.createElement('style');
    st.id = 'ec-action-center-css';
    st.textContent =
      // Card is the whole click area. Kill underline on EVERY state and
      // descendant -- the website-wide <a> styles must not bleed through.
      '.ec-ac-card,' +
        '.ec-ac-card:hover,' +
        '.ec-ac-card:focus,' +
        '.ec-ac-card:active,' +
        '.ec-ac-card:visited,' +
        '.ec-ac-card *,' +
        '.ec-ac-card:hover *,' +
        '.ec-ac-card:focus *,' +
        '.ec-ac-card:active *,' +
        '.ec-ac-card:visited *' +
        '{text-decoration:none !important;}' +
      '.ec-ac-card{display:block;padding:10px 12px;border:1px solid #e5e7eb;border-radius:10px;background:#fff;color:inherit;margin-bottom:8px;outline:none;}' +
      '.ec-ac-card:hover{border-color:#2C3DA6;background:#f7f8fb;}' +
      '.ec-ac-row1{display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:11px;}' +
      '.ec-ac-pill{padding:1px 7px;border-radius:8px;color:#fff;font-weight:600;font-size:10px;letter-spacing:.3px;}' +
      '.ec-ac-src{padding:1px 7px;border-radius:8px;background:#eef0fb;color:#2C3DA6;font-weight:600;font-size:10px;letter-spacing:.4px;}' +
      '.ec-ac-time{margin-left:auto;color:#6b7280;font-size:11px;}' +
      // Title + subtitle are single line, ellipsis.
      '.ec-ac-title{font-size:13.5px;font-weight:600;color:#111827;line-height:1.35;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}' +
      '.ec-ac-subtitle{font-size:11.5px;color:#6b7280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}' +
      '.ec-ac-more,.ec-ac-more:hover,.ec-ac-more:focus,.ec-ac-more:visited{display:block;text-align:center;padding:10px;font-size:12.5px;color:#2C3DA6;font-weight:600;text-decoration:none !important;background:#f9fafb;border-top:1px solid #e5e7eb;}';
    document.head.appendChild(st);
  }

  var DISPLAY_LIMIT = 4;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];
    });
  }

  function priColor(p) { return p === 'High' ? '#dc2626' : (p === 'Low' ? '#9ca3af' : '#f59e0b'); }
  function priLabel(p) { return p === 'High' ? 'CAO' : (p === 'Low' ? 'THẤP' : 'TB'); }

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

  function findPanel() {
    var nodes = document.querySelectorAll('.panel');
    for (var i = 0; i < nodes.length; i++) {
      var t = nodes[i].querySelector('.panel-title');
      if (t && /Việc cần làm/.test(t.textContent)) return nodes[i];
    }
    return null;
  }

  function renderCards(items) {
    var panel = findPanel();
    if (!panel) return;
    var listEl = panel.querySelector('.approval-list');
    if (!listEl) return;
    if (!items || items.length === 0) {
      listEl.innerHTML = '<div style="padding:24px;text-align:center;color:#6b7280;font-size:13px;">Không có việc nào cần làm</div>';
      return;
    }
    var total = items.length;
    var visibleItems = items.slice(0, DISPLAY_LIMIT);
    var html = visibleItems.map(function(it) {
      // action_url is supplied by the server resolver. NO URL building here.
      var href = it.action_url || '#';
      // action_label is exposed via aria-label / title only (no nested button).
      var aria = esc(it.action_label || 'Mở');
      return '<a href="' + esc(href) + '" class="ec-ac-card"' +
        ' aria-label="' + aria + '"' +
        ' title="' + aria + '">' +
        '<div class="ec-ac-row1">' +
          '<span class="ec-ac-pill" style="background:' + priColor(it.priority) + ';">' + priLabel(it.priority) + '</span>' +
          '<span class="ec-ac-src">' + esc(it.source_label || '') + '</span>' +
          '<span class="ec-ac-time">' + esc(ago(it.modified)) + '</span>' +
        '</div>' +
        '<div class="ec-ac-title">' + esc(it.title || '') + '</div>' +
        '<div class="ec-ac-subtitle">' + esc(it.subtitle || '') + '</div>' +
      '</a>';
    }).join('');
    if (total > DISPLAY_LIMIT) {
      var more = total - DISPLAY_LIMIT;
      var u = (window.frappe && window.frappe.session && window.frappe.session.user) || '';
      var moreLink = '/app/todo/view/list?status=Open&allocated_to=' + encodeURIComponent(u);
      html += '<a href="' + moreLink + '" class="ec-ac-more">Xem thêm ' + more + ' việc →</a>';
    }
    listEl.innerHTML = html;
  }

  function loadItems() {
    var panel = findPanel();
    if (!panel) return;
    if (window.frappe && typeof window.frappe.call === 'function') {
      window.frappe.call({
        method: 'ecentric_workspace.action_center.api.get_action_items',
        type: 'GET',
        callback: function(r) {
          var msg = r && r.message;
          if (msg && msg.success && msg.items) renderCards(msg.items);
        }
      });
    }
  }

  function init() {
    loadItems();
    setInterval(loadItems, 90000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  console.log('[ec-action-center-widget] installed (asset, ui polish)');
})();
