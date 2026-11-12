// Copyright (c) 2026, eCentric and contributors
// Nhac cho MAY CHIEU quiz (/quiz/chieu) - chi phat o may chieu, dien thoai nguoi choi im lang.
//   * Sanh cho: bai YouTube nguoi dan chon (trinh phat YouTube chinh thuc, an khoi man hinh).
//   * Luc choi: link YouTube thu hai neu nguoi dan dan vao; de trong = nhac khong loi vui nhe do
//     trinh duyet TU TAO (Web Audio) - khong file, khong ban quyen. Cau dang mo thi nho lai.
// Trinh duyet chi cho phat tieng sau mot cu bam: nut 🎵 tren thanh tren; da bat tu lan truoc thi
// cu bam dau tien bat ky tren trang se mo tieng. Cai dat luu tren chinh may chieu (localStorage).
// Giao dien: ECDtMusic.attach(slot, phase) - goi sau moi lan ve lai man chieu.
(function () {
  "use strict";
  var KEY = "ecdt-music-v1";
  var DEFAULT_YT = "https://www.youtube.com/watch?v=WoCUczmsNz0";
  var cfg = load();
  var phase = "", slot = null, pop = null;
  var started = false;        // da co cu bam cua nguoi dung -> duoc phat tieng
  var want = "";              // "yt" | "synth" | ""

  function load() {
    var c = { on: false, vol: 0.7, yt: DEFAULT_YT, ytGame: "", game: true };
    try {
      var s = JSON.parse(window.localStorage.getItem(KEY) || "null");
      if (s && typeof s === "object") {
        if (typeof s.on === "boolean") c.on = s.on;
        if (typeof s.vol === "number" && s.vol >= 0 && s.vol <= 1) c.vol = s.vol;
        if (typeof s.yt === "string") c.yt = s.yt;
        if (typeof s.ytGame === "string") c.ytGame = s.ytGame;
        if (typeof s.game === "boolean") c.game = s.game;
      }
    } catch (e) { /* che do rieng tu / chan luu tru: dung mac dinh */ }
    return c;
  }
  function save() { try { window.localStorage.setItem(KEY, JSON.stringify(cfg)); } catch (e) { /* bo qua */ } }
  function toast(m, bad) { if (window.ECDt && window.ECDt.toast) window.ECDt.toast(m, bad); }

  // ---------------------------------------------------------------- YouTube --
  var yt = { player: null, ready: false, loading: false, id: "", start: 0, bad: {}, apiFail: false };

  function parseYt(url) {
    var u = String(url || "").trim(), m;
    m = u.match(/(?:youtu\.be\/|[?&]v=|\/embed\/|\/shorts\/|\/live\/)([A-Za-z0-9_-]{11})/) || u.match(/^([A-Za-z0-9_-]{11})$/);
    if (!m) return null;
    var t = u.match(/[?&](?:t|start)=(\d+)/);
    return { id: m[1], start: t ? parseInt(t[1], 10) : 0 };
  }
  function ytUsable(url) { var v = parseYt(url); return !!v && !yt.bad[v.id] && !yt.apiFail; }

  // Mot trinh phat YouTube an dung chung: doi bai bang loadVideoById, het bai thi tu phat lai.
  function ytEnsure(url) {
    var v = parseYt(url);
    if (!v) return;
    if (yt.player) {
      if (yt.ready && yt.id !== v.id) {
        yt.id = v.id; yt.start = v.start;
        try { yt.player.loadVideoById({ videoId: v.id, startSeconds: v.start }); } catch (e) { /* bo qua */ }
      } else if (!yt.ready) { yt.id = v.id; yt.start = v.start; }
      return;
    }
    yt.id = v.id; yt.start = v.start;
    var host = document.getElementById("ecdt-yt-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "ecdt-yt-host";
      host.setAttribute("aria-hidden", "true");
      host.style.cssText = "position:fixed;left:-9999px;top:0;width:240px;height:200px;overflow:hidden;pointer-events:none";
      document.body.appendChild(host);
    }
    host.innerHTML = '<div id="ecdt-yt"></div>';
    var make = function () {
      try {
        var first = yt.id;
        yt.player = new window.YT.Player("ecdt-yt", {
          width: 240, height: 200, videoId: first,
          playerVars: { autoplay: 0, controls: 0, start: yt.start, playsinline: 1, rel: 0 },
          events: {
            onReady: function () {
              yt.ready = true;
              if (yt.id !== first) { try { yt.player.cueVideoById({ videoId: yt.id, startSeconds: yt.start }); } catch (e) { /* bo qua */ } }
              apply();
            },
            onStateChange: function (ev) {                 // 0 = het bai -> phat lai tu dau
              if (ev && ev.data === 0 && want === "yt") { try { yt.player.seekTo(yt.start || 0, true); yt.player.playVideo(); } catch (e) { /* bo qua */ } }
            },
            onError: function () { yt.bad[yt.id] = true; ytFail("Video YouTube này không cho phát nhúng - đang dùng nhạc nền thay thế."); }
          }
        });
      } catch (e) { yt.apiFail = true; ytFail("Không mở được trình phát YouTube - đang dùng nhạc nền thay thế."); }
    };
    if (window.YT && window.YT.Player) return make();
    if (yt.loading) { yt.pending = make; return; }
    yt.loading = true; yt.pending = make;
    var prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = function () {
      yt.loading = false;
      if (typeof prev === "function") { try { prev(); } catch (e) { /* bo qua */ } }
      if (yt.pending) { var f = yt.pending; yt.pending = null; f(); }
    };
    var sc = document.createElement("script");
    sc.src = "https://www.youtube.com/iframe_api";
    sc.async = true;
    sc.onerror = function () { yt.loading = false; yt.apiFail = true; ytFail("Không tải được YouTube (mạng chặn?) - đang dùng nhạc nền thay thế."); };
    document.head.appendChild(sc);
    setTimeout(function () { if (!yt.ready && !yt.apiFail && want === "yt") { yt.apiFail = true; ytFail("YouTube tải quá lâu - đang dùng nhạc nền thay thế."); } }, 12000);
  }
  function ytFail(msg) {
    if (cfg.on && started) toast(msg, true);
    apply();
  }
  function ytVol() { return Math.round(cfg.vol * 100 * (phase === "question" ? 0.5 : 1)); }
  function ytPlay() {
    if (!yt.player || !yt.ready) return;
    try { yt.player.setVolume(ytVol()); yt.player.unMute(); if (yt.player.getPlayerState() !== 1) yt.player.playVideo(); } catch (e) { /* bo qua */ }
  }
  function ytPause() { if (yt.player && yt.ready) { try { yt.player.pauseVideo(); } catch (e) { /* bo qua */ } } }

  // ------------------------------------------------- Nhac nen tu tao (Web Audio) --
  // Vong 4 o nhip C - G - Am - F, 116 BPM: trong bass, kick nhe, hi-hat, hop am nay va giai dieu arpeggio.
  var ac = null, master = null, timer = null, nextT = 0, step = 0, noiseBuf = null, synthOn = false;
  var BPM = 116, SPS = 60 / BPM / 4;                       // giay moi not moc kep (16 o / o nhip)
  var CHORDS = [[48, 52, 55], [43, 47, 50], [45, 48, 52], [41, 45, 48]];   // C, G, Am, F (MIDI)
  var MEL = [                                                              // chi so not trong hop am (+12 = len quang)
    [0, -1, 1, -1, 2, -1, 1, 2, 3, -1, 2, -1, 1, -1, 2, -1],
    [2, -1, 1, -1, 0, -1, 1, -1, 2, -1, 3, 2, 1, -1, -1, -1],
    [0, -1, 2, -1, 1, -1, 2, 3, 4, -1, 3, -1, 2, -1, 1, -1],
    [3, -1, 2, -1, 1, -1, 2, -1, 1, -1, 0, -1, -1, -1, -1, -1]
  ];

  function hz(m) { return 440 * Math.pow(2, (m - 69) / 12); }
  function audio() {
    if (ac) return ac;
    var C = window.AudioContext || window.webkitAudioContext;
    if (!C) return null;
    ac = new C();
    master = ac.createGain();
    master.gain.value = 0;
    master.connect(ac.destination);
    noiseBuf = ac.createBuffer(1, Math.floor(ac.sampleRate * 0.2), ac.sampleRate);
    var d = noiseBuf.getChannelData(0);
    for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    return ac;
  }
  function tone(type, f, t, dur, vol, cutoff) {
    var o = ac.createOscillator(), g = ac.createGain(), out = g;
    o.type = type; o.frequency.setValueAtTime(f, t);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g);
    if (cutoff) { var lp = ac.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = cutoff; g.connect(lp); out = lp; }
    out.connect(master);
    o.start(t); o.stop(t + dur + 0.02);
  }
  function kick(t) {
    var o = ac.createOscillator(), g = ac.createGain();
    o.frequency.setValueAtTime(140, t); o.frequency.exponentialRampToValueAtTime(45, t + 0.12);
    g.gain.setValueAtTime(0.5, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
    o.connect(g); g.connect(master); o.start(t); o.stop(t + 0.2);
  }
  function hat(t, vol) {
    var s = ac.createBufferSource(), hp = ac.createBiquadFilter(), g = ac.createGain();
    s.buffer = noiseBuf; hp.type = "highpass"; hp.frequency.value = 7000;
    g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.05);
    s.connect(hp); hp.connect(g); g.connect(master); s.start(t); s.stop(t + 0.06);
  }
  function playStep(n, t) {
    var bar = Math.floor(n / 16) % 4, s = n % 16, ch = CHORDS[bar];
    if (s === 0 || s === 8) kick(t);
    if (s % 4 === 2) hat(t, 0.06);
    if (s === 0 || s === 6 || s === 8 || s === 14) tone("triangle", hz(ch[0] - 12), t, SPS * 1.8, 0.32);
    if (s === 4 || s === 12) ch.forEach(function (m) { tone("square", hz(m + 12), t, 0.12, 0.035, 1800); });
    var mi = MEL[bar][s];
    if (mi >= 0) {
      var note = ch[mi % 3] + 24 + (mi >= 3 ? 12 : 0);
      tone("triangle", hz(note), t, SPS * 1.6, 0.12);
      tone("sine", hz(note + 12), t, SPS * 1.2, 0.03);
    }
  }
  function sched() {
    while (nextT < ac.currentTime + 0.12) { playStep(step, nextT); nextT += SPS; step++; }
  }
  function synthGain() { return cfg.vol * (phase === "question" ? 0.12 : 0.24); }
  function synthStart() {
    if (!audio()) return;
    if (ac.state === "suspended") ac.resume();
    master.gain.setTargetAtTime(synthGain(), ac.currentTime, 0.3);
    if (synthOn) return;
    synthOn = true; step = 0; nextT = ac.currentTime + 0.08;
    timer = setInterval(sched, 25);
  }
  function synthStop() {
    if (!ac || !synthOn) return;
    synthOn = false;
    master.gain.setTargetAtTime(0, ac.currentTime, 0.15);
    var t = timer; setTimeout(function () { if (!synthOn) clearInterval(t); }, 600);
  }

  // ------------------------------------------------------------- dieu phoi --
  function apply() {
    var live = ["lobby", "question", "locked", "reveal", "board", "ended"].indexOf(phase) >= 0;
    var url = phase === "lobby" ? cfg.yt : cfg.ytGame;
    want = "";
    if (cfg.on && started && live) {
      if (url && ytUsable(url)) want = "yt";
      else if (cfg.game) want = "synth";                // khong link / link hong -> nhac khong loi
    }
    if (want === "yt") { ytEnsure(url); if (!ytUsable(url)) want = cfg.game ? "synth" : ""; }
    if (want === "yt") { synthStop(); ytPlay(); }
    else if (want === "synth") { ytPause(); synthStart(); }
    else { ytPause(); synthStop(); }
    paintButton();
  }

  function begin() {                                        // trong mot cu bam cua nguoi dung
    started = true;
    if (audio() && ac.state === "suspended") ac.resume();
  }
  // Da bat tu lan truoc: cu bam dau tien bat ky tren trang mo tieng (trinh duyet chan tu phat).
  function armFirstGesture() {
    var go = function () {
      document.removeEventListener("pointerdown", go, true);
      document.removeEventListener("keydown", go, true);
      if (!started) { begin(); apply(); }
    };
    document.addEventListener("pointerdown", go, true);
    document.addEventListener("keydown", go, true);
  }

  // ------------------------------------------------------------- giao dien --
  function css() {
    if (document.getElementById("ecdt-music-css")) return;
    var s = document.createElement("style");
    s.id = "ecdt-music-css";
    s.textContent =
      "#ecdt-mpop{position:fixed;z-index:2147483000;top:56px;right:16px;width:320px;background:#fff;color:#1d1b3a;border-radius:16px;" +
      "box-shadow:0 18px 48px rgba(20,10,60,.35);padding:16px;font:14px/1.45 Inter,system-ui,sans-serif}" +
      "#ecdt-mpop h4{margin:0 0 10px;font-size:15px}#ecdt-mpop label{display:flex;align-items:center;gap:8px;margin:8px 0}" +
      "#ecdt-mpop input[type=text]{width:100%;box-sizing:border-box;border:1px solid #d6d3e8;border-radius:10px;padding:8px 10px;font:inherit}" +
      "#ecdt-mpop input[type=range]{flex:1}#ecdt-mpop .row{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}" +
      "#ecdt-mpop .hint{color:#6b6890;font-size:12px;margin-top:2px}" +
      "#ecdt-mpop button{border:0;border-radius:10px;padding:8px 14px;font:600 13px Inter,system-ui,sans-serif;cursor:pointer;background:#eeecf8;color:#1d1b3a}" +
      "#ecdt-mpop button.pri{background:#ffbf00;color:#2a1600}" +
      ".ecdt-mbtn.off-lobby{background:#ffbf00!important;color:#2a1600!important}";
    document.head.appendChild(s);
  }

  function paintButton() {
    if (!slot || !slot.isConnected) return;
    css();
    var b = slot.querySelector("button");
    if (!b) {
      slot.innerHTML = '<button type="button" class="dt-b sm ghost ecdt-mbtn" style="color:#fff" title="Nhạc trên máy chiếu"></button>';
      b = slot.querySelector("button");
      b.onclick = function (e) { e.stopPropagation(); togglePop(); };
    }
    var playing = cfg.on && started;
    b.textContent = playing ? "🎵 Nhạc" : (cfg.on ? "🎵 Bấm để mở tiếng" : "🔇 Bật nhạc");
    b.classList.toggle("off-lobby", phase === "lobby" && !playing);
  }

  function togglePop() {
    if (pop) { closePop(); return; }
    css();
    pop = document.createElement("div");
    pop.id = "ecdt-mpop";
    pop.innerHTML =
      "<h4>🎵 Nhạc trên máy chiếu</h4>" +
      '<label><input type="checkbox" id="ecdt-m-on"> Bật nhạc</label>' +
      '<label>🔈 <input type="range" id="ecdt-m-vol" min="0" max="100" step="5"> 🔊</label>' +
      '<div style="margin-top:10px">Nhạc lúc chờ vào phòng (link YouTube)</div>' +
      '<input type="text" id="ecdt-m-yt" placeholder="https://www.youtube.com/watch?v=..." spellcheck="false">' +
      '<div style="margin-top:10px">Nhạc khi chơi (link YouTube)</div>' +
      '<input type="text" id="ecdt-m-ytg" placeholder="Để trống = nhạc không lời tự tạo" spellcheck="false">' +
      '<div class="hint">Ô nào để trống thì phát nhạc không lời tự tạo.</div>' +
      '<label><input type="checkbox" id="ecdt-m-game"> Có nhạc trong lúc chơi</label>' +
      '<div class="hint">Câu đang mở thì nhạc tự nhỏ lại. Điện thoại người chơi không phát nhạc.</div>' +
      '<div class="row"><button type="button" id="ecdt-m-def">Bài mặc định</button><button type="button" class="pri" id="ecdt-m-ok">Xong</button></div>';
    document.body.appendChild(pop);
    var on = pop.querySelector("#ecdt-m-on"), vol = pop.querySelector("#ecdt-m-vol"),
      ytIn = pop.querySelector("#ecdt-m-yt"), ytG = pop.querySelector("#ecdt-m-ytg"), game = pop.querySelector("#ecdt-m-game");
    on.checked = cfg.on; vol.value = Math.round(cfg.vol * 100); ytIn.value = cfg.yt; ytG.value = cfg.ytGame; game.checked = cfg.game;
    on.onchange = function () { cfg.on = on.checked; if (cfg.on) begin(); save(); apply(); };
    vol.oninput = function () {
      cfg.vol = Math.max(0, Math.min(1, vol.value / 100)); save();
      if (yt.player && yt.ready) { try { yt.player.setVolume(ytVol()); } catch (e) { /* bo qua */ } }
      if (ac && synthOn) master.gain.setTargetAtTime(synthGain(), ac.currentTime, 0.1);
    };
    game.onchange = function () { cfg.game = game.checked; save(); apply(); };
    var setYt = function () {
      var v = ytIn.value.trim(), w = ytG.value.trim();
      if ((v && !parseYt(v)) || (w && !parseYt(w))) { toast("Link YouTube không đúng - dán link dạng youtube.com/watch?v=... hoặc youtu.be/...", true); return false; }
      if (v !== cfg.yt || w !== cfg.ytGame) { cfg.yt = v; cfg.ytGame = w; save(); apply(); }
      return true;
    };
    ytIn.onchange = setYt; ytG.onchange = setYt;
    pop.querySelector("#ecdt-m-def").onclick = function () { ytIn.value = DEFAULT_YT; setYt(); };
    pop.querySelector("#ecdt-m-ok").onclick = function () { if (setYt()) closePop(); };
    if (!cfg.on) { on.checked = true; on.onchange(); }          // bam nut lan dau = bat luon
    else if (!started) { begin(); apply(); }
    setTimeout(function () { document.addEventListener("pointerdown", outside, true); }, 0);
  }
  function outside(e) { if (pop && !pop.contains(e.target) && !(slot && slot.contains(e.target))) closePop(); }
  function closePop() {
    document.removeEventListener("pointerdown", outside, true);
    if (pop) { pop.remove(); pop = null; }
  }

  if (cfg.on) armFirstGesture();
  window.addEventListener("pagehide", function () { synthStop(); });

  window.ECDtMusic = {
    attach: function (el, ph) {
      slot = el || null;
      if (ph !== phase) { phase = ph || ""; apply(); } else paintButton();
    }
  };
})();
