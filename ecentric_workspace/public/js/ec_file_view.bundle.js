// Copyright (c) 2026, eCentric and contributors
//
// Xem online tep Word (.docx) dinh kem - dung chung cho MOI trang phe duyet + popup hub
// /approvals/all-requests + sheet "Cho toi duyet" (26/11/2026, Ke toan mo EC-CTR-2026-00130:
// bam link .docx thi trinh duyet TAI ve, khong xem duoc nhu PDF).
//
// GIAO KEO VOI TRANG - KHONG sua trang nao: moi noi ve danh sach dinh kem deu la
// <a href="/private/files/...docx"> (renderAttachments cua 31 form, popup hub .ec-apl-file,
// ec_cho_duyet .cd-a). Mot listener click tren document, giai doan CAPTURE (chay truoc moi
// handler cua trang), bat link cung origin trỏ /files/... hoac /private/files/... duoi .docx
// -> chan tai, mo hop thoai "Xem tep". De trinh duyet xu ly binh thuong khi: Ctrl/Cmd/Shift/Alt
// hoac nut chuot khac nut trai, link (hoac to tien) co data-no-preview, link co thuoc tinh
// download, link khac origin (SharePoint "Mo online" giu nguyen). PDF / anh: khong dung toi.
//
// AN TOAN (cung cach trinh xem truoc hop dong mau o contract_review/ui/main_section.html, KOL.pvFrameHTML):
//   * Tep lay bang fetch cung origin, credentials same-origin = DUNG session nguoi dang xem;
//     quyen tep rieng tu do Frappe kiem (403 -> "Ban khong co quyen xem tep nay"). Khong goi API
//     nao khac, khong luu gi.
//   * docx-preview chay trong <iframe sandbox="allow-scripts"> KHONG allow-same-origin + CSP nonce:
//     tep .docx do nguoi khac tai len co the chua the HTML / link javascript; trong khung nguon goc
//     rong, ma do khong cham duoc cookie, trang hay API cua ERP. Trang chi gui byte qua postMessage.
//   * Ten tep luon escape truoc khi vao HTML.
// Thu vien vendored (khong CDN): public/vendor/docx_preview/{jszip,docx-preview}.min.js.
(function () {
  "use strict";
  if (window.EcFileView) return;

  var PV_BASE = "/assets/ecentric_workspace/vendor/docx_preview/";
  var MAX_BYTES = 20 * 1024 * 1024;   // lon hon -> goi y tai ve (ve trong trinh duyet se rat cham)
  var RENDER_TIMEOUT_MS = 20000;
  var MSG_T = "ecfv";
  var cur = null;                       // hop thoai dang mo (chi mot)

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function safeDecode(s) { try { return decodeURIComponent(s); } catch (e) { return s; } }
  function mb(b) { return (Math.round((Number(b) || 0) / 104857.6) / 10).toString().replace(".", ",") + " MB"; }

  // Link -> {url, name} neu la tep .docx cua chinh ERP; null neu khong (de trinh duyet tu xu ly).
  function docxInfo(a) {
    if (!a || !a.getAttribute) return null;
    var raw = a.getAttribute("href");
    if (!raw || /^\s*(javascript|data|blob):/i.test(raw)) return null;
    var u;
    try { u = new URL(raw, window.location.href); } catch (e) { return null; }
    if (u.origin !== window.location.origin) return null;
    var path = safeDecode(u.pathname);
    if (!/^\/(private\/)?files\//.test(path)) return null;
    if (!/\.docx$/i.test(path)) return null;
    return { url: u.pathname + u.search, href: raw, name: path.split("/").pop() || "tep.docx" };
  }

  function findAnchor(e) {
    var path = typeof e.composedPath === "function" ? e.composedPath() : [];
    for (var i = 0; i < path.length; i++) {
      var n = path[i];
      if (n && n.tagName === "A" && n.hasAttribute && n.hasAttribute("href")) return n;
    }
    var t = e.target;
    return t && t.closest ? t.closest("a[href]") : null;
  }

  function onDocClick(e) {
    if (e.defaultPrevented || e.button !== 0) return;
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    var a = findAnchor(e);
    if (!a || a.hasAttribute("download")) return;
    if (a.closest && a.closest("[data-no-preview]")) return;
    var f = docxInfo(a);
    if (!f) return;
    e.preventDefault();
    e.stopPropagation();   // khong cho click lot xuong handler cua dong / the (vd mo chi tiet)
    open(f.url, f.name, a, f.href);
  }

  // HTML cua khung xem. Cung khuon voi KOL.pvFrameHTML (contract_review): CSP chi cho script tu
  // thu muc trinh xem + doan co nonce; the HTML trong tep (onerror=...) bi chan, khong tai gi ra ngoai.
  function frameHTML(base) {
    var n = String(Math.random()).slice(2) + String(Date.now());
    return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
      + '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'nonce-' + n + '\' ' + base + '; style-src \'unsafe-inline\'; img-src data: blob:; font-src data:">'
      + '<style>html,body{margin:0;background:#eef0f3}.docx-wrapper{background:#eef0f3!important;padding:16px!important}'
      + '@media (max-width:640px){.docx-wrapper{align-items:flex-start!important;padding:8px!important}}</style>'
      + '<script src="' + base + 'jszip.min.js"><\/script><script src="' + base + 'docx-preview.min.js"><\/script></head><body><div id="d"></div><script nonce="' + n + '">'
      + '(function(){var P=parent;function say(m){P.postMessage(m,"*");}'
      + 'function fit(){var w=document.querySelector(".docx-wrapper"),g=document.querySelector("section.docx");if(!w||!g)return;w.style.zoom="";'
      + 'var s=Math.min(1,(document.documentElement.clientWidth-8)/(g.offsetWidth+32));if(s>0&&s<1)w.style.zoom=String(Math.round(s*100)/100);}'
      + 'window.addEventListener("resize",fit);var got=false;'
      + 'document.addEventListener("keydown",function(k){if(k.key==="Escape"||k.key==="Esc")say({t:"' + MSG_T + '",esc:true});});'
      + 'window.addEventListener("message",function(e){if(e.source!==P||!e.data||e.data.t!=="' + MSG_T + '"||got)return;got=true;'
      + 'if(!window.docx||!window.docx.renderAsync){say({t:"' + MSG_T + '",ok:false,load:true});return;}'
      + 'window.docx.renderAsync(e.data.b,document.getElementById("d"),null,{className:"docx",inWrapper:true,breakPages:true,ignoreLastRenderedPageBreak:true,useBase64URL:true})'
      + '.then(function(){fit();say({t:"' + MSG_T + '",ok:true});},function(err){say({t:"' + MSG_T + '",ok:false,msg:String(err&&err.message||err)});});});'
      + 'say({t:"' + MSG_T + '",ready:true});})();<\/script></body></html>';
  }

  // Byte dau tep: .docx la goi ZIP ("PK\3\4"); .doc cu (Word 97-2003) la OLE (D0 CF 11 E0).
  function sniff(u8) {
    if (u8.length >= 4 && u8[0] === 0x50 && u8[1] === 0x4B && u8[2] === 0x03 && u8[3] === 0x04) return "zip";
    if (u8.length >= 4 && u8[0] === 0xD0 && u8[1] === 0xCF && u8[2] === 0x11 && u8[3] === 0xE0) return "ole";
    return "other";
  }

  function focusables(root) {
    return Array.prototype.slice.call(root.querySelectorAll('a[href],button:not([disabled]),iframe,[tabindex]:not([tabindex="-1"])'));
  }

  function close() {
    var c = cur;
    if (!c) return;
    cur = null;
    window.removeEventListener("message", c.onMsg);
    window.removeEventListener("keydown", c.onKey, true);
    clearTimeout(c.timer);
    try { if (c.ctrl) c.ctrl.abort(); } catch (e) { /* trinh duyet cu: bo qua */ }
    if (c.ov.parentNode) c.ov.parentNode.removeChild(c.ov);
    var back = c.opener && c.opener.isConnected !== false ? c.opener : c.prevFocus;
    if (back && back.focus) { try { back.focus(); } catch (e) { /* phan tu da mat */ } }
  }

  // url: duong dan cung origin de fetch; dlHref: link goc cho nut "Tai ve" (mac dinh = url).
  async function open(url, name, opener, dlHref) {
    if (cur) return;                    // bam hai lan: khong mo hai hop thoai
    name = name || safeDecode(String(url).split("?")[0].split("/").pop()) || "tep.docx";
    var ov = document.createElement("div");
    ov.className = "ec-fv-ov";
    ov.innerHTML = '<div class="ec-fv-modal" role="dialog" aria-modal="true" aria-labelledby="ec-fv-t">'
      + '<div class="ec-fv-h"><div class="ec-fv-ttl"><div class="ec-fv-k">Xem tệp</div>'
      + '<div class="ec-fv-name" id="ec-fv-t" title="' + esc(name) + '">' + esc(name) + '</div></div>'
      + '<div class="ec-fv-act"><a class="ec-fv-btn" data-fv-dl data-no-preview href="' + esc(dlHref || url) + '" download="' + esc(name) + '">Tải về</a>'
      + '<button type="button" class="ec-fv-btn ec-fv-primary" data-fv-close>Đóng</button></div></div>'
      + '<div class="ec-fv-b" aria-busy="true"><div class="ec-fv-st" role="status"><span class="ec-fv-spin" aria-hidden="true"></span>Đang tải tệp…</div></div>'
      + '</div>';
    var c = { ov: ov, opener: opener || null, prevFocus: document.activeElement, frame: null, timer: null, ctrl: null, bytes: null, sent: false };
    cur = c;
    var box = ov.querySelector(".ec-fv-b");
    var modal = ov.querySelector(".ec-fv-modal");

    function fail(msg) {
      if (cur !== c) return;
      clearTimeout(c.timer);
      box.setAttribute("aria-busy", "false");
      box.innerHTML = '<div class="ec-fv-err" role="alert"><b>' + esc(msg) + '</b>'
        + '<div>Bấm <b>Tải về</b> để mở bằng Word trên máy.</div></div>';
    }
    c.onMsg = function (e) {
      if (cur !== c || !c.frame || e.source !== c.frame.contentWindow || !e.data || e.data.t !== MSG_T) return;
      if (e.data.esc) { close(); return; }   // Esc khi focus dang o trong khung xem
      if (e.data.ready) {
        if (c.bytes && !c.sent) { c.sent = true; c.frame.contentWindow.postMessage({ t: MSG_T, b: c.bytes }, "*"); }
        return;
      }
      clearTimeout(c.timer);
      box.setAttribute("aria-busy", "false");
      if (e.data.ok) {
        var st = box.querySelector(".ec-fv-st"); if (st && st.parentNode) st.parentNode.removeChild(st);
        c.frame.style.visibility = "visible";
        return;
      }
      if (window.console && console.error) console.error("ec_file_view", e.data.msg || "viewer load");
      fail(e.data.load ? "Không tải được trình xem. Tải lại trang (Ctrl+Shift+R) rồi thử lại."
        : "Trình xem không đọc được tệp này (tệp hỏng hoặc định dạng Word cũ).");
    };
    c.onKey = function (e) {
      if (cur !== c) return;
      if (e.key === "Escape" || e.key === "Esc") {
        e.preventDefault(); e.stopImmediatePropagation(); close(); return;
      }
      // mui ten / phim khac khong lot xuong trang ben duoi (popup hub dung mui ten de chuyen phieu)
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.stopImmediatePropagation(); return; }
      if (e.key === "Tab") {             // giu focus trong hop thoai
        var f = focusables(modal); if (!f.length) return;
        var first = f[0], last = f[f.length - 1], a = document.activeElement;
        if (e.shiftKey && (a === first || !modal.contains(a))) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && (a === last || !modal.contains(a))) { e.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener("message", c.onMsg);
    window.addEventListener("keydown", c.onKey, true);
    ov.addEventListener("click", function (e) { if (e.target === ov) close(); });
    ov.querySelector("[data-fv-close]").addEventListener("click", close);
    document.body.appendChild(ov);
    try { ov.querySelector("[data-fv-close]").focus(); } catch (e) { /* bo qua */ }

    var res, buf;
    try {
      c.ctrl = typeof AbortController === "function" ? new AbortController() : null;
      res = await fetch(url, { credentials: "same-origin", signal: c.ctrl ? c.ctrl.signal : undefined });
    } catch (e) {
      if (cur === c) fail("Không tải được tệp. Kiểm tra kết nối mạng rồi thử lại.");
      return;
    }
    if (cur !== c) return;
    if (res.status === 401 || res.status === 403) { fail("Bạn không có quyền xem tệp này."); return; }
    if (res.status === 404) { fail("Không tìm thấy tệp (có thể đã bị xoá hoặc đổi tên)."); return; }
    if (!res.ok) { fail("Không tải được tệp (mã lỗi " + res.status + ")."); return; }
    var len = Number(res.headers && res.headers.get ? res.headers.get("content-length") : 0) || 0;
    if (len > MAX_BYTES) {
      try { if (c.ctrl) c.ctrl.abort(); } catch (e) { /* bo qua */ }
      fail("Tệp lớn (" + mb(len) + ", quá " + mb(MAX_BYTES) + ") nên không xem trực tiếp được.");
      return;
    }
    try { buf = await res.arrayBuffer(); } catch (e) {
      if (cur === c) fail("Không tải được tệp. Kiểm tra kết nối mạng rồi thử lại.");
      return;
    }
    if (cur !== c) return;
    if (buf.byteLength > MAX_BYTES) { fail("Tệp lớn (" + mb(buf.byteLength) + ", quá " + mb(MAX_BYTES) + ") nên không xem trực tiếp được."); return; }
    var u8 = new Uint8Array(buf);
    var kind = sniff(u8);
    if (kind === "ole") { fail("Tệp là định dạng Word cũ (.doc) nên trình xem không đọc được."); return; }
    if (kind !== "zip") { fail("Tệp không phải Word .docx hợp lệ (có thể đã hỏng)."); return; }

    c.bytes = u8;
    box.querySelector(".ec-fv-st").lastChild.nodeValue = "Đang vẽ trang…";
    var fr = document.createElement("iframe");
    fr.className = "ec-fv-frame";
    fr.title = "Nội dung tệp " + name;
    fr.setAttribute("sandbox", "allow-scripts");
    fr.setAttribute("referrerpolicy", "no-referrer");
    fr.style.visibility = "hidden";
    fr.srcdoc = frameHTML(window.location.origin + PV_BASE);
    c.frame = fr;
    box.appendChild(fr);
    c.timer = setTimeout(function () {
      if (cur === c && box.getAttribute("aria-busy") === "true") fail("Trình xem chạy quá lâu.");
    }, RENDER_TIMEOUT_MS);
  }

  document.addEventListener("click", onDocClick, true);

  window.EcFileView = { open: open, close: close, docxInfo: docxInfo, frameHTML: frameHTML, MAX_BYTES: MAX_BYTES, PV_BASE: PV_BASE };
})();
