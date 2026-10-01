// Copyright (c) 2026, eCentric and contributors
// ec_survey_summary.js -- ve tong hop ket qua theo tung cau hoi (thanh ngang CSS, khong can
// thu vien bieu do). Dung o tab "Kết quả" cua trinh soan va o "Xem tóm tắt" sau khi nop.
//
//   ECSvySummary.render(form, summary, {texts: bool, fileLink: fn(url) -> href})
//
// `summary` = surveys/domain/summary.py::summarize (hoac public_summary - khong co chu tu do).
(function () {
  "use strict";
  if (window.ECSvySummary) return;
  var S = window.ECSvy, esc = S.esc;

  function bar(label, n, total, color) {
    var pct = total ? Math.round(100 * n / total) : 0;
    return '<div class="svy-bar"><span class="t" title="' + esc(label) + '">' + esc(label) + '</span><span class="track"><i style="width:' + pct + "%" +
      (color ? ";background:" + esc(color) : "") + '"></i></span><span class="v"><b>' + n + "</b> · " + pct + "%</span></div>";
  }

  function choice(q, s) {
    var total = s.answered || 0;
    var h = '<div class="svy-bars">';
    (q.options || []).forEach(function (o) { h += bar(o.label, s.counts[o.id] || 0, total); });
    if (q.allow_other) h += bar("Khác", s.other || 0, total, "#9ca3af");
    h += "</div>";
    if (s.other_samples && s.other_samples.length) h += '<div class="svy-lbl" style="margin-top:10px">Câu trả lời "Khác"</div>' + texts(s.other_samples);
    return h;
  }

  function numbers(q, s) {
    var keys = Object.keys(s.distribution || {}).sort(function (a, b) { return a - b; });
    var h = '<div class="svy-row" style="gap:18px;margin-bottom:10px">';
    h += '<div><div class="svy-eyebrow">Trung bình</div><div class="svy-avg">' + (s.average == null ? "–" : String(s.average).replace(".", ",")) +
      '<span class="svy-small svy-muted"> / ' + (q.type === "rating" ? q.rating_max : q.scale_max) + "</span></div></div>";
    if (s.nps !== undefined) h += '<div><div class="svy-eyebrow">Điểm NPS</div><div class="svy-avg" style="color:' + (s.nps >= 0 ? "var(--ok)" : "var(--bad)") + '">' + s.nps + "</div></div>";
    h += "</div><div class=\"svy-bars\">";
    keys.forEach(function (k) {
      var label = k + (q.type === "rating" ? " ★" : "");
      if (q.type === "scale" && +k === q.scale_min && q.min_label) label += " - " + q.min_label;
      if (q.type === "scale" && +k === q.scale_max && q.max_label) label += " - " + q.max_label;
      h += bar(label, s.distribution[k], s.answered);
    });
    return h + "</div>";
  }

  function gridTable(q, s) {
    var h = '<div class="svy-grid"><table><thead><tr><th></th>';
    (q.cols || []).forEach(function (c) { h += "<th>" + esc(c.label) + "</th>"; });
    h += "</tr></thead><tbody>";
    (q.rows || []).forEach(function (r) {
      var row = (s.table || {})[r.id] || {}, tot = 0, best = 0;
      (q.cols || []).forEach(function (c) { tot += row[c.id] || 0; best = Math.max(best, row[c.id] || 0); });
      h += '<tr><td class="rl">' + esc(r.label) + "</td>";
      (q.cols || []).forEach(function (c) {
        var n = row[c.id] || 0;
        var a = tot ? (0.12 + 0.6 * n / tot) : 0;
        h += '<td style="background:rgba(44,61,166,' + a.toFixed(2) + ");color:" + (a > 0.45 ? "#fff" : "inherit") + ";font-weight:" + (n && n === best ? 700 : 400) + '">' + n + "</td>";
      });
      h += "</tr>";
    });
    return h + "</tbody></table></div>";
  }

  function ranking(q, s) {
    var rows = (q.options || []).map(function (o) { return { label: o.label, avg: (s.average_rank || {})[o.id] }; });
    rows.sort(function (a, b) { return (a.avg || 99) - (b.avg || 99); });
    var h = '<div class="svy-small svy-muted" style="margin-bottom:8px">Thứ hạng trung bình (càng nhỏ càng được ưu tiên)</div><div class="svy-rank">';
    rows.forEach(function (r, i) {
      h += '<div class="it"><span class="pos">' + (i + 1) + '</span><span class="svy-grow">' + esc(r.label) + '</span><span class="svy-muted svy-small">' + (r.avg == null ? "–" : String(r.avg).replace(".", ",")) + "</span></div>";
    });
    return h + "</div>";
  }

  function texts(list, q, opts) {
    var h = '<div class="svy-texts">';
    list.forEach(function (v) {
      if (Array.isArray(v)) {
        h += "<div>" + v.map(function (f) {
          var href = opts && opts.fileLink ? opts.fileLink(f.url) : "";
          return href ? '<a href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(f.name) + "</a>" : esc(f.name);
        }).join(", ") + "</div>";
      } else h += "<div>" + esc(q && q.type === "date" ? S.fmtDate(v + " 00:00") : v) + "</div>";
    });
    return h + "</div>";
  }

  function render(form, summary, opts) {
    opts = opts || {};
    var qs = S.questions(form), out = "";
    if (!qs.length) return '<div class="svy-empty">Chưa có câu hỏi.</div>';
    qs.forEach(function (q, i) {
      var s = (summary.questions || {})[q.id] || { answered: 0 };
      var h = '<section class="svy-panel svy-pad"><div class="svy-row between" style="align-items:flex-start"><div class="svy-grow"><div class="svy-eyebrow">Câu ' + (i + 1) + "</div>" +
        '<div style="font-weight:600;font-size:15px">' + esc(q.title || "Câu hỏi") + '</div></div><span class="svy-pill mute">' + (s.answered || 0) + " trả lời</span></div>" +
        '<div style="margin-top:12px">';
      if (!s.answered) h += '<div class="svy-muted svy-small">Chưa có câu trả lời.</div>';
      else if (q.type === "single" || q.type === "multi" || q.type === "dropdown") h += choice(q, s);
      else if (q.type === "scale" || q.type === "rating") h += numbers(q, s);
      else if (q.type === "grid_single" || q.type === "grid_multi") h += gridTable(q, s);
      else if (q.type === "ranking") h += ranking(q, s);
      else if (s.samples && opts.texts !== false) h += texts(s.samples, q, opts) + (s.answered > s.samples.length ? '<div class="svy-small svy-muted" style="margin-top:6px">Hiện ' + s.samples.length + "/" + s.answered + " câu trả lời mới nhất - xem đủ trong file Excel.</div>" : "");
      else h += '<div class="svy-muted svy-small">' + s.answered + " người đã trả lời câu này.</div>";
      out += h + "</div></section>";
    });
    return out;
  }

  window.ECSvySummary = { render: render };
})();
