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
//
// LOC THEM (16/10/2026, Finance gop y tren Contract Review): sap xep (moi/cu, so tien),
// khoang so tien, cot + o loc rieng tung form. Tat ca do SERVER khai qua get_all_filters
// (`amount`, `columns`, `extra_filters`) tu ApprovalDefinition - bundle khong biet form nao
// co gi. Bo loc phu nam trong hang "Bo loc them" thu gon de 390px van gon.
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
  // Ngay KHONG gio (truong Date nghiep vu): doc thang chuoi, khong qua Date() - "2026-10-16"
  // qua Date() la nua dem UTC, sang mui gio khac thanh ngay hom truoc.
  function ngayNgan(v) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v || ""));
    return m ? m[3] + "/" + m[2] + "/" + m[1] : String(v || "");
  }
  // O so tien: dung EcMoney (asset dung chung, dau cham) neu trang co nap; khong thi chi
  // giu chu so - "1.500.000" van ra 1500000, khong bao gio thanh 1.5.
  function docTien(el) {
    var M = window.EcMoney;
    if (M && el.hasAttribute("data-money")) return M.val(el);
    var d = String(el.value || "").replace(/\D/g, "");
    return d === "" ? null : Number(d);
  }
  function hienTien(v) {
    if (v == null || v === "") return "";
    var M = window.EcMoney;
    return M ? M.fmt(v) : String(Math.round(Number(v))).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
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

  function oThem(c, v) {
    var x = (v.extra || {})[c.fieldname];
    if (c.kind === "money") return '<td class="ec-at-num">' + esc(tien(x)) + '</td>';
    var t = (x == null || x === "") ? "" : (c.kind === "date" ? ngayNgan(x) : String(x));
    return '<td><span class="ec-at-tt" title="' + esc(t) + '">' + esc(t || "—") + '</span></td>';
  }

  function dongHTML(v, cot) {
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
      (cot || []).map(function (c) { return oThem(c, v); }).join("") +
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

  function moiBoLoc() {
    return { search: "", sort: "newest", amount_min: null, amount_max: null, extra: {} };
  }

  // So o loc DANG BAT (khong tinh o tim kiem va thu tu). `phu` = chi dem o trong hang
  // "Bo loc them" - de nguoi dung biet hang dang dong van con loc.
  function demLoc(st, phu) {
    var f = st.f, n = 0;
    if (!phu) {
      ["status", "department", "requester"].forEach(function (k) { if (f[k]) n++; });
      if (f.date_from || f.date_to) n++;
    }
    if (f.amount_min != null || f.amount_max != null) n++;
    Object.keys(f.extra || {}).forEach(function (k) { if (f.extra[k]) n++; });
    return n;
  }

  function coLocThem(o) {
    return !!(o.amount || (o.extra_filters || []).length);
  }

  function sapXepHTML(st) {
    var o = st.opts || {}, a = o.amount;
    var ds = [["newest", "Mới → cũ"], ["oldest", "Cũ → mới"]];
    if (a) ds.push(["amount_desc", a.label + " cao → thấp"], ["amount_asc", a.label + " thấp → cao"]);
    return '<select class="ec-at-f ec-at-sx" data-f="sort" title="Sắp xếp" aria-label="Sắp xếp">' +
      ds.map(function (x) {
        return '<option value="' + x[0] + '"' + (st.f.sort === x[0] ? " selected" : "") + '>' +
          esc(x[1]) + '</option>';
      }).join("") + '</select>';
  }

  function hangThemHTML(st) {
    var o = st.opts || {}, a = o.amount;
    var h = "";
    if (a) {
      h += '<span class="ec-at-khoang">' +
        '<input type="text" inputmode="numeric" data-money class="ec-at-f ec-at-tien" data-f="amount_min"' +
        ' placeholder="' + esc(a.label) + ' từ" aria-label="' + esc(a.label) + ' từ" value="' + esc(hienTien(st.f.amount_min)) + '">' +
        '<span class="ec-at-gach">–</span>' +
        '<input type="text" inputmode="numeric" data-money class="ec-at-f ec-at-tien" data-f="amount_max"' +
        ' placeholder="đến" aria-label="' + esc(a.label) + ' đến" value="' + esc(hienTien(st.f.amount_max)) + '">' +
        '</span>';
    }
    (o.extra_filters || []).forEach(function (x) {
      h += '<select class="ec-at-f" data-x="' + esc(x.fieldname) + '" aria-label="' + esc(x.label) + '">' +
        '<option value="">' + esc(x.label) + ': tất cả</option>' +
        (x.options || []).map(function (v) {
          return '<option value="' + esc(v) + '"' + (String((st.f.extra || {})[x.fieldname] || "") === String(v) ? " selected" : "") +
            '>' + esc(v) + '</option>';
        }).join("") + '</select>';
    });
    return '<div class="ec-at-more" id="' + st.idThem + '"' + (st.moRong ? "" : " hidden") + '>' + h + '</div>';
  }

  function nutThemHTML(st) {
    var n = demLoc(st, true);
    return '<button type="button" class="ec-at-mo" aria-controls="' + st.idThem + '" aria-expanded="' +
      (st.moRong ? "true" : "false") + '">Bộ lọc thêm<span class="ec-at-so"' + (n ? "" : " hidden") + '>' +
      n + '</span></button>';
  }

  function soCot(st) { return 5 + ((st.opts || {}).columns || []).length; }

  function khung(st) {
    var o = st.opts || {}, cot = o.columns || [], them = coLocThem(o);
    var nTong = demLoc(st, false);
    return '<div class="ec-at">' +
      '<div class="ec-at-bar">' +
        '<input type="search" class="ec-at-q" placeholder="Tìm mã, tiêu đề, người…" value="' + esc(st.f.search || "") + '">' +
        chonHTML("status", "Mọi trạng thái", o.statuses, st.f.status) +
        chonHTML("department", "Mọi phòng ban", o.departments, st.f.department) +
        chonHTML("requester", "Mọi người đề nghị", o.requesters, st.f.requester) +
        '<input type="date" class="ec-at-f" data-f="date_from" value="' + esc(st.f.date_from || "") + '" title="Từ ngày">' +
        '<input type="date" class="ec-at-f" data-f="date_to" value="' + esc(st.f.date_to || "") + '" title="Đến ngày">' +
        sapXepHTML(st) +
        (them ? nutThemHTML(st) : "") +
        '<button type="button" class="ec-at-reset">Xoá lọc' + (nTong ? " (" + nTong + ")" : "") + '</button>' +
        '<span class="ec-at-spacer"></span>' +
        '<button type="button" class="ec-at-x" data-fmt="xlsx">Excel</button>' +
        '<button type="button" class="ec-at-x" data-fmt="csv">CSV</button>' +
      '</div>' +
      (them ? hangThemHTML(st) : "") +
      '<div class="ec-at-wrap"><table class="ec-at-tb' + (cot.length ? " ec-at-rong" : "") + '"><thead><tr>' +
        '<th class="ec-at-c-ma">Mã · ngày gửi</th><th class="ec-at-c-tt">Tiêu đề · người đề nghị</th>' +
        cot.map(function (c) {
          return '<th class="ec-at-c-x' + (c.kind === "money" ? " ec-at-num" : "") + '">' + esc(c.label) + '</th>';
        }).join("") +
        '<th class="ec-at-c-tien ec-at-num">' + esc((o.amount && o.amount.label) || "Số tiền") + '</th>' +
        '<th class="ec-at-c-st">Trạng thái · bước</th><th class="ec-at-c-cho">Đang chờ ai</th>' +
      '</tr></thead><tbody class="ec-at-body"></tbody></table></div>' +
      '<div class="ec-at-foot"><span class="ec-at-dem"></span><span class="ec-at-pg"></span></div>' +
    '</div>';
  }

  // Cap nhat so o loc dang bat TAI CHO - khong dung lai khung (nguoi dung dang thao tac).
  function capNhatDem(st) {
    var r = st.el.querySelector(".ec-at-reset");
    if (r) { var n = demLoc(st, false); r.textContent = "Xoá lọc" + (n ? " (" + n + ")" : ""); }
    var so = st.el.querySelector(".ec-at-so");
    if (so) {
      var m = demLoc(st, true);
      so.textContent = String(m);
      if (m) so.removeAttribute("hidden"); else so.setAttribute("hidden", "");
    }
  }

  function veThan(st) {
    var tb = st.el.querySelector(".ec-at-body");
    var dem = st.el.querySelector(".ec-at-dem");
    var pg = st.el.querySelector(".ec-at-pg");
    var cs = soCot(st), cot = (st.opts || {}).columns || [];
    if (st.dangTai) {
      tb.innerHTML = '<tr><td colspan="' + cs + '" class="ec-at-trong">Đang tải…</td></tr>';
      dem.textContent = ""; pg.innerHTML = ""; return;
    }
    if (st.loi) {
      tb.innerHTML = '<tr><td colspan="' + cs + '" class="ec-at-trong">' + esc(st.loi) + '</td></tr>';
      dem.textContent = ""; pg.innerHTML = ""; return;
    }
    var rows = st.rows || [];
    tb.innerHTML = rows.length ? rows.map(function (v) { return dongHTML(v, cot); }).join("")
      : '<tr><td colspan="' + cs + '" class="ec-at-trong">Không có phiếu nào khớp bộ lọc.</td></tr>';
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
    var f = boLoc(st);
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

  // MOT cho dung bo loc gui server - cho CA bang LAN tep xuat. Hai ban sao thi tep xuat ra
  // se lech cai nguoi ta dang nhin, va khong ai thay cho toi luc doi chieu so lieu.
  var KHOA_LOC = ["status", "department", "requester", "date_from", "date_to"];
  function boLoc(st) {
    var f = {}, sf = st.f || {};
    KHOA_LOC.forEach(function (k) { if (sf[k]) f[k] = sf[k]; });
    // Ngay: server doi CA HAI dau moi ap dung khoang. Gui mot dau thi im lang bi bo qua,
    // nguoi dung tuong da loc. Bu dau con thieu bang bien rong hop ly.
    if (f.date_from && !f.date_to) f.date_to = new Date().toISOString().slice(0, 10);
    if (f.date_to && !f.date_from) f.date_from = "2000-01-01";
    // Thu tu: chi gui KHOA (server doi chieu danh sach trang), mac dinh thi khong gui.
    if (sf.sort && sf.sort !== "newest") f.sort = sf.sort;
    if (sf.amount_min != null) f.amount_min = sf.amount_min;
    if (sf.amount_max != null) f.amount_max = sf.amount_max;
    var ex = {}, co = false;
    Object.keys(sf.extra || {}).forEach(function (k) {
      if (sf.extra[k]) { ex[k] = sf.extra[k]; co = true; }
    });
    if (co) f.extra = ex;
    return f;
  }

  function taiTep(st, fmt, nut) {
    var f = boLoc(st);
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
      var x = f.getAttribute("data-x"), k = f.getAttribute("data-f");
      if (x) {
        st.f.extra = st.f.extra || {};
        st.f.extra[x] = f.value || "";
      } else if (k === "amount_min" || k === "amount_max") {
        st.f[k] = docTien(f);
      } else {
        st.f[k] = f.value || "";
      }
      capNhatDem(st);
      st.start = 0; nap(st);
    });
    el.addEventListener("click", function (e) {
      var t = e.target;
      if (t.closest(".ec-at-reset")) {
        // Xoa CA thu tu lan hang "Bo loc them"; hang dang mo/dong giu nguyen nhu nguoi dung de.
        st.f = moiBoLoc(); st.start = 0;
        el.innerHTML = khung(st); noiSuKien(st); nap(st); return;
      }
      var mo = t.closest(".ec-at-mo");
      if (mo) {
        st.moRong = !st.moRong;
        var hang = el.querySelector(".ec-at-more");
        if (hang) { if (st.moRong) hang.removeAttribute("hidden"); else hang.setAttribute("hidden", ""); }
        mo.setAttribute("aria-expanded", st.moRong ? "true" : "false");
        return;
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

  var SO_KHUNG = 0;
  function render(box, o) {
    if (!box) return;
    o = o || {};
    var st = {
      el: box, goi: o.call, ns: o.ns || "", moChiTiet: o.open,
      f: moiBoLoc(), start: 0, len: o.pageLength || 50,
      rows: [], total: 0, opts: { statuses: [], departments: [], requesters: [] },
      luot: 0, moRong: false, idThem: "ec-at-them-" + (++SO_KHUNG)
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

  window.EcAllTab = {
    render: render, _dongHTML: dongHTML, _tien: tien, _maNgan: maNgan,
    _boLoc: boLoc, _docTien: docTien
  };
})();
