// Copyright (c) 2026, eCentric and contributors
// ec_st_kalodata.js -- trang /kalodata (Kalodata dung chung). Goi API qua window.ecApi (public/js/ec_api.js).
// KHONG co luat nghiep vu o day: ai duoc dung, thu tu, het gio, gia han deu do server quyet
// (shared_tools/). Trang chi ve lai theo `state` va dem nguoc tu so giay server gui.
// Link dang nhap Kalodata (open_link) song 60 s: mo thang tab moi, KHONG hien / copy / luu.
(function () {
  "use strict";
  if (window.ECSt) return;
  var PREFIX = "ecentric_workspace.shared_tools.controllers.api.";
  var TOOL = "kalodata";
  var MSG_FAIL = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT.";
  var root, S = null, base = 0, pollT = null, tickT = null, loading = false, lastAt = 0, baseTitle = document.title;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function byId(id) { return document.getElementById(id); }

  // window.ecApi nap qua hooks web_include_js (cuoi <body>): doi toi khi co.
  function whenApi() {
    if (window.ecApi) return Promise.resolve(window.ecApi);
    return new Promise(function (resolve, reject) {
      var n = 0;
      (function wait() {
        if (window.ecApi) return resolve(window.ecApi);
        if (++n > 160) { var e = new Error("noapi"); e.stMessage = "Trang chưa tải xong - bấm Ctrl+Shift+R."; return reject(e); }
        setTimeout(wait, 50);
      })();
    });
  }
  async function api(method, args, post) {
    var ea = await whenApi();
    var env;
    try {
      env = await (post ? ea.post(PREFIX + method, args || {}) : ea.get(PREFIX + method, args || {}));
    } catch (e) {
      if (e && e.csrf) e.stMessage = "Phiên làm việc đã đổi. Bấm Ctrl+Shift+R để tải lại trang.";
      else if (e && e.status === 0) e.stMessage = "Mất kết nối mạng.";
      else if (e && (e.status === 403 || e.status === 401)) e.stMessage = "Phiên đăng nhập đã hết - đăng nhập lại nhé.";
      throw e;
    }
    if (env && env.success) return env.data;
    var err = new Error((env && env.message) || "fail");
    err.stMessage = (env && env.message) || "";
    throw err;
  }
  function msg(e) { return (e && e.stMessage) || MSG_FAIL; }

  var toastT;
  function toast(text, kind) {
    var el = byId("ec-st-toast");
    if (!el) { el = document.createElement("div"); el.id = "ec-st-toast"; el.setAttribute("role", "status"); (byId("ec-st") || document.body).appendChild(el); }
    el.className = kind || "";
    el.textContent = text;
    el.hidden = false;
    clearTimeout(toastT);
    toastT = setTimeout(function () { el.hidden = true; }, kind === "bad" ? 6000 : 3000);
  }
  function busy(btn, on) { if (btn) { btn.disabled = !!on; btn.classList.toggle("busy", !!on); } }

  // ------------------------------------------------------------------ thoi gian
  function left(sec) { return Math.max(0, Math.round(sec - (performance.now() - base) / 1000)); }
  function mmss(sec) { var m = Math.floor(sec / 60), s = sec % 60; return m + ":" + (s < 10 ? "0" : "") + s; }

  var ICON_OPEN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>';

  // ------------------------------------------------------------------ ve
  function render() {
    var me = S.me || {}, t = S.tool;
    var html = '<div class="st-wrap"><header>' +
      '<div class="st-title-row"><h1 class="st-title">' + esc(t.title) + ' dùng chung</h1>' +
      '<span class="st-pill ' + (S.host.ok ? "st-pill--ok" : "st-pill--off") + '"><span class="st-dot" aria-hidden="true"></span>' + esc(S.host.label) + '</span></div>' +
      '<p class="st-sub">Một người dùng một lúc · mỗi lượt ' + t.lease + ' phút · đến lượt có ' + t.ready + ' phút để mở</p></header>' +
      (t.notice ? '<p class="st-notice">' + esc(t.notice) + '</p>' : "") +
      '<div class="st-grid"><div class="st-col">' + hero(me) + filesCard() + '</div>' +
      '<div class="st-col">' + queueCard(me) + (me.status === "Waiting" || !me.status ? holderCard() : "") + rulesCard() + '</div></div>' +
      (S.is_manager && window.ECStStats ? window.ECStStats.card() : "") + '</div>';
    // Thu tu tren dien thoai (cot don): luot cua toi -> hang doi -> nguoi dang dung -> file -> quy dinh.
    byId("st-root").innerHTML = html;
    paintTimers();
    showArmed();
    document.title = (me.status === "Ready" ? "(Đến lượt) " : "") + baseTitle;
  }

  function hero(me) {
    var t = S.tool;
    if (me.status === "Active") {
      var total = me.total_sec || t.lease * 60;
      return '<section class="st-card st-card--hero st-o1" aria-labelledby="st-h-hero">' +
        '<p class="st-eyebrow" id="st-h-hero">Bạn đang dùng ' + esc(t.title) + '</p>' +
        '<div class="st-big-row"><span class="st-big" data-left="remaining_sec">' + mmss(left(me.remaining_sec)) + '</span><span class="st-big-label">còn lại trong lượt</span></div>' +
        '<div class="st-bar" role="img" aria-label="Thời gian còn lại"><span data-bar="' + total + '"></span></div>' +
        '<div class="st-bar-legend"><span>Bắt đầu ' + esc(me.started) + '</span><span>Kết thúc ' + esc(me.ends) + '</span></div>' +
        '<div class="st-actions">' +
        '<button class="st-btn st-btn--primary" type="button" data-act="open">' + ICON_OPEN + 'Mở lại ' + esc(t.title) + '</button>' +
        '<button class="st-btn" type="button" data-act="extend"' + (me.extend_reason ? ' disabled aria-describedby="st-why"' : "") + '>Gia hạn ' + t.extend + ' phút</button>' +
        '<button class="st-btn st-btn--danger" type="button" data-act="leave" data-confirm="Bấm lần nữa để kết thúc">Kết thúc sớm</button></div>' +
        (me.extend_reason ? '<p class="st-why" id="st-why">' + esc(me.extend_reason) + '</p>' : "") +
        '<p class="st-hint">Lỡ đóng tab ' + esc(t.title) + '? Bấm "Mở lại" để vào tiếp, lượt vẫn tính. Để yên ' + t.idle + ' phút, lượt tự kết thúc.</p></section>';
    }
    if (me.status === "Ready") {
      return '<section class="st-card st-card--hero st-card--ready st-o1" aria-labelledby="st-h-hero">' +
        '<p class="st-eyebrow" id="st-h-hero">Đến lượt bạn</p>' +
        '<div class="st-big-row"><span class="st-big-label">Mở ' + esc(t.title) + ' trong</span><span class="st-big" data-left="ready_left_sec">' + mmss(left(me.ready_left_sec)) + '</span></div>' +
        '<div class="st-bar" role="img" aria-label="Thời gian còn lại để mở"><span data-bar="' + (t.ready * 60) + '" data-src="ready_left_sec"></span></div>' +
        '<div class="st-actions">' +
        '<button class="st-btn st-btn--primary st-btn--big" type="button" data-act="open">' + ICON_OPEN + 'Mở ' + esc(t.title) + '</button>' +
        '<button class="st-btn" type="button" data-act="leave" data-confirm="Bấm lần nữa để bỏ lượt">Bỏ lượt</button></div>' +
        '<p class="st-hint">' + esc(t.title) + ' mở ở tab mới. Không mở kịp thì lượt chuyển cho người tiếp theo.</p></section>';
    }
    if (me.status === "Waiting") {
      return '<section class="st-card st-card--hero st-o1" aria-labelledby="st-h-hero">' +
        '<p class="st-eyebrow" id="st-h-hero">Bạn đang xếp hàng</p>' +
        '<div class="st-big-row"><span class="st-big">Thứ ' + me.position + '</span><span class="st-big-label">trong hàng đợi</span></div>' +
        '<p class="st-lead">Dự kiến đến lượt sau khoảng <b>' + me.eta_min + ' phút</b>.</p>' +
        '<div class="st-actions"><button class="st-btn" type="button" data-act="leave" data-confirm="Bấm lần nữa để rời hàng">Rời hàng đợi</button></div>' +
        '<p class="st-hint">Đến lượt, ERP báo trên chuông thông báo và trang này. Giữ tab này mở để không lỡ lượt.</p></section>';
    }
    var free = !S.holder;
    return '<section class="st-card st-card--hero st-o1" aria-labelledby="st-h-hero">' +
      '<p class="st-eyebrow" id="st-h-hero">' + (free ? esc(t.title) + " đang trống" : "Có người đang dùng") + '</p>' +
      '<p class="st-lead">' + (free ? "Vào hàng là đến lượt bạn ngay." :
        "Vào hàng đợi, đến lượt ERP sẽ báo. " + (S.queue.length > 1 ? "Đang có " + (S.queue.length - 1) + " người chờ." : "Chưa ai chờ.")) + '</p>' +
      '<div class="st-actions"><button class="st-btn st-btn--primary st-btn--big" type="button" data-act="join">Vào hàng đợi</button></div></section>';
  }

  function queueCard(me) {
    var rows = S.queue.map(function (q) {
      var pos = q.status === "Waiting" ? String(q.pos)
        : '<span class="st-pill ' + (q.status === "Ready" ? "st-pill--warn" : "st-pill--navy") + '">' + esc(q.status_label) + '</span>';
      var x = S.is_manager && !q.is_me
        ? '<button class="st-q-x" type="button" data-act="force" data-entry="' + esc(q.entry) + '" data-confirm="Chắc chưa?" aria-label="Kết thúc lượt của ' + esc(q.name) + '">Kết thúc</button>' : "";
      return '<li class="st-q' + (q.is_me ? " st-q--me" : "") + '"><span class="st-q-pos">' + pos + '</span>' +
        '<span class="st-avatar" aria-hidden="true">' + esc(q.initials) + '</span>' +
        '<span class="st-q-who"><b>' + esc(q.name) + (q.is_me ? " (bạn)" : "") + '</b><span>' + esc(q.department || " ") + '</span></span>' +
        '<span class="st-q-meta">' + esc(q.meta) + '</span>' + x + '</li>';
    }).join("");
    var waiting = S.queue.filter(function (q) { return q.status === "Waiting"; }).length;
    var head = me.status && me.status !== "Waiting" ? (me.waiting_after ? me.waiting_after + " người chờ sau bạn" : "chưa ai chờ")
      : waiting + " người đang chờ";
    return '<section class="st-card st-o2" aria-labelledby="st-h-queue"><div class="st-card-head"><h2 class="st-h2" id="st-h-queue">Hàng đợi</h2><span class="st-muted">' + esc(head) + '</span></div>' +
      (rows ? '<ol class="st-queue">' + rows + '</ol>' : '<p class="st-empty">Chưa có ai trong hàng.</p>') + '</section>';
  }

  function holderCard() {
    var h = S.holder, t = S.tool;
    var body = !h ? '<p class="st-empty">Không ai đang dùng.</p>'
      : '<dl class="st-kv"><dt>Người dùng</dt><dd>' + esc(h.name) + (h.department ? " · " + esc(h.department) : "") + '</dd>' +
        (h.status === "Active" ? '<dt>Từ</dt><dd>' + esc(h.since) + '</dd><dt>Còn lại</dt><dd>' + h.remaining_min + ' phút</dd>'
          : '<dt>Trạng thái</dt><dd>Vừa đến lượt, đang mở</dd>') + '</dl>';
    return '<section class="st-card st-o3" aria-labelledby="st-h-holder"><h2 class="st-h2" id="st-h-holder" style="margin-bottom:12px">Đang dùng ' + esc(t.title) + '</h2>' + body + '</section>';
  }

  function rulesCard() {
    var t = S.tool;
    return '<section class="st-card st-o5" aria-labelledby="st-h-rules"><h2 class="st-h2" id="st-h-rules" style="margin-bottom:12px">Quy định</h2><ul class="st-rules">' +
      '<li>Mỗi lượt ' + t.lease + ' phút. Không ai chờ thì gia hạn thêm ' + t.extend + ' phút.</li>' +
      '<li>Để yên ' + t.idle + ' phút, lượt tự kết thúc.</li>' +
      '<li>Xuất bảng tối đa 2500 trang mỗi lần (trên 50 trang, file về theo từng phần 50 trang), 30 lần mỗi giờ.</li>' +
      '<li>Không đăng xuất, không đổi mật khẩu tài khoản ' + esc(t.title) + '.</li></ul></section>';
  }

  // Mot lan xuat nhieu trang (nhieu phan): nut Tai Excel gop + danh sach tung phan CSV (an trong <details>).
  function runItem(f) {
    var href = "/api/method/" + PREFIX + "download_run?run=" + encodeURIComponent(f.run);
    var meta = [f.source, f.rows + " dòng", f.parts.length + " phần", f.at].filter(Boolean).join(" · ");
    var parts = f.parts.map(function (p) {
      return '<a href="/api/method/' + PREFIX + 'download?name=' + encodeURIComponent(p.name) + '" data-act="dl" download>Phần ' +
        p.part + (p.rows == null ? "" : " (" + p.rows + " dòng)") + '</a>';
    }).join("");
    return '<li class="st-file st-file--run"><div class="st-file-main"><div class="st-file-name">' +
      '<span class="st-file-title" title="' + esc(f.page) + '">' + esc(f.page || "Kalodata") + '</span>' +
      (f["new"] ? '<span class="st-new">Mới</span>' : "") + '</div><div class="st-file-meta">' + esc(meta) + '</div>' +
      '<details class="st-parts"><summary>Tải từng phần (CSV)</summary><div class="st-parts-list">' + parts + '</div></details></div>' +
      '<a class="st-btn st-btn--sm st-btn--primary" href="' + href + '" data-act="dl" download aria-label="Tải Excel gộp ' + esc(f.page) + '">Tải Excel</a></li>';
  }

  function filesCard() {
    // Moi file mot dong gon: ten trang (cat bot neu dai) + dong phu "nguon · so dong · luc", nut Tai luon thay.
    var rows = (S.exports || []).map(function (f) {
      if (f.kind === "run") return runItem(f);
      var href = "/api/method/" + PREFIX + "download?name=" + encodeURIComponent(f.name);
      var meta = [f.source, f.rows == null ? "" : f.rows + " dòng", f.at].filter(Boolean).join(" · ");
      return '<li class="st-file"><div class="st-file-main"><div class="st-file-name">' +
        '<span class="st-file-title" title="' + esc(f.page || f.file_name) + '">' + esc(f.page || f.file_name) + '</span>' +
        (f["new"] ? '<span class="st-new">Mới</span>' : "") + '</div><div class="st-file-meta">' + esc(meta) + '</div></div>' +
        '<a class="st-btn st-btn--sm" href="' + href + '" data-act="dl" download aria-label="Tải file ' + esc(f.page || f.file_name) + '">Tải file</a></li>';
    }).join("");
    return '<section class="st-card st-o4" aria-labelledby="st-h-files"><div class="st-card-head"><h2 class="st-h2" id="st-h-files">File đã xuất của tôi</h2><span class="st-muted">giữ 7 ngày</span></div>' +
      (rows ? '<ul class="st-files">' + rows + '</ul>' : '<p class="st-empty">Chưa có file nào.</p>') +
      '<p class="st-files-note">File xuất trong ' + esc(S.tool.title) + ' (nút Xuất bảng hoặc nút Export của ' + esc(S.tool.title) + ') hiện ở đây sau vài giây.</p></section>';
  }

  // ------------------------------------------------------------------ dem nguoc
  function paintTimers() {
    if (!S) return;
    var me = S.me || {};
    var hit0 = false;
    Array.prototype.forEach.call(root.querySelectorAll("[data-left]"), function (el) {
      var v = left(me[el.getAttribute("data-left")] || 0);
      el.textContent = mmss(v);
      if (v === 0) hit0 = true;
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-bar]"), function (el) {
      var total = +el.getAttribute("data-bar") || 1;
      var src = el.getAttribute("data-src") || "remaining_sec";
      el.style.width = Math.max(0, Math.min(100, left(me[src] || 0) / total * 100)) + "%";
    });
    if (hit0 && performance.now() - lastAt > 4000) refresh();
  }

  // ------------------------------------------------------------------ tai
  async function refresh(first) {
    if (loading) return;
    loading = true;
    lastAt = performance.now();
    var was = S && S.me && S.me.status;
    try {
      var data = await api("state", { tool: TOOL });
      apply(data, was);
    } catch (e) {
      if (first) byId("st-root").innerHTML = '<div class="st-wrap"><div class="st-error" role="alert"><b>Không tải được trang</b>' + esc(msg(e)) + '</div></div>';
      else toast(msg(e), "bad");
    } finally {
      loading = false;
    }
  }
  function apply(data, was) {
    var firstManager = !S && data && data.is_manager;
    S = data;
    if (firstManager && window.ECStStats) window.ECStStats.load(30);
    base = performance.now();
    render();
    var now = S.me && S.me.status;
    if (was && was !== "Ready" && now === "Ready") toast("Đến lượt bạn! Bấm Mở " + S.tool.title + " trong " + S.tool.ready + " phút.", "warn");
    if (was === "Active" && !now) toast("Lượt của bạn đã kết thúc.");
    schedule();
  }
  function schedule() {
    clearTimeout(pollT);
    pollT = setTimeout(function () { if (!document.hidden) refresh(); else schedule(); }, ((S && S.poll_sec) || 10) * 1000);
  }

  // ------------------------------------------------------------------ thao tac
  // Nut nguy hiem: bam lan 1 doi chu, bam lan 2 trong ARM_MS moi chay (khong dung confirm() chan trang).
  // Trang tu ve lai moi 10 s nen trang thai "da bam lan 1" giu theo khoa (act + entry), khong theo nut.
  var ARM_MS = 6000, armSig = "", armUntil = 0;
  function sigOf(btn) { return btn.getAttribute("data-act") + ":" + (btn.getAttribute("data-entry") || ""); }
  function showArmed() {
    if (!armSig || performance.now() > armUntil) return;
    Array.prototype.forEach.call(root.querySelectorAll("[data-confirm]"), function (b) {
      if (sigOf(b) === armSig) b.textContent = b.getAttribute("data-confirm");
    });
  }
  function armed(btn) {
    if (!btn.getAttribute("data-confirm")) return true;
    var sig = sigOf(btn);
    if (sig === armSig && performance.now() <= armUntil) { armSig = ""; return true; }
    armSig = sig;
    armUntil = performance.now() + ARM_MS;
    showArmed();
    setTimeout(function () { if (armSig === sig && performance.now() > armUntil) { armSig = ""; if (S) render(); } }, ARM_MS + 50);
    return false;
  }

  async function act(btn) {
    var a = btn.getAttribute("data-act");
    if (a === "open") return openTool(btn);
    if (a === "stats") { if (window.ECStStats) window.ECStStats.load(+btn.getAttribute("data-days") || 30); return; }
    if (!armed(btn)) return;
    var map = { join: ["join", "Đã vào hàng đợi."], leave: ["leave", "Đã cập nhật lượt của bạn."],
                extend: ["extend", "Đã gia hạn thêm " + S.tool.extend + " phút."], force: ["force_end", "Đã kết thúc lượt đó."] };
    var m = map[a];
    if (!m) return;
    busy(btn, true);
    try {
      var args = { tool: TOOL };
      if (a === "force") args.entry = btn.getAttribute("data-entry");
      var data = await api(m[0], args, true);
      apply(data, S.me && S.me.status);
      toast(m[1]);
    } catch (e) {
      busy(btn, false);
      toast(msg(e), "bad");
    }
  }

  async function openTool(btn) {
    // Mo tab TRONG cu bam (truoc await) de trinh duyet khong chan popup; co link moi chuyen tab sang.
    var w = window.open("", "_blank");
    if (w) {
      try { w.opener = null; w.document.title = "Đang mở " + S.tool.title + "…"; w.document.body.innerHTML = '<p style="font:16px system-ui;padding:24px">Đang mở ' + esc(S.tool.title) + '…</p>'; } catch (e) { /* tab da sang trang khac */ }
    }
    busy(btn, true);
    try {
      var data = await api("open_link", { tool: TOOL }, true);
      if (w && !w.closed) w.location.replace(data.url);
      else { toast("Trình duyệt chặn tab mới - mở ngay trong tab này.", "warn"); window.location.assign(data.url); return; }
      busy(btn, false);
      refresh();
    } catch (e) {
      if (w && !w.closed) w.close();
      busy(btn, false);
      toast(msg(e), "bad");
      refresh();
    }
  }

  function init() {
    root = byId("st-root");
    if (!root) return;
    root.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-act]");
      if (!btn || !root.contains(btn) || btn.disabled) return;
      if (btn.getAttribute("data-act") === "dl") { setTimeout(refresh, 1500); return; }
      ev.preventDefault();
      act(btn);
    });
    document.addEventListener("visibilitychange", function () { if (!document.hidden && S) refresh(); });
    tickT = setInterval(paintTimers, 1000);
    refresh(true);
  }

  // ec_st_stats.js (khoi thong ke cho quan ly) dung lai api / esc / ve lai trang.
  window.ECSt = { refresh: refresh, api: api, esc: esc, msg: msg, rerender: function () { if (S) render(); } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
