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
  // Trang ngoai /approvals muon dung CHUNG combobox cua ERP thi tu khai bang mot phan tu
  // co `data-ec-formkit` (vd /ec-hr/phan-bo-cong-viec, 28/09). Opt-in chu khong mo rong bo
  // loc duong dan: cac trang /ec-hr khac va SO/PO van giu nguyen nhu cu.
  function optedIn() {
    return !!document.querySelector("[data-ec-formkit]");
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------------------------------------------------------------- combobox */
  // Dong bo chung cho moi combobox: phat hien trang gan sel.value bang code (24/11/2026). Khong dung
  // setInterval (giu tien trinh/tab thuc mai): doi chieu sau moi thao tac cua nguoi dung (click,
  // go, doi, focus) va moi lan form ve lai (scan) - gia tri doi bang code gan nhu luon nam ngay sau
  // mot thao tac nhu vay.
  var SYNC_SET = [], syncPending = null;
  function syncAll() {
    for (var i = SYNC_SET.length - 1; i >= 0; i--) {
      var s = SYNC_SET[i];
      if (!s.isConnected) { SYNC_SET.splice(i, 1); continue; }
      var o = s.options[s.selectedIndex];
      if ((s.selectedIndex + "|" + (o ? o.value : "")) !== s.__ecCbShown) s.__ecCbSync();
    }
  }
  function ensureSyncLoop() {
    if (ensureSyncLoop.done) return;
    ensureSyncLoop.done = true;
    ["click", "input", "change", "keyup", "focusin"].forEach(function (ev) {
      document.addEventListener(ev, function () { clearTimeout(syncPending); syncPending = setTimeout(syncAll, 30); }, true);
    });
  }
  function enhanceSelect(sel) {
    if (!sel || sel.__ecCb || sel.multiple || sel.disabled) return;
    // TRANG TU KHAI QUYEN SO HUU - cung mot luat da ap cho input[type=file] ben duoi.
    // Mot <select> nam trong o cua bang chat khong dung duoc combobox: bang tim kiem bung ra
    // de len hang ben duoi va bi vien bang cat mat (Booking Request, bang KOL/KOC, 15/09).
    // Trang biet ngu canh do, asset toan site thi khong - nen de trang noi.
    if (sel.hasAttribute("data-ec-no-formkit") || sel.closest("[data-ec-no-formkit]")) return;
    if (sel.closest(".ec-cb")) return;                 // trang đã có combobox của riêng nó
    // 24/11/2026 (Hoan: "mot so dropdown rat xau, dong bo voi dropdown cua toan ERP"): o NAM TRONG
    // O NHAP CUA FORM (.fld) thi moi <select> tu 2 lua chon deu dung combobox chung; danh sach ngan
    // (< 8) an o tim. Ngoai form (bo loc, bang) giu luat cu: >= 6 lua chon moi nang cap.
    var inForm = !!(sel.closest && sel.closest(".fld"));
    if (sel.options.length < (inForm ? 2 : 6)) return;
    sel.__ecCb = true;
    var compact = sel.options.length < 8;

    var wrap = document.createElement("div");
    wrap.className = "ec-cb" + (compact ? " ec-cb-compact" : "");
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
    var lastShown = null;
    function syncDisplay() {
      var o = sel.options[sel.selectedIndex];
      var label = o ? o.textContent.trim() : "";
      var empty = !o || !o.value;
      lastShown = sel.selectedIndex + "|" + (o ? o.value : "");
      sel.__ecCbShown = lastShown;
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
    // 01/10/2026 (Hoan): o nam sat day man hinh thi danh sach bi cat mat duoi.
    // Mo len TREN khi phia duoi khong du cho ma phia tren rong hon; va co chieu cao
    // theo cho trong that de khong bao gio tran khoi man hinh.
    function place() {
      panel.classList.remove("ec-cb-up");
      panel.style.maxHeight = "";
      var r = wrap.getBoundingClientRect();
      var vh = window.innerHeight || document.documentElement.clientHeight || 0;
      if (!vh || !r) return;
      var below = vh - r.bottom - 12, above = r.top - 12;
      var want = Math.min(panel.scrollHeight || 320, 320);
      var up = below < want && above > below;
      if (up) panel.classList.add("ec-cb-up");
      var room = up ? above : below;
      if (room > 120 && room < want) panel.style.maxHeight = Math.floor(room) + "px";
    }
    function open() {
      panel.hidden = false;
      search.value = "";
      render("");
      place();
      setTimeout(function () { search.focus({ preventScroll: true }); }, 0);
    }
    function close() { panel.hidden = true; }

    btn.onclick = function (e) { e.stopPropagation(); panel.hidden ? open() : close(); };
    search.oninput = function () { render(search.value); };
    search.onkeydown = function (e) { if (e.key === "Escape") { close(); btn.focus(); } };
    document.addEventListener("click", function (e) { if (!wrap.contains(e.target)) close(); });
    sel.addEventListener("change", syncDisplay);
    // Trang doi gia tri bang code (sel.value = x) khong phat 'change' -> o hien thi bi cu. Khong boc
    // setter (select la doi tuong dac biet co chi so, boc accessor khong chay o moi trinh duyet):
    // dang ky vao SYNC_SET, doi chieu sau moi thao tac / moi lan ve lai, chi ve lai khi doi.
    sel.__ecCbSync = syncDisplay;
    SYNC_SET.push(sel);
    ensureSyncLoop();
    // Trang thay danh sach lua chon (innerHTML option) ma khong ve lai ca form.
    try { new MutationObserver(syncDisplay).observe(sel, { childList: true, subtree: true, attributes: true, attributeFilter: ["selected"] }); } catch (e) { /* bo qua */ }
    // Trang focus vao o loi dau tien -> chuyen focus sang nut hien thi.
    sel.focus = function () { try { btn.focus(); } catch (e) { /* bo qua */ } };
    syncDisplay();
  }

  /* ---------------------------------------------------------------- dropzone */
  function enhanceFile(inp) {
    if (!inp || inp.__ecDz) return;
    // TRANG TU KHAI QUYEN SO HUU. Loc theo duong dan van khong du: nhieu trang cung nam
    // duoi /approvals va vai trang trong so do da co bo tai tep rieng, nen formkit boc them
    // mot lop nua -> hai vung keo-tha chong nhau (Payment Request, 2026-08-26).
    // `data-ec-no-formkit` cho trang tu chon khong tham gia ma khong phai sua file nay lan nua.
    // 24/11/2026 (Hoan: "mot so form chi la mot nut tai tep rat xau, khong dong bo"): bo guard
    // `data-upload`. Vung keo-tha thua 26/08 thuc ra boc #ecdUpload cua khu ky so (o do nay tu khai
    // data-ec-no-formkit) - KHONG phai o data-upload. O data-upload van do trang quan ly: dropzone chi
    // goi inp.click() / gan files roi phat 'change', handler uploadFile cua trang chay nhu cu.
    if (inp.hasAttribute("data-ec-no-formkit") || inp.closest("[data-ec-no-formkit]")) return;
    // O tai tep bi AN la o do trang tu dieu khien bang nut rieng (vd "+ Tai tai lieu").
    // Boc dropzone len no se tao mot vung keo-tha thu hai nam canh nut do.
    if ((inp.style && inp.style.display === "none") || inp.hidden) return;
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
    if (!onApprovalPage() && !optedIn()) return;
    document.querySelectorAll("select").forEach(enhanceSelect);
    document.querySelectorAll('input[type="file"]').forEach(enhanceFile);
    syncAll();
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
