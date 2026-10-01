// Copyright (c) 2026, eCentric and contributors
// ec_survey_manage.js -- trang /khao-sat/quan-ly: khao sat toi tao / cung quan ly, tao moi tu
// mau, nhan ban (dot hang thang), xoa ban nhap.
(function () {
  "use strict";
  var S = window.ECSvy, esc = S.esc;
  var root = S.byId("svy-root");
  if (!root || root.getAttribute("data-page") !== "manage") return;
  var st = { data: null, filter: "all", q: "" };
  var LABEL = { draft: ["Nháp", "mute"], scheduled: ["Sắp mở", "warn"], open: ["Đang mở", "ok"], closed: ["Đã đóng", "bad"] };
  var REWARD = { wheel: "Vòng quay", lucky_number: "Số may mắn" };

  function builder(name, tab) { return "/khao-sat/soan?s=" + encodeURIComponent(name) + (tab ? "&tab=" + tab : ""); }

  function rows() {
    return st.data.surveys.filter(function (s) {
      if (st.filter !== "all" && s.effective !== st.filter) return false;
      return !st.q || s.title.toLowerCase().indexOf(st.q) >= 0;
    });
  }

  function render() {
    var d = st.data, list = rows();
    var counts = { all: d.surveys.length };
    d.surveys.forEach(function (s) { counts[s.effective] = (counts[s.effective] || 0) + 1; });
    var h = '<div class="svy-wrap"><div class="svy-row between"><div><div class="svy-eyebrow"><a href="/khao-sat" style="color:inherit">Khảo sát</a></div><h1 style="font-size:22px">Quản lý khảo sát</h1></div>' +
      (d.can_create ? '<button class="svy-b pri" data-act="new">' + S.icon("plus") + "Tạo khảo sát</button>" : "") + "</div>";
    if (!d.can_create) h += '<div class="svy-banner">' + S.icon("lock") + "<div>Bạn chưa có quyền tạo khảo sát. Nhờ HR cấp quyền <b>EC Survey Creator</b>. Dưới đây là các khảo sát bạn được mời cùng quản lý.</div></div>";
    h += '<div class="svy-row between"><div class="svy-chips">' + [["all", "Tất cả"], ["draft", "Nháp"], ["open", "Đang mở"], ["scheduled", "Sắp mở"], ["closed", "Đã đóng"]].map(function (f) {
      return '<button class="svy-chip' + (st.filter === f[0] ? " on" : "") + '" data-filter="' + f[0] + '">' + f[1] + " · " + (counts[f[0]] || 0) + "</button>";
    }).join("") + '</div><input class="svy-in" style="max-width:260px" type="search" placeholder="Tìm theo tên" value="' + esc(st.q) + '" data-search aria-label="Tìm khảo sát"></div>';
    if (!d.surveys.length) {
      h += '<div class="svy-panel svy-empty"><b>Chưa có khảo sát nào</b>' + (d.can_create ? 'Bấm "Tạo khảo sát" để bắt đầu - có sẵn mẫu khảo sát tháng, đăng ký sự kiện, bài kiểm tra.' : "") + "</div>";
    } else if (!list.length) {
      h += '<div class="svy-panel svy-empty">Không có khảo sát khớp bộ lọc.</div>';
    } else {
      h += '<div class="svy-panel"><table class="svy-table"><thead><tr><th>Khảo sát</th><th>Trạng thái</th><th>Phiếu</th><th>Hạn</th><th>Người tạo</th><th></th></tr></thead><tbody>';
      list.forEach(function (s) {
        var lb = LABEL[s.effective] || LABEL.draft;
        h += '<tr><td class="title"><a href="' + builder(s.name) + '">' + esc(s.title) + '</a><div class="svy-small svy-muted">' + esc(s.name) + " · " + s.questions + " câu" +
          (REWARD[s.reward_mode] ? " · " + REWARD[s.reward_mode] : "") + (s.anonymous ? " · ẩn danh" : "") + "</div></td>" +
          '<td data-l="Trạng thái"><span class="svy-pill ' + lb[1] + '">' + lb[0] + "</span></td>" +
          '<td data-l="Phiếu"><a href="' + builder(s.name, "results") + '"><b>' + s.responses + "</b></a></td>" +
          '<td data-l="Hạn">' + (s.close_at ? esc(S.fmtDt(s.close_at)) : '<span class="svy-muted">—</span>') + "</td>" +
          '<td data-l="Người tạo">' + esc(s.owner_name || s.owner) + "</td>" +
          '<td data-l=""><div class="svy-row" style="justify-content:flex-end;flex-wrap:nowrap"><a class="svy-b sm" href="' + builder(s.name) + '">Soạn</a>' +
          (d.can_create ? '<button class="svy-b sm ghost" data-act="dup" data-name="' + esc(s.name) + '" title="Nhân bản cho đợt mới">' + S.icon("copy") + "</button>" : "") +
          (s.effective === "draft" ? '<button class="svy-b sm ghost danger" data-act="del" data-name="' + esc(s.name) + '" title="Xoá bản nháp">' + S.icon("trash") + "</button>" : "") +
          "</div></td></tr>";
      });
      h += "</tbody></table></div>";
    }
    root.innerHTML = h + "</div>";
  }

  function chooseTemplate() {
    var m = S.modal("<h3>Tạo khảo sát mới</h3><div class=\"svy-muted svy-small\">Chọn một mẫu để bắt đầu. Mọi câu hỏi đều sửa được sau.</div>" +
      '<div class="svy-tpls">' + st.data.templates.map(function (t) {
        return '<button class="svy-tpl" data-tpl="' + esc(t.key) + '"><b>' + esc(t.label) + "</b><span>" + esc(t.description) + "</span></button>";
      }).join("") + '</div><div class="svy-row" style="justify-content:flex-end"><button class="svy-b" data-close>Huỷ</button></div>', { wide: true });
    m.box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-tpl]");
      if (!b) return;
      S.busy(b, true);
      S.api("create", { template: b.getAttribute("data-tpl") }, true).then(function (r) { location.href = builder(r.name); },
        function (err) { S.busy(b, false); S.toast(err.svyMessage, true); });
    });
  }

  root.addEventListener("click", function (e) {
    var f = e.target.closest("[data-filter]");
    if (f) { st.filter = f.getAttribute("data-filter"); render(); return; }
    var b = e.target.closest("[data-act]");
    if (!b) return;
    var act = b.getAttribute("data-act"), name = b.getAttribute("data-name");
    if (act === "new") chooseTemplate();
    if (act === "dup") {
      S.busy(b, true);
      S.api("create", { source: name }, true).then(function (r) { location.href = builder(r.name); }, function (err) { S.busy(b, false); S.toast(err.svyMessage, true); });
    }
    if (act === "del") {
      S.confirm("Xoá bản nháp?", "Không khôi phục được.", "Xoá", true).then(function (ok) {
        if (!ok) return;
        S.api("delete", { name: name }, true).then(function () { S.toast("Đã xoá."); boot(); }, function (err) { S.toast(err.svyMessage, true); });
      });
    }
  });
  root.addEventListener("input", function (e) {
    if (!e.target.hasAttribute("data-search")) return;
    st.q = e.target.value.trim().toLowerCase();
    var pos = e.target.selectionStart;
    render();
    var inp = root.querySelector("[data-search]");
    inp.focus(); inp.setSelectionRange(pos, pos);
  });

  function boot() {
    S.api("manage_list").then(function (d) { st.data = d; render(); }, function (e) {
      root.innerHTML = '<div class="svy-wrap"><div class="svy-panel svy-empty"><b>Không tải được</b>' + esc(e.svyMessage) + "</div></div>";
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
