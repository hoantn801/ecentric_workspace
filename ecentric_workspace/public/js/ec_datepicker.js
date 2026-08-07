// Copyright (c) 2026, eCentric and contributors
//
// ec_datepicker -- a shared, dependency-free date / datetime / date-range
// picker that PROGRESSIVELY ENHANCES native <input type="date"> and
// <input type="datetime-local"> across the whole ERP portal.
//
// Design contract (why this is safe to load site-wide):
//   * The native <input> stays in the DOM as the SINGLE SOURCE OF TRUTH. We
//     only skin it: the custom calendar writes the native value back in the
//     exact native format (yyyy-mm-dd / yyyy-mm-ddTHH:MM) and dispatches the
//     same `input` + `change` events, so every existing form handler, submit
//     path and value read (incl. MSO/SO/PO/GBS forms) behaves identically.
//   * We never touch Frappe Desk (/app/*) -- bail immediately there.
//   * Single-install guarded; idempotent; a MutationObserver enhances inputs
//     added later by dynamic forms; any enhancement error reverts to native.
//   * Display is vi-VN (dd/MM/yyyy, week starts Monday). No business logic.
//
// Opt-in date range: give two inputs the SAME `data-ec-dp-range="<group>"`.
// Roles are read from `data-ec-dp-role="start|end"` (or inferred from DOM
// order). The two fields stay separate (1 ô start, 1 ô end) but the calendar
// shows the range band and keeps start <= end automatically.
//
// The pure date helpers are exported for node unit tests; the DOM wiring is
// skipped when there is no `document` (node).
'use strict';
(function () {
  // ----------------------------------------------------------- pure helpers --
  var MONTHS_VI = ['Tháng 1', 'Tháng 2', 'Tháng 3', 'Tháng 4', 'Tháng 5',
    'Tháng 6', 'Tháng 7', 'Tháng 8', 'Tháng 9', 'Tháng 10', 'Tháng 11', 'Tháng 12'];
  var WEEKDAYS_VI = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']; // Monday-first

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function parseNative(val) {
    if (!val) return null;
    var m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(String(val));
    if (!m) return null;
    return {
      y: +m[1], m: +m[2], d: +m[3],
      hh: m[4] != null ? +m[4] : 0, mm: m[5] != null ? +m[5] : 0
    };
  }
  function toNative(o, withTime) {
    var s = o.y + '-' + pad(o.m) + '-' + pad(o.d);
    return withTime ? (s + 'T' + pad(o.hh) + ':' + pad(o.mm)) : s;
  }
  function toDisplay(o, withTime) {
    var s = pad(o.d) + '/' + pad(o.m) + '/' + o.y;
    return withTime ? (s + ' ' + pad(o.hh) + ':' + pad(o.mm)) : s;
  }
  function daysInMonth(y, m) { return new Date(y, m, 0).getDate(); }
  function firstDow(y, m) { return (new Date(y, m - 1, 1).getDay() + 6) % 7; }
  function buildGrid(y, m) {
    var lead = firstDow(y, m), dim = daysInMonth(y, m), cells = [], i;
    for (i = 0; i < lead; i++) cells.push(null);
    for (i = 1; i <= dim; i++) cells.push(i);
    while (cells.length % 7 !== 0) cells.push(null);
    return cells;
  }
  function dayKey(o) { return o.y * 10000 + o.m * 100 + o.d; }        // sortable int
  function isBetween(cell, a, b) {                                    // strictly between
    if (!a || !b) return false;
    var k = dayKey(cell), lo = Math.min(dayKey(a), dayKey(b)), hi = Math.max(dayKey(a), dayKey(b));
    return k > lo && k < hi;
  }
  function cmpDate(o, nativeStr) {
    var p = parseNative(nativeStr);
    if (!p) return 0;
    var a = dayKey(o), b = dayKey(p);
    return a < b ? -1 : (a > b ? 1 : 0);
  }
  function dateOutOfRange(o, min, max) {
    return (min && cmpDate(o, min) < 0) || (max && cmpDate(o, max) > 0);
  }
  function clampInt(n, lo, hi) {
    n = parseInt(n, 10);
    if (isNaN(n)) return lo;
    return n < lo ? lo : (n > hi ? hi : n);
  }

  var PURE = {
    pad: pad, parseNative: parseNative, toNative: toNative, toDisplay: toDisplay,
    daysInMonth: daysInMonth, firstDow: firstDow, buildGrid: buildGrid,
    dayKey: dayKey, isBetween: isBetween, cmpDate: cmpDate,
    dateOutOfRange: dateOutOfRange, clampInt: clampInt,
    MONTHS_VI: MONTHS_VI, WEEKDAYS_VI: WEEKDAYS_VI
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = PURE;
  if (typeof document === 'undefined') return; // node unit tests stop here

  // -------------------------------------------------------------- DOM wiring --
  if (window.__ecDpInstalled) return;
  window.__ecDpInstalled = 1;
  if (/^\/app(\/|$)/.test(location.pathname)) return; // never on Frappe Desk
  if (window.__ecDpDisabled) return;

  var CAL_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">'
    + '<rect x="3" y="4.5" width="18" height="16" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/>'
    + '<path d="M3 9h18M8 2.5v4M16 2.5v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';

  var WHEEL_IH = 36; // wheel option height (px) -- MUST match .ec-dp-opt height + wheel padding in CSS
  var WHEEL_REP = 5; // list is repeated N times for an infinite loop; we recentre on the middle copy

  function fire(el, type) { el.dispatchEvent(new Event(type, { bubbles: true })); }
  function mk(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }
  function todayObj() {
    var d = new Date();
    return { y: d.getFullYear(), m: d.getMonth() + 1, d: d.getDate(), hh: 0, mm: 0 };
  }
  function clone(o) { return { y: o.y, m: o.m, d: o.d, hh: o.hh || 0, mm: o.mm || 0 }; }

  var openInst = null;
  var RANGE_REG = {}; // group -> [DP, DP]

  function DP(input) {
    this.input = input;
    this.withTime = input.type === 'datetime-local';
    this.rangeGroup = input.getAttribute('data-ec-dp-range') || null;
    this.rangeRole = input.getAttribute('data-ec-dp-role') || null;
    this.partner = null;
    this.build();
  }

  DP.prototype.build = function () {
    var input = this.input;
    input.classList.add('ec-dp-native');
    input.setAttribute('tabindex', '-1');
    input.setAttribute('aria-hidden', 'true');
    var wrap = mk('span', 'ec-dp-wrap');
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    var field = mk('button', 'ec-dp-field',
      '<span class="ec-dp-val"></span><span class="ec-dp-ico">' + CAL_SVG + '</span>');
    field.type = 'button';
    field.setAttribute('aria-haspopup', 'dialog');
    field.setAttribute('aria-expanded', 'false');
    if (input.disabled || input.hasAttribute('readonly')) field.disabled = true;
    wrap.appendChild(field);
    this.field = field;
    this.valNode = field.querySelector('.ec-dp-val');
    this.placeholder = input.getAttribute('placeholder')
      || (this.withTime ? 'dd/mm/yyyy hh:mm' : 'dd/mm/yyyy');
    this.refresh();
    var self = this;
    field.addEventListener('click', function () { self.toggle(); });
    input.addEventListener('change', function () { self.refresh(); });
    if (input.form) input.form.addEventListener('reset', function () {
      setTimeout(function () { self.refresh(); }, 0);
    });
  };

  DP.prototype.refresh = function () {
    var o = parseNative(this.input.value);
    this.sel = o;
    if (o) {
      this.valNode.textContent = toDisplay(o, this.withTime);
      this.field.classList.remove('ec-dp-empty');
    } else {
      this.valNode.textContent = this.placeholder;
      this.field.classList.add('ec-dp-empty');
    }
  };

  DP.prototype.toggle = function () { this.pop ? this.close() : this.open(); };

  DP.prototype.open = function () {
    if (openInst && openInst !== this) openInst.close();
    openInst = this;
    var base = parseNative(this.input.value) || todayObj();
    this.view = { y: base.y, m: base.m };
    this.draft = parseNative(this.input.value)
      ? clone(base) : { y: base.y, m: base.m, d: base.d, hh: 0, mm: 0 };
    this.pop = mk('div', 'ec-dp-pop' + (this.withTime ? ' has-time' : ''));
    this.pop.setAttribute('role', 'dialog');
    this.pop.setAttribute('aria-label', 'Chọn ngày');
    document.body.appendChild(this.pop);
    this.render();
    this.position();
    this.field.setAttribute('aria-expanded', 'true');
    var self = this;
    this._onDoc = function (e) {
      if (self.pop && !self.pop.contains(e.target) && !self.field.contains(e.target)) self.close();
    };
    this._onKey = function (e) { self.onKey(e); };
    this._onWin = function () { self.position(); };
    setTimeout(function () { document.addEventListener('mousedown', self._onDoc); }, 0);
    document.addEventListener('keydown', this._onKey);
    window.addEventListener('resize', this._onWin);
    window.addEventListener('scroll', this._onWin, true);
  };

  DP.prototype.close = function () {
    if (!this.pop) return;
    document.removeEventListener('mousedown', this._onDoc);
    document.removeEventListener('keydown', this._onKey);
    window.removeEventListener('resize', this._onWin);
    window.removeEventListener('scroll', this._onWin, true);
    this.pop.remove();
    this.pop = null;
    this.field.setAttribute('aria-expanded', 'false');
    if (openInst === this) openInst = null;
    this.field.focus();
  };

  DP.prototype.position = function () {
    if (!this.pop) return;
    var r = this.field.getBoundingClientRect();
    var pw = this.pop.offsetWidth || 300, ph = this.pop.offsetHeight || 320;
    var left = Math.max(8, Math.min(r.left, window.innerWidth - pw - 8));
    var top = r.bottom + 6;
    if (top + ph > window.innerHeight - 8 && r.top - ph - 6 > 8) top = r.top - ph - 6;
    this.pop.style.left = left + 'px';
    this.pop.style.top = top + 'px';
  };

  // Range endpoints (start/end) parsed from BOTH inputs, or null.
  DP.prototype.rangePair = function () {
    if (!this.partner) return null;
    var s = this.rangeRole === 'start' ? this : this.partner;
    var e = this.rangeRole === 'start' ? this.partner : this;
    return { start: parseNative(s.input.value), end: parseNative(e.input.value) };
  };

  DP.prototype.render = function () {
    var self = this, v = this.view, min = this.input.getAttribute('min'),
      max = this.input.getAttribute('max'), pair = this.rangePair();
    var h = '<div class="ec-dp-body"><div class="ec-dp-cal">';
    h += '<div class="ec-dp-hd">'
      + '<button type="button" class="ec-dp-nav" data-mv="-1" aria-label="Tháng trước">‹</button>'
      + '<span class="ec-dp-title">' + MONTHS_VI[v.m - 1] + ' ' + v.y + '</span>'
      + '<button type="button" class="ec-dp-nav" data-mv="1" aria-label="Tháng sau">›</button></div>';
    h += '<div class="ec-dp-wd">';
    for (var i = 0; i < 7; i++) h += '<span>' + WEEKDAYS_VI[i] + '</span>';
    h += '</div><div class="ec-dp-grid" role="grid">';
    var cells = buildGrid(v.y, v.m), td = todayObj();
    cells.forEach(function (d) {
      if (d == null) { h += '<span class="ec-dp-cell ec-dp-blank"></span>'; return; }
      var o = { y: v.y, m: v.m, d: d }, cls = 'ec-dp-cell';
      var dis = dateOutOfRange(o, min, max);
      var isSel = self.draft && self.draft.y === v.y && self.draft.m === v.m && self.draft.d === d;
      if (td.y === v.y && td.m === v.m && td.d === d) cls += ' is-today';
      if (pair) {
        if (pair.start && dayKey(o) === dayKey(pair.start)) cls += ' is-range-start';
        if (pair.end && dayKey(o) === dayKey(pair.end)) cls += ' is-range-end';
        if (isBetween(o, pair.start, pair.end)) cls += ' is-range';
      }
      if (isSel) cls += ' is-sel';
      h += '<button type="button" role="gridcell" class="' + cls + '" data-d="' + d + '"'
        + (dis ? ' disabled aria-disabled="true"' : '')
        + ' tabindex="' + (isSel ? '0' : '-1') + '">' + d + '</button>';
    });
    h += '</div></div>'; // grid, cal
    if (this.withTime) h += this.timeHtml();
    h += '</div>'; // body
    h += '<div class="ec-dp-ft">'
      + '<button type="button" class="ec-dp-btn ec-dp-clear">Xóa</button>'
      + '<button type="button" class="ec-dp-btn ec-dp-today">Hôm nay</button>'
      + (this.withTime ? '<button type="button" class="ec-dp-btn ec-dp-ok">Xong</button>' : '')
      + '</div>';
    this.pop.innerHTML = h;
    this.bind();
    this.scrollWheels();
    var sel = this.pop.querySelector('.ec-dp-cell.is-sel')
      || this.pop.querySelector('.ec-dp-cell[data-d]:not([disabled])');
    if (sel) sel.focus();
  };

  // Time panel beside the calendar: manual hh:mm inputs on top (type by hand)
  // + scrollable wheels below. The two are kept in sync by setTime().
  DP.prototype.timeHtml = function () {
    var dd = this.draft || { hh: 0, mm: 0 };
    function wheel(unit, max) {
      // Fixed centre band (.ec-dp-band) + an INFINITE scrollable column: the
      // list is repeated WHEEL_REP times and we recentre on the middle copy, so
      // scrolling loops (…23 -> 00 -> 01…) with no blank ends. The one option
      // that settles under the band is the selected value.
      var s = '<div class="ec-dp-wheelbox"><div class="ec-dp-band" aria-hidden="true"></div>'
        + '<div class="ec-dp-wheel" data-unit="' + unit + '" role="listbox" aria-label="'
        + (unit === 'hh' ? 'Giờ' : 'Phút') + '">';
      for (var r = 0; r < WHEEL_REP; r++)
        for (var n = 0; n <= max; n++)
          s += '<button type="button" class="ec-dp-opt" data-v="' + n + '" role="option" tabindex="-1">'
            + pad(n) + '</button>';
      return s + '</div></div>';
    }
    return '<div class="ec-dp-time">'
      + '<div class="ec-dp-time-top">'
      + '<input class="ec-dp-tin ec-dp-hh" type="text" inputmode="numeric" maxlength="2" '
      + 'aria-label="Giờ" value="' + pad(dd.hh) + '">'
      + '<span class="ec-dp-colon">:</span>'
      + '<input class="ec-dp-tin ec-dp-mm" type="text" inputmode="numeric" maxlength="2" '
      + 'aria-label="Phút" value="' + pad(dd.mm) + '">'
      + '</div>'
      + '<div class="ec-dp-wheels">'
      + wheel('hh', 23) + '<span class="ec-dp-colon">:</span>' + wheel('mm', 59)
      + '</div></div>';
  };

  // Single source of truth for a time unit -- keeps the manual input, the wheel
  // highlight and this.draft consistent whichever the user touched.
  // Mark ONLY the child at index idx as the selected (centred) option.
  DP.prototype.markWheel = function (w, idx) {
    var opts = w.children;
    for (var i = 0; i < opts.length; i++) opts[i].classList.toggle('is-sel', i === idx);
  };

  // Update draft + manual input for a time unit; optionally recentre the looping
  // wheel on the middle copy (instant, seamless -- same value stays under band).
  DP.prototype.setTime = function (unit, val, recenter) {
    if (!this.pop) return;
    var len = unit === 'hh' ? 24 : 60, v = clampInt(val, 0, len - 1);
    this.draft = this.draft || { y: 0, m: 0, d: 0, hh: 0, mm: 0 };
    this.draft[unit] = v;
    var input = this.pop.querySelector(unit === 'hh' ? '.ec-dp-hh' : '.ec-dp-mm');
    if (input && document.activeElement !== input) input.value = pad(v); // don't fight typing
    if (recenter) {
      var w = this.pop.querySelector('.ec-dp-wheel[data-unit="' + unit + '"]');
      if (w) {
        var idx = Math.floor(WHEEL_REP / 2) * len + v; // value v on the middle copy
        w.scrollTop = idx * WHEEL_IH;                  // pad=(H-IH)/2 => centres exactly
        this.markWheel(w, idx);
      }
    }
  };

  DP.prototype.scrollWheels = function () {
    if (!this.withTime || !this.pop || !this.draft) return;
    this.setTime('hh', this.draft.hh, true);
    this.setTime('mm', this.draft.mm, true);
  };

  DP.prototype.bind = function () {
    var self = this;
    this.pop.querySelectorAll('.ec-dp-nav').forEach(function (b) {
      b.addEventListener('click', function () { self.moveMonth(+b.getAttribute('data-mv')); });
    });
    this.pop.querySelectorAll('.ec-dp-cell[data-d]').forEach(function (b) {
      if (b.disabled) return;
      b.addEventListener('click', function () { self.pickDay(+b.getAttribute('data-d')); });
    });
    ['hh', 'mm'].forEach(function (unit) {
      var inp = self.pop.querySelector(unit === 'hh' ? '.ec-dp-hh' : '.ec-dp-mm');
      if (!inp) return;
      inp.addEventListener('input', function () { self.setTime(unit, inp.value, false); });
      inp.addEventListener('change', function () { self.setTime(unit, inp.value, true); });
    });
    // Infinite wheel. On scroll settle: read the value under the band, mark it,
    // and recentre on the middle copy ONLY near the buffer ends -- so the common
    // case leaves the browser's own momentum + snap untouched (smooth), and the
    // seamless loop jump happens rarely and invisibly. Clicks scroll smoothly.
    this.pop.querySelectorAll('.ec-dp-wheel').forEach(function (w) {
      var unit = w.getAttribute('data-unit'), len = unit === 'hh' ? 24 : 60, t;
      var input = self.pop.querySelector(unit === 'hh' ? '.ec-dp-hh' : '.ec-dp-mm');
      w.addEventListener('scroll', function () {
        clearTimeout(t);
        t = setTimeout(function () {
          var idx = Math.round(w.scrollTop / WHEEL_IH), v = ((idx % len) + len) % len;
          self.draft = self.draft || { y: 0, m: 0, d: 0, hh: 0, mm: 0 };
          self.draft[unit] = v;
          if (input && document.activeElement !== input) input.value = pad(v);
          self.markWheel(w, idx);
          if (idx < len || idx >= len * (WHEEL_REP - 1)) {  // near an end -> loop
            var mid = Math.floor(WHEEL_REP / 2) * len + v;
            w.scrollTop = mid * WHEEL_IH;
            self.markWheel(w, mid);
          }
        }, 110);
      });
      w.addEventListener('click', function (e) {
        var b = e.target.closest('.ec-dp-opt');
        if (b) w.scrollTo({ top: Array.prototype.indexOf.call(w.children, b) * WHEEL_IH, behavior: 'smooth' });
      });
    });
    var clr = this.pop.querySelector('.ec-dp-clear');
    if (clr) clr.addEventListener('click', function () { self.commit(null); });
    var tdy = this.pop.querySelector('.ec-dp-today');
    if (tdy) tdy.addEventListener('click', function () {
      var t = todayObj(); self.view = { y: t.y, m: t.m };
      self.draft = { y: t.y, m: t.m, d: t.d, hh: self.draft ? self.draft.hh : 0, mm: self.draft ? self.draft.mm : 0 };
      if (self.withTime) self.render(); else self.commit(self.draft);
    });
    var ok = this.pop.querySelector('.ec-dp-ok');
    if (ok) ok.addEventListener('click', function () { self.commit(self.draft); });
  };

  DP.prototype.moveMonth = function (delta) {
    var m = this.view.m + delta, y = this.view.y;
    if (m < 1) { m = 12; y--; } else if (m > 12) { m = 1; y++; }
    this.view = { y: y, m: m };
    this.render();
  };

  DP.prototype.pickDay = function (d) {
    this.draft = this.draft || { hh: 0, mm: 0 };
    this.draft.y = this.view.y; this.draft.m = this.view.m; this.draft.d = d;
    if (this.withTime) this.render();
    else this.commit(this.draft);
  };

  DP.prototype._writeNative = function (o) {
    this.input.value = o ? toNative(o, this.withTime) : '';
    fire(this.input, 'input');
    fire(this.input, 'change');
    this.refresh();
  };

  // Keep the partner field consistent so start <= end always holds.
  DP.prototype.syncRange = function (o) {
    var p = this.partner; if (!p || !o) return;
    var bound = toNative({ y: o.y, m: o.m, d: o.d }, false), pv = parseNative(p.input.value);
    if (this.rangeRole === 'start') {
      p.input.setAttribute('min', bound);
      if (pv && dayKey(pv) < dayKey(o)) p._writeNative({ y: o.y, m: o.m, d: o.d, hh: pv.hh, mm: pv.mm });
    } else {
      p.input.setAttribute('max', bound);
      if (pv && dayKey(pv) > dayKey(o)) p._writeNative({ y: o.y, m: o.m, d: o.d, hh: pv.hh, mm: pv.mm });
    }
  };

  DP.prototype.commit = function (o) {
    this._writeNative(o);
    if (this.partner) this.syncRange(o);
    this.close();
  };

  DP.prototype.onKey = function (e) {
    if (!this.pop) return;
    if (e.key === 'Escape') { e.preventDefault(); this.close(); return; }
    var cell = document.activeElement;
    if (!cell || !cell.classList || !cell.classList.contains('ec-dp-cell')) return;
    var d = +cell.getAttribute('data-d'), move = 0;
    if (e.key === 'ArrowRight') move = 1;
    else if (e.key === 'ArrowLeft') move = -1;
    else if (e.key === 'ArrowDown') move = 7;
    else if (e.key === 'ArrowUp') move = -7;
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (!cell.disabled) this.pickDay(d); return; }
    else return;
    e.preventDefault();
    var target = d + move, dim = daysInMonth(this.view.y, this.view.m);
    if (target < 1) { this.moveMonth(-1); target = daysInMonth(this.view.y, this.view.m) + target; }
    else if (target > dim) { var over = target - dim; this.moveMonth(1); target = over; }
    var next = this.pop.querySelector('.ec-dp-cell[data-d="' + target + '"]');
    if (next) next.focus();
  };

  // ---------------------------------------------------------- range linking --
  function linkRange(dp) {
    if (!dp.rangeGroup) return;
    var arr = RANGE_REG[dp.rangeGroup] = RANGE_REG[dp.rangeGroup] || [];
    if (arr.indexOf(dp) < 0) arr.push(dp);
    if (arr.length !== 2) return;
    var a = arr[0], b = arr[1], startDP, endDP;
    if (a.rangeRole === 'start' || b.rangeRole === 'end') { startDP = a; endDP = b; }
    else if (b.rangeRole === 'start' || a.rangeRole === 'end') { startDP = b; endDP = a; }
    else {
      var following = a.input.compareDocumentPosition(b.input) & 4; // DOCUMENT_POSITION_FOLLOWING
      startDP = following ? a : b; endDP = following ? b : a;
    }
    startDP.rangeRole = 'start'; endDP.rangeRole = 'end';
    startDP.partner = endDP; endDP.partner = startDP;
    var sv = parseNative(startDP.input.value), ev = parseNative(endDP.input.value);
    if (sv) endDP.input.setAttribute('min', toNative({ y: sv.y, m: sv.m, d: sv.d }, false));
    if (ev) startDP.input.setAttribute('max', toNative({ y: ev.y, m: ev.m, d: ev.d }, false));
  }

  // ------------------------------------------------------------- enhancement --
  function enhanceIn(root) {
    var nodes = (root || document).querySelectorAll(
      'input[type="date"]:not([data-ec-dp]),input[type="datetime-local"]:not([data-ec-dp])');
    for (var i = 0; i < nodes.length; i++) {
      var inp = nodes[i];
      inp.setAttribute('data-ec-dp', '1');
      try { linkRange(new DP(inp)); }
      catch (err) {
        inp.classList.remove('ec-dp-native');
        inp.removeAttribute('tabindex');
        inp.removeAttribute('aria-hidden');
      }
    }
  }

  function boot() {
    enhanceIn(document);
    var pending = false;
    new MutationObserver(function () {
      if (pending) return;
      pending = true;
      setTimeout(function () { pending = false; enhanceIn(document); }, 80);
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
