// Copyright (c) 2026, eCentric and contributors
//
// "Cho toi duyet" - duyet nhanh tren dien thoai (06/10/2026, Hoan).
//
// Gan vao MOI phan tu co [data-ec-cho-duyet] (hien o /viec-cua-toi). Trang ve san khung + dong
// "Dang tai..." trong markup; asset nay chi THAY noi dung #cd-body sau khi co du lieu, khong an
// / khong lam mo / khong ve lai khung.
//
// SERVER QUYET DINH HET (approval_center/shared/requests/quick_approve.py):
//   list_my_pending  - phieu dang cho DUNG minh o DUNG cap hien tai + tom tat + quyen
//   quick_decide     - di qua controller cua chinh loai phieu; loi -> hoan tac + cau bao ro
// O day chi ve the, bang truot, va goi hai cua do. Loai can nhap them (ky so, chinh so tien,
// ngay Operation) -> chi co nut "Mo trang chi tiet". KHONG co duyet hang loat (07/10, Hoan bo:
// moi phieu phai duoc mo ra va quyet dinh rieng).
//
// Sau moi quyet dinh: phat su kien `ec:cho-duyet-doi` {count} - trang /viec-cua-toi nghe de
// tai lai lan "Viec" (cung nguon voi badge "Viec cua toi").
// KHONG boc window.fetch; goi fetch thang, mang CSRF token cua trang.
(function () {
  "use strict";
  if (window.EcChoDuyet) return;
  var API = "/api/method/ecentric_workspace.approval_center.reporting.actions.";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function csrf() {
    return (window.frappe && window.frappe.csrf_token) || window.csrf_token || "";
  }
  function fmtDate(s) {
    if (!s) return "";
    var m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
    if (!m) return esc(s);
    return m[3] + "/" + m[2] + (m[4] ? " " + m[4] + ":" + m[5] : "");
  }
  // Gia tri o mat "xem day du" den tu get_request_detail DANG THO (90500000, 2026-07-01) - cung
  // nguon popup trang "Tat ca yeu cau" dung, nen dinh dang o day theo fieldtype server gui kem.
  function fmtVal(v, t) {
    if (v == null || v === "") return "";
    var s = String(v);
    if ((t === "Currency" || t === "Int" || t === "Float") && /^-?\d+(\.\d+)?$/.test(s)) {
      var n = Number(s), neg = n < 0 ? "-" : "";
      n = Math.abs(n);
      var ip = Math.floor(n), frac = Math.round((n - ip) * 100);
      return neg + String(ip).replace(/\B(?=(\d{3})+(?!\d))/g, ".") + (frac ? "," + (frac < 10 ? "0" : "") + frac : "");
    }
    var m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
    if (m && (t === "Date" || t === "Datetime")) return m[3] + "/" + m[2] + "/" + m[1] + (m[4] && t === "Datetime" ? " " + m[4] + ":" + m[5] : "");
    return s;
  }

  // Cau bao loi: lay nguyen van cau server (QuickDecideError 417). 401 moi la het phien;
  // 403 la thieu quyen - KHONG bao "dang nhap lai".
  function serverMsg(status, j) {
    var m = "";
    try {
      var sm = j && j._server_messages ? JSON.parse(j._server_messages) : [];
      if (sm.length) { var x = JSON.parse(sm[sm.length - 1]); m = x.message || ""; }
    } catch (e) { /* bo qua */ }
    if (!m && j && j.exception) m = String(j.exception).replace(/^[\w.]+:\s*/, "");
    if (status === 401) return "Phiên đăng nhập đã hết - tải lại trang để đăng nhập.";
    if (status === 403) return m ? ("Không đủ quyền: " + m) : "Bạn không có quyền thực hiện thao tác này trên phiếu.";
    return m || "Không thực hiện được. Thử lại sau.";
  }
  function get(method) {
    return fetch(API + method, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(serverMsg(r.status, j)); return j.message; }); });
  }
  function post(method, body) {
    return fetch(API + method, {
      method: "POST", credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf() },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) {
      if (!r.ok) throw new Error(serverMsg(r.status, j)); return j.message; }); });
  }

  function Inst(root) {
    this.root = root;
    this.body = root.querySelector("[data-cd-body]") || root;
    this.countEl = root.querySelector("[data-cd-count]");
    this.rows = [];
    this.busy = false;
    var self = this;
    root.addEventListener("click", function (ev) { self.onClick(ev); });
    this.load();
  }

  Inst.prototype.load = function () {
    var self = this;
    return get("list_my_pending").then(function (m) {
      self.rows = (m && m.rows) || [];
      self.error = "";
      self.paint();
    }).catch(function (e) { self.error = e.message; self.paint(); });
  };

  Inst.prototype.setCount = function () {
    if (this.countEl) this.countEl.textContent = this.error ? "" : String(this.rows.length);
  };

  Inst.prototype.paint = function () {
    this.setCount();
    if (this.error) {
      this.body.innerHTML = '<div class="cd-err">' + esc(this.error)
        + ' <button type="button" class="cd-link" data-cd-retry>Thử lại</button></div>';
      return;
    }
    if (!this.rows.length) {
      this.body.innerHTML = '<p class="cd-empty">Không có phiếu nào đang chờ bạn duyệt.</p>';
      return;
    }
    var groups = [], by = {};
    this.rows.forEach(function (r) {
      var k = r.type_label || r.approval_type;
      if (!by[k]) { by[k] = []; groups.push(k); }
      by[k].push(r);
    });
    var self = this, h = [];
    groups.forEach(function (g) {
      h.push('<div class="cd-group"><div class="cd-gh">' + esc(g) + ' <span>' + by[g].length + "</span></div>");
      by[g].forEach(function (r) { h.push(self.cardHTML(r)); });
      h.push("</div>");
    });
    this.body.innerHTML = h.join("");
  };

  Inst.prototype.cardHTML = function (r) {
    var c = r.capabilities || {};
    var chips = (r.summary || []).slice(0, 3).map(function (s) {
      return '<span class="cd-chip"><i>' + esc(s.label) + "</i> " + esc(s.value) + "</span>";
    }).join("");
    var meta = esc(r.requester_name || r.requested_by) + " · gửi " + fmtDate(r.submitted_at)
      + (r.due_at ? ' · <b class="cd-due">hạn ' + fmtDate(r.due_at) + "</b>" : "");
    var act = c.needs_input
      ? (r.detail_url ? '<a class="cd-btn" href="' + esc(r.detail_url) + '">Mở để duyệt</a>' : "")
      : (c.can_approve ? '<button type="button" class="cd-btn cd-ok" data-cd-quick="' + esc(r.request) + '">'
          + (c.sign_required ? "Duyệt &amp; Ký" : "Duyệt") + "</button>" : "");
    return '<article class="cd-card" data-cd-open="' + esc(r.request) + '">'
      + '<div class="cd-main"><div class="cd-title">' + esc(r.title) + "</div>"
      + '<div class="cd-meta">' + meta + "</div>"
      + (chips ? '<div class="cd-chips">' + chips + "</div>" : "")
      + (c.needs_input ? '<div class="cd-note">' + esc(c.needs_input_reason) + "</div>" : "")
      + "</div>" + (act ? '<div class="cd-act">' + act + "</div>" : "") + "</article>";
  };

  Inst.prototype.find = function (id) {
    for (var i = 0; i < this.rows.length; i++) if (this.rows[i].request === id) return this.rows[i];
    return null;
  };

  Inst.prototype.onClick = function (ev) {
    var t = ev.target;
    if (!t.closest) return;
    if (t.closest("[data-cd-retry]")) { this.load(); return; }
    var q = t.closest("[data-cd-quick]");
    if (q) { ev.stopPropagation(); this.openSheet(this.find(q.getAttribute("data-cd-quick"))); return; }
    if (t.closest("a")) return;            // "Mo de duyet" -> trang chi tiet
    var card = t.closest("[data-cd-open]");
    if (card) this.openSheet(this.find(card.getAttribute("data-cd-open")));
  };

  // ---- bang truot tu duoi len -------------------------------------------------------
  var SIGN_FILE = "/api/method/ecentric_workspace.platform.esign.api.get_package_file?dsf_name=";
  var ACT_VI = { Submitted: "Đã gửi", Approved: "Đã duyệt", Rejected: "Từ chối", "Information Requested": "Yêu cầu bổ sung",
    Resubmitted: "Gửi lại", Restarted: "Gửi lại từ đầu", Skipped: "Bỏ qua", Cancelled: "Huỷ", Reminded: "Nhắc xử lý",
    Commented: "Ghi chú", Signed: "Đã ký" };

  Inst.prototype.openSheet = function (r) {
    if (!r) return;
    var self = this, c = r.capabilities || {};
    var ov = document.createElement("div");
    ov.className = "cd-ov";
    var rows = (r.summary || []).map(function (s) {
      return '<div class="cd-kv"><span>' + esc(s.label) + "</span><b>" + esc(s.value) + "</b></div>";
    }).join("");
    // 07/10 (Hoan chot "vao thang B"): cap ky so duyet & ky NGAY TAI BANG, kem link xem tai
    // lieu se ky (qua cua co kiem quyen, khong lo /private/files).
    var files = (c.sign_required && (r.sign_files || []).length)
      ? '<div class="cd-docs">' + (r.sign_files || []).map(function (f) {
          return '<a class="cd-doc" href="' + SIGN_FILE + encodeURIComponent(f.dsf) + '" target="_blank" rel="noopener">'
            + '<span class="cd-doc-ic" aria-hidden="true">PDF</span><span class="cd-doc-nm"><b>Tài liệu sẽ ký</b><i>'
            + esc(f.file_name) + "</i></span><span class=\"cd-doc-go\">Xem</span></a>";
        }).join("") + "</div>"
      : "";
    var btns = c.needs_input
      ? (r.detail_url ? '<a class="cd-btn cd-ok cd-wide" href="' + esc(r.detail_url) + '">Mở trang chi tiết để duyệt</a>' : "")
      : ((c.can_approve ? (c.sign_required
            ? '<button type="button" class="cd-btn cd-ok" data-cd-do="approve_sign">Duyệt &amp; Ký</button>'
            : '<button type="button" class="cd-btn cd-ok" data-cd-do="approve">Duyệt</button>') : "")
        + (c.can_request_info ? '<button type="button" class="cd-btn" data-cd-do="request_information">Yêu cầu bổ sung</button>' : "")
        + (c.can_reject ? '<button type="button" class="cd-btn cd-no" data-cd-do="reject">Từ chối</button>' : ""));
    ov.innerHTML = '<div class="cd-sheet" role="dialog" aria-modal="true" aria-label="' + esc(r.title) + '">'
      + '<div class="cd-grip" aria-hidden="true"></div>'
      + '<div data-cd-pane="act">'
      + '<div class="cd-sh-head"><div><div class="cd-sh-type">' + esc(r.type_label) + " · " + esc(r.level_name || "") + "</div>"
      + '<div class="cd-sh-title">' + esc(r.title) + "</div>"
      + '<div class="cd-meta">' + esc(r.requester_name || r.requested_by) + " · gửi " + fmtDate(r.submitted_at)
      + (r.due_at ? " · hạn " + fmtDate(r.due_at) : "") + "</div></div>"
      + '<button type="button" class="cd-x" data-cd-close aria-label="Đóng">&times;</button></div>'
      + (rows ? '<div class="cd-kvs">' + rows + "</div>" : "")
      + files
      + (c.needs_input ? '<div class="cd-note">' + esc(c.needs_input_reason) + "</div>"
        : '<label class="cd-lbl" for="cd-cmt">Nhận xét / lý do'
          + (c.comment_required ? ' <span class="cd-req">(bắt buộc khi duyệt)</span>' : "")
          + '</label><textarea id="cd-cmt" rows="3" placeholder="Từ chối / yêu cầu bổ sung bắt buộc ghi lý do"></textarea>'
          + '<div class="cd-msg" data-cd-msg role="alert"></div>')
      + '<div class="cd-sh-btns">' + btns + "</div>"
      + (c.sign_required && !c.needs_input ? '<p class="cd-hint">Chữ ký được xác nhận trong vài phút sau khi gửi.</p>' : "")
      + '<button type="button" class="cd-link cd-full" data-cd-full>Xem đầy đủ phiếu</button>'
      + "</div>"
      + '<div data-cd-pane="full" hidden></div>'
      + "</div>";
    document.body.appendChild(ov);
    var close = function () {
      if (ov.parentNode) ov.parentNode.removeChild(ov);
      if (ov.__unlock) ov.__unlock();
    };
    ov.addEventListener("click", function (ev) {
      if (ev.target === ov || (ev.target.closest && ev.target.closest("[data-cd-close]"))) { close(); return; }
      if (ev.target.closest && ev.target.closest("[data-cd-full]")) { self.showFull(r, ov); return; }
      if (ev.target.closest && ev.target.closest("[data-cd-back]")) { self.pane(ov, "act"); return; }
      var b = ev.target.closest && ev.target.closest("[data-cd-do]");
      if (b) self.decide(r, b.getAttribute("data-cd-do"), ov, close);
    });
    // KHONG tu focus o nhan xet (07/10, Hoan): focus la bat ban phim len, che mat phieu dang
    // doc. Nguoi duyet tu cham vao o khi can ghi.
    self.lockScroll(ov, close);
  };

  // 07/10 (Hoan): keo trong bang thi BANG di chuyen, khong phai trang nen.
  //  * khoa cuon trang nen khi bang mo (tra lai dung vi tri khi dong);
  //  * bang tu cuon ben trong (overscroll-behavior: contain o CSS);
  //  * dang o dau bang ma keo XUONG -> bang di xuong theo ngon tay; tha qua 90px thi dong,
  //    chua toi thi bat ve.
  Inst.prototype.lockScroll = function (ov, close) {
    var de = document.documentElement, b = document.body;
    var prev = [de.style.overflow, b.style.overflow];
    de.style.overflow = "hidden"; b.style.overflow = "hidden";
    ov.__unlock = function () { de.style.overflow = prev[0]; b.style.overflow = prev[1]; };
    var sh = ov.querySelector(".cd-sheet");
    if (!sh) return;
    // Cham vao nen mo (ngoai bang) ma keo -> khong cho trang nen cuon theo (iOS bo qua
    // overflow:hidden cua body khi keo tren lop phu).
    ov.addEventListener("touchmove", function (e) {
      if (!sh.contains(e.target) && e.cancelable) e.preventDefault();
    }, { passive: false });
    var y0 = null, dy = 0;
    sh.addEventListener("touchstart", function (e) {
      y0 = (sh.scrollTop <= 0 && e.touches && e.touches.length === 1) ? e.touches[0].clientY : null;
      dy = 0;
    }, { passive: true });
    sh.addEventListener("touchmove", function (e) {
      if (y0 == null) return;
      dy = e.touches[0].clientY - y0;
      if (dy <= 0 || sh.scrollTop > 0) { dy = 0; sh.style.transform = ""; return; }
      if (e.cancelable) e.preventDefault();
      sh.style.transition = "none";
      sh.style.transform = "translateY(" + dy + "px)";
    }, { passive: false });
    sh.addEventListener("touchend", function () {
      if (y0 == null) return;
      y0 = null;
      sh.style.transition = "transform .18s ease-out";
      if (dy > 90) { sh.style.transform = "translateY(100%)"; setTimeout(close, 160); }
      else { sh.style.transform = ""; }
      dy = 0;
    });
  };

  // Hai mat cua CUNG mot bang: "act" (quyet dinh) va "full" (xem day du). Doi mat do nguoi
  // dung bam, khong phai luc tai - binh luan / chu dang go o mat "act" van giu nguyen.
  Inst.prototype.pane = function (ov, which) {
    Array.prototype.forEach.call(ov.querySelectorAll("[data-cd-pane]"), function (p) {
      p.hidden = p.getAttribute("data-cd-pane") !== which;
    });
    var sh = ov.querySelector(".cd-sheet");
    if (sh) { sh.classList.toggle("cd-sheet-full", which === "full"); sh.scrollTop = 0; }
  };

  // Chi tiet day du = DUNG cua popup trang "Tat ca yeu cau" (reporting.actions.get_request_detail:
  // facade.detail cua chinh form -> da kiem quyen xem, da an luong theo luat cua form).
  Inst.prototype.showFull = function (r, ov) {
    var self = this, box = ov.querySelector('[data-cd-pane="full"]');
    var head = '<button type="button" class="cd-link cd-back" data-cd-back>‹ Về bước duyệt</button>'
      + '<div class="cd-sh-title">' + esc(r.title) + "</div>";
    box.innerHTML = head + '<p class="cd-loading">Đang tải chi tiết phiếu…</p>';
    this.pane(ov, "full");
    get("get_request_detail?request_name=" + encodeURIComponent(r.request)).then(function (d) {
      d = d || {};
      var f = (d.display_fields || []).map(function (x) {
        return '<div class="cd-kv"><span>' + esc(x.label) + "</span><b>" + esc(fmtVal(x.value, x.fieldtype)) + "</b></div>";
      }).join("");
      var att = (d.attachments || []).map(function (a) {
        var url = a.sp_share_url || a.sp_web_url || a.file_url;
        return '<div class="cd-kv"><span class="cd-fn">' + esc(a.file_name || a.file_url) + '</span><b><a class="cd-a" href="'
          + esc(url) + '" target="_blank" rel="noopener">Mở</a></b></div>';
      }).join("");
      var tl = (d.timeline || []).map(function (t) {
        return '<div class="cd-tl"><b>' + esc(ACT_VI[t.action] || t.action) + "</b> · " + esc(t.actor || "")
          + " · " + fmtDate(t.action_time) + (t.comment ? '<div class="cd-tl-c">' + esc(t.comment) + "</div>" : "") + "</div>";
      }).join("");
      box.innerHTML = head
        + (f ? '<div class="cd-sec">Thông tin</div><div class="cd-kvs">' + f + "</div>" : "")
        + (att ? '<div class="cd-sec">Đính kèm (' + (d.attachments || []).length + ')</div><div class="cd-kvs">' + att + "</div>" : "")
        + (tl ? '<div class="cd-sec">Lịch sử duyệt</div>' + tl : "")
        + '<button type="button" class="cd-btn cd-ok cd-wide cd-mt" data-cd-back>Về bước duyệt</button>'
        + (r.detail_url ? '<a class="cd-link cd-full" href="' + esc(r.detail_url) + '">Mở trang đầy đủ</a>' : "");
    }).catch(function (e) {
      box.innerHTML = head + '<div class="cd-err">' + esc(e.message) + "</div>"
        + '<button type="button" class="cd-btn cd-wide cd-mt" data-cd-back>Về bước duyệt</button>';
    });
  };

  Inst.prototype.decide = function (r, action, ov, close) {
    if (this.busy) return;
    var c = r.capabilities || {};
    var ta = ov.querySelector("#cd-cmt"), msg = ov.querySelector("[data-cd-msg]");
    var cmt = ta ? (ta.value || "").trim() : "";
    var say = function (t) { if (msg) msg.textContent = t; };
    if ((action === "reject" || action === "request_information") && !cmt) { say(action === "reject" ? "Từ chối bắt buộc ghi lý do." : "Ghi rõ cần bổ sung gì."); if (ta) ta.focus(); return; }
    if ((action === "approve" || action === "approve_sign") && c.comment_required && !cmt) { say("Loại phiếu này bắt buộc nhập nhận xét khi duyệt."); if (ta) ta.focus(); return; }
    var self = this, btns = ov.querySelectorAll("[data-cd-do]");
    this.busy = true;
    Array.prototype.forEach.call(btns, function (b) { b.disabled = true; });
    say("Đang gửi…");
    post("quick_decide", { request_name: r.request, action: action, comment: cmt }).then(function (res) {
      self.busy = false;
      close();
      self.removeRow(r.request, res && res.remaining);
      self.toast({ approve: "Đã duyệt ", approve_sign: "Đã gửi lệnh ký - ", reject: "Đã từ chối ",
                   request_information: "Đã yêu cầu bổ sung " }[action] + r.title);
    }).catch(function (e) {
      self.busy = false;
      Array.prototype.forEach.call(btns, function (b) { b.disabled = false; });
      say(e.message);
    });
  };

  Inst.prototype.removeRow = function (id, remaining) {
    this.rows = this.rows.filter(function (x) { return x.request !== id; });
    this.paint();
    try {
      document.dispatchEvent(new CustomEvent("ec:cho-duyet-doi",
        { detail: { count: remaining != null ? remaining : this.rows.length } }));
    } catch (e) { /* trinh duyet cu */ }
  };

  Inst.prototype.toast = function (text, isErr) {
    var t = this.root.querySelector("[data-cd-toast]");
    if (!t) { t = document.createElement("div"); t.setAttribute("data-cd-toast", ""); t.className = "cd-toast"; t.setAttribute("role", "status"); this.root.appendChild(t); }
    t.textContent = text;
    t.className = "cd-toast" + (isErr ? " cd-toast-err" : "");
    clearTimeout(this._tt);
    this._tt = setTimeout(function () { t.textContent = ""; }, isErr ? 8000 : 3500);
  };

  function mountAll() {
    var nodes = document.querySelectorAll("[data-ec-cho-duyet]");
    Array.prototype.forEach.call(nodes, function (n) {
      if (!n.__ecCd) n.__ecCd = new Inst(n);
    });
  }
  window.EcChoDuyet = { mountAll: mountAll, _Inst: Inst };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountAll);
  else mountAll();
})();
