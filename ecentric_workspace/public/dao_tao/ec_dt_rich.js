// Copyright (c) 2026, eCentric and contributors
// ec_dt_rich.js -- noi dung bai hoc co dinh dang, trinh bay kieu bai viet nhu Tin noi bo
// (Hoan 18/11: chon phuong an A + danh sach viec co o tich cua phuong an B).
// Noi dung van luu CHU THUAN; moi dong la mot khoi. KHONG nhan HTML: moi chu deu thoat ky tu,
// anh/video chi nhan link https, /files, /private/files hoac anh cua app (/assets/ecentric_workspace/).
// Bai cu khong co cu phap nao -> hien nhu truoc (D.richText).
//   ## Tieu de (vao muc luc)   ### Tieu de nho   > meo   !> luu y   ---  ke ngang
//   - / • gach dau dong        1. buoc danh so   **dam**
//   [anh] link | chu thich     [video] link | chu thich | anh bia
//   [the] Ten | mo ta          (nhieu dong lien nhau -> bang dinh nghia)
//   [so] 47/54 | chu thich     (nhieu dong lien nhau -> hang so lieu)
//   [sai] ...  [dung] ...      (dat lien nhau -> bang so sanh)
//   [ ] viec can lam           (nhieu dong lien nhau -> danh sach co o tich, luu tren may nguoi doc)
(function () {
  "use strict";
  var D = window.ECDt;
  var MARK = /^(##+ |> |!> |\[ \] |\[(anh|video|the|so|sai|dung)\] )/m;
  var GROUP = { the: 1, so: 1, sai: 1, dung: 1, li: 1, step: 1, ck: 1 };

  function safe(u) {
    u = String(u || "").trim();
    return (D.safeUrl(u) || u.indexOf("/assets/ecentric_workspace/") === 0) ? u : "";
  }
  function inline(s) { return D.richText(s).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>"); }
  function parts(s) { return s.split("|").map(function (x) { return x.trim(); }); }

  function classify(line) {
    var m;
    if (/^### /.test(line)) return { k: "h3", t: line.slice(4) };
    if (/^## /.test(line)) return { k: "h", t: line.slice(3) };
    if (/^!> /.test(line)) return { k: "warn", t: line.slice(3) };
    if (/^> /.test(line)) return { k: "tip", t: line.slice(2) };
    if (/^---+$/.test(line)) return { k: "hr" };
    if (/^\[ \] /.test(line)) return { k: "ck", t: line.slice(4) };
    if ((m = line.match(/^\[(anh|video|the|so|sai|dung)\] (.*)$/))) return { k: m[1], t: m[2] };
    if ((m = line.match(/^(?:- |• )(.*)$/))) return { k: "li", t: m[1] };
    if ((m = line.match(/^(\d{1,2})[.)] (.*)$/))) return { k: "step", n: m[1], t: m[2] };
    if (!line.trim()) return { k: "gap" };
    return { k: "p", t: line };
  }

  function group(k, items, st) {
    if (k === "the") {
      return '<div class="dt-rdl">' + items.map(function (b) {
        var p = parts(b.t);
        return '<div class="dt-rdl-row"><b>' + inline(p[0]) + "</b><span>" + inline(p.slice(1).join(" | ")) + "</span></div>";
      }).join("") + "</div>";
    }
    if (k === "so") {
      return '<div class="dt-rfacts">' + items.map(function (b) {
        var p = parts(b.t);
        return '<div class="dt-rfact"><b>' + D.esc(p[0]) + "</b><span>" + inline(p[1] || "") + "</span></div>";
      }).join("") + "</div>";
    }
    if (k === "cmp") {
      return '<table class="dt-rcmp"><tbody>' + items.map(function (b) {
        var bad = b.k === "sai";
        return '<tr><th scope="row" class="' + (bad ? "bad" : "ok") + '">' + (bad ? "Chưa tốt" : "Nên làm") + "</th><td>" + inline(b.t) + "</td></tr>";
      }).join("") + "</tbody></table>";
    }
    if (k === "ck") {
      var g = st.ck++;
      return '<div class="dt-rck" data-ckg="' + g + '"><div class="dt-rck-hd"><b>Việc cần làm</b><span data-ckn>0/' + items.length + "</span></div>" +
        items.map(function (b, j) {
          return '<label class="dt-rck-row"><input type="checkbox" data-ck="' + g + "." + j + '"><span>' + inline(b.t) + "</span></label>";
        }).join("") + "</div>";
    }
    if (k === "li") return '<ul class="dt-rlist">' + items.map(function (b) { return "<li>" + inline(b.t) + "</li>"; }).join("") + "</ul>";
    return '<ol class="dt-rlist">' + items.map(function (b) { return "<li>" + inline(b.t) + "</li>"; }).join("") + "</ol>";
  }

  function one(b, st) {
    var k = b.k;
    if (k === "h") return '<h2 class="dt-rh" id="dt-s' + st.sec + '">' + D.esc(b.t) + "</h2>";
    if (k === "h3") return '<h3 class="dt-rh3">' + inline(b.t) + "</h3>";
    if (k === "tip" || k === "warn") return '<div class="dt-rnote ' + k + '">' + inline(b.t) + "</div>";
    if (k === "hr") return '<hr class="dt-rhr">';
    if (k === "anh") {
      var a = parts(b.t), src = safe(a[0]);
      if (!src) return "";
      if (!st.cover) st.cover = src;
      st.fig++;
      return '<figure class="dt-rfig"><a href="' + D.esc(src) + '" target="_blank" rel="noopener"><img src="' + D.esc(src) + '" alt="' + D.esc(a[1] || "") + '" loading="lazy"></a>' +
        (a[1] ? "<figcaption>Ảnh " + st.fig + ": " + inline(a[1]) + "</figcaption>" : "") + "</figure>";
    }
    if (k === "video") {
      var v = parts(b.t), vs = safe(v[0]), poster = safe(v[2]);
      if (!vs) return "";
      var h = /\.mp4(\?|$)/i.test(vs)
        ? '<video src="' + D.esc(vs) + '" controls playsinline preload="none"' + (poster ? ' poster="' + D.esc(poster) + '"' : "") + "></video>"
        : D.embedVideo(vs);
      return '<figure class="dt-rfig">' + h + (v[1] ? "<figcaption>Video: " + inline(v[1]) + "</figcaption>" : "") + "</figure>";
    }
    return "<p>" + inline(b.t) + "</p>";
  }

  // -> {html, toc: [{id, title}], cover: link anh dau tien | ""}
  function parse(text) {
    text = String(text || "").replace(/\r\n/g, "\n");
    if (!MARK.test(text)) return { html: '<div class="dt-body">' + D.richText(text) + "</div>", toc: [], cover: "" };
    var lines = text.split("\n").map(classify), out = [], toc = [], st = { sec: 0, fig: 0, ck: 0, cover: "" }, i = 0;
    while (i < lines.length) {
      var b = lines[i], k = b.k;
      if (k === "gap") { i++; continue; }
      if (GROUP[k]) {
        var cmp = k === "sai" || k === "dung", grp = [b];
        while (i + 1 < lines.length && (lines[i + 1].k === k || (cmp && (lines[i + 1].k === "sai" || lines[i + 1].k === "dung")))) { grp.push(lines[++i]); }
        out.push(group(cmp ? "cmp" : k, grp, st));
      } else {
        if (k === "h") { st.sec++; toc.push({ id: "dt-s" + st.sec, title: b.t }); }
        out.push(one(b, st));
      }
      i++;
    }
    return { html: '<div class="dt-rich">' + out.join("") + "</div>", toc: toc, cover: st.cover };
  }

  // O tich luu tren may nguoi doc (chi la tien loi ca nhan, khong phai du lieu cua cong ty).
  function bindChecks(box, key) {
    function store(k, v) { try { if (v) localStorage.setItem(k, "1"); else localStorage.removeItem(k); } catch (e) { /* bo qua */ } }
    function read(k) { try { return localStorage.getItem(k) === "1"; } catch (e) { return false; } }
    D.qsa(box, "[data-ckg]").forEach(function (g) {
      var boxes = D.qsa(g, "[data-ck]"), cnt = g.querySelector("[data-ckn]");
      function count() { cnt.textContent = boxes.filter(function (x) { return x.checked; }).length + "/" + boxes.length; }
      boxes.forEach(function (c) {
        var k = "ecdt-ck:" + key + ":" + c.dataset.ck;
        c.checked = read(k);
        c.parentNode.classList.toggle("done", c.checked);
        c.onchange = function () { store(k, c.checked); c.parentNode.classList.toggle("done", c.checked); count(); };
      });
      count();
    });
  }

  function render(text) {
    var r = parse(text);
    return r.html;
  }

  window.ECDtRich = { render: render, parse: parse, bindChecks: bindChecks };
})();
