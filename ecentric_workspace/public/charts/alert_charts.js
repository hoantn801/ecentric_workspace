/*!
 * AlertCharts - Alert Center chart renderers (ecentric_workspace).
 * Owns the Alert-specific chart option assembly + business-label application +
 * click/drill-down callback wiring. Reads ALL palettes/styling from
 * window.ECChartTheme and ALL lifecycle from window.ECCharts; it never
 * re-implements generic lifecycle and never hardcodes palettes.
 *
 * Exposes exactly one global: window.AlertCharts
 * Consumes: window.echarts, window.ECChartTheme, window.ECCharts
 */
(function () {
  "use strict";

  var T = window.ECChartTheme;
  var C = window.ECCharts;

  // Top 3 categories + an aggregated "Other", against the dimension's OWN total.
  // rows: [{ key, n }]; labelFor(key)->business label (optional); returns
  // { data:[{name,value,raw}], total }.
  function top3(rows, labelFor, otherLabel, noneLabel) {
    var r = (rows || []).slice().sort(function (a, b) { return b.n - a.n; });
    var total = r.reduce(function (s, x) { return s + (x.n || 0); }, 0);
    var top = r.slice(0, 3);
    var used = top.reduce(function (s, x) { return s + (x.n || 0); }, 0);
    var other = Math.max(0, total - used);
    var data = top.map(function (x) {
      var name = (x.key == null || x.key === "") ? (noneLabel || "(none)")
        : (labelFor ? labelFor(x.key) : x.key);
      return { name: name, value: x.n, raw: x.key };
    });
    if (other > 0) data.push({ name: otherLabel || "Other", value: other, raw: null });
    return { data: data, total: total };
  }

  function donutFallbackHTML(d) {
    if (!d.total) return '<div class="al-empty">' + (T.empty.text) + "</div>";
    return '<table class="al-tbl al-chart-fbt"><tbody>' + d.data.map(function (x) {
      return "<tr><td>" + C.esc(x.name) + '</td><td class="r"><b>' + x.value +
        '</b></td><td class="r">' + C.pct(x.value, d.total) + "</td></tr>";
    }).join("") + "</tbody></table>";
  }

  // renderDistributionDonut(element, dimension, rows, options)
  //  dimension: "brand" | "platform" | "rule" (selects the theme palette)
  //  rows: [{key, n}] straight from api_dashboard.by_dimension
  //  options: { label, totalLabel, otherLabel, noneLabel, labelFor, fallbackEl, onClick(raw) }
  function renderDistributionDonut(el, dimension, rows, options) {
    options = options || {};
    var label = options.label || dimension;
    var d = top3(rows, options.labelFor, options.otherLabel, options.noneLabel);
    if (!C.ok()) { C.fallback(el, options.fallbackEl, donutFallbackHTML(d)); return null; }
    C.clearFallback(el, options.fallbackEl);
    C.dispose(el); // dispose before rerender (no duplicate instances)
    var option = {
      color: T.palette(dimension),
      animationDuration: T.animation.duration,
      animationEasing: T.animation.easing,
      aria: { enabled: true, label: { description: label } },
      tooltip: T.tooltip({
        trigger: "item",
        formatter: function (p) {
          return label + "<br/>" + C.esc(p.name) + ": <b>" + p.value + "</b> (" + p.percent + "%)";
        }
      }),
      legend: T.legend({ type: "scroll", bottom: 0 }),
      graphic: d.total ? T.centerText(d.total, options.totalLabel || "") : [],
      series: [{
        name: label, type: "pie", radius: ["54%", "76%"], center: ["50%", "44%"],
        avoidLabelOverlap: true, minAngle: 3,
        label: { show: false }, labelLine: { show: false },
        itemStyle: { borderColor: "#fff", borderWidth: 1 },
        emphasis: { scale: true, scaleSize: 6,
          itemStyle: { shadowBlur: 10, shadowColor: "rgba(15,23,42,0.18)" } },
        data: d.data
      }]
    };
    var inst = C.setOption(el, option, true);
    if (inst && typeof options.onClick === "function") {
      inst.off("click");
      inst.on("click", function (p) {
        var raw = p.data && p.data.raw;
        if (raw == null || raw === "") return; // Other / none = inert
        options.onClick(raw);
      });
    }
    return inst;
  }

  function trendFallbackHTML(rows, L) {
    if (!rows || !rows.length) return '<div class="al-empty">' + (T.empty.text) + "</div>";
    return '<table class="al-tbl al-chart-fbt"><thead><tr><th>' + C.esc(L.date || "Date") +
      '</th><th class="r">' + C.esc(L["new"] || "New") + '</th><th class="r">' +
      C.esc(L.resolved || "Resolved") + '</th><th class="r">' + C.esc(L.ignored || "Ignored") +
      "</th></tr></thead><tbody>" + rows.map(function (x) {
        return "<tr><td>" + C.esc(x.day) + '</td><td class="r">' + x["new"] +
          '</td><td class="r">' + x.resolved + '</td><td class="r">' + x.ignored + "</td></tr>";
      }).join("") + "</tbody></table>";
  }

  // renderTrend(element, rows, options)
  //  rows: [{day, new, resolved, ignored}] straight from api_dashboard.trend
  //  options: { labels:{new,resolved,ignored,date,title}, fallbackEl, onPointClick(day) }
  // TRUTHFUL series only - New / Resolved / Ignored. No fabricated severity,
  // backlog or cumulative series.
  function renderTrend(el, rows, options) {
    options = options || {};
    rows = rows || [];
    var L = options.labels || {};
    if (!C.ok()) { C.fallback(el, options.fallbackEl, trendFallbackHTML(rows, L)); return null; }
    C.clearFallback(el, options.fallbackEl);
    C.dispose(el);
    var xs = rows.map(function (d) { return d.day; });
    var pal = T.palette("series");
    var option = {
      animationDuration: T.animation.duration,
      animationEasing: T.animation.easing,
      aria: { enabled: true, label: { description: L.title || "Alert trend" } },
      tooltip: T.tooltip({ trigger: "axis" }),
      legend: T.legend({ top: 2, data: [L["new"] || "New", L.resolved || "Resolved", L.ignored || "Ignored"] }),
      grid: T.grid(),
      xAxis: { type: "category", data: xs, boundaryGap: true, axisLabel: T.axisLabel() },
      yAxis: { type: "value", minInterval: 1, axisLabel: T.axisLabel(), splitLine: T.splitLine() },
      series: [
        { name: L["new"] || "New", type: "bar", barMaxWidth: 22,
          itemStyle: { color: pal[0], borderRadius: [3, 3, 0, 0] },
          data: rows.map(function (d) { return d["new"]; }) },
        { name: L.resolved || "Resolved", type: "line", smooth: true, symbol: "circle", symbolSize: 5,
          itemStyle: { color: pal[1] },
          data: rows.map(function (d) { return d.resolved; }) },
        { name: L.ignored || "Ignored", type: "line", smooth: true, symbol: "circle", symbolSize: 4,
          itemStyle: { color: pal[2] }, lineStyle: { type: "dashed" },
          data: rows.map(function (d) { return d.ignored; }) }
      ]
    };
    var inst = C.setOption(el, option, true);
    if (inst && typeof options.onPointClick === "function") {
      inst.off("click");
      inst.on("click", function (p) {
        if (p.componentType !== "series") return;
        var day = xs[p.dataIndex];
        if (day) options.onPointClick(day);
      });
    }
    return inst;
  }

  window.AlertCharts = {
    renderDistributionDonut: renderDistributionDonut,
    renderTrend: renderTrend
  };
})();
