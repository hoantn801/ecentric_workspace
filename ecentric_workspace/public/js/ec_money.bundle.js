// Copyright (c) 2026, eCentric and contributors
//
// O nhap SO TIEN dung chung cho moi form phe duyet (01/10/2026, Hoan): phan cach hang nghin
// bang DAU CHAM (kieu Viet Nam: 10.000.000), can le PHAI (CSS ec_money.bundle.css).
//
// GIAO KEO VOI TRANG:
//   markup: <input type="text" inputmode="numeric" data-money data-model="x"
//                  value="'+esc(window.EcMoney?EcMoney.fmt(v):(v==null?"":v))+'">
//           So le (USD...): data-money="dec" + inputmode="decimal" - dau PHAY la phan thap phan.
//   binder: var v = (window.EcMoney && el.hasAttribute("data-money")) ? EcMoney.val(el) : ...
// Trang thai ban dau nam trong markup (gia tri da dinh dang san luc ve). Asset chi them MOT
// listener 'input' pha capture tren document: dinh dang lai o dang go (giu vi tri con tro)
// TRUOC khi handler cua trang doc gia tri. Model cua trang luon nhan so (Number) hoac null.
(function () {
  "use strict";
  if (window.EcMoney) return;

  function isDec(el) { return !!el && el.getAttribute("data-money") === "dec"; }

  // Chuoi NGUOI DUNG GO (da dinh dang kieu VN) -> Number | null. Khong dung cho so tu server.
  function parse(str, dec) {
    var s = String(str == null ? "" : str);
    if (!dec) {
      var d = s.replace(/\D/g, "");
      return d === "" ? null : Number(d);
    }
    s = s.replace(/\./g, "").replace(/[^\d,]/g, "");
    var i = s.indexOf(",");
    if (i >= 0) s = s.slice(0, i) + "." + s.slice(i + 1).replace(/,/g, "").slice(0, 2);
    if (s === "" || s === ".") return null;
    return Number(s);
  }

  function groupInt(digits) {
    digits = digits.replace(/^0+(?=\d)/, "");
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  // So (tu server / model) -> chuoi hien thi. Rong khi null / "".
  function fmt(v, dec) {
    if (v == null || v === "") return "";
    var n = Number(v);
    if (isNaN(n)) return String(v);
    var neg = n < 0 ? "-" : "";
    n = Math.abs(n);
    if (!dec) return neg + groupInt(String(Math.round(n)));
    var parts = (Math.round(n * 100) / 100).toFixed(2).split(".");
    var frac = parts[1].replace(/0+$/, "");
    return neg + groupInt(parts[0]) + (frac ? "," + frac : "");
  }

  // Dinh dang chuoi DANG GO: giu dau phay vua go va phan thap phan dang do.
  function typing(raw, dec) {
    var s = String(raw == null ? "" : raw);
    if (!dec) { var d = s.replace(/\D/g, ""); return d ? groupInt(d) : ""; }
    s = s.replace(/\./g, "").replace(/[^\d,]/g, "");
    var i = s.indexOf(",");
    var intPart = i >= 0 ? s.slice(0, i) : s;
    var out = intPart ? groupInt(intPart) : (i >= 0 ? "0" : "");
    if (i >= 0) out += "," + s.slice(i + 1).replace(/,/g, "").slice(0, 2);
    return out;
  }

  function reformat(el) {
    var raw = el.value, pos = el.selectionStart != null ? el.selectionStart : raw.length;
    var keep = isDec(el) ? /[\d,]/ : /\d/;
    var before = 0;
    for (var k = 0; k < pos && k < raw.length; k++) if (keep.test(raw[k])) before++;
    var out = typing(raw, isDec(el));
    if (out === raw) return;
    el.value = out;
    var i = 0, n = 0;
    while (i < out.length && n < before) { if (keep.test(out[i])) n++; i++; }
    try { el.setSelectionRange(i, i); } catch (e) { /* input khong ho tro selection */ }
  }

  function val(el) { return el ? parse(el.value, isDec(el)) : null; }

  document.addEventListener("input", function (ev) {
    var el = ev.target;
    if (el && el.tagName === "INPUT" && el.hasAttribute("data-money") && !el.readOnly) reformat(el);
  }, true);

  window.EcMoney = { fmt: fmt, parse: parse, val: val, reformat: reformat };
})();
