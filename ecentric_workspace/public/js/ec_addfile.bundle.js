// Copyright (c) 2026, eCentric and contributors
//
// Nut "Them tep" o buoc duyet, dung chung cho MOI form phe duyet + popup /approvals/all-requests
// (16/10/2026, Hoan: Finance cap 1 soan hop dong roi dinh kem de Finance cap 2 xem tiep).
//
// Server quyet dinh het (shared/requests/add_file.py): ai duoc them (nguoi DANG giu phieu - duyet
// Pending o cap hien tai, hoac chu viec o buoc xu ly), tep phai la tep rieng tu cua chinh nguoi
// bam, ghi vet "Attachment Added" vao lich su duyet, Contract Review thi day tep moi len
// SharePoint. O day chi: ve nut theo `capabilities.can_add_attachment`, tai tep len
// (upload_file, is_private=1, KHONG kem doctype/docname - xem test_fulfillment_upload_permission),
// roi goi MOT endpoint router `reporting.actions.add_attachment` cho moi form.
//
// GIAO KEO VOI TRANG - KHONG sua trang form nao:
//   * 31 trang form da goi `EcRemind.buttonHTML(cap)` trong khu "Hanh dong"; ec_remind.bundle.js
//     noi them `EcAddFile.buttonHTML(cap)` vao do. Nut la <label> (khong co data-act) nen
//     handleActionClick cua trang bo qua; o day bat su kien `change` tren document.
//   * Them xong: phat `ec-addfile:done` (cancelable, detail {request, file_name}). Trang nao tu
//     ve lai (popup hub) thi preventDefault; con lai -> bao toast + phat `popstate` de route()
//     cua trang form ve lai chi tiet (?id=...) - moi trang form deu nghe popstate.
(function () {
  "use strict";
  if (window.EcAddFile) return;
  var ENDPOINT = "ecentric_workspace.approval_center.reporting.actions.add_attachment";
  // Khop shared/requests/add_file.py BLOCKED_EXT (server van kiem lai - day chi de bao som).
  var BLOCKED = [".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".js", ".jar",
    ".sh", ".php", ".py", ".html", ".htm", ".xhtml", ".svg", ".hta", ".dll"];
  var busy = false;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function ext(n) { var m = /\.[^.\/\\]+$/.exec(String(n || "").toLowerCase()); return m ? m[0] : ""; }
  function size(b) {
    b = Number(b) || 0;
    return b >= 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB";
  }
  function csrf() { return (window.frappe && window.frappe.csrf_token) || ""; }

  function buttonHTML(cap) {
    cap = cap || {};
    if (!cap.can_add_attachment || !cap.add_attachment_request) return "";
    return '<label class="btn ec-addfile-btn" tabindex="0" role="button"'
      + ' title="Đính kèm thêm tệp vào phiếu — ghi vào lịch sử duyệt, không xoá được">'
      + '<input type="file" hidden data-ec-addfile="' + esc(cap.add_attachment_request) + '">'
      + "📎 Thêm tệp</label>";
  }

  function serverMsg(j) {
    j = j || {};
    try {
      var arr = JSON.parse(j._server_messages || "[]"), m = arr[0];
      if (m) { try { m = JSON.parse(m).message || m; } catch (e) { /* chuoi tho */ } }
      if (m) return String(m).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
    } catch (e) { /* bo qua */ }
    if (j.exception) return String(j.exception).replace(/^[\w.]+:\s*/, "");
    return "";
  }

  var toastTimer = null;
  function toast(msg, err) {
    var t = document.getElementById("ec-addfile-toast");
    if (!t) {
      t = document.createElement("div");
      t.id = "ec-addfile-toast";
      t.className = "ec-addfile-toast";
      t.setAttribute("role", "status");
      t.setAttribute("aria-live", "polite");
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.className = "ec-addfile-toast" + (err ? " err" : "");
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, 4000);
  }

  function upload(f) {
    var fd = new FormData();
    fd.append("file", f, f.name);
    fd.append("is_private", "1");
    return fetch("/api/method/upload_file", {
      method: "POST", credentials: "same-origin",
      headers: { "X-Frappe-CSRF-Token": csrf() }, body: fd
    }).then(function (r) {
      if (r.status === 413) throw new Error("Tệp quá lớn để tải lên.");
      return r.json().catch(function () { return {}; }).then(function (j) {
        var url = j && j.message && j.message.file_url;
        if (!r.ok || !url) throw new Error(serverMsg(j) || "Không tải được tệp lên. Thử lại sau.");
        return url;
      });
    });
  }

  function attach(req, url) {
    return fetch("/api/method/" + ENDPOINT, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json",
        "X-Frappe-CSRF-Token": csrf() },
      body: JSON.stringify({ request_name: req, file_url: url })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(serverMsg(j) || "Không thêm được tệp vào phiếu. Thử lại sau.");
        return (j && j.message) || {};
      });
    });
  }

  function done(req, res) {
    var name = (res && res.file_name) || "";
    var ev = null;
    try {
      ev = new CustomEvent("ec-addfile:done", { cancelable: true,
        detail: { request: req, file_name: name, business_name: res && res.business_name } });
    } catch (e) { ev = null; }
    var handled = ev ? !document.dispatchEvent(ev) : false;
    if (handled) return;
    toast("Đã thêm tệp " + name + " vào phiếu.");
    var hasId = false;
    try { hasId = !!new URLSearchParams(window.location.search).get("id"); } catch (e) { hasId = false; }
    if (hasId) {
      try { window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state })); }
      catch (e) { /* trinh duyet qua cu: nguoi dung tai lai trang la thay */ }
    }
  }

  function closePanel() {
    var old = document.querySelector(".ec-addfile-panel");
    if (old && old.parentNode) old.parentNode.removeChild(old);
  }

  function openPanel(label, req, f) {
    closePanel();
    var bad = BLOCKED.indexOf(ext(f.name)) >= 0;
    var p = document.createElement("div");
    p.className = "ec-addfile-panel";
    p.setAttribute("role", "group");
    p.setAttribute("aria-label", "Thêm tệp vào phiếu");
    p.innerHTML = '<div class="ec-addfile-msg">' + (bad
      ? "Loại tệp <b>" + esc(ext(f.name)) + "</b> không được phép đính kèm."
      : "Thêm <b>" + esc(f.name) + "</b> (" + esc(size(f.size)) + ") vào phiếu? Tệp được ghi vào "
        + "lịch sử duyệt và <b>không xoá được</b>.")
      + "</div>"
      + '<div class="ec-addfile-err" role="alert" hidden></div>'
      + '<div class="ec-addfile-row">'
      + (bad ? "" : '<button type="button" class="btn primary" data-ec-addfile-ok>Thêm tệp</button>')
      + '<button type="button" class="btn" data-ec-addfile-cancel>' + (bad ? "Đóng" : "Huỷ") + "</button></div>";
    var host = (label.closest && (label.closest(".actions") || label.closest('[data-h="foot"]'))) || label;
    host.parentNode.insertBefore(p, host.nextSibling);
    var ok = p.querySelector("[data-ec-addfile-ok]"), cancel = p.querySelector("[data-ec-addfile-cancel]");
    var err = p.querySelector(".ec-addfile-err");
    cancel.onclick = function () { if (!busy) closePanel(); };
    if (!ok) return p;
    ok.onclick = function () {
      if (busy) return;
      busy = true;
      ok.disabled = true; cancel.disabled = true; err.hidden = true;
      ok.textContent = "Đang tải lên…";
      upload(f).then(function (url) {
        ok.textContent = "Đang thêm vào phiếu…";
        return attach(req, url);
      }).then(function (res) {
        busy = false;
        closePanel();
        done(req, res);
      }).catch(function (e) {
        busy = false;
        ok.disabled = false; cancel.disabled = false;
        ok.textContent = "Thử lại";
        err.textContent = (e && e.message) || "Không thêm được tệp. Thử lại sau.";
        err.hidden = false;
      });
    };
    try { ok.focus(); } catch (e) { /* bo qua */ }
    return p;
  }

  document.addEventListener("change", function (e) {
    var inp = e.target;
    if (!inp || !inp.matches || !inp.matches("input[data-ec-addfile]")) return;
    var f = inp.files && inp.files[0];
    if (!f || busy) return;
    var label = inp.closest("label") || inp;
    openPanel(label, inp.getAttribute("data-ec-addfile"), f);
    try { inp.value = ""; } catch (x) { /* chon lai cung tep van bat duoc change */ }
  });
  document.addEventListener("keydown", function (e) {
    var el = e.target;
    if (!el || !el.matches || !el.matches(".ec-addfile-btn")) return;
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    var inp = el.querySelector("input[data-ec-addfile]");
    if (inp) inp.click();
  });

  window.EcAddFile = { buttonHTML: buttonHTML, ENDPOINT: ENDPOINT };
})();
