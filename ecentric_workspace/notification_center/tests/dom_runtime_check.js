// Behavioural runtime check for the Notification Center global asset.
// Runs the REAL asset against a minimal DOM/frappe stub and asserts the badge
// matrix (0/1/9/10+), single badge + single dropdown, reinstall-no-duplicate,
// the Frappe-Desk guard, and that a legacy bell handler is stripped on adopt.
//
//   node ecentric_workspace/notification_center/tests/dom_runtime_check.js
// Exits non-zero on the first failed assertion.
'use strict';
const fs = require('fs');
const path = require('path');
const ASSET = path.join(__dirname, '..', '..', 'public', 'js', 'notification_center.js');
const SRC = fs.readFileSync(ASSET, 'utf8');

let failures = 0;
function ok(cond, msg) { if (!cond) { failures++; console.error('FAIL: ' + msg); } else { console.log('ok  - ' + msg); } }

// ---- tiny DOM ----
function mkClassList() {
  const set = new Set();
  return {
    add: (...c) => c.forEach(x => set.add(x)),
    remove: (...c) => c.forEach(x => set.delete(x)),
    toggle: (c, on) => { const v = on === undefined ? !set.has(c) : !!on; v ? set.add(c) : set.delete(c); return v; },
    contains: (c) => set.has(c),
    _set: set,
  };
}
class El {
  constructor(tag) { this.tagName = (tag || 'div').toUpperCase(); this.children = []; this.parentNode = null;
    this.attrs = {}; this.style = {}; this.classList = mkClassList(); this._html = ''; this.textContent = '';
    this._listeners = {}; this.id = ''; }
  set className(v) { this._cn = v; String(v || '').split(/\s+/).filter(Boolean).forEach(c => this.classList.add(c)); }
  get className() { return this._cn || ''; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'id') this.id = String(v); }
  getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; }
  removeAttribute(k) { delete this.attrs[k]; }
  set innerHTML(v) { this._html = v; this.children = [];
    const re = /id="([^"]+)"/g; let m;
    while ((m = re.exec(v))) { const e = new El('div'); e.setAttribute('id', m[1]); this.appendChild(e); } }
  get innerHTML() { return this._html; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; return c; }
  replaceChild(nw, old) { const i = this.children.indexOf(old); if (i >= 0) { this.children[i] = nw; nw.parentNode = this; old.parentNode = null; } return old; }
  cloneNode() { const e = new El(this.tagName); e.attrs = Object.assign({}, this.attrs); e._cn = this._cn;
    String(this._cn || '').split(/\s+/).filter(Boolean).forEach(c => e.classList.add(c)); e.id = this.id; return e; }
  contains(n) { if (n === this) return true; return this.children.some(c => c.contains && c.contains(n)); }
  addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); }
  dispatch(t, ev) { (this._listeners[t] || []).slice().forEach(fn => fn(ev)); }
  focus() {}
  getBoundingClientRect() { return { bottom: 40, right: 200, top: 10, left: 180 }; }
  querySelector(sel) { return this._find(sel, false); }
  querySelectorAll(sel) { return this._find(sel, true); }
  _find(sel, all) {
    const acc = [];
    const walk = (n) => { n.children.forEach(c => { if (c._match(sel)) acc.push(c); walk(c); }); };
    walk(this);
    return all ? acc : (acc[0] || null);
  }
  _match(sel) {
    if (sel === '.dot') return this.classList.contains('dot');
    if (sel === '.ec-nc-badge') return this.classList.contains('ec-nc-badge');
    if (sel === '#ec-nc-list') return this.id === 'ec-nc-list';
    if (sel === '#ec-nc-allread') return this.id === 'ec-nc-allread';
    if (sel === '#ec-nc-mute') return this.id === 'ec-nc-mute';
    return false;
  }
}

function freshEnv(pathname, bell) {
  const head = new El('head'); const body = new El('body');
  const docListeners = {};
  const byId = {};
  const document = {
    readyState: 'complete', head, body,
    createElement: (t) => new El(t),
    getElementById: (id) => byId[id] || null,
    addEventListener: (t, fn) => { (docListeners[t] = docListeners[t] || []).push(fn); },
    _dispatch: (t, ev) => (docListeners[t] || []).slice().forEach(fn => fn(ev)),
    querySelector: (sel) => {
      if (sel.indexOf('notification-log') >= 0) return bell;       // findBell primary
      return null;
    },
    querySelectorAll: () => [],
  };
  // track elements that set an id (for getElementById of pop + css)
  const _origAppendHead = head.appendChild.bind(head);
  head.appendChild = (c) => { if (c.id) byId[c.id] = c; return _origAppendHead(c); };
  const _origAppendBody = body.appendChild.bind(body);
  body.appendChild = (c) => { if (c.id) byId[c.id] = c; return _origAppendBody(c); };

  const store = {};
  const calls = [];
  const window = {
    location: { pathname: pathname },
    localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
    addEventListener: () => {},
    frappe: { call: (o) => { calls.push(o); } },
    AudioContext: null,
  };
  window.window = window;
  return { window, document, calls, byId, bell };
}

