// Copyright (c) 2026, eCentric and contributors
// ec_ts_licenses.js -- trang /tai-san/ban-quyen: bang ban quyen phan mem + ngan chi tiet (cho da cap,
// gia han, sua, huy). URL: ?stage=&category=&product=&view=&q=&id=. Ten / hang / nhom ban quyen lay
// tu danh muc phan mem (chon dropdown + "Them phan mem moi"; xem Gop theo phan mem / Gop hai ten lech). Quyen, giai doan han, chi phi deu do server tinh;
// truong tien chi co trong du lieu khi nguoi xem co quyen chi phi.
(function () {
  "use strict";
  var T = window.ECTs, esc = T.esc;
  var CHIPS = [["", "Tất cả"], ["due", "Sắp hết hạn"], ["expired", "Đã quá hạn"], ["perpetual", "Vĩnh viễn"], ["cancelled", "Đã huỷ"]];
  var st = { stage: T.param("stage"), category: T.param("category"), product: T.param("product"),
    view: T.param("view") === "group" ? "group" : "list", q: T.param("q") };
  var cur = { id: T.param("id"), detail: null };
  var root, kpiBox, listBox, drawer, last = null, qTimer = null, emps = null, prodReq = null;

  // Danh muc phan mem (dropdown + bo loc). Xoa cache sau khi them / sua / gop.
  function products(fresh) {
    if (fresh || !prodReq) prodReq = T.get("products").then(function (d) { return d; }, function (e) { prodReq = null; throw e; });
    return prodReq;
  }

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
        return '<button type="button" class="ts-chip' + (c[0] === st.stage ? " on" : "") + '" data-s="' + esc(c[0]) + '">' + esc(c[1]) +
          '<span class="ts-cnt" data-cnt="' + esc(c[0] || "total") + '"></span></button>';
      }).join("") + "</div>" +
      '<div class="ts-filters"><input class="ts-in" type="search" data-q placeholder="Tên, hãng, tài khoản, người phụ trách…" aria-label="Tìm bản quyền" value="' + esc(st.q) + '" style="min-width:340px">' +
      '<select class="ts-sel" data-cat aria-label="Nhóm"><option value="">Tất cả nhóm</option></select>' +
      '<select class="ts-sel" data-prod aria-label="Phần mềm"><option value="">Tất cả phần mềm</option></select>' +
      '<span class="ts-sp"></span><div class="ts-seg" role="group" aria-label="Cách xem" data-view>' +
      '<button type="button" data-v="list"' + (st.view === "list" ? ' class="on"' : "") + ">Từng bản quyền</button>" +
      '<button type="button" data-v="group"' + (st.view === "group" ? ' class="on"' : "") + ">Gộp theo phần mềm</button></div></div>" +
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
    root.querySelector("[data-prod]").addEventListener("change", function (e) { setProduct(e.target.value); });
    root.querySelector("[data-view]").addEventListener("click", function (e) {
      var b = e.target.closest("button[data-v]"); if (b) setView(b.getAttribute("data-v"));
    });
    listBox.addEventListener("click", function (e) {
      var act = e.target.closest("[data-pedit],[data-pmerge]");
      if (act) {
        e.stopPropagation();
        var g = groupOf(act.getAttribute("data-pedit") || act.getAttribute("data-pmerge"));
        if (act.hasAttribute("data-pedit")) editProduct(g); else mergeProduct(g);
        return;
      }
      var gr = e.target.closest("tr[data-group]");
      if (gr) { if (gr.getAttribute("data-group")) { setView("list", true); setProduct(gr.getAttribute("data-group")); } return; }
      var tr = e.target.closest("tr[data-name]");
      if (tr) openDrawer(tr.getAttribute("data-name"));
    });
    listBox.addEventListener("keydown", function (e) {
      var tr = e.target.closest && e.target.closest("tr[data-name],tr[data-group]");
      if (tr && e.target === tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); tr.click(); }
    });
  }

  function setStage(s) {
    st.stage = s || ""; T.setParam("stage", st.stage);
    T.qsa(root, "[data-chips] .ts-chip").forEach(function (x) { x.classList.toggle("on", x.getAttribute("data-s") === st.stage); });
    loadList();
  }

  function setProduct(p) {
    st.product = p || ""; T.setParam("product", st.product);
    var sel = root.querySelector("[data-prod]"); if (sel) sel.value = st.product;
    loadList();
  }

  function setView(v, quiet) {
    st.view = v === "group" ? "group" : "list"; T.setParam("view", st.view === "group" ? "group" : "");
    T.qsa(root, "[data-view] button").forEach(function (x) { x.classList.toggle("on", x.getAttribute("data-v") === st.view); });
    if (!quiet && last) drawList(last);
  }

  function fillProducts() {
    products().then(function (d) {
      var sel = root.querySelector("[data-prod]");
      sel.innerHTML = '<option value="">Tất cả phần mềm</option>' + (d.rows || []).filter(function (p) { return !p.disabled || p.name === st.product; }).map(function (p) {
        return '<option value="' + esc(p.name) + '"' + (p.name === st.product ? " selected" : "") + ">" + esc(p.label) + "</option>";
      }).join("");
    }, function () { /* bo loc phu - loi thi de trong */ });
  }

  function filters() {
    var f = { category: st.category, product: st.product, q: st.q };
    if (st.stage === "cancelled") f.status = "Cancelled"; else f.stage = st.stage;
    return f;
  }

  function loadList() {
    listBox.innerHTML = '<div style="padding:16px">' + T.skel(6) + "</div>";
    return T.get("licenses", { filters: JSON.stringify(filters()) }).then(function (d) {
      last = d;
      drawActions(d);
      drawKpi(d);
      var sm = d.summary || {};
      T.qsa(root, "[data-cnt]").forEach(function (x) { var n = sm[x.getAttribute("data-cnt")]; x.textContent = n == null ? "" : T.fmtNum(n); });
      var sel = root.querySelector("[data-cat]");
      sel.innerHTML = '<option value="">Tất cả nhóm</option>' + (d.categories || []).map(function (c) {
        return '<option value="' + esc(c) + '"' + (c === st.category ? " selected" : "") + ">" + esc(c) + "</option>";
      }).join("");
      fillProducts();
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
    // tip: giai thich dai -> tooltip (dong phu chi de so ngan, khong bi cat "...").
    function k(label, value, sub, stage, ic, col, raw, tip) {
      return T.kpiCard({ button: 1, attrs: stage != null ? ' data-kstage="' + esc(stage) + '"' : "", icon: ic, color: col,
        label: label, value: value, raw: raw, sub: sub ? esc(sub) : "", title: tip });
    }
    kpiBox.innerHTML = '<div class="ts-grid ' + (cost ? "ts-g5" : "ts-g4") + '">' +
      k("Đang dùng", T.fmtNum(s.total), "", "", "key", null, s.total, "Không tính bản quyền đã huỷ") +
      k("Sắp hết hạn", '<span' + (s.due ? ' style="color:#92400e"' : "") + ">" + T.fmtNum(s.due) + "</span>", "", "due", "clock", "#d97706", s.due) +
      k("Đã quá hạn", '<span' + (s.expired ? ' class="ts-bad-text"' : "") + ">" + T.fmtNum(s.expired) + "</span>", "", "expired", "alert", "#dc2626", s.expired) +
      k("Chỗ đã cấp", T.fmtNum(s.used) + '<span class="ts-muted" style="font-size:18px"> / ' + T.fmtNum(s.seats) + "</span>",
        s.seats ? "Còn trống " + T.fmtNum(Math.max(0, (s.seats || 0) - (s.used || 0))) + " chỗ" : "", null, "users", null, s.used) +
      (cost ? k("Chi phí tháng", T.fmtMillion(s.monthly_cost), "", null, "coins", null, s.monthly_cost, "Quy đổi theo kỳ thanh toán") : "") + "</div>";
  }

  function groupOf(product) {
    return ((last && last.groups) || []).filter(function (g) { return g.product === product; })[0] || { product: product };
  }

  // Gop theo phan mem: moi phan mem mot dong. Bam dong -> loc danh sach theo phan mem do.
  function drawGroups(d) {
    var gs = d.groups || [], cost = !!(d.can && d.can.see_cost), mng = !!(d.can && d.can.manage);
    if (!gs.length) {
      listBox.innerHTML = '<div class="ts-empty" style="padding:32px">' + (st.stage || st.category || st.product || st.q ? "Không có phần mềm nào khớp bộ lọc." :
        "Chưa có bản quyền nào." + (mng ? " Bấm Thêm bản quyền để nhập." : "")) + "</div>";
      return;
    }
    var head = "<tr><th>Phần mềm</th><th>Nhóm</th><th class=\"ts-num\">Số bản quyền</th><th class=\"ts-num\">Chỗ</th><th>Hết hạn gần nhất</th>" +
      (cost ? '<th class="ts-num">Chi phí / tháng</th>' : "") + (mng ? "<th></th>" : "") + "</tr>";
    var body = gs.map(function (g) {
      var warn = g.expired ? '<span class="ts-pill ts-red">' + g.expired + " quá hạn</span>" : g.due ? '<span class="ts-pill ts-amber">' + g.due + " sắp hết</span>" : "";
      return '<tr class="ts-click" data-group="' + esc(g.product || "") + '" tabindex="0">' +
        '<td><span class="ts-strong">' + esc(g.label || "") + "</span>" + (g.vendor ? '<div class="ts-note">' + esc(g.vendor) + "</div>" : "") +
        (g.product ? "" : '<div class="ts-note ts-bad-text">Chưa gắn danh mục</div>') + "</td>" +
        "<td>" + esc(g.category || "") + "</td>" +
        '<td class="ts-num">' + T.fmtNum(g.licenses) + "</td>" +
        '<td class="ts-num">' + T.fmtNum(g.used) + " / " + T.fmtNum(g.seats) + "</td>" +
        "<td>" + (g.next_expiry ? '<div class="ts-row" style="gap:6px;flex-wrap:nowrap"><span>' + fdate(g.next_expiry) + "</span>" + warn + "</div>" : '<span class="ts-muted">Vĩnh viễn</span>') + "</td>" +
        (cost ? '<td class="ts-num">' + money(g.monthly_cost) + "</td>" : "") +
        (mng ? '<td class="ts-nw">' + (g.product ? '<button type="button" class="ts-btn ts-sm" data-pedit="' + esc(g.product) + '">Sửa</button> ' +
          '<button type="button" class="ts-btn ts-sm" data-pmerge="' + esc(g.product) + '" title="Gộp tên ghi lệch vào một phần mềm khác">Gộp vào…</button>' : "") + "</td>" : "") + "</tr>";
    }).join("");
    listBox.innerHTML = '<div class="ts-table-wrap"><table class="ts-table"><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";
  }

  function drawList(d) {
    if (st.view === "group") { drawGroups(d); return; }
    var rows = d.rows || [], cost = !!(d.can && d.can.see_cost);
    if (!rows.length) {
      listBox.innerHTML = '<div class="ts-empty" style="padding:32px">' + (st.stage || st.category || st.product || st.q ? "Không có bản quyền nào khớp bộ lọc." :
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
        '<div class="ts-form"><div class="ts-lbl ts-full">Phần mềm *<div data-prod-pick>' + T.skel(1) + "</div>" +
        '<span class="ts-note" style="font-weight:400">Chọn từ danh mục để cùng một phần mềm luôn một tên (gộp số liệu được). Chưa có thì bấm Thêm phần mềm mới.</span></div>' +
        '<label class="ts-lbl" data-sub>Kỳ thanh toán<select class="ts-sel" name="billing_cycle">' + opt(cycles, L.billing_cycle || "Yearly") + "</select></label>" +
        inp("seats", "Số chỗ", L.seats || 1, { num: 1 }) +
        inp("start_date", "Ngày bắt đầu", L.start_date || (creating ? today : ""), { type: "date" }) +
        inp("expiry_date", creating ? "Hết hạn *" : "Hết hạn (sửa khi nhập nhầm)", creating ? "" : (L.expiry_date || ""), { type: "date", sub: 1 }) +
        // O chon nguoi trong nhu o nhap (cung cao, cung vien) - khong de chu + nut le loi.
        '<div class="ts-lbl">Người phụ trách<button type="button" class="ts-in ts-pickfield" data-owner-pick>' +
        '<span data-owner-label class="' + (L.owner_name || L.owner_employee ? "" : "ts-ph") + '">' + esc(L.owner_name || L.owner_employee || "Chọn nhân viên…") +
        '</span>' + T.icon("chevron") + "</button></div>" +
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
          var owner = L.owner_employee || "", prodPick = null;
          function v(n) { var f = el.querySelector('[name="' + n + '"]'); return f ? f.value : ""; }
          function syncType() {
            var perp = ltype === "Perpetual";
            T.qsa(el, "[data-sub]").forEach(function (x) { x.hidden = perp; });
          }
          if (infoOk) {
            syncType();
            var pHost = el.querySelector("[data-prod-pick]");
            products(true).then(function (pd) {
              var rows = (pd.rows || []).filter(function (p) { return !p.disabled || p.name === L.product; });
              prodPick = T.catalogPick(pHost, { rows: rows, selected: L.product || null, placeholder: "Chọn phần mềm…",
                label: function (r) { return r.label; }, sub: function (r) { return [r.vendor, r.category].filter(Boolean).join(" · "); },
                addLabel: "Thêm phần mềm mới", onAdd: function (q) { return productForm(null, q, pd); },
                onPick: function (k, r) {
                  if (!creating || !r) return;
                  // Loai / ky mac dinh theo phan mem - van doi duoc cho lan mua nay.
                  if (r.license_type && types[r.license_type]) {
                    ltype = r.license_type;
                    T.qsa(el, "[data-type] .ts-chip").forEach(function (x) { x.classList.toggle("on", x.getAttribute("data-v") === ltype); });
                    syncType();
                  }
                  var bc = el.querySelector('[name="billing_cycle"]');
                  if (r.billing_cycle && bc) bc.value = r.billing_cycle;
                } });
            }, function (er) { pHost.innerHTML = T.errBox(er); });
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
                    el.querySelector("[data-owner-label]").className = "";
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
              data = { seats: String(v("seats")).replace(/[^\d]/g, ""),
                start_date: v("start_date"), owner_employee: owner, department: v("department"), account: v("account"),
                key_location: v("key_location"), note: v("note") };
              var prod = prodPick && prodPick.value();
              if (!prod) { T.toast("Chọn phần mềm (hoặc Thêm phần mềm mới).", true); return; }
              if (creating || prod !== L.product) data.product = prod;
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
            call.then(function (r) { close(); products(true); T.toast(creating ? "Đã thêm bản quyền." : "Đã lưu."); resolve(r || true); },
              function (er) { T.busy(btn, false); T.toast(T.msg(er), true); });
          });
        }, true);
    });
  }

  // Them (p=null) / sua mot phan mem trong danh muc. Them -> Promise(row|null) (chon ngay o form ban quyen).
  function productForm(p, name, pd) {
    pd = pd || {};
    var cats = pd.categories || (last && last.categories) || [];
    var types = pd.types || (last && last.types) || {}, cycles = pd.cycles || (last && last.cycles) || {};
    var P = p || { product_name: name || "", category: "Khác", license_type: "Subscription", billing_cycle: "Yearly" };
    function opts(map, val) {
      return (Array.isArray(map) ? map.map(function (k) { return [k, k]; }) : Object.keys(map).map(function (k) { return [k, map[k]]; }))
        .map(function (x) { return '<option value="' + esc(x[0]) + '"' + (x[0] === val ? " selected" : "") + ">" + esc(x[1]) + "</option>"; }).join("");
    }
    var body = '<div class="ts-form">' +
      '<label class="ts-lbl ts-full">Tên phần mềm *<input class="ts-in" name="product_name" maxlength="140" placeholder="Vd: Windows 11 Pro" value="' + esc(P.product_name || P.label || "") + '"></label>' +
      '<label class="ts-lbl">Hãng<input class="ts-in" name="vendor" maxlength="140" placeholder="Vd: Microsoft" value="' + esc(P.vendor || "") + '"></label>' +
      '<label class="ts-lbl">Nhóm<select class="ts-sel" name="category">' + opts(cats, P.category || "Khác") + "</select></label>" +
      '<label class="ts-lbl">Loại<select class="ts-sel" name="license_type">' + opts(types, P.license_type || "Subscription") + "</select></label>" +
      '<label class="ts-lbl" data-cyc>Kỳ thanh toán<select class="ts-sel" name="billing_cycle">' + opts(cycles, P.billing_cycle || "Yearly") + "</select></label>" +
      "</div>" + (p ? '<div class="ts-note">Đổi tên / hãng / nhóm áp dụng luôn cho mọi bản quyền của phần mềm này.</div>' :
        '<div class="ts-note">Loại và kỳ là mặc định khi chọn phần mềm này - từng lần mua vẫn đổi được.</div>');
    return new Promise(function (resolve) {
      T.modal(p ? "Sửa phần mềm" : "Thêm phần mềm mới", body,
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>' + (p ? "Lưu" : "Thêm") + "</button>",
        function (el, close) {
          function v(n) { return el.querySelector('[name="' + n + '"]').value; }
          var lt = el.querySelector('[name="license_type"]');
          function sync() { el.querySelector("[data-cyc]").hidden = lt.value === "Perpetual"; }
          lt.addEventListener("change", sync); sync();
          el.querySelector("[data-close]").addEventListener("click", function () { resolve(null); });
          el.querySelector("[data-ok]").addEventListener("click", function (ev) {
            var btn = ev.currentTarget;
            var data = { product_name: v("product_name").trim(), vendor: v("vendor"), category: v("category"), license_type: v("license_type"),
              billing_cycle: v("license_type") === "Perpetual" ? "" : v("billing_cycle") };
            if (!data.product_name) { T.toast("Nhập tên phần mềm.", true); return; }
            T.busy(btn, true);
            var call = p ? T.post("update_product", { name: p.name || p.product, data: JSON.stringify(data) })
              : T.catalogCreate("create_product", data, "phần mềm này");
            call.then(function (r) {
              T.busy(btn, false);
              if (!p && !r) return;                     // huy o buoc hoi trung - giu form de sua ten
              close(); products(true);
              T.toast(p ? (r && r.licenses ? "Đã lưu, cập nhật " + r.licenses + " bản quyền." : "Đã lưu.") : "Đã thêm " + r.label + ".");
              resolve(p ? true : r);
            }, function (er) { T.busy(btn, false); T.toast(T.msg(er), true); });
          });
        });
    });
  }

  function editProduct(g) {
    products(true).then(function (pd) {
      var p = (pd.rows || []).filter(function (x) { return x.name === g.product; })[0];
      if (!p) { T.toast("Không tìm thấy phần mềm.", true); return; }
      productForm(p, null, pd).then(function (ok) { if (ok) loadList(); });
    }, function (e) { T.toast(T.msg(e), true); });
  }

  // Gop: moi ban quyen cua phan mem nay chuyen sang phan mem dich; phan mem nay ngung dung (khong xoa).
  function mergeProduct(g) {
    products(true).then(function (pd) {
      var rows = (pd.rows || []).filter(function (x) { return !x.disabled && x.name !== g.product; });
      var target = null;
      T.modal("Gộp " + (g.label || g.product), "<p>Chọn phần mềm đúng tên. " + T.fmtNum(g.licenses || 0) +
        " bản quyền của <b>" + esc(g.label || g.product) + "</b> sẽ chuyển sang đó; tên cũ ngừng dùng (vẫn giữ lịch sử).</p><div data-tg>" + T.skel(2) + "</div>",
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok disabled>Gộp</button>',
        function (el, close) {
          var ok = el.querySelector("[data-ok]");
          T.picker(el.querySelector("[data-tg]"), rows, { placeholder: "Tìm phần mềm…", label: function (r) { return r.label; },
            sub: function (r) { return [r.vendor, r.category, r.licenses ? r.licenses + " bản quyền" : ""].filter(Boolean).join(" · "); },
            onPick: function (k) { target = k; ok.disabled = false; } });
          ok.addEventListener("click", function () {
            T.busy(ok, true);
            T.post("merge_product", { source: g.product, target: target }).then(function (r) {
              close(); products(true);
              T.toast("Đã gộp " + T.fmtNum(r.licenses) + " bản quyền.");
              if (st.product === g.product) setProduct(target); else loadList();
            }, function (e) { T.busy(ok, false); T.toast(T.msg(e), true); });
          });
        });
    }, function (e) { T.toast(T.msg(e), true); });
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
