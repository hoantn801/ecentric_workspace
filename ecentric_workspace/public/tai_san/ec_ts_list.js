// Copyright (c) 2026, eCentric and contributors
// ec_ts_list.js -- trang /tai-san/thiet-bi: bang thiet bi + ngan chi tiet 600px (5 the).
// URL: ?status=&q=&asset=. Moi thao tac goi API; danh sach thao tac hop le do server tra (`actions`).
(function () {
  "use strict";
  var T = window.ECTs, O = window.ECTsOps, esc = T.esc;
  var TABS = [["info", "Tổng quan"], ["parts", "Linh kiện"], ["dep", "Khấu hao"], ["hist", "Lịch sử"], ["rep", "Sửa chữa"]];
  var st = { status: T.param("status"), q: T.param("q"), category: T.param("category"), department: T.param("department"),
    issues_only: T.param("issues") === "1", include_components: false, page: 1 };
  var cur = { asset: T.param("asset"), tab: "info", detail: null, partSel: null };
  var root, listBox, drawer, split, last = null, qTimer = null;

  // ------------------------------------------------------------ danh sach --
  function shell() {
    root.innerHTML = '<div class="ts-wrap">' +
      '<div class="ts-head"><div class="ts-head-main"><h1 class="ts-title">Danh sách thiết bị</h1><div class="ts-sub" data-total>&nbsp;</div></div>' +
      '<div class="ts-filters"><a class="ts-btn" href="/tai-san">' + T.icon("back") + "Tổng quan</a></div></div>" +
      '<div class="ts-chips" data-chips role="group" aria-label="Lọc trạng thái"></div>' +
      '<div class="ts-filters"><input class="ts-in" type="search" data-q placeholder="Tag, tên máy, serial, người giữ…" aria-label="Tìm thiết bị" value="' + esc(st.q) + '" style="min-width:260px">' +
      '<select class="ts-sel" data-f="category" aria-label="Loại"></select><select class="ts-sel" data-f="department" aria-label="Phòng ban"></select>' +
      '<label class="ts-ck"><input type="checkbox" data-issues' + (st.issues_only ? " checked" : "") + "> Chỉ máy có vấn đề</label>" +
      '<label class="ts-ck"><input type="checkbox" data-comp> Gồm linh kiện rời</label></div>' +
      '<div class="ts-split"><div class="ts-left"><div class="ts-card" style="padding:0" data-list></div></div><aside class="ts-drawer" data-drawer hidden aria-label="Chi tiết thiết bị"></aside></div></div>';
    listBox = root.querySelector("[data-list]");
    drawer = root.querySelector("[data-drawer]");
    split = root.querySelector(".ts-split");
    var chips = [["", "Tất cả"]].concat(T.STATUS_ORDER.map(function (s) { return [s, T.statusLabel(s)]; }));
    root.querySelector("[data-chips]").innerHTML = chips.map(function (c) {
      return '<button type="button" class="ts-chip' + (c[0] === st.status ? " on" : "") + '" data-s="' + esc(c[0]) + '">' + (c[0] ? T.dot(c[0]) : "") + esc(c[1]) + "</button>";
    }).join("");
    root.querySelector("[data-chips]").addEventListener("click", function (e) {
      var b = e.target.closest(".ts-chip"); if (!b) return;
      st.status = b.getAttribute("data-s"); st.page = 1; T.setParam("status", st.status);
      T.qsa(root, "[data-chips] .ts-chip").forEach(function (x) { x.classList.toggle("on", x === b); });
      loadList();
    });
    root.querySelector("[data-q]").addEventListener("input", function (e) {
      clearTimeout(qTimer);
      var v = e.target.value;
      qTimer = setTimeout(function () { st.q = v; st.page = 1; T.setParam("q", v); loadList(); }, 300);
    });
    T.qsa(root, "[data-f]").forEach(function (el) {
      el.addEventListener("change", function () { st[el.getAttribute("data-f")] = el.value; st.page = 1; T.setParam(el.getAttribute("data-f"), el.value); loadList(); });
    });
    root.querySelector("[data-issues]").addEventListener("change", function (e) { st.issues_only = e.target.checked; st.page = 1; T.setParam("issues", e.target.checked ? "1" : ""); loadList(); });
    root.querySelector("[data-comp]").addEventListener("change", function (e) { st.include_components = e.target.checked; st.page = 1; loadList(); });
    listBox.addEventListener("click", function (e) {
      // data-goto (KHONG dung data-page: the goc #ts-root co data-page="list" -> moi cu bam deu bi
      // hieu la "sang trang", tai lai bang va drawer khong mo).
      var pg = e.target.closest("[data-goto]");
      if (pg && listBox.contains(pg)) { st.page = Number(pg.getAttribute("data-goto")); loadList(); return; }
      var tr = e.target.closest("tr[data-name]");
      if (tr) openDrawer(tr.getAttribute("data-name"));
    });
    listBox.addEventListener("keydown", function (e) {
      var tr = e.target.closest && e.target.closest("tr[data-name]");
      if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openDrawer(tr.getAttribute("data-name")); }
    });
  }

  function fillSelect(sel, list, val, all) {
    if (!sel) return;
    sel.innerHTML = '<option value="">' + esc(all) + "</option>" + (list || []).map(function (x) {
      return '<option value="' + esc(x) + '"' + (x === val ? " selected" : "") + ">" + esc(x) + "</option>";
    }).join("");
  }

  function loadList() {
    listBox.innerHTML = '<div style="padding:16px">' + T.skel(6) + "</div>";
    var f = { q: st.q, status: st.status, category: st.category, department: st.department,
      issues_only: st.issues_only ? 1 : 0, include_components: st.include_components ? 1 : 0, page: st.page };
    T.get("list_assets", { filters: JSON.stringify(f) }).then(function (d) {
      last = d;
      fillSelect(root.querySelector('[data-f="category"]'), d.categories, st.category, "Tất cả loại");
      if (!root.querySelector('[data-f="department"]').options.length || st.department === "") {
        fillSelect(root.querySelector('[data-f="department"]'), d.departments, st.department, "Tất cả phòng ban");
      }
      root.querySelector("[data-total]").textContent = T.fmtNum(d.total) + " thiết bị khớp bộ lọc";
      drawList(d);
    }, function (e) {
      if (T.toMineIfDenied(e)) return;
      listBox.innerHTML = '<div style="padding:16px">' + T.errBox(e, true) + "</div>";
      var b = listBox.querySelector("[data-retry]"); if (b) b.addEventListener("click", loadList);
    });
  }

  function drawList(d) {
    var cost = d.can && d.can.see_cost;
    if (!d.rows.length) { listBox.innerHTML = '<div class="ts-empty" style="padding:32px">Không có thiết bị nào khớp bộ lọc.</div>'; return; }
    // .ts-wide: cot phu, an khi mo ngan chi tiet (bang con du cho de doc, khong bop chu xuong 3 dong).
    var head = '<tr><th class="ts-nw">Tag</th><th class="ts-col-dev">Thiết bị</th><th class="ts-wide">Loại</th><th>Trạng thái</th>' +
      '<th class="ts-col-who">Người giữ</th><th class="ts-wide ts-col-dept">Phòng ban</th><th class="ts-wide ts-nw">Ngày mua</th>' +
      (cost ? '<th class="ts-num ts-wide">Nguyên giá</th><th class="ts-num ts-wide">Còn lại</th>' : "") + "</tr>";
    var body = d.rows.map(function (r) {
      return '<tr class="ts-click' + (r.name === cur.asset ? " on" : "") + '" data-name="' + esc(r.name) + '" tabindex="0">' +
        '<td class="ts-strong ts-nw">' + esc(r.tag || r.name) + "</td>" +
        "<td>" + esc(r.asset_name || "") + (r.serial ? '<div class="ts-note">SN ' + esc(r.serial) + "</div>" : "") +
        (r.components ? '<div class="ts-note">+' + r.components + " linh kiện lắp thêm</div>" : "") +
        (r.issues && r.issues.length ? '<div class="ts-note ts-bad-text">' + esc(r.issues.join(" · ")) + "</div>" : "") + "</td>" +
        '<td class="ts-wide">' + esc(r.category || "") + "</td>" +
        '<td class="ts-nw">' + T.pill(r.status, last && last.status_labels) + (r.condition && r.condition !== "Good" ? " " + T.condPill(r.condition) : "") + "</td>" +
        "<td" + (r.holder_left ? ' class="ts-bad-text"' : "") + ">" + esc(r.holder_name || (r.installed_on ? "Lắp trong " + r.installed_on : "—")) + (r.holder_left ? '<div class="ts-note ts-bad-text">Đã nghỉ việc</div>' : "") + "</td>" +
        '<td class="ts-wide">' + esc(r.department || "") + '</td><td class="ts-wide ts-nw">' + T.fmtDate(r.purchase_date) + "</td>" +
        (cost ? '<td class="ts-num ts-wide">' + (r.gross != null ? T.fmtMillion(r.gross) : "") + '</td><td class="ts-num ts-wide">' + (r.nbv != null ? T.fmtMillion(r.nbv) : "") + "</td>" : "") + "</tr>";
    }).join("");
    var pages = Math.max(1, Math.ceil(d.total / (d.page_size || 50)));
    listBox.innerHTML = '<div class="ts-table-wrap"><table class="ts-table"><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>" +
      (pages > 1 ? '<div class="ts-pager">Trang ' + d.page + "/" + pages +
        '<button type="button" class="ts-btn ts-sm" data-goto="' + (d.page - 1) + '"' + (d.page <= 1 ? " disabled" : "") + ">Trước</button>" +
        '<button type="button" class="ts-btn ts-sm" data-goto="' + (d.page + 1) + '"' + (d.page >= pages ? " disabled" : "") + ">Sau</button></div>" : "");
  }

  // ------------------------------------------------------------- ngan phai --
  function openDrawer(name) {
    cur.asset = name; cur.tab = cur.tab || "info"; cur.partSel = null;
    T.setParam("asset", name);
    T.qsa(listBox, "tr[data-name]").forEach(function (tr) { tr.classList.toggle("on", tr.getAttribute("data-name") === name); });
    drawer.hidden = false;
    split.classList.add("ts-has-drawer");
    drawer.innerHTML = '<div class="ts-dbody">' + T.skel(6) + "</div>";
    loadDetail();
  }
  function closeDrawer() {
    cur.asset = ""; cur.detail = null; drawer.hidden = true; drawer.innerHTML = ""; T.setParam("asset", "");
    split.classList.remove("ts-has-drawer");
    T.qsa(listBox, "tr.on").forEach(function (tr) { tr.classList.remove("on"); });
  }
  function loadDetail() {
    var name = cur.asset;
    return T.get("asset_detail", { name: name }).then(function (d) {
      if (name !== cur.asset) return;
      cur.detail = d; drawDrawer();
    }, function (e) {
      drawer.innerHTML = '<div class="ts-dbody">' + T.errBox(e, true) + '<button type="button" class="ts-btn" data-x>Đóng</button></div>';
      var b = drawer.querySelector("[data-retry]"); if (b) b.addEventListener("click", loadDetail);
      drawer.querySelector("[data-x]").addEventListener("click", closeDrawer);
    });
  }
  function refreshAll() { loadDetail(); loadList(); }

  function drawDrawer() {
    var d = cur.detail, a = d.asset;
    drawer.innerHTML = '<div class="ts-dhead"><div class="ts-row"><span class="ts-dev-ico" style="width:40px;height:40px">' + T.deviceIcon(a.category) + "</span>" +
      '<div style="flex:1;min-width:0"><div class="ts-dname">' + esc(a.tag || a.name) + " · " + esc(a.asset_name || "") + "</div>" +
      '<div class="ts-note">' + esc(a.category || "") + (a.serial ? " · SN " + esc(a.serial) : "") + "</div></div>" +
      '<button type="button" class="ts-btn ts-sm" data-x aria-label="Đóng">' + T.icon("x") + "</button></div>" +
      '<div class="ts-row">' + T.pill(a.status, null) + (a.condition && a.condition !== "Good" ? T.condPill(a.condition) : "") +
      (a.holder_left ? '<span class="ts-pill ts-red">Người giữ đã nghỉ</span>' : "") + "</div></div>" +
      '<div class="ts-tabs" role="tablist">' + TABS.map(function (t) {
        return '<button type="button" class="ts-tab' + (t[0] === cur.tab ? " on" : "") + '" role="tab" aria-selected="' + (t[0] === cur.tab) + '" data-tab="' + t[0] + '">' + t[1] +
          (t[0] === "parts" && d.components.length ? " · " + d.components.length : "") + (t[0] === "rep" && d.repairs.length ? " · " + d.repairs.length : "") + "</button>";
      }).join("") + '</div><div class="ts-dbody" data-body></div>';
    drawer.querySelector("[data-x]").addEventListener("click", closeDrawer);
    drawer.querySelector(".ts-tabs").addEventListener("click", function (e) {
      var b = e.target.closest("[data-tab]"); if (!b) return;
      cur.tab = b.getAttribute("data-tab");
      T.qsa(drawer, ".ts-tab").forEach(function (x) { x.classList.toggle("on", x === b); x.setAttribute("aria-selected", x === b); });
      drawTab();
    });
    drawTab();
  }

  function drawTab() {
    var body = drawer.querySelector("[data-body]");
    var fn = { info: tabInfo, parts: tabParts, dep: tabDep, hist: tabHist, rep: tabRep }[cur.tab] || tabInfo;
    fn(body, cur.detail);
  }

  function kv(label, value) { return "<div><span>" + esc(label) + "</span><b>" + (value == null || value === "" ? "—" : value) + "</b></div>"; }

  function tabInfo(body, d) {
    var a = d.asset, info = d.info || {}, can = d.can || {};
    var issues = (last && last.rows || []).filter(function (r) { return r.name === a.name; })[0];
    body.innerHTML = (issues && issues.issues && issues.issues.length ? '<div class="ts-issue">' + esc(issues.issues.join(" · ")) + "</div>" : "") +
      '<div class="ts-info">' +
      kv("Tag", esc(a.tag || "")) + kv("Mã tài sản", esc(a.name)) + kv("Loại", esc(a.category || "")) + kv("Serial", esc(a.serial || "")) +
      kv("Người giữ", a.holder ? esc(a.holder_name || a.holder) + (a.holder_left ? ' <span class="ts-bad-text">(đã nghỉ)</span>' : "") : "") +
      kv("Phòng ban", esc(a.department || "")) + kv("Ngày mua", T.fmtDate(a.purchase_date)) + kv("Bảo hành đến", T.fmtDate(a.warranty_until)) +
      kv("Sở hữu", esc((T.OWN[a.ownership] || a.ownership || ""))) + kv("Tình trạng", esc(T.COND[a.condition] || a.condition || "")) +
      (a.reserved_for ? kv("Giữ chỗ cho", esc(a.reserved_for)) : "") +
      (d.parent ? kv("Đang lắp trong", '<button type="button" class="ts-link" data-open="' + esc(d.parent.name) + '">' + esc(d.parent.tag || d.parent.name) + " · " + esc(d.parent.asset_name || "") + "</button>") : "") +
      (can.see_cost ? kv("Nhà cung cấp", esc(info.ec_supplier || "")) + kv("Hoá đơn", esc(info.ec_invoice || "")) + kv("Vị trí", esc(info.location || "")) + kv("Mã hàng", esc(info.item_code || "")) +
        (info.ec_monthly_rent ? kv("Thuê / phụ cấp tháng", T.fmtMoney(info.ec_monthly_rent)) : "") : "") +
      "</div>" +
      (d.actions && d.actions.length ? '<div><div class="ts-eb">Thao tác</div><div class="ts-actions">' + d.actions.map(function (x) {
        var danger = x.action === "dispose" || x.action === "lost" || x.action === "break";
        return '<button type="button" class="ts-btn' + (danger ? " ts-danger" : "") + '" data-act="' + esc(x.action) + '">' + esc(x.label) + "</button>";
      }).join("") + "</div></div>" : (can.manage ? "" : '<div class="ts-note">Chỉ quản lý tài sản thao tác được trên thiết bị.</div>'));
    body.onclick = onInfoClick;
  }
  function onInfoClick(e) {
    var op = e.target.closest("[data-open]");
    if (op) { openDrawer(op.getAttribute("data-open")); return; }
    var b = e.target.closest("[data-act]");
    if (!b || cur.tab !== "info") return;
    var act = b.getAttribute("data-act");
    var lab = (cur.detail.actions.filter(function (x) { return x.action === act; })[0] || {}).label || act;
    O.transition(cur.detail.asset, act, lab).then(function (r) { if (r) refreshAll(); });
  }

  // ------------------------------------------------------------ linh kien --
  function parts(d) {
    var out = (d.specs || []).map(function (s) { return { kind: "base", type: s.part_type, spec: s.spec, qty: s.qty, note: s.note }; });
    (d.components || []).forEach(function (c) { out.push({ kind: "addon", type: c.category, spec: c.asset_name, row: c }); });
    return out;
  }

  function diagram(cat, list) {
    var pc = /pc|desktop|may ban|máy bàn/i.test(String(cat || ""));
    var n = list.length, cols = pc ? 2 : 3, rows = Math.max(1, Math.ceil(n / cols));
    var W = 540, H = pc ? 60 + rows * 54 + 40 : 120 + rows * 50 + 30;
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Sơ đồ linh kiện">';
    var bx, by, bw, bh;
    if (pc) {
      bx = 150; by = 14; bw = 240; bh = H - 28;
      s += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" rx="12" fill="#fff" stroke="#9ca3af" stroke-width="2"/>' +
        '<circle cx="' + (bx + bw - 22) + '" cy="' + (by + 20) + '" r="6" fill="none" stroke="#9ca3af" stroke-width="2"/>';
      bx += 14; by += 40; bw -= 28;
    } else {
      s += '<rect x="130" y="10" width="280" height="88" rx="8" fill="#fff" stroke="#9ca3af" stroke-width="2"/><rect x="142" y="20" width="256" height="68" rx="3" fill="#eef0fb"/>' +
        '<path d="M70 ' + (H - 12) + " L110 104 L430 104 L470 " + (H - 12) + ' Z" fill="#fff" stroke="#9ca3af" stroke-width="2"/>';
      bx = 120; by = 112; bw = 300;
    }
    var cw = (bw - (cols - 1) * 8) / cols;
    list.forEach(function (p, i) {
      var x = bx + (i % cols) * (cw + 8), y = by + Math.floor(i / cols) * (pc ? 54 : 50);
      var add = p.kind === "addon", on = cur.partSel === i;
      s += '<g data-pi="' + i + '" style="cursor:pointer"><rect x="' + x + '" y="' + y + '" width="' + cw + '" height="' + (pc ? 46 : 42) + '" rx="6" fill="' + (add ? "#eef0fb" : "#f9fafb") +
        '" stroke="' + (on ? "#2C3DA6" : add ? "#2C3DA6" : "#d1d5db") + '" stroke-width="' + (on ? 2.5 : 1.5) + '"' + (add ? ' stroke-dasharray="5 4"' : "") + "/>" +
        '<text x="' + (x + 8) + '" y="' + (y + 17) + '" font-size="11" font-weight="700" fill="#374151">' + esc(String(p.type || "").slice(0, 18)) + "</text>" +
        '<text x="' + (x + 8) + '" y="' + (y + 33) + '" font-size="10.5" fill="#6b7280">' + esc(String(p.spec || "").slice(0, Math.floor(cw / 6))) + "</text></g>";
    });
    if (!n) s += '<text x="' + (W / 2) + '" y="' + (H - 30) + '" font-size="12" text-anchor="middle" fill="#9ca3af">Chưa khai cấu hình</text>';
    return s + "</svg>";
  }

  function tabParts(body, d) {
    var a = d.asset, can = d.can || {}, list = parts(d);
    var sel = cur.partSel != null ? list[cur.partSel] : null;
    body.innerHTML = (d.parent ? '<div class="ts-infobox">Linh kiện này đang lắp trong <button type="button" class="ts-link" data-open="' + esc(d.parent.name) + '">' + esc(d.parent.tag || d.parent.name) + "</button>.</div>" : "") +
      '<div class="ts-diagram">' + diagram(a.category, list) + "</div>" +
      '<div class="ts-legend"><span><i style="width:14px;height:10px;border:1.5px solid #d1d5db;border-radius:3px;display:inline-block"></i>Cấu hình gốc</span>' +
      '<span><i style="width:14px;height:10px;border:1.5px dashed #2C3DA6;background:#eef0fb;border-radius:3px;display:inline-block"></i>Linh kiện lắp thêm (có mã tài sản riêng)</span></div>' +
      (list.length ? '<div class="ts-parts">' + list.map(function (p, i) {
        return '<button type="button" class="ts-part' + (p.kind === "addon" ? " ts-addon" : "") + (i === cur.partSel ? " on" : "") + '" data-pi="' + i + '"><span>' + esc(p.type || "") +
          (p.qty && p.qty > 1 ? " × " + p.qty : "") + "</span><b>" + esc(p.spec || "") + "</b></button>";
      }).join("") + "</div>" : "") +
      (sel ? '<div class="ts-partinfo">' + (sel.kind === "addon" ?
        '<div class="ts-row"><b class="ts-strong">' + esc(sel.row.tag || sel.row.name) + "</b> " + T.pill(sel.row.status) + '<span class="ts-sp"></span>' +
          '<button type="button" class="ts-link" data-open="' + esc(sel.row.name) + '">Mở</button></div><div class="ts-note">' + esc(sel.row.asset_name || "") +
          (sel.row.gross != null ? " · nguyên giá " + T.fmtMoney(sel.row.gross) : "") + "</div>" +
          (can.manage ? '<div class="ts-actions" style="margin-top:8px"><button type="button" class="ts-btn ts-sm" data-rm="' + esc(sel.row.name) + '">Tháo ra, về kho</button>' +
            '<button type="button" class="ts-btn ts-sm ts-danger" data-rmb="' + esc(sel.row.name) + '">Tháo ra, đánh dấu hỏng</button></div>' : "") :
        '<b class="ts-strong">' + esc(sel.type || "") + "</b>: " + esc(sel.spec || "") + (sel.note ? '<div class="ts-note">' + esc(sel.note) + "</div>" : "") +
          '<div class="ts-note">Thuộc cấu hình gốc, tính chung vào nguyên giá máy.</div>') + "</div>" : "") +
      (can.manage && !d.is_component_category ? '<div class="ts-actions"><button type="button" class="ts-btn" data-specs>Sửa cấu hình gốc</button>' +
        '<button type="button" class="ts-btn ts-primary" data-install>' + T.icon("plus") + "Lắp linh kiện</button></div>" : "");
    body.onclick = function (e) {
      var op = e.target.closest("[data-open]"); if (op) { openDrawer(op.getAttribute("data-open")); return; }
      var pi = e.target.closest("[data-pi]");
      if (pi) { var i = Number(pi.getAttribute("data-pi")); cur.partSel = cur.partSel === i ? null : i; tabParts(body, d); return; }
      var rm = e.target.closest("[data-rm],[data-rmb]");
      if (rm) {
        var broken = rm.hasAttribute("data-rmb"), comp = rm.getAttribute(broken ? "data-rmb" : "data-rm");
        T.confirmBox("Tháo linh kiện", broken ? "Tháo ra và chuyển linh kiện sang Hỏng chờ xử lý?" : "Tháo ra và trả linh kiện về kho (Sẵn sàng)?", "Tháo ra", broken).then(function (ok) {
          if (!ok) return;
          T.post("remove_component", { component: comp, to_status: broken ? "Broken" : "" }).then(function () { T.toast("Đã tháo linh kiện."); cur.partSel = null; refreshAll(); },
            function (er) { T.toast(T.msg(er), true); });
        });
        return;
      }
      if (e.target.closest("[data-specs]")) { editSpecs(d); return; }
      if (e.target.closest("[data-install]")) installComp(d);
    };
  }

  function editSpecs(d) {
    var tpl = d.spec_template || [];
    var rows = (d.specs || []).length ? d.specs.map(function (s) { return { part_type: s.part_type, spec: s.spec, qty: s.qty || 1, note: s.note || "" }; }) :
      tpl.map(function (p) { return { part_type: p, spec: "", qty: 1, note: "" }; });
    function rowHtml(r) {
      return '<div class="ts-row" data-r style="align-items:flex-end"><label class="ts-lbl" style="flex:0 0 130px">Bộ phận<input class="ts-in" data-k="part_type" list="ts-spec-tpl" value="' + esc(r.part_type) + '"></label>' +
        '<label class="ts-lbl" style="flex:1">Thông số<input class="ts-in" data-k="spec" value="' + esc(r.spec) + '"></label>' +
        '<label class="ts-lbl" style="flex:0 0 64px">SL<input class="ts-in" data-k="qty" inputmode="numeric" value="' + esc(r.qty) + '"></label>' +
        '<button type="button" class="ts-btn ts-sm" data-del aria-label="Xoá dòng">' + T.icon("x") + "</button></div>";
    }
    T.modal("Cấu hình gốc · " + (d.asset.tag || d.asset.name),
      '<datalist id="ts-spec-tpl">' + tpl.map(function (p) { return '<option value="' + esc(p) + '">'; }).join("") + "</datalist>" +
      '<div data-rows style="display:flex;flex-direction:column;gap:8px">' + rows.map(rowHtml).join("") + "</div>" +
      '<button type="button" class="ts-btn ts-sm" data-add>' + T.icon("plus") + "Thêm dòng</button>" +
      '<div class="ts-note">Cấu hình gốc là phần mua kèm máy, không có mã tài sản riêng. Linh kiện mua sau dùng "Lắp linh kiện".</div>',
      '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>Lưu cấu hình</button>',
      function (el, close) {
        var box = el.querySelector("[data-rows]");
        el.querySelector("[data-add]").addEventListener("click", function () { box.insertAdjacentHTML("beforeend", rowHtml({ part_type: "", spec: "", qty: 1 })); });
        box.addEventListener("click", function (e) { var x = e.target.closest("[data-del]"); if (x) x.closest("[data-r]").remove(); });
        el.querySelector("[data-ok]").addEventListener("click", function (ev) {
          var btn = ev.currentTarget;
          var out = T.qsa(box, "[data-r]").map(function (r) {
            function v(k) { return r.querySelector('[data-k="' + k + '"]').value.trim(); }
            return { part_type: v("part_type"), spec: v("spec"), qty: Number(v("qty")) || 1, note: "" };
          }).filter(function (r) { return r.part_type && r.spec; });
          T.busy(btn, true);
          T.post("save_specs", { asset: d.asset.name, rows: out }).then(function () { close(); T.toast("Đã lưu cấu hình gốc."); loadDetail(); },
            function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
        });
      }, true);
  }

  function installComp(d) {
    T.modal("Lắp linh kiện vào " + (d.asset.tag || d.asset.name),
      '<div data-pk>' + T.skel(4) + '</div><div class="ts-note">Chỉ hiện linh kiện đang Sẵn sàng trong kho. Nguyên giá linh kiện khấu hao riêng.</div>',
      '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok disabled>Lắp vào máy</button>',
      function (el, close) {
        var pick = null, ok = el.querySelector("[data-ok]");
        T.pickList("components").then(function (rows) {
          pick = T.picker(el.querySelector("[data-pk]"), rows, { placeholder: "Tag, loại, thông số…",
            label: function (r) { return (r.tag || r.name) + " · " + (r.asset_name || ""); }, sub: function (r) { return [r.category, r.specs].filter(Boolean).join(" · "); },
            text: function (r) { return [r.tag, r.name, r.asset_name, r.category, r.specs].join(" "); }, onPick: function () { ok.disabled = false; } });
        }, function (e) { el.querySelector("[data-pk]").innerHTML = T.errBox(e); });
        ok.addEventListener("click", function () {
          T.busy(ok, true);
          T.post("install_component", { component: pick.value(), parent: d.asset.name }).then(function () { close(); T.toast("Đã lắp linh kiện."); refreshAll(); },
            function (e) { T.busy(ok, false); T.toast(T.msg(e), true); });
        });
      }, true);
  }

  // ------------------------------------------------------------- khau hao --
  function curve(points, nowYm) {
    if (!points || points.length < 2) return "";
    var W = 540, H = 180, pl = 54, pr = 10, pt = 10, pb = 26;
    var max = 0;
    points.forEach(function (p) { max = Math.max(max, Number(p[1] || 0)); });
    function x(i) { return pl + i * (W - pl - pr) / (points.length - 1); }
    function y(v) { return pt + (max ? (1 - v / max) : 1) * (H - pt - pb); }
    var line = points.map(function (p, i) { return (i ? "L" : "M") + x(i).toFixed(1) + " " + y(Number(p[1] || 0)).toFixed(1); }).join(" ");
    var nowI = -1;
    points.forEach(function (p, i) { if (p[0] <= nowYm) nowI = i; });
    var step = Math.max(1, Math.ceil(points.length / 6));
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Đường giá trị còn lại">' +
      '<line x1="' + pl + '" y1="' + (H - pb) + '" x2="' + (W - pr) + '" y2="' + (H - pb) + '" stroke="#e5e7eb"/>' +
      '<text x="' + (pl - 6) + '" y="' + (pt + 4) + '" font-size="10" text-anchor="end" fill="#6b7280">' + esc(T.fmtMillion(max)) + "</text>" +
      '<text x="' + (pl - 6) + '" y="' + (H - pb) + '" font-size="10" text-anchor="end" fill="#6b7280">0</text>' +
      '<path d="' + line + " L" + x(points.length - 1).toFixed(1) + " " + (H - pb) + " L" + pl + " " + (H - pb) + ' Z" fill="#eef0fb"/>' +
      '<path d="' + line + '" fill="none" stroke="#2C3DA6" stroke-width="2"/>';
    points.forEach(function (p, i) {
      if (i % step === 0 || i === points.length - 1) s += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 8) + '" font-size="10" text-anchor="middle" fill="#6b7280">' + esc(T.fmtMonth(p[0])) + "</text>";
    });
    if (nowI >= 0) s += '<circle cx="' + x(nowI).toFixed(1) + '" cy="' + y(Number(points[nowI][1] || 0)).toFixed(1) + '" r="4.5" fill="#2C3DA6" stroke="#fff" stroke-width="2"/>';
    return s + "</svg>";
  }

  function tabDep(body, d) {
    var dp = d.depreciation;
    if (!(d.can && d.can.see_cost) || !dp) {
      body.innerHTML = '<div class="ts-empty">' + (d.can && d.can.see_cost ? "Thiết bị chưa có dữ liệu khấu hao." : "Số tiền và khấu hao chỉ hiện với quản lý tài sản và tài chính.") + "</div>";
      return;
    }
    var now = new Date().toISOString().slice(0, 7);
    body.innerHTML = '<div class="ts-info">' +
      kv("Nguyên giá", T.fmtMoney(dp.gross)) + kv("Giá trị thu hồi", T.fmtMoney(dp.salvage)) +
      kv("Thời gian khấu hao", T.fmtNum(dp.life) + " tháng") + kv("Từ – đến", T.fmtMonth(dp.start) + " – " + T.fmtMonth(dp.end)) +
      kv("Mỗi tháng", T.fmtMoney(dp.monthly)) + kv("Đã khấu hao", T.fmtNum(dp.months_done) + "/" + T.fmtNum(dp.life) + " tháng") +
      kv("Luỹ kế", T.fmtMoney(dp.accumulated)) + kv("Còn lại", "<span" + (dp.fully_depreciated ? ' class="ts-muted"' : "") + ">" + T.fmtMoney(dp.nbv) + "</span>") +
      kv("Tháng này", T.fmtMoney(dp.this_month)) + (dp.components_total ? kv("Linh kiện lắp thêm", T.fmtMoney(dp.components_total)) : "") + "</div>" +
      '<div class="ts-bar"><span style="width:' + (dp.life ? Math.min(100, dp.months_done * 100 / dp.life) : 0) + '%"></span></div>' +
      (dp.fully_depreciated ? '<div class="ts-infobox">Đã khấu hao hết, vẫn dùng bình thường.</div>' : "") +
      '<div class="ts-diagram">' + curve(dp.curve, now) + "</div>" +
      '<div class="ts-note">Khấu hao quản trị theo đường thẳng — chưa ghi sổ kế toán.</div>';
  }

  // -------------------------------------------------------------- lich su --
  function tabHist(body, d) {
    var ev = d.events || [];
    if (!ev.length) { body.innerHTML = '<div class="ts-empty">Chưa có sự kiện nào.</div>'; return; }
    body.innerHTML = '<ul class="ts-tl">' + ev.map(function (e) {
      var ck = e.checklist && typeof e.checklist === "object" ? Object.keys(e.checklist).filter(function (k) { return e.checklist[k]; }) : [];
      return "<li><div class=\"ts-row\"><b class=\"ts-strong\">" + esc(e.label) + '</b><span class="ts-sp"></span><span class="ts-note">' + T.fmtDT(e.time) + "</span></div>" +
        '<div class="ts-note">' + (e.from_status || e.to_status ? esc(T.statusLabel(e.from_status)) + " → " + esc(T.statusLabel(e.to_status)) : "") +
        (e.from_employee || e.to_employee ? " · " + esc(e.from_employee || "kho") + " → " + esc(e.to_employee || "kho") : "") +
        (e.actor ? " · bởi " + esc(e.actor) : "") + "</div>" +
        (e.related_asset ? '<div class="ts-note">Liên quan: <button type="button" class="ts-link" data-open="' + esc(e.related_asset) + '">' + esc(e.related_asset) + "</button></div>" : "") +
        (e.ref_name ? '<div class="ts-note">Chứng từ: ' + (e.ref_route ? '<a href="' + esc(e.ref_route) + '" target="_blank" rel="noopener">' + esc(e.ref_name) + "</a>" : esc(e.ref_name)) + "</div>" : "") +
        (ck.length ? '<div class="ts-note">Checklist: ' + esc(ck.join(", ")) + "</div>" : "") +
        (e.note ? '<div class="ts-note">' + esc(e.note) + "</div>" : "") +
        (e.acknowledged_at ? '<div class="ts-note" style="color:#047857">Nhân viên đã xác nhận ' + T.fmtDT(e.acknowledged_at) + "</div>" : "") + "</li>";
    }).join("") + "</ul>";
    body.onclick = function (e) { var op = e.target.closest("[data-open]"); if (op) openDrawer(op.getAttribute("data-open")); };
  }

  // ------------------------------------------------------------- sua chua --
  function tabRep(body, d) {
    var can = d.can || {}, reps = d.repairs || [];
    var specParts = (d.specs || []).map(function (s) { return s.part_type; });
    body.innerHTML = (can.manage ? '<div class="ts-row"><span class="ts-sp"></span><button type="button" class="ts-btn ts-primary" data-open-rep>' + T.icon("wrench") + "Báo hỏng / gửi sửa</button></div>" : "") +
      (reps.length ? reps.map(function (r) {
        var open = r.status === "Open" || r.status === "In Repair";
        return '<div class="ts-kc' + (r.overdue ? " ts-late" : "") + '"><div class="ts-row"><b class="ts-strong">' + esc(r.name) + "</b>" +
          '<span class="ts-pill">' + esc(r.status_label || r.status) + "</span>" + (r.overdue ? '<span class="ts-pill ts-red">Quá hẹn</span>' : "") + '<span class="ts-sp"></span>' +
          '<span class="ts-note">' + T.fmtDate(r.sent_date) + (r.returned_date ? " → " + T.fmtDate(r.returned_date) : r.expected_return ? " · hẹn " + T.fmtDate(r.expected_return) : "") + "</span></div>" +
          '<div class="ts-note">' + esc(r.mode_label || "") + (r.vendor ? " · " + esc(r.vendor) : "") + (r.damaged_parts ? " · " + esc(r.damaged_parts) : "") + "</div>" +
          (r.expected_cost != null || r.actual_cost != null ? '<div class="ts-note">Dự kiến ' + T.fmtMoney(r.expected_cost) + (r.actual_cost ? " · thực tế " + T.fmtMoney(r.actual_cost) : "") + "</div>" : "") +
          (r.result ? '<div class="ts-note">Kết quả: ' + (r.result === "Fixed" ? "Sửa được" : "Không sửa được") + "</div>" : "") +
          (r.loaner_asset ? '<div class="ts-note">Máy tạm: ' + esc(r.loaner_asset) + "</div>" : "") +
          (open && can.manage ? '<div class="ts-actions"><button type="button" class="ts-btn ts-sm ts-primary" data-close-rep="' + esc(r.name) + '">Nhận lại</button>' +
            '<button type="button" class="ts-btn ts-sm" data-cancel-rep="' + esc(r.name) + '">Huỷ phiếu</button></div>' : "") + "</div>";
      }).join("") : '<div class="ts-empty">Chưa sửa lần nào.</div>');
    body.onclick = function (e) {
      if (e.target.closest("[data-open-rep]")) { O.openRepair(d.asset, specParts).then(function (r) { if (r) refreshAll(); }); return; }
      var c = e.target.closest("[data-close-rep]");
      if (c) {
        var rep = reps.filter(function (x) { return x.name === c.getAttribute("data-close-rep"); })[0];
        O.closeRepair(rep).then(function (r) { if (r) refreshAll(); });
        return;
      }
      var x = e.target.closest("[data-cancel-rep]");
      if (x) {
        T.confirmBox("Huỷ phiếu sửa", "Huỷ phiếu " + x.getAttribute("data-cancel-rep") + "? Máy về trạng thái trước khi gửi sửa.", "Huỷ phiếu", true).then(function (ok) {
          if (!ok) return;
          T.post("cancel_repair", { repair: x.getAttribute("data-cancel-rep") }).then(function () { T.toast("Đã huỷ phiếu."); refreshAll(); }, function (er) { T.toast(T.msg(er), true); });
        });
      }
    };
  }

  function start() {
    root = document.getElementById("ts-root");
    if (!root) return;
    shell();
    loadList();
    if (cur.asset) openDrawer(cur.asset);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && cur.asset && !document.querySelector("#ec-ts .ts-modal-bg")) closeDrawer(); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
