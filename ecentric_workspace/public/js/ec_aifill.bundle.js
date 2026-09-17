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
            maxChars: 8000, maxFiles: 5, files: [], fileExts: [], uploading: false,
            _filesHtml: null, panel: null };

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
    S.filled = {}; S.sources = {}; S.before = {};
    paint(); render();
  }

  /* ------------------------------------------------------- dấu + trích dẫn */
  var BADGE_SVG =
    '<svg viewBox="0 0 64 64" aria-hidden="true">' +
    '<rect x="7" y="7" width="50" height="50" rx="17" fill="#F7C948" stroke="#E0AE22" stroke-width="3"/>' +
    '<circle cx="24" cy="31" r="5.6" fill="#1E2A5A"/><circle cx="40" cy="31" r="5.6" fill="#1E2A5A"/></svg>';

  /** Vẽ lại dấu sau MỖI lần trang đổi DOM. Dấu phải suy ra từ state của asset, không bám
   *  vào phần tử — `renderCreate` thay sạch innerHTML nên mọi thứ gắn vào DOM đều bay. */
  function paint() {
    document.querySelectorAll(".ec-aifill-badge, .ec-aifill-src").forEach(function (n) {
      if (!S.filled[n.getAttribute("data-for")]) n.remove();
    });
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

  function render() {
    if (!S.panel) return;
    var n = Object.keys(S.filled).length;
    var quota = S.remaining == null ? "" :
      '<span class="ec-aifill-quota">còn ' + S.remaining + ' lượt hôm nay</span>';
    S.panel.innerHTML =
      '<div class="ec-aifill-top">' + MARK +
        '<span class="ec-aifill-title">AI điền hộ</span>' + quota + '</div>' +
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
    renderFiles();
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
    if (!mount()) {
      var tries = 0, tm = setInterval(function () {
        if (mount() || ++tries > 25) clearInterval(tm);
      }, 400);
    }
    // Trang vẽ lại liên tục → vẽ lại dấu + gắn lại panel sau mỗi lần DOM đổi.
    new MutationObserver(function (muts) {
      if (fromUs(muts, S.panel)) return;     // đừng tự đuổi theo cái đuôi của mình
      mount(); paint(); renderFiles();
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
                       refuseReason: refuseReason, kb: kb };
})();