function run(env) {
  const fn = new Function('window', 'document', 'console', SRC + '\n//# sourceURL=nc.js');
  fn(env.window, env.document, console);
}

// helper: feed a frappe.call callback the given unread count
function feedUnread(env, n) {
  // refreshCount uses get_unread_count GET; reply via its callback
  const c = env.calls.find(c => c.method.endsWith('get_unread_count'));
  if (c && c.callback) c.callback({ message: { success: true, unread: n } });
}

// ---------- 1) badge matrix on a normal shell page ----------
(function () {
  const bell = new El('a'); bell.setAttribute('href', '/app/notification-log'); bell.className = 'icon-btn';
  const dot = new El('span'); dot.className = 'dot'; bell.appendChild(dot);
  const env = freshEnv('/overview', bell);
  run(env);
  // after adopt, the bell in DOM is a clone; grab it from the stubbed querySelector path:
  // our document.querySelector always returns the ORIGINAL bell ref; the asset replaced
  // it only if parentNode existed. We gave no parent, so adopt returns original -> same ref.
  const theBell = bell;
  const badge = theBell.querySelector('.ec-nc-badge');
  ok(!!badge, 'badge element mounted on the native bell');
  ok(theBell.querySelectorAll('.ec-nc-badge').length === 1, 'exactly one badge on the bell');

  feedUnread(env, 0);
  ok(badge.classList.contains('on') === false, 'unread 0 -> badge hidden (no .on)');

  feedUnread(env, 1);
  ok(badge.classList.contains('on') === true && badge.textContent === '1' && !badge.classList.contains('ec-nc-badge--pill'),
     'unread 1 -> visible circle "1" (no pill)');

  feedUnread(env, 9);
  ok(badge.textContent === '9' && !badge.classList.contains('ec-nc-badge--pill'),
     'unread 9 -> circle "9" (no pill)');

  feedUnread(env, 10);
  ok(badge.textContent === '9+' && badge.classList.contains('ec-nc-badge--pill'),
     'unread 10 -> "9+" pill');

  feedUnread(env, 250);
  ok(badge.textContent === '9+' && badge.classList.contains('ec-nc-badge--pill'),
     'unread 250 -> still "9+" pill (capped)');

  feedUnread(env, 0);
  ok(badge.classList.contains('on') === false, 'back to 0 -> badge hidden again');

  // single dropdown in body
  const pops = env.document.body.children.filter(c => c.classList.contains('ec-nc-pop'));
  ok(pops.length === 1, 'exactly one dropdown appended to body');
})();

// ---------- 2) reinstall (asset loaded twice) -> no duplicate ----------
(function () {
  const bell = new El('a'); bell.setAttribute('href', '/app/notification-log'); bell.className = 'icon-btn';
  const env = freshEnv('/approval', bell);
  run(env);
  // simulate the homepage double-load: same window, run again
  run(env);
  ok(bell.querySelectorAll('.ec-nc-badge').length === 1, 'reinstall -> still one badge (single-install guard)');
  const pops = env.document.body.children.filter(c => c.classList.contains('ec-nc-pop'));
  ok(pops.length === 1, 'reinstall -> still one dropdown');
})();

// ---------- 3) Frappe Desk guard ----------
(function () {
  const bell = new El('a'); bell.setAttribute('href', '/app/notification-log'); bell.className = 'icon-btn';
  const env = freshEnv('/app/some-desk-page', bell);
  run(env);
  ok(bell.querySelector('.ec-nc-badge') === null, 'on /app/* (Frappe Desk) the asset does NOT mount a badge');
  ok(env.calls.length === 0, 'on Frappe Desk the asset makes no API calls (fully inert)');
})();

// ---------- 4) legacy "feature in development" handler is stripped on adopt ----------
(function () {
  const root = new El('div');               // give the bell a parent so adopt can replace it
  const bell = new El('a'); bell.setAttribute('href', '/app/notification-log'); bell.className = 'icon-btn';
  bell.setAttribute('onclick', "alert('Tính năng đang phát triển')");
  let legacyFired = 0; bell.addEventListener('click', () => { legacyFired++; });
  root.appendChild(bell);
  const env = freshEnv('/tasks', bell);
  // make findBell return our bell, and let adopt replace within root
  run(env);
  const adopted = root.children[0];
  ok(adopted !== bell, 'native bell is replaced by a clean clone (legacy listeners dropped)');
  ok(adopted.getAttribute('onclick') === null, 'inline onclick legacy handler removed');
  ok(adopted.getAttribute('href') === '/app/notification-log', 'clone keeps href (Ctrl/Cmd/middle-click still native)');
  // plain left click -> our handler intercepts + stops propagation; legacy never fires
  let stopped = 0;
  adopted.dispatch('click', { button: 0, preventDefault(){}, stopPropagation(){ stopped++; }, stopImmediatePropagation(){ stopped++; } });
  ok(stopped >= 1, 'plain left-click calls stopPropagation (defeats document-level legacy toast)');
  ok(legacyFired === 0, 'legacy click listener never fires after adopt');
})();

if (failures) { console.error('\n' + failures + ' assertion(s) FAILED'); process.exit(1); }
console.log('\nAll runtime assertions passed.');
process.exit(0);
