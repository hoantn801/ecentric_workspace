/* ec_formkit — nâng cấp form Approval Center ở tầng runtime.
 *
 * Vì sao làm ở asset thay vì sửa 26 trang HTML: các trang form được render bằng chuỗi JS và
 * vẽ lại liên tục (renderCreate). Sửa markup từng trang vừa lặp lại 26 lần vừa phải resync +
 * bump drift-lock mỗi lần đổi giao diện. Asset này quan sát DOM và nâng cấp mọi <select> /
 * ô chọn tệp mới xuất hiện, nên form giữ nguyên logic còn trải nghiệm thì đồng bộ với SO/PO.
 *
 * Nguyên tắc: KHÔNG thay đổi dữ liệu. Combobox chỉ ghi vào chính <select> gốc rồi phát
 * 'input' + 'change' để handler sẵn có của trang xử lý; vùng kéo-thả chỉ gán files vào
 * <input type=file> gốc rồi phát 'change'. Gỡ asset đi là form trở lại như cũ.
 */
(function () {
  "use strict";
  if (window.__ecFormkitInstalled) return;
  window.__ecFormkitInstalled = true;

  // CHỈ chạy trên các trang form của Approval Center.
  // Bộ lọc cũ ("có phần tử #ec-*-root") quá lỏng: các trang GBS SO/PO và All Tickets cũng có
  // root dạng đó VÀ đã tự có combobox + vùng kéo-thả riêng, nên asset này nâng cấp chồng lên,
  // sinh ra hai ô chọn / hai vùng kéo-thả. Khoá theo đường dẫn là ranh giới rõ ràng nhất.
  function onApprovalPage() {
    return /^\/approvals(\/|$)/.test(window.location.pathname || "");
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------------------------------------------------------------- combobox */
  function enhanceSelect(sel) {
    if (!sel || sel.__ecCb || sel.multiple || sel.disabled) return;
    if (sel.closest(".ec-cb")) return;                 // trang đã có combobox của riêng nó
    if (sel.options.length < 6) return;            // danh sách ngắn: <select> gốc dễ dùng hơn
    sel.__ecCb = true;

    var wrap = document.createElement("div");
    wrap.className = "ec-cb";
    sel.parentNode.insertBefore(wrap, sel);
    wrap.appendChild(sel);
    sel.style.display = "none";

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ec-cb-display";
    var arrow = document.createElement("span");
    arrow.className = "ec-cb-arrow";
    arrow.textContent = "▼";
    var panel = document.createElement("div");
    panel.className = "ec-cb-panel";
    panel.hidden = true;
    panel.innerHTML =
      '<div class="ec-cb-search-wrap"><input class="ec-cb-search" placeholder="Tìm..." /></div>' +
      '<div class="ec-cb-count"></div><div class="ec-cb-list"></div>';
    wrap.appendChild(btn);
    wrap.appendChild(arrow);
    wrap.appendChild(panel);

    var search = panel.querySelector(".ec-cb-search");
    var count = panel.querySelector(".ec-cb-count");
    var list = panel.querySelector(".ec-cb-list");

    function opts() {
      return Array.prototype.slice.call(sel.options);
    }
    function syncDisplay() {
      var o = sel.options[sel.selectedIndex];
      var label = o ? o.textContent.trim() : "";
      var empty = !o || !o.value;
      btn.textContent = empty ? (label || "— Chọn —") : label;
      btn.classList.toggle("ec-cb-placeholder", empty);
    }
    function render(q) {
      q = (q || "").trim().toLowerCase();
      var rows = opts().filter(function (o) {
        return !q || o.textContent.toLowerCase().indexOf(q) >= 0;
      });
      count.textContent = rows.length + " kết quả";
      list.innerHTML = rows.length
        ? rows.map(function (o) {
            return '<div class="ec-cb-option' + (o.selected ? " ec-cb-selected" : "") +
                   '" data-val="' + esc(o.value) + '">' + esc(o.textContent.trim()) + "</div>";
          }).join("")
        : '<div class="ec-cb-empty">Không tìm thấy</div>';
      Array.prototype.forEach.call(list.querySelectorAll(".ec-cb-option"), function (el) {
        el.onclick = function () {
          sel.value = el.getAttribute("data-val");
          // phát cả hai để mọi handler của trang (input/change) đều nhận
          sel.dispatchEvent(new Event("input", { bubbles: true }));
          sel.dispatchEvent(new Event("change", { bubbles: true }));
          close();
          syncDisplay();
        };
      });
    }
    function open() {
      panel.hidden = false;
      search.value = "";
      render("");
      setTimeout(function () { search.focus(); }, 0);
    }
    function close() { panel.hidden = true; }

    btn.onclick = function (e) { e.stopPropagation(); panel.hidden ? open() : close(); };
    search.oninput = function () { render(search.value); };
    search.onkeydown = function (e) { if (e.key === "Escape") { close(); btn.focus(); } };
    document.addEventListener("click", function (e) { if (!wrap.contains(e.target)) close(); });
    sel.addEventListener("change", syncDisplay);
    syncDisplay();
  }

  /* ---------------------------------------------------------------- dropzone */
  function enhanceFile(inp) {
    if (!inp || inp.__ecDz) return;
    // trang đã có vùng kéo-thả riêng (SO/PO...) -> không chồng thêm
    if (inp.closest(".ec-dz") || (inp.parentNode && inp.parentNode.querySelector(".ec-dz"))) return;
    var host = inp.parentNode;
    if (host && /drop|dz|upload-zone/i.test(host.className || "")) return;
    inp.__ecDz = true;

    var dz = document.createElement("div");
    dz.className = "ec-dz";
    dz.innerHTML =
      '<div class="ec-dz-ic"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg></div>' +
      '<div class="ec-dz-main">Kéo thả tệp vào đây</div>' +
      '<div class="ec-dz-sub">hoặc <span class="ec-dz-link">bấm để chọn tệp</span></div>' +
      '<div class="ec-dz-hint">PDF, Word, Excel, PowerPoint, hình ảnh' +
      (inp.multiple ? " — chọn được nhiều tệp" : "") + " — tối đa ~25MB/tệp</div>";
    inp.parentNode.insertBefore(dz, inp);
    inp.style.display = "none";

    dz.addEventListener("click", function () { inp.click(); });
    ["dragenter", "dragover"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) { e.preventDefault(); e.stopPropagation(); dz.classList.add("ec-dz-over"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) { e.preventDefault(); e.stopPropagation(); dz.classList.remove("ec-dz-over"); });
    });
    dz.addEventListener("drop", function (e) {
      var files = e.dataTransfer && e.dataTransfer.files;
      if (!files || !files.length) return;
      try {
        var dt = new DataTransfer();
        Array.prototype.slice.call(files, 0, inp.multiple ? files.length : 1)
          .forEach(function (f) { dt.items.add(f); });
        inp.files = dt.files;
        inp.dispatchEvent(new Event("change", { bubbles: true }));   // để uploadFile của trang chạy
      } catch (err) { /* trình duyệt không cho gán files -> bấm chọn vẫn dùng được */ }
    });
  }

  /* ------------------------------------------------------------------- quét */
  function scan() {
    if (!onApprovalPage()) return;
    document.querySelectorAll("select").forEach(enhanceSelect);
    document.querySelectorAll('input[type="file"]').forEach(enhanceFile);
  }

  function start() {
    scan();
    // Form vẽ lại liên tục (renderCreate) nên phải nâng cấp lại phần tử mới xuất hiện.
    var pending = null;
    new MutationObserver(function () {
      clearTimeout(pending);
      pending = setTimeout(scan, 60);
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
