/*!
 * ECChartTheme - ERP-wide chart visual source of truth (ecentric_workspace).
 * The single place that owns chart colours, palettes, typography and the
 * tooltip/axis/grid/legend/animation style fragments. No chart page should
 * hardcode ordinary palettes or styling after this module exists.
 *
 * Exposes exactly one global: window.ECChartTheme
 * Pure data + small style-fragment builders; depends on nothing.
 */
(function () {
  "use strict";

  // Light + (where practical) dark-ready semantic tokens.
  var TOKENS = {
    light: {
      ink: "#0f172a", muted: "#64748b", faint: "#94a3b8",
      grid: "#eef2f7", axis: "#64748b", border: "#e2e8f0",
      surface: "#ffffff", surfaceAlt: "#f8fafc"
    },
    dark: {
      ink: "#e5e7eb", muted: "#94a3b8", faint: "#64748b",
      grid: "#1e293b", axis: "#94a3b8", border: "#334155",
      surface: "#0b1220", surfaceAlt: "#111827"
    }
  };

  var theme = {
    // Detect dark mode lazily so a host page/theme can flip it.
    mode: function () {
      try {
        return (window.matchMedia &&
          window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
      } catch (e) { return "light"; }
    },
    tokens: function () { return TOKENS[this.mode()] || TOKENS.light; },

    // Semantic colours (status meaning, stable across light/dark).
    semantic: {
      critical: "#db2777", warning: "#d4a017", ok: "#1a8754",
      info: "#2f6db0", neutral: "#94a3b8"
    },

    // Dimension palettes - distinct, coordinated families (NOT one navy ramp).
    // Index 3 (lightest) is conventionally used for the "Other" bucket.
    palettes: {
      brand:    ["#1f3a5f", "#2f6db0", "#5b9bd5", "#c3d4e8"], // blue / navy
      platform: ["#0f766e", "#14a8a0", "#5fd0c8", "#bfe9e6"], // teal / cyan
      rule:     ["#b45309", "#ea8b2f", "#f4b46b", "#f6dcb8"], // amber / coral
      // Trend series order: New, Resolved, Ignored.
      series:   ["#2f6db0", "#0f766e", "#94a3b8"]
    },
    palette: function (name) { return this.palettes[name] || this.palettes.brand; },

    typography: {
      fontFamily: "Inter, system-ui, -apple-system, Segoe UI, Arial, sans-serif",
      base: 12, axis: 10, legend: 11, centerTotal: 21, centerSub: 10
    },

    animation: { duration: 450, durationUpdate: 300, easing: "cubicOut" },

    empty: { text: "—", color: "#94a3b8" },

    // ECharts loading-spinner options.
    loading: function () {
      var t = this.tokens();
      return {
        text: "", color: this.semantic.info, textColor: t.muted,
        maskColor: this.mode() === "dark" ? "rgba(11,18,32,0.6)" : "rgba(255,255,255,0.6)",
        zlevel: 0
      };
    },

    // --- reusable ECharts option fragments (style only; no data) -------------
    tooltip: function (extra) {
      var t = this.tokens();
      return merge({
        confine: true, borderWidth: 1, borderColor: t.border,
        backgroundColor: t.surface,
        textStyle: { color: t.ink, fontSize: this.typography.base,
                     fontFamily: this.typography.fontFamily },
        extraCssText: "box-shadow:0 8px 24px rgba(15,23,42,0.12);border-radius:8px;"
      }, extra || {});
    },
    axisLabel: function () {
      var t = this.tokens();
      return { fontSize: this.typography.axis, color: t.axis,
               fontFamily: this.typography.fontFamily, hideOverlap: true };
    },
    splitLine: function () { return { lineStyle: { color: this.tokens().grid } }; },
    grid: function (extra) {
      return merge({ left: 42, right: 18, top: 32, bottom: 30, containLabel: false }, extra || {});
    },
    legend: function (extra) {
      var t = this.tokens();
      return merge({
        icon: "circle", itemWidth: 10, itemHeight: 10,
        textStyle: { fontSize: this.typography.legend, color: t.muted,
                     fontFamily: this.typography.fontFamily }
      }, extra || {});
    },
    centerText: function (total, subLabel) {
      var t = this.tokens();
      return [
        { type: "text", left: "center", top: "38%",
          style: { text: String(total), textAlign: "center",
                   fontSize: this.typography.centerTotal, fontWeight: 700,
                   fontFamily: this.typography.fontFamily, fill: t.ink } },
        { type: "text", left: "center", top: "52%",
          style: { text: subLabel || "", textAlign: "center",
                   fontSize: this.typography.centerSub, fill: t.muted,
                   fontFamily: this.typography.fontFamily } }
      ];
    }
  };

  // tiny shallow merge (theme-local; the heavier deep merge lives in ECCharts).
  function merge(base, over) {
    var out = {}, k;
    for (k in base) if (Object.prototype.hasOwnProperty.call(base, k)) out[k] = base[k];
    for (k in over) if (Object.prototype.hasOwnProperty.call(over, k)) out[k] = over[k];
    return out;
  }

  window.ECChartTheme = theme;
})();
