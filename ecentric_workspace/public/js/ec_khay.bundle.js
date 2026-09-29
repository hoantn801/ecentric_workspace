/* ec_khay — Khay, trợ lý ở góc mọi trang ERP (28/09/2026).
 *
 * Kiểu A (khung chat nổi) là mặc định; có tệp hoặc phiếu nhiều ô thì tự nở thành kiểu B
 * (ngăn kéo bên phải). Thiết kế đã duyệt: artifact "Khay Chat Popup".
 *
 * KHAY KHÔNG CÓ LUẬT NGHIỆP VỤ NÀO. Nó chỉ gọi những endpoint CÓ SẴN, đúng như trang gốc gọi:
 *   - hiểu câu:      ecentric_workspace.platform.ai.khay.intent   (chỉ đề xuất, không ghi)
 *   - xin nghỉ:      ec_hr_leave_apply   — mọi luật (lùi ngày, ốm cần giấy, trùng ngày…) ở đó
 *   - số dư phép:    ec_hr_leave_data
 *   - đề nghị TT:    approval_center.api.ai_formfill.suggest → create_draft → mở nháp.
 *                    KHÔNG gửi thay: "Chi phí hợp lệ?" và ô tích xác nhận là phán đoán của
 *                    người (chốt 23/09).
 *   - hỏi đáp:       gemini_chat (quyền theo A14)
 *
 * PHẠM VI: chỉ chạy trên trang ERP có vỏ shell (`[data-ec-shell]`) hoặc thanh tab nhân sự
 * (`.ec-tabwrap`). Trang nào không muốn có Khay thì gắn `data-ec-no-khay` — trang tự khai,
 * asset không đoán (bài học ec_formkit 25–26/08).
 *
 * Giao diện nằm trong Shadow DOM: Bootstrap của Frappe tô đè `.btn/.row/.card` (bẫy 16/09).
 * Kill switch: server trả `enabled:false` (thiếu role EC Khay Pilot, site_config
 * `ec_khay_disabled`, hoặc `ec_ai_disabled`) → không vẽ gì.
 */
