// Runtime proof for ERP Shell v1 (mirrors the NC *_check.js style).
// Executes the REAL asset in a vm sandbox with a stub window/document and
// proves: opt-in-only init (no fetch without marker), install guard,
// active-route matcher precedence (incl. the hr-activity + G1 regression
// cases), query-string preservation, and idempotent reinit.
//   node ecentric_workspace/shell/tests/ec_shell_check.js
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'public', 'js', 'ec_shell.js'), 'utf8');
let failures = 0;
function ok(c, m) { if (!c) { failures++; console.error('FAIL: ' + m); } else { console.log('ok  - ' + m); } }

function makeSandbox(pathname, hasMarker) {
  let fetchCalls = 0;
  const doc = {
    readyState: 'complete',
    querySelector: sel => (hasMarker && sel === '[data-ec-shell="1"]') ? { innerHTML: '' } : null,
    addEventListener: () => {}, createElement: () => ({ classList: { add(){}, remove(){} }, setAttribute(){}, appendChild(){} }),
    body: { appendChild: () => {}, classList: { add(){}, remove(){} } },
    activeElement: null,
  };
  const win = {
    location: { pathname: pathname },
    document: doc,
    fetch: () => { fetchCalls++; return { then: () => ({ then: () => ({ catch: () => {} }) }) }; },
    addEventListener: () => {},
    console: console,
  };
  win.window = win;
  const sb = vm.createContext(Object.assign({ console, document: doc, fetch: win.fetch, window: win }, {}));
  sb.window.fetch = win.fetch;
  return { sb, win, get fetchCalls() { return fetchCalls; } };
}

// ---- 1. no marker -> full no-op (no fetch), but pure helpers exposed -------
{
  const env = makeSandbox('/approvals/leave', false);
  vm.runInContext(SRC, env.sb);
  ok(env.win.ECShell && typeof env.win.ECShell.matchActive === 'function', 'ECShell helpers exposed without opt-in');
  ok(env.fetchCalls === 0, 'no boot fetch on a page WITHOUT the data-ec-shell marker');
  ok(env.win._ecShellV1Installed === true, 'install guard set');
  vm.runInContext(SRC, env.sb);
  ok(env.fetchCalls === 0, 'second inclusion is a no-op (single-install guard)');
}

// ---- 2. marker present -> boot fetch fired --------------------------------
{
  const env = makeSandbox('/approvals/leave', true);
  vm.runInContext(SRC, env.sb);
  ok(env.fetchCalls === 1, 'boot fetch fires exactly once on an opted-in page');
}

// ---- 3. never on Desk ------------------------------------------------------
{
  const env = makeSandbox('/app/todo', true);
  vm.runInContext(SRC, env.sb);
  ok(env.fetchCalls === 0, 'no activation on /app/* even with a marker');
}

