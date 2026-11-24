// Copyright (c) 2026, eCentric and contributors
//
// Khoi "Tom tat" cuoi form phe duyet - phuong an A1 "Luoi can bang" (Hoan chot 24/11/2026, mockup
// APPROVAL_FORM_SUMMARY_V2_2026-11-24.html). Mot ban dung chung cho moi form (A65 muc 3): trang chi
// KHAI cau hinh (nhom, truong, kind), khong tu dung HTML tom tat nua.
//
// Bo cuc: dai so chinh mong 1 hang (so tien o mep phai) -> moi nhom la mot luoi o dong (nhan tren,
// gia tri duoi), so o moi hang chenh nhau toi da 1 (5 -> 3+2, 7 -> 4+3) nen khong con o le trong ->
// luong duyet 1 dong -> thanh duoi: con thieu ben trai (bam la cuon toi o + dat con tro), nut ben phai.
//
// CHI HIEN THI: khong goi API, khong doi du lieu, khong khoa nut. Nut Gui giu nguyen logic cua trang.
//
// GIAO KEO VOI TRANG
//   Markup (trong formCardsHTML / render, thay cho the "Tom tat" cu + hang nut):
//     EcSummary.cardHTML("offr-summary", actionsHTML)
//   Ve lai (trong renderSummary, goi moi lan go):
//     EcSummary.render($("offr-summary"), {
//       draft: state.draft,                    // de dem MOI o co dau sao cua form (ke ca o khong hien o day)
//       by: "Nguyen A",                       // nguoi gui (dong phu o dau khoi), tuy chon
//       resubmit: false,                       // true: dang sua de gui lai -> cau o thanh duoi doi theo
//       hero:   [F, F, F],                     // 1-4 o so chinh; o kind "money" tu dat o mep phai
//       groups: [{ title: "Ung vien", fields: [F, F, ...] },
//                { title: "Cac dot", lines: [["Dot 1", 1000000], ...], total: "Tong cong" }],
//       flow:   "Line manager → HR → CEO" | ["Line manager", "HR", "CEO"],
//       after:  ["Finance lap UNC"]           // buoc sau duyet, tuy chon
//     });
//   F = { label, value, field, kind, req, currency }  hoac viet tat  [label, value, field, kind]
//     field : ten data-fld / data-model cua o nhap -> link "con thieu" nhay toi o; va neu `req`
//             khong khai thi BAT BUOC = nhan cua o do co dau sao (<span class="req">) -> khong khai
//             lap danh sach bat buoc, luon khop voi form.
//     kind  : "money" (so, dau cham, can phai, ₫) | "date" (YYYY-MM-DD -> dd/mm/yyyy) |
//             "long" (doan chu dai, chiem tron hang) | bo trong = chu thuong.
//     F = null / false -> bo qua (tien cho truong theo dieu kien).
// Moi chuoi (nhan, gia tri, ten nhom, buoc duyet, nguoi gui) deu esc() o day.
(function () {
  "use strict";
  if (window.EcSummary) return;

  var KEY_RE = /^[A-Za-z0-9_-]+$/;
  var MAX_LINKS = 6;

  function esc(s) {
    return (s == null ? "" : String(s)).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function text(v) {
    if (v == null) return "";
    if (Array.isArray(v)) return v.filter(function (x) { return x != null && String(x).trim() !== ""; }).join(", ");
    return String(v);
  }
  // "—" la cach cac trang cu ghi "chua co" -> cung tinh la trong.
  function isEmpty(v) { var t = text(v).trim(); return t === "" || t === "—"; }

  // ---- so tien --------------------------------------------------------------------------------
  // Nhan so JS (25000000, 20.5), chuoi so JS ("25000000", "20.5") hoac chuoi da phan cach kieu Viet
  // ("25.000.000", "1.234,5"). Chuoi khac (vd "Theo HD") -> null, hien nguyen van.
  function toNumber(v) {
    if (typeof v === "number") return isFinite(v) ? v : null;
    var s = text(v).trim().replace(/\s+/g, "");
    if (!s) return null;
    if (/^-?\d{1,3}(\.\d{3})+(,\d+)?$/.test(s)) return Number(s.replace(/\./g, "").replace(",", "."));
    if (/^-?\d+(\.\d+)?$/.test(s)) return Number(s);
    if (/^-?\d+,\d+$/.test(s)) return Number(s.replace(",", "."));
    return null;
  }
  function fmtNumber(n) {
    var neg = n < 0, r = Math.round(Math.abs(n) * 100) / 100;
    var ip = Math.floor(r), fp = Math.round((r - ip) * 100);
    var s = String(ip).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    if (fp) s += "," + (fp < 10 ? "0" + fp : String(fp).replace(/0$/, ""));
    return (neg && (ip || fp) ? "-" : "") + s;
  }
  function curText(c) { return (!c || /^(vnd|đ|₫)$/i.test(String(c).trim())) ? "₫" : String(c); }
  function moneyHTML(v, currency) {
    var n = toNumber(v);
    if (n == null) return esc(text(v));
    return '<span class="ec-sum-num">' + fmtNumber(n) + '<span class="ec-sum-cur">&nbsp;' + esc(curText(currency)) + "</span></span>";
  }
  function fmtDate(v) {
    var s = text(v), m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(s);
    if (!m) return s;
    return m[3] + "/" + m[2] + "/" + m[1] + (m[4] ? (" " + m[4] + ":" + m[5]) : "");
  }

  // ---- chia hang can bang -------------------------------------------------------------------
  // n o vao cac hang toi da `max` o; so o moi hang chenh nhau <= 1; moi hang luon kin 12 cot.
  // Tra ve mang span (tren luoi 12 cot) theo thu tu o. 5,4 -> [4,4,4,6,6]; 7,4 -> [3,3,3,3,4,4,4].
  function rowSpans(n, max) {
    var out = [];
    n = Math.max(0, Math.floor(Number(n) || 0)); max = Math.min(4, Math.max(1, Math.floor(Number(max) || 1)));
    if (!n) return out;
    var rows = Math.ceil(n / max), base = Math.floor(n / rows), extra = n % rows;
    for (var r = 0; r < rows; r++) {
      var c = base + (r < extra ? 1 : 0);
      for (var i = 0; i < c; i++) out.push(12 / c);
    }
    return out;
  }
  // max <= 4 -> moi hang 1..4 o -> span 12/6/4/3, luon nguyen tren luoi 12 cot.
  function spanStyle(s4, s2) { return "--ec-sum-s4:" + s4 + ";--ec-sum-s2:" + s2; }

  // ---- truong & trang thai ------------------------------------------------------------------
  function findField(field, root) {
    if (!field || !KEY_RE.test(String(field))) return null;
    root = root || document;
    return root.querySelector('[data-fld="' + field + '"]') || root.querySelector('[data-model="' + field + '"]');
  }
  // O dang an (form an theo dieu kien) -> khong tinh. jsdom/trinh duyet: [hidden] hoac display:none ghi tay.
  function isHidden(el) {
    return !!(el.closest && el.closest('[hidden],[style*="display:none"],[style*="display: none"]'));
  }
  // Bat buoc khi nhan cua o nhap co dau sao (<span class="req">) va o dang hien.
  function domRequired(field, root) {
    if (!field || !KEY_RE.test(String(field))) return false;
    var box = (root || document).querySelector('[data-fld="' + field + '"]');
    if (!box || isHidden(box)) return false;
    return !!box.querySelector("label .req");
  }
  // Moi o bat buoc dang hien cua form ma cau hinh tom tat KHONG liet ke: van tinh vao "Bat buoc x/y" va
  // "Con thieu" (doc gia tri tu cfg.draft theo ten data-fld) -> "✓ Du thong tin" khong bao gio noi doi
  // khi con o co sao bi trong ma tom tat khong hien.
  function extraRequired(root, draft, known) {
    if (!draft || !root || !root.querySelectorAll) return [];
    var out = [];
    root.querySelectorAll("[data-fld]").forEach(function (box) {
      var k = box.getAttribute("data-fld");
      if (!k || !KEY_RE.test(k) || known[k] || k.charAt(0) === "_" || isHidden(box)) return;
      var lab = box.querySelector("label");
      if (!lab || !lab.querySelector(".req")) return;
      known[k] = 1;
      var t = lab.cloneNode(true);
      t.querySelectorAll(".req").forEach(function (r) { r.remove(); });
      out.push({ label: (t.textContent || k).replace(/\s+/g, " ").trim(), value: draft[k], field: k, kind: "", req: true,
        empty: isEmpty(draft[k]), extra: true });
    });
    return out;
  }
  function norm(f, root) {
    if (Array.isArray(f)) f = { label: f[0], value: f[1], field: f[2], kind: f[3] };
    if (!f || typeof f !== "object") return null;
    var o = { label: text(f.label), value: f.value, field: (f.field && KEY_RE.test(String(f.field))) ? String(f.field) : "",
      kind: f.kind || "", currency: f.currency };
    o.req = (f.req != null) ? !!f.req : domRequired(o.field, root);
    o.empty = isEmpty(f.value);
    return o;
  }
  function model(cfg, root) {
    cfg = cfg || {};
    root = root || cfg.root || (typeof document !== "undefined" ? document : null);
    var hero = (cfg.hero || []).map(function (f) { return norm(f, root); }).filter(Boolean);
    var groups = (cfg.groups || []).filter(Boolean).map(function (g) {
      if (g.lines) return { title: text(g.title), lines: g.lines.filter(Boolean), total: g.total, currency: g.currency };
      return { title: text(g.title), fields: (g.fields || []).map(function (f) { return norm(f, root); }).filter(Boolean) };
    }).filter(function (g) { return g.lines ? g.lines.length : g.fields.length; });
    var all = hero.slice();
    groups.forEach(function (g) { if (g.fields) all = all.concat(g.fields); });
    var known = {};
    all.forEach(function (f) { if (f.field) known[f.field] = 1; });
    all = all.concat(extraRequired(root, cfg.draft, known));
    var req = all.filter(function (f) { return f.req; });
    var miss = req.filter(function (f) { return f.empty; });
    return { hero: hero, groups: groups, all: all, req: req, miss: miss, done: req.length - miss.length, ok: !miss.length };
  }
  function status(cfg, root) {
    var m = model(cfg, root);
    return { required: m.req.length, done: m.done, ok: m.ok,
      missing: m.miss.map(function (f) { return { label: f.label, field: f.field }; }) };
  }

  // ---- luong duyet --------------------------------------------------------------------------
  // Nhan chuoi "A → B → C (theo cấu hình)" cua trang cu hoac mang. "Tạo yêu cầu" khong phai buoc duyet.
  function flowSteps(flow) {
    var note = "", steps;
    if (Array.isArray(flow)) steps = flow.map(text);
    else {
      var s = text(flow).trim();
      var m = /\s*\((theo [^)]*)\)\s*$/i.exec(s);
      if (m) { note = m[1]; s = s.slice(0, m.index); }
      steps = s ? s.split(/\s*(?:→|->)\s*/) : [];
    }
    steps = steps.map(function (x) { return x.trim(); }).filter(function (x) { return x && !/^tạo yêu cầu$/i.test(x); });
    return { steps: steps, note: note };
  }

  // ---- HTML ---------------------------------------------------------------------------------
  function valueHTML(f) {
    if (f.empty) return f.req ? "Cần nhập" : "—";
    if (f.kind === "money") return moneyHTML(f.value, f.currency);
    if (f.kind === "date") return esc(fmtDate(f.value));
    return esc(text(f.value));
  }
  function stateCls(f) { return f.empty ? (f.req ? " is-miss" : " is-none") : ""; }
  function fieldAttr(f) { return f.field ? (' data-sum-f="' + esc(f.field) + '"') : ""; }
  function cellHTML(f, style) {
    return '<div class="ec-sum-c' + (f.kind === "money" ? " is-num" : "") + (f.kind === "long" ? " is-long" : "") + stateCls(f) + '"'
      + ' style="' + style + '"' + fieldAttr(f) + '><div class="ec-sum-lb">' + esc(f.label) + "</div>"
      + '<div class="ec-sum-vl"' + (f.empty && !f.req ? ' title="Chưa nhập"' : "") + ">" + valueHTML(f) + "</div></div>";
  }
  function heroHTML(hero) {
    if (!hero.length) return "";
    // so tien luon o mep phai; so o le -> o "dan dau" (so tien, neu khong co thi o dau) chiem tron hang o man hep
    var list = hero.filter(function (f) { return f.kind !== "money"; }).concat(hero.filter(function (f) { return f.kind === "money"; }));
    var lead = list.length % 2 === 1 ? (list.filter(function (f) { return f.kind === "money"; })[0] || list[0]) : null;
    return '<div class="ec-sum-hero" style="--ec-sum-hn:' + list.length + '">' + list.map(function (f) {
      return '<div class="ec-sum-hc' + (f.kind === "money" ? " is-num" : "") + (f === lead ? " is-lead" : "") + stateCls(f) + '"' + fieldAttr(f) + ">"
        + '<div class="ec-sum-lb">' + esc(f.label) + '</div><div class="ec-sum-vl">' + valueHTML(f) + "</div></div>";
    }).join("") + "</div>";
  }
  function linesHTML(g) {
    var sum = 0, rows = g.lines.map(function (l) {
      var lb = Array.isArray(l) ? l[0] : l.label, v = Array.isArray(l) ? l[1] : l.value;
      var n = toNumber(v); if (n != null) sum += n;
      return "<tr><td>" + esc(text(lb)) + '</td><td class="r">' + (isEmpty(v) ? "—" : moneyHTML(v, g.currency)) + "</td></tr>";
    }).join("");
    var foot = "";
    if (g.total) {
      var t = (typeof g.total === "object") ? g.total : { label: g.total === true ? "Tổng cộng" : g.total, value: sum };
      foot = '<tfoot><tr><td>' + esc(text(t.label)) + '</td><td class="r">' + moneyHTML(t.value == null ? sum : t.value, g.currency) + "</td></tr></tfoot>";
    }
    return '<table class="ec-sum-lines"><tbody>' + rows + "</tbody>" + foot + "</table>";
  }
  function groupHTML(g) {
    var cells, count;
    if (g.lines) {
      cells = '<div class="ec-sum-c is-table" style="--ec-sum-s4:12;--ec-sum-s2:12">' + linesHTML(g) + "</div>";
      count = g.lines.length + " dòng";
    } else {
      var sh = g.fields.filter(function (f) { return f.kind !== "long"; });
      var lg = g.fields.filter(function (f) { return f.kind === "long"; });
      var s4 = rowSpans(sh.length, 4), s2 = rowSpans(sh.length, 2);
      cells = sh.map(function (f, i) { return cellHTML(f, spanStyle(s4[i], s2[i])); }).join("")
        + lg.map(function (f) { return cellHTML(f, spanStyle(12, 12)); }).join("");
      count = g.fields.length + " mục";
    }
    return '<div class="ec-sum-g"><div class="ec-sum-gt">' + esc(g.title) + "<small>" + esc(count) + "</small></div>"
      + '<div class="ec-sum-cells">' + cells + "</div></div>";
  }
  function flowHTML(cfg) {
    var fl = flowSteps(cfg.flow), after = (cfg.after || []).map(text).filter(Boolean);
    if (!fl.steps.length && !after.length) return "";
    // dau "›" di kem buoc phia sau -> khong bao gio treo o cuoi dong khi xuong hang
    function sep(i) { return i ? '<span class="ec-sum-sep" aria-hidden="true">›</span>' : ""; }
    var h = fl.steps.map(function (s, i) {
      return '<span class="ec-sum-stp">' + sep(i) + '<span class="ec-sum-chip"><b>' + (i + 1) + "</b>" + esc(s) + "</span></span>";
    }).join("");
    if (after.length) h += '<span class="ec-sum-stp"><span class="ec-sum-afl">Sau duyệt</span></span>'
      + after.map(function (a, i) { return '<span class="ec-sum-stp">' + sep(i) + '<span class="ec-sum-chip is-after">' + esc(a) + "</span></span>"; }).join("");
    if (fl.note) h += '<span class="ec-sum-note">' + esc(fl.note) + "</span>";
    return '<div class="ec-sum-flow"><span class="ec-sum-fl">Luồng duyệt</span><div class="ec-sum-chips">' + h + "</div></div>";
  }
  function progressHTML(m) {
    if (!m.req.length) return "";
    var pct = Math.round((m.done * 100) / m.req.length);
    return '<div class="ec-sum-prog' + (m.ok ? " is-ok" : "") + '" aria-label="Đã điền ' + m.done + "/" + m.req.length + ' mục bắt buộc">'
      + "<span>" + (m.ok ? "✓ Đủ " : "Bắt buộc ") + m.done + "/" + m.req.length + "</span>"
      + '<span class="ec-sum-bar" aria-hidden="true"><i style="width:' + pct + '%"></i></span></div>';
  }
  function html(cfg, root) {
    cfg = cfg || {};
    var m = model(cfg, root);
    var sub = cfg.sub != null ? text(cfg.sub) : ((cfg.by && !isEmpty(cfg.by) ? ("Người gửi: " + text(cfg.by) + " · ") : "") + "Rà lại trước khi gửi");
    return '<div class="ec-sum-h"><div class="ec-sum-ht"><h3>Tóm tắt</h3><p>' + esc(sub) + "</p></div>" + progressHTML(m) + "</div>"
      + '<div class="ec-sum-body">' + heroHTML(m.hero) + m.groups.map(groupHTML).join("") + flowHTML(cfg) + "</div>";
  }
  function messageHTML(cfg, root) {
    cfg = cfg || {};
    var m = model(cfg, root);
    if (!m.ok) {
      var shown = m.miss.slice(0, MAX_LINKS);
      var links = shown.map(function (f) {
        return f.field ? '<button type="button" class="ec-sum-link" data-sum-goto="' + esc(f.field) + '">' + esc(f.label) + "</button>"
          : "<span>" + esc(f.label) + "</span>";
      }).join(", ");
      var more = m.miss.length > shown.length ? (" và " + (m.miss.length - shown.length) + " mục khác") : "";
      return '<span class="ec-sum-msg-bad">Còn thiếu ' + m.miss.length + " mục: " + links + more + "</span>";
    }
    var first = flowSteps(cfg.flow).steps[0];
    if (cfg.resubmit) return '<span class="ec-sum-msg-ok">✓ Đủ thông tin bắt buộc, có thể gửi lại.</span>';
    if (first) return '<span class="ec-sum-msg-ok">✓ Đủ thông tin. Gửi xong, <b>' + esc(first) + "</b> nhận phiếu đầu tiên.</span>";
    return m.req.length ? '<span class="ec-sum-msg-ok">✓ Đủ thông tin bắt buộc, có thể gửi.</span>' : "";
  }

  // Khung tinh dat san trong markup trang: phan noi dung (id cu cua trang) + thanh duoi chua hang nut
  // cua trang (giu nguyen id/handler). id="ec-sum" (moi trang mot khoi) de kieu dung chung thang kieu
  // #ec-xxx-root .actions cua trang - cung cach #ec-fh cua dau trang.
  function cardHTML(id, actionsHTML) {
    return '<section class="ec-sum" id="ec-sum" aria-label="Tóm tắt"><div class="ec-sum-main" id="' + esc(id) + '"></div>'
      + '<div class="ec-sum-f"><div class="ec-sum-msg" aria-live="polite"></div>' + (actionsHTML || "") + "</div></section>";
  }
  function render(host, cfg) {
    if (!host) return null;
    // pham vi tim o nhap: khung form chua khoi tom tat (khong quet modal / tab khac)
    var root = (cfg && cfg.root) || (host.closest && host.closest('[class*="formwrap"]')) || host.ownerDocument || document;
    host.innerHTML = html(cfg, root);
    var card = host.closest ? host.closest(".ec-sum") : null;
    var msg = card ? card.querySelector(".ec-sum-msg") : null;
    var mh = messageHTML(cfg, root);
    if (msg) { msg.innerHTML = mh; card.classList.toggle("is-ok", !!(cfg && model(cfg, root).ok)); }
    else if (mh) host.insertAdjacentHTML("beforeend", '<div class="ec-sum-msg">' + mh + "</div>");
    return status(cfg, root);
  }

  // ---- nhay toi o con thieu -----------------------------------------------------------------
  var CTL = 'input:not([type="hidden"]):not([disabled]),select:not([disabled]),textarea:not([disabled]),[contenteditable="true"],button:not([disabled])';
  function goto(field, root) {
    var box = findField(field, root);
    if (!box) return false;
    var ctl = (box.matches && box.matches("input,select,textarea")) ? box : box.querySelector(CTL);
    try { box.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (_e) { if (box.scrollIntoView) box.scrollIntoView(); }
    if (ctl && ctl.focus) { try { ctl.focus({ preventScroll: true }); } catch (_f) { ctl.focus(); } }
    box.classList.remove("ec-sum-flash");
    void box.offsetWidth;
    box.classList.add("ec-sum-flash");
    setTimeout(function () { box.classList.remove("ec-sum-flash"); }, 1600);
    return true;
  }
  document.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest("[data-sum-goto]") : null;
    if (!b) return;
    e.preventDefault();
    goto(b.getAttribute("data-sum-goto"));
  });

  window.EcSummary = {
    cardHTML: cardHTML, render: render, html: html, messageHTML: messageHTML, status: status, goto: goto,
    rowSpans: rowSpans, fmtNumber: fmtNumber, toNumber: toNumber, fmtDate: fmtDate, flowSteps: flowSteps, esc: esc
  };
})();
