// Copyright (c) 2026, eCentric and contributors
// /quiz -- cua vao Quiz truc tiep: nhap ma phong, phong dang mo, "Quiz cua toi" (lich su + ve).
// Ban dao tao / HR thay them: danh sach bo quiz, mo phong, phong gan day.
(function () {
  "use strict";
  var D = window.ECDt;
  var root = D.byId("dt-root");
  var PHASE = { lobby: "Đang chờ vào", question: "Đang chơi", locked: "Đang chơi", reveal: "Đang chơi", board: "Đang chơi", ended: "Đã kết thúc", cancelled: "Đã huỷ" };

  function load() {
    root.innerHTML = '<div class="dt-wrap">' + D.skel(3) + "</div>";
    D.api("quiz_home").then(function (d) {
      render(d);
      if (d.can_host) D.api("quiz_list").then(hostPart, function (e) { D.toast(D.msg(e), true); });
    }, function (e) { root.innerHTML = '<div class="dt-wrap"><p class="dt-err">' + D.esc(D.msg(e)) + "</p></div>"; });
  }

  function render(d) {
    var t = d.tickets || {};
    var h = '<div class="dt-wrap"><section class="dt-hero"><div style="flex:1;min-width:260px"><h1>Quiz trực tiếp</h1><p>Được hỏi AI thoải mái, chỉ cấm tool can thiệp. Nhập mã 6 số trên màn chiếu để vào.</p>' +
      '<div class="dt-row" style="margin-top:12px"><input id="dt-code" class="dt-code-in" style="max-width:240px;font-size:24px;padding:10px" inputmode="numeric" maxlength="6" placeholder="Mã phòng" aria-label="Mã phòng">' +
      '<button class="dt-b gold lg" id="dt-go">Vào</button></div></div><div class="dt-stat"><b>' + (t.this_week || 0) + "/" + (t.cap || 3) +
      '</b><span>vé tuần này</span></div></section>';
    if ((d.rooms || []).length) {
      h += '<div class="dt-panel dt-pad"><h2 class="dt-h2">Phòng đang mở</h2><div class="dt-grid3" style="margin-top:10px">' + d.rooms.map(function (r) {
        return '<a class="dt-panel dt-pad" style="text-decoration:none;color:inherit" href="/quiz/choi?c=' + D.esc(r.code) + '"><b>' + D.esc(r.title) +
          '</b><div class="dt-row dt-small dt-muted"><span>Mã ' + D.esc(r.code) + "</span><span>·</span><span>" + D.esc(r.host) + '</span></div><span class="dt-chip ' +
          (r.phase === "lobby" ? "ok" : "nv") + '">' + (PHASE[r.phase] || r.phase) + "</span></a>";
      }).join("") + "</div></div>";
    }
    h += '<div id="dt-host"></div><div class="dt-panel dt-pad"><h2 class="dt-h2">Quiz của tôi</h2>' + ((d.played || []).length ? '<table class="dt-table" style="margin-top:8px"><thead><tr><th>Quiz</th><th>Tên trong game</th><th>Điểm</th><th>Hạng</th><th>Giải</th></tr></thead><tbody>' +
      d.played.map(function (p) {
        return "<tr><td><b>" + D.esc(p.title) + '</b><br><span class="dt-small dt-muted">' + D.fmtDate(p.ended_at) + " " + (PHASE[p.phase] || "") + "</span></td><td>" + D.esc(p.nickname) +
          "</td><td>" + D.fmtNum(p.score) + "</td><td>" + (p.rank ? p.rank + "/" + (p.players || "") : "—") + "</td><td>" + (p.awards || []).map(function (a) {
            return '<span class="dt-chip ok">' + D.esc(a.label) + (a.tickets ? " · " + a.tickets + " vé" : "") + (a.gift ? " · " + D.esc(a.gift) : "") + "</span>";
          }).join(" ") + "</td></tr>";
      }).join("") + "</tbody></table>" : '<p class="dt-empty">Bạn chưa chơi quiz nào.</p>') + "</div>" +
      '<div class="dt-panel dt-pad"><h2 class="dt-h2">Vé quay số tuần</h2><p class="dt-muted dt-small">Tối đa ' + (t.cap || 3) + " vé / người / tuần, tính chung quiz và bài thực hành. " + D.esc(t.week || "") + "</p>" +
      ((t.history || []).length ? "<ul>" + t.history.slice(0, 10).map(function (x) {
        return "<li>" + D.esc(x.label) + " · <b>" + x.count + " vé</b>" + (x.revoked ? ' <span class="dt-chip bad">đã thu hồi</span>' : "") + "</li>";
      }).join("") + "</ul>" : '<p class="dt-muted">Chưa có vé.</p>') + "</div></div>";
    root.innerHTML = h;
    var inp = D.byId("dt-code");
    function go() { var c = inp.value.replace(/\D/g, ""); if (c.length !== 6) return D.toast("Mã phòng gồm 6 số.", true); location.href = "/quiz/choi?c=" + c; }
    D.byId("dt-go").onclick = go;
    inp.onkeydown = function (e) { if (e.key === "Enter") go(); };
  }

  function hostPart(d) {
    var box = D.byId("dt-host");
    if (!box) return;
    var live = (d.rooms || []).filter(function (r) { return r.live; });
    box.innerHTML = '<div class="dt-panel dt-pad"><div class="dt-row"><h2 class="dt-h2">Ban đào tạo · Bộ quiz</h2><span class="dt-sp"></span>' +
      '<a class="dt-b pri" href="/quiz/soan">' + D.icon("plus") + " Tạo bộ quiz</a></div>" +
      (live.length ? '<div class="dt-row" style="margin:10px 0">' + live.map(function (r) {
        return '<a class="dt-b gold" href="/quiz/chieu?s=' + encodeURIComponent(r.name) + '">' + D.icon("play") + " Màn chiếu " + D.esc(r.title) + " · " + D.esc(r.code) + "</a>";
      }).join("") + "</div>" : "") +
      ((d.quizzes || []).length ? '<table class="dt-table" style="margin-top:8px"><thead><tr><th>Bộ quiz</th><th>Số câu</th><th>Trạng thái</th><th>Người tạo</th><th></th></tr></thead><tbody>' +
        d.quizzes.map(function (q) {
          return "<tr><td><b>" + D.esc(q.title) + '</b><br><span class="dt-small dt-muted">Sửa ' + D.fmtDate(q.modified) + (q.last_played ? " · chơi " + D.fmtDate(q.last_played) : "") +
            "</span></td><td>" + (q.n_questions || 0) + '</td><td><span class="dt-chip ' + (q.status === "Ready" ? "ok" : "warn") + '">' + (q.status === "Ready" ? "Sẵn sàng" : "Nháp") +
            "</span></td><td>" + D.esc(q.owner_name) + '</td><td style="text-align:right;white-space:nowrap"><a class="dt-b sm" href="/quiz/soan?q=' + encodeURIComponent(q.name) + '">Sửa</a> ' +
            (q.status === "Ready" ? '<button class="dt-b sm pri" data-open="' + D.esc(q.name) + '">' + D.icon("play") + " Mở phòng</button>" : "") + "</td></tr>";
        }).join("") + "</tbody></table>" : '<p class="dt-empty">Chưa có bộ quiz nào.</p>') + "</div>";
    D.qsa(box, "[data-open]").forEach(function (b) {
      b.onclick = function () {
        D.busy(b, true);
        D.api("room_open", { quiz: b.dataset.open }, true).then(function (r) { location.href = "/quiz/chieu?s=" + encodeURIComponent(r.session); },
          function (e) { D.busy(b, false); D.toast(D.msg(e), true); });
      };
    });
  }

  load();
})();
