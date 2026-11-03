// Copyright (c) 2026, eCentric and contributors
//
// Hien thi dung chung cho trang phe duyet (03/11/2026, dot UX "de dung cho nhan vien").
// Mot ban duy nhat cho 31 trang form + trang hub "Tat ca yeu cau" (A65 muc 3: logic dung
// chung la asset cua app, khong chep vao tung main_section.html).
//
// Ba viec, deu CHI la hien thi - khong goi API, khong doi du lieu:
//
//  1. LICH SU: engine ghi `EC Approval Action.action` bang tieng Anh ("Attachment Added",
//     "Reminded", "System Transition"...). Moi trang co mot bang dich rieng, thieu mot nua so
//     gia tri -> nhan vien thay chu tieng Anh tho. Bang duoi day phu DU 15 option cua DocType
//     (+ vai gia tri cu/rieng form), co test khoa: them option moi ma quen dich -> test do.
//
//  2. THANH TIEN TRINH: truoc day cham tron danh so theo VI TRI (i+1), ma vi tri 1 la
//     "Da gui" -> Cap duyet 1 hien so 2, Cap 2 hien so 3... lech voi so cap engine dung o
//     moi noi khac ("Cap hien tai: 1", log, email). Da gay mot lan ho tro nham thuc te.
//     Nay: buoc nao la CAP DUYET (co `level`) thi cham hien dung so cap va ten ghi
//     "Cap N · <ten cap>"; buoc khong phai cap duyet (Da gui / Xu ly / Hoan tat) khong danh so.
//
//  3. LOI: thong diep may chu ky thuat (Traceback, NoneType, pymysql, CSRF...) khong bao gio
//     toi tay nguoi dung nguyen van; thay bang cau tieng Viet noi ro phai lam gi tiep.
//
// GIAO KEO VOI TRANG (moi trang chi them dong uy quyen, giu ban cu lam du phong):
//   function timelineHTML(items){ if(window.EcApprovalUI) return EcApprovalUI.timelineHTML(items); ... }
//   function renderStepsHTML(steps){ if(window.EcApprovalUI) return EcApprovalUI.stepsHTML(steps); ... }
//   buildStepper: steps.push({level:l.level_no, name:..., state:..., meta:...})
//   function mapErr(e){ if(window.EcApprovalUI&&EcApprovalUI.isTechnical(e)) return EcApprovalUI.errorText(e); ... }
//
// `meta` cua mot buoc la HTML do trang tu dung VA TU esc() (co the chua <span class="ov">) -
// ham nay chen nguyen van. Moi chuoi khac (ten buoc, nhan, nguoi, ghi chu) deu esc() o day.
(function () {
  "use strict";
  if (window.EcApprovalUI) return;

  function esc(s) {
    return (s == null ? "" : String(s)).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ---- 1. nhan tieng Viet ------------------------------------------------------------------
  // Khoa = option cua EC Approval Action.action (ec_approval_action.json) + vai gia tri rieng
  // form/cu con nam trong du lieu. Chu dong tu o thi qua khu ("Da ...") vi day la nhat ky.
  var ACTION = {
    "Submitted": "Đã gửi yêu cầu",
    "Approved": "Đã duyệt",
    "Rejected": "Đã từ chối",
    "Information Requested": "Yêu cầu bổ sung thông tin",
    "Resubmitted": "Đã gửi lại sau khi bổ sung",
    "Restarted": "Duyệt lại từ đầu",
    "Skipped": "Bỏ qua cấp này",
    "Cancelled": "Đã hủy yêu cầu",
    "System Transition": "Hệ thống tự chuyển bước",
    "Assigned": "Đã giao người xử lý",
    "Started": "Đã nhận xử lý",
    "Completed": "Đã xử lý xong",
    "Commented": "Ghi chú",
    "Reminded": "Đã nhắc người xử lý",
    "Attachment Added": "Đã thêm tệp đính kèm",
    // rieng form / gia tri cu
    "Amount Adjusted": "Điều chỉnh số tiền",
    "Reopened": "Mở lại",
    "Escalated": "Chuyển lên cấp trên",
    "Information Provided": "Đã bổ sung thông tin",
    "Claimed": "Đã nhận xử lý",
    "Delegated": "Ủy quyền",
    "Reassigned": "Chuyển người xử lý"
  };
  // Trang thai phieu (EC Approval Request), trang thai cap duyet, trang thai xu ly.
  var STATUS = {
    "Draft": "Nháp",
    "Pending": "Chờ duyệt",
    "In Progress": "Đang xử lý",
    "Approved": "Đã duyệt",
    "Rejected": "Đã từ chối",
    "Information Required": "Cần bổ sung",
    "Information Requested": "Cần bổ sung",
    "Cancelled": "Đã hủy",
    "Skipped": "Bỏ qua",
    "Completed": "Hoàn tất",
    "Not Started": "Chưa bắt đầu",
    "Assigned": "Chờ nhận xử lý"
  };
  // Tai khoan he thong ghi log thay may (scheduler, hook): hien "He thong" thay vi ten tai khoan.
  var SYSTEM_ACTORS = { "Administrator": 1, "Guest": 1, "System": 1 };

  function actionLabel(a) { return ACTION[a] || (a ? String(a) : "Hoạt động"); }
  function statusLabel(s) { return STATUS[s] || (s == null ? "" : String(s)); }
  function actorLabel(u) { if (!u) return ""; return SYSTEM_ACTORS[u] ? "Hệ thống" : String(u); }

  // ---- ngay gio: luon dd/mm/yyyy [HH:mm] ----------------------------------------------------
  // Doc THANG chuoi "YYYY-MM-DD[ T]HH:MM" ma may chu tra ve (gio dia phuong cua site), KHONG
  // qua new Date(): Date coi chuoi co "T" la UTC/khong ro mui gio tuy trinh duyet -> lech gio.
  function fmtDateTime(v) {
    if (v == null || v === "") return "—";
    var s = String(v);
    var m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(s);
    if (!m) return s;
    return m[3] + "/" + m[2] + "/" + m[1] + (m[4] ? (" " + m[4] + ":" + m[5]) : "");
  }
  function fmtDate(v) { var t = fmtDateTime(v); return t === "—" ? t : t.split(" ")[0]; }

  // ---- cap duyet ----------------------------------------------------------------------------
  // "Cap 1 · Truong phong duyet". Ten cap rong hoac chinh no da la "Cap 1"/"Level 1" -> chi "Cap 1".
  function levelText(levelNo, levelName, total) {
    var n = Number(levelNo);
    if (!n) return levelName ? String(levelName) : "";
    var head = "Cấp " + n + (Number(total) > 0 ? ("/" + Number(total)) : "");
    var nm = levelName ? String(levelName).trim() : "";
    if (!nm || /^(cấp|level|bước)\s*\d+$/i.test(nm)) return head;
    return head + " · " + nm;
  }

  // ---- 2. thanh tien trinh ------------------------------------------------------------------
  var STEP_LBL = { done: "Hoàn thành", current: "Đang xử lý", upcoming: "Chờ", rejected: "Từ chối",
    info: "Cần bổ sung", skipped: "Bỏ qua", cancelled: "Đã hủy" };
  var STEP_COLOR = { done: "var(--green)", current: "var(--navy)", rejected: "var(--red)",
    info: "var(--amber)", skipped: "var(--gray-400)", upcoming: "var(--gray-400)", cancelled: "var(--red)" };
  function isLevel(s) { return s && s.level != null && s.level !== "" && Number(s.level) > 0; }
  function stepDot(s) {
    if (s.state === "done") return "✓";
    if (s.state === "rejected" || s.state === "cancelled") return "✕";
    return isLevel(s) ? String(Number(s.level)) : "";
  }
  function stepName(s) {
    if (!isLevel(s)) return esc(s.name);
    var nm = s.name ? String(s.name).trim() : "";
    var lv = "Cấp " + Number(s.level);
    if (!nm || /^(cấp|level|bước)\s*\d+$/i.test(nm)) return '<span class="ec-step-lv">' + esc(lv) + "</span>";
    return '<span class="ec-step-lv">' + esc(lv) + " · </span>" + esc(nm);
  }
  // Giu nguyen khung HTML cu (.stepline/.step/.step-dot/.step-name/.step-state/.step-meta) de
  // CSS san co cua tung trang ap dung y nguyen - doi noi dung, khong doi giao dien.
  function stepsHTML(steps, opts) {
    steps = steps || []; opts = opts || {};
    var n = steps.length, k = 0;
    steps.forEach(function (s, i) { if (s.state !== "upcoming") k = i; });
    var inner = steps.map(function (s) {
      var lbl = s.statusLabel || STEP_LBL[s.state] || s.state || "";
      return '<div class="step ' + esc(s.state) + '" role="listitem"' + (s.state === "current" ? ' aria-current="step"' : "") + ">"
        + '<div class="step-top"><div class="step-dot" aria-hidden="true">' + stepDot(s) + "</div>"
        + '<div class="step-name">' + stepName(s) + "</div>"
        + '<div class="step-state" style="color:' + (STEP_COLOR[s.state] || "var(--gray-400)") + '">' + esc(lbl) + "</div></div>"
        + '<div class="step-meta">' + (s.meta || "") + "</div></div>";
    }).join("");
    return '<div class="stepline' + (opts.cancelled ? " is-cancelled" : "") + '" role="list" aria-label="Tiến trình phê duyệt" style="--n:' + n + ";--k:" + k + '">' + inner + "</div>";
  }

  // ---- lich su ------------------------------------------------------------------------------
  function timelineItemParts(a) {
    a = a || {};
    var head = actionLabel(a.action);
    var lv = a.level_no ? levelText(a.level_no, a.level_name) : "";
    var tr = (a.previous_status && a.new_status && a.previous_status !== a.new_status)
      ? (statusLabel(a.previous_status) + " → " + statusLabel(a.new_status)) : "";
    return { label: head, level: lv, actor: actorLabel(a.actor || a.user),
      when: fmtDateTime(a.action_time || a.creation || a.timestamp), transition: tr,
      comment: a.comment ? String(a.comment) : "" };
  }
  function timelineHTML(items) {
    if (!items || !items.length) return '<div class="hint">Chưa có hoạt động nào.</div>';
    return items.map(function (a) {
      var p = timelineItemParts(a);
      var meta = [p.actor, p.when !== "—" ? p.when : "", p.transition].filter(Boolean).map(esc).join(" · ");
      return '<div class="tl-item"><div class="tl-dot"></div><div>'
        + '<div class="tl-act">' + esc(p.label) + (p.level ? (" · " + esc(p.level)) : "") + "</div>"
        + '<div class="tl-meta">' + meta + "</div>"
        + (p.comment ? ('<div class="tl-cmt">' + esc(p.comment) + "</div>") : "")
        + "</div></div>";
    }).join("");
  }

  // ---- 3. loi -------------------------------------------------------------------------------
  // Lay thong diep THAT cua may chu ra khoi loi frappe.call (no nam o _server_messages chu
  // khong o e.message khi frappe.throw). Ban dung chung cho 8 ban sao extractServerMsg.
  function serverMessage(e) {
    if (!e) return "";
    function strip(s) {
      var t = String(s == null ? "" : s).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
      try { var ta = document.createElement("textarea"); ta.innerHTML = t; t = ta.value; } catch (_e) {}
      return t;
    }
    if (typeof e === "string") return strip(e);
    var sm = e._server_messages || (e.responseJSON && e.responseJSON._server_messages);
    if (sm) {
      try {
        var arr = (typeof sm === "string") ? JSON.parse(sm) : sm;
        for (var i = 0; i < arr.length; i++) {
          var f = arr[i], o = f;
          if (typeof f === "string") { try { o = JSON.parse(f); } catch (_a) { o = { message: f }; } }
          var mm = o && (o.message || o.title);
          if (mm) return strip(mm);
        }
      } catch (_b) {}
    }
    var rj = e.responseJSON || {};
    if (typeof e.message === "string" && e.message) return strip(e.message);
    if (typeof rj.message === "string" && rj.message) return strip(rj.message);
    if (rj.message && rj.message.message) return strip(rj.message.message);
    var exc = rj.exception || e.exception || "";
    if (exc) { var p = String(exc).split(": "); return strip(p.length > 1 ? p.slice(1).join(": ") : exc); }
    return "";
  }
  function httpStatus(e) {
    if (!e || typeof e !== "object") return 0;
    return Number(e.status || e.httpStatus || (e.xhr && e.xhr.status) || 0) || 0;
  }
  function excType(e) {
    if (!e || typeof e !== "object") return "";
    return String(e.exc_type || (e.responseJSON && e.responseJSON.exc_type) || "");
  }
  var MSG = {
    network: "Mất kết nối tới hệ thống. Kiểm tra mạng rồi thử lại.",
    session: "Phiên đăng nhập đã hết hạn. Tải lại trang (F5) rồi thử lại.",
    permission: "Bạn không có quyền thực hiện thao tác này. Nếu cần, liên hệ người quản lý hoặc IT.",
    timeout: "Hệ thống đang phản hồi chậm. Đợi vài giây rồi thử lại.",
    system: "Hệ thống gặp lỗi khi xử lý. Vui lòng thử lại; nếu vẫn lỗi, báo IT kèm mã phiếu."
  };
  // Dau hieu chu cua LAP TRINH VIEN, khong phai cau cho nguoi dung: ten exception Python,
  // loi SQL, stack trace, thuoc tinh/kieu. Cau tieng Viet tu frappe.throw thi KHONG khop.
  var TECH_RE = /Traceback|NoneType|AttributeError|KeyError|TypeError|ValueError|IndexError|NameError|ImportError|ModuleNotFound|has no attribute|object is not|not subscriptable|unsupported operand|pymysql|OperationalError|ProgrammingError|IntegrityError|InternalError|DataError|Duplicate entry|Deadlock|Lock wait timeout|frappe\.exceptions|File "[^"]*", line \d+|Internal Server Error|<!DOCTYPE|\bsyntax error\b|\b1062\b|\b1048\b/i;
  function kind(e) {
    var st = httpStatus(e), et = excType(e), m = serverMessage(e);
    if (/CSRFTokenError|SessionExpired/i.test(et + " " + m)) return "session";
    if (st === 0 && /Failed to fetch|NetworkError|Network request failed|ERR_NETWORK|net::/i.test(m)) return "network";
    if (st === 401) return "session";
    if (st === 504 || st === 502 || st === 503 || /Gateway Time-?out|Request Timeout|timed out/i.test(m)) return "timeout";
    if (TECH_RE.test(m)) return "system";
    if (st >= 500 && !m) return "system";
    if (st === 403 && !m) return "permission";
    return "";
  }
  function isTechnical(e) { return !!kind(e); }
  // Cau hien cho nguoi dung. Thong diep nghiep vu (tieng Viet, tu frappe.throw) giu nguyen;
  // thong diep ky thuat thay bang cau huong dan. Khong co gi -> `fallback`.
  function errorText(e, fallback) {
    var k = kind(e);
    if (k) return MSG[k];
    var m = serverMessage(e);
    if (m) return m.length > 300 ? (m.slice(0, 297) + "…") : m;
    return fallback || "Không thực hiện được. Vui lòng thử lại.";
  }

  window.EcApprovalUI = {
    actionLabel: actionLabel, statusLabel: statusLabel, actorLabel: actorLabel,
    fmtDateTime: fmtDateTime, fmtDate: fmtDate, levelText: levelText,
    stepsHTML: stepsHTML, timelineHTML: timelineHTML, timelineItemParts: timelineItemParts,
    serverMessage: serverMessage, errorText: errorText, isTechnical: isTechnical,
    ACTION_LABELS: ACTION, STATUS_LABELS: STATUS
  };
})();
