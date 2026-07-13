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
    { key: 'apc.legacy_tickets', route: '/approval', active_patterns: ['/approval'] },
  ];
  ok(M(NAV, '/approvals/hr-activity') === 'apc.catalog', 'hr-activity highlights Approval Center (bug fixed via registry matching)');
  ok(M(NAV, '/approvals/dashboard') === 'apc.dashboard', 'exact route outranks catalog prefix pattern');
  ok(M(NAV, '/approvals') === 'apc.catalog', 'catalog exact');
  ok(M(NAV, '/approvals/') === 'apc.catalog', 'trailing slash normalized');
  ok(M(NAV, '/approval') === 'apc.legacy_tickets', 'legacy /approval matches ONLY its exact item (no prefix bleed)');
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

console.log(failures === 0 ? '\nALL CHECKS PASSED' : '\n' + failures + ' FAILURES');
process.exit(failures ? 1 : 0);
