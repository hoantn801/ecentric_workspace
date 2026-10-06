// Copyright (c) 2026, eCentric and contributors
// ec_survey_editor.js -- tab "Câu hỏi" cua trinh soan /khao-sat/soan (kieu Google Forms):
// the dang chon mo bo soan day du, the khac hien ban xem gon; them cau hoi / khoi chu / phan
// moi; doi loai; lua chon, re nhanh theo lua chon, luoi, thang diem, dap an bai kiem tra.
//
//   ECSvyEditor.render(B)            -> HTML cua tab
//   ECSvyEditor.onInput(e, B)        -> true neu da xu ly (go chu: KHONG ve lai, giu con tro)
//   ECSvyEditor.onClick(e, B)        -> true neu da xu ly (thao tac cau truc: ve lai)
// B = trang thai trinh soan (ec_survey_builder.js): B.form, B.settings, B.active, B.changed().
(function () {
  "use strict";
  if (window.ECSvyEditor) return;
  var S = window.ECSvy, esc = S.esc;

  var TYPES = [
    ["short_text", "Trả lời ngắn"], ["paragraph", "Đoạn văn"], ["single", "Trắc nghiệm (chọn 1)"],
    ["multi", "Hộp kiểm (chọn nhiều)"], ["dropdown", "Danh sách thả xuống"], ["scale", "Thang điểm"],
    ["rating", "Đánh giá sao"], ["grid_single", "Lưới trắc nghiệm"], ["grid_multi", "Lưới hộp kiểm"],
    ["ranking", "Xếp hạng"], ["date", "Ngày"], ["time", "Giờ"], ["file", "Tải tệp lên"]
  ];
  var TYPE_LABEL = {};
  TYPES.forEach(function (t) { TYPE_LABEL[t[0]] = t[1]; });
  var OPTION_TYPES = ["single", "multi", "dropdown", "ranking"];
  var GRID_TYPES = ["grid_single", "grid_multi"];
  var QUIZ_TYPES = ["short_text", "single", "multi", "dropdown"];

  function isOpt(t) { return OPTION_TYPES.indexOf(t) >= 0; }
  function isGrid(t) { return GRID_TYPES.indexOf(t) >= 0; }
  function find(B, id) { var i = B.form.items.findIndex(function (it) { return it.id === id; }); return { i: i, it: B.form.items[i] }; }

  function newQuestion(type) {
    var q = { id: S.uid("q"), kind: "question", type: type || "single", title: "", description: "", required: false, points: 0 };
    return withDefaults(q);
  }
  function withDefaults(q) {
    if (isOpt(q.type) && !(q.options && q.options.length)) q.options = [{ id: S.uid("o"), label: "Lựa chọn 1" }];
    if (q.type === "scale") { if (q.scale_min === undefined) q.scale_min = 1; if (!q.scale_max) q.scale_max = 5; }
    if (q.type === "rating" && !q.rating_max) q.rating_max = 5;
    if (isGrid(q.type)) {
      if (!(q.rows && q.rows.length)) q.rows = [{ id: S.uid("r"), label: "Hàng 1" }];
      if (!(q.cols && q.cols.length)) q.cols = [{ id: S.uid("c"), label: "Cột 1" }];
    }
    if (q.type === "file" && !q.max_files) q.max_files = 1;
    if ((q.type === "short_text" || q.type === "paragraph") && !q.validation) q.validation = { kind: "none", min: null, max: null };
    return q;
  }

  // Phan (section) ma moi item thuoc ve -> chi cho re nhanh / chuyen phan TOI phia sau.
  function sectionsAfter(B, itemId) {
    var secs = S.sections(B.form), idx = 0;
    secs.forEach(function (s, k) {
      if ((s.sec && s.sec.id === itemId) || s.items.some(function (it) { return it.id === itemId; })) idx = k;
    });
    return secs.slice(idx + 1).filter(function (s) { return s.sec; }).map(function (s) {
      return { id: s.sec.id, label: "Phần " + (secs.indexOf(s) + 1) + (s.sec.title ? ": " + s.sec.title : "") };
    });
  }
  function gotoSelect(B, itemId, value, attr, firstLabel) {
    var h = '<select class="svy-sel" ' + attr + ">";
    h += '<option value=""' + (!value ? " selected" : "") + ">" + esc(firstLabel || "Tiếp tục phần sau") + "</option>";
    sectionsAfter(B, itemId).forEach(function (s) {
      h += '<option value="' + esc(s.id) + '"' + (value === s.id ? " selected" : "") + ">Chuyển tới " + esc(s.label) + "</option>";
    });
    h += '<option value="__submit__"' + (value === "__submit__" ? " selected" : "") + ">Gửi biểu mẫu</option>";
    return h + "</select>";
  }

  // ------------------------------------------------------------------ xem gon --
  function preview(q) {
    var h = '<div class="prev"><div class="qt">' + (q.title ? esc(q.title) : '<span class="svy-muted">Câu hỏi chưa có nội dung</span>') +
      (q.required ? ' <span style="color:var(--bad)">*</span>' : "") + "</div>";
    if (isOpt(q.type)) {
      var mk = q.type === "multi" ? "sq" : "";
      (q.options || []).slice(0, 6).forEach(function (o) { h += '<div class="opt"><i class="' + mk + '"></i>' + esc(o.label || "(trống)") + "</div>"; });
      if ((q.options || []).length > 6) h += '<div class="opt svy-small">+' + (q.options.length - 6) + " lựa chọn</div>";
      if (q.allow_other) h += '<div class="opt"><i class="' + mk + '"></i>Khác…</div>';
    } else if (q.type === "scale") h += '<div class="opt">Thang ' + q.scale_min + " → " + q.scale_max + "</div>";
    else if (q.type === "rating") h += '<div class="opt">' + q.rating_max + " sao</div>";
    else if (isGrid(q.type)) h += '<div class="opt">' + (q.rows || []).length + " hàng × " + (q.cols || []).length + " cột</div>";
    return h + "</div>";
  }

  function card(B, it, idx, total) {
    var on = B.active === it.id;
    var head = '<div class="svy-panel svy-pad svy-item' + (on ? " on" : "") + '" data-item="' + esc(it.id) + '">';
    if (it.kind === "section") {
      var no = S.sections(B.form).findIndex(function (s) { return s.sec && s.sec.id === it.id; }) + 1;
      head = '<div><div class="svy-sec" style="background:var(--navy)">Phần ' + no + "</div>" + head.replace("svy-item", "svy-item svy-sech");
    }
    var badge = "";
    if (!on) {
      badge = '<span class="badge svy-pill mute">' + (it.kind === "question" ? esc(TYPE_LABEL[it.type] || "") : it.kind === "section" ? "Phần mới" : "Tiêu đề & mô tả") + "</span>";
      if (it.kind === "question") return head + badge + preview(it) + "</div>";
      return head + badge + '<div class="prev"><div class="qt">' + (it.title ? esc(it.title) : '<span class="svy-muted">(chưa có tiêu đề)</span>') + "</div>" +
        (it.description ? '<div class="svy-small svy-muted">' + esc(it.description) + "</div>" : "") + "</div></div>" + (it.kind === "section" ? "</div>" : "");
    }
    var body = it.kind === "question" ? editor(B, it) : blockEditor(B, it);
    var foot = '<div class="svy-edfoot">' +
      (it.kind === "question" ? '<label class="svy-switch"><input type="checkbox" data-ed="required" data-id="' + esc(it.id) + '"' + (it.required ? " checked" : "") + ">Bắt buộc</label><span style=\"width:8px\"></span>" : "") +
      '<button class="svy-b ghost icon" data-act="up" data-id="' + esc(it.id) + '" title="Lên"' + (idx ? "" : " disabled") + ">" + S.icon("up") + "</button>" +
      '<button class="svy-b ghost icon" data-act="down" data-id="' + esc(it.id) + '" title="Xuống"' + (idx < total - 1 ? "" : " disabled") + ">" + S.icon("down") + "</button>" +
      '<button class="svy-b ghost icon" data-act="dup" data-id="' + esc(it.id) + '" title="Nhân bản">' + S.icon("copy") + "</button>" +
      '<button class="svy-b ghost icon danger" data-act="del" data-id="' + esc(it.id) + '" title="Xoá">' + S.icon("trash") + "</button></div>";
    return head + body + foot + "</div>" + (it.kind === "section" ? "</div>" : "");
  }

  function blockEditor(B, it) {
    var h = '<div class="svy-ed"><input class="ttl-in" data-ed="title" data-id="' + esc(it.id) + '" value="' + esc(it.title) + '" placeholder="' + (it.kind === "section" ? "Tiêu đề phần" : "Tiêu đề") + '" maxlength="300">' +
      '<textarea class="svy-ta" style="min-height:60px" data-ed="description" data-id="' + esc(it.id) + '" placeholder="Mô tả (không bắt buộc)" maxlength="3000">' + esc(it.description) + "</textarea>";
    if (it.kind === "section") h += '<div class="svy-row"><span class="svy-lbl">Sau phần này:</span>' + gotoSelect(B, it.id, it.next, 'data-ed="next" data-id="' + esc(it.id) + '" style="width:auto"') + "</div>";
    return h + "</div>";
  }

  function editor(B, q) {
    var id = esc(q.id), quiz = B.settings.is_quiz && QUIZ_TYPES.indexOf(q.type) >= 0;
    var h = '<div class="svy-ed"><div class="top"><input class="ttl-in" data-ed="title" data-id="' + id + '" value="' + esc(q.title) + '" placeholder="Câu hỏi" maxlength="300">' +
      '<select class="svy-sel" data-ed="type" data-id="' + id + '" aria-label="Loại câu hỏi">' + TYPES.map(function (t) {
        return '<option value="' + t[0] + '"' + (t[0] === q.type ? " selected" : "") + ">" + t[1] + "</option>";
      }).join("") + "</select></div>" +
      '<textarea class="svy-ta" style="min-height:44px" data-ed="description" data-id="' + id + '" placeholder="Mô tả / gợi ý cho câu hỏi (không bắt buộc)" maxlength="3000">' + esc(q.description) + "</textarea>";
    if (isOpt(q.type)) h += optionsEditor(B, q, quiz);
    else if (isGrid(q.type)) h += gridEditor(q);
    else if (q.type === "scale") {
      h += '<div class="svy-row"><select class="svy-sel" style="width:auto" data-ed="scale_min" data-id="' + id + '"><option value="0"' + (q.scale_min === 0 ? " selected" : "") + '>0</option><option value="1"' + (q.scale_min === 1 ? " selected" : "") + ">1</option></select> đến " +
        '<select class="svy-sel" style="width:auto" data-ed="scale_max" data-id="' + id + '">';
      for (var n = 2; n <= 10; n++) h += '<option value="' + n + '"' + (q.scale_max === n ? " selected" : "") + ">" + n + "</option>";
      h += '</select><span class="svy-small svy-muted">(0 → 10 = NPS)</span></div><div class="svy-form2"><input class="svy-in" data-ed="min_label" data-id="' + id + '" value="' + esc(q.min_label || "") + '" placeholder="Nhãn đầu thang (vd Rất không hài lòng)" maxlength="60">' +
        '<input class="svy-in" data-ed="max_label" data-id="' + id + '" value="' + esc(q.max_label || "") + '" placeholder="Nhãn cuối thang (vd Rất hài lòng)" maxlength="60"></div>';
    } else if (q.type === "rating") {
      h += '<div class="svy-row"><span class="svy-lbl">Số sao tối đa</span><select class="svy-sel" style="width:auto" data-ed="rating_max" data-id="' + id + '">';
      for (var r = 3; r <= 10; r++) h += '<option value="' + r + '"' + (q.rating_max === r ? " selected" : "") + ">" + r + "</option>";
      h += "</select></div>";
    } else if (q.type === "file") {
      h += '<div class="svy-row"><span class="svy-lbl">Số tệp tối đa</span><select class="svy-sel" style="width:auto" data-ed="max_files" data-id="' + id + '">';
      for (var f = 1; f <= 5; f++) h += '<option value="' + f + '"' + (q.max_files === f ? " selected" : "") + ">" + f + "</option>";
      h += "</select>" + (B.settings.anonymous ? '<span class="svy-pill bad">Khảo sát ẩn danh không dùng được câu tải tệp</span>' : '<span class="svy-small svy-muted">Tệp riêng tư, chỉ người quản lý tải về được.</span>') + "</div>";
    } else if (q.type === "short_text" || q.type === "paragraph") h += validationEditor(q, quiz);
    else h += '<div class="svy-small svy-muted">Người trả lời chọn ' + (q.type === "date" ? "ngày" : "giờ") + ".</div>";
    if (quiz) {
      h += '<div class="svy-row" style="background:var(--ok-bg);border-radius:9px;padding:8px 10px"><span class="svy-lbl">Điểm</span><input class="svy-in" type="number" min="0" max="100" style="width:80px" data-ed="points" data-id="' + id + '" value="' + (q.points || 0) + '">' +
        '<span class="svy-small svy-muted">' + (q.type === "short_text" ? "Nhập các đáp án chấp nhận, mỗi dòng một đáp án (không phân biệt hoa thường)." : "Bấm dấu ✓ cạnh lựa chọn đúng.") + "</span></div>";
      if (q.type === "short_text") h += '<textarea class="svy-ta" style="min-height:56px" data-ed="correct_text" data-id="' + id + '" placeholder="Đáp án đúng">' + esc((q.correct || []).join("\n")) + "</textarea>";
    }
    return h + "</div>";
  }

  function optionsEditor(B, q, quiz) {
    var id = esc(q.id), mk = q.type === "multi" ? "sq" : (q.type === "ranking" ? "" : "");
    var h = '<div class="svy-opts">';
    (q.options || []).forEach(function (o, i) {
      var correct = (q.correct || []).indexOf(o.id) >= 0;
      h += '<div class="svy-oe">' + (q.type === "ranking" || q.type === "dropdown" ? '<span class="svy-small svy-muted" style="width:18px;text-align:right">' + (i + 1) + ".</span>" : '<span class="mk ' + mk + '"></span>') +
        '<input class="svy-in svy-grow" data-ed="opt" data-id="' + id + '" data-i="' + i + '" value="' + esc(o.label) + '" placeholder="Lựa chọn ' + (i + 1) + '" maxlength="300">' +
        (q.branch ? gotoSelect(B, q.id, o.goto, 'data-ed="goto" data-id="' + id + '" data-i="' + i + '"', "Tiếp tục") : "") +
        (quiz ? '<button class="svy-b icon sm' + (correct ? " ok" : "") + '" data-act="correct" data-id="' + id + '" data-i="' + i + '" title="Đánh dấu đáp án đúng">' + S.icon("check") + "</button>" : "") +
        '<button class="svy-b ghost icon" data-act="optup" data-id="' + id + '" data-i="' + i + '" title="Lên"' + (i ? "" : " disabled") + ">" + S.icon("up") + "</button>" +
        '<button class="svy-b ghost icon" data-act="optdel" data-id="' + id + '" data-i="' + i + '" title="Xoá lựa chọn"' + (q.options.length > 1 ? "" : " disabled") + ">" + S.icon("x") + "</button></div>";
    });
    if (q.allow_other) h += '<div class="svy-oe"><span class="mk ' + mk + '"></span><span class="svy-in svy-grow svy-muted" style="display:flex;align-items:center">Khác: (người trả lời tự nhập)</span><button class="svy-b ghost icon" data-act="otherdel" data-id="' + id + '" title="Bỏ Khác">' + S.icon("x") + "</button></div>";
    h += '</div><div class="svy-row"><button class="svy-b sm" data-act="optadd" data-id="' + id + '">' + S.icon("plus") + "Thêm lựa chọn</button>" +
      (!q.allow_other && (q.type === "single" || q.type === "multi") ? '<button class="svy-b sm ghost" data-act="otheradd" data-id="' + id + '">Thêm "Khác"</button>' : "") +
      '<button class="svy-b sm ghost" data-act="bulk" data-id="' + id + '">Dán nhiều lựa chọn</button></div>';
    h += '<div class="svy-row" style="gap:16px">';
    if (q.type !== "ranking") h += '<label class="svy-switch"><input type="checkbox" data-ed="shuffle" data-id="' + id + '"' + (q.shuffle ? " checked" : "") + ">Xáo thứ tự lựa chọn</label>";
    else h += '<label class="svy-switch"><input type="checkbox" data-ed="shuffle" data-id="' + id + '"' + (q.shuffle ? " checked" : "") + ">Xáo thứ tự ban đầu</label>";
    if (q.type === "single" || q.type === "dropdown") h += '<label class="svy-switch"><input type="checkbox" data-ed="branch" data-id="' + id + '"' + (q.branch ? " checked" : "") + ">Chuyển tới phần theo câu trả lời</label>";
    if (q.type === "multi") {
      h += '<span class="svy-row"><span class="svy-small">Chọn tối thiểu</span><input class="svy-in" type="number" min="0" style="width:64px;min-height:32px" data-ed="min_select" data-id="' + id + '" value="' + (q.min_select || 0) + '">' +
        '<span class="svy-small">tối đa</span><input class="svy-in" type="number" min="0" style="width:64px;min-height:32px" data-ed="max_select" data-id="' + id + '" value="' + (q.max_select || 0) + '"><span class="svy-small svy-muted">(0 = không giới hạn)</span></span>';
    }
    h += "</div>";
    if (q.branch && !sectionsAfter(B, q.id).length) h += '<div class="svy-small" style="color:var(--warn)">Chưa có phần nào nằm sau câu này - thêm "Phần mới" để rẽ nhánh.</div>';
    else if ((q.type === "single" || q.type === "dropdown") && !q.branch) h += '<div class="svy-small svy-muted">Muốn chọn phương án X thì chuyển tới phần Y: thêm "Phần mới" bên dưới, rồi bật "Chuyển tới phần theo câu trả lời" và chọn phần cho từng phương án.</div>';
    return h;
  }

  function gridEditor(q) {
    var id = esc(q.id);
    function list(key, title) {
      var h = '<div class="svy-field"><span class="svy-lbl">' + title + '</span><div class="svy-opts">';
      (q[key] || []).forEach(function (r, i) {
        h += '<div class="svy-oe"><span class="svy-small svy-muted" style="width:18px;text-align:right">' + (i + 1) + '.</span><input class="svy-in svy-grow" data-ed="' + key + '" data-id="' + id + '" data-i="' + i + '" value="' + esc(r.label) + '" maxlength="300">' +
          '<button class="svy-b ghost icon" data-act="griddel" data-k="' + key + '" data-id="' + id + '" data-i="' + i + '"' + (q[key].length > 1 ? "" : " disabled") + ">" + S.icon("x") + "</button></div>";
      });
      return h + '</div><button class="svy-b sm" style="align-self:flex-start" data-act="gridadd" data-k="' + key + '" data-id="' + id + '">' + S.icon("plus") + (key === "rows" ? "Thêm hàng" : "Thêm cột") + "</button></div>";
    }
    return '<div class="svy-form2">' + list("rows", "Hàng (tiêu chí)") + list("cols", "Cột (mức đánh giá)") + '</div><label class="svy-switch"><input type="checkbox" data-ed="require_each_row" data-id="' + id + '"' + (q.require_each_row ? " checked" : "") + ">Bắt buộc trả lời mọi hàng (khi câu hỏi bắt buộc)</label>";
  }

  function validationEditor(q) {
    var v = q.validation || { kind: "none" }, id = esc(q.id);
    var kinds = q.type === "paragraph" ? [["none", "Không kiểm tra"], ["length", "Độ dài"]] :
      [["none", "Không kiểm tra"], ["number", "Là số"], ["email", "Là email"], ["phone", "Là số điện thoại"], ["length", "Độ dài"]];
    var h = '<div class="svy-row"><span class="svy-lbl">Kiểm tra câu trả lời</span><select class="svy-sel" style="width:auto" data-ed="vkind" data-id="' + id + '">' +
      kinds.map(function (k) { return '<option value="' + k[0] + '"' + (v.kind === k[0] ? " selected" : "") + ">" + k[1] + "</option>"; }).join("") + "</select>";
    if (v.kind === "number" || v.kind === "length") {
      var unit = v.kind === "length" ? " ký tự" : "";
      h += '<span class="svy-small">từ</span><input class="svy-in" type="number" style="width:90px;min-height:34px" data-ed="vmin" data-id="' + id + '" value="' + (v.min == null ? "" : v.min) + '" placeholder="—">' +
        '<span class="svy-small">đến</span><input class="svy-in" type="number" style="width:90px;min-height:34px" data-ed="vmax" data-id="' + id + '" value="' + (v.max == null ? "" : v.max) + '" placeholder="—"><span class="svy-small svy-muted">' + unit + "</span>";
    }
    return h + "</div>";
  }

  // ------------------------------------------------------------------- ca tab --
  function render(B) {
    var items = B.form.items, h = '<div class="svy-items">';
    h += '<div class="svy-panel svy-pad svy-fhead" style="--accent:' + esc(B.settings.accent_color || "#2C3DA6") + '"><div class="svy-ed">' +
      '<input class="ttl-in" style="font-size:22px;font-weight:700" data-set="title" value="' + esc(B.settings.title) + '" placeholder="Tiêu đề khảo sát" maxlength="200">' +
      '<textarea class="svy-ta" style="min-height:60px" data-set="description" placeholder="Mô tả khảo sát: mục đích, ai cần làm, mất bao lâu..." maxlength="3000">' + esc(B.settings.description || "") + "</textarea></div></div>";
    if (B.data.stats.responses && B.data.status !== "Draft") h += '<div class="svy-banner warn">' + S.icon("bell") + "<div>Đã có <b>" + B.data.stats.responses + "</b> phiếu trả lời. Sửa nội dung thì phiếu cũ vẫn giữ; đổi loại câu hỏi hoặc xoá lựa chọn có thể làm phiếu cũ không khớp.</div></div>";
    if (B.data.status === "Closed") h += '<div class="svy-banner bad">' + S.icon("lock") + "<div>Khảo sát đã đóng - mở lại để sửa câu hỏi.</div></div>";
    items.forEach(function (it, i) { h += card(B, it, i, items.length); });
    if (!items.length) h += '<div class="svy-panel svy-empty"><b>Chưa có câu hỏi</b>Bấm "Câu hỏi" bên dưới để thêm.</div>';
    h += '</div><div class="svy-addbar"><div class="box"><button class="svy-b pri sm" data-act="add" data-kind="question">' + S.icon("plus") + "Câu hỏi</button>" +
      '<button class="svy-b sm" data-act="add" data-kind="note">' + S.icon("text") + "Tiêu đề & mô tả</button>" +
      '<button class="svy-b sm" data-act="add" data-kind="section">' + S.icon("section") + "Phần mới</button></div></div>";
    return h;
  }

  function num(v, d) { var n = parseInt(v, 10); return isNaN(n) ? d : n; }

  function onInput(e, B) {
    var t = e.target, ed = t.getAttribute("data-ed"), set = t.getAttribute("data-set");
    if (set) { B.settings[set] = t.value; B.changed(false); return true; }
    if (!ed) return false;
    var f = find(B, t.getAttribute("data-id")), it = f.it;
    if (!it) return true;
    var i = num(t.getAttribute("data-i"), -1), structural = false;
    switch (ed) {
      case "title": case "description": case "min_label": case "max_label": it[ed] = t.value; break;
      case "opt": it.options[i].label = t.value; break;
      case "rows": case "cols": it[ed][i].label = t.value; break;
      case "correct_text": it.correct = t.value.split("\n").map(function (x) { return x.trim(); }).filter(Boolean); break;
      case "points": it.points = Math.max(0, Math.min(100, num(t.value, 0))); break;
      case "min_select": case "max_select": it[ed] = Math.max(0, num(t.value, 0)); break;
      case "vmin": case "vmax": it.validation[ed === "vmin" ? "min" : "max"] = t.value === "" ? null : Number(t.value); break;
      default:
        if (e.type !== "change") return true;
        structural = true;
        if (ed === "type") {
          var keep = { id: it.id, kind: "question", type: t.value, title: it.title, description: it.description, required: it.required, points: it.points };
          if (isOpt(t.value) && it.options) keep.options = it.options.map(function (o) { return { id: o.id, label: o.label }; });
          B.form.items[f.i] = withDefaults(keep);
        } else if (ed === "required" || ed === "shuffle" || ed === "branch" || ed === "require_each_row") it[ed] = t.checked;
        else if (ed === "scale_min" || ed === "scale_max" || ed === "rating_max" || ed === "max_files") it[ed] = num(t.value, 1);
        else if (ed === "goto") it.options[i].goto = t.value;
        else if (ed === "next") it.next = t.value;
        else if (ed === "vkind") it.validation = { kind: t.value, min: null, max: null };
    }
    B.changed(structural);
    return true;
  }

  function onClick(e, B) {
    var b = e.target.closest("[data-act]"), cardEl = e.target.closest("[data-item]");
    if (!b) {
      if (cardEl && B.active !== cardEl.getAttribute("data-item")) { B.active = cardEl.getAttribute("data-item"); B.redraw(); return true; }
      return false;
    }
    var act = b.getAttribute("data-act"), id = b.getAttribute("data-id"), f = id ? find(B, id) : null, it = f && f.it, i = num(b.getAttribute("data-i"), -1);
    var items = B.form.items;
    if (act === "add") {
      var kind = b.getAttribute("data-kind");
      var neu = kind === "question" ? newQuestion("single") : { id: S.uid(kind === "section" ? "s" : "n"), kind: kind, title: "", description: "", next: "" };
      var at = B.active ? find(B, B.active).i + 1 : items.length;
      if (at <= 0) at = items.length;
      items.splice(at, 0, neu);
      B.active = neu.id;
      B.changed(true);
      setTimeout(function () { var el = document.querySelector('[data-item="' + neu.id + '"] .ttl-in'); if (el) { el.focus(); el.scrollIntoView({ block: "center", behavior: "smooth" }); } }, 30);
      return true;
    }
    if (!it) return false;
    if (act === "up" || act === "down") {
      var j = f.i + (act === "up" ? -1 : 1);
      if (j < 0 || j >= items.length) return true;
      items.splice(j, 0, items.splice(f.i, 1)[0]);
    } else if (act === "dup") {
      var copy = S.clone(it);
      copy.id = S.uid(it.kind === "question" ? "q" : "s");
      (copy.options || []).forEach(function (o) { o.id = S.uid("o"); });
      copy.correct = [];
      items.splice(f.i + 1, 0, copy);
      B.active = copy.id;
    } else if (act === "del") {
      items.splice(f.i, 1);
      B.active = (items[f.i] || items[f.i - 1] || {}).id || null;
    } else if (act === "optadd") it.options.push({ id: S.uid("o"), label: "Lựa chọn " + (it.options.length + 1) });
    else if (act === "optdel") { var gone = it.options.splice(i, 1)[0]; it.correct = (it.correct || []).filter(function (x) { return x !== gone.id; }); }
    else if (act === "optup" && i > 0) it.options.splice(i - 1, 0, it.options.splice(i, 1)[0]);
    else if (act === "otheradd") it.allow_other = true;
    else if (act === "otherdel") it.allow_other = false;
    else if (act === "correct") {
      var oid = it.options[i].id, cur = it.correct || [];
      if (it.type === "multi") it.correct = cur.indexOf(oid) >= 0 ? cur.filter(function (x) { return x !== oid; }) : cur.concat([oid]);
      else it.correct = cur[0] === oid ? [] : [oid];
    } else if (act === "gridadd") { var k = b.getAttribute("data-k"); it[k].push({ id: S.uid(k[0]), label: (k === "rows" ? "Hàng " : "Cột ") + (it[k].length + 1) }); }
    else if (act === "griddel") it[b.getAttribute("data-k")].splice(i, 1);
    else if (act === "bulk") { bulkOptions(B, it); return true; }
    else return false;
    B.changed(true);
    return true;
  }

  function bulkOptions(B, it) {
    var m = S.modal('<h3>Dán nhiều lựa chọn</h3><div class="svy-small svy-muted">Mỗi dòng một lựa chọn. Các lựa chọn hiện có sẽ được thay thế.</div><textarea class="svy-ta" style="min-height:180px" id="svy-bulk">' +
      esc((it.options || []).map(function (o) { return o.label; }).join("\n")) + '</textarea><div class="svy-row" style="justify-content:flex-end"><button class="svy-b" data-close>Huỷ</button><button class="svy-b pri" data-ok>Áp dụng</button></div>');
    m.box.querySelector("[data-ok]").addEventListener("click", function () {
      var lines = S.byId("svy-bulk").value.split("\n").map(function (x) { return x.trim(); }).filter(Boolean).slice(0, 60);
      if (!lines.length) return;
      var old = {};
      (it.options || []).forEach(function (o) { old[o.label] = o.id; });
      it.options = lines.map(function (l) { return { id: old[l] || S.uid("o"), label: l }; });
      it.correct = (it.correct || []).filter(function (x) { return it.options.some(function (o) { return o.id === x; }); });
      m.close();
      B.changed(true);
    });
  }

  window.ECSvyEditor = { render: render, onInput: onInput, onClick: onClick, TYPE_LABEL: TYPE_LABEL };
})();
