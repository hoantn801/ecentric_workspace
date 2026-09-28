/* ec_hr_pages.js - phan DUNG CHUNG cua 3 trang /ec-hr/attendance, /ec-hr/leave, /ec-hr/salary.
 *
 * Truoc 28/09 moi trang tu mang mot ban rieng cua cac khoi nay (ec-auth-guard-v1,
 * ec-cradle-js, ec-tab-js, the theme-color) - ba ban lech nhau tung chut va trang nghi
 * phep goi ec_hr_today_state BA lan moi lan mo (boot chay ca o DOMContentLoaded lan
 * load, cong them mot listener load rieng). NHIEU_LOP/brief_hr.md muc 4-5.
 *
 * Nap bang <script src> o CUOI noi dung trang (sau thanh tab), nen luc chay thi moi phan
 * tu da co. Khong boc window.fetch, khong chen khoi <script id> nao vao trang.
 * Sua file nay thi doi ?v= trong ca 3 trang (test hr/tests/test_hr_pages_layers.py bat).
 */
(function () {
  "use strict";
  if (window.__ecHrPages) return;
  window.__ecHrPages = true;

  /* 1. Chua dang nhap thi sang /login, thay vi de trang ve nua voi "Hi, -" va vong xoay mai
     mai (ec-auth-guard-v1, 19/08). Dem so lan trong sessionStorage de khong lap vo tan neu
     trinh duyet chan cookie. */
  try {
    var mu = document.cookie.match(/(?:^|; *)user_id=([^;]*)/);
    var u = mu ? decodeURIComponent(mu[1]) : "";
    if (u && u !== "Guest") {
      try { sessionStorage.removeItem("ec_auth_try"); } catch (e) {}
    } else {
      var tries = 0;
      try { tries = parseInt(sessionStorage.getItem("ec_auth_try") || "0", 10) || 0; } catch (e) {}
      if (tries < 2) {
        try { sessionStorage.setItem("ec_auth_try", String(tries + 1)); } catch (e) {}
        location.replace("/login?redirect-to=" + encodeURIComponent(location.pathname + location.search));
        return;
      }
    }
  } catch (e) {}

  /* 2. Mau thanh trang thai tren dien thoai. */
  try {
    var tc = document.querySelector('meta[name="theme-color"]');
    if (!tc) { tc = document.createElement("meta"); tc.setAttribute("name", "theme-color"); document.head.appendChild(tc); }
    tc.setAttribute("content", "#F4F6FB");
  } catch (e) {}

  /* 3. Thanh tab duoi cung (dien thoai): danh dau tab dang mo, ve "noi" om nut cham cong,
     bat trang thai "da cham cong". */
  function td() {
    var x = new Date();
    return x.getFullYear() + "-" + ("0" + (x.getMonth() + 1)).slice(-2) + "-" + ("0" + x.getDate()).slice(-2);
  }
  function mark() {
    var p = location.pathname.replace(/\/$/, "");
    [].forEach.call(document.querySelectorAll(".ec-tab a[data-p]"), function (a) {
      if (a.getAttribute("data-p") === p) a.classList.add("on");
    });
  }
  function draw() {
    var svg = document.querySelector(".ec-tabbg"), wrap = document.querySelector(".ec-tabwrap");
    if (!svg || !wrap) return;
    var b = wrap.getBoundingClientRect(), W = Math.round(b.width), H = Math.round(b.height);
    if (!W || !H) return;
    var fab = document.getElementById("ec-tab-ci");
    var fr = fab ? fab.getBoundingClientRect() : null;
    var Rfab = fr ? fr.width / 2 : 26;
    var cy = fr ? (fr.top + fr.height / 2 - b.top) : 12;
    var cx = W / 2, gap = 5, Rc = Rfab + gap, Rf = 30, R = 26;
    var k = Rc + Rf, dx2 = k * k - (Rf - cy) * (Rf - cy);
    if (dx2 < 1) return;
    var fx = Math.sqrt(dx2), tx = fx - Rf * fx / k, ty = Rf - Rf * (Rf - cy) / k;
    var d = "M0 " + H + " L0 " + R + " Q0 0 " + R + " 0 L" + (cx - fx).toFixed(2) + " 0" +
      " A " + Rf + " " + Rf + " 0 0 1 " + (cx - tx).toFixed(2) + " " + ty.toFixed(2) +
      " A " + Rc.toFixed(2) + " " + Rc.toFixed(2) + " 0 0 0 " + (cx + tx).toFixed(2) + " " + ty.toFixed(2) +
      " A " + Rf + " " + Rf + " 0 0 1 " + (cx + fx).toFixed(2) + " 0" +
      " L" + (W - R) + " 0 Q" + W + " 0 " + W + " " + R + " L" + W + " " + H + " Z";
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    var path = svg.querySelector("path");
    if (path) { path.setAttribute("d", d); path.setAttribute("fill", "#ffffff"); }
  }
  function prime() {
    try {
      if (sessionStorage.getItem("ec_ci") === td()) {
        var wp = document.querySelector(".ec-tabwrap");
        if (wp) wp.classList.add("checked");
      }
    } catch (e) {}
  }
  var asked = false;
  function askState() {
    // MOT lan moi trang. Trang cham cong tu biet trang thai tu du lieu cua chinh no (nut
    // #ha-ci-btn, dong bo sang thanh tab trong script cua trang) nen khong hoi lai.
    if (asked || document.getElementById("ha-ci-btn")) return;
    asked = true;
    var tk = (window.frappe && window.frappe.csrf_token) || "";
    fetch("/api/method/ec_hr_today_state", {
      method: "POST",
      headers: { "X-Frappe-CSRF-Token": tk, "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({})
    }).then(function (r) { return r.json(); }).then(function (j) {
      var m = j && j.message, wp = document.querySelector(".ec-tabwrap");
      try { if (m && m.checked) sessionStorage.setItem("ec_ci", td()); else sessionStorage.removeItem("ec_ci"); } catch (e) {}
      if (wp) wp.classList.toggle("checked", !!(m && (m.checked || m.dayoff)));
      draw();
    }).catch(function () { draw(); });
  }

  mark(); prime(); draw();
  function boot() { draw(); askState(); setTimeout(draw, 150); setTimeout(draw, 600); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  window.addEventListener("load", draw);
  window.addEventListener("resize", draw);
})();
