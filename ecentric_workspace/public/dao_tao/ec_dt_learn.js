// Copyright (c) 2026, eCentric and contributors
// /dao-tao -- trang Hoc (huong D): Bai tuan · Thu vien · Binh chon · Phan thuong.
(function () {
  "use strict";
  var D = window.ECDt;
  var root = D.byId("dt-root");
  var data = null, tab = (location.hash || "#tuan").slice(1), filt = { topic: "", level: "", tool: "", q: "" };
  var STEPS = ["view", "quiz", "practice", "done"];

  function load() {
    root.innerHTML = '<div class="dt-wrap">' + D.skel(3) + "</div>";
    D.api("learn_hub").then(function (d) { data = d; render(); },
      function (e) { root.innerHTML = '<div class="dt-wrap"><p class="dt-err">' + D.esc(D.msg(e)) + "</p></div>"; });
  }

  function card(l) {
    var idx = STEPS.indexOf(l.step);
    var bars = STEPS.filter(function (s) { return s === "view" || (s === "quiz" && l.has_quiz) || (s === "practice" && l.has_practice); });
    return '<div class="dt-panel dt-lesson"><div class="dt-row dt-small"><span class="dt-chip nv">' + D.esc(l.topic) + '</span><span class="dt-chip">' + D.esc(l.level) +
      '</span><span class="dt-chip">' + D.esc(l.tool) + '</span><span class="dt-sp"></span><span class="dt-muted">' + D.esc(l.week_label) + "</span></div><h3>" + D.esc(l.title) +
      '</h3><p class="dt-muted">' + D.esc(l.summary) + '</p><div class="dt-steps">' + bars.map(function (s) { return "<i" + (STEPS.indexOf(s) < idx || l.step === "done" ? ' class="on"' : "") + "></i>"; }).join("") +
      '</div><div class="dt-row">' + (l.quiz_score != null && l.has_quiz ? '<span class="dt-small dt-muted">Quiz ' + l.quiz_score + "/" + l.quiz_scored + "</span>" : "") +
      '<span class="dt-sp"></span><a class="dt-b ' + (l.step === "done" ? "" : "pri") + '" href="' + D.esc(l.url) + '">' + D.esc(l.step_label) + "</a></div></div>";
  }

  function render() {
    var t = data.tickets || {};
    var h = '<div class="dt-wrap"><section class="dt-hero"><div style="flex:1;min-width:260px"><h1>Đào tạo</h1><p>Mỗi tuần một bài ngắn về AI cho công việc. Xem bài → làm quiz → nộp bài thực hành → nhận vé quay số.</p>' +
      '<div class="dt-row" style="margin-top:12px"><a class="dt-b gold" href="/quiz">' + D.icon("play") + " Quiz trực tiếp</a>" + (data.can_manage ? '<a class="dt-b" href="/dao-tao/quan-ly">Quản lý bài học</a>' : "") +
      '</div></div><div class="dt-stat"><b>' + data.done + "/" + data.total + '</b><span>bài đã xong</span></div><div class="dt-stat"><b>' + (t.this_week || 0) + "/" + (t.cap || 3) +
      '</b><span>vé tuần này</span></div></section><div class="dt-tabs" role="tablist">' +
      [["tuan", "Bài tuần"], ["thu-vien", "Thư viện"], ["binh-chon", "Bình chọn"], ["thuong", "Phần thưởng"]].map(function (x) {
        return '<button class="dt-tab" role="tab" data-tab="' + x[0] + '" aria-selected="' + (tab === x[0]) + '">' + x[1] + "</button>";
      }).join("") + '</div><div id="dt-tabbody"></div></div>';
    root.innerHTML = h;
    D.qsa(root, "[data-tab]").forEach(function (b) { b.onclick = function () { tab = b.dataset.tab; history.replaceState(null, "", "#" + tab); render(); }; });
    var body = D.byId("dt-tabbody");
    if (tab === "thu-vien") library(body);
    else if (tab === "binh-chon") votes(body);
    else if (tab === "thuong") rewards(body);
    else body.innerHTML = data.week.length ? '<div class="dt-grid2">' + data.week.map(card).join("") + "</div>" : '<p class="dt-empty">Tuần này chưa có bài mới.</p>';
  }

  function library(body) {
    function sel(k, list, lbl) {
      return '<select class="dt-sel" data-f="' + k + '" style="width:auto"><option value="">' + lbl + "</option>" + list.map(function (v) {
        return '<option' + (filt[k] === v ? " selected" : "") + ">" + D.esc(v) + "</option>"; }).join("") + "</select>";
    }
    var rows = data.library.filter(function (l) {
      return (!filt.topic || l.topic === filt.topic) && (!filt.level || l.level === filt.level) && (!filt.tool || l.tool === filt.tool) &&
        (!filt.q || (l.title + " " + l.summary).toLowerCase().indexOf(filt.q.toLowerCase()) >= 0);
    });
    body.innerHTML = '<div class="dt-row" style="margin-bottom:12px"><input class="dt-in" id="dt-q" style="max-width:260px" placeholder="Tìm bài…" value="' + D.esc(filt.q) + '">' +
      sel("topic", data.filters.topics, "Mọi chủ đề") + sel("level", data.filters.levels, "Mọi cấp độ") + sel("tool", data.filters.tools, "Mọi công cụ") + "</div>" +
      (rows.length ? '<div class="dt-grid2">' + rows.map(card).join("") + "</div>" : '<p class="dt-empty">Không có bài phù hợp.</p>');
    D.qsa(body, "[data-f]").forEach(function (s) { s.onchange = function () { filt[s.dataset.f] = s.value; library(body); }; });
    var q = D.byId("dt-q");
    q.oninput = function () { filt.q = q.value; var pos = q.selectionStart; library(body); var n = D.byId("dt-q"); n.focus(); n.setSelectionRange(pos, pos); };
  }

  function votes(body) {
    var t = data.topics;
    body.innerHTML = '<div class="dt-panel"><div class="dt-pad dt-row"><div><b>Chủ đề cho bài tới</b><p class="dt-small dt-muted">Mỗi người ' + t.per_user +
      " phiếu, phiếu được trả lại khi chủ đề thành bài học. Còn <b>" + t.left + '</b> phiếu.</p></div><span class="dt-sp"></span><button class="dt-b pri" id="dt-prop">' + D.icon("plus") +
      " Đề xuất chủ đề</button></div>" + (t.items.length ? t.items.map(function (x) {
        var open = x.status === "Open";
        return '<div class="dt-topic"><button class="dt-vote" data-v="' + D.esc(x.name) + '" aria-pressed="' + x.voted + '"' + (open ? "" : " disabled") + '>▲<span>' + x.votes +
          '</span></button><div style="flex:1;min-width:0"><b>' + D.esc(x.title) + "</b>" + (x.description ? '<p class="dt-small dt-muted">' + D.esc(x.description) + "</p>" : "") +
          '<span class="dt-small dt-muted">' + D.esc(x.by) + "</span></div>" + (open ? "" : '<span class="dt-chip ' + (x.status === "Done" ? "ok" : "nv") + '">' +
          ({ Planned: "Đã lên kế hoạch", Done: "Đã thành bài", Rejected: "Không làm" }[x.status] || x.status) + "</span>") + "</div>";
      }).join("") : '<p class="dt-empty">Chưa có chủ đề nào - đề xuất cái đầu tiên nhé.</p>') + "</div>";
    D.qsa(body, "[data-v]").forEach(function (b) {
      b.onclick = function () {
        var on = b.getAttribute("aria-pressed") !== "true";
        D.busy(b, true);
        D.api("topic_vote", { topic: b.dataset.v, on: on ? 1 : 0 }, true).then(function (r) { data.topics = r; votes(body); }, function (e) { D.busy(b, false); D.toast(D.msg(e), true); });
      };
    });
    D.byId("dt-prop").onclick = function () {
      D.modal('<h2 class="dt-h2">Đề xuất chủ đề</h2><div class="dt-f" style="margin-top:10px"><label>Chủ đề</label><input class="dt-in" id="dt-tt" maxlength="120" placeholder="Vd: Dùng Claude đọc file Excel 50.000 dòng"></div>' +
        '<div class="dt-f" style="margin-top:8px"><label>Vì sao cần (không bắt buộc)</label><textarea class="dt-ta" id="dt-td" maxlength="500"></textarea></div><div class="dt-row" style="margin-top:12px;justify-content:flex-end">' +
        '<button class="dt-b" data-close>Huỷ</button><button class="dt-b pri" id="dt-send">Gửi</button></div>', function (m, close) {
          D.byId("dt-tt").focus();
          D.byId("dt-send").onclick = function () {
            var b = this; D.busy(b, true);
            D.api("topic_propose", { topic: { title: D.byId("dt-tt").value, description: D.byId("dt-td").value } }, true).then(function (r) {
              close(); data.topics = r.topics; votes(body); D.toast("Đã thêm chủ đề.");
            }, function (e) { D.busy(b, false); D.toast(D.msg(e), true); });
          };
        });
    };
  }

  // ------------------------------------------------------------- quay so tuan --
  function fmtN(n, top) { var w = Math.max(2, String(top || 100).length); n = String(n); while (n.length < w) n = "0" + n; return n; }
  function drawBox(box) {
    box.innerHTML = D.skel(1);
    D.api("draw_hub").then(function (d) { drawRender(box, d); }, function (e) { box.innerHTML = '<p class="dt-err">' + D.esc(D.msg(e)) + "</p>"; });
  }
  function drawRender(box, d) {
    var prizes = (d.prizes || []).map(function (p) { return '<span class="dt-chip nv">' + D.icon("gift") + " " + D.esc(p.label) + " × " + p.quantity + "</span>"; }).join(" ");
    var mine = d.mine.filter(function (m) { return m.active; });
    var left = Math.max(0, d.tickets - mine.length);
    var h = '<div class="dt-row"><h2 class="dt-h2">🎟️ ' + D.esc(d.title) + '</h2><span class="dt-sp"></span><span class="dt-chip ' + (d.status === "Done" ? "ok" : "warn") + '">' +
      (d.status === "Done" ? "Đã quay" : "Quay lúc " + D.esc(d.draw_at.slice(11, 16)) + " · " + D.fmtDate(d.draw_at)) + "</span></div>" +
      '<p class="dt-small dt-muted" style="margin:6px 0">Mỗi vé = một lượt: mỗi vé giữ một số trong dải 1–' + d.range + '. Số không ai giữ thì quà để lại. Chưa chọn kịp thì máy chọn giúp lúc ' +
      D.esc(d.lock_at.slice(11, 16)) + ".</p>" + (prizes ? '<div class="dt-row" style="margin:8px 0">' + prizes + "</div>" : '<p class="dt-muted">Ban đào tạo chưa cài quà tuần này.</p>') +
      '<div class="dt-row" style="margin:10px 0"><b>Số của bạn:</b>' + (mine.length ? mine.map(function (m) {
        return '<span class="dt-chip ok" style="font-size:15px">' + fmtN(m.number, d.range) + (m.auto ? " (máy chọn)" : "") +
          (d.open ? ' <button class="dt-b sm ghost" data-rel="' + m.number + '" aria-label="Bỏ số" style="padding:0 4px">×</button>' : "") + "</span>";
      }).join(" ") : '<span class="dt-muted">chưa có</span>') + '<span class="dt-sp"></span><span class="dt-small dt-muted">' + d.tickets + " vé · còn " + left + " vé chưa chọn số</span></div>";
    if (d.open && left > 0) {
      h += '<div class="dt-row"><input class="dt-in" id="dt-num" type="number" min="1" max="' + d.range + '" style="max-width:140px" placeholder="Số 1–' + d.range + '">' +
        '<button class="dt-b pri" id="dt-pick">Chọn số này</button><button class="dt-b" id="dt-rand">Chọn ngẫu nhiên</button></div>';
      if ((d.taken || []).length || d.range <= 300) {
        var taken = {}; (d.taken || []).forEach(function (n) { taken[n] = 1; });
        h += '<div class="dt-small dt-muted" style="margin-top:8px">Bảng số (' + d.taken_count + "/" + d.range + ' đã có người giữ) - bấm số trống để chọn:</div><div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">';
        for (var n = 1; n <= d.range; n++) {
          h += '<button class="dt-b sm" data-n="' + n + '"' + (taken[n] ? ' disabled style="opacity:.35"' : "") + ">" + fmtN(n, d.range) + "</button>";
        }
        h += "</div>";
      }
    } else if (d.status !== "Done" && !d.tickets) {
      h += '<p class="dt-muted">Bạn chưa có vé tuần này - làm quiz bài học, nộp bài thực hành hoặc đạt giải ở Quiz trực tiếp để có vé.</p>';
    }
    if (d.results) {
      h += '<h3 style="margin-top:12px">Kết quả</h3>' + (d.results.length ? '<table class="dt-table"><tbody>' + d.results.map(function (r) {
        return '<tr' + (r.me ? ' style="background:var(--ok-bg)"' : "") + "><td><b>" + fmtN(r.number, d.range) + "</b></td><td>" + D.esc(r.prize) + "</td><td>" +
          (r.winner ? D.esc(r.winner) + (r.me ? " 🎉" : "") : '<span class="dt-muted">Số không ai giữ - quà để lại</span>') + "</td></tr>";
      }).join("") + "</tbody></table>" : '<p class="dt-muted">Tuần này không có quà.</p>');
    }
    box.innerHTML = h;
    function act(method, args, btn) {
      D.busy(btn, true);
      D.api(method, args, true).then(function (v) { drawRender(box, v); D.toast("Đã cập nhật số của bạn."); }, function (e) { D.busy(btn, false); D.toast(D.msg(e), true); });
    }
    var pk = D.byId("dt-pick"); if (pk) pk.onclick = function () { act("draw_pick", { number: D.byId("dt-num").value }, pk); };
    var rd = D.byId("dt-rand"); if (rd) rd.onclick = function () { act("draw_pick", {}, rd); };
    D.qsa(box, "[data-n]").forEach(function (b) { b.onclick = function () { act("draw_pick", { number: b.dataset.n }, b); }; });
    D.qsa(box, "[data-rel]").forEach(function (b) { b.onclick = function () { act("draw_release", { number: b.dataset.rel }, b); }; });
  }

  function rewards(body) {
    var t = data.tickets;
    body.innerHTML = '<div class="dt-panel dt-pad" id="dt-draw" style="margin-bottom:14px"></div><div class="dt-grid2"><div class="dt-panel dt-pad"><h2 class="dt-h2">' + D.icon("ticket") + " Vé tuần này: " + t.this_week + "/" + t.cap + "</h2>" +
      '<p class="dt-muted" style="margin-top:6px">' + D.esc(t.week) + ". Nhận vé khi: làm quiz bài học đạt từ 60% (1 vé), nộp bài thực hành đúng hạn (1 vé), đạt giải ở Quiz trực tiếp. Tối đa " + t.cap +
      ' vé / người / tuần.</p></div><div class="dt-panel dt-pad"><h2 class="dt-h2">Lịch sử vé</h2>' +
      ((t.history || []).length ? "<ul>" + t.history.map(function (x) {
        return "<li>" + D.esc(x.label) + " · <b>" + x.count + " vé</b> · " + D.fmtDate(x.week_start) + (x.revoked ? ' <span class="dt-chip bad">đã thu hồi</span>' : "") + "</li>";
      }).join("") + "</ul>" : '<p class="dt-muted">Chưa có vé.</p>') + "</div></div>";
    drawBox(D.byId("dt-draw"));
  }

  load();
})();
