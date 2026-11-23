// Copyright (c) 2026, eCentric and contributors
// ec_richtext.bundle.js - O SOAN NOI DUNG kieu soan mail, dung chung cho moi form (23/11/2026).
//
// Ly do: "Phe duyet dot xuat" thay cho viec xin CEO duyet qua mail -> noi dung can dinh dang nhu mail
// (dam / nghieng / gach chan / mau chu / to nen / danh sach / thut le / trich dan / bang / link) va DAN
// TU OUTLOOK / GMAIL / WORD / EXCEL ma giu duoc dinh dang (bang so lieu dan tu Excel van la bang).
//
//   var ed = EcRichText.mount(hostEl, { html, placeholder, onChange(html), onFiles(files) });
//   ed.getHTML() / ed.setHTML(html) / ed.focus()
//   EcRichText.clean(html)   -> HTML da loc (dung khi VE noi dung ra trang, phong thu lop 2)
//   EcRichText.toText(html)  -> chu tran (tom tat, dem ky tu)
//
// An toan: loc o client (dan vao + truoc khi ve) VA server loc lai khi luu (frappe sanitize_html).
// Chi giu the / thuoc tinh trong danh sach cho phep; style chi giu color / background-color voi gia
// tri mau hop le; link chi http(s) / mailto / duong dan noi bo. Anh dan vao KHONG nhung vao noi dung
// (tep rieng tu cua phieu) - giao cho onFiles de form tu dua vao "Tep dinh kem".
(function () {
  'use strict';
  if (window.EcRichText) return;

  var KEEP = { P: 'p', BR: 'br', DIV: 'p', H1: 'h3', H2: 'h3', H3: 'h3', H4: 'h4', H5: 'h4', H6: 'h4',
    STRONG: 'strong', B: 'strong', EM: 'em', I: 'em', U: 'u', S: 's', STRIKE: 's', DEL: 's',
    UL: 'ul', OL: 'ol', LI: 'li', A: 'a', BLOCKQUOTE: 'blockquote', HR: 'hr', SUB: 'sub', SUP: 'sup',
    TABLE: 'table', THEAD: 'thead', TBODY: 'tbody', TFOOT: 'tbody', TR: 'tr', TH: 'th', TD: 'td',
    SPAN: 'span', FONT: 'span', CODE: 'code', PRE: 'pre' };
  var DROP = /^(SCRIPT|STYLE|IFRAME|OBJECT|EMBED|META|LINK|TITLE|HEAD|SVG|MATH|NOSCRIPT|TEMPLATE|FORM|INPUT|BUTTON|SELECT|TEXTAREA|VIDEO|AUDIO|CANVAS|IMG|PICTURE|SOURCE|XML|O:P)$/;
  var COLOR_RE = /^(#[0-9a-f]{3,8}|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(,\s*[\d.]+\s*)?\)|[a-z]{3,20})$/i;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function safeUrl(u) {
    u = String(u || '').trim();
    if (!u) return '';
    if (/^(https?:\/\/|mailto:|\/(?!\/)|#)/i.test(u)) return u;
    if (/^[\w.-]+\.[a-z]{2,}(\/|$)/i.test(u)) return 'https://' + u;
    return '';
  }
  function pickColor(style, prop) {
    var m = new RegExp('(?:^|;)\\s*' + prop + '\\s*:\\s*([^;!]+)', 'i').exec(style || '');
    var v = m && m[1].trim();
    if (!v || !COLOR_RE.test(v) || /^(inherit|initial|transparent|windowtext|auto|currentcolor|black|#000|#000000|white|#fff|#ffffff)$/i.test(v)) return '';
    return v;
  }

  // HTML bat ky -> HTML trong danh sach cho phep. Tra { html, droppedImages }.
  function sanitize(html, doc) {
    doc = doc || document;
    var tpl = doc.createElement('template');
    tpl.innerHTML = String(html || '')
      .replace(/<!--[\s\S]*?-->/g, '')                         // comment Word / Outlook
      .replace(/<\/?(o|w|v|m):[^>]*>/gi, '');                  // the namespace Office
    var dropped = 0;
    function walk(src, dst) {
      Array.prototype.slice.call(src.childNodes).forEach(function (n) {
        if (n.nodeType === 3) { dst.appendChild(doc.createTextNode(n.nodeValue)); return; }
        if (n.nodeType !== 1) return;
        var tag = n.nodeName.toUpperCase();
        if (tag === 'IMG' || tag === 'PICTURE') { dropped++; return; }
        if (DROP.test(tag)) return;
        var style = n.getAttribute('style') || '';
        // Google Docs boc ca bai trong <b style="font-weight:normal">
        if (tag === 'B' && /font-weight:\s*normal/i.test(style)) { walk(n, dst); return; }
        var keep = KEEP[tag];
        if (!keep) { walk(n, dst); return; }
        if (keep === 'span') {
          var color = pickColor(style, 'color') || (tag === 'FONT' && COLOR_RE.test(n.getAttribute('color') || '') ? n.getAttribute('color') : '');
          var bg = pickColor(style, 'background-color') || pickColor(style, 'background');
          var bold = /font-weight:\s*(bold|[6-9]00)/i.test(style), ital = /font-style:\s*italic/i.test(style);
          var und = /text-decoration[^;]*underline/i.test(style);
          var host = dst;
          if (bold) { var b = doc.createElement('strong'); host.appendChild(b); host = b; }
          if (ital) { var i = doc.createElement('em'); host.appendChild(i); host = i; }
          if (und) { var u = doc.createElement('u'); host.appendChild(u); host = u; }
          if (color || bg) {
            var sp = doc.createElement('span');
            sp.setAttribute('style', (color ? 'color:' + color + ';' : '') + (bg ? 'background-color:' + bg + ';' : ''));
            host.appendChild(sp); host = sp;
          }
          walk(n, host);
          return;
        }
        var out = doc.createElement(keep);
        if (keep === 'a') {
          var href = safeUrl(n.getAttribute('href'));
          if (!href) { walk(n, dst); return; }
          out.setAttribute('href', href);
          out.setAttribute('target', '_blank');
          out.setAttribute('rel', 'noopener');
        }
        if (keep === 'td' || keep === 'th') {
          ['colspan', 'rowspan'].forEach(function (a) {
            var v = parseInt(n.getAttribute(a) || '', 10);
            if (v > 1 && v < 50) out.setAttribute(a, String(v));
          });
        }
        if (keep === 'p' || keep === 'li' || keep === 'td' || keep === 'th') {
          var al = /text-align:\s*(center|right)/i.exec(style) || /^(center|right)$/i.exec(n.getAttribute('align') || '');
          if (al) out.setAttribute('style', 'text-align:' + al[1].toLowerCase());
          var bgc = (keep === 'td' || keep === 'th') && pickColor(style, 'background-color');
          if (bgc) out.setAttribute('style', (out.getAttribute('style') ? out.getAttribute('style') + ';' : '') + 'background-color:' + bgc);
        }
        walk(n, out);
        if (keep === 'p' && !out.childNodes.length) return;   // <div></div> rong cua Outlook
        dst.appendChild(out);
      });
    }
    var box = doc.createElement('div');
    walk(tpl.content || tpl, box);
    return { html: box.innerHTML, droppedImages: dropped };
  }
  function clean(html) { return sanitize(html).html; }
  function toText(html) {
    var d = document.createElement('div');
    d.innerHTML = clean(String(html || '').replace(/<\/(p|li|h3|h4|tr|blockquote)>/gi, '$&\n').replace(/<br\s*\/?>/gi, '\n'));
    return (d.textContent || '').replace(/ /g, ' ').replace(/\n{3,}/g, '\n\n').trim();
  }
  function isEmpty(html) { return !toText(html); }

  var COLORS = ['#c0392b', '#d35400', '#b7950b', '#1e8449', '#1f618d', '#6c3483', '#566573'];
  var MARKS = ['#fff3a3', '#ffd6d6', '#d4f5dd', '#d6e8ff'];
  var TB = [
    ['undo', '↶', 'Hoàn tác (Ctrl+Z)'], ['redo', '↷', 'Làm lại (Ctrl+Y)'], '|',
    ['bold', '<b>B</b>', 'Đậm (Ctrl+B)'], ['italic', '<i>I</i>', 'Nghiêng (Ctrl+I)'],
    ['underline', '<u>U</u>', 'Gạch chân (Ctrl+U)'], ['strikeThrough', '<s>S</s>', 'Gạch ngang'], '|',
    ['color', '<span class="ecrt-a">A</span>', 'Màu chữ'], ['mark', '<span class="ecrt-hl">ab</span>', 'Tô nền'], '|',
    ['insertUnorderedList', '•≡', 'Danh sách chấm'], ['insertOrderedList', '1.≡', 'Danh sách số'],
    ['outdent', '⇤', 'Giảm thụt lề'], ['indent', '⇥', 'Tăng thụt lề'], ['quote', '❝', 'Trích dẫn'], '|',
    ['link', '🔗', 'Chèn link (Ctrl+K)'], ['table', '▦', 'Chèn bảng'], ['removeFormat', 'T̸', 'Xóa định dạng']
  ];

  function mount(host, opts) {
    opts = opts || {};
    host.classList.add('ecrt');
    host.innerHTML = '<div class="ecrt-tb" role="toolbar" aria-label="Định dạng nội dung">' + TB.map(function (t) {
      if (t === '|') return '<span class="ecrt-sep"></span>';
      return '<button type="button" class="ecrt-b" data-ecrt="' + t[0] + '" title="' + esc(t[2]) + '" aria-label="' + esc(t[2]) + '">' + t[1] + '</button>';
    }).join('') + '<div class="ecrt-pop" hidden></div></div>'
      + '<div class="ecrt-ed" contenteditable="true" role="textbox" aria-multiline="true" spellcheck="true" data-ph="'
      + esc(opts.placeholder || '') + '"></div>';
    var ed = host.querySelector('.ecrt-ed'), pop = host.querySelector('.ecrt-pop');
    ed.innerHTML = clean(opts.html || '');
    var lastRange = null;
    function changed() { ed.classList.toggle('is-empty', isEmpty(ed.innerHTML)); if (opts.onChange) opts.onChange(ed.innerHTML); }
    function save() {
      var sel = window.getSelection && window.getSelection();
      if (sel && sel.rangeCount && ed.contains(sel.getRangeAt(0).commonAncestorContainer)) lastRange = sel.getRangeAt(0).cloneRange();
    }
    function restore() {
      ed.focus();
      var sel = window.getSelection && window.getSelection();
      if (sel && lastRange) { sel.removeAllRanges(); sel.addRange(lastRange); }
    }
    function exec(cmd, val) { try { document.execCommand(cmd, false, val); } catch (e) { /* trinh duyet cu */ } }
    try { document.execCommand('styleWithCSS', false, true); } catch (e) { /* bo qua */ }
    ['keyup', 'mouseup', 'blur'].forEach(function (ev) { ed.addEventListener(ev, save); });
    ed.addEventListener('input', changed);
    function closePop() { pop.hidden = true; pop.innerHTML = ''; }
    function swatches(kind) {
      var list = kind === 'color' ? COLORS : MARKS;
      pop.innerHTML = list.map(function (c) {
        return '<button type="button" class="ecrt-sw" data-sw="' + c + '" style="background:' + c + '" title="' + c + '"></button>';
      }).join('') + '<button type="button" class="ecrt-sw ecrt-sw-x" data-sw="" title="Bỏ màu">✕</button>';
      pop.setAttribute('data-kind', kind); pop.hidden = false;
    }
    function askLink() {
      var hasText = lastRange && !lastRange.collapsed;
      pop.innerHTML = '<input class="ecrt-in" data-ln-url placeholder="https://… hoặc /approvals/…" autocomplete="off">'
        + (hasText ? '' : '<input class="ecrt-in" data-ln-text placeholder="Chữ hiển thị" autocomplete="off">')
        + '<button type="button" class="ecrt-ok" data-ln-ok>Chèn</button>';
      pop.setAttribute('data-kind', 'link'); pop.hidden = false;
      var u = pop.querySelector('[data-ln-url]'); if (u) u.focus();
    }
    host.querySelector('.ecrt-tb').addEventListener('mousedown', function (ev) {
      if (!ev.target.closest('input')) ev.preventDefault();          // giu vung chon trong o soan
    });
    host.querySelector('.ecrt-tb').addEventListener('click', function (ev) {
      var sw = ev.target.closest('[data-sw]');
      if (sw) {
        restore();
        var kind = pop.getAttribute('data-kind'), c = sw.getAttribute('data-sw');
        if (kind === 'color') exec('foreColor', c || '#1f2937');
        else exec('hiliteColor', c || 'transparent');
        closePop(); changed(); return;
      }
      if (ev.target.closest('[data-ln-ok]')) {
        var url = safeUrl((pop.querySelector('[data-ln-url]') || {}).value);
        if (!url) { var i = pop.querySelector('[data-ln-url]'); if (i) i.classList.add('bad'); return; }
        var t = pop.querySelector('[data-ln-text]');
        restore();
        if (t) exec('insertHTML', '<a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(t.value.trim() || url) + '</a>&nbsp;');
        else { exec('createLink', url); }
        closePop(); changed(); return;
      }
      var b = ev.target.closest('[data-ecrt]');
      if (!b) return;
      var k = b.getAttribute('data-ecrt');
      if (k === 'color' || k === 'mark') { if (!pop.hidden && pop.getAttribute('data-kind') === k) closePop(); else { save(); swatches(k); } return; }
      if (k === 'link') { save(); askLink(); return; }
      closePop();
      restore();
      if (k === 'quote') exec('formatBlock', '<blockquote>');
      else if (k === 'table') exec('insertHTML', '<table><tbody><tr><th><br></th><th><br></th><th><br></th></tr>'
        + '<tr><td><br></td><td><br></td><td><br></td></tr><tr><td><br></td><td><br></td><td><br></td></tr></tbody></table><p><br></p>');
      else if (k === 'removeFormat') { exec('removeFormat'); exec('unlink'); }
      else exec(k);
      changed();
    });
    ed.addEventListener('keydown', function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && (ev.key === 'k' || ev.key === 'K')) { ev.preventDefault(); save(); askLink(); }
      if (ev.key === 'Escape') closePop();
    });
    ed.addEventListener('paste', function (ev) {
      var cd = ev.clipboardData; if (!cd) return;
      var files = Array.prototype.slice.call(cd.files || []).filter(function (f) { return /^image\//.test(f.type || ''); });
      var html = cd.getData('text/html');
      if (files.length && !html) { ev.preventDefault(); if (opts.onFiles) opts.onFiles(files); return; }
      ev.preventDefault();
      if (html) {
        var res = sanitize(html);
        exec('insertHTML', res.html);
        if (res.droppedImages && opts.onDroppedImages) opts.onDroppedImages(res.droppedImages);
      } else {
        var text = cd.getData('text/plain') || '';
        exec('insertHTML', text.split(/\r?\n\r?\n/).map(function (p) {
          return '<p>' + esc(p).replace(/\r?\n/g, '<br>') + '</p>';
        }).join(''));
      }
      changed();
    });
    ed.addEventListener('drop', function (ev) {
      var files = ev.dataTransfer && Array.prototype.slice.call(ev.dataTransfer.files || []);
      if (files && files.length) { ev.preventDefault(); if (opts.onFiles) opts.onFiles(files); }
    });
    changed();
    return {
      el: ed,
      getHTML: function () { return clean(ed.innerHTML); },
      setHTML: function (h) { ed.innerHTML = clean(h || ''); changed(); },
      focus: function () { ed.focus(); }
    };
  }

  window.EcRichText = { mount: mount, clean: clean, sanitize: sanitize, toText: toText, isEmpty: isEmpty, safeUrl: safeUrl };
})();
