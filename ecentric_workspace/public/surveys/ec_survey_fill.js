// Copyright (c) 2026, eCentric and contributors
// ec_survey_fill.js -- trang /khao-sat/lam?s=<ma>  (xem truoc: &preview=1)
// Tra loi tung phan -> nop -> cam on + diem (bai kiem tra) + phan thuong (vong quay / so may man).
(function () {
  "use strict";
  var S = window.ECSvy, F = window.ECSvyForm, esc = S.esc;
  var root = S.byId("svy-root");
  if (!root || root.getAttribute("data-page") !== "fill") return;

  var st = { name: S.param("s"), preview: S.param("preview") === "1", data: null, form: null, qmap: {},
             answers: {}, cur: 0, errors: {}, rnd: null, done: null, spinning: false };

  function getState() { return st; }

  // ----------------------------------------------------------------------- tai --
  function load() {
    if (!st.name) return fatal("Thiếu mã khảo sát trong đường dẫn.");
    S.api("get_form", { name: st.name, preview: st.preview ? 1 : 0 }).then(function (d) {
      st.data = d;
      st.form = d.form;
      st.qmap = {};
      S.questions(d.form).forEach(function (q) { st.qmap[q.id] = q; });
      st.rnd = S.seeded(d.name + "|" + (window.frappe && frappe.session && frappe.session.user || ""));
      if (d.settings.shuffle_questions) shuffleSections();
      root.style.setProperty("--accent", d.settings.accent_color || "#2C3DA6");
      root.style.setProperty("--on-accent", S.onColor(d.settings.accent_color || "#2C3DA6"));
      document.title = d.title + " - Khảo sát";
      if (d.my_answers) st.answers = S.clone(d.my_answers);
      if (d.submitted && !st.preview && !(d.settings.allow_edit && d.my_answers && d.effective === "open")) {
        st.done = { submitted: true, reward: d.reward, message: "Bạn đã nộp khảo sát này." };
      }
      render();
    }, function (e) { fatal(e.svyMessage); });
  }

  function shuffleSections() {
    var out = [];
    S.sections(st.form).forEach(function (sec) {
      if (sec.sec) out.push(sec.sec);
      var qs = sec.items.filter(function (it) { return it.kind === "question"; });
      var mixed = S.shuffle(qs, st.rnd), k = 0;
      sec.items.forEach(function (it) { out.push(it.kind === "question" ? mixed[k++] : it); });
    });
    st.form = { v: st.form.v, items: out };
  }

  function fatal(msg) {
    root.innerHTML = '<div class="svy-wrap svy-narrow"><div class="svy-panel svy-empty"><b>Không mở được khảo sát</b>' + esc(msg || "") +
      '<div style="margin-top:14px"><a class="svy-b" href="/khao-sat">' + S.icon("back") + "Về danh sách khảo sát</a></div></div></div>";
  }

  // ---------------------------------------------------------------------- ve --
  function header() {
    var d = st.data, set = d.settings, meta = [];
    if (set.close_at) meta.push(S.icon("clock") + "Hạn <b>" + esc(S.fmtDt(set.close_at)) + "</b> (" + esc(S.deadline(set.close_at)) + ")");
    if (set.anonymous) meta.push(S.icon("lock") + "<b>Ẩn danh</b> - người tạo không biết câu trả lời của ai");
    var when = set.draw_scheduled_at ? " · " + esc(S.fmtDt(set.draw_scheduled_at)) + " trên trang chủ" : "";
    if (set.reward_mode === "wheel") meta.push(S.icon("gift") + "Nộp xong được <b>quay vòng quay may mắn</b>");
    if (set.reward_mode === "lucky_number") meta.push(S.icon("gift") + "<span>Nộp xong <b>chọn số may mắn</b>, quay số" + when + "</span>");
    if (set.reward_mode === "race") meta.push(S.icon("gift") + "<span>Nộp xong <b>có xe đua về đích</b>" + when + "</span>");
    if (set.is_quiz) meta.push(S.icon("trophy") + "<b>Bài kiểm tra</b> có chấm điểm");
    var h = "";
    if (st.preview) h += '<div class="svy-banner warn">' + S.icon("eye") + "<div><b>Chế độ xem trước.</b> Câu trả lời không được lưu. Bấm Gửi để thử luồng - không có phiếu nào được tạo.</div></div>";
    var gift = S.giftBox({ mode: set.reward_mode, prizes: d.prizes, drawAt: set.draw_scheduled_at, note: set.reward_note });
    h += '<header class="svy-panel svy-fhead">' + gift + '<div class="band"><span class="sh1" aria-hidden="true"></span><span class="sh2" aria-hidden="true"></span><h1>' + esc(d.title) + "</h1>" +
      (d.description ? '<div class="desc">' + esc(d.description) + "</div>" : "") + "</div>" +
      (meta.length ? '<div class="svy-meta">' + meta.map(function (m) { return '<span class="svy-row" style="gap:6px">' + m + "</span>"; }).join("") + "</div>" : "") + "</header>";
    return h;
  }

  function statusBlock() {
    var e = st.data.effective;
    if (st.preview || e === "open") return "";
    if (e === "scheduled") return '<div class="svy-panel svy-empty"><b>Khảo sát chưa mở</b>Mở lúc ' + esc(S.fmtDt(st.data.settings.open_at)) + ". Quay lại sau nhé.</div>";
    if (e === "draft") return '<div class="svy-panel svy-empty"><b>Khảo sát đang là bản nháp</b>Người soạn chưa phát hành.</div>';
    return '<div class="svy-panel svy-empty"><b>Khảo sát đã đóng</b>Cảm ơn bạn đã quan tâm.</div>';
  }

  function render() {
    var h = '<div class="svy-wrap svy-narrow">' + header();
    if (st.done) h += doneView();
    else {
      var blocked = statusBlock();
      h += blocked || sectionView();
    }
    root.innerHTML = h + "</div>";
    if (st.done && st.done.reward && st.done.reward.mode === "wheel") drawWheel();
  }

  function pathNow() { return S.path(st.form, st.answers); }

  function sectionView() {
    var secs = S.sections(st.form), byId = {};
    secs.forEach(function (s) { byId[s.id] = s; });
    var p = pathNow();
    if (st.cur >= p.length) st.cur = p.length - 1;
    var sec = byId[p[st.cur]];
    var last = st.cur === p.length - 1;
    var h = "";
    if (st.data.settings.show_progress && secs.length > 1) {
      var pct = Math.round(100 * (st.cur + 1) / Math.max(p.length, 1));
      h += '<div class="svy-row" style="gap:10px"><div class="svy-progress svy-grow"><i style="width:' + pct + '%"></i></div><span class="svy-small svy-muted">Phần ' + (st.cur + 1) + "/" + p.length + "</span></div>";
    }
    if (sec.sec && (sec.sec.title || sec.sec.description)) {
      h += '<div class="svy-asec"><div class="eb">Phần ' + (secs.indexOf(sec) + 1) + " / " + secs.length + "</div><h2>" + esc(sec.sec.title) + "</h2>" +
        (sec.sec.description ? '<div class="qd">' + esc(sec.sec.description) + "</div>" : "") + "</div>";
    }
    var n = 0, all = S.questions(st.form);
    sec.items.forEach(function (it) {
      if (it.kind === "note") {
        h += '<section class="svy-panel svy-pad svy-note"><h2>' + esc(it.title) + "</h2>" + (it.description ? '<div class="qd">' + esc(it.description) + "</div>" : "") + "</section>";
        return;
      }
      n++;
      h += F.question(it, st.answers[it.id], { err: st.errors[it.id], rnd: st.rnd, quiz: st.data.settings.is_quiz, number: all.indexOf(it) + 1 });
    });
    if (!n && !sec.items.length) h += '<div class="svy-panel svy-empty">Phần này chưa có câu hỏi.</div>';
    h += '<div class="svy-nav"><div>' + (st.cur > 0 ? '<button class="svy-b" data-act="back">' + S.icon("back") + "Quay lại</button>" : "") + "</div>" +
      '<div class="svy-row"><span class="svy-small svy-muted">* bắt buộc</span>' +
      (last ? '<button class="svy-b pri" data-act="submit">' + S.icon("send") + (st.data.submitted ? "Cập nhật câu trả lời" : "Gửi") + "</button>"
            : '<button class="svy-b pri" data-act="next">Tiếp</button>') + "</div></div>";
    return h;
  }

  // Kiem nhanh phia trinh duyet (bat buoc + so luong lua chon). Server kiem lai day du.
  function checkSection() {
    var secs = S.sections(st.form), p = pathNow(), sec = null;
    secs.forEach(function (s) { if (s.id === p[st.cur]) sec = s; });
    var errs = {};
    (sec ? sec.items : []).forEach(function (q) {
      if (q.kind !== "question") return;
      var v = st.answers[q.id];
      if (q.required && S.isEmpty(q, v)) errs[q.id] = "Câu này bắt buộc.";
      else if (q.type === "multi" && !S.isEmpty(q, v)) {
        var c = S.selected(v).length + (v.other ? 1 : 0);
        if (q.min_select && c < q.min_select) errs[q.id] = "Chọn ít nhất " + q.min_select + " mục.";
        if (q.max_select && c > q.max_select) errs[q.id] = "Chọn tối đa " + q.max_select + " mục.";
      } else if ((q.type === "grid_single" || q.type === "grid_multi") && q.required && q.require_each_row &&
                 Object.keys(v || {}).length < (q.rows || []).length) errs[q.id] = "Cần trả lời đủ mọi hàng.";
    });
    st.errors = errs;
    return !Object.keys(errs).length;
  }

  function focusFirstError() {
    var k = Object.keys(st.errors)[0];
    var el = k && S.byId("q-" + k);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function onChange(id, rerender) {
    if (st.errors[id]) { delete st.errors[id]; rerender = true; }
    if (rerender) {
      var y = window.scrollY;
      render();
      window.scrollTo(0, y);
    }
  }

  function submit(btn) {
    if (!checkSection()) { render(); focusFirstError(); return; }
    if (st.preview) {
      st.done = { submitted: true, preview: true, message: "Xem trước: đến đây người trả lời sẽ thấy lời cảm ơn và phần thưởng." };
      render(); window.scrollTo(0, 0); return;
    }
    S.busy(btn, true);
    S.api("submit", { name: st.name, answers: st.answers }, true).then(function (res) {
      st.done = res;
      st.data.submitted = true;
      render();
      window.scrollTo(0, 0);
    }, function (e) {
      S.busy(btn, false);
      if (e.data && e.data.errors) {
        st.errors = e.data.errors;
        var first = Object.keys(st.errors)[0], p = pathNow(), secs = S.sections(st.form);
        secs.forEach(function (s) {
          if (s.items.some(function (q) { return q.id === first; }) && p.indexOf(s.id) >= 0) st.cur = p.indexOf(s.id);
        });
        render(); focusFirstError();
      }
      S.toast(e.svyMessage, true);
    });
  }

  // ----------------------------------------------------------------- sau khi nop --
  function doneView() {
    var d = st.done, h = '<section class="svy-panel svy-done"><div class="tick">' + S.icon("check") + "</div>" +
      "<h2>" + (d.edited ? "Đã cập nhật câu trả lời" : "Đã gửi câu trả lời") + '</h2><p class="svy-muted" style="white-space:pre-line;margin:6px 0 0">' + esc(d.message || "") + "</p>";
    if (d.score) h += '<div style="margin-top:14px"><div class="svy-eyebrow">Điểm của bạn</div><div class="svy-score">' + d.score.score + "/" + d.score.max_score + "</div></div>";
    h += '<div class="svy-row" style="justify-content:center;margin-top:16px">';
    if (d.summary || st.data.settings.show_summary) h += '<button class="svy-b" data-act="summary">' + S.icon("list") + "Xem tóm tắt kết quả</button>";
    if (!d.preview && st.data.settings.allow_edit && !st.data.settings.anonymous && st.data.effective === "open") h += '<button class="svy-b" data-act="edit">Sửa câu trả lời</button>';
    h += st.preview ? '<button class="svy-b" data-act="restart">Làm lại từ đầu</button>' : '<a class="svy-b" href="/khao-sat">Về trang khảo sát</a>';
    h += "</div></section>";
    if (d.reward && d.reward.mode && d.reward.mode !== "none") h += rewardView(d.reward);
    else if (d.preview && st.data.settings.reward_mode !== "none") h += '<section class="svy-panel svy-reward"><div class="svy-muted">Xem trước: người trả lời sẽ thấy ' + ({ wheel: "vòng quay may mắn", lucky_number: "bảng chọn số may mắn", race: "xe đua của mình" }[st.data.settings.reward_mode] || "phần thưởng") + " ở đây.</div></section>";
    h += '<div id="svy-sum"></div>';
    return h;
  }

  function rewardView(r) {
    var h = '<section class="svy-panel svy-reward" id="svy-reward">';
    if (r.mode === "lucky_number") h += numberView(r);
    else if (r.mode === "race") h += raceView(r);
    else {
      h += '<div class="svy-eyebrow">Vòng quay may mắn</div>' + wavesHTML(r.waves, !!r.result) +
        '<div class="svy-wheelbox"><span class="pin"></span><div id="svy-wheel"></div><div class="hub">eC</div></div><div id="svy-wheel-msg">';
      h += wheelMsg(r) + "</div>";
    }
    if (r.note) h += '<div class="svy-small svy-muted" style="white-space:pre-line">' + esc(r.note) + "</div>";
    return h + "</section>";
  }

  // Vong quay chia dot: dot cua minh + dot nao con qua (khong lo luot trung).
  // Truoc khi quay: KHONG hien luot / dot (biet dot minh con qua hay het thi canh duoc luc quay).
  function wavesHTML(w, spun) {
    if (!spun || !w || !w.waves || !w.waves.length) return '<h2 class="svy-wave-h">Mỗi đợt có đúng 1 phần quà</h2><div class="svy-small svy-muted">Quà rải đều theo thứ tự quay - người quay đầu hay cuối đều cùng cơ hội.</div>';
    var cur = w.waves[w.current - 1];
    var h = '<div class="svy-small svy-muted">Bạn đã quay ở lượt thứ <b>' + w.seq + "</b>" + (cur ? " · đợt " + cur.index : "") + "</div>";
    h += '<div class="svy-waves">' + w.waves.map(function (x) {
      var cls = x.state === "done" ? "done" : x.index === w.current ? "on" : "later";
      var txt = x.state === "done" ? "đã có người trúng" : x.index === w.current ? "còn quà" : x.state === "open" ? "còn quà" : "chưa tới";
      return '<span class="svy-wave ' + cls + '">Đợt ' + x.index + " (lượt " + x.from + "-" + x.to + "): " + txt + "</span>";
    }).join("") + "</div>";
    return h;
  }

  function drawWhen(r) {
    return r.draw_at ? esc(S.fmtDt(r.draw_at)) : "giờ người tạo hẹn";
  }

  function resultLine(r) {
    if (r.result === "Win") return '<h2 style="color:var(--ok)">Chúc mừng! Bạn trúng ' + esc(r.prize_label) + "</h2>";
    if (r.result === "Lose") return '<h3 class="svy-muted">Lần này chưa trúng - hẹn bạn đợt sau!</h3>';
    return "";
  }

  // Con so may man: bang so cong khai, so da co nguoi giu thi khoa; doi so duoc toi gio quay.
  function numberView(r) {
    var b = r.board || { top: 100, holders: [] }, top = b.top, page = st.npage || 0, size = 100;
    var held = {};
    b.holders.forEach(function (x) { held[x.n] = x; });
    var h = '<div class="svy-eyebrow">Con số may mắn của bạn</div><div class="svy-big-ticket"><b>' + esc(r.lucky_number || "???") + "</b></div>";
    if (r.drawn) return h + resultLine(r) + '<p class="svy-muted" style="margin:0">Kết quả quay số nằm trong popup <a href="/">trang chủ</a> hôm quay.</p>';
    h += '<p class="svy-muted" style="margin:0;max-width:52ch">' + (r.lucky_number ? "Đổi được tới giờ quay." : "Chọn một số còn trống - mỗi số chỉ một người giữ.") +
      " Quay số lúc <b>" + drawWhen(r) + "</b>: popup trang chủ tự quay, máy quay trong cả dải nên có thể ra số chưa ai giữ.</p>";
    if (!r.can_pick) return h + '<div class="svy-banner">Đã tới giờ quay - không đổi số được nữa.</div>';
    h += '<div class="svy-row" style="justify-content:center"><button class="svy-b" data-act="pick-random">' + S.icon("gift") + "Chọn giúp tôi một số</button>" +
      '<span class="svy-small svy-muted">' + b.count + " / " + top + " số đã có người giữ</span></div>";
    if (top > size) {
      h += '<div class="svy-npages">';
      for (var pg = 0; pg * size < top; pg++) h += '<button class="svy-b sm' + (pg === page ? " pri" : "") + '" data-npage="' + pg + '">' + (pg * size + 1) + "-" + Math.min(top, (pg + 1) * size) + "</button>";
      h += "</div>";
    }
    h += '<div class="svy-ngrid" role="grid" aria-label="Bảng số may mắn">';
    for (var n = page * size + 1; n <= Math.min(top, (page + 1) * size); n++) {
      var x = held[n], lab = String(n);
      while (lab.length < Math.max(3, String(top).length)) lab = "0" + lab;
      h += x ? '<button class="svy-num ' + (x.me ? "mine" : "taken") + '" ' + (x.me ? "" : "disabled ") + 'title="' + esc(x.me ? "Số của bạn" : x.name) + '">' + lab + "</button>"
        : '<button class="svy-num" data-pick="' + n + '">' + lab + "</button>";
    }
    h += "</div>";
    if (b.holders.length) {
      h += '<div class="svy-holders"><div class="svy-row between"><b>Ai đang giữ số nào</b><span class="svy-small svy-muted">Công khai cho vui · ' + b.holders.length + " người</span></div><div class=\"svy-hlist\">" +
        b.holders.map(function (x) { return '<span class="svy-holder' + (x.me ? " me" : "") + '"><b>' + esc(x.label) + "</b>" + esc(x.me ? "Bạn" : x.name || "Đã có người giữ") + "</span>"; }).join("") + "</div></div>";
    }
    return h;
  }

  function raceView(r) {
    var h = '<div class="svy-eyebrow">Đua về đích</div><div class="svy-cart" aria-hidden="true">🛒</div>';
    if (r.drawn) return h + resultLine(r) + '<p class="svy-muted" style="margin:0">Xem lại cuộc đua trong popup <a href="/">trang chủ</a> hôm đua.</p>';
    return h + '<h2 class="svy-wave-h">Xe của bạn đã vào vạch xuất phát</h2><p class="svy-muted" style="margin:0;max-width:50ch">Ai nộp phiếu cũng có một xe. Đúng <b>' + drawWhen(r) +
      "</b> popup trang chủ tự mở và các xe chạy từ KHO eCentric tới vạch GIAO THÀNH CÔNG - về đầu nhận quà. Trước 5 phút bạn nhận thông báo.</p>";
  }

  function wheelMsg(r) {
    if (r.can_spin) return '<button class="svy-b gold" data-act="spin" style="padding:12px 28px;font-size:15px">Quay ngay!</button>';
    if (r.result === "Win") return '<h2 style="color:var(--ok)">Chúc mừng! Bạn trúng ' + esc(r.prize_label) + "</h2>";
    if (r.result === "Lose") return '<h3 class="svy-muted">Chúc bạn may mắn lần sau!</h3>';
    return "";
  }

  function redrawReward() {
    var box = S.byId("svy-reward");
    if (box) box.outerHTML = rewardView(st.done.reward);
  }

  function pick(n, btn) {
    if (st.picking) return;
    st.picking = true;
    if (btn) S.busy(btn, true);
    S.api("pick_number", { name: st.name, number: n || 0 }, true).then(function (r) {
      st.picking = false;
      st.done.reward = r;
      redrawReward();
      S.toast("Bạn đang giữ số " + r.lucky_number);
    }, function (e) {
      st.picking = false;
      if (btn) S.busy(btn, false);
      S.toast(e.svyMessage, true);
      refreshBoard();
    });
  }

  // Lam moi bang so moi 20 giay khi con chon duoc - thay so nguoi khac vua giu.
  function refreshBoard() {
    var r = st.done && st.done.reward;
    if (!r || r.mode !== "lucky_number" || !r.can_pick || document.hidden) return;
    S.api("number_board", { name: st.name }).then(function (b) {
      if (!st.done || !st.done.reward || st.picking) return;
      st.done.reward.board = b;
      st.done.reward.can_pick = b.can_pick;
      redrawReward();
    }, function () { /* im lang: lan sau thu lai */ });
  }
  setInterval(refreshBoard, 20000);

  function segments() {
    var prizes = st.data.prizes || [], segs = [], palette = ["#2C3DA6", "#f5b800", "#EF7CAF", "#10b981", "#7c3aed", "#0ea5e9", "#f97316"];
    var n = Math.max(6, prizes.length * 2);
    var lose = n - prizes.length, pi = 0, li = 0;
    for (var i = 0; i < n; i++) {
      var takePrize = pi < prizes.length && (li >= lose || i % 2 === 0);
      if (takePrize) { var p = prizes[pi++]; segs.push({ win: true, id: p.id, label: p.label, color: p.color || palette[(pi - 1) % palette.length] }); }
      else { li++; segs.push({ win: false, label: "Chúc may mắn", color: li % 2 ? "#eef0fb" : "#ffffff" }); }
    }
    return segs;
  }

  function drawWheel(rotation) {
    var box = S.byId("svy-wheel");
    if (!box) return;
    var segs = segments(), n = segs.length, R = 100, h = "";
    st.segs = segs;
    segs.forEach(function (s, i) {
      var a0 = (i / n) * 2 * Math.PI - Math.PI / 2, a1 = ((i + 1) / n) * 2 * Math.PI - Math.PI / 2;
      var x0 = R + R * Math.cos(a0), y0 = R + R * Math.sin(a0), x1 = R + R * Math.cos(a1), y1 = R + R * Math.sin(a1);
      var mid = (a0 + a1) / 2, tx = R + R * 0.62 * Math.cos(mid), ty = R + R * 0.62 * Math.sin(mid);
      var dark = s.win && !/^#f(5b8|fff)/i.test(s.color);
      h += '<path d="M' + R + "," + R + " L" + x0.toFixed(2) + "," + y0.toFixed(2) + " A" + R + "," + R + " 0 0,1 " + x1.toFixed(2) + "," + y1.toFixed(2) + ' Z" fill="' + esc(s.color) + '" stroke="#fff" stroke-width="1.2"/>';
      var label = s.label.length > 14 ? s.label.slice(0, 13) + "…" : s.label;
      h += '<text x="' + tx.toFixed(2) + '" y="' + ty.toFixed(2) + '" transform="rotate(' + (mid * 180 / Math.PI + 90).toFixed(1) + " " + tx.toFixed(2) + " " + ty.toFixed(2) +
        ')" text-anchor="middle" dominant-baseline="middle" font-size="' + (n > 10 ? 6.5 : 8) + '" font-weight="700" fill="' + (dark ? "#fff" : "#1f2937") + '">' + esc(label) + "</text>";
    });
    box.innerHTML = '<svg class="wheel" viewBox="0 0 200 200" style="transform:rotate(' + (rotation || 0) + 'deg)"><circle cx="100" cy="100" r="99" fill="#fff"/>' + h + "</svg>";
  }

  function spin(btn) {
    if (st.spinning) return;
    st.spinning = true;
    S.busy(btn, true);
    S.api("spin", { name: st.name }, true).then(function (r) {
      var segs = st.segs || segments(), n = segs.length, idx = 0, cands = [];
      segs.forEach(function (s, i) { if (r.result === "Win" ? (s.win && s.id === r.prize) : !s.win) cands.push(i); });
      idx = cands.length ? cands[Math.floor(Math.random() * cands.length)] : 0;
      var center = (idx + 0.5) * 360 / n, jitter = (Math.random() - 0.5) * (300 / n);
      var target = 360 * 7 + (360 - center) + jitter;
      var svg = S.byId("svy-wheel").querySelector("svg");
      S.byId("svy-wheel-msg").innerHTML = '<div class="svy-muted">Đang quay...</div>';
      requestAnimationFrame(function () { svg.style.transform = "rotate(" + target + "deg)"; });
      setTimeout(function () {
        st.spinning = false;
        st.done.reward = r;
        S.byId("svy-wheel-msg").innerHTML = wheelMsg(r);
        var head = document.querySelector("#svy-reward .svy-wave-h");
        if (head && r.waves) {
          var tmp = document.createElement("div"); tmp.innerHTML = wavesHTML(r.waves, true);
          var note = head.nextElementSibling;
          head.parentNode.insertBefore(tmp, head); head.remove(); if (note) note.remove();
        }
        if (r.result === "Win") confetti();
      }, 5400);
    }, function (e) {
      st.spinning = false;
      S.busy(btn, false);
      S.toast(e.svyMessage, true);
    });
  }

  function confetti() {
    var box = document.createElement("div"), colors = ["#2C3DA6", "#f5b800", "#EF7CAF", "#10b981", "#0ea5e9"];
    box.className = "svy-confetti";
    for (var i = 0; i < 90; i++) {
      var p = document.createElement("i");
      p.style.left = Math.random() * 100 + "%";
      p.style.background = colors[i % colors.length];
      p.style.animationDelay = (Math.random() * 0.8) + "s";
      p.style.transform = "rotate(" + Math.random() * 360 + "deg)";
      box.appendChild(p);
    }
    S.byId("ec-svy").appendChild(box);
    setTimeout(function () { box.remove(); }, 4200);
  }

  function showSummary(btn) {
    var box = S.byId("svy-sum");
    if (box.innerHTML) { box.innerHTML = ""; return; }
    var put = function (sum) {
      box.innerHTML = '<div class="svy-row between" style="margin:8px 0"><h2 style="font-size:17px">Tóm tắt kết quả</h2><span class="svy-muted svy-small">' + sum.total + " phiếu</span></div>" +
        '<div class="svy-items">' + window.ECSvySummary.render(st.form, sum, { texts: false }) + "</div>";
    };
    if (st.done.summary) return put(st.done.summary);
    S.busy(btn, true);
    S.api("public_summary", { name: st.name }).then(function (sum) { S.busy(btn, false); st.done.summary = sum; put(sum); },
      function (e) { S.busy(btn, false); S.toast(e.svyMessage, true); });
  }

  // ------------------------------------------------------------------- su kien --
  root.addEventListener("click", function (e) {
    var pk = e.target.closest("[data-pick]");
    if (pk) { pick(parseInt(pk.getAttribute("data-pick"), 10), pk); return; }
    var pg = e.target.closest("[data-npage]");
    if (pg) { st.npage = parseInt(pg.getAttribute("data-npage"), 10); redrawReward(); return; }
    var b = e.target.closest("[data-act]");
    if (!b || b.disabled) return;
    var act = b.getAttribute("data-act");
    if (act === "next") {
      if (!checkSection()) { render(); focusFirstError(); return; }
      st.cur++; render(); window.scrollTo(0, 0);
    } else if (act === "back") { st.cur = Math.max(0, st.cur - 1); st.errors = {}; render(); window.scrollTo(0, 0); }
    else if (act === "submit") submit(b);
    else if (act === "spin") spin(b);
    else if (act === "pick-random") pick(0, b);
    else if (act === "summary") showSummary(b);
    else if (act === "edit") { st.done = null; st.cur = 0; render(); window.scrollTo(0, 0); }
    else if (act === "restart") { st.done = null; st.cur = 0; st.answers = {}; st.errors = {}; render(); window.scrollTo(0, 0); }
  });
  F.bind(root, getState, onChange);

  function boot() { load(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
