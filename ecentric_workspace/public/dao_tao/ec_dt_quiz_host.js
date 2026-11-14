// Copyright (c) 2026, eCentric and contributors
// /quiz/chieu?s=<phong> -- MAY CHIEU + bang nguoi dan (Ban dao tao / HR). Nguoi dan bam chuyen
// cau; server tu khoa khi het gio hoac khi moi nguoi da tra loi. Moi nut gui kem `version`
// trang dang nhin: lech (dong ho vua khoa cau, nguoi dan khac vua bam) thi server khong lam va
// tra trang thai moi - tranh bam "Tiep" hai lan nhay qua mot cau.
(function () {
  "use strict";
  var D = window.ECDt;
  var root = D.byId("dt-root");
  var session = D.param("s");
  var st = null, gotAt = 0, pollT = null, tickT = null, renderedKey = "", panel = false, acting = false;
  var ACT = { start: "Bắt đầu", lock: "Khoá câu", reveal: "Công bố đáp án", board: "Bảng xếp hạng", next: "Câu tiếp", end: "Về đích" };
  var GUARD = { basic: "Cơ bản", standard: "Chuẩn", strict: "Nghiêm" };
  var FLAG = { fast: "Trả lời nhanh bất thường", automation: "Trình duyệt tự động", blur: "Rời màn hình", device: "Thử vào từ máy khác" };

  if (!session) { root.innerHTML = '<div class="dt-proj"><div class="dt-center"><h2>Thiếu mã phòng.</h2><a class="dt-b gold" href="/quiz">Về trang Quiz</a></div></div>'; return; }

  function load(delay) {
    clearTimeout(pollT);
    pollT = setTimeout(function () {
      D.api("room_state", { session: session }).then(function (s) { st = s; gotAt = Date.now(); render(false); load(); },
        function (e) { if (!st) root.innerHTML = '<div class="dt-proj"><div class="dt-center"><h2>' + D.esc(D.msg(e)) + "</h2></div></div>"; load(3000); });
    }, delay != null ? delay : (st && (st.phase === "question" || st.phase === "lobby") ? 1000 : 2000));
  }

  function act(action, btn) {
    if (acting) return;
    if ((action === "end" && st.phase !== "reveal" && st.phase !== "board") || action === "cancel") {
      if (!window.confirm(action === "cancel" ? "Huỷ phòng? Không ai nhận giải." : "Kết thúc sớm và chốt kết quả ngay?")) return;
    }
    acting = true; D.busy(btn, true);
    D.api("room_act", { session: session, action: action, version: st.version }, true).then(function (r) {
      acting = false; st = r.state; gotAt = Date.now();
      if (r.stale) D.toast("Phòng vừa đổi trạng thái - xem lại rồi bấm tiếp.");
      render(true); load();
    }, function (e) { acting = false; D.busy(btn, false); D.toast(D.msg(e), true); load(0); });
  }

  // Sanh cho: ve lai khi ai do doi ten / nhan vat (truoc chi so dem nguoi -> doi nhan vat khong hien).
  function lobbySig() { return (st.lobby || []).map(function (p) { return [p.email, p.nickname, JSON.stringify(p.avatar || {}), p.kicked ? 1 : 0].join("~"); }).join("|"); }
  function key() { return [st.phase, st.index, st.players, st.phase === "lobby" ? lobbySig() : "", panel ? 1 : 0, (st.flags || []).length, st.power_open ? st.power_open.picked : ""].join("|"); }

  function render(force) {
    var k = key();
    if (!force && k === renderedKey) { updateLive(); return; }
    renderedKey = k;
    var top = '<div class="dt-ptop"><b style="font-size:18px">' + D.esc(st.title) + '</b><span class="dt-pill" style="background:rgba(255,255,255,.16);border-radius:999px;padding:4px 12px">Mã <b>' +
      D.esc(st.code) + '</b></span><span class="dt-sp"></span><span title="Mức bảo vệ">' + D.icon("shield") + " " + (GUARD[st.settings.guard] || "") +
      '</span><span>👥 <b id="dt-np">' + st.players + "</b></span>" +
      '<span id="dt-mus"></span><button class="dt-b sm ghost" style="color:#fff" id="dt-fs">Toàn màn hình</button></div>';
    var main = "";
    if (st.phase === "lobby") main = lobby();
    else if (st.phase === "question" || st.phase === "locked") main = question();
    else if (st.phase === "reveal") main = reveal();
    else if (st.phase === "board") main = board();
    else if (st.phase === "ended") main = final();
    else main = '<div class="dt-center"><h1>Phòng đã huỷ</h1><a class="dt-b gold" href="/quiz">Về trang Quiz</a></div>';
    var na = st.next_action;
    var bar = '<div class="dt-pbar">' + (na ? '<button class="dt-b gold lg" id="dt-main" data-a="' + na + '">' + ACT[na] + (na === "next" ? " (" + (st.index + 2) + "/" + st.total + ")" : "") + "</button>" : "") +
      '<span class="dt-sp"></span>' + (st.flags && st.flags.length ? '<span class="dt-chip warn">' + D.icon("flag") + " " + st.flags.length + " cờ</span>" : "") +
      (st.phase !== "ended" && st.phase !== "cancelled" ? '<button class="dt-b" id="dt-panel">' + (panel ? "Ẩn người chơi" : "Người chơi") + "</button>" : "") +
      (["lobby", "question", "locked", "reveal", "board"].indexOf(st.phase) >= 0 ? (st.phase !== "lobby" ? '<button class="dt-b" data-a="end">Kết thúc sớm</button>' : "") +
        '<button class="dt-b danger" data-a="cancel">Huỷ phòng</button>' : '<a class="dt-b" href="/quiz">Về trang Quiz</a>') + "</div>";
    root.innerHTML = '<div class="dt-proj">' + top + '<div class="dt-pmain">' + main + (panel ? players() : "") + "</div>" + bar + "</div>";
    D.qsa(root, "[data-a]").forEach(function (b) { b.onclick = function () { act(b.dataset.a, b); }; });
    var pb = D.byId("dt-panel"); if (pb) pb.onclick = function () { panel = !panel; render(true); };
    D.byId("dt-fs").onclick = function () { var el = document.documentElement; if (!document.fullscreenElement && el.requestFullscreen) el.requestFullscreen(); else if (document.exitFullscreen) document.exitFullscreen(); };
    if (st.phase === "lobby") qr();
    if (panel) bindPlayers();
    var csv = D.byId("dt-csv"); if (csv) csv.onclick = downloadAwards;
    if (window.ECDtMusic) { try { window.ECDtMusic.attach(D.byId("dt-mus"), st.phase); } catch (e) { /* nhac hong khong duoc lam hong man chieu */ } }
    updateLive();
  }

  function updateLive() {
    clearTimeout(tickT);
    var np = D.byId("dt-np"); if (np) np.textContent = st.players;
    var an = D.byId("dt-ans"); if (an) an.textContent = st.answered + "/" + st.players;
    var ring = D.byId("dt-ring");
    if (ring && st.phase === "question") {
      var passed = Date.now() - gotAt, lead = Math.max(0, st.lead_ms - passed), left = Math.max(0, st.remaining_ms - passed);
      ring.style.setProperty("--p", (lead > 0 ? 100 : 100 * left / Math.max(1, st.limit_ms)) + "%");
      ring.querySelector("span").textContent = lead > 0 ? "…" : Math.ceil(left / 1000);
      var x2 = D.byId("dt-x2"); if (x2) x2.hidden = lead <= 0;
      if (left > 0) tickT = setTimeout(updateLive, 250);
    }
  }

  function joinUrl() { return location.origin + "/quiz/choi?c=" + st.code; }
  function qr() {
    var box = D.byId("dt-qr");
    if (!box || typeof window.qrcode !== "function") return;
    try { var q = window.qrcode(0, "M"); q.addData(joinUrl()); q.make(); box.innerHTML = q.createSvgTag({ cellSize: 5, margin: 2, scalable: true }); }
    catch (e) { box.textContent = ""; }
  }
  function lobby() {
    return '<div class="dt-row" style="gap:18px;align-items:stretch"><div class="dt-joincode"><div id="dt-qr" style="width:170px;height:170px"></div><div><div>Vào <b style="font-size:20px;letter-spacing:0;color:var(--ink)">' +
      D.esc(location.host) + '/quiz</b> hoặc quét QR</div><div>Mã phòng</div><b>' + D.esc(st.code) + "</b></div></div>" +
      '<div class="dt-side" style="flex:1;min-width:240px"><b>Luật chơi</b><span>' + (st.settings.mode === "team" ? "Cá nhân + đường đua phòng ban" : "Cá nhân") +
      "</span><span>" + (st.settings.show_on_phone ? "Câu hỏi hiện trên điện thoại" : "Điện thoại chỉ có ô màu - nhìn màn chiếu") + "</span><span>Được hỏi AI · không dùng tool can thiệp</span></div></div>" +
      '<h2>' + st.players + " người đã vào</h2><div class=\"dt-lobby\">" + st.lobby.filter(function (p) { return !p.kicked; }).map(function (p) {
        return '<div class="dt-pc">' + D.pcard(p, 38) + "</div>";
      }).join("") + "</div>";
  }
  function qText() { return st.question.text; }
  function media() {
    var m = st.question.media, u = m && D.safeUrl(m.url);
    if (!u) return "";
    if (m.kind === "video") return '<video src="' + D.esc(u) + '" autoplay muted loop playsinline style="max-height:34vh;max-width:100%;border-radius:14px;align-self:center"></video>';
    return '<img src="' + D.esc(u) + '" alt="" style="max-height:34vh;max-width:100%;border-radius:14px;align-self:center;background:#fff">';
  }
  function opts(rv, tally) {
    var q = st.question;
    if (!q.options) return "";
    var right = (rv && rv.correct) || [];
    return '<div class="dt-opts">' + q.options.map(function (o, i) {
      var ok = right.indexOf(o.id) >= 0, n = tally && tally.options ? (tally.options[o.id] || 0) : null;
      return '<div class="dt-opt c' + i + (rv && right.length && !ok ? " dim" : "") + (ok ? " right" : "") + '"><span class="dt-shape">' + D.LETTERS[i] +
        "</span><span>" + D.esc(o.text) + "</span>" + (n != null ? '<b style="margin-left:auto">' + n + "</b>" : "") + "</div>";
    }).join("") + "</div>";
  }
  function otherPrompt() {
    var q = st.question;
    var hint = { slider: "Kéo thanh trượt trên điện thoại", pin: "Ghim lên ảnh trên điện thoại", order: "Sắp xếp trên điện thoại",
      match: "Ghép cặp trên điện thoại", type: "Gõ đáp án trên điện thoại", cloud: "Gõ vài từ - đám mây hiện sau khi khoá" }[q.type];
    if (q.type === "pin") return '<img src="' + D.esc(D.safeUrl(q.media && q.media.url)) + '" alt="" style="max-height:44vh;max-width:100%;border-radius:14px;align-self:center">';
    return hint ? '<p class="dt-big">' + hint + "</p>" : "";
  }
  function question() {
    var locked = st.phase === "locked";
    return '<div class="dt-row" style="gap:16px;align-items:center"><div class="dt-ring" id="dt-ring"><span>' + (locked ? "🔒" : "") + '</span></div><div class="dt-qtitle" style="flex:1">' +
      D.esc(qText()) + '</div><div class="dt-side" style="text-align:center"><b style="font-size:34px" id="dt-ans">' + (locked ? "—" : st.answered + "/" + st.players) +
      "</b><span>đã trả lời</span><span>Câu " + (st.index + 1) + "/" + st.total + "</span></div></div>" +
      (st.question.type !== "pin" ? media() : "") + (st.question.options ? opts(null, null) : otherPrompt()) +
      (locked ? '<p class="dt-big">Đã khoá - bấm Công bố đáp án</p>' : "") +
      (lastX2() && !locked ? '<div class="dt-x2" id="dt-x2" hidden><div><b>×2</b><span>CÂU CUỐI · NHÂN ĐÔI ĐIỂM</span><small>Cả điểm thưởng chuỗi cũng nhân đôi</small></div></div>' : "");
  }
  // Cau cuoi nhan doi (Hoan 13/11): bao truoc tren man chieu + dien thoai.
  function lastX2() { return st.is_last && st.settings && st.settings.last_double !== false; }
  function nextNotes() {
    var h = "";
    if (st.settings && st.settings.last_double !== false && st.index + 2 === st.total)
      h += '<div class="dt-note x2">×2 · Câu tiếp theo là câu cuối - nhân đôi điểm (cả thưởng chuỗi)</div>';
    if ((st.steals || []).length) {
      h += '<div class="dt-steals">' + st.steals.slice(0, 5).map(function (e) {
        return "<div>" + (e.blocked ? "🛡️ <b>" + D.esc(e.victim_nick) + "</b> đã chặn cú đánh cắp của <b>" + D.esc(e.thief_nick) + "</b>!" :
          "😈 <b>" + D.esc(e.thief_nick) + "</b> vừa đánh cắp " + D.fmtNum(e.amount) + " điểm của <b>" + D.esc(e.victim_nick) + "</b>!") + "</div>";
      }).join("") + (st.steals.length > 5 ? "<div>+" + (st.steals.length - 5) + " vụ khác</div>" : "") + "</div>";
    }
    if (st.power_open)
      h += '<div class="dt-note pw">🎁 Power-up đã mở trên điện thoại - mọi người chọn trước khi bấm Câu tiếp (' + st.power_open.picked + "/" + st.players + " đã chọn)</div>";
    return h;
  }
  function reveal() {
    var q = st.question, rv = st.reveal || {}, t = st.tally || {}, h = '<div class="dt-qtitle">' + D.esc(qText()) + "</div>";
    if (q.options) {
      var total = Math.max(1, t.total || 0);
      h += '<div class="dt-hbars">' + q.options.map(function (o, i) {
        var n = (t.options || {})[o.id] || 0, ok = (rv.correct || []).indexOf(o.id) >= 0;
        return '<div class="dt-hb"><b>' + n + '</b><i style="height:' + Math.max(4, 100 * n / total) + "%;background:var(--c" + (i + 1) + ");" +
          (rv.correct && rv.correct.length && !ok ? "opacity:.35" : "") + '"></i><span>' + D.LETTERS[i] + (ok ? " ✓" : "") + "</span></div>";
      }).join("") + "</div>" + opts(rv, t);
    } else if (q.type === "slider") {
      h += '<p class="dt-big">Đáp án: ' + rv.answer + (rv.tolerance ? " ± " + rv.tolerance : "") + " " + D.esc(q.unit || "") + "</p>" +
        '<p style="text-align:center">' + (t.values || []).length + " câu trả lời</p>";
    } else if (q.type === "pin") {
      var z = rv.zone || {}, zs = z.shape === "circle" ? "left:" + (z.x - z.r) * 100 + "%;top:" + (z.y - z.r / (z.ar || 1)) * 100 + "%;width:" + z.r * 200 + "%;aspect-ratio:1" :
        "left:" + z.x * 100 + "%;top:" + z.y * 100 + "%;width:" + z.w * 100 + "%;height:" + z.h * 100 + "%";
      h += '<div class="dt-pinbox" style="max-width:min(900px,70vh*1.5);align-self:center"><img src="' + D.esc(D.safeUrl(q.media && q.media.url)) + '" alt=""><span class="dt-zone' +
        (z.shape === "circle" ? " circle" : "") + '" style="' + zs + '"></span>' + (t.pins || []).map(function (p) {
          return '<span class="dt-dot" style="left:' + p[0] * 100 + "%;top:" + p[1] * 100 + '%"></span>';
        }).join("") + "</div>";
    } else if (q.type === "order") {
      var tx = {}; q.items.forEach(function (i) { tx[i.id] = i.text; });
      h += '<div class="dt-olist" style="max-width:720px;align-self:center;width:100%">' + (rv.order || []).map(function (id, i) {
        return '<div class="dt-oitem"><b>' + (i + 1) + "</b>" + D.esc(tx[id]) + "</div>"; }).join("") + "</div>";
    } else if (q.type === "match") {
      var rt = {}; q.rights.forEach(function (r) { rt[r.id] = r.text; });
      h += '<div class="dt-olist" style="max-width:820px;align-self:center;width:100%">' + q.lefts.map(function (l) {
        return '<div class="dt-oitem">' + D.esc(l.text) + " → <b>" + D.esc(rt[(rv.pairs || {})[l.id]]) + "</b></div>"; }).join("") + "</div>";
    } else if (q.type === "type") {
      h += '<p class="dt-big">' + (rv.accept || []).map(D.esc).join(" / ") + "</p>";
    } else if (q.type === "cloud") {
      var mx = Math.max.apply(null, [1].concat((t.words || []).map(function (w) { return w[1]; })));
      h += '<div class="dt-cloud">' + (t.words || []).map(function (w, i) {
        return '<span style="font-size:' + (18 + 42 * w[1] / mx) + "px;color:var(--c" + (i % 6 + 1) + ')">' + D.esc(w[0]) + "</span>"; }).join("") + "</div>";
    }
    if (rv.explain) h += '<div class="dt-side">💡 ' + D.esc(rv.explain) + "</div>";
    return h + nextNotes();
  }
  function rows(list) {
    return '<div class="dt-board" style="max-width:820px;width:100%;align-self:center">' + (list || []).map(function (p) {
      return '<div class="dt-brow" style="font-size:20px"><span class="dt-rk">' + p.rank + "</span>" + D.pcard(p, 44) + '<span class="dt-sc">' + D.fmtNum(p.score) + "</span></div>";
    }).join("") + "</div>";
  }
  function teamRows(list) {
    var mx = Math.max.apply(null, [1].concat((list || []).map(function (t) { return t.score; })));
    return '<div class="dt-board" style="max-width:820px;width:100%;align-self:center">' + (list || []).map(function (t) {
      return '<div class="dt-brow"><span class="dt-rk">' + t.rank + '</span><span class="dt-tname">' + D.esc(t.team) + "<small>" + t.members +
        " người</small></span>" + '<span class="dt-bar" style="background:rgba(255,255,255,.12)"><i style="width:' + (100 * t.score / mx) + '%;background:var(--gold)"></i></span><span class="dt-sc">' +
        D.fmtNum(t.score) + "</span></div>";
    }).join("") + "</div>";
  }
  function board() {
    return '<h1 style="text-align:center">Bảng xếp hạng</h1>' + nextNotes() + rows(st.board) + (st.teams ? '<h2 style="text-align:center">Đường đua phòng ban</h2>' + teamRows(st.teams) : "");
  }
  function final() {
    var f = st.final || {}, pod = f.podium || [];
    var order = [1, 0, 2], hts = ["34vh", "26vh", "20vh"];   // hts theo hang: hang 1 cao nhat
    var h = '<h1 style="text-align:center">🏁 Về đích!</h1><div class="dt-row" style="align-items:flex-end;gap:24px;justify-content:center"><div class="dt-podium">' +
      order.map(function (i) {
        var p = pod[i]; if (!p) return "";
        var aw = (f.awards || []).filter(function (a) { return a.user === p.email; }).map(function (a) { return a.label + (a.gift ? " · " + a.gift : "") + (a.tickets ? " · " + a.tickets + " vé" : ""); });
        return '<div class="dt-pod">' + D.avatar(p.avatar, 76) + '<b style="font-size:20px">' + D.esc(p.nickname) + '</b><span class="dt-mail" style="color:#e9ddff">' +
          D.esc(p.email) + "</span><span>" + D.fmtNum(p.score) + ' điểm</span><span class="dt-small" style="text-align:center">' + D.esc(aw.join(" · ")) +
          '</span><div class="dt-step" style="height:' + hts[i] + '">' + (i + 1) + "</div></div>";
      }).join("") + "</div>" + ((f.teams || []).length ? '<div class="dt-side" style="min-width:300px"><b>Top phòng ban</b>' + (f.teams || []).slice(0, 6).map(function (t) {
        return '<div class="dt-row"><b>' + t.rank + "</b><span>" + D.esc(t.team) + '</span><span class="dt-sp"></span><b>' + D.fmtNum(t.score) + "</b></div>";
      }).join("") + "</div>" : "") + "</div>";
    // Danh sach nhan giai day du (Hoan 13/11): ten, email, phong ban, giai, qua, ve + tai CSV de phat qua.
    var aw = f.awards || [], dept = {};
    (st.lobby || []).forEach(function (p) { dept[p.email] = p.department; });
    if (aw.length) {
      h += '<div class="dt-side dt-awards"><div class="dt-row"><b>Danh sách nhận giải (' + aw.length + ')</b><span class="dt-sp"></span>' +
        '<button class="dt-b sm" id="dt-csv">Tải danh sách (CSV)</button></div><table class="dt-table" style="color:#fff"><thead><tr><th>Giải</th><th>Người chơi</th><th>Email</th><th>Phòng ban</th><th>Quà</th><th>Vé</th></tr></thead><tbody>' +
        aw.map(function (a) {
          return "<tr><td><b>" + D.esc(a.label) + "</b></td><td>" + D.esc(a.nickname) + "</td><td>" + D.esc(a.user) + "</td><td>" + D.esc(a.department || dept[a.user] || "") +
            "</td><td>" + D.esc(a.gift || "") + "</td><td>" + (a.tickets || 0) + "</td></tr>";
        }).join("") + "</tbody></table></div>";
    }
    return h;
  }

  function downloadAwards() {
    var f = st.final || {}, dept = {};
    (st.lobby || []).forEach(function (p) { dept[p.email] = p.department; });
    var q = function (v) { v = String(v == null ? "" : v); return '"' + v.replace(/"/g, '""') + '"'; };
    var rows = [["Giải", "Tên trong game", "Email", "Phòng ban", "Quà", "Vé"]].concat((f.awards || []).map(function (a) {
      return [a.label, a.nickname, a.user, a.department || dept[a.user] || "", a.gift || "", a.tickets || 0];
    }));
    var blob = new Blob(["\ufeff" + rows.map(function (r) { return r.map(q).join(","); }).join("\r\n")], { type: "text/csv;charset=utf-8" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "giai-quiz-" + (st.code || "phong") + ".csv";
    document.body.appendChild(link); link.click(); link.remove();
  }

  // ----------------------------------------------------------- quan ly nguoi choi --
  function players() {
    return '<div class="dt-side"><div class="dt-row"><b>Người chơi</b><span class="dt-sp"></span><span class="dt-small">Cờ chỉ để xem - không tự trừ điểm</span></div>' +
      (st.flags || []).map(function (f) {
        return '<div class="dt-flag">' + D.icon("flag") + " <b>" + D.esc(f.nickname) + "</b> · " + D.esc(f.email) + " — " + f.flags.map(function (x) { return FLAG[x] || x; }).join(", ") + "</div>";
      }).join("") + '<table class="dt-table" style="color:#fff"><tbody>' + st.lobby.map(function (p) {
        return "<tr><td>" + D.pcard(p, 30) + (p.kicked ? ' <span class="dt-chip bad">đã mời ra</span>' : "") + "</td><td>" + D.esc(p.department) + '</td><td style="text-align:right;white-space:nowrap">' +
          '<button class="dt-b sm" data-op="rename" data-u="' + D.esc(p.email) + '">Đổi tên</button> ' +
          (st.settings.guard !== "basic" ? '<button class="dt-b sm" data-op="reset_device" data-u="' + D.esc(p.email) + '">Cho đổi máy</button> ' : "") +
          (p.flags.length ? '<button class="dt-b sm" data-op="clear_flags" data-u="' + D.esc(p.email) + '">Bỏ cờ</button> ' : "") +
          (p.kicked ? '<button class="dt-b sm" data-op="unkick" data-u="' + D.esc(p.email) + '">Cho vào lại</button>' :
            '<button class="dt-b sm danger" data-op="kick" data-u="' + D.esc(p.email) + '">Mời ra</button>') + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }
  function bindPlayers() {
    D.qsa(root, "[data-op]").forEach(function (b) {
      b.onclick = function () {
        var args = { session: session, user: b.dataset.u, op: b.dataset.op };
        if (args.op === "rename") { var n = window.prompt("Tên mới (tối đa 16 ký tự)"); if (!n) return; args.nickname = n; }
        if (args.op === "kick" && !window.confirm("Mời " + args.user + " ra khỏi phòng?")) return;
        D.busy(b, true);
        D.api("room_player", args, true).then(function () { D.toast("Đã cập nhật."); load(0); }, function (e) { D.busy(b, false); D.toast(D.msg(e), true); });
      };
    });
  }

  root.innerHTML = '<div class="dt-proj"><div class="dt-center"><p>Đang mở phòng…</p></div></div>';
  load(0);
  D.onRoom(session, function () { load(0); });
})();
