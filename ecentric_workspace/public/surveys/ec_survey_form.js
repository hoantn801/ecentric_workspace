// Copyright (c) 2026, eCentric and contributors
// ec_survey_form.js -- ve MOT cau hoi de tra loi + doc thao tac cua nguoi dung vao `answers`.
// Dung cho trang /khao-sat/lam (ca che do xem truoc cua nguoi soan).
//
//   ECSvyForm.question(q, value, {err, readonly, rnd, number})  -> chuoi HTML cua the cau hoi
//   ECSvyForm.bind(root, getState, onChange)                    -> gan su kien (uy quyen) mot lan
//
// Dinh dang `value` theo tung loai: xem docstring surveys/domain/answers.py.
(function () {
  "use strict";
  if (window.ECSvyForm) return;
  var S = window.ECSvy, esc = S.esc;
  var OTHER = "__other__";

  function optOrder(q, rnd) {
    var opts = q.options || [];
    return q.shuffle && rnd ? S.shuffle(opts, rnd) : opts;
  }
  function attrs(q, extra) { return 'data-q="' + esc(q.id) + '" ' + (extra || ""); }

  function choice(q, v, ro, rnd) {
    var multi = q.type === "multi";
    var sel = S.selected(v);
    var other = v && typeof v === "object" && typeof v.other === "string";
    var type = multi ? "checkbox" : "radio";
    var h = '<div class="svy-opts" role="' + (multi ? "group" : "radiogroup") + '">';
    optOrder(q, rnd).forEach(function (o) {
      var on = sel.indexOf(o.id) >= 0;
      h += '<label class="svy-opt' + (on ? " on" : "") + '"><input type="' + type + '" name="q_' + esc(q.id) + '" value="' + esc(o.id) + '" ' +
        attrs(q, 'data-a="' + (multi ? "selm" : "sel1") + '"') + (on ? " checked" : "") + (ro ? " disabled" : "") + "><span>" + esc(o.label) + "</span></label>";
    });
    if (q.allow_other) {
      h += '<label class="svy-opt' + (other ? " on" : "") + '"><input type="' + type + '" name="q_' + esc(q.id) + '" value="' + OTHER + '" ' +
        attrs(q, 'data-a="' + (multi ? "selm" : "sel1") + '"') + (other ? " checked" : "") + (ro ? " disabled" : "") + '><span>Khác:</span>' +
        '<input class="svy-in line svy-grow" type="text" maxlength="500" ' + attrs(q, 'data-a="other"') + ' value="' + esc(other ? v.other : "") + '"' +
        (ro ? " disabled" : "") + ' aria-label="Lựa chọn khác"></label>';
    }
    return h + "</div>";
  }

  function dropdown(q, v, ro, rnd) {
    var sel = S.selected(v)[0] || "";
    var h = '<select class="svy-sel" style="max-width:420px" ' + attrs(q, 'data-a="drop"') + (ro ? " disabled" : "") + '><option value="">Chọn</option>';
    optOrder(q, rnd).forEach(function (o) {
      h += '<option value="' + esc(o.id) + '"' + (o.id === sel ? " selected" : "") + ">" + esc(o.label) + "</option>";
    });
    return h + "</select>";
  }

  function scale(q, v, ro) {
    var h = '<div class="svy-scale">';
    if (q.min_label) h += '<span class="lab">' + esc(q.min_label) + "</span>";
    h += '<div class="nums" role="radiogroup">';
    for (var n = q.scale_min; n <= q.scale_max; n++) {
      h += '<button type="button" class="svy-num' + (v === n ? " on" : "") + '" ' + attrs(q, 'data-a="num" data-v="' + n + '"') +
        ' role="radio" aria-checked="' + (v === n) + '"' + (ro ? " disabled" : "") + ">" + n + "</button>";
    }
    h += "</div>";
    if (q.max_label) h += '<span class="lab">' + esc(q.max_label) + "</span>";
    return h + "</div>";
  }

  function rating(q, v, ro) {
    var h = '<div class="svy-stars" role="radiogroup">';
    for (var n = 1; n <= q.rating_max; n++) {
      h += '<button type="button" class="svy-star' + (v >= n ? " on" : "") + '" ' + attrs(q, 'data-a="num" data-v="' + n + '"') +
        ' aria-label="' + n + ' sao"' + (ro ? " disabled" : "") + '><svg viewBox="0 0 24 24"><path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4 6.1 20.5l1.2-6.5L2.5 9.4l6.6-.9z"/></svg></button>';
    }
    return h + "</div>";
  }

  function grid(q, v, ro) {
    var multi = q.type === "grid_multi";
    v = v && typeof v === "object" ? v : {};
    var h = '<div class="svy-grid"><table><thead><tr><th></th>';
    (q.cols || []).forEach(function (c) { h += "<th>" + esc(c.label) + "</th>"; });
    h += "</tr></thead><tbody>";
    (q.rows || []).forEach(function (r) {
      h += '<tr><td class="rl">' + esc(r.label) + "</td>";
      (q.cols || []).forEach(function (c) {
        var cur = v[r.id];
        var on = multi ? (Array.isArray(cur) && cur.indexOf(c.id) >= 0) : cur === c.id;
        h += '<td><input type="' + (multi ? "checkbox" : "radio") + '" name="g_' + esc(q.id) + "_" + esc(r.id) + '" ' +
          attrs(q, 'data-a="' + (multi ? "gm" : "g1") + '" data-r="' + esc(r.id) + '" data-c="' + esc(c.id) + '"') +
          ' aria-label="' + esc(r.label + ": " + c.label) + '"' + (on ? " checked" : "") + (ro ? " disabled" : "") + "></td>";
      });
      h += "</tr>";
    });
    return h + "</tbody></table></div>";
  }

  function ranking(q, v, ro) {
    var labels = {};
    (q.options || []).forEach(function (o) { labels[o.id] = o.label; });
    var order = Array.isArray(v) && v.length ? v : (q.options || []).map(function (o) { return o.id; });
    var h = '<div class="svy-rank">';
    order.forEach(function (id, i) {
      h += '<div class="it"><span class="pos">' + (i + 1) + '</span><span class="svy-grow">' + esc(labels[id] || "") + "</span>" +
        '<button type="button" class="svy-b ghost icon" ' + attrs(q, 'data-a="rk" data-i="' + i + '" data-d="-1"') + ' aria-label="Lên"' + (ro || !i ? " disabled" : "") + ">" + S.icon("up") + "</button>" +
        '<button type="button" class="svy-b ghost icon" ' + attrs(q, 'data-a="rk" data-i="' + i + '" data-d="1"') + ' aria-label="Xuống"' + (ro || i === order.length - 1 ? " disabled" : "") + ">" + S.icon("down") + "</button></div>";
    });
    return h + "</div>" + (Array.isArray(v) && v.length ? "" : '<div class="svy-small svy-muted" style="margin-top:6px">Dùng mũi tên để xếp thứ tự - mục trên cùng là ưu tiên nhất.</div>');
  }

  function files(q, v, ro) {
    var list = Array.isArray(v) ? v : [];
    var h = "";
    if (!ro && list.length < (q.max_files || 1)) {
      h += '<label class="svy-b sm" style="cursor:pointer">' + S.icon("upload") + "Tải tệp lên" +
        '<input type="file" hidden ' + attrs(q, 'data-a="file"') + "></label>";
    }
    if (list.length) {
      h += '<div class="svy-files">';
      list.forEach(function (f, i) {
        h += '<div class="svy-file">' + S.icon("link") + '<span class="svy-grow">' + esc(f.name) + "</span>" +
          (ro ? "" : '<button type="button" class="svy-b ghost icon" ' + attrs(q, 'data-a="frm" data-i="' + i + '"') + ' aria-label="Bỏ tệp">' + S.icon("x") + "</button>") + "</div>";
      });
      h += "</div>";
    }
    return h + '<div class="svy-small svy-muted" style="margin-top:6px">Tối đa ' + (q.max_files || 1) + " tệp. Chỉ người quản lý khảo sát xem được tệp.</div>";
  }

  function textInput(q, v, ro) {
    var val = typeof v === "string" ? v : "";
    var kind = (q.validation || {}).kind;
    if (q.type === "paragraph") {
      return '<textarea class="svy-ta" maxlength="5000" ' + attrs(q, 'data-a="text"') + (ro ? " disabled" : "") + ' placeholder="Câu trả lời của bạn">' + esc(val) + "</textarea>";
    }
    var type = q.type === "date" ? "date" : q.type === "time" ? "time" : kind === "email" ? "email" : kind === "phone" ? "tel" : "text";
    var mode = kind === "number" ? ' inputmode="decimal"' : "";
    return '<input class="svy-in' + (q.type === "short_text" ? " line" : "") + '" style="max-width:' + (q.type === "short_text" ? "520px" : "220px") + '" type="' + type + '"' + mode +
      ' maxlength="500" ' + attrs(q, 'data-a="text"') + ' value="' + esc(val) + '"' + (ro ? " disabled" : "") + (q.type === "short_text" ? ' placeholder="Câu trả lời của bạn"' : "") + ">";
  }

  function body(q, v, ro, rnd) {
    switch (q.type) {
      case "single": case "multi": return choice(q, v, ro, rnd);
      case "dropdown": return dropdown(q, v, ro, rnd);
      case "scale": return scale(q, v, ro);
      case "rating": return rating(q, v, ro);
      case "grid_single": case "grid_multi": return grid(q, v, ro);
      case "ranking": return ranking(q, v, ro);
      case "file": return files(q, v, ro);
      default: return textInput(q, v, ro);
    }
  }

  function hint(q) {
    if (q.type === "multi" && (q.min_select || q.max_select)) {
      if (q.min_select && q.max_select) return q.min_select === q.max_select ? "Chọn đúng " + q.min_select + " mục." : "Chọn từ " + q.min_select + " đến " + q.max_select + " mục.";
      return q.min_select ? "Chọn ít nhất " + q.min_select + " mục." : "Chọn tối đa " + q.max_select + " mục.";
    }
    return "";
  }

  function question(q, value, opts) {
    opts = opts || {};
    var h = '<section class="svy-panel svy-pad svy-q' + (opts.err ? " err" : "") + '" id="q-' + esc(q.id) + '" data-qcard="' + esc(q.id) + '">';
    if (q.points && opts.quiz) h += '<span class="pts">' + q.points + " điểm</span>";
    h += '<div class="qt">' + esc(q.title || "Câu hỏi") + (q.required ? '<span class="req" aria-label="bắt buộc">*</span>' : "") + "</div>";
    var hn = hint(q);
    if (q.description || hn) h += '<div class="qd">' + esc([q.description, hn].filter(Boolean).join("\n")) + "</div>";
    h += '<div class="qbody">' + body(q, value, opts.readonly, opts.rnd) + "</div>";
    if (opts.err) h += '<div class="qerr" role="alert">' + S.icon("x") + esc(opts.err) + "</div>";
    if (opts.verdict !== undefined) {
      h += '<div class="qerr" style="color:' + (opts.verdict ? "var(--ok)" : "var(--bad)") + '">' + S.icon(opts.verdict ? "check" : "x") + (opts.verdict ? "Đúng" : "Chưa đúng") + "</div>";
    }
    return h + "</section>";
  }

  // ------------------------------------------------------------------ doc thao tac --
  function bind(root, getState, onChange) {
    function q(id) { return getState().qmap[id]; }
    function set(id, v, rerender) { getState().answers[id] = v; onChange(id, rerender); }

    root.addEventListener("change", function (e) {
      var t = e.target, id = t.getAttribute("data-q"), a = t.getAttribute("data-a");
      if (!id || !a) return;
      var st = getState(), cur = st.answers[id];
      if (a === "sel1") {
        set(id, t.value === OTHER ? { sel: [], other: (cur && cur.other) || "" } : { sel: [t.value] }, true);
      } else if (a === "selm") {
        var v = cur && typeof cur === "object" ? S.clone(cur) : { sel: [] };
        v.sel = v.sel || [];
        if (t.value === OTHER) { if (t.checked) v.other = v.other || ""; else delete v.other; }
        else if (t.checked) { if (v.sel.indexOf(t.value) < 0) v.sel.push(t.value); }
        else v.sel = v.sel.filter(function (x) { return x !== t.value; });
        set(id, v, true);
      } else if (a === "drop") {
        set(id, t.value ? { sel: [t.value] } : null, false);
      } else if (a === "g1" || a === "gm") {
        var g = cur && typeof cur === "object" ? S.clone(cur) : {};
        var r = t.getAttribute("data-r"), c = t.getAttribute("data-c");
        if (a === "g1") g[r] = c;
        else {
          var arr = Array.isArray(g[r]) ? g[r] : [];
          arr = t.checked ? arr.concat([c]) : arr.filter(function (x) { return x !== c; });
          if (arr.length) g[r] = arr; else delete g[r];
        }
        set(id, g, false);
      } else if (a === "file" && t.files && t.files[0]) {
        var file = t.files[0];
        t.value = "";
        S.toast("Đang tải " + file.name + "...");
        S.uploadFile(file).then(function (f) {
          var list = Array.isArray(getState().answers[id]) ? getState().answers[id].slice() : [];
          list.push(f);
          set(id, list, true);
          S.toast("Đã tải lên " + f.name);
        }, function (err) { S.toast(err.svyMessage || "Không tải được tệp.", true); });
      } else if (a === "text") {
        set(id, t.value, false);
      }
    });
    root.addEventListener("input", function (e) {
      var t = e.target, id = t.getAttribute("data-q"), a = t.getAttribute("data-a");
      if (!id) return;
      if (a === "text") set(id, t.value, false);
      else if (a === "other") {
        var st = getState(), cur = st.answers[id];
        var v = cur && typeof cur === "object" ? S.clone(cur) : { sel: [] };
        v.other = t.value;
        if (q(id).type !== "multi") v.sel = [];
        set(id, v, false);
        var radio = t.closest(".svy-opt").querySelector("input[type=radio],input[type=checkbox]");
        if (radio && !radio.checked) { radio.checked = true; }
      }
    });
    root.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-a]");
      if (!b || b.disabled) return;
      var id = b.getAttribute("data-q"), a = b.getAttribute("data-a");
      var st = getState();
      if (a === "num") {
        var n = parseInt(b.getAttribute("data-v"), 10);
        set(id, st.answers[id] === n && q(id).type === "rating" ? null : n, true);
      } else if (a === "rk") {
        var qq = q(id), order = Array.isArray(st.answers[id]) && st.answers[id].length ? st.answers[id].slice() : (qq.options || []).map(function (o) { return o.id; });
        var i = parseInt(b.getAttribute("data-i"), 10), d = parseInt(b.getAttribute("data-d"), 10), j = i + d;
        if (j < 0 || j >= order.length) return;
        var tmp = order[i]; order[i] = order[j]; order[j] = tmp;
        set(id, order, true);
      } else if (a === "frm") {
        var list = (st.answers[id] || []).slice();
        list.splice(parseInt(b.getAttribute("data-i"), 10), 1);
        set(id, list.length ? list : null, true);
      }
    });
  }

  window.ECSvyForm = { question: question, bind: bind, OTHER: OTHER };
})();
