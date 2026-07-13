// Copyright (c) 2026, eCentric and contributors
// ERP Shell v1 -- shared shell runtime. SHELL BEHAVIOR ONLY:
//   * activates ONLY on pages carrying the opt-in marker [data-ec-shell="1"]
//   * renders sidebar (nav registry via GET get_shell_boot), user card, logout
//   * exact/most-specific active-route matching (no fuzzy "contains" fallbacks)
//   * mobile drawer + backdrop + keyboard accessibility
// It must NEVER: touch business/approval logic, mutate records, bypass
// permissions, reimplement Notification Center (the bell below only EMITS the
// frozen contract marker data-ec-notification-bell="1"; the NC asset owns all
// bell behavior), or break the page when boot fails (static fallback remains).
//
// Kill switch: site_config `ec_shell_disabled: 1` -> boot returns
// {enabled:false} -> fallback nav stays. Any boot error == same (fail closed
// for the shell only).
//
// Globals: exactly one, window.ECShell (version + pure helpers for tests).
(function () {
  'use strict';

  var VERSION = 'ec-shell v1.1.0 (phase 1B.1 header polish)';
  // Official brand asset -- same site file the homepage uses (/files File doc).
  var LOGO_SRC = '/files/eCentric%20logo%20-%20mini.png';
  var BOOT_URL = '/api/method/ecentric_workspace.shell.api.get_shell_boot';
  var MARKER = '[data-ec-shell="1"]';

  // ---------------------------------------------------------------- pure ---
  function normPath(p) {
    p = String(p || '/').split('?')[0].split('#')[0];
    if (p.length > 1 && p.charAt(p.length - 1) === '/') p = p.slice(0, -1);
    return p || '/';
  }

  // Most-specific wins: exact route (1000+len) > exact pattern (900+len) >
  // prefix pattern "<base>/*" (500+len(base)). "/" is an alias of "/home".
  // NO substring/keyword fallbacks (the legacy "first slug containing 'form'"
  // heuristic caused the G1 mis-highlight bug; deliberately absent here).
  function matchActive(items, pathname) {
    var path = normPath(pathname);
    var bestKey = null, bestScore = 0;
    (items || []).forEach(function (it) {
      var score = 0;
      if (normPath(it.route) === path) score = 1000 + it.route.length;
      (it.active_patterns || []).forEach(function (pat) {
        var s = 0;
        if (pat.slice(-2) === '/*') {
          var base = normPath(pat.slice(0, -2));
          if (path === base || path.indexOf(base + '/') === 0) s = 500 + base.length;
        } else if (normPath(pat) === path) {
          s = 900 + pat.length;
        }
        if (s > score) score = s;
      });
      if (score > bestScore) { bestScore = score; bestKey = it.key; }
    });
    return bestKey;
  }

  function groupItems(items) {
    var order = [], byGroup = {};
    (items || []).forEach(function (it) {
      var g = it.group || '';
      if (!byGroup[g]) { byGroup[g] = []; order.push(g); }
      byGroup[g].push(it);
    });
    return order.map(function (g) { return { group: g, items: byGroup[g] }; });
  }

  function initials(name) {
    var parts = String(name || '?').trim().split(/\s+/);
    var s = (parts.length > 1)
      ? parts[0].charAt(0) + parts[parts.length - 1].charAt(0)
      : String(name || '?').slice(0, 2);
    return s.toUpperCase();
  }

  // ------------------------------------------------------------------ dom --
  var ICONS = {
    home:  '<path d="M3 12l9-9 9 9M5 10v10h14V10"/>',
    check: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    chart: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
    doc:   '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M9 15l2 2 4-4"/>',
    bell:  '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    burger:'<path d="M3 6h18M3 12h18M3 18h18"/>',
    logout:'<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>'
  };
  function svg(name) {
    return '<svg viewBox="0 0 24 24" aria-hidden="true">' + (ICONS[name] || ICONS.doc) + '</svg>';
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function navHtml(nav, activeKey) {
    var h = '';
    groupItems(nav).forEach(function (g) {
      if (g.group) h += '<div class="ec-shell-grouplabel">' + esc(g.group) + '</div>';
      g.items.forEach(function (it) {
        var act = it.key === activeKey ? ' ec-shell-active' : '';
        h += '<a class="ec-shell-item' + act + '" href="' + esc(it.route) + '"' +
             (act ? ' aria-current="page"' : '') + '>' + svg(it.icon) +
             '<span>' + esc(it.label) + '</span></a>';
      });
    });
    return '<nav class="ec-shell-nav" aria-label="Điều hướng chính">' + h + '</nav>';
  }

  // Bell: EMITS the frozen NC contract marker; NC binds/badges it itself
  // (capture-phase click + MutationObserver adoption). No shell-side bell JS.
  // SINGLE EMISSION POINT -- rendered either in the page header-right slot
  // (preferred) or in the sidebar head, never both, never in the drawer.
  function bellHtml() {
    return '<a class="ec-shell-iconbtn" href="/app/notification-log" ' +
      'data-ec-notification-bell="1" aria-label="Thông báo" title="Thông báo">' +
      svg('bell') + '</a>';
  }

  function shellHtml(boot, activeKey, opts) {
    var u = boot.user || {};
    var av = u.image
      ? '<span class="ec-shell-avatar"><img src="' + esc(u.image) + '" alt=""></span>'
      : '<span class="ec-shell-avatar">' + esc(initials(u.full_name || u.name)) + '</span>';
    var headBell = (opts && opts.bell) ? bellHtml() : '';
    return (
      '<div class="ec-shell-head">' +
        '<a class="ec-shell-brand" href="/">' +
          '<img class="ec-shell-logoimg" src="' + LOGO_SRC + '" alt="eCentric">' +
          '<span class="ec-shell-logo" hidden>eC</span>' +
        '<span class="ec-shell-brandname">eCentric</span></a>' +
        headBell +
      '</div>' +
      navHtml(boot.nav, activeKey) +
      '<div class="ec-shell-foot">' +
        '<a class="ec-shell-usercard" href="/app/user" title="' + esc(u.name) + '">' + av +
          '<span class="ec-shell-username">' + esc(u.full_name || u.name) + '</span></a>' +
        // Same logout contract as pm_app.html -- do NOT invent a second flow.
        '<button type="button" class="ec-shell-iconbtn" data-ec-shell-logout="1" ' +
          'aria-label="Đăng xuất" title="Đăng xuất">' + svg('logout') + '</button>' +
      '</div>'
    );
  }

  // ---------------------------------------------------------------- state --
  var S = { mount: null, boot: null, activeKey: null, drawer: null, backdrop: null,
            burger: null, lastFocus: null, bound: false };

  function drawerOpen() {
    if (!S.boot) return;
    if (!S.drawer) {
      S.backdrop = document.createElement('div');
      S.backdrop.className = 'ec-shell-backdrop';
      S.backdrop.setAttribute('data-ec-shell-close', '1');
      S.drawer = document.createElement('aside');
      S.drawer.className = 'ec-shell-drawer';
      S.drawer.setAttribute('role', 'dialog');
      S.drawer.setAttribute('aria-modal', 'true');
      S.drawer.setAttribute('aria-label', 'Điều hướng');
      document.body.appendChild(S.backdrop);
      document.body.appendChild(S.drawer);
    }
    S.drawer.innerHTML = shellHtml(S.boot, S.activeKey, { bell: false }); // fresh render; bell lives in the header
    S.lastFocus = document.activeElement;
    S.backdrop.classList.add('ec-shell-on');
    S.drawer.classList.add('ec-shell-on');
    document.body.classList.add('ec-shell-noscroll');
    var first = S.drawer.querySelector('a,button');
    if (first && first.focus) first.focus();
  }

  function drawerClose() {
    if (!S.drawer) return;
    S.backdrop.classList.remove('ec-shell-on');
    S.drawer.classList.remove('ec-shell-on');
    document.body.classList.remove('ec-shell-noscroll');
    if (S.lastFocus && S.lastFocus.focus) { try { S.lastFocus.focus(); } catch (e) {} }
  }

  function doLogout() {
    // exact contract copied from pm_app.html -- single logout implementation.
    fetch('/api/method/logout', { credentials: 'same-origin' })
      .finally(function () { window.location.href = '/login-page'; });
  }

  function bindOnce() {
    if (S.bound) return;
    S.bound = true;
    // ONE delegated listener; never binds per-render (idempotent re-init safe).
    document.addEventListener('click', function (ev) {
      var t = ev.target && ev.target.closest ? ev.target : null;
      if (!t) return;
      if (t.closest('[data-ec-shell-logout]')) { ev.preventDefault(); doLogout(); return; }
      if (t.closest('[data-ec-shell-open]'))   { ev.preventDefault(); drawerOpen(); return; }
      if (t.closest('[data-ec-shell-close]'))  { drawerClose(); return; }
      if (S.drawer && S.drawer.classList.contains('ec-shell-on') &&
          t.closest('.ec-shell-drawer a')) { drawerClose(); return; } // navigating away
    }, false);
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') drawerClose();
    }, false);
  }

  function ensureBurger() {
    // pages exposing their own opener (data-ec-shell-open on an existing
    // hamburger) suppress the floating burger.
    if (document.querySelector('[data-ec-shell-open]')) return;
    S.burger = document.createElement('button');
    S.burger.type = 'button';
    S.burger.className = 'ec-shell-burger';
    S.burger.setAttribute('data-ec-shell-open', '1');
    S.burger.setAttribute('aria-label', 'Mở menu');
    S.burger.innerHTML = svg('burger');
    document.body.appendChild(S.burger);
  }

  function renderHeaderRight() {
    // Optional page slot: <div class="ec-shell-tbright" data-ec-shell-header-right="1">
    // Right side of the page header hosts [reserved Action Center slot][bell].
    var slot = document.querySelector('[data-ec-shell-header-right="1"]');
    if (!slot) return false;
    slot.innerHTML =
      // Reserved for the future Action Center entry (Phase 1C+). Kept empty
      // and non-interactive on purpose -- do NOT put content here yet.
      '<span class="ec-shell-actionslot" data-ec-shell-action-slot="1" aria-hidden="true"></span>' +
      bellHtml();
    return true;
  }

  function bindLogoFallback() {
    var img = S.mount && S.mount.querySelector('.ec-shell-logoimg');
    if (!img) return;
    img.addEventListener('error', function () {
      img.hidden = true;
      var fb = S.mount.querySelector('.ec-shell-logo');
      if (fb) fb.hidden = false;
    }, { once: true });
  }

  function render() {
    if (!S.mount || !S.boot) return;
    S.activeKey = matchActive(S.boot.nav, window.location.pathname);
    var bellInHeader = renderHeaderRight();          // exactly ONE bell per page
    S.mount.innerHTML = shellHtml(S.boot, S.activeKey, { bell: !bellInHeader });
    bindLogoFallback();
  }

  function reinit() {  // idempotent: safe to call repeatedly
    try { render(); } catch (e) { warn(e); }
  }

  function warn(e) {
    try { console.warn('[ec-shell] disabled:', e && e.message ? e.message : e); } catch (x) {}
  }

  function init() {
    S.mount = document.querySelector(MARKER);
    if (!S.mount) return;                       // NOT opted in -> full no-op
    fetch(BOOT_URL, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) {
        if (!r.ok) throw new Error('boot HTTP ' + r.status);
        return r.json();
      })
      .then(function (j) {
        var m = j && j.message;
        if (!m || m.enabled !== true || !m.nav || !m.nav.length) {
          warn(m && m.reason ? m.reason : 'boot disabled/empty'); // fallback stays
          return;
        }
        S.boot = m;
        bindOnce();
        render();
        ensureBurger();
      })
      .catch(warn);                             // fail closed: fallback nav stays
  }

  // -------------------------------------------------------------- install --
  // pure helpers are ALWAYS exposed (tests), even when init bails out.
  if (!window.ECShell) {
    window.ECShell = {
      version: VERSION,
      matchActive: matchActive,
      normPath: normPath,
      groupItems: groupItems,
      reinit: reinit
    };
  }

  if (window._ecShellV1Installed) return;       // single-install guard
  window._ecShellV1Installed = true;

  var p = window.location && window.location.pathname || '';
  if (p === '/app' || p.indexOf('/app/') === 0) return;  // never on Desk

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
