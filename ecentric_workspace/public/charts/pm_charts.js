/*!
 * PMCharts - PM dashboard chart renderers (ecentric_workspace).
 * Mirrors AlertCharts: reads ALL palette/structure fragments from window.ECChartTheme and ALL
 * lifecycle (init/reuse/dispose/resize/fallback) from window.ECCharts. It NEVER re-implements
 * lifecycle, NEVER hardcodes a vendor copy, and NEVER calls AlertCharts. Calm PM palette
 * (navy/cyan/gray; yellow-orange = risk, red = critical) — not Alert's red/orange.
 *
 * Exposes exactly one global: window.PMCharts
 * Consumes: window.echarts, window.ECChartTheme, window.ECCharts
 */
(function () {
  "use strict";
  var C = window.ECCharts;
  var T = window.ECChartTheme || {};

  // calm PM palette
  var PM = {
    navy: "#2C3DA6", blue: "#4763d6", cyan: "#0e9aa7", teal: "#2bb3a3",
    gray: "#94a3b8", grayDark: "#475569",
    green: "#0a7a4f", amber: "#b8860b", orange: "#b3541e", red: "#c0392b",
    track: "#eef1f7"
  };

  function _t(part, fallback) {
    // theme fragment that may be a function (call with cfg) or an object
    var v = T[part];
    if (typeof v === "function") return v;
    return function (cfg) { return Object.assign({}, v || fallback || {}, cfg || {}); };
  }
  var themeTooltip = _t("tooltip", { trigger: "item" });
  var themeLegend = _t("legend", {});
  var themeGrid = (T.grid && typeof T.grid === "object") ? T.grid : { left: 8, right: 12, top: 16, bottom: 8, containLabel: true };
  var themeAxisLabel = (T.axisLabel && typeof T.axisLabel === "object") ? T.axisLabel : { color: PM.grayDark, fontSize: 11 };
  var themeSplit = (T.splitLine && typeof T.splitLine === "object") ? T.splitLine : { lineStyle: { color: "#eef1f7" } };
  var anim = T.animation || { duration: 500, easing: "cubicOut" };
  var emptyText = (T.empty && T.empty.text) || "Chưa có dữ liệu";

  function _ok() { return C && C.ok && C.ok(); }
  function _fbTable(rows, total) {
    if (!total) return '<div class="pm-chart-empty">' + emptyText + "</div>";
    return '<table class="pm-chart-fbt"><tbody>' + rows.map(function (r) {
      return "<tr><td>" + C.esc(r[0]) + '</td><td class="r"><b>' + (r[1] || 0) + "</b></td></tr>";
    }).join("") + "</tbody></table>";
  }

  // segs: [[name, value, colorHex], ...]; centerNum/centerLabel for the hole.
  function renderRiskDonut(boxEl, fbEl, segs, opts) {
    opts = opts || {};
    segs = segs || [];
    var total = segs.reduce(function (a, s) { return a + (s[1] || 0); }, 0);
    if (!_ok()) { if (C) C.fallback(boxEl, fbEl, _fbTable(segs, total)); return null; }
    C.clearFallback(boxEl, fbEl);
    var data = segs.map(function (s) { return { name: s[0], value: s[1] || 0, itemStyle: { color: s[2] } }; });
    var option = {
      color: segs.map(function (s) { return s[2]; }),
      animationDuration: anim.duration, animationEasing: anim.easing,
      tooltip: themeTooltip({ trigger: "item",
        formatter: function (p) { return C.esc(p.name) + ": <b>" + p.value + "</b> (" + p.percent + "%)"; } }),
      legend: themeLegend({ type: "scroll", bottom: 0, icon: "circle" }),
      graphic: (total && T.centerText) ? T.centerText(opts.centerNum != null ? opts.centerNum : total, opts.centerLabel || "") : [],
      series: [{
        name: opts.name || "", type: "pie", radius: ["56%", "78%"], center: ["50%", "44%"],
        avoidLabelOverlap: true, minAngle: 3, label: { show: false }, labelLine: { show: false },
        itemStyle: { borderColor: "#fff", borderWidth: 1.5 },
        emphasis: { scale: true, scaleSize: 6, itemStyle: { shadowBlur: 10, shadowColor: "rgba(15,23,42,0.18)" } },
        data: total ? data : []
      }]
    };
    var inst = C.setOption(boxEl, option, true);
    if (inst && typeof opts.onClick === "function") {
      inst.off("click"); inst.on("click", function (p) { if (p && p.name) opts.onClick(p.name); });
    }
    return inst;
  }

  // dist: {label:value}; order: [labels]; colorFor(label)->hex (optional).
  function renderStatusBar(boxEl, fbEl, dist, order, opts) {
    opts = opts || {}; dist = dist || {}; order = order || Object.keys(dist);
    var rows = order.map(function (k) { return [k, dist[k] || 0]; });
    var total = rows.reduce(function (a, r) { return a + r[1]; }, 0);
    if (!_ok()) { if (C) C.fallback(boxEl, fbEl, _fbTable(rows, total)); return null; }
    C.clearFallback(boxEl, fbEl);
    var colorFor = opts.colorFor || function () { return PM.navy; };
    var option = {
      animationDuration: anim.duration, animationEasing: anim.easing,
      grid: Object.assign({}, themeGrid, { top: 14, bottom: 6, left: 6, right: 14, containLabel: true }),
      tooltip: themeTooltip({ trigger: "axis", axisPointer: { type: "shadow" },
        formatter: function (a) { var p = a[0]; return C.esc(p.name) + ": <b>" + p.value + "</b>"; } }),
      xAxis: { type: "value", axisLabel: themeAxisLabel, splitLine: themeSplit, minInterval: 1 },
      yAxis: { type: "category", inverse: true, data: order, axisLabel: themeAxisLabel,
        axisTick: { show: false }, axisLine: { show: false } },
      series: [{
        type: "bar", barWidth: "58%", barMaxWidth: 22,
        itemStyle: { borderRadius: [0, 4, 4, 0], color: function (p) { return colorFor(order[p.dataIndex]); } },
        label: { show: true, position: "right", color: PM.grayDark, fontSize: 11 },
        data: rows.map(function (r) { return r[1]; })
      }]
    };
    return C.setOption(boxEl, option, true);
  }

  // rows: [{u, open, overdue, blocked}] -> horizontal stacked (open with risk overlay).
  function renderWorkload(boxEl, fbEl, rows, opts) {
    opts = opts || {}; rows = (rows || []).slice(0, 8);
    var total = rows.reduce(function (a, r) { return a + (r.open || 0); }, 0);
    if (!_ok()) { if (C) C.fallback(boxEl, fbEl, _fbTable(rows.map(function (r) { return [(r.u || "").split("@")[0], r.open || 0]; }), total)); return null; }
    C.clearFallback(boxEl, fbEl);
    var names = rows.map(function (r) { return (r.u || "").split("@")[0]; });
    var safe = rows.map(function (r) { return Math.max(0, (r.open || 0) - Math.min((r.overdue || 0) + (r.blocked || 0), r.open || 0)); });
    var risk = rows.map(function (r) { return Math.min((r.overdue || 0) + (r.blocked || 0), r.open || 0); });
    var option = {
      animationDuration: anim.duration, animationEasing: anim.easing,
      grid: Object.assign({}, themeGrid, { top: 10, bottom: 6, left: 6, right: 16, containLabel: true }),
      tooltip: themeTooltip({ trigger: "axis", axisPointer: { type: "shadow" } }),
      legend: themeLegend({ bottom: 0, data: ["Đang mở", "Rủi ro"] }),
      xAxis: { type: "value", axisLabel: themeAxisLabel, splitLine: themeSplit, minInterval: 1 },
      yAxis: { type: "category", inverse: true, data: names, axisLabel: themeAxisLabel,
        axisTick: { show: false }, axisLine: { show: false } },
      series: [
        { name: "Đang mở", type: "bar", stack: "w", barWidth: "55%", barMaxWidth: 20,
          itemStyle: { color: PM.navy, borderRadius: [4, 0, 0, 4] }, data: safe },
        { name: "Rủi ro", type: "bar", stack: "w",
          itemStyle: { color: PM.orange, borderRadius: [0, 4, 4, 0] }, data: risk }
      ]
    };
    var inst = C.setOption(boxEl, option, true);
    if (inst && typeof opts.onClick === "function") {
      inst.off("click"); inst.on("click", function (p) { var u = rows[p.dataIndex]; if (u) opts.onClick(u.u); });
    }
    return inst;
  }

  function disposeAll() { if (C && C.disposeAll) C.disposeAll(); }
  function attachResize() { if (C && C.attachResize) C.attachResize(); }
  function available() { return _ok(); }

  window.PMCharts = {
    renderRiskDonut: renderRiskDonut,
    renderStatusBar: renderStatusBar,
    renderWorkload: renderWorkload,
    disposeAll: disposeAll, attachResize: attachResize, available: available,
    PM: PM
  };
})();
