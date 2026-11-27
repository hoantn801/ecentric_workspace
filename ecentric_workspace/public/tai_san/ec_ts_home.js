// Copyright (c) 2026, eCentric and contributors
// ec_ts_home.js -- trang /tai-san (tong quan). Chi ve giao dien tu dashboard; so lieu do server tinh.
(function () {
  "use strict";
  var T = window.ECTs, O = window.ECTsOps, esc = T.esc;
  var LIST = "/tai-san/thiet-bi";
  var LIC = "/tai-san/ban-quyen";
  var COST_COL = { depreciation: ["Khấu hao", "#2C3DA6"], repair: ["Sửa chữa", "#d97706"], rent: ["Thuê / phụ cấp", "#9ca3af"] };
  var state = { month: T.param("month"), department: T.param("department"), category: T.param("category") };
  var root;

  function load() {
    root.innerHTML = '<div class="ts-wrap">' + T.skel(6) + "</div>";
    T.get("dashboard", state).then(render, function (e) {
      if (T.toMineIfDenied(e)) return;
      root.innerHTML = '<div class="ts-wrap">' + T.errBox(e, true) + "</div>";
      var b = root.querySelector("[data-retry]"); if (b) b.addEventListener("click", load);
    });
  }

  function opts(list, val, all) {
    return '<option value="">' + esc(all) + "</option>" + (list || []).map(function (x) {
      return '<option value="' + esc(x) + '"' + (x === val ? " selected" : "") + ">" + esc(x) + "</option>";
    }).join("");
  }

  function kpi(label, value, sub, status) {
    return '<a class="ts-kpi" href="' + LIST + (status ? "?status=" + encodeURIComponent(status) : "") + '">' +
      '<div class="ts-kpi-l">' + (status ? T.dot(status) : "") + esc(label) + '</div><div class="ts-kpi-v">' + T.fmtNum(value) + "</div>" +
      (sub ? '<div class="ts-kpi-s">' + esc(sub) + "</div>" : "") + "</a>";
  }

  function finance(d) {
    var f = d.finance;
    if (!f) return "";
    var mc = f.month_cost || {};
    function card(l, v, sub, pct) {
      return '<div class="ts-card"><div class="ts-kpi-l">' + esc(l) + '</div><div class="ts-fin-v">' + T.fmtMillion(v) + "</div>" +
        (sub ? '<div class="ts-kpi-s">' + sub + "</div>" : "") + (pct != null ? '<div class="ts-bar"><span style="width:' + Math.max(0, Math.min(100, pct)) + '%"></span></div>' : "") + "</div>";
    }
    var g = Number(f.gross || 0);
    return '<div class="ts-grid ts-g4">' +
      card("Nguyên giá", f.gross, "Toàn bộ thiết bị đang quản lý") +
      card("Khấu hao luỹ kế", f.accumulated, g ? Math.round(Number(f.accumulated || 0) * 100 / g) + "% nguyên giá" : "", g ? Number(f.accumulated || 0) * 100 / g : null) +
      card("Giá trị còn lại", f.nbv, "Đến " + esc(T.fmtMonth(f.month || d.month))) +
      card("Chi phí " + T.fmtMonth(f.month || d.month), mc.total,
        "Khấu hao " + T.fmtMillion(mc.depreciation) + " · Sửa " + T.fmtMillion(mc.repair) + " · Thuê " + T.fmtMillion(mc.rent)) +
      "</div>";
  }

  function cost12(d) {
    var rows = d.cost_12m;
    if (!rows || !rows.length) return "";
    var max = 0;
    rows.forEach(function (r) { max = Math.max(max, Number(r.depreciation || 0) + Number(r.repair || 0) + Number(r.rent || 0)); });
    var cols = rows.map(function (r) {
      var tot = Number(r.depreciation || 0) + Number(r.repair || 0) + Number(r.rent || 0);
      var h = max ? Math.round(tot * 150 / max) : 0;
      var segs = ["depreciation", "repair", "rent"].map(function (k) {
        var v = Number(r[k] || 0);
        return v > 0 ? '<span style="display:block;height:' + (tot ? v * 100 / tot : 0) + '%;background:' + COST_COL[k][1] + '" title="' + esc(COST_COL[k][0] + ": " + T.fmtMoney(v)) + '"></span>' : "";
      }).join("");
      return '<div class="ts-col"><div class="ts-col-v">' + (tot ? T.fmtMillion(tot).replace(" tr", "") : "") + '</div><div class="ts-col-b" style="height:' + h + 'px">' + segs + "</div></div>";
    }).join("");
    return '<div class="ts-card"><div class="ts-card-h"><div class="ts-card-t">Chi phí thiết bị 12 tháng (triệu đồng)</div></div>' +
      '<div class="ts-cols">' + cols + '</div><div class="ts-col-x">' + rows.map(function (r) { return "<span>" + esc(T.fmtMonth(r.month)) + "</span>"; }).join("") + "</div>" +
      '<div class="ts-legend">' + ["depreciation", "repair", "rent"].map(function (k) {
        return '<span><i style="width:10px;height:10px;border-radius:2px;display:inline-block;background:' + COST_COL[k][1] + '"></i>' + COST_COL[k][0] + "</span>";
      }).join("") + "</div></div>";
  }

  function byCategory(d) {
    var rows = d.by_category || [];
    if (!rows.length) return '<div class="ts-card"><div class="ts-card-t">Trạng thái theo loại</div><div class="ts-empty">Chưa có thiết bị.</div></div>';
    var used = {};
    var bars = rows.map(function (r) {
      var segs = T.STATUS_ORDER.map(function (s) {
        var n = (r.counts || {})[s] || 0;
        if (!n) return "";
        used[s] = 1;
        return '<span style="width:' + (r.total ? n * 100 / r.total : 0) + "%;background:" + T.statusColor(s) + '" title="' + esc(T.statusLabel(s, d.status_labels) + ": " + n) + '"></span>';
      }).join("");
      return '<div class="ts-hbar"><span class="ts-strong">' + esc(r.category || "—") + '</span><div class="ts-stack">' + segs + '</div><span class="ts-num">' + T.fmtNum(r.total) + "</span></div>";
    }).join("");
    return '<div class="ts-card"><div class="ts-card-h"><div class="ts-card-t">Trạng thái theo loại thiết bị</div></div>' + bars +
      '<div class="ts-legend">' + T.STATUS_ORDER.filter(function (s) { return used[s]; }).map(function (s) {
        return "<span>" + T.dot(s) + esc(T.statusLabel(s, d.status_labels)) + "</span>";
      }).join("") + "</div></div>";
  }

  function byDepartment(d) {
    var rows = d.by_department || [];
    var max = 0;
    rows.forEach(function (r) { max = Math.max(max, Number(r.count || 0)); });
    return '<div class="ts-card"><div class="ts-card-h"><div class="ts-card-t">Thiết bị theo phòng ban</div></div>' +
      (rows.length ? rows.map(function (r) {
        // Ten phong ban DAY DU (khong cat "E-commerce ..."): dong ten + so, thanh do, ghi chu gop mot dong.
        var notes = [];
        if (r.in_use != null && r.in_use !== r.count) notes.push(T.fmtNum(r.in_use) + " đang dùng");
        if (r.nbv != null) notes.push("Còn lại " + T.fmtMillion(r.nbv));
        return '<div class="ts-drow"><div class="ts-drow-h"><span class="ts-strong">' + esc(r.department || "—") + '</span><span class="ts-num ts-strong">' + T.fmtNum(r.count) + "</span></div>" +
          '<div class="ts-bar" style="margin:4px 0 0"><span style="width:' + (max ? r.count * 100 / max : 0) + '%"></span></div>' +
          (notes.length ? '<div class="ts-note">' + esc(notes.join(" · ")) + "</div>" : "") + "</div>";
      }).join("") : '<div class="ts-empty">Chưa có thiết bị.</div>') + "</div>";
  }

  function age(d) {
    var rows = d.age || [];
    var max = 0;
    rows.forEach(function (r) { max = Math.max(max, Number(r.count || 0)); });
    return '<div class="ts-card"><div class="ts-card-h"><div class="ts-card-t">Tuổi thiết bị</div></div><div class="ts-age">' + rows.map(function (r, i) {
      return '<div><span class="ts-col-v">' + T.fmtNum(r.count) + '</span><i style="height:' + (max ? Math.max(2, Math.round(r.count * 110 / max)) : 2) + "px" +
        (i === rows.length - 1 ? ";background:#d97706" : "") + '"></i><span class="ts-note">' + esc(r.bucket) + "</span></div>";
    }).join("") + "</div></div>";
  }

  function assetLink(a, name) {
    return '<a href="' + LIST + "?asset=" + encodeURIComponent(name || a.asset || a.name) + '">' + esc(a.tag || a.asset || a.name) + "</a>";
  }

  function todo(d) {
    var t = d.todo || {};
    var secs = [];
    function sec(title, red, items, empty) {
      if (!items) return;
      secs.push("<section><div class=\"ts-eb" + (red ? " ts-red" : "") + '">' + esc(title) + (items.length ? " · " + items.length : "") + "</div>" +
        (items.length ? items.slice(0, 6).join("") + (items.length > 6 ? '<div class="ts-note">… và ' + (items.length - 6) + " mục khác</div>" : "") :
          '<div class="ts-note">' + esc(empty) + "</div>") + "</section>");
    }
    function li(main, right) { return '<div class="ts-li"><div class="ts-li-main">' + main + "</div>" + (right ? "<div>" + right + "</div>" : "") + "</div>"; }
    sec("Người giữ đã nghỉ việc", true, (t.holder_left || []).map(function (x) {
      return li(assetLink(x) + " · " + esc(x.asset_name || "") + '<div class="ts-note">Đang ghi cho ' + esc(x.employee_name || x.employee) + "</div>", '<span class="ts-pill ts-red">Cần thu hồi</span>');
    }), "Không có.");
    sec("Chờ thu hồi (Clearance)", false, (t.returns || []).map(function (x) {
      return li('<a href="' + esc(x.route) + '" target="_blank" rel="noopener">' + esc(x.employee_name || x.employee) + "</a> · " + esc(x.department || "") +
        '<div class="ts-note">' + (x.assets || []).map(function (a) { return esc(a.tag || a.name); }).join(", ") + "</div>",
        '<span class="ts-note' + (x.days_left < 0 ? " ts-bad-text" : "") + '">' + (x.days_left < 0 ? "Quá " + (-x.days_left) + " ngày" : "Còn " + x.days_left + " ngày") + "</span>");
    }), "Không có ai sắp nghỉ đang giữ máy.");
    sec("Chờ cấp phát", false, (t.allocations || []).map(function (x) {
      return li('<a href="' + esc(x.route) + '" target="_blank" rel="noopener">' + esc(x.employee_name || x.source) + "</a> · " + esc(x.source_label || "") +
        '<div class="ts-note">' + esc(x.need || "") + "</div>", x.due ? '<span class="ts-note">' + T.fmtDate(x.due) + "</span>" : "");
    }), "Không có yêu cầu đang chờ.");
    sec("Đang sửa chữa", (t.repairs || []).some(function (r) { return r.overdue; }), (t.repairs || []).map(function (r) {
      return li(assetLink(r, r.asset) + " · " + esc(r.mode_label || "") + (r.vendor ? " · " + esc(r.vendor) : "") +
        '<div class="ts-note">' + esc(r.status_label || "") + (r.expected_return ? " · hẹn " + T.fmtDate(r.expected_return) : "") + "</div>",
        r.overdue ? '<span class="ts-pill ts-red">Quá hẹn</span>' : "");
    }), "Không có máy đang sửa.");
    sec("Sắp hết bảo hành", false, (t.warranty || []).map(function (x) {
      return li(assetLink(x) + " · " + esc(x.asset_name || ""), '<span class="ts-note">' + T.fmtDate(x.warranty_until) + " · còn " + x.days_left + " ngày</span>");
    }), "Không có máy sắp hết bảo hành.");
    if (t.fully_depreciated) sec("Đã khấu hao hết", false, t.fully_depreciated.map(function (x) {
      return li(assetLink(x) + " · " + esc(x.asset_name || ""));
    }), "Không có.");
    sec("Nằm kho lâu", false, (t.idle || []).map(function (x) {
      return li(assetLink(x) + " · " + esc(x.asset_name || ""), '<span class="ts-note">' + T.fmtNum(x.idle_days) + " ngày</span>");
    }), "Không có máy nằm kho lâu.");
    return '<div class="ts-card" style="padding:0"><div class="ts-card-h" style="padding:14px 18px 10px"><div class="ts-card-t">Cần xử lý</div><span class="ts-sp"></span>' +
      '<a class="ts-link" href="/tai-san/luan-chuyen">Mở bảng luân chuyển</a></div><div class="ts-todo">' + secs.join("") + "</div></div>";
  }

  function licenses(d) {
    var b = d.licenses;
    if (!b) return "";
    var s = b.summary || {}, todo = b.todo || [];
    return '<div class="ts-card"><div class="ts-card-h"><div class="ts-card-t">Bản quyền phần mềm</div><span class="ts-sp"></span>' +
      '<a class="ts-link" href="' + LIC + '">Mở danh sách</a></div>' +
      '<div class="ts-row ts-note" style="margin-bottom:8px">' + T.fmtNum(s.total) + " bản quyền · " + T.fmtNum(s.used) + "/" + T.fmtNum(s.seats) + " chỗ đã cấp" +
      (s.due ? ' · <a href="' + LIC + '?stage=due">' + T.fmtNum(s.due) + " sắp hết hạn</a>" : "") +
      (s.expired ? ' · <a class="ts-bad-text" href="' + LIC + '?stage=expired">' + T.fmtNum(s.expired) + " đã quá hạn</a>" : "") +
      (s.monthly_cost != null ? " · " + T.fmtMillion(s.monthly_cost) + "/tháng" : "") + "</div>" +
      (todo.length ? todo.map(function (r) {
        return '<div class="ts-li"><div class="ts-li-main"><a class="ts-strong" href="' + LIC + "?id=" + encodeURIComponent(r.name) + '">' + esc(r.license_name || r.name) + "</a>" +
          '<div class="ts-note">' + esc([r.vendor, r.expiry_date ? "hết hạn " + T.fmtDate(r.expiry_date) : "", T.licDays(r.days_left)].filter(Boolean).join(" · ")) + "</div></div>" +
          "<div>" + T.licPill(r) + "</div></div>";
      }).join("") : '<div class="ts-note">Không có bản quyền sắp hết hạn.</div>') + "</div>";
  }

  function render(d) {
    var can = d.can || {}, k = d.kpis || {}, f = d.filters || {};
    root.innerHTML = '<div class="ts-wrap">' +
      '<div class="ts-head"><div class="ts-head-main"><h1 class="ts-title">Tài sản &amp; thiết bị</h1>' +
      '<div class="ts-sub">' + T.fmtNum(k.total) + " thiết bị · " + T.fmtNum(k.components_installed) + " linh kiện đang lắp trong máy</div></div>" +
      '<div class="ts-filters"><select class="ts-sel" data-f="department" aria-label="Phòng ban">' + opts(f.departments, state.department, "Tất cả phòng ban") + "</select>" +
      '<select class="ts-sel" data-f="category" aria-label="Loại thiết bị">' + opts(f.categories, state.category, "Tất cả loại") + "</select>" +
      (can.see_cost ? '<input class="ts-in" type="month" data-f="month" aria-label="Tháng" value="' + esc(state.month || d.month || "") + '">' : "") +
      (can.manage ? '<button type="button" class="ts-btn ts-primary" data-new>' + T.icon("plus") + "Nhập thiết bị</button>" : "") + "</div></div>" +
      '<div class="ts-grid ts-g5">' +
      kpi("Đang dùng", k.in_use, "", "In Use") + kpi("Sẵn sàng", k.available, "", "Available") + kpi("Đã giữ chỗ", k.reserved, "", "Reserved") +
      kpi("Chờ kiểm tra", k.pending_check, "", "Pending Check") + kpi("Hỏng / đang sửa", k.broken_or_repair, (k.lost ? "Mất " + k.lost : ""), "Broken") + "</div>" +
      (can.see_cost ? finance(d) + '<div class="ts-note">Khấu hao quản trị — chưa ghi sổ kế toán.</div>' + cost12(d) : "") +
      todo(d) + licenses(d) +
      '<div class="ts-grid ts-g2">' + byCategory(d) + '<div class="ts-grid">' + byDepartment(d) + age(d) + "</div></div>" +
      "</div>";
    T.qsa(root, "[data-f]").forEach(function (el) {
      el.addEventListener("change", function () {
        state[el.getAttribute("data-f")] = el.value;
        T.setParam(el.getAttribute("data-f"), el.value);
        load();
      });
    });
    var nb = root.querySelector("[data-new]");
    if (nb) nb.addEventListener("click", function () { O.createAsset(d.can).then(function (r) { if (r) load(); }); });
  }

  function start() {
    root = document.getElementById("ts-root");
    if (!root) return;
    load();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
