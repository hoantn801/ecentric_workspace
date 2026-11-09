/* Trung tam Du lieu (/du-lieu) - asset dung chung cho 4 trang www/du_lieu (PO Hoan chot 09/11/2026).
 *
 * Server (data_hub/service.py) ve san trang thai dau: KPI, bang (da sap, bo loc "Dang mo"), kanban.
 * File nay chi: loc bang tai cho, bat Danh sach | Gantt (ve Gantt tu API), mo popup chi tiet giua man
 * hinh (ve tu API - MOT cho ve duy nhat, ca khi mo bang ?ma=), form tao yeu cau, hop Nhan viec,
 * cap nhat cua team Data, nghiem thu, trao doi (@ten, tep), theo doi. Moi ghi la POST toi
 * ecentric_workspace.data_hub.api.* (tra {success, message, data}).
 *
 * Ham thuan (sortKey, filterMatch, ganttLayout, slaDays, ...) gan vao window.ECDataHub de test jsdom
 * goi thang (data_hub/tests/js/test_ec_data_hub.mjs). Chong bam 2 lan: moi nut gui khoa toi khi xong.
 */
(function () {
  "use strict";
  if (typeof window === "undefined") return;
  if (window.ECDataHub && window.ECDataHub.__installed) return;

  var API = "/api/method/ecentric_workspace.data_hub.api.";
  var URGENT = "Khẩn";
  var PRI_RANK = { "Khẩn": 0, "Cao": 1, "Bình thường": 2, "Thấp": 3 };
  var ST = { WAIT: "Chờ tiếp nhận", DOING: "Đang xử lý", PAUSED: "Tạm dừng", REVIEW: "Chờ nghiệm thu",
             DONE: "Hoàn tất", CANCEL: "Huỷ" };
  var MAX_FILES = 5, FILE_MAX = 10 * 1024 * 1024;

  // ------------------------------------------------------------------ tien ich thuan ----------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function isoToDate(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : null;
  }
  function dateToIso(d) { return d.toISOString().slice(0, 10); }
  function addDays(iso, n) { var d = isoToDate(iso); d.setUTCDate(d.getUTCDate() + n); return dateToIso(d); }
  function dayDiff(a, b) { return Math.round((isoToDate(b) - isoToDate(a)) / 86400000); }
  function fmtDate(iso) { var d = isoToDate(iso); return d ? ("0" + d.getUTCDate()).slice(-2) + "/" + ("0" + (d.getUTCMonth() + 1)).slice(-2) : ""; }
  function fmtSize(n) { return n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"; }

  /* Khoa sap xep - GIONG data_hub/domain.py sort_key (test so khop hai ben):
   * dang mo: (cho nghiem thu xuong sau, Khan truoc, qua han truoc, han gan, gui truoc); da dong cuoi. */
  function sortKey(r) {
    if (r.scope !== "open") return [3, 0, 0, -(Date.parse((r.closed || r.created || "").replace(" ", "T")) || 0), r.code];
    var urgent = (r.priority === URGENT) ? 0 : 1;
    return [r.status === ST.REVIEW ? 1 : 0, urgent, r.overdue ? 0 : 1, r.due || "9999-12-31", r.created || "", r.code];
  }
  function cmpKey(a, b) {
    for (var i = 0; i < a.length; i++) {
      if (a[i] < b[i]) return -1;
      if (a[i] > b[i]) return 1;
    }
    return 0;
  }
  function sortRows(rows) { return rows.slice().sort(function (a, b) { return cmpKey(sortKey(a), sortKey(b)); }); }

  /* Bo loc bang: f = {q, type, team, scope (open|all|done), mine}. row = dataset cua <tr>. */
  function filterMatch(row, f) {
    if (f.scope === "open" && row.scope !== "open") return false;
    if (f.scope === "done" && row.scope !== "done") return false;
    if (f.type && row.type !== f.type) return false;
    if (f.team && row.team !== f.team) return false;
    if (f.mine && String(row.mine) !== "1") return false;
    var q = (f.q || "").trim().toLowerCase();
    if (q && (row.search || "").indexOf(q) < 0 && (row.code || "").toLowerCase().indexOf(q) < 0) return false;
    return true;
  }

  /* So ngay lam viec du kien = type_hints[loai][muc] (server tinh: ceil(so ngay x he so), toi thieu 1). */
  function slaDays(hints, type, pri) {
    var t = (hints || {})[type];
    return t && t[pri] ? t[pri] : null;
  }

  /* Gantt: vi tri thanh theo NGAY (khong phai ngay lam viec - ngay nghi van chiem cot, to xam).
   * -> {n, todayIdx, lanes:[{key,label,sub,height,bars:[{code,css,leftPct,widthPct,top,extLeftPct,lateWidthPct,clipL,clipR,...}]}]} */
  function ganttLayout(g, rowH) {
    rowH = rowH || 28;
    var n = g.days.length, start = g.days[0].date, end = g.days[n - 1].date;
    var todayIdx = -1;
    g.days.forEach(function (d, i) { if (d.today) todayIdx = i; });
    var lanes = g.lanes.map(function (ln) {
      var bars = ln.bars.map(function (b, i) {
        var s = b.start < start ? start : b.start;
        var e0 = b.late_to && b.late_to > b.due ? b.late_to : b.due;
        var e = e0 > end ? end : e0;
        if (e < s) e = s;
        var si = dayDiff(start, s), ei = dayDiff(start, e);
        var span = ei - si + 1;
        var out = { code: b.code, title: b.title, kind: b.kind, css: b.css, status: b.status,
                    leftPct: si / n * 100, widthPct: span / n * 100, top: 6 + i * rowH,
                    clipL: b.start < start, clipR: e0 > end, extLeftPct: null, lateLeftPct: null };
        // Phan da doi han: tu sau han goc toi han hien tai (gach cheo).
        if (b.original_due && b.due > b.original_due && b.original_due >= s) {
          var oi = dayDiff(start, b.original_due) + 1;
          out.extLeftPct = Math.max(0, Math.min(100, (oi - si) / span * 100));
        }
        if (b.late_to && b.late_to > b.due && b.due >= s) {
          out.lateLeftPct = Math.max(0, Math.min(100, (dayDiff(start, b.due) + 1 - si) / span * 100));
        }
        return out;
      });
      return { key: ln.key, label: ln.label, sub: ln.sub, bars: bars, height: Math.max(58, bars.length * rowH + 10) };
    });
    return { n: n, todayIdx: todayIdx, lanes: lanes, start: start, end: end };
  }

  /* @ten trong tin nhan: nguoi con giu "@Ten" trong noi dung moi tinh la duoc goi. */
  function mentionsIn(body, picked) {
    var out = [];
    (picked || []).forEach(function (p) {
      if (p && p.user && body.indexOf("@" + p.name) >= 0 && out.indexOf(p.user) < 0) out.push(p.user);
    });
    return out;
  }

  function linkify(text, mentions) {
    var h = esc(text);
    h = h.replace(/(https?:\/\/[^\s<>"']+)/g, '<a class="edh-link" href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
    (mentions || []).forEach(function (m) {
      if (!m || !m.name) return;
      var at = "@" + esc(m.name);
      h = h.split(at).join('<span class="edh-at">' + at + "</span>");
    });
    return h.replace(/\n/g, "<br>");
  }

  // ------------------------------------------------------------------ goi API ---------------
  function csrf() {
    return (window.frappe && window.frappe.csrf_token) || window.csrf_token || "";
  }
  function call(method, args, post) {
    var url = API + method, opts = { credentials: "same-origin", headers: { "Accept": "application/json" } };
    args = args || {};
    if (post) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.headers["X-Frappe-CSRF-Token"] = csrf();
      opts.body = JSON.stringify(args);
    } else {
      var qs = Object.keys(args).filter(function (k) { return args[k] != null && args[k] !== ""; })
        .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(args[k]); }).join("&");
      if (qs) url += "?" + qs;
    }
    return fetch(url, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (j) {
        var m = j && j.message;
        if (m && typeof m === "object" && "success" in m) {
          if (m.success) return m.data;
          throw new Error(m.message || "Có lỗi, thử lại sau.");
        }
        if (res.status === 403) throw new Error("Bạn không có quyền làm việc này (hoặc phiên đăng nhập đã hết hạn).");
        if (!res.ok) throw new Error(serverMsg(j) || "Máy chủ đang bận, thử lại sau ít phút.");
        return m;
      });
    }, function () { throw new Error("Mất kết nối mạng. Kiểm tra mạng rồi thử lại."); });
  }
  function serverMsg(j) {
    try {
      var s = JSON.parse(j._server_messages || "[]")[0];
      return s ? JSON.parse(s).message : "";
    } catch (e) { return ""; }
  }

  /* Khoa nut khi dang gui - chong bam hai lan. `work` la HAM tra promise: chi goi khi nut chua khoa
   * (truyen san mot promise thi viec da chay truoc khi kip kiem khoa). */
  function busy(btn, work) {
    var run = function () {
      try { return Promise.resolve(work()); } catch (e) { return Promise.reject(e); }
    };
    if (!btn) return run();
    if (btn.getAttribute("aria-busy") === "true") return Promise.reject(new Error("__busy"));
    btn.setAttribute("aria-busy", "true");
    btn.disabled = true;
    var done = function () { btn.removeAttribute("aria-busy"); btn.disabled = false; };
    return run().then(function (v) { done(); return v; }, function (e) { done(); throw e; });
  }

  function readFiles(list) {
    var files = Array.prototype.slice.call(list || []);
    if (files.length > MAX_FILES) return Promise.reject(new Error("Tối đa " + MAX_FILES + " tệp mỗi lần."));
    for (var i = 0; i < files.length; i++) {
      if (files[i].size > FILE_MAX) return Promise.reject(new Error("Tệp quá 10 MB: " + files[i].name));
    }
    return Promise.all(files.map(function (f) {
      return new Promise(function (ok, bad) {
        var r = new FileReader();
        r.onload = function () { ok({ name: f.name, data: String(r.result || "") }); };
        r.onerror = function () { bad(new Error("Không đọc được tệp " + f.name)); };
        r.readAsDataURL(f);
      });
    }));
  }

  // ------------------------------------------------------------------ trang -----------------
  function App(root, boot) {
    this.root = root;
    this.boot = boot || {};
    this.doc = root.ownerDocument;
    this.opener = null;
    this.detail = null;
    this.ganttStart = null;
  }

  App.prototype.$ = function (sel, scope) { return (scope || this.doc).querySelector(sel); };
  App.prototype.$$ = function (sel, scope) { return Array.prototype.slice.call((scope || this.doc).querySelectorAll(sel)); };

  App.prototype.toast = function (msg, err) {
    var t = this.$("[data-edh-toast]");
    if (!t) return;
    t.textContent = msg;
    t.className = "edh-toast" + (err ? " is-err" : "");
    t.hidden = false;
    clearTimeout(this._tt);
    this._tt = setTimeout(function () { t.hidden = true; }, err ? 6000 : 3500);
  };
  App.prototype.fail = function (e) {
    if (e && e.message === "__busy") return;
    this.toast((e && e.message) || "Có lỗi, thử lại sau.", true);
  };

  App.prototype.setParam = function (key, val) {
    try {
      var u = new URL(this.doc.defaultView.location.href);
      if (val) u.searchParams.set(key, val); else u.searchParams.delete(key);
      this.doc.defaultView.history.replaceState(null, "", u.pathname + (u.search || "") + (u.hash || ""));
    } catch (e) { /* trinh duyet cu: bo qua */ }
  };

  App.prototype.init = function () {
    var self = this;
    this.bindList();
    this.bindCreate();
    this.bindOps();
    this.bindAccept();
    this.bindDetailShell();
    this.doc.addEventListener("keydown", function (e) {
      if (e.key === "Escape" || e.key === "Esc") self.closeTop();
    });
    if (this.boot.page === "index" && this.boot.gantt && this.$("[data-edh-gantt]") && !this.$("[data-edh-gantt]").hidden) {
      this.renderGantt(this.boot.gantt);
    }
    if (this.boot.open) this.showDetail(this.boot.open);
    if (this.boot.missing) this.setParam("ma", "");
    return this;
  };

  // ---- bang + bo loc + Danh sach | Gantt
  App.prototype.filters = function () {
    var get = function (k) { var el = this.$('[data-edh-f="' + k + '"]'); return el ? el : null; }.bind(this);
    return { q: get("q") ? get("q").value : "", type: get("type") ? get("type").value : "",
             team: get("team") ? get("team").value : "", scope: get("scope") ? get("scope").value : "open",
             mine: get("mine") ? get("mine").checked : false };
  };
  App.prototype.applyFilters = function () {
    var f = this.filters(), shown = 0;
    this.$$("[data-edh-rows] tr").forEach(function (tr) {
      var ok = filterMatch(tr.dataset, f);
      tr.hidden = !ok;
      if (ok) shown++;
    });
    var empty = this.$("[data-edh-empty]");
    if (empty) empty.hidden = shown > 0;
    return shown;
  };
  App.prototype.bindList = function () {
    var self = this;
    this.$$("[data-edh-f]").forEach(function (el) {
      el.addEventListener(el.type === "search" ? "input" : "change", function () { self.applyFilters(); });
    });
    var body = this.$("[data-edh-rows]");
    if (body) {
      body.addEventListener("click", function (e) {
        var tr = e.target.closest("tr[data-code]");
        if (tr) self.open(tr.dataset.code, tr);
      });
      body.addEventListener("keydown", function (e) {
        var tr = e.target.closest("tr[data-code]");
        if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); self.open(tr.dataset.code, tr); }
      });
    }
    this.$$("[data-edh-view]").forEach(function (b) {
      b.addEventListener("click", function () { self.setView(b.dataset.edhView); });
    });
    this.$$("[data-edh-g-shift]").forEach(function (b) {
      b.addEventListener("click", function () {
        var n = +b.dataset.edhGShift;
        var base = self.ganttStart || (self.boot.gantt && self.boot.gantt.start) || null;
        self.loadGantt(n === 0 || !base ? null : addDays(base, n), b);
      });
    });
    var g = this.$("[data-edh-gantt-body]");
    if (g) g.addEventListener("click", function (e) {
      var bar = e.target.closest("[data-edh-bar]");
      if (bar) self.open(bar.dataset.edhBar, bar);
    });
  };
  App.prototype.setView = function (v) {
    var gantt = v === "gantt";
    this.$$("[data-edh-view]").forEach(function (b) {
      var on = b.dataset.edhView === v;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    var G = this.$("[data-edh-gantt]"), L = this.$("[data-edh-list]");
    if (G) G.hidden = !gantt;
    if (L) L.hidden = gantt;
    this.setParam("xem", gantt ? "gantt" : "");
    if (gantt && !this._ganttLoaded) this.loadGantt(null);
  };
  App.prototype.loadGantt = function (start, btn) {
    var self = this, body = this.$("[data-edh-gantt-body]");
    if (body && !this._ganttLoaded) body.innerHTML = '<p class="edh-state"><span class="edh-spin" aria-hidden="true"></span> Đang tải Gantt…</p>';
    return busy(btn, function () { return call("gantt", { start: start || "" }); }).then(function (g) { self.renderGantt(g); }, function (e) {
      if (e && e.message === "__busy") return;
      if (body && !self._ganttLoaded) body.innerHTML = '<p class="edh-state is-err">Không tải được Gantt. ' + esc(e.message) + ' <button type="button" class="edh-btn is-sm" data-edh-g-retry>Thử lại</button></p>';
      var r = self.$("[data-edh-g-retry]");
      if (r) r.addEventListener("click", function () { self.loadGantt(start); });
      if (self._ganttLoaded) self.fail(e);
    });
  };
  App.prototype.renderGantt = function (g) {
    var body = this.$("[data-edh-gantt-body]");
    if (!body || !g || !g.days || !g.days.length) return;
    this._ganttLoaded = true;
    this.ganttStart = g.start;
    var L = ganttLayout(g), cols = "repeat(" + L.n + ",minmax(30px,1fr))";
    var range = this.$("[data-edh-g-range]");
    if (range) range.textContent = fmtDate(g.start) + " – " + fmtDate(g.end) + " · mỗi hàng là một người, thanh là một yêu cầu";
    var h = '<div class="edh-g-grid" style="--edh-g-n:' + L.n + '"><div class="edh-g-corner"></div><div class="edh-g-days" style="grid-template-columns:' + cols + '">';
    g.days.forEach(function (d) {
      h += '<div class="' + (d.off ? "is-off" : "") + (d.today ? " is-today" : "") + '">' + esc(d.label) + "</div>";
    });
    h += "</div>";
    if (!L.lanes.length) {
      h += '<div class="edh-g-who"></div><div class="edh-g-lane edh-state">Chưa có ai trong team Data.</div>';
    }
    L.lanes.forEach(function (ln) {
      h += '<div class="edh-g-who" style="min-height:' + ln.height + 'px"><b>' + esc(ln.label) + "</b><span>" + esc(ln.sub || "") + "</span></div>";
      h += '<div class="edh-g-lane" style="min-height:' + ln.height + 'px"><div class="edh-g-bg" style="grid-template-columns:' + cols + '">';
      g.days.forEach(function (d) { h += '<div class="' + (d.off ? "is-off" : "") + '"></div>'; });
      h += "</div>";
      if (L.todayIdx >= 0) h += '<div class="edh-g-today" style="left:calc(' + (L.todayIdx + 0.5) + " / " + L.n + ' * 100%)"></div>';
      ln.bars.forEach(function (b) {
        var lab = b.kind === "availability" ? "<b>DA</b> " : "<b>" + esc(b.code) + "</b> ";
        var ext = b.extLeftPct != null ? '<span class="edh-bar-ext" style="left:' + b.extLeftPct.toFixed(2) + '%"></span>' : "";
        var late = b.lateLeftPct != null ? '<span class="edh-bar-late" style="left:' + b.lateLeftPct.toFixed(2) + '%"></span>' : "";
        h += '<button type="button" class="edh-bar is-' + esc(b.css) + (b.clipL ? " is-clipl" : "") + (b.clipR ? " is-clipr" : "") +
          '" data-edh-bar="' + esc(b.code) + '" style="left:' + b.leftPct.toFixed(2) + "%;width:" + b.widthPct.toFixed(2) + "%;top:" + b.top +
          'px" title="' + esc(b.code + " · " + b.title + " · " + b.status) + '">' + ext + late + lab + esc(b.title) + "</button>";
      });
      h += "</div>";
    });
    h += "</div>";
    body.innerHTML = h;
  };

  // ---- overlay chung
  App.prototype.openOv = function (ov, opener) {
    ov.hidden = false;
    ov._opener = opener || this.doc.activeElement;
    this.doc.body.classList.add("edh-noscroll");
  };
  App.prototype.closeOv = function (ov) {
    if (!ov || ov.hidden) return;
    ov.hidden = true;
    if (!this.$$(".edh-ov").some(function (o) { return !o.hidden; })) this.doc.body.classList.remove("edh-noscroll");
    var o = ov._opener;
    if (o && o.focus && this.doc.contains(o)) { try { o.focus(); } catch (e) { /* */ } }
  };
  App.prototype.closeTop = function () {
    var order = ["[data-edh-accept-ov]", "[data-edh-new-ov]", "[data-edh-detail-ov]"];
    for (var i = 0; i < order.length; i++) {
      var ov = this.$(order[i]);
      if (ov && !ov.hidden) {
        if (order[i] === "[data-edh-detail-ov]") this.closeDetail(); else this.closeOv(ov);
        return true;
      }
    }
    var m = this.$(".edh-at-menu");
    if (m) { m.remove(); return true; }
    return false;
  };

  // ---- tao yeu cau
  App.prototype.bindCreate = function () {
    var self = this, ov = this.$("[data-edh-new-ov]"), form = this.$("[data-edh-new-form]");
    if (!ov || !form) return;
    this.$$("[data-edh-new]").forEach(function (b) {
      b.addEventListener("click", function () {
        self.openOv(ov, b);
        var t = self.$("#edh-new-type");
        if (t) t.focus();
      });
    });
    ov.addEventListener("click", function (e) { if (e.target === ov) self.closeOv(ov); });
    this.$$("[data-edh-close]", form).forEach(function (b) { b.addEventListener("click", function () { self.closeOv(ov); }); });
    var type = form.elements.request_type, pri = form.elements.proposed_priority;
    var hint = function () { self.updateSlaHint(); };
    type.addEventListener("change", hint);
    pri.addEventListener("change", hint);
    var files = this.$("[data-edh-new-files]");
    if (files) files.addEventListener("change", function () {
      var list = self.$("[data-edh-new-filelist]");
      if (list) list.textContent = Array.prototype.map.call(files.files, function (f) { return f.name + " (" + fmtSize(f.size) + ")"; }).join(", ");
    });
    form.addEventListener("submit", function (e) { e.preventDefault(); self.submitCreate(); });
  };
  App.prototype.updateSlaHint = function () {
    var form = this.$("[data-edh-new-form]"), box = this.$("[data-edh-sla-hint]");
    if (!form || !box) return null;
    var type = form.elements.request_type.value, pri = form.elements.proposed_priority.value;
    var urgentBox = this.$("[data-edh-urgent-box]");
    if (urgentBox) urgentBox.hidden = pri !== URGENT;
    var n = slaDays(this.boot.type_hints, type, pri);
    box.innerHTML = n ? "Hạn dự kiến: <b>" + n + " ngày làm việc</b> sau khi team Data nhận việc" +
      (pri !== "Bình thường" ? " (mức " + esc(pri) + (pri === URGENT ? ", nếu team Data xác nhận" : "") + ")" : "") +
      ". Team Data có thể điều chỉnh, mọi thay đổi đều báo bạn."
      : "Chọn loại để xem hạn dự kiến. Hạn tính theo ngày làm việc (bỏ T7/CN, ngày lễ) sau khi team Data nhận việc.";
    return n;
  };
  App.prototype.submitCreate = function () {
    var self = this, form = this.$("[data-edh-new-form]"), err = this.$("[data-edh-new-err]");
    var btn = this.$("[data-edh-new-submit]");
    var el = form.elements;
    var data = { request_type: el.request_type.value, proposed_priority: el.proposed_priority.value,
                 urgent_reason: el.urgent_reason.value.trim(), title: el.title.value.trim(),
                 description: el.description.value.trim(), data_used: el.data_used.value.trim(),
                 reference_link: el.reference_link.value.trim() };
    var errs = [];
    if (!data.request_type) errs.push("Chọn loại yêu cầu.");
    if (!data.title) errs.push("Chưa có tiêu đề.");
    if (!data.description) errs.push("Chưa có mô tả / đầu ra mong muốn.");
    if (data.proposed_priority === URGENT && !data.urgent_reason) errs.push("Mức Khẩn cần ghi lý do để team Data xác nhận.");
    if (data.reference_link && !/^https?:\/\//i.test(data.reference_link)) errs.push("Link mẫu phải bắt đầu bằng http:// hoặc https://");
    if (errs.length) { err.textContent = errs.join(" "); err.hidden = false; return Promise.resolve(null); }
    err.hidden = true;
    var fileInput = this.$("[data-edh-new-files]");
    return busy(btn, function () { return readFiles(fileInput ? fileInput.files : []).then(function (files) {
      data.files = files;
      return call("create", { data: JSON.stringify(data) }, true);
    }); }).then(function (out) {
      self.toast("Đã gửi " + out.code + ". Team Data sẽ nhận việc và báo bạn.");
      self.closeOv(self.$("[data-edh-new-ov]"));
      self.reload("?ma=" + encodeURIComponent(out.code));
      return out;
    }, function (e) {
      if (e && e.message === "__busy") return null;
      err.textContent = e.message;
      err.hidden = false;
      return null;
    });
  };
  App.prototype.reload = function (search) {
    var w = this.doc.defaultView;
    if (w.__edhNoReload) { w.__edhReloaded = search || ""; return; }
    w.location.href = w.location.pathname + (search || w.location.search);
  };

  // ---- popup chi tiet
  App.prototype.bindDetailShell = function () {
    var self = this, ov = this.$("[data-edh-detail-ov]");
    if (!ov) return;
    ov.addEventListener("click", function (e) { if (e.target === ov) self.closeDetail(); });
  };
  App.prototype.open = function (code, opener) {
    var self = this, ov = this.$("[data-edh-detail-ov]"), box = this.$("[data-edh-detail]");
    if (!ov || !code) return Promise.resolve(null);
    this.openOv(ov, opener);
    box.innerHTML = '<div class="edh-dm-loading"><span class="edh-spin" aria-hidden="true"></span> Đang tải chi tiết…</div>';
    this.setParam("ma", code);
    this._loading = code;
    return call("get_ticket", { code: code }).then(function (d) {
      if (self._loading !== code) return null;
      self.showDetail(d);
      return d;
    }, function (e) {
      box.innerHTML = '<div class="edh-dm-loading is-err"><p>' + esc(e.message) + '</p><button type="button" class="edh-btn" data-edh-x>Đóng</button></div>';
      var x = self.$("[data-edh-x]", box);
      if (x) x.addEventListener("click", function () { self.closeDetail(); });
      return null;
    });
  };
  App.prototype.closeDetail = function () {
    var ov = this.$("[data-edh-detail-ov]");
    this._loading = null;
    this.detail = null;
    this.setParam("ma", "");
    this.closeOv(ov);
  };
  App.prototype.showDetail = function (d) {
    var ov = this.$("[data-edh-detail-ov]"), box = this.$("[data-edh-detail]");
    if (!ov || !box) return;
    if (ov.hidden) this.openOv(ov);
    this.detail = d;
    this.picked = [];
    box.innerHTML = renderDetail(d, this.boot.me);
    this.bindDetail(d);
    var x = this.$("[data-edh-x]", box);
    if (x) x.focus();
    var msgs = this.$("[data-edh-msgs]", box);
    if (msgs) msgs.scrollTop = msgs.scrollHeight;
  };

  function badge(text, css, extra) {
    return '<span class="edh-badge is-' + esc(css) + (extra || "") + '"><span class="edh-dot" aria-hidden="true"></span>' + esc(text) + "</span>";
  }

  function renderDetail(d, me) {
    var c = d.can || {};
    var h = '<div class="edh-dm-h"><div class="edh-dm-ht"><div class="edh-hint">' + esc(d.code) + " · " + esc(d.type_short) +
      (d.team ? " · " + esc(d.team) : "") + "</div><h2 class=\"edh-dm-title\">" + esc(d.title) + '</h2><div class="edh-badges">' +
      badge("Ưu tiên: " + d.priority + (d.priority_confirmed ? "" : " (đề xuất)"), d.priority_css) +
      (d.overdue ? " " + badge(d.sla_label, "red") : "") + " " + badge(d.status_label, d.status_css) +
      (d.acceptance ? " " + badge(d.acceptance, d.acceptance === "Chưa đạt" ? "red" : "green") : "") +
      '</div></div><div class="edh-dm-ha"><button type="button" class="edh-btn is-sm" data-edh-follow aria-pressed="' + (d.following ? "true" : "false") + '">' +
      (d.following ? "Đang theo dõi" : "Theo dõi") + '</button><button type="button" class="edh-btn is-sm edh-x" data-edh-x aria-label="Đóng">✕</button></div></div>';
    h += '<div class="edh-dm-b"><section class="edh-card edh-dm-info" aria-label="Thông tin yêu cầu">';
    h += '<div class="edh-summary">' +
      sumItem("Người gửi", esc(d.requester_name) + (d.team ? " (" + esc(d.team) + ")" : "")) +
      sumItem("Người xử lý", d.assignee_name ? esc(d.assignee_name) : '<span class="edh-hint">Chưa phân công</span>') +
      sumItem("Hạn", dueHtml(d)) +
      sumItem("Task /pm", d.pm_url ? '<a class="edh-link" href="' + esc(d.pm_url) + '" target="_blank" rel="noopener">' + esc(d.pm_task) + " ↗</a>" : '<span class="edh-hint">' + (d.status === ST.WAITING ? "tạo khi team Data nhận" : "—") + "</span>") +
      sumItem("Gửi lúc", esc(d.created_fmt)) +
      sumItem(d.start ? "Bắt đầu" : "Dự kiến bắt đầu", d.start ? esc(d.start_fmt) : (d.queue ? esc(d.queue.expected_start) : "—")) +
      (d.data_used ? sumItem("Dữ liệu dùng", esc(d.data_used), true) : "") + "</div>";
    if (d.queue) {
      h += '<p class="edh-banner is-info">Đang ở vị trí <b>' + d.queue.position + "</b> trong hàng đợi, dự kiến bắt đầu <b>" + esc(d.queue.expected_start) +
        "</b>, xong khoảng " + esc(d.queue.expected_due) + " (" + d.queue.sla_days + " ngày làm việc). Hạn nhận việc: " + esc(d.intake_due_fmt) + ".</p>";
    }
    if (d.status === ST.PAUSED) h += '<p class="edh-banner is-warn">Tạm dừng – chờ người gửi từ ' + esc(d.paused_since_fmt) + ". Đồng hồ hạn đang dừng; tiếp tục thì hạn được cộng thêm số ngày làm việc đã dừng.</p>";
    if (d.status === ST.CANCEL && d.cancel_reason) h += '<p class="edh-banner is-err">Đã huỷ: ' + esc(d.cancel_reason) + "</p>";
    if (d.urgent_reason) h += '<p class="edh-banner is-warn"><b>Lý do Khẩn:</b> ' + esc(d.urgent_reason) + "</p>";
    h += actionsHtml(d);
    if (c.operate) h += teamEditHtml(d);
    h += '<div class="edh-sect">Mô tả</div><div class="edh-desc">' + linkify(d.description) + "</div>";
    if (d.reference_link) h += '<div class="edh-sect">Link mẫu</div><a class="edh-link" href="' + esc(d.reference_link) + '" target="_blank" rel="noopener noreferrer">' + esc(d.reference_link) + "</a>";
    if (d.output_link) h += '<div class="edh-sect">Kết quả</div><a class="edh-link" href="' + esc(d.output_link) + '" target="_blank" rel="noopener noreferrer">' + esc(d.output_link) + "</a>";
    if (d.attachments && d.attachments.length) {
      h += '<div class="edh-sect">Tệp</div><div class="edh-filelinks">' + d.attachments.map(fileLink).join(" · ") + "</div>";
    }
    h += '<div class="edh-sect">Tiến độ</div><div class="edh-tl">' + (d.timeline || []).map(function (t) {
      return '<div class="edh-tl-item' + (t.warn ? " is-warn" : "") + '"><span class="edh-tl-dot" aria-hidden="true"></span><div><b>' + esc(t.when) + "</b> " + esc(t.text) +
        (t.note ? ' · <i>' + esc(t.note) + "</i>" : "") + "</div></div>";
    }).join("") + "</div></section>";
    h += '<section class="edh-card edh-dm-chat" aria-label="Trao đổi"><div class="edh-sect edh-sect-top">Trao đổi <span class="edh-hint">· ' +
      (d.followers || []).length + " người theo dõi</span></div><div class=\"edh-msgs\" data-edh-msgs>" +
      ((d.messages || []).length ? d.messages.map(function (m) {
        return '<div class="edh-msg' + (m.me ? " is-me" : "") + '"><b>' + esc(m.author_name) + '</b><span class="edh-hint"> ' + esc(m.when) + "</span>" +
          (m.body ? "<p>" + linkify(m.body, m.mentions) + "</p>" : "") +
          (m.files && m.files.length ? '<div class="edh-filelinks">' + m.files.map(fileLink).join(" · ") + "</div>" : "") + "</div>";
      }).join("") : '<p class="edh-state edh-msgs-empty">Chưa có trao đổi. Hỏi team Data ngay tại đây.</p>') + "</div>";
    if (c.message) {
      h += '<form class="edh-compose" data-edh-compose novalidate><label class="edh-sr" for="edh-msg">Tin nhắn</label>' +
        '<textarea id="edh-msg" name="body" rows="2" maxlength="3000" placeholder="Nhắn… (@ để gọi tên)"></textarea>' +
        '<div class="edh-cmp-f"><label class="edh-btn is-sm edh-file-btn">📎 Đính kèm<input type="file" data-edh-msg-files multiple hidden></label>' +
        '<span class="edh-hint edh-file-list" data-edh-msg-filelist></span><button type="submit" class="edh-btn is-primary is-sm" data-edh-send>Gửi</button></div></form>';
    } else {
      h += '<p class="edh-hint">Bấm “Theo dõi” để tham gia trao đổi và nhận thông báo.</p>';
    }
    h += "</section></div>";
    return h;
  }
  function sumItem(label, html, full) {
    return '<div' + (full ? ' class="edh-full"' : "") + "><span>" + esc(label) + "</span>" + html + "</div>";
  }
  function dueHtml(d) {
    if (d.status === ST.WAITING) return "hạn nhận " + esc(d.intake_due_fmt || "—");
    if (!d.due_fmt) return "—";
    var h = esc(d.due_fmt);
    if (d.original_due_fmt) h += " <s>" + esc(d.original_due_fmt) + "</s>";
    if (d.due_change_count) h += ' <span class="edh-hint">· đã dời ' + d.due_change_count + " lần</span>";
    return h + '<div class="edh-sla is-' + esc(d.sla_css || "ok") + '" aria-hidden="true"><i style="width:' + (+d.sla_pct || 0) + '%"></i></div>';
  }
  function fileLink(f) {
    return '<a class="edh-link" href="' + esc(f.url) + '">' + esc(f.name) + "</a> <span class=\"edh-hint\">" + fmtSize(f.size || 0) + "</span>";
  }
  function actionsHtml(d) {
    var c = d.can || {}, h = "";
    if (c.accept) h += '<button type="button" class="edh-btn is-primary" data-edh-accept="' + esc(d.code) + '">Nhận việc</button>';
    if (c.respond) {
      h += '<div class="edh-respond" data-edh-respond><p><b>Team Data đã hoàn tất.</b> Kết quả đã đúng yêu cầu chưa?</p>' +
        '<div class="edh-actions"><button type="button" class="edh-btn is-primary" data-edh-ok>Đạt</button>' +
        '<button type="button" class="edh-btn is-warn" data-edh-nok>Chưa đạt</button></div>' +
        '<div class="edh-fld" data-edh-nok-box hidden><label for="edh-nok-r">Chưa đạt ở điểm nào? <span class="edh-req">*</span></label>' +
        '<textarea id="edh-nok-r" rows="2" maxlength="1000"></textarea><button type="button" class="edh-btn is-sm is-warn" data-edh-nok-send>Gửi lại team Data</button></div></div>';
    }
    if (c.cancel) {
      h += '<details class="edh-cancel"><summary>Huỷ yêu cầu</summary><div class="edh-fld">' +
        '<label for="edh-cancel-r">Lý do' + (c.cancel_needs_reason ? ' <span class="edh-req">*</span>' : "") + '</label>' +
        '<input id="edh-cancel-r" maxlength="1000"><button type="button" class="edh-btn is-sm is-danger" data-edh-cancel>Xác nhận huỷ</button></div></details>';
    }
    return h ? '<div class="edh-actions edh-dm-actions">' + h + "</div>" : "";
  }
  function teamEditHtml(d) {
    var opt = function (items, cur, val, lab) {
      return items.map(function (x) {
        var v = val ? x[val] : x, l = lab ? x[lab] : x;
        return '<option value="' + esc(v) + '"' + (v === cur ? " selected" : "") + ">" + esc(l) + "</option>";
      }).join("");
    };
    var team = d.team_members || [];
    if (d.assignee && !team.some(function (m) { return m.user === d.assignee; })) team = team.concat([{ user: d.assignee, name: d.assignee_name || d.assignee }]);
    return '<form class="edh-edit" data-edh-edit novalidate><div class="edh-sect">Cập nhật (team Data)</div><div class="edh-grid3">' +
      '<div class="edh-fld"><label for="edh-e-st">Trạng thái</label><select id="edh-e-st" name="status">' + opt(d.team_statuses || [], d.status, "value", "label") + "</select></div>" +
      '<div class="edh-fld"><label for="edh-e-pri">Ưu tiên</label><select id="edh-e-pri" name="priority">' + opt(d.priorities || [], d.priority) + "</select></div>" +
      '<div class="edh-fld"><label for="edh-e-due">Hạn</label><input id="edh-e-due" name="due_date" type="date" value="' + esc(d.due_date) + '"></div>' +
      '<div class="edh-fld"><label for="edh-e-who">Người xử lý</label><select id="edh-e-who" name="assignee">' + opt(team, d.assignee, "user", "name") + "</select></div>" +
      '<div class="edh-fld"><label for="edh-e-start">Bắt đầu</label><input id="edh-e-start" name="start_date" type="date" value="' + esc(d.start) + '"></div>' +
      '<div class="edh-fld"><label for="edh-e-out">Link kết quả</label><input id="edh-e-out" name="output_link" type="url" maxlength="500" value="' + esc(d.output_link) + '" placeholder="https://…"></div>' +
      '</div><div class="edh-fld" data-edh-e-reason-box hidden><label for="edh-e-reason">Lý do đổi hạn <span class="edh-req">*</span></label><input id="edh-e-reason" name="reason" maxlength="1000" placeholder="Người gửi sẽ thấy lý do này"></div>' +
      '<div class="edh-fld"><label for="edh-e-note">Ghi chú cho người gửi</label><textarea id="edh-e-note" name="note" rows="2" maxlength="3000" placeholder="VD: đã xong 70%, còn trang Chi phí"></textarea></div>' +
      '<p class="edh-err" data-edh-e-err role="alert" hidden></p><div class="edh-actions"><button type="submit" class="edh-btn is-primary is-sm" data-edh-e-save>Lưu &amp; báo người gửi</button>' +
      '<span class="edh-hint">' + (d.pm_task ? "Task /pm đổi theo." : "Chưa có task /pm - lưu xong sẽ tạo bù.") + "</span></div></form>";
  }

  App.prototype.bindDetail = function (d) {
    var self = this, box = this.$("[data-edh-detail]");
    var on = function (sel, ev, fn) { var el = self.$(sel, box); if (el) el.addEventListener(ev, fn); return el; };
    on("[data-edh-x]", "click", function () { self.closeDetail(); });
    var fol = on("[data-edh-follow]", "click", function () {
      busy(fol, function () { return call("follow", { code: d.code, on: d.following ? 0 : 1 }, true); }).then(function () { return self.refresh(d.code); }, function (e) { self.fail(e); });
    });
    on("[data-edh-accept]", "click", function (e) { self.openAccept(d.code, d.accept_defaults, d.team_members, e.currentTarget); });
    var ok = on("[data-edh-ok]", "click", function () {
      busy(ok, function () { return call("respond", { code: d.code, verdict: "Đạt" }, true); }).then(function () { self.toast("Đã nghiệm thu: Đạt. Cảm ơn bạn!"); self.after(d.code); }, function (e) { self.fail(e); });
    });
    on("[data-edh-nok]", "click", function () { var b = self.$("[data-edh-nok-box]", box); b.hidden = false; self.$("#edh-nok-r", box).focus(); });
    var nok = on("[data-edh-nok-send]", "click", function () {
      var r = self.$("#edh-nok-r", box).value.trim();
      if (!r) { self.toast("Ghi rõ chưa đạt ở điểm nào để team Data sửa.", true); return; }
      busy(nok, function () { return call("respond", { code: d.code, verdict: "Chưa đạt", reason: r }, true); }).then(function () { self.toast("Đã gửi lại team Data."); self.after(d.code); }, function (e) { self.fail(e); });
    });
    var cancel = on("[data-edh-cancel]", "click", function () {
      var r = self.$("#edh-cancel-r", box).value.trim();
      if ((d.can || {}).cancel_needs_reason && !r) { self.toast("Huỷ yêu cầu cần ghi lý do.", true); return; }
      busy(cancel, function () { return call("cancel", { code: d.code, reason: r }, true); }).then(function () { self.toast("Đã huỷ " + d.code + "."); self.after(d.code); }, function (e) { self.fail(e); });
    });
    var edit = this.$("[data-edh-edit]", box);
    if (edit) {
      var due0 = d.due_date;
      edit.elements.due_date.addEventListener("change", function () {
        self.$("[data-edh-e-reason-box]", box).hidden = edit.elements.due_date.value === due0;
      });
      edit.addEventListener("submit", function (e) {
        e.preventDefault();
        var el = edit.elements, err = self.$("[data-edh-e-err]", box);
        var data = { status: el.status.value, priority: el.priority.value, due_date: el.due_date.value, assignee: el.assignee.value,
                     start_date: el.start_date.value, output_link: el.output_link.value.trim(), reason: el.reason.value.trim(), note: el.note.value.trim() };
        if (data.due_date !== due0 && !data.reason) { err.textContent = "Đổi hạn cần ghi lý do (người gửi sẽ thấy)."; err.hidden = false; return; }
        err.hidden = true;
        busy(self.$("[data-edh-e-save]", box), function () { return call("update", { code: d.code, data: JSON.stringify(data) }, true); }).then(function (out) {
          self.toast((out.warnings && out.warnings.length) ? out.warnings[0] : "Đã lưu và báo người gửi.", !!(out.warnings && out.warnings.length));
          self.after(d.code);
        }, function (e2) { if (e2.message !== "__busy") { err.textContent = e2.message; err.hidden = false; } });
      });
    }
    var form = this.$("[data-edh-compose]", box);
    if (form) this.bindCompose(form, d);
  };

  App.prototype.bindCompose = function (form, d) {
    var self = this, ta = form.elements.body, files = this.$("[data-edh-msg-files]", form);
    var people = [];
    var seen = {};
    [{ user: d.requester, name: d.requester_name }, { user: d.assignee, name: d.assignee_name }].concat(d.followers || [], d.team_members || [])
      .forEach(function (p) { if (p && p.user && p.name && !seen[p.user]) { seen[p.user] = 1; people.push(p); } });
    if (files) files.addEventListener("change", function () {
      var l = self.$("[data-edh-msg-filelist]", form);
      if (l) l.textContent = Array.prototype.map.call(files.files, function (f) { return f.name; }).join(", ");
    });
    ta.addEventListener("input", function () { self.mentionMenu(ta, people); });
    ta.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true })); }
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var body = ta.value.trim();
      if (!body && !(files && files.files.length)) { self.toast("Chưa có nội dung tin nhắn.", true); return; }
      var btn = self.$("[data-edh-send]", form);
      busy(btn, function () { return readFiles(files ? files.files : []).then(function (fs) {
        return call("send_message", { code: d.code, body: body, mentions: JSON.stringify(mentionsIn(body, self.picked)), files: JSON.stringify(fs) }, true);
      }); }).then(function () { self.picked = []; return self.refresh(d.code); }, function (e2) { self.fail(e2); });
    });
  };

  /* Menu @ten: tu nguoi lien quan (nguoi gui, nguoi xu ly, theo doi, team Data) + tim nhan vien (>= 2 ky tu). */
  App.prototype.mentionMenu = function (ta, people) {
    var self = this, old = this.$(".edh-at-menu");
    if (old) old.remove();
    var pos = ta.selectionStart || ta.value.length, before = ta.value.slice(0, pos);
    var m = /(^|\s)@([^\s@]{0,30})$/.exec(before);
    if (!m) return;
    var q = m[2].toLowerCase();
    var local = people.filter(function (p) { return !q || p.name.toLowerCase().indexOf(q) >= 0 || p.user.indexOf(q) >= 0; }).slice(0, 6);
    var show = function (list) {
      var cur = self.$(".edh-at-menu");
      if (cur) cur.remove();
      if (!list.length) return;
      var ul = self.doc.createElement("ul");
      ul.className = "edh-at-menu";
      ul.setAttribute("role", "listbox");
      list.forEach(function (p) {
        var li = self.doc.createElement("li");
        li.setAttribute("role", "option");
        li.tabIndex = 0;
        li.textContent = p.name;
        li.dataset.user = p.user;
        var pick = function (e) {
          e.preventDefault();
          var start = pos - m[2].length - 1;
          ta.value = ta.value.slice(0, start) + "@" + p.name + " " + ta.value.slice(pos);
          self.picked = (self.picked || []).concat([p]);
          ul.remove();
          ta.focus();
        };
        li.addEventListener("mousedown", pick);
        li.addEventListener("keydown", function (e) { if (e.key === "Enter") pick(e); });
        ul.appendChild(li);
      });
      ta.parentNode.insertBefore(ul, ta.nextSibling);
    };
    show(local);
    if (q.length >= 2 && local.length < 6) {
      call("people", { q: q }).then(function (rows) {
        var have = {};
        local.forEach(function (p) { have[p.user] = 1; });
        show(local.concat((rows || []).filter(function (r) { return !have[r.user]; }).map(function (r) { return { user: r.user, name: r.name }; })).slice(0, 8));
      }, function () { /* goi y la phu: loi thi giu danh sach tai cho */ });
    }
  };

  App.prototype.refresh = function (code) {
    var self = this;
    return call("get_ticket", { code: code }).then(function (d) { if (self.detail && self.detail.code === code) self.showDetail(d); return d; },
      function (e) { self.fail(e); });
  };
  /* Sau mot thay doi trang thai: tai lai trang giu popup (KPI, bang, kanban ve lai tu server). */
  App.prototype.after = function (code) {
    var w = this.doc.defaultView, u;
    try { u = new URL(w.location.href); u.searchParams.set("ma", code); } catch (e) { u = null; }
    this.reload(u ? u.search : "?ma=" + encodeURIComponent(code));
  };

  // ---- Nhan viec (team Data)
  App.prototype.bindAccept = function () {
    var self = this, ov = this.$("[data-edh-accept-ov]"), form = this.$("[data-edh-accept-form]");
    if (!ov || !form) return;
    ov.addEventListener("click", function (e) { if (e.target === ov) self.closeOv(ov); });
    this.$$("[data-edh-close]", form).forEach(function (b) { b.addEventListener("click", function () { self.closeOv(ov); }); });
    var el = form.elements;
    var re = function () { self.previewDue(); };
    el.start_date.addEventListener("change", re);
    el.priority.addEventListener("change", re);
    el.due_date.addEventListener("change", function () { self.syncAcceptReason(); });
    form.addEventListener("submit", function (e) { e.preventDefault(); self.submitAccept(); });
  };
  App.prototype.openAccept = function (code, defaults, team, opener) {
    var ov = this.$("[data-edh-accept-ov]"), form = this.$("[data-edh-accept-form]");
    if (!ov || !form) return;
    defaults = defaults || (this.boot.accept || {})[code] || {};
    team = team || this.boot.team || [];
    var el = form.elements, me = this.boot.me;
    this._acc = { code: code, rule_due: defaults.due };
    this.$("[data-edh-acc-code]").textContent = "· " + code;
    el.assignee.innerHTML = '<option value="">— Chọn —</option>' + team.map(function (m) {
      return '<option value="' + esc(m.user) + '"' + (m.user === me ? " selected" : "") + ">" + esc(m.name) + "</option>";
    }).join("");
    el.priority.value = defaults.priority || "Bình thường";
    el.start_date.value = defaults.start || "";
    el.due_date.value = defaults.due || "";
    el.reason.value = "";
    var urgent = this.$("[data-edh-acc-urgent]");
    if (defaults.proposed_priority === URGENT) {
      urgent.hidden = false;
      urgent.innerHTML = "<b>Người gửi đề xuất Khẩn:</b> " + esc(defaults.urgent_reason || "") + " — giữ Khẩn để xác nhận, hoặc chọn mức thấp hơn (ghi lịch sử).";
    } else urgent.hidden = true;
    this.$("[data-edh-acc-rule]").textContent = defaults.sla_days ? "(quy tắc: " + defaults.sla_days + " ngày làm việc → " + fmtDate(defaults.due) + ")" : "";
    this.$("[data-edh-acc-err]").hidden = true;
    this.syncAcceptReason();
    this.openOv(ov, opener);
    el.assignee.focus();
  };
  App.prototype.syncAcceptReason = function () {
    var form = this.$("[data-edh-accept-form]");
    if (!form || !this._acc) return;
    this.$("[data-edh-acc-reason-box]").hidden = !form.elements.due_date.value || form.elements.due_date.value === this._acc.rule_due;
  };
  App.prototype.previewDue = function () {
    var self = this, form = this.$("[data-edh-accept-form]"), el = form.elements;
    if (!this._acc) return Promise.resolve(null);
    var keepCustom = el.due_date.value && el.due_date.value !== this._acc.rule_due;
    return call("preview_due", { code: this._acc.code, start_date: el.start_date.value, priority: el.priority.value }).then(function (p) {
      self._acc.rule_due = p.due;
      if (!keepCustom) el.due_date.value = p.due;
      self.$("[data-edh-acc-rule]").textContent = "(quy tắc: " + p.sla_days + " ngày làm việc → " + fmtDate(p.due) + ")";
      self.syncAcceptReason();
      return p;
    }, function (e) { self.fail(e); return null; });
  };
  App.prototype.submitAccept = function () {
    var self = this, form = this.$("[data-edh-accept-form]"), el = form.elements, err = this.$("[data-edh-acc-err]");
    var data = { code: this._acc.code, assignee: el.assignee.value, priority: el.priority.value, start_date: el.start_date.value,
                 due_date: el.due_date.value, reason: el.reason.value.trim() };
    var errs = [];
    if (!data.assignee) errs.push("Chọn người xử lý.");
    if (!data.start_date) errs.push("Chọn ngày bắt đầu.");
    if (!data.due_date) errs.push("Chọn hạn.");
    if (data.due_date && data.start_date && data.due_date < data.start_date) errs.push("Hạn không được trước ngày bắt đầu.");
    if (data.due_date && data.due_date !== this._acc.rule_due && !data.reason) errs.push("Đổi hạn so với quy tắc cần ghi lý do.");
    if (errs.length) { err.textContent = errs.join(" "); err.hidden = false; return Promise.resolve(null); }
    err.hidden = true;
    return busy(this.$("[data-edh-acc-submit]"), function () { return call("accept", data, true); }).then(function (out) {
      self.toast(out.warning || ("Đã nhận " + data.code + (out.pm_task ? " · task /pm " + out.pm_task : "") + "."), !!out.warning);
      self.closeOv(self.$("[data-edh-accept-ov]"));
      self.after(data.code);
      return out;
    }, function (e) {
      if (e.message === "__busy") return null;
      err.textContent = e.message;
      err.hidden = false;
      return null;
    });
  };

  // ---- Dieu phoi
  App.prototype.bindOps = function () {
    var self = this;
    this.$$("[data-edh-open]").forEach(function (b) { b.addEventListener("click", function () { self.open(b.dataset.edhOpen, b); }); });
    this.$$(".edh-kanban [data-edh-accept]").forEach(function (b) {
      b.addEventListener("click", function () { self.openAccept(b.dataset.edhAccept, null, null, b); });
    });
    this.$$("[data-edh-resume]").forEach(function (b) {
      b.addEventListener("click", function () {
        busy(b, function () { return call("resume", { code: b.dataset.edhResume }, true); }).then(function () {
          self.toast("Đã tiếp tục " + b.dataset.edhResume + ", hạn đã cộng phần tạm dừng.");
          self.reload();
        }, function (e) { self.fail(e); });
      });
    });
  };

  function boot(doc) {
    doc = doc || document;
    var root = doc.getElementById("edh");
    if (!root) return null;
    var data = {};
    try { data = JSON.parse((doc.getElementById("edh-boot") || {}).textContent || "{}"); } catch (e) { data = {}; }
    return new App(root, data).init();
  }

  window.ECDataHub = {
    __installed: true, App: App, boot: boot, sortKey: sortKey, sortRows: sortRows, filterMatch: filterMatch,
    slaDays: slaDays, ganttLayout: ganttLayout, mentionsIn: mentionsIn, linkify: linkify, renderDetail: renderDetail,
    esc: esc, fmtDate: fmtDate, addDays: addDays, call: call, busy: busy,
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { window.ECDataHub.app = boot(document); });
  else window.ECDataHub.app = boot(document);
})();
