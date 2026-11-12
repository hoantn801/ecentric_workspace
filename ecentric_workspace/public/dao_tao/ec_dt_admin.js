// Copyright (c) 2026, eCentric and contributors
// /dao-tao/quan-ly -- Quan ly bai hoc (Ban dao tao / HR): soan bai, xem bai thuc hanh + thu hoi
// ve, doi trang thai chu de binh chon. Quyen kiem o server (dao_tao/application/access.py).
(function () {
  "use strict";
  var D = window.ECDt;
  var root = D.byId("dt-root");
  var data = null, tab = "bai";

  function load(then) {
    D.api("lesson_admin").then(function (d) { data = d; if (then) then(); else render(); },
      function (e) { root.innerHTML = '<div class="dt-wrap"><p class="dt-err">' + D.esc(D.msg(e)) + "</p></div>"; });
  }

  function render() {
    var h = '<div class="dt-wrap"><div class="dt-row"><h1 style="font-size:22px">Quản lý bài học</h1><span class="dt-sp"></span><a class="dt-b" href="/dao-tao">Xem trang Học</a>' +
      '<a class="dt-b" href="/quiz">Quiz trực tiếp</a><button class="dt-b pri" id="dt-new">' + D.icon("plus") + ' Bài mới</button></div><div class="dt-tabs">' +
      [["bai", "Bài học"], ["thuc-hanh", "Bài thực hành"], ["chu-de", "Chủ đề bình chọn"]].map(function (x) {
        return '<button class="dt-tab" data-tab="' + x[0] + '" aria-selected="' + (tab === x[0]) + '">' + x[1] + "</button>"; }).join("") + '</div><div id="dt-body"></div></div>';
    root.innerHTML = h;
    D.byId("dt-new").onclick = function () { editor(null); };
    D.qsa(root, "[data-tab]").forEach(function (b) { b.onclick = function () { tab = b.dataset.tab; render(); }; });
    var body = D.byId("dt-body");
    if (tab === "thuc-hanh") practice(body);
    else if (tab === "chu-de") topics(body);
    else lessons(body);
  }

  function lessons(body) {
    body.innerHTML = data.lessons.length ? '<div class="dt-panel"><table class="dt-table"><thead><tr><th>Bài</th><th>Tuần</th><th>Trạng thái</th><th>Đã xem</th><th>Làm quiz</th><th>Thực hành</th><th></th></tr></thead><tbody>' +
      data.lessons.map(function (l) {
        return "<tr><td><b>" + D.esc(l.title) + '</b><br><span class="dt-small dt-muted">' + D.esc(l.topic) + " · " + D.esc(l.level) + " · " + D.esc(l.tool) + "</span></td><td>" + D.fmtDate(l.week_start) +
          '</td><td><span class="dt-chip ' + (l.status === "Published" ? "ok" : "warn") + '">' + (l.status === "Published" ? "Đã đăng" : "Nháp") + "</span></td><td>" + l.viewed + "</td><td>" + l.quiz +
          "</td><td>" + l.practice + '</td><td style="white-space:nowrap"><a class="dt-b sm" href="/dao-tao/bai?l=' + encodeURIComponent(l.name) + '">Xem</a> <button class="dt-b sm" data-ed="' + D.esc(l.name) + '">Sửa</button></td></tr>';
      }).join("") + "</tbody></table></div>" : '<p class="dt-empty">Chưa có bài nào. Bấm “Bài mới”.</p>';
    D.qsa(body, "[data-ed]").forEach(function (b) { b.onclick = function () { editor(b.dataset.ed); }; });
  }

  function editor(name) {
    var go = function (l) {
      l = l || { title: "", summary: "", body: "", topic: data.options.topics[0], level: data.options.levels[0], tool: data.options.tools[0], status: "Draft" };
      function sel(k, list) { return '<select class="dt-sel" id="dt-' + k + '">' + list.map(function (v) { return "<option" + (l[k] === v ? " selected" : "") + ">" + D.esc(v) + "</option>"; }).join("") + "</select>"; }
      var h = '<div class="dt-wrap dt-narrow"><div class="dt-row"><button class="dt-b ghost" id="dt-back">' + D.icon("back") + ' Danh sách</button><span class="dt-sp"></span>' +
        '<button class="dt-b" id="dt-sd">Lưu nháp</button><button class="dt-b pri" id="dt-sp">Lưu & đăng</button></div><div class="dt-panel dt-pad" style="display:grid;gap:12px">' +
        '<div class="dt-f"><label>Tiêu đề</label><input class="dt-in" id="dt-title" maxlength="140" value="' + D.esc(l.title) + '"><span class="dt-ferr" data-e="title"></span></div>' +
        '<div class="dt-f"><label>Tóm tắt (hiện trên thẻ bài)</label><input class="dt-in" id="dt-summary" maxlength="400" value="' + D.esc(l.summary) + '"></div>' +
        '<div class="dt-row"><div class="dt-f"><label>Tuần (thứ Hai)</label><input class="dt-in" type="date" id="dt-week" value="' + D.esc((l.week_start || "").slice(0, 10)) + '"><span class="dt-ferr" data-e="week_start"></span></div>' +
        '<div class="dt-f"><label>Chủ đề</label>' + sel("topic", data.options.topics) + '</div><div class="dt-f"><label>Cấp độ</label>' + sel("level", data.options.levels) +
        '</div><div class="dt-f"><label>Công cụ</label>' + sel("tool", data.options.tools) + "</div></div>" +
        '<div class="dt-f"><label>Video (YouTube / link https / tệp .mp4)</label><div class="dt-row"><input class="dt-in" id="dt-video" style="flex:1" value="' + D.esc(l.video_url || "") +
        '"><label class="dt-b sm">' + D.icon("upload") + ' Tải lên<input type="file" id="dt-vf" accept="video/mp4" hidden></label></div><span class="dt-ferr" data-e="video_url"></span></div>' +
        '<div class="dt-f"><label>Slide / tài liệu</label><div class="dt-row"><input class="dt-in" id="dt-slide" style="flex:1" value="' + D.esc(l.slide_url || "") +
        '"><label class="dt-b sm">' + D.icon("upload") + ' Tải lên<input type="file" id="dt-sf" hidden></label></div><span class="dt-ferr" data-e="slide_url"></span></div>' +
        '<div class="dt-f"><label>Nội dung bài (chữ thường; link https tự bấm được)</label><textarea class="dt-ta" id="dt-body2" style="min-height:220px">' + D.esc(l.body || "") + "</textarea></div>" +
        '<div class="dt-f"><label>Quiz bài học (tự luyện - chọn từ bộ quiz đã soạn)</label><select class="dt-sel" id="dt-quiz"><option value="">— Không có quiz —</option>' +
        data.quizzes.map(function (q) { return '<option value="' + D.esc(q.name) + '"' + (l.quiz === q.name ? " selected" : "") + ">" + D.esc(q.title) + "</option>"; }).join("") + "</select></div>" +
        '<div class="dt-f"><label>Đề bài thực hành (để trống = không có)</label><textarea class="dt-ta" id="dt-pp" maxlength="1000">' + D.esc(l.practice_prompt || "") + "</textarea></div>" +
        '<div class="dt-f"><label>Hạn nộp thực hành</label><input class="dt-in" type="datetime-local" id="dt-due" value="' + D.esc((l.practice_due || "").slice(0, 16).replace(" ", "T")) + '"></div></div></div>';
      root.innerHTML = h;
      D.byId("dt-back").onclick = function () { load(); };
      [["dt-vf", "dt-video"], ["dt-sf", "dt-slide"]].forEach(function (x) {
        D.byId(x[0]).onchange = function () {
          var f = this.files[0]; if (!f) return;
          D.toast("Đang tải lên…");
          D.upload(f, false).then(function (u) { D.byId(x[1]).value = u; D.toast("Đã tải lên."); }, function (e) { D.toast(D.msg(e), true); });
        };
      });
      function save(status, btn) {
        var due = D.byId("dt-due").value;
        var p = { name: l.name, status: status, title: D.byId("dt-title").value, summary: D.byId("dt-summary").value, week_start: D.byId("dt-week").value,
          topic: D.byId("dt-topic").value, level: D.byId("dt-level").value, tool: D.byId("dt-tool").value, video_url: D.byId("dt-video").value.trim(),
          slide_url: D.byId("dt-slide").value.trim(), body: D.byId("dt-body2").value, quiz: D.byId("dt-quiz").value, practice_prompt: D.byId("dt-pp").value,
          practice_due: due ? due.replace("T", " ") + ":00" : "" };
        D.qsa(root, "[data-e]").forEach(function (x) { x.textContent = ""; });
        D.busy(btn, true);
        D.api("lesson_save", { lesson: p }, true).then(function (r) { D.busy(btn, false); l = r; D.toast(status === "Published" ? "Đã đăng bài." : "Đã lưu nháp."); },
          function (e) {
            D.busy(btn, false); D.toast(D.msg(e), true);
            var er = (e.data && e.data.errors) || {};
            Object.keys(er).forEach(function (k) { var x = root.querySelector('[data-e="' + k + '"]'); if (x) x.textContent = er[k]; });
          });
      }
      D.byId("dt-sd").onclick = function () { save("Draft", this); };
      D.byId("dt-sp").onclick = function () { save("Published", this); };
    };
    if (name) D.api("lesson_admin_get", { name: name }).then(go, function (e) { D.toast(D.msg(e), true); });
    else go(null);
  }

  function practice(body) {
    var opts = data.lessons.filter(function (l) { return l.practice_prompt; });
    body.innerHTML = opts.length ? '<div class="dt-row"><select class="dt-sel" id="dt-pl" style="max-width:420px">' + opts.map(function (l) {
      return '<option value="' + D.esc(l.name) + '">' + D.esc(l.title) + " (" + l.practice + " bài)</option>"; }).join("") + '</select></div><div id="dt-sub" style="margin-top:12px"></div>' :
      '<p class="dt-empty">Chưa có bài học nào có bài thực hành.</p>';
    if (!opts.length) return;
    function show() {
      var box = D.byId("dt-sub"), n = D.byId("dt-pl").value;
      box.innerHTML = D.skel(2);
      D.api("lesson_submissions", { name: n }).then(function (d) {
        var rows = d.rows.filter(function (r) { return r.practice_at; });
        box.innerHTML = rows.length ? '<p class="dt-small dt-muted">Kiểm tra ngẫu nhiên. “Thu hồi” chỉ huỷ vé của bài thực hành này.</p><div class="dt-panel"><table class="dt-table"><tbody>' + rows.map(function (r) {
          return "<tr><td style=\"width:220px\"><b>" + D.esc(r.full_name) + '</b><br><span class="dt-small dt-muted">' + D.esc(r.user) + "<br>" + D.fmtDate(r.practice_at) + '</span></td><td><div class="dt-body" style="font-size:13.5px">' +
            D.richText(r.practice_text || "") + "</div>" + (r.practice_link && D.safeUrl(r.practice_link) ? '<a href="' + D.esc(D.safeUrl(r.practice_link)) + '" target="_blank" rel="noopener noreferrer">Mở link</a>' : "") +
            '</td><td style="white-space:nowrap">' + (r.review ? '<span class="dt-chip ' + (r.review === "OK" ? "ok" : "bad") + '">' + (r.review === "OK" ? "Đạt" : "Đã thu hồi") + "</span><br>" : "") +
            '<button class="dt-b sm" data-rv="OK" data-u="' + D.esc(r.user) + '">Đạt</button> <button class="dt-b sm danger" data-rv="Revoked" data-u="' + D.esc(r.user) + '">Thu hồi vé</button></td></tr>';
        }).join("") + "</tbody></table></div>" : '<p class="dt-empty">Chưa ai nộp.</p>';
        D.qsa(box, "[data-rv]").forEach(function (b) {
          b.onclick = function () {
            if (b.dataset.rv === "Revoked" && !window.confirm("Thu hồi vé bài thực hành của " + b.dataset.u + "?")) return;
            D.busy(b, true);
            D.api("lesson_review", { name: n, user: b.dataset.u, verdict: b.dataset.rv }, true).then(function () { D.toast("Đã cập nhật."); show(); }, function (e) { D.busy(b, false); D.toast(D.msg(e), true); });
          };
        });
      }, function (e) { box.innerHTML = '<p class="dt-err">' + D.esc(D.msg(e)) + "</p>"; });
    }
    D.byId("dt-pl").onchange = show;
    show();
  }

  function topics(body) {
    var LBL = { Open: "Đang bình chọn", Planned: "Đã lên kế hoạch", Done: "Đã thành bài", Rejected: "Không làm" };
    body.innerHTML = data.topics.length ? '<div class="dt-panel"><table class="dt-table"><thead><tr><th>Chủ đề</th><th>Phiếu</th><th>Trạng thái</th><th>Bài học</th></tr></thead><tbody>' +
      data.topics.map(function (t) {
        return "<tr><td><b>" + D.esc(t.title) + '</b><br><span class="dt-small dt-muted">' + D.esc(t.description || "") + "</span></td><td>" + t.votes + '</td><td><select class="dt-sel" data-ts="' + D.esc(t.name) + '">' +
          data.options.topic_statuses.map(function (s) { return '<option value="' + s + '"' + (t.status === s ? " selected" : "") + ">" + LBL[s] + "</option>"; }).join("") + '</select></td><td><select class="dt-sel" data-tl="' +
          D.esc(t.name) + '"><option value="">—</option>' + data.lessons.map(function (l) { return '<option value="' + D.esc(l.name) + '"' + (t.lesson === l.name ? " selected" : "") + ">" + D.esc(l.title) + "</option>"; }).join("") + "</select></td></tr>";
      }).join("") + '</tbody></table></div><p class="dt-small dt-muted" style="margin-top:8px">“Đã thành bài” / “Không làm” trả lại phiếu cho người đã bầu.</p>' : '<p class="dt-empty">Chưa có chủ đề nào.</p>';
    function upd(name) {
      var st = body.querySelector('[data-ts="' + name + '"]').value, ls = body.querySelector('[data-tl="' + name + '"]').value;
      D.api("topic_status", { topic: name, status: st, lesson: ls || null }, true).then(function () { D.toast("Đã cập nhật."); load(function () { tab = "chu-de"; render(); }); }, function (e) { D.toast(D.msg(e), true); });
    }
    D.qsa(body, "[data-ts]").forEach(function (s) { s.onchange = function () { upd(s.dataset.ts); }; });
    D.qsa(body, "[data-tl]").forEach(function (s) { s.onchange = function () { upd(s.dataset.tl); }; });
  }

  load(function () { render(); var l = D.param("l"); if (l) editor(l); });
})();
