// Copyright (c) 2026, eCentric and contributors
// /quiz/soan[?q=<bo quiz>|?t=<mau>] -- trinh soan bo quiz (Ban dao tao / HR).
// Chi giu ban nhap tren trang; server chuan hoa + kiem tung cau khi luu (dao_tao/domain/questions.py)
// va SINH LAI id lua chon moi lan luu (id khong lo thu tu dap an) -> luu xong nap lai tu server.
(function () {
  "use strict";
  var D = window.ECDt;
  var root = D.byId("dt-root");
  var quiz = null, meta = null, cur = 0, errs = {}, seq = 0, dirty = false;
  var GUARDS = [
    { k: "basic", t: "Cơ bản", d: "Đáp án chỉ nằm trên server · đăng nhập tài khoản eCentric · server bấm giờ, mỗi câu trả lời 1 lần." },
    { k: "standard", t: "Chuẩn (khuyên dùng)", d: "Thêm: xáo thứ tự đáp án từng người · 1 người 1 thiết bị · gắn cờ trả lời nhanh bất thường · chặn trình duyệt điều khiển tự động." },
    { k: "strict", t: "Nghiêm", d: "Thêm: xáo câu, chặn copy, ghi nhận rời màn hình. Không hợp luật “được hỏi AI” - chỉ dùng cho bài kiểm tra bắt buộc." }
  ];
  function tmp() { return "n" + (++seq); }

  function norm(q) {
    q = D.clone(q);
    ["options", "items"].forEach(function (k) { (q[k] || []).forEach(function (o) { if (!o.id) o.id = tmp(); }); });
    (q.pairs || []).forEach(function (p) { if (!p.id) p.id = tmp(); });
    if (q.options && q.type !== "truefalse") {
      q.correct = (q.correct || []).map(function (c) { return typeof c === "number" ? (q.options[c] || {}).id : c; }).filter(Boolean);
    }
    if (q.type === "truefalse") q.correct = [(q.correct === true || (q.correct || [])[0] === "t") ? "t" : ((q.correct === false || (q.correct || [])[0] === "f") ? "f" : "")];
    q.time = q.time || 20;
    return q;
  }
  function blank(type) {
    var q = { type: type || "single", text: "", time: meta.time_default, media: null, explain: "" };
    if (["single", "multi", "poll"].indexOf(q.type) >= 0) { q.options = [0, 1, 2, 3].map(function () { return { id: tmp(), text: "" }; }); q.correct = []; }
    if (q.type === "truefalse") q.correct = ["t"];
    if (q.type === "slider") { q.min = 0; q.max = 100; q.step = 1; q.answer = 50; q.tolerance = 0; q.unit = ""; }
    if (q.type === "pin") q.zone = { shape: "rect", x: 0.4, y: 0.4, w: 0.2, h: 0.2 };
    if (q.type === "order") q.items = [0, 1, 2, 3].map(function () { return { id: tmp(), text: "" }; });
    if (q.type === "match") q.pairs = [0, 1, 2].map(function () { return { id: tmp(), left: "", right: "" }; });
    if (q.type === "type") q.accept = [""];
    return q;
  }
  function changeType(q, type) {
    var n = blank(type);
    n.text = q.text; n.time = q.time; n.media = q.media; n.explain = q.explain;
    if (q.options && n.options && type !== "truefalse") { n.options = q.options; n.correct = type === "poll" ? [] : (type === "single" ? (q.correct || []).slice(0, 1) : q.correct || []); }
    return n;
  }

  function load() {
    var name = D.param("q");
    D.api("quiz_get", name ? { name: name } : { template: D.param("t") || "" }).then(function (d) {
      meta = d.meta; quiz = d.quiz; quiz.questions = (quiz.questions || []).map(norm);
      if (!quiz.questions.length) quiz.questions.push(blank("single"));
      render();
    }, function (e) { root.innerHTML = '<div class="dt-wrap"><p class="dt-err">' + D.esc(D.msg(e)) + "</p></div>"; });
  }
  window.addEventListener("beforeunload", function (e) { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

  function render() {
    var h = '<div class="dt-wrap"><div class="dt-row"><a class="dt-b ghost" href="/quiz">' + D.icon("back") + ' Quiz</a><span class="dt-sp"></span>' +
      '<label class="dt-b">' + D.icon("upload") + ' Nhập Excel (Kahoot / Wayground)<input type="file" id="dt-imp" accept=".xlsx" hidden></label>' +
      '<button class="dt-b" id="dt-draft">Lưu nháp</button><button class="dt-b pri" id="dt-ready">' + D.icon("check") + " Lưu & sẵn sàng</button></div>" +
      '<div class="dt-panel dt-pad" style="display:grid;gap:10px"><div class="dt-f"><label for="dt-title">Tên bộ quiz</label><input class="dt-in' + (errs.title ? " bad" : "") +
      '" id="dt-title" maxlength="140" value="' + D.esc(quiz.title) + '" placeholder="Vd: Claude buổi 1 · Quiz sau buổi học">' + (errs.title ? '<span class="dt-ferr">' + D.esc(errs.title) + "</span>" : "") +
      '</div><div class="dt-f"><label for="dt-desc">Mô tả (không bắt buộc)</label><input class="dt-in" id="dt-desc" maxlength="500" value="' + D.esc(quiz.description) + '"></div>' +
      (!quiz.name ? '<div class="dt-row"><span class="dt-lbl">Mẫu nhanh</span><div class="dt-seg">' + meta.templates.map(function (t) {
        return '<button data-tpl="' + t.key + '" aria-pressed="' + (quiz.template === t.key) + '">' + D.esc(t.label) + "</button>"; }).join("") + "</div></div>" : "") +
      '</div><div class="dt-ed"><div class="dt-qnav" id="dt-qnav"></div><div id="dt-qed"></div></div>' +
      '<div class="dt-panel dt-pad" id="dt-rules"></div><div class="dt-panel dt-pad" id="dt-guard"></div><div class="dt-panel dt-pad" id="dt-prizes"></div></div>';
    root.innerHTML = h;
    D.byId("dt-title").oninput = function () { quiz.title = this.value; dirty = true; };
    D.byId("dt-desc").oninput = function () { quiz.description = this.value; dirty = true; };
    D.qsa(root, "[data-tpl]").forEach(function (b) {
      b.onclick = function () { D.api("quiz_get", { template: b.dataset.tpl }).then(function (d) { quiz.template = d.quiz.template; quiz.settings = d.quiz.settings; render(); }); };
    });
    D.byId("dt-draft").onclick = function () { save("Draft", this); };
    D.byId("dt-ready").onclick = function () { save("Ready", this); };
    D.byId("dt-imp").onchange = function () { importFile(this.files[0]); this.value = ""; };
    drawNav(); drawQ(); drawRules(); drawGuard(); drawPrizes();
  }

  // ------------------------------------------------------------------ danh sach cau --
  function label(t) { var x = meta.types.filter(function (y) { return y.type === t; })[0]; return x ? x.label : t; }
  function drawNav() {
    var box = D.byId("dt-qnav");
    box.innerHTML = quiz.questions.map(function (q, i) {
      return '<button data-i="' + i + '" aria-current="' + (i === cur) + '" class="' + (errs["q" + (i + 1)] ? "bad" : "") + '"><span class="dt-n">' + (i + 1) +
        '</span><span style="min-width:0"><span class="dt-small dt-muted">' + D.esc(label(q.type)) + " · " + q.time + "s</span><br>" + D.esc((q.text || "(chưa có câu hỏi)").slice(0, 60)) + "</span></button>";
    }).join("") + '<button id="dt-add" style="justify-content:center">' + D.icon("plus") + " Thêm câu</button>";
    D.qsa(box, "[data-i]").forEach(function (b) { b.onclick = function () { cur = +b.dataset.i; drawNav(); drawQ(); }; });
    D.byId("dt-add").onclick = function () {
      if (quiz.questions.length >= meta.limits.questions) return D.toast("Tối đa " + meta.limits.questions + " câu.", true);
      quiz.questions.push(blank(quiz.questions[cur] ? quiz.questions[cur].type : "single")); cur = quiz.questions.length - 1; dirty = true; drawNav(); drawQ();
    };
  }

  // ---------------------------------------------------------------------- soan 1 cau --
  function drawQ() {
    var q = quiz.questions[cur], box = D.byId("dt-qed");
    if (!q) { box.innerHTML = ""; return; }
    var er = errs["q" + (cur + 1)];
    var h = '<div class="dt-panel dt-pad" style="display:grid;gap:12px">' + (er ? '<p class="dt-err">Câu ' + (cur + 1) + ": " + D.esc(er) + "</p>" : "") +
      '<div class="dt-row"><b>Câu ' + (cur + 1) + '</b><span class="dt-sp"></span><button class="dt-b sm" id="dt-up"' + (cur === 0 ? " disabled" : "") + ">" + D.icon("up") +
      '</button><button class="dt-b sm" id="dt-dn"' + (cur === quiz.questions.length - 1 ? " disabled" : "") + ">" + D.icon("down") + '</button><button class="dt-b sm" id="dt-dup">' +
      D.icon("copy") + ' Nhân đôi</button><button class="dt-b sm danger" id="dt-del">' + D.icon("trash") + " Xoá</button></div>" +
      '<div class="dt-tpick">' + meta.types.map(function (t) {
        return '<button data-t="' + t.type + '" aria-pressed="' + (q.type === t.type) + '">' + D.esc(t.label) + (t.scored ? "" : ' <span class="dt-muted">(không chấm)</span>') + "</button>";
      }).join("") + "</div>" +
      '<div class="dt-f"><label>Câu hỏi</label><textarea class="dt-ta" id="dt-qt" maxlength="' + meta.limits.text + '" style="min-height:64px">' + D.esc(q.text) + "</textarea></div>" +
      '<div class="dt-row"><div class="dt-f"><label>Thời gian</label><select class="dt-sel" id="dt-time">' + meta.times.map(function (t) {
        return '<option value="' + t + '"' + (t === q.time ? " selected" : "") + ">" + t + " giây</option>"; }).join("") + "</select></div>" +
      '<div class="dt-f" style="flex:1;min-width:220px"><label>Ảnh / GIF / video ngắn' + (q.type === "pin" ? " (bắt buộc - ảnh để ghim)" : "") + '</label><div class="dt-row">' +
      '<label class="dt-b sm">' + D.icon("upload") + ' Tải lên<input type="file" id="dt-mfile" accept="image/*,video/mp4" hidden></label>' +
      '<input class="dt-in" id="dt-murl" style="flex:1" placeholder="hoặc dán link https://…" value="' + D.esc(q.media ? q.media.url : "") + '">' +
      (q.media ? '<button class="dt-b sm ghost" id="dt-mdel">' + D.icon("x") + "</button>" : "") + "</div></div></div>" +
      (q.media && q.type !== "pin" ? (q.media.kind === "video" ? '<video src="' + D.esc(D.safeUrl(q.media.url)) + '" muted style="max-height:160px;border-radius:10px"></video>' :
        '<img src="' + D.esc(D.safeUrl(q.media.url)) + '" alt="" style="max-height:160px;max-width:100%;border-radius:10px;object-fit:contain;align-self:start">') : "") +
      '<div id="dt-body"></div><div class="dt-f"><label>Giải thích (hiện sau khi công bố đáp án)</label><input class="dt-in" id="dt-exp" maxlength="600" value="' + D.esc(q.explain) + '"></div></div>';
    box.innerHTML = h;
    D.byId("dt-qt").oninput = function () { q.text = this.value; dirty = true; var nb = D.qsa(D.byId("dt-qnav"), "[data-i]")[cur]; if (nb) nb.lastChild.lastChild.textContent = (q.text || "(chưa có câu hỏi)").slice(0, 60); };
    D.byId("dt-time").onchange = function () { q.time = +this.value; dirty = true; drawNav(); };
    D.byId("dt-exp").oninput = function () { q.explain = this.value; dirty = true; };
    D.byId("dt-murl").onchange = function () {
      var u = this.value.trim();
      if (u && !D.safeUrl(u)) return D.toast("Link phải bắt đầu bằng https://", true);
      q.media = u ? { kind: /\.mp4(\?|$)/i.test(u) ? "video" : "image", url: u } : null; dirty = true; drawQ();
    };
    D.byId("dt-mfile").onchange = function () {
      var f = this.files[0]; if (!f) return;
      if (f.size > 8 * 1024 * 1024) return D.toast("Tệp tối đa 8MB.", true);
      D.toast("Đang tải lên…");
      D.upload(f, false).then(function (u) { q.media = { kind: /^video/.test(f.type) ? "video" : "image", url: u }; dirty = true; drawQ(); }, function (e) { D.toast(D.msg(e), true); });
    };
    var md = D.byId("dt-mdel"); if (md) md.onclick = function () { q.media = null; dirty = true; drawQ(); };
    D.qsa(box, "[data-t]").forEach(function (b) { b.onclick = function () { quiz.questions[cur] = changeType(q, b.dataset.t); dirty = true; drawNav(); drawQ(); }; });
    D.byId("dt-up").onclick = function () { move(-1); };
    D.byId("dt-dn").onclick = function () { move(1); };
    D.byId("dt-dup").onclick = function () { var c = norm(D.clone(q)); reid(c); quiz.questions.splice(cur + 1, 0, c); cur++; dirty = true; drawNav(); drawQ(); };
    D.byId("dt-del").onclick = function () {
      if (quiz.questions.length === 1) return D.toast("Bộ quiz cần ít nhất 1 câu.", true);
      quiz.questions.splice(cur, 1); cur = Math.max(0, cur - 1); dirty = true; drawNav(); drawQ();
    };
    drawBody(q);
  }
  function reid(q) {
    var map = {};
    ["options", "items"].forEach(function (k) { (q[k] || []).forEach(function (o) { var n = tmp(); map[o.id] = n; o.id = n; }); });
    if (q.correct && q.type !== "truefalse") q.correct = q.correct.map(function (c) { return map[c] || c; });
  }
  function move(d) { var j = cur + d, a = quiz.questions; var t = a[cur]; a[cur] = a[j]; a[j] = t; cur = j; dirty = true; drawNav(); drawQ(); }

  function drawBody(q) {
    var box = D.byId("dt-body"), t = q.type, h = "";
    if (t === "single" || t === "multi" || t === "poll") {
      h = '<div class="dt-lbl">Lựa chọn' + (t === "poll" ? "" : (t === "single" ? " - bấm ô màu để chọn 1 đáp án đúng" : " - bấm ô màu để chọn các đáp án đúng")) + "</div>" +
        q.options.map(function (o, i) {
          var ok = (q.correct || []).indexOf(o.id) >= 0;
          return '<div class="dt-optrow"><button class="dt-mark" data-ok="' + i + '" style="background:var(--c' + (i + 1) + ')" aria-label="Đáp án đúng" aria-pressed="' + ok + '">' +
            (t === "poll" ? D.LETTERS[i] : (ok ? "✓" : D.LETTERS[i])) + '</button><input class="dt-in" data-o="' + i + '" maxlength="' + meta.limits.option_text + '" value="' + D.esc(o.text) +
            '" placeholder="Lựa chọn ' + D.LETTERS[i] + '">' + (q.options.length > 2 ? '<button class="dt-b sm ghost" data-rm="' + i + '">' + D.icon("x") + "</button>" : "") + "</div>";
        }).join("") + (q.options.length < meta.limits.options ? '<button class="dt-b sm" id="dt-addo">' + D.icon("plus") + " Thêm lựa chọn</button>" : "");
    } else if (t === "truefalse") {
      h = '<div class="dt-lbl">Đáp án đúng</div><div class="dt-seg"><button data-tf="t" aria-pressed="' + (q.correct[0] === "t") + '">Đúng</button><button data-tf="f" aria-pressed="' + (q.correct[0] === "f") + '">Sai</button></div>';
    } else if (t === "slider") {
      h = '<div class="dt-row">' + [["min", "Nhỏ nhất"], ["max", "Lớn nhất"], ["step", "Bước"], ["answer", "Đáp án"], ["tolerance", "Sai số đủ điểm (±)"]].map(function (f) {
        return '<div class="dt-f" style="width:130px"><label>' + f[1] + '</label><input class="dt-in" type="number" data-n="' + f[0] + '" value="' + D.esc(q[f[0]]) + '"></div>';
      }).join("") + '<div class="dt-f" style="width:100px"><label>Đơn vị</label><input class="dt-in" id="dt-unit" maxlength="12" value="' + D.esc(q.unit || "") + '"></div></div>' +
        '<p class="dt-small dt-muted">Lệch trong sai số = đủ điểm; lệch xa hơn (tới 3 lần) được một phần điểm.</p>';
    } else if (t === "pin") {
      h = '<div class="dt-row"><span class="dt-lbl">Vùng đúng</span><div class="dt-seg"><button data-sh="rect" aria-pressed="' + (q.zone.shape === "rect") + '">Chữ nhật</button><button data-sh="circle" aria-pressed="' +
        (q.zone.shape === "circle") + '">Tròn</button></div><span class="dt-small dt-muted">Kéo trên ảnh để vẽ vùng đúng</span></div>' +
        (q.media && q.media.kind === "image" ? '<div class="dt-pinedit" id="dt-pe"><img src="' + D.esc(D.safeUrl(q.media.url)) + '" alt="" draggable="false"><span class="dt-zone" id="dt-z"></span></div>' :
          '<p class="dt-err">Tải ảnh lên trước (ô Ảnh ở trên).</p>');
    } else if (t === "order") {
      h = '<div class="dt-lbl">Các mục theo THỨ TỰ ĐÚNG (người chơi thấy bị xáo)</div>' + q.items.map(function (o, i) {
        return '<div class="dt-optrow"><b style="width:22px">' + (i + 1) + '</b><input class="dt-in" data-it="' + i + '" maxlength="' + meta.limits.option_text + '" value="' + D.esc(o.text) + '">' +
          '<button class="dt-b sm ghost" data-iu="' + i + '"' + (i === 0 ? " disabled" : "") + ">" + D.icon("up") + "</button>" + (q.items.length > 3 ? '<button class="dt-b sm ghost" data-irm="' + i + '">' + D.icon("x") + "</button>" : "") + "</div>";
      }).join("") + (q.items.length < 6 ? '<button class="dt-b sm" id="dt-addi">' + D.icon("plus") + " Thêm mục</button>" : "");
    } else if (t === "match") {
      h = '<div class="dt-lbl">Các cặp đúng (vế phải sẽ bị xáo)</div>' + q.pairs.map(function (p, i) {
        return '<div class="dt-optrow"><input class="dt-in" data-pl="' + i + '" maxlength="' + meta.limits.option_text + '" value="' + D.esc(p.left) + '" placeholder="Vế trái">→<input class="dt-in" data-pr="' + i +
          '" maxlength="' + meta.limits.option_text + '" value="' + D.esc(p.right) + '" placeholder="Vế phải">' + (q.pairs.length > 2 ? '<button class="dt-b sm ghost" data-prm="' + i + '">' + D.icon("x") + "</button>" : "") + "</div>";
      }).join("") + (q.pairs.length < 6 ? '<button class="dt-b sm" id="dt-addp">' + D.icon("plus") + " Thêm cặp</button>" : "");
    } else if (t === "type") {
      h = '<div class="dt-f"><label>Các cách viết được chấp nhận (mỗi dòng một cách - không phân biệt hoa thường, gõ thiếu dấu vẫn đúng)</label><textarea class="dt-ta" id="dt-acc">' +
        D.esc((q.accept || []).join("\n")) + "</textarea></div>";
    } else if (t === "cloud") {
      h = '<p class="dt-muted">Người chơi gõ vài từ; màn chiếu hiện đám mây từ sau khi khoá. Không tính điểm.</p>';
    }
    box.innerHTML = h;
    bindBody(q, box);
  }
  function bindBody(q, box) {
    function redraw() { dirty = true; drawBody(q); }
    D.qsa(box, "[data-o]").forEach(function (i) { i.oninput = function () { q.options[+i.dataset.o].text = i.value; dirty = true; }; });
    D.qsa(box, "[data-ok]").forEach(function (b) {
      b.onclick = function () {
        if (q.type === "poll") return;
        var id = q.options[+b.dataset.ok].id, k = q.correct.indexOf(id);
        if (q.type === "single") q.correct = [id]; else if (k >= 0) q.correct.splice(k, 1); else q.correct.push(id);
        redraw();
      };
    });
    D.qsa(box, "[data-rm]").forEach(function (b) { b.onclick = function () { var o = q.options.splice(+b.dataset.rm, 1)[0]; q.correct = q.correct.filter(function (c) { return c !== o.id; }); redraw(); }; });
    var ao = D.byId("dt-addo"); if (ao) ao.onclick = function () { q.options.push({ id: tmp(), text: "" }); redraw(); };
    D.qsa(box, "[data-tf]").forEach(function (b) { b.onclick = function () { q.correct = [b.dataset.tf]; redraw(); }; });
    D.qsa(box, "[data-n]").forEach(function (i) { i.oninput = function () { q[i.dataset.n] = i.value === "" ? "" : Number(i.value); dirty = true; }; });
    var un = D.byId("dt-unit"); if (un) un.oninput = function () { q.unit = un.value; dirty = true; };
    D.qsa(box, "[data-it]").forEach(function (i) { i.oninput = function () { q.items[+i.dataset.it].text = i.value; dirty = true; }; });
    D.qsa(box, "[data-iu]").forEach(function (b) { b.onclick = function () { var i = +b.dataset.iu, t = q.items[i]; q.items[i] = q.items[i - 1]; q.items[i - 1] = t; redraw(); }; });
    D.qsa(box, "[data-irm]").forEach(function (b) { b.onclick = function () { q.items.splice(+b.dataset.irm, 1); redraw(); }; });
    var ai = D.byId("dt-addi"); if (ai) ai.onclick = function () { q.items.push({ id: tmp(), text: "" }); redraw(); };
    D.qsa(box, "[data-pl]").forEach(function (i) { i.oninput = function () { q.pairs[+i.dataset.pl].left = i.value; dirty = true; }; });
    D.qsa(box, "[data-pr]").forEach(function (i) { i.oninput = function () { q.pairs[+i.dataset.pr].right = i.value; dirty = true; }; });
    D.qsa(box, "[data-prm]").forEach(function (b) { b.onclick = function () { q.pairs.splice(+b.dataset.prm, 1); redraw(); }; });
    var ap = D.byId("dt-addp"); if (ap) ap.onclick = function () { q.pairs.push({ id: tmp(), left: "", right: "" }); redraw(); };
    var acc = D.byId("dt-acc"); if (acc) acc.oninput = function () { q.accept = acc.value.split("\n").map(function (s) { return s.trim(); }).filter(Boolean); dirty = true; };
    D.qsa(box, "[data-sh]").forEach(function (b) {
      b.onclick = function () { var z = q.zone; q.zone = b.dataset.sh === "circle" ? { shape: "circle", x: z.x + (z.w || 0) / 2 || 0.5, y: z.y + (z.h || 0) / 2 || 0.5, r: 0.1 } : { shape: "rect", x: 0.4, y: 0.4, w: 0.2, h: 0.2 }; redraw(); };
    });
    var pe = D.byId("dt-pe");
    if (pe) pinEditor(q, pe);
  }
  function pinEditor(q, pe) {
    var zEl = D.byId("dt-z"), start = null;
    function show() {
      var z = q.zone;
      zEl.className = "dt-zone" + (z.shape === "circle" ? " circle" : "");
      if (z.shape === "circle") { zEl.style.cssText = "left:" + (z.x - z.r) * 100 + "%;top:" + (z.y - z.r) * pe.offsetWidth / pe.offsetHeight * 100 + "%;width:" + z.r * 200 + "%;aspect-ratio:1"; }
      else zEl.style.cssText = "left:" + z.x * 100 + "%;top:" + z.y * 100 + "%;width:" + z.w * 100 + "%;height:" + z.h * 100 + "%";
    }
    function pt(e) { var r = pe.getBoundingClientRect(); return { x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) }; }
    pe.onpointerdown = function (e) { start = pt(e); pe.setPointerCapture(e.pointerId); };
    pe.onpointermove = function (e) {
      if (!start) return;
      var p = pt(e);
      if (q.zone.shape === "circle") {
        var r = pe.getBoundingClientRect(), dx = (p.x - start.x), dy = (p.y - start.y) * r.height / r.width;
        q.zone = { shape: "circle", x: start.x, y: start.y, r: Math.max(0.01, Math.sqrt(dx * dx + dy * dy)) };
      } else q.zone = { shape: "rect", x: Math.min(start.x, p.x), y: Math.min(start.y, p.y), w: Math.max(0.01, Math.abs(p.x - start.x)), h: Math.max(0.01, Math.abs(p.y - start.y)) };
      dirty = true; show();
    };
    pe.onpointerup = function () { start = null; };
    var img = pe.querySelector("img");
    if (img.complete) show(); else img.onload = show;
  }

  // ---------------------------------------------------------------- luat / bao ve --
  function sw(k, label, sub) {
    return '<label class="dt-row" style="justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line2)"><span><b>' + label + '</b><br><span class="dt-small dt-muted">' + sub +
      '</span></span><span class="dt-sw"><input type="checkbox" data-s="' + k + '"' + (quiz.settings[k] ? " checked" : "") + "><span></span></span></label>";
  }
  function seg(k, opts) {
    return '<div class="dt-seg">' + opts.map(function (o) { return '<button data-sg="' + k + '" data-v="' + o[0] + '" aria-pressed="' + (quiz.settings[k] === o[0]) + '">' + o[1] + "</button>"; }).join("") + "</div>";
  }
  function drawRules() {
    var box = D.byId("dt-rules");
    box.innerHTML = '<h2 class="dt-h2">Luật chơi</h2><div class="dt-row" style="margin:10px 0"><span class="dt-lbl" style="width:120px">Kiểu thi</span>' +
      seg("mode", [["solo", "Cá nhân"], ["team", "Cá nhân + đường đua phòng ban"]]) + '</div><p class="dt-small dt-muted">Kết thúc game luôn hiện cả top người chơi và top phòng ban. Điểm đội = trung bình mỗi người; phòng dưới 4 người gộp vào “Văn phòng”.</p>' +
      '<div class="dt-row" style="margin:10px 0"><span class="dt-lbl" style="width:120px">Bảng xếp hạng</span>' + seg("board", [["each", "Mỗi câu"], ["five", "Mỗi 5 câu"], ["end", "Cuối game"]]) + "</div>" +
      sw("show_on_phone", "Hiện câu hỏi trên điện thoại", "Bật = kiểu Quizizz. Tắt = điện thoại chỉ có ô màu, mọi người nhìn màn chiếu.") +
      sw("by_speed", "Tính điểm theo tốc độ", "Trả lời ngay = 1.000, sát hết giờ = 500.") +
      sw("streak", "Thưởng chuỗi đúng", "+100 mỗi câu đúng liên tiếp, tối đa +500.") +
      sw("last_double", "Câu cuối nhân đôi", "") +
      sw("allow_nick", "Cho đặt tên trong game", "Email công ty luôn hiện nhỏ bên dưới tên.") +
      sw("allow_avatar", "Cho trang trí nhân vật", "Màu, nền, mắt, phụ kiện - lưu theo tài khoản.");
    D.qsa(box, "[data-s]").forEach(function (i) { i.onchange = function () { quiz.settings[i.dataset.s] = i.checked; dirty = true; }; });
    D.qsa(box, "[data-sg]").forEach(function (b) { b.onclick = function () { quiz.settings[b.dataset.sg] = b.dataset.v; dirty = true; drawRules(); }; });
  }
  function drawGuard() {
    var box = D.byId("dt-guard");
    box.innerHTML = '<h2 class="dt-h2">' + D.icon("shield") + ' Mức bảo vệ</h2><p class="dt-small dt-muted">Luật: được hỏi AI, chỉ cấm tool can thiệp. Cờ gian lận chỉ để người dẫn xem - không tự trừ điểm.</p><div class="dt-grid3" style="margin-top:10px">' +
      GUARDS.map(function (g) {
        var on = quiz.settings.guard === g.k;
        return '<button class="dt-panel dt-pad" data-g="' + g.k + '" style="text-align:left;cursor:pointer;' + (on ? "border-color:var(--navy);background:var(--wash)" : "") + '"><b>' + g.t + '</b><p class="dt-small dt-muted" style="margin-top:4px">' + g.d + "</p></button>";
      }).join("") + "</div>";
    D.qsa(box, "[data-g]").forEach(function (b) { b.onclick = function () { quiz.settings.guard = b.dataset.g; dirty = true; drawGuard(); }; });
  }

  // ------------------------------------------------------------------- phan thuong --
  function drawPrizes() {
    var box = D.byId("dt-prizes"), ps = quiz.prizes;
    var rows = ps.map(function (p, i) {
      var ranks = meta.ranks.filter(function (r) { return r.scope === p.scope; });
      return '<div class="dt-prize"><select class="dt-sel" data-ps="' + i + '"><option value="player"' + (p.scope === "player" ? " selected" : "") + '>Người chơi</option><option value="team"' +
        (p.scope === "team" ? " selected" : "") + '>Phòng ban</option></select><select class="dt-sel" data-pr="' + i + '">' + ranks.map(function (r) {
          return '<option value="' + r.rank + '"' + (r.rank === p.rank ? " selected" : "") + ">" + D.esc(r.label) + "</option>"; }).join("") + '</select><select class="dt-sel" data-pt="' + i + '">' +
        [0, 1, 2, 3].map(function (n) { return '<option value="' + n + '"' + (n === +p.tickets ? " selected" : "") + ">" + n + " vé</option>"; }).join("") +
        '</select><input class="dt-in" data-pg="' + i + '" list="dt-gifts" maxlength="60" value="' + D.esc(p.gift) + '" placeholder="Quà kèm (không bắt buộc)"><button class="dt-b sm ghost" data-px="' + i + '">' + D.icon("x") + "</button></div>";
    }).join("");
    var tk = 0; ps.forEach(function (p) { tk += +p.tickets; });
    box.innerHTML = '<div class="dt-row"><h2 class="dt-h2">' + D.icon("gift") + ' Phần thưởng</h2><span class="dt-sp"></span><button class="dt-b sm" data-add="player">+ Giải người chơi</button><button class="dt-b sm" data-add="team">+ Giải phòng ban</button></div>' +
      '<p class="dt-small dt-muted">Một người nhận được nhiều giải nếu đủ điều kiện. Vé tối đa ' + meta.limits.tickets_week + " / người / tuần (tính chung quiz + bài thực hành).</p>" +
      '<datalist id="dt-gifts">' + meta.gifts.map(function (g) { return '<option value="' + D.esc(g) + '">'; }).join("") + "</datalist>" +
      '<div style="display:grid;gap:8px;margin-top:10px">' + (rows || '<p class="dt-muted">Chưa có giải nào.</p>') + "</div>";
    D.qsa(box, "[data-add]").forEach(function (b) {
      b.onclick = function () { if (ps.length >= meta.limits.prizes) return; ps.push({ scope: b.dataset.add, rank: b.dataset.add === "team" ? "team1" : "rank1", tickets: 1, gift: "" }); dirty = true; drawPrizes(); };
    });
    D.qsa(box, "[data-ps]").forEach(function (s) { s.onchange = function () { var p = ps[+s.dataset.ps]; p.scope = s.value; p.rank = s.value === "team" ? "team1" : "rank1"; dirty = true; drawPrizes(); }; });
    D.qsa(box, "[data-pr]").forEach(function (s) { s.onchange = function () { ps[+s.dataset.pr].rank = s.value; dirty = true; }; });
    D.qsa(box, "[data-pt]").forEach(function (s) { s.onchange = function () { ps[+s.dataset.pt].tickets = +s.value; dirty = true; }; });
    D.qsa(box, "[data-pg]").forEach(function (s) { s.oninput = function () { ps[+s.dataset.pg].gift = s.value; dirty = true; }; });
    D.qsa(box, "[data-px]").forEach(function (s) { s.onclick = function () { ps.splice(+s.dataset.px, 1); dirty = true; drawPrizes(); }; });
  }

  // ---------------------------------------------------------------------- luu --
  function payload(status) {
    return { name: quiz.name, modified: quiz.modified, title: quiz.title, description: quiz.description, template: quiz.template,
      status: status, settings: quiz.settings, prizes: quiz.prizes, questions: quiz.questions };
  }
  function save(status, btn) {
    D.busy(btn, true);
    D.api("quiz_save", { quiz: payload(status) }, true).then(function (r) {
      D.busy(btn, false); dirty = false;
      errs = r.errors || {};
      quiz = r.quiz; quiz.questions = quiz.questions.map(norm);
      if (!D.param("q")) history.replaceState(null, "", "/quiz/soan?q=" + encodeURIComponent(quiz.name));
      render();
      D.toast(Object.keys(errs).length ? "Đã lưu nháp - còn " + Object.keys(errs).length + " câu chưa xong." : (status === "Ready" ? "Đã lưu - sẵn sàng mở phòng." : "Đã lưu nháp."));
    }, function (e) {
      D.busy(btn, false);
      errs = (e.data && e.data.errors) || {};
      render();
      D.toast(D.msg(e), true);
    });
  }
  function importFile(f) {
    if (!f) return;
    D.toast("Đang đọc tệp…");
    D.upload(f, true).then(function (url) { return D.api("quiz_import", { file_url: url }, true); }).then(function (r) {
      var add = (r.questions || []).map(norm);
      if (quiz.questions.length === 1 && !quiz.questions[0].text) quiz.questions = [];
      quiz.questions = quiz.questions.concat(add).slice(0, meta.limits.questions);
      cur = Math.max(0, quiz.questions.length - add.length); dirty = true; render();
      D.toast("Đã nhập " + add.length + " câu - xem lại rồi bấm Lưu.");
    }, function (e) { D.toast(D.msg(e), true); });
  }

  load();
})();
