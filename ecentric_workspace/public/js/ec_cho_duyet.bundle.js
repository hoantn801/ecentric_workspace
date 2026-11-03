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
//
// UX 03/11/2026 (ux2, dien thoai 390px):
//   * the: so tien noi bat (row.amount do server chon tu tom tat DA loc luong), han tuong doi
//     "Qua han 2 ngay" / "Han hom nay 17:00", the qua han to vien do, nhom ghi "N qua han";
//   * bang: Tu choi / Yeu cau bo sung co BUOC XAC NHAN (ly do bat buoc) - Duyet giu mot cham;
//     chong mo 2 bang chong nhau (truoc day keo khoa cuon trang vinh vien), Esc de dong, tra
//     focus ve the; chong bam 2 lan (nut khoa + chu "Dang duyet...");
//   * loi: KHONG bao gio hien chu ky thuat (exception, "Failed to fetch", HTTP 500) - chi cau
//     tieng Viet; mat mang -> bao offline va tu tai lai khi co mang.
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

  // Cau bao loi: lay nguyen van cau NGHIEP VU cua server (QuickDecideError / ValidationError,
  // HTTP 417 - server viet san tieng Viet). 401 moi la het phien; 403 la thieu quyen - KHONG bao
  // "dang nhap lai". Loi he thong (5xx, HTML, exception tho) KHONG bao gio len man hinh nguyen
  // van: nguoi duyet chi can biet "chua xu ly duoc, thu lai" (UX 03/11/2026).
  var MSG_NET = "Không kết nối được máy chủ - kiểm tra mạng (Wi-Fi / 4G) rồi thử lại.";
  var MSG_OFF = "Bạn đang mất mạng. Danh sách sẽ tự tải lại khi có mạng.";
  var MSG_SYS = "Hệ thống đang bận nên chưa xử lý được. Thử lại sau ít phút.";
  function plain(s) {
    return String(s == null ? "" : s).replace(/<[^>]*>/g, " ").replace(/&nbsp;/g, " ")
      .replace(/\s+/g, " ").trim();
  }
  function serverMsg(status, j) {
    var m = "";
    try {
      var sm = j && j._server_messages ? JSON.parse(j._server_messages) : [];
      if (sm.length) { var x = JSON.parse(sm[sm.length - 1]); m = plain(x.message || ""); }
    } catch (e) { /* bo qua */ }
    var exc = (j && j.exc_type) || "";
    if (status === 401) return "Phiên đăng nhập đã hết - tải lại trang để đăng nhập.";
    if (exc === "CSRFTokenError") return "Trang đã mở quá lâu - tải lại trang rồi thử lại.";
    if (status === 403) return m ? ("Không đủ quyền: " + m) : "Bạn không có quyền thực hiện thao tác này trên phiếu.";
    // 417 = loi nghiep vu (ValidationError va con): cau server la cau cho nguoi dung doc.
    if (status === 417) {
      if (!m && j && j.exception) m = plain(String(j.exception).replace(/^[\w.]+:\s*/, ""));
      return m || "Không thực hiện được. Thử lại sau.";
    }
    return MSG_SYS;
  }
  // fetch tu choi (mat mang, DNS, bi chan) -> TypeError "Failed to fetch" tieng Anh. Doi thanh
  // cau tieng Viet; loi da qua serverMsg (co .cd) giu nguyen.
  function netErr(e) {
    if (e && e.cd) throw e;
    var x = new Error((typeof navigator !== "undefined" && navigator.onLine === false) ? MSG_OFF : MSG_NET);
    x.cd = true; x.offline = true;
    throw x;
  }
  function handle(r) {
    return r.json().catch(function () { return {}; }).then(function (j) {
      if (!r.ok) { var e = new Error(serverMsg(r.status, j)); e.cd = true; e.status = r.status; throw e; }
      return j.message;
    });
  }
  function get(method) {
    return fetch(API + method, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(handle, netErr);
  }
  function post(method, body) {
    return fetch(API + method, {
      method: "POST", credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrf() },
      body: JSON.stringify(body)
    }).then(handle, netErr);
  }

  // Han cua cap hien tai -> chu tieng Viet theo NGAY LICH (gio site = gio VN, may nguoi dung o
  // VN): "Quá hạn 2 ngày", "Quá hạn" (cung ngay, da qua gio), "Hạn hôm nay 17:00",
  // "Hạn ngày mai", "Hạn 07/10". now truyen vao de test co dinh.
  function parseLocal(s) {
    var m = String(s || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
    if (!m) return null;
    return new Date(+m[1], +m[2] - 1, +m[3], m[4] ? +m[4] : 23, m[5] ? +m[5] : 59);
  }
  function dueInfo(s, now) {
    var d = parseLocal(s);
    if (!d) return null;
    now = now || new Date();
    var day = function (x) { return new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime(); };
    var diff = Math.round((day(d) - day(now)) / 86400000);
    var hm = ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
    if (d.getTime() < now.getTime()) {
      return { od: true, text: diff < 0 ? ("Quá hạn " + (-diff) + " ngày") : "Quá hạn từ " + hm };
    }
    if (diff === 0) return { od: false, soon: true, text: "Hạn hôm nay " + hm };
    if (diff === 1) return { od: false, soon: true, text: "Hạn ngày mai" };
    return { od: false, text: "Hạn " + fmtDate(s).slice(0, 5) };
  }

  function Inst(root) {
    this.root = root;
    this.body = root.querySelector("[data-cd-body]") || root;
    this.countEl = root.querySelector("[data-cd-count]");
    this.rows = [];
    this.busy = false;
    var self = this;
    root.addEventListener("click", function (ev) { self.onClick(ev); });
    // The co tabindex=0 -> ban phim: Enter / Space tren the mo bang (nhu cham).
    root.addEventListener("keydown", function (ev) {
      var t = ev.target;
      if ((ev.key === "Enter" || ev.key === " ") && t && t.matches && t.matches("[data-cd-open]")) {
        ev.preventDefault(); self.openSheet(self.find(t.getAttribute("data-cd-open")), t);
      }
    });
    // Mat mang luc tai -> khi co mang lai thi tu tai, khong bat nguoi dung bam "Thu lai".
    window.addEventListener("online", function () { if (self.error) self.load(); });
    this.load();
  }

  Inst.prototype.load = function () {
    var self = this;
    return get("list_my_pending").then(function (m) {
      self.rows = (m && m.rows) || [];
      self.error = "";
      self.paint();
    }).catch(function (e) { self.error = (e && e.cd) ? e.message : MSG_SYS; self.paint(); });
  };

  Inst.prototype.setCount = function () {
    if (this.countEl) this.countEl.textContent = this.error ? "" : String(this.rows.length);
  };

  Inst.prototype.paint = function () {
    this.setCount();
    if (this.error) {
      this.body.innerHTML = '<div class="cd-err" role="alert">' + esc(this.error)
        + ' <button type="button" class="cd-link" data-cd-retry>Thử lại</button></div>';
      return;
    }
    if (!this.rows.length) {
      this.body.innerHTML = '<p class="cd-empty">Không có phiếu nào đang chờ bạn duyệt.</p>';
      return;
    }
    // Server da xep theo han (gap nhat truoc, khong han cuoi) -> nhom theo loai giu thu tu
    // xuat hien = nhom co phieu gap nhat dung dau.
    var groups = [], by = {}, now = new Date();
    this.rows.forEach(function (r) {
      var k = r.type_label || r.approval_type;
      if (!by[k]) { by[k] = []; groups.push(k); }
      by[k].push(r);
    });
    var self = this, h = [];
    groups.forEach(function (g) {
      var od = by[g].filter(function (r) { var d = dueInfo(r.due_at, now); return d && d.od; }).length;
      h.push('<div class="cd-group"><div class="cd-gh">' + esc(g) + ' <span>' + by[g].length + "</span>"
        + (od ? ' <em class="cd-gh-od">' + od + " quá hạn</em>" : "") + "</div>");
      by[g].forEach(function (r) { h.push(self.cardHTML(r, now)); });
      h.push("</div>");
    });
    this.body.innerHTML = h.join("");
  };

  // So tien: server chon san (row.amount = o Currency dau tien cua tom tat da loc luong). Chip
  // khong lap lai o do.
  function chipsOf(r) {
    var amt = r.amount;
    return (r.summary || []).filter(function (s) {
      return !(amt && s.label === amt.label && s.value === amt.value);
    });
  }
  function dueHTML(r, now) {
    var d = dueInfo(r.due_at, now);
    if (!d) return "";
    return '<b class="cd-due' + (d.od ? " cd-due-od" : "") + '">' + esc(d.text) + "</b>";
  }

  Inst.prototype.cardHTML = function (r, now) {
    var c = r.capabilities || {};
    var chips = chipsOf(r).slice(0, 3).map(function (s) {
      return '<span class="cd-chip"><i>' + esc(s.label) + "</i> " + esc(s.value) + "</span>";
    }).join("");
    var d = dueInfo(r.due_at, now);
    var meta = esc(r.requester_name || r.requested_by) + " · gửi " + fmtDate(r.submitted_at);
    var act = c.needs_input
      ? (r.detail_url ? '<a class="cd-btn" href="' + esc(r.detail_url) + '">Mở để duyệt</a>' : "")
      : (c.can_approve ? '<button type="button" class="cd-btn cd-ok" data-cd-quick="' + esc(r.request) + '">'
          + (c.sign_required ? "Duyệt &amp; Ký" : "Duyệt") + "</button>" : "");
    return '<article class="cd-card' + (d && d.od ? " cd-card-od" : "") + '" data-cd-open="' + esc(r.request)
      + '" tabindex="0" aria-label="' + esc(r.title) + (d ? " - " + esc(d.text) : "") + '">'
      + '<div class="cd-main"><div class="cd-title">' + esc(r.title) + "</div>"
      + (r.amount ? '<div class="cd-amt"><i>' + esc(r.amount.label) + "</i> " + esc(r.amount.value) + "</div>" : "")
      + '<div class="cd-meta">' + meta + "</div>"
      + (d ? '<div class="cd-dueline">' + dueHTML(r, now) + "</div>" : "")
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
    if (q) { ev.stopPropagation(); this.openSheet(this.find(q.getAttribute("data-cd-quick")), q); return; }
    if (t.closest("a")) return;            // "Mo de duyet" -> trang chi tiet
    var card = t.closest("[data-cd-open]");
    if (card) this.openSheet(this.find(card.getAttribute("data-cd-open")), card);
  };

  // ---- bang truot tu duoi len -------------------------------------------------------
  var SIGN_FILE = "/api/method/ecentric_workspace.platform.esign.api.get_package_file?dsf_name=";
  var ACT_VI = { Submitted: "Đã gửi", Approved: "Đã duyệt", Rejected: "Từ chối", "Information Requested": "Yêu cầu bổ sung",
    Resubmitted: "Gửi lại", Restarted: "Gửi lại từ đầu", Skipped: "Bỏ qua", Cancelled: "Huỷ", Reminded: "Nhắc xử lý", "Attachment Added": "Thêm tệp",
    Commented: "Ghi chú", Signed: "Đã ký", "System Transition": "Hệ thống chuyển bước", Assigned: "Giao xử lý",
    Started: "Bắt đầu xử lý", Completed: "Hoàn tất" };
  // Nut quyet dinh -> chu tren nut khi dang gui + cau xac nhan (chi buoc khong dao nguoc duoc
  // bang tay cua nguoi gui: Tu choi / Yeu cau bo sung; Duyet giu MOT cham - PO chot).
  var ACT = {
    approve: { busy: "Đang duyệt…", done: "Đã duyệt: " },
    approve_sign: { busy: "Đang gửi lệnh ký…", done: "Đã gửi lệnh ký: " },
    reject: { busy: "Đang từ chối…", done: "Đã từ chối: ", need: "Từ chối bắt buộc ghi lý do.",
      ask: "Từ chối phiếu này? Người gửi sẽ nhận lý do bạn ghi.", go: "Xác nhận từ chối" },
    request_information: { busy: "Đang gửi…", done: "Đã yêu cầu bổ sung: ", need: "Ghi rõ cần bổ sung gì.",
      ask: "Trả phiếu về người gửi để bổ sung? Họ sẽ nhận nội dung bạn ghi.", go: "Xác nhận trả về bổ sung" }
  };

  Inst.prototype.openSheet = function (r, opener) {
    if (!r) return;
    // Cham 2 lan nhanh (hoac cham nut roi cham the) tung mo 2 bang chong nhau: bang thu hai luu
    // "overflow:hidden" lam gia tri cu -> dong ca hai van khoa cuon trang. Moi luc MOT bang.
    if (this.ov && this.ov.parentNode) return;
    var self = this, c = r.capabilities || {};
    var now = new Date(), due = dueInfo(r.due_at, now);
    var ov = document.createElement("div");
    ov.className = "cd-ov";
    var rows = chipsOf(r).map(function (s) {
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
      : '<div class="cd-btnrow" data-cd-btns>' + ((c.can_approve ? (c.sign_required
            ? '<button type="button" class="cd-btn cd-ok" data-cd-do="approve_sign">Duyệt &amp; Ký</button>'
            : '<button type="button" class="cd-btn cd-ok" data-cd-do="approve">Duyệt</button>') : "")
        + (c.can_request_info ? '<button type="button" class="cd-btn" data-cd-do="request_information">Yêu cầu bổ sung</button>' : "")
        + (c.can_reject ? '<button type="button" class="cd-btn cd-no" data-cd-do="reject">Từ chối</button>' : ""))
        + "</div>"
        + '<div class="cd-confirm" data-cd-confirm hidden><p class="cd-confirm-q" data-cd-confirm-q></p>'
        + '<div class="cd-btnrow"><button type="button" class="cd-btn" data-cd-confirm-no>Quay lại</button>'
        + '<button type="button" class="cd-btn cd-no-solid" data-cd-confirm-go></button></div></div>';
    ov.innerHTML = '<div class="cd-sheet" role="dialog" aria-modal="true" tabindex="-1" aria-label="' + esc(r.title) + '">'
      + '<div class="cd-grip" aria-hidden="true"></div>'
      + '<div data-cd-pane="act">'
      + '<div class="cd-sh-head"><div><div class="cd-sh-type">' + esc(r.type_label)
      + (r.level_name ? " · Bước " + esc(r.level_name) : "") + "</div>"
      + '<div class="cd-sh-title">' + esc(r.title) + "</div>"
      + '<div class="cd-meta">' + esc(r.requester_name || r.requested_by) + " · gửi " + fmtDate(r.submitted_at) + "</div>"
      + (due ? '<div class="cd-dueline">' + dueHTML(r, now) + "</div>" : "") + "</div>"
      + '<button type="button" class="cd-x" data-cd-close aria-label="Đóng">&times;</button></div>'
      + (r.amount ? '<div class="cd-sh-amt"><span>' + esc(r.amount.label) + "</span><b>" + esc(r.amount.value) + "</b></div>" : "")
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
    this.ov = ov;
    var onKey = function (ev) { if (ev.key === "Escape" || ev.key === "Esc") close(); };
    var close = function () {
      if (ov.parentNode) ov.parentNode.removeChild(ov);
      if (ov.__unlock) { ov.__unlock(); ov.__unlock = null; }
      document.removeEventListener("keydown", onKey);
      if (self.ov === ov) self.ov = null;
      // Tra focus ve cho nguoi dung vua cham (ban phim / trinh doc man hinh khong bi lac).
      if (opener && opener.isConnected && opener.focus) { try { opener.focus({ preventScroll: true }); } catch (e) { /* cu */ } }
    };
    document.addEventListener("keydown", onKey);
    ov.addEventListener("click", function (ev) {
      var t = ev.target, at = function (q) { return t.closest && t.closest(q); };
      if (t === ov || at("[data-cd-close]")) { close(); return; }
      if (at("[data-cd-full]")) { self.showFull(r, ov); return; }
      if (at("[data-cd-back]")) { self.pane(ov, "act"); return; }
      if (at("[data-cd-confirm-no]")) { self.confirmStep(ov, null); return; }
      if (at("[data-cd-confirm-go]")) { self.decide(r, ov.__ask, ov, close, true); return; }
      var b = at("[data-cd-do]");
      if (b) self.decide(r, b.getAttribute("data-cd-do"), ov, close);
    });
    // KHONG tu focus o nhan xet (07/10, Hoan): focus la bat ban phim len, che mat phieu dang
    // doc. Focus vao KHUNG bang (tabindex=-1) - khong bat ban phim, trinh doc man hinh vao dung hop.
    var shf = ov.querySelector(".cd-sheet");
    if (shf && shf.focus) { try { shf.focus({ preventScroll: true }); } catch (e) { /* cu */ } }
    self.lockScroll(ov, close);
  };

  // Buoc xac nhan cho Tu choi / Yeu cau bo sung: an hang nut, hien cau hoi + "Quay lai" /
  // "Xac nhan ...". action = null -> ve hang nut cu.
  Inst.prototype.confirmStep = function (ov, action) {
    var row = ov.querySelector("[data-cd-btns]"), box = ov.querySelector("[data-cd-confirm]");
    ov.__ask = action;
    if (row) row.hidden = !!action;
    if (box) box.hidden = !action;
    if (action && box) {
      box.querySelector("[data-cd-confirm-q]").textContent = ACT[action].ask;
      var go = box.querySelector("[data-cd-confirm-go]");
      go.textContent = ACT[action].go;
      go.disabled = false;
    }
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
      box.innerHTML = head + '<div class="cd-err">' + esc((e && e.cd) ? e.message : MSG_SYS) + "</div>"
        + '<button type="button" class="cd-btn cd-wide cd-mt" data-cd-back>Về bước duyệt</button>';
    });
  };

  Inst.prototype.decide = function (r, action, ov, close, confirmed) {
    if (this.busy || !action || !ACT[action]) return;
    var c = r.capabilities || {};
    var ta = ov.querySelector("#cd-cmt"), msg = ov.querySelector("[data-cd-msg]");
    var cmt = ta ? (ta.value || "").trim() : "";
    var say = function (t) { if (msg) msg.textContent = t; };
    var spec = ACT[action];
    // Nguoi dung vua bam nut -> dua con tro vao o ly do la DUNG (khong phai tu focus luc mo bang).
    if (spec.need && !cmt) { this.confirmStep(ov, null); say(spec.need); if (ta) ta.focus(); return; }
    if ((action === "approve" || action === "approve_sign") && c.comment_required && !cmt) { say("Loại phiếu này bắt buộc nhập nhận xét khi duyệt."); if (ta) ta.focus(); return; }
    if (spec.ask && !confirmed) { say(""); this.confirmStep(ov, action); return; }
    var self = this, btns = ov.querySelectorAll("[data-cd-do],[data-cd-confirm-go],[data-cd-confirm-no]");
    var lead = confirmed ? ov.querySelector("[data-cd-confirm-go]") : ov.querySelector('[data-cd-do="' + action + '"]');
    var label = lead ? lead.textContent : "";
    this.busy = true;
    Array.prototype.forEach.call(btns, function (b) { b.disabled = true; });
    if (lead) { lead.textContent = spec.busy; lead.setAttribute("aria-busy", "true"); }
    if (ta) ta.readOnly = true;
    say("");
    post("quick_decide", { request_name: r.request, action: action, comment: cmt }).then(function (res) {
      self.busy = false;
      close();
      var left = res && res.remaining;
      self.removeRow(r.request, left);
      var n = left != null ? left : self.rows.length;
      self.toast(spec.done + r.title + (n > 0 ? " · còn " + n + " phiếu chờ bạn." : " · bạn đã xử lý hết phiếu chờ duyệt."));
    }).catch(function (e) {
      self.busy = false;
      Array.prototype.forEach.call(btns, function (b) { b.disabled = false; });
      if (lead) { lead.textContent = label; lead.removeAttribute("aria-busy"); }
      if (ta) ta.readOnly = false;
      say(e && e.cd ? e.message : MSG_SYS);
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
  window.EcChoDuyet = { mountAll: mountAll, _Inst: Inst, _dueInfo: dueInfo, _serverMsg: serverMsg };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountAll);
  else mountAll();
})();
