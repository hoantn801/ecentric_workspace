// Harness chay ec_shell.js THAT trong jsdom cho test_server_nav.py (khong can site).
//
//   node server_nav_harness.js parity  <fixture.json>
//   node server_nav_harness.js hydrate <fixture.json>
//
// parity : in navHtml()/navSig() cua JS cho tung case -> Python so voi ban server.
// hydrate: dung trang tu `html` (menu do server dung san), cho fetch boot tra `boot`,
//          chay ec_shell.js, roi bao: node <nav> con NGUYEN hay bi ve lai, thuoc tinh
//          tren mount, ten tren the nguoi dung, so link trong menu.
// Ket qua in ra stdout dang JSON mot dong. Loi thi exit 1 kem thong diep.
'use strict';
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'public', 'js', 'ec_shell.js'), 'utf8');
const mode = process.argv[2];
const fixture = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

function parity() {
  const vm = require('vm');
  const win = { location: { pathname: '/nowhere' }, addEventListener() {}, console };
  win.window = win;
  const doc = { readyState: 'complete', querySelector: () => null, addEventListener() {} };
  const sb = vm.createContext({ window: win, document: doc, console });
  vm.runInContext(SRC, sb);
  const E = win.ECShell;
  const out = fixture.cases.map(c => ({
    name: c.name,
    html: E.navHtml(c.items, c.active),
    sig: E.navSig(c.context, c.items, c.active),
  }));
  process.stdout.write(JSON.stringify(out));
}

async function hydrate() {
  const { JSDOM } = require('jsdom');
  const dom = new JSDOM('<!DOCTYPE html><html><body><div class="page_content">' + fixture.html +
                        '</div></body></html>',
                        { url: 'https://team.ecentric.vn' + fixture.pathname, runScripts: 'outside-only' });
  const w = dom.window;
  const bootUrl = '/api/method/ecentric_workspace.shell.api.get_shell_boot';
  w.fetch = (url) => {
    const u = String(url);
    const body = u.indexOf(bootUrl) >= 0 ? { message: fixture.boot } : { message: {} };
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
  };
  const mount = w.document.querySelector('[data-ec-shell="1"]');
  const navBefore = mount ? mount.querySelector('.ec-shell-nav') : null;
  w.eval(SRC);
  await new Promise(r => setTimeout(r, 60));
  const navAfter = mount ? mount.querySelector('.ec-shell-nav') : null;
  const name = mount && mount.querySelector('.ec-shell-username');
  process.stdout.write(JSON.stringify({
    hasMount: !!mount,
    navKept: !!navBefore && navBefore === navAfter,
    sig: mount ? mount.getAttribute('data-ec-nav-sig') : null,
    ctx: mount ? mount.getAttribute('data-ec-context') : null,
    username: name ? name.textContent : null,
    links: mount ? mount.querySelectorAll('.ec-shell-nav a').length : -1,
    logout: mount ? mount.querySelectorAll('[data-ec-shell-logout]').length : -1,
  }));
}

try {
  if (mode === 'parity') parity();
  else if (mode === 'hydrate') hydrate().catch(e => { console.error(e && e.stack || e); process.exit(1); });
  else { console.error('mode must be parity|hydrate'); process.exit(1); }
} catch (e) {
  console.error(e && e.stack || e);
  process.exit(1);
}
