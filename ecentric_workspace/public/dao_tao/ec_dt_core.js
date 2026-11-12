// Copyright (c) 2026, eCentric and contributors
// ec_dt_core.js -- phan DUNG CHUNG cua cac trang Dao tao + Quiz: goi API, toast, modal, nhan
// vat (avatar SVG), tien ich. Goi API qua window.ecApi (public/js/ec_api.js, nap qua hooks).
// KHONG co luat nghiep vu o day: cham diem, gio, quyen deu o server (dao_tao/).
(function () {
  "use strict";
  if (window.ECDt) return;
  var PREFIX = "ecentric_workspace.dao_tao.controllers.api.";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function byId(id) { return document.getElementById(id); }
  function qsa(root, sel) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function param(n) { return new URLSearchParams(window.location.search).get(n) || ""; }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }

  var ICONS = {
    plus: '<path d="M12 5v14M5 12h14"/>', trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
    up: '<path d="m18 15-6-6-6 6"/>', down: '<path d="m6 9 6 6 6-6"/>', x: '<path d="M18 6 6 18M6 6l12 12"/>',
    check: '<path d="M20 6 9 17l-5-5"/>', play: '<path d="M7 4v16l13-8z"/>', back: '<path d="M15 18l-6-6 6-6"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    gift: '<rect x="3" y="8" width="18" height="13" rx="1"/><path d="M12 8v13M3 12h18M12 8c-2-4-6-4-6-1.5S9 8 12 8zm0 0c2-4 6-4 6-1.5S15 8 12 8z"/>',
    trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
    upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>', shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    ticket: '<path d="M3 8a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 0-2 2H5a2 2 0 0 0-2-2v-2a2 2 0 0 0 0-4z"/>',
    flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>', edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
    book: '<path d="M4 19a2 2 0 0 1 2-2h14V3H6a2 2 0 0 0-2 2z"/><path d="M4 19a2 2 0 0 0 2 2h14v-4"/>'
  };
  function icon(n) { return '<svg class="dt-ico" viewBox="0 0 24 24" aria-hidden="true">' + (ICONS[n] || "") + "</svg>"; }

  // window.ecApi nap qua hooks web_include_js - Frappe chen cac bundle do o CUOI <body>, SAU noi
  // dung trang, nen luc script trang chay lan dau ecApi CHUA co (loi deploy 12/11: trang trong
  // "Trang chua tai xong"). Doi toi khi co (toi da ~8 giay) roi moi goi.
  function whenApi() {
    if (window.ecApi) return Promise.resolve(window.ecApi);
    return new Promise(function (resolve, reject) {
      var n = 0;
      (function wait() {
        if (window.ecApi) return resolve(window.ecApi);
        if (++n > 160) return reject(Object.assign(new Error("noapi"), { dtMessage: "Trang chưa tải xong - bấm Ctrl+Shift+R." }));
        setTimeout(wait, 50);
      })();
    });
  }
  function api(method, args, post) {
    return whenApi().then(function () { return call(method, args, post); });
  }
  function call(method, args, post) {
    var p = post ? window.ecApi.post(PREFIX + method, args || {}) : window.ecApi.get(PREFIX + method, args || {});
    return p.then(function (env) {
      if (env && env.success) return env.data;
      var err = new Error((env && env.message) || "fail");
      err.dtMessage = (env && env.message) || "";
      err.data = env && env.data;
      throw err;
    }, function (e) {
      if (e && e.csrf) e.dtMessage = "Phiên làm việc đã đổi. Bấm Ctrl+Shift+R để tải lại trang.";
      else if (e && e.status === 0) e.dtMessage = "Mất kết nối mạng.";
      else if (e && (e.status === 403 || e.status === 401)) e.dtMessage = "Phiên đăng nhập đã hết - đăng nhập lại nhé.";
      throw e;
    });
  }
  // Quet QR bang camera -> trinh duyet chua dang nhap ERP: dua ve trang dang nhap roi quay lai.
  function loginRedirect(e) {
    var m = (e && e.dtMessage) || "";
    if ((e && (e.status === 403 || e.status === 401)) || /đăng nhập/i.test(m)) {
      location.href = "/login?redirect-to=" + encodeURIComponent(location.pathname + location.search);
      return true;
    }
    return false;
  }
  function msg(e) { return (e && e.dtMessage) || "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."; }

  var toastT;
  function toast(text, bad) {
    var el = byId("dt-toast");
    if (!el) { el = document.createElement("div"); el.id = "dt-toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
    el.className = "dt-toast" + (bad ? " bad" : "");
    el.textContent = text;
    el.hidden = false;
    clearTimeout(toastT);
    toastT = setTimeout(function () { el.hidden = true; }, bad ? 5000 : 2600);
  }
  function busy(btn, on) { if (btn) { btn.disabled = !!on; btn.classList.toggle("busy", !!on); } }

  function modal(html, onMount) {
    var bg = document.createElement("div");
    bg.className = "dt-modal-bg";
    bg.innerHTML = '<div class="dt-modal" role="dialog" aria-modal="true">' + html + "</div>";
    var root = byId("ec-dt") || document.body;
    root.appendChild(bg);
    function close() { bg.remove(); document.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); }
    document.addEventListener("keydown", onKey);
    bg.addEventListener("click", function (e) { if (e.target === bg || e.target.closest("[data-close]")) close(); });
    if (onMount) onMount(bg.firstChild, close);
    return close;
  }

  // ------------------------------------------------------------------ nhan vat --
  // Phai khop dao_tao/domain/profile.py (BODY_COLORS, BG_COLORS, EYES, ACCESSORIES).
  var AV = {
    b: ["#7C5CFF", "#FF6B6B", "#16A34A", "#F59E0B", "#0EA5E9", "#EC4899"],
    g: ["#EEF2FF", "#FEF3C7", "#DCFCE7", "#FCE7F3", "#E0F2FE", "#F1F5F9"],
    e: ["Tròn", "Cười", "Kính", "Ngủ"],
    a: ["Không", "Mũ", "Tai nghe", "Vương miện", "Nơ"]
  };
  function avIdx(av, k) { var v = parseInt((av || {})[k], 10); return v >= 0 && v < AV[k].length ? v : 0; }
  function avatarSvg(av) {
    var b = AV.b[avIdx(av, "b")], g = AV.g[avIdx(av, "g")], e = avIdx(av, "e"), a = avIdx(av, "a");
    var s = '<svg viewBox="0 0 100 100" aria-hidden="true"><rect width="100" height="100" fill="' + g + '"/>' +
      '<path d="M18 100 C18 60 30 34 50 34 C70 34 82 60 82 100Z" fill="' + b + '"/>' +
      '<circle cx="50" cy="46" r="26" fill="' + b + '"/>';
    if (e === 0) s += '<circle cx="41" cy="45" r="5" fill="#fff"/><circle cx="59" cy="45" r="5" fill="#fff"/><circle cx="42" cy="46" r="2.4" fill="#111"/><circle cx="60" cy="46" r="2.4" fill="#111"/>';
    else if (e === 1) s += '<path d="M35 46 q6 -6 12 0 M53 46 q6 -6 12 0" stroke="#111" stroke-width="3" fill="none" stroke-linecap="round"/>';
    else if (e === 2) s += '<circle cx="41" cy="45" r="7" fill="#fff" stroke="#111" stroke-width="2.5"/><circle cx="59" cy="45" r="7" fill="#fff" stroke="#111" stroke-width="2.5"/><path d="M48 45h4" stroke="#111" stroke-width="2.5"/><circle cx="41" cy="46" r="2.2" fill="#111"/><circle cx="59" cy="46" r="2.2" fill="#111"/>';
    else s += '<path d="M35 47h12 M53 47h12" stroke="#111" stroke-width="3" stroke-linecap="round"/>';
    s += '<path d="M43 57 q7 6 14 0" stroke="#111" stroke-width="2.6" fill="none" stroke-linecap="round"/>';
    if (a === 1) s += '<path d="M26 30 q24 -22 48 0 z" fill="#111827"/><rect x="22" y="28" width="56" height="5" rx="2" fill="#111827"/>';
    else if (a === 2) s += '<path d="M24 46 a26 26 0 0 1 52 0" stroke="#111827" stroke-width="5" fill="none"/><rect x="18" y="40" width="10" height="16" rx="4" fill="#111827"/><rect x="72" y="40" width="10" height="16" rx="4" fill="#111827"/>';
    else if (a === 3) s += '<path d="M32 26 l6 -12 l6 8 l6 -12 l6 12 l6 -8 l6 12 z" fill="#F5B800" stroke="#a87b00" stroke-width="1.5"/>';
    else if (a === 4) s += '<path d="M50 24 l-14 -8 v16 z M50 24 l14 -8 v16 z" fill="#EC4899"/><circle cx="50" cy="24" r="4" fill="#be185d"/>';
    return s + "</svg>";
  }
  function avatar(av, size) {
    size = size || 36;
    return '<span class="dt-av" style="width:' + size + "px;height:" + size + 'px">' + avatarSvg(av) + "</span>";
  }
  function pcard(p, size) {
    return '<span class="dt-pcard">' + avatar(p.avatar, size || 34) + '<span style="min-width:0"><span class="dt-nick">' +
      esc(p.nickname) + '</span><br><span class="dt-mail">' + esc(p.email || "") + "</span></span></span>";
  }

  // ------------------------------------------------------------------- dinh dang --
  function fmtNum(n) { return Number(n || 0).toLocaleString("vi-VN"); }
  function fmtDate(s) {
    if (!s) return "";
    var d = new Date(String(s).replace(" ", "T"));
    if (isNaN(d)) return String(s).slice(0, 10);
    return ("0" + d.getDate()).slice(-2) + "/" + ("0" + (d.getMonth() + 1)).slice(-2) + "/" + d.getFullYear();
  }
  // Noi dung bai hoc la CHU THUAN: thoat ky tu roi moi tu noi link https.
  function richText(s) {
    return esc(s).replace(/(https:\/\/[^\s<]+)/g, function (u) {
      return '<a href="' + u + '" target="_blank" rel="noopener noreferrer">' + u + "</a>";
    });
  }
  function safeUrl(u) {
    u = String(u || "");
    return (u.indexOf("https://") === 0 || u.indexOf("/files/") === 0 || u.indexOf("/private/files/") === 0) ? u : "";
  }
  function embedVideo(u) {
    u = safeUrl(u);
    var m = u.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]{6,})/);
    if (m) return '<div class="dt-video"><iframe src="https://www.youtube-nocookie.com/embed/' + esc(m[1]) + '" allowfullscreen loading="lazy" title="Video"></iframe></div>';
    if (/\.mp4(\?|$)/i.test(u)) return '<video src="' + esc(u) + '" controls style="width:100%;border-radius:12px"></video>';
    return u ? '<a class="dt-b" href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">Mở video</a>' : "";
  }

  function upload(file, isPrivate) {
    var fd = new FormData();
    fd.append("file", file, file.name);
    fd.append("is_private", isPrivate ? "1" : "0");
    fd.append("folder", "Home/Attachments");
    var tokP = whenApi().then(function (ea) { return ea.csrfToken ? ea.csrfToken(false) : ""; }, function () { return ""; });
    return tokP.then(function (tok) {
      return fetch("/api/method/upload_file", { method: "POST", credentials: "same-origin",
        headers: { "X-Frappe-CSRF-Token": tok || "", Accept: "application/json" }, body: fd });
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok || !j.message || !j.message.file_url) throw Object.assign(new Error("upload"), { dtMessage: "Tải tệp lên không được." });
        return j.message.file_url;
      });
    });
  }

  // Realtime (neu socket song) - chi la "cu hich" goi lai state; khong co thi van poll.
  function onRoom(session, fn) {
    var tries = 0;
    (function bind() {
      var rt = window.frappe && window.frappe.realtime, s = rt && rt.socket;
      if (s && typeof s.on === "function") {
        s.on("ec_quiz_room", function (m) { if (m && m.s === session) fn(m); });
        return;
      }
      if (++tries < 10) setTimeout(bind, 1500);
    })();
  }

  function skel(n) {
    var h = "";
    for (var i = 0; i < (n || 3); i++) h += '<div class="dt-panel dt-pad"><div class="dt-skel" style="width:40%"></div><div class="dt-skel" style="width:85%"></div></div>';
    return h;
  }

  window.ECDt = { api: api, msg: msg, esc: esc, byId: byId, qsa: qsa, param: param, clone: clone, icon: icon,
    toast: toast, busy: busy, loginRedirect: loginRedirect, modal: modal, AV: AV, avatar: avatar, avatarSvg: avatarSvg, pcard: pcard,
    fmtNum: fmtNum, fmtDate: fmtDate, richText: richText, safeUrl: safeUrl, embedVideo: embedVideo,
    upload: upload, onRoom: onRoom, skel: skel, LETTERS: ["A", "B", "C", "D", "E", "F"] };
})();
