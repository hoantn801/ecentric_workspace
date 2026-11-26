// Copyright (c) 2026, eCentric and contributors
// ec_ts_moves.js -- trang /tai-san/luan-chuyen: bang 4 cot cap phat / thu hoi / kiem tra / dang sua.
(function () {
  "use strict";
  var T = window.ECTs, O = window.ECTsOps, esc = T.esc;
  var root, data = null;

  function load() {
    if (!data) root.innerHTML = '<div class="ts-wrap">' + T.skel(6) + "</div>";
    T.get("board", {}).then(function (d) { data = d; render(); }, function (e) {
      root.innerHTML = '<div class="ts-wrap">' + T.errBox(e, true) + "</div>";
      var b = root.querySelector("[data-retry]"); if (b) b.addEventListener("click", load);
    });
  }

  function assetA(r) {
    return '<a class="ts-strong" href="/tai-san/thiet-bi?asset=' + encodeURIComponent(r.name || r.asset) + '">' + esc(r.tag || r.name || r.asset) + "</a>";
  }
  function col(title, n, dotColor, inner, empty) {
    return '<section class="ts-colk"><div class="ts-colk-h"><span class="ts-dot" style="background:' + dotColor + '"></span>' + esc(title) +
      '<span class="ts-sp"></span><span class="ts-tag">' + n + "</span></div>" + (inner || '<div class="ts-note" style="padding:6px 4px">' + esc(empty) + "</div>") + "</section>";
  }

  function render() {
    var d = data, can = d.can || {};
    var alloc = (d.allocate || []).map(function (c, i) {
      return '<div class="ts-kc"><div class="ts-row"><b class="ts-strong">' + esc(c.employee_name || c.source) + '</b><span class="ts-sp"></span>' +
        (c.due ? '<span class="ts-note">' + T.fmtDate(c.due) + "</span>" : "") + "</div>" +
        '<div class="ts-note"><a href="' + esc(c.route) + '" target="_blank" rel="noopener">' + esc(c.source_label || "") + " " + esc(c.source) + "</a>" + (c.department ? " · " + esc(c.department) : "") + "</div>" +
        (c.need ? '<div class="ts-note">' + esc(c.need) + "</div>" : "") +
        (c.reserved_asset ? '<div class="ts-note">Đã giữ chỗ: <b>' + esc(c.reserved_asset) + "</b></div>" : "") +
        (c.source_type === "EC New Staff Preparation" && !c.has_employee ? '<div class="ts-note" style="color:#92400e">Chưa có hồ sơ nhân viên: chỉ giữ chỗ được.</div>' : "") +
        (can.manage ? '<button type="button" class="ts-btn ts-sm ts-primary" data-alloc="' + i + '">' + (c.source_type === "EC New Staff Preparation" && !c.has_employee ? "Giữ chỗ" : "Cấp phát") + "</button>" : "") + "</div>";
    }).join("") + (d.reserved || []).map(function (r) {
      return '<div class="ts-kc"><div class="ts-row">' + assetA(r) + '<span class="ts-sp"></span>' + T.pill(r.status) + "</div>" +
        '<div class="ts-note">' + esc(r.asset_name || "") + (r.reserved_for ? " · giữ cho " + esc(r.reserved_for) : "") + "</div>" +
        (can.manage ? '<div class="ts-actions"><button type="button" class="ts-btn ts-sm ts-primary" data-tr="assign" data-a="' + esc(r.name) + '">Cấp phát</button>' +
          '<button type="button" class="ts-btn ts-sm" data-tr="unreserve" data-a="' + esc(r.name) + '">Bỏ giữ chỗ</button></div>' : "") + "</div>";
    }).join("");
    var rets = (d.returns || []).map(function (c, i) {
      var late = c.days_left < 0, soon = c.days_left <= 2;
      return '<div class="ts-kc' + (late ? " ts-late" : "") + '"><div class="ts-row"><b class="ts-strong">' + esc(c.employee_name || c.employee) + '</b><span class="ts-sp"></span>' +
        (c.all_returned ? '<span class="ts-pill">' + T.dot("Available") + "Đã thu đủ</span>" :
          '<span class="ts-note' + (soon ? " ts-bad-text" : "") + '">' + (late ? "Quá " + (-c.days_left) + " ngày" : c.days_left === 0 ? "Hôm nay" : "Còn " + c.days_left + " ngày") + "</span>") + "</div>" +
        '<div class="ts-note"><a href="' + esc(c.route) + '" target="_blank" rel="noopener">Clearance ' + esc(c.source) + "</a> · ngày cuối " + T.fmtDate(c.last_working_day) + "</div>" +
        (c.assets || []).map(function (a) {
          return '<div class="ts-row" style="border-top:1px solid #f3f4f6;padding-top:6px">' + assetA(a) + '<span class="ts-note" style="flex:1;min-width:0">' + esc(a.asset_name || "") + "</span>" +
            (can.manage ? '<button type="button" class="ts-btn ts-sm" data-ret="' + i + '" data-a="' + esc(a.name) + '">Nhận lại</button>' : "") + "</div>";
        }).join("") + "</div>";
    }).join("");
    var checks = (d.checks || []).map(function (r) {
      return '<div class="ts-kc"><div class="ts-row">' + assetA(r) + '<span class="ts-sp"></span>' + T.pill(r.status) + "</div><div class=\"ts-note\">" + esc(r.asset_name || "") + "</div>" +
        (can.manage ? '<div class="ts-actions"><button type="button" class="ts-btn ts-sm ts-primary" data-chk="1" data-a="' + esc(r.name) + '">Đạt</button>' +
          '<button type="button" class="ts-btn ts-sm ts-danger" data-chk="0" data-a="' + esc(r.name) + '">Không đạt</button></div>' : "") + "</div>";
    }).join("") + (d.broken || []).map(function (r) {
      return '<div class="ts-kc"><div class="ts-row">' + assetA(r) + '<span class="ts-sp"></span>' + T.pill(r.status) + "</div><div class=\"ts-note\">" + esc(r.asset_name || "") +
        (r.holder_name ? " · " + esc(r.holder_name) : "") + "</div>" + (r.condition && r.condition !== "Good" ? "<div>" + T.condPill(r.condition) + "</div>" : "") +
        (can.manage ? '<button type="button" class="ts-btn ts-sm" data-rep="' + esc(r.name) + '">' + T.icon("wrench") + "Gửi sửa</button>" : "") + "</div>";
    }).join("");
    var reps = (d.repairs || []).map(function (r) {
      return '<div class="ts-kc' + (r.overdue ? " ts-late" : "") + '"><div class="ts-row">' + assetA(r) + '<span class="ts-sp"></span>' +
        (r.overdue ? '<span class="ts-pill ts-red">Quá hẹn</span>' : '<span class="ts-pill">' + esc(r.status_label || "") + "</span>") + "</div>" +
        '<div class="ts-note">' + esc(r.asset_name || "") + "</div><div class=\"ts-note\">" + esc(r.mode_label || "") + (r.vendor ? " · " + esc(r.vendor) : "") +
        (r.expected_return ? " · hẹn " + T.fmtDate(r.expected_return) : "") + "</div>" + (r.loaner_asset ? '<div class="ts-note">Máy tạm: ' + esc(r.loaner_asset) + "</div>" : "") +
        (can.manage ? '<button type="button" class="ts-btn ts-sm" data-close-rep="' + esc(r.name) + '">Nhận lại</button>' : "") + "</div>";
    }).join("");
    var dmg = d.damage_requests || [];
    root.innerHTML = '<div class="ts-wrap">' +
      '<div class="ts-head"><div class="ts-head-main"><h1 class="ts-title">Cấp phát &amp; thu hồi</h1>' +
      '<div class="ts-sub">Thẻ lấy từ phiếu Chuẩn bị nhân sự mới, Xin cấp tài sản, Clearance và Báo hỏng / mất.</div></div>' +
      '<div class="ts-filters"><button type="button" class="ts-btn" data-reload>Làm mới</button>' +
      (can.manage ? '<button type="button" class="ts-btn ts-primary" data-alloc-free>' + T.icon("plus") + "Cấp phát</button>" : "") + "</div></div>" +
      (dmg.length ? '<div class="ts-strip"><div class="ts-eb">Phiếu Báo hỏng / mất đã duyệt · ' + dmg.length + "</div>" + dmg.map(function (r, i) {
        return '<div class="ts-li"><div class="ts-li-main"><a href="' + esc(r.route) + '" target="_blank" rel="noopener" class="ts-strong">' + esc(r.title || r.source) + "</a>" +
          '<div class="ts-note">' + esc(r.incident_type || "") + " · " + T.fmtDate(r.incident_date) + " · " + (r.asset ? "máy " + esc(r.tag || r.asset) : '<span class="ts-bad-text">mã "' + esc(r.asset_code || "") + '" không khớp thiết bị nào</span>') +
          (r.estimated_cost != null ? " · dự kiến " + T.fmtMoney(r.estimated_cost) : "") + "</div></div>" +
          (can.manage && r.asset ? '<div class="ts-actions" style="flex:0 0 auto"><button type="button" class="ts-btn ts-sm" data-dmg="repair" data-i="' + i + '">Gửi sửa</button>' +
            '<button type="button" class="ts-btn ts-sm ts-danger" data-dmg="lost" data-i="' + i + '">Báo mất</button></div>' : "") + "</div>";
      }).join("") + "</div>" : "") +
      '<div class="ts-board">' +
      col("Chờ cấp phát", (d.allocate || []).length + (d.reserved || []).length, "#2C3DA6", alloc, "Không có yêu cầu cấp máy.") +
      col("Chờ thu hồi", (d.returns || []).length, "#d97706", rets, "Không có ai sắp nghỉ đang giữ máy.") +
      col("Chờ kiểm tra", (d.checks || []).length + (d.broken || []).length, "#9ca3af", checks, "Không có máy chờ kiểm tra.") +
      col("Đang sửa", (d.repairs || []).length, "#dc2626", reps, "Không có máy đang sửa.") + "</div>" +
      '<div class="ts-note">00:40 ngày làm việc cuối của người nghỉ, máy chưa trả tự chuyển sang Chờ kiểm tra. Sửa chữa dự kiến trên ' + T.fmtMoney(d.repair_threshold) + " cần phiếu Báo hỏng / mất được duyệt.</div></div>";
  }

  function returnModal(card, asset) {
    T.modal("Nhận lại máy · " + (card.employee_name || ""),
      '<p class="ts-muted">' + esc(asset.tag || asset.name) + " · " + esc(asset.asset_name || "") + "</p>" +
      '<div><div class="ts-lbl" style="margin-bottom:6px">Checklist nhận lại</div>' + T.checklistHtml(data.return_checklist, "ret") + "</div>" +
      '<label class="ts-lbl">Ghi chú<textarea class="ts-ta" name="note" maxlength="1000"></textarea></label>' +
      '<div class="ts-note">Máy chuyển sang Chờ kiểm tra; kiểm tra xong mới về kho.</div>',
      '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>Xác nhận đã nhận</button>',
      function (el, close) {
        el.querySelector("[data-ok]").addEventListener("click", function (ev) {
          var btn = ev.currentTarget; T.busy(btn, true);
          T.post("return_for_clearance", { asset: asset.name, clearance: card.source, checklist: T.checklistValue(el, "ret"), note: el.querySelector('[name="note"]').value })
            .then(function () { close(); T.toast("Đã nhận lại máy."); load(); }, function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
        });
      });
  }

  function checkModal(asset, passed) {
    T.modal((passed ? "Kiểm tra đạt · " : "Kiểm tra không đạt · ") + (asset.tag || asset.name),
      '<p class="ts-muted">' + esc(asset.asset_name || "") + "</p>" +
      '<div><div class="ts-lbl" style="margin-bottom:6px">Đã kiểm tra</div>' + T.checklistHtml(data.return_checklist, "chk") + "</div>" +
      '<label class="ts-lbl">Tình trạng' + O.condSelect("condition", passed ? "Good" : "Partially Damaged") + "</label>" +
      '<label class="ts-lbl">Ghi chú<textarea class="ts-ta" name="note" maxlength="1000"></textarea></label>' +
      '<div class="ts-note">' + (passed ? "Máy về kho, trạng thái Sẵn sàng." : "Máy chuyển sang Hỏng chờ xử lý.") + "</div>",
      '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ' + (passed ? "ts-primary" : "ts-danger") + '" data-ok>' + (passed ? "Đạt, về kho" : "Không đạt") + "</button>",
      function (el, close) {
        el.querySelector("[data-ok]").addEventListener("click", function (ev) {
          var btn = ev.currentTarget; T.busy(btn, true);
          T.post("check", { asset: asset.name, passed: passed ? 1 : 0, checklist: T.checklistValue(el, "chk"), note: el.querySelector('[name="note"]').value,
            condition: el.querySelector('[name="condition"]').value })
            .then(function () { close(); T.toast("Đã ghi kết quả kiểm tra."); load(); }, function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
        });
      });
  }

  function find(list, name) { return (list || []).filter(function (r) { return r.name === name; })[0]; }

  function onClick(e) {
    var t;
    if (e.target.closest("[data-reload]")) { load(); return; }
    if (e.target.closest("[data-alloc-free]")) { O.allocate(null, data.handover_checklist).then(function (r) { if (r) load(); }); return; }
    if ((t = e.target.closest("[data-alloc]"))) { O.allocate(data.allocate[Number(t.getAttribute("data-alloc"))], data.handover_checklist).then(function (r) { if (r) load(); }); return; }
    if ((t = e.target.closest("[data-tr]"))) {
      var r0 = find(data.reserved, t.getAttribute("data-a"));
      var act = t.getAttribute("data-tr");
      O.transition(r0, act, act === "assign" ? "Cấp phát" : "Bỏ giữ chỗ").then(function (r) { if (r) load(); });
      return;
    }
    if ((t = e.target.closest("[data-ret]"))) {
      var card = data.returns[Number(t.getAttribute("data-ret"))];
      returnModal(card, find(card.assets, t.getAttribute("data-a")));
      return;
    }
    if ((t = e.target.closest("[data-chk]"))) { checkModal(find(data.checks, t.getAttribute("data-a")), t.getAttribute("data-chk") === "1"); return; }
    if ((t = e.target.closest("[data-rep]"))) { O.openRepair(find(data.broken, t.getAttribute("data-rep")), []).then(function (r) { if (r) load(); }); return; }
    if ((t = e.target.closest("[data-close-rep]"))) { O.closeRepair(find(data.repairs, t.getAttribute("data-close-rep"))).then(function (r) { if (r) load(); }); return; }
    if ((t = e.target.closest("[data-dmg]"))) {
      var req = data.damage_requests[Number(t.getAttribute("data-i"))];
      var asset = { name: req.asset, tag: req.tag, asset_name: req.title };
      if (t.getAttribute("data-dmg") === "repair") { O.openRepair(asset, [], req.source).then(function (r) { if (r) load(); }); return; }
      T.confirmBox("Báo mất theo phiếu", "Chuyển " + (req.tag || req.asset) + " sang Mất theo phiếu " + req.source + "?", "Báo mất", true).then(function (ok) {
        if (!ok) return;
        T.post("handle_damage_request", { request: req.source, asset: req.asset, action: "lost", data: {} })
          .then(function () { T.toast("Đã chuyển sang Mất."); load(); }, function (er) { T.toast(T.msg(er), true); });
      });
    }
  }

  function start() {
    root = document.getElementById("ts-root");
    if (!root) return;
    root.addEventListener("click", onClick);
    load();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
