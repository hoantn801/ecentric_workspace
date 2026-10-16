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
// LOC THEM (16/10/2026, Finance gop y tren Contract Review): sap xep, khoang so tien, cot +
// o loc rieng tung form. Tat ca do SERVER khai qua get_all_filters (`amount`, `columns`,
// `extra_filters`, `sort_cols`) tu ApprovalDefinition - bundle khong biet form nao co gi.
// Cung ngay, PO duyet dua sap xep + loc LEN HEADER COT (xem khoi "SAP XEP + LOC TREN
// HEADER COT" ben duoi) thay cho hang o chon + "Bo loc them".
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

  // ======================================================================================
  // SAP XEP + LOC TREN HEADER COT (16/10/2026, PO Hoan duyet mockup): kieu Excel / Sheets.
  //   * Bam NHAN cot -> sap xep theo cot do; bam lan nua -> dao chieu. Mui ten o cot dang sap.
  //   * Bam PHEU canh nhan -> o noi (popover) neo duoi header: hai nut chieu sap xep + o loc
  //     cua cot (tick nhieu gia tri / khoang so tien / khoang ngay) + "Bỏ lọc" / "Áp dụng".
  //   * <= 640px: o noi thanh tam day (bottom sheet), nut >= 44px.
  // Thanh tren chi con: tim kiem, hang chip tom tat, "Xoá lọc (n)", xuat tep.
  // Cot nao sap xep duoc do SERVER noi (get_all_filters.sort_cols) - bam cot server khong
  // nhan roi im lang ve mac dinh la noi doi nguoi dung.
  // ======================================================================================

  // Pheu: SVG noi dong, khong dua vao font icon (trang khong bao dam nap font nao).
  var PHEU = '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">' +
    '<path d="M1.5 2.5h13l-5 6v4.5l-3 1.5v-6z" fill="currentColor"/></svg>';
  var MAC_DINH = { col: "submitted", dir: "desc" };
  var HIEN_TOI_DA = 3;          // chip liet ke toi da 3 gia tri, con lai "+n"
  var TIM_KHI_TREN = 8;         // danh sach tick > 8 dong thi co o tim nho

  function moiBoLoc() {
    return {
      search: "", sort: null, status: [], department: [], requester: [],
      date_from: "", date_to: "", amount_min: null, amount_max: null, extra: {}
    };
  }

  function laMacDinh(s) { return !s || (s.col === MAC_DINH.col && s.dir === MAC_DINH.dir); }

  // Bo dau de tim "dong" ra "Đông", "hop dong" ra "Hợp đồng".
  function boDau(s) {
    return String(s == null ? "" : s).toLowerCase().replace(/đ/g, "d")
      .normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  function giaTri(o) { return o && typeof o === "object" && o.value != null ? o.value : o; }
  function nhanCua(o) {
    if (o && typeof o === "object") return o.label != null ? o.label : o.value;
    return o;
  }

  // Loc rieng cua form ma KHONG co cot de neo (khai all_tab_filters nhung khong khai cot):
  // dua vao o noi cua cot "Tieu de · nguoi de nghi" de van loc duoc.
  function locMoCoi(o) {
    var coCot = {};
    (o.columns || []).forEach(function (c) { coCot[c.fieldname] = true; });
    return (o.extra_filters || []).filter(function (x) { return !coCot[x.fieldname]; });
  }
  function locCua(o, fn) {
    var ds = o.extra_filters || [];
    for (var i = 0; i < ds.length; i++) if (ds[i].fieldname === fn) return ds[i];
    return null;
  }

  // Danh sach cot cua bang (CA cot co dinh lan cot form khai) - mot cho duy nhat biet cot nao
  // sap xep / loc duoc va bang cach nao.
  function dsCot(st) {
    var o = st.opts || {};
    var sx = Array.isArray(o.sort_cols) ? o.sort_cols : ["submitted", "status"];
    function duoc(k) { return sx.indexOf(k) >= 0; }
    var nguoi = (o.requesters || []).length || (o.departments || []).length || locMoCoi(o).length;
    var cot = [
      { key: "submitted", cls: "ec-at-c-ma", label: "Mã · ngày gửi", ngan: "Ngày gửi",
        kind: "date", sort: duoc("submitted"), loc: "ngay" },
      { key: "title", cls: "ec-at-c-tt", label: "Tiêu đề · người đề nghị", ngan: "Tiêu đề",
        kind: "text", sort: duoc("title"), loc: nguoi ? "nguoi" : null }
    ];
    (o.columns || []).forEach(function (c) {
      var k = "x:" + c.fieldname;
      cot.push({
        key: k, cls: "ec-at-c-x" + (c.kind === "money" ? " ec-at-num" : ""), label: c.label,
        ngan: c.label, kind: c.kind, sort: duoc(k), fn: c.fieldname,
        // `filter` do server noi; server cu khong noi thi dua vao extra_filters co cung ten.
        loc: (c.filter !== false && locCua(o, c.fieldname)) ? "x" : null
      });
    });
    var nhanTien = (o.amount && o.amount.label) || "Số tiền";
    cot.push({ key: "amount", cls: "ec-at-c-tien ec-at-num", label: nhanTien, ngan: nhanTien,
      kind: "money", sort: !!o.amount && duoc("amount"), loc: o.amount ? "tien" : null });
    cot.push({ key: "status", cls: "ec-at-c-st", label: "Trạng thái · bước", ngan: "Trạng thái",
      kind: "text", sort: duoc("status"), loc: (o.statuses || []).length ? "status" : null });
    cot.push({ key: "cho", cls: "ec-at-c-cho", label: "Đang chờ ai", sort: false, loc: null });
    return cot;
  }
  function cotTheoKhoa(st, k) {
    var ds = dsCot(st);
    for (var i = 0; i < ds.length; i++) if (ds[i].key === k) return ds[i];
    return null;
  }

  // Bam lan dau: cot chu A -> Z; cot tien / ngay cao -> thap, moi -> cu.
  function chieuDau(c) { return (c.kind === "money" || c.kind === "date") ? "desc" : "asc"; }
  function nhanChieu(c, dir, hoa) {
    var t = (c.kind === "money") ? (dir === "asc" ? "thấp → cao" : "cao → thấp")
      : (c.kind === "date") ? (dir === "asc" ? "cũ → mới" : "mới → cũ")
        : (dir === "asc" ? "A → Z" : "Z → A");
    return hoa ? t.charAt(0).toUpperCase() + t.slice(1) : t;
  }

  function sapHienTai(st) { return st.f.sort || MAC_DINH; }

  function datSap(st, col, dir) {
    st.f.sort = (col === MAC_DINH.col && dir === MAC_DINH.dir) ? null : { col: col, dir: dir };
  }

  // ---- trang thai loc cua tung cot --------------------------------------------------------
  function coLocCot(st, c) {
    var f = st.f;
    if (c.loc === "ngay") return !!(f.date_from || f.date_to);
    if (c.loc === "nguoi") {
      return !!(f.requester.length || f.department.length ||
        locMoCoi(st.opts || {}).some(function (x) { return ((f.extra || {})[x.fieldname] || []).length; }));
    }
    if (c.loc === "x") return !!((f.extra || {})[c.fn] || []).length;
    if (c.loc === "tien") return f.amount_min != null || f.amount_max != null;
    if (c.loc === "status") return !!f.status.length;
    return false;
  }

  // So o loc DANG BAT (khong tinh tim kiem va thu tu) - moi nhom gia tri tinh mot.
  function demLoc(st) {
    var f = st.f, n = 0;
    ["status", "department", "requester"].forEach(function (k) { if ((f[k] || []).length) n++; });
    if (f.date_from || f.date_to) n++;
    if (f.amount_min != null || f.amount_max != null) n++;
    Object.keys(f.extra || {}).forEach(function (k) { if ((f.extra[k] || []).length) n++; });
    return n;
  }

  // ---- header --------------------------------------------------------------------------
  function thHTML(st, c) {
    var s = sapHienTai(st), dang = c.sort && s.col === c.key;
    var h = '<th class="' + c.cls + (dang ? " ec-at-on" : "") + '" data-col="' + esc(c.key) + '"' +
      (c.sort ? ' aria-sort="' + (dang ? (s.dir === "asc" ? "ascending" : "descending") : "none") + '"' : "") +
      '><span class="ec-at-h">';
    if (c.sort) {
      h += '<button type="button" class="ec-at-sx" data-sort="' + esc(c.key) + '" title="Sắp xếp theo ' +
        esc(c.ngan) + '"><span class="ec-at-hl">' + esc(c.label) + '</span><span class="ec-at-mui" aria-hidden="true">' +
        (dang ? (s.dir === "asc" ? "▲" : "▼") : "") + '</span></button>';
    } else {
      h += '<span class="ec-at-hl">' + esc(c.label) + '</span>';
    }
    if (c.sort || c.loc) {
      var mo = st.mo === c.key;
      h += '<button type="button" class="ec-at-pheu' + (coLocCot(st, c) ? " ec-at-co" : "") +
        '" data-pop="' + esc(c.key) + '" aria-haspopup="dialog" aria-expanded="' + (mo ? "true" : "false") +
        '" aria-label="Sắp xếp và lọc: ' + esc(c.ngan) + '" title="Sắp xếp và lọc">' + PHEU + '</button>';
    }
    return h + '</span></th>';
  }

  function theadHTML(st) {
    return '<tr>' + dsCot(st).map(function (c) { return thHTML(st, c); }).join("") + '</tr>';
  }

  // ---- chip tom tat ----------------------------------------------------------------------
  function lietKe(ds) {
    var hien = ds.slice(0, HIEN_TOI_DA).join(", ");
    return ds.length > HIEN_TOI_DA ? hien + " +" + (ds.length - HIEN_TOI_DA) : hien;
  }
  function nhanTheoGiaTri(ds, vals) {
    var m = {};
    (ds || []).forEach(function (o) { m[String(giaTri(o))] = nhanCua(o); });
    return vals.map(function (v) { return m[String(v)] != null ? m[String(v)] : v; });
  }
  function khoangChu(a, b) { return (a || "…") + " – " + (b || "…"); }

  function dsChip(st) {
    var f = st.f, o = st.opts || {}, out = [];
    if (!laMacDinh(f.sort)) {
      var c = cotTheoKhoa(st, f.sort.col);
      if (c) out.push({ bo: "sort", t: c.ngan + ": " + nhanChieu(c, f.sort.dir) });
    }
    if (f.date_from || f.date_to) {
      out.push({ bo: "date", t: "Ngày gửi: " + khoangChu(f.date_from && ngayNgan(f.date_from), f.date_to && ngayNgan(f.date_to)) });
    }
    if (f.requester.length) out.push({ bo: "requester", t: "Người đề nghị: " + lietKe(nhanTheoGiaTri(o.requesters, f.requester)) });
    if (f.department.length) out.push({ bo: "department", t: "Phòng ban: " + lietKe(f.department) });
    Object.keys(f.extra || {}).forEach(function (fn) {
      var v = f.extra[fn] || [];
      if (!v.length) return;
      var x = locCua(o, fn);
      out.push({ bo: "x:" + fn, t: ((x && x.label) || fn) + ": " + lietKe(v) });
    });
    if (f.amount_min != null || f.amount_max != null) {
      out.push({ bo: "amount", t: ((o.amount && o.amount.label) || "Số tiền") + ": " +
        khoangChu(f.amount_min != null ? hienTien(f.amount_min) : "", f.amount_max != null ? hienTien(f.amount_max) : "") });
    }
    if (f.status.length) out.push({ bo: "status", t: "Trạng thái: " + lietKe(nhanTheoGiaTri(o.statuses, f.status)) });
    return out;
  }

  function chipsHTML(st) {
    return dsChip(st).map(function (c) {
      return '<span class="ec-at-chip"><span class="ec-at-chip-t" title="' + esc(c.t) + '">' + esc(c.t) + '</span>' +
        '<button type="button" class="ec-at-chip-x" data-bo="' + esc(c.bo) + '" aria-label="Bỏ ' + esc(c.t) + '">×</button></span>';
    }).join("");
  }

  function boMot(st, k) {
    var f = st.f;
    if (k === "sort") f.sort = null;
    else if (k === "date") { f.date_from = ""; f.date_to = ""; }
    else if (k === "amount") { f.amount_min = null; f.amount_max = null; }
    else if (k === "status" || k === "department" || k === "requester") f[k] = [];
    else if (k.indexOf("x:") === 0) { f.extra = f.extra || {}; delete f.extra[k.slice(2)]; }
  }

  // ---- o noi (popover) cua mot cot ---------------------------------------------------------
  function nhomTickHTML(nhom, nhan, ds, chon) {
    var co = {};
    (chon || []).forEach(function (v) { co[String(v)] = true; });
    var h = '<fieldset class="ec-at-nhom" data-nhom="' + esc(nhom) + '"><legend>' + esc(nhan) + '</legend>';
    if ((ds || []).length > TIM_KHI_TREN) {
      h += '<input type="search" class="ec-at-tim" placeholder="Tìm…" aria-label="Tìm trong ' + esc(nhan) + '">';
    }
    h += '<div class="ec-at-ds">';
    if (!(ds || []).length) h += '<div class="ec-at-chua">Chưa có giá trị nào.</div>';
    (ds || []).forEach(function (o) {
      var v = String(giaTri(o)), l = String(nhanCua(o));
      h += '<label class="ec-at-ck" data-tim="' + esc(boDau(l + " " + v)) + '"><input type="checkbox" value="' + esc(v) + '"' +
        (co[v] ? " checked" : "") + '><span>' + esc(l) + '</span></label>';
    });
    return h + '</div></fieldset>';
  }

  function popHTML(st, c) {
    var f = st.f, o = st.opts || {}, s = sapHienTai(st);
    var h = '<div class="ec-at-pop-dau"><span class="ec-at-pop-t">' + esc(c.ngan) + '</span>' +
      '<button type="button" class="ec-at-dong" aria-label="Đóng">×</button></div>';
    if (c.sort) {
      h += '<div class="ec-at-hg-row">' + ["asc", "desc"].map(function (d) {
        var dang = s.col === c.key && s.dir === d;
        return '<button type="button" class="ec-at-hg' + (dang ? " ec-at-dang" : "") + '" data-dir="' + d +
          '" aria-pressed="' + (dang ? "true" : "false") + '">' + esc(nhanChieu(c, d, true)) + '</button>';
      }).join("") + '</div>';
    }
    if (c.loc) {
      h += '<div class="ec-at-pop-than">';
      if (c.loc === "ngay") {
        // data-ec-dp-range: ec_datepicker (asset dung chung) ve dai khoang tren lich.
        var nhom = "ec-at-ngay-" + st.so;
        h += '<div class="ec-at-khoang">' +
          '<label>Từ ngày<input type="date" data-k="date_from" data-ec-dp-range="' + nhom + '" data-ec-dp-role="start" value="' + esc(f.date_from || "") + '"></label>' +
          '<label>Đến ngày<input type="date" data-k="date_to" data-ec-dp-range="' + nhom + '" data-ec-dp-role="end" value="' + esc(f.date_to || "") + '"></label></div>';
      } else if (c.loc === "tien") {
        h += '<div class="ec-at-khoang">' +
          '<label>Từ<input type="text" inputmode="numeric" data-money data-k="amount_min" class="ec-at-tien" value="' + esc(hienTien(f.amount_min)) + '"></label>' +
          '<label>Đến<input type="text" inputmode="numeric" data-money data-k="amount_max" class="ec-at-tien" value="' + esc(hienTien(f.amount_max)) + '"></label></div>';
      } else if (c.loc === "status") {
        h += nhomTickHTML("status", "Trạng thái", o.statuses, f.status);
      } else if (c.loc === "x") {
        var x = locCua(o, c.fn) || {};
        h += nhomTickHTML("x:" + c.fn, c.label, x.options, (f.extra || {})[c.fn]);
      } else if (c.loc === "nguoi") {
        h += nhomTickHTML("requester", "Người đề nghị", o.requesters, f.requester) +
          nhomTickHTML("department", "Phòng ban", o.departments, f.department) +
          locMoCoi(o).map(function (x) {
            return nhomTickHTML("x:" + x.fieldname, x.label, x.options, (f.extra || {})[x.fieldname]);
          }).join("");
      }
      h += '</div><div class="ec-at-pop-chan"><button type="button" class="ec-at-bo">Bỏ lọc</button>' +
        '<button type="button" class="ec-at-ap">Áp dụng</button></div>';
    }
    return h;
  }

  // Doc o noi -> st.f (chi cot dang mo). Goi khi "Áp dụng" va khi bam nut chieu sap xep
  // (bam chieu = ap dung luon, khong de mat dau tick nguoi dung vua chon).
  function docPop(st, c, pop) {
    var f = st.f;
    if (!c.loc) return;
    if (c.loc === "ngay") {
      var a = pop.querySelector('[data-k="date_from"]').value || "";
      var b = pop.querySelector('[data-k="date_to"]').value || "";
      if (a && b && a > b) { var t = a; a = b; b = t; }      // go nguoc thi hieu y
      f.date_from = a; f.date_to = b;
      return;
    }
    if (c.loc === "tien") {
      var lo = docTien(pop.querySelector('[data-k="amount_min"]'));
      var hi = docTien(pop.querySelector('[data-k="amount_max"]'));
      if (lo != null && hi != null && lo > hi) { var u = lo; lo = hi; hi = u; }
      f.amount_min = lo; f.amount_max = hi;
      return;
    }
    [].forEach.call(pop.querySelectorAll(".ec-at-nhom"), function (g) {
      var nhom = g.getAttribute("data-nhom");
      var vals = [].map.call(g.querySelectorAll('input[type="checkbox"]:checked'), function (i) { return i.value; });
      if (nhom.indexOf("x:") === 0) {
        f.extra = f.extra || {};
        if (vals.length) f.extra[nhom.slice(2)] = vals; else delete f.extra[nhom.slice(2)];
      } else {
        f[nhom] = vals;
      }
    });
  }

  function boLocCot(st, c) {
    var f = st.f;
    if (c.loc === "ngay") boMot(st, "date");
    else if (c.loc === "tien") boMot(st, "amount");
    else if (c.loc === "status") boMot(st, "status");
    else if (c.loc === "x") boMot(st, "x:" + c.fn);
    else if (c.loc === "nguoi") {
      f.requester = []; f.department = [];
      locMoCoi(st.opts || {}).forEach(function (x) { boMot(st, "x:" + x.fieldname); });
    }
  }

  function laHep() {
    var w = window;
    if (typeof w.matchMedia === "function") {
      try { return w.matchMedia("(max-width: 640px)").matches; } catch (e) { /* roi xuong duoi */ }
    }
    return (w.innerWidth || 1024) <= 640;
  }

  function nutPheu(st, k) {
    var ds = st.el.querySelectorAll(".ec-at-pheu");
    for (var i = 0; i < ds.length; i++) if (ds[i].getAttribute("data-pop") === k) return ds[i];
    return null;
  }

  function moPop(st, k) {
    var c = cotTheoKhoa(st, k);
    var pop = st.el.querySelector(".ec-at-pop"), nen = st.el.querySelector(".ec-at-nen");
    if (!c || !pop) return;
    st.mo = k;
    pop.innerHTML = popHTML(st, c);
    pop.setAttribute("aria-label", "Sắp xếp và lọc: " + c.ngan);
    var hep = laHep();
    pop.className = "ec-at-pop" + (hep ? " ec-at-sheet" : "");
    pop.removeAttribute("hidden");
    if (hep) { nen.removeAttribute("hidden"); pop.style.left = ""; pop.style.top = ""; }
    else {
      nen.setAttribute("hidden", "");
      var goc = st.el.querySelector(".ec-at"), nut = nutPheu(st, k), th = nut && nut.closest("th");
      if (goc && th) {
        var r0 = goc.getBoundingClientRect(), r = th.getBoundingClientRect();
        var rong = pop.offsetWidth || 264;
        var trai = /ec-at-num/.test(th.className) ? r.right - r0.left - rong : r.left - r0.left;
        trai = Math.max(0, Math.min(trai, Math.max(0, r0.width - rong)));
        pop.style.left = trai + "px";
        pop.style.top = (r.bottom - r0.top + 4) + "px";
      }
    }
    var nut2 = nutPheu(st, k);
    if (nut2) nut2.setAttribute("aria-expanded", "true");
    var dau = pop.querySelector(".ec-at-hg, input, .ec-at-ap");
    if (dau && dau.focus) dau.focus();
    // Esc / bam ra ngoai: DONG, KHONG ap dung. Gan khi mo, go khi dong - khong de listener
    // song mai tren document sau khi tab da bi ve lai.
    st.ngoai = function (e) {
      if (!st.mo) return;
      var t = e.target;
      if (pop.contains(t)) return;
      // Lich cua ec_datepicker gan vao <body>, nam NGOAI o noi: bam chon ngay khong phai
      // "bam ra ngoai".
      if (t.closest && t.closest(".ec-dp-pop")) return;
      var p = t.closest && t.closest(".ec-at-pheu");
      if (p && p.getAttribute("data-pop") === st.mo) return;     // nut pheu tu xu ly (bat/tat)
      dongPop(st, false);
    };
    st.phim = function (e) {
      if (e.key !== "Escape" || !st.mo) return;
      if (document.querySelector(".ec-dp-pop")) return;     // Esc dong lich truoc, o noi sau
      e.preventDefault(); dongPop(st, true);
    };
    document.addEventListener("mousedown", st.ngoai, true);
    document.addEventListener("keydown", st.phim, true);
  }

  function dongPop(st, traFocus) {
    var k = st.mo;
    st.mo = null;
    if (st.ngoai) document.removeEventListener("mousedown", st.ngoai, true);
    if (st.phim) document.removeEventListener("keydown", st.phim, true);
    st.ngoai = st.phim = null;
    var pop = st.el.querySelector(".ec-at-pop"), nen = st.el.querySelector(".ec-at-nen");
    if (pop) { pop.setAttribute("hidden", ""); pop.innerHTML = ""; }
    if (nen) nen.setAttribute("hidden", "");
    var nut = k && nutPheu(st, k);
    if (nut) {
      nut.setAttribute("aria-expanded", "false");
      if (traFocus && nut.focus) nut.focus();
    }
  }

  // Dong o noi, ap dung, tra focus ve dung nut pheu (header vua ve lai).
  function xong(st, k) {
    dongPop(st, false); apDung(st);
    var nut = nutPheu(st, k);
    if (nut && nut.focus) nut.focus();
  }

  // Ve lai PHAN phu thuoc bo loc (header, chip, so dem) TAI CHO - khong dung lai khung: o tim
  // kiem dang co con tro cua nguoi dung.
  function veLoc(st) {
    var th = st.el.querySelector(".ec-at-tb thead");
    if (th) th.innerHTML = theadHTML(st);
    var ch = st.el.querySelector(".ec-at-chips");
    if (ch) {
      ch.innerHTML = chipsHTML(st);
      if (ch.innerHTML) ch.removeAttribute("hidden"); else ch.setAttribute("hidden", "");
    }
    var r = st.el.querySelector(".ec-at-reset");
    if (r) { var n = demLoc(st); r.textContent = "Xoá lọc" + (n ? " (" + n + ")" : ""); }
  }

  function apDung(st) {
    veLoc(st);
    st.start = 0; nap(st);
  }

  function soCot(st) { return 5 + ((st.opts || {}).columns || []).length; }

  function khung(st) {
    var o = st.opts || {}, cot = o.columns || [];
    var nTong = demLoc(st), chip = chipsHTML(st);
    return '<div class="ec-at">' +
      '<div class="ec-at-bar">' +
        '<input type="search" class="ec-at-q" placeholder="Tìm mã, tiêu đề, người…" aria-label="Tìm phiếu" value="' + esc(st.f.search || "") + '">' +
        '<button type="button" class="ec-at-reset">Xoá lọc' + (nTong ? " (" + nTong + ")" : "") + '</button>' +
        '<span class="ec-at-spacer"></span>' +
        '<button type="button" class="ec-at-x" data-fmt="xlsx">Excel</button>' +
        '<button type="button" class="ec-at-x" data-fmt="csv">CSV</button>' +
      '</div>' +
      '<div class="ec-at-chips" aria-live="polite"' + (chip ? "" : " hidden") + '>' + chip + '</div>' +
      '<div class="ec-at-wrap"><table class="ec-at-tb' + (cot.length ? " ec-at-rong" : "") + '"><thead>' +
        theadHTML(st) +
      '</thead><tbody class="ec-at-body"></tbody></table></div>' +
      '<div class="ec-at-foot"><span class="ec-at-dem"></span><span class="ec-at-pg"></span></div>' +
      '<div class="ec-at-nen" hidden></div>' +
      '<div class="ec-at-pop" role="dialog" hidden></div>' +
    '</div>';
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
  // Hop dong voi server (all_list._pinned_filters):
  //   status / department / requester : [gia tri...]   (server van nhan chuoi don kieu cu)
  //   date_from / date_to             : "YYYY-MM-DD"
  //   amount_min / amount_max         : so
  //   extra                           : { fieldname: [gia tri...] }
  //   sort                            : { col: "submitted|title|amount|status|x:<fieldname>",
  //                                       dir: "asc|desc" }  - mac dinh (moi -> cu) thi khong gui
  var KHOA_LOC = ["status", "department", "requester", "date_from", "date_to"];
  function boLoc(st) {
    var f = {}, sf = st.f || {};
    KHOA_LOC.forEach(function (k) {
      var v = sf[k];
      if (Array.isArray(v)) { if (v.length) f[k] = v.slice(); }
      else if (v) f[k] = v;
    });
    // Ngay: server doi CA HAI dau moi ap dung khoang. Gui mot dau thi im lang bi bo qua,
    // nguoi dung tuong da loc. Bu dau con thieu bang bien rong hop ly.
    if (f.date_from && !f.date_to) f.date_to = new Date().toISOString().slice(0, 10);
    if (f.date_to && !f.date_from) f.date_from = "2000-01-01";
    // Thu tu: chi gui KHOA COT + chieu (server doi chieu danh sach trang), mac dinh thi khong gui.
    // (Viet thang dieu kien mac dinh o day: boLoc phai tu du, khong goi ham ngoai.)
    var sx = sf.sort;
    if (sx && !(sx.col === "submitted" && sx.dir === "desc")) f.sort = { col: sx.col, dir: sx.dir };
    if (sf.amount_min != null) f.amount_min = sf.amount_min;
    if (sf.amount_max != null) f.amount_max = sf.amount_max;
    var ex = {}, co = false;
    Object.keys(sf.extra || {}).forEach(function (k) {
      var v = sf.extra[k];
      if (Array.isArray(v) ? v.length : v) { ex[k] = Array.isArray(v) ? v.slice() : [v]; co = true; }
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
      if (q) {
        st.f.search = q.value.trim();
        goLoc(st);
        return;
      }
      var tim = e.target.closest(".ec-at-tim");
      if (tim) {
        var k = boDau(tim.value.trim());
        [].forEach.call(tim.closest(".ec-at-nhom").querySelectorAll(".ec-at-ck"), function (l) {
          if (!k || l.getAttribute("data-tim").indexOf(k) >= 0) l.removeAttribute("hidden");
          else l.setAttribute("hidden", "");
        });
      }
    });
    el.addEventListener("click", function (e) {
      var t = e.target;
      if (t.closest(".ec-at-reset")) {
        // Xoa CA thu tu lan moi o loc (kem o tim) - ve lai khung, ve mac dinh moi -> cu.
        if (st.mo) dongPop(st, false);
        st.f = moiBoLoc(); st.start = 0;
        el.innerHTML = khung(st); nap(st); return;
      }
      var chipX = t.closest(".ec-at-chip-x");
      if (chipX) { boMot(st, chipX.getAttribute("data-bo")); apDung(st); return; }
      var sx = t.closest(".ec-at-sx");
      if (sx) {
        var c = cotTheoKhoa(st, sx.getAttribute("data-sort"));
        if (!c || !c.sort) return;
        var s = sapHienTai(st);
        datSap(st, c.key, s.col === c.key ? (s.dir === "asc" ? "desc" : "asc") : chieuDau(c));
        if (st.mo) dongPop(st, false);
        apDung(st);
        return;
      }
      var ph = t.closest(".ec-at-pheu");
      if (ph) {
        var k = ph.getAttribute("data-pop");
        var dangMo = st.mo === k;
        if (st.mo) dongPop(st, false);
        if (!dangMo) moPop(st, k);
        return;
      }
      var pop = t.closest(".ec-at-pop");
      if (pop) {
        var cc = cotTheoKhoa(st, st.mo);
        if (!cc) return;
        var hg = t.closest(".ec-at-hg");
        if (hg) {
          docPop(st, cc, pop);
          datSap(st, cc.key, hg.getAttribute("data-dir") === "asc" ? "asc" : "desc");
          xong(st, cc.key);
          return;
        }
        if (t.closest(".ec-at-ap")) {
          docPop(st, cc, pop);
          xong(st, cc.key);
          return;
        }
        if (t.closest(".ec-at-bo")) {
          boLocCot(st, cc);
          xong(st, cc.key);
          return;
        }
        if (t.closest(".ec-at-dong")) { dongPop(st, true); return; }
        return;
      }
      if (t.closest(".ec-at-nen")) { dongPop(st, false); return; }
      var x = t.closest(".ec-at-x");
      if (x) { taiTep(st, x.getAttribute("data-fmt"), x); return; }
      if (t.closest(".ec-at-pv")) { st.start = Math.max(0, st.start - st.len); nap(st); return; }
      if (t.closest(".ec-at-nx")) { st.start = st.start + st.len; nap(st); return; }
      var row = t.closest(".ec-at-row");
      if (row && st.moChiTiet) st.moChiTiet(row.getAttribute("data-open"));
    });
    el.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      // Enter trong o noi = "Áp dụng" (o so tien / ngay / tim khong phai form submit).
      var pop = e.target.closest && e.target.closest(".ec-at-pop");
      if (pop) {
        if (e.target.tagName === "INPUT" && e.target.type !== "checkbox") {
          e.preventDefault();
          var ap = pop.querySelector(".ec-at-ap");
          if (ap && !e.target.classList.contains("ec-at-tim")) ap.click();
        }
        return;
      }
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
      luot: 0, mo: null, so: ++SO_KHUNG
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
    _boLoc: boLoc, _docTien: docTien, _dsCot: dsCot, _dsChip: dsChip
  };
})();
