// Copyright (c) 2026, eCentric and contributors
// ec_st_stats.js -- khoi "Thong ke su dung" tren /kalodata, CHI quan ly thay (server tu kiem quyen o
// shared_tools.views.stats). Tai mot lan khi mo trang va khi doi khoang 7 / 30 / 90 ngay; KHONG tai lai
// theo nhip 10 s cua trang (so lieu thong ke khong can tung giay).
// Bieu do: mot chuoi, mot mau (#4F5FC8 - da chay validate_palette: dat), cot bo goc 4px, tooltip khi re chuot,
// so lieu chinh van doc duoc bang chu (o so + bang nguoi dung) -> khong phu thuoc mau.
(function () {
  "use strict";
  if (window.ECStStats) return;
  var data = null, days = 30, loading = false, error = "";

  function E(s) { return window.ECSt.esc(s); }
  function fmt(n) { return Number(n || 0).toLocaleString("vi-VN"); }

  async function load(d) {
    days = d || days;
    loading = true; error = "";
    window.ECSt.rerender();
    try {
      data = await window.ECSt.api("stats", { tool: "kalodata", days: days }, false);
    } catch (e) {
      error = window.ECSt.msg(e);
    } finally {
      loading = false;
      window.ECSt.rerender();
    }
  }

  function tile(label, value, sub) {
    return '<div class="st-kpi"><div class="st-kpi-v">' + E(value) + '</div><div class="st-kpi-l">' + E(label) + '</div>' +
      (sub ? '<div class="st-kpi-s">' + E(sub) + '</div>' : "") + '</div>';
  }

  // bars: [{label, value, tip}] ; every: hien nhan truc x moi n cot
  function bars(title, list, unit, every) {
    var max = Math.max.apply(null, list.map(function (b) { return b.value; }).concat([1]));
    var total = list.reduce(function (a, b) { return a + b.value; }, 0);
    var cols = list.map(function (b, i) {
      var h = b.value ? Math.max(3, Math.round(b.value / max * 100)) : 0;
      return '<div class="st-bar-col" data-tip="' + E(b.tip) + '" tabindex="0" aria-label="' + E(b.tip) + '">' +
        '<div class="st-bar-fill" style="height:' + h + '%"></div>' +
        '<div class="st-bar-x">' + (i % every === 0 ? E(b.label) : "") + '</div></div>';
    }).join("");
    return '<figure class="st-chart"><figcaption><b>' + E(title) + '</b><span>cao nhất ' + fmt(max) + ' ' + E(unit) +
      ' · tổng ' + fmt(total) + ' ' + E(unit) + '</span></figcaption>' +
      '<div class="st-bars" role="img" aria-label="' + E(title) + '">' + cols + '</div></figure>';
  }

  function card() {
    var seg = [7, 30, 90].map(function (d) {
      return '<button type="button" class="st-seg' + (d === days ? " on" : "") + '" data-act="stats" data-days="' + d + '" aria-pressed="' +
        (d === days) + '">' + d + ' ngày</button>';
    }).join("");
    var head = '<div class="st-card-head"><h2 class="st-h2" id="st-h-stats">Thống kê sử dụng</h2><div class="st-segs" role="group" aria-label="Khoảng thời gian">' + seg + '</div></div>';
    var body;
    if (error) body = '<p class="st-empty">' + E(error) + '</p>';
    else if (!data) body = '<div class="st-skel" style="width:60%"></div><div class="st-skel" style="width:90%"></div>';
    else {
      var k = data.kpi;
      body = '<div class="st-kpis">' +
        tile("Lượt dùng", fmt(k.sessions), fmt(k.users) + " người") +
        tile("Giờ sử dụng", fmt(k.hours), "giờ") +
        tile("Lần xuất bảng", fmt(k.exports), fmt(k.pages) + " trang") +
        tile("Dòng đã xuất", fmt(k.rows)) +
        tile("Chờ trung bình", fmt(k.avg_wait_min) + " phút", "từ lúc vào hàng") +
        tile("Không mở kịp", k.no_show_pct + "%", fmt(k.idle_end) + " lượt hết vì để yên") +
        '</div><div class="st-charts">' +
        bars("Phút sử dụng mỗi ngày (14 ngày gần nhất)", data.by_day.map(function (d) {
          return { label: d.date, value: d.minutes, tip: d.date + ": " + fmt(d.minutes) + " phút" };
        }), "phút", 2) +
        bars("Lượt bắt đầu theo giờ trong ngày (" + data.days + " ngày)", data.by_hour.map(function (v, h) {
          return { label: h + "h", value: v, tip: h + ":00–" + h + ":59: " + fmt(v) + " lượt" };
        }), "lượt", 3) +
        '</div>' + topTable(data.top);
    }
    return '<section class="st-card st-stats st-o5" aria-labelledby="st-h-stats" aria-busy="' + loading + '">' + head + body + '</section>';
  }

  function topTable(top) {
    if (!top.length) return '<p class="st-empty">Chưa có ai dùng trong khoảng này.</p>';
    var rows = top.map(function (u) {
      return '<tr><td><b>' + E(u.name) + '</b>' + (u.department ? '<span class="st-muted"> · ' + E(u.department) + '</span>' : "") + '</td>' +
        '<td class="num">' + fmt(u.sessions) + '</td><td class="num">' + fmt(u.minutes) + '</td><td class="num">' + fmt(u.exports) + '</td><td class="num">' + fmt(u.rows) + '</td></tr>';
    }).join("");
    return '<div class="st-table-wrap"><table class="st-table st-top"><caption>Người dùng nhiều nhất</caption><thead><tr><th scope="col">Người dùng</th>' +
      '<th scope="col" class="num">Lượt</th><th scope="col" class="num">Phút</th><th scope="col" class="num">Lần xuất</th><th scope="col" class="num">Dòng</th></tr></thead><tbody>' +
      rows + '</tbody></table></div>';
  }

  window.ECStStats = { card: card, load: load };
})();
