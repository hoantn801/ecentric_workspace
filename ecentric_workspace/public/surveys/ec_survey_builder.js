// Copyright (c) 2026, eCentric and contributors
// ec_survey_builder.js -- trang /khao-sat/soan?s=<ma>: khung trinh soan + tu luu + 4 tab
// Cai dat / Doi tuong / Phan thuong (o day) va Cau hoi (ec_survey_editor.js), Ket qua
// (ec_survey_results.js). Phat hanh / dong / mo lai / nhan ban / xoa.
//
// Tu luu: moi thay doi -> cho 1.2s -> POST save toan bo (settings + form + 3 bang con) kem
// `modified` lan tai truoc. Server tu choi neu ai khac vua luu -> hien thanh bao tai lai,
// KHONG ghi de im lang.
(function () {
  "use strict";
  var S = window.ECSvy, E = window.ECSvyEditor, esc = S.esc;
  var root = S.byId("svy-root");
  if (!root || root.getAttribute("data-page") !== "builder") return;

  var COLORS = ["#2C3DA6", "#0f766e", "#7c3aed", "#db2777", "#ea580c", "#ca8a04", "#16a34a", "#0284c7", "#334155"];
  var STATUS = { draft: ["Nháp", "mute"], scheduled: ["Sắp mở", "warn"], open: ["Đang mở", "ok"], closed: ["Đã đóng", "bad"] };
  var B = { name: S.param("s"), tab: S.param("tab") || "questions", active: null, dir: null, dirErr: "",
            timer: null, saving: null, again: false, saveText: "", saveErr: false, conflict: false, pick: null };

  // ------------------------------------------------------------------- tu luu --
  B.changed = function (structural) {
    B.saveText = "Đang chờ lưu...";
    B.saveErr = false;
    paintSave();
    var tt = document.querySelector("#svy-bhead .ttl");
    if (tt) tt.textContent = B.settings.title || "Khảo sát";
    clearTimeout(B.timer);
    B.timer = setTimeout(save, 1200);
    if (structural) B.redraw();
  };
  B.onCount = function (n) {             // tab Ket qua vua dem lai so phieu -> so tren tab
    if (B.data.stats.responses === n) return;
    B.data.stats.responses = n;
    drawHead();
  };
  B.redraw = function () { var y = window.scrollY; drawTab(); window.scrollTo(0, y); };

  function payload() {
    return { modified: B.modified, settings: B.settings, form: B.form, targets: B.targets, editors: B.editors, prizes: B.prizes };
  }
  function save() {
    clearTimeout(B.timer);
    B.timer = null;
    if (B.conflict) return Promise.resolve();
    if (B.saving) { B.again = true; return B.saving; }
    B.saveText = "Đang lưu...";
    paintSave();
    B.saving = S.api("save", { name: B.name, payload: payload() }, true).then(function (r) {
      B.modified = r.modified;
      (r.prizes || []).forEach(function (p, i) { if (B.prizes[i]) { B.prizes[i].id = p.id; B.prizes[i].awarded = p.awarded; } });
      B.saveText = "Đã lưu " + new Date().toTimeString().slice(0, 5);
      B.saveErr = false;
    }, function (e) {
      B.saveErr = true;
      B.saveText = "Chưa lưu được";
      if (/người vừa sửa/.test(e.svyMessage || "")) { B.conflict = true; drawHead(); }
      S.toast(e.svyMessage, true);
    }).then(function () {
      B.saving = null;
      paintSave();
      if (B.again) { B.again = false; return save(); }
    });
    return B.saving;
  }
  function flush() { return B.timer || B.saving ? save() : Promise.resolve(); }
  function paintSave() { var el = S.byId("svy-save"); if (el) { el.textContent = B.saveText; el.className = "svy-save" + (B.saveErr ? " err" : ""); } }
  window.addEventListener("beforeunload", function (e) { if (B.timer || B.saving) { e.preventDefault(); e.returnValue = ""; } });

  // --------------------------------------------------------------------- tai --
  function load() {
    if (!B.name) return fatal("Thiếu mã khảo sát.");
    S.api("get_builder", { name: B.name }).then(function (d) {
      B.data = d;
      B.settings = d.settings;
      B.form = d.form;
      B.targets = d.targets;
      B.editors = d.editors;
      B.prizes = d.prizes;
      B.modified = d.modified;
      B.active = (d.form.items[0] || {}).id || null;
      document.title = d.settings.title + " - Soạn khảo sát";
      drawAll();
      S.api("directory").then(function (dir) { B.dir = dir; if (B.tab === "audience" || B.tab === "settings") drawTab(); },
        function (e) { B.dirErr = e.svyMessage; });
    }, function (e) { fatal(e.svyMessage); });
  }
  function fatal(msg) {
    root.innerHTML = '<div class="svy-wrap"><div class="svy-panel svy-empty"><b>Không mở được trình soạn</b>' + esc(msg) + '<div style="margin-top:12px"><a class="svy-b" href="/khao-sat/quan-ly">Về danh sách</a></div></div></div>';
  }

  // --------------------------------------------------------------- khung trang --
  function drawAll() {
    root.innerHTML = '<div class="svy-bhead" id="svy-bhead"></div><div class="svy-wrap" id="svy-tab" style="max-width:900px"></div>';
    drawHead();
    drawTab();
  }

  function drawHead() {
    var d = B.data, st = STATUS[d.effective] || STATUS.draft;
    var tabs = [["questions", "Câu hỏi"], ["settings", "Cài đặt"], ["audience", "Đối tượng"], ["reward", "Phần thưởng"], ["results", "Kết quả", d.stats.responses]];
    var act = d.status === "Draft" ? '<button class="svy-b pri" data-act="publish">' + S.icon("send") + "Phát hành</button>"
      : d.status === "Open" ? '<button class="svy-b" data-act="close">Đóng khảo sát</button>' : '<button class="svy-b pri" data-act="reopen">Mở lại</button>';
    var h = '<div class="in"><div class="svy-row between" style="flex-wrap:nowrap"><div class="svy-row svy-grow" style="flex-wrap:nowrap;min-width:0">' +
      '<a class="svy-b ghost icon" href="/khao-sat/quan-ly" title="Về danh sách">' + S.icon("back") + "</a>" +
      '<div style="min-width:0"><div class="ttl">' + esc(B.settings.title || "Khảo sát") + '</div><div class="svy-row" style="gap:6px"><span class="svy-pill ' + st[1] + '">' + st[0] + '</span><span class="svy-save" id="svy-save"></span></div></div></div>' +
      '<div class="svy-row" style="flex-wrap:nowrap"><a class="svy-b ghost icon" href="/khao-sat/lam?s=' + encodeURIComponent(B.name) + '&preview=1" target="_blank" rel="noopener" title="Xem trước">' + S.icon("eye") + "</a>" +
      '<button class="svy-b ghost icon" data-act="link" title="Sao chép đường dẫn">' + S.icon("link") + "</button>" +
      '<button class="svy-b ghost icon" data-act="dup" title="Nhân bản cho đợt mới">' + S.icon("copy") + "</button>" +
      (d.status === "Draft" && d.is_owner ? '<button class="svy-b ghost icon danger" data-act="del" title="Xoá bản nháp">' + S.icon("trash") + "</button>" : "") + act + "</div></div>" +
      '<nav class="svy-tabs" role="tablist">' + tabs.map(function (t) {
        return '<button class="svy-tab' + (B.tab === t[0] ? " on" : "") + '" data-tab="' + t[0] + '" role="tab" aria-selected="' + (B.tab === t[0]) + '">' + t[1] + (t[2] !== undefined ? '<span class="n">' + t[2] + "</span>" : "") + "</button>";
      }).join("") + "</nav></div>";
    if (B.conflict) h += '<div class="svy-wrap" style="padding-top:8px;padding-bottom:0;max-width:900px"><div class="svy-banner bad">' + S.icon("x") + '<div class="svy-grow">Có người vừa sửa khảo sát này ở nơi khác - thay đổi của bạn chưa được lưu.</div><button class="svy-b sm" onclick="location.reload()">Tải lại</button></div></div>';
    S.byId("svy-bhead").innerHTML = h;
    paintSave();
  }

  function drawTab() {
    var el = S.byId("svy-tab");
    if (!el) return;
    if (B.tab === "results") { el.innerHTML = '<div id="svy-results"></div>'; window.ECSvyResults.mount(S.byId("svy-results"), B); return; }
    el.innerHTML = B.tab === "settings" ? settingsTab() : B.tab === "audience" ? audienceTab() : B.tab === "reward" ? rewardTab() : E.render(B);
  }

  // ------------------------------------------------------------------- cai dat --
  function sw(field, title, sub, disabled) {
    return '<div class="svy-setrow"><div class="t"><b>' + title + "</b>" + (sub ? "<span>" + sub + "</span>" : "") + '</div><label class="svy-switch"><input type="checkbox" data-s="' + field + '"' +
      (+B.settings[field] ? " checked" : "") + (disabled ? " disabled" : "") + ' aria-label="' + esc(title) + '"></label></div>';
  }
  function settingsTab() {
    var s = B.settings, d = B.data;
    var h = '<section class="svy-panel svy-pad"><h3 style="font-size:15px;margin-bottom:12px">Thời gian</h3><div class="svy-form2">' +
      '<div class="svy-field"><label for="s-open">Mở từ</label><input id="s-open" class="svy-in" type="datetime-local" data-s="open_at" value="' + esc(S.toLocalInput(s.open_at)) + '"><span class="hint">Để trống = mở ngay khi phát hành.</span></div>' +
      '<div class="svy-field"><label for="s-close">Đóng lúc</label><input id="s-close" class="svy-in" type="datetime-local" data-s="close_at" value="' + esc(S.toLocalInput(s.close_at)) + '"><span class="hint">Qua giờ này khảo sát tự đóng.</span></div>' +
      '<div class="svy-field"><label for="s-limit">Giới hạn số phiếu</label><input id="s-limit" class="svy-in" type="number" min="0" data-s="response_limit" value="' + (s.response_limit || 0) + '"><span class="hint">0 = không giới hạn. Đủ phiếu thì tự đóng.</span></div></div></section>';
    h += '<section class="svy-panel svy-pad"><h3 style="font-size:15px">Trả lời</h3>' +
      sw("anonymous", "Ẩn danh", "Không lưu tên người trả lời cùng câu trả lời. Không đổi được sau khi đã có phiếu." + (d.stats.responses ? " <b>Đã có phiếu - đang khoá.</b>" : ""), d.stats.responses > 0) +
      sw("allow_edit", "Cho sửa câu trả lời sau khi nộp", "Chỉ khi khảo sát còn mở và không ẩn danh.") +
      sw("show_progress", "Hiện thanh tiến độ", "Khi khảo sát có nhiều phần.") +
      sw("shuffle_questions", "Xáo thứ tự câu hỏi", "Trong từng phần; mỗi người một thứ tự cố định.") +
      sw("show_summary", "Cho người trả lời xem tóm tắt kết quả", "Chỉ số đếm / trung bình, không có câu trả lời chữ.") +
      sw("notify_on_publish", "Báo cho đối tượng khi phát hành", "Thông báo chuông ERP + web push (không gửi Teams).") +
      '<div class="svy-field" style="margin-top:10px"><label for="s-confirm">Lời nhắn sau khi nộp</label><textarea id="s-confirm" class="svy-ta" style="min-height:60px" data-s="confirmation_message" placeholder="Cảm ơn bạn đã trả lời khảo sát!" maxlength="1000">' + esc(s.confirmation_message || "") + "</textarea></div></section>";
    h += '<section class="svy-panel svy-pad"><h3 style="font-size:15px">Bài kiểm tra</h3>' +
      sw("is_quiz", "Bật chế độ bài kiểm tra", "Gán điểm và đáp án đúng cho câu trắc nghiệm / hộp kiểm / thả xuống / trả lời ngắn.") +
      (+s.is_quiz ? sw("show_score", "Hiện điểm ngay sau khi nộp", "") : "") + "</section>";
    h += '<section class="svy-panel svy-pad"><h3 style="font-size:15px;margin-bottom:10px">Giao diện</h3><div class="svy-lbl" style="margin-bottom:6px">Màu chủ đạo</div><div class="svy-swatches">' +
      COLORS.map(function (c) { return '<button class="svy-sw' + (s.accent_color === c ? " on" : "") + '" style="background:' + c + '" data-color="' + c + '" aria-label="Màu ' + c + '"></button>'; }).join("") + "</div></section>";
    h += '<section class="svy-panel svy-pad"><h3 style="font-size:15px">Người cùng quản lý</h3><div class="svy-small svy-muted" style="margin:2px 0 10px">Được soạn câu hỏi và xem kết quả. Chủ khảo sát: <b>' + esc(d.owner_name) + "</b>.</div>";
    if (d.is_owner) h += tags(B.editors.map(function (e) { return { key: e.user, label: e.label }; }), "editor") + picker("editor", "Thêm người cùng quản lý");
    else h += tags(B.editors.map(function (e) { return { key: e.user, label: e.label }; }), null) + '<div class="svy-small svy-muted">Chỉ chủ khảo sát thay đổi được danh sách này.</div>';
    return h + "</section>";
  }

  // ----------------------------------------------------------------- doi tuong --
  function tags(list, kind, cls) {
    if (!list.length) return '<div class="svy-small svy-muted" style="margin-bottom:8px">Chưa có ai.</div>';
    return '<div class="svy-tags" style="margin-bottom:8px">' + list.map(function (t) {
      return '<span class="svy-tag' + (cls ? " " + cls : "") + '">' + esc(t.label) + (kind ? '<button data-untag="' + kind + '" data-key="' + esc(t.key) + '" aria-label="Bỏ">' + S.icon("x") + "</button>" : "") + "</span>";
    }).join("") + "</div>";
  }
  function picker(kind, placeholder) {
    if (!B.dir) return '<div class="svy-small svy-muted">' + esc(B.dirErr || "Đang tải danh bạ...") + "</div>";
    return '<div class="svy-pick" data-pickbox="' + kind + '"><input class="svy-in" type="search" data-pick="' + kind + '" placeholder="' + esc(placeholder) + '" autocomplete="off"><div class="list" hidden></div></div>';
  }
  function deptLabel(n) { var d = (B.dir && B.dir.departments || []).find(function (x) { return x.name === n; }); return d ? d.label : n; }
  function personLabel(u) { var p = (B.dir && B.dir.people || []).find(function (x) { return x.user === u; }); return p ? p.name : u; }

  // Ban sao cua domain/audience.py - chi de hien "khoang N nguoi"; server tinh lai khi luu.
  function eligibleCount() {
    if (!B.dir) return null;
    var parent = {}, depts = {}, users = {}, excl = {};
    B.dir.departments.forEach(function (d) { parent[d.name] = d.parent; });
    B.targets.forEach(function (t) {
      if (t.kind === "Department") depts[t.department] = 1;
      else if (t.kind === "User") users[t.user] = 1;
      else if (t.kind === "Exclude") excl[t.user] = 1;
    });
    var out = {};
    B.dir.people.forEach(function (p) {
      if (B.settings.audience_mode === "all") { out[p.user] = 1; return; }
      var cur = p.department, guard = 0;
      while (cur && guard++ < 50) { if (depts[cur]) { out[p.user] = 1; break; } cur = parent[cur]; }
    });
    if (B.settings.audience_mode !== "all") Object.keys(users).forEach(function (u) { out[u] = 1; });
    Object.keys(excl).forEach(function (u) { delete out[u]; });
    return Object.keys(out).length;
  }

  function deptTree() {
    var kids = {}, chosen = {};
    B.dir.departments.forEach(function (d) { (kids[d.parent || ""] = kids[d.parent || ""] || []).push(d); });
    B.targets.forEach(function (t) { if (t.kind === "Department") chosen[t.department] = 1; });
    var known = {};
    B.dir.departments.forEach(function (d) { known[d.name] = 1; });
    var roots = B.dir.departments.filter(function (d) { return !d.parent || !known[d.parent]; });
    function walk(list, depth, inherited) {
      return list.map(function (d) {
        var on = !!chosen[d.name];
        return '<label style="padding-left:' + (6 + depth * 18) + 'px"><input type="checkbox" data-dept="' + esc(d.name) + '"' + (on || inherited ? " checked" : "") + (inherited ? " disabled" : "") + ">" + esc(d.label) +
          (inherited ? ' <span class="svy-small svy-muted">(theo phòng cha)</span>' : "") + "</label>" + walk(kids[d.name] || [], depth + 1, inherited || on);
      }).join("");
    }
    return '<input class="svy-in" type="search" data-deptq placeholder="Lọc phòng ban" style="margin-bottom:8px"><div class="svy-tree" id="svy-tree">' + walk(roots, 0, false) + "</div>";
  }

  function audienceTab() {
    var s = B.settings, n = eligibleCount();
    var inc = B.targets.filter(function (t) { return t.kind === "User"; }).map(function (t) { return { key: t.user, label: t.label || personLabel(t.user) }; });
    var exc = B.targets.filter(function (t) { return t.kind === "Exclude"; }).map(function (t) { return { key: t.user, label: t.label || personLabel(t.user) }; });
    var h = '<section class="svy-panel svy-pad"><div class="svy-row between" style="margin-bottom:12px"><h3 style="font-size:15px">Ai được làm khảo sát?</h3>' +
      (n === null ? "" : '<span class="svy-pill run">≈ ' + n + " người</span>") + '</div><div class="svy-modes" style="grid-template-columns:repeat(2,minmax(0,1fr))">' +
      '<button class="svy-mode' + (s.audience_mode === "all" ? " on" : "") + '" data-amode="all"><b>Cả công ty</b><span>Mọi nhân viên đang làm việc (hồ sơ Active).</span></button>' +
      '<button class="svy-mode' + (s.audience_mode === "custom" ? " on" : "") + '" data-amode="custom"><b>Chọn phòng ban / người</b><span>Chọn phòng ban (tính cả phòng con) và thêm từng người.</span></button></div></section>';
    if (s.audience_mode === "custom") {
      h += '<section class="svy-panel svy-pad"><h3 style="font-size:15px;margin-bottom:10px">Phòng ban tham gia</h3>' + (B.dir ? deptTree() : '<div class="svy-small svy-muted">' + esc(B.dirErr || "Đang tải...") + "</div>") + "</section>";
      h += '<section class="svy-panel svy-pad"><h3 style="font-size:15px;margin-bottom:10px">Thêm từng người</h3>' + tags(inc, "User") + picker("User", "Tìm theo tên hoặc email") + "</section>";
    }
    h += '<section class="svy-panel svy-pad"><h3 style="font-size:15px">Không được tham gia</h3><div class="svy-small svy-muted" style="margin:2px 0 10px">Người trong danh sách này không làm được khảo sát, kể cả khi thuộc phòng ban đã chọn.</div>' +
      tags(exc, "Exclude", "x") + picker("Exclude", "Thêm người bị loại trừ") + "</section>";
    return h;
  }

  // --------------------------------------------------------------- phan thuong --
  function rewardTab() {
    var s = B.settings, started = B.data.stats.reward_started;
    var modes = [["none", "Không có quà", "Khảo sát bình thường."], ["wheel", "Vòng quay may mắn", "Nộp xong quay ngay, biết kết quả liền."], ["lucky_number", "Con số may mắn", "Nộp xong nhận số; cuối đợt bạn bấm quay số."]];
    var h = '<section class="svy-panel svy-pad"><h3 style="font-size:15px;margin-bottom:12px">Kiểu phần thưởng</h3>' +
      (started ? '<div class="svy-banner warn" style="margin-bottom:10px">' + S.icon("lock") + "<div>Đã có người nhận quà / số - không đổi kiểu phần thưởng được nữa.</div></div>" : "") +
      '<div class="svy-modes">' + modes.map(function (m) {
        return '<button class="svy-mode' + (s.reward_mode === m[0] ? " on" : "") + '" data-rmode="' + m[0] + '"' + (started && s.reward_mode !== m[0] ? " disabled" : "") + "><b>" + m[1] + "</b><span>" + m[2] + "</span></button>";
      }).join("") + "</div></section>";
    if (s.reward_mode === "none") return h;
    h += '<section class="svy-panel svy-pad"><h3 style="font-size:15px;margin-bottom:10px">Quà</h3><div class="svy-items" style="gap:8px">';
    B.prizes.forEach(function (p, i) {
      h += '<div class="svy-prize"><input type="color" data-p="color" data-i="' + i + '" value="' + esc(p.color || "#2C3DA6") + '" aria-label="Màu ô">' +
        '<input class="svy-in" data-p="label" data-i="' + i + '" value="' + esc(p.label) + '" placeholder="Tên quà, vd Ly trà sữa" maxlength="80">' +
        '<input class="svy-in" type="number" min="' + (p.awarded || 0) + '" data-p="quantity" data-i="' + i + '" value="' + p.quantity + '" aria-label="Số lượng">' +
        '<span class="aw svy-small svy-muted">Đã trao ' + (p.awarded || 0) + "</span>" +
        '<button class="svy-b ghost icon danger" data-act="pdel" data-i="' + i + '"' + (p.awarded ? " disabled" : "") + ' title="Xoá quà">' + S.icon("x") + "</button></div>";
    });
    h += '</div><button class="svy-b sm" style="margin-top:10px" data-act="padd">' + S.icon("plus") + "Thêm quà</button></section>";
    h += '<section class="svy-panel svy-pad"><div class="svy-form2">';
    if (s.reward_mode === "wheel") {
      h += '<div class="svy-field"><label for="r-exp">Số người dự kiến tham gia</label><input id="r-exp" class="svy-in" type="number" min="0" data-s="wheel_expected" value="' + (s.wheel_expected || 0) + '">' +
        '<span class="hint">Để 0 = lấy số người trong đối tượng (≈ ' + (eligibleCount() || B.data.stats.eligible) + "). Xác suất trúng mỗi lượt = quà còn lại / lượt còn lại, nên nếu đủ người tham gia sẽ phát đúng hết số quà. Ít người hơn dự kiến thì hạ số này xuống.</span></div>";
    }
    h += '<div class="svy-field"><label for="r-note">Cách nhận quà</label><textarea id="r-note" class="svy-ta" style="min-height:70px" data-s="reward_note" placeholder="Vd: Nhận tại quầy lễ tân tầng 5 trước 17:00 thứ Sáu." maxlength="1000">' + esc(s.reward_note || "") + "</textarea></div></div></section>";
    if (s.reward_mode === "lucky_number") h += '<div class="svy-banner">' + S.icon("gift") + "<div>Quay số ở tab <b>Kết quả</b> khi kết thúc đợt. Người trúng nhận thông báo qua chuông ERP.</div></div>";
    return h;
  }

  // ------------------------------------------------------------------- su kien --
  function setField(f, v) { B.settings[f] = v; }

  root.addEventListener("input", function (e) {
    var t = e.target;
    if (B.tab === "questions" && E.onInput(e, B)) return;
    if (t.hasAttribute("data-s") && t.type !== "checkbox") { setField(t.getAttribute("data-s"), t.type === "number" ? (parseInt(t.value, 10) || 0) : t.value); B.changed(false); if (t.getAttribute("data-s") === "title") drawHead(); return; }
    if (t.hasAttribute("data-p")) {
      var p = B.prizes[+t.getAttribute("data-i")], k = t.getAttribute("data-p");
      p[k] = k === "quantity" ? Math.max(p.awarded || 0, parseInt(t.value, 10) || 0) : t.value;
      B.changed(false); return;
    }
    if (t.hasAttribute("data-pick")) { showPick(t); return; }
    if (t.hasAttribute("data-deptq")) {
      var q = t.value.trim().toLowerCase();
      S.qsa(S.byId("svy-tree"), "label").forEach(function (l) { l.hidden = q && l.textContent.toLowerCase().indexOf(q) < 0; });
    }
  });
  root.addEventListener("change", function (e) {
    var t = e.target;
    if (B.tab === "questions" && E.onInput(e, B)) return;
    if (t.hasAttribute("data-s") && t.type === "checkbox") {
      setField(t.getAttribute("data-s"), t.checked ? 1 : 0);
      if (t.getAttribute("data-s") === "anonymous" && t.checked) setField("allow_edit", 0);
      B.changed(true); return;
    }
    if (t.hasAttribute("data-dept")) {
      var name = t.getAttribute("data-dept");
      B.targets = B.targets.filter(function (x) { return !(x.kind === "Department" && x.department === name); });
      if (t.checked) B.targets.push({ kind: "Department", department: name, label: deptLabel(name) });
      B.changed(true);
    }
  });

  function showPick(input) {
    var kind = input.getAttribute("data-pick"), q = input.value.trim().toLowerCase(), list = input.parentNode.querySelector(".list");
    if (!q) { list.hidden = true; return; }
    var taken = {};
    if (kind === "editor") B.editors.forEach(function (x) { taken[x.user] = 1; });
    else B.targets.forEach(function (x) { if (x.kind === kind) taken[x.user] = 1; });
    var hits = B.dir.people.filter(function (p) {
      return !taken[p.user] && (p.name.toLowerCase().indexOf(q) >= 0 || p.user.toLowerCase().indexOf(q) >= 0);
    }).slice(0, 8);
    list.innerHTML = hits.length ? hits.map(function (p) {
      return '<button type="button" data-pickadd="' + kind + '" data-user="' + esc(p.user) + '" data-label="' + esc(p.name) + '"><span class="svy-av" style="width:26px;height:26px;font-size:11px">' + esc(S.initials(p.name)) +
        '</span><span class="svy-grow"><b>' + esc(p.name) + '</b><br><span class="svy-small svy-muted">' + esc(p.user) + (p.department ? " · " + esc(deptLabel(p.department)) : "") + "</span></span></button>";
    }).join("") : '<div class="svy-small svy-muted" style="padding:10px 12px">Không tìm thấy.</div>';
    list.hidden = false;
  }

  function publishFlow(btn) {
    S.busy(btn, true);
    flush().then(function () { return S.api("publish", { name: B.name }, true); }).then(function (r) {
      S.toast(r.notified ? "Đã phát hành - đang gửi thông báo cho đối tượng." : "Đã phát hành.");
      return reloadMeta();
    }, function (e) {
      S.busy(btn, false);
      if (/Chưa phát hành được/.test(e.svyMessage || "")) {
        S.modal('<h3>Chưa phát hành được</h3><div style="white-space:pre-line">' + esc(e.svyMessage.replace(/^Chưa phát hành được:\n/, "")) + '</div><div class="svy-row" style="justify-content:flex-end"><button class="svy-b pri" data-close>Đã hiểu</button></div>');
      } else S.toast(e.svyMessage, true);
    });
  }
  function reloadMeta() {
    return S.api("get_builder", { name: B.name }).then(function (d) {
      B.data = d; B.modified = d.modified; B.prizes = d.prizes;
      drawHead(); drawTab();
    });
  }
  function simple(method, btn, okMsg, ask) {
    var go = function () {
      S.busy(btn, true);
      flush().then(function () { return S.api(method, { name: B.name }, true); }).then(function () { S.toast(okMsg); return reloadMeta(); },
        function (e) { S.busy(btn, false); S.toast(e.svyMessage, true); });
    };
    if (ask) S.confirm(ask[0], ask[1], ask[2]).then(function (ok) { if (ok) go(); }); else go();
  }

  root.addEventListener("click", function (e) {
    var t = e.target;
    var tab = t.closest("[data-tab]");
    if (tab) { flush(); B.tab = tab.getAttribute("data-tab"); history.replaceState(null, "", "?s=" + encodeURIComponent(B.name) + (B.tab !== "questions" ? "&tab=" + B.tab : "")); drawHead(); drawTab(); window.scrollTo(0, 0); return; }
    var add = t.closest("[data-pickadd]");
    if (add) {
      var kind = add.getAttribute("data-pickadd"), user = add.getAttribute("data-user"), label = add.getAttribute("data-label");
      if (kind === "editor") B.editors.push({ user: user, label: label });
      else B.targets.push({ kind: kind, user: user, label: label });
      B.changed(true);
      var again = root.querySelector('[data-pick="' + kind + '"]');
      if (again) again.focus();
      return;
    }
    var un = t.closest("[data-untag]");
    if (un) {
      var k = un.getAttribute("data-untag"), key = un.getAttribute("data-key");
      if (k === "editor") B.editors = B.editors.filter(function (x) { return x.user !== key; });
      else B.targets = B.targets.filter(function (x) { return !(x.kind === k && x.user === key); });
      B.changed(true); return;
    }
    var am = t.closest("[data-amode]");
    if (am) { setField("audience_mode", am.getAttribute("data-amode")); B.changed(true); return; }
    var rm = t.closest("[data-rmode]");
    if (rm && !rm.disabled) {
      setField("reward_mode", rm.getAttribute("data-rmode"));
      if (rm.getAttribute("data-rmode") !== "none" && !B.prizes.length) B.prizes.push({ id: "", label: "", quantity: 1, awarded: 0, color: "#f5b800" });
      B.changed(true); return;
    }
    var col = t.closest("[data-color]");
    if (col) { setField("accent_color", col.getAttribute("data-color")); B.changed(true); return; }
    if (!t.closest(".svy-pick")) S.qsa(root, ".svy-pick .list").forEach(function (l) { l.hidden = true; });
    if (B.tab === "questions" && E.onClick(e, B)) return;
    var b = t.closest("[data-act]");
    if (!b || b.disabled) return;
    var act = b.getAttribute("data-act");
    if (act === "padd") { B.prizes.push({ id: "", label: "", quantity: 1, awarded: 0, color: "" }); B.changed(true); }
    else if (act === "pdel") { B.prizes.splice(+b.getAttribute("data-i"), 1); B.changed(true); }
    else if (act === "publish") publishFlow(b);
    else if (act === "close") simple("close", b, "Đã đóng khảo sát.", ["Đóng khảo sát?", "Không ai nộp thêm được nữa. Bạn có thể mở lại sau.", "Đóng"]);
    else if (act === "reopen") simple("reopen", b, "Đã mở lại.");
    else if (act === "link") {
      var url = location.origin + "/khao-sat/lam?s=" + encodeURIComponent(B.name);
      (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(function () { S.toast("Đã sao chép: " + url); }, function () { S.toast(url); });
    } else if (act === "dup") {
      S.busy(b, true);
      flush().then(function () { return S.api("create", { source: B.name }, true); }).then(function (r) { location.href = "/khao-sat/soan?s=" + encodeURIComponent(r.name); },
        function (err) { S.busy(b, false); S.toast(err.svyMessage, true); });
    } else if (act === "del") {
      S.confirm("Xoá bản nháp?", "Không khôi phục được.", "Xoá", true).then(function (ok) {
        if (!ok) return;
        clearTimeout(B.timer); B.timer = null;
        S.api("delete", { name: B.name }, true).then(function () { location.href = "/khao-sat/quan-ly"; }, function (err) { S.toast(err.svyMessage, true); });
      });
    }
  });

  function boot() { load(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
