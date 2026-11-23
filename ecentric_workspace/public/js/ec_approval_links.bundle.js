// Copyright (c) 2026, eCentric and contributors
//
// "Gan phieu duyet" vao o dinh kem - dung chung cho MOI form phe duyet + popup /approvals/all-requests
// (Dot 0 quy trinh nhan su, Hoan chot 22/11/2026). Dung phieu da duyet (vd Phe duyet dot xuat cua CEO)
// lam chung tu thay vi anh chup. Chi luu LIEN KET.
//
// Server quyet dinh het (shared/requests/approval_links.py): ai gan / go duoc (nguoi DANG giu phieu),
// tim phieu nao (chi phieu minh duoc xem - cung luat tab "Tat ca"), phieu rieng tu (nguoi gan phai la
// nguoi gui phieu do + bat buoc chon co cho nguoi duyet doc khong), nhan an toan cua chip, chan gui khi
// phieu gan bi tu choi / huy ma chua ghi ly do, audit. O day chi VE theo `capabilities`:
//   cap.approval_links      [chip...]  (code, title|null, status, status_label, private, can_open,
//                                       detail_url, bad, used_elsewhere, shared, can_unlink, link,
//                                       override_reason)
//   cap.can_link_approval   bool
//   cap.approval_link_host  {doctype, name}
//
// GIAO KEO VOI TRANG - KHONG sua trang form nao: ec_addfile.bundle.js noi `EcApprovalLinks.blockHTML(cap)`
// vao `EcAddFile.buttonHTML(cap)` (31 form goi qua EcRemind.buttonHTML, popup hub goi thang). Sau moi
// thao tac widget TU ve lai khoi cua no (goi list_approval_links) - khong bat trang ve lai.
(function () {
  "use strict";
  if (window.EcApprovalLinks) return;
  var BASE = "/api/method/ecentric_workspace.approval_center.reporting.actions.";
  var busy = false;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function csrf() { return (window.frappe && window.frappe.csrf_token) || ""; }
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
  function errText(e, fallback) {
    if (window.EcApprovalUI && typeof window.EcApprovalUI.errorText === "function") {
      return window.EcApprovalUI.errorText(e, fallback);
    }
    return (e && e.message) || fallback;
  }
  function api(method, params, post) {
    var url = BASE + method, opts = { credentials: "same-origin",
      headers: { "Accept": "application/json", "X-Frappe-CSRF-Token": csrf() } };
    if (post) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(params || {});
    } else {
      var qs = Object.keys(params || {}).filter(function (k) { return params[k] != null && params[k] !== ""; })
        .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]); }).join("&");
      url += qs ? ("?" + qs) : "";
      opts.method = "GET";
    }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(serverMsg(j) || "Không thực hiện được. Thử lại sau.");
        return (j && j.message) || {};
      });
    });
  }

  var toastTimer = null;
  function toast(msg, err) {
    var t = document.getElementById("ec-aplk-toast");
    if (!t) {
      t = document.createElement("div");
      t.id = "ec-aplk-toast";
      t.setAttribute("role", "status");
      t.setAttribute("aria-live", "polite");
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.className = "ec-aplk-toast" + (err ? " err" : "");
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, 4000);
  }

  // ---- chip ---------------------------------------------------------------------------
  function chipHTML(c, canEdit) {
    var cls = "ec-aplk-chip" + (c.bad ? " ec-aplk-chip--bad" : "") + (c.private ? " ec-aplk-chip--private" : "");
    var head = c.can_open && c.detail_url
      ? '<a class="ec-aplk-code" href="' + esc(c.detail_url) + '" target="_blank" rel="noopener">' + esc(c.code) + "</a>"
      : '<span class="ec-aplk-code">' + esc(c.code) + "</span>";
    var title = c.title ? '<span class="ec-aplk-title">' + esc(c.title) + "</span>"
      : (c.private ? '<span class="ec-aplk-title ec-aplk-muted">Phiếu riêng tư</span>' : "");
    var meta = [];
    meta.push('<span class="ec-aplk-status' + (c.bad ? " bad" : "") + '">' + esc(c.status_label || c.status || "") + "</span>");
    if (c.private) meta.push('<span class="ec-aplk-tag">' + (c.shared ? "Người duyệt được đọc" : "Chỉ hiện mã") + "</span>");
    if (c.used_elsewhere) meta.push('<span class="ec-aplk-tag warn">Đã gắn vào ' + esc(c.used_elsewhere) + " phiếu khác</span>");
    var extra = "";
    if (c.bad) {
      extra = c.override_reason
        ? '<div class="ec-aplk-reason">Lý do vẫn dùng: ' + esc(c.override_reason) + "</div>"
        : '<div class="ec-aplk-reason bad">Phiếu gắn đã bị ' + (c.status === "Cancelled" ? "huỷ" : "từ chối") + "."
          + (canEdit ? ' <button type="button" class="ec-aplk-linkbtn" data-ec-aplk-reason="' + esc(c.link) + '">Ghi lý do vẫn dùng</button>' : "")
          + "</div>";
    }
    var x = c.can_unlink ? '<button type="button" class="ec-aplk-x" data-ec-aplk-unlink="' + esc(c.link)
      + '" aria-label="Gỡ phiếu ' + esc(c.code) + '" title="Gỡ phiếu">×</button>' : "";
    return '<div class="' + cls + '" role="listitem"><div class="ec-aplk-line">' + head + title + x + "</div>"
      + '<div class="ec-aplk-meta">' + meta.join("") + "</div>" + extra + "</div>";
  }

  function innerHTML(cap) {
    var chips = cap.approval_links || [];
    var can = !!cap.can_link_approval;
    var list = chips.length ? '<div class="ec-aplk-list" role="list">' + chips.map(function (c) { return chipHTML(c, can); }).join("") + "</div>" : "";
    var btn = can ? '<button type="button" class="btn ec-aplk-add" data-ec-aplk-open>🔗 Gắn phiếu duyệt</button>' : "";
    return '<div class="ec-aplk-h">Phiếu duyệt đính kèm' + (chips.length ? " (" + chips.length + ")" : "") + "</div>" + list + btn;
  }

  function blockHTML(cap) {
    cap = cap || {};
    var host = cap.approval_link_host;
    var chips = cap.approval_links || [];
    if (!host || !host.doctype || !host.name || (!chips.length && !cap.can_link_approval)) return "";
    return '<div class="ec-aplk" data-ec-aplk-dt="' + esc(host.doctype) + '" data-ec-aplk-name="' + esc(host.name) + '">'
      + innerHTML(cap) + "</div>";
  }

  function hostOf(el) {
    var box = el && el.closest ? el.closest(".ec-aplk") : null;
    return box ? { box: box, doctype: box.getAttribute("data-ec-aplk-dt"), name: box.getAttribute("data-ec-aplk-name") } : null;
  }

  function redraw(h, cap) {
    if (!h || !h.box) return;
    if (cap && cap.chips) cap = { approval_links: cap.chips, can_link_approval: true,
      approval_link_host: { doctype: h.doctype, name: h.name } };
    if (cap && cap.approval_links) { h.box.innerHTML = innerHTML(cap); return Promise.resolve(); }
    return api("list_approval_links", { host_doctype: h.doctype, host_name: h.name }).then(function (c) {
      h.box.innerHTML = innerHTML(c || {});
    });
  }

  // ---- hop chon phieu -----------------------------------------------------------------
  function closeModal() {
    var m = document.querySelector(".ec-aplk-overlay");
    if (m && m.parentNode) m.parentNode.removeChild(m);
  }

  function openModal(h) {
    closeModal();
    var prev = document.activeElement;
    var ov = document.createElement("div");
    ov.className = "ec-aplk-overlay";
    ov.innerHTML = '<div class="ec-aplk-modal" role="dialog" aria-modal="true" aria-labelledby="ec-aplk-mt">'
      + '<div class="ec-aplk-mh" id="ec-aplk-mt">Gắn phiếu duyệt</div>'
      + '<div class="ec-aplk-mb">'
      + '<div class="ec-aplk-search"><label for="ec-aplk-q">Tìm theo mã / loại phiếu</label>'
      + '<input id="ec-aplk-q" type="search" autocomplete="off" placeholder="VD: EC-ADHOC-2026-00012">'
      + '<label for="ec-aplk-box">Phạm vi</label><select id="ec-aplk-box"><option value="mine">Của tôi</option>'
      + '<option value="received">Tôi đã duyệt</option><option value="">Tất cả tôi xem được</option></select></div>'
      + '<div class="ec-aplk-results" aria-live="polite"><div class="ec-aplk-muted">Đang tải…</div></div>'
      + '<div class="ec-aplk-choice" hidden></div>'
      + '<div class="ec-aplk-err" role="alert" hidden></div></div>'
      + '<div class="ec-aplk-mf"><button type="button" class="btn" data-x>Huỷ</button>'
      + '<button type="button" class="btn primary" data-ok disabled>Gắn phiếu</button></div></div>';
    document.body.appendChild(ov);
    var q = ov.querySelector("#ec-aplk-q"), box = ov.querySelector("#ec-aplk-box");
    var res = ov.querySelector(".ec-aplk-results"), choice = ov.querySelector(".ec-aplk-choice");
    var err = ov.querySelector(".ec-aplk-err"), ok = ov.querySelector("[data-ok]");
    var picked = null, rows = [], timer = null, seq = 0;

    function close() { closeModal(); if (prev && prev.focus) try { prev.focus(); } catch (e) { /* bo qua */ } }
    ov.querySelector("[data-x]").onclick = function () { if (!busy) close(); };
    ov.addEventListener("keydown", function (e) { if (e.key === "Escape" && !busy) close(); });
    ov.addEventListener("click", function (e) { if (e.target === ov && !busy) close(); });

    function refreshOk() {
      var need = picked && picked.private;
      var chosen = need ? !!choice.querySelector("input[name=ec-aplk-share]:checked") : true;
      ok.disabled = !picked || !chosen || busy;
    }
    function renderRows() {
      if (!rows.length) { res.innerHTML = '<div class="ec-aplk-muted">Không có phiếu phù hợp.</div>'; return; }
      res.innerHTML = '<table class="ec-aplk-table"><thead><tr><th scope="col">Mã</th><th scope="col">Tiêu đề</th>'
        + '<th scope="col">Trạng thái</th></tr></thead><tbody>' + rows.map(function (r, i) {
          var dis = r.already_linked || !r.can_attach;
          var note = r.already_linked ? " (đã gắn)" : (!r.can_attach ? " (chỉ người gửi phiếu riêng tư mới gắn được)" : "");
          return '<tr class="' + (dis ? "dis" : "") + (picked === r ? " sel" : "") + '" data-i="' + i + '"' + (dis ? "" : ' tabindex="0"') + ">"
            + "<td>" + esc(r.code) + "</td><td>" + esc(r.title || (r.private ? "Phiếu riêng tư" : "")) + esc(note)
            + (r.used_elsewhere ? ' <span class="ec-aplk-tag warn">đã gắn vào ' + esc(r.used_elsewhere) + " phiếu khác</span>" : "")
            + '</td><td class="' + (r.bad ? "bad" : "") + '">' + esc(r.status_label) + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
    function pick(i) {
      var r = rows[i];
      if (!r || r.already_linked || !r.can_attach) return;
      picked = r;
      renderRows();
      if (r.private) {
        choice.hidden = false;
        choice.innerHTML = '<div class="ec-aplk-ch"><b>' + esc(r.code) + "</b> là phiếu riêng tư</div>"
          + '<label class="ec-aplk-radio"><input type="radio" name="ec-aplk-share" value="1"> Cho người duyệt phiếu này đọc nội dung'
          + '<small>Họ xem + tải tệp khi còn trong luồng của phiếu này; mỗi lần mở được ghi lại.</small></label>'
          + '<label class="ec-aplk-radio"><input type="radio" name="ec-aplk-share" value="0"> Chỉ hiện mã và trạng thái'
          + '<small>Người duyệt không đọc được nội dung — chứng từ có thể không đủ.</small></label>';
      } else {
        choice.hidden = true;
        choice.innerHTML = "";
      }
      refreshOk();
    }
    res.addEventListener("click", function (e) {
      var tr = e.target.closest && e.target.closest("tr[data-i]");
      if (tr) pick(Number(tr.getAttribute("data-i")));
    });
    res.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var tr = e.target.closest && e.target.closest("tr[data-i]");
      if (tr) { e.preventDefault(); pick(Number(tr.getAttribute("data-i"))); }
    });
    choice.addEventListener("change", refreshOk);

    function load() {
      var my = ++seq;
      res.innerHTML = '<div class="ec-aplk-muted">Đang tải…</div>';
      api("search_linkable", { host_doctype: h.doctype, host_name: h.name, q: q.value.trim(), box: box.value })
        .then(function (d) {
          if (my !== seq) return;
          rows = (d && d.rows) || [];
          picked = null; choice.hidden = true; choice.innerHTML = "";
          renderRows(); refreshOk();
        }).catch(function (e) {
          if (my !== seq) return;
          res.innerHTML = "";
          err.textContent = errText(e, "Không tải được danh sách phiếu.");
          err.hidden = false;
        });
    }
    q.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(load, 300); });
    box.addEventListener("change", load);
    ok.onclick = function () {
      if (busy || !picked) return;
      var sh = choice.querySelector("input[name=ec-aplk-share]:checked");
      busy = true; ok.disabled = true; err.hidden = true;
      ok.textContent = "Đang gắn…";
      api("link_approval", { host_doctype: h.doctype, host_name: h.name, target_request: picked.request,
        share: picked.private ? (sh ? sh.value : "") : "0" }, true).then(function (d) {
        busy = false;
        close();
        toast(d && d.duplicate ? "Phiếu này đã được gắn trước đó." : "Đã gắn phiếu " + picked.code + ".");
        return redraw(h, d);
      }).catch(function (e) {
        busy = false;
        ok.textContent = "Gắn phiếu";
        refreshOk();
        err.textContent = errText(e, "Không gắn được phiếu. Thử lại sau.");
        err.hidden = false;
      });
    };
    try { q.focus(); } catch (e) { /* bo qua */ }
    load();
    return ov;
  }

  // ---- su kien (uy quyen tren document) ------------------------------------------------
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t || !t.closest) return;
    var open = t.closest("[data-ec-aplk-open]");
    var un = t.closest("[data-ec-aplk-unlink]");
    var rs = t.closest("[data-ec-aplk-reason]");
    if (!open && !un && !rs) return;
    e.preventDefault();
    e.stopPropagation();
    var h = hostOf(t);
    if (!h || busy) return;
    if (open) { openModal(h); return; }
    if (un) {
      if (!window.confirm("Gỡ phiếu này khỏi phiếu hiện tại? Quyền xem đi kèm (nếu có) sẽ bị thu hồi.")) return;
      busy = true; un.disabled = true;
      api("unlink_approval", { link: un.getAttribute("data-ec-aplk-unlink") }, true).then(function (d) {
        busy = false; toast("Đã gỡ phiếu."); return redraw(h, d);
      }).catch(function (x) { busy = false; un.disabled = false; toast(errText(x, "Không gỡ được phiếu."), true); });
      return;
    }
    if (rs) {
      var reason = window.prompt("Lý do vẫn dùng phiếu bị từ chối / huỷ (người duyệt sẽ thấy):", "");
      if (reason == null) return;
      if (!String(reason).trim()) { toast("Vui lòng nhập lý do.", true); return; }
      busy = true; rs.disabled = true;
      api("set_link_override_reason", { link: rs.getAttribute("data-ec-aplk-reason"), reason: reason }, true).then(function (d) {
        busy = false; toast("Đã ghi lý do."); return redraw(h, d);
      }).catch(function (x) { busy = false; rs.disabled = false; toast(errText(x, "Không ghi được lý do."), true); });
    }
  }, true);

  window.EcApprovalLinks = { blockHTML: blockHTML, chipHTML: chipHTML, openModal: openModal };
})();
