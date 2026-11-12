/* ec_quiz_live — thẻ nổi "Quiz đang mở" (Hoàn chốt 12/11/2026, cửa vào F3 số 2).
 *
 * Hiện trên mọi trang ERP có vỏ shell (`[data-ec-shell]`) và trên app nhân sự (`.ec-tabwrap`,
 * ngay phía trên thanh tab - thanh tab KHÔNG đổi). Chỉ hiện khi có phòng quiz đang mở;
 * bấm là vào /quiz/choi?c=<mã>. Đóng (×) thì ẩn phòng đó tới hết phiên trình duyệt.
 *
 * KHÔNG có luật nghiệp vụ: danh sách phòng do server trả
 * (ecentric_workspace.dao_tao.controllers.api.live_card - cache 15 giây chung cho cả công ty).
 * Trang tự tắt bằng `data-ec-no-quizcard`; tắt toàn site: site_config ec_quiz_card_disabled.
 * Giao diện trong Shadow DOM (Bootstrap của Frappe tô đè .btn/.card - bẫy 16/09).
 * Đứng bên TRÁI để không đè nút Khay ở góc phải.
 */
(function () {
  "use strict";
  if (window.__ecQuizCard) return;
  window.__ecQuizCard = true;

  var API = "/api/method/ecentric_workspace.dao_tao.controllers.api.live_card";
  var POLL_MS = 45000;
  var host = null, root = null, timer = null;

  function eligible() {
    var p = location.pathname || "/";
    if (/^\/(quiz|login|app|desk)(\/|$)/.test(p)) return false;
    if (document.querySelector("[data-ec-no-quizcard]")) return false;
    return !!(document.querySelector("[data-ec-shell]") || document.querySelector(".ec-tabwrap"));
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function dismissed(code) { try { return sessionStorage.getItem("ecq_card_x_" + code) === "1"; } catch (e) { return false; } }
  function dismiss(code) { try { sessionStorage.setItem("ecq_card_x_" + code, "1"); } catch (e) { /* bo qua */ } }

  function bottomOffset() {
    var bar = document.querySelector(".ec-tabwrap");
    if (bar) {
      var cs = window.getComputedStyle(bar);
      if (cs.display !== "none" && cs.visibility !== "hidden") return Math.round(bar.getBoundingClientRect().height) + 12;
    }
    return 20;
  }

  var CSS = ":host{all:initial}" +
    ".card{position:fixed;left:12px;right:88px;max-width:420px;bottom:calc(var(--b,20px) + env(safe-area-inset-bottom,0px));z-index:9990;" +
    "display:flex;align-items:center;gap:10px;padding:10px 10px 10px 14px;border-radius:16px;color:#fff;" +
    "background:linear-gradient(120deg,#46178f,#864cbf);box-shadow:0 10px 28px rgba(46,15,98,.35);" +
    "font:500 14px/1.35 Inter,-apple-system,'Segoe UI',Roboto,sans-serif;animation:up .25s ease-out}" +
    "@keyframes up{from{transform:translateY(16px);opacity:0}to{transform:none;opacity:1}}" +
    "@media (prefers-reduced-motion:reduce){.card{animation:none}}" +
    ".ic{width:36px;height:36px;border-radius:10px;background:rgba(255,255,255,.18);display:flex;align-items:center;justify-content:center;flex:none;font-size:20px}" +
    ".tx{min-width:0;flex:1}.tx b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
    ".tx span{font-size:12px;opacity:.85}" +
    "a.go{flex:none;background:#f5b800;color:#3a2c00;text-decoration:none;font-weight:800;border-radius:10px;padding:9px 12px;min-height:40px;display:flex;align-items:center}" +
    "button.x{flex:none;background:transparent;border:0;color:#fff;opacity:.8;font-size:20px;width:32px;height:40px;cursor:pointer}" +
    "a.go:focus-visible,button.x:focus-visible{outline:2px solid #fff;outline-offset:2px}" +
    "@media (min-width:901px){.card{right:auto;width:380px}}";

  function render(rooms) {
    var r = (rooms || []).filter(function (x) { return x && x.code && !dismissed(x.code); })[0];
    if (!r) { if (host) host.style.display = "none"; return; }
    if (!host) {
      host = document.createElement("div");
      host.setAttribute("data-ec-quizcard", "1");
      root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
      document.body.appendChild(host);
    }
    host.style.display = "";
    host.style.setProperty("--b", bottomOffset() + "px");
    var playing = r.phase !== "lobby";
    root.innerHTML = "<style>" + CSS + "</style>" +
      '<div class="card" role="status"><span class="ic" aria-hidden="true">🎮</span><span class="tx"><b>' + esc(r.title || "Quiz") +
      "</b><span>" + (playing ? "Đang chơi" : "Quiz đang mở") + " · mã " + esc(r.code) + '</span></span>' +
      '<a class="go" href="/quiz/choi?c=' + encodeURIComponent(r.code) + '">Vào chơi</a>' +
      '<button class="x" type="button" aria-label="Ẩn thẻ quiz">×</button></div>';
    root.querySelector("button.x").onclick = function () { dismiss(r.code); host.style.display = "none"; };
  }

  function load() {
    if (document.hidden) return;
    var req = window.ecApi && window.ecApi.get
      ? window.ecApi.get("ecentric_workspace.dao_tao.controllers.api.live_card")
      : fetch(API, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; }).then(function (j) { return j && j.message; });
    req.then(function (env) { if (env && env.success) render((env.data || {}).rooms); }, function () { /* khach / mat mang: im lang */ });
  }

  function start() {
    if (!eligible()) return;
    load();
    timer = setInterval(load, POLL_MS);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) load(); });
    window.addEventListener("resize", function () { if (host) host.style.setProperty("--b", bottomOffset() + "px"); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
