// Copyright (c) 2026, eCentric and contributors
// ec_ky_luat.js - trang /ky-luat va /ky-luat/quyet-dinh (hr/ky_luat). Nap RIENG tren 2 trang nay
// (hr/ky_luat/pages.py), khong vao web_include_js.
//
// KHONG CO LUAT NGHIEP VU O DAY. Server (hr/ky_luat/application/*) kiem quyen, thoi hieu, ngay
// hop, hinh thuc - JS chi: loc bang da ve san, mo popup chi tiet (GET), dien form, tai tep
// (upload_file rieng tu), gui POST, hien loi server tra ve. An / hien o theo the / hinh thuc chi
// la tien nghi hien thi; server van tu choi gia tri sai.
(function () {
  "use strict";
  if (window.EcKyLuat) return;
  var NS = "ecentric_workspace.hr.ky_luat.controllers.api.";
  var DEC_NS = "ecentric_workspace.approval_center.api.discipline_decision.";
  var ESIGN = "ecentric_workspace.platform.esign.api.";
  var BOOT = {};
  var state = { current: null, step: null };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function dmy(v) { var s = String(v || ""); return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(8, 10) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4) + s.slice(10, 16) : (s || "—"); }

  function toast(msg, isErr) {
    var t = $("[data-ekl-toast]"); if (!t) return;
    t.textContent = msg; t.hidden = false; t.className = "ekl-toast" + (isErr ? " is-err" : "");
    clearTimeout(t._h); t._h = setTimeout(function () { t.hidden = true; }, 3500);
  }

  function serverMsg(e) {
    try {
      var sm = e && e.body && e.body._server_messages;
      if (sm) { var arr = JSON.parse(sm); var m = JSON.parse(arr[0]); return String(m.message || m).replace(/<[^>]+>/g, ""); }
    } catch (x) { /* bo qua */ }
    if (e && e.csrf) return "Phiên đăng nhập đã đổi - tải lại trang (Ctrl+Shift+R).";
    return "Không kết nối được máy chủ. Thử lại sau.";
  }

  // Envelope cua module: {success, message, data}. Loi -> Error co .errors (theo truong).
  async function api(method, args, isGet) {
    var api_ = window.ecApi;
    if (!api_) throw new Error("Thiếu ec_api - tải lại trang (Ctrl+Shift+R).");
    var res;
    try { res = isGet ? await api_.get(NS + method, args) : await api_.post(NS + method, args); }
    catch (e) { throw new Error(serverMsg(e)); }
    if (!res || !res.success) {
      var err = new Error((res && res.message) || "Không thực hiện được.");
      err.errors = (res && res.data && res.data.errors) || null;
      throw err;
    }
    return res.data;
  }

  async function upload(file) {
    var tok = window.ecApi ? await window.ecApi.csrfToken(false) : "";
    var fd = new FormData();
    fd.append("file", file, file.name);
    fd.append("is_private", "1");
    var r = await fetch("/api/method/upload_file", { method: "POST", credentials: "same-origin",
      headers: { "X-Frappe-CSRF-Token": tok }, body: fd });
    if (r.status === 413) throw new Error("Tệp quá lớn để tải lên.");
    var j = await r.json().catch(function () { return {}; });
    var url = j && j.message && j.message.file_url;
    if (!r.ok || !url) throw new Error("Không tải được tệp lên. Thử lại sau.");
    return url;
  }

  // ------------------------------------------------------------------ bang + loc --
  function applyFilter() {
    var q = ($("[data-ekl-q]") || {}).value || "";
    var mine = ($("[data-ekl-mine]") || {}).checked;
    q = q.trim().toLowerCase();
    var shown = 0;
    $all("[data-ekl-rows] tr").forEach(function (tr) {
      var ok = (!q || (tr.getAttribute("data-search") || "").indexOf(q) >= 0) && (!mine || tr.getAttribute("data-mine") === "1");
      tr.hidden = !ok; if (ok) shown++;
    });
    var empty = $("[data-ekl-empty]"); if (empty) empty.hidden = shown > 0;
  }

  // --------------------------------------------------------------- popup / form --
  function openOv(sel) { var ov = $(sel); if (ov) { ov.hidden = false; var m = ov.querySelector("[role=dialog]"); if (m) m.focus(); } return ov; }
  function closeAll() { $all(".ekl-ov").forEach(function (o) { o.hidden = true; }); }
  function setErr(form, msg, errors) {
    var p = form.querySelector("[data-ekl-err]");
    $all(".ekl-fld.is-invalid", form).forEach(function (f) { f.classList.remove("is-invalid"); });
    if (errors) Object.keys(errors).forEach(function (k) {
      var inp = form.querySelector('[name="' + k + '"]'); var f = inp && inp.closest(".ekl-fld"); if (f) f.classList.add("is-invalid");
    });
    if (p) { p.textContent = msg || ""; p.hidden = !msg; }
  }
  function busy(btn, on) { if (!btn) return; btn.disabled = on; btn.classList.toggle("is-busy", on); }

  function fillOptions(form) {
    $all("[data-ekl-opt]", form).forEach(function (sel) {
      var list = BOOT[sel.getAttribute("data-ekl-opt")] || [];
      var blank = sel.getAttribute("data-ekl-blank") ? '<option value="">— Không chọn —</option>' : '<option value="">— Chọn —</option>';
      sel.innerHTML = blank + list.map(function (o) {
        return '<option value="' + esc(o.value) + '">' + esc(o.label) + (o.sample ? " (mẫu tạm)" : "") + "</option>";
      }).join("");
    });
  }
  function syncPenalty(form) {
    var card = (form.querySelector('[name="card"]') || {}).value;
    var pen = form.querySelector("[data-ekl-penalty]"); if (!pen) return;
    var keep = pen.value;
    var opts = (BOOT.cards || {})[card] || [];
    pen.innerHTML = (opts.length > 1 ? '<option value="">— Chọn hình thức —</option>' : "") + opts.map(function (p) { return "<option>" + esc(p) + "</option>"; }).join("");
    if (opts.indexOf(keep) >= 0) pen.value = keep;
    syncShow(form);
  }
  function syncShow(form) {
    var pen = (form.querySelector('[name="penalty"]') || {}).value;
    $all("[data-ekl-show]", form).forEach(function (el) { el.hidden = el.getAttribute("data-ekl-show") !== pen; });
  }
  function collect(form) {
    var out = {};
    $all("input[name],select[name],textarea[name]", form).forEach(function (el) {
      if (el.closest("[hidden]") && el.type !== "hidden") return;
      if (el.type === "checkbox") out[el.name] = el.checked ? 1 : 0;
      else out[el.name] = el.value;
    });
    return out;
  }
  function setVals(form, d) {
    Object.keys(d || {}).forEach(function (k) {
      var el = form.querySelector('[name="' + k + '"]'); if (!el) return;
      if (el.type === "checkbox") el.checked = String(d[k]) === "1"; else el.value = d[k] == null ? "" : d[k];
      var nm = form.querySelector('[data-ekl-file-name="' + k + '"]'); if (nm) nm.textContent = d[k] ? "Đã có tệp" : "";
    });
  }

  function openNoticeForm() {
    var form = $('[data-ekl-form="notice"]'); if (!form) return;
    form.reset(); fillOptions(form); setErr(form); $all("[data-ekl-file-name]", form).forEach(function (s) { s.textContent = ""; });
    openOv('[data-ekl-form-ov="notice"]');
  }
  function openCaseForm(mode, data) {
    var form = $('[data-ekl-form="case"]'); if (!form) return;
    form.reset(); fillOptions(form); setErr(form); form.setAttribute("data-mode", mode);
    $all("[data-ekl-file-name]", form).forEach(function (s) { s.textContent = ""; });
    var titles = { create: "Lập hồ sơ kỷ luật", propose: "Đề xuất kỷ luật", edit: "Sửa hồ sơ", accept: "Nhận đề xuất - lập hồ sơ" };
    $("[data-ekl-case-title]", form).textContent = titles[mode] || "Hồ sơ";
    $all("[data-ekl-only-new]", form).forEach(function (el) { el.hidden = !(mode === "create" || mode === "propose"); });
    $all("[data-ekl-hr-only]", form).forEach(function (el) { el.hidden = !BOOT.is_hr; });
    // Ho so cu chua co tieu de: o trong = giu tieu de tu sinh (server khong bat nhap khi sua).
    $all("[data-ekl-title-hint]", form).forEach(function (el) { el.hidden = !(data && !data.title); });
    if (data) { var c = data.card; setVals(form, { card: c }); syncPenalty(form); setVals(form, data); }
    syncPenalty(form);
    if (data) setVals(form, { penalty: data.penalty, dismissal_ground: data.dismissal_ground });
    syncShow(form);
    openOv('[data-ekl-form-ov="case"]');
  }

  // Form thao tac: mot khung, than form do step quyet dinh.
  var STEPS = {
    notify: { title: "Thông báo họp xử lý kỷ luật", method: "notify_meeting", body: function (d) {
      return '<p class="ekl-note">Ngày họp sớm nhất: <b>' + esc(dmy(d.earliest_meeting)) + "</b> (" + esc(BOOT.meeting_notice_days) +
        " ngày làm việc sau hôm nay, đã trừ ngày lễ). Hệ thống gửi ERP + email cho nhân viên" + (d.is_union_member === "1" ? " và đại diện công đoàn" : "") + ".</p>" +
        fld("Ngày họp", '<input type="date" name="meeting_date" required min="' + esc(d.earliest_meeting || "") + '" value="' + esc(d.earliest_meeting || "") + '">', true) +
        fld("Địa điểm / hình thức", '<input name="place" maxlength="200">'); } },
    attend: { title: "Xác nhận tham dự họp", method: "confirm_attendance", body: function () {
      return fld("Bạn sẽ", '<select name="attend"><option value="1">Tham dự</option><option value="0">Không tham dự</option></select>', true) +
        fld("Ghi chú (tuỳ chọn)", '<textarea name="note" rows="3"></textarea>') +
        '<p class="ekl-hint">Không tham dự cuộc họp vẫn diễn ra. Im lặng không có nghĩa là đồng ý.</p>'; } },
    record: { title: "Ghi biên bản họp", method: "record_meeting", payload: true, body: function () {
      return fld("Nhân viên", '<select name="employee_present" required><option value="">— Chọn —</option>' + (BOOT.present || []).map(function (p) { return "<option>" + esc(p) + "</option>"; }).join("") + "</select>", true) +
        fld("Ý kiến / phản hồi của nhân viên", '<textarea name="employee_statement" rows="4"></textarea>') +
        fileFld("Biên bản họp có ký", "meeting_minutes", true) +
        fld("Người không ký và lý do", '<textarea name="unsigned_notes" rows="2"></textarea>'); } },
    submit: { title: "Trình CEO ký quyết định", method: "submit_to_ceo", payload: true, body: stepDecision },
    resubmit: { title: "Gửi lại CEO sau bổ sung", method: "resubmit_to_ceo", payload: true, body: stepDecision },
    postpone: { title: "Hoãn xử lý (Điều 122.4)", method: "postpone_case", body: function () {
      return fld("Lý do", '<select name="block_reason" required>' + (BOOT.blocks || []).map(function (b) { return "<option>" + esc(b) + "</option>"; }).join("") + "</select>", true) +
        fld("Từ ngày", '<input type="date" name="block_from" required>', true) + fld("Đến ngày (dự kiến)", '<input type="date" name="block_to" required>', true) +
        fld("Ghi chú nội bộ", '<textarea name="note" rows="2"></textarea>') +
        '<p class="ekl-hint">Thời hiệu tự kéo dài theo Điều 123.2 nếu còn dưới 60 ngày khi hết thời gian này.</p>'; } },
    cancel: { title: "Huỷ hồ sơ", method: "cancel_case", body: reasonBody },
    expunge: { title: "Xoá kỷ luật sau khi xem xét", method: "expunge_case", body: function () { return fld("Lý do (không phải tái phạm)", '<textarea name="note" rows="3" required></textarea>', true); } },
    reply: { title: "Phản hồi thẻ vàng", method: "notice_reply", body: function () { return fld("Nội dung phản hồi", '<textarea name="message" rows="4" required></textarea>', true); } },
    ncancel: { title: "Huỷ thẻ vàng", method: "notice_cancel", body: reasonBody },
    retitle: { title: "Sửa tiêu đề hồ sơ", method: "case_retitle", body: titleBody },
    nretitle: { title: "Sửa tiêu đề thẻ vàng", method: "notice_retitle", body: titleBody }
  };
  function titleBody(d) {
    return fld("Tiêu đề", '<input name="title" required maxlength="' + esc(BOOT.title_max || 140) + '" value="' + esc(d.title || "") +
      '" placeholder="' + esc(d.display_title || BOOT.title_placeholder || "") + '">', true) +
      '<p class="ekl-hint">Thay đổi được ghi vào nhật ký (tiêu đề cũ → mới).</p>';
  }
  function titleHead(kind, d) {
    return '<div class="ekl-modal-h is-stack"><span class="ekl-dtitle' + (d.title_auto ? " is-auto" : "") + '">' + esc(d.display_title || d.name) +
      '</span><span class="ekl-dsub">' + esc(kind) + " " + esc(d.name) + ' <span class="ekl-badge">' + esc(kind === "Thẻ vàng" ? d.status : d.display_status) + "</span>" +
      (d.title_auto ? ' <span class="ekl-hint">(tiêu đề tự sinh)</span>' : "") + "</span></div>";
  }
  function fld(label, ctrl, req) { return '<div class="ekl-fld"><label>' + esc(label) + (req ? ' <span class="ekl-req">*</span>' : "") + "</label>" + ctrl + "</div>"; }
  function fileFld(label, name, req) {
    return fld(label, '<input type="file" data-ekl-file="' + name + '"><input type="hidden" name="' + name + '"><span class="ekl-hint" data-ekl-file-name="' + name + '"></span>', req);
  }
  function reasonBody() { return fld("Lý do", '<textarea name="reason" rows="3" required></textarea>', true); }
  function stepDecision(d) {
    return fileFld("Dự thảo quyết định", "decision_draft", true) + (d.decision_draft ? '<p class="ekl-hint">Đã có dự thảo - tải tệp mới nếu muốn thay.</p>' : "") +
      fld("Ngày hiệu lực", '<input type="date" name="effective_date" value="' + esc(d.effective_date || "") + '">') +
      (d.penalty === "Sa thải" ? fld("Ngày chấm dứt hợp đồng", '<input type="date" name="termination_date" required value="' + esc(d.termination_date || "") + '">', true) +
        '<p class="ekl-note">CEO ký xong: hệ thống ghi ngày nghỉ việc trên hồ sơ và mở Clearance.</p>' : "");
  }
  function openStep(key) {
    var cfg = STEPS[key]; var form = $('[data-ekl-form="step"]'); if (!cfg || !form || !state.current) return;
    state.step = key;
    $("[data-ekl-step-title]", form).textContent = cfg.title;
    $("[data-ekl-step-body]", form).innerHTML = cfg.body(state.current.data || {});
    setErr(form);
    openOv('[data-ekl-form-ov="step"]');
  }

  // ------------------------------------------------------------------ chi tiet --
  function kv(label, v) { return v ? "<dt>" + esc(label) + "</dt><dd>" + esc(v) + "</dd>" : ""; }
  function fileLink(label, url) { return url ? '<dt>' + esc(label) + '</dt><dd><a href="' + esc(url) + '" target="_blank" rel="noopener">Mở tệp</a></dd>' : ""; }
  function btn(act, label, cls) { return '<button type="button" class="ekl-btn ' + (cls || "") + '" data-ekl-act="' + act + '">' + esc(label) + "</button>"; }
  function logHtml(logs) {
    return '<h3 class="ekl-h3">Nhật ký</h3><ul class="ekl-log">' + (logs || []).map(function (l) {
      return "<li><b>" + esc(l.action) + "</b> · " + esc(l.actor) + " · " + esc(dmy(l.at)) + (l.note ? '<div class="ekl-hint">' + esc(l.note) + "</div>" : "") + "</li>";
    }).join("") + "</ul>";
  }
  function noticeHtml(d) {
    var a = d.actions || {};
    return titleHead("Thẻ vàng", d) + '<div class="ekl-modal-b">' +
      '<p class="ekl-note">' + esc(d.note) + "</p>" + (d.hint ? '<p class="ekl-banner is-warn">' + esc(d.hint) + "</p>" : "") +
      '<dl class="ekl-kv">' + kv("Nhân viên", d.employee_name) + kv("Hành vi", d.behavior) + kv("Ngày xảy ra", dmy(d.incident_date)) +
      kv("Người gửi", d.issued_by + (d.issuer_role ? " (" + d.issuer_role + ")" : "")) + kv("Hạn phản hồi", dmy(d.reply_due)) +
      kv("Điều khoản", d.rule) + fileLink("Bằng chứng", d.evidence) + "</dl>" +
      '<p class="ekl-pre">' + esc(d.content) + "</p>" + (d.response ? '<h3 class="ekl-h3">Phản hồi</h3><p class="ekl-pre">' + esc(d.response) + "</p>" : "") +
      logHtml(d.logs) + '</div><div class="ekl-modal-f">' + btn("close", "Đóng") +
      (a.cancel ? btn("ncancel", "Huỷ thẻ", "is-danger") : "") + (a.retitle ? btn("nretitle", "Sửa tiêu đề") : "") + (a.reply ? btn("reply", "Viết phản hồi") : "") +
      (a.read ? btn("read", "Đã đọc", "is-primary") : "") + "</div>";
  }
  function caseHtml(d) {
    var a = d.actions || {}; var chk = d.check || {};
    var warn = (chk.errors || []).concat(chk.warnings || []).concat(d.recidivism_note ? [d.recidivism_note] : []);
    return titleHead("Hồ sơ", d) +
      '<div class="ekl-modal-b">' + (warn.length ? '<div class="ekl-banner is-warn">' + warn.map(esc).join("<br>") + "</div>" : "") +
      '<dl class="ekl-kv">' + kv("Nhân viên", d.employee_name) + kv("Thẻ · hình thức", (d.card || "") + " · " + (d.penalty || "") + (d.extend_months && d.extend_months !== "0" ? " (" + d.extend_months + " tháng)" : "")) +
      kv("Căn cứ sa thải", d.ground_label) + kv("Điều khoản nội quy", d.rule_title) + kv("Ngày vi phạm", dmy(d.violation_date)) +
      kv("Hết thời hiệu", dmy(d.limitation_effective_end) + (d.limitation_end && d.limitation_end !== d.limitation_effective_end ? " (gốc " + dmy(d.limitation_end) + ", đã kéo dài)" : "")) +
      kv("Hạn HR thẩm định", dmy(d.hr_review_due)) + kv("Hoãn", d.block_reason ? d.block_reason + ": " + dmy(d.block_from) + " - " + dmy(d.block_to) : "") +
      kv("Ngày họp", d.meeting_date ? dmy(d.meeting_date) + (d.meeting_place ? " · " + d.meeting_place : "") : "") + kv("Nhân viên xác nhận", d.attendance_reply) +
      kv("Tại cuộc họp", d.employee_present) + kv("Hạn CEO ký", dmy(d.ceo_due)) + kv("Ngày ban hành", dmy(d.decision_date)) +
      kv("Tự xoá kỷ luật", dmy(d.expunge_due)) + kv("Không tự xoá vì", d.expunge_hold_note) + kv("Chấm dứt HĐ", d.offboarding_note) +
      fileLink("Bằng chứng", d.evidence) + fileLink("Biên bản vi phạm", d.violation_record) + fileLink("Biên bản họp", d.meeting_minutes) + fileLink("Dự thảo quyết định", d.decision_draft) +
      (d.decision_url ? '<dt>Phiếu trình CEO</dt><dd><a href="' + esc(d.decision_url) + '">' + esc(d.decision_request) + "</a></dd>" : "") + "</dl>" +
      '<h3 class="ekl-h3">Mô tả</h3><p class="ekl-pre">' + esc(d.description) + "</p>" +
      (d.employee_statement ? '<h3 class="ekl-h3">Ý kiến nhân viên</h3><p class="ekl-pre">' + esc(d.employee_statement) + "</p>" : "") +
      (d.hr_note ? '<h3 class="ekl-h3">Ghi chú nội bộ HR</h3><p class="ekl-pre">' + esc(d.hr_note) + "</p>" : "") +
      logHtml(d.logs) + '</div><div class="ekl-modal-f">' + btn("close", "Đóng") +
      (a.cancel ? btn("cancel", "Huỷ hồ sơ", "is-danger") : "") + (a.postpone ? btn("postpone", "Hoãn") : "") + (a.resume ? btn("resume", "Tiếp tục") : "") +
      (a.retitle ? btn("retitle", "Sửa tiêu đề") : "") + (a.accept ? btn("accept", "Nhận đề xuất", "is-primary") : (a.edit ? btn("edit", "Sửa") : "")) +
      (a.notify ? btn("notify", "Thông báo họp", "is-primary") : "") + (a.attend ? btn("attend", "Xác nhận tham dự", "is-primary") : "") +
      (a.record ? btn("record", "Ghi biên bản họp", "is-primary") : "") + (a.submit ? btn("submit", "Trình CEO", "is-primary") : "") +
      (a.resubmit ? btn("resubmit", "Gửi lại CEO", "is-primary") : "") + (a.expunge ? btn("expunge", "Xoá kỷ luật") : "") + "</div>";
  }
  async function openDetail(kind, name) {
    var ov = openOv("[data-ekl-detail-ov]"); var box = $("[data-ekl-detail]");
    box.innerHTML = '<p class="ekl-state"><span class="ekl-spin" aria-hidden="true"></span> Đang tải…</p>';
    try {
      var d = await api(kind === "notice" ? "get_notice" : "get_case", { name: name }, true);
      state.current = { kind: kind, name: name, data: d };
      box.innerHTML = kind === "notice" ? noticeHtml(d) : caseHtml(d);
    } catch (e) {
      box.innerHTML = '<div class="ekl-modal-b"><p class="ekl-banner is-err">' + esc(e.message) + '</p></div><div class="ekl-modal-f">' + btn("close", "Đóng") + "</div>";
    }
    return ov;
  }
  function reloadWith(name) {
    var u = new URL(window.location.href);
    if (name) u.searchParams.set("ma", name); else u.searchParams.delete("ma");
    window.EcKyLuat.navigate(u.toString());
  }

  async function quickAct(act) {
    var c = state.current; if (!c) return;
    var map = { read: "notice_read", resume: "resume_case" };
    if (act === "resume" && !window.confirm("Tiếp tục hồ sơ? Cần thông báo họp lại từ đầu.")) return;
    try { await api(map[act], { name: c.name }); toast("Đã cập nhật."); reloadWith(c.name); }
    catch (e) { toast(e.message, true); }
  }

  async function submitForm(form) {
    var kind = form.getAttribute("data-ekl-form"); var b = form.querySelector("[data-ekl-submit]");
    var v = collect(form); var method, args;
    if (kind === "notice") { method = "issue_notice"; args = { payload: v }; }
    else if (kind === "case") {
      var mode = form.getAttribute("data-mode");
      if (mode === "edit" || mode === "accept") { method = "update_case"; if (mode === "accept") v.accept = 1; args = { name: v.name, payload: v }; }
      else { method = mode === "propose" ? "propose_case" : "create_case"; args = { payload: v }; }
    } else {
      var cfg = STEPS[state.step]; method = cfg.method;
      args = cfg.payload ? { name: state.current.name, payload: v } : Object.assign({ name: state.current.name }, v);
    }
    busy(b, true); setErr(form);
    try {
      var res = await api(method, args);
      toast(res && res.hint ? res.hint : "Đã lưu.");
      reloadWith((res && res.name) || (state.current && state.current.name));
    } catch (e) { setErr(form, e.message, e.errors); }
    finally { busy(b, false); }
  }

  // --------------------------------------------------------------- trang quyet dinh --
  async function decide(act) {
    var box = $("[data-ekl-decide]"); var cmt = ($("[data-ekl-d-comment]") || {}).value || "";
    var err = box.querySelector("[data-ekl-err]"); err.hidden = true;
    if (act !== "approve" && !cmt.trim()) { err.textContent = "Nhập ghi chú cho HR."; err.hidden = false; return; }
    var labels = { approve: "Ký ban hành quyết định kỷ luật?", info: "Trả hồ sơ cho HR bổ sung?", reject: "Quyết định KHÔNG kỷ luật?" };
    if (!window.confirm(labels[act])) return;
    var btns = $all("[data-ekl-decide-act]"); btns.forEach(function (x) { busy(x, true); });
    try {
      if (act === "approve") {
        var st = null;
        try { st = await window.ecApi.get(ESIGN + "get_signing_status", { business_doctype: BOOT.doctype, business_name: BOOT.name }); } catch (x) { st = null; }
        if (st && st.enabled) await window.ecApi.post(ESIGN + "approve_and_sign", { business_doctype: BOOT.doctype, business_name: BOOT.name, comment: cmt });
        else await window.ecApi.post(DEC_NS + "approve", { name: BOOT.name, comment: cmt });
      } else {
        await window.ecApi.post(DEC_NS + (act === "info" ? "request_information" : "reject"), { name: BOOT.name, comment: cmt });
      }
      try { await api("sync_case", { name: BOOT.case }); } catch (x) { /* job hang ngay se dong bo */ }
      toast("Đã ghi quyết định."); window.location.reload();
    } catch (e) {
      err.textContent = e.message && e.body ? serverMsg(e) : (e.message || "Không thực hiện được."); err.hidden = false;
    } finally { btns.forEach(function (x) { busy(x, false); }); }
  }

  // ---------------------------------------------------------------------- noi day --
  function bind() {
    try { BOOT = JSON.parse(($("#ekl-boot") || {}).textContent || "{}"); } catch (e) { BOOT = {}; }
    document.addEventListener("input", function (e) { if (e.target.matches("[data-ekl-q]")) applyFilter(); });
    document.addEventListener("change", async function (e) {
      var t = e.target;
      if (t.matches("[data-ekl-mine]")) applyFilter();
      if (t.matches('[name="card"]')) syncPenalty(t.form);
      if (t.matches('[name="penalty"]')) syncShow(t.form);
      if (t.matches("[data-ekl-file]") && t.files && t.files[0]) {
        var key = t.getAttribute("data-ekl-file"); var form = t.form; var nm = form.querySelector('[data-ekl-file-name="' + key + '"]');
        nm.textContent = "Đang tải lên…";
        try { form.querySelector('[name="' + key + '"]').value = await upload(t.files[0]); nm.textContent = "Đã tải: " + t.files[0].name; }
        catch (x) { nm.textContent = ""; toast(x.message, true); }
      }
    });
    document.addEventListener("click", function (e) {
      var t = e.target.closest("[data-ekl-open],[data-ekl-open-form],[data-ekl-close],[data-ekl-act],[data-ekl-decide-act]");
      if (!t) { if (e.target.classList && e.target.classList.contains("ekl-ov")) closeAll(); return; }
      if (t.hasAttribute("data-ekl-open")) return openDetail(t.getAttribute("data-ekl-open"), t.getAttribute("data-name"));
      if (t.hasAttribute("data-ekl-open-form")) {
        var f = t.getAttribute("data-ekl-open-form");
        return f === "notice" ? openNoticeForm() : openCaseForm(f === "propose" ? "propose" : "create");
      }
      if (t.hasAttribute("data-ekl-close")) return closeAll();
      if (t.hasAttribute("data-ekl-decide-act")) return decide(t.getAttribute("data-ekl-decide-act"));
      var act = t.getAttribute("data-ekl-act");
      if (act === "close") return closeAll();
      if (act === "read" || act === "resume") return quickAct(act);
      if (act === "edit" || act === "accept") { closeAll(); return openCaseForm(act, state.current.data); }
      closeAll(); openStep(act);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeAll();
      if (e.key === "Enter" && e.target.matches("tr[data-ekl-open]")) openDetail(e.target.getAttribute("data-ekl-open"), e.target.getAttribute("data-name"));
    });
    document.addEventListener("submit", function (e) {
      if (!e.target.matches("[data-ekl-form]")) return;
      e.preventDefault(); submitForm(e.target);
    });
    if (BOOT.open) {
      var row = $('tr[data-name="' + (window.CSS && CSS.escape ? CSS.escape(BOOT.open) : BOOT.open) + '"]');
      openDetail(row ? row.getAttribute("data-ekl-open") : (BOOT.tab === "ho-so" ? "case" : "notice"), BOOT.open);
    }
  }

  window.EcKyLuat = { esc: esc, dmy: dmy, api: api, syncPenalty: syncPenalty, applyFilter: applyFilter, STEPS: STEPS,
    caseHtml: caseHtml, noticeHtml: noticeHtml, _boot: function (b) { BOOT = b || {}; },
    navigate: function (url) { window.location.assign(url); } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind); else bind();
})();
