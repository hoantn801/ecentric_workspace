// Unit + wiring tests for the shared ec_datepicker.
// Run WITHOUT a bench:  node ecentric_workspace/public/js/tests/test_ec_datepicker.js
'use strict';
const fs = require('fs');
const path = require('path');
const D = require('../ec_datepicker.js');            // pure exports (no DOM)
const SRC = fs.readFileSync(path.join(__dirname, '..', 'ec_datepicker.js'), 'utf8');
const CSS = fs.readFileSync(path.join(__dirname, '..', '..', 'css', 'ec_datepicker.bundle.css'), 'utf8');
const HOOKS = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'hooks.py'), 'utf8');

let failures = 0;
function ok(c, m) { if (!c) { failures++; console.error('FAIL: ' + m); } else { console.log('ok  - ' + m); } }
function eq(a, b, m) { ok(JSON.stringify(a) === JSON.stringify(b), m + ' (got ' + JSON.stringify(a) + ')'); }

// ---- parseNative ----
eq(D.parseNative('2026-08-07'), { y: 2026, m: 8, d: 7, hh: 0, mm: 0 }, 'parse date');
eq(D.parseNative('2026-08-07T14:30'), { y: 2026, m: 8, d: 7, hh: 14, mm: 30 }, 'parse datetime');
ok(D.parseNative('') === null, 'parse empty -> null');
ok(D.parseNative('garbage') === null, 'parse garbage -> null');

// ---- serialize / display (value preservation) ----
const o = { y: 2026, m: 8, d: 7, hh: 14, mm: 5 };
ok(D.toNative(o, false) === '2026-08-07', 'toNative date');
ok(D.toNative(o, true) === '2026-08-07T14:05', 'toNative datetime (zero-padded)');
ok(D.toDisplay(o, false) === '07/08/2026', 'toDisplay vi-VN date');
ok(D.toDisplay(o, true) === '07/08/2026 14:05', 'toDisplay vi-VN datetime');
// round-trip: native -> parse -> native is identity
ok(D.toNative(D.parseNative('2026-12-31T09:00'), true) === '2026-12-31T09:00', 'round-trip datetime identity');

// ---- calendar math ----
ok(D.daysInMonth(2026, 2) === 28, 'Feb 2026 = 28 days');
ok(D.daysInMonth(2024, 2) === 29, 'Feb 2024 = 29 days (leap)');
ok(D.daysInMonth(2026, 4) === 30, 'Apr = 30 days');
ok(D.firstDow(2024, 1) === 0, 'Jan 1 2024 was Monday -> firstDow 0 (Monday-first)');
const g = D.buildGrid(2024, 1);
ok(g.length % 7 === 0, 'grid is whole weeks');
ok(g[0] === 1 && g[30] === 31, 'Jan 2024 grid starts at 1, has 31');
ok(D.buildGrid(2026, 2).filter(x => x != null).length === 28, 'Feb 2026 grid has 28 real cells');

// ---- range + clamp ----
ok(D.cmpDate({ y: 2026, m: 8, d: 7 }, '2026-08-10') === -1, 'cmpDate before');
ok(D.cmpDate({ y: 2026, m: 8, d: 7 }, '2026-08-01') === 1, 'cmpDate after');
ok(D.cmpDate({ y: 2026, m: 8, d: 7 }, '2026-08-07') === 0, 'cmpDate equal');
ok(D.cmpDate({ y: 2026, m: 8, d: 7 }, '') === 0, 'cmpDate empty bound -> 0');
ok(D.dateOutOfRange({ y: 2026, m: 8, d: 7 }, '2026-08-10', null) === true, 'before min = out');
ok(D.dateOutOfRange({ y: 2026, m: 8, d: 15 }, '2026-08-10', '2026-08-20') === false, 'in range = in');
ok(D.dateOutOfRange({ y: 2026, m: 8, d: 25 }, null, '2026-08-20') === true, 'after max = out');
ok(D.clampInt('99', 0, 23) === 23 && D.clampInt('-3', 0, 59) === 0 && D.clampInt('abc', 0, 23) === 0,
  'clampInt clamps hi/lo/NaN');

// ---- range helpers ----
ok(D.dayKey({ y: 2026, m: 8, d: 7 }) === 20260807, 'dayKey sortable int');
ok(D.isBetween({ y: 2026, m: 8, d: 10 }, { y: 2026, m: 8, d: 5 }, { y: 2026, m: 8, d: 15 }) === true,
  'isBetween: inside range');
ok(D.isBetween({ y: 2026, m: 8, d: 5 }, { y: 2026, m: 8, d: 5 }, { y: 2026, m: 8, d: 15 }) === false,
  'isBetween: endpoint is NOT strictly between');
