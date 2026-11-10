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
    h += extraHtml(d);
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
  /* Dot 2: ke hoach bo sung data (DA-) + muc Thu vien bao cao cua yeu cau Power BI. */
  function extraHtml(d) {
    var h = "";
    if (d.plan) {
      h += '<p class="edh-banner is-info">Bổ sung <b>' + esc(d.plan.data_type) + "</b> (" + esc(d.plan.team) + ") · sàn " + esc(d.plan.platforms) +
        " → " + esc(d.plan.channels) + " · cách lấy " + esc(d.plan.method || "—") + ". " +
        (d.plan.needs_acceptance ? "Từ đề xuất: người đề xuất nghiệm thu khi team Data hoàn tất." : "Hoàn tất thì các ô đã chọn tự chuyển “Có”.") +
        ' <a class="edh-link" href="/du-lieu/san-co">Xem ma trận</a></p>';
    }
    if (d.library) {
      h += '<p class="edh-banner is-info">Trong Thư viện báo cáo: <a class="edh-link" href="' + esc(d.library.link) + '" target="_blank" rel="noopener noreferrer">' + esc(d.library.title) + " ↗</a></p>";
    } else if ("library" in d && d.status === ST.DONE && d.team_members) {
      h += '<p class="edh-hint"><a class="edh-link" href="/du-lieu/san-co?xem=thu-vien&amp;tu=' + encodeURIComponent(d.code) + '">+ Thêm vào Thư viện báo cáo</a></p>';
    }
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
    esc: esc, fmtDate: fmtDate, addDays: addDays, call: call, busy: busy, readFiles: readFiles, fmtSize: fmtSize,
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { window.ECDataHub.app = boot(document); });
  else window.ECDataHub.app = boot(document);
})();


/* ===================================================================================================
 * DOT 2 (PO Hoan chot 09/11/2026) - Data availability (/du-lieu/san-co) + goi y "da co dashboard tuong tu"
 * tren form tao yeu cau (/du-lieu). Dung lai App cua dot 1 (popup chi tiet, toast, overlay, khoa nut).
 * Server (data_hub/avail_service.py) ve san ma tran / KPI / Can bo sung / de xuat / thu vien; o day chi
 * loc tai cho, mo hop, gui POST toi ecentric_workspace.data_hub.api.* roi tai lai trang.
 * Ham thuan gan vao window.ECDataHub.avail de test jsdom (data_hub/tests/js/test_ec_data_hub_avail.mjs).
 * =================================================================================================== */
