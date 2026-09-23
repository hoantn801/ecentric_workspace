/* ec_aifill — panel "AI điền hộ" cho các form Approval Center.
 *
 * VÌ SAO LÀM Ở ASSET CHỨ KHÔNG SỬA main_section.html — cùng lý do với `ec_formkit`: các trang
 * form được render bằng chuỗi JS và vẽ lại liên tục (`renderCreate`). Sửa markup từng trang
 * vừa lặp lại 28 lần, vừa kéo theo nghi thức 3 bước (HTML + BASELINE_SHA256 +
 * resync_manifest.json) mỗi lần chỉnh giao diện. Ở asset thì giai đoạn 1 KHÔNG đụng một dòng
 * HTML nào.
 *
 * NGUYÊN TẮC: KHÔNG chạm vào state của trang. Asset ghi vào chính ô `[data-model]` rồi phát
 * `input` + `change`, để `onModelInput` sẵn có của trang xử lý tiếp — kể cả mọi phản ứng dây
 * chuyền (payment_date → tự điền ec_ky_chi_phi, ec_loai_chi_phi → vẽ lại cả form). Gỡ asset
 * đi là form trở lại y như cũ.
 *
 * Kill switch: server trả `enabled:false` (site_config `ec_ai_formfill_disabled`, hoặc người
 * dùng không có role pilot) → asset không vẽ gì.
 */
