// Click-behaviour proof for the Notification Center global asset.
// Executes the REAL asset against a mini-DOM that models event BUBBLING, the onclick
// PROPERTY handler, the inline onclick ATTRIBUTE, addEventListener listeners and a
// DOCUMENT-level delegated handler. For each shell route it proves:
//   * plain left-click  -> opens the NC dropdown, fires NO legacy handler (any form),
//                          and cancels native nav (preventDefault)
//   * Ctrl-click / middle-click -> does NOT open the dropdown, keeps native nav
//                          (no preventDefault), still fires NO legacy handler
//   * Frappe Desk (/app/...) and a public page with no bell -> fully inert, no error
//
//   node ecentric_workspace/notification_center/tests/bell_click_check.js
'use strict';
const fs = require('fs');
const path = require('path');
const SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'public', 'js', 'notification_center.js'), 'utf8');

let failures = 0;
function ok(c, m) { if (!c) { failures++; console.error('FAIL: ' + m); } else { console.log('ok  - ' + m); } }

function mkClassList() {
  const set = new Set();
  return { add: (...c) => c.forEach(x => set.add(x)), remove: (...c) => c.forEach(x => set.delete(x)),
    toggle: (c, on) => { const v = on === undefined ? !set.has(c) : !!on; v ? set.add(c) : set.delete(c); return v; },
    contains: (c) => set.has(c) };
}
class El {
  constructor(tag) { this.tagName = (tag || 'div').toUpperCase(); this.children = []; this.parentNode = null;
    this.attrs = {}; this.style = {}; this.classList = mkClassList(); this.textContent = ''; this.id = '';
    this._l = {}; this.onclick = null; }
  set className(v) { this._cn = v; String(v || '').split(/\s+/).filter(Boolean).forEach(c => this.classList.add(c)); }
  get className() { return this._cn || ''; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'id') this.id = String(v); }
  getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; }
  removeAttribute(k) { delete this.attrs[k]; }
  set innerHTML(v) { this._html = v; this.children = []; const re = /id="([^"]+)"/g; let m;
    while ((m = re.exec(v))) { const e = new El('div'); e.setAttribute('id', m[1]); this.appendChild(e); } }
  get innerHTML() { return this._html || ''; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; return c; }
  replaceChild(nw, old) { const i = this.children.indexOf(old); if (i >= 0) { this.children[i] = nw; nw.parentNode = this; old.parentNode = null; } return old; }
  cloneNode() { const e = new El(this.tagName); e.attrs = Object.assign({}, this.attrs); e._cn = this._cn;
    String(this._cn || '').split(/\s+/).filter(Boolean).forEach(c => e.classList.add(c)); e.id = this.id; return e; }
  contains(n) { if (n === this) return true; return this.children.some(c => c.contains && c.contains(n)); }
  addEventListener(t, fn) { (this._l[t] = this._l[t] || []).push(fn); }
  focus() {}
  getBoundingClientRect() { return { bottom: 40, right: 200, top: 10, left: 180 }; }
  querySelector(sel) { return this._find(sel, false); }
  querySelectorAll(sel) { return this._find(sel, true); }
  _find(sel, all) { const acc = []; const walk = (n) => n.children.forEach(c => { if (c._match(sel)) acc.push(c); walk(c); }); walk(this); return all ? acc : (acc[0] || null); }
  _match(sel) {
    if (sel === '.dot') return this.classList.contains('dot');
    if (sel === '.ec-nc-badge') return this.classList.contains('ec-nc-badge');
    if (sel === '#ec-nc-list') return this.id === 'ec-nc-list';
    if (sel === '#ec-nc-allread') return this.id === 'ec-nc-allread';
    if (sel === '#ec-nc-mute') return this.id === 'ec-nc-mute';
    return false;
  }
}

function makeDoc() {
  const head = new El('head'); const body = new El('body');
  const byId = {}; const docL = {}; let theBell = null;
  const register = (c) => { if (c.id) byId[c.id] = c; };
  const _h = head.appendChild.bind(head); head.appendChild = (c) => { register(c); return _h(c); };
  const _b = body.appendChild.bind(body); body.appendChild = (c) => { register(c); return _b(c); };
  const document = {
    readyState: 'complete', head, body, _docL: docL,
    createElement: (t) => new El(t),
    getElementById: (id) => byId[id] || null,
    addEventListener: (t, fn) => { (docL[t] = docL[t] || []).push(fn); },
    querySelector: (sel) => (sel.indexOf('notification-log') >= 0 ? theBell : null),
    querySelectorAll: () => [],
    setBell: (b) => { theBell = b; },
  };
  return document;
}

// Dispatch a click that BUBBLES target -> ancestors -> document, honouring
// stopPropagation / stopImmediatePropagation, the onclick property, the inline
// onclick attribute (legacy), and addEventListener listeners.
function dispatchClick(document, target, init) {
  init = init || {};
  const ev = { type: 'click', target, button: init.button || 0,
    metaKey: !!init.metaKey, ctrlKey: !!init.ctrlKey, shiftKey: !!init.shiftKey, altKey: !!init.altKey,
    defaultPrevented: false, _stop: false, _stopImm: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this._stop = true; },
    stopImmediatePropagation() { this._stop = true; this._stopImm = true; } };
  const path = []; let n = target; while (n) { path.push(n); n = n.parentNode; } path.push(document);
  for (const node of path) {
    // inline onclick attribute (legacy) fires first on the element, like a browser
    if (node.getAttribute && node.getAttribute('onclick') && node._inlineHandler) node._inlineHandler(ev);
    const ls = (node._l && node._l.click) || (node._docL && node._docL.click) || [];
    for (const fn of ls.slice()) { fn(ev); if (ev._stopImm) break; }
    if (node.onclick) node.onclick(ev);
    if (ev._stop) break;
  }
  return ev;
}