(function () {
  "use strict";
  if (typeof window === "undefined" || !window.ECDataHub || window.ECDataHub.avail) return;
  var H = window.ECDataHub, esc = H.esc, call = H.call, busy = H.busy;
  var MAIN = ["Shopee", "TikTok", "Lazada"];

  /* Loc ma tran: f = {q, team, state (full|gap|plan|stale|front)}; row = dataset cua <tr data-edh-mrow>. */
  function matrixMatch(row, f) {
    if (f.team && row.team !== f.team) return false;
    if (f.state && String(row[f.state]) !== "1") return false;
    var q = (f.q || "").trim().toLowerCase();
    return !q || (row.search || "").indexOf(q) >= 0;
  }
  function libMatch(row, f) {
    if (f.team && row.team !== f.team) return false;
    var q = (f.q || "").trim().toLowerCase();
    return !q || (row.search || "").indexOf(q) >= 0;
  }
  /* Form -> du lieu gui (checkbox nhieu gia tri). */
  function formData(form) {
    var out = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.disabled || el.type === "file") return;
      if (el.type === "checkbox") {
        if (el.name === "platforms" || el.name === "channels") { (out[el.name] = out[el.name] || []); if (el.checked) out[el.name].push(el.value); }
        else out[el.name] = el.checked ? 1 : 0;
      } else out[el.name] = typeof el.value === "string" ? el.value.trim() : el.value;
    });
    return out;
  }
  function checkPlatforms(data) {
    return (data.platforms || []).length > 0 || !!(data.other_platform || "").trim();
  }
  /* Goi y tuong tu (form tao yeu cau) -> HTML. */
  function suggestHtml(s) {
    var lib = (s && s.library) || [], req = (s && s.requests) || [];
    if (!lib.length && !req.length) return "";
    var h = "";
    lib.forEach(function (x) {
      h += '<li>Đã có dashboard tương tự: <b>' + esc(x.title) + "</b>" + (x.team ? ' <span class="edh-hint">(' + esc(x.team) + ")</span>" : "") +
        ' — <a class="edh-link" href="' + esc(x.link) + '" target="_blank" rel="noopener noreferrer">mở xem ↗</a></li>';
    });
    req.forEach(function (x) {
      h += '<li>Đang có yêu cầu tương tự: <b>' + esc(x.code) + "</b> " + esc(x.title) + ' <span class="edh-hint">(' + esc(x.status) +
        ')</span> — <a class="edh-link" href="' + esc(x.url) + '" target="_blank" rel="noopener">mở xem</a></li>';
    });
    return '<p><b>Có thể bạn không cần yêu cầu mới:</b></p><ul>' + h + "</ul>";
  }
  function debounce(fn, ms) {
    var t = null;
    return function () { var a = arguments, self = this; clearTimeout(t); t = setTimeout(function () { fn.apply(self, a); }, ms); };
  }
  function nowLocal(d) {
    d = d || new Date();
    var p = function (n) { return ("0" + n).slice(-2); };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  function Avail(app) {
    this.app = app;
    this.boot = app.boot;
    this.doc = app.doc;
    this.$ = app.$.bind(app);
    this.$$ = app.$$.bind(app);
  }
  Avail.prototype.init = function () {
    this.bindSub();
    this.bindFilters();
    this.bindPropose();
    this.bindProposalDetail();
    if (this.boot.is_team) {
      this.bindReview();
      this.bindPlan();
      this.bindRow();
      this.bindLibrary();
    }
    if (this.boot.prefill) this.openLibrary(null, this.boot.prefill);
    var self = this;
    this.doc.addEventListener("keydown", function (e) {
      if (e.key !== "Escape" && e.key !== "Esc") return;
      ["[data-edh-why-ov]", "[data-edh-plan-ov]", "[data-edh-rowf-ov]", "[data-edh-lib-ov]", "[data-edh-prop-ov]", "[data-edh-pdet-ov]"].some(function (sel) {
        var ov = self.$(sel);
        if (ov && !ov.hidden) { self.app.closeOv(ov); return true; }
        return false;
      });
    });
    return this;
  };
  Avail.prototype.done = function (msg, warn) {
    this.app.toast(msg, !!warn);
    this.app.reload();
  };
  Avail.prototype.formOv = function (ovSel, formSel, errSel, submitSel, method, build, okMsg) {
    var self = this, ov = this.$(ovSel), form = this.$(formSel);
    if (!ov || !form) return null;
    ov.addEventListener("click", function (e) { if (e.target === ov) self.app.closeOv(ov); });
    this.$$("[data-edh-close]", form).forEach(function (b) { b.addEventListener("click", function () { self.app.closeOv(ov); }); });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var err = self.$(errSel), args = build(form);
      if (typeof args === "string") { err.textContent = args; err.hidden = false; return; }
      err.hidden = true;
      busy(self.$(submitSel), function () {
        // args.__prep: buoc chuan bi bat dong bo (doc tep -> base64) TRONG khoa nut, roi moi goi API
        return Promise.resolve(typeof args.__prep === "function" ? args.__prep() : args).then(function (a) { return call(method, a, true); });
      }).then(function (out) {
        self.app.closeOv(ov);
        var m = okMsg(out || {});
        self.done(m[0], m[1]);
      }, function (e2) {
        if (e2 && e2.message === "__busy") return;
        err.textContent = e2.message;
        err.hidden = false;
      });
    });
    return { ov: ov, form: form };
  };

  // ---- Ma tran | Thu vien
  Avail.prototype.bindSub = function () {
    var self = this;
    this.$$("[data-edh-sub]").forEach(function (b) {
      b.addEventListener("click", function () { self.setSub(b.dataset.edhSub); });
    });
  };
  Avail.prototype.setSub = function (v) {
    this.$$("[data-edh-sub]").forEach(function (b) {
      var on = b.dataset.edhSub === v;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    this.$$("[data-edh-av]").forEach(function (s) { s.hidden = s.dataset.edhAv !== v; });
    this.app.setParam("xem", v === "library" ? "thu-vien" : "");
  };

  // ---- loc
  Avail.prototype.bindFilters = function () {
    var self = this;
    this.$$("[data-edh-af]").forEach(function (el) {
      el.addEventListener(el.type === "search" ? "input" : "change", function () { self.applyMatrix(); });
    });
    this.$$("[data-edh-lf]").forEach(function (el) {
      el.addEventListener(el.type === "search" ? "input" : "change", function () { self.applyLibrary(); });
    });
  };
  Avail.prototype.val = function (attr, k) { var el = this.$("[" + attr + '="' + k + '"]'); return el ? el.value : ""; };
  Avail.prototype.applyMatrix = function () {
    var f = { q: this.val("data-edh-af", "q"), team: this.val("data-edh-af", "team"), state: this.val("data-edh-af", "state") };
    var shown = 0, perTeam = {};
    this.$$("[data-edh-mrow]").forEach(function (tr) {
      var ok = matrixMatch(tr.dataset, f);
      tr.hidden = !ok;
      if (ok) { shown++; perTeam[tr.dataset.team] = 1; }
    });
    this.$$("[data-edh-mteam]").forEach(function (tr) { tr.hidden = !perTeam[tr.dataset.edhMteam]; });
    var empty = this.$("[data-edh-mempty]");
    if (empty) empty.hidden = shown > 0;
    return shown;
  };
  Avail.prototype.applyLibrary = function () {
    var f = { q: this.val("data-edh-lf", "q"), team: this.val("data-edh-lf", "team") }, shown = 0;
    this.$$("[data-edh-lrow]").forEach(function (tr) { var ok = libMatch(tr.dataset, f); tr.hidden = !ok; if (ok) shown++; });
    var empty = this.$("[data-edh-lempty]");
    if (empty) empty.hidden = shown > 0;
    return shown;
  };

  // ---- de xuat (moi nhan vien) - 10/11/2026: phong ban ERP, loai du lieu chon / them moi, link nguon, anh huong
  // dan, tan suat, khoang du lieu, kenh nhan, can truoc (ngay gio); Cao / Khan bat buoc ly do.
  var URL_RE = /^https?:\/\/[^\s<>"']+$/i;
  function splitLinks(raw) {
    return String(raw || "").split(/[\s,]+/).filter(function (x) { return x; });
  }
  /* Kiem form de xuat (giong server - server van kiem lai). d = formData; needReason = ["Cao","Khẩn"]. */
  function proposalErrors(d, needReason, now) {
    var errs = [];
    if (!d.department) errs.push("Chọn phòng ban cần dữ liệu.");
    if (!d.data_type) errs.push("Chọn hoặc ghi loại dữ liệu cần crawl.");
    if (!checkPlatforms(d)) errs.push("Chọn ít nhất một sàn.");
    var links = splitLinks(d.source_links);
    if (links.some(function (x) { return !URL_RE.test(x); })) errs.push("Link nguồn phải bắt đầu bằng http:// hoặc https://");
    else if (links.length > 20) errs.push("Tối đa 20 link nguồn.");
    if (!d.frequency) errs.push("Chọn tần suất cập nhật.");
    if (d.data_from && d.data_to && d.data_to < d.data_from) errs.push("Khoảng dữ liệu: “đến ngày” không được trước “từ ngày”.");
    if (d.needed_by && now && d.needed_by <= now) errs.push("“Cần trước” phải là thời điểm trong tương lai.");
    if (!d.purpose) errs.push("Ghi dữ liệu này dùng để làm gì.");
    if ((needReason || []).indexOf(d.urgency) >= 0 && !d.urgency_reason) errs.push("Mức “" + d.urgency + "” cần ghi lý do cần gấp.");
    return errs;
  }
  Avail.prototype.bindPropose = function () {
    var self = this, need = this.boot.need_reason || [], NEW = this.boot.dtype_new || "__new__";
    var f = this.formOv("[data-edh-prop-ov]", "[data-edh-prop-form]", "[data-edh-prop-err]", "[data-edh-prop-submit]", "propose", function (form) {
      var d = formData(form);
      d.data_type = d.data_type_pick === NEW ? (d.data_type_new || "") : (d.data_type_pick || "");
      delete d.data_type_pick;
      delete d.data_type_new;
      var errs = proposalErrors(d, need, nowLocal());
      if (errs.length) return errs.join(" ");
      var inp = self.$("[data-edh-prop-files]", form);
      var list = inp ? inp.files : [];
      return { __prep: function () {
        return H.readFiles(list).then(function (files) {
          if (files.length) d.files = files;
          return { data: JSON.stringify(d) };
        });
      } };
    }, function (out) { return ["Đã gửi đề xuất " + (out.name || "") + ". Team Data sẽ duyệt và báo bạn."]; });
    if (!f) return;
    this.prop = f;
    var el = f.form.elements;
    var dt = this.$("[data-edh-dtype]", f.form), dtNew = this.$("[data-edh-dtype-new]", f.form);
    var syncType = function () {
      var on = dt && dt.value === NEW;
      if (!dtNew) return;
      dtNew.hidden = !on;
      dtNew.required = !!on;
      if (on) dtNew.focus();
    };
    if (dt) dt.addEventListener("change", syncType);
    var urg = this.$("[data-edh-urg]", f.form), why = this.$("[data-edh-urg-why]", f.form);
    var syncUrg = function () {
      var on = !!urg && need.indexOf(urg.value) >= 0;
      if (!why) return;
      why.hidden = !on;
      el.urgency_reason.disabled = !on;
      el.urgency_reason.required = on;
    };
    if (urg) urg.addEventListener("change", function () { syncUrg(); if (!why.hidden) el.urgency_reason.focus(); });
    this.$$("[data-edh-propose]").forEach(function (b) {
      b.addEventListener("click", function () {
        var nb = self.$("[data-edh-need]", f.form);
        if (nb) nb.min = nowLocal();
        syncType();
        syncUrg();
        self.app.openOv(f.ov, b);
        (el.department && !el.department.value ? el.department : el.data_type_pick).focus();
      });
    });
  };

  // ---- chi tiet de xuat (moi nguoi xem bang; tep tai duoc khi la nguoi de xuat / team Data)
  function proposalDetailHtml(p, labels) {
    if (!p) return '<p class="edh-state">Không tìm thấy đề xuất.</p>';
    var row = function (label, html, full) { return html ? '<div' + (full ? ' class="edh-full"' : "") + "><span>" + esc(label) + "</span>" + html + "</div>" : ""; };
    var t = function (v) { return v ? esc(v) : ""; };
    var pre = function (v) { return v ? '<div class="edh-pre">' + esc(v) + "</div>" : ""; };
    var links = (p.links || []).filter(function (x) { return URL_RE.test(x); }).map(function (x) {
      return '<li><a class="edh-link" href="' + esc(x) + '" target="_blank" rel="noopener noreferrer">' + esc(x) + " ↗</a></li>";
    }).join("");
    var files = (p.files || []).map(function (x) {
      var size = ' <span class="edh-hint">' + H.fmtSize(x.size || 0) + "</span>";
      if (x.url && x.url.indexOf("/api/method/") === 0) return '<li><a class="edh-link" href="' + esc(x.url) + '">' + esc(x.name) + "</a>" + size + "</li>";
      return "<li>" + esc(x.name) + size + "</li>";
    }).join("");
    var urgent = p.urgency && p.urgency !== "Bình thường";
    var urgHtml = urgent ? '<span class="edh-badge is-' + (p.urgency === "Khẩn" ? "red" : "amber") + '">' + esc(p.urgency) + "</span>" + (p.urgency_reason ? '<div class="edh-urgwhy">' + esc(p.urgency_reason) + "</div>" : "") : t(p.urgency);
    var h = '<div class="edh-summary">';
    h += row("Phòng ban", t(p.team) + (p.department && p.department !== p.team ? ' <span class="edh-hint">' + esc(p.department) + "</span>" : ""));
    h += row("Loại dữ liệu", "<b>" + t(p.data_type) + "</b>");
    h += row("Sàn", t(p.platform_text));
    h += row("Tần suất cập nhật", t(p.frequency) || '<span class="edh-hint">—</span>');
    h += row("Khoảng dữ liệu", t(p.range_text));
    h += row("Muốn nhận ở", t(p.channel_text));
    h += row("Mức cần gấp", urgHtml, urgent && p.urgency_reason);
    h += row("Cần trước", p.needed_by_fmt ? "<b>" + esc(p.needed_by_fmt) + "</b>" : "");
    h += row("Phạm vi", pre(p.scope), true);
    h += row("Link nguồn", links ? '<ul class="edh-ul">' + links + "</ul>" : "", true);
    h += row("Ảnh / file hướng dẫn", files ? '<ul class="edh-ul">' + files + "</ul>" : "", true);
    h += row("Dùng để làm gì", pre(p.purpose), true);
    h += row("Ghi chú cũ", pre(p.urgency_note), true);
    h += row("Người gửi", t(p.proposer_name) + (p.created_fmt ? ' <span class="edh-hint">· ' + esc(p.created_fmt) + "</span>" : ""));
    h += row("Trạng thái", p.label ? '<span class="edh-badge is-' + esc(p.css || "gray") + '">' + esc(p.label) + "</span>" : "");
    h += row("Ghi chú team Data", p.reason ? "<b>" + t(p.decided_by_name) + ":</b> " + esc(p.reason) : "", true);
    return h + "</div>";
  }
  Avail.prototype.bindProposalDetail = function () {
    var self = this, ov = this.$("[data-edh-pdet-ov]");
    if (!ov) return;
    ov.addEventListener("click", function (e) { if (e.target === ov) self.app.closeOv(ov); });
    this.$$("[data-edh-close]", ov).forEach(function (b) { b.addEventListener("click", function () { self.app.closeOv(ov); }); });
    var tbl = this.$(".edh-props");
    if (!tbl) return;
    tbl.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("[data-edh-pdet-open]") : null;
      if (!b) return;
      var name = b.getAttribute("data-edh-pdet-open");
      var p = (self.boot.proposals || {})[name];
      self.$("[data-edh-pdet-what]").textContent = "· " + name;
      self.$("[data-edh-pdet]").innerHTML = proposalDetailHtml(p, self.boot.channel_labels);
      self.app.openOv(ov, b);
      var dlg = ov.querySelector("[role=dialog]");
      if (dlg) dlg.focus();
    });
  };

  // ---- duyet / tu choi (team Data)
  Avail.prototype.bindReview = function () {
    var self = this;
    this.$$("[data-edh-approve]").forEach(function (b) {
      b.addEventListener("click", function () {
        busy(b, function () { return call("review_proposal", { name: b.dataset.edhApprove, verdict: "Đã duyệt" }, true); }).then(function (out) {
          self.done("Đã duyệt " + b.dataset.edhApprove + ((out && out.created && out.created.length) ? " · thêm ô " + out.created.join(", ") : "") + ". Bấm “Lên kế hoạch” ở danh sách Cần bổ sung.");
        }, function (e) { self.app.fail(e); });
      });
    });
    var f = this.formOv("[data-edh-why-ov]", "[data-edh-why-form]", "[data-edh-why-err]", "[data-edh-why-submit]", "review_proposal", function (form) {
      var r = form.elements.reason.value.trim();
      if (!r) return "Từ chối cần ghi lý do (người đề xuất sẽ thấy).";
      return { name: self._why, verdict: "Từ chối", reason: r };
    }, function () { return ["Đã từ chối " + self._why + " và báo người đề xuất."]; });
    this.$$("[data-edh-reject]").forEach(function (b) {
      b.addEventListener("click", function () {
        self._why = b.dataset.edhReject;
        self.$("[data-edh-why-what]").textContent = "· " + self._why;
        f.form.elements.reason.value = "";
        self.$("[data-edh-why-err]").hidden = true;
        self.app.openOv(f.ov, b);
        f.form.elements.reason.focus();
      });
    });
  };

  // ---- len ke hoach (team Data)
  Avail.prototype.bindPlan = function () {
    var self = this;
    var f = this.formOv("[data-edh-plan-ov]", "[data-edh-plan-form]", "[data-edh-plan-err]", "[data-edh-plan-submit]", "plan_availability", function (form) {
      var d = formData(form), errs = [];
      if (!checkPlatforms(d)) errs.push("Chọn ít nhất một sàn.");
      if (!(d.channels || []).length) errs.push("Chọn ít nhất một kênh đích.");
      if (!d.assignee) errs.push("Chọn người xử lý.");
      if (!d.start_date) errs.push("Chọn ngày bắt đầu.");
      if (!d.due_date) errs.push("Chọn ngày kết thúc.");
      if (d.start_date && d.due_date && d.due_date < d.start_date) errs.push("Ngày kết thúc không được trước ngày bắt đầu.");
      return errs.length ? errs.join(" ") : { data: JSON.stringify(d) };
    }, function (out) { return [out.warning || ("Đã lên kế hoạch " + out.code + " · hạn " + H.fmtDate(out.due) + (out.pm_task ? " · task /pm " + out.pm_task : "") + "."), !!out.warning]; });
    if (!f) return;
    this.plan = f;
    this.$$("[data-edh-plan]").forEach(function (b) {
      b.addEventListener("click", function () {
        var g = (self.boot.gaps || {})[b.dataset.edhPlan];
        if (g) self.openPlan(g, g.platforms, b);
      });
    });
    this.$$("[data-edh-plan-cell]").forEach(function (b) {
      b.addEventListener("click", function () {
        var r = (self.boot.rows || {})[b.dataset.edhPlanCell];
        if (!r) return;
        var g = null;
        Object.keys(self.boot.gaps || {}).forEach(function (k) {
          var x = self.boot.gaps[k];
          if (x.team === r.team && x.data_type === r.data_type) g = x;
        });
        self.openPlan(g || { team: r.team, data_type: r.data_type, proposal: "", urgency: "" }, [r.platform], b);
      });
    });
    var el = f.form.elements;
    el.start_date.addEventListener("change", function () { self.planDefaults(); });
    el.due_date.addEventListener("change", function () { self._customDue = el.due_date.value !== self._ruleDue; });
  };
  Avail.prototype.openPlan = function (g, platforms, opener) {
    var f = this.plan, el = f.form.elements, d = this.boot.plan_defaults || {};
    el.team.value = g.team;
    el.data_type.value = g.data_type;
    el.proposal.value = g.proposal || "";
    el.priority.value = g.urgency || "";
    var other = [];
    (platforms || []).forEach(function (p) { if (MAIN.indexOf(p) < 0) other.push(p); });
    this.$$('input[name="platforms"]', f.form).forEach(function (c) { c.checked = (platforms || []).indexOf(c.value) >= 0; });
    el.other_platform.value = other.join(", ");
    var prop = g.proposal ? (this.boot.proposals || {})[g.proposal] : null;
    var want = (prop && prop.channels && prop.channels.length) ? prop.channels : null;
    this.$$('input[name="channels"]', f.form).forEach(function (c) { c.checked = !want || want.indexOf(c.value) >= 0; });
    el.note.value = prop && prop.brief ? "Từ đề xuất " + g.proposal + ": " + prop.brief : "";
    el.start_date.value = d.start || "";
    el.due_date.value = d.due || "";
    this._ruleDue = d.due;
    this._customDue = false;
    this.$("[data-edh-plan-what]").textContent = "· " + g.data_type + " (" + g.team + ")";
    var pb = this.$("[data-edh-plan-prop]");
    pb.hidden = !g.proposal;
    if (g.proposal) {
      pb.textContent = "Từ đề xuất " + g.proposal + (g.urgency ? " · mức " + g.urgency : "") +
        (prop && prop.urgency_reason ? " (" + prop.urgency_reason + ")" : "") + (prop && prop.brief ? " · " + prop.brief : "") +
        ". Người đề xuất được báo hạn và nghiệm thu khi xong.";
    }
    this.$("[data-edh-plan-rule]").textContent = d.sla_days ? "(mặc định: crawl " + d.sla_days + " ngày làm việc)" : "";
    this.$("[data-edh-plan-err]").hidden = true;
    this.app.openOv(f.ov, opener);
    if (g.urgency && g.urgency !== "Bình thường") this.planDefaults();
    el.assignee.focus();
  };
  Avail.prototype.planDefaults = function () {
    var self = this, el = this.plan.form.elements;
    return call("plan_defaults", { start_date: el.start_date.value, priority: el.priority.value }).then(function (p) {
      self._ruleDue = p.due;
      if (!self._customDue) el.due_date.value = p.due;
      self.$("[data-edh-plan-rule]").textContent = "(mặc định: crawl " + p.sla_days + " ngày làm việc → " + H.fmtDate(p.due) + ")";
      return p;
    }, function (e) { self.app.fail(e); return null; });
  };

  // ---- sua / them dong ma tran (team Data)
  Avail.prototype.bindRow = function () {
    var self = this;
    var f = this.formOv("[data-edh-rowf-ov]", "[data-edh-rowf]", "[data-edh-rowf-err]", "[data-edh-rowf-submit]", "save_availability", function (form) {
      var d = formData(form), errs = [];
      if (!d.team) errs.push("Ghi team.");
      if (!d.data_type) errs.push("Ghi loại dữ liệu.");
      if (!d.platform) errs.push("Ghi sàn / nguồn.");
      return errs.length ? errs.join(" ") : { data: JSON.stringify(d) };
    }, function (out) { return [out.created ? "Đã thêm dòng dữ liệu." : "Đã lưu dòng dữ liệu."]; });
    if (!f) return;
    this.rowf = f;
    this.$$("[data-edh-row-edit]").forEach(function (b) {
      b.addEventListener("click", function () { self.openRow((self.boot.rows || {})[b.dataset.edhRowEdit], b); });
    });
    this.$$("[data-edh-row-new]").forEach(function (b) { b.addEventListener("click", function () { self.openRow(null, b); }); });
    var now = this.$("[data-edh-r-now]", f.form);
    if (now) now.addEventListener("click", function () { f.form.elements.last_updated.value = nowLocal(); });
  };
  Avail.prototype.openRow = function (r, opener) {
    var f = this.rowf, el = f.form.elements;
    r = r || {};
    ["name", "team", "data_type", "platform", "frequency", "data_owner", "note", "last_updated"].forEach(function (k) { el[k].value = r[k] || ""; });
    ["in_sharepoint", "in_dw", "in_powerbi", "front_priority"].forEach(function (k) { el[k].checked = !!r[k]; });
    ["team", "data_type", "platform"].forEach(function (k) { el[k].readOnly = !!r.name; });
    this.$("#edh-rowf-h").textContent = r.name ? "Sửa dòng · " + r.data_type + " · " + r.platform + " (" + r.team + ")" : "Thêm dòng dữ liệu";
    this.$("[data-edh-rowf-err]").hidden = true;
    this.app.openOv(f.ov, opener);
    (r.name ? el.in_sharepoint : el.team).focus();
  };

  // ---- thu vien bao cao (team Data)
  Avail.prototype.bindLibrary = function () {
    var self = this;
    var f = this.formOv("[data-edh-lib-ov]", "[data-edh-lib-form]", "[data-edh-lib-err]", "[data-edh-lib-submit]", "save_library", function (form) {
      var d = formData(form), errs = [];
      if (!d.title) errs.push("Chưa có tên báo cáo.");
      if (!/^https?:\/\//i.test(d.link || "")) errs.push("Link báo cáo phải bắt đầu bằng http:// hoặc https://");
      return errs.length ? errs.join(" ") : { data: JSON.stringify(d) };
    }, function (out) { return [out.created ? "Đã thêm vào Thư viện báo cáo." : "Đã lưu báo cáo."]; });
    if (!f) return;
    this.lib = f;
    this.$$("[data-edh-lib-new]").forEach(function (b) { b.addEventListener("click", function () { self.openLibrary(b, null); }); });
    this.$$("[data-edh-lib-edit]").forEach(function (b) {
      b.addEventListener("click", function () { self.openLibrary(b, (self.boot.library || {})[b.dataset.edhLibEdit]); });
    });
    this.$$("[data-edh-lib-toggle]").forEach(function (b) {
      b.addEventListener("click", function () {
        busy(b, function () { return call("library_active", { name: b.dataset.edhLibToggle, active: b.dataset.active }, true); }).then(function () {
          self.done(b.dataset.active === "1" ? "Đã hiện lại báo cáo." : "Đã ẩn báo cáo (vẫn giữ lịch sử).");
        }, function (e) { self.app.fail(e); });
      });
    });
  };
  Avail.prototype.openLibrary = function (opener, x) {
    if (!this.lib) return;
    var el = this.lib.form.elements;
    x = x || {};
    el.name.value = x.name || "";
    el.title.value = x.title || "";
    el.link.value = x.link || "";
    el.team.value = x.team || "";
    el.report_owner.value = x.owner || "";
    el.data_sources.value = x.data_sources || "";
    el.from_ticket.value = x.from_ticket || "";
    el.tags.value = x.tags || "";
    this.$("#edh-lib-h").textContent = x.name ? "Sửa báo cáo" : "Thêm báo cáo vào thư viện";
    this.$("[data-edh-lib-err]").hidden = true;
    this.app.openOv(this.lib.ov, opener);
    el.title.focus();
  };

  // ---- goi y "da co dashboard tuong tu" tren form tao yeu cau (/du-lieu)
  function bindSuggest(app) {
    var input = app.$("#edh-new-title"), box = app.$("[data-edh-similar]");
    if (!input || !box) return null;
    var last = "";
    var run = function () {
      var q = input.value.trim();
      if (q === last) return Promise.resolve(null);
      last = q;
      if (q.length < 3) { box.hidden = true; box.innerHTML = ""; return Promise.resolve(null); }
      return call("suggest", { q: q }).then(function (s) {
        if (input.value.trim() !== q) return null;
        var h = suggestHtml(s);
        box.innerHTML = h;
        box.hidden = !h;
        return s;
      }, function () { box.hidden = true; return null; });   // goi y la phu: loi thi im lang
    };
    input.addEventListener("input", debounce(run, 350));
    return run;
  }

  function install(app) {
    if (!app) return null;
    var out = {};
    if (app.boot.page === "avail") out.avail = new Avail(app).init();
    if (app.boot.page === "index") out.suggest = bindSuggest(app);
    return out;
  }

  H.avail = { matrixMatch: matrixMatch, libMatch: libMatch, formData: formData, suggestHtml: suggestHtml, debounce: debounce,
              nowLocal: nowLocal, Avail: Avail, install: install, proposalErrors: proposalErrors,
              proposalDetailHtml: proposalDetailHtml, splitLinks: splitLinks };
  var go = function () { H.avail.page = install(H.app); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go);
  else go();
})();
