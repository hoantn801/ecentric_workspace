// Copyright (c) 2026, eCentric and contributors
// ec_survey_ca_nhan.js -- trang /khao-sat/ca-nhan: ket qua khao sat CA NHAN (moc thu viec / thuc
// tap, nghi viec) ma nguoi xem duoc phep thay. Quyen tinh o SERVER (surveys/application/ca_nhan):
// HR / C&B xem du; quan ly truc tiep chi thay phan "LM xem duoc" cua cap duoi truc tiep. Trang
// nay chi ve lai dung cai server tra - khong tu an / hien cau nao.
(function () {
  "use strict";
  var S = window.ECSvy;
  if (!S) return;
  var esc = S.esc;
  var root = S.byId("svy-root");
  if (!root || root.getAttribute("data-page") !== "ca_nhan") return;
  var st = { rows: null, filter: "all", open: S.param("a") };

  function pill(t) {
    var cls = { "Đã nộp": "ok", "Chưa nộp": "run", "Quá hạn": "bad", "Đã huỷ": "mute" }[t] || "mute";
    return '<span class="svy-pill ' + cls + '">' + esc(t) + "</span>";
  }
  function quyenLabel(q) { return q === "lm" ? "Quản lý trực tiếp" : "HR · C&B"; }

  function listHTML() {
    var rows = (st.rows || []).filter(function (r) { return st.filter === "all" || r.trang_thai === st.filter; });
    var tabs = ["all", "Đã nộp", "Chưa nộp", "Quá hạn"].map(function (k) {
      var n = (st.rows || []).filter(function (r) { return k === "all" || r.trang_thai === k; }).length;
      return '<button type="button" class="svy-tab' + (st.filter === k ? " on" : "") + '" data-f="' + esc(k) + '">' +
        esc(k === "all" ? "Tất cả" : k) + ' <span class="n">' + n + "</span></button>";
    }).join("");
    var body = rows.length ? '<table class="svy-table"><thead><tr><th>Khảo sát</th><th>Người trả lời</th><th>Giao</th><th>Hạn</th><th>Trạng thái</th><th>Bạn xem với tư cách</th></tr></thead><tbody>' +
      rows.map(function (r) {
        return '<tr><td class="title" data-l="Khảo sát"><a href="?a=' + encodeURIComponent(r.name) + '" data-open="' + esc(r.name) + '">' + esc(r.title) + "</a></td>" +
          '<td data-l="Người trả lời">' + esc(r.user_name) + "</td><td data-l=\"Giao\">" + esc(S.fmtDate(r.assigned_on)) + "</td>" +
          '<td data-l="Hạn">' + esc(S.fmtDate(r.due_date)) + "</td><td data-l=\"Trạng thái\">" + pill(r.trang_thai) + "</td>" +
          '<td data-l="Quyền">' + esc(quyenLabel(r.quyen)) + "</td></tr>";
      }).join("") + "</tbody></table>"
      : '<div class="svy-empty"><b>Chưa có khảo sát nào bạn được xem</b>Kết quả khảo sát mốc của nhân viên trực tiếp quản lý (hoặc mọi người, nếu bạn thuộc HR · C&B) sẽ hiện ở đây.</div>';
    return '<div class="svy-wrap"><div><h1 style="font-size:22px;margin:0 0 4px">Kết quả khảo sát mốc</h1>' +
      '<div class="svy-muted svy-small">Khảo sát giao cho từng người (thử việc, thực tập, nghỉ việc). Quản lý trực tiếp không thấy các câu thuộc nhóm “chỉ HR · C&B”.</div></div>' +
      '<div class="svy-tabs" role="tablist">' + tabs + '</div><div class="svy-panel">' + body + "</div></div>";
  }

  function detailHTML(d) {
    var ans = d.submitted ? (d.answers.length ? d.answers.map(function (a, i) {
      return '<div class="svy-pad" style="border-bottom:1px solid var(--line2)"><div class="svy-small svy-muted">Câu ' + (i + 1) + "</div><b>" +
        esc(a.title) + '</b><div style="margin-top:4px;white-space:pre-wrap">' + (a.value ? esc(a.value) : '<span class="svy-muted">(bỏ trống)</span>') + "</div></div>";
    }).join("") : '<div class="svy-empty">Không có câu nào bạn được xem.</div>')
      : '<div class="svy-empty"><b>Chưa nộp</b>Hạn ' + esc(S.fmtDate(d.due_date)) + ".</div>";
    var hidden = d.so_cau_an ? '<div class="svy-pad svy-muted svy-small">' + d.so_cau_an + " câu thuộc nhóm “chỉ HR · C&B” đã được ẩn với bạn.</div>" : "";
    var tam = d.mau_tam ? ' <span class="svy-pill warn">Mẫu tạm</span>' : "";
    return '<div class="svy-wrap svy-narrow"><div><a class="svy-b sm" href="?" data-back="1">‹ Danh sách</a></div>' +
      '<div><h1 style="font-size:22px;margin:0 0 4px">' + esc(d.title) + tam + "</h1>" +
      '<div class="svy-muted svy-small">' + esc(d.user_name) + (d.submitted ? " · nộp " + esc(S.fmtDt(d.submitted_at)) : "") + "</div></div>" +
      '<div class="svy-panel">' + ans + hidden + "</div></div>";
  }

  function paint(html) { root.innerHTML = html; }
  function fail(e) { paint('<div class="svy-wrap"><div class="svy-panel svy-empty"><b>Không tải được</b>' + esc(S.friendly(e)) + "</div></div>"); }

  function showList() {
    var p = st.rows ? Promise.resolve(st.rows) : S.api("ca_nhan_danh_sach").then(function (d) { st.rows = (d && d.rows) || []; return st.rows; });
    p.then(function () { paint(listHTML()); }).catch(fail);
  }
  function showOne(name) {
    S.api("ca_nhan_xem", { name: name }).then(function (d) { paint(detailHTML(d)); }).catch(fail);
  }
  function route() { st.open = S.param("a"); if (st.open) showOne(st.open); else showList(); }

  root.addEventListener("click", function (e) {
    var f = e.target.closest("[data-f]");
    if (f) { st.filter = f.getAttribute("data-f"); paint(listHTML()); return; }
    var o = e.target.closest("[data-open]");
    if (o) { e.preventDefault(); history.pushState({}, "", "?a=" + encodeURIComponent(o.getAttribute("data-open"))); route(); return; }
    var b = e.target.closest("[data-back]");
    if (b) { e.preventDefault(); history.pushState({}, "", window.location.pathname); route(); }
  });
  window.addEventListener("popstate", route);
  window.ECSvyCaNhan = { route: route, listHTML: listHTML, detailHTML: detailHTML, st: st };
  route();
})();
