/* Trung tam Du lieu - trang /du-lieu/quy-tac (dot 3): sua + gui duyet + duyet / tu choi quy tac thoi han.
 *
 * Chi nap tren trang nay, SAU ec_data_hub.bundle.js (dung chung ECDataHub.call / busy - POST kem CSRF,
 * tra {success, message, data}). Server (data_hub/rules_service.py) ve san moi trang thai: bang, cot
 * "De xuat moi", o nhap so (an toi khi bam "Sua quy tac"), nut theo vai. File nay chi: bat / tat che do
 * sua, kiem so lieu ngay tren may (CUNG luat voi rules_domain.normalize_input - test khoa hai ben),
 * gui POST, hoi xac nhan tai cho (khong dung confirm()), tai lai trang khi xong.
 * Ham thuan gan vao window.ECDataHubRules de test jsdom goi thang.
 */
(function () {
  "use strict";
  if (typeof window === "undefined") return;
  if (window.ECDataHubRules && window.ECDataHubRules.__installed) return;

  // ------------------------------------------------------------------ ham thuan ---------------
  function parseNum(v) {
    var s = String(v == null ? "" : v).trim();
    if (!/^-?\d+([.,]\d+)?$/.test(s)) return null;
    return parseFloat(s.replace(",", "."));
  }
  function fmtMult(x) { return String(Math.round(x * 100) / 100).replace(".", ","); }

  /* input = {days: {key: "7"}, mult: {muc: "0,5"}, reason}; boot = {keys, priorities, labels, limits, active}.
   * -> {errors: [..], bad: [ten o], days, mult, changes: n}. Giong rules_domain.normalize_input. */
  function validate(input, boot) {
    var L = boot.limits, errors = [], bad = [], days = {}, mult = {}, changes = 0;
    (boot.keys || []).forEach(function (k) {
      var raw = String((input.days || {})[k] == null ? "" : input.days[k]).trim();
      if (raw === "") { days[k] = boot.active.days[k]; return; }
      if (!/^-?\d+$/.test(raw)) { errors.push("“" + boot.labels[k] + "”: số ngày phải là số nguyên."); bad.push("days." + k); return; }
      var n = parseInt(raw, 10);
      if (n < L.days_min || n > L.days_max) { errors.push("“" + boot.labels[k] + "”: số ngày từ " + L.days_min + " đến " + L.days_max + "."); bad.push("days." + k); return; }
      days[k] = n;
      if (n !== boot.active.days[k]) changes++;
    });
    (boot.priorities || []).forEach(function (p) {
      var raw = String((input.mult || {})[p] == null ? "" : input.mult[p]).trim();
      if (raw === "") { mult[p] = boot.active.mult[p]; return; }
      var x = parseNum(raw);
      if (x === null) { errors.push("Hệ số “" + p + "” phải là số (ví dụ 0,5)."); bad.push("mult." + p); return; }
      if (x < L.mult_min - 1e-9 || x > L.mult_max + 1e-9) { errors.push("Hệ số “" + p + "” từ " + fmtMult(L.mult_min) + " đến " + fmtMult(L.mult_max) + "."); bad.push("mult." + p); return; }
      if (Math.abs(Math.round(x * 100) / 100 - x) > 1e-9) { errors.push("Hệ số “" + p + "” tối đa 2 chữ số thập phân."); bad.push("mult." + p); return; }
      mult[p] = Math.round(x * 100) / 100;
      if (Math.abs(mult[p] - boot.active.mult[p]) > 1e-9) changes++;
    });
    if (String(input.reason || "").length > L.reason_max) errors.push("Lý do dài quá " + L.reason_max + " ký tự.");
    return { errors: errors, bad: bad, days: days, mult: mult, changes: changes };
  }

  // ------------------------------------------------------------------ trang -------------------
  function Page(doc, boot) {
    this.doc = doc;
    this.boot = boot || {};
    this.root = doc.querySelector("[data-edh-rules]");
    this.form = doc.querySelector("[data-edh-rules-form]");
    this.panel = doc.querySelector("[data-edh-rules-panel]");
    this.ask = null;
  }
  Page.prototype.$ = function (sel) { return this.doc.querySelector(sel); };
  Page.prototype.$$ = function (sel) { return Array.prototype.slice.call(this.doc.querySelectorAll(sel)); };
  Page.prototype.hub = function () { return window.ECDataHub || null; };

  Page.prototype.toast = function (msg, err) {
    var t = this.$("[data-edh-toast]");
    if (!t) return;
    t.textContent = msg;
    t.className = "edh-toast" + (err ? " is-err" : "");
    t.hidden = false;
    clearTimeout(this._tt);
    this._tt = setTimeout(function () { t.hidden = true; }, err ? 6000 : 3500);
  };
  Page.prototype.reload = function () {
    var w = this.doc.defaultView;
    if (w.__edhNoReload) { w.__edhReloaded = true; return; }
    w.location.reload();
  };
  Page.prototype.post = function (btn, method, args, okMsg) {
    var self = this, H = this.hub();
    if (!H) { this.toast("Trang chưa tải xong, tải lại trang (Ctrl+Shift+R).", true); return Promise.resolve(null); }
    return H.busy(btn, function () { return H.call(method, args, true); }).then(function (data) {
      self.toast(okMsg);
      self.reload();
      return data;
    }, function (e) {
      if (e && e.message === "__busy") return null;
      self.showErr(e && e.message || "Có lỗi, thử lại sau.");
      return null;
    });
  };
  Page.prototype.showErr = function (msg) {
    var box = (this.ask && this.$("[data-edh-rules-panel-err]")) || this.$("[data-edh-rules-err]");
    if (box && (this.ask || this.editing())) { box.textContent = msg; box.hidden = false; }
    else this.toast(msg, true);
  };

  // ---- che do sua
  Page.prototype.editing = function () { return !!(this.root && this.root.classList.contains("is-editing")); };
  Page.prototype.setEditing = function (on) {
    if (!this.root) return;
    this.closeAsk();
    this.root.classList.toggle("is-editing", !!on);
    var err = this.$("[data-edh-rules-err]");
    if (err) err.hidden = true;
    if (on) {
      var first = this.$("[data-edh-rules-days]");
      if (first) first.focus();
      this.refresh();
    } else if (this.form) {
      this.form.reset();
      this.refresh();
    }
  };
  Page.prototype.input = function () {
    var out = { days: {}, mult: {}, reason: "" };
    this.$$("[data-edh-rules-days]").forEach(function (el) { out.days[el.getAttribute("data-edh-rules-days")] = el.value; });
    this.$$("[data-edh-rules-mult]").forEach(function (el) { out.mult[el.getAttribute("data-edh-rules-mult")] = el.value; });
    var r = this.$("[data-edh-rules-reason]");
    out.reason = r ? r.value.trim() : "";
    return out;
  };
  /* Danh dau o doi so voi dang ap dung + o sai; dem so thay doi. */
  Page.prototype.refresh = function () {
    var res = validate(this.input(), this.boot);
    this.$$(".edh-rules-num").forEach(function (el) {
      var name = el.getAttribute("name");
      var active = el.getAttribute("data-active");
      var same = el.hasAttribute("data-edh-rules-mult")
        ? (parseNum(el.value) !== null && Math.abs(parseNum(el.value) - parseNum(active)) < 1e-9)
        : String(el.value).trim() === String(active);
      el.classList.toggle("is-changed", !same);
      if (res.bad.indexOf(name) >= 0) el.setAttribute("aria-invalid", "true"); else el.removeAttribute("aria-invalid");
    });
    var c = this.$("[data-edh-rules-count]");
    if (c) c.textContent = res.changes ? (res.changes + " thay đổi so với quy tắc đang áp dụng.") : "Chưa đổi gì so với quy tắc đang áp dụng.";
    return res;
  };
  Page.prototype.save = function (btn, submit) {
    var inp = this.input(), res = this.refresh(), err = this.$("[data-edh-rules-err]");
    var errors = res.errors.slice();
    if (!res.changes) errors.push("Chưa có gì thay đổi so với quy tắc đang áp dụng.");
    if (submit && !inp.reason) errors.push("Ghi lý do thay đổi để người duyệt quy tắc xem xét.");
    if (errors.length) {
      if (err) { err.textContent = errors.join("\n"); err.hidden = false; }
      if (submit && !inp.reason) { var r = this.$("[data-edh-rules-reason]"); if (r) r.focus(); }
      return Promise.resolve(null);
    }
    if (err) err.hidden = true;
    return this.post(btn, "save_rule_draft",
      { data: { days: res.days, mult: res.mult, reason: inp.reason, submit: submit ? 1 : 0 } },
      submit ? "Đã gửi duyệt. Quy tắc cũ vẫn áp dụng tới khi được duyệt." : "Đã lưu bản nháp.");
  };

  // ---- hoi xac nhan tai cho (duyet / tu choi / rut lai / huy ban nhap)
  var ASK = {
    approve: { label: "Ghi chú (không bắt buộc)", ok: "Xác nhận duyệt", need: false,
               hint: "Duyệt xong: bộ mới áp dụng cho yêu cầu MỚI từ hôm nay; yêu cầu đã gửi giữ hạn cũ." },
    reject: { label: "Lý do từ chối (bắt buộc - team Data sẽ thấy)", ok: "Từ chối thay đổi", need: true, css: "is-reject" },
    withdraw: { label: "Lý do rút lại (không bắt buộc)", ok: "Rút lại đề xuất", need: false },
    discard: { label: "Lý do huỷ bản nháp (không bắt buộc)", ok: "Huỷ bản nháp", need: false, css: "is-reject" },
  };
  Page.prototype.openAsk = function (kind, name) {
    var conf = ASK[kind];
    if (!conf || !this.panel) return;
    this.ask = { kind: kind, name: name };
    this.panel.hidden = false;
    this.panel.className = "edh-rules-ask" + (conf.css ? " " + conf.css : "");
    this.$("[data-edh-rules-note-label]").textContent = conf.label;
    var ok = this.$("[data-edh-rules-panel-ok]");
    ok.textContent = conf.ok;
    ok.className = "edh-btn " + (conf.css ? "is-danger" : "is-primary");
    var note = this.$("[data-edh-rules-note]");
    note.value = "";
    note.placeholder = conf.hint || "";
    var err = this.$("[data-edh-rules-panel-err]");
    err.hidden = true;
    note.focus();
  };
  Page.prototype.closeAsk = function () {
    this.ask = null;
    if (this.panel) this.panel.hidden = true;
  };
  Page.prototype.confirmAsk = function (btn) {
    if (!this.ask) return Promise.resolve(null);
    var a = this.ask, conf = ASK[a.kind], note = this.$("[data-edh-rules-note]").value.trim();
    if (conf.need && !note) {
      var err = this.$("[data-edh-rules-panel-err]");
      err.textContent = "Ghi lý do từ chối để team Data biết cần sửa gì.";
      err.hidden = false;
      return Promise.resolve(null);
    }
    if (a.kind === "approve") return this.post(btn, "decide_rule", { name: a.name, verdict: "approve", note: note }, "Đã duyệt - bộ quy tắc mới đang áp dụng.");
    if (a.kind === "reject") return this.post(btn, "decide_rule", { name: a.name, verdict: "reject", note: note }, "Đã từ chối - đã báo người đề xuất.");
    return this.post(btn, "cancel_rule", { name: a.name, reason: note }, a.kind === "withdraw" ? "Đã rút lại đề xuất." : "Đã huỷ bản nháp.");
  };

  Page.prototype.init = function () {
    var self = this;
    if (!this.root) return this;
    this.$$("[data-edh-rules-edit]").forEach(function (b) { b.addEventListener("click", function () { self.setEditing(true); }); });
    var cancel = this.$("[data-edh-rules-cancel-edit]");
    if (cancel) cancel.addEventListener("click", function () { self.setEditing(false); });
    var save = this.$("[data-edh-rules-save]");
    if (save) save.addEventListener("click", function () { self.save(save, false); });
    this.$$("[data-edh-rules-send]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (b.getAttribute("data-edh-rules-send") === "edit") return self.save(b, true);
        // Ban nhap da luu: chua co ly do -> mo che do sua, tro vao o ly do.
        if (b.getAttribute("data-need-reason")) {
          self.setEditing(true);
          var r = self.$("[data-edh-rules-reason]");
          var err = self.$("[data-edh-rules-err]");
          if (err) { err.textContent = "Ghi lý do thay đổi trước khi gửi duyệt."; err.hidden = false; }
          if (r) r.focus();
          return null;
        }
        return self.post(b, "submit_rule", { name: b.getAttribute("data-name") }, "Đã gửi duyệt. Quy tắc cũ vẫn áp dụng tới khi được duyệt.");
      });
    });
    this.$$("[data-edh-rules-ask]").forEach(function (b) {
      b.addEventListener("click", function () { self.openAsk(b.getAttribute("data-edh-rules-ask"), b.getAttribute("data-name")); });
    });
    var close = this.$("[data-edh-rules-panel-close]");
    if (close) close.addEventListener("click", function () { self.closeAsk(); });
    var ok = this.$("[data-edh-rules-panel-ok]");
    if (ok) ok.addEventListener("click", function () { self.confirmAsk(ok); });
    if (this.form) {
      this.form.addEventListener("input", function () { if (self.editing()) self.refresh(); });
      this.form.addEventListener("submit", function (e) { e.preventDefault(); });
    }
    this.doc.addEventListener("keydown", function (e) {
      if ((e.key === "Escape" || e.key === "Esc") && self.ask) self.closeAsk();
    });
    return this;
  };

  function boot(doc) {
    doc = doc || document;
    var data = {};
    try { data = JSON.parse((doc.getElementById("edh-boot") || {}).textContent || "{}"); } catch (e) { data = {}; }
    if (data.page !== "rules" || data.denied) return null;
    return new Page(doc, data).init();
  }

  window.ECDataHubRules = { __installed: true, Page: Page, boot: boot, validate: validate, parseNum: parseNum, fmtMult: fmtMult };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { window.ECDataHubRules.page = boot(document); });
  else window.ECDataHubRules.page = boot(document);
})();
