// Copyright (c) 2026, eCentric and contributors
// ec_form_header.bundle.js - dau trang form phe duyet kieu "thanh cong cu dinh" (phuong an C, Hoan chot
// 23/11/2026). Markup (ten form, icon, hang tab, sao, "?") nam SAN trong tung trang (A65 - khong ve lai
// sau khi tai). File nay chi gan hanh vi:
//   * nut ▾ / bam ten form: mo menu "Doi loai phieu" (Da ghim + Ban hay dung, lay tu list_catalog khi
//     MO menu lan dau - khong goi gi luc tai trang ngoai trang thai sao);
//   * ngoi sao: ghim / bo ghim loai phieu dang mo (catalog_api.set_pin, POST, chi cua chinh minh).
// Khong co #ec-fh tren trang -> khong lam gi.
(function () {
  'use strict';
  var CAT = 'ecentric_workspace.approval_center.api.catalog.';
  var ICONS = {
    'wallet': '<path d="M20 12V8H6a2 2 0 0 1 0-4h12v4"/><path d="M4 6v12a2 2 0 0 0 2 2h14v-4"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>',
    'users': '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    'package': '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M3 7l9 5 9-5M12 12v10"/>',
    'database': '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    'target': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    'calendar-clock': '<path d="M21 7.5V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h6"/><path d="M16 2v4M8 2v4M3 10h18"/><circle cx="18" cy="16" r="4"/><path d="M18 14.5V16l1 1"/>',
    'building-2': '<path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18"/><path d="M6 12H4a2 2 0 0 0-2 2v8h4M18 9h2a2 2 0 0 1 2 2v11h-4M10 6h4M10 10h4M10 14h4"/>',
    'file-check': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M9 15l2 2 4-4"/>'
  };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function call(method, args, post) {
    var fr = window.frappe;
    if (!fr || !fr.call) return Promise.reject(new Error('no frappe'));
    return fr.call({ method: CAT + method, args: args || {}, type: post ? 'POST' : 'GET' }).then(function (r) { return r && r.message; });
  }
  function toast(msg) {
    if (window.frappe && frappe.show_alert) { try { frappe.show_alert({ message: msg, indicator: 'blue' }, 3); return; } catch (e) { /* bo qua */ } }
  }

  function init() {
    var bar = document.getElementById('ec-fh');
    if (!bar || bar.getAttribute('data-ec-fh-bound') === '1') return;
    bar.setAttribute('data-ec-fh-bound', '1');
    var code = bar.getAttribute('data-ec-fh-type') || '';
    var id = bar.querySelector('.ec-fh-id'), menu = bar.querySelector('.ec-fh-menu'), sw = bar.querySelector('[data-ec-fh-switch]');
    var star = bar.querySelector('[data-ec-fh-pin]');
    var cat = null, loading = null;

    function load() {
      if (cat) return Promise.resolve(cat);
      if (!loading) loading = call('list_catalog').then(function (m) { cat = m || { types: [] }; return cat; });
      return loading;
    }
    function paintStar(on) {
      if (!star) return;
      star.setAttribute('aria-pressed', on ? 'true' : 'false');
      star.setAttribute('title', on ? 'Bỏ ghim khỏi Approval Center' : 'Ghim lên đầu Approval Center');
      star.setAttribute('aria-label', star.getAttribute('title'));
    }
    function item(t) {
      var ic = t.icon || t.category_icon || 'file-check';
      return '<a role="menuitem" href="' + esc(t.route) + '"><span class="ec-fh-ic ec-fh-tone-' + esc(ic) + '"><svg viewBox="0 0 24 24" aria-hidden="true">'
        + (ICONS[ic] || ICONS['file-check']) + '</svg></span>' + esc(t.title_vi || t.approval_title || '') + '</a>';
    }
    function paintMenu() {
      var types = (cat && cat.types) || [], by = {};
      types.forEach(function (t) { by[t.approval_code] = t; });
      var ok = function (c) { var t = by[c]; return t && t.route && t.card_status === 'Active' && c !== code; };
      var pins = (cat.my_pins || []).filter(ok);
      var use = Object.keys(cat.my_usage || {}).filter(function (c) { return ok(c) && pins.indexOf(c) < 0; })
        .sort(function (a, b) { return (cat.my_usage[b] || 0) - (cat.my_usage[a] || 0); }).slice(0, 4);
      var html = '';
      if (pins.length) html += '<div class="lbl">Đã ghim</div>' + pins.map(function (c) { return item(by[c]); }).join('');
      if (use.length) html += '<div class="lbl">Bạn hay dùng</div>' + use.map(function (c) { return item(by[c]); }).join('');
      if (!html) html = '<div class="muted">Chưa có loại phiếu ghim / hay dùng.</div>';
      menu.innerHTML = html + '<a role="menuitem" class="all" href="/approvals">Xem tất cả loại phiếu →</a>';
    }
    function open(on) {
      if (!menu || !id) return;
      menu.hidden = !on;
      id.classList.toggle('open', on);
      if (sw) sw.setAttribute('aria-expanded', on ? 'true' : 'false');
      if (on) {
        menu.innerHTML = '<div class="muted">Đang tải…</div>';
        load().then(paintMenu).catch(function () { menu.innerHTML = '<div class="muted">Không tải được danh sách.</div><a class="all" href="/approvals">Mở Approval Center →</a>'; });
      }
    }
    if (id) id.addEventListener('click', function (e) {
      if (e.target.closest('.ec-fh-menu')) return;
      open(menu.hidden);
    });
    document.addEventListener('click', function (e) { if (menu && !menu.hidden && !bar.contains(e.target)) open(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menu && !menu.hidden) { open(false); if (sw) sw.focus(); } });

    if (star) {
      load().then(function (c) { paintStar((c.my_pins || []).indexOf(code) >= 0); }).catch(function () { /* giu trang thai mac dinh */ });
      star.addEventListener('click', function () {
        var on = star.getAttribute('aria-pressed') !== 'true';
        paintStar(on);
        call('set_pin', { approval_type: code, pinned: on ? 1 : 0 }, true).then(function (m) {
          if (cat && m && m.my_pins) cat.my_pins = m.my_pins;
          toast(on ? 'Đã ghim lên đầu Approval Center.' : 'Đã bỏ ghim.');
        }).catch(function (e) {
          paintStar(!on);
          var msg = '';
          try { var sm = e && (e._server_messages || (e.responseJSON && e.responseJSON._server_messages)); if (sm) msg = JSON.parse(JSON.parse(sm)[0]).message || ''; } catch (x) { /* bo qua */ }
          toast(msg || 'Không lưu được, thử lại.');
        });
      });
    }
  }
  window.EcFormHeader = { init: init };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
