// Copyright (c) 2026, eCentric and contributors
// ec_ts_repairs.js -- trang /tai-san/sua-chua: phieu sua chua theo trang thai + chi phi 12 thang.
(function () {
  "use strict";
  var T = window.ECTs, O = window.ECTsOps, esc = T.esc;
  var TABS = [["", "Tất cả"], ["Open", "Chờ gửi"], ["In Repair", "Đang sửa"], ["Done", "Đã xong"], ["Cancelled", "Đã huỷ"]];
  var st = { status: T.param("status") }, root, box, data = null;

  function shell() {
    root.innerHTML = '<div class="ts-wrap"><div class="ts-head"><div class="ts-head-main"><h1 class="ts-title">Sửa chữa thiết bị</h1>' +
      '<div class="ts-sub">Mở phiếu sửa từ chi tiết thiết bị hoặc bảng Cấp phát &amp; thu hồi.</div></div>' +
      '<div class="ts-filters"><a class="ts-btn" href="/tai-san/luan-chuyen">Bảng luân chuyển</a></div></div>' +
      '<div class="ts-chips" data-tabs role="tablist">' + TABS.map(function (t) {
        return '<button type="button" class="ts-chip' + (t[0] === st.status ? " on" : "") + '" role="tab" data-s="' + esc(t[0]) + '">' + esc(t[1]) + "</button>";
      }).join("") + '</div><div data-box></div></div>';
    box = root.querySelector("[data-box]");
    root.querySelector("[data-tabs]").addEventListener("click", function (e) {
      var b = e.target.closest("[data-s]"); if (!b) return;
      st.status = b.getAttribute("data-s"); T.setParam("status", st.status);
      T.qsa(root, "[data-tabs] .ts-chip").forEach(function (x) { x.classList.toggle("on", x === b); });
      load();
    });
    box.addEventListener("click", onClick);
  }

  function load() {
    box.innerHTML = T.skel(6);
    T.get("repairs", st.status ? { status: st.status } : {}).then(function (d) { data = d; render(); }, function (e) {
      box.innerHTML = T.errBox(e, true);
      var b = box.querySelector("[data-retry]"); if (b) b.addEventListener("click", load);
    });
  }

  function costChart(cbm) {
    var keys = Object.keys(cbm || {}).sort();
    if (!keys.length) return "";
    var max = 0;
    keys.forEach(function (k) { max = Math.max(max, Number(cbm[k] || 0)); });
    return '<div class="ts-card"><div class="ts-card-h"><div class="ts-card-t">Chi phí sửa chữa 12 tháng</div><span class="ts-sp"></span>' +
      '<span class="ts-note">Tổng ' + T.fmtMoney(keys.reduce(function (s, k) { return s + Number(cbm[k] || 0); }, 0)) + "</span></div>" +
      '<div class="ts-cols">' + keys.map(function (k) {
        var v = Number(cbm[k] || 0);
        return '<div class="ts-col"><div class="ts-col-v">' + (v ? T.fmtMillion(v).replace(" tr", "") : "") + '</div><div class="ts-col-b" style="height:' + (max ? Math.round(v * 150 / max) : 0) +
          'px;background:#d97706" title="' + esc(T.fmtMonth(k) + ": " + T.fmtMoney(v)) + '"></div></div>';
      }).join("") + '</div><div class="ts-col-x">' + keys.map(function (k) { return "<span>" + esc(T.fmtMonth(k)) + "</span>"; }).join("") + "</div>" +
      '<div class="ts-note" style="margin-top:6px">Triệu đồng, theo ngày nhận lại.</div></div>';
  }

  function render() {
    var d = data, can = d.can || {}, rows = d.rows || [], rep = d.repeat || {};
    var cost = can.see_cost;
    box.innerHTML = (cost ? costChart(d.cost_by_month) : "") +
      '<div class="ts-card" style="padding:0">' + (rows.length ? '<div class="ts-table-wrap"><table class="ts-table"><thead><tr><th>Phiếu</th><th>Thiết bị</th><th>Hỏng</th><th>Hình thức</th>' +
        "<th>Gửi</th><th>Hẹn / nhận lại</th>" + (cost ? '<th class="ts-num">Chi phí</th>' : "") + "<th>Trạng thái</th><th></th></tr></thead><tbody>" +
        rows.map(function (r) {
          var open = r.status === "Open" || r.status === "In Repair";
          return "<tr><td class=\"ts-strong\">" + esc(r.name) + "</td>" +
            '<td><a class="ts-strong" href="/tai-san/thiet-bi?asset=' + encodeURIComponent(r.asset) + '">' + esc(r.tag || r.asset) + "</a>" +
            (rep[r.asset] ? '<span class="ts-repeat" title="Sửa lặp lại">Sửa ' + rep[r.asset] + " lần</span>" : "") + '<div class="ts-note">' + esc(r.asset_name || "") + "</div></td>" +
            "<td>" + (r.damage_level === "Full" ? "Toàn bộ" : "Một phần") + (r.damaged_parts ? '<div class="ts-note">' + esc(r.damaged_parts) + "</div>" : "") + "</td>" +
            "<td>" + esc(r.mode_label || "") + (r.vendor ? '<div class="ts-note">' + esc(r.vendor) + "</div>" : "") + (r.loaner_asset ? '<div class="ts-note">Máy tạm ' + esc(r.loaner_asset) + "</div>" : "") + "</td>" +
            "<td>" + T.fmtDate(r.sent_date) + "</td>" +
            "<td" + (r.overdue ? ' class="ts-bad-text"' : "") + ">" + (r.returned_date ? T.fmtDate(r.returned_date) : r.expected_return ? "hẹn " + T.fmtDate(r.expected_return) : "—") + (r.overdue ? '<div class="ts-note ts-bad-text">Quá hẹn</div>' : "") + "</td>" +
            (cost ? '<td class="ts-num">' + (r.actual_cost ? T.fmtMoney(r.actual_cost) : r.expected_cost ? '<span class="ts-muted">~' + T.fmtMoney(r.expected_cost) + "</span>" : "") + "</td>" : "") +
            '<td><span class="ts-pill">' + esc(r.status_label || r.status) + "</span>" + (r.result ? '<div class="ts-note">' + (r.result === "Fixed" ? "Sửa được" : "Không sửa được") + "</div>" : "") + "</td>" +
            "<td>" + (open && can.manage ? '<div class="ts-row" style="flex-wrap:nowrap"><button type="button" class="ts-btn ts-sm ts-primary" data-close-rep="' + esc(r.name) + '">Nhận lại</button>' +
              '<button type="button" class="ts-btn ts-sm" data-cancel-rep="' + esc(r.name) + '">Huỷ</button></div>' : "") + "</td></tr>";
        }).join("") + "</tbody></table></div>" : '<div class="ts-empty" style="padding:32px">Không có phiếu sửa chữa nào.</div>') + "</div>" +
      '<div class="ts-note">Máy sửa lặp lại nhiều lần được đánh dấu đỏ để cân nhắc thay mới.</div>';
  }

  function onClick(e) {
    var c = e.target.closest("[data-close-rep]");
    if (c) {
      var rep = (data.rows || []).filter(function (r) { return r.name === c.getAttribute("data-close-rep"); })[0];
      O.closeRepair(rep).then(function (r) { if (r) load(); });
      return;
    }
    var x = e.target.closest("[data-cancel-rep]");
    if (x) {
      var name = x.getAttribute("data-cancel-rep");
      T.confirmBox("Huỷ phiếu sửa", "Huỷ phiếu " + name + "? Máy về trạng thái trước khi gửi sửa.", "Huỷ phiếu", true).then(function (ok) {
        if (!ok) return;
        T.post("cancel_repair", { repair: name }).then(function () { T.toast("Đã huỷ phiếu."); load(); }, function (er) { T.toast(T.msg(er), true); });
      });
    }
  }

  function start() {
    root = document.getElementById("ts-root");
    if (!root) return;
    shell();
    load();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
