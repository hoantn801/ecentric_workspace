// Copyright (c) 2026, eCentric and contributors
// ec_survey_hub.js -- trang /khao-sat: khao sat dang mo cho toi, da lam, bang vang.
(function () {
  "use strict";
  var S = window.ECSvy, esc = S.esc;
  var root = S.byId("svy-root");
  if (!root || root.getAttribute("data-page") !== "hub") return;
  var st = { tab: "open", data: null };

  function rewardChip(c) {
    if (c.reward_mode === "wheel") return '<span class="svy-pill gold">' + S.icon("gift") + "Vòng quay" + (c.prizes && c.prizes.length ? ": " + esc(c.prizes.join(", ")) : "") + "</span>";
    if (c.reward_mode === "lucky_number") return '<span class="svy-pill gold">' + S.icon("gift") + "Số may mắn" + (c.prizes && c.prizes.length ? ": " + esc(c.prizes.join(", ")) : "") + "</span>";
    return "";
  }

  function openCard(c) {
    var soon = c.effective === "scheduled";
    var meta = ['<span><b>' + c.questions + "</b> câu hỏi</span>"];
    if (c.close_at) meta.push("<span>Hạn <b>" + esc(S.fmtDt(c.close_at)) + "</b></span>");
    if (c.anonymous) meta.push("<span>" + S.icon("lock") + " Ẩn danh</span>");
    if (c.is_quiz) meta.push("<span>Bài kiểm tra</span>");
    return '<article class="svy-card" style="--c:' + esc(c.accent_color || "#2C3DA6") + '">' +
      '<div class="svy-row between">' + (soon ? '<span class="svy-pill warn">Mở lúc ' + esc(S.fmtDt(c.open_at)) + "</span>"
        : (c.close_at ? '<span class="svy-pill run">' + esc(S.deadline(c.close_at)) + "</span>" : '<span class="svy-pill ok">Đang mở</span>')) + rewardChip(c) + "</div>" +
      "<h3>" + esc(c.title) + "</h3>" + (c.description ? '<div class="desc">' + esc(c.description) + "</div>" : "") +
      '<div class="svy-meta">' + meta.join("") + "</div>" +
      '<div class="foot"><span></span>' + (soon ? '<span class="svy-b" aria-disabled="true" style="opacity:.6">Chưa mở</span>'
        : '<a class="svy-b pri" href="/khao-sat/lam?s=' + encodeURIComponent(c.name) + '">Làm khảo sát</a>') + "</div></article>";
  }

  function doneCard(c) {
    var reward = "";
    if (c.reward_mode === "lucky_number" && c.lucky_number) reward = '<span class="svy-ticket">Số ' + String(c.lucky_number).padStart(3, "0") + "</span>";
    if (c.reward_result === "Win") reward = '<span class="svy-pill ok">' + S.icon("trophy") + "Trúng " + esc(c.prize_label) + "</span>";
    else if (c.reward_result === "Lose") reward = '<span class="svy-pill mute">Chúc may mắn lần sau</span>';
    else if (c.reward_mode === "wheel") reward = '<a class="svy-pill gold" href="/khao-sat/lam?s=' + encodeURIComponent(c.name) + '">' + S.icon("gift") + "Chưa quay - quay ngay</a>";
    return '<article class="svy-card" style="--c:' + esc(c.accent_color || "#2C3DA6") + '"><div class="svy-row between"><span class="svy-pill ok">' + S.icon("check") + "Đã nộp</span>" + reward + "</div>" +
      "<h3>" + esc(c.title) + '</h3><div class="svy-meta"><span>Nộp lúc <b>' + esc(S.fmtDt(c.submitted_at)) + "</b></span>" +
      (c.effective === "open" ? "" : "<span>Đã đóng</span>") + '</div><div class="foot"><span></span><a class="svy-b sm" href="/khao-sat/lam?s=' + encodeURIComponent(c.name) + '">Xem</a></div></article>';
  }

  function board(list) {
    if (!list.length) return '<div class="svy-panel svy-empty"><b>Chưa có ai trúng quà</b>Làm khảo sát có quà để có tên ở đây.</div>';
    var medals = ["🥇", "🥈", "🥉"];
    return '<div class="svy-panel svy-board">' + list.map(function (w, i) {
      return '<div class="it' + (w.me ? " me" : "") + '"><span class="svy-av">' + esc(S.initials(w.name)) + '</span><div class="svy-grow"><b>' + esc(w.name) + (w.me ? " (bạn)" : "") +
        '</b><div class="svy-small svy-muted">' + esc(w.survey) + " · " + esc(S.fmtDt(w.at)) + '</div></div><span class="svy-pill gold">' + S.icon("gift") + esc(w.prize) + "</span>" +
        (i < 3 ? '<span class="svy-medal" aria-hidden="true">' + medals[i] + "</span>" : "") + "</div>";
    }).join("") + "</div>";
  }

  function render() {
    var d = st.data;
    var tabs = [["open", "Đang mở", d.open.length], ["done", "Đã làm", d.done.length], ["board", "Bảng vàng", d.board.length]];
    var h = '<div class="svy-wrap"><section class="svy-hero"><div><h1>Khảo sát</h1><p>Mọi khảo sát của công ty ở một chỗ. Mỗi phiếu chỉ mất vài phút - có khảo sát còn kèm quà may mắn.</p></div>' +
      '<div class="svy-row"><div class="svy-stats"><div class="svy-stat hl"><span>Chờ bạn</span><b>' + d.open.filter(function (c) { return c.effective === "open"; }).length + '</b></div><div class="svy-stat"><span>Đã làm</span><b>' + d.done.length + "</b></div></div>" +
      (d.can_create ? '<a class="svy-b gold" href="/khao-sat/quan-ly">Quản lý khảo sát</a>' : "") + "</div></section>";
    h += '<nav class="svy-tabs" role="tablist">' + tabs.map(function (t) {
      return '<button class="svy-tab' + (st.tab === t[0] ? " on" : "") + '" role="tab" aria-selected="' + (st.tab === t[0]) + '" data-tab="' + t[0] + '">' + t[1] + '<span class="n">' + t[2] + "</span></button>";
    }).join("") + "</nav>";
    if (st.tab === "open") h += d.open.length ? '<div class="svy-cards">' + d.open.map(openCard).join("") + "</div>" : '<div class="svy-panel svy-empty"><b>Không có khảo sát nào đang chờ bạn</b>Khi có khảo sát mới, bạn sẽ nhận thông báo qua chuông ERP.</div>';
    if (st.tab === "done") h += d.done.length ? '<div class="svy-cards">' + d.done.map(doneCard).join("") + "</div>" : '<div class="svy-panel svy-empty"><b>Bạn chưa làm khảo sát nào</b></div>';
    if (st.tab === "board") h += board(d.board);
    root.innerHTML = h + "</div>";
  }

  root.addEventListener("click", function (e) {
    var t = e.target.closest("[data-tab]");
    if (t) { st.tab = t.getAttribute("data-tab"); render(); }
  });

  function boot() {
    S.api("hub").then(function (d) { st.data = d; render(); }, function (e) {
      root.innerHTML = '<div class="svy-wrap"><div class="svy-panel svy-empty"><b>Không tải được danh sách khảo sát</b>' + esc(e.svyMessage) +
        '<div style="margin-top:12px"><button class="svy-b" onclick="location.reload()">Thử lại</button></div></div></div>';
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