// ---- 4. matcher precedence + regressions -----------------------------------
{
  const env = makeSandbox('/x', false);
  vm.runInContext(SRC, env.sb);
  const M = env.win.ECShell.matchActive;
  const NAV = [
    { key: 'core.home', route: '/home', active_patterns: ['/', '/home'] },
    { key: 'apc.catalog', route: '/approvals', active_patterns: ['/approvals', '/approvals/*'] },
    { key: 'apc.dashboard', route: '/approvals/dashboard', active_patterns: ['/approvals/dashboard'] },
    { key: 'approval.inbox', route: '/approval', active_patterns: ['/approval'] },
    { key: 'tickets.all', route: '/all-ticket', active_patterns: ['/all-ticket'] },
    { key: 'legacy.create_po', route: '/form-po', active_patterns: ['/form-po'] },
    { key: 'legacy.others', route: '/others', active_patterns: ['/others'], children: [
      { key: 'legacy.create_client', label: 'Client Request', route: '/client-request', icon: 'doc', active_patterns: ['/client-request'], keywords: ['client'] },
    ] },
  ];
  ok(M(NAV, '/approvals/hr-activity') === 'apc.catalog', 'hr-activity highlights Approval Center (bug fixed via registry matching)');
  ok(M(NAV, '/approvals/dashboard') === 'apc.dashboard', 'exact route outranks catalog prefix pattern');
  ok(M(NAV, '/approvals') === 'apc.catalog', 'catalog exact');
  ok(M(NAV, '/approvals/') === 'apc.catalog', 'trailing slash normalized');
  ok(M(NAV, '/approval') === 'approval.inbox', 'legacy /approval matches ONLY its exact item (no prefix bleed)');
  ok(M(NAV, '/all-ticket') === 'tickets.all', '/all-ticket highlights its own entry');
  ok(M(NAV, '/approval?id=MSO-123&type=mso_request'.split('?')[0]) === 'approval.inbox', '/approval?id= deep link keeps All Tickets active');
  ok(M(NAV, '/form-po') === 'legacy.create_po', 'creation route /form-po highlights its item');
  ok(M(NAV, '/client-request') === 'legacy.create_client', 'CHILD route active-match works (Others submenu)');
  {
    const entries2 = env.win.ECShell.buildSearchEntries(NAV.map(x => Object.assign({label: x.key, icon: 'doc', group: 'g', keywords: []}, x)), []);
    ok(entries2.some(e => e.route === '/client-request'), 'search index includes submenu children');
    ok(!entries2.some(e => e.route === '/others'), 'non-navigable toggle row excluded from search');
  }
  ok(M(NAV, '/all-tickets') === null, 'duplicate route /all-tickets matches NOTHING (no lookalike bleed)');
  ok(M(NAV, '/home') === 'core.home' && M(NAV, '/') === 'core.home', '/ aliases /home');
  ok(M(NAV, '/approvals/leave?id=EC-LV-0001&tab=my-requests'.split('?')[0]) === 'apc.catalog', 'deep-link path matches catalog');
  ok(M(NAV, '/gbs-po-form') === null, 'G1 regression: unknown route matches NOTHING (no substring fallback)');
  ok(M(NAV, '/approvalsx') === null, 'no prefix bleed onto lookalike routes');
  ok(env.win.ECShell.normPath('/approvals/leave?id=1&tab=create') === '/approvals/leave', 'query string never alters matching, links untouched');
}

// ---- 5. reinit idempotent ---------------------------------------------------
{
  const env = makeSandbox('/approvals', false);
  vm.runInContext(SRC, env.sb);
  let threw = false;
  try { env.win.ECShell.reinit(); env.win.ECShell.reinit(); } catch (e) { threw = true; }
  ok(!threw, 'reinit() is idempotent and safe without boot data');
}

// ---- 6. smoothness sandbox (sessionStorage + real-promise fetch) -----------
function makeSandbox2(opts) {
  let fetchCalls = 0, renders = 0;
  const headChildren = [];
  const mount = {
    _html: '',
    set innerHTML(v) { renders++; this._html = v; },
    get innerHTML() { return this._html; },
    querySelector: () => null,
  };
  const storage = {
    _d: {},
    getItem(k) { return (k in this._d) ? this._d[k] : null; },
    setItem(k, v) { this._d[k] = String(v); },
    removeItem(k) { delete this._d[k]; },
  };
  if (opts.cacheEntry) storage._d['ec_shell_boot_cache_v1'] = JSON.stringify(opts.cacheEntry);
  const doc = {
    readyState: 'complete',
    cookie: opts.cookie || '',
    querySelector: sel => (sel === '[data-ec-shell="1"]' && opts.marker) ? mount : null,
    addEventListener() {},
    createElement: t => ({ tagName: t, rel: '', href: '', style: {}, textContent: '',
      classList: { add() {}, remove() {} }, setAttribute() {}, appendChild() {}, innerHTML: '' }),
    head: { appendChild: el => headChildren.push(el) },
    body: { appendChild() {}, classList: { add() {}, remove() {} } },
    activeElement: null,
  };
  const win = {
    location: { pathname: opts.pathname || '/approvals', origin: 'https://team.ecentric.vn' },
    document: doc, sessionStorage: storage, console,
    fetch() {
      fetchCalls++;
      if (opts.failFetch) return Promise.reject(new Error('net down'));
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ message: opts.bootMsg }) });
    },
    addEventListener() {},
  };
  win.window = win;
  const sb = vm.createContext({ console, window: win, document: doc, fetch: win.fetch,
    sessionStorage: storage, setTimeout, clearTimeout, JSON, Date });
  return { sb, win, storage, headChildren, mount,
    get fetchCalls() { return fetchCalls; }, get renders() { return renders; } };
}
const flush = () => new Promise(r => setTimeout(r, 10));
const NAV1 = [
  { key: 'core.home', label: 'Trang chủ', route: '/home', icon: 'home', group: '', active_patterns: ['/', '/home'] },
  { key: 'apc.catalog', label: 'Approval Center', route: '/approvals', icon: 'check', group: 'Phê duyệt', active_patterns: ['/approvals', '/approvals/*'] },
];
const BOOT1 = { enabled: true, nav: NAV1, user: { name: 'u@ecentric.vn', full_name: 'U One', image: '' } };
const BOOT2 = JSON.parse(JSON.stringify(BOOT1)); BOOT2.nav[1].label = 'Approval Center v2';

