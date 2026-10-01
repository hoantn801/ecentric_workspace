// Copyright (c) 2026, eCentric and contributors
// ec_survey_core.js -- phan DUNG CHUNG cua 4 trang khao sat: goi API, toast/modal, dinh dang
// ngay gio, ve + doc cau tra loi tung loai cau hoi, duong di qua cac phan.
//
// Goi API qua window.ecApi (public/js/ec_api.js, nap moi trang qua hooks web_include_js): xin
// CSRF tuoi + thu lai mot lan khi gap CSRFTokenError. Khong tin window.frappe.csrf_token (HTML
// trang co the la ban cache cua phien khac - su co 14/09 va 17/09).
//
// SERVER LA NGUON SU THAT. path() o day chi de biet "trang ke tiep" (UX); luc nop server tinh
// lai duong di va kiem bat buoc tu dau (surveys/domain/answers.py). Doi quy tac re nhanh thi
// sua CA HAI noi - test: approval_center/tests/js/test_survey_core.mjs.
(function () {
  "use strict";
  if (window.ECSvy) return;
  var PREFIX = "ecentric_workspace.surveys.controllers.api.";
  var GOTO_SUBMIT = "__submit__";
  var START = "__start__";

  // ------------------------------------------------------------------ tien ich --
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function byId(id) { return document.getElementById(id); }
  function qsa(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }
  function uid(p) { return (p || "i") + Math.random().toString(36).slice(2, 9); }
  function param(name) { return new URLSearchParams(window.location.search).get(name) || ""; }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }

  var ICONS = {
    plus: '<path d="M12 5v14M5 12h14"/>', trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    up: '<path d="m18 15-6-6-6 6"/>', down: '<path d="m6 9 6 6 6-6"/>', x: '<path d="M18 6 6 18M6 6l12 12"/>',
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    check: '<path d="M20 6 9 17l-5-5"/>', clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    gift: '<rect x="3" y="8" width="18" height="13" rx="1"/><path d="M12 8v13M3 12h18M12 8c-2-4-6-4-6-1.5S9 8 12 8zm0 0c2-4 6-4 6-1.5S15 8 12 8z"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>', back: '<path d="M15 18l-6-6 6-6"/>',
    section: '<rect x="3" y="4" width="18" height="6" rx="1"/><rect x="3" y="14" width="18" height="6" rx="1"/>',
    text: '<path d="M4 7V5h16v2M9 19h6M12 5v14"/>', upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
    star: '<path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4 6.1 20.5l1.2-6.5L2.5 9.4l6.6-.9z"/>',
    send: '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/>', bell: '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    download: '<path d="M12 4v12M7 11l5 5 5-5M4 20h16"/>', link: '<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
    trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>'
  };
  function icon(n) { return '<svg class="svy-ico" viewBox="0 0 24 24" aria-hidden="true">' + (ICONS[n] || "") + "</svg>"; }

  // ------------------------------------------------------------------------ API --
  function friendly(e) {
    if (e && e.csrf) return "Phiên làm việc đã đổi. Bấm Ctrl+Shift+R để tải lại trang (vẫn lỗi thì đăng xuất rồi đăng nhập lại).";
    if (e && (e.status === 403 || e.excType === "PermissionError")) return "Bạn không có quyền làm thao tác này, hoặc phiên đăng nhập đã hết.";
    if (e && e.status === 0) return "Mất kết nối mạng.";
    return (e && e.svyMessage) || "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT.";
  }
  function api(method, args, post) {
    if (!window.ecApi) return Promise.reject(Object.assign(new Error("noapi"), { svyMessage: "Trang chưa tải xong - bấm Ctrl+Shift+R." }));
    var p = post ? window.ecApi.post(PREFIX + method, args || {}) : window.ecApi.get(PREFIX + method, args || {});
    return p.then(function (env) {
      if (env && env.success) return env.data;
      var err = new Error((env && env.message) || "fail");
      err.svyMessage = (env && env.message) || "";
      err.data = env && env.data;
      throw err;
    }, function (e) { e.svyMessage = friendly(e); throw e; });
  }
  function apiUrl(method, args) {
    return "/api/method/" + PREFIX + method + "?" + new URLSearchParams(args || {}).toString();
  }

  function uploadFile(file) {
    var fd = new FormData();
    fd.append("file", file, file.name);
    fd.append("is_private", "1");
    fd.append("folder", "Home/Attachments");
    var tokenP = window.ecApi ? window.ecApi.csrfToken(false) : Promise.resolve("");
    return tokenP.then(function (tok) {
      return fetch("/api/method/upload_file", { method: "POST", credentials: "same-origin",
        headers: { "X-Frappe-CSRF-Token": tok || "", Accept: "application/json" }, body: fd });
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok || !j.message || !j.message.file_url) {
          var e = new Error("upload");
          e.svyMessage = r.status === 413 ? "Tệp quá lớn (giới hạn khoảng 25 MB)." : "Không tải được tệp lên.";
          throw e;
        }
        return { url: j.message.file_url, name: j.message.file_name || file.name };
      });
    });
  }

  // ---------------------------------------------------------------- toast / modal --
  var toastTimer = null;
  function toast(msg, isErr) {
    var t = byId("svy-toast");
    if (!t) { t = document.createElement("div"); t.id = "svy-toast"; t.className = "svy-toast"; t.setAttribute("role", "status"); (byId("ec-svy") || document.body).appendChild(t); }
    t.textContent = msg;
    t.className = "svy-toast show" + (isErr ? " err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.className = "svy-toast" + (isErr ? " err" : ""); }, isErr ? 6500 : 3200);
  }
  function modal(html, opts) {
    opts = opts || {};
    var wrap = document.createElement("div");
    wrap.className = "svy-modal";
    wrap.innerHTML = '<div class="box' + (opts.wide ? " wide" : "") + '" role="dialog" aria-modal="true">' + html + "</div>";
    (byId("ec-svy") || document.body).appendChild(wrap);
    function close() { wrap.remove(); document.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); }
    document.addEventListener("keydown", onKey);
    wrap.addEventListener("click", function (e) { if (e.target === wrap || e.target.closest("[data-close]")) close(); });
    var first = wrap.querySelector("input,textarea,button.pri,button");
    if (first) setTimeout(function () { first.focus(); }, 30);
    return { el: wrap, box: wrap.firstChild, close: close };
  }
  function confirmBox(title, text, okLabel, danger) {
    return new Promise(function (resolve) {
      var m = modal("<h3>" + esc(title) + '</h3><div class="svy-muted" style="white-space:pre-line">' + esc(text || "") +
        '</div><div class="svy-row" style="justify-content:flex-end"><button class="svy-b" data-close>Huỷ</button>' +
        '<button class="svy-b ' + (danger ? "danger" : "pri") + '" data-ok>' + esc(okLabel || "Đồng ý") + "</button></div>");
      m.box.querySelector("[data-ok]").addEventListener("click", function () { m.close(); resolve(true); });
      m.el.addEventListener("click", function (e) { if (e.target === m.el || e.target.closest("[data-close]")) resolve(false); });
    });
  }
  function busy(btn, on) { if (!btn) return; btn.disabled = !!on; btn.classList.toggle("busy", !!on); }

  // --------------------------------------------------------------- ngay gio --
  function parseDt(s) {
    if (!s) return null;
    var m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
    return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : null;
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function fmtDt(s) {
    var d = parseDt(s);
    return d ? pad(d.getHours()) + ":" + pad(d.getMinutes()) + " " + pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + "/" + d.getFullYear() : "";
  }
  function fmtDate(s) { var d = parseDt(s); return d ? pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + "/" + d.getFullYear() : ""; }
  function toLocalInput(s) { return s ? String(s).slice(0, 16).replace(" ", "T") : ""; }
  function deadline(s) {
    var d = parseDt(s);
    if (!d) return "";
    var ms = d - new Date();
    if (ms <= 0) return "đã hết hạn";
    var h = Math.floor(ms / 3600000);
    if (h < 1) return "còn " + Math.max(1, Math.floor(ms / 60000)) + " phút";
    if (h < 48) return "còn " + h + " giờ";
    return "còn " + Math.floor(h / 24) + " ngày";
  }
  function initials(name) {
    var p = String(name || "?").trim().split(/\s+/);
    return ((p.length > 1 ? p[p.length - 2][0] : "") + p[p.length - 1][0]).toUpperCase();
  }

  // ------------------------------------------------------------ cau truc form --
  function sections(form) {
    var out = [], cur = { id: START, sec: null, items: [] };
    (form.items || []).forEach(function (it) {
      if (it.kind === "section") {
        if (cur.sec || cur.items.length) out.push(cur);
        cur = { id: it.id, sec: it, items: [] };
      } else cur.items.push(it);
    });
    if (cur.sec || cur.items.length || !out.length) out.push(cur);
    return out;
  }
  function selected(ans) {
    if (ans && typeof ans === "object" && !Array.isArray(ans)) return Array.isArray(ans.sel) ? ans.sel : (ans.sel ? [ans.sel] : []);
    return typeof ans === "string" && ans ? [ans] : [];
  }
  function branchTarget(items, answers) {
    var target = null;
    items.forEach(function (q) {
      if (q.kind !== "question" || !q.branch) return;
      var sel = selected(answers[q.id]);
      if (!sel.length) return;
      (q.options || []).forEach(function (o) { if (o.id === sel[0] && o.goto) target = o.goto; });
    });
    return target;
  }
  // Ban sao cua answers.path() phia server - XEM GHI CHU dau file.
  function path(form, answers) {
    answers = answers || {};
    var secs = sections(form), order = {}, out = [], i = 0;
    secs.forEach(function (s, k) { order[s.id] = k; });
    while (i >= 0 && i < secs.length) {
      var s = secs[i];
      out.push(s.id);
      var t = branchTarget(s.items, answers);
      if (t === null) t = (s.sec && s.sec.next) || "";
      if (t === GOTO_SUBMIT) break;
      var j = t ? (order[t] === undefined ? -1 : order[t]) : i + 1;
      i = j > i ? j : i + 1;
    }
    return out;
  }
  function questions(form) { return (form.items || []).filter(function (it) { return it.kind === "question"; }); }

  function isEmpty(q, v) {
    if (v === undefined || v === null || v === "") return true;
    if (Array.isArray(v)) return !v.length;
    if (typeof v === "object") {
      if (q && (q.type === "single" || q.type === "multi" || q.type === "dropdown")) return !selected(v).length && !v.other;
      return !Object.keys(v).length;
    }
    return false;
  }

  // Xao tron co hat giong: cung nguoi + cung khao sat -> cung thu tu khi tai lai trang.
  function seeded(seedStr) {
    var h = 2166136261;
    for (var i = 0; i < seedStr.length; i++) { h ^= seedStr.charCodeAt(i); h = Math.imul(h, 16777619); }
    return function () { h ^= h << 13; h ^= h >>> 17; h ^= h << 5; return ((h >>> 0) % 100000) / 100000; };
  }
  // Mau chu doc duoc tren nen mau the (phuong an A "The mau"): nen sang (vang) -> chu den.
  function onColor(hex) {
    var m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return "#fff";
    var n = parseInt(m[1], 16), r = n >> 16 & 255, g = n >> 8 & 255, b = n & 255;
    return (0.299 * r + 0.587 * g + 0.114 * b) > 170 ? "#111827" : "#fff";
  }
  function accentVars(hex) {
    var c = /^#[0-9a-f]{6}$/i.test(hex || "") ? hex : "#2C3DA6";
    return "--c:" + c + ";--on-c:" + onColor(c);
  }

  function shuffle(arr, rnd) {
    var a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(rnd() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; }
    return a;
  }

  window.ECSvy = {
    esc: esc, byId: byId, qsa: qsa, uid: uid, param: param, clone: clone, icon: icon,
    api: api, apiUrl: apiUrl, friendly: friendly, uploadFile: uploadFile,
    toast: toast, modal: modal, confirm: confirmBox, busy: busy,
    parseDt: parseDt, fmtDt: fmtDt, fmtDate: fmtDate, toLocalInput: toLocalInput, deadline: deadline, initials: initials,
    sections: sections, path: path, questions: questions, selected: selected, isEmpty: isEmpty,
    seeded: seeded, shuffle: shuffle, onColor: onColor, accentVars: accentVars, GOTO_SUBMIT: GOTO_SUBMIT, START: START
  };
})();
