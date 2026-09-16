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
            maxChars: 8000, panel: null };

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
          'placeholder="Dán nội dung hợp đồng, email, hay mô tả khoản chi vào đây. AI đọc và điền vào form bên dưới — bạn xem lại rồi tự bấm Gửi."></textarea>' +
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
    if (note && S._note) note.value = S._note;
    S.panel.querySelector(".ec-aifill-run").onclick = run;
    var u = S.panel.querySelector(".ec-aifill-undo");
    if (u) u.onclick = undoAll;
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
    if (!note) { say("Dán nội dung vào ô trên đã nhé.", "warn"); return; }
    S.busy = true; render(); say("");
    call("suggest", { approval_code: code, note: note, current: JSON.stringify(draft()) })
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
    if (!mount()) {
      var tries = 0, tm = setInterval(function () {
        if (mount() || ++tries > 25) clearInterval(tm);
      }, 400);
    }
    // Trang vẽ lại liên tục → vẽ lại dấu + gắn lại panel sau mỗi lần DOM đổi.
    new MutationObserver(function () { mount(); paint(); })
      .observe(document.body, { childList: true, subtree: true });

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
  window.__ecAifill = { writeOrder: writeOrder, isUserEdit: isUserEdit, ROUTES: ROUTES };
})();
