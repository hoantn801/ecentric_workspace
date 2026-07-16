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

  var VERSION = 'ec-shell v1.5.0 (UX follow-up: sticky regions + instant nav)';
  // Boot cache (sessionStorage, stale-while-revalidate). NEVER authorization:
  // the cache only skips the paint delay; the backend stays the source of
  // truth and refreshes every page view. Keyed/invalidated by VERSION, TTL,
  // and user identity (user_id cookie + fresh-payload user check).
  var CACHE_KEY = 'ec_shell_boot_cache_v1';
  var CACHE_TTL_MS = 5 * 60 * 1000;
  // Nav-search type source: the EXISTING permission-filtered Approval catalog
  // endpoint. Cards without a route (Coming Soon/hidden/inactive) are dropped,
  // so search can never offer a destination the catalog would not.
  var CATALOG_URL = '/api/method/ecentric_workspace.approval_center.api.catalog.list_catalog';
  var CATALOG_CACHE_KEY = 'ec_shell_catalog_cache_v1';
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

  function cookieUser() {
    try {
      var m = document.cookie.match(/(?:^|;\s*)user_id=([^;]*)/);
      return m ? decodeURIComponent(m[1]) : null;
    } catch (e) { return null; }
  }

  // pure (exposed for tests): is a cache entry usable for instant render?
  function cacheValid(entry, nowTs, cookieUid) {
    if (!entry || typeof entry !== 'object') return false;
    if (entry.v !== VERSION) return false;                    // schema/version
    if (!entry.ts || (nowTs - entry.ts) > CACHE_TTL_MS) return false;  // TTL
    var m = entry.data;
    if (!m || m.enabled !== true || !m.nav || !m.nav.length) return false;
    if (!m.user || !m.user.name) return false;
    if (cookieUid && cookieUid !== m.user.name) return false; // identity changed
    return true;
  }

  function readCache() {
    try {
      if (!window.sessionStorage) return null;
      var raw = window.sessionStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      var e = JSON.parse(raw);
      return cacheValid(e, Date.now(), cookieUser()) ? e : null;
    } catch (err) { return null; }
  }

  function writeCache(m) {
    try {
      if (!window.sessionStorage) return;
      if (m && m.enabled === true) {
        window.sessionStorage.setItem(CACHE_KEY,
          JSON.stringify({ v: VERSION, ts: Date.now(), data: m }));
      } else {
        window.sessionStorage.removeItem(CACHE_KEY);  // disabled/kill switch
      }
    } catch (err) {}
  }

  // pure (exposed for tests): prefetch policy -- internal Approval/home GET
  // documents ONLY. Never Desk, never APIs/actions, never logout/login, never
  // external origins, never fragments or non-http schemes. PREFETCH only --
  // prerender/Speculation Rules are deliberately NOT used in 1C-alpha.
  function shouldPrefetch(href, origin, knownRoutes) {
    if (!href || typeof href !== 'string') return false;
    if (href.charAt(0) === '#') return false;
    if (/^(javascript|mailto|tel|data|blob):/i.test(href)) return false;
    var path = href;
    if (/^https?:\/\//i.test(path)) {
      if (!origin || path.indexOf(origin + '/') !== 0) return false;
      path = path.slice(origin.length);
    }
    if (path.charAt(0) !== '/') return false;
    path = path.split('?')[0].split('#')[0];
    if (path === '/app' || path.indexOf('/app/') === 0) return false;
    if (path.indexOf('/api/') === 0) return false;
    if (path.indexOf('/login') === 0 || path.indexOf('logout') !== -1) return false;
    if (path === '/' || path === '/home') return true;
    if (path === '/approval') return true;
    if (path === '/approvals' || path.indexOf('/approvals/') === 0) return true;
    // registry-known internal destinations (UX follow-up): every validated nav
    // route is an internal GET page by construction; deny-rules above still win.
    return !!(knownRoutes && knownRoutes.indexOf(path) >= 0);
  }

  function knownNavRoutes() {
    if (!S.boot) return [];
    return flattenNav(S.boot.nav).map(function (it) { return it.route; });
  }

  // pure: deterministic Vietnamese-insensitive normalization. Per-char NFD
  // strip keeps a strict 1:1 index map (needed for highlight ranges).
  function normalizeVN(s) {
    var out = '';
    s = String(s == null ? '' : s).toLowerCase();
    for (var i = 0; i < s.length; i++) {
      var ch = s.charAt(i);
      if (ch === 'đ') { out += 'd'; continue; }
      var d = ch.normalize ? ch.normalize('NFD').replace(/[\u0300-\u036f]/g, '') : ch;
      out += d.charAt(0) || ch;
    }
    return out;
  }

  // pure: build search entries. Modules from the boot nav; approval types from
  // permission-filtered catalog cards -- ONLY cards with a live route.
  function buildSearchEntries(bootNav, catalogTypes) {
    var out = [];
    flattenNav(bootNav).forEach(function (it) {
      if (it.children && it.children.length) return;   // toggle rows are not destinations
      out.push({ label: it.label, route: it.route, icon: it.icon || 'doc',
                 group: 'module', sub: it.group || '',
                 keywords: (it.keywords || []).concat([it.route]) });
    });
    (catalogTypes || []).forEach(function (c) {
      if (!c || !c.route) return;                       // inaccessible: excluded
      out.push({ label: c.approval_title || c.route, route: c.route, icon: 'doc',
                 group: 'type', sub: c.category_name || '',
                 keywords: [c.description || '', c.category_name || '', c.route] });
    });
    return out;
  }

  // pure: rank + highlight. Match label (best, with highlight range), then
  // keywords/sub (no highlight). Case- and accent-insensitive, partial words.
  function searchNav(entries, query, limitPerGroup) {
    var q = normalizeVN(String(query || '').trim());
    if (!q) return { modules: [], types: [], total: 0 };
    var lim = limitPerGroup || 8;
    var scored = [];
    (entries || []).forEach(function (e) {
      var nl = normalizeVN(e.label);
      var idx = nl.indexOf(q);
      var score = -1, hl = null;
      if (idx >= 0) { score = 100 - idx + (nl === q ? 50 : 0); hl = [idx, q.length]; }
      else {
        var hay = normalizeVN((e.keywords || []).join(' ') + ' ' + (e.sub || ''));
        if (hay.indexOf(q) >= 0) score = 10;
      }
      if (score >= 0) scored.push({ e: e, score: score, hl: hl });
    });
    scored.sort(function (a, b) { return b.score - a.score || a.e.label.localeCompare(b.e.label); });
    var modules = [], types = [];
    scored.forEach(function (r) {
      var item = { label: r.e.label, route: r.e.route, icon: r.e.icon, sub: r.e.sub, hl: r.hl };
      if (r.e.group === 'module') { if (modules.length < lim) modules.push(item); }
      else if (types.length < lim) types.push(item);
    });
    return { modules: modules, types: types, total: modules.length + types.length };
  }

  // pure: catalog cache validity (mirrors cacheValid; user-isolated).
  function catalogCacheValid(entry, nowTs, userName) {
    if (!entry || typeof entry !== 'object') return false;
    if (entry.v !== VERSION) return false;
    if (!entry.ts || (nowTs - entry.ts) > CACHE_TTL_MS) return false;
    if (!userName || entry.user !== userName) return false;
    return Object.prototype.toString.call(entry.types) === '[object Array]';
  }

  // Most-specific wins: exact route (1000+len) > exact pattern (900+len) >
  // prefix pattern "<base>/*" (500+len(base)). "/" is an alias of "/home".
  // NO substring/keyword fallbacks (the legacy "first slug containing 'form'"
  // heuristic caused the G1 mis-highlight bug; deliberately absent here).
  function flattenNav(items) {
    var out = [];
    (items || []).forEach(function (it) {
      out.push(it);
      (it.children || []).forEach(function (ch) { out.push(ch); });
    });
    return out;
  }

  function matchActive(items, pathname) {
    var path = normPath(pathname);
    var bestKey = null, bestScore = 0;
    flattenNav(items).forEach(function (it) {
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
    search:'<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
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

  function itemHtml(it, activeKey, extraCls) {
    var act = it.key === activeKey ? ' ec-shell-active' : '';
    return '<a class="ec-shell-item' + (extraCls || '') + act + '" href="' + esc(it.route) + '"' +
           (act ? ' aria-current="page"' : '') + '>' + svg(it.icon) +
           '<span>' + esc(it.label) + '</span></a>';
  }

  function navHtml(nav, activeKey) {
    var h = '';
    groupItems(nav).forEach(function (g) {
      var loneParent = g.items.length === 1 && g.items[0].children && g.items[0].children.length;
      if (g.group && !loneParent) h += '<div class="ec-shell-grouplabel">' + esc(g.group) + '</div>';
      g.items.forEach(function (it) {
        if (it.children && it.children.length) {
          // minimal collapsible submenu (2B.1 nav patch): toggle is a BUTTON
          // (never navigates; the parent route is a non-navigable anchor);
          // expanded automatically when a child is active.
          var childActive = it.children.some(function (ch) { return ch.key === activeKey; });
          var open = childActive || S.subOpen[it.key] === true;
          h += '<button type="button" class="ec-shell-item ec-shell-subtoggle" ' +
               'data-ec-shell-subtoggle="' + esc(it.key) + '" aria-expanded="' + (open ? 'true' : 'false') + '">' +
               svg(it.icon) + '<span>' + esc(it.label) + '</span>' +
               '<svg class="ec-shell-chev" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>' +
               '</button>';
          h += '<div class="ec-shell-children"' + (open ? '' : ' hidden') + ' data-ec-shell-children="' + esc(it.key) + '">';
          it.children.forEach(function (ch) { h += itemHtml(ch, activeKey, ' ec-shell-child'); });
          h += '</div>';
        } else {
          h += itemHtml(it, activeKey, '');
        }
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
      // nav search (1C.1): input under the brand area + grouped results.
      // Frontend-only; module entries from the boot nav, approval types from
      // the permission-filtered catalog (lazy-loaded). Results are plain
      // <a href> -- no interception, backend authorization unchanged.
      '<div class="ec-shell-search">' +
        svg('search') +
        '<input class="ec-shell-search-in" type="text" placeholder="Tìm chức năng…" ' +
          'role="combobox" aria-expanded="false" aria-autocomplete="list" ' +
          'aria-label="Tìm chức năng" autocomplete="off" spellcheck="false">' +
        '<button type="button" class="ec-shell-search-clear" data-ec-shell-search-clear="1" ' +
          'hidden aria-label="Xóa tìm kiếm">&times;</button>' +
      '</div>' +
      '<div class="ec-shell-search-results" role="listbox" hidden></div>' +
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
            burger: null, lastFocus: null, bound: false, vtDone: false, subOpen: {} };
  var prefetched = {};
  var hoverTimer = null;

  function prefetch(href) {
    if (prefetched[href]) return;
    prefetched[href] = 1;
    try {
      var l = document.createElement('link');
      l.rel = 'prefetch'; l.href = href; l.as = 'document';
      document.head.appendChild(l);
    } catch (e) {}
  }

  function intentTarget(ev) {
    var t = ev.target && ev.target.closest ? ev.target : null;
    if (!t) return null;
    return t.closest('.ec-shell-nav a, .ec-shell-drawer a, .ec-shell-fallback a, a.ec-shell-crumblink');
  }

  // Cross-document View Transitions: PURE progressive enhancement. We only
  // feature-detect (never call startViewTransition); the rule is injected on
  // opted-in pages only, so shell->shell navigations crossfade natively in
  // supporting browsers and everything else falls back to normal navigation.
  function injectViewTransition() {
    if (S.vtDone) return;
    if (typeof document.startViewTransition !== 'function') return;
    S.vtDone = true;
    try {
      var st = document.createElement('style');
      st.setAttribute('data-ec-shell-vt', '1');
      st.textContent = '@view-transition{navigation:auto}';
      document.head.appendChild(st);
    } catch (e) {}
  }

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

  // ------------------------------------------------------------ nav search --
  var SEARCH = { types: null, loading: false, failed: false, sel: -1, flat: [] };

  function readCatalogCache(userName) {
    try {
      if (!window.sessionStorage) return null;
      var raw = window.sessionStorage.getItem(CATALOG_CACHE_KEY);
      if (!raw) return null;
      var e = JSON.parse(raw);
      return catalogCacheValid(e, Date.now(), userName) ? e.types : null;
    } catch (err) { return null; }
  }

  function ensureCatalog() {
    if (SEARCH.types || SEARCH.loading || SEARCH.failed || !S.boot) return;
    var userName = S.boot.user && S.boot.user.name;
    var cached = readCatalogCache(userName);
    if (cached) { SEARCH.types = cached; return; }
    SEARCH.loading = true;
    fetch(CATALOG_URL, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { if (!r.ok) throw new Error('catalog HTTP ' + r.status); return r.json(); })
      .then(function (j) {
        var m = j && j.message;
        var types = (m && m.types || []).filter(function (c) { return c && c.route; })
          .map(function (c) {   // slim: labels/routes only -- never business data
            return { approval_title: c.approval_title, route: c.route,
                     category_name: c.category_name, description: c.description || '' };
          });
        SEARCH.types = types;
        SEARCH.loading = false;
        try {
          window.sessionStorage.setItem(CATALOG_CACHE_KEY,
            JSON.stringify({ v: VERSION, ts: Date.now(), user: userName, types: types }));
        } catch (e) {}
        var inp = activeSearchInput();
        if (inp && inp.value) renderResults(inp);   // refresh open results
      })
      .catch(function () { SEARCH.loading = false; SEARCH.failed = true; });
  }

  function searchWrap(inp) { return inp ? inp.parentNode : null; }
  function resultsBox(inp) {
    var w = searchWrap(inp);
    return w && w.nextElementSibling && w.nextElementSibling.className &&
      String(w.nextElementSibling.className).indexOf('ec-shell-search-results') >= 0
      ? w.nextElementSibling : null;
  }
  function searchHost(inp) {  // the aside (mount or drawer) containing this input
    var n = inp;
    while (n && n !== document.body) {
      var cn = String(n.className || '');
      if (cn.indexOf('ec-shell-mount') >= 0 || cn.indexOf('ec-shell-drawer') >= 0) return n;
      n = n.parentNode;
    }
    return null;
  }
  function activeSearchInput() {
    var el = document.activeElement;
    return el && String(el.className || '').indexOf('ec-shell-search-in') >= 0 ? el : null;
  }

  function hlLabel(item) {
    if (!item.hl) return esc(item.label);
    var a = item.hl[0], b = item.hl[0] + item.hl[1];
    return esc(item.label.slice(0, a)) + '<b class="ec-shell-hl">' +
           esc(item.label.slice(a, b)) + '</b>' + esc(item.label.slice(b));
  }

  function renderResults(inp) {
    var box = resultsBox(inp); if (!box) return;
    var host = searchHost(inp);
    var q = inp.value || '';
    var clearBtn = searchWrap(inp).querySelector('.ec-shell-search-clear');
    if (clearBtn) clearBtn.hidden = !q;
    if (!q.trim()) {
      box.hidden = true; box.innerHTML = '';
      inp.setAttribute('aria-expanded', 'false');
      if (host) host.classList.remove('ec-shell-searching');
      SEARCH.sel = -1; SEARCH.flat = [];
      return;
    }
    ensureCatalog();
    var res = searchNav(buildSearchEntries(S.boot && S.boot.nav, SEARCH.types), q, 8);
    SEARCH.flat = res.modules.concat(res.types);
    if (SEARCH.sel >= SEARCH.flat.length) SEARCH.sel = SEARCH.flat.length - 1;
    var h = '';
    function grp(title, items, offset) {
      if (!items.length) return;
      h += '<div class="ec-shell-search-grp">' + esc(title) + '</div>';
      items.forEach(function (it, i) {
        var idx = offset + i;
        h += '<a class="ec-shell-search-item' + (idx === SEARCH.sel ? ' ec-shell-selected' : '') +
             '" role="option" aria-selected="' + (idx === SEARCH.sel ? 'true' : 'false') +
             '" href="' + esc(it.route) + '">' + svg(it.icon || 'doc') +
             '<span class="ec-shell-search-lbl">' + hlLabel(it) +
             (it.sub ? '<small>' + esc(it.sub) + '</small>' : '') + '</span></a>';
      });
    }
    grp('Chức năng', res.modules, 0);
    grp('Yêu cầu phê duyệt', res.types, res.modules.length);
    if (!res.total) {
      h = '<div class="ec-shell-search-empty">Không tìm thấy chức năng phù hợp' +
          (SEARCH.loading ? ' (đang tải danh mục…)' : '') + '</div>';
    }
    box.innerHTML = h;
    box.hidden = false;
    inp.setAttribute('aria-expanded', 'true');
    if (host) host.classList.add('ec-shell-searching');
  }

  function clearSearch(inp) {
    if (!inp) return;
    inp.value = '';
    SEARCH.sel = -1;
    renderResults(inp);
  }

  function onSearchKeydown(ev, inp) {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      if (!SEARCH.flat.length) return;
      SEARCH.sel = ev.key === 'ArrowDown'
        ? (SEARCH.sel + 1) % SEARCH.flat.length
        : (SEARCH.sel <= 0 ? SEARCH.flat.length - 1 : SEARCH.sel - 1);
      renderResults(inp);
    } else if (ev.key === 'Enter') {
      if (!SEARCH.flat.length) return;
      var pickIdx = SEARCH.sel >= 0 ? SEARCH.sel : 0;
      var box = resultsBox(inp);
      var links = box ? box.querySelectorAll('.ec-shell-search-item') : null;
      var el = links && links[pickIdx];
      // navigate via the real result anchor (native <a> semantics; nothing
      // intercepted); fallback assigns location from the pure result model.
      if (el && el.click) { el.click(); return; }
      var pick = SEARCH.flat[pickIdx];
      if (pick && pick.route) window.location.href = pick.route;
    } else if (ev.key === 'Escape') {
      ev.stopPropagation();          // first Esc clears search; next closes drawer
      clearSearch(inp);
      inp.blur();
    }
  }

  function focusSearch() {
    var inp = S.mount && S.mount.querySelector('.ec-shell-search-in');
    var visible = false;
    if (inp) { try { visible = inp.offsetParent !== null; } catch (e) { visible = true; } }
    if (inp && visible) { inp.focus(); return; }
    drawerOpen();                    // mobile: sidebar hidden -> search in drawer
    var dinp = S.drawer && S.drawer.querySelector('.ec-shell-search-in');
    if (dinp && dinp.focus) dinp.focus();
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
      var st = t.closest('[data-ec-shell-subtoggle]');
      if (st) {
        var k = st.getAttribute('data-ec-shell-subtoggle');
        S.subOpen[k] = !(S.subOpen[k] === true);
        var box = st.nextElementSibling;
        if (box && box.getAttribute && box.getAttribute('data-ec-shell-children') === k) {
          box.hidden = !S.subOpen[k];
        }
        st.setAttribute('aria-expanded', S.subOpen[k] ? 'true' : 'false');
        return;
      }
      if (S.drawer && S.drawer.classList.contains('ec-shell-on') &&
          t.closest('.ec-shell-drawer a')) { drawerClose(); return; } // navigating away
    }, false);
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') drawerClose();
    }, false);
    // pointer-intent prefetch (hover >=65ms or pointerdown). Delegated, bound
    // once, allow-listed via shouldPrefetch(). Navigation itself is NEVER
    // intercepted -- prefetch only warms the HTTP cache.
    document.addEventListener('pointerover', function (ev) {
      var a = intentTarget(ev);
      if (!a) return;
      var href = a.getAttribute('href');
      if (!shouldPrefetch(href, window.location.origin, knownNavRoutes())) return;
      clearTimeout(hoverTimer);
      hoverTimer = setTimeout(function () { prefetch(href); }, 65);
    }, true);
    document.addEventListener('pointerout', function () { clearTimeout(hoverTimer); }, true);
    document.addEventListener('pointerdown', function (ev) {
      var a = intentTarget(ev);
      if (!a) return;
      var href = a.getAttribute('href');
      if (shouldPrefetch(href, window.location.origin, knownNavRoutes())) prefetch(href);
    }, true);
    // nav search: delegated, bound once. Results are plain anchors -> native
    // navigation; nothing here intercepts routing or touches business data.
    document.addEventListener('input', function (ev) {
      var t = ev.target;
      if (t && String(t.className || '').indexOf('ec-shell-search-in') >= 0) {
        SEARCH.sel = -1;
        renderResults(t);
      }
    }, true);
    document.addEventListener('keydown', function (ev) {
      var t = ev.target;
      if (t && String(t.className || '').indexOf('ec-shell-search-in') >= 0) {
        onSearchKeydown(ev, t);
        return;
      }
      if ((ev.ctrlKey || ev.metaKey) && String(ev.key).toLowerCase() === 'k') {
        ev.preventDefault();
        focusSearch();
      }
    }, true);
    document.addEventListener('click', function (ev) {
      var t = ev.target && ev.target.closest ? ev.target : null;
      if (!t) return;
      var btn = t.closest('[data-ec-shell-search-clear]');
      if (btn) {
        var inp = btn.parentNode && btn.parentNode.querySelector('.ec-shell-search-in');
        clearSearch(inp);
        if (inp && inp.focus) inp.focus();
      }
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

  function applyBoot(m) {
    S.boot = m;
    bindOnce();          // flag-guarded: never double-binds
    render();            // wholesale innerHTML: never duplicates bell/nav
    ensureBurger();      // no-ops when an opener already exists
    injectViewTransition();
  }

  function init() {
    S.mount = document.querySelector(MARKER);
    if (!S.mount) return;                       // NOT opted in -> full no-op

    // 1) instant paint from the per-tab cache (stale-while-revalidate)
    var cached = readCache();
    if (cached) applyBoot(cached.data);

    // 2) background refresh -- backend stays the source of truth
    fetch(BOOT_URL, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) {
        if (!r.ok) throw new Error('boot HTTP ' + r.status);
        return r.json();
      })
      .then(function (j) {
        var m = j && j.message;
        if (!m || m.enabled !== true || !m.nav || !m.nav.length) {
          writeCache(m);                        // clears cache on disabled
          if (!S.boot) warn(m && m.reason ? m.reason : 'boot disabled/empty');
          return;                               // rendered shell (if any) stays
        }
        var changed = !S.boot || JSON.stringify(m) !== JSON.stringify(S.boot);
        writeCache(m);                          // refresh ts + payload
        if (changed) applyBoot(m);              // update ONLY when different
      })
      .catch(function (e) {
        // fail closed for the shell only; a cached render stays fully usable
        if (!S.boot) warn(e);
      });
  }

  // -------------------------------------------------------------- install --
  // pure helpers are ALWAYS exposed (tests), even when init bails out.
  if (!window.ECShell) {
    window.ECShell = {
      version: VERSION,
      matchActive: matchActive,
      normPath: normPath,
      groupItems: groupItems,
      cacheValid: cacheValid,
      shouldPrefetch: shouldPrefetch,
      normalizeVN: normalizeVN,
      buildSearchEntries: buildSearchEntries,
      searchNav: searchNav,
      catalogCacheValid: catalogCacheValid,
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