function buildEnv(pathname, withBell) {
  const document = makeDoc();
  const root = new El('div'); document.body.appendChild(root);
  let bell = null, legacy = { inline: 0, prop: 0, addEL: 0, delegated: 0 };
  if (withBell) {
    bell = new El('a'); bell.setAttribute('href', '/app/notification-log'); bell.className = 'icon-btn';
    const dot = new El('span'); dot.className = 'dot'; bell.appendChild(dot);
    root.appendChild(bell);
    document.setBell(bell);
    // LEGACY "feature in development" handler installed in ALL forms:
    bell.setAttribute('onclick', "ecToast('Tính năng đang phát triển')");   // inline attribute
    bell._inlineHandler = () => { legacy.inline++; };                       // its effect
    bell.onclick = () => { legacy.prop++; };                                // property handler
    bell.addEventListener('click', () => { legacy.addEL++; });              // addEventListener
    document.addEventListener('click', (e) => {                            // document-delegated
      let t = e.target; let hit = false; while (t) { if (t === bell || (t.getAttribute && t.getAttribute('data-ec-nc'))) { hit = true; break; } t = t.parentNode; }
      if (hit) legacy.delegated++;
    });
  }
  const calls = [];
  const win = { location: { pathname }, addEventListener: () => {},
    localStorage: { _s: {}, getItem(k){ return k in this._s ? this._s[k] : null; }, setItem(k,v){ this._s[k]=String(v); } },
    frappe: { call: (o) => { calls.push(o);
      if (o.method.endsWith('get_unread_count') && o.callback) o.callback({ message: { success: true, unread: 3 } });
      if (o.method.endsWith('get_notifications') && o.callback) o.callback({ message: { success: true, unread: 3, items: [] } });
    } }, AudioContext: null };
  win.window = win;
  return { document, win, root, bell, legacy, calls };
}

function run(env) { new Function('window', 'document', 'console', SRC)(env.win, env.document, console); }
function adoptedBell(env) { return env.root.children.find(c => c.getAttribute && c.getAttribute('data-ec-nc') === '1'); }
function popOpen(env) { const p = env.document.getElementById('ec-nc-pop-root'); return !!(p && p.classList.contains('on')); }

['/home', '/overview', '/approval'].forEach(function (route) {
  const env = buildEnv(route, true);
  run(env);
  const bell = adoptedBell(env);
  ok(!!bell, route + ': native bell adopted (clean clone in DOM)');
  ok(bell.getAttribute('onclick') === null, route + ': inline onclick attribute removed');
  ok(!bell.onclick, route + ': onclick property handler not present on clone');
  ok(((bell._l && bell._l.click) || []).length === 1, route + ': only the asset click handler on the bell (legacy addEventListener dropped)');

  // ---- plain left-click ----
  let ev = dispatchClick(env.document, bell, { button: 0 });
  ok(popOpen(env) === true, route + ': plain left-click OPENS the NC dropdown');
  ok(ev.defaultPrevented === true, route + ': plain left-click cancels native nav (preventDefault)');
  ok(env.legacy.inline === 0 && env.legacy.prop === 0 && env.legacy.addEL === 0 && env.legacy.delegated === 0,
     route + ': plain left-click fires NO legacy handler (no "đang phát triển" toast)');

  // close again before modifier tests
  dispatchClick(env.document, env.document.body, { button: 0 });

  // ---- Ctrl-click (open in new tab / native) ----
  const before = Object.assign({}, env.legacy);
  ev = dispatchClick(env.document, bell, { button: 0, ctrlKey: true });
  ok(popOpen(env) === false, route + ': Ctrl-click does NOT open the dropdown');
  ok(ev.defaultPrevented === false, route + ': Ctrl-click keeps native /app/notification-log nav');
  ok(env.legacy.inline === before.inline && env.legacy.prop === before.prop && env.legacy.addEL === before.addEL && env.legacy.delegated === before.delegated,
     route + ': Ctrl-click fires NO legacy handler');

  // ---- middle-click ----
  ev = dispatchClick(env.document, bell, { button: 1 });
  ok(popOpen(env) === false, route + ': middle-click does NOT open the dropdown');
  ok(ev.defaultPrevented === false, route + ': middle-click keeps native nav');
});

// Frappe Desk: inert
(function () {
  const env = buildEnv('/app/build', true);
  run(env);
  ok(adoptedBell(env) === undefined && env.calls.length === 0, '/app/* (Frappe Desk): asset inert (no adopt, no API, no Desk bind)');
})();

// public page with no eCentric bell: no error, inert
(function () {
  const env = buildEnv('/login', false);
  let threw = false; try { run(env); } catch (e) { threw = true; }
  ok(!threw, '/login (no bell): asset loads without error');
  ok(env.calls.length === 0, '/login (no bell): asset stays inert');
})();

if (failures) { console.error('\n' + failures + ' assertion(s) FAILED'); process.exit(1); }
console.log('\nAll click-behaviour assertions passed.');
process.exit(0);