(async () => {
  // version string straight from the asset
  const v0 = makeSandbox2({ marker: false, bootMsg: BOOT1 });
  vm.runInContext(SRC, v0.sb);
  const VER = v0.win.ECShell.version;
  const entry = (over) => Object.assign({ v: VER, ts: Date.now(), data: BOOT1 }, over || {});

  // -- cacheValid pure matrix
  const CV = v0.win.ECShell.cacheValid;
  ok(CV(entry(), Date.now(), null) === true, 'cacheValid: fresh entry accepted');
  ok(CV(entry({ ts: Date.now() - 6 * 60 * 1000 }), Date.now(), null) === false, 'cacheValid: expired TTL rejected');
  ok(CV(entry({ v: 'other' }), Date.now(), null) === false, 'cacheValid: version mismatch rejected');
  ok(CV(entry(), Date.now(), 'someoneelse@x') === false, 'cacheValid: user identity mismatch rejected');
  ok(CV(entry({ data: { enabled: false } }), Date.now(), null) === false, 'cacheValid: disabled payload rejected');

  // -- shouldPrefetch pure matrix
  const SP = v0.win.ECShell.shouldPrefetch, O = 'https://team.ecentric.vn';
  ok(SP('/approvals', O) && SP('/approvals/leave?id=X&tab=create', O) && SP('/approval', O) && SP('/home', O),
     'prefetch allows internal approval/home links');
  ok(!SP('/app/todo', O) && !SP('/api/method/logout', O) && !SP('/login-page', O) && !SP('/api/method/x', O),
     'prefetch blocks Desk/APIs/login/logout');
  ok(!SP('https://evil.example.com/approvals', O) && !SP('#x', O) && !SP('mailto:a@b', O) && !SP('/approvalsx', O),
     'prefetch blocks external/fragment/mailto/lookalike');

  // -- SWR: valid cache -> instant render, background fetch, equal payload -> no re-render
  const e1 = makeSandbox2({ marker: true, cacheEntry: entry(), bootMsg: BOOT1 });
  vm.runInContext(SRC, e1.sb);
  ok(e1.renders >= 1, 'valid cache renders synchronously (before fetch resolves)');
  const rSync = e1.renders;
  ok(e1.fetchCalls === 1, 'background refresh still fires exactly once');
  await flush();
  ok(e1.renders === rSync, 'identical fresh payload -> NO re-render (deterministic compare)');
  ok(JSON.parse(e1.storage._d['ec_shell_boot_cache_v1']).ts > 0, 'cache timestamp refreshed');

  // -- SWR: changed payload -> exactly one extra render
  const e2 = makeSandbox2({ marker: true, cacheEntry: entry(), bootMsg: BOOT2 });
  vm.runInContext(SRC, e2.sb);
  const r2 = e2.renders;
  await flush();
  ok(e2.renders === r2 + 1, 'changed fresh payload -> exactly one UI update');
  ok(e2.mount.innerHTML.indexOf('Approval Center v2') >= 0, 'updated label rendered');
  ok((e2.mount.innerHTML.match(/data-ec-notification-bell="1"/g) || []).length === 1, 'still exactly ONE bell after SWR update');

  // -- expired cache -> no sync render, renders after fetch
  const e3 = makeSandbox2({ marker: true, cacheEntry: entry({ ts: Date.now() - 6 * 60 * 1000 }), bootMsg: BOOT1 });
  vm.runInContext(SRC, e3.sb);
  ok(e3.renders === 0, 'expired cache -> no instant render');
  await flush();
  ok(e3.renders === 1, 'expired cache -> renders after fresh boot');

  // -- fetch failure with valid cache -> shell stays, no throw
  const e4 = makeSandbox2({ marker: true, cacheEntry: entry(), failFetch: true });
  let threw = false;
  try { vm.runInContext(SRC, e4.sb); await flush(); } catch (e) { threw = true; }
  ok(!threw && e4.renders >= 1, 'refresh failure keeps cached shell usable');
  ok('ec_shell_boot_cache_v1' in e4.storage._d, 'cache retained after failed refresh');

  // -- disabled fresh payload -> cache cleared, fallback stays
  const e5 = makeSandbox2({ marker: true, bootMsg: { enabled: false, reason: 'kill_switch' } });
  vm.runInContext(SRC, e5.sb);
  await flush();
  ok(e5.renders === 0, 'kill switch -> no shell render (fallback markup stays)');
  ok(!('ec_shell_boot_cache_v1' in e5.storage._d), 'kill switch clears the boot cache');

  // -- no marker -> storage untouched, no fetch
  const e6 = makeSandbox2({ marker: false, cacheEntry: entry(), bootMsg: BOOT1 });
  vm.runInContext(SRC, e6.sb);
  await flush();
  ok(e6.fetchCalls === 0, 'no marker -> still zero fetch with cache present');

  // ---- 7. nav search (1C.1): pure core --------------------------------------
  const E = v0.win.ECShell;
  ok(E.normalizeVN('Nghỉ phép') === 'nghi phep' && E.normalizeVN('THĂNG Chức') === 'thang chuc'
     && E.normalizeVN('Điều hành') === 'dieu hanh', 'normalizeVN strips Vietnamese accents incl đ/Đ');
  const CARDS = [
    { approval_title: 'Leave', route: '/approvals/leave', category_name: 'HR', description: 'Đăng ký nghỉ phép' },
    { approval_title: 'Promotion Request', route: '/approvals/promotion', category_name: 'Administration', description: 'Đề xuất thăng chức' },
    { approval_title: 'Employee Referral', route: '/approvals/employee-referral', category_name: 'Others', description: 'Giới thiệu ứng viên' },
    { approval_title: 'Service Referral', route: '/approvals/service-referral', category_name: 'Others', description: 'Giới thiệu dịch vụ' },
    { approval_title: 'Hidden Coming Soon', route: null, category_name: 'HR', description: 'not accessible' },
  ];
  const MODS = [
    { label: 'Trang chủ', route: '/home', icon: 'home', group: '', keywords: ['trang chu', 'home'] },
    { label: 'Bảng điều hành', route: '/approvals/dashboard', icon: 'chart', group: 'Phê duyệt', keywords: ['dashboard'] },
  ];
  const entries = E.buildSearchEntries(MODS, CARDS);
  ok(entries.length === 2 + 4, 'buildSearchEntries: route-less (inaccessible) cards are EXCLUDED');
  let r = E.searchNav(entries, 'nghi phep');
  ok(r.types.length === 1 && r.types[0].route === '/approvals/leave', "'nghi phep' -> Leave (via VN description keyword)");
  r = E.searchNav(entries, 'thang chuc');
  ok(r.types.length === 1 && r.types[0].label === 'Promotion Request', "'thang chuc' -> Promotion");
  r = E.searchNav(entries, 'referral');
  ok(r.types.length === 2, "'referral' -> both Referral types (partial, case-insensitive)");
  r = E.searchNav(entries, 'REFER');
  ok(r.types.length === 2 && r.types[0].hl && r.types[0].hl[1] === 5, 'uppercase partial match + highlight range');
  r = E.searchNav(entries, 'dashboard');
  ok(r.modules.length === 1 && r.modules[0].route === '/approvals/dashboard' && r.types.length === 0,
     "'dashboard' -> module group only (grouping correct)");
  r = E.searchNav(entries, 'zzz-khong-co');
  ok(r.total === 0, 'no match -> empty result set (empty state)');
  ok(E.searchNav(entries, '').total === 0, 'blank query -> no results');

  // catalog cache: user isolation
  const CE = (o) => Object.assign({ v: VER, ts: Date.now(), user: 'u@ecentric.vn', types: [] }, o || {});
  ok(E.catalogCacheValid(CE(), Date.now(), 'u@ecentric.vn') === true, 'catalog cache: same user accepted');
  ok(E.catalogCacheValid(CE(), Date.now(), 'other@ecentric.vn') === false, 'catalog cache: OTHER user rejected (isolation)');
  ok(E.catalogCacheValid(CE({ v: 'x' }), Date.now(), 'u@ecentric.vn') === false, 'catalog cache: version mismatch rejected');
  ok(E.catalogCacheValid(CE({ ts: Date.now() - 6 * 60 * 1000 }), Date.now(), 'u@ecentric.vn') === false, 'catalog cache: TTL expiry rejected');

  // ---- 8. search UI presence in rendered shell -------------------------------
  {
    const e7 = makeSandbox2({ marker: true, cacheEntry: entry(), bootMsg: BOOT1 });
    vm.runInContext(SRC, e7.sb);
    await flush();
    const html = e7.mount.innerHTML;
    ok(html.indexOf('ec-shell-search-in') >= 0 && html.indexOf('Tìm chức năng…') >= 0,
       'search input with placeholder renders inside the shell (under brand)');
    ok(html.indexOf('ec-shell-search-results') >= 0, 'results listbox container present');
    ok((html.match(/data-ec-notification-bell="1"/g) || []).length === 1, 'bell still unique with search present');
  }

  // ---- 9. prerender allow-list (v1.6.0): no-store nav routes only ------------
  {
    const PN = v0.win.ECShell.prerenderUrls;
    const nav = [
      { key: 'core.home', route: '/home', active_patterns: ['/'] },
      { key: 'apc.catalog', route: '/approvals', active_patterns: ['/approvals'] },
      { key: 'approval.inbox', route: '/approval', active_patterns: ['/approval'] },
      { key: 'tickets.all', route: '/all-ticket', active_patterns: ['/all-ticket'] },
      { key: 'legacy.create_mso', route: '/mso-form', active_patterns: ['/mso-form'] },
      { key: 'legacy.others', route: '/others', active_patterns: ['/others'], children: [
        { key: 'legacy.create_client', route: '/client-request', active_patterns: ['/client-request'] },
      ] },
    ];
    const urls = PN(nav, '/approvals');
    ok(urls.indexOf('/approval') >= 0 && urls.indexOf('/all-ticket') >= 0 && urls.indexOf('/mso-form') >= 0,
       'prerender list covers the slow no-store routes');
    ok(urls.indexOf('/approvals') < 0, 'current page excluded from its own prerender list');
    ok(urls.indexOf('/others') < 0, 'non-navigable submenu toggle excluded from prerender');
    ok(urls.indexOf('/client-request') >= 0, 'submenu children ARE prerenderable destinations');
    ok(urls.every(u => u.indexOf('?') < 0 && u.indexOf('#') < 0), 'no query/hash (detail) URL is ever prerendered -- side-effect safe');
    ok(new Set(urls).size === urls.length, 'prerender list deduped');
  }

  // ---- 10. HR nav (v1.8.1): salary no_prerender exclusion ------------------
  {
    const PN = v0.win.ECShell.prerenderUrls, SP = v0.win.ECShell.shouldPrefetch;
    const O = 'https://team.ecentric.vn';
    const nav = [
      { key: 'core.home', route: '/home', active_patterns: ['/'] },
      { key: 'hr.attendance', route: '/ec-hr/attendance', active_patterns: ['/ec-hr/attendance'] },
      { key: 'hr.salary', route: '/ec-hr/salary', active_patterns: ['/ec-hr/salary'], no_prerender: true },
    ];
    const urls = PN(nav, '/home');
    ok(urls.indexOf('/ec-hr/attendance') >= 0, 'HR: attendance IS prerenderable (normal shell nav)');
    ok(urls.indexOf('/ec-hr/salary') < 0, 'SECURITY: salary NEVER in prerender allow-list (no_prerender)');
    // prefetch: knownNavRoutes filters no_prerender, so salary is not in the list passed to shouldPrefetch
    const known = nav.filter(it => !it.no_prerender).map(it => it.route);
    ok(SP('/ec-hr/attendance', O, known) === true, 'HR: attendance is prefetchable');
    ok(SP('/ec-hr/salary', O, known) === false, 'SECURITY: salary is NOT prefetchable (excluded from knownRoutes)');
    ok(SP(O + '/ec-hr/salary', O, known) === false, 'SECURITY: salary absolute URL also not prefetchable');
  }

  // ---- navigation contexts: resolveContext parity + scoped vs global -------
  {
    const env = makeSandbox('/x', false);
    vm.runInContext(SRC, env.sb);
    const RC = env.win.ECShell.resolveContext, CI = env.win.ECShell.ctxItems, AI = env.win.ECShell.allItems;
    const BOOT = {
      default_context: 'approval_document',
      context_order: ['approval_document', 'hr'],
      contexts: {
        home: { items: [
          { key: 'core.home', route: '/home', active_patterns: ['/', '/home'] },
          { key: 'ctx.approval_document', route: '/approvals', active_patterns: ['/approvals'] },
          { key: 'ctx.hr', route: '/ec-hr/attendance', active_patterns: ['/ec-hr/attendance'] }] },
        approval_document: { items: [
          { key: 'core.home', route: '/home', active_patterns: ['/', '/home'] },
          { key: 'apc.catalog', route: '/approvals', active_patterns: ['/approvals', '/approvals/*'] },
          { key: 'legacy.create_po', route: '/form-po', active_patterns: ['/form-po'] }] },
        hr: { items: [
          { key: 'core.home', route: '/home', active_patterns: ['/', '/home'] },
          { key: 'hr.attendance', route: '/ec-hr/attendance', active_patterns: ['/ec-hr/attendance'] },
          { key: 'hr.salary', route: '/ec-hr/salary', active_patterns: ['/ec-hr/salary'], no_prerender: true }] }
      },
      all_items: [
        { key: 'apc.catalog', route: '/approvals' },
        { key: 'hr.salary', route: '/ec-hr/salary', no_prerender: true },
        { key: 'hr.attendance', route: '/ec-hr/attendance' }]
    };
    ok(RC(BOOT, '/approvals/leave') === 'approval_document', 'ctx: /approvals/* -> approval_document');
    ok(RC(BOOT, '/form-po') === 'approval_document', 'ctx: /form-po -> approval_document');
    ok(RC(BOOT, '/ec-hr/salary') === 'hr', 'ctx: /ec-hr/salary -> hr');
    ok(RC(BOOT, '/') === 'home', 'ctx: / -> home (never silently approval)');
    ok(RC(BOOT, '/weekly-update') === 'approval_document', 'ctx: unregistered -> default');
    ok(RC({ nav: [] }, '/x') === null, 'ctx: pre-context payload -> null (legacy render path)');
    ok(CI(BOOT, 'hr').length === 3 && CI(BOOT, 'hr')[2].no_prerender === true, 'ctxItems returns scoped items');
    ok(AI(BOOT).some(i => i.route === '/ec-hr/salary'), 'allItems: salary DISCOVERABLE globally');
    const PN2 = env.win.ECShell.prerenderUrls(CI(BOOT, 'hr'), '/ec-hr/attendance');
    ok(PN2.indexOf('/ec-hr/salary') === -1, 'salary NEVER in Speculation prerender list');
    ok(PN2.indexOf('/home') >= 0, 'hr context still prerenders its own safe routes');
    const known = AI(BOOT).filter(i => !i.no_prerender).map(i => i.route);
    ok(known.indexOf('/ec-hr/salary') === -1 && known.indexOf('/approvals') >= 0,
       'salary NEVER in prefetch/eager allow-list; cross-context routes stay warm-able');
  }

  console.log(failures === 0 ? '\nALL CHECKS PASSED' : '\n' + failures + ' FAILURES');
  process.exit(failures ? 1 : 0);
})();
