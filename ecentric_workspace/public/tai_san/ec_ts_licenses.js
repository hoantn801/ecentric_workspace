// Copyright (c) 2026, eCentric and contributors
// ec_ts_licenses.js -- trang /tai-san/ban-quyen: bang ban quyen phan mem + ngan chi tiet (cho da cap,
// gia han, sua, huy). URL: ?stage=&category=&q=&id=. Quyen, giai doan han, chi phi deu do server tinh;
// truong tien chi co trong du lieu khi nguoi xem co quyen chi phi.
(function () {
  "use strict";
  var T = window.ECTs, esc = T.esc;
  var CHIPS = [["", "Tất cả"], ["due", "Sắp hết hạn"], ["expired", "Đã quá hạn"], ["perpetual", "Vĩnh viễn"], ["cancelled", "Đã huỷ"]];
  var st = { stage: T.param("stage"), category: T.param("category"), q: T.param("q") };
  var cur = { id: T.param("id"), detail: null };
  var root, kpiBox, listBox, drawer, last = null, qTimer = null, emps = null;

  function money(v) { return v == null || v === "" ? "" : T.fmtMoney(v); }
  function fdate(s) { return esc(T.fmtDate(s)); }
  function leadNote() {
    var ld = (last && last.lead_days) || {};
    return "Nhắc trước " + (ld["default"] || 30) + " ngày (gói theo tháng: " + (ld.short || 10) + " ngày).";
  }

  // ------------------------------------------------------------ danh sach --
  function shell() {
    root.innerHTML = '<div class="ts-wrap">' +
      '<div class="ts-head"><div class="ts-head-main"><h1 class="ts-title">Bản quyền phần mềm</h1>' +
      '<div class="ts-sub">Thuê bao và bản quyền vĩnh viễn, ai đang được cấp chỗ, khi nào hết hạn.</div></div>' +
      '<div class="ts-filters" data-actions></div></div>' +
      '<div data-kpi></div>' +
      '<div class="ts-chips" data-chips role="group" aria-label="Lọc theo hạn">' + CHIPS.map(function (c) {
        return '<button type="button" class="ts-chip' + (c[0] === st.stage ? " on" : "") + '" data-s="' + esc(c[0]) + '">' + esc(c[1]) + "</button>";
      }).join("") + "</div>" +
      '<div class="ts-filters"><input class="ts-in" type="search" data-q placeholder="Tên, hãng, tài khoản, người phụ trách…" aria-label="Tìm bản quyền" value="' + esc(st.q) + '" style="min-width:260px">' +
      '<select class="ts-sel" data-cat aria-label="Nhóm"><option value="">Tất cả nhóm</option></select></div>' +
      '<div class="ts-split"><div class="ts-left"><div class="ts-card" style="padding:0" data-list></div>' +
      '<div class="ts-note" style="margin-top:10px">' + esc(leadNote()) + " Người phụ trách và quản lý tài sản nhận thông báo.</div></div>" +
      '<aside class="ts-drawer" data-drawer hidden aria-label="Chi tiết bản quyền"></aside></div></div>';
    kpiBox = root.querySelector("[data-kpi]");
    listBox = root.querySelector("[data-list]");
    drawer = root.querySelector("[data-drawer]");
    root.querySelector("[data-chips]").addEventListener("click", function (e) {
      var b = e.target.closest(".ts-chip"); if (!b) return;
      setStage(b.getAttribute("data-s"));
    });
    kpiBox.addEventListener("click", function (e) {
      var b = e.target.closest("[data-kstage]"); if (b) setStage(b.getAttribute("data-kstage"));
    });
    root.querySelector("[data-q]").addEventListener("input", function (e) {
      clearTimeout(qTimer);
      var v = e.target.value;
      qTimer = setTimeout(function () { st.q = v; T.setParam("q", v); loadList(); }, 300);
    });
    root.querySelector("[data-cat]").addEventListener("change", function (e) {
      st.category = e.target.value; T.setParam("category", st.category); loadList();
    });
    listBox.addEventListener("click", function (e) {
      var tr = e.target.closest("tr[data-name]");
      if (tr) openDrawer(tr.getAttribute("data-name"));
    });
    listBox.addEventListener("keydown", function (e) {
      var tr = e.target.closest && e.target.closest("tr[data-name]");
      if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openDrawer(tr.getAttribute("data-name")); }
    });
  }

  function setStage(s) {
    st.stage = s || ""; T.setParam("stage", st.stage);
    T.qsa(root, "[data-chips] .ts-chip").forEach(function (x) { x.classList.toggle("on", x.getAttribute("data-s") === st.stage); });
    loadList();
  }

  function filters() {
    var f = { category: st.category, q: st.q };
    if (st.stage === "cancelled") f.status = "Cancelled"; else f.stage = st.stage;
    return f;
  }

  function loadList() {
    listBox.innerHTML = '<div style="padding:16px">' + T.skel(6) + "</div>";
    return T.get("licenses", { filters: JSON.stringify(filters()) }).then(function (d) {
      last = d;
      drawActions(d);
      drawKpi(d);
      var sel = root.querySelector("[data-cat]");
      sel.innerHTML = '<option value="">Tất cả nhóm</option>' + (d.categories || []).map(function (c) {
        return '<option value="' + esc(c) + '"' + (c === st.category ? " selected" : "") + ">" + esc(c) + "</option>";
      }).join("");
      drawList(d);
    }, function (e) {
      if (T.toMineIfDenied(e)) return;
      listBox.innerHTML = '<div style="padding:16px">' + T.errBox(e, true) + "</div>";
      var b = listBox.querySelector("[data-retry]"); if (b) b.addEventListener("click", loadList);
    });
  }

  function drawActions(d) {
    var box = root.querySelector("[data-actions]");
    if (box.childNodes.length || !(d.can && d.can.manage)) return;
    box.innerHTML = '<button type="button" class="ts-btn ts-primary" data-new>' + T.icon("plus") + "Thêm bản quyền</button>";
    box.querySelector("[data-new]").addEventListener("click", function () {
      licenseForm(null).then(function (r) { if (r && r.license) { loadList(); openDrawer(r.license); } });
    });
  }

  function drawKpi(d) {
    var s = d.summary || {}, cost = s.monthly_cost != null;
    function k(label, value, sub, stage) {
      return '<button type="button" class="ts-kpi"' + (stage != null ? ' data-kstage="' + esc(stage) + '"' : "") + '><div class="ts-kpi-l">' + esc(label) + "</div>" +
        '<div class="ts-kpi-v">' + value + "</div>" + (sub ? '<div class="ts-kpi-s">' + esc(sub) + "</div>" : "") + "</button>";
    }
    kpiBox.innerHTML = '<div class="ts-grid ' + (cost ? "ts-g5" : "ts-g4") + '">' +
      k("Đang dùng", T.fmtNum(s.total), "Không tính bản quyền đã huỷ", "") +
      k("Sắp hết hạn", '<span' + (s.due ? ' style="color:#92400e"' : "") + ">" + T.fmtNum(s.due) + "</span>", "", "due") +
      k("Đã quá hạn", '<span' + (s.expired ? ' class="ts-bad-text"' : "") + ">" + T.fmtNum(s.expired) + "</span>", "", "expired") +
      k("Chỗ đã cấp", T.fmtNum(s.used) + '<span class="ts-muted" style="font-size:18px"> / ' + T.fmtNum(s.seats) + "</span>",
        s.seats ? "Còn trống " + T.fmtNum(Math.max(0, (s.seats || 0) - (s.used || 0))) + " chỗ" : "", null) +
      (cost ? k("Chi phí tháng", T.fmtMillion(s.monthly_cost), "Quy đổi theo kỳ thanh toán", null) : "") + "</div>";
  }

  function drawList(d) {
    var rows = d.rows || [], cost = !!(d.can && d.can.see_cost);
    if (!rows.length) {
      listBox.innerHTML = '<div class="ts-empty" style="padding:32px">' + (st.stage || st.category || st.q ? "Không có bản quyền nào khớp bộ lọc." :
        "Chưa có bản quyền nào." + (d.can && d.can.manage ? " Bấm Thêm bản quyền để nhập." : "")) + "</div>";
      return;
    }
    var head = "<tr><th>Bản quyền</th><th>Nhóm</th><th>Loại / kỳ</th><th class=\"ts-num\">Chỗ</th><th>Hết hạn</th><th>Phụ trách</th>" +
      (cost ? '<th class="ts-num">Chi phí / tháng</th>' : "") + "</tr>";
    var body = rows.map(function (r) {
      var full = r.seats && r.used >= r.seats;
      return '<tr class="ts-click' + (r.name === cur.id ? " on" : "") + '" data-name="' + esc(r.name) + '" tabindex="0">' +
        '<td><span class="ts-strong">' + esc(r.license_name || r.name) + "</span>" + (r.vendor ? '<div class="ts-note">' + esc(r.vendor) + "</div>" : "") + "</td>" +
        "<td>" + esc(r.category || "") + "</td>" +
        "<td>" + esc(r.type_label || r.license_type || "") + (r.cycle_label ? '<div class="ts-note">' + esc(r.cycle_label) + (r.auto_renew ? " · tự gia hạn" : "") + "</div>" : "") + "</td>" +
        '<td class="ts-num' + (full ? " ts-strong" : "") + '">' + T.fmtNum(r.used) + " / " + T.fmtNum(r.seats) + "</td>" +
        "<td>" + (r.expiry_date ? '<div class="ts-row" style="gap:6px;flex-wrap:nowrap"><span>' + fdate(r.expiry_date) + "</span>" + T.licPill(r) + "</div>" +
          '<div class="ts-note' + (r.stage === "Expired" ? " ts-bad-text" : "") + '">' + esc(T.licDays(r.days_left)) + "</div>" : T.licPill(r)) + "</td>" +
        "<td>" + esc(r.owner_name || r.owner_employee || "—") + (r.department ? '<div class="ts-note">' + esc(r.department) + "</div>" : "") + "</td>" +
        (cost ? '<td class="ts-num">' + money(r.monthly_cost) + "</td>" : "") + "</tr>";
    }).join("");
    listBox.innerHTML = '<div class="ts-table-wrap"><table class="ts-table"><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";
  }

  // ------------------------------------------------------------- ngan phai --
  function openDrawer(name) {
    cur.id = name; cur.detail = null;
    T.setParam("id", name);
    T.qsa(listBox, "tr[data-name]").forEach(function (tr) { tr.classList.toggle("on", tr.getAttribute("data-name") === name); });
    drawer.hidden = false;
    drawer.innerHTML = '<div class="ts-dbody">' + T.skel(6) + "</div>";
    loadDetail();
  }
  function closeDrawer() {
    cur.id = ""; cur.detail = null; drawer.hidden = true; drawer.innerHTML = ""; T.setParam("id", "");
    T.qsa(listBox, "tr.on").forEach(function (tr) { tr.classList.remove("on"); });
  }
  function loadDetail() {
    var name = cur.id;
    return T.get("license_detail", { name: name }).then(function (d) {
      if (name !== cur.id) return;
      cur.detail = d; drawDrawer();
    }, function (e) {
      if (T.toMineIfDenied(e)) return;
      drawer.innerHTML = '<div class="ts-dbody">' + T.errBox(e, true) + '<button type="button" class="ts-btn" data-x>Đóng</button></div>';
      var b = drawer.querySelector("[data-retry]"); if (b) b.addEventListener("click", loadDetail);
      drawer.querySelector("[data-x]").addEventListener("click", closeDrawer);
    });
  }
  function refreshAll() { loadDetail(); loadList(); }

  function kv(label, value) { return "<div><span>" + esc(label) + "</span><b>" + (value == null || value === "" ? "—" : value) + "</b></div>"; }

  function drawDrawer() {
    var d = cur.detail, L = d.license || {}, can = d.can || {};
    var live = L.status !== "Cancelled", sub = L.license_type === "Subscription";
    var hasCost = Object.prototype.hasOwnProperty.call(L, "cost_per_cycle");
    var acts = [];
    if (can.manage && live && sub) acts.push('<button type="button" class="ts-btn ts-primary" data-renew>Gia hạn</button>');
    if (can.manage) acts.push('<button type="button" class="ts-btn" data-edit>Sửa</button>');
    else if (can.finance && hasCost) acts.push('<button type="button" class="ts-btn" data-edit>Sửa chi phí</button>');
    if (can.manage && live) acts.push('<button type="button" class="ts-btn ts-danger" data-cancel>Huỷ bản quyền</button>');
    var seats = d.seats || [], hist = d.history || [], ren = d.renewals || [];
    drawer.innerHTML = '<div class="ts-dhead"><div class="ts-row"><div style="flex:1;min-width:0"><div class="ts-dname">' + esc(L.license_name || L.name) + "</div>" +
      '<div class="ts-note">' + esc([L.vendor, L.category, L.name].filter(Boolean).join(" · ")) + "</div></div>" +
      '<button type="button" class="ts-btn ts-sm" data-x aria-label="Đóng">' + T.icon("x") + "</button></div>" +
      '<div class="ts-row">' + T.licPill(L) + (L.status === "Expired" ? '<span class="ts-pill ts-red">' + esc(L.status_label || "Hết hạn") + "</span>" : "") +
      (L.expiry_date && live ? '<span class="ts-note">' + esc(T.licDays(L.days_left)) + "</span>" : "") + "</div></div>" +
      '<div class="ts-dbody">' +
      '<div class="ts-info">' +
      kv("Loại", esc(L.type_label || L.license_type || "")) + kv("Kỳ thanh toán", esc(L.cycle_label || "")) +
      kv("Số chỗ", T.fmtNum(L.used) + " / " + T.fmtNum(L.seats) + (L.free ? ' <span class="ts-muted">(trống ' + T.fmtNum(L.free) + ")</span>" : "")) +
      kv("Tự gia hạn", sub ? (L.auto_renew ? "Có" : "Không") : "") +
      kv("Bắt đầu", fdate(L.start_date)) + kv("Hết hạn", fdate(L.expiry_date)) +
      kv("Người phụ trách", esc(L.owner_name || L.owner_employee || "")) + kv("Phòng ban", esc(L.department || "")) +
      kv("Tài khoản", esc(L.account || "")) + kv("Nơi lưu key", esc(L.key_location || "")) +
      (hasCost ? kv("Chi phí mỗi kỳ", money(L.cost_per_cycle)) + kv("Quy ra tháng", money(L.monthly_cost)) + kv("Hoá đơn NCC", esc(L.supplier_invoice || "")) : "") +
      "</div>" +
      (L.note ? '<div class="ts-infobox" style="white-space:pre-line">' + esc(L.note) + "</div>" : "") +
      (sub && live ? '<div class="ts-note">' + esc(leadNote()) + (L.lead_days ? " Bản quyền này nhắc trước " + L.lead_days + " ngày." : "") + "</div>" : "") +
      (acts.length ? '<div class="ts-actions">' + acts.join("") + "</div>" : "") +
      // cho dang cap
      "<section><div class=\"ts-eb\">Đang cấp · " + T.fmtNum(seats.length) + " / " + T.fmtNum(L.seats) + '<span class="ts-sp"></span>' +
      (can.manage && L.status === "Active" ? '<button type="button" class="ts-btn ts-sm ts-wash" data-assign>' + T.icon("plus") + "Cấp cho nhân viên</button>" : "") + "</div>" +
      (seats.length ? seats.map(function (s) {
        return '<div class="ts-li"><div class="ts-li-main"><b class="ts-strong">' + esc(s.employee_name || s.employee) + "</b>" +
          '<div class="ts-note">' + esc([s.department, s.assigned_on ? "cấp " + T.fmtDate(s.assigned_on) : "", s.note].filter(Boolean).join(" · ")) + "</div></div>" +
          (can.manage ? '<button type="button" class="ts-btn ts-sm" data-revoke="' + esc(s.name) + '">Thu lại</button>' : "") + "</div>";
      }).join("") : '<div class="ts-empty">Chưa cấp cho ai.</div>') + "</section>" +
      // gia han
      (sub || ren.length ? "<section><div class=\"ts-eb\">Lịch sử gia hạn</div>" + (ren.length ? '<ul class="ts-tl">' + ren.map(function (r) {
        return "<li><div><b class=\"ts-strong\">" + fdate(r.renewed_on) + "</b> · " + (r.old_expiry ? fdate(r.old_expiry) + " → " : "đến ") + fdate(r.new_expiry) + "</div>" +
          '<div class="ts-note">' + esc([r.cost != null ? T.fmtMoney(r.cost) : "", r.renewed_by_name || r.renewed_by, r.note].filter(Boolean).join(" · ")) + "</div></li>";
      }).join("") + "</ul>" : '<div class="ts-empty">Chưa gia hạn lần nào.</div>') + "</section>" : "") +
      // da thu
      (hist.length ? "<section><div class=\"ts-eb\">Đã thu lại · " + hist.length + "</div>" + hist.map(function (s) {
        return '<div class="ts-li"><div class="ts-li-main">' + esc(s.employee_name || s.employee) +
          '<div class="ts-note">' + esc([s.assigned_on ? "cấp " + T.fmtDate(s.assigned_on) : "", s.revoked_on ? "thu " + T.fmtDate(s.revoked_on) : "", s.note].filter(Boolean).join(" · ")) + "</div></div></div>";
      }).join("") + "</section>" : "") +
      "</div>";
    drawer.querySelector("[data-x]").addEventListener("click", closeDrawer);
    drawer.onclick = onDrawerClick;
  }

  function onDrawerClick(e) {
    var d = cur.detail; if (!d) return;
    var L = d.license, t;
    if (e.target.closest("[data-renew]")) { renewModal(d).then(function (r) { if (r) refreshAll(); }); return; }
    if (e.target.closest("[data-edit]")) { licenseForm(d).then(function (r) { if (r) refreshAll(); }); return; }
    if (e.target.closest("[data-cancel]")) { cancelModal(L).then(function (r) { if (r) refreshAll(); }); return; }
    if ((t = e.target.closest("[data-assign]"))) {
      T.pickEmployee("Cấp " + (L.license_name || L.name) + ": chọn nhân viên").then(function (emp) {
        if (!emp) return;
        T.post("assign_license", { name: L.name, employee: emp, note: "" }).then(function () { T.toast("Đã cấp bản quyền."); refreshAll(); },
          function (er) { T.toast(T.msg(er), true); });
      });
      return;
    }
    if ((t = e.target.closest("[data-revoke]"))) {
      var seat = (d.seats || []).filter(function (s) { return s.name === t.getAttribute("data-revoke"); })[0];
      if (seat) revokeModal(L, seat).then(function (r) { if (r) refreshAll(); });
    }
  }

  // ------------------------------------------------------------ hop thoai --
  function revokeModal(L, seat) {
    return new Promise(function (resolve) {
      T.modal("Thu lại bản quyền", '<p class="ts-muted">' + esc(L.license_name || L.name) + " · " + esc(seat.employee_name || seat.employee) + "</p>" +
        '<label class="ts-lbl">Ghi chú<textarea class="ts-ta" name="note" maxlength="500" placeholder="Ví dụ: chuyển bộ phận, không dùng nữa…"></textarea></label>' +
        '<div class="ts-note">Nhớ gỡ người này khỏi tài khoản trên trang của hãng nếu cần.</div>',
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>Thu lại</button>',
        function (el, close) {
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          el.querySelector("[data-ok]").addEventListener("click", function (ev) {
            var btn = ev.currentTarget; T.busy(btn, true);
            T.post("revoke_license_seat", { seat: seat.name, note: el.querySelector('[name="note"]').value })
              .then(function (r) { close(); T.toast("Đã thu lại."); resolve(r || true); }, function (er) { T.busy(btn, false); T.toast(T.msg(er), true); });
          });
        });
    });
  }

  function cancelModal(L) {
    return new Promise(function (resolve) {
      T.modal("Huỷ bản quyền", '<p class="ts-muted">' + esc(L.license_name || L.name) + "</p>" +
        '<div class="ts-warn">Huỷ là ngừng dùng: mọi chỗ đang cấp (' + T.fmtNum(L.used) + ") được thu lại, lịch sử vẫn giữ. Không mở lại được trên trang.</div>" +
        '<label class="ts-lbl">Lý do<textarea class="ts-ta" name="note" maxlength="500"></textarea></label>',
        '<button type="button" class="ts-btn" data-close>Thôi</button><button type="button" class="ts-btn ts-danger" data-ok>Huỷ bản quyền</button>',
        function (el, close) {
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          el.querySelector("[data-ok]").addEventListener("click", function (ev) {
            var btn = ev.currentTarget; T.busy(btn, true);
            T.post("cancel_license", { name: L.name, note: el.querySelector('[name="note"]').value })
              .then(function (r) { close(); T.toast("Đã huỷ bản quyền" + (r && r.revoked ? ", thu lại " + r.revoked + " chỗ." : ".")); resolve(r || true); },
                function (er) { T.busy(btn, false); T.toast(T.msg(er), true); });
          });
        });
    });
  }

  function renewModal(d) {
    var L = d.license;
    return new Promise(function (resolve) {
      T.modal("Gia hạn · " + (L.license_name || L.name),
        '<p class="ts-muted">Hạn hiện tại: ' + (L.expiry_date ? fdate(L.expiry_date) + " · " + esc(T.licDays(L.days_left)) : "—") + (L.cycle_label ? " · " + esc(L.cycle_label) : "") + "</p>" +
        '<div class="ts-form"><label class="ts-lbl">Hạn mới<input class="ts-in" type="date" name="new_expiry" value="' + esc(d.suggested_expiry || "") + '" required></label>' +
        '<label class="ts-lbl">Chi phí kỳ mới (₫)<input class="ts-in" name="cost" inputmode="numeric" placeholder="Trống = giữ như cũ"></label>' +
        '<label class="ts-lbl ts-full">Ghi chú<textarea class="ts-ta" name="note" maxlength="500" placeholder="Số hoá đơn, đổi gói…"></textarea></label></div>' +
        '<div class="ts-note">' + (d.suggested_expiry ? "Hạn mới gợi ý theo kỳ thanh toán. " : "") + "Gia hạn xong, mốc nhắc tính lại theo hạn mới.</div>",
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>Gia hạn</button>',
        function (el, close) {
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          el.querySelector("[data-ok]").addEventListener("click", function (ev) {
            var btn = ev.currentTarget, exp = el.querySelector('[name="new_expiry"]').value;
            if (!exp) { T.toast("Chọn hạn mới.", true); return; }
            var cost = String(el.querySelector('[name="cost"]').value || "").replace(/[^\d]/g, "");
            T.busy(btn, true);
            T.post("renew_license", { name: L.name, new_expiry: exp, cost: cost, note: el.querySelector('[name="note"]').value })
              .then(function (r) { close(); T.toast("Đã gia hạn đến " + T.fmtDate(r && r.expiry_date || exp) + "."); resolve(r || true); },
                function (er) { T.busy(btn, false); T.toast(T.msg(er), true); });
          });
        });
    });
  }

  function employees() {
    if (!emps) emps = T.pickList("employees");
    return emps;
  }

  // Them (d = null) hoac sua (d = license_detail). Chi gui truong nguoi dung thay / duoc phep sua:
  // truong tien vang mat trong du lieu thi KHONG gui (tranh ghi de bang rong).
  function licenseForm(d) {
    var L = d ? d.license : {}, can = d ? (d.can || {}) : ((last && last.can) || {});
    var creating = !d, infoOk = creating || !!can.manage;
    var hasInvoice = creating || Object.prototype.hasOwnProperty.call(L, "supplier_invoice");
    var costOk = creating || !!can.finance;
    var types = (last && last.types) || { Subscription: "Thuê bao (có hạn)", Perpetual: "Vĩnh viễn" };
    var cycles = (last && last.cycles) || { Monthly: "Theo tháng", Quarterly: "Theo quý", Yearly: "Theo năm", Other: "Kỳ khác" };
    var cats = (last && last.categories) || [];
    var ltype = L.license_type || "Subscription";
    var today = new Date().toISOString().slice(0, 10);
    function opt(map, val) {
      return Object.keys(map).map(function (k) { return '<option value="' + esc(k) + '"' + (k === val ? " selected" : "") + ">" + esc(map[k]) + "</option>"; }).join("");
    }
    function inp(name, label, val, extra) {
      return '<label class="ts-lbl' + (extra && extra.full ? " ts-full" : "") + '"' + (extra && extra.sub ? " data-sub" : "") + ">" + esc(label) +
        '<input class="ts-in" name="' + name + '"' + (extra && extra.type ? ' type="' + extra.type + '"' : "") + (extra && extra.num ? ' inputmode="numeric"' : "") +
        ' maxlength="140" value="' + esc(val == null ? "" : val) + '"></label>';
    }
    var body = "";
    if (infoOk) {
      body += (creating ? '<div><div class="ts-lbl" style="margin-bottom:6px">Loại</div><div class="ts-chips" data-type>' + Object.keys(types).map(function (k) {
        return '<button type="button" class="ts-chip' + (k === ltype ? " on" : "") + '" data-v="' + esc(k) + '">' + esc(types[k]) + "</button>";
      }).join("") + "</div></div>" : '<p class="ts-muted">' + esc(L.type_label || ltype) + "</p>") +
        '<div class="ts-form">' + inp("license_name", "Tên bản quyền *", L.license_name, { full: 1 }) +
        inp("vendor", "Hãng / nhà cung cấp", L.vendor) +
        '<label class="ts-lbl">Nhóm<select class="ts-sel" name="category">' + cats.map(function (c) {
          return '<option value="' + esc(c) + '"' + (c === (L.category || "Khác") ? " selected" : "") + ">" + esc(c) + "</option>";
        }).join("") + "</select></label>" +
        '<label class="ts-lbl" data-sub>Kỳ thanh toán<select class="ts-sel" name="billing_cycle">' + opt(cycles, L.billing_cycle || "Yearly") + "</select></label>" +
        inp("seats", "Số chỗ", L.seats || 1, { num: 1 }) +
        inp("start_date", "Ngày bắt đầu", L.start_date || (creating ? today : ""), { type: "date" }) +
        inp("expiry_date", creating ? "Hết hạn *" : "Hết hạn (sửa khi nhập nhầm)", creating ? "" : (L.expiry_date || ""), { type: "date", sub: 1 }) +
        '<label class="ts-lbl">Người phụ trách<div class="ts-row" style="flex-wrap:nowrap"><span class="ts-strong" data-owner-label style="flex:1;min-width:0">' +
        esc(L.owner_name || L.owner_employee || "Chưa chọn") + '</span><button type="button" class="ts-btn ts-sm" data-owner-pick>Chọn</button></div></label>' +
        '<label class="ts-lbl">Phòng ban<select class="ts-sel" name="department"><option value="">—</option>' +
        (L.department ? '<option value="' + esc(L.department) + '" selected>' + esc(L.department) + "</option>" : "") + "</select></label>" +
        '<div class="ts-full" data-owner-host hidden></div>' +
        inp("account", "Tài khoản đăng nhập", L.account) + inp("key_location", "Nơi lưu key / mật khẩu", L.key_location) +
        (hasInvoice ? inp("supplier_invoice", "Hoá đơn NCC", L.supplier_invoice) : "") +
        (costOk ? inp("cost_per_cycle", "Chi phí mỗi kỳ (₫)", L.cost_per_cycle ? Math.round(L.cost_per_cycle) : "", { num: 1 }) : "") +
        '<label class="ts-ck ts-full" data-sub><input type="checkbox" name="auto_renew"' + (L.auto_renew ? " checked" : "") + "> Hãng tự gia hạn (vẫn nhắc để kiểm tra thẻ / hoá đơn)</label>" +
        '<label class="ts-lbl ts-full">Ghi chú<textarea class="ts-ta" name="note" maxlength="1000">' + esc(L.note || "") + "</textarea></label></div>" +
        (creating ? "" : '<div class="ts-note">Gia hạn kỳ mới dùng nút Gia hạn (có lưu lịch sử); ô Hết hạn ở đây chỉ để sửa khi nhập nhầm. Chi phí chỉ Finance / HOF sửa sau khi nhập.</div>');
    } else {
      body += '<p class="ts-muted">' + esc(L.license_name || L.name) + '</p><div class="ts-form">' + inp("cost_per_cycle", "Chi phí mỗi kỳ (₫)", L.cost_per_cycle ? Math.round(L.cost_per_cycle) : "", { num: 1 }) + "</div>";
    }
    return new Promise(function (resolve) {
      T.modal(creating ? "Thêm bản quyền" : "Sửa · " + (L.license_name || L.name), body,
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>' + (creating ? "Thêm" : "Lưu") + "</button>",
        function (el, close) {
          var owner = L.owner_employee || "";
          function v(n) { var f = el.querySelector('[name="' + n + '"]'); return f ? f.value : ""; }
          function syncType() {
            var perp = ltype === "Perpetual";
            T.qsa(el, "[data-sub]").forEach(function (x) { x.hidden = perp; });
          }
          if (infoOk) {
            syncType();
            var tb = el.querySelector("[data-type]");
            if (tb) tb.addEventListener("click", function (e) {
              var b = e.target.closest(".ts-chip"); if (!b) return;
              ltype = b.getAttribute("data-v");
              T.qsa(tb, ".ts-chip").forEach(function (x) { x.classList.toggle("on", x === b); });
              syncType();
            });
            var dep = el.querySelector('[name="department"]');
            employees().then(function (rows) {
              var seen = {}, list = [];
              rows.forEach(function (r) { if (r.department && !seen[r.department]) { seen[r.department] = 1; list.push(r.department); } });
              list.sort();
              if (L.department && !seen[L.department]) list.unshift(L.department);
              var curDep = dep.value;
              dep.innerHTML = '<option value="">—</option>' + list.map(function (x) {
                return '<option value="' + esc(x) + '"' + (x === curDep ? " selected" : "") + ">" + esc(x) + "</option>";
              }).join("");
            }, function () { /* giu lua chon hien tai */ });
            el.querySelector("[data-owner-pick]").addEventListener("click", function () {
              var host = el.querySelector("[data-owner-host]");
              host.hidden = !host.hidden;
              if (host.hidden || host.getAttribute("data-ready")) return;
              host.setAttribute("data-ready", "1");
              host.innerHTML = T.skel(2);
              employees().then(function (rows) {
                T.picker(host, rows, { placeholder: "Tên nhân viên…", label: function (r) { return r.label; }, sub: function (r) { return r.department; },
                  selected: owner, onPick: function (k, r) {
                    owner = k;
                    el.querySelector("[data-owner-label]").textContent = (r && r.label) || k;
                    if (r && r.department && !dep.value) {
                      if (!dep.querySelector('option[value="' + r.department.replace(/["\\]/g, "\\$&") + '"]')) dep.insertAdjacentHTML("beforeend", '<option value="' + esc(r.department) + '">' + esc(r.department) + "</option>");
                      dep.value = r.department;
                    }
                    host.hidden = true;
                  } });
              }, function (er) { host.innerHTML = T.errBox(er); });
            });
          }
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          el.querySelector("[data-ok]").addEventListener("click", function (ev) {
            var btn = ev.currentTarget, data = {};
            if (infoOk) {
              data = { license_name: v("license_name"), vendor: v("vendor"), category: v("category"), seats: String(v("seats")).replace(/[^\d]/g, ""),
                start_date: v("start_date"), owner_employee: owner, department: v("department"), account: v("account"),
                key_location: v("key_location"), note: v("note") };
              if (!data.license_name.trim()) { T.toast("Nhập tên bản quyền.", true); return; }
              if (ltype !== "Perpetual") {
                data.billing_cycle = v("billing_cycle");
                data.auto_renew = el.querySelector('[name="auto_renew"]').checked ? 1 : 0;
              }
              if (hasInvoice) data.supplier_invoice = v("supplier_invoice");
              if (!creating && ltype !== "Perpetual" && v("expiry_date") && v("expiry_date") !== (L.expiry_date || "")) {
                data.expiry_date = v("expiry_date");
              }
              if (creating) {
                data.license_type = ltype;
                if (ltype !== "Perpetual") {
                  data.expiry_date = v("expiry_date");
                  if (!data.expiry_date) { T.toast("Thuê bao cần ngày hết hạn.", true); return; }
                }
              }
            }
            if (costOk && el.querySelector('[name="cost_per_cycle"]')) {
              var c = String(v("cost_per_cycle")).replace(/[^\d]/g, "");
              var old = L.cost_per_cycle ? String(Math.round(L.cost_per_cycle)) : "";
              if (creating || c !== old) data.cost_per_cycle = c;
            }
            T.busy(btn, true);
            var call = creating ? T.post("create_license", { data: JSON.stringify(data) }) :
              T.post("update_license", { name: L.name, data: JSON.stringify(data) });
            call.then(function (r) { close(); T.toast(creating ? "Đã thêm bản quyền." : "Đã lưu."); resolve(r || true); },
              function (er) { T.busy(btn, false); T.toast(T.msg(er), true); });
          });
        }, true);
    });
  }

  function start() {
    root = document.getElementById("ts-root");
    if (!root) return;
    shell();
    loadList().then(function () {
      if (cur.id && last) openDrawer(cur.id);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