(function () {
  "use strict";
  if (window.__ecAifillInstalled) return;
  window.__ecAifillInstalled = true;

  /* Giai đoạn 1: chỉ payment_request. Giai đoạn 4 nối route vào đây.
   * Khóa theo đường dẫn ĐẦY ĐỦ, không theo tiền tố: bài học 25/08 + 26/08 của ec_formkit —
   * `/approvals/*` khớp cả những trang đã tự quản lý widget của chúng. */
  var ROUTES = {
    "/approvals/payment-request": "PAYMENT_REQUEST"
  };

  /* Hai ô đắt nhất khi sai: hiện đoạn văn bản gốc ngay dưới ô để việc xem lại chuyển từ
   * PHÁN ĐOÁN sang ĐỐI CHIẾU HAI CHUỖI. */
  var QUOTE_FIELDS = ["payment_amount", "bank_account_number"];

  /* G2 — tệp cho AI đọc. Panel có Ô THẢ TỆP CỦA RIÊNG NÓ.
   *
   * Bản đầu (17/09) đi bòn danh sách tệp từ DOM của trang (`#payr-att-name .ec-file a`) —
   * SAI, vì hai lý do:
   *   1. Mục "TÀI LIỆU & KÝ SỐ" của form chỉ mở SAU KHI lưu nháp, nên lúc người ta cần AI
   *      điền thì chưa có chỗ nào để thả tệp cả.
   *   2. Mục đó phục vụ KÝ SỐ — tệp phải có phiếu rồi mới gắn được. Còn AI thì cần tệp
   *      TRƯỚC để có cái mà đọc. Hai nhu cầu ngược chiều nhau, không dùng chung một ô được.
   *
   * Nên: tệp thả vào đây là ĐẦU VÀO CỦA AI, cùng hạng với đoạn văn bản dán ở trên — không
   * phải chứng từ của phiếu. Chứng từ vẫn đính kèm ở bước "Tiếp tục: Thêm chứng từ" như cũ.
   * Nói thẳng điều đó trên giao diện, đừng để người dùng tự đoán. */
  var UPLOAD_URL = "/api/method/upload_file";
  var MAX_BYTES = 10 * 1024 * 1024;

  /* Ô nào làm trang vẽ lại cả form → phải ghi TRƯỚC, nếu không lần vẽ lại xoá sạch những ô
   * điền sau nó. Danh sách này là dự phòng; cơ chế thật là truy vấn lại DOM trước mỗi lần ghi
   * và ghi mỗi ô một animation frame. */
  var RERENDER_FIRST = ["ec_loai_chi_phi", "has_purchase_request", "payment_mode",
                        "ec_brand_moi", "funding_source_doctype"];

  var code = ROUTES[(window.location.pathname || "").replace(/\/+$/, "")] || null;

  /* ---------------------------------------------------------------- tiện ích */
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function call(method, args) {
    return frappe.call({
      method: "ecentric_workspace.approval_center.api.ai_formfill." + method,
      args: args, type: "POST"
    }).then(function (r) { return (r || {}).message || {}; });
  }

  /* Thứ tự ghi: ô gây vẽ lại trước, phần còn lại sau. PURE — test được. */
  function writeOrder(fieldnames) {
    var first = [], rest = [];
    fieldnames.forEach(function (f) {
      (RERENDER_FIRST.indexOf(f) >= 0 ? first : rest).push(f);
    });
    return first.concat(rest);
  }

  /* Sự kiện này có phải người gõ thật không?
   * `e.isTrusted` là thứ DUY NHẤT phân biệt phím người gõ với sự kiện tổng hợp mà chính asset
   * vừa phát ra. Không có nó thì dấu "AI điền" tự xoá ngay tại lúc điền. PURE — test được. */
  function isUserEdit(ev) {
    return !!(ev && ev.isTrusted);
  }

  /* ------------------------------------------------------------------ state */
  var S = { filled: {}, sources: {}, before: {}, busy: false, remaining: null, cap: null,
            maxChars: 8000, maxFiles: 5, files: [], fileExts: [], uploading: false, ran: false,
            _filesHtml: null, panel: null,
            maxDrafts: 10, hasFlags: false, ns: "" };

  /* Tệp có nhận được không, và nếu không thì VÌ SAO. PURE.
   * Chặn ở client cho người dùng biết ngay, nhưng server vẫn chặn lại lần nữa — cổng ở
   * client là để nói cho nhanh, không phải để tin. */
  function refuseReason(file, danhSach, maxFiles, exts) {
    if (!file) return "tệp rỗng";
    if (!file.size) return "tệp rỗng";
    if (file.size > MAX_BYTES) return "tệp quá lớn (tối đa 10MB)";
    var ext = (file.name || "").split(".").pop().toLowerCase();
    if ((file.name || "").indexOf(".") < 0) return "không rõ loại tệp";
    if (exts && exts.length && exts.indexOf(ext) < 0) {
      return (["doc", "docx", "xls", "xlsx", "ppt", "pptx"].indexOf(ext) >= 0)
        ? "tệp Office — hãy xuất ra PDF rồi thả lại"
        : "AI không đọc được loại tệp này";
    }
    if ((danhSach || []).length >= maxFiles) return "một lượt tối đa " + maxFiles + " tệp";
    for (var i = 0; i < (danhSach || []).length; i++) {
      if (danhSach[i].name === file.name && danhSach[i].size === file.size) return "đã có rồi";
    }
    return null;
  }

  /* Tải MỘT tệp lên kho tệp riêng tư của Frappe. Không gửi doctype/docname: lúc này phiếu
   * chưa tồn tại, và `upload_file` kiểm quyền role trên DocType đó — bài học của chính
   * trang này (xem chú thích trong main_section.html). */
  function uploadOne(file) {
    var fd = new FormData();
    fd.append("file", file);
    fd.append("is_private", "1");
    return fetch(UPLOAD_URL, {
      method: "POST",
      headers: { "X-Frappe-CSRF-Token": (window.frappe && frappe.csrf_token) || "" },
      body: fd
    }).then(function (r) {
      if (r.status === 413) throw new Error("tệp quá lớn so với giới hạn máy chủ");
      return r.json();
    }).then(function (j) {
      var m = j && j.message, url = m && m.file_url;
      if (!url) throw new Error("máy chủ không trả về đường dẫn tệp");
      return { url: url, name: (m && m.file_name) || file.name, size: file.size };
    });
  }

  function fieldBox(name) {
    return document.querySelector('#ec-aifill-host ~ * [data-fld="' + name + '"]')
        || document.querySelector('[data-fld="' + name + '"]');
  }
  function control(name) {
    return document.querySelector('[data-model="' + name + '"]');
  }

  /* --------------------------------------------------------------- ghi & xoá */
  function setValue(el, value) {
    if (!el) return false;
    if (el.type === "checkbox") { el.checked = !!value; }
    else if (el.tagName === "SELECT") {
      var hit = Array.prototype.filter.call(el.options, function (o) {
        return String(o.value) === String(value) || o.textContent.trim() === String(value);
      })[0];
      if (!hit) return false;              // không có option khớp → KHÔNG ghi bừa
      el.value = hit.value;
    } else { el.value = value == null ? "" : String(value); }
    // Phát cho handler sẵn có của TRANG chạy — asset không tự cập nhật state của trang.
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function fillSequential(fields, done) {
    var names = writeOrder(Object.keys(fields)), i = 0;
    (function step() {
      if (i >= names.length) { paint(); return done && done(); }
      var name = names[i++];
      var el = control(name);             // TRUY VẤN LẠI mỗi vòng: trang có thể vừa vẽ lại
      if (el) {
        S.before[name] = (el.type === "checkbox") ? el.checked : el.value;
        if (setValue(el, fields[name])) S.filled[name] = true;
      }
      paint();
      window.requestAnimationFrame(step);
    })();
  }

  function settle(name) {
    delete S.filled[name];
    delete S.sources[name];
    paint();
  }

  function undoAll() {
    Object.keys(S.filled).forEach(function (name) {
      var el = control(name);
      if (el && Object.prototype.hasOwnProperty.call(S.before, name)) setValue(el, S.before[name]);
    });
    S.filled = {}; S.sources = {}; S.before = {}; S.ran = false;
    paint(); render();
  }

  /* ------------------------------------------------------- dấu + trích dẫn */
  var BADGE_SVG =
    '<svg viewBox="0 0 64 64" aria-hidden="true">' +
    '<rect x="7" y="7" width="50" height="50" rx="17" fill="#F7C948" stroke="#E0AE22" stroke-width="3"/>' +
    '<circle cx="24" cy="31" r="5.6" fill="#1E2A5A"/><circle cx="40" cy="31" r="5.6" fill="#1E2A5A"/></svg>';

  /** Vẽ lại dấu sau MỖI lần trang đổi DOM. Dấu phải suy ra từ state của asset, không bám
   *  vào phần tử — `renderCreate` thay sạch innerHTML nên mọi thứ gắn vào DOM đều bay. */
  /* Ô nào BẮT BUỘC mà còn trống. Đọc dấu `*` mà chính trang đã vẽ (`label > .req`) —
   * không đoán theo danh sách cứng, vì danh sách cứng lệch khỏi form là lệch âm thầm.
   * Chỉ tính ô ĐANG HIỆN: `request_attachment` là ô bắt buộc nhưng bị khối ký số ẩn đi,
   * tô đỏ một ô không nhìn thấy là chỉ vào hư không. */
  function missingRequired() {
    var out = [];
    document.querySelectorAll("[data-fld]").forEach(function (box) {
      var lab = box.querySelector("label");
      if (!lab || !lab.querySelector(".req")) return;
      /* Hỏi KHỐI có đang hiện không, ĐỪNG hỏi ô điều khiển.
       *
       * Bản đầu hỏi `el.offsetParent` của chính ô — và trượt đúng những ô hay bị bỏ sót
       * nhất: `ec_formkit` giấu <select> đi (`display:none`) để dựng combobox, `ec_datepicker`
       * clip <input type=date> lại để dựng nút của nó. Cả hai ô ĐỀU đang hiện trên màn hình,
       * chỉ là thứ hiện ra không phải cái ta vừa hỏi. Khối `[data-fld]` mới là thứ biến mất
       * khi trang thật sự ẩn một ô đi (`request_attachment` lúc khối ký số đóng) — nên nó
       * mới là thứ đáng hỏi. */
      if (!box.offsetParent) return;
      /* `[data-model]` là hợp đồng mà trang tự khai: ô nào giữ giá trị thật thì có nó.
       * "Ô đầu tiên trong khối" là phỏng đoán, và phỏng đoán đó vỡ ngay khi một asset khác
       * chèn thêm một <input> phụ trợ vào trước. */
      var el = box.querySelector("[data-model]") ||
               box.querySelector("input, select, textarea");
      if (!el) return;
      if (el.type === "checkbox") { if (!el.checked) out.push(box); return; }
      if (!String(el.value || "").trim()) out.push(box);
    });
    return out;
  }

  function paint() {
    document.querySelectorAll(".ec-aifill-badge, .ec-aifill-src").forEach(function (n) {
      if (!S.filled[n.getAttribute("data-for")]) n.remove();
    });

    /* BẢN ĐỒ HOÀN THÀNH, không phải báo cáo lỗi.
     *
     * Vàng cho ô AI điền: vàng là màu NHẬN DIỆN của trợ lý (cùng con mặt vàng trên dấu),
     * không phải màu ngữ nghĩa — nên nó không phạm A58. Xanh thì phạm: xanh ở hệ này nghĩa
     * là "đã duyệt", tô xanh một ô chưa ai duyệt là dạy sai từ vựng trạng thái.
     *
     * Đỏ nhạt cho ô bắt buộc còn trống: đỏ ở hệ này CÓ phần dành cho validation
     * (DESIGN.md §Colors: "Từ chối, lỗi validation, dấu *"). Nhưng chỉ bật SAU KHI AI chạy
     * một lượt — một form trắng chưa ai đụng vào mà đỏ lòm là mắng người dùng trước khi họ
     * làm gì. Và dùng WASH chứ không dùng viền đỏ: viền đỏ là ngôn ngữ riêng của validation
     * sau khi bấm Gửi (`.fld.invalid`), mượn nó ở đây là hai thứ khác nhau trông giống nhau.
     */
    document.querySelectorAll(".ec-aifill-lit, .ec-aifill-gap").forEach(function (n) {
      n.classList.remove("ec-aifill-lit", "ec-aifill-gap");
    });
    Object.keys(S.filled).forEach(function (name) {
      var box = fieldBox(name);
      if (box) box.classList.add("ec-aifill-lit");
    });
    if (S.ran) {
      missingRequired().forEach(function (box) {
        if (!box.classList.contains("ec-aifill-lit")) box.classList.add("ec-aifill-gap");
      });
    }

    Object.keys(S.filled).forEach(function (name) {
      var box = fieldBox(name);
      if (!box) return;
      var label = box.querySelector("label");
      if (label && !label.querySelector('.ec-aifill-badge[data-for="' + name + '"]')) {
        var b = document.createElement("span");
        b.className = "ec-aifill-badge";
        b.setAttribute("data-for", name);
        b.innerHTML = BADGE_SVG + "AI điền";
        label.appendChild(b);
      }
      var quote = S.sources[name];
      if (quote && !box.querySelector('.ec-aifill-src[data-for="' + name + '"]')) {
        var d = document.createElement("div");
        d.className = "ec-aifill-src";
        d.setAttribute("data-for", name);
        d.innerHTML = '<span class="ec-aifill-src-lbl">Lấy từ</span>' + esc(quote);
        box.appendChild(d);
      }
    });
  }

  /* --------------------------------------------------------------- giao diện */
  var MARK =
    '<svg class="ec-aifill-mark" viewBox="0 0 64 64" aria-hidden="true">' +
    '<path d="M32 3.4v3" stroke="#E0AE22" stroke-width="2" stroke-linecap="round" fill="none"/>' +
    '<rect x="9" y="9" width="46" height="46" rx="15.5" fill="#F7C948" stroke="#E0AE22" stroke-width="2.2"/>' +
    '<circle cx="24.6" cy="29.4" r="4.3" fill="#1E2A5A"/><circle cx="39.4" cy="29.4" r="4.3" fill="#1E2A5A"/>' +
    '<circle cx="26.2" cy="27.8" r="1.15" fill="#fff"/><circle cx="41" cy="27.8" r="1.15" fill="#fff"/>' +
    '<path d="M25.4 39.4c1.9 2.8 4 4.2 6.6 4.2s4.7-1.4 6.6-4.2" fill="none" stroke="#1E2A5A" stroke-width="2.6" stroke-linecap="round"/></svg>';

  /* Cần gạt hai chế độ. Nằm ngay dưới tiêu đề panel, đúng chỗ tab thứ tư sẽ nằm nếu sau
   * này trang mở tab thật. Dùng `aria-pressed` chứ không phải `role=tab`: nó KHÔNG phải
   * tab của trang, và nói dối trình đọc màn hình về cấu trúc là tệ hơn im lặng. */
  function modeHtml() {
    return '<div class="ec-aifill-modes">' +
      '<button type="button" class="ec-aifill-mode" data-mode="one" aria-pressed="' +
        (B.on ? "false" : "true") + '">Một phiếu</button>' +
      '<button type="button" class="ec-aifill-mode" data-mode="batch" aria-pressed="' +
        (B.on ? "true" : "false") + '">Tạo hàng loạt</button></div>';
  }

  function render() {
    if (!S.panel) return;
    var n = Object.keys(S.filled).length;
    var quota = S.remaining == null ? "" :
      '<span class="ec-aifill-quota">còn ' + S.remaining + ' lượt hôm nay</span>';
    if (B.on) {
      S.panel.innerHTML =
        '<div class="ec-aifill-top">' + MARK +
          '<span class="ec-aifill-title">AI điền hộ</span>' + quota + '</div>' +
        modeHtml() +
        '<div class="ec-aifill-body"><div class="ec-aifill-batch"></div>' +
          '<div class="ec-aifill-msg"></div></div>' +
        '<div class="ec-aifill-progress"><i></i></div>';
      S.panel.classList.toggle("is-running", !!B.busy || !!B.rows.some(function (r) { return r.busy; }));
      wireModes();
      B._html = null;
      renderBatch();
      return;
    }
    S.panel.innerHTML =
      '<div class="ec-aifill-top">' + MARK +
        '<span class="ec-aifill-title">AI điền hộ</span>' + quota + '</div>' +
      modeHtml() +
      '<div class="ec-aifill-body">' +
        '<textarea class="ec-aifill-note" rows="3" maxlength="' + S.maxChars + '" ' +
          'placeholder="Dán nội dung hợp đồng, email, hay mô tả khoản chi vào đây — hoặc chỉ cần đính kèm tệp ở dưới. AI đọc và điền vào form, bạn xem lại rồi tự bấm Gửi."></textarea>' +
        '<div class="ec-aifill-files"></div>' +
        '<div class="ec-aifill-foot">' +
          '<button type="button" class="ec-aifill-run"' + (S.busy ? " disabled" : "") + '>' +
            (S.busy ? "Đang đọc…" : "Điền vào form") + '</button>' +
          (n ? '<button type="button" class="ec-aifill-undo">Hoàn tác</button>' : "") +
          '<span class="ec-aifill-hint">Không chắc thì AI để trống — ô trống rẻ hơn ô sai trông như đúng.</span>' +
        '</div>' +
        '<div class="ec-aifill-msg"></div>' +
      '</div>' +
      '<div class="ec-aifill-progress"><i></i></div>';
    S.panel.classList.toggle("is-running", !!S.busy);
    var note = S.panel.querySelector(".ec-aifill-note");
    if (note) {
      if (S._note) note.value = S._note;
      // Giữ lại những gì đang gõ: panel bị vẽ lại nhiều lần (xong lượt, hoàn tác), mất chữ
      // đang gõ giữa chừng là mất công người dùng.
      note.oninput = function () { S._note = note.value; };
    }
    S.panel.querySelector(".ec-aifill-run").onclick = run;
    var u = S.panel.querySelector(".ec-aifill-undo");
    if (u) u.onclick = undoAll;
    // Panel vừa bị ghi đè innerHTML nên hộp tệp là hộp MỚI và RỖNG. Không xoá nhớ đệm thì
    // `renderFiles` so chuỗi thấy "y như cũ" rồi bỏ qua, và khối tệp không bao giờ hiện lại.
    S._filesHtml = null;
    wireModes();
    renderFiles();
  }

  function wireModes() {
    if (!S.panel) return;
    S.panel.querySelectorAll(".ec-aifill-mode").forEach(function (b) {
      b.onclick = function () { setMode(b.getAttribute("data-mode") === "batch"); };
    });
  }

  function kb(n) {
    if (!n) return "";
    return n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
  }

  /* HTML của khối tệp. PURE — và phải TẤT ĐỊNH: cùng đầu vào phải ra đúng cùng một chuỗi,
   * vì `renderFiles` dựa vào việc so chuỗi để biết có cần ghi DOM hay không (nếu không thì
   * chính nó nuôi MutationObserver của mình — sự cố 17/09). */
  function filesHtml(list, maxFiles, busy) {
    var rows = (list || []).map(function (f, i) {
      return '<div class="ec-aifill-file">' +
        '<span class="ec-aifill-file-nm">' + esc(f.name) + '</span>' +
        '<span class="ec-aifill-file-kb">' + kb(f.size) + '</span>' +
        '<button type="button" class="ec-aifill-file-x" data-rm="' + i + '" ' +
        'title="Bỏ tệp này" aria-label="Bỏ tệp ' + esc(f.name) + '">&times;</button>' +
        '</div>';
    }).join("");

    var day = (list || []).length >= maxFiles;
    var zone = '<label class="ec-aifill-drop' + (day ? " is-full" : "") + '">' +
      '<input type="file" multiple' + (day ? " disabled" : "") + '>' +
      '<span>' + (day
        ? ("Đủ " + maxFiles + " tệp cho một lượt — bỏ bớt nếu muốn đổi tệp khác.")
        : (busy ? "Đang tải tệp lên…"
                : "<b>Thả tệp vào đây</b> hoặc bấm để chọn — PDF, ảnh, văn bản thuần.")) +
      '</span></label>';

    return '<div class="ec-aifill-files-lbl">Tệp cho AI đọc' +
      '<span class="ec-aifill-files-note">chỉ để AI đọc — chứng từ của phiếu vẫn đính kèm ' +
      'ở bước “Tiếp tục: Thêm chứng từ”</span></div>' + rows + zone;
  }

  /* Mutation nào do CHÍNH ASSET NÀY gây ra bên trong panel của nó. PURE.
   *
   * Không có phép lọc này thì `renderFiles` ghi `innerHTML` → đó là một mutation trong
   * `document.body` → observer chạy lại → ghi lại → TREO CẢ TRANG. Đã xảy ra thật ngày
   * 17/09 trên production: trang payment-request chỉ còn mỗi panel, form biến mất. */
  function fromUs(muts, panel) {
    if (!panel || !muts || !muts.length) return false;
    for (var i = 0; i < muts.length; i++) {
      if (!panel.contains(muts[i].target)) return false;
    }
    return true;
  }

  /* Vẽ RIÊNG khối tệp, không vẽ lại cả panel: trang đổi DOM liên tục (mỗi lần tải xong một
   * tệp là một lần `renderFileList`), mà vẽ lại cả panel thì con trỏ trong ô văn bản nhảy
   * về đầu ngay giữa lúc người ta đang gõ.
   *
   * GHI CÓ ĐIỀU KIỆN. Ghi vô điều kiện = tự nuôi observer của chính mình (xem `fromUs`). */
  function renderFiles() {
    if (B.on) return;                 // chế độ lô có khối tệp riêng (`renderBatch`)
    var box = S.panel && S.panel.querySelector(".ec-aifill-files");
    if (!box) return;
    var html = filesHtml(S.files, S.maxFiles, S.uploading);
    if (html === S._filesHtml) return;        // không có gì đổi -> KHÔNG đụng vào DOM
    S._filesHtml = html;
    box.innerHTML = html;

    Array.prototype.forEach.call(box.querySelectorAll("[data-rm]"), function (b) {
      b.onclick = function () {
        // Chỉ bỏ khỏi DANH SÁCH GỬI. Không xoá bản ghi File trên máy chủ: xoá là việc
        // không lùi lại được, và tệp có thể đang được dùng ở chỗ khác.
        S.files.splice(+b.getAttribute("data-rm"), 1);
        S._filesHtml = null; renderFiles();
      };
    });

    var zone = box.querySelector(".ec-aifill-drop");
    var input = zone && zone.querySelector("input[type=file]");
    if (input) {
      input.onchange = function () { nhanTep(input.files); input.value = ""; };
    }
    if (zone) {
      ["dragenter", "dragover"].forEach(function (e) {
        zone.addEventListener(e, function (ev) {
          ev.preventDefault(); zone.classList.add("is-over");
        });
      });
      ["dragleave", "drop"].forEach(function (e) {
        zone.addEventListener(e, function (ev) {
          ev.preventDefault(); zone.classList.remove("is-over");
        });
      });
      zone.addEventListener("drop", function (ev) {
        if (ev.dataTransfer && ev.dataTransfer.files) nhanTep(ev.dataTransfer.files);
      });
    }
  }

  /* Nhận một mẻ tệp: lọc trước, tải tuần tự, báo từng cái bị bỏ và VÌ SAO.
   * Tuần tự chứ không song song: một mẻ 5 tệp 10MB bắn cùng lúc là cách làm nghẽn đúng cái
   * máy chủ mà người dùng đang chờ. */
  function nhanTep(fileList) {
    var vao = Array.prototype.slice.call(fileList || []);
    if (!vao.length) return;
    var bo = [];
    var nhan = [];
    vao.forEach(function (f) {
      var ly = refuseReason(f, S.files.concat(nhan), S.maxFiles, S.fileExts);
      if (ly) bo.push(esc(f.name) + " (" + ly + ")"); else nhan.push(f);
    });
    if (bo.length) say("<b>Bỏ qua " + bo.length + " tệp:</b> " + bo.join("; "), "warn");
    if (!nhan.length) { renderFiles(); return; }

    S.uploading = true; S._filesHtml = null; renderFiles();
    nhan.reduce(function (p, f) {
      return p.then(function () {
        return uploadOne(f).then(function (ok) { S.files.push(ok); })
          .catch(function (e) {
            bo.push(esc(f.name) + " (" + esc((e && e.message) || "không tải lên được") + ")");
          });
      });
    }, Promise.resolve()).then(function () {
      S.uploading = false; S._filesHtml = null; renderFiles();
      if (bo.length) say("<b>Bỏ qua " + bo.length + " tệp:</b> " + bo.join("; "), "warn");
      else say("");
    });
  }

  /* Tệp bị bỏ phải NÓI RA. Im lặng bỏ một hoá đơn rồi trả về form điền thiếu là cách người
   * dùng tin rằng AI đã đọc thứ nó chưa hề đọc. */
  function filesNote(res) {
    var bad = (res && res.files_rejected) || [];
    if (!bad.length) return "";
    return '<br><span class="ec-aifill-filebad"><b>Bỏ qua ' + bad.length + ' tệp:</b> ' +
      bad.map(function (r) { return esc(r.file) + " (" + esc(r.message) + ")"; }).join("; ") +
      "</span>";
  }

  function say(html, kind) {
    var box = S.panel && S.panel.querySelector(".ec-aifill-msg");
    if (box) box.innerHTML = html ? '<div class="ec-aifill-note-' + (kind || "info") + '">' + html + "</div>" : "";
  }

  function draft() {
    // Những gì người dùng ĐÃ tự gõ — server không ghi đè lên chúng.
    var out = {};
    document.querySelectorAll("[data-model]").forEach(function (el) {
      var k = el.getAttribute("data-model");
      var v = el.type === "checkbox" ? (el.checked ? "Yes" : "No") : el.value;
      if (v !== "" && v != null) out[k] = v;
    });
    return out;
  }

  function run() {
    if (S.busy) return;
    var note = (S.panel.querySelector(".ec-aifill-note").value || "").trim();
    S._note = note;
    if (S.uploading) { say("Đợi tải tệp xong đã nhé.", "warn"); return; }
    var picked = S.files.slice(0, S.maxFiles).map(function (f) { return f.url; });
    if (!note && !picked.length) {
      say("Dán nội dung vào ô trên, hoặc thả một tệp vào ô bên dưới.", "warn"); return;
    }
    S.busy = true; render(); say("");
    call("suggest", { approval_code: code, note: note, current: JSON.stringify(draft()),
                      files: JSON.stringify(picked) })
      .then(function (res) {
        S.busy = false;
        if (res.remaining != null) S.remaining = res.remaining;
        if (res.refused === "refused_quota") {
          render(); say("Hôm nay bạn đã dùng hết " + (res.cap || "") +
            " lượt. Lượt mới có lại từ 0h sáng mai. Form vẫn điền tay bình thường.", "warn"); return;
        }
        if (res.refused === "refused_too_long") {
          render(); say("Nội dung dài quá (tối đa " + res.max_chars + " ký tự).", "warn"); return;
        }
        if (res.refused === "refused_no_key") {
          render(); say("Chưa cấu hình khoá Gemini — báo IT giúp nhé.", "warn"); return;
        }
        if (res.refused === "empty") {
          render();
          say("Không có gì để đọc." + filesNote(res), "warn"); return;
        }
        if (res.error) {
          render();
          say("<b>Không đọc được lần này.</b> Nội dung bạn gõ vẫn còn nguyên — bấm lại là chạy tiếp, " +
              "và lượt này không bị tính.", "err");
          return;
        }
        S.sources = res.sources || {};
        S.ran = true;
        var fields = res.fields || {};
        fillSequential(fields, function () {
          render();
          var msg = "Đã điền <b>" + Object.keys(S.filled).length + " ô</b>.";
          if (res.dropped_count) msg += " Bỏ qua <b>" + res.dropped_count + " ô</b> vì không chắc.";
          if ((res.files_read || []).length) {
            msg += " Đã đọc <b>" + res.files_read.length + " tệp</b>.";
          }
          msg += filesNote(res);
          var probe = res.probe || {};
          if (probe.ok === false && probe.message) {
            msg += '<br><span class="ec-aifill-probe"><b>Chưa gửi được:</b> ' + esc(probe.message) + "</span>";
          }
          say(msg, "ok");
        });
      })
      .catch(function (e) {
        S.busy = false; render();
        say("<b>Không gọi được.</b> " + esc((e && e.message) || "Thử lại sau."), "err");
      });
  }

  /* ---------------------------------------------------------------- lắp đặt */

  /* ============================ G2b — "Tạo hàng loạt" ============================
   *
   * VÌ SAO LÀ MỘT CHẾ ĐỘ TRONG PANEL, KHÔNG PHẢI TAB THỨ TƯ.
   * Thiết kế §14.3 gọi đây là "tab thứ tư". Đọc code trang mới thấy không làm được mà
   * không đụng vào trang: `renderTabs()` ghi `box.innerHTML` từ một danh sách CỨNG bốn
   * dòng, nên mọi nút tab chèn thêm bị xoá ở lần vẽ lại kế tiếp; chèn lại trong
   * MutationObserver chính là vòng lặp đã làm chết form hôm 17/09. Và `data-tab` lạ thì
   * `go()` của trang không biết đường nào mà đi.
   * Làm tab thật = sửa `main_section.html` = bump BASELINE_SHA256 + patch resync — đúng
   * cái mà G1/G2a cố tình tránh. Nên: một cần gạt ngay trong panel. Nó nằm đúng chỗ tab
   * thứ tư sẽ nằm, và nâng lên thành tab thật sau này là một thay đổi phía TRANG, làm có
   * chủ đích, không phải một asset dùng chung lén sửa thanh tab của trang.
   *
   * MỘT LÔ CHỈ TẠO, KHÔNG QUYẾT ĐỊNH (A61 §1). Màn "sau khi gửi" liệt kê từng phiếu một —
   * mã riêng, lỗi riêng — chứ không phải một dòng "đã gửi 8 phiếu": hình dạng giao diện
   * phải nói đúng hình dạng hệ thống. Và không có nút duyệt-tất-cả ở bất kỳ đâu.
   */
  var B = { on: false, rows: [], busy: false, uploading: false,
            mo: null, _html: null, done: null };
  var _rid = 0;

  /* Ô nào hiện trên dòng. Ít thôi: dòng là để QUÉT, không phải để đọc kỹ. Muốn đọc kỹ thì
   * mở dòng ra. Tiền căn phải + tabular-nums để quét dọc cột là so được độ lớn. */
  var ROW_FIELDS = [
    ["payee_full_name", "Người nhận"], ["payment_amount", "Số tiền"],
    ["account_bank", "Ngân hàng"], ["bank_account_number", "Số tài khoản"],
    ["payment_date", "Ngày thanh toán"], ["reason", "Lý do / nội dung"]
  ];

  function money(v) {
    var n = Number(String(v == null ? "" : v).replace(/[^\d.-]/g, ""));
    if (!isFinite(n) || !n) return "";
    return n.toLocaleString("vi-VN");
  }

  function batchCall(method, args) {
    if (!S.ns) return Promise.reject(new Error("form này chưa mở tạo hàng loạt"));
    return frappe.call({ method: S.ns + method, args: args, type: "POST" })
      .then(function (r) { return (r || {}).message || {}; });
  }

  /* Trần 10 là TRẦN QUYẾT ĐỊNH, không phải trần công suất — nên lý do từ chối cũng nói
   * theo quyết định, không nói "hết chỗ". */
  function batchRefuse(file) {
    var da = B.rows.map(function (r) { return { name: r.file.name, size: r.file.size }; });
    if (da.length >= S.maxDrafts) {
      // `refuseReason` nói "một lượt tối đa N tệp" — đúng cho panel một phiếu, sai ở đây:
      // con số này đếm PHIẾU, và lý do của nó không phải là máy chạy không kịp.
      return "một lô tối đa " + S.maxDrafts + " phiếu — đây là số quyết định người duyệt " +
             "phải đọc, không phải giới hạn của máy";
    }
    return refuseReason(file, da, S.maxDrafts, S.fileExts);
  }

  function rowState(r) {
    if (r.name) return ["Đã tạo nháp", "ok"];
    if (r.err) return ["Lỗi", "bad"];
    if (r.busy) return ["Đang đọc…", "wait"];
    var thieu = ROW_FIELDS.filter(function (f) {
      return !String((r.fields || {})[f[0]] || "").trim();
    }).length;
    return thieu ? ["Thiếu " + thieu + " ô", "warn"] : ["Sẵn sàng", "gray"];
  }

  /* Ba dấu hiệu — rẻ để tra, đắt nếu bỏ sót. Cả ba đều là thứ mắt người bỏ sót ở phiếu
   * thứ sáu, nên chúng phải nằm TRÊN dòng chứ không nằm sau một cú bấm. */
  var FLAG_TEXT = {
    dup_in_batch: ["Trùng STK trong lô", "Hai dòng trong lô này cùng một số tài khoản — có thể AI đọc một tệp thành hai, hoặc một khoản sắp bị trả hai lần."],
    new_account: ["Số tài khoản mới", "Số tài khoản này chưa từng nằm trên phiếu nào đã gửi."],
    amount_off: ["Số tiền lệch xa", "Lệch từ 3 lần trở lên so với những phiếu bạn từng gửi cho số tài khoản này."]
  };

  function flagsHtml(r) {
    var f = r.flags || {}, out = [];
    ["dup_in_batch", "new_account", "amount_off"].forEach(function (k) {
      if (!f[k]) return;
      out.push('<span class="ec-aifill-flag" title="' + esc(FLAG_TEXT[k][1]) + '">' +
               esc(FLAG_TEXT[k][0]) + "</span>");
    });
    return out.join("");
  }

  function rowHtml(r) {
    var st = rowState(r), fl = r.fields || {};
    var mo = B.mo === r.key;
    var than = "";
    if (mo && !r.name) {
      than = '<div class="ec-aifill-row-body">' + ROW_FIELDS.map(function (f) {
        var v = String(fl[f[0]] || "");
        var dai = f[0] === "reason";
        return '<label class="ec-aifill-f' + (dai ? " wide" : "") + '"><span>' + esc(f[1]) + "</span>" +
          (dai ? '<textarea rows="2" data-k="' + f[0] + '">' + esc(v) + "</textarea>"
               : '<input type="' + (f[0] === "payment_date" ? "date" : "text") +
                 '" data-k="' + f[0] + '" value="' + esc(v) + '">') + "</label>";
      }).join("") + "</div>";
    }
    /* Nói RÕ còn thiếu ô nào, kèm nhãn đúng như trên form. "Lỗi" một mình là thứ đẩy
     * người dùng đi hỏi, và đẩy tôi đi điều tra trên prod. */
    var thieu = (r.missing || []).map(function (x) { return x.label || x.fieldname; });
    var ket = r.name
      ? '<div class="ec-aifill-row-done">' +
          '<a class="ec-aifill-row-link" href="/approvals/payment-request?tab=detail&id=' +
          encodeURIComponent(r.name) + '">' + esc(r.name) + "</a>" +
          (thieu.length
            ? '<span class="ec-aifill-row-need">còn thiếu: ' + esc(thieu.join(", ")) + "</span>"
            : '<span class="ec-aifill-row-need">đủ ô bắt buộc — mở ra xem lại rồi bấm Gửi</span>') +
        "</div>"
      : (r.err ? '<span class="ec-aifill-row-err">' + esc(r.err) + "</span>" : "");
    return '<div class="ec-aifill-row" data-row="' + esc(r.key) + '">' +
      '<div class="ec-aifill-row-top">' +
        '<button type="button" class="ec-aifill-row-x2" data-act="mo" aria-expanded="' +
          (mo ? "true" : "false") + '">' + (mo ? "▾" : "▸") + "</button>" +
        '<span class="ec-aifill-row-file" title="' + esc(r.file.name) + '">' + esc(r.file.name) + "</span>" +
        '<span class="ec-aifill-row-who">' + esc(fl.payee_full_name || "—") + "</span>" +
        '<span class="ec-aifill-row-amt">' + esc(money(fl.payment_amount)) + "</span>" +
        '<span class="ec-aifill-chip is-' + st[1] + '">' + esc(st[0]) + "</span>" +
        (r.name ? "" : '<button type="button" class="ec-aifill-row-del" data-act="xoa" ' +
                       'aria-label="Bỏ dòng này">×</button>') +
      "</div>" +
      (flagsHtml(r) ? '<div class="ec-aifill-row-flags">' + flagsHtml(r) + "</div>" : "") +
      ket + than + "</div>";
  }

  function batchHtml() {
    var n = B.rows.length;
    var sanSang = B.rows.filter(function (r) { return !r.name && !r.busy && !r.err; }).length;
    var daGui = B.rows.filter(function (r) { return r.name; }).length;
    var drop =
      '<div class="ec-aifill-drop ec-aifill-bdrop' + (n >= S.maxDrafts ? " is-full" : "") +
        '" tabindex="0" role="button">' +
        (n >= S.maxDrafts
          ? "<span>Đủ " + S.maxDrafts + " phiếu rồi. Bỏ bớt một dòng nếu muốn thêm tệp khác.</span>"
          : "<span><b>Thả tối đa " + S.maxDrafts + " tệp</b> — mỗi tệp thành một phiếu, " +
            "và chính tệp đó là chứng từ đính kèm của phiếu ấy.</span>") +
        '<input type="file" multiple accept="' +
        (S.fileExts || []).map(function (e) { return "." + e; }).join(",") + '"></div>';

    var canhBao = n >= S.maxDrafts
      ? '<div class="ec-aifill-cap">Tối đa ' + S.maxDrafts + ' phiếu một lô. Không phải vì máy chậm: ' +
        S.maxDrafts + ' phiếu là ' + S.maxDrafts + ' quyết định mà người duyệt phải đọc.</div>'
      : "";

    /* KHÔNG có ô cam kết ở đây nữa, và đó là điều cố ý.
     *
     * Ô cam kết là chữ ký trách nhiệm cho việc GỬI. Màn này không gửi, nên để nó lại là
     * xin một chữ ký cho một hành động không xảy ra — và tệ hơn, nó dạy người dùng tích
     * vào những ô như thế mà không đọc. Chữ ký ấy thuộc về form, nơi người ta thực sự bấm
     * Gửi, và nó vẫn nằm nguyên ở đó. */
    var chan = "";
    if (sanSang && !B.busy) {
      chan =
        '<div class="ec-aifill-foot">' +
          '<button type="button" class="ec-aifill-run ec-aifill-send">Tạo ' + sanSang +
            " bản nháp</button>" +
          '<span class="ec-aifill-hint">Tạo xong bạn mở từng phiếu, điền nốt phần của mình rồi tự bấm Gửi.</span>' +
        "</div>";
    } else if (B.busy) {
      chan = '<div class="ec-aifill-foot"><span class="ec-aifill-hint">Đang tạo từng bản nháp một…</span></div>';
    }
    if (daGui) {
      chan = '<div class="ec-aifill-sent">Đã tạo ' + daGui + " bản nháp. Mỗi phiếu ở trên " +
             "còn chờ bạn điền nốt và tự bấm Gửi — hệ thống chưa gửi cái nào cả.</div>" + chan;
    }

    return drop + canhBao +
      (n ? '<div class="ec-aifill-rows">' + B.rows.map(rowHtml).join("") + "</div>" : "") +
      chan;
  }

  /* Ghi DOM CÓ ĐIỀU KIỆN, và không bao giờ ghi khi con trỏ đang nằm trong khối: người ta
   * đang sửa một ô mà mình vẽ lại cả danh sách thì con trỏ nhảy về đầu. Cùng một luật đã
   * áp cho `renderFiles`. */
  function renderBatch() {
    if (!B.on || !S.panel) return;
    var host = S.panel.querySelector(".ec-aifill-batch");
    if (!host) return;
    var html = batchHtml();
    if (html === B._html) return;
    if (host.contains(document.activeElement) &&
        /^(INPUT|TEXTAREA)$/.test((document.activeElement || {}).tagName || "")) return;
    B._html = html;
    host.innerHTML = html;
    wireBatch(host);
  }

  function wireBatch(host) {
    var drop = host.querySelector(".ec-aifill-bdrop");
    var inp = drop && drop.querySelector("input[type=file]");
    if (drop && inp) {
      drop.onclick = function () { if (B.rows.length < S.maxDrafts) inp.click(); };
      drop.onkeydown = function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); drop.click(); }
      };
      inp.onchange = function () { batchNhan(inp.files); inp.value = ""; };
      ["dragenter", "dragover"].forEach(function (t) {
        drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.add("is-over"); });
      });
      ["dragleave", "drop"].forEach(function (t) {
        drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.remove("is-over"); });
      });
      drop.addEventListener("drop", function (e) {
        if (e.dataTransfer && e.dataTransfer.files) batchNhan(e.dataTransfer.files);
      });
    }
    host.querySelectorAll("[data-row]").forEach(function (el) {
      var key = el.getAttribute("data-row");
      var r = B.rows.filter(function (x) { return x.key === key; })[0];
      if (!r) return;
      var mo = el.querySelector('[data-act="mo"]');
      if (mo) mo.onclick = function () { B.mo = (B.mo === key ? null : key); B._html = null; renderBatch(); };
      var xoa = el.querySelector('[data-act="xoa"]');
      if (xoa) xoa.onclick = function () {
        B.rows = B.rows.filter(function (x) { return x.key !== key; });
        B._html = null; renderBatch(); batchFlags();
      };
      el.querySelectorAll("[data-k]").forEach(function (f) {
        f.oninput = function () {
          r.fields = r.fields || {};
          r.fields[f.getAttribute("data-k")] = f.value;
          // Người dùng vừa sửa tay -> cờ cũ có thể sai. Xoá trước, tra lại sau.
          B._html = null;
        };
        f.onchange = function () { batchFlags(); };
      });
    });
    var send = host.querySelector(".ec-aifill-send");
    if (send) send.onclick = batchTaoNhap;
  }

  /* Mỗi tệp một lượt gọi RIÊNG, tuần tự. Không gộp 10 tệp vào một request: một request
   * 10 lượt Gemini là ~80 giây, quá cửa sổ timeout, và một tệp hỏng kéo cả lô xuống.
   * Gọi riêng thì dòng nào xong vẽ dòng đó, và lỗi ở lượt 4 không đụng lượt 5. */
  function batchNhan(fileList) {
    var vao = Array.prototype.slice.call(fileList || []);
    if (!vao.length) return;
    var bo = [], nhan = [];
    vao.forEach(function (f) {
      var ly = batchRefuse(f);
      if (ly) bo.push(esc(f.name) + " (" + ly + ")");
      else { nhan.push(f); B.rows.push({ key: "r" + (++_rid), file: f, fields: {}, busy: true }); }
    });
    if (bo.length) say("<b>Bỏ qua " + bo.length + " tệp:</b> " + bo.join("; "), "warn");
    B._html = null; renderBatch();

    nhan.reduce(function (p, f) {
      return p.then(function () {
        var r = B.rows.filter(function (x) { return x.file === f; })[0];
        if (!r) return;
        return uploadOne(f)
          .then(function (up) {
            r.url = up.url;
            return call("suggest", { approval_code: code, files: JSON.stringify([up.url]) });
          })
          .then(function (res) {
            if (res.refused || res.error) throw new Error(res.refused || res.error);
            r.fields = res.fields || {};
            // Tệp đọc được thì CHÍNH NÓ là chứng từ của phiếu — bỏ hẳn một bước đính kèm
            // thủ công cho mỗi phiếu. Đây mới là chỗ "hàng loạt" tiết kiệm thật.
            if (r.url) r.fields.request_attachment = r.url;
            if (typeof res.remaining === "number") { S.remaining = res.remaining; }
          })
          .catch(function (e) { r.err = (e && e.message) || "không đọc được tệp này"; })
          .then(function () { r.busy = false; B._html = null; renderBatch(); });
      });
    }, Promise.resolve()).then(function () { batchFlags(); });
  }

  function batchFlags() {
    if (!S.hasFlags) return;
    var rows = B.rows.filter(function (r) { return !r.name && !r.err; }).map(function (r) {
      return { key: r.key, bank_account_number: (r.fields || {}).bank_account_number || "",
               payment_amount: (r.fields || {}).payment_amount || 0 };
    });
    if (!rows.length) return;
    call("batch_flags", { approval_code: code, rows: JSON.stringify(rows) })
      .then(function (res) {
        B.rows.forEach(function (r) { r.flags = (res || {})[r.key] || null; });
        B._html = null; renderBatch();
      })
      .catch(function () { /* cờ là thứ tăng thêm — hỏng thì im, đừng chặn việc gửi */ });
  }

  /* Gửi TỪNG phiếu một, tuần tự, mỗi phiếu một kết quả riêng. Người bấm là người dùng,
   * sau khi tích ô cam kết có ghi rõ số phiếu — AI không bao giờ tự gửi. */
  /* CÂU TIẾNG VIỆT THẬT CỦA SERVER, không phải "gửi không thành công".
   *
   * Frappe không đặt lỗi nghiệp vụ vào `e.message`: `frappe.throw` xếp câu đó vào
   * `_server_messages` — một chuỗi JSON chứa những chuỗi JSON khác, mỗi cái có khoá
   * `message`, và nội dung là HTML. Bản đầu của tôi đọc `e.message` rồi rơi về một câu
   * chết, nên "Loại chi phí này gắn với một brand — vui lòng chọn brand" biến thành
   * "gửi không thành công", và mỗi lỗi sau đó thành một cuộc điều tra trên prod.
   */
  function loiThat(e, mac_dinh) {
    var raw = (e && e._server_messages) ||
              (window.frappe && frappe.last_response && frappe.last_response._server_messages);
    try {
      var cau = JSON.parse(raw).map(function (x) {
        try { return JSON.parse(x).message || x; } catch (_) { return x; }
      }).join(" · ");
      cau = String(cau).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
      if (cau) return cau;
    } catch (_) { /* không parse được thì rơi xuống dưới */ }
    var m = e && (e.message || e.exc_type);
    return (m && String(m).trim()) || mac_dinh;
  }

  /* CHỈ TẠO BẢN NHÁP. Không gửi.
   *
   * Chốt với Hoàn 23/09. Bản đầu của tôi gửi luôn cả lô, và cái sai không nằm ở giao diện
   * mà ở chính đề bài: hai ô bắt buộc của phiếu là PHÁN ĐOÁN CỦA CON NGƯỜI — "Chi phí hợp
   * lệ?" và ô tích xác nhận thông tin — còn Brand thì không nằm trên hoá đơn nên AI không
   * thể biết. Một lô TT_KOL vì thế gần như không bao giờ gửi sạch được, và mỗi lần không
   * sạch là một dòng "Lỗi" không giải thích gì.
   *
   * Nên lô dừng ở bản nháp: máy làm phần máy đọc được, người làm phần chỉ người mới trả
   * lời được, và ranh giới đó hiện ra trên màn hình bằng danh sách "còn thiếu".
   */
  function batchTaoNhap() {
    if (B.busy) return;
    var chay = B.rows.filter(function (r) { return !r.name && !r.busy && !r.err; });
    if (!chay.length) return;
    B.busy = true; B._html = null; renderBatch();
    chay.reduce(function (p, r) {
      return p.then(function () {
        return call("create_draft", { approval_code: code,
                                      fields: JSON.stringify(r.fields || {}) })
          .then(function (res) {
            if (!res || !res.name) throw new Error("không tạo được bản nháp");
            r.name = res.name;
            r.missing = res.missing || [];
            r.err = null;
          })
          .catch(function (e) { r.err = loiThat(e, "không tạo được bản nháp"); })
          .then(function () { B._html = null; renderBatch(); });
      });
    }, Promise.resolve()).then(function () {
      B.busy = false; B.mo = null; B._html = null; renderBatch();
    });
  }

  function setMode(on) {
    B.on = !!on;
    S._filesHtml = null; B._html = null;
    render();
  }

  function mount() {
    if (S.panel && document.body.contains(S.panel)) return true;
    /* Neo theo CLASS `.tabs`, không theo id: id mỗi form một kiểu (`payr-tabs`, `book-tabs`,
     * `ctr-tabs`…) nhưng class thì giống nhau cả 28. Panel chèn GIỮA `.tabs` và thân form —
     * hai anh em mà trang chỉ ghi đè `innerHTML`, nên nó sống sót mọi lần vẽ lại. */
    var tabs = document.querySelector(".content > .tabs");
    if (!tabs) return false;
    var p = document.createElement("div");
    p.className = "ec-aifill";
    p.id = "ec-aifill-host";
    tabs.insertAdjacentElement("afterend", p);
    S.panel = p;
    render();
    return true;
  }

  function start(boot) {
    S.remaining = boot.remaining; S.cap = boot.cap;
    S.maxChars = boot.max_chars || S.maxChars;
    S.maxFiles = boot.max_files || S.maxFiles;
    S.fileExts = boot.file_exts || [];
    var bt = boot.batch || {};
    S.maxDrafts = bt.max_drafts || S.maxDrafts;
    S.hasFlags = !!bt.has_flags;
    S.ns = bt.ns || "";
    if (!mount()) {
      var tries = 0, tm = setInterval(function () {
        if (mount() || ++tries > 25) clearInterval(tm);
      }, 400);
    }
    // Trang vẽ lại liên tục → vẽ lại dấu + gắn lại panel sau mỗi lần DOM đổi.
    new MutationObserver(function (muts) {
      if (fromUs(muts, S.panel)) return;     // đừng tự đuổi theo cái đuôi của mình
      mount(); paint(); renderFiles(); renderBatch();
    }).observe(document.body, { childList: true, subtree: true });

    // Gõ tay vào một ô AI đã điền → dấu biến mất. `capture` để bắt trước handler của trang.
    ["input", "change"].forEach(function (evt) {
      document.addEventListener(evt, function (ev) {
        if (!isUserEdit(ev)) return;
        var t = ev.target;
        var k = t && t.getAttribute && t.getAttribute("data-model");
        if (k && S.filled[k]) settle(k);
      }, true);
    });
  }

  function boot() {
    if (!code || typeof frappe === "undefined" || !frappe.call) return;
    call("bootstrap", { approval_code: code })
      .then(function (b) { if (b && b.enabled) start(b); })
      .catch(function () { /* tắt thì im lặng, không làm phiền form */ });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else { boot(); }

  // Bề mặt cho test: HÀM THUẦN, không phải state.
  window.__ecAifill = { writeOrder: writeOrder, isUserEdit: isUserEdit, ROUTES: ROUTES,
                       filesHtml: filesHtml, fromUs: fromUs,
                       refuseReason: refuseReason, kb: kb,
                       missingRequired: missingRequired,
                       money: money, rowState: rowState, batchRefuse: batchRefuse,
                       flagsHtml: flagsHtml, batchHtml: batchHtml, B: B, S: S,
                       loiThat: loiThat,
                       setMode: setMode };
})();
