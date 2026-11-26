// Copyright (c) 2026, eCentric and contributors
// ec_ts_count.js -- trang /tai-san/kiem-ke: mo dot, danh dau tung may, dong dot.
(function () {
  "use strict";
  var T = window.ECTs, esc = T.esc;
  var RESULTS = ["OK", "Wrong Holder", "Wrong Status", "Not Found", "Damaged"];
  var RESULT_VI = { "OK": "Đúng như sổ", "Wrong Holder": "Sai người giữ", "Wrong Status": "Sai trạng thái", "Not Found": "Không thấy", "Damaged": "Hỏng" };
  var st = { filter: T.param("filter") || "", q: "" }, root, data = null;

  function load() {
    if (!data) root.innerHTML = '<div class="ts-wrap">' + T.skel(6) + "</div>";
    T.get("count_summary", {}).then(function (d) { data = d; render(); }, function (e) {
      root.innerHTML = '<div class="ts-wrap">' + T.errBox(e, true) + "</div>";
      var b = root.querySelector("[data-retry]"); if (b) b.addEventListener("click", load);
    });
  }

  function head(sub, right) {
    return '<div class="ts-head"><div class="ts-head-main"><h1 class="ts-title">Kiểm kê thiết bị</h1><div class="ts-sub">' + sub + "</div></div>" +
      '<div class="ts-filters">' + (right || "") + "</div></div>";
  }

  function renderClosed() {
    var y = new Date();
    root.innerHTML = '<div class="ts-wrap ts-narrow">' + head("Đối chiếu sổ với thực tế: ai đang giữ máy nào, máy còn hay mất, tình trạng ra sao.") +
      '<div class="ts-card"><div class="ts-card-t">Chưa có đợt kiểm kê nào đang mở</div>' +
      '<p class="ts-muted">Mở đợt sẽ chụp danh sách thiết bị hiện tại. Nhân viên tự xác nhận trong Tài sản của tôi; quản lý tài sản đánh dấu phần còn lại.</p>' +
      (data && data.can && data.can.manage ?
        '<label class="ts-lbl">Tên đợt<input class="ts-in" data-title value="Kiểm kê ' + (y.getMonth() + 1) + "/" + y.getFullYear() + '" maxlength="140"></label>' +
        '<div class="ts-row" style="margin-top:12px"><span class="ts-sp"></span><button type="button" class="ts-btn ts-primary" data-open-count>Mở đợt kiểm kê</button></div>' :
        '<p class="ts-note">Chỉ người quản lý tài sản mở được đợt kiểm kê.</p>') + "</div></div>";
  }

  function visible(rows) {
    var q = st.q.toLowerCase();
    return rows.filter(function (r) {
      if (st.filter === "unchecked" && r.result) return false;
      if (st.filter === "mismatch" && !(r.result && r.result !== "OK")) return false;
      if (st.filter === "self" && !r.self_confirmed) return false;
      return !q || [r.asset, r.tag, r.asset_name, r.expected_holder, r.expected_holder_name, r.actual_holder,
        r.actual_holder_name, r.note].join(" ").toLowerCase().indexOf(q) >= 0;
    });
  }

  function rowsHtml(d) {
    var rows = visible(d.rows || []);
    if (!rows.length) return '<div class="ts-empty" style="padding:28px">Không có dòng nào khớp bộ lọc.</div>';
    var labels = d.result_labels || {}, canMark = !!(d.can && d.can.manage);
    return '<div class="ts-table-wrap"><table class="ts-table"><thead><tr><th>Thiết bị</th><th>Theo sổ</th><th>Nhân viên</th><th>Kết quả</th><th>Thực tế / ghi chú</th></tr></thead><tbody>' +
      rows.map(function (r) {
        return '<tr data-a="' + esc(r.asset) + '"><td><a class="ts-strong" href="/tai-san/thiet-bi?asset=' + encodeURIComponent(r.asset) + '">' + esc(r.tag || r.asset) + "</a>" +
          (r.asset_name ? '<div class="ts-note">' + esc(r.asset_name) + "</div>" : "") + "</td>" +
          "<td>" + T.pill(r.expected_status) + '<div class="ts-note">' + esc(r.expected_holder_name || r.expected_holder || "Kho") + "</div></td>" +
          "<td>" + (r.self_confirmed ? '<span class="ts-pill">' + T.dot("Available") + "Đã tự xác nhận</span>" : '<span class="ts-note">Chưa</span>') + "</td>" +
          '<td><select class="ts-sel" data-res' + (canMark ? "" : " disabled") + ' aria-label="Kết quả kiểm kê ' + esc(r.asset) + '"><option value="">Chưa kiểm</option>' + RESULTS.map(function (k) {
            return '<option value="' + k + '"' + (r.result === k ? " selected" : "") + ">" + esc(labels[k] || RESULT_VI[k] || k) + "</option>";
          }).join("") + "</select>" + (r.counted_at ? '<div class="ts-note">' + T.fmtDT(r.counted_at) + "</div>" : "") + "</td>" +
          "<td>" + (r.actual_holder ? '<div class="ts-note">Người giữ thực tế: <b>' + esc(r.actual_holder_name || r.actual_holder) + "</b></div>" : "") + (r.note ? '<div class="ts-note">' + esc(r.note) + "</div>" : "") +
          (canMark ? '<button type="button" class="ts-link" data-note>Ghi chú</button>' : "") + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }

  function render() {
    var d = data;
    if (!d.count) { renderClosed(); return; }
    var c = d.count, pct = d.total ? Math.round(d.done * 100 / d.total) : 0;
    var self = (d.rows || []).filter(function (r) { return r.self_confirmed; }).length;
    var chips = [["", "Tất cả · " + d.total], ["unchecked", "Chưa kiểm · " + (d.total - d.done)], ["mismatch", "Lệch sổ · " + d.mismatch], ["self", "Tự xác nhận · " + self]];
    root.innerHTML = '<div class="ts-wrap">' + head(esc(c.title || c.name) + (c.started_on ? " · mở từ " + T.fmtDate(c.started_on) : ""),
      '<button type="button" class="ts-btn" data-reload>Làm mới</button>' +
      (d.can && d.can.manage ? '<button type="button" class="ts-btn ts-danger" data-close-count>Đóng đợt</button>' : "")) +
      '<div class="ts-grid ts-g4">' +
      '<div class="ts-card"><div class="ts-kpi-l">Đã kiểm</div><div class="ts-kpi-v">' + T.fmtNum(d.done) + '<span class="ts-muted" style="font-size:16px">/' + T.fmtNum(d.total) + "</span></div>" +
      '<div class="ts-prog" style="margin-top:8px"><span style="width:' + pct + '%"></span></div></div>' +
      '<div class="ts-card"><div class="ts-kpi-l">Chưa kiểm</div><div class="ts-kpi-v">' + T.fmtNum(d.total - d.done) + "</div></div>" +
      '<div class="ts-card"><div class="ts-kpi-l">Lệch sổ</div><div class="ts-kpi-v' + (d.mismatch ? " ts-bad-text" : "") + '">' + T.fmtNum(d.mismatch) + "</div></div>" +
      '<div class="ts-card"><div class="ts-kpi-l">Nhân viên tự xác nhận</div><div class="ts-kpi-v">' + T.fmtNum(self) + "</div></div></div>" +
      '<div class="ts-filters"><div class="ts-chips" data-chips>' + chips.map(function (x) {
        return '<button type="button" class="ts-chip' + (x[0] === st.filter ? " on" : "") + '" data-flt="' + x[0] + '">' + esc(x[1]) + "</button>";
      }).join("") + '</div><span class="ts-sp"></span><input class="ts-in" type="search" data-q placeholder="Mã thiết bị, nhân viên…" aria-label="Tìm" value="' + esc(st.q) + '"></div>' +
      '<div class="ts-card" style="padding:0" data-rows>' + rowsHtml(d) + "</div>" +
      '<div class="ts-note">Chọn kết quả là lưu ngay. "Sai người giữ" sẽ hỏi người đang giữ thực tế.</div></div>';
    root.querySelector("[data-q]").addEventListener("input", function (e) { st.q = e.target.value; root.querySelector("[data-rows]").innerHTML = rowsHtml(data); });
  }

  function mark(asset, result, holder, note, sel) {
    if (sel) sel.disabled = true;
    return T.post("mark_count", { asset: asset, result: result, actual_holder: holder || "", note: note || "" }).then(function () {
      T.toast("Đã lưu " + asset + "."); load();
    }, function (e) { if (sel) sel.disabled = false; T.toast(T.msg(e), true); load(); });
  }

  function rowOf(asset) { return (data.rows || []).filter(function (r) { return r.asset === asset; })[0] || {}; }

  function onChange(e) {
    var sel = e.target.closest("[data-res]");
    if (!sel) return;
    var asset = sel.closest("tr").getAttribute("data-a"), v = sel.value, r = rowOf(asset);
    if (!v) { load(); return; }
    if (v === "Wrong Holder") {
      T.pickEmployee("Người đang giữ thực tế " + asset).then(function (emp) {
        if (!emp) { load(); return; }
        mark(asset, v, emp, r.note, sel);
      });
      return;
    }
    mark(asset, v, "", r.note, sel);
  }

  function onClick(e) {
    var t;
    if (e.target.closest("[data-reload]")) { load(); return; }
    if ((t = e.target.closest("[data-flt]"))) {
      st.filter = t.getAttribute("data-flt"); T.setParam("filter", st.filter);
      T.qsa(root, "[data-chips] .ts-chip").forEach(function (x) { x.classList.toggle("on", x === t); });
      root.querySelector("[data-rows]").innerHTML = rowsHtml(data);
      return;
    }
    if ((t = e.target.closest("[data-open-count]"))) {
      T.busy(t, true);
      T.post("open_count", { title: root.querySelector("[data-title]").value }).then(function () { T.toast("Đã mở đợt kiểm kê."); data = null; load(); },
        function (er) { T.busy(t, false); T.toast(T.msg(er), true); });
      return;
    }
    if (e.target.closest("[data-close-count]")) {
      var left = data.total - data.done;
      T.confirmBox("Đóng đợt kiểm kê", (left ? "Còn " + left + " máy chưa kiểm. " : "") + "Đóng đợt thì không đánh dấu thêm được.", "Đóng đợt", true).then(function (ok) {
        if (!ok) return;
        T.post("close_count", {}).then(function (r) {
          T.toast("Đã đóng đợt" + (r && r.unchecked ? ", " + r.unchecked + " máy chưa kiểm." : "."));
          data = null; load();
        }, function (er) { T.toast(T.msg(er), true); });
      });
      return;
    }
    if ((t = e.target.closest("[data-note]"))) {
      var asset = t.closest("tr").getAttribute("data-a"), r = rowOf(asset);
      T.modal("Ghi chú kiểm kê · " + asset, '<label class="ts-lbl">Ghi chú<textarea class="ts-ta" name="note" maxlength="500">' + esc(r.note || "") + "</textarea></label>" +
        (r.result ? "" : '<div class="ts-note">Máy chưa có kết quả: lưu ghi chú sẽ ghi kết quả "Đúng như sổ".</div>'),
        '<button type="button" class="ts-btn" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary" data-ok>Lưu</button>',
        function (el, close) {
          el.querySelector("[data-ok]").addEventListener("click", function () {
            close(); mark(asset, r.result || "OK", r.actual_holder, el.querySelector('[name="note"]').value);
          });
        });
    }
  }

  function start() {
    root = document.getElementById("ts-root");
    if (!root) return;
    root.addEventListener("change", onChange);
    root.addEventListener("click", onClick);
    load();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