ok(D.isBetween({ y: 2026, m: 8, d: 10 }, { y: 2026, m: 8, d: 15 }, { y: 2026, m: 8, d: 5 }) === true,
  'isBetween: order-independent');
ok(D.isBetween({ y: 2026, m: 8, d: 10 }, null, { y: 2026, m: 8, d: 15 }) === false,
  'isBetween: missing endpoint -> false');

// ---- structural guarantees (safety contract) ----
ok(/__ecDpInstalled/.test(SRC), 'single-install guarded');
ok(/\^\\\/app/.test(SRC), 'hard no-op on Frappe Desk (/app/*)');
ok(/:not\(\[data-ec-dp\]\)/.test(SRC), 'idempotent: skips already-enhanced inputs');
ok(SRC.indexOf("fire(this.input, 'input')") >= 0 && SRC.indexOf("fire(this.input, 'change')") >= 0,
  'value-preserving: dispatches native input + change events');
ok(/ec-dp-native/.test(SRC), 'native input kept as source of truth (clipped, not removed)');
ok(/new MutationObserver/.test(SRC), 'enhances dynamically-added inputs');
ok(/input\[type="date"\]/.test(SRC) && /input\[type="datetime-local"\]/.test(SRC),
  'targets date + datetime-local only');
ok(/catch \(err\)/.test(SRC) && /removeAttribute\('aria-hidden'\)/.test(SRC),
  'reverts to native input on enhancement error (fail-safe)');

// ---- new features: range + time wheels + pink ----
ok(/data-ec-dp-range/.test(SRC), 'opt-in date range via data-ec-dp-range');
ok(/function linkRange/.test(SRC) && /partner/.test(SRC), 'range links a start/end partner pair');
ok(/setAttribute\('min'/.test(SRC) && /setAttribute\('max'/.test(SRC),
  'range keeps start <= end by syncing min/max');
ok(/is-range-start/.test(SRC) && /is-range-end/.test(SRC) && /is-range/.test(SRC),
  'calendar shades the range band + endpoints');
ok(/ec-dp-wheel/.test(SRC) && /scrollWheels/.test(SRC), 'time uses scrollable wheels');
ok(/ec-dp-tin/.test(SRC) && /inputmode="numeric"/.test(SRC), 'manual hh:mm inputs to type time by hand');
ok(/setTime/.test(SRC), 'manual input <-> wheel two-way sync (setTime)');
ok(/ec-dp-tin/.test(CSS), 'CSS: styled manual time inputs');
ok(/ec-dp-band/.test(SRC) && /ec-dp-wheelbox/.test(SRC), 'iOS-style fixed centre selection band');
ok(/WHEEL_IH/.test(SRC) && /w\.scrollTop \/ WHEEL_IH/.test(SRC),
  'scroll settles -> value under the fixed band becomes the pick');
ok(/ec-dp-band/.test(CSS) && /translateY\(-50%\)/.test(CSS), 'CSS: pink band pinned to centre');
ok(/WHEEL_REP/.test(SRC) && /\(\(idx % len\) \+ len\) % len/.test(SRC),
  'infinite loop: list repeated + modulo recentre on the middle copy');
ok(/scroll-snap-type/.test(CSS) && /ec-dp-wheel/.test(CSS), 'CSS: wheels are scroll-snap columns');
ok(/ec-dp-body[\s\S]*flex/.test(CSS), 'CSS: time sits beside the calendar (flex body)');
ok(/--ec-dp-accent:\s*#2563eb/.test(CSS), 'CSS: blue primary accent (#2563eb)');
ok(/--ec-dp-today:\s*#db2777/.test(CSS), 'CSS: pink kept as the "today" accent');
ok(/--ec-dp-range/.test(CSS), 'CSS: range band token');

// ---- hooks wiring (regression guard) ----
ok(HOOKS.indexOf('ec_datepicker.bundle.js') >= 0, 'hooks: JS bundle in web_include_js');
ok(HOOKS.indexOf('ec_datepicker.bundle.css') >= 0, 'hooks: CSS bundle in web_include_css');

// ---- asset files exist + non-empty ----
['../ec_datepicker.js', '../ec_datepicker.bundle.js', '../../css/ec_datepicker.bundle.css']
  .forEach(function (p) {
    const full = path.join(__dirname, p);
    ok(fs.existsSync(full) && fs.statSync(full).size > 0, 'asset exists: ' + p);
  });

console.log(failures ? ('\n' + failures + ' FAILURE(S)') : '\nALL TESTS PASSED');
process.exit(failures ? 1 : 0);
