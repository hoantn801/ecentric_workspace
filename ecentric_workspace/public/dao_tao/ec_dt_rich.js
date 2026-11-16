// Copyright (c) 2026, eCentric and contributors
// ec_dt_rich.js -- hien noi dung bai hoc co dinh dang (Hoan 15/11: bai hoc phai truc quan).
// Noi dung van luu CHU THUAN; moi dong la mot khoi. KHONG nhan HTML: moi chu deu thoat ky tu,
// anh/video chi nhan link https, /files, /private/files hoac anh cua app (/assets/ecentric_workspace/).
// Bai cu khong co cu phap nao -> trang hien nhu truoc (D.richText).
//   ## Tieu de            -> muc lon (danh so, co muc luc)      ### Tieu de nho
//   > loi khuyen           !> luu y            ---  ke ngang
//   - / • gach dau dong    1. buoc danh so      **dam**
//   [anh] link | chu thich                       [video] link | chu thich | anh bia
//   [the] Tieu de | mo ta  (nhieu dong lien nhau -> luoi the)
//   [so] 47/54 | chu thich (nhieu dong lien nhau -> hang so lieu)
//   [sai] ...  [dung] ...  (dat lien nhau -> so sanh hai cot)
(function () {
  "use strict";
  var D = window.ECDt;
  var MARK = /^(##+ |> |!> |\[(anh|video|the|so|sai|dung)\] )/m;
  var GROUP = { the: 1, so: 1, sai: 1, dung: 1, li: 1, step: 1 };

  function safe(u) {
    u = String(u || "").trim();
    return (D.safeUrl(u) || u.indexOf("/assets/ecentric_workspace/") === 0) ? u : "";
  }
  function inline(s) {
    return D.richText(s).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  }
  function parts(s) { return s.split("|").map(function (x) { return x.trim(); }); }

  function classify(line) {
    var m;
    if (/^### /.test(line)) return { k: "h3", t: line.slice(4) };
    if (/^## /.test(line)) return { k: "h", t: line.slice(3) };
    if (/^!> /.test(line)) return { k: "warn", t: line.slice(3) };
    if (/^> /.test(line)) return { k: "tip", t: line.slice(2) };
    if (/^---+$/.test(line)) return { k: "hr" };
    if ((m = line.match(/^\[(anh|video|the|so|sai|dung)\] (.*)$/))) return { k: m[1], t: m[2] };
    if ((m = line.match(/^(?:- |• )(.*)$/))) return { k: "li", t: m[1] };
    if ((m = line.match(/^(\d{1,2})[.)] (.*)$/))) return { k: "step", n: m[1], t: m[2] };
    if (!line.trim()) return { k: "gap" };
    return { k: "p", t: line };
  }

  function block(k, items, sec) {
    var h = "";
    if (k === "the") {
      return '<div class="dt-rcards n' + (items.length % 3 === 0 ? 3 : (items.length % 2 === 0 ? 2 : 3)) + '">' + items.map(function (b) {
        var p = parts(b.t);
        return '<div class="dt-rcard"><b>' + inline(p[0]) + "</b>" + (p[1] ? "<span>" + inline(p.slice(1).join(" | ")) + "</span>" : "") + "</div>";
      }).join("") + "</div>";
    }
    if (k === "so") {
      return '<div class="dt-rstats">' + items.map(function (b) {
        var p = parts(b.t);
        return '<div class="dt-rstat"><b>' + D.esc(p[0]) + "</b><span>" + inline(p[1] || "") + "</span></div>";
      }).join("") + "</div>";
    }
    if (k === "sai" || k === "dung") {
      return items.map(function (b) {
        return '<div class="dt-rcmp ' + b.k + '"><small>' + (b.k === "sai" ? "✗ Chưa tốt" : "✓ Nên làm") + "</small>" + inline(b.t) + "</div>";
      }).join("");
    }
    if (k === "li") return "<ul class=\"dt-rlist\">" + items.map(function (b) { return "<li>" + inline(b.t) + "</li>"; }).join("") + "</ul>";
    if (k === "step") {
      return '<ol class="dt-rsteps">' + items.map(function (b) {
        return '<li><span class="dt-rn">' + D.esc(b.n) + "</span><div>" + inline(b.t) + "</div></li>";
      }).join("") + "</ol>";
    }
    var b = items[0];
    if (k === "h") return '<h2 class="dt-rh" id="dt-s' + sec + '"><span>' + sec + "</span>" + D.esc(b.t) + "</h2>";
    if (k === "h3") return '<h3 class="dt-rh3">' + inline(b.t) + "</h3>";
    if (k === "tip" || k === "warn") return '<div class="dt-rnote ' + k + '">' + inline(b.t) + "</div>";
    if (k === "hr") return '<hr class="dt-rhr">';
    if (k === "anh") {
      var a = parts(b.t), src = safe(a[0]);
      if (!src) return "";
      h = '<figure class="dt-rfig"><a href="' + D.esc(src) + '" target="_blank" rel="noopener"><img src="' + D.esc(src) + '" alt="' + D.esc(a[1] || "") + '" loading="lazy"></a>';
      return h + (a[1] ? "<figcaption>" + inline(a[1]) + "</figcaption>" : "") + "</figure>";
    }
    if (k === "video") {
      var v = parts(b.t), vs = safe(v[0]), poster = safe(v[2]);
      if (!vs) return "";
      h = /\.mp4(\?|$)/i.test(vs)
        ? '<video src="' + D.esc(vs) + '" controls playsinline preload="none"' + (poster ? ' poster="' + D.esc(poster) + '"' : "") + "></video>"
        : D.embedVideo(vs);
      return '<figure class="dt-rfig dt-rvid">' + h + (v[1] ? "<figcaption>▶ " + inline(v[1]) + "</figcaption>" : "") + "</figure>";
    }
    return "<p>" + inline(b.t) + "</p>";
  }

  function render(text) {
    text = String(text || "").replace(/\r\n/g, "\n");
    if (!MARK.test(text)) return '<div class="dt-body">' + D.richText(text) + "</div>";
    var lines = text.split("\n").map(classify), out = [], toc = [], sec = 0, i = 0;
    while (i < lines.length) {
      var b = lines[i], k = b.k, grp = [b];
      if (k === "gap") { i++; continue; }
      if (GROUP[k]) {
        var cmp = k === "sai" || k === "dung";
        while (i + 1 < lines.length && (lines[i + 1].k === k || (cmp && (lines[i + 1].k === "sai" || lines[i + 1].k === "dung")))) { grp.push(lines[++i]); }
        if (cmp) { out.push('<div class="dt-rcmps">' + block("sai", grp, sec) + "</div>"); i++; continue; }
      }
      if (k === "h") { sec++; toc.push(b.t); }
      out.push(block(k, grp, sec));
      i++;
    }
    var nav = toc.length >= 3 ? '<nav class="dt-rtoc" aria-label="Trong bài này"><b>Trong bài này</b>' + toc.map(function (t, j) {
      return '<a href="#dt-s' + (j + 1) + '"><span>' + (j + 1) + "</span>" + D.esc(t) + "</a>";
    }).join("") + "</nav>" : "";
    return '<div class="dt-rich">' + nav + out.join("") + "</div>";
  }

  window.ECDtRich = { render: render };
})();
