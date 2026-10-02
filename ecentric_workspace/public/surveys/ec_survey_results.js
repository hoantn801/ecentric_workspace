// Copyright (c) 2026, eCentric and contributors
// ec_survey_results.js -- tab "Kết quả" cua trinh soan: tong quan + phan thuong (quay so),
// tom tat theo cau hoi, tung phieu, nguoi tham gia (da / chua lam + nhac), xuat Excel.
//
//   ECSvyResults.mount(el, B)  -> tai du lieu va ve vao `el`
(function () {
  "use strict";
  if (window.ECSvyResults) return;
  var S = window.ECSvy, esc = S.esc;

  function mount(el, B) {
    var R = { sub: "summary", ov: null, resp: null, idx: 0, people: null, pf: "todo" };

    function fileLink(url) { return S.apiUrl("download_file", { name: B.name, url: url }); }

    function load() {
      el.innerHTML = '<div class="svy-panel svy-pad"><div class="svy-skel" style="width:40%"></div><div class="svy-skel" style="width:80%"></div></div>';
      S.api("results_overview", { name: B.name }).then(function (ov) { R.ov = ov; draw(); if (B.onCount) B.onCount(ov.summary.total); },
        function (e) { el.innerHTML = '<div class="svy-panel svy-empty"><b>Không tải được kết quả</b>' + esc(e.svyMessage) + "</div>"; });
    }

    function kpis() {
      var ov = R.ov, rate = ov.eligible ? Math.round(100 * ov.submitted_eligible / ov.eligible) : 0;
      var h = '<div class="svy-kpis"><div class="svy-kpi"><span>Phiếu</span><b>' + ov.summary.total + '</b></div><div class="svy-kpi"><span>Đối tượng</span><b>' + ov.eligible +
        '</b></div><div class="svy-kpi"><span>Tỷ lệ tham gia</span><b>' + rate + "%</b></div>";
      if (ov.quiz) h += '<div class="svy-kpi"><span>Điểm TB</span><b>' + (ov.quiz.average == null ? "–" : String(ov.quiz.average).replace(".", ",")) + "/" + ov.quiz.max_score + "</b></div>";
      return h + "</div>";
    }

    function rewardCard() {
      var r = R.ov.reward;
      if (!r) return "";
      var MODE = { wheel: "Vòng quay chia đợt", lucky_number: "Số may mắn", race: "Đua về đích" };
      var sched = r.mode === "lucky_number" || r.mode === "race";
      var stat = r.mode === "wheel" ? r.spins + " lượt đã quay"
        : r.mode === "lucky_number" ? r.numbers + "/" + r.number_range + " số đã có người giữ" : r.racers + " xe";
      if (sched) stat += r.draw_at ? " · đã " + (r.mode === "race" ? "đua" : "quay") + " lúc " + esc(S.fmtDt(r.draw_at))
        : r.draw_scheduled_at ? " · hẹn " + esc(S.fmtDt(r.draw_scheduled_at)) + " trên trang chủ" : " · chưa đặt giờ";
      var h = '<section class="svy-panel svy-pad"><div class="svy-row between"><div><div class="svy-eyebrow">Phần thưởng · ' + (MODE[r.mode] || "") + "</div>" +
        '<div style="font-weight:600">' + r.prizes.map(function (p) { return esc(p.label) + " " + p.awarded + "/" + p.quantity; }).join(" · ") + "</div>" +
        '<div class="svy-small svy-muted">' + stat + "</div></div>";
      if (sched && !r.draw_at) h += '<button class="svy-b gold" data-ract="draw">' + S.icon("gift") + (r.mode === "race" ? "Đua ngay" : "Quay ngay") + "</button>";
      h += "</div>";
      // Bang so da chon (Hoan 02/10: nguoi quan ly can xem ai giu so nao). Bam moi tai - dung API
      // number_board co san (an danh thi khong co ten).
      if (r.mode === "lucky_number" && r.numbers) {
        h += '<div style="margin-top:10px"><button class="svy-b sm" data-ract="numbers" aria-expanded="' + (R.nums ? "true" : "false") + '">' +
          S.icon("list") + (R.nums ? "Ẩn các số đã chọn" : "Xem " + r.numbers + " số đã chọn") + '</button><div id="svy-nums"></div></div>';
      }
      if (r.empty_numbers && r.empty_numbers.length) h += '<div class="svy-small svy-muted" style="margin-top:8px">Số không ai giữ (quà để lại): <b>' + r.empty_numbers.map(esc).join(", ") + "</b></div>";
      if (r.winners.length) {
        h += '<div class="svy-board" style="margin-top:10px">' + r.winners.map(function (w) {
          return '<div class="it"><span class="svy-av">' + esc(S.initials(w.name)) + '</span><div class="svy-grow"><b>' + esc(w.name) + '</b><div class="svy-small svy-muted">' + esc(w.user) +
            (w.lucky_number ? " · số " + esc(w.lucky_number) : "") + '</div></div><span class="svy-pill gold">' + esc(w.prize) + "</span></div>";
        }).join("") + "</div>";
      } else h += '<div class="svy-small svy-muted" style="margin-top:8px">Chưa có ai trúng.</div>';
      return h + "</section>";
    }

    function draw() {
      var tabs = [["summary", "Tóm tắt"], ["responses", "Từng phiếu"], ["people", "Người tham gia"]];
      var h = '<div class="svy-row between"><div class="svy-chips">' + tabs.map(function (t) {
        return '<button class="svy-chip' + (R.sub === t[0] ? " on" : "") + '" data-rsub="' + t[0] + '">' + t[1] + "</button>";
      }).join("") + '</div><div class="svy-row"><a class="svy-b sm" href="' + esc(S.apiUrl("export_xlsx", { name: B.name })) + '">' + S.icon("download") + "Xuất Excel</a>" +
        (B.data.effective === "open" ? '<button class="svy-b sm" data-ract="remind">' + S.icon("bell") + "Nhắc người chưa làm</button>" : "") +
        '<button class="svy-b sm ghost" data-ract="reload" title="Tải lại">↻</button></div></div>';
      h += kpis();
      if (R.sub === "summary") {
        h += rewardCard();
        h += R.ov.summary.total ? '<div class="svy-items">' + window.ECSvySummary.render(B.form, R.ov.summary, { fileLink: fileLink }) + "</div>"
          : '<div class="svy-panel svy-empty"><b>Chưa có phiếu trả lời</b>Chia sẻ đường dẫn hoặc bấm phát hành để mọi người nhận thông báo.</div>';
      } else if (R.sub === "responses") h += '<div id="svy-resp"></div>';
      else h += '<div id="svy-people"></div>';
      el.innerHTML = '<div class="svy-items">' + h + "</div>";
      if (R.sub === "responses") loadResponse(R.idx);
      if (R.sub === "people") loadPeople();
      if (R.sub === "summary" && R.nums) loadNumbers();
    }

    function answerText(q, v) {
      if (S.isEmpty(q, v)) return '<span class="svy-muted">(bỏ trống)</span>';
      var lb = {};
      (q.options || []).forEach(function (o) { lb[o.id] = o.label; });
      if (q.type === "single" || q.type === "multi" || q.type === "dropdown") {
        return S.selected(v).map(function (x) { return esc(lb[x] || x); }).concat(v.other ? ["<i>Khác:</i> " + esc(v.other)] : []).join("<br>");
      }
      if (q.type === "ranking") return v.map(function (x, i) { return (i + 1) + ". " + esc(lb[x] || x); }).join("<br>");
      if (q.type === "file") return v.map(function (f) { return '<a href="' + esc(fileLink(f.url)) + '" target="_blank" rel="noopener">' + esc(f.name) + "</a>"; }).join("<br>");
      if (q.type === "grid_single" || q.type === "grid_multi") {
        var cl = {};
        (q.cols || []).forEach(function (c) { cl[c.id] = c.label; });
        return (q.rows || []).map(function (r) {
          var x = v[r.id];
          return esc(r.label) + ": <b>" + esc(Array.isArray(x) ? x.map(function (c) { return cl[c]; }).join(", ") : (cl[x] || "—")) + "</b>";
        }).join("<br>");
      }
      if (q.type === "rating") return v + " ★";
      if (q.type === "date") return esc(S.fmtDate(v + " 00:00"));
      return esc(String(v)).replace(/\n/g, "<br>");
    }

    function loadResponse(i) {
      var box = S.byId("svy-resp");
      if (!R.ov.summary.total) { box.innerHTML = '<div class="svy-panel svy-empty">Chưa có phiếu nào.</div>'; return; }
      box.innerHTML = '<div class="svy-panel svy-pad"><div class="svy-skel"></div></div>';
      S.api("results_response", { name: B.name, index: i }).then(function (r) {
        R.idx = r.index;
        var h = '<section class="svy-panel svy-pad"><div class="svy-row between"><div><b>' + (r.respondent ? esc(r.respondent) : (B.settings.anonymous ? "Ẩn danh" : "—")) + '</b><div class="svy-small svy-muted">Nộp ' + esc(S.fmtDt(r.submitted_at)) +
          (r.updated_at ? " · sửa " + esc(S.fmtDt(r.updated_at)) : "") + (r.max_score ? " · điểm " + r.score + "/" + r.max_score : "") + '</div></div><div class="svy-row"><button class="svy-b sm" data-ract="prev"' + (r.index ? "" : " disabled") + ">" + S.icon("back") + "</button>" +
          '<span class="svy-small">' + (r.index + 1) + " / " + r.total + '</span><button class="svy-b sm" data-ract="next"' + (r.index < r.total - 1 ? "" : " disabled") + ">›</button></div></div></section>";
        S.questions(B.form).forEach(function (q, n) {
          h += '<section class="svy-panel svy-pad"><div class="svy-eyebrow">Câu ' + (n + 1) + '</div><div style="font-weight:600;margin-bottom:6px">' + esc(q.title) + "</div><div>" + answerText(q, r.answers[q.id]) + "</div></section>";
        });
        box.innerHTML = '<div class="svy-items">' + h + "</div>";
      }, function (e) { box.innerHTML = '<div class="svy-panel svy-empty">' + esc(e.svyMessage) + "</div>"; });
    }

    function loadNumbers() {
      var box = S.byId("svy-nums");
      if (!box) return;
      box.innerHTML = '<div class="svy-skel" style="margin-top:10px"></div>';
      S.api("number_board", { name: B.name }).then(function (d) {
        if (!R.nums) return;
        var list = d.holders || [];
        box.innerHTML = list.length ? '<div class="svy-held">' + list.map(function (x) {
          return '<div class="it"><span class="svy-ticket">' + esc(x.label) + "</span>" + (x.name ? "<span>" + esc(x.name) + "</span>" : "") + "</div>";
        }).join("") + "</div>" + (B.settings.anonymous ? '<div class="svy-small svy-muted" style="margin-top:6px">Khảo sát ẩn danh: chỉ hiện số, không hiện tên.</div>' : "")
          : '<div class="svy-small svy-muted" style="margin-top:8px">Chưa ai chọn số.</div>';
      }, function (e) { box.innerHTML = '<div class="svy-small" style="margin-top:8px;color:var(--red,#c0392b)">' + esc(e.svyMessage) + "</div>"; });
    }

    function loadPeople() {
      var box = S.byId("svy-people");
      var paint = function () {
        var all = R.people, todo = all.filter(function (p) { return !p.done; }), done = all.filter(function (p) { return p.done; });
        var list = R.pf === "todo" ? todo : done;
        var h = '<div class="svy-row"><button class="svy-chip' + (R.pf === "todo" ? " on" : "") + '" data-pf="todo">Chưa làm · ' + todo.length + '</button><button class="svy-chip' + (R.pf === "done" ? " on" : "") + '" data-pf="done">Đã nộp · ' + done.length + "</button>" +
          (B.settings.anonymous ? '<span class="svy-small svy-muted">Ẩn danh: chỉ biết ai đã nộp, không biết ai trả lời gì.</span>' : "") + "</div>";
        h += list.length ? '<div class="svy-panel svy-board">' + list.map(function (p) {
          return '<div class="it"><span class="svy-av">' + esc(S.initials(p.name)) + '</span><div class="svy-grow"><b>' + esc(p.name) + '</b><div class="svy-small svy-muted">' + esc(p.department || p.user) +
            (p.in_audience ? "" : " · ngoài đối tượng hiện tại") + "</div></div>" + (p.done ? '<span class="svy-small svy-muted">' + esc(S.fmtDt(p.submitted_at)) + "</span>" : "") + "</div>";
        }).join("") + "</div>" : '<div class="svy-panel svy-empty">Không có ai.</div>';
        box.innerHTML = '<div class="svy-items">' + h + "</div>";
      };
      if (R.people) return paint();
      box.innerHTML = '<div class="svy-panel svy-pad"><div class="svy-skel"></div></div>';
      S.api("results_participation", { name: B.name }).then(function (d) { R.people = d.people; paint(); }, function (e) { box.innerHTML = '<div class="svy-panel svy-empty">' + esc(e.svyMessage) + "</div>"; });
    }

    el.onclick = function (e) {
      var sub = e.target.closest("[data-rsub]");
      if (sub) { R.sub = sub.getAttribute("data-rsub"); draw(); return; }
      var pf = e.target.closest("[data-pf]");
      if (pf) { R.pf = pf.getAttribute("data-pf"); loadPeople(); return; }
      var b = e.target.closest("[data-ract]");
      if (!b || b.disabled) return;
      var act = b.getAttribute("data-ract");
      if (act === "reload") { R.people = null; load(); }
      else if (act === "numbers") {
        R.nums = !R.nums;
        b.setAttribute("aria-expanded", String(R.nums));
        var cnt = R.ov.reward.numbers;
        b.innerHTML = S.icon("list") + (R.nums ? "Ẩn các số đã chọn" : "Xem " + cnt + " số đã chọn");
        if (R.nums) loadNumbers(); else S.byId("svy-nums").innerHTML = "";
      }
      else if (act === "prev") loadResponse(R.idx - 1);
      else if (act === "next") loadResponse(R.idx + 1);
      else if (act === "remind") {
        S.confirm("Nhắc người chưa làm?", "Gửi chuông ERP + tin nhắn Teams cho mọi người trong đối tượng chưa nộp. Mỗi người tối đa một lần mỗi ngày.", "Gửi nhắc").then(function (ok) {
          if (!ok) return;
          S.busy(b, true);
          S.api("remind", { name: B.name }, true).then(function (r) { S.busy(b, false); S.toast(r.queued ? "Đang gửi nhắc cho " + r.queued + " người." : "Mọi người đã làm rồi!"); },
            function (err) { S.busy(b, false); S.toast(err.svyMessage, true); });
        });
      } else if (act === "draw") {
        S.confirm("Quay ngay, không chờ giờ hẹn?", "Kết quả được chốt ngay và báo cho người trúng; popup trang chủ hôm nay hiện kết quả. Không hoàn tác được.", "Quay ngay").then(function (ok) {
          if (!ok) return;
          S.busy(b, true);
          S.api("draw", { name: B.name }, true).then(function () { S.toast("Đã chốt kết quả."); load(); },
            function (err) { S.busy(b, false); S.toast(err.svyMessage, true); });
        });
      }
    };
    load();
  }

  window.ECSvyResults = { mount: mount };
})();
