// Copyright (c) 2026, eCentric and contributors
//
// Tab "Tat ca" dung chung cho CA 28 form phe duyet (16/09, Hoan).
//
// VI SAO LA MOT ASSET DUNG CHUNG, KHONG PHAI 28 BAN SAO. Bo loc + bang + phan trang +
// export la ngan dong. Chep vao 28 file main_section.html thi lan sua tiep theo phai sua
// dung 28 cho, va dot 15/09 vua chung minh dieu gi xay ra khi mot trong so do bi bo sot:
// `readRoute` thieu o 27 form, listener thieu o 1 form, thanh tab chet ca 28 ma khong ai
// thay. Mot ban duy nhat thi mot lan sua la xong.
//
// GIAO KEO VOI TRANG: trang chi dua vao `call` (ham goi API cua chinh no) va `ns` (duong
// dan module). Bundle KHONG doan ten ham, KHONG doc bien toan cuc cua trang.
//
// PHAM VI DU LIEU la viec cua SERVER. `list_all` ghim `approval_type` va AND
// `scope_predicate` vao moi truy van. Bo loc o day chi de nguoi dung thu hep thu ho da
// duoc phep xem - khong bao gio de mo rong.
(function () {
  "use strict";
  if (window.EcAllTab) return;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function tien(v) {
    if (v == null || v === "") return "";
    var n = Number(v);
    if (isNaN(n)) return esc(String(v));
    try { return n.toLocaleString("vi-VN"); } catch (e) { return String(Math.round(n)); }
  }
  function ngay(v) {
    if (!v) return "";
    var d = new Date(String(v).replace(" ", "T"));
    if (isNaN(d.getTime())) return esc(String(v).slice(0, 16));
    function p(n) { return (n < 10 ? "0" : "") + n; }
    return p(d.getDate()) + "/" + p(d.getMonth() + 1) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }
  function maNgan(name) {
    // Ma phieu day du dai va lap lai tien to o moi dong; giu 5 ky tu cuoi de mat quet duoc
    // cot, nhung title mang ban day du cho ai can doc chinh xac.
    var s = String(name || "");
    return s.length > 6 ? s.slice(-5) : s;
  }
  var NHOM = {
    Approved: "ok", Rejected: "no", Cancelled: "no",
    Pending: "cho", "Information Required": "hoi"
  };

  function dongHTML(v) {
    var cho = (v.approvers || []).filter(function (a) { return a.status === "Pending"; })
      .map(function (a) { return a.name || a.user || ""; }).filter(Boolean);
    var buoc = (v.current_level ? v.current_level : "") +
      (v.total_levels ? "/" + v.total_levels : "");
    var nhom = NHOM[v.status] || "cho";
    var quaHan = v.sla_breached && v.status === "Pending";
    return '<tr class="ec-at-row" data-open="' + esc(v.name) + '" tabindex="0">' +
      '<td><span class="ec-at-ma" title="' + esc(v.name) + '">' + esc(maNgan(v.name)) + '</span>' +
        '<span class="ec-at-sub">' + esc(ngay(v.submitted_at)) + '</span></td>' +
      '<td><span class="ec-at-tt" title="' + esc(v.title || "") + '">' + esc(v.title || "—") + '</span>' +
        '<span class="ec-at-sub" title="' + esc(v.department || "") + '">' +
        esc(((v.requester_info || {}).name) || v.requester || "") +
        (v.department ? " · " + esc(v.department) : "") + '</span></td>' +
      '<td class="ec-at-num">' + esc(tien(v.amount)) +
        '<span class="ec-at-sub">' + esc(v.currency || "") + '</span></td>' +
      '<td><span class="ec-at-tag ec-at-' + nhom + '">' + esc(v.status_label || v.status || "") + '</span>' +
        '<span class="ec-at-sub">' + esc(buoc) + (buoc && v.current_level_name ? " · " : "") +
        esc(v.current_level_name || "") + '</span></td>' +
      '<td><span class="ec-at-tt">' + esc(cho.join(", ") || "—") + '</span>' +
        (quaHan ? '<span class="ec-at-sub ec-at-late">quá hạn SLA</span>' :
          (v.sla_due_at ? '<span class="ec-at-sub">hạn ' + esc(ngay(v.sla_due_at)) + '</span>' : '')) +
      '</td></tr>';
  }

  function chonHTML(name, nhan, ds, val) {
    return '<select class="ec-at-f" data-f="' + name + '"><option value="">' + esc(nhan) + '</option>' +
      (ds || []).map(function (o) {
        var v = o && o.value != null ? o.value : o, l = o && o.label != null ? o.label : v;
        return '<option value="' + esc(v) + '"' + (String(val || "") === String(v) ? " selected" : "") +
          '>' + esc(l) + '</option>';
      }).join("") + '</select>';
  }

  function khung(st) {
    var o = st.opts || {};
    return '<div class="ec-at">' +
      '<div class="ec-at-bar">' +
        '<input type="search" class="ec-at-q" placeholder="Tìm mã, tiêu đề, người…" value="' + esc(st.f.search || "") + '">' +
        chonHTML("status", "Mọi trạng thái", o.statuses, st.f.status) +
        chonHTML("department", "Mọi phòng ban", o.departments, st.f.department) +
        chonHTML("requester", "Mọi người đề nghị", o.requesters, st.f.requester) +
        '<input type="date" class="ec-at-f" data-f="date_from" value="' + esc(st.f.date_from || "") + '" title="Từ ngày">' +
        '<input type="date" class="ec-at-f" data-f="date_to" value="' + esc(st.f.date_to || "") + '" title="Đến ngày">' +
        '<button type="button" class="ec-at-reset">Xoá lọc</button>' +
        '<span class="ec-at-spacer"></span>' +
        '<button type="button" class="ec-at-x" data-fmt="xlsx">Excel</button>' +
        '<button type="button" class="ec-at-x" data-fmt="csv">CSV</button>' +
      '</div>' +
      '<div class="ec-at-wrap"><table class="ec-at-tb"><thead><tr>' +
        '<th>Mã · ngày gửi</th><th>Tiêu đề · người đề nghị</th><th class="ec-at-num">Số tiền</th>' +
        '<th>Trạng thái · bước</th><th>Đang chờ ai</th>' +
      '</tr></thead><tbody class="ec-at-body"></tbody></table></div>' +
      '<div class="ec-at-foot"><span class="ec-at-dem"></span><span class="ec-at-pg"></span></div>' +
    '</div>';
  }

  function veThan(st) {
    var tb = st.el.querySelector(".ec-at-body");
    var dem = st.el.querySelector(".ec-at-dem");
    var pg = st.el.querySelector(".ec-at-pg");
    if (st.dangTai) {
      tb.innerHTML = '<tr><td colspan="5" class="ec-at-trong">Đang tải…</td></tr>';
      dem.textContent = ""; pg.innerHTML = ""; return;
    }
    if (st.loi) {
      tb.innerHTML = '<tr><td colspan="5" class="ec-at-trong">' + esc(st.loi) + '</td></tr>';
      dem.textContent = ""; pg.innerHTML = ""; return;
    }
    var rows = st.rows || [];
    tb.innerHTML = rows.length ? rows.map(dongHTML).join("")
      : '<tr><td colspan="5" class="ec-at-trong">Không có phiếu nào khớp bộ lọc.</td></tr>';
    var tu = st.total ? st.start + 1 : 0, den = Math.min(st.start + st.len, st.total);
    var t = tu + "–" + den + " trong " + st.total + " phiếu";
    if (st.total_amount != null) t += " · tổng " + tien(st.total_amount);
    else if (st.sum_capped) t += " · tổng: thu hẹp bộ lọc để tính";
    dem.textContent = t;
    var trang = Math.floor(st.start / st.len) + 1, het = Math.max(1, Math.ceil(st.total / st.len));
    pg.innerHTML = '<button type="button" class="ec-at-pv"' + (st.start <= 0 ? " disabled" : "") + '>Trước</button>' +
      '<span>' + trang + "/" + het + '</span>' +
      '<button type="button" class="ec-at-nx"' + (den >= st.total ? " disabled" : "") + '>Sau</button>';
  }

  function nap(st) {
    st.dangTai = true; st.loi = null; veThan(st);
    var f = {};
    ["status", "department", "requester", "date_from", "date_to"].forEach(function (k) {
      if (st.f[k]) f[k] = st.f[k];
    });
    // Ngay: server doi CA HAI dau moi ap dung khoang. Gui mot dau thi im lang bi bo qua,
    // nguoi dung tuong da loc. Bu dau con thieu bang bien rong hop ly.
    if (f.date_from && !f.date_to) f.date_to = new Date().toISOString().slice(0, 10);
    if (f.date_to && !f.date_from) f.date_from = "2000-01-01";
    var luot = ++st.luot;
    st.goi("list_all", {
      filters: JSON.stringify(f), start: st.start, page_length: st.len,
      search: st.f.search || null
    }).then(function (r) {
      if (luot !== st.luot) return;          // ket qua cu ve sau - bo di, khong ghi de
      r = r || {};
      st.rows = r.rows || []; st.total = r.total || 0;
      st.total_amount = r.total_amount; st.sum_capped = !!r.sum_capped;
      st.dangTai = false; veThan(st);
    }).catch(function (e) {
      if (luot !== st.luot) return;
      st.dangTai = false;
      st.loi = (e && e.message) ? e.message : "Không tải được danh sách.";
      veThan(st);
    });
  }

  function taiTep(st, fmt, nut) {
    var f = {};
    ["status", "department", "requester", "date_from", "date_to"].forEach(function (k) {
      if (st.f[k]) f[k] = st.f[k];
    });
    if (f.date_from && !f.date_to) f.date_to = new Date().toISOString().slice(0, 10);
    if (f.date_to && !f.date_from) f.date_from = "2000-01-01";
    var cu = nut.textContent;
    nut.disabled = true; nut.textContent = "Đang xuất…";
    // POST, khong phai mo mot URL GET: export_all GHI mot dong vet, ma Frappe hoan tac moi
    // thao tac ghi trong request GET (do duoc 15/09) - tep van tai ve nhung vet bien mat.
    var fr = window.frappe || {};
    fetch("/api/method/" + st.ns + "export_all", {
      method: "POST", credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Frappe-CSRF-Token": fr.csrf_token || ""
      },
      body: JSON.stringify({ filters: JSON.stringify(f), search: st.f.search || null, fmt: fmt })
    }).then(function (res) {
      if (!res.ok) {
        return res.text().then(function (t) {
          var m = "";
          try { m = (JSON.parse(t)._server_messages ? JSON.parse(JSON.parse(t)._server_messages)[0] : ""); } catch (e) { }
          try { m = m ? (JSON.parse(m).message || m) : m; } catch (e) { }
          throw new Error(m || ("Xuất tệp thất bại (HTTP " + res.status + ")"));
        });
      }
      return res.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url; a.download = "";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
    }).catch(function (e) {
      // Bao NGUYEN VAN cau server noi. Tran dong la mot loi CO THE SUA duoc - nguoi dung
      // chi sua duoc khi doc dung "vuot 5000, thu hep bo loc", khong phai "co loi xay ra".
      var box = st.el.querySelector(".ec-at-dem");
      if (box) box.textContent = (e && e.message) || "Xuất tệp thất bại.";
    }).then(function () {
      nut.disabled = false; nut.textContent = cu;
    });
  }

  var HEN = null;
  function goLoc(st) {
    clearTimeout(HEN);
    HEN = setTimeout(function () { st.start = 0; nap(st); }, 300);
  }

  function noiSuKien(st) {
    var el = st.el;
    el.addEventListener("input", function (e) {
      var q = e.target.closest(".ec-at-q");
      if (!q) return;
      st.f.search = q.value.trim();
      goLoc(st);
    });
    el.addEventListener("change", function (e) {
      var f = e.target.closest(".ec-at-f");
      if (!f) return;
      st.f[f.getAttribute("data-f")] = f.value || "";
      st.start = 0; nap(st);
    });
    el.addEventListener("click", function (e) {
      var t = e.target;
      if (t.closest(".ec-at-reset")) {
        st.f = { search: "" }; st.start = 0;
        el.innerHTML = khung(st); noiSuKien(st); nap(st); return;
      }
      var x = t.closest(".ec-at-x");
      if (x) { taiTep(st, x.getAttribute("data-fmt"), x); return; }
      if (t.closest(".ec-at-pv")) { st.start = Math.max(0, st.start - st.len); nap(st); return; }
      if (t.closest(".ec-at-nx")) { st.start = st.start + st.len; nap(st); return; }
      var row = t.closest(".ec-at-row");
      if (row && st.moChiTiet) st.moChiTiet(row.getAttribute("data-open"));
    });
    el.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      var row = e.target.closest && e.target.closest(".ec-at-row");
      if (row && st.moChiTiet) { e.preventDefault(); st.moChiTiet(row.getAttribute("data-open")); }
    });
  }

  function render(box, o) {
    if (!box) return;
    o = o || {};
    var st = {
      el: box, goi: o.call, ns: o.ns || "", moChiTiet: o.open,
      f: { search: "" }, start: 0, len: o.pageLength || 50,
      rows: [], total: 0, opts: { statuses: [], departments: [], requesters: [] },
      luot: 0
    };
    // Lay bo loc TRUOC roi moi dung khung MOT LAN. Ban dau dung khung ngay rooi dung lai
    // khi bo loc ve - nguoi go nhanh se bi cuop con tro giua chung va mat chu vua go.
    // Dung lai DOM duoi tay nguoi dung la mot loi, khong phai mot danh doi ve toc do.
    box.innerHTML = '<div class="ec-at"><div class="ec-at-foot">' +
      '<span class="ec-at-dem">Đang tải…</span></div></div>';
    function batDau() {
      box.innerHTML = khung(st);
      noiSuKien(st);
      nap(st);
    }
    st.goi("get_all_filters", {}).then(function (r) {
      st.opts = r || st.opts;
      batDau();
    }).catch(function () {
      // Thieu bo loc thi bang van phai dung duoc: danh sach moi la thu nguoi ta vao day de xem.
      batDau();
    });
    return st;
  }

  window.EcAllTab = { render: render, _dongHTML: dongHTML, _tien: tien, _maNgan: maNgan };
})();
