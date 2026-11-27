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
  var fqT, root, S = null, base = 0, pollT = null, tickT = null, loading = false, lastAt = 0, baseTitle = document.title;

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
  // Bo cuc A (PO duyet 27/11/2026, theo Approval Center): bang trang thai -> 2 khung (dang dung & hang doi |
  // ban hay xuat) -> danh sach file (tim + loc + nhom theo ngay + chia trang) -> quy dinh | quan ly -> thong ke.
  var IC = {
    file: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/></svg>',
    xls: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/></svg>',
    chart: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5L20 7"/></svg>',
    search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>'
  };

  function render() {
    var me = S.me || {}, t = S.tool;
    // Giu o tim kiem khi trang tu ve lai moi 10 s (dang go thi khong mat chu / mat con tro).
    var fq = byId("st-fq"), focused = fq && document.activeElement === fq, caret = focused ? fq.selectionStart : 0;
    var html = '<div class="st-wrap"><header>' +
      '<div class="st-title-row"><h1 class="st-title">' + esc(t.title) + ' dùng chung</h1>' +
      '<span class="st-pill ' + (S.host.ok ? "st-pill--ok" : "st-pill--off") + '"><span class="st-dot" aria-hidden="true"></span>' + esc(S.host.label) + '</span></div>' +
      '<p class="st-sub">Một người dùng một lúc · mỗi lượt ' + t.lease + ' phút · đến lượt có ' + t.ready + ' phút để mở</p></header>' +
      (t.notice ? '<p class="st-notice">' + esc(t.notice) + '</p>' : "") +
      (S.is_manager && t.enabled === false ? '<p class="st-notice">' + esc(t.title) + ' đang tạm đóng với mọi người, chỉ quản lý vào được. Làm xong các bước trong khung Quản lý thì bấm Mở lại cho mọi người.</p>' : "") +
      banner(me) +
      '<div class="st-duo">' + peopleCard() + oftenCard() + '</div>' +
      filesCard() +
      '<div class="st-duo st-duo--end">' + rulesCard() + (S.is_manager ? adminCard() : "") + '</div>' +
      (S.is_manager && window.ECStStats ? window.ECStStats.card() : "") + '</div>';
    byId("st-root").innerHTML = html;
    if (focused && (fq = byId("st-fq"))) { fq.focus(); try { fq.setSelectionRange(caret, caret); } catch (e) { /* bo qua */ } }
    paintTimers();
    showArmed();
    document.title = (me.status === "Ready" ? "(Đến lượt) " : "") + baseTitle;
  }

  function btn(act, label, cls, confirm, extra) {
    return '<button class="st-btn' + (cls ? " " + cls : "") + '" type="button" data-act="' + act + '"' +
      (confirm ? ' data-confirm="' + esc(confirm) + '"' : "") + (extra || "") + '>' + label + '</button>';
  }

  // Bang trang thai: mau + so tron + 1 dong chinh + 1 dong phu + nut, doi theo luot cua nguoi xem.
  function banner(me) {
    var t = S.tool, h = S.holder, waiting = S.queue.filter(function (q) { return q.status === "Waiting"; }).length;
    var tone, dot, title, sub, bar = "", acts = "";
    if (me.status === "Active") {
      var total = me.total_sec || t.lease * 60, late = me.remaining_sec < 600;
      tone = late ? "warn" : "pri";
      dot = '<span data-left-min="remaining_sec"></span>';
      title = 'Bạn đang dùng · còn <span class="st-num" data-left="remaining_sec"></span>';
      sub = esc(me.started) + ' → ' + esc(me.ends) + ' · ' +
        (me.connected ? esc(t.title) + " đang mở ở một tab khác của bạn, chuyển sang tab đó để dùng tiếp." :
         late && !me.extend_reason ? "Không ai chờ, gia hạn thêm " + t.extend + " phút được." :
         "Lỡ đóng tab thì bấm Mở lại, lượt vẫn tính. Để yên " + t.idle + " phút, lượt tự kết thúc.");
      bar = '<div class="st-bar"><span data-bar="' + total + '"></span></div>';
      acts = btn("leave", "Kết thúc lượt", "st-btn--danger", "Bấm lần nữa để kết thúc") +
        (me.extend_reason ? "" : btn("extend", "Gia hạn " + t.extend + " phút")) +
        (me.connected
          // Tab cu con mo: mo tab moi se NGAT tab cu -> hoi lai mot lan (nut khong con la nut chinh).
          ? btn("open", ICON_OPEN + "Mở tab mới", "", "Tab đang mở sẽ bị ngắt · bấm lần nữa")
          : btn("open", ICON_OPEN + "Mở lại " + esc(t.title), "st-btn--primary"));
    } else if (me.status === "Ready") {
      tone = "ok";
      dot = '<span data-left="ready_left_sec"></span>';
      title = 'Đến lượt bạn · bấm Mở trong <span class="st-num" data-left="ready_left_sec"></span>';
      sub = "Hết " + t.ready + " phút không mở, lượt chuyển cho người sau. " + esc(t.title) + " mở ở tab mới.";
      bar = '<div class="st-bar"><span data-bar="' + (t.ready * 60) + '" data-src="ready_left_sec"></span></div>';
      acts = btn("leave", "Bỏ lượt", "", "Bấm lần nữa để bỏ lượt") + btn("open", ICON_OPEN + "Mở " + esc(t.title), "st-btn--primary st-btn--big");
    } else if (me.status === "Waiting") {
      tone = "warn";
      dot = "#" + me.position;
      title = "Bạn đứng thứ " + me.position + " trong hàng";
      sub = "Dự kiến đến lượt sau khoảng " + me.eta_min + " phút. Đến lượt, ERP báo trên chuông thông báo và trang này.";
      acts = btn("leave", "Rời hàng", "", "Bấm lần nữa để rời hàng");
    } else if (h) {
      tone = "pri";
      dot = h.status === "Active" ? h.remaining_min + "′" : "…";
      title = esc(h.name) + (h.status === "Active" ? " đang dùng · còn " + h.remaining_min + " phút" : " vừa đến lượt, đang mở");
      sub = "Vào hàng đợi, đến lượt ERP sẽ báo. " + (waiting ? "Đang có " + waiting + " người chờ." : "Chưa ai chờ.");
      acts = btn("join", "Vào hàng đợi", "st-btn--primary st-btn--big");
    } else {
      tone = "ok";
      dot = IC.check;
      title = esc(t.title) + " đang trống";
      sub = "Vào hàng là đến lượt bạn ngay, có " + t.ready + " phút để bấm Mở.";
      acts = btn("join", "Vào hàng đợi", "st-btn--primary st-btn--big");
    }
    if (!S.host.ok) {
      tone = "bad";
      dot = "!";
      title = "Máy " + esc(t.title) + " đang offline";
      sub = "Tạm thời chưa mở được " + esc(t.title) + ". Chỗ của bạn trong hàng vẫn giữ. Kéo dài quá 15 phút thì báo IT.";
      bar = "";
      acts = me.status ? btn("leave", me.status === "Waiting" ? "Rời hàng" : "Kết thúc lượt", "", "Bấm lần nữa để xác nhận") : "";
    }
    return '<section class="st-banner st-banner--' + tone + '" aria-labelledby="st-h-banner">' +
      '<span class="st-bn-dot st-num" aria-hidden="true">' + dot + '</span>' +
      '<div class="st-bn-txt"><h2 class="st-bn-t" id="st-h-banner">' + title + '</h2><p class="st-bn-s">' + sub + '</p>' + bar + '</div>' +
      (acts ? '<div class="st-bn-acts">' + acts + '</div>' : "") + '</section>';
  }

  function peopleCard() {
    var waiting = S.queue.filter(function (q) { return q.status === "Waiting"; }).length;
    var cards = S.queue.map(function (q) {
      var tag = q.status === "Waiting" ? '<span class="st-tag st-tag--warn">Chờ #' + q.pos + ' · ' + esc(q.meta) + '</span>'
        : '<span class="st-tag ' + (q.status === "Ready" ? "st-tag--ok" : "st-tag--pri") + '">' + esc(q.status_label) + ' · ' + esc(q.meta) + '</span>';
      var x = S.is_manager && !q.is_me
        ? '<button class="st-q-x" type="button" data-act="force" data-entry="' + esc(q.entry) + '" data-confirm="Chắc chưa?" aria-label="Kết thúc lượt của ' + esc(q.name) + '">Kết thúc</button>' : "";
      return '<li class="st-person' + (q.is_me ? " st-person--me" : "") + '"><span class="st-avatar" aria-hidden="true">' + esc(q.initials) + '</span>' +
        '<b class="st-person-n" title="' + esc(q.name) + '">' + esc(q.name) + (q.is_me ? " (bạn)" : "") + '</b>' +
        '<span class="st-person-d">' + esc(q.department || " ") + '</span>' + tag + x + '</li>';
    }).join("");
    return '<section class="st-panel" aria-labelledby="st-h-queue"><div class="st-ph"><h2 class="st-h2" id="st-h-queue">Đang dùng &amp; hàng đợi</h2>' +
      '<span class="st-muted">' + waiting + ' người chờ</span></div>' +
      (cards ? '<ol class="st-people">' + cards + '</ol>' : '<p class="st-empty st-empty--box">Chưa ai dùng, chưa ai chờ.</p>') + '</section>';
  }

  // "Ban hay xuat": gom file 7 ngay cua chinh nguoi xem theo trang Kalodata, 3 trang nhieu dong nhat.
  function oftenCard() {
    var by = {};
    (S.exports || []).forEach(function (f) {
      var k = f.page || "Kalodata";
      by[k] = by[k] || { name: k, rows: 0, n: 0 };
      by[k].rows += +f.rows || 0;
      by[k].n += 1;
    });
    var top = Object.keys(by).map(function (k) { return by[k]; }).sort(function (a, b) { return b.rows - a.rows || b.n - a.n; }).slice(0, 3);
    var max = top.length ? Math.max(top[0].rows, 1) : 1;
    var rows = top.map(function (x) {
      return '<li><span class="st-ic">' + IC.chart + '</span><span class="st-often-n" title="' + esc(x.name) + '">' + esc(x.name) + '</span>' +
        '<span class="st-often-bar" aria-hidden="true"><i style="width:' + Math.max(4, Math.round(x.rows / max * 100)) + '%"></i></span>' +
        '<span class="st-often-c st-num">' + fmtN(x.rows) + ' dòng · ' + x.n + ' lần</span></li>';
    }).join("");
    return '<section class="st-panel" aria-labelledby="st-h-often"><div class="st-ph"><h2 class="st-h2" id="st-h-often">Bạn hay xuất</h2><span class="st-muted">7 ngày qua</span></div>' +
      (rows ? '<ul class="st-often">' + rows + '</ul>' : '<p class="st-empty st-empty--box">Chưa xuất file nào. Trong ' + esc(S.tool.title) + ', bấm nút Xuất bảng ở góc phải bảng.</p>') + '</section>';
  }
  function fmtN(n) { return Number(n || 0).toLocaleString("vi-VN"); }

  // Chi quan ly (System Manager / EC Shared Tool Manager) thay. Server tu kiem quyen moi lenh.
  function adminCard() {
    var t = S.tool, on = t.enabled !== false;
    var steps = on ? "" : '<ol class="st-rules st-admin-steps">' +
      '<li>Bấm <b>Vào hàng đợi</b> → <b>Mở ' + esc(t.title) + '</b> (chỉ quản lý vào được lúc này).</li>' +
      '<li>Trong ' + esc(t.title) + ', đăng nhập tài khoản mới bằng <b>số điện thoại hoặc email + mật khẩu</b>. Không dùng Google / TikTok (bị chặn trên máy dùng chung).</li>' +
      '<li>Bấm <b>Kết thúc lượt</b>, rồi <b>Mở lại cho mọi người</b>.</li></ol>';
    return '<section class="st-panel st-admin" aria-labelledby="st-h-admin"><div class="st-ph"><h2 class="st-h2" id="st-h-admin">Quản lý</h2>' +
      '<span class="st-pill ' + (on ? "st-pill--ok" : "st-pill--warn") + '">' + (on ? "Đang mở cho mọi người" : "Đang tạm đóng") + '</span></div>' +
      steps + '<div class="st-actions st-admin-actions">' +
      (on ? btn("admin-reset", "Đổi tài khoản " + esc(t.title), "st-btn--sm", "Bấm lần nữa để đổi tài khoản") +
            btn("admin-close", "Tạm đóng", "st-btn--sm", "Bấm lần nữa để tạm đóng")
          : btn("admin-open", "Mở lại cho mọi người", "st-btn--sm st-btn--primary") +
            btn("admin-reset", "Xoá đăng nhập lại", "st-btn--sm", "Bấm lần nữa để xoá lại")) +
      '</div><p class="st-hint">Mật khẩu ' + esc(t.title) + ' chỉ gõ trong trang ' + esc(t.title) + '. ERP không lưu và không thấy mật khẩu.</p></section>';
  }

  function rulesCard() {
    var t = S.tool;
    return '<section class="st-panel" aria-labelledby="st-h-rules"><div class="st-ph"><h2 class="st-h2" id="st-h-rules">Quy định</h2></div><ul class="st-rules">' +
      '<li>Mỗi lượt ' + t.lease + ' phút. Không ai chờ thì gia hạn thêm ' + t.extend + ' phút.</li>' +
      '<li>Để yên ' + t.idle + ' phút, lượt tự kết thúc.</li>' +
      '<li>Xuất bảng tối đa 2500 trang mỗi lần (trên 50 trang, file về theo từng phần 50 trang), 30 lần mỗi giờ.</li>' +
      '<li>Không đăng xuất, không đổi mật khẩu tài khoản ' + esc(t.title) + '.</li></ul></section>';
  }

  // ---------------------------------------------------------------- danh sach file
  // Tim + loc (Tat ca / Chua tai / Hom nay / theo nguon) chay o trinh duyet tren S.exports (toi da 120 dong).
  // Moi trang 5 file, nhom theo ngay; trang / bo loc / chu dang tim giu qua cac lan tu ve lai.
  var FILES_PER_PAGE = 5, filePage = 1, fileFilter = "all", fileQuery = "";
  function filterFiles(all) {
    var q = fileQuery.trim().toLowerCase();
    return all.filter(function (f) {
      if (fileFilter === "new" && !f["new"]) return false;
      if (fileFilter === "today" && f.day !== "Hôm nay") return false;
      if (fileFilter.indexOf("src:") === 0 && f.source !== fileFilter.slice(4)) return false;
      return !q || String(f.page || f.file_name || "").toLowerCase().indexOf(q) >= 0;
    });
  }
  function chips(all) {
    var list = [["all", "Tất cả", all.length],
      ["new", "Chưa tải", all.filter(function (f) { return f["new"]; }).length],
      ["today", "Hôm nay", all.filter(function (f) { return f.day === "Hôm nay"; }).length]];
    var srcs = {};
    all.forEach(function (f) { if (f.source) srcs[f.source] = (srcs[f.source] || 0) + 1; });
    if (Object.keys(srcs).length > 1) Object.keys(srcs).forEach(function (s) { list.push(["src:" + s, s, srcs[s]]); });
    return list.map(function (c) {
      return '<button type="button" class="st-chip" data-act="ffilter" data-f="' + esc(c[0]) + '" aria-pressed="' + (fileFilter === c[0]) + '">' +
        esc(c[1]) + ' <i class="st-num">' + c[2] + '</i></button>';
    }).join("");
  }
  function pager(total) {
    var n = Math.ceil(total / FILES_PER_PAGE);
    if (n <= 1) return "";
    var b = function (p, label, cur, dis, aria) {
      return '<button type="button" class="st-pg' + (cur ? " on" : "") + '" data-act="fpage" data-page="' + p + '"' +
        (dis ? " disabled" : "") + (cur ? ' aria-current="page"' : "") + ' aria-label="' + aria + '">' + label + '</button>';
    };
    var out = [b(filePage - 1, "‹", false, filePage === 1, "Trang trước")];
    for (var p = 1; p <= n; p++) {
      if (n > 7 && p > 2 && p < n - 1 && Math.abs(p - filePage) > 1) { if (out[out.length - 1] !== "…") out.push("…"); continue; }
      out.push(b(p, p, p === filePage, false, "Trang " + p));
    }
    out.push(b(filePage + 1, "›", false, filePage === n, "Trang sau"));
    return '<nav class="st-pager" aria-label="Trang danh sách file">' + out.map(function (x) { return x === "…" ? '<span class="st-pg-gap">…</span>' : x; }).join("") + '</nav>';
  }
  function fileRow(f) {
    var name = f.page || f.file_name || esc(S.tool.title);
    var run = f.kind === "run";
    var href = "/api/method/" + PREFIX + (run ? "download_run?run=" + encodeURIComponent(f.run) : "download?name=" + encodeURIComponent(f.name));
    var meta = [f.source, f.rows == null ? "" : fmtN(f.rows) + " dòng", f.pages ? f.pages + " trang" : "", run ? f.parts.length + " phần" : ""].filter(Boolean).join(" · ");
    var parts = run ? '<details class="st-parts"><summary>Tải từng phần (CSV)</summary><div class="st-parts-list">' + f.parts.map(function (p) {
      return '<a href="/api/method/' + PREFIX + 'download?name=' + encodeURIComponent(p.name) + '" data-act="dl" download>Phần ' +
        p.part + (p.rows == null ? "" : " (" + p.rows + " dòng)") + '</a>';
    }).join("") + '</div></details>' : "";
    return '<li class="st-file' + (f["new"] ? " st-file--new" : "") + '"><span class="st-ic">' + (run ? IC.xls : IC.file) + '</span>' +
      '<div class="st-file-main"><div class="st-file-name"><span class="st-file-title" title="' + esc(name) + '">' + esc(name) + '</span>' +
      (f["new"] ? '<span class="st-new">Mới</span>' : "") + '</div><div class="st-file-meta">' + esc(meta) + '</div>' + parts + '</div>' +
      '<span class="st-file-time st-num">' + esc(f.time || f.at) + '</span>' +
      '<a class="st-btn st-btn--sm' + (run ? " st-btn--primary" : "") + '" href="' + href + '" data-act="dl" download aria-label="Tải ' + esc(name) + '">' +
      (run ? "Tải Excel" : "Tải file") + '</a></li>';
  }
  function filesCard() {
    var all = S.exports || [], list = filterFiles(all);
    var pages = Math.max(1, Math.ceil(list.length / FILES_PER_PAGE));
    if (filePage > pages) filePage = pages;
    var counts = {};
    list.forEach(function (f) { counts[f.day] = (counts[f.day] || 0) + 1; });
    var day = null, body = "";
    list.slice((filePage - 1) * FILES_PER_PAGE, filePage * FILES_PER_PAGE).forEach(function (f) {
      if (f.day !== day) {
        if (day !== null) body += '</ul>';
        day = f.day;
        body += '<div class="st-glabel">' + esc(day || "Cũ hơn") + ' · ' + (counts[day] || 0) + '</div><ul class="st-files">';
      }
      body += fileRow(f);
    });
    if (day !== null) body += '</ul>';
    var tools = all.length ? '<div class="st-ftools"><label class="st-search" for="st-fq">' + IC.search +
      '<input id="st-fq" type="search" placeholder="Tìm file theo tên trang…" value="' + esc(fileQuery) + '" autocomplete="off" aria-label="Tìm file"></label>' +
      '<div class="st-chips" role="group" aria-label="Lọc file">' + chips(all) + '</div></div>' : "";
    var empty = !all.length ? '<p class="st-empty st-empty--pad">Chưa có file nào.</p>'
      : !list.length ? '<p class="st-empty st-empty--pad">Không có file khớp bộ lọc.</p>' : "";
    var from = list.length ? (filePage - 1) * FILES_PER_PAGE + 1 : 0, to = Math.min(filePage * FILES_PER_PAGE, list.length);
    return '<section class="st-panel st-panel--list" aria-labelledby="st-h-files"><div class="st-ph"><h2 class="st-h2" id="st-h-files">File đã xuất của tôi</h2>' +
      '<span class="st-muted">' + all.length + ' file · giữ 7 ngày</span></div>' + tools + body + empty +
      '<div class="st-lfoot"><span class="st-muted">' + (list.length ? from + "–" + to + " / " + list.length + " · " : "") +
      'Bấm Xuất bảng hoặc Export trong ' + esc(S.tool.title) + ', file hiện ở đây sau vài giây.</span>' + pager(list.length) + '</div></section>';
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
    Array.prototype.forEach.call(root.querySelectorAll("[data-left-min]"), function (el) {
      el.textContent = Math.ceil(left(me[el.getAttribute("data-left-min")] || 0) / 60) + "′";
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
    if (a === "open") { if (armed(btn)) openTool(btn); return; }
    if (a === "fpage") { filePage = Math.max(1, +btn.getAttribute("data-page") || 1); render(); return; }
    if (a === "ffilter") { fileFilter = btn.getAttribute("data-f") || "all"; filePage = 1; render(); return; }
    if (a === "stats") { if (window.ECStStats) window.ECStStats.load(+btn.getAttribute("data-days") || 30); return; }
    if (!armed(btn)) return;
    var map = { join: ["join", "Đã vào hàng đợi."], leave: ["leave", "Đã cập nhật lượt của bạn."],
                extend: ["extend", "Đã gia hạn thêm " + S.tool.extend + " phút."], force: ["force_end", "Đã kết thúc lượt đó."],
                "admin-reset": ["admin_reset", "Đã xoá phiên đăng nhập cũ. Làm tiếp các bước trong khung Quản lý."],
                "admin-open": ["admin_enable", "Đã mở lại cho mọi người."], "admin-close": ["admin_enable", "Đã tạm đóng công cụ."] };
    var m = map[a];
    if (!m) return;
    busy(btn, true);
    try {
      var args = { tool: TOOL };
      if (a === "force") args.entry = btn.getAttribute("data-entry");
      if (a === "admin-open" || a === "admin-close") args.on = a === "admin-open" ? 1 : 0;
      if (a === "admin-reset") toast("Đang xoá phiên đăng nhập trên máy Kalodata, chờ khoảng 10–20 giây…");
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
    root.addEventListener("input", function (ev) {
      if (ev.target.id !== "st-fq") return;
      fileQuery = ev.target.value;
      filePage = 1;
      clearTimeout(fqT);
      fqT = setTimeout(render, 200);
    });
    document.addEventListener("visibilitychange", function () { if (!document.hidden && S) refresh(); });
    tickT = setInterval(paintTimers, 1000);
    refresh(true);
  }

  // ec_st_stats.js (khoi thong ke cho quan ly) dung lai api / esc / ve lai trang.
  window.ECSt = { refresh: refresh, api: api, esc: esc, msg: msg, rerender: function () { if (S) render(); } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
