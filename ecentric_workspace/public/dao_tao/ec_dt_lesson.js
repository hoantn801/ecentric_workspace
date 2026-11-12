// Copyright (c) 2026, eCentric and contributors
// /dao-tao/bai?l=<bai> -- mot bai hoc: noi dung, quiz tu luyen (cham o server, nop xong moi
// thay dap an), bai thuc hanh (nop la co ve; Ban dao tao kiem tra ngau nhien, thu hoi duoc).
(function () {
  "use strict";
  var D = window.ECDt;
  var root = D.byId("dt-root");
  var name = D.param("l"), L = null, ans = {}, result = null;

  function load() {
    if (!name) { root.innerHTML = '<div class="dt-wrap"><p class="dt-err">Thiếu mã bài học.</p><a class="dt-b" href="/dao-tao">Về trang Đào tạo</a></div>'; return; }
    root.innerHTML = '<div class="dt-wrap dt-narrow">' + D.skel(3) + "</div>";
    D.api("lesson", { name: name }).then(function (d) { L = d; render(); },
      function (e) { root.innerHTML = '<div class="dt-wrap"><p class="dt-err">' + D.esc(D.msg(e)) + '</p><a class="dt-b" href="/dao-tao">Về trang Đào tạo</a></div>'; });
  }

  function render() {
    var p = L.progress || {};
    var h = '<div class="dt-wrap dt-narrow"><div class="dt-row"><a class="dt-b ghost" href="/dao-tao">' + D.icon("back") + " Đào tạo</a><span class=\"dt-sp\"></span>" +
      (L.can_manage ? '<a class="dt-b sm" href="/dao-tao/quan-ly?l=' + encodeURIComponent(L.name) + '">' + D.icon("edit") + " Sửa bài</a>" : "") + "</div>" +
      '<div class="dt-panel dt-pad" style="display:grid;gap:12px"><div class="dt-row dt-small"><span class="dt-chip nv">' + D.esc(L.topic) + '</span><span class="dt-chip">' + D.esc(L.level) +
      '</span><span class="dt-chip">' + D.esc(L.tool) + "</span>" + (L.status !== "Published" ? '<span class="dt-chip warn">Nháp</span>' : "") + "</div><h1>" + D.esc(L.title) + "</h1>" +
      (L.summary ? '<p class="dt-muted" style="font-size:15px">' + D.esc(L.summary) + "</p>" : "") + (L.video_url ? D.embedVideo(L.video_url) : "") +
      (L.slide_url && D.safeUrl(L.slide_url) ? '<a class="dt-b" href="' + D.esc(D.safeUrl(L.slide_url)) + '" target="_blank" rel="noopener noreferrer">' + D.icon("book") + " Mở slide / tài liệu</a>" : "") +
      (L.body ? '<div class="dt-body">' + D.richText(L.body) + "</div>" : "") + "</div>";
    if (L.quiz) h += '<div class="dt-panel dt-pad" id="dt-quiz"></div>';
    if (L.practice_prompt) {
      var rv = p.review === "Revoked";
      h += '<div class="dt-panel dt-pad" style="display:grid;gap:10px"><h2 class="dt-h2">Bài thực hành</h2><div class="dt-body" style="font-size:14px">' + D.richText(L.practice_prompt) + "</div>" +
        (L.practice_due ? '<p class="dt-small dt-muted">Hạn nộp: ' + D.esc(String(L.practice_due).slice(0, 16)) + (L.practice_open ? "" : " - đã quá hạn (vẫn nộp được, nhưng không có vé)") + "</p>" : "") +
        (p.practice_at ? '<p><span class="dt-chip ' + (rv ? "bad" : (p.review === "OK" ? "ok" : "nv")) + '">' + (rv ? "Đã bị thu hồi vé" : (p.review === "OK" ? "Ban đào tạo đã xem - đạt" : "Đã nộp " + D.fmtDate(p.practice_at))) + "</span></p>" : "") +
        '<div class="dt-f"><label for="dt-pt">Bạn đã làm gì, kết quả ra sao?</label><textarea class="dt-ta" id="dt-pt" maxlength="4000" style="min-height:120px">' + D.esc(p.practice_text || "") + "</textarea></div>" +
        '<div class="dt-f"><label for="dt-pl">Link kết quả (không bắt buộc - SharePoint, Claude chat share…)</label><input class="dt-in" id="dt-pl" value="' + D.esc(p.practice_link || "") + '" placeholder="https://…"></div>' +
        '<div class="dt-row"><span class="dt-sp"></span><button class="dt-b pri" id="dt-psend"' + (rv ? " disabled" : "") + ">" + (p.practice_at ? "Nộp lại" : "Nộp bài") + "</button></div></div>";
    }
    h += "</div>";
    root.innerHTML = h;
    if (L.quiz) quiz();
    var ps = D.byId("dt-psend");
    if (ps) ps.onclick = function () {
      D.busy(ps, true);
      D.api("lesson_practice", { name: name, text: D.byId("dt-pt").value, link: D.byId("dt-pl").value.trim() }, true).then(function (r) {
        D.toast(r.ticket ? "Đã nộp - bạn nhận 1 vé!" : (r.on_time ? "Đã nộp lại." : "Đã nộp (quá hạn nên không có vé)."));
        load();
      }, function (e) { D.busy(ps, false); D.toast(D.msg(e), true); });
    };
  }

  // ------------------------------------------------------------------- quiz tu luyen --
  function quiz() {
    var box = D.byId("dt-quiz"), p = L.progress || {}, qs = L.quiz.questions;
    var h = '<div class="dt-row"><h2 class="dt-h2">Quiz: ' + D.esc(L.quiz.title) + '</h2><span class="dt-sp"></span>' + (p.quiz_at ? '<span class="dt-chip ok">Điểm tốt nhất ' + p.quiz_score + "/" + p.quiz_scored + "</span>" : "") +
      '</div><p class="dt-small dt-muted">Không giới hạn thời gian. Đạt từ 60% lần đầu được 1 vé. Làm lại thoải mái.</p>';
    if (result) {
      h += '<div class="dt-res ' + (result.passed ? "ok" : "bad") + '" style="color:#fff;margin:10px 0">' + result.score + "/" + result.scored + "<small>" +
        (result.passed ? (result.ticket ? "Đạt - bạn nhận 1 vé!" : "Đạt!") : "Chưa đạt 60% - xem lại đáp án rồi làm lại nhé") + "</small></div>";
    }
    qs.forEach(function (q, i) {
      var det = result ? result.detail[i] : null;
      h += '<div style="border-top:1px solid var(--line2);padding:14px 0"><b>' + (i + 1) + ". " + D.esc(q.text) + '</b> <span class="dt-chip">' + D.esc(q.label) + "</span>" +
        (det && det.ratio != null ? (det.ratio >= 1 ? ' <span class="dt-chip ok">Đúng</span>' : ' <span class="dt-chip bad">Chưa đúng</span>') : "") +
        (q.media && D.safeUrl(q.media.url) && q.type !== "pin" ? '<img src="' + D.esc(D.safeUrl(q.media.url)) + '" alt="" style="max-height:200px;max-width:100%;display:block;margin-top:8px;border-radius:10px">' : "") +
        '<div style="margin-top:8px" data-q="' + i + '">' + control(q, i) + "</div>" + (det ? keyText(q, det.reveal) : "") + "</div>";
    });
    h += '<div class="dt-row"><span class="dt-sp"></span>' + (result ? '<button class="dt-b" id="dt-again">Làm lại</button>' : '<button class="dt-b pri" id="dt-qsend">Nộp bài quiz</button>') + "</div>";
    box.innerHTML = h;
    bind(box, qs);
    var again = D.byId("dt-again"); if (again) again.onclick = function () { result = null; ans = {}; quiz(); };
    var send = D.byId("dt-qsend");
    if (send) send.onclick = function () {
      D.busy(send, true);
      D.api("lesson_quiz", { name: name, answers: ans }, true).then(function (r) { result = r; L.progress.quiz_at = 1; L.progress.quiz_score = Math.max(r.score, L.progress.quiz_score || 0); L.progress.quiz_scored = r.scored; quiz(); },
        function (e) { D.busy(send, false); D.toast(D.msg(e), true); });
    };
  }
  function control(q, i) {
    var a = ans[q.id] || {}, dis = result ? " disabled" : "";
    if (q.options) {
      var multi = q.type === "multi";
      return q.options.map(function (o) {
        var on = multi ? (a.o || []).indexOf(o.id) >= 0 : a.o === o.id;
        return '<label class="dt-row" style="padding:4px 0"><input type="' + (multi ? "checkbox" : "radio") + '" name="q' + i + '" data-o="' + D.esc(o.id) + '"' + (on ? " checked" : "") + dis + ">" + D.esc(o.text) + "</label>";
      }).join("");
    }
    if (q.type === "slider") {
      var v = a.v != null ? a.v : q.min;
      return '<div class="dt-row"><input type="range" data-sl min="' + q.min + '" max="' + q.max + '" step="' + q.step + '" value="' + v + '" style="flex:1"' + dis + '><b data-sv>' + v + " " + D.esc(q.unit || "") + "</b></div>";
    }
    if (q.type === "pin") {
      return '<div class="dt-pinbox" data-pin style="max-width:520px"><img src="' + D.esc(D.safeUrl(q.media && q.media.url)) + '" alt="">' +
        (a.x != null ? '<span class="dt-dot" style="left:' + a.x * 100 + "%;top:" + a.y * 100 + '%"></span>' : "") + "</div>";
    }
    if (q.type === "order") {
      var ord = a.o || q.items.map(function (x) { return x.id; }), tx = {};
      q.items.forEach(function (x) { tx[x.id] = x.text; });
      if (!a.o) ans[q.id] = { o: ord };
      return ord.map(function (id, k) {
        return '<div class="dt-row" style="padding:3px 0"><b>' + (k + 1) + "</b><span style=\"flex:1\">" + D.esc(tx[id]) + '</span><button class="dt-b sm" data-mv="' + k + '"' + (k === 0 || result ? " disabled" : "") + ">" + D.icon("up") + "</button></div>";
      }).join("");
    }
    if (q.type === "match") {
      return q.lefts.map(function (l) {
        return '<div class="dt-row" style="padding:3px 0"><span style="flex:1">' + D.esc(l.text) + '</span><select class="dt-sel" data-l="' + D.esc(l.id) + '" style="max-width:55%"' + dis +
          '><option value="">— ghép với —</option>' + q.rights.map(function (r) { return '<option value="' + D.esc(r.id) + '"' + ((a.m || {})[l.id] === r.id ? " selected" : "") + ">" + D.esc(r.text) + "</option>"; }).join("") + "</select></div>";
      }).join("");
    }
    return '<input class="dt-in" data-t maxlength="' + (q.maxlen || 60) + '" value="' + D.esc(a.t || "") + '"' + dis + ">";
  }
  function bind(box, qs) {
    D.qsa(box, "[data-q]").forEach(function (w) {
      var q = qs[+w.dataset.q];
      D.qsa(w, "[data-o]").forEach(function (i) {
        i.onchange = function () {
          if (q.type === "multi") ans[q.id] = { o: D.qsa(w, "[data-o]").filter(function (x) { return x.checked; }).map(function (x) { return x.dataset.o; }) };
          else ans[q.id] = { o: i.dataset.o };
        };
      });
      var sl = w.querySelector("[data-sl]");
      if (sl) { if (!ans[q.id]) ans[q.id] = { v: +sl.value }; sl.oninput = function () { ans[q.id] = { v: +sl.value }; w.querySelector("[data-sv]").textContent = sl.value + " " + (q.unit || ""); }; }
      var pin = w.querySelector("[data-pin]");
      if (pin && !result) pin.onclick = function (e) { var r = pin.getBoundingClientRect(); ans[q.id] = { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }; w.innerHTML = control(q); bind(box, qs); };
      D.qsa(w, "[data-mv]").forEach(function (b) { b.onclick = function () { var o = ans[q.id].o, k = +b.dataset.mv, t = o[k]; o[k] = o[k - 1]; o[k - 1] = t; w.innerHTML = control(q); bind(box, qs); }; });
      D.qsa(w, "[data-l]").forEach(function (s) { s.onchange = function () { var m = {}; D.qsa(w, "[data-l]").forEach(function (x) { if (x.value) m[x.dataset.l] = x.value; }); ans[q.id] = { m: m }; }; });
      var t = w.querySelector("[data-t]");
      if (t) t.oninput = function () { ans[q.id] = { t: t.value }; };
    });
  }
  function keyText(q, rv) {
    var s = "";
    if (rv.correct && q.options) s = q.options.filter(function (o) { return rv.correct.indexOf(o.id) >= 0; }).map(function (o) { return o.text; }).join(", ");
    else if (q.type === "slider") s = rv.answer + (rv.tolerance ? " ± " + rv.tolerance : "") + " " + (q.unit || "");
    else if (q.type === "order") { var tx = {}; q.items.forEach(function (x) { tx[x.id] = x.text; }); s = rv.order.map(function (id) { return tx[id]; }).join(" → "); }
    else if (q.type === "match") { var rt = {}; q.rights.forEach(function (r) { rt[r.id] = r.text; }); s = q.lefts.map(function (l) { return l.text + " → " + rt[rv.pairs[l.id]]; }).join("; "); }
    else if (q.type === "type") s = (rv.accept || []).join(" / ");
    else if (q.type === "pin") s = "vùng tô trên ảnh";
    return (s ? '<p class="dt-small" style="margin-top:6px">Đáp án: <b>' + D.esc(s) + "</b></p>" : "") + (rv.explain ? '<p class="dt-small dt-muted">💡 ' + D.esc(rv.explain) + "</p>" : "");
  }

  load();
})();
