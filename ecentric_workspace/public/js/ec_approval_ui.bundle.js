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
//   function renderStepsHTML(steps,det){ if(window.EcApprovalUI) return EcApprovalUI.stepsHTML(withJourney(...),{detail:det}); ... }
//   (det: chi truyen tu buildStepper/buildDraftStepper - det cua chinh phieu dang ve; 24/11 Tien trinh A)
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
    "Approval Linked": "Đã gắn phiếu duyệt",
    "Approval Unlinked": "Đã gỡ phiếu duyệt",
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

  // ---- 2. thanh tien trinh -----------------------------------------------------------------
  // Phuong an A (24/11/2026, PO Hoan chot "Tien trinh phe duyet A ok" - mockup
  // APPROVAL_STEPPER_MOCKUP_2026-11-24.html): stepper ngang gon + bang "Viec cua ban" phia tren.
  //  * Bang: chi ve khi trang truyen opts.detail (det cua get_detail) co det.viewer do SERVER tinh
  //    (shared/requests/viewer_task.py). Nut Duyet / Tra lai / Chinh sua & gui lai KHONG goi API:
  //    chung bam ho dung nut [data-act] san co cua trang (cung modal, cung kiem tra, cung loading).
  //    "Mo viec cua toi" cuon toi nut Nhan / Hoan tat xu ly cua trang.
  //  * Pha chua dien ra / da xong gom thanh 1 nut mo duoc; toi da MAX_COLS cot; moi cot co dinh 3
  //    dong (ten, trang thai, nguoi/gio). Mo ta dai vao tooltip (va hien trong danh sach o ban hep).
  //  * Khung <= 600px (container query tren .ec-aps): thanh doan mau + "Buoc x/y" + danh sach doc.
  //  * Trang thai ban dau nam san trong markup (A65): panel nhom co `hidden`, ban hep / ban rong do
  //    CSS chon - JS khong an / hien gi luc tai.
  // Cap duyet: cham hien DUNG so cap engine, ten "Cap N · <ten>" (03/11, khong doi).
  var STEP_LBL = { done: "Hoàn thành", current: "Đang xử lý", upcoming: "Chờ", rejected: "Từ chối",
    info: "Cần bổ sung", skipped: "Bỏ qua", cancelled: "Đã hủy" };
  var MAX_COLS = 6;
  var SVG = {
    check: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    dash: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M4.5 8h7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    clock: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 5v3.2l2 1.3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    me: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="8" cy="5.4" r="2.6" fill="currentColor"/><path d="M3.2 13.6c.6-2.6 2.5-4.1 4.8-4.1s4.2 1.5 4.8 4.1z" fill="currentColor"/></svg>',
    dot: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="8" cy="8" r="2.4" fill="currentColor"/></svg>',
    x: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M5 5l6 6M11 5l-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    chev: '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    layers: '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M8 2.5l5.5 3L8 8.5 2.5 5.5zM2.5 8.4L8 11.4l5.5-3M2.5 11L8 14l5.5-3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
    eye: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>'
  };
  var _seq = 0;
  function isLevel(s) { return s && s.level != null && s.level !== "" && Number(s.level) > 0; }
  function isDoneLike(s) { return s.state === "done" || s.state === "skipped"; }
  function isMine(s) { return !!(s.mine && s.state === "current"); }
  function tone(s) { return isMine(s) ? "mine" : (s.state || "upcoming"); }
  function stepName(s) {
    if (!isLevel(s)) return esc(s.name);
    var nm = s.name ? String(s.name).trim() : "";
    var lv = "Cấp " + Number(s.level);
    if (!nm || /^(cấp|level|bước)\s*\d+$/i.test(nm)) return '<span class="ec-step-lv">' + esc(lv) + "</span>";
    return '<span class="ec-step-lv">' + esc(lv) + " · </span>" + esc(nm);
  }
  function stepNameText(s) {
    if (!isLevel(s)) return String(s.name == null ? "" : s.name);
    var nm = s.name ? String(s.name).trim() : "";
    var lv = "Cấp " + Number(s.level);
    return (!nm || /^(cấp|level|bước)\s*\d+$/i.test(nm)) ? lv : (lv + " · " + nm);
  }
  // `meta` la HTML trang da esc -> bo the cho thuoc tinh title (thuc the giu nguyen, chi va dau ").
  function metaTitle(html) { return String(html || "").replace(/<[^>]*>/g, "").replace(/"/g, "&quot;").trim(); }
  function nodeInner(s) {
    if (s.group) return (s.state === "done" ? SVG.check : SVG.layers) + '<span class="ec-aps-count">' + Number(s.count || 0) + "</span>";
    if (s.state === "done") return SVG.check;
    if (s.state === "rejected" || s.state === "cancelled") return SVG.x;
    if (s.state === "skipped") return SVG.dash;
    if (isMine(s)) return SVG.me;
    if (isLevel(s)) return '<span class="ec-aps-num">' + Number(s.level) + "</span>";
    if (s.state === "current") return SVG.clock;
    if (s.state === "info") return '<span class="ec-aps-num">!</span>';
    return SVG.dot;
  }
  function nodeHTML(s, small) {
    var cls = "ec-aps-node ec-aps-node--" + esc(s.state || "upcoming") + (isMine(s) ? " ec-aps-node--mine" : "")
      + (s.after ? " ec-aps-node--after" : "") + (small ? " ec-aps-node--sm" : "");
    return '<span class="' + cls + '" aria-hidden="true">' + nodeInner(s) + "</span>";
  }
  // Nhan trang thai: buoc cua ban noi ro "Cho ban ..."; cap duyet dang cho / chua toi noi bang loi (mockup A).
  function labelOf(s) {
    if (isMine(s)) return isLevel(s) ? "Chờ bạn duyệt" : "Chờ bạn xử lý";
    if (s.statusLabel) return s.statusLabel;
    if (isLevel(s) && s.state === "current") return "Chờ duyệt";
    if (isLevel(s) && s.state === "upcoming") return "Chưa tới";
    return STEP_LBL[s.state] || s.state || "";
  }
  // Buoc sau duyet tu withJourney: mo ta nam o `desc` (tooltip), khong lap lai o dong meta.
  function metaOf(s) { return (s.desc && s.meta === esc(s.desc)) ? "" : (s.meta || ""); }
  function tipHTML(text, end) {
    return '<span class="ec-aps-tip' + (end ? " ec-aps-tip--end" : "") + '"><button type="button" class="ec-aps-tip-btn" aria-label="Diễn giải: '
      + esc(text) + '">i</button><span class="ec-aps-tip-pop" role="tooltip">' + esc(text) + "</span></span>";
  }
  var ME_BADGE = '<span class="ec-aps-me">Bạn</span>';
  function waitText(sec) {
    sec = Number(sec);
    if (!(sec >= 0) || sec === Infinity) return "";
    var m = Math.floor(sec / 60);
    if (m < 1) return "vừa xong";
    if (m < 60) return m + " phút";
    var h = Math.floor(m / 60);
    if (h < 48) return h + " giờ";
    return Math.floor(h / 24) + " ngày";
  }
  function fmtShort(v) { var t = fmtDateTime(v); var m = /^(\d{2}\/\d{2})\/\d{4}(.*)$/.exec(t); return m ? (m[1] + m[2]) : t; }
  function waitChip(s) { return s.wait ? ' <span class="ec-aps-wait">chờ ' + esc(s.wait) + "</span>" : ""; }

  // ---- viec cua nguoi dang xem (det.viewer do server tinh) ----
  function applyViewer(steps, det) {
    var v = (det && det.viewer) || null;
    var mineLv = {};
    ((det && det.levels) || []).forEach(function (l) { if (l && l.mine) mineLv[Number(l.level_no)] = true; });
    var label = v && v.step_label ? _norm(v.step_label) : "";
    var wait = v && v.waiting_seconds != null ? waitText(v.waiting_seconds) : "";
    var waitDone = false;
    return steps.map(function (s) {
      var c = Object.assign({}, s);
      var lvMine = isLevel(s) && mineLv[Number(s.level)];
      var ffMine = !!(v && v.kind === "fulfill" && label && _norm(s.name) === label);
      c.mine = !!(s.mine || lvMine || ffMine);
      if (wait && !waitDone && c.state === "current" && v && (
          (v.level_no && isLevel(s) && Number(s.level) === Number(v.level_no)) || (label && _norm(s.name) === label))) {
        c.wait = wait; waitDone = true;
      }
      return c;
    });
  }
  var ROLE_SUB = {
    requester: "Bạn là người gửi phiếu, không có việc cần làm. Hệ thống sẽ báo khi có kết quả.",
    approver: "Bạn không có việc ở bước này. Hệ thống sẽ báo khi tới lượt bạn hoặc khi có kết quả.",
    follower: "Bạn được thêm vào theo dõi phiếu này, không có việc cần làm.",
    fulfiller: "Bạn không có việc cần làm lúc này."
  };
  // opts.approveMode "open": trang co luong rieng o tung cap (vd Danh gia nhan su: tu danh gia / quan ly gui CEO)
  // -> bang khong dat nut Duyet / Tra lai chung, chi "Mo viec cua toi" dua toi khoi Hanh dong cua trang.
  function youModel(det, opts) {
    var v = det && det.viewer;
    opts = opts || {};
    if (!v || !v.kind) return null;
    var caps = det.capabilities || {};
    var lvl = v.level_no ? levelText(v.level_no, v.level_name) : "";
    var wait = v.waiting_seconds != null ? waitText(v.waiting_seconds) : "";
    var since = v.waiting_since ? fmtShort(v.waiting_since) : "";
    var due = v.due_at ? fmtDateTime(v.due_at) : "";
    var sub = [];
    if (v.kind === "approve" && opts.approveMode === "open") {
      if (wait) sub.push("Phiếu chờ bạn " + wait + (since ? " (từ " + since + ")" : ""));
      if (due) sub.push("Hạn " + due);
      if (!sub.length) sub.push("Phiếu đang chờ bạn xử lý");
      return { mine: true, kicker: "Việc của bạn", title: "Đến lượt bạn: " + (lvl || "phiếu này"), sub: sub.join(". ") + ".",
        acts: [{ act: "panel", label: "Mở việc của tôi", kind: "primary", title: "Tới phần Hành động của phiếu" }] };
    }
    if (v.kind === "approve") {
      var acts = [];
      if (caps.can_request_information) acts.push({ act: "reqinfo", label: "Trả lại", kind: "danger", title: "Trả lại người gửi để bổ sung hoặc điều chỉnh" });
      if (caps.can_approve) acts.push({ act: "approve", label: caps.requires_signature ? "Duyệt & Ký" : "Duyệt", kind: "primary", title: "Duyệt " + (lvl || "phiếu này") });
      if (wait) sub.push("Phiếu chờ bạn " + wait + (since ? " (từ " + since + ")" : ""));
      if (due) sub.push("Hạn " + due);
      sub.push(v.next_level_no ? ("Sau bạn: " + levelText(v.next_level_no, v.next_level_name)) : "Bạn là cấp duyệt cuối");
      return { mine: true, kicker: "Việc của bạn", title: "Duyệt " + (lvl || "phiếu này"), sub: sub.join(". ") + ".", acts: acts };
    }
    if (v.kind === "resubmit") {
      return { mine: true, kicker: "Việc của bạn", title: "Bổ sung thông tin và gửi lại",
        sub: (lvl ? lvl + " đã trả lại phiếu để bạn bổ sung." : "Phiếu được trả lại để bạn bổ sung.") + " Sửa xong bấm gửi lại để phiếu duyệt tiếp.",
        acts: [{ act: "edit", label: "Chỉnh sửa & gửi lại", kind: "primary", title: "Mở phiếu để chỉnh sửa và gửi lại" }] };
    }
    if (v.kind === "fulfill") {
      if (due) sub.push("Hạn " + due);
      if (wait) sub.push("Phiếu đã duyệt, chờ xử lý " + wait + (since ? " (từ " + since + ")" : ""));
      if (!sub.length) sub.push("Phiếu đã duyệt xong, đang chờ bạn xử lý");
      return { mine: true, kicker: "Việc của bạn", title: (v.claimable ? "Nhận việc: " : "") + String(v.step_label || "Xử lý sau duyệt"),
        sub: sub.join(". ") + ".", acts: [{ act: "open", label: "Mở việc của tôi", kind: "primary", title: "Tới phần xử lý trên phiếu này" }] };
    }
    if (v.kind === "watch") {
      var names = (v.waiting_on || []).filter(Boolean).join(", ");
      var st = ((det.approval || {}).approval_status) || "";
      var title;
      if (st === "Information Required") title = "Đang chờ " + (names || "người gửi") + " bổ sung thông tin";
      else if (v.step_label) title = "Đang chờ " + (names || "người xử lý") + " · " + v.step_label;
      else title = "Đang chờ " + (names || "người duyệt") + (lvl ? " (" + lvl + ")" : "") + " duyệt";
      if (wait) title += " · " + wait;
      return { mine: false, kicker: "Bạn đang theo dõi", title: title,
        sub: ROLE_SUB[v.role] || "Bạn không có việc cần làm ở phiếu này.", acts: [] };
    }
    return null;
  }
  function youHTML(m) {
    if (!m) return "";
    var btns = m.acts.map(function (a) {
      return '<button type="button" class="ec-aps-btn' + (a.kind ? " ec-aps-btn--" + a.kind : "") + '" data-ec-aps-act="' + esc(a.act)
        + '" title="' + esc(a.title || a.label) + '">' + esc(a.label) + "</button>";
    }).join("");
    return '<div class="ec-aps-you' + (m.mine ? "" : " ec-aps-you--watch") + '" role="region" aria-label="' + esc(m.kicker) + '">'
      + '<span class="ec-aps-you-ico" aria-hidden="true">' + (m.mine ? SVG.me : SVG.eye) + "</span>"
      + '<div class="ec-aps-you-body"><div class="ec-aps-you-kicker">' + esc(m.kicker) + '</div><div class="ec-aps-you-title">' + esc(m.title)
      + '</div><div class="ec-aps-you-sub">' + esc(m.sub) + '</div><div class="ec-aps-you-note" role="status" hidden></div></div>'
      + (btns ? '<div class="ec-aps-you-acts">' + btns + "</div>" : "") + "</div>";
  }

  // ---- gom pha ----
  function groupOf(kind, list) {
    var st = list.every(isDoneLike) ? "done"
      : (list.some(function (s) { return s.state === "current" || s.state === "info"; }) ? "current" : "upcoming");
    var lv = list.filter(function (s) { return isLevel(s) && s.state !== "skipped"; });
    var g = { group: kind, id: "ec-aps-g" + (++_seq), steps: list, state: st, count: list.length, meta: "" };
    if (kind === "approve") {
      g.name = "Phê duyệt"; g.count = lv.length || list.length;
      g.statusLabel = st === "done" ? ("Đã duyệt " + lv.length + "/" + lv.length + " cấp") : "Đang duyệt";
      var last = lv.length ? lv[lv.length - 1] : null;
      g.meta = last ? metaOf(last) : "";
    } else if (kind === "after") {
      g.name = "Sau duyệt · " + list.length + " bước"; g.after = true;
      g.statusLabel = st === "upcoming" ? "Chưa bắt đầu" : labelOf(st === "done" ? { state: "done" } : { state: "current" });
      g.meta = "Tự chạy khi duyệt xong";
    } else if (kind === "done") {
      g.name = "Đã xong · " + list.length + " bước"; g.statusLabel = "Hoàn thành";
    } else {
      g.name = "Còn " + list.length + " bước"; g.statusLabel = "Chưa tới"; g.after = !!list[list.length - 1].after;
    }
    return g;
  }
  function flat(items) {
    var out = [];
    items.forEach(function (it) { if (it.group) out = out.concat(it.steps); else out.push(it); });
    return out;
  }
  function buildItems(steps) {
    var fa = -1;
    for (var i = 0; i < steps.length; i++) { if (steps[i].after) { fa = i; break; } }
    var items;
    if (fa <= 0) items = steps.slice();
    else {
      var p1 = steps.slice(0, fa), p2 = steps.slice(fa);
      items = p1.every(isDoneLike) ? [groupOf("approve", p1)].concat(p2) : p1.concat([groupOf("after", p2)]);
    }
    if (items.length > MAX_COLS) {
      var run = 0;
      while (run < items.length - 1 && !items[run].group && isDoneLike(items[run])) run++;
      if (run >= 2) items = [groupOf("done", items.slice(0, run))].concat(items.slice(run));
    }
    if (items.length > MAX_COLS) {
      items = items.slice(0, MAX_COLS - 1).concat([groupOf("rest", flat(items.slice(MAX_COLS - 1)))]);
    }
    return items;
  }
  function colOf(it) {
    // 24/11 (Hoan): can giua -> cac cot BANG NHAU de net noi tam-toi-tam thang hang.
    return it.group ? "minmax(120px,1fr)" : "minmax(0,1fr)";
  }
  function itemHTML(it, i, items) {
    var next = items[i + 1];
    var cls = ["ec-aps-item", "ec-aps-item--" + esc(it.state || "upcoming")];
    if (isMine(it)) cls.push("ec-aps-item--mine");
    if (it.after) cls.push("ec-aps-item--after");
    if (it.group) cls.push("ec-aps-item--group");
    if (!next) cls.push("ec-aps-item--last");
    else if (isDoneLike(it) && next.state !== "upcoming") cls.push("ec-aps-item--link-done");
    if (next && next.after) cls.push("ec-aps-item--link-after");
    var end = i >= items.length - 2;
    var head = '<div class="' + cls.join(" ") + '" role="listitem"' + (it.state === "current" && !it.group ? ' aria-current="step"' : "") + ">";
    if (it.group) {
      var tg = ' data-ec-aps-toggle="' + it.id + '" aria-expanded="false" aria-controls="' + it.id + '"';
      return head + '<div class="ec-aps-rail"><button type="button" class="ec-aps-node ec-aps-node--group ec-aps-node--' + esc(it.state) + (it.after ? " ec-aps-node--after" : "")
        + '"' + tg + ' aria-label="Mở nhóm ' + esc(it.name) + '">' + nodeInner(it) + '</button><span class="ec-aps-line" aria-hidden="true"></span></div>'
        + '<div class="ec-aps-text"><button type="button" class="ec-aps-gbtn"' + tg + '><span class="ec-aps-name">' + esc(it.name) + "</span>" + SVG.chev + "</button>"
        + '<div class="ec-aps-status ec-aps-tx--' + esc(it.state) + '">' + esc(it.statusLabel) + "</div>"
        + '<div class="ec-aps-meta" title="' + metaTitle(it.meta) + '">' + (it.meta || "") + "</div></div></div>";
    }
    var meta = metaOf(it);
    return head + '<div class="ec-aps-rail">' + nodeHTML(it) + '<span class="ec-aps-line" aria-hidden="true"></span></div>'
      + '<div class="ec-aps-text"><div class="ec-aps-name" title="' + esc(stepNameText(it)) + '">' + stepName(it) + "</div>"
      + '<div class="ec-aps-status ec-aps-tx--' + tone(it) + '"><span class="ec-aps-lbl">' + esc(labelOf(it)) + "</span>" + (isMine(it) ? ME_BADGE : "")
      + (it.desc ? tipHTML(it.desc, end) : "") + "</div>"
      + '<div class="ec-aps-meta" title="' + metaTitle(meta) + '">' + meta + waitChip(it) + "</div></div></div>";
  }
  function panelHTML(g) {
    return '<div class="ec-aps-panel" id="' + g.id + '" hidden>' + g.steps.map(function (s) {
      var meta = metaOf(s);
      return '<div class="ec-aps-mini">' + nodeHTML(s, true) + '<div class="ec-aps-mini-body">'
        + '<div class="ec-aps-name" title="' + esc(stepNameText(s)) + '">' + stepName(s) + "</div>"
        + '<div class="ec-aps-status ec-aps-tx--' + tone(s) + '">' + esc(labelOf(s)) + (isMine(s) ? ME_BADGE : "") + "</div>"
        + (meta ? '<div class="ec-aps-meta ec-aps-meta--wrap">' + meta + "</div>" : "")
        + (s.desc ? '<div class="ec-aps-desc">' + esc(s.desc) + "</div>" : "") + "</div></div>";
    }).join("") + "</div>";
  }
  function currentOf(steps) {
    for (var i = 0; i < steps.length; i++) { if (/^(current|info|rejected|cancelled)$/.test(steps[i].state)) return i; }
    for (var j = steps.length - 1; j >= 0; j--) { if (steps[j].state === "done") return j; }
    return 0;
  }
  function vlistHTML(steps) {
    var h = '<ol class="ec-aps-vlist">', shown = false;
    steps.forEach(function (s, i) {
      if (s.after && !shown && i > 0) { h += '</ol><div class="ec-aps-vsec">Sau khi duyệt</div><ol class="ec-aps-vlist">'; shown = true; }
      var meta = metaOf(s);
      h += '<li class="ec-aps-vrow ec-aps-vrow--' + esc(s.state || "upcoming") + (s.after ? " ec-aps-vrow--after" : "") + '">' + nodeHTML(s, true)
        + '<div class="ec-aps-vrow-body"><div class="ec-aps-vrow-l1"><span class="ec-aps-vrow-name">' + stepName(s) + "</span>"
        + '<span class="ec-aps-pill ec-aps-pill--' + tone(s) + '">' + esc(labelOf(s)) + "</span></div>"
        + (meta || s.wait ? '<div class="ec-aps-vrow-meta">' + meta + waitChip(s) + "</div>" : "")
        + (s.desc ? '<div class="ec-aps-desc">' + esc(s.desc) + "</div>" : "") + "</div></li>";
    });
    return h + "</ol>";
  }
  function compactHTML(steps) {
    if (!steps.length) return "";
    var ci = currentOf(steps), c = steps[ci];
    var seg = steps.map(function (s, i) {
      var gap = s.after && i > 0 && !steps[i - 1].after ? '<span class="ec-aps-seg ec-aps-seg--gap"></span>' : "";
      return gap + '<span class="ec-aps-seg ec-aps-seg--' + tone(s) + '"></span>';
    }).join("");
    return '<div class="ec-aps-compact"><div class="ec-aps-segbar" aria-hidden="true">' + seg + "</div>"
      + '<div class="ec-aps-now">' + nodeHTML(c) + '<div class="ec-aps-now-body">'
      + '<div class="ec-aps-now-k">Bước ' + (ci + 1) + "/" + steps.length + " · " + (c.after ? "Sau khi duyệt" : "Phê duyệt") + "</div>"
      + '<div class="ec-aps-now-name">' + stepName(c) + "</div>"
      + '<div class="ec-aps-status ec-aps-tx--' + tone(c) + '">' + esc(labelOf(c)) + (isMine(c) ? ME_BADGE : "") + "</div>"
      + (metaOf(c) || c.wait ? '<div class="ec-aps-meta ec-aps-meta--wrap">' + metaOf(c) + waitChip(c) + "</div>" : "")
      + "</div></div>"
      + '<details class="ec-aps-more"><summary>Xem toàn bộ tiến trình · ' + steps.length + " bước " + SVG.chev + "</summary>" + vlistHTML(steps) + "</details></div>";
  }
  // opts.cancelled: phieu da huy (giu class is-cancelled). opts.detail: det cua get_detail -> bang
  // "Viec cua ban" + co mine. Khong co detail (xem truoc luc tao, hub) -> chi ve stepper.
  // opts.approveMode: "open" -> xem youModel.
  function stepsHTML(steps, opts) {
    opts = opts || {};
    var det = opts.detail || null;
    steps = applyViewer(steps || [], det);
    var items = buildItems(steps);
    var track = items.length ? ('<div class="ec-aps-track" role="list" aria-label="Tiến trình phê duyệt" style="grid-template-columns:'
      + items.map(colOf).join(" ") + '">' + items.map(function (it, i) { return itemHTML(it, i, items); }).join("") + "</div>") : "";
    var panels = items.filter(function (it) { return it.group; }).map(panelHTML).join("");
    return '<div class="ec-aps' + (opts.cancelled ? " is-cancelled" : "") + '" data-ec-aps="1">'
      + youHTML(det ? youModel(det, opts) : null) + track + panels + compactHTML(steps) + "</div>";
  }

  // Bam vao bang / nut nhom: mot listener uy quyen cho moi stepper tren trang.
  var TARGETS = {
    approve: ['[data-act="approvesign"]', '[data-act="approve"]'],
    reqinfo: ['[data-act="reqinfo"]'],
    edit: ['[data-act="edit"]'],
    open: ['[data-act="complete"]', '[data-act="claim"]', '[id$="-complete"]', '[id$="-claim"]'],
    panel: ['.actions [data-act]']
  };
  function findTarget(act, from) {
    var scope = (from.closest && from.closest('[id$="-root"]')) || from.ownerDocument || document;
    var sels = TARGETS[act] || [];
    for (var i = 0; i < sels.length; i++) {
      var list = scope.querySelectorAll(sels[i]);
      for (var j = 0; j < list.length; j++) {
        var el = list[j];
        if (!el.closest(".ec-aps") && !el.disabled) return el;
      }
    }
    return null;
  }
  function toggleGroup(btn) {
    var id = btn.getAttribute("data-ec-aps-toggle");
    var root = btn.closest(".ec-aps");
    if (!root || !id) return;
    var panel = root.querySelector("#" + id);
    if (!panel) return;
    var open = panel.hidden;
    Array.prototype.forEach.call(root.querySelectorAll(".ec-aps-panel"), function (p) { if (p !== panel) p.hidden = true; });
    Array.prototype.forEach.call(root.querySelectorAll("[data-ec-aps-toggle]"), function (b) {
      var mine = b.getAttribute("data-ec-aps-toggle") === id;
      b.setAttribute("aria-expanded", mine && open ? "true" : "false");
    });
    panel.hidden = !open;
  }
  function onStepperClick(e) {
    var t = e.target;
    if (!t || !t.closest) return;
    var tg = t.closest("[data-ec-aps-toggle]");
    if (tg) { e.preventDefault(); toggleGroup(tg); return; }
    var b = t.closest("[data-ec-aps-act]");
    if (!b) return;
    e.preventDefault();
    var act = b.getAttribute("data-ec-aps-act");
    var el = findTarget(act, b);
    var box = b.closest(".ec-aps-you"), note = box && box.querySelector(".ec-aps-you-note");
    if (!el) {
      if (note) { note.hidden = false; note.textContent = "Không tìm thấy nút tương ứng trên trang. Kéo xuống phần Hành động để thao tác."; }
      return;
    }
    if (note) note.hidden = true;
    if (act === "open" || act === "panel") {
      try { el.scrollIntoView({ block: "center", behavior: "smooth" }); } catch (_s) {}
      try { el.focus({ preventScroll: true }); } catch (_f) {}
      return;
    }
    el.click();
  }
  if (typeof document !== "undefined" && document.addEventListener) document.addEventListener("click", onStepperClick);

  // ---- quy trinh A-Z (24/11/2026) ----------------------------------------------------------
  // Hoan: "show full quy trinh tu A-Z thay vi toi khi CEO review xong moi co buoc tiep". Trang
  // van tu dung cac buoc duyet (ten + trang thai that); ham nay CHEN cac buoc sau duyet do server
  // khai (ApprovalDefinition.journey_after -> get_bootstrap / get_detail "journey_after"):
  //   [Tao] -> cap duyet ... -> viec cua chinh phieu (fulfillment / auto) -> Hoan tat -> phieu / viec
  //   tiep theo (form / info, nhan "Tiep theo").
  // Buoc trung ten voi buoc trang da ve (vd "Finance xu ly UNC" co trang thai that) -> giu cua trang.
  // Phieu bi tu choi / da huy -> giu nguyen (khong ve tiep).
  var DONE_RE = /^Ho\u00e0n t\u1ea5t/i;
  function _norm(t) { return String(t || "").trim().toLowerCase(); }
  function withJourney(steps, journey) {
    steps = (steps || []).slice();
    journey = journey || [];
    if (!journey.length) return steps;
    if (steps.some(function (s) { return s.state === "rejected" || s.state === "cancelled"; })) return steps;
    var hi = -1;
    for (var i = steps.length - 1; i >= 0; i--) { if (DONE_RE.test(String(steps[i].name || ""))) { hi = i; break; } }
    var hoan = hi >= 0 ? steps.splice(hi, 1)[0] : null;
    var names = {};
    steps.forEach(function (s) { names[_norm(s.name)] = true; });
    var levels = steps.filter(isLevel);
    var approved = (hoan && hoan.state === "done")
      || (levels.length > 0 && levels.every(function (s) { return s.state === "done" || s.state === "skipped"; }));
    var own = [], next = [];
    journey.forEach(function (j) {
      if (!j || !j.label || names[_norm(j.label)]) return;
      (j.kind === "fulfillment" || j.kind === "auto" ? own : next).push(j);
    });
    var pending = false;
    own.forEach(function (j) {
      var st = "upcoming", lbl = "Sau duyệt";
      if (approved && j.kind === "auto") { st = "done"; lbl = "Hệ thống tự làm"; }
      else if (approved) { st = "current"; lbl = "Chờ nhận việc"; pending = true; }
      steps.push({ name: j.label, state: st, statusLabel: lbl, meta: esc(j.meta || ""), desc: j.meta || "", after: true });
    });
    steps.forEach(function (s) { if (s.state === "current" && !isLevel(s) && approved) pending = true; });
    if (!hoan) hoan = { name: "Hoàn tất", state: "upcoming", meta: "" };
    hoan = Object.assign({}, hoan);
    if (!approved || pending) { hoan.state = "upcoming"; delete hoan.statusLabel; }
    else if (approved) hoan.state = "done";
    steps.push(hoan);
    next.forEach(function (j) {
      steps.push({ name: j.label, state: "upcoming", statusLabel: "Tiếp theo", meta: esc(j.meta || ""), desc: j.meta || "", after: true });
    });
    return steps;
  }

  // ---- lich su ------------------------------------------------------------------------------
  // "Duyet thay" (admin_override_current_level) ghi 2 dong: Skipped (bo luot nguoi duyet cua cap) + Approved.
  // Comment may la tieng Anh co dinh trong transitions.py -> doi sang nhan dung nghia (QC 18/11: dong Skipped
  // hien "Bo qua cap nay" lam tuong cap bi bo qua).
  var OVERRIDE_SKIP = "Admin override approved by ", OVERRIDE_OK = "Admin override approve. Reason: ";
  function overrideParts(a) {
    var c = a.comment ? String(a.comment) : "";
    if (a.action === "Skipped" && c.indexOf(OVERRIDE_SKIP) === 0)
      return { head: "Duyệt thay: bỏ lượt người duyệt", comment: a.related_user ? ("Lượt của " + a.related_user) : "" };
    if (a.action === "Approved" && c.indexOf(OVERRIDE_OK) === 0)
      return { head: "Đã duyệt thay", comment: "Lý do: " + c.slice(OVERRIDE_OK.length) };
    return null;
  }
  function timelineItemParts(a) {
    a = a || {};
    var ov = overrideParts(a);
    var head = ov ? ov.head : actionLabel(a.action);
    var lv = a.level_no ? levelText(a.level_no, a.level_name) : "";
    var tr = (a.previous_status && a.new_status && a.previous_status !== a.new_status)
      ? (statusLabel(a.previous_status) + " → " + statusLabel(a.new_status)) : "";
    return { label: head, level: lv, actor: actorLabel(a.actor || a.user),
      when: fmtDateTime(a.action_time || a.creation || a.timestamp), transition: tr,
      comment: ov ? ov.comment : (a.comment ? String(a.comment) : "") };
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
    stepsHTML: stepsHTML, withJourney: withJourney, viewerBanner: youModel, waitText: waitText, timelineHTML: timelineHTML, timelineItemParts: timelineItemParts,
    serverMessage: serverMessage, errorText: errorText, isTechnical: isTechnical,
    ACTION_LABELS: ACTION, STATUS_LABELS: STATUS
  };
})();
