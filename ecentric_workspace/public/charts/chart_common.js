/*!
 * ECCharts - ERP-wide reusable ECharts lifecycle helpers (ecentric_workspace).
 * Owns init/get/dispose/resize, a SINGLE debounced window-resize listener,
 * loading + empty/error fallback rendering, a safe deep option merge and small
 * HTML/format utilities. Prevents duplicate instances, duplicate listeners and
 * memory leaks.
 *
 * Exposes exactly one global: window.ECCharts
 * Depends only on window.echarts (optional - everything degrades if absent).
 */
(function () {
  "use strict";

  var registry = [];          // tracked DOM elements that hold a live instance
  var resizeBound = false;    // guard so only ONE resize listener is ever added
  var resizeTimer = null;

  function ok() { return typeof window.echarts !== "undefined" && !!window.echarts; }

  function _idx(el) { return registry.indexOf(el); }
  function _track(el) { if (el && _idx(el) < 0) registry.push(el); }
  function _untrack(el) { var i = _idx(el); if (i >= 0) registry.splice(i, 1); }

  // Reuse the existing instance for this element or create one (never two).
  function ensure(el) {
    if (!ok() || !el) return null;
    var inst = window.echarts.getInstanceByDom(el) || window.echarts.init(el);
    _track(el);
    return inst;
  }
  function get(el) { return (ok() && el) ? window.echarts.getInstanceByDom(el) : null; }

  function dispose(el) {
    var inst = get(el);
    if (inst) { try { inst.dispose(); } catch (e) {} }
    _untrack(el);
  }
  function disposeAll() { registry.slice().forEach(dispose); }

  function resize(el) { var inst = get(el); if (inst) { try { inst.resize(); } catch (e) {} } }
  function resizeAll() { registry.slice().forEach(resize); }

  // Idempotent: attaches the debounced window listener at most once per page.
  function attachResize(debounceMs) {
    if (resizeBound) return;
    resizeBound = true;
    var wait = typeof debounceMs === "number" ? debounceMs : 120;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(resizeAll, wait);
    });
  }

  function showLoading(el, opt) { var inst = ensure(el); if (inst) inst.showLoading("default", opt || {}); }
  function hideLoading(el) { var inst = get(el); if (inst) inst.hideLoading(); }

  // Dispose-before-rerender is the caller-safe path: setOption(...,notMerge).
  function setOption(el, option, notMerge) {
    var inst = ensure(el);
    if (!inst) return null;
    inst.hideLoading();
    inst.setOption(option, notMerge !== false);
    return inst;
  }

  // Show the table/text fallback element and hide the (canvas) chart box.
  function fallback(boxEl, fbEl, html) {
    if (boxEl) boxEl.style.display = "none";
    if (fbEl) { fbEl.hidden = false; fbEl.innerHTML = html; }
  }
  function clearFallback(boxEl, fbEl) {
    if (fbEl) fbEl.hidden = true;
    if (boxEl) boxEl.style.display = "";
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function pct(value, total) {
    if (!total) return "0%";
    var p = value * 100 / total;
    return (p < 1 ? p.toFixed(1) : Math.round(p)) + "%";
  }

  // Safe recursive merge (plain objects only; arrays/scalars are replaced).
  function deepMerge(base, over) {
    var out = {}, k;
    for (k in base) if (has(base, k)) out[k] = base[k];
    for (k in over) if (has(over, k)) {
      out[k] = (isObj(out[k]) && isObj(over[k])) ? deepMerge(out[k], over[k]) : over[k];
    }
    return out;
  }
  function isObj(v) { return v && typeof v === "object" && !(v instanceof Array); }
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  window.ECCharts = {
    ok: ok, ensure: ensure, get: get,
    dispose: dispose, disposeAll: disposeAll,
    resize: resize, resizeAll: resizeAll, attachResize: attachResize,
    showLoading: showLoading, hideLoading: hideLoading,
    setOption: setOption, fallback: fallback, clearFallback: clearFallback,
    esc: esc, pct: pct, merge: deepMerge
  };
})();
