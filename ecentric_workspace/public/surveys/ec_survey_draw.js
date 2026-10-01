// Copyright (c) 2026, eCentric and contributors
// ec_survey_draw.js -- hieu ung QUAY SO MAY MAN / DUA VE DICH (PO Hoan duyet mockup v2.1, 01/10/2026).
//
// Dung chung cho popup trang chu ("Hom nay o eCentric", qua ec_home_popup.bundle.js) va trang
// /khao-sat/lam. KHONG tu goi mang: noi goi dua du lieu (draw_feed.py -> "draws") va mot ham
// `reload()` de lay ban moi khi toi gio.
//
//   ECSvyDraw.mount(el, draw, { serverNow, reload, onWin })   ve + tu chay theo gio server
//   ECSvyDraw.unmount(el)                                      go hen gio / khung hinh
//
// Trang thai (server quyet): countdown (T-5 -> T) -> live (T -> T+3 phut) -> done (toi het ngay).
// Ket qua do SERVER chot luc T; o day chi phat lai hieu ung dung ket qua do. Mo trang muon thi
// thay ket qua ngay, co nut "Xem lai". Dong ho canh theo gio server (serverNow), khong theo may.
(function () {
  "use strict";
  if (window.ECSvyDraw) return;

  var POLL_MS = 5000, POLL_MAX = 60;          // cho ket qua toi da ~5 phut sau gio quay (job chay moi phut)
  var LIVE_COLORS = ["#ef4444", "#f97316", "#eab308", "#2563eb", "#16a34a", "#9333ea", "#db2777", "#0d9488", "#dc2626", "#2C3DA6", "#0ea5e9", "#65a30d"];
  var CSS = [
    ".ecd{--navy:#2C3DA6;--pink:#EF7CAF;--gold:#FFC000;--ink:#111827;--ink3:#6b7280;--line:#e5e7eb;font-family:inherit;color:var(--ink);display:flex;flex-direction:column;min-width:0}",
    ".ecd *{box-sizing:border-box}",
    ".ecd-head{color:#fff;padding:16px 20px;display:flex;flex-wrap:wrap;gap:10px 16px;justify-content:space-between;align-items:center;position:relative;overflow:hidden}",
    ".ecd-head.num{background:linear-gradient(120deg,#2C3DA6,#7b3fe4 60%,#EF7CAF)}",
    ".ecd-head.race{background:linear-gradient(120deg,#0f9f75,#0ea5e9 55%,#2C3DA6)}",
    ".ecd-head h3{margin:4px 0 0;font-size:21px;font-weight:800;letter-spacing:-.3px;line-height:1.25;color:#fff}",
    ".ecd-head p{margin:2px 0 0;font-size:12.5px;opacity:.88}",
    ".ecd-chip{display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.2);border-radius:999px;padding:2px 10px;font-size:11.5px;font-weight:800;letter-spacing:.3px}",
    ".ecd-live{width:8px;height:8px;border-radius:50%;background:#ef4444;box-shadow:0 0 0 0 rgba(239,68,68,.7);animation:ecd-pulse 1.2s infinite}",
    "@keyframes ecd-pulse{70%{box-shadow:0 0 0 7px rgba(239,68,68,0)}100%{box-shadow:0 0 0 0 rgba(239,68,68,0)}}",
    ".ecd-mine{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.3);border-radius:12px;padding:6px 12px;font-size:12px;text-align:right}",
    ".ecd-mine b{display:block;font-size:20px;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:.06em}",
    ".ecd-body{padding:16px 20px;display:flex;flex-direction:column;gap:10px}",
    ".ecd-clock{display:flex;flex-direction:column;align-items:center;gap:6px;text-align:center;padding:10px 0}",
    ".ecd-clock .big{font-size:56px;font-weight:800;font-variant-numeric:tabular-nums;color:var(--navy);line-height:1;letter-spacing:.02em}",
    ".ecd-clock .lbl{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--ink3)}",
    ".ecd-muted{color:var(--ink3);font-size:12.5px}",
    ".ecd-row{display:grid;grid-template-columns:minmax(110px,1fr) auto minmax(150px,1.3fr);gap:14px;align-items:center;border:1px solid var(--line);border-radius:14px;padding:10px 14px;background:#fafbff}",
    ".ecd-row .pz small{display:block;font-size:10.5px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;color:var(--ink3)}",
    ".ecd-row .pz b{font-size:14px}",
    ".ecd-reels{display:flex;gap:6px}",
    ".ecd-reel{width:42px;height:56px;border-radius:10px;background:#0f172a;overflow:hidden;position:relative;box-shadow:inset 0 -6px 12px rgba(0,0,0,.45),inset 0 6px 12px rgba(0,0,0,.45)}",
    ".ecd-strip{position:absolute;left:0;right:0;top:0;will-change:transform}",
    ".ecd-strip span,.ecd-reel>span{display:block;height:56px;line-height:56px;text-align:center;font-size:34px;font-weight:800;color:var(--gold);font-variant-numeric:tabular-nums}",
    ".ecd-reels.idle .ecd-strip{animation:ecd-roll .6s linear infinite}",
    "@keyframes ecd-roll{to{transform:translateY(-20%)}}",
    ".ecd-res{min-width:0;font-size:13px}",
    ".ecd-win{display:inline-flex;align-items:center;gap:8px;background:#e7f8ee;color:#17683a;border-radius:999px;padding:4px 12px 4px 4px;font-weight:700;max-width:100%}",
    ".ecd-win.me{background:var(--gold);color:#3a2c00}",
    ".ecd-av{width:26px;height:26px;border-radius:50%;background:var(--navy);color:#fff;display:grid;place-items:center;font-size:10.5px;font-weight:800;flex:none}",
    ".ecd-none{display:inline-block;background:#f1f2f6;color:var(--ink3);border-radius:999px;padding:4px 12px;font-weight:600}",
    ".ecd-wait{color:var(--ink3);font-style:italic}",
    ".ecd-pop{animation:ecd-popin .35s ease}",
    "@keyframes ecd-popin{from{transform:scale(.6);opacity:0}}",
    ".ecd-foot{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between}",
    ".ecd-btn{appearance:none;border:1px solid var(--line);background:#fff;border-radius:9px;padding:7px 14px;font:inherit;font-size:13px;font-weight:700;color:#374151;cursor:pointer}",
    ".ecd-btn:hover{border-color:var(--navy);color:var(--navy)}",
    ".ecd-note{background:#fff8e1;color:#7a5a00;border-radius:10px;padding:8px 12px;font-size:12.5px}",
    ".ecd-track{position:relative;border-radius:14px;overflow:hidden;background:#334155}",
    ".ecd-track canvas{display:block;width:100%}",
    ".ecd-podium{display:flex;flex-wrap:wrap;gap:8px}",
    ".ecd-pod{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:999px;padding:4px 14px 4px 4px;background:#fff;font-size:13px}",
    ".ecd-pod i{font-style:normal;width:26px;height:26px;border-radius:50%;display:grid;place-items:center;font-weight:800;color:#111827}",
    ".ecd-pod.me{border-color:var(--gold);background:#fffbea}",
    ".ecd-confetti{position:absolute;inset:0;pointer-events:none;overflow:hidden}",
    ".ecd-confetti i{position:absolute;top:-14px;width:8px;height:13px;border-radius:2px;animation:ecd-fall 2.4s ease-in forwards}",
    "@keyframes ecd-fall{to{transform:translateY(520px) rotate(640deg)}}",
    "@media (max-width:640px){.ecd-row{grid-template-columns:1fr auto}.ecd-row .ecd-res{grid-column:1/-1}.ecd-reel{width:34px;height:46px}.ecd-strip span,.ecd-reel>span{height:46px;line-height:46px;font-size:28px}.ecd-clock .big{font-size:44px}}",
    "@media (prefers-reduced-motion:reduce){.ecd *{animation:none!important;transition:none!important}}"
  ].join("\n");

  function injectCss() {
    if (document.getElementById("ecd-css")) return;
    var st = document.createElement("style");
    st.id = "ecd-css";
    st.textContent = CSS;
    document.head.appendChild(st);
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function parse(s) {                                   // "YYYY-MM-DD HH:MM:SS" (gio site) -> ms
    var m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(s || "");
    return m ? new Date(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)).getTime() : 0;
  }
  function hhmm(s) { return String(s || "").slice(11, 16); }
  function initials(n) {
    var p = String(n || "").trim().split(/\s+/);
    return ((p.length > 1 ? p[p.length - 2][0] : "") + (p[p.length - 1] || "?")[0]).toUpperCase();
  }
  var RANKS = ["", "Giải nhất", "Giải nhì", "Giải ba"];
  function rankLabel(r) { return RANKS[r] || "Giải " + r; }
  function digits(d) { return Math.max(3, String((d.range || [1, 100])[1]).length); }
  function reduced() { return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; }

  // ------------------------------------------------------------------ khung chung --
  function headHTML(c) {
    var d = c.draw, race = d.mode === "race";
    var chip = c.phase === "countdown" ? "Sắp " + (race ? "đua" : "quay") + " · " + hhmm(d.draw_at)
      : c.phase === "live" ? '<span class="ecd-live"></span>TRỰC TIẾP' : race ? "Đã về đích" : "Đã quay xong";
    var sub = race ? (d.racer_total || 0) + " xe · ai nộp phiếu cũng có xe · " + topN(d) + " người về đầu nhận quà"
      : (d.holders || 0) + " người giữ số · dải " + pad(1, d) + "-" + pad(d.range[1], d) + " · " + units(d).length + " lượt quay";
    var mine = race ? (d.joined ? '<div class="ecd-mine">Xe của bạn<b>Sẵn sàng</b></div>' : "")
      : (d.my_number ? '<div class="ecd-mine">Số của bạn<b>' + esc(d.my_number) + "</b></div>" : "");
    return '<div class="ecd-head ' + (race ? "race" : "num") + '"><div><span class="ecd-chip">' + chip + "</span><h3>" + esc(d.title) + "</h3><p>" + esc(sub) + "</p></div>" + mine + "</div>";
  }
  function pad(n, d) { var s = String(n); while (s.length < digits(d)) s = "0" + s; return s; }
  function topN(d) { var n = 0; (d.prizes || []).forEach(function (p) { n += p.quantity; }); return n; }
  function units(d) {                                    // giai nho quay truoc (giong server)
    var out = [];
    (d.prizes || []).slice().reverse().forEach(function (p) { for (var i = 0; i < p.quantity; i++) out.push(p); });
    return out;
  }

  function clockHTML(c) {
    var d = c.draw, race = d.mode === "race";
    var mine = race ? (d.joined ? "Xe của bạn đã vào vạch xuất phát." : "Bạn chưa nộp phiếu nên chưa có xe - vẫn xem được trực tiếp.")
      : (d.my_number ? "Số của bạn: <b>" + esc(d.my_number) + "</b>." : "Bạn chưa giữ số nào - vẫn xem được trực tiếp.");
    return '<div class="ecd-clock"><span class="lbl">Bắt đầu sau</span><span class="big" data-ecd-clock>--:--</span>' +
      '<span class="ecd-muted">Đúng ' + esc(hhmm(d.draw_at)) + " " + (race ? "xe tự chạy" : "máy tự quay") + ", bạn không cần làm gì. " + mine + "</span></div>";
  }

  // ------------------------------------------------------------------ quay so --
  function reelsHTML(num, n, state) {
    var h = '<div class="ecd-reels' + (state === "idle" ? " idle" : "") + '">';
    for (var k = 0; k < n; k++) {
      if (state === "static") { h += '<div class="ecd-reel"><span>' + esc(num ? num.charAt(k) : "?") + "</span></div>"; continue; }
      h += '<div class="ecd-reel"><div class="ecd-strip">';
      for (var j = 0; j < 50; j++) h += "<span>" + (j % 10) + "</span>";
      h += "</div></div>";
    }
    return h + "</div>";
  }
  function winHTML(r, pop) {
    if (!r.name) return '<span class="ecd-none' + (pop ? " ecd-pop" : "") + '">Không ai giữ số này · quà để lại</span>';
    return '<span class="ecd-win' + (r.is_me ? " me" : "") + (pop ? " ecd-pop" : "") + '"><span class="ecd-av">' + esc(initials(r.name)) + "</span>" + esc(r.name) + (r.is_me ? " (bạn)" : "") + "</span>";
  }
  function numberBody(c, mode) {
    var d = c.draw, n = digits(d), list = d.results && d.results.length ? d.results : null, h = "";
    var rows = list || units(d).map(function (p) { return { rank: p.rank, prize: p.label }; });
    rows.forEach(function (r, i) {
      var state = mode === "static" ? "static" : mode === "idle" ? "idle" : "spin";
      var res = mode === "static" ? winHTML(r) : '<span class="ecd-wait" data-ecd-res="' + i + '">' + (mode === "idle" ? "Đang chốt kết quả..." : "Đang quay...") + "</span>";
      h += '<div class="ecd-row"><div class="pz"><small>' + esc(rankLabel(r.rank)) + "</small><b>" + esc(r.prize) + "</b></div>" +
        '<div data-ecd-reel="' + i + '">' + reelsHTML(mode === "static" ? r.number : "", n, state) + '</div><div class="ecd-res">' + res + "</div></div>";
    });
    return h;
  }
  function spinNumbers(c) {
    var d = c.draw, list = d.results || [], n = digits(d), last = 0;
    list.forEach(function (r, i) {
      var box = c.el.querySelector('[data-ecd-reel="' + i + '"]');
      if (!box) return;
      var strips = box.querySelectorAll(".ecd-strip");
      Array.prototype.forEach.call(strips, function (s, k) {
        var digit = +String(r.number).charAt(k) || 0, dur = 1.6 + i * 1.4 + k * 0.45;
        s.style.transition = "none"; s.style.transform = "translateY(0)";
        void s.offsetWidth;
        s.style.transition = "transform " + dur + "s cubic-bezier(.15,.7,.12,1)";
        s.style.transform = "translateY(-" + ((40 + digit) * 100 / 50) + "%)";
      });
      var end = (1.6 + i * 1.4 + (n - 1) * 0.45) * 1000 + 150;
      last = Math.max(last, end);
      c.timers.push(setTimeout(function () {
        var el = c.el.querySelector('[data-ecd-res="' + i + '"]');
        if (el) el.outerHTML = winHTML(r, true);
        if (r.is_me) celebrate(c);
      }, reduced() ? 0 : end));
    });
    c.timers.push(setTimeout(function () { finish(c); }, reduced() ? 0 : last + 300));
  }

  // ------------------------------------------------------------------ dua ve dich --
  function lanesOf(d) {
    if (d.racers && d.racers.length) return d.racers;
    var n = Math.min(Math.max(d.racer_total || 0, 1), 12), out = [];
    for (var i = 0; i < n; i++) out.push({ place: 0, short: i === 0 && d.joined ? "Bạn" : "", is_me: i === 0 && d.joined });
    return out;
  }
  function raceBody(c) {
    var d = c.draw, lanes = lanesOf(d), more = (d.racer_total || 0) - lanes.length;
    if (settled(d) && !(d.racers && d.racers.length)) return '<div class="ecd-note">Không có xe nào tham gia cuộc đua này.</div>';
    return '<div class="ecd-track"><canvas data-ecd-race height="' + (lanes.length * 44 + 54) + '"></canvas></div>' +
      (more > 0 && d.racers && d.racers.length ? '<span class="ecd-muted">Hiện ' + lanes.length + " xe (người về đầu và bạn) · cùng " + more + " xe khác trên đường đua.</span>" : "") +
      '<div class="ecd-podium" data-ecd-podium>' + (c.phase === "done" || c.played ? podiumHTML(d) : "") + "</div>";
  }
  function podiumHTML(d) {
    var g = ["#FFC000", "#c0c7d6", "#e0915a"];
    return (d.results || []).map(function (w, i) {
      return '<span class="ecd-pod' + (w.is_me ? " me" : "") + '"><i style="background:' + (g[i] || "#eef0fb") + '">' + w.place + "</i><b>" + esc(w.name) + (w.is_me ? " (bạn)" : "") + '</b><span class="ecd-muted">' + esc(w.prize) + "</span></span>";
    }).join("");
  }
  function cart(ctx, x, y, color, moving, t) {
    ctx.save(); ctx.translate(x, y);
    if (moving) {
      ctx.strokeStyle = "rgba(255,255,255,.55)"; ctx.lineWidth = 2;
      for (var s = 0; s < 3; s++) { var o = (t * 0.04 + s * 7) % 18; ctx.beginPath(); ctx.moveTo(-34 - o, -8 + s * 7); ctx.lineTo(-22 - o, -8 + s * 7); ctx.stroke(); }
    }
    ctx.fillStyle = "#d4a373"; ctx.fillRect(-12, -24, 20, 14); ctx.fillStyle = "#b07d4f"; ctx.fillRect(-3, -24, 3, 14);
    ctx.fillStyle = "#fff"; ctx.font = "700 7px Inter, sans-serif"; ctx.fillText("eC", -11, -14);
    ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(-20, -12); ctx.lineTo(18, -12); ctx.lineTo(13, 4); ctx.lineTo(-15, 4); ctx.closePath(); ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,.5)"; ctx.lineWidth = 1.2;
    for (var k = -12; k < 14; k += 7) { ctx.beginPath(); ctx.moveTo(k, -10); ctx.lineTo(k - 1, 2); ctx.stroke(); }
    ctx.strokeStyle = "#1f2937"; ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(-20, -12); ctx.lineTo(-27, -22); ctx.stroke();
    var a = moving ? t * 0.02 : 0;
    [[-10, 9], [9, 9]].forEach(function (w) {
      ctx.fillStyle = "#111827"; ctx.beginPath(); ctx.arc(w[0], w[1], 5, 0, 2 * Math.PI); ctx.fill();
      ctx.strokeStyle = "#9ca3af"; ctx.lineWidth = 1.5; ctx.beginPath();
      ctx.moveTo(w[0] + Math.cos(a) * 3, w[1] + Math.sin(a) * 3); ctx.lineTo(w[0] - Math.cos(a) * 3, w[1] - Math.sin(a) * 3); ctx.stroke();
    });
    ctx.restore();
  }
  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  // mode: "idle" (cho o vach xuat phat) | "run" (chay) | "end" (ve dich, dung yen)
  function runRace(c, mode) {
    var cv = c.el.querySelector("[data-ecd-race]");
    if (!cv) return;
    var lanes = lanesOf(c.draw), dpr = window.devicePixelRatio || 1;
    var W = Math.max(cv.parentNode.clientWidth, 320), H = lanes.length * 44 + 54;
    cv.width = W * dpr; cv.height = H * dpr; cv.style.height = H + "px";
    var ctx = cv.getContext("2d"); ctx.scale(dpr, dpr);
    var top = 44, lane = 44, x0 = 120, xf = W - 96, L = xf - x0;
    var fin = lanes.map(function (r, i) { var p = (r.place || i + 1) - 1; return 5200 + p * 230 + (p % 3) * 40; });
    var maxT = Math.max.apply(null, fin);
    var start = performance.now() - (mode === "end" || reduced() ? maxT + 1000 : 0);
    if (c.raf) cancelAnimationFrame(c.raf);
    function pos(i, t) {
      if (mode === "idle") return x0;
      var p = Math.min(t / fin[i], 1), wob = 0.06 * Math.sin(p * Math.PI * (2 + i % 3) + i) * p * (1 - p) * 4;
      return x0 + L * Math.max(0, Math.min(1, p + wob * (1 - p)));
    }
    function frame(now) {
      if (!c.el.isConnected) return;
      var t = now - start;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = "#1e293b"; ctx.fillRect(0, 0, W, top - 6);
      ctx.fillStyle = "#fff"; ctx.font = "800 13px Inter, sans-serif"; ctx.fillText("KHO eCentric", 12, 25);
      ctx.textAlign = "right"; ctx.fillText("GIAO THÀNH CÔNG", W - 12, 25); ctx.textAlign = "left";
      for (var i = 0; i < lanes.length; i++) {
        var y = top + i * lane;
        ctx.fillStyle = i % 2 ? "#3b4a61" : "#364357"; ctx.fillRect(0, y, W, lane);
        ctx.strokeStyle = "rgba(255,255,255,.22)"; ctx.setLineDash([14, 12]); ctx.beginPath(); ctx.moveTo(0, y + lane); ctx.lineTo(W, y + lane); ctx.stroke(); ctx.setLineDash([]);
      }
      for (var r = 0; r < Math.ceil((H - top) / 10); r++) for (var q = 0; q < 3; q++) { ctx.fillStyle = (r + q) % 2 ? "#fff" : "#111827"; ctx.fillRect(xf + 14 + q * 8, top + r * 10, 8, 10); }
      ctx.fillStyle = "#22c55e"; ctx.fillRect(x0 - 30, top, 3, H - top);
      var order = lanes.map(function (_, k) { return [k, pos(k, t)]; }).sort(function (a, b) { return b[1] - a[1]; });
      lanes.forEach(function (rc, k) {
        var yy = top + k * lane + lane / 2 + 4, x = pos(k, t), moving = mode === "run" && t < fin[k];
        cart(ctx, x, yy, LIVE_COLORS[k % LIVE_COLORS.length], moving, t);
        var label = rc.is_me ? "Bạn" : (rc.short || (rc.place ? "#" + rc.place : ""));
        if (label) {
          ctx.font = "700 11.5px Inter, sans-serif";
          var w = ctx.measureText(label).width + 14;
          ctx.fillStyle = rc.is_me ? "#FFC000" : "#fff"; rr(ctx, x - w - 32, yy - 19, w, 18, 9); ctx.fill();
          ctx.fillStyle = "#111827"; ctx.fillText(label, x - w - 25, yy - 6);
        }
        if (mode !== "idle" && !moving && rc.place) {
          ctx.fillStyle = rc.place <= 3 ? ["#FFC000", "#e5e7eb", "#e0915a"][rc.place - 1] : "rgba(255,255,255,.85)";
          ctx.beginPath(); ctx.arc(xf + 64, yy - 5, 11, 0, 2 * Math.PI); ctx.fill();
          ctx.fillStyle = "#111827"; ctx.font = "800 11px Inter, sans-serif"; ctx.textAlign = "center"; ctx.fillText(rc.place, xf + 64, yy - 1); ctx.textAlign = "left";
        }
      });
      if (mode === "run") {
        ctx.fillStyle = "rgba(15,23,42,.78)"; rr(ctx, W / 2 - 150, 7, 300, 26, 13); ctx.fill();
        ctx.fillStyle = "#fff"; ctx.font = "700 11.5px Inter, sans-serif"; ctx.textAlign = "center";
        ctx.fillText("Dẫn đầu: " + order.slice(0, 3).map(function (o, j) { var l = lanes[o[0]]; return (j + 1) + ". " + (l.is_me ? "Bạn" : l.short || "?"); }).join("   "), W / 2, 24);
        ctx.textAlign = "left";
      }
      if (mode === "run" && t < maxT + 200) { c.raf = requestAnimationFrame(frame); return; }
      if (mode === "run") {
        var pd = c.el.querySelector("[data-ecd-podium]");
        if (pd) pd.innerHTML = podiumHTML(c.draw);
        if ((c.draw.results || []).some(function (w) { return w.is_me; })) celebrate(c);
        finish(c);
      }
    }
    c.raf = requestAnimationFrame(frame);
  }

  // ------------------------------------------------------------------ dieu phoi --
  function celebrate(c) {
    if (reduced() || c.el.querySelector(".ecd-confetti")) return;
    var box = document.createElement("div"), colors = ["#2C3DA6", "#FFC000", "#EF7CAF", "#10b981", "#0ea5e9"];
    box.className = "ecd-confetti";
    for (var i = 0; i < 70; i++) {
      var p = document.createElement("i");
      p.style.left = Math.random() * 100 + "%"; p.style.background = colors[i % colors.length];
      p.style.animationDelay = Math.random() * 0.8 + "s";
      box.appendChild(p);
    }
    c.root.appendChild(box);
    c.timers.push(setTimeout(function () { box.remove(); }, 3800));
    if (c.opts.onWin) try { c.opts.onWin(c.draw); } catch (e) { /* bo qua */ }
  }
  function finish(c) {
    c.played = true;
    var f = c.el.querySelector("[data-ecd-foot]");
    if (f) f.innerHTML = footHTML(c);
  }
  function footHTML(c) {
    var d = c.draw, hasRes = settled(d);
    var note = d.mode === "race" ? "Kết quả hiện trong popup tới hết ngày. Người về đầu nhận thông báo riêng kèm cách nhận quà."
      : "Số không ai giữ thì quà đó để lại. Kết quả hiện trong popup tới hết ngày; người trúng nhận thông báo riêng.";
    return (hasRes ? '<span class="ecd-note">' + note + "</span>" : "<span></span>") +
      (hasRes && c.played ? '<button type="button" class="ecd-btn" data-ecd-replay>' + (d.mode === "race" ? "Xem lại cuộc đua" : "Xem lại hiệu ứng quay") + "</button>" : "");
  }

  // "Da chot" theo co `drawn` cua server - cuoc dua 0 xe / quay so khong ai giu so van la da chot.
  function settled(d) { return !!(d.drawn || (d.results && d.results.length)); }
  function render(c, animate) {
    var d = c.draw, race = d.mode === "race", hasRes = settled(d), body;
    clearTimers(c);
    if (c.phase === "countdown") body = clockHTML(c) + (race ? raceBody(c) : "");
    else if (!hasRes) body = race ? raceBody(c) : numberBody(c, "idle");
    else body = race ? raceBody(c) : numberBody(c, animate ? "spin" : "static");
    c.root.innerHTML = headHTML(c) + '<div class="ecd-body">' + body + '<div class="ecd-foot" data-ecd-foot></div></div>';
    if (!animate && hasRes) c.played = true;
    finishFootOnly(c);
    if (race) runRace(c, c.phase === "countdown" || !hasRes ? "idle" : animate ? "run" : "end");
    else if (animate && hasRes) spinNumbers(c);
    if (c.phase === "countdown") tickClock(c);
    if (c.phase !== "countdown" && !hasRes) poll(c);
  }
  function finishFootOnly(c) { var f = c.el.querySelector("[data-ecd-foot]"); if (f) f.innerHTML = footHTML(c); }

  function now(c) { return Date.now() + c.skew; }
  function tickClock(c) {
    var at = parse(c.draw.draw_at);
    function step() {
      var left = Math.max(0, Math.round((at - now(c)) / 1000));
      var el = c.el.querySelector("[data-ecd-clock]");
      if (el) el.textContent = (left >= 3600 ? Math.floor(left / 3600) + ":" : "") + ("0" + Math.floor(left % 3600 / 60)).slice(-2) + ":" + ("0" + left % 60).slice(-2);
      if (left <= 0) { c.phase = "live"; render(c, false); return; }
      c.timers.push(setTimeout(step, 1000 - (now(c) % 1000)));
    }
    step();
  }
  function poll(c) {
    if (!c.opts.reload || c.polls >= POLL_MAX) return;
    c.timers.push(setTimeout(function () {
      c.polls += 1;
      Promise.resolve(c.opts.reload(c.draw.name)).then(function (fresh) {
        if (!c.el.isConnected || c.el.__ecd !== c) return;      // da go / da gan luot khac
        if (fresh && settled(fresh)) {
          c.draw = fresh; c.phase = "live"; render(c, true);
        } else poll(c);
      }, function () { poll(c); });
    }, POLL_MS));
  }
  function clearTimers(c) {
    (c.timers || []).forEach(clearTimeout);
    c.timers = [];
    if (c.raf) { cancelAnimationFrame(c.raf); c.raf = null; }
  }

  function mount(el, draw, opts) {
    if (!el || !draw) return null;
    injectCss();
    unmount(el);
    opts = opts || {};
    var c = { el: el, draw: draw, opts: opts, timers: [], polls: 0, played: false,
              skew: opts.serverNow ? parse(opts.serverNow) - Date.now() : 0 };
    el.innerHTML = '<div class="ecd"></div>';
    c.root = el.firstChild;
    c.root.style.position = "relative";
    var hasRes = settled(draw);
    c.phase = draw.state === "countdown" && parse(draw.draw_at) > now(c) ? "countdown" : draw.state === "done" ? "done" : "live";
    // "live" ma DA co ket qua luc mo: nguoi xem vua toi trong 3 phut dang quay -> van chay hieu ung.
    render(c, c.phase === "live" && hasRes);
    el.addEventListener("click", c.onClick = function (e) {
      if (!e.target.closest || !e.target.closest("[data-ecd-replay]")) return;
      c.played = false; render(c, true);
    });
    el.__ecd = c;
    return c;
  }

  function unmount(el) {
    var c = el && el.__ecd;
    if (!c) return;
    clearTimers(c);
    el.removeEventListener("click", c.onClick);
    el.__ecd = null;
  }

  window.ECSvyDraw = { mount: mount, unmount: unmount, _parse: parse };
})();
