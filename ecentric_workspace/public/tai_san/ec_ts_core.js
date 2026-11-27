// Copyright (c) 2026, eCentric and contributors
// ec_ts_core.js -- phan DUNG CHUNG cua 6 trang Quan ly tai san: goi API, toast, modal, dinh dang,
// pill trang thai, bo chon nhan vien / thiet bi. Goi API qua window.ecApi (public/js/ec_api.js).
// KHONG co luat nghiep vu o day: quyen, chuyen trang thai, khau hao deu o server (tai_san/).
(function () {
  "use strict";
  if (window.ECTs) return;
  var PREFIX = "ecentric_workspace.tai_san.controllers.api.";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function byId(id) { return document.getElementById(id); }
  function qsa(root, sel) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function param(n) { return new URLSearchParams(window.location.search).get(n) || ""; }
  function setParam(n, v) {
    var u = new URL(window.location.href);
    if (v) u.searchParams.set(n, v); else u.searchParams.delete(n);
    history.replaceState(null, "", u.pathname + (u.search || "") + u.hash);
  }

  // window.ecApi nap qua hooks web_include_js (CUOI <body>, sau noi dung trang): doi toi khi co.
  function whenApi() {
    if (window.ecApi) return Promise.resolve(window.ecApi);
    return new Promise(function (resolve, reject) {
      var n = 0;
      (function wait() {
        if (window.ecApi) return resolve(window.ecApi);
        if (++n > 160) { var e = new Error("noapi"); e.tsMessage = "Trang chưa tải xong - bấm Ctrl+Shift+R."; return reject(e); }
        setTimeout(wait, 50);
      })();
    });
  }
  function api(method, args, post) {
    return whenApi().then(function (ea) {
      var p = post ? ea.post(PREFIX + method, args || {}) : ea.get(PREFIX + method, args || {});
      return p.then(function (env) {
        if (env && env.success) return env.data;
        var err = new Error((env && env.message) || "fail");
        err.tsMessage = (env && env.message) || "";
        err.denied = !!(env && env.data && env.data.denied);
        throw err;
      }, function (e) {
        if (e && e.csrf) e.tsMessage = "Phiên làm việc đã đổi. Bấm Ctrl+Shift+R để tải lại trang.";
        else if (e && e.status === 0) e.tsMessage = "Mất kết nối mạng.";
        else if (e && (e.status === 403 || e.status === 401)) e.tsMessage = "Phiên đăng nhập đã hết - đăng nhập lại nhé.";
        throw e;
      });
    });
  }
  function get(method, args) { return api(method, args, false); }
  function post(method, args) { return api(method, args, true); }
  // Trang chi danh cho quan ly: nguoi khong co quyen tong quan duoc dua ve "Tai san cua toi".
  var MINE_ROUTE = "/tai-san/cua-toi";
  function toMineIfDenied(e) {
    if (!(e && e.denied)) return false;
    window.location.replace(MINE_ROUTE);
    return true;
  }
  function msg(e) { return (e && e.tsMessage) || "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."; }

  function rootEl() { return byId("ec-ts") || document.body; }
  var toastT;
  function toast(text, bad) {
    var el = byId("ec-ts-toast");
    if (!el) { el = document.createElement("div"); el.id = "ec-ts-toast"; el.setAttribute("role", "status"); rootEl().appendChild(el); }
    el.className = bad ? "bad" : "";
    el.textContent = text;
    el.hidden = false;
    clearTimeout(toastT);
    toastT = setTimeout(function () { el.hidden = true; }, bad ? 6000 : 2600);
  }
  function busy(btn, on) { if (btn) { btn.disabled = !!on; btn.classList.toggle("busy", !!on); } }

  // modal(title, bodyHtml, footHtml, onMount(el, close), wide)
  function modal(title, body, foot, onMount, wide) {
    var bg = document.createElement("div");
    bg.className = "ts-modal-bg";
    bg.innerHTML = '<div class="ts-modal' + (wide ? " ts-wide" : "") + '" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
      '<div class="ts-mh"><div class="ts-mt">' + esc(title) + '</div><span class="ts-sp"></span>' +
      '<button type="button" class="ts-btn ts-sm" data-close aria-label="Đóng">' + icon("x") + "</button></div>" +
      '<div class="ts-mb">' + body + "</div>" + (foot ? '<div class="ts-mf">' + foot + "</div>" : "") + "</div>";
    rootEl().appendChild(bg);
    function close() { if (bg.parentNode) bg.parentNode.removeChild(bg); document.removeEventListener("keydown", onKey); }
    // Esc chi dong modal tren cung (modal con mo tu form - vd Them phan mem moi - khong dong luon form cha).
    function onKey(e) {
      if (e.key !== "Escape") return;
      var all = document.querySelectorAll(".ts-modal-bg");
      if (all[all.length - 1] === bg) close();
    }
    document.addEventListener("keydown", onKey);
    bg.addEventListener("click", function (e) { if (e.target === bg || (e.target.closest && e.target.closest("[data-close]"))) close(); });
    if (onMount) onMount(bg.firstChild, close);
    var f = bg.querySelector("input,select,textarea,button.ts-primary");
    if (f) setTimeout(function () { try { f.focus(); } catch (x) { /* bo qua */ } }, 30);
    return close;
  }
  function confirmBox(title, text, okLabel, danger) {
    return new Promise(function (resolve) {
      modal(title, "<p>" + esc(text) + "</p>",
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ' + (danger ? "ts-danger" : "ts-primary") + '" data-ok>' + esc(okLabel || "Đồng ý") + "</button>",
        function (el, close) {
          el.querySelector("[data-ok]").addEventListener("click", function () { close(); resolve(true); });
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(false); });
        });
    });
  }

  var ICONS = {
    x: '<path d="M18 6 6 18M6 6l12 12"/>', chevron: '<path d="m6 9 6 6 6-6"/>', plus: '<path d="M12 5v14M5 12h14"/>', search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    laptop: '<rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/>', pc: '<rect x="3" y="4" width="13" height="10" rx="1.5"/><path d="M7 18h5M9.5 14v4"/><rect x="18" y="4" width="3.5" height="14" rx="1"/>',
    monitor: '<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4"/>', printer: '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="1.5"/><path d="M7 14h10v7H7z"/>',
    chip: '<rect x="6" y="6" width="12" height="12" rx="1.5"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    check: '<path d="M20 6 9 17l-5-5"/>', alert: '<path d="M12 3 2 21h20z"/><path d="M12 10v5M12 18v.5"/>', back: '<path d="M15 18l-6-6 6-6"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>', box: '<path d="M3 7l9-4 9 4-9 4z"/><path d="M3 7v10l9 4 9-4V7M12 11v10"/>',
    bookmark: '<path d="M6 3h12v18l-6-4-6 4z"/>', clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    coins: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
    trend: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>', key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l3 3M14 9l2 2"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
    wrench: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.4 2.4-2.6-.6-.6-2.6z"/>', link: '<path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>'
  };
  function icon(n) { return '<svg class="ts-ico" viewBox="0 0 24 24" aria-hidden="true">' + (ICONS[n] || "") + "</svg>"; }
  // O icon mau cua the so lieu (cung kieu o icon the Approval Center): nen nhat cung mau, bo goc 9px.
  function kpiIcon(n, color) {
    return '<span class="ts-kpi-ic" style="--c:' + esc(color || "#2C3DA6") + '">' + icon(n) + "</span>";
  }
  // The so lieu NGANG (Hoan 27/11: the doc "hoi xau"): o icon trai, nhan nho + so lon ben phai, so 0 mo.
  // value: chuoi HTML da escape (so da dinh dang); sub: HTML; extra: HTML them cuoi (vd thanh %).
  function kpiCard(o) {
    var tag = o.href ? "a" : o.button ? "button" : "div";
    var attrs = (o.href ? ' href="' + esc(o.href) + '"' : "") + (o.button ? ' type="button"' : "") + (o.attrs || "") +
      (o.title ? ' title="' + esc(o.title) + '"' : "");
    var zero = String(o.raw == null ? "" : o.raw) === "0";
    return "<" + tag + ' class="ts-kpi ts-kr"' + attrs + ">" + kpiIcon(o.icon, o.color) + '<div class="ts-kb">' +
      '<div class="ts-kpi-l">' + esc(o.label) + '</div><div class="ts-kpi-v' + (zero ? " ts-zero" : "") + '">' + o.value + "</div>" +
      // Dong phu LUON co (trong = &nbsp;): nhan / so cac the cung hang nam cung mot do cao.
      '<div class="ts-kpi-s">' + (o.sub || "&nbsp;") + "</div>" + (o.extra || "") + "</div></" + tag + ">";
  }
  function deviceIcon(cat) {
    var c = String(cat || "").toUpperCase();
    var n = c.indexOf("PC") === 0 || c.indexOf("DESKTOP") >= 0 ? "pc" : c.indexOf("MONITOR") >= 0 ? "monitor" :
      c.indexOf("PRINT") >= 0 ? "printer" : (c.indexOf("RAM") >= 0 || c.indexOf("SSD") >= 0 || c.indexOf("GPU") >= 0) ? "chip" : "laptop";
    return '<svg viewBox="0 0 24 24" aria-hidden="true">' + ICONS[n] + "</svg>";
  }

  // ---- trang thai (mau cham theo DESIGN.md / API.md: nen xam + cham mau) ----
  var STATUS = {
    "Available": { l: "Sẵn sàng", c: "#10b981" }, "Reserved": { l: "Đã giữ chỗ", c: "#9ca3af", ring: 1 },
    "In Use": { l: "Đang dùng", c: "#2C3DA6" }, "Pending Check": { l: "Chờ kiểm tra", c: "#d97706", ring: 1 },
    "Broken": { l: "Hỏng chờ xử lý", c: "#dc2626" }, "Under Repair": { l: "Đang sửa", c: "#d97706" },
    "Lost": { l: "Mất", c: "#6b7280" }, "Disposed": { l: "Thanh lý", c: "#d1d5db" }, "Retired": { l: "Ngừng dùng", c: "#9ca3af" }
  };
  var STATUS_ORDER = ["Available", "Reserved", "In Use", "Pending Check", "Broken", "Under Repair", "Lost", "Disposed", "Retired"];
  function statusLabel(s, labels) { return (labels && labels[s]) || (STATUS[s] && STATUS[s].l) || s || "—"; }
  function statusColor(s) { return (STATUS[s] && STATUS[s].c) || "#9ca3af"; }
  function dot(s) {
    var st = STATUS[s] || {};
    return st.ring ? '<span class="ts-dot ring" style="color:' + statusColor(s) + '"></span>' : '<span class="ts-dot" style="background:' + statusColor(s) + '"></span>';
  }
  function pill(s, labels) { return '<span class="ts-pill">' + dot(s) + esc(statusLabel(s, labels)) + "</span>"; }
  var COND = { "Good": "Tốt", "Partially Damaged": "Hỏng một phần", "Fully Damaged": "Hỏng toàn bộ" };
  function condPill(c) {
    if (!c || c === "Good") return '<span class="ts-pill">Tốt</span>';
    return '<span class="ts-pill ' + (c === "Fully Damaged" ? "ts-cond-full" : "ts-cond-partial") + '">' + esc(COND[c] || c) + "</span>";
  }
  var OWN = { "Owned": "Công ty sở hữu", "Rented": "Đi thuê", "Personal": "Máy cá nhân (phụ cấp)" };

  // ---- dinh dang ----
  function fmtNum(n) { return Math.round(Number(n || 0)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "."); }
  function fmtMoney(n) { return fmtNum(n) + " ₫"; }
  function fmtMillion(n) {
    var v = Number(n || 0) / 1e6;
    return v.toFixed(1).replace(".", ",") + " tr";
  }
  function fmtDate(s) {
    if (!s) return "";
    var p = String(s).slice(0, 10).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : String(s);
  }
  function fmtDT(s) { return s ? fmtDate(s) + " " + String(s).slice(11, 16) : ""; }
  function fmtMonth(ym) { var p = String(ym || "").split("-"); return p.length >= 2 ? "T" + parseInt(p[1], 10) + "/" + p[0].slice(2) : ym; }
  function skel(n) {
    var h = "";
    for (var i = 0; i < (n || 3); i++) h += '<div class="ts-skel" style="width:' + (40 + (i * 23) % 55) + '%"></div>';
    return h;
  }
  function errBox(e, retry) {
    return '<div class="ts-err">' + icon("alert") + "<span>" + esc(msg(e)) + "</span>" +
      (retry ? '<button type="button" class="ts-btn ts-sm" data-retry>Thử lại</button>' : "") + "</div>";
  }

  // ---- bo chon co tim kiem: picker(rows, {label(r), sub(r), right(r), selected, onPick}) ----
  function picker(host, rows, opt) {
    opt = opt || {};
    var state = { q: "", sel: opt.selected || null };
    host.innerHTML = '<input class="ts-in" type="search" placeholder="' + esc(opt.placeholder || "Tìm…") + '" aria-label="Tìm"><div class="ts-pick" role="listbox"></div>';
    var inp = host.querySelector("input"), list = host.querySelector(".ts-pick");
    function draw() {
      var q = state.q.toLowerCase();
      var hit = rows.filter(function (r) { return !q || (opt.text ? opt.text(r) : opt.label(r)).toLowerCase().indexOf(q) >= 0; });
      if (!hit.length) { list.innerHTML = '<div class="ts-empty">' + esc(!rows.length && opt.emptyText ? opt.emptyText : "Không có kết quả.") + "</div>"; return; }
      list.innerHTML = hit.slice(0, 120).map(function (r) {
        var k = opt.key ? opt.key(r) : r.name;
        return '<button type="button" class="ts-opt' + (k === state.sel ? " on" : "") + '" data-k="' + esc(k) + '" role="option" aria-selected="' + (k === state.sel) + '">' +
          '<span class="ts-opt-main"><b class="ts-strong">' + esc(opt.label(r)) + "</b>" + (opt.sub ? '<span class="ts-note" style="display:block">' + esc(opt.sub(r) || "") + "</span>" : "") +
          "</span>" + (opt.right ? '<span class="ts-note">' + (opt.right(r) || "") + "</span>" : "") + "</button>";
      }).join("");
    }
    inp.addEventListener("input", function () { state.q = inp.value; draw(); });
    list.addEventListener("click", function (e) {
      var b = e.target.closest(".ts-opt"); if (!b) return;
      state.sel = b.getAttribute("data-k"); draw();
      if (opt.onPick) opt.onPick(state.sel, rows.filter(function (r) { return (opt.key ? opt.key(r) : r.name) === state.sel; })[0]);
    });
    draw();
    return { value: function () { return state.sel; } };
  }
  // O chon tu danh muc (phan mem ban quyen, mau thiet bi): bam -> danh sach tim duoc + nut "Them moi".
  // opt: rows, selected, placeholder, label(r), sub(r), addLabel, onAdd() -> Promise(row|null), onPick(k, r).
  // Them moi xong -> dong moi duoc chon ngay. Tra ve { value(), row() }.
  function catalogPick(host, opt) {
    var rows = opt.rows || [], sel = opt.selected || null;
    host.innerHTML = '<button type="button" class="ts-in ts-pickfield" data-cp-btn aria-haspopup="listbox"><span data-cp-label></span>' + icon("chevron") + "</button>" +
      '<div class="ts-cp-panel" data-cp-panel hidden><div data-cp-list></div>' +
      (opt.onAdd ? '<button type="button" class="ts-btn ts-sm ts-cp-add" data-cp-add>' + icon("plus") + esc(opt.addLabel || "Thêm mới") + "</button>" : "") + "</div>";
    var btn = host.querySelector("[data-cp-btn]"), panel = host.querySelector("[data-cp-panel]");
    function rowOf(k) { return rows.filter(function (r) { return r.name === k; })[0] || null; }
    function paint() {
      var r = rowOf(sel), lab = host.querySelector("[data-cp-label]");
      lab.className = r ? "" : "ts-ph";
      lab.innerHTML = r ? esc(opt.label(r)) + (opt.sub && opt.sub(r) ? ' <span class="ts-note">· ' + esc(opt.sub(r)) + "</span>" : "") : esc(opt.placeholder || "Chọn…");
    }
    function list() {
      picker(host.querySelector("[data-cp-list]"), rows, { placeholder: "Tìm…", label: opt.label, sub: opt.sub, selected: sel,
        emptyText: opt.onAdd ? "Danh mục chưa có gì - bấm " + (opt.addLabel || "Thêm mới") + "." : "",
        onPick: function (k, r) { choose(k, r); } });
    }
    function choose(k, r) {
      sel = k; paint(); panel.hidden = true;
      if (opt.onPick) opt.onPick(k, r || rowOf(k));
    }
    btn.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) { list(); var i = panel.querySelector("input"); if (i) i.focus(); }
    });
    var add = host.querySelector("[data-cp-add]");
    if (add) add.addEventListener("click", function () {
      var q = (panel.querySelector("input") || {}).value || "";
      opt.onAdd(q.trim()).then(function (r) {
        if (!r) return;
        if (!rowOf(r.name)) rows.push(r);
        choose(r.name, r);
      });
    });
    paint();
    return { value: function () { return sel; }, row: function () { return rowOf(sel); } };
  }
  // Tao dong danh muc qua `method` (create_product / create_model) co chan trung:
  // da co -> chon luon dong co san; giong ten -> hoi "dung cai co san?" hoac "van tao moi". -> Promise(row|null)
  function catalogCreate(method, data, what) {
    function send(force) { return post(method, { data: JSON.stringify(data), force: force ? 1 : 0 }); }
    return send(false).then(function (r) {
      if (r.exact) { toast("Đã có " + r.exact.label + " - chọn sẵn cho bạn."); return r.exact; }
      if (!r.similar) return r.row;
      return new Promise(function (resolve) {
        modal("Có thể đã có " + (what || "trong danh mục"),
          "<p>Danh mục đã có tên gần giống <b>" + esc(data.product_name || data.item_name || "") + "</b>. Dùng cái có sẵn để sau này gộp số liệu đúng:</p>" +
          '<div class="ts-pick">' + r.similar.map(function (x) {
            return '<button type="button" class="ts-opt" data-use="' + esc(x.name) + '"><span class="ts-opt-main"><b class="ts-strong">' + esc(x.label) + "</b>" +
              '<span class="ts-note" style="display:block">' + esc([x.vendor, x.category].filter(Boolean).join(" · ")) + "</span></span>" +
              '<span class="ts-note">Dùng cái này</span></button>';
          }).join("") + "</div>",
          '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn" data-force>Vẫn tạo mới</button>',
          function (el, close) {
            el.querySelector(".ts-pick").addEventListener("click", function (e) {
              var b = e.target.closest("[data-use]"); if (!b) return;
              var k = b.getAttribute("data-use");
              close(); resolve(r.similar.filter(function (x) { return x.name === k; })[0]);
            });
            el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
            el.querySelector("[data-force]").addEventListener("click", function (ev) {
              busy(ev.currentTarget, true);
              send(true).then(function (r2) { close(); resolve(r2.row || r2.exact || null); },
                function (e) { busy(ev.currentTarget, false); toast(msg(e), true); });
            });
          });
      });
    });
  }

  var cache = {};
  // fresh: bo cache (vd vua them mau thiet bi moi).
  function pickList(kind, category, fresh) {
    var k = kind + "|" + (category || "");
    if (fresh || !cache[k] || kind === "available" || kind === "components") cache[k] = get("pickers", { kind: kind, category: category || "" });
    return cache[k];
  }
  // Mo modal chon nhan vien -> Promise(employee name | null)
  function pickEmployee(title) {
    return new Promise(function (resolve) {
      var chosen = null;
      modal(title || "Chọn nhân viên", '<div data-pk>' + skel(4) + "</div>",
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok disabled>Chọn</button>',
        function (el, close) {
          var ok = el.querySelector("[data-ok]");
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          pickList("employees").then(function (rows) {
            picker(el.querySelector("[data-pk]"), rows, { placeholder: "Tên nhân viên…", label: function (r) { return r.label; },
              sub: function (r) { return r.department; }, onPick: function (k) { chosen = k; ok.disabled = false; } });
          }, function (e) { el.querySelector("[data-pk]").innerHTML = errBox(e); });
          ok.addEventListener("click", function () { close(); resolve(chosen); });
        });
    });
  }
  function checklistHtml(items, name) {
    return (items || []).map(function (t, i) {
      return '<label class="ts-ck"><input type="checkbox" name="' + esc(name || "ck") + '" value="' + esc(t) + '" data-i="' + i + '"><span>' + esc(t) + "</span></label>";
    }).join("");
  }
  function checklistValue(root, name) {
    var out = {};
    qsa(root, 'input[name="' + (name || "ck") + '"]').forEach(function (c) { out[c.value] = !!c.checked; });
    return out;
  }
  // ---- ban quyen: pill giai doan han (server tinh stage: OK / Due / Expired / null) ----
  function licPill(r) {
    if (r.status === "Cancelled") return '<span class="ts-pill">' + esc(r.status_label || "Đã huỷ") + "</span>";
    if (r.stage === "Expired") return '<span class="ts-pill ts-red">' + esc(r.stage_label || "Đã quá hạn") + "</span>";
    if (r.stage === "Due") return '<span class="ts-pill ts-amber">' + esc(r.stage_label || "Sắp hết hạn") + "</span>";
    if (r.stage === "OK") return '<span class="ts-pill"><span class="ts-dot" style="background:#10b981"></span>' + esc(r.stage_label || "Còn hạn") + "</span>";
    return '<span class="ts-pill">' + esc(r.type_label || "Vĩnh viễn") + "</span>";
  }
  function licDays(n) {
    if (n == null || n === "") return "";
    n = Number(n);
    return n < 0 ? "Quá " + (-n) + " ngày" : n === 0 ? "Hết hạn hôm nay" : "Còn " + n + " ngày";
  }
  function assetLine(r) {
    return '<span class="ts-tag">' + esc(r.tag || r.name) + "</span> · " + esc(r.asset_name || "");
  }

  window.ECTs = {
    esc: esc, byId: byId, qsa: qsa, param: param, setParam: setParam, get: get, post: post, msg: msg, toMineIfDenied: toMineIfDenied,
    toast: toast, busy: busy, modal: modal, confirmBox: confirmBox, icon: icon, kpiIcon: kpiIcon, kpiCard: kpiCard, deviceIcon: deviceIcon,
    pill: pill, dot: dot, condPill: condPill, statusLabel: statusLabel, statusColor: statusColor,
    STATUS_ORDER: STATUS_ORDER, COND: COND, OWN: OWN,
    fmtNum: fmtNum, fmtMoney: fmtMoney, fmtMillion: fmtMillion, fmtDate: fmtDate, fmtDT: fmtDT, fmtMonth: fmtMonth,
    skel: skel, errBox: errBox, picker: picker, pickList: pickList, pickEmployee: pickEmployee,
    catalogPick: catalogPick, catalogCreate: catalogCreate,
    checklistHtml: checklistHtml, checklistValue: checklistValue, assetLine: assetLine, licPill: licPill, licDays: licDays
  };
})();