(function () {
  "use strict";

  /* ------------------------------------------------------------ PURE (test được) */
  var THU = ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"];
  var LEAVE_VI = {
    "Annual Leave": "Phép năm", "Sick Leave": "Nghỉ ốm", "Compensatory Off": "Nghỉ bù",
    "Leave Without Pay": "Nghỉ không lương", "Marriage Leave": "Nghỉ cưới",
    "Bereavement Leave": "Nghỉ tang", "Maternity Leave": "Nghỉ thai sản",
    "Paternity Leave": "Nghỉ vợ sinh", "Casual Leave": "Nghỉ việc riêng"
  };
  var MAX_BYTES = 7 * 1024 * 1024;       // trần tệp inline của cổng AI (Kie)
  var MAX_FILES = 5;
  var STORE = "ec-khay-v1";
  var MAX_KEEP = 30;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  /* "2026-09-29" -> "Thứ Ba 29/09/2026". Chuỗi lạ thì trả nguyên. */
  function viDate(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    if (!m) return String(iso || "");
    var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    return THU[d.getUTCDay()] + " " + m[3] + "/" + m[2] + "/" + m[1];
  }
  function leaveLabel(t) { return LEAVE_VI[t] || t || ""; }
  function leaveRange(lv) {
    if (!lv) return "";
    var s = viDate(lv.from_date);
    if (lv.to_date && lv.to_date !== lv.from_date) s += " → " + viDate(lv.to_date);
    if (+lv.half_day) s += lv.half_day_part === "morning" ? " (buổi sáng)" :
      lv.half_day_part === "afternoon" ? " (buổi chiều)" : " (nửa ngày)";
    return s;
  }
  /* Chặn sớm cho người dùng biết ngay; server vẫn chặn lại. */
  function fileRefuse(file, list) {
    if (!file || !file.size) return "tệp rỗng";
    if (file.size > MAX_BYTES) return "tệp quá lớn (tối đa 7MB)";
    if ((file.name || "").indexOf(".") < 0) return "không rõ loại tệp";
    if ((list || []).length >= MAX_FILES) return "tối đa " + MAX_FILES + " tệp một lần";
    return null;
  }
  function fmtValue(v) {
    if (typeof v === "number") return v.toLocaleString("vi-VN");
    if (v === true) return "Có";
    if (v === false) return "Không";
    return String(v == null ? "" : v);
  }
  /* Câu lỗi THẬT của server (frappe.throw nằm trong _server_messages, không ở message). */
  function serverError(j, fallback) {
    try {
      if (j && j._server_messages) {
        var t = JSON.parse(j._server_messages).map(function (x) {
          try { return JSON.parse(x).message || x; } catch (e) { return x; }
        }).join(" · ").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
        if (t) return t;
      }
    } catch (e) { /* rơi xuống dưới */ }
    if (j && j.exc_type === "PermissionError") return "Bạn chưa có quyền làm việc này.";
    return fallback || "Có lỗi, bạn thử lại nhé.";
  }
  /* Lịch sử gửi cho AI: chỉ lượt chữ, 10 lượt cuối. */
  function historyOf(msgs) {
    return (msgs || []).filter(function (m) {
      return (m.role === "user" || m.role === "bot") && m.text;
    }).slice(-10).map(function (m) {
      return { role: m.role === "user" ? "user" : "model", text: m.text };
    });
  }
  /* "gemini-3-8-flash-openai" -> "Gemini 3.8 Flash", "gpt-6-luna" -> "GPT-6 Luna".
   * Luồng OpenAI chỉ là đường gọi, cùng một model nên không hiện. */
  function modelLabel(model) {
    var m = String(model || "").trim().toLowerCase().replace(/-openai$/, "");
    if (!m) return "";
    var p = m.split("-"), brand = { gemini: "Gemini", gpt: "GPT", grok: "Grok", claude: "Claude" }[p[0]] ||
      (p[0].charAt(0).toUpperCase() + p[0].slice(1));
    var nums = [], words = [];
    p.slice(1).forEach(function (x) {
      if (/^\d+$/.test(x) && !words.length) nums.push(x);
      else words.push(x.charAt(0).toUpperCase() + x.slice(1));
    });
    var ver = nums.join(".");
    var head = ver ? brand + (brand === "GPT" ? "-" : " ") + ver : brand;
    return [head].concat(words).join(" ");
  }
  function mdLite(text) {
    return esc(text).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");
  }
  function shouldRun(doc, path) {
    if (/^\/(app|login|api)(\/|$)/.test(path || "")) return false;
    if (doc.querySelector("[data-ec-no-khay]")) return false;
    return !!(doc.querySelector("[data-ec-shell]") || doc.querySelector(".ec-tabwrap"));
  }

  /* Trang chủ còn khung chat cũ "AI Trợ lý" (#ec-chat-fab, nằm trong Web Page trang chủ,
   * được áo linh vật bởi khối home v2). Hai con chồng ở cùng góc. Ai đã có eC Mate thì
   * ẩn con cũ; ai chưa có eC Mate vẫn giữ con cũ, không ai mất chỗ chat. Hoàn chốt 28/09. */
  var RETIRE_ID = "ec-khay-retire-old-chat";
  function retireOldChat(doc) {
    if (doc.getElementById(RETIRE_ID)) return false;
    var st = doc.createElement("style");
    st.id = RETIRE_ID;
    st.textContent = "#ec-chat-fab,#ec-chat-panel{display:none!important}";
    (doc.head || doc.documentElement).appendChild(st);
    return true;
  }

  var PURE = { viDate: viDate, leaveLabel: leaveLabel, leaveRange: leaveRange,
               fileRefuse: fileRefuse, fmtValue: fmtValue, serverError: serverError,
               historyOf: historyOf, mdLite: mdLite, shouldRun: shouldRun, esc: esc,
               modelLabel: modelLabel,
               retireOldChat: retireOldChat };
  /* Cho test (jsdom) đọc các hàm PURE. KHÔNG dùng `module.exports`: esbuild thấy chữ
   * `module` sẽ gói file thành CommonJS, `module` có thật lúc chạy và widget tự thoát. */
  window.__ecKhayPure = PURE;

  if (window.__ecKhayInstalled) return;
  window.__ecKhayInstalled = true;

  /* ------------------------------------------------------------------ mạng */
  var tokenP = null;
  function freshToken(force) {
    if (force) tokenP = null;
    if (!tokenP) {
      tokenP = fetch("/api/method/get_csrf", { credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          var t = j && j.message && j.message.csrf_token;
          return t || (window.frappe && frappe.csrf_token) || "";
        })
        .catch(function () { return (window.frappe && frappe.csrf_token) || ""; });
    }
    return tokenP;
  }
  function parse(r) {
    return r.json().catch(function () { return {}; }).then(function (j) {
      return { ok: r.ok, status: r.status, j: j || {} };
    });
  }
  /* POST có CSRF tươi; gặp CSRFTokenError thì xin token MỚI và thử lại đúng một lần. */
  function post(method, body, retried) {
    return freshToken(retried).then(function (tok) {
      return fetch("/api/method/" + method, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Accept": "application/json",
                   "X-Frappe-CSRF-Token": tok },
        body: JSON.stringify(body || {})
      }).then(parse);
    }).then(function (res) {
      if (!res.ok && res.j.exc_type === "CSRFTokenError" && !retried) {
        return post(method, body, true);
      }
      if (!res.ok) throw new Error(serverError(res.j));
      return res.j.message;
    });
  }
  function get(method, params) {
    var q = params ? "?" + Object.keys(params).map(function (k) {
      return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]);
    }).join("&") : "";
    return fetch("/api/method/" + method + q, { credentials: "same-origin",
                                                headers: { "Accept": "application/json" } })
      .then(parse).then(function (res) {
        if (!res.ok) throw new Error(serverError(res.j));
        return res.j.message;
      });
  }
  function upload(file, retried) {
    return freshToken(retried).then(function (tok) {
      var fd = new FormData();
      fd.append("file", file);
      fd.append("is_private", "1");
      return fetch("/api/method/upload_file", {
        method: "POST", credentials: "same-origin",
        headers: { "X-Frappe-CSRF-Token": tok }, body: fd
      });
    }).then(function (r) {
      if (r.status === 413) throw new Error("tệp quá lớn so với giới hạn máy chủ");
      return parse(r);
    }).then(function (res) {
      if (!res.ok && res.j.exc_type === "CSRFTokenError" && !retried) return upload(file, true);
      var url = res.j.message && res.j.message.file_url;
      if (!res.ok || !url) throw new Error(serverError(res.j, "tải tệp không được"));
      return url;
    });
  }

  var API = {
    boot: "ecentric_workspace.platform.ai.khay.boot",
    intent: "ecentric_workspace.platform.ai.khay.intent",
    chat: "gemini_chat",
    leaveApply: "ec_hr_leave_apply",
    leaveData: "ec_hr_leave_data",
    suggest: "ecentric_workspace.approval_center.api.ai_formfill.suggest",
    draft: "ecentric_workspace.approval_center.api.ai_formfill.create_draft"
  };

  /* ------------------------------------------------------------------ state */
  var S = { boot: null, open: false, wide: false, busy: false, msgs: [], files: [],
            leaveData: null };
  var R = {};   // tham chiếu DOM trong shadow root

  function save() {
    try {
      var keep = S.msgs.filter(function (m) { return m.role === "user" || m.role === "bot"; })
        .slice(-MAX_KEEP).map(function (m) { return { role: m.role, text: m.text, by: m.by || "" }; });
      sessionStorage.setItem(STORE, JSON.stringify({ open: S.open, wide: S.wide, msgs: keep }));
    } catch (e) { /* trình duyệt chặn lưu trữ thì thôi */ }
  }
  function load() {
    try {
      var o = JSON.parse(sessionStorage.getItem(STORE) || "{}");
      S.msgs = Array.isArray(o.msgs) ? o.msgs : [];
      S.open = !!o.open; S.wide = !!o.wide;
    } catch (e) { S.msgs = []; }
  }

  /* ------------------------------------------------------------------ giao diện */
  var FACE =
    '<svg viewBox="0 0 64 64" aria-hidden="true">' +
    '<ellipse cx="32" cy="60" rx="21" ry="2.6" fill="#1E2A5A" opacity=".08"/>' +
    '<circle cx="32" cy="31" r="17" fill="#F7C948"/>' +
    '<path d="M30.5 14.5c.5-4 3.5-5.5 6-4.5" stroke="#1E2A5A" stroke-width="2.2" fill="none" stroke-linecap="round"/>' +
    '<g class="lid"><circle cx="26" cy="29.5" r="3.1" fill="#1E2A5A"/><circle cx="27.05" cy="28.38" r=".93" fill="#fff" opacity=".9"/></g>' +
    '<g class="lid"><circle cx="38" cy="29.5" r="3.1" fill="#1E2A5A"/><circle cx="39.05" cy="28.38" r=".93" fill="#fff" opacity=".9"/></g>' +
    '<path d="M6 37h52l-4.6 18.3A3.2 3.2 0 0 1 50.3 58H13.7a3.2 3.2 0 0 1-3.1-2.7z" fill="#1E2A5A"/>' +
    '<rect x="5" y="35.4" width="54" height="3.6" rx="1.8" fill="#34427A"/>' +
    '<ellipse cx="17" cy="36.4" rx="3.6" ry="2.6" fill="#F7C948"/><ellipse cx="47" cy="36.4" rx="3.6" ry="2.6" fill="#F7C948"/>' +
    '<rect x="25.5" y="45" width="13" height="5.5" rx="1.6" fill="#FFF6DA"/></svg>';
  function icon(d) {
    return '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="' + d + '"/></svg>';
  }
  var I = {
    send: icon("M5 12h13M13 6l6 6-6 6"),
    clip: icon("M20 11.5l-7.8 7.8a5 5 0 0 1-7.1-7.1l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4l7.8-7.8"),
    x: icon("M6 6l12 12M18 6L6 18"),
    wide: icon("M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"),
    narrow: icon("M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"),
    cal: icon("M4 7h16v13H4zM4 11h16M9 3v4M15 3v4"),
    cash: icon("M3 6h18v12H3zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5"),
    form: icon("M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6")
  };

  var CSS = [
    ":host{all:initial}",
    "*{box-sizing:border-box}",
    ".w{--navy:#2C3DA6;--navy-50:#eef0fb;--navy-100:#dfe3f7;--navy-700:#1f2d80;--ink:#1E2A5A;",
    "--sun-50:#fff8e1;--amber:#b45309;--amber-50:#fffbeb;--green:#047857;--green-50:#ecfdf5;",
    "--red:#b91c1c;--red-50:#fef2f2;--g50:#fafbfc;--g100:#f3f4f6;--g200:#e5e7eb;--g300:#d1d5db;",
    "--g500:#6b7280;--g600:#4b5563;--g700:#374151;--g900:#111827;",
    "font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;",
    "line-height:1.45;color:var(--g900);-webkit-font-smoothing:antialiased}",
    ".i{width:16px;height:16px;flex:none;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}",
    "button{font:inherit;cursor:pointer}",
    ":focus-visible{outline:2px solid var(--navy);outline-offset:2px}",
    ".fab{position:fixed;right:14px;bottom:calc(var(--kb,14px) + env(safe-area-inset-bottom,0px));",
    "width:80px;height:80px;background:transparent;border:0;display:grid;place-items:center;z-index:1045;padding:0;",
    "transition:transform .18s ease}",
    ".fab svg{width:80px;height:80px;filter:drop-shadow(0 6px 10px rgba(30,42,90,.28))}",
    ".fab:hover{transform:translateY(-3px)}.fab[aria-expanded=true] svg{filter:drop-shadow(0 6px 14px rgba(44,61,166,.45))}",
    ".lid{animation:blink 5.5s infinite;transform-box:fill-box;transform-origin:center}",
    "@keyframes blink{0%,96%,100%{transform:scaleY(1)}98%{transform:scaleY(.1)}}",
    ".pan{position:fixed;right:20px;bottom:calc(var(--kb,14px) + 90px + env(safe-area-inset-bottom,0px));",
    "width:372px;height:min(580px,calc(100vh - 120px));background:#fff;border:1px solid var(--g200);",
    "border-radius:18px;box-shadow:0 18px 48px -12px rgba(30,42,90,.28),0 4px 12px -4px rgba(30,42,90,.12);",
    "display:flex;flex-direction:column;overflow:hidden;z-index:1046}",
    ".pan.wide{top:0;right:0;bottom:0;height:auto;width:440px;border-radius:0;border-width:0 0 0 1px;",
    "box-shadow:-14px 0 40px -18px rgba(30,42,90,.35)}",
    ".hd{display:flex;align-items:center;gap:10px;padding:12px 14px;background:linear-gradient(180deg,var(--navy-50),#fff);border-bottom:1px solid var(--g100)}",
    ".hd .av{width:34px;height:34px}.hd .t{flex:1;min-width:0}.hd b{display:block;font-size:14px}",
    ".hd span{font-size:12px;color:var(--g500)}",
    ".ib{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;color:var(--g600);background:transparent;border:0;padding:0}",
    ".ib:hover{background:var(--g100)}",
    ".ms{flex:1;min-height:0;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:10px}",
    ".ms>*{flex-shrink:0}",
    ".m{max-width:86%;padding:9px 12px;border-radius:14px;font-size:13.5px;word-wrap:break-word}",
    ".u{align-self:flex-end;background:var(--navy);color:#fff;border-bottom-right-radius:4px}",
    ".bw{display:flex;align-items:flex-end;gap:7px;max-width:92%}",
    ".bw .ava{width:26px;height:26px;flex:none;border-radius:50%;background:var(--sun-50);display:grid;place-items:center}",
    ".bw .ava svg{width:22px;height:22px}",
    ".b{background:var(--g100);color:var(--g900);border-bottom-left-radius:4px;max-width:100%}",
    ".b.err{background:var(--red-50);color:var(--red)}",
    ".chips{display:flex;flex-wrap:wrap;gap:6px;padding-left:33px}",
    ".by{font-size:11px;line-height:1.3;color:var(--g500);padding-left:33px;margin-top:-6px}",
    ".chip{font-size:12.5px;font-weight:600;color:var(--navy);background:#fff;border:1px solid var(--navy-100);border-radius:999px;padding:5px 11px}",
    ".chip:hover{background:var(--navy-50)}",
    ".fl{align-self:flex-end;display:flex;flex-direction:column;gap:6px;max-width:86%}",
    ".f{display:flex;align-items:center;gap:9px;background:#fff;border:1px solid var(--g200);border-radius:11px;padding:7px 11px 7px 7px}",
    ".f .fi{width:30px;height:36px;border-radius:6px;background:var(--navy-50);color:var(--navy);font-size:11px;font-weight:800;display:grid;place-items:center;flex:none}",
    ".f b{display:block;font-size:12.5px;word-break:break-all}.f span{font-size:12px;color:var(--g500)}",
    ".f.bad span{color:var(--red)}",
    ".card{background:#fff;border:1px solid var(--g200);border-radius:12px;overflow:hidden;margin-left:33px}",
    ".ch{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--g100)}",
    ".ch b{font-size:13.5px;flex:1}.ch .i{color:var(--navy)}",
    ".pill{font-size:11.5px;font-weight:700;border-radius:999px;padding:2px 8px;background:var(--sun-50);color:#8a5a00}",
    ".pill.ok{background:var(--green-50);color:var(--green)}",
    ".kv{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;padding:10px 12px;margin:0;font-size:13px}",
    ".kv dt{color:var(--g500)}.kv dd{margin:0;text-align:right;font-weight:500;font-variant-numeric:tabular-nums;word-break:break-word}",
    ".kv dd small{display:block;font-weight:400;color:var(--g500);font-size:12px}",
    ".note{margin:0 12px 10px;padding:8px 10px;border-radius:9px;font-size:12.5px;background:var(--amber-50);color:var(--amber)}",
    ".note.bad{background:var(--red-50);color:var(--red)}.note.good{background:var(--green-50);color:var(--green)}",
    ".acts{display:flex;gap:8px;padding:10px 12px;background:var(--g50);border-top:1px solid var(--g100)}",
    ".btn{font-size:13px;font-weight:650;border-radius:9px;padding:8px 13px;border:1px solid transparent;display:inline-flex;align-items:center;justify-content:center;gap:6px;text-decoration:none}",
    ".btn.p{background:var(--navy);color:#fff;flex:1}.btn.p:hover{background:var(--navy-700)}",
    ".btn.s{background:#fff;color:var(--g700);border-color:var(--g300)}",
    ".btn[disabled]{opacity:.6;cursor:progress}",
    ".typing{display:inline-flex;gap:4px;padding:5px 2px}",
    ".typing i{width:6px;height:6px;border-radius:50%;background:var(--g500);animation:dot 1.2s infinite}",
    ".typing i:nth-child(2){animation-delay:.2s}.typing i:nth-child(3){animation-delay:.4s}",
    "@keyframes dot{0%,80%,100%{opacity:.3}40%{opacity:1}}",
    ".in{display:flex;align-items:center;gap:8px;border-top:1px solid var(--g200);padding:10px 12px 6px;background:#fff}",
    ".in textarea{flex:1;min-width:0;resize:none;border:1px solid var(--g200);background:var(--g50);border-radius:10px;",
    "padding:9px 12px;font:inherit;font-size:13.5px;color:var(--g900);height:40px;max-height:120px;line-height:20px;",
    "overflow-y:hidden;display:block;margin:0;box-sizing:border-box}",
    ".in textarea::placeholder{color:var(--g500);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
    ".in .ib{flex:none;height:40px;width:40px}",
    ".in textarea:focus{outline:none;border-color:var(--navy);background:#fff}",
    ".ib.send{background:var(--navy);color:#fff}.ib.send[disabled]{opacity:.5}",
    ".fine{font-size:11.5px;color:var(--g500);text-align:center;padding:2px 12px 10px;background:#fff;margin:0}",
    ".slow{display:block;font-size:12px;color:var(--g500);margin-top:4px}",
    ".drop{position:fixed;right:16px;bottom:calc(var(--kb,14px) + 90px);width:300px;height:190px;border:2px dashed var(--navy);",
    "border-radius:16px;background:rgba(238,240,251,.96);display:grid;place-items:center;text-align:center;z-index:1047;padding:16px}",
    ".drop svg{width:56px;height:56px}.drop b{display:block;color:var(--navy-700);font-size:15px;margin-top:6px}",
    ".drop span{font-size:12.5px;color:var(--g600)}.drop.on{background:var(--navy-50);box-shadow:0 0 0 6px rgba(44,61,166,.12)}",
    "[hidden]{display:none!important}",
    "@media (max-width:640px){.pan,.pan.wide{inset:0;width:auto;height:auto;border-radius:0;border:0}.drop{left:16px;right:16px;width:auto}}",
    "@media (prefers-reduced-motion:reduce){.lid,.typing i{animation:none}}"
  ].join("");

  function NAME() { return (S.boot && S.boot.name) || "eC Mate"; }

  function build(host) {
    var root = host.attachShadow({ mode: "open" });
    var nm = esc(NAME());
    root.innerHTML = "<style>" + CSS + "</style>" +
      '<div class="w">' +
      '<button class="fab" type="button" aria-label="Mở ' + nm + '" aria-expanded="false">' + FACE + "</button>" +
      '<section class="pan" role="dialog" aria-label="' + nm + '" hidden>' +
      '<header class="hd"><span class="av">' + FACE + '</span>' +
      '<div class="t"><b>' + nm + '</b><span>Trợ lý của bạn trên ERP</span></div>' +
      '<button class="ib wide" type="button" aria-label="Mở rộng">' + I.wide + "</button>" +
      '<button class="ib close" type="button" aria-label="Đóng">' + I.x + "</button></header>" +
      '<div class="ms" aria-live="polite"></div>' +
      '<form class="in"><button class="ib attach" type="button" aria-label="Đính kèm tệp">' + I.clip + "</button>" +
      '<input type="file" class="file" multiple hidden accept=".pdf,.png,.jpg,.jpeg,.webp">' +
      '<label hidden for="ec-khay-q">Nhắn cho ' + nm + '</label>' +
      '<textarea id="ec-khay-q" rows="1" placeholder="Nhắn cho ' + nm + '…"></textarea>' +
      '<button class="ib send" type="submit" aria-label="Gửi">' + I.send + "</button></form>" +
      '<div class="fine">AI chỉ soạn sẵn, bạn bấm mới gửi.</div></section>' +
      '<div class="drop" hidden><div>' + FACE + "<b>Thả tệp vào đây</b>" +
      "<span>Hoá đơn, báo giá, giấy khám · PDF hoặc ảnh, tối đa 7MB</span></div></div></div>";
    R.root = root;
    R.fab = root.querySelector(".fab");
    R.pan = root.querySelector(".pan");
    R.ms = root.querySelector(".ms");
    R.form = root.querySelector(".in");
    R.q = root.querySelector("textarea");
    R.file = root.querySelector(".file");
    R.wideBtn = root.querySelector(".wide");
    R.drop = root.querySelector(".drop");
    R.send = root.querySelector(".send");
  }

  /* ---------------------------------------------------------------- vẽ */
  function botHtml(inner, cls) {
    return '<div class="bw"><span class="ava">' + FACE + '</span><div class="m b' +
      (cls ? " " + cls : "") + '">' + inner + "</div></div>";
  }
  function msgHtml(m, idx) {
    if (m.role === "user") return '<div class="m u">' + esc(m.text) + "</div>";
    if (m.role === "bot") {
      var h = botHtml(mdLite(m.text), m.err ? "err" : "");
      if (m.by && !m.err) h += '<div class="by">Trả lời bởi ' + esc(modelLabel(m.by)) + "</div>";
      if (m.options && m.options.length) {
        h += '<div class="chips">' + m.options.map(function (o) {
          return '<button type="button" class="chip" data-say="' + esc(o) + '">' + esc(o) + "</button>";
        }).join("") + "</div>";
      }
      return h;
    }
    if (m.role === "files") {
      return '<div class="fl">' + m.items.map(function (f) {
        var ext = (f.name.split(".").pop() || "").slice(0, 4).toUpperCase();
        var st = f.err ? f.err : f.url ? "đã tải lên" : "đang tải…";
        return '<div class="f' + (f.err ? " bad" : "") + '"><span class="fi">' + esc(ext) +
          "</span><div><b>" + esc(f.name) + "</b><span>" + esc(st) + "</span></div></div>";
      }).join("") + "</div>";
    }
    if (m.role === "typing") {
      return '<div class="bw"><span class="ava">' + FACE + '</span><div class="m b"><span class="typing" aria-label="' +
        esc(NAME()) + ' đang nghĩ"><i></i><i></i><i></i></span>' +
        (m.slow ? '<span class="slow">AI đang chậm hơn thường lệ, bạn chờ mình chút nhé…</span>' : "") + "</div></div>";
    }
    if (m.role === "leave") return leaveCard(m, idx);
    if (m.role === "pay") return payCard(m, idx);
    return "";
  }
  function paint() {
    var h = S.msgs.map(msgHtml).join("");
    if (!S.msgs.length) h = greet();
    R.ms.innerHTML = h;
    R.ms.scrollTop = R.ms.scrollHeight;
    R.send.disabled = S.busy;
    R.pan.classList.toggle("wide", S.wide);
    R.wideBtn.innerHTML = S.wide ? I.narrow : I.wide;
    R.wideBtn.setAttribute("aria-label", S.wide ? "Thu nhỏ" : "Mở rộng");
  }
  function greet() {
    var b = S.boot || {};
    var opts = [];
    if (b.can_leave) opts.push("Cho mình xin nghỉ ngày mai");
    if (b.can_payment) opts.push("Tạo đề nghị thanh toán từ hoá đơn");
    opts.push("Tuần này team mình thế nào?");
    return botHtml("Chào " + esc(b.first_name || "bạn") + "! Mình là " + esc(NAME()) + ". Bạn cần xin nghỉ, " +
      "tạo phiếu hay hỏi gì cứ nhắn nhé.") +
      '<div class="chips">' + opts.map(function (o) {
        return '<button type="button" class="chip" data-say="' + esc(o) + '">' + esc(o) + "</button>";
      }).join("") + "</div>";
  }

  function leaveCard(m, idx) {
    var lv = m.leave, bal = "";
    if (S.leaveData && S.leaveData.types) {
      var t = S.leaveData.types.filter(function (x) { return x.name === lv.leave_type; })[0];
      if (t && !+t.lwp) bal = (+t.bal).toLocaleString("vi-VN") + " ngày";
    }
    var needDoc = lv.leave_type === "Sick Leave" && !firstUrl();
    var needOt = lv.leave_type === "Compensatory Off";
    var sent = m.state === "sent";
    var h = '<div class="card"><div class="ch">' + I.cal + "<b>Đơn nghỉ phép</b>" +
      '<span class="pill' + (sent ? " ok" : "") + '">' + (sent ? "Đã gửi" : "Nháp") + "</span></div>" +
      '<dl class="kv"><dt>Loại</dt><dd>' + esc(leaveLabel(lv.leave_type)) + "</dd>" +
      "<dt>Ngày</dt><dd>" + esc(leaveRange(lv)) + (sent && m.days ? "<small>" + esc(m.days) + " ngày</small>" : "") + "</dd>" +
      (lv.reason ? "<dt>Lý do</dt><dd>" + esc(lv.reason) + "</dd>" : "") +
      (bal && !sent ? "<dt>Phép còn lại</dt><dd>" + esc(bal) + "</dd>" : "") + "</dl>";
    if (m.error) h += '<div class="note bad">' + esc(m.error) + "</div>";
    else if (sent) h += '<div class="note good">Đơn ' + esc(m.name) + " đã gửi, đang chờ duyệt.</div>";
    else if (needDoc) h += '<div class="note">Nghỉ ốm cần giấy khám hoặc đơn thuốc — bạn thả tệp vào đây rồi bấm gửi.</div>';
    else if (needOt) h += '<div class="note">Nghỉ bù cần chọn ngày đã OT — bạn làm ở trang Nghỉ phép nhé.</div>';
    else if (lv.past && lv.leave_type !== "Sick Leave") h += '<div class="note">Chỉ nghỉ ốm mới được xin lùi ngày.</div>';
    h += '<div class="acts">';
    if (!sent && !needOt) {
      h += '<button type="button" class="btn p" data-act="leave-send" data-i="' + idx + '"' +
        (m.state === "sending" || needDoc ? " disabled" : "") + ">" + I.send +
        (m.state === "sending" ? "Đang gửi…" : "Gửi đơn") + "</button>";
    }
    h += '<a class="btn s" href="/ec-hr/leave">' + (sent ? "Xem đơn" : "Trang nghỉ phép") + "</a></div></div>";
    return h;
  }

  function payCard(m, idx) {
    var h = '<div class="card"><div class="ch">' + (m.code === "PAYMENT_REQUEST" ? I.cash : I.form) +
      "<b>" + esc(m.title || "Đề nghị thanh toán") + "</b>" +
      '<span class="pill">' + (m.draft ? "Đã tạo nháp" : "Nháp") + "</span></div>";
    if (m.state === "reading") {
      return h + '<div class="note">' + (m.urls && m.urls.length ?
        "Mình đang đọc tệp, thường mất 10–30 giây…" : "Mình đang điền phiếu từ câu của bạn…") +
        "</div></div>";
    }
    var keys = Object.keys(m.fields || {});
    if (keys.length) {
      h += '<dl class="kv">' + keys.map(function (k) {
        var src = (m.sources || {})[k];
        return "<dt>" + esc((m.labels || {})[k] || k) + "</dt><dd>" + esc(fmtValue(m.fields[k])) +
          (src ? "<small>“" + esc(String(src).slice(0, 80)) + "”</small>" : "") + "</dd>";
      }).join("") + "</dl>";
    }
    if (m.error) h += '<div class="note bad">' + esc(m.error) + "</div>";
    else if (m.missing && m.missing.length) {
      h += '<div class="note">Còn ' + m.missing.length + " ô bạn điền nốt trên phiếu: " +
        esc(m.missing.map(function (x) { return x.label; }).join(", ")) + ".</div>";
    } else if (m.probe && m.probe.ok === false && m.probe.message) {
      h += '<div class="note">' + esc(m.probe.message) + "</div>";
    }
    h += '<div class="acts">';
    if (keys.length && !m.error) {
      h += '<button type="button" class="btn p" data-act="pay-draft" data-i="' + idx + '"' +
        (m.state === "saving" ? " disabled" : "") + ">" +
        (m.state === "saving" ? "Đang tạo nháp…" : m.draft ? "Mở nháp để gửi" : "Tạo nháp & mở") + "</button>";
    }
    h += '<a class="btn s" href="' + esc(m.route || S.boot.payment_route || "/approvals/payment-request") +
      '">Tự điền</a></div></div>';
    if (m.by) h += '<div class="by">Điền bởi ' + esc(modelLabel(m.by)) + "</div>";
    return h;
  }

  /* ---------------------------------------------------------------- hành động */
  function push(m) { S.msgs.push(m); paint(); save(); return S.msgs.length - 1; }
  var slowTimer = null;
  function typing() {
    clearTimeout(slowTimer);
    var idx = push({ role: "typing" });
    slowTimer = setTimeout(function () {
      var m = S.msgs[idx];
      if (m && m.role === "typing") { m.slow = true; paint(); }
    }, 9000);
  }
  function dropTyping() {
    clearTimeout(slowTimer);
    S.msgs = S.msgs.filter(function (m) { return m.role !== "typing"; });
  }
  function firstUrl() {
    for (var i = S.msgs.length - 1; i >= 0; i--) {
      var m = S.msgs[i];
      if (m.role === "files") {
        for (var j = 0; j < m.items.length; j++) if (m.items[j].url) return m.items[j].url;
      }
    }
    return "";
  }
  function awaitingDoc() {
    return S.msgs.some(function (m) {
      return m.role === "leave" && m.state !== "sent" && m.leave && m.leave.leave_type === "Sick Leave";
    });
  }
  function pendingUrls() {
    return S.files.filter(function (f) { return f.url; }).map(function (f) { return f.url; });
  }

  function ask(text) {
    text = String(text || "").trim();
    var urls = pendingUrls();
    if ((!text && !urls.length) || S.busy) return;
    var hist = historyOf(S.msgs);
    if (text) push({ role: "user", text: text });
    S.busy = true; typing();
    var names = S.files.filter(function (f) { return f.url; }).map(function (f) { return f.name; });
    post(API.intent, { message: text, history: hist, page: location.pathname, files: names })
      .then(function (r) {
        dropTyping();
        r = r || {};
        if (r.action === "leave") return onLeave(r);
        if (r.action === "approval" || r.action === "payment_request") return onApproval(r, text, urls);
        if (r.action === "answer" && !r.needs_data && r.reply) return push({ role: "bot", text: r.reply, by: r.model });
        if (r.action === "answer") return onAnswer(text, hist);
        push({ role: "bot", text: r.reply || "Bạn nói rõ hơn giúp mình nhé.",
               options: r.options || [], err: r.action === "error", by: r.reply ? r.model : "" });
      })
      .catch(function (e) {
        dropTyping();
        push({ role: "bot", text: (e && e.message) || "AI đang bận, bạn thử lại sau nhé.", err: true });
      })
      .then(function () { S.busy = false; paint(); });
  }

  function onLeave(r) {
    push({ role: "bot", text: r.reply || "Mình soạn sẵn đơn rồi, bạn xem lại nhé.", by: r.model });
    var idx = push({ role: "leave", leave: r.leave, state: "draft" });
    if (!S.leaveData) {
      get(API.leaveData).then(function (d) { S.leaveData = d || {}; paint(); })
        .catch(function () { /* số dư là thứ thêm vào, lỗi thì thôi */ });
    }
    return idx;
  }

  function sendLeave(idx) {
    var m = S.msgs[idx];
    if (!m || m.state === "sending" || m.state === "sent") return;
    var lv = m.leave;
    m.state = "sending"; m.error = ""; paint();
    post(API.leaveApply, { leave_type: lv.leave_type, from_date: lv.from_date, to_date: lv.to_date,
                           half_day: lv.half_day ? 1 : 0, half_day_date: lv.half_day_date || "",
                           reason: lv.reason || "", attachment: lv.leave_type === "Sick Leave" ? firstUrl() : "" })
      .then(function (res) {
        m.state = "sent"; m.name = (res && res.name) || ""; m.days = res && res.days;
        push({ role: "bot", text: "Xong! Đơn **" + m.name + "** đã gửi, mình sẽ không làm gì thêm với đơn này." });
      })
      .catch(function (e) { m.state = "draft"; m.error = (e && e.message) || "Gửi không được."; })
      .then(function () { paint(); save(); });
  }

  /* Mọi form Approval Center (29/09): server đã chọn form trong danh sách người này tạo được
   * và kiểm lại ở suggest/create_draft. Không có tệp thì AI điền từ chính câu chat. */
  function onApproval(r, text, urls) {
    S.boot.labels = r.labels || {};
    S.wide = true;
    push({ role: "bot", text: r.reply || "Mình điền sẵn phiếu cho bạn nhé.", by: r.model });
    var idx = push({ role: "pay", state: "reading", code: r.approval_code || "PAYMENT_REQUEST",
                     title: r.approval_title || "", route: r.route,
                     labels: r.labels || {}, urls: urls });
    S.files = [];
    return post(API.suggest, { approval_code: r.approval_code, note: text, files: JSON.stringify(urls) })
      .then(function (res) {
        var m = S.msgs[idx];
        res = res || {};
        m.state = "ready";
        if (!res.refused && !res.error && !Object.keys(res.fields || {}).length) {
          m.error = "Mình chưa điền được ô nào từ câu này — bạn bấm Tự điền, hoặc kể rõ hơn nhé.";
        }
        if (res.refused || res.error) {
          m.error = res.refused === "refused_quota" ? "Bạn đã dùng hết lượt AI điền hộ hôm nay." :
            res.refused === "empty" ? "Mình không đọc được tệp nào — bạn thử tệp PDF hoặc ảnh rõ hơn nhé." :
            "AI đang bận, bạn thử lại sau ít phút.";
        }
        m.fields = res.fields || {}; m.sources = res.sources || {}; m.probe = res.probe || null;
        m.log = res.log || "";
        m.by = m.error ? "" : (res.model || "");
        (res.files_rejected || []).forEach(function (x) {
          push({ role: "bot", text: "Không đọc được " + x.file + ": " + x.message, err: true });
        });
      })
      .catch(function (e) { var m = S.msgs[idx]; m.state = "ready"; m.error = (e && e.message) || "Đọc tệp không được."; })
      .then(function () { paint(); });
  }

  function payDraft(idx) {
    var m = S.msgs[idx];
    if (!m || m.state === "saving") return;
    var route = m.route || S.boot.payment_route || "/approvals/payment-request";
    if (m.draft) { location.href = route + "?id=" + encodeURIComponent(m.draft); return; }
    var fields = {};
    Object.keys(m.fields || {}).forEach(function (k) { fields[k] = m.fields[k]; });
    // Tệp AI đã đọc chính là chứng từ của phiếu — giống chế độ hàng loạt của AI điền hộ.
    if (m.urls && m.urls[0]) fields.request_attachment = m.urls[0];
    m.state = "saving"; m.error = ""; paint();
    post(API.draft, { approval_code: m.code, fields: JSON.stringify(fields), log: m.log || "" })
      .then(function (res) {
        if (!res || !res.name) throw new Error("Không tạo được bản nháp.");
        m.draft = res.name; m.missing = res.missing || []; m.state = "ready";
        push({ role: "bot", text: "Đã tạo nháp **" + res.name + "**. Mình mở phiếu để bạn kiểm tra và bấm Gửi nhé." });
        setTimeout(function () { location.href = route + "?id=" + encodeURIComponent(res.name); }, 900);
      })
      .catch(function (e) { m.state = "ready"; m.error = (e && e.message) || "Không tạo được bản nháp."; })
      .then(function () { paint(); save(); });
  }

  function onAnswer(text, hist) {
    S.busy = true; typing();
    return post(API.chat, { message: text, history: JSON.stringify(hist) })
      .then(function (r) {
        dropTyping();
        if (r && r.success) push({ role: "bot", text: r.reply, by: r.model });
        else push({ role: "bot", text: (r && r.error) || "AI đang bận, bạn thử lại sau nhé.", err: true });
      })
      .catch(function (e) { dropTyping(); push({ role: "bot", text: (e && e.message) || "Có lỗi.", err: true }); });
  }

  function addFiles(list) {
    var arr = Array.prototype.slice.call(list || []);
    if (!arr.length) return;
    openPanel(true);
    var items = [];
    arr.forEach(function (file) {
      var why = fileRefuse(file, S.files);
      var it = { name: file.name || "tệp", size: file.size, url: "", err: why || "" };
      items.push(it);
      if (!why) S.files.push(it);
    });
    var idx = push({ role: "files", items: items });
    var jobs = items.filter(function (it) { return !it.err; }).map(function (it) {
      var file = arr.filter(function (f) { return f.name === it.name && f.size === it.size; })[0];
      return upload(file).then(function (url) { it.url = url; })
        .catch(function (e) { it.err = (e && e.message) || "tải lên không được"; });
    });
    Promise.all(jobs).then(function () {
      S.msgs[idx] = { role: "files", items: items };
      S.files = S.files.filter(function (f) { return f.url; });
      paint();
      // Đơn nghỉ ốm đang chờ giấy khám thì tệp này là để gửi kèm đơn, không phải câu hỏi mới.
      if (S.files.length && !R.q.value.trim() && !awaitingDoc()) ask("");
    });
  }

  /* ---------------------------------------------------------------- mở / đóng */
  function openPanel(wide) {
    S.open = true;
    if (wide) S.wide = true;
    R.pan.hidden = false;
    R.fab.setAttribute("aria-expanded", "true");
    paint(); save();
    setTimeout(function () { try { R.q.focus(); } catch (e) { /* noop */ } }, 30);
  }
  function closePanel() {
    S.open = false;
    R.pan.hidden = true;
    R.fab.setAttribute("aria-expanded", "false");
    save();
    try { R.fab.focus(); } catch (e) { /* noop */ }
  }

  /* Nâng nút lên trên thanh tab nhân sự ở điện thoại để không đè lên nhau. */
  function placeAboveTabbar(host) {
    var bar = document.querySelector(".ec-tabwrap");
    var h = 20;
    if (bar) {
      var cs = window.getComputedStyle(bar);
      if (cs.display !== "none" && cs.visibility !== "hidden") h = Math.round(bar.getBoundingClientRect().height) + 12;
    }
    host.style.setProperty("--kb", h + "px");
  }

  function wire(host) {
    R.fab.addEventListener("click", function () { if (S.open) closePanel(); else openPanel(false); });
    R.root.querySelector(".close").addEventListener("click", closePanel);
    R.wideBtn.addEventListener("click", function () { S.wide = !S.wide; paint(); save(); });
    R.form.addEventListener("submit", function (e) {
      e.preventDefault();
      var t = R.q.value; R.q.value = ""; R.q.style.height = ""; R.q.style.overflowY = "";
      ask(t);
    });
    R.q.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault(); R.form.requestSubmit ? R.form.requestSubmit() : R.form.dispatchEvent(new Event("submit"));
      }
    });
    R.q.addEventListener("input", function () {
      R.q.style.height = "40px";
      var h = Math.min(120, Math.max(40, R.q.scrollHeight + 2));
      R.q.style.height = h + "px";
      R.q.style.overflowY = R.q.scrollHeight > 118 ? "auto" : "hidden";
    });
    R.root.querySelector(".attach").addEventListener("click", function () { R.file.click(); });
    R.file.addEventListener("change", function () { addFiles(R.file.files); R.file.value = ""; });
    R.ms.addEventListener("click", function (e) {
      var t = e.target.closest ? e.target.closest("[data-say],[data-act]") : null;
      if (!t) return;
      if (t.getAttribute("data-say")) return ask(t.getAttribute("data-say"));
      var i = +t.getAttribute("data-i");
      if (t.getAttribute("data-act") === "leave-send") sendLeave(i);
      if (t.getAttribute("data-act") === "pay-draft") payDraft(i);
    });
    R.pan.addEventListener("keydown", function (e) { if (e.key === "Escape") closePanel(); });

    /* Vùng thả CHỈ ở góc Khay, không phủ cả trang: các ô tải tệp sẵn có của trang
     * (chứng từ, ký số) vẫn phải nhận tệp như cũ. */
    var depth = 0;
    function hasFiles(e) {
      var t = e.dataTransfer && e.dataTransfer.types;
      return !!t && Array.prototype.indexOf.call(t, "Files") >= 0;
    }
    window.addEventListener("dragenter", function (e) { if (hasFiles(e)) { depth++; R.drop.hidden = false; } });
    window.addEventListener("dragleave", function () { depth = Math.max(0, depth - 1); if (!depth) R.drop.hidden = true; });
    window.addEventListener("drop", function () { depth = 0; R.drop.hidden = true; });
    R.drop.addEventListener("dragover", function (e) { e.preventDefault(); R.drop.classList.add("on"); });
    R.drop.addEventListener("dragleave", function () { R.drop.classList.remove("on"); });
    R.drop.addEventListener("drop", function (e) {
      e.preventDefault(); R.drop.classList.remove("on");
      addFiles(e.dataTransfer && e.dataTransfer.files);
    });
    R.pan.addEventListener("dragover", function (e) { if (hasFiles(e)) e.preventDefault(); });
    R.pan.addEventListener("drop", function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); addFiles(e.dataTransfer.files);
    });
    window.addEventListener("resize", function () { placeAboveTabbar(host); });
  }

  function start() {
    if (!shouldRun(document, location.pathname)) return;
    get(API.boot).then(function (b) {
      if (!b || !b.enabled) return;
      S.boot = b;
      retireOldChat(document);
      load();
      var host = document.createElement("div");
      host.id = "ec-khay-host";
      document.body.appendChild(host);
      build(host);
      wire(host);
      placeAboveTabbar(host);
      paint();
      if (S.open) openPanel(false);
    }).catch(function () { /* không bật được thì im lặng: Khay là thứ thêm vào */ });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
