// Copyright (c) 2026, eCentric and contributors
// ec_ts_mine.js -- trang /tai-san/cua-toi (uu tien man hinh dien thoai): may minh dang giu,
// xac nhan da nhan, bao hong, tu xac nhan kiem ke.
(function () {
  "use strict";
  var T = window.ECTs, esc = T.esc;
  var LEVEL = { Partial: "Hỏng một phần", Full: "Hỏng toàn bộ", Lost: "Bị mất" };
  var root, data = null, confirmed = {};

  function load() {
    if (!data) root.innerHTML = '<div class="ts-wrap ts-mine">' + T.skel(4) + "</div>";
    T.get("my_assets", {}).then(function (d) {
      data = d; confirmed = {};
      (d.assets || []).forEach(function (a) { if (a.count_confirmed) confirmed[a.name] = a.count_confirmed === "ok" ? 1 : 2; });
      render();
    }, function (e) {
      root.innerHTML = '<div class="ts-wrap ts-mine">' + T.errBox(e, true) + "</div>";
      var b = root.querySelector("[data-retry]"); if (b) b.addEventListener("click", load);
    });
  }

  function card(a, count) {
    var specs = a.specs || [], comps = a.components || [];
    return '<article class="ts-mcard" data-a="' + esc(a.name) + '">' +
      '<div class="ts-mcard-h"><span class="ts-dev-ico">' + T.deviceIcon(a.category) + '</span><div style="flex:1;min-width:0">' +
      '<div class="ts-strong" style="font-size:15px">' + esc(a.asset_name || a.name) + "</div>" +
      '<div class="ts-note">' + esc(a.tag || a.name) + (a.serial ? " · SN " + esc(a.serial) : "") + "</div>" +
      '<div class="ts-row" style="margin-top:6px">' + T.pill(a.status) + (a.condition && a.condition !== "Good" ? T.condPill(a.condition) : "") + "</div></div></div>" +
      (a.pending_ack ? '<div class="ts-ack"><div><b>Bạn vừa được cấp thiết bị này.</b> Kiểm tra đủ máy, sạc, phụ kiện rồi xác nhận.</div>' +
        '<button type="button" class="ts-btn ts-primary ts-big" data-ack>' + T.icon("check") + "Tôi đã nhận đủ</button></div>" : "") +
      (specs.length ? '<div class="ts-specs">' + specs.map(function (s) {
        return "<div><span>" + esc(s.part_type) + "</span>" + esc(s.spec) + (s.qty > 1 ? " × " + s.qty : "") + "</div>";
      }).join("") + "</div>" : "") +
      (comps.length ? '<div class="ts-note">Lắp thêm: ' + comps.map(function (c) { return esc((c.tag || c.name) + " " + (c.asset_name || "")); }).join(", ") + "</div>" : "") +
      (a.warranty_until ? '<div class="ts-note">Bảo hành đến ' + T.fmtDate(a.warranty_until) + "</div>" : "") +
      (count ? (confirmed[a.name] ? '<div class="ts-infobox">Đã gửi xác nhận kiểm kê: ' + (confirmed[a.name] === 1 ? "đúng, đang giữ." : "báo không đúng.") + "</div>" :
        '<div class="ts-infobox"><div class="ts-strong" style="margin-bottom:8px">Xác nhận kiểm kê</div><div class="ts-actions">' +
        '<button type="button" class="ts-btn ts-primary ts-big" data-cc="1">Đúng, tôi đang giữ</button><button type="button" class="ts-btn ts-big" data-cc="0">Không đúng</button></div></div>') : "") +
      '<div class="ts-actions"><button type="button" class="ts-btn ts-big" data-dmg>' + T.icon("alert") + "Báo hỏng / mất</button></div></article>";
  }

  function render() {
    var d = data;
    var head = '<div class="ts-head"><div class="ts-head-main"><h1 class="ts-title">Tài sản của tôi</h1>' +
      (d.employee ? '<div class="ts-sub">' + esc(d.employee.employee_name || d.employee.name || "") + "</div>" : "") + "</div></div>";
    if (d.no_employee) {
      root.innerHTML = '<div class="ts-wrap ts-mine">' + head + '<div class="ts-card"><div class="ts-card-t">Tài khoản chưa gắn hồ sơ nhân viên</div>' +
        '<p class="ts-muted">Thiết bị được cấp theo hồ sơ nhân viên. Nhờ HR gắn tài khoản đăng nhập này vào hồ sơ của bạn rồi mở lại trang.</p></div></div>';
      return;
    }
    var list = d.assets || [], pend = list.filter(function (a) { return a.pending_ack; }).length;
    root.innerHTML = '<div class="ts-wrap ts-mine">' + head +
      (pend ? '<div class="ts-ack"><b>Cần xác nhận ' + pend + " thiết bị mới được cấp.</b></div>" : "") +
      (d.count ? '<div class="ts-infobox"><b>' + esc(d.count.title || "Đợt kiểm kê") + "</b> đang mở" + (d.count.started_on ? " từ " + T.fmtDate(d.count.started_on) : "") +
        ". Xác nhận từng thiết bị bạn đang giữ bên dưới.</div>" : "") +
      (list.length ? list.map(function (a) { return card(a, d.count); }).join("") :
        '<div class="ts-card"><div class="ts-empty">Bạn chưa giữ thiết bị nào của công ty.</div></div>') +
      (d.request_route ? '<a class="ts-btn ts-wash ts-big" href="' + esc(d.request_route) + '" style="justify-content:center">' + T.icon("plus") + "Xin cấp / đổi thiết bị</a>" : "") +
      '<div class="ts-note">Máy hỏng hay mất, báo ngay để được gửi sửa hoặc cấp máy tạm. Khi nghỉ việc, trả máy theo phiếu Clearance.</div></div>';
  }

  function assetOf(el) {
    var name = el.closest("[data-a]").getAttribute("data-a");
    return (data.assets || []).filter(function (a) { return a.name === name; })[0];
  }

  function damageSheet(a) {
    var parts = (a.specs || []).map(function (s) { return s.part_type; }).filter(Boolean);
    if (!parts.length) parts = ["Màn hình", "Bàn phím", "Pin", "Sạc", "Bản lề", "Cổng kết nối"];
    T.modal("Báo hỏng · " + (a.tag || a.name),
      '<div><div class="ts-lbl" style="margin-bottom:6px">Mức độ</div><div class="ts-chips" data-lv>' + (data.damage_levels || ["Partial", "Full", "Lost"]).map(function (l, i) {
        return '<button type="button" class="ts-chip ts-big' + (i === 0 ? " on" : "") + '" data-v="' + esc(l) + '">' + esc(LEVEL[l] || l) + "</button>";
      }).join("") + "</div></div>" +
      '<div data-partwrap><div class="ts-lbl" style="margin-bottom:6px">Bộ phận hỏng</div><div class="ts-chips" data-parts>' + parts.map(function (p) {
        return '<button type="button" class="ts-chip ts-big" data-p="' + esc(p) + '" aria-pressed="false">' + esc(p) + "</button>";
      }).join("") + "</div></div>" +
      '<label class="ts-lbl">Mô tả<textarea class="ts-ta" name="description" maxlength="1000" placeholder="Hỏng thế nào, từ khi nào…"></textarea></label>' +
      '<div class="ts-note">Quản lý tài sản nhận thông báo và liên hệ bạn để gửi sửa hoặc cấp máy tạm.</div>',
      '<button type="button" class="ts-btn ts-big" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary ts-big" data-ok>Gửi báo hỏng</button>',
      function (el, close) {
        el.querySelector("[data-lv]").addEventListener("click", function (e) {
          var b = e.target.closest(".ts-chip"); if (!b) return;
          T.qsa(el.querySelector("[data-lv]"), ".ts-chip").forEach(function (x) { x.classList.toggle("on", x === b); });
          el.querySelector("[data-partwrap]").hidden = b.getAttribute("data-v") === "Lost";
        });
        el.querySelector("[data-parts]").addEventListener("click", function (e) {
          var b = e.target.closest(".ts-chip"); if (!b) return;
          b.classList.toggle("on"); b.setAttribute("aria-pressed", b.classList.contains("on"));
        });
        el.querySelector("[data-ok]").addEventListener("click", function (ev) {
          var btn = ev.currentTarget, lv = el.querySelector("[data-lv] .on").getAttribute("data-v");
          T.busy(btn, true);
          T.post("report_damage", { asset: a.name, level: lv,
            parts: lv === "Lost" ? [] : T.qsa(el, "[data-parts] .on").map(function (b) { return b.getAttribute("data-p"); }),
            description: el.querySelector('[name="description"]').value })
            .then(function () { close(); T.toast("Đã gửi báo hỏng."); load(); }, function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
        });
      });
  }

  function confirmCount(a, ok, btn) {
    function send(note) {
      T.busy(btn, true);
      T.post("confirm_count", { asset: a.name, ok: ok ? 1 : 0, note: note || "" }).then(function () {
        confirmed[a.name] = ok ? 1 : 2; T.toast("Đã gửi xác nhận."); render();
      }, function (e) { T.busy(btn, false); T.toast(T.msg(e), true); });
    }
    if (ok) { send(""); return; }
    T.modal("Không đúng · " + (a.tag || a.name), '<label class="ts-lbl">Sai ở đâu?<textarea class="ts-ta" name="note" maxlength="500" placeholder="Ví dụ: máy đã trả, đang ở người khác…"></textarea></label>',
      '<button type="button" class="ts-btn ts-big" data-close>Huỷ</button><button type="button" class="ts-btn ts-primary ts-big" data-ok>Gửi</button>',
      function (el, close) { el.querySelector("[data-ok]").addEventListener("click", function () { var n = el.querySelector('[name="note"]').value; close(); send(n); }); });
  }

  function onClick(e) {
    var t;
    if ((t = e.target.closest("[data-ack]"))) {
      var a = assetOf(t); T.busy(t, true);
      T.post("acknowledge", { asset: a.name }).then(function () { T.toast("Đã xác nhận nhận đủ."); load(); }, function (er) { T.busy(t, false); T.toast(T.msg(er), true); });
      return;
    }
    if ((t = e.target.closest("[data-dmg]"))) { damageSheet(assetOf(t)); return; }
    if ((t = e.target.closest("[data-cc]"))) confirmCount(assetOf(t), t.getAttribute("data-cc") === "1", t);
  }

  function start() {
    root = document.getElementById("ts-root");
    if (!root) return;
    root.addEventListener("click", onClick);
    load();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
