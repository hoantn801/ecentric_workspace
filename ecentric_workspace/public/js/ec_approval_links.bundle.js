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
//
// 26/11/2026 - NGUOI LAP PHIEU (0 EC Approval Link tren site: cac trang chi goi buttonHTML o panel cua
// nguoi duyet). Them hai cho:
//   * Chi tiet phieu NHAP: nhanh `cap.can_submit` cua actionPanelHTML noi them EcAddFile.buttonHTML(cap).
//   * Form TAO MOI / sua nhap / sua de gui lai: khoi Tom tat A1 nhan them o thu 3
//       EcSummary.cardHTML(id, actions, EcApprovalLinks.formHTML({name, cap, call, save}))
//     - co ma + capability (get_detail cua trang)  -> ve dung blockHTML(cap) (chip + nut, theo server);
//     - chua co ma (form moi) -> [THAY THE 26/11 toi, xem doan duoi] nut "Gan phieu duyet": bam -> `save(done)` = saveDraft(false, done) CUA
//       TRANG (dung duong luu nhap san co, loi validate bao nhu nut Luu nhap; thanh cong goi done(name)
//       va KHONG chuyen trang) -> lay capability that qua call("get_detail") -> mo hop chon phieu.
//       Form van o trang thai sua nhap, du lieu da nhap giu nguyen.
//
// 26/11/2026 (toi) - KHONG BAT DIEN DU FORM MOI DUOC GAN. Luu nhap truoc vap truong bat buoc cua
// DocType (vd EC Payment Request: Ly do / So tien / Ngay / STK...) -> hop "Message" tieng Anh tho. Nay:
//   * form CHUA co ma: bam nut -> mo hop chon NGAY (search_linkable khong host: chi phieu nguoi xem
//     duoc). Phieu chon duoc GIU TAM tren form (chip "Sẽ gắn khi lưu", go duoc) - chua ghi gi len server.
//   * lan dau trang luu nhap thanh cong (nut Luu nhap, Gui = luu nhap roi submit_request, "Tiep tuc"...)
//     -> gan cac phieu tam bang DUNG link_approval (server kiem quyen lai day du) TRUOC khi tra ket qua
//     luu ve cho trang, nen voi Gui: luu -> gan -> submit_request (assert_host_submittable thay phieu
//     gan). Gan loi -> bao ro phieu nao; viec luu / gui van tiep tuc.
//   * form DA co ma: nhu cu (mo hop gan thang).
//   Cach chen giua "luu" va "submit" ma khong sua 31 trang: boc window.frappe.call (xem pendingHook).
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
        if (!r.ok) {
          // Giu status / exc_type / _server_messages de EcApprovalUI.errorText nhan ra 503 (dang cap nhat),
          // truong bat buoc... thay vi chi con chuoi tho.
          var er = new Error(serverMsg(j) || "Không thực hiện được. Thử lại sau.");
          er.status = r.status; er.exc_type = (j && j.exc_type) || "";
          if (j && j._server_messages) er._server_messages = j._server_messages;
          throw er;
        }
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
    var btn = can ? '<button type="button" class="btn ec-aplk-add" data-ec-aplk-open><svg class="ec-btn-ic" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.5 1.5"/><path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.5-1.5"/></svg>Gắn phiếu duyệt</button>' : "";
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

  // name phieu chu -> capability moi nhat ma widget biet (sau get_detail / gan / go / ghi ly do). Form tao
  // ve lai (go phim, doi loai...) doc lai tu day nen chip khong bien mat / khong hien ban cu.
  var capCache = {};
  function remember(h, cap) {
    if (!h || !h.name || !cap) return;
    capCache[h.name] = { approval_links: cap.approval_links || [], can_link_approval: !!cap.can_link_approval,
      approval_link_host: cap.approval_link_host || { doctype: h.doctype, name: h.name } };
  }

  function redraw(h, cap) {
    if (!h || !h.box) return;
    if (cap && cap.chips) cap = { approval_links: cap.chips, can_link_approval: true,
      approval_link_host: { doctype: h.doctype, name: h.name } };
    if (cap && cap.approval_links) { remember(h, cap); h.box.innerHTML = innerHTML(cap); return Promise.resolve(); }
    return api("list_approval_links", { host_doctype: h.doctype, host_name: h.name }).then(function (c) {
      remember(h, c || {});
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
          var note = r.already_linked ? (h.pending ? " (đã chọn)" : " (đã gắn)") : (!r.can_attach ? " (chỉ người gửi phiếu riêng tư mới gắn được)" : "");
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
      api("search_linkable", h.pending ? { q: q.value.trim(), box: box.value }
        : { host_doctype: h.doctype, host_name: h.name, q: q.value.trim(), box: box.value })
        .then(function (d) {
          if (my !== seq) return;
          rows = (d && d.rows) || [];
          if (h.pending) rows.forEach(function (r) { if (pendingIndex(r.request) >= 0) r.already_linked = true; });
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
      if (h.pending) {                       // form moi: giu tam, gan that sau khi luu
        addPending(picked, picked.private ? (sh ? sh.value : "") : "0");
        close();
        toast("Phiếu " + picked.code + " sẽ được gắn khi bạn lưu nháp hoặc gửi.");
        redrawForm();
        return;
      }
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

  // ---- form tao moi / sua nhap / sua de gui lai (26/11/2026) ----------------------------
  // Moi trang form chi co MOT form dang mo -> giu mot ban { name, call, save } cua lan ve gan nhat.
  var form = null;

  // ---- phieu giu tam tren form moi (chua co ma) ------------------------------------------
  // [{ request, code, title, private, share, status_label, bad }] - chi trong trinh duyet; mat khi tai lai trang.
  var pending = [];
  function pendingIndex(req) {
    for (var i = 0; i < pending.length; i++) if (pending[i].request === req) return i;
    return -1;
  }
  function addPending(r, share) {
    if (pendingIndex(r.request) >= 0) return;
    pending.push({ request: r.request, code: r.code, title: r.title || null, private: !!r.private,
      share: share, status_label: r.status_label || "", bad: !!r.bad });
    pendingHook();
  }

  function pendingChipHTML(p) {
    var title = p.title ? '<span class="ec-aplk-title">' + esc(p.title) + "</span>"
      : (p.private ? '<span class="ec-aplk-title ec-aplk-muted">Phiếu riêng tư</span>' : "");
    var meta = '<span class="ec-aplk-status' + (p.bad ? " bad" : "") + '">' + esc(p.status_label) + "</span>"
      + '<span class="ec-aplk-tag">Sẽ gắn khi lưu</span>'
      + (p.private ? '<span class="ec-aplk-tag">' + (p.share === "1" ? "Người duyệt được đọc" : "Chỉ hiện mã") + "</span>" : "");
    return '<div class="ec-aplk-chip ec-aplk-chip--pending' + (p.private ? " ec-aplk-chip--private" : "") + '" role="listitem">'
      + '<div class="ec-aplk-line"><span class="ec-aplk-code">' + esc(p.code) + "</span>" + title
      + '<button type="button" class="ec-aplk-x" data-ec-aplk-unpend="' + esc(p.request) + '" aria-label="Bỏ chọn phiếu '
      + esc(p.code) + '" title="Bỏ chọn">×</button></div><div class="ec-aplk-meta">' + meta + "</div></div>";
  }

  function newBlockHTML() {
    var list = pending.length ? '<div class="ec-aplk-list" role="list">' + pending.map(pendingChipHTML).join("") + "</div>" : "";
    return '<div class="ec-aplk ec-aplk--new"><div class="ec-aplk-h">Phiếu duyệt đính kèm' + (pending.length ? " (" + pending.length + ")" : "") + "</div>"
      + '<p class="ec-aplk-note">Dùng phiếu đã duyệt (vd Phê duyệt đột xuất của CEO) làm chứng từ cho phiếu này. '
      + "Phiếu chọn sẽ được gắn khi bạn lưu nháp hoặc gửi — không cần nhập xong form trước.</p>" + list
      + '<button type="button" class="btn ec-aplk-add" data-ec-aplk-create><svg class="ec-btn-ic" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.5 1.5"/><path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.5-1.5"/></svg>Gắn phiếu duyệt</button></div>';
  }

  function redrawForm() {
    var slot = document.querySelector("[data-ec-aplk-form]");
    if (!slot || !form) return;
    var cap = form.name && capCache[form.name];
    slot.innerHTML = form.name && cap ? blockHTML(cap) : newBlockHTML();
  }

  // ---- form tao moi / sua nhap / sua de gui lai (26/11/2026) ----------------------------
  // Moi trang form chi co MOT form dang mo -> giu mot ban { name, call, save } cua lan ve gan nhat.
  var form = null;

  // opts: { name: ma phieu hoac null, cap: capabilities tu get_detail (neu trang dang giu),
  //         call: ham call(method, args) cua trang, save: (cu, khong con dung o form moi) }
  function formHTML(opts) {
    opts = opts || {};
    var name = opts.name || null;
    // Phieu tam chi thuoc form MOI dang mo. Trang chuyen sang ve mot phieu da co ma (mo nhap khac, chi
    // tiet...) ma chua luu form moi -> bo, khong de lan luu cua phieu kia gan nham.
    if (name && pending.length) pending = [];
    form = { name: name, call: opts.call, save: opts.save };
    var cap = (name && capCache[name]) || opts.cap || null;
    var inner;
    if (name && cap && cap.approval_link_host) inner = blockHTML(cap);           // quyen theo server
    else if (typeof opts.call === "function") inner = newBlockHTML();
    else inner = "";
    return inner ? '<div class="ec-aplk-slot" data-ec-aplk-form>' + inner + "</div>" : "";
  }

  async function capabilityOf(name) {
    var det = await form.call("get_detail", { name: name });
    var cap = (det && det.capabilities) || {};
    if (cap.approval_link_host) remember({ name: name, doctype: cap.approval_link_host.doctype }, cap);
    return cap;
  }

  async function startFromForm(btn) {
    if (busy || !form || btn.disabled) return;
    var slot = btn.closest ? btn.closest("[data-ec-aplk-form]") : null;
    if (!form.name) {                      // form moi: mo hop ngay, khong luu nhap
      openModal({ pending: true, box: slot ? slot.querySelector(".ec-aplk") : null });
      return;
    }
    var label = btn.textContent;
    busy = true;
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    try {
      btn.textContent = "Đang mở…";
      var cap = await capabilityOf(form.name);
      var host = cap.approval_link_host;
      if (slot) slot.innerHTML = blockHTML(cap);
      if (!cap.can_link_approval || !host || !host.doctype || !host.name) {
        toast("Bạn không gắn được phiếu duyệt vào phiếu này ở trạng thái hiện tại.", true);
        return;
      }
      var box = slot ? slot.querySelector(".ec-aplk") : null;
      busy = false;
      openModal({ box: box, doctype: host.doctype, name: host.name });
    } catch (e) {
      toast(errText(e, "Không mở được phần gắn phiếu duyệt. Thử lại sau."), true);
    } finally {
      busy = false;
      if (btn.isConnected) {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
        btn.textContent = label;
      }
    }
  }

  // ---- gan cac phieu tam ngay sau lan luu dau tien -----------------------------------------
  // Tra ve Promise KHONG BAO GIO reject: loi gan chi duoc bao, khong lam hong viec luu / gui.
  async function flushPending(name) {
    var items = pending.slice();
    pending = [];
    if (!items.length) return;
    if (form && !form.name) form.name = name;
    var failed = [], okCodes = [], host = null, lastChips = null;
    try {
      var cap = await capabilityOf(name);
      host = cap.approval_link_host;
      if (!host || !host.doctype || !host.name) throw new Error("");
    } catch (e) {
      toast("Đã lưu " + name + " nhưng chưa gắn được phiếu " + items.map(function (p) { return p.code; }).join(", ")
        + ". Mở phiếu và bấm Gắn phiếu duyệt lại.", true);
      return;
    }
    for (var i = 0; i < items.length; i++) {
      var p = items[i];
      try {
        var d = await api("link_approval", { host_doctype: host.doctype, host_name: host.name,
          target_request: p.request, share: p.private ? p.share : "0" }, true);
        okCodes.push(p.code);
        if (d && d.chips) lastChips = d.chips;
      } catch (e) {
        failed.push(p.code + " (" + errText(e, "không gắn được") + ")");
      }
    }
    if (lastChips) remember({ name: host.name, doctype: host.doctype },
      { approval_links: lastChips, can_link_approval: true, approval_link_host: host });
    if (failed.length) {
      toast((okCodes.length ? "Đã gắn " + okCodes.join(", ") + ". " : "")
        + "Chưa gắn được: " + failed.join("; ") + ". Mở phiếu " + name + " để gắn lại.", true);
    } else {
      toast("Đã gắn " + okCodes.length + " phiếu duyệt vào " + name + ": " + okCodes.join(", ") + ".");
    }
    redrawForm();
  }

  // Boc window.frappe.call MOT lan, chi khi co phieu tam. Chi chan dung cuoc goi `<ns>.save_draft`
  // KHONG kem `name` (lan luu dau cua form moi) tra ve `message.name`: chen flushPending truoc khi
  // tra ket qua cho trang (trang Gui chi goi submit_request sau do). Moi cuoc goi khac / khong co
  // phieu tam -> tra nguyen promise cua frappe, khong doi gi.
  // Ly do boc o day thay vi sua trang: 31 trang tu goi frappe.call trong saveDraft (khong qua `call`
  // truyen cho formHTML); sua tung trang = 31 lan sua HTML + resync. Rui ro: neu sau nay trang luu
  // nhap qua duong khac frappe.call / ten khac save_draft thi phieu tam khong duoc gan (chip van hien
  // tren form; test_gan_phieu_nguoi_lap.mjs khoa ca 31 trang).
  var hooked = false;
  function isFirstSave(o) {
    return o && typeof o === "object" && /\.save_draft$/.test(String(o.method || ""))
      && !(o.args && o.args.name);
  }
  function pendingHook() {
    var fr = window.frappe;
    if (hooked || !fr || typeof fr.call !== "function") return;
    var orig = fr.call;
    fr.call = function (o) {
      var p = orig.apply(this, arguments);
      if (!pending.length || !isFirstSave(o) || !p || typeof p.then !== "function") return p;
      return p.then(function (r) {
        var nm = r && r.message && r.message.name;
        if (!nm || !pending.length) return r;
        return flushPending(nm).then(function () { return r; }, function () { return r; });
      });
    };
    hooked = true;
  }

  // ---- su kien (uy quyen tren document) ------------------------------------------------
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t || !t.closest) return;
    var create = t.closest("[data-ec-aplk-create]");
    if (create) { e.preventDefault(); e.stopPropagation(); startFromForm(create); return; }
    var unp = t.closest("[data-ec-aplk-unpend]");
    if (unp) {
      e.preventDefault(); e.stopPropagation();
      var k = pendingIndex(unp.getAttribute("data-ec-aplk-unpend"));
      if (k >= 0) pending.splice(k, 1);
      redrawForm();
      return;
    }
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

  window.EcApprovalLinks = { blockHTML: blockHTML, chipHTML: chipHTML, openModal: openModal, formHTML: formHTML,
    pendingCount: function () { return pending.length; } };
})();
