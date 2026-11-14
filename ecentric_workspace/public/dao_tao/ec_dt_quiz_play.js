// Copyright (c) 2026, eCentric and contributors
// /quiz/choi?c=<ma> -- man hinh NGUOI CHOI (dien thoai truoc tien).
// Server la nguon su that: may chi nhan cau hoi KHONG co dap an (dao_tao/domain/questions.py
// public_view), gio dem tu so ms con lai server tinh, dung/sai chi co sau khi cau khoa.
// Ma thiet bi (localStorage) gui kem moi lan goi - muc bao ve Chuan: 1 nguoi 1 thiet bi.
(function () {
  "use strict";
  var D = window.ECDt;
  var root = D.byId("dt-root");
  var code = (D.param("c") || "").replace(/\D/g, "");
  var device = (function () {
    try {
      var v = localStorage.getItem("ecq_dev");
      if (!v) { v = Math.random().toString(36).slice(2) + Date.now().toString(36); localStorage.setItem("ecq_dev", v); }
      return v;
    } catch (e) { return ""; }
  })();
  var st = null, renderedKey = "", pollT = null, tickT = null, gotAt = 0, sending = false, editing = false;
  var draft = {};   // cau tra loi dang soan (chon nhieu, thanh truot, ...)

  function shell(inner) {
    return '<div class="dt-qz"><div class="dt-qtop"><span class="dt-pill">' + (st && st.code ? "Phòng " + D.esc(st.code) : "Quiz") +
      '</span><span class="dt-sp"></span>' + (st && st.me ? '<span class="dt-pill">' + D.fmtNum(st.me.score) + " điểm</span>" : "") +
      '</div><div class="dt-qbody">' + inner + "</div></div>";
  }

  // ------------------------------------------------------------------- vao phong --
  function codeScreen(err) {
    root.innerHTML = shell('<div class="dt-center"><h1>Vào quiz</h1><p>Nhập 6 số trên màn chiếu</p>' +
      '<input id="dt-code" class="dt-code-in" inputmode="numeric" maxlength="6" autocomplete="off" value="' + D.esc(code) + '" aria-label="Mã phòng">' +
      (err ? '<p class="dt-err">' + D.esc(err) + "</p>" : "") +
      '<button class="dt-b gold lg" id="dt-go">Vào phòng</button><a href="/quiz" style="color:#e9ddff">Quiz của tôi</a></div>');
    var inp = D.byId("dt-code");
    inp.focus();
    function go() {
      code = inp.value.replace(/\D/g, "");
      if (code.length !== 6) { D.toast("Mã phòng gồm 6 số.", true); return; }
      history.replaceState(null, "", "/quiz/choi?c=" + code);
      join(D.byId("dt-go"));
    }
    D.byId("dt-go").onclick = go;
    inp.onkeydown = function (e) { if (e.key === "Enter") go(); };
  }

  function join(btn) {
    D.busy(btn, true);
    D.api("join", { code: code, device: device, automation: navigator.webdriver ? 1 : 0 }, true).then(function (s) {
      apply(s);
      if (s.phase === "lobby" && (s.first_join || !seenCreator()) && (s.rules.allow_nick || s.rules.allow_avatar)) creator();
      else render(true);
      D.onRoom(s.session, function () { poll(0); });
      poll();
    }, function (e) { if (D.loginRedirect(e)) return; D.busy(btn, false); codeScreen(D.msg(e)); });
  }
  function seenCreator() { try { return localStorage.getItem("ecq_cr_" + code) === "1"; } catch (e) { return true; } }

  // ----------------------------------------------------------------- nhan vat --
  function creator() {
    editing = true;
    var me = st.me, av = D.clone(me.avatar || {});
    function pick(k, label) {
      var h = '<div class="dt-lbl" style="color:#e9ddff">' + label + '</div><div class="dt-avpick">';
      D.AV[k].forEach(function (v, i) {
        var on = (av[k] || 0) === i;
        h += '<button type="button" data-k="' + k + '" data-v="' + i + '" aria-pressed="' + on + '">' +
          (k === "b" || k === "g" ? '<span class="dt-sw8" style="background:' + v + '"></span>' : D.esc(v)) + "</button>";
      });
      return h + "</div>";
    }
    function draw() {
      root.innerHTML = shell('<div class="dt-center" style="gap:8px"><h2>Tạo nhân vật</h2><div id="dt-avbig">' + D.avatar(av, 120) + "</div>" +
        (st.rules.allow_nick ? '<input id="dt-nick" class="dt-in" maxlength="16" style="max-width:280px;text-align:center;font-weight:700" value="' + D.esc(me.nickname) + '" aria-label="Tên trong game">' :
          '<b>' + D.esc(me.nickname) + "</b>") +
        '<span class="dt-small" style="color:#e9ddff">' + D.esc(me.email) + " · luôn hiện dưới tên</span></div>" +
        (st.rules.allow_avatar ? '<div class="dt-side">' + pick("b", "Màu") + pick("g", "Nền") + pick("e", "Mắt") + pick("a", "Phụ kiện") + "</div>" : "") +
        '<button class="dt-b gold lg" id="dt-save">Vào sảnh</button>');
      D.qsa(root, "[data-k]").forEach(function (b) {
        b.onclick = function () {
          var nick = D.byId("dt-nick") ? D.byId("dt-nick").value : null;
          av[b.dataset.k] = parseInt(b.dataset.v, 10);
          draw();
          if (nick !== null) D.byId("dt-nick").value = nick;
        };
      });
      D.byId("dt-save").onclick = function () {
        var btn = this;
        D.busy(btn, true);
        var args = { code: code };
        if (st.rules.allow_nick) args.nickname = D.byId("dt-nick").value;
        if (st.rules.allow_avatar) args.avatar = av;
        D.api("set_profile", args, true).then(function (s) {
          try { localStorage.setItem("ecq_cr_" + code, "1"); } catch (e) { /* bo qua */ }
          editing = false; apply(s); render(true);
        }, function (e) { D.busy(btn, false); D.toast(D.msg(e), true); });
      };
    }
    draw();
  }

  // ---------------------------------------------------------------------- vong --
  function apply(s) { st = s; gotAt = Date.now(); }
  function poll(delay) {
    clearTimeout(pollT);
    var wait = delay != null ? delay : (st && st.phase === "question" ? 1500 : 2500);
    if (document.hidden && delay == null) wait = 5000;
    pollT = setTimeout(function () {
      D.api("state", { code: code, device: device }).then(function (s) {
        apply(s);
        // Nguoi dan bam Bat dau khi minh con o man Tao nhan vat -> dong man do, vao cau hoi ngay.
        if (editing && s.phase !== "lobby") { editing = false; render(true); }
        else if (!editing) render(false);
        poll();
      }, function (e) {
        if (e && e.dtMessage && /không có phòng|đã mời|thiết bị khác/i.test(e.dtMessage)) {
          var stop = function () {
            root.innerHTML = shell('<div class="dt-center"><h2>' + D.esc(e.dtMessage) + '</h2><a class="dt-b gold" href="/quiz">Quiz của tôi</a></div>');
          };
          // Phong vua ve dich / bi huy: ma phong het hieu luc -> lay ket qua theo ten phong.
          if (st && st.session && /không có phòng/i.test(e.dtMessage)) {
            D.api("result", { session: st.session }).then(function (s) { apply(s); render(true); }, stop);
          } else stop();
          return;
        }
        poll(4000);
      });
    }, wait);
  }
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && st) poll(0);
    if (document.hidden && st && st.rules && st.rules.strict && st.phase === "question") {
      D.api("report", { code: code, kind: "blur" }, true).catch(function () { /* bo qua */ });
    }
  });

  function key() {
    var pw = st.power ? [st.power.offer ? 1 : 0, st.power.picked ? st.power.picked.id : "", (st.power.bag || []).map(function (b) { return b.id; }).join(","),
      (st.power.active || []).map(function (b) { return b.id; }).join(",")].join("/") : "";
    return [st.phase, st.index, st.answered ? 1 : 0, st.kicked ? 1 : 0, st.me ? st.me.rank : "", st.version > 0 && st.phase === "lobby" ? (st.me && st.me.players) : "", pw].join("|");
  }

  function render(force) {
    if (!st) return;
    var k = key();
    if (!force && k === renderedKey) { timer(); return; }
    renderedKey = k;
    if (st.kicked) { root.innerHTML = shell('<div class="dt-center"><h2>Người dẫn đã mời bạn ra khỏi phòng.</h2></div>'); return; }
    var ph = st.phase, h = "";
    if (ph === "lobby") h = lobby();
    else if (ph === "question") h = st.answered ? waitBox("Đã chốt!", "Chờ mọi người trả lời…") : questionHtml();
    else if (ph === "locked") h = st.answered ? waitBox("Đã chốt!", "Chờ công bố đáp án…") : waitBox("Hết giờ", "Câu này bạn chưa kịp trả lời.");
    else if (ph === "reveal") h = stealLines() + powerOffer() + revealHtml();
    else if (ph === "board") h = stealLines() + powerOffer() + boardHtml();
    else if (ph === "ended") h = finalHtml();
    else h = waitBox("Phòng đã đóng", "");
    root.innerHTML = shell(h);
    if (st.rules && st.rules.strict) { root.style.userSelect = "none"; root.oncopy = function (e) { e.preventDefault(); }; }
    if (ph === "lobby") { var eb = D.byId("dt-edit"); if (eb) eb.onclick = creator; }
    if (ph === "question" && !st.answered) bindQuestion();
    bindPower();
    timer();
  }

  function waitBox(t, sub) {
    return '<div class="dt-center"><div style="font-size:54px">⏳</div><h2>' + D.esc(t) + "</h2><p>" + D.esc(sub) + "</p>" + meLine() + "</div>";
  }
  function meLine() {
    var m = st.me || {};
    return '<div class="dt-brow me" style="width:100%">' + D.pcard(m, 40) + '<span class="dt-sc">' +
      (m.rank ? "#" + m.rank + " · " : "") + D.fmtNum(m.score) + "</span></div>";
  }
  function lobby() {
    var m = st.me;
    return '<div class="dt-center"><div>' + D.avatar(m.avatar, 120) + '</div><h2>' + D.esc(m.nickname) + '</h2><span style="color:#e9ddff">' +
      D.esc(m.email) + '</span><p style="font-size:18px">Bạn đã vào! Nhìn tên mình trên màn chiếu nhé.</p><p>' +
      D.fmtNum(m.players) + " người trong phòng · chờ người dẫn bắt đầu</p>" +
      ((st.rules.allow_nick || st.rules.allow_avatar) ? '<button class="dt-b" id="dt-edit">Đổi nhân vật</button>' : "") + "</div>";
  }

  // ------------------------------------------------------------------- cau hoi --
  function timer() {
    var bar = D.byId("dt-tbar"), num = D.byId("dt-tnum");
    clearTimeout(tickT);
    if (!st || st.phase !== "question" || st.answered) return;
    var passed = Date.now() - gotAt;
    var lead = Math.max(0, (st.lead_ms || 0) - passed);
    var left = Math.max(0, (st.remaining_ms || 0) - passed);
    var lock = D.byId("dt-leadin");
    if (lock) lock.hidden = lead <= 0;
    // [data-keep]: nut tu quan trang thai (Len/Xuong o mep, Gui cua cau ghim truoc khi ghim).
    D.qsa(root, ".dt-ans").forEach(function (b) { if (!b.hasAttribute("data-keep")) b.disabled = lead > 0; });
    if (num) num.textContent = lead > 0 ? "Chuẩn bị " + Math.ceil(lead / 1000) : Math.ceil(left / 1000) + "s";
    if (bar) bar.style.width = (lead > 0 ? 100 : Math.min(100, 100 * left / Math.max(1, st.limit_ms))) + "%";
    if (left > 0) tickT = setTimeout(timer, 250);
  }
  function qHead(q) {
    var t = '<div class="dt-timer"><span class="dt-pill" style="background:rgba(255,255,255,.16);border-radius:999px;padding:3px 10px;font-weight:700">Câu ' +
      (st.index + 1) + "/" + st.total + '</span><div class="dt-bar"><i id="dt-tbar"></i></div><b id="dt-tnum"></b></div>';
    if (lastX2()) t = t.replace("</span>", ' <b class="dt-x2chip">×2</b></span>');
    t += powerOffer() + powerBag();
    if (q.tiles_only) return t + '<p style="text-align:center">Nhìn câu hỏi trên màn chiếu</p>' + leadIn();
    return t + '<div class="dt-qcard"><span class="dt-chip nv">' + D.esc(q.label) + "</span><h2 style=\"margin-top:6px\">" + D.esc(q.text) + "</h2>" +
      (q.media && q.media.url && q.type !== "pin" ? mediaHtml(q.media) : "") + "</div>" +
      leadIn();
  }
  function leadIn() {
    return lastX2() ? '<p id="dt-leadin" class="dt-x2lead" hidden><b>×2</b> Câu cuối · nhân đôi điểm!</p>' : '<p id="dt-leadin" class="dt-big" hidden>Chuẩn bị…</p>';
  }
  function lastX2() { return st.is_last && st.rules && st.rules.last_double !== false; }

  // ---------------------------------------------------------------- power-up --
  function powerOffer() {
    var pw = st.power;
    if (!pw) return "";
    if (pw.offer) return '<div class="dt-pwcard"><b>🎁 Chọn 1 power-up</b><span class="dt-small">Skill vào túi (tối đa ' + pw.bag_max +
      ") - câu nào muốn dùng thì bấm Dùng trước khi trả lời.</span>" + pw.offer.map(function (o) {
        return '<button class="dt-pwbtn" data-pick="' + D.esc(o.id) + '"><span class="dt-pwic">' + D.esc(o.icon) + "</span><span><b>" + D.esc(o.label) +
          "</b><small>" + D.esc(o.desc) + "</small></span></button>";
      }).join("") + '<button class="dt-b sm" data-pick="skip" style="align-self:center">Bỏ qua</button></div>';
    if (pw.window && pw.full && !pw.picked && st.phase !== "question") return '<div class="dt-pwcard done">🎒 Túi đã đầy (' + pw.bag_max + " skill) - dùng bớt skill để nhận lượt power-up sau.</div>";
    if (pw.picked && st.phase !== "question") return '<div class="dt-pwcard done">' + (pw.picked.id === "skip" ? "Bạn đã bỏ qua lượt power-up này." :
      "Đã chọn: <b>" + D.esc(pw.picked.label) + "</b>" + (pw.picked.id === "gold" ? " · +300 điểm" : " · nằm trong túi")) + "</div>";
    return "";
  }
  function stealLines() {
    return (st.steals || []).map(function (e) {
      var t = e.role === "thief" ? (e.blocked ? "🛡️ " + D.esc(e.other) + " đã chặn cú đánh cắp của bạn!" : "😈 Bạn lấy được " + D.fmtNum(e.amount) + " điểm từ " + D.esc(e.other))
        : (e.blocked ? "🛡️ Khiên đã chặn cú đánh cắp của " + D.esc(e.other) + "!" : "😈 " + D.esc(e.other) + " vừa lấy của bạn " + D.fmtNum(e.amount) + " điểm");
      return '<div class="dt-pwcard done">' + t + "</div>";
    }).join("");
  }
  function powerBag() {
    var pw = st.power;
    if (!pw || st.answered) return "";
    var h = "";
    if ((pw.active || []).length) h += '<div class="dt-pwbar">' + pw.active.map(function (a) { return '<span class="dt-pwchip">' + D.esc(a.icon) + " " + D.esc(a.label) + " · đang dùng</span>"; }).join("") + "</div>";
    if ((pw.bag || []).length) h += '<div class="dt-pwbar">' + pw.bag.map(function (b) {
      if (b.auto) return '<span class="dt-pwchip">' + D.esc(b.icon) + " " + D.esc(b.label) + " · tự bật</span>";
      return '<button class="dt-pwuse" data-use="' + D.esc(b.id) + '" data-keep>' + D.esc(b.icon) + " Dùng: " + D.esc(b.label) + "</button>";
    }).join("") + "</div>";
    return h;
  }
  function bindPower() {
    D.qsa(root, "[data-pick]").forEach(function (b) {
      b.onclick = function () { powerCall("power_pick", b.dataset.pick, b); };
    });
    D.qsa(root, "[data-use]").forEach(function (b) {
      b.onclick = function () { powerCall("power_use", b.dataset.use, b); };
    });
  }
  function powerCall(method, id, btn) {
    if (sending) return;
    sending = true; D.busy(btn, true);
    D.api(method, { code: code, power: id, device: device }, true).then(function (s) {
      sending = false; apply(s); render(true);
    }, function (e) { sending = false; D.busy(btn, false); D.toast(D.msg(e), true); poll(0); });
  }
  function mediaHtml(m) {
    var u = D.safeUrl(m.url);
    if (!u) return "";
    if (m.kind === "video") return '<video class="dt-qimg" src="' + D.esc(u) + '" autoplay muted playsinline loop></video>';
    return '<img class="dt-qimg" src="' + D.esc(u) + '" alt="" style="margin-top:10px">';
  }
  function optTiles(q, multi) {
    var long = q.options.some(function (o) { return (o.text || "").length > 24; });
    var h = '<div class="dt-opts' + (q.tiles_only ? " tiles" : "") + (long ? " long" : "") + '">';
    q.options.forEach(function (o, i) {
      if (o.gone) {                                   // power-up "Loai 1 dap an sai": giu dung vi tri / mau
        h += '<button class="dt-opt c' + i + ' gone" disabled data-keep aria-label="Đã loại"><span class="dt-shape">' + D.LETTERS[i] +
          "</span><span>✂️ Đã loại</span></button>";
        return;
      }
      h += '<button class="dt-opt dt-ans c' + i + '" data-o="' + D.esc(o.id) + '" aria-pressed="false"><span class="dt-shape">' + D.LETTERS[i] +
        "</span><span>" + D.esc(o.text) + "</span>" + (multi ? '<span class="dt-tick" aria-hidden="true"></span>' : "") + "</button>";
    });
    return h + "</div>" + (multi ? '<p style="text-align:center">Chọn ' + (q.pick || "các") + ' đáp án rồi bấm Gửi</p><button class="dt-b gold lg dt-ans" id="dt-send">Gửi</button>' : "");
  }
  function questionHtml() {
    var q = st.question;
    draft = {};
    var t = q.type, h = qHead(q);
    if (t === "single" || t === "truefalse" || t === "poll") h += optTiles(q, false);
    else if (t === "multi") h += optTiles(q, true);
    else if (t === "slider") {
      var mid = q.min + Math.round((q.max - q.min) / 2 / q.step) * q.step;
      h += '<div class="dt-qcard" style="text-align:center"><div class="dt-big" id="dt-sv">' + mid + " " + D.esc(q.unit || "") + '</div>' +
        '<input type="range" class="dt-slider dt-ans" id="dt-sl" min="' + q.min + '" max="' + q.max + '" step="' + q.step + '" value="' + mid +
        '" style="accent-color:#46178f"><div class="dt-row"><span>' + q.min + '</span><span class="dt-sp"></span><span>' + q.max + "</span></div></div>" +
        '<button class="dt-b gold lg dt-ans" id="dt-send">Gửi</button>';
    } else if (t === "pin") {
      h += '<div class="dt-pinbox" id="dt-pinbox"><img src="' + D.esc(D.safeUrl(q.media && q.media.url)) + '" alt="Ảnh để ghim"></div>' +
        '<p style="text-align:center">Chạm vào ảnh để ghim</p><button class="dt-b gold lg dt-ans" id="dt-send" data-keep disabled>Gửi</button>';
    } else if (t === "order") {
      draft.order = q.items.map(function (i) { return i.id; });
      h += '<div class="dt-olist" id="dt-ol"></div><button class="dt-b gold lg dt-ans" id="dt-send">Gửi thứ tự</button>';
    } else if (t === "match") {
      h += '<div class="dt-olist">' + q.lefts.map(function (l) {
        return '<div class="dt-oitem"><span class="dt-sp">' + D.esc(l.text) + '</span><select class="dt-sel dt-ans" data-l="' + D.esc(l.id) +
          '" style="max-width:55%"><option value="">— ghép với —</option>' + q.rights.map(function (r) {
            return '<option value="' + D.esc(r.id) + '">' + D.esc(r.text) + "</option>";
          }).join("") + "</select></div>";
      }).join("") + '</div><button class="dt-b gold lg dt-ans" id="dt-send">Gửi</button>';
    } else if (t === "type" || t === "cloud") {
      h += '<input class="dt-in dt-ans" id="dt-txt" maxlength="' + (q.maxlen || 60) + '" placeholder="' + (t === "cloud" ? "Một vài từ…" : "Gõ đáp án…") +
        '" style="font-size:18px;padding:14px" autocomplete="off"><button class="dt-b gold lg dt-ans" id="dt-send">Gửi</button>';
    }
    return h;
  }
  function drawOrder() {
    var q = st.question, box = D.byId("dt-ol");
    var txt = {};
    q.items.forEach(function (i) { txt[i.id] = i.text; });
    box.innerHTML = draft.order.map(function (id, i) {
      return '<div class="dt-oitem"><b>' + (i + 1) + '</b><span class="dt-sp">' + D.esc(txt[id]) + '</span><button class="dt-b sm dt-ans" data-keep data-up="' + i +
        '" aria-label="Lên"' + (i === 0 ? " disabled" : "") + ">" + D.icon("up") + '</button><button class="dt-b sm dt-ans" data-keep data-dn="' + i + '" aria-label="Xuống"' +
        (i === draft.order.length - 1 ? " disabled" : "") + ">" + D.icon("down") + "</button></div>";
    }).join("");
    D.qsa(box, "[data-up],[data-dn]").forEach(function (b) {
      b.onclick = function () {
        var i = parseInt(b.dataset.up != null ? b.dataset.up : b.dataset.dn, 10), j = b.dataset.up != null ? i - 1 : i + 1;
        if (j < 0 || j >= draft.order.length) return;
        var tmp = draft.order[i]; draft.order[i] = draft.order[j]; draft.order[j] = tmp; drawOrder();
      };
    });
  }
  function bindQuestion() {
    var q = st.question, t = q.type;
    if (t === "single" || t === "truefalse" || t === "poll") {
      D.qsa(root, ".dt-opt").forEach(function (b) { b.onclick = function () { if (sending) return; b.setAttribute("aria-pressed", "true"); send({ o: b.dataset.o }); }; });
      return;
    }
    if (t === "multi") {
      draft.sel = {};
      D.qsa(root, ".dt-opt").forEach(function (b) {
        b.onclick = function (ev) {
          if (ev) ev.preventDefault();
          var on = !draft.sel[b.dataset.o]; draft.sel[b.dataset.o] = on; b.setAttribute("aria-pressed", String(on));
          var tk = b.querySelector(".dt-tick"); if (tk) tk.textContent = on ? "✓" : "";
          var n = Object.keys(draft.sel).filter(function (k) { return draft.sel[k]; }).length, sb = D.byId("dt-send");
          if (sb) sb.textContent = n ? "Gửi (" + n + " đáp án)" : "Gửi";
        };
      });
    }
    if (t === "slider") {
      var sl = D.byId("dt-sl");
      sl.oninput = function () { D.byId("dt-sv").textContent = sl.value + " " + (q.unit || ""); };
    }
    if (t === "pin") {
      var box = D.byId("dt-pinbox");
      box.onclick = function (e) {
        var r = box.getBoundingClientRect();
        draft.x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
        draft.y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
        var pin = box.querySelector(".dt-pin");
        if (!pin) { pin = document.createElement("span"); pin.className = "dt-pin"; pin.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7z" fill="#e21b3c" stroke="#fff" stroke-width="2"/></svg>'; box.appendChild(pin); }
        pin.style.left = draft.x * 100 + "%"; pin.style.top = draft.y * 100 + "%";
        D.byId("dt-send").disabled = false;
      };
    }
    if (t === "order") drawOrder();
    var sendB = D.byId("dt-send");
    if (sendB) sendB.onclick = function () {
      var p;
      if (t === "multi") { p = { o: Object.keys(draft.sel).filter(function (k) { return draft.sel[k]; }) }; if (!p.o.length) return D.toast("Chọn ít nhất một đáp án.", true); }
      else if (t === "slider") p = { v: parseFloat(D.byId("dt-sl").value) };
      else if (t === "pin") p = { x: draft.x, y: draft.y };
      else if (t === "order") p = { o: draft.order };
      else if (t === "match") {
        p = { m: {} };
        D.qsa(root, "select[data-l]").forEach(function (s) { if (s.value) p.m[s.dataset.l] = s.value; });
        if (!Object.keys(p.m).length) return D.toast("Ghép ít nhất một cặp.", true);
      } else { p = { t: D.byId("dt-txt").value.trim() }; if (!p.t) return D.toast("Chưa nhập câu trả lời.", true); }
      send(p);
    };
    var txt = D.byId("dt-txt");
    if (txt) txt.onkeydown = function (e) { if (e.key === "Enter" && sendB) sendB.click(); };
  }
  function send(payload) {
    if (sending) return;
    sending = true;
    D.qsa(root, ".dt-ans").forEach(function (b) { b.disabled = true; });
    D.api("answer", { code: code, qid: st.question.id, payload: payload, device: device }, true).then(function () {
      sending = false; st.answered = true; render(true); poll(300);
    }, function (e) {
      sending = false; D.toast(D.msg(e), true); poll(0);
    });
  }

  // -------------------------------------------------------------------- ket qua --
  function revealHtml() {
    var r = st.result || {}, q = st.question, rv = st.reveal || {};
    var cls = !r.scored ? "none" : (r.correct ? "ok" : (r.partial ? "part" : (st.answered ? "bad" : "none")));
    var title = !r.scored ? "Cảm ơn bạn!" : (r.correct ? "Chính xác!" : (r.partial ? "Gần đúng!" : (st.answered ? "Chưa đúng" : "Hết giờ")));
    var h = '<div class="dt-res ' + cls + '">' + title + "<small>" + (r.scored ? (r.points < 0 ? "" : "+") + D.fmtNum(r.points) + " điểm" +
      (r.correct && r.streak > 1 ? " · chuỗi " + r.streak + " 🔥" : "") : "Câu này không tính điểm") + "</small></div>";
    h += '<div class="dt-qcard"><h2>' + D.esc(q.text) + "</h2>" + answerKey(q, rv, st.my_answer) +
      (rv.explain ? '<p class="dt-muted" style="margin-top:10px">💡 ' + D.esc(rv.explain) + "</p>" : "") + "</div>";
    return h + meLine();
  }
  function answerKey(q, rv, mine) {
    var t = q.type;
    if (q.options && (t === "single" || t === "multi" || t === "truefalse" || t === "poll")) {
      var right = rv.correct || [], my = mine ? [].concat(mine.o || []) : [];
      return '<div class="dt-opts" style="margin-top:10px">' + q.options.map(function (o, i) {
        var ok = right.indexOf(o.id) >= 0;
        return '<div class="dt-opt c' + i + (right.length && !ok ? " dim" : "") + (ok ? " right" : "") + '" ' + (my.indexOf(o.id) >= 0 ? 'aria-pressed="true"' : "") +
          '><span class="dt-shape">' + D.LETTERS[i] + "</span><span>" + D.esc(o.text) + "</span></div>";
      }).join("") + "</div>";
    }
    if (t === "slider") return '<p class="dt-big" style="color:#26890c">' + rv.answer + (rv.tolerance ? " ± " + rv.tolerance : "") + " " + D.esc(q.unit || "") + "</p>" +
      (mine ? '<p class="dt-muted" style="text-align:center">Bạn chọn ' + mine.v + "</p>" : "");
    if (t === "pin") {
      var z = rv.zone || {}, zs = z.shape === "circle" ?
        "left:" + (z.x - z.r) * 100 + "%;top:" + (z.y - z.r / (z.ar || 1)) * 100 + "%;width:" + z.r * 200 + "%;aspect-ratio:1" :
        "left:" + z.x * 100 + "%;top:" + z.y * 100 + "%;width:" + z.w * 100 + "%;height:" + z.h * 100 + "%";
      return '<div class="dt-pinbox" style="margin-top:10px"><img src="' + D.esc(D.safeUrl(q.media && q.media.url)) + '" alt=""><span class="dt-zone' +
        (z.shape === "circle" ? " circle" : "") + '" style="' + zs + '"></span>' +
        (mine ? '<span class="dt-dot" style="left:' + mine.x * 100 + "%;top:" + mine.y * 100 + '%"></span>' : "") + "</div>";
    }
    if (t === "order") {
      var tx = {}; q.items.forEach(function (i) { tx[i.id] = i.text; });
      return '<ol style="margin-top:10px">' + (rv.order || []).map(function (id) { return "<li>" + D.esc(tx[id]) + "</li>"; }).join("") + "</ol>";
    }
    if (t === "match") {
      var rt = {}; q.rights.forEach(function (r) { rt[r.id] = r.text; });
      return '<ul style="margin-top:10px">' + q.lefts.map(function (l) { return "<li>" + D.esc(l.text) + " → <b>" + D.esc(rt[(rv.pairs || {})[l.id]]) + "</b></li>"; }).join("") + "</ul>";
    }
    if (t === "type") return '<p style="margin-top:10px">Đáp án: <b>' + (rv.accept || []).map(D.esc).join(" / ") + "</b></p>" +
      (mine ? '<p class="dt-muted">Bạn gõ: ' + D.esc(mine.t) + "</p>" : "");
    return "";
  }
  function boardRows(rows) {
    var me = st.me || {};
    return '<div class="dt-board">' + (rows || []).map(function (p) {
      return '<div class="dt-brow' + (p.email === me.email ? " me" : "") + '"><span class="dt-rk">' + p.rank + "</span>" + D.pcard(p, 36) +
        '<span class="dt-sc">' + D.fmtNum(p.score) + "</span></div>";
    }).join("") + "</div>";
  }
  function boardHtml() {
    var r = st.result || {};
    return '<h2 style="text-align:center">Bảng xếp hạng</h2>' + boardRows(st.board) +
      '<p style="text-align:center">' + (r.scored ? (r.correct ? "Câu vừa rồi: đúng +" + D.fmtNum(r.points) : "Câu vừa rồi: chưa đúng") : "") + "</p>" + meLine();
  }
  function finalHtml() {
    var f = st.final || {};
    var h = '<div class="dt-center"><div style="font-size:54px">🏁</div><h1>Về đích!</h1><p style="font-size:20px">Hạng <b>' +
      (f.my_rank || "—") + "</b>/" + (f.players || "—") + " · " + D.fmtNum(f.my_score) + " điểm</p></div>";
    if ((f.awards || []).length) {
      h += '<div class="dt-qcard"><h2>🎁 Giải của bạn</h2><ul>' + f.awards.map(function (a) {
        return "<li><b>" + D.esc(a.label) + "</b>" + (a.tickets ? " · " + a.tickets + " vé" : "") + (a.gift ? " · " + D.esc(a.gift) : "") + "</li>";
      }).join("") + "</ul>" + (f.awards[0].granted != null ? '<p class="dt-muted dt-small">Vé thực nhận: ' + f.awards[0].granted + " (tối đa 3 vé / tuần)</p>" : "") + "</div>";
    }
    h += '<h3>Top người chơi</h3>' + boardRows(f.podium);
    if ((f.teams || []).length) {
      h += '<h3>Top phòng ban</h3><div class="dt-board">' + f.teams.map(function (t) {
        return '<div class="dt-brow"><span class="dt-rk">' + t.rank + "</span><span>" + D.esc(t.team) + ' <span class="dt-mail">(' + t.members +
          ' người)</span></span><span class="dt-sc">' + D.fmtNum(t.score) + "</span></div>";
      }).join("") + "</div>";
    }
    return h + '<a class="dt-b gold" href="/quiz" style="align-self:center">Quiz của tôi</a>';
  }

  if (!code || code.length !== 6) codeScreen("");
  else { root.innerHTML = shell('<div class="dt-center"><p>Đang vào phòng…</p></div>'); join(null); }
})();
