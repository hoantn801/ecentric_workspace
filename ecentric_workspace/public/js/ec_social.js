// Copyright (c) 2026, eCentric and contributors
// ec_social.js - Bang tin + Cau lac bo (/bang-tin, /bang-tin/cau-lac-bo[/<slug>], /bang-tin/bai/<ten>,
// /bang-tin/quan-ly). Mockup v2, PO duyet 04/10/2026.
//
// Server ve san moi the bai / khoi binh luan. File nay chi:
//   1. o dang bai: tu gian, doc anh (base64), chon nguoi (khen / gan ten / nguoi phu trach), gui;
//   2. the bai: tim, binh luan / loi chuc (mo, gui, tra loi, sua, xoa, an), tham gia su kien, menu
//      (sua / xoa / bao cao / an), xem anh lon, "Xem bai cu hon";
//   3. CLB: tham gia / roi, de xuat CLB; trang kiem duyet: giu / an bai, duyet CLB, doi nguoi phu trach.
// Moi thao tac tren the bai: server tra lai HTML ve san -> thay khoi. JS khong co quy tac nghiep vu.
// Goi server qua window.ecApi (CSRF tuoi). Loi -> thong bao tieng Viet.
(function () {
  'use strict';

  var API = 'ecentric_workspace.social.api.';
  var IMG_MAX = 6;
  var IMG_BYTES = 10 * 1024 * 1024;

  // ------------------------------------------------------------------ tien ich ------
  var toastTimer = null;
  function toast(msg, isErr) {
    var t = document.getElementById('esc-toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.toggle('esc-toast-err', !!isErr);
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, isErr ? 6000 : 2600);
  }

  function errMsg(e) {
    if (!e) return 'Có lỗi, thử lại sau.';
    if (e.csrf) return 'Phiên đăng nhập vừa đổi. Tải lại trang (Ctrl+Shift+R) rồi thử lại.';
    var m = e.body && e.body.message;
    if (m && typeof m === 'object' && m.message) return String(m.message);
    if (e.status === 413) return 'Ảnh quá lớn. Bớt ảnh hoặc chọn ảnh nhỏ hơn.';
    if (e.status === 403) return 'Bạn không có quyền làm việc này.';
    if (e.status === 404) return 'Không tìm thấy (có thể bài đã bị xoá).';
    if (!e.status) return 'Mất kết nối. Kiểm tra mạng rồi thử lại.';
    return 'Có lỗi, thử lại sau.';
  }

  function call(method, args, get) {
    if (!window.ecApi) return Promise.reject(new Error('Trang chưa tải xong, thử lại sau giây lát.'));
    var fn = get ? window.ecApi.get : window.ecApi.post;
    return fn(API + method, args || {}).then(function (res) {
      if (res && res.success) return res.data;
      throw new Error((res && res.message) || 'Có lỗi, thử lại sau.');
    }, function (e) {
      throw new Error(errMsg(e));
    });
  }

  function busy(el, on) {
    if (!el) return;
    el.disabled = !!on;
    if (on) el.setAttribute('aria-busy', 'true'); else el.removeAttribute('aria-busy');
  }

  function fromHTML(html) {
    var t = document.createElement('template');
    t.innerHTML = String(html || '').trim();
    return t.content;
  }

  function grow(ta) {
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight + 2, 320) + 'px';
  }

  function cardOf(el) { return el.closest('[data-esc-post],[data-esc-moment-card],[data-esc-hr]'); }

  // "Bam lan nua de ..." thay cho hop thoai confirm (khong chan trang).
  function armed(btn, label) {
    if (btn.getAttribute('data-armed') === '1') return true;
    var old = btn.textContent;
    btn.setAttribute('data-armed', '1');
    btn.textContent = label;
    setTimeout(function () { btn.removeAttribute('data-armed'); btn.textContent = old; }, 4000);
    return false;
  }

  // ------------------------------------------------------------------ chon nguoi ------
  var peoplePromise = null;
  function people() {
    if (!peoplePromise) {
      peoplePromise = call('people', {}, true).catch(function (e) { peoplePromise = null; throw e; });
    }
    return peoplePromise;
  }

  function fold(s) {
    return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd');
  }

  function Picker(box) {
    var single = box.getAttribute('data-single') === '1';
    var chosen = [];
    var input = document.createElement('input');
    input.type = 'text';
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-label', single ? 'Tìm một đồng nghiệp' : 'Tìm đồng nghiệp để gắn tên');
    input.placeholder = 'Gõ tên đồng nghiệp…';
    var list = document.createElement('ul');
    list.className = 'esc-pick-list';
    list.setAttribute('role', 'listbox');
    list.id = 'esc-pl-' + Math.random().toString(36).slice(2, 8);
    input.setAttribute('aria-controls', list.id);
    list.hidden = true;
    box.appendChild(input);
    box.appendChild(list);
    var active = -1;
    var shown = [];

    function renderTags() {
      box.querySelectorAll('.esc-tag').forEach(function (t) { t.remove(); });
      chosen.forEach(function (p) {
        var tag = document.createElement('span');
        tag.className = 'esc-tag';
        tag.textContent = p.name;
        var x = document.createElement('button');
        x.type = 'button';
        x.setAttribute('aria-label', 'Bỏ ' + p.name);
        x.textContent = '×';
        x.addEventListener('click', function () {
          chosen = chosen.filter(function (c) { return c.user !== p.user; });
          renderTags();
          input.focus();
        });
        tag.appendChild(x);
        box.insertBefore(tag, input);
      });
      input.hidden = single && chosen.length > 0;
    }
    function close() { list.hidden = true; input.setAttribute('aria-expanded', 'false'); active = -1; }
    function pick(p) {
      if (single) chosen = [p];
      else if (!chosen.some(function (c) { return c.user === p.user; })) chosen.push(p);
      input.value = '';
      close();
      renderTags();
      if (!input.hidden) input.focus();
      box.dispatchEvent(new Event('change', { bubbles: true }));
    }
    function render() {
      var q = fold(input.value.trim());
      people().then(function (all) {
        shown = all.filter(function (p) {
          return !chosen.some(function (c) { return c.user === p.user; }) && (!q || fold(p.name).indexOf(q) >= 0);
        }).slice(0, 8);
        list.textContent = '';
        shown.forEach(function (p, i) {
          var li = document.createElement('li');
          li.setAttribute('role', 'option');
          li.id = list.id + '-' + i;
          li.setAttribute('aria-selected', i === active ? 'true' : 'false');
          var b = document.createElement('span');
          b.textContent = p.name;
          var s = document.createElement('small');
          s.textContent = p.dept || '';
          li.appendChild(b);
          li.appendChild(s);
          li.addEventListener('mousedown', function (ev) { ev.preventDefault(); pick(p); });
          list.appendChild(li);
        });
        if (!shown.length) {
          var none = document.createElement('li');
          none.textContent = q ? 'Không thấy ai tên như vậy.' : 'Gõ tên để tìm.';
          none.setAttribute('aria-disabled', 'true');
          list.appendChild(none);
        }
        list.hidden = false;
        input.setAttribute('aria-expanded', 'true');
        input.setAttribute('aria-activedescendant', active >= 0 ? list.id + '-' + active : '');
      }, function (e) { toast(e.message, true); });
    }
    input.addEventListener('input', function () { active = -1; render(); });
    input.addEventListener('focus', render);
    input.addEventListener('blur', function () { setTimeout(close, 120); });
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowDown') { ev.preventDefault(); active = Math.min(active + 1, shown.length - 1); render(); }
      else if (ev.key === 'ArrowUp') { ev.preventDefault(); active = Math.max(active - 1, 0); render(); }
      else if (ev.key === 'Enter') { ev.preventDefault(); if (shown[active >= 0 ? active : 0]) pick(shown[active >= 0 ? active : 0]); }
      else if (ev.key === 'Escape') { close(); }
      else if (ev.key === 'Backspace' && !input.value && chosen.length) { chosen.pop(); renderTags(); }
    });
    box._picker = {
      users: function () { return chosen.map(function (c) { return c.user; }); },
      clear: function () { chosen = []; renderTags(); }
    };
    return box._picker;
  }
  function picker(box) { return box && (box._picker || Picker(box)); }

  // ------------------------------------------------------------------ o dang bai ------
  // Anh dien thoai 4-5 MB x 6 tam gui base64 trong MOT POST se vuot gioi han nginx (413): thu nho
  // ngay tren trinh duyet (canh dai <= 1600px, JPEG). Server van ve lai + bo EXIF lan nua.
  var SIDE = 1600;
  var TOTAL_MAX = 20 * 1024 * 1024;
  function readFile(f) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () { resolve({ name: f.name, data: r.result }); };
      r.onerror = function () { reject(new Error('Không đọc được ảnh ' + f.name)); };
      r.readAsDataURL(f);
    });
  }
  function shrink(f) {
    if (/gif$/i.test(f.type || f.name)) return readFile(f);
    return readFile(f).then(function (got) {
      return new Promise(function (resolve) {
        var img = new Image();
        img.onload = function () {
          var k = Math.min(1, SIDE / Math.max(img.naturalWidth, img.naturalHeight));
          if (k >= 1 && f.size < 1.5 * 1024 * 1024) { resolve(got); return; }
          var c = document.createElement('canvas');
          c.width = Math.round(img.naturalWidth * k);
          c.height = Math.round(img.naturalHeight * k);
          c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
          resolve({ name: f.name.replace(/\.[^.]+$/, '') + '.jpg', data: c.toDataURL('image/jpeg', 0.85) });
        };
        img.onerror = function () { resolve(got); };   // trinh duyet khong ve duoc (HEIC...): gui nguyen, server bao loi
        img.src = got.data;
      });
    });
  }
  function totalSize(list) { return list.reduce(function (n, x) { return n + (x.data ? x.data.length : 0); }, 0); }

  function initComposer(form) {
    var body = form.querySelector('[data-esc-cp-body]');
    var send = form.querySelector('[data-esc-cp-send]');
    var fileIn = form.querySelector('[data-esc-cp-file]');
    var imgsBox = form.querySelector('[data-esc-cp-imgs]');
    var files = [];
    var sending = false;

    function panel(key) { return form.querySelector('[data-esc-panel="' + key + '"]'); }
    function isOn(key) { var b = form.querySelector('[data-esc-tool="' + key + '"]'); return b && b.getAttribute('aria-pressed') === 'true'; }
    function ready() {
      var has = body.value.trim().length > 0 || files.length > 0 || (isOn('event') && form.elements.event_title && form.elements.event_title.value.trim());
      send.disabled = sending || !has;
    }
    function renderImgs() {
      imgsBox.textContent = '';
      imgsBox.hidden = !files.length;
      files.forEach(function (f, i) {
        var w = document.createElement('div');
        w.className = 'esc-cp-img';
        var img = document.createElement('img');
        img.src = f.data;
        img.alt = '';
        var x = document.createElement('button');
        x.type = 'button';
        x.textContent = '×';
        x.setAttribute('aria-label', 'Bỏ ảnh ' + (i + 1));
        x.addEventListener('click', function () { files.splice(i, 1); renderImgs(); ready(); });
        w.appendChild(img);
        w.appendChild(x);
        imgsBox.appendChild(w);
      });
    }

    body.addEventListener('input', function () { grow(body); ready(); });
    form.addEventListener('input', ready);
    fileIn.addEventListener('change', function () {
      var picked = Array.prototype.slice.call(fileIn.files || []);
      fileIn.value = '';
      if (files.length + picked.length > IMG_MAX) { toast('Tối đa ' + IMG_MAX + ' ảnh mỗi bài.', true); picked = picked.slice(0, IMG_MAX - files.length); }
      var big = picked.filter(function (f) { return f.size > IMG_BYTES; });
      if (big.length) toast('Ảnh lớn quá 10 MB: ' + big.map(function (f) { return f.name; }).join(', '), true);
      Promise.all(picked.filter(function (f) { return f.size <= IMG_BYTES; }).map(shrink)).then(function (got) {
        var keep = [];
        got.forEach(function (g) { if (totalSize(files.concat(keep, [g])) <= TOTAL_MAX) keep.push(g); });
        if (keep.length < got.length) toast('Ảnh quá nặng, chỉ thêm được ' + keep.length + '/' + got.length + ' ảnh.', true);
        files = files.concat(keep);
        renderImgs();
        ready();
      }, function (e) { toast(e.message, true); });
    });
    form.querySelectorAll('[data-esc-tool]').forEach(function (b) {
      b.addEventListener('click', function () {
        var key = b.getAttribute('data-esc-tool');
        var on = b.getAttribute('aria-pressed') !== 'true';
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
        var p = panel(key);
        if (p) p.hidden = !on;
        if (on && key === 'kudos' && isOn('event')) form.querySelector('[data-esc-tool="event"]').click();
        var pk = p && p.querySelector('[data-esc-pick]');
        if (on && pk) { picker(pk); var i = pk.querySelector('input'); if (i && !i.hidden) i.focus(); }
        if (on && key === 'event' && form.elements.event_title) form.elements.event_title.focus();
        ready();
      });
    });

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (sending || send.disabled) return;
      var data = { body: body.value, files: files };
      var club = form.getAttribute('data-esc-club') || (form.elements.club && form.elements.club.value) || '';
      if (club) data.club = club;
      if (form.elements.dept_only && form.elements.dept_only.checked) data.dept_only = 1;
      if (isOn('kudos')) {
        var to = picker(panel('kudos').querySelector('[data-esc-pick]')).users();
        if (!to.length) { toast('Chọn đồng nghiệp bạn muốn khen.', true); return; }
        data.kudos_to = to[0];
        var v = form.querySelector('input[name="kudos_value"]:checked');
        if (v) data.kudos_value = v.value;
      }
      if (isOn('tags')) data.mentions = picker(panel('tags').querySelector('[data-esc-pick]')).users();
      if (isOn('event')) {
        data.event_title = form.elements.event_title.value;
        data.event_start = form.elements.event_start.value;
        data.event_place = form.elements.event_place.value;
      }
      sending = true;
      busy(send, true);
      send.textContent = 'Đang đăng…';
      call('create', { data: JSON.stringify(data) }).then(function (r) {
        var feed = document.querySelector('[data-esc-feed]');
        if (feed) feed.insertBefore(fromHTML(r.html), feed.firstChild);
        form.reset();
        body.value = '';
        grow(body);
        files = [];
        renderImgs();
        form.querySelectorAll('[data-esc-tool][aria-pressed="true"]').forEach(function (b) { b.click(); });
        form.querySelectorAll('[data-esc-pick]').forEach(function (p) { if (p._picker) p._picker.clear(); });
        toast('Đã đăng lên Bảng tin.');
      }, function (e) { toast(e.message, true); }).then(function () {
        sending = false;
        busy(send, false);
        send.textContent = 'Đăng';
        ready();
      });
    });
    ready();
  }

  // ------------------------------------------------------------------ binh luan ------
  function setCount(card, n) {
    var t = card.querySelector('[data-esc-cmt-toggle]');
    if (!t) return;
    var moment = card.getAttribute('data-esc-kind') === 'moment';
    t.setAttribute('data-esc-cmt-count', n);
    t.textContent = n ? n + (moment ? ' lời chúc' : ' bình luận') : '';
  }

  function loadComments(card, focus) {
    var wrap = card.querySelector('[data-esc-cmts-wrap]');
    if (!wrap) return;
    wrap.hidden = false;
    var post = card.getAttribute('data-esc-post');
    var done = function () {
      var ta = wrap.querySelector('[data-esc-cmt-in]');
      if (focus && ta) ta.focus();
    };
    if (wrap.getAttribute('data-esc-loaded') === '1' || !post) { done(); return; }
    wrap.textContent = 'Đang tải…';
    call('comments', { post: post }, true).then(function (r) {
      wrap.textContent = '';
      wrap.appendChild(fromHTML(r.html));
      wrap.setAttribute('data-esc-loaded', '1');
      setCount(card, r.count);
      done();
    }, function (e) { wrap.textContent = ''; toast(e.message, true); });
  }

  function swapComments(card, r, keepFrom) {
    var wrap = card.querySelector('[data-esc-cmts-wrap]');
    var draft = '';
    var main = wrap.querySelector('[data-esc-cmt-form] [data-esc-cmt-in]');
    if (main && main !== keepFrom) draft = main.value;
    wrap.textContent = '';
    wrap.appendChild(fromHTML(r.html));
    wrap.setAttribute('data-esc-loaded', '1');
    if (r.post) card.setAttribute('data-esc-post', r.post);
    setCount(card, r.count);
    var ta = wrap.querySelector('[data-esc-cmt-form] [data-esc-cmt-in]');
    if (ta && draft) { ta.value = draft; grow(ta); }
  }

  var cmtBusy = false;
  function cmtCall(card, method, args, src) {
    if (cmtBusy) return Promise.resolve();
    cmtBusy = true;
    if (src) src.readOnly = true;
    return call(method, args).then(function (r) { swapComments(card, r, src); }, function (e) {
      toast(e.message, true);
      if (src) src.readOnly = false;
      throw e;
    }).then(function () { cmtBusy = false; }, function () { cmtBusy = false; });
  }

  function sendComment(ta) {
    var card = cardOf(ta);
    var text = ta.value.trim();
    if (!text) return;
    var reply = ta.closest('[data-esc-reply-box]');
    var args = { content: text };
    var post = card.getAttribute('data-esc-post');
    if (post) args.post = post;
    else args.moment = card.getAttribute('data-esc-moment-card') || '';
    if (reply) args.parent = reply.getAttribute('data-esc-reply-box');
    var edit = ta.closest('[data-esc-edit-cmt]');
    if (edit) {
      cmtCall(card, 'comment_edit', { comment: edit.getAttribute('data-esc-edit-cmt'), content: text }, ta);
      return;
    }
    cmtCall(card, 'comment_add', args, ta).then(function () {
      var again = card.querySelector('[data-esc-cmt-form] [data-esc-cmt-in]');
      if (again && !reply) again.focus();
    }, function () {});
  }

  function cmtAction(btn) {
    var act = btn.getAttribute('data-esc-cmt-act');
    var item = btn.closest('[data-esc-cmt]');
    var card = cardOf(btn);
    var name = item.getAttribute('data-esc-cmt');
    if (act === 'like') return cmtCall(card, 'comment_like', { comment: name }).catch(function () {});
    if (act === 'hide') return cmtCall(card, 'comment_hide', { comment: name, hidden: 1 }).catch(function () {});
    if (act === 'unhide') return cmtCall(card, 'comment_hide', { comment: name, hidden: 0 }).catch(function () {});
    if (act === 'delete') {
      if (!armed(btn, 'Bấm lần nữa để xoá')) return;
      return cmtCall(card, 'comment_delete', { comment: name }).catch(function () {});
    }
    if (act === 'reply') {
      var root = item.parentNode.closest('[data-esc-cmt]') || item;
      var body = root.querySelector('.esc-cm-b');
      var box = body.querySelector(':scope > [data-esc-reply-box]');
      if (!box) {
        box = document.createElement('div');
        box.className = 'esc-cm esc-cm-rep';
        box.setAttribute('data-esc-reply-box', root.getAttribute('data-esc-cmt'));
        var ta = document.createElement('textarea');
        ta.rows = 1;
        ta.maxLength = 2000;
        ta.setAttribute('data-esc-cmt-in', '');
        ta.setAttribute('aria-label', 'Viết trả lời');
        ta.placeholder = 'Viết trả lời… (Enter để gửi)';
        box.appendChild(ta);
        body.appendChild(box);
      }
      var t = box.querySelector('textarea');
      var who = item.querySelector('.esc-bub b');
      if (who && !t.value && item !== root) t.value = who.textContent + ' ';
      t.focus();
      return;
    }
    if (act === 'edit') {
      var p = item.querySelector('[data-esc-cmt-text]');
      if (!p || item.querySelector('[data-esc-edit-cmt]')) return;
      var wrap = document.createElement('div');
      wrap.setAttribute('data-esc-edit-cmt', name);
      var ed = document.createElement('textarea');
      ed.rows = 2;
      ed.maxLength = 2000;
      ed.value = p.textContent;
      ed.setAttribute('data-esc-cmt-in', '');
      ed.setAttribute('aria-label', 'Sửa bình luận (Enter để lưu, Esc để huỷ)');
      wrap.appendChild(ed);
      p.hidden = true;
      p.parentNode.appendChild(wrap);
      ed.focus();
      ed.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape') { wrap.remove(); p.hidden = false; }
      });
    }
  }

  // ------------------------------------------------------------------ the bai ------
  function replaceCard(card, html) {
    var node = fromHTML(html).firstElementChild;
    if (!node) return;
    var wasOpen = card.querySelector('[data-esc-cmts-wrap]:not([hidden])');
    card.replaceWith(node);
    if (wasOpen) loadComments(node, false);
  }

  function setRx(card, rx, btn) {
    btn.setAttribute('aria-pressed', rx.mine ? 'true' : 'false');
    var sum = card.querySelector('[data-esc-rx-sum]');
    if (!sum) return;
    sum.textContent = '';
    if (rx.total) {
      var em = document.createElement('span');
      em.className = 'esc-em';
      em.textContent = rx.emojis;
      sum.appendChild(em);
      sum.appendChild(document.createTextNode(' ' + rx.total));
    }
  }

  function menuClose(except) {
    document.querySelectorAll('[data-esc-menu][aria-expanded="true"]').forEach(function (b) {
      if (b === except) return;
      b.setAttribute('aria-expanded', 'false');
      b.nextElementSibling.hidden = true;
    });
  }

  function inlineForm(card, label, placeholder, okText, onOk) {
    var old = card.querySelector('[data-esc-inline]');
    if (old) old.remove();
    var box = document.createElement('div');
    box.className = 'esc-edit';
    box.setAttribute('data-esc-inline', '');
    var lab = document.createElement('label');
    lab.className = 'esc-cp-lbl';
    lab.textContent = label;
    var ta = document.createElement('textarea');
    ta.maxLength = 300;
    ta.placeholder = placeholder;
    ta.rows = 2;
    lab.appendChild(ta);
    var row = document.createElement('div');
    row.className = 'esc-row-end';
    var cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'esc-btn esc-btn-sm';
    cancel.textContent = 'Huỷ';
    cancel.addEventListener('click', function () { box.remove(); });
    var ok = document.createElement('button');
    ok.type = 'button';
    ok.className = 'esc-btn esc-btn-sm esc-btn-pri';
    ok.textContent = okText;
    ok.addEventListener('click', function () { busy(ok, true); onOk(ta.value, function () { busy(ok, false); }); });
    row.appendChild(cancel);
    row.appendChild(ok);
    box.appendChild(lab);
    box.appendChild(row);
    card.querySelector('.esc-post-h').insertAdjacentElement('afterend', box);
    ta.focus();
  }

  function postAction(btn) {
    var card = cardOf(btn);
    var post = card.getAttribute('data-esc-post');
    var act = btn.getAttribute('data-esc-act');
    menuClose();
    if (act === 'delete') {
      inlineForm(card, 'Xoá bài này? Ảnh và bình luận của bài cũng mất, không khôi phục được.', 'Không cần ghi gì', 'Xoá bài', function (_, fail) {
        call('delete', { post: post }).then(function () { card.remove(); toast('Đã xoá bài.'); }, function (e) { fail(); toast(e.message, true); });
      });
      var ta = card.querySelector('[data-esc-inline] textarea');
      if (ta) ta.parentNode.removeChild(ta);
      return;
    }
    if (act === 'report') {
      inlineForm(card, 'Báo cáo bài này cho HR', 'Bài có gì chưa ổn? (không bắt buộc)', 'Gửi báo cáo', function (reason, fail) {
        call('report', { post: post, reason: reason }).then(function (r) {
          var box = card.querySelector('[data-esc-inline]');
          if (box) box.remove();
          toast(r && r.again ? 'Bạn đã báo cáo bài này rồi. HR sẽ xem.' : 'Đã gửi báo cáo. HR sẽ xem và xử lý.');
        }, function (e) { fail(); toast(e.message, true); });
      });
      return;
    }
    if (act === 'hide') {
      inlineForm(card, 'Ẩn bài (chỉ người đăng và HR còn thấy)', 'Lý do (người đăng thấy)', 'Ẩn bài', function (reason, fail) {
        call('hide', { post: post, hidden: 1, reason: reason }).then(function (r) { replaceCard(card, r.html); toast('Đã ẩn bài.'); },
          function (e) { fail(); toast(e.message, true); });
      });
      return;
    }
    if (act === 'unhide') {
      call('hide', { post: post, hidden: 0 }).then(function (r) { replaceCard(card, r.html); toast('Đã hiện lại bài.'); },
        function (e) { toast(e.message, true); });
      return;
    }
    if (act === 'edit') {
      var bodyEl = card.querySelector('[data-esc-body]');
      inlineForm(card, 'Sửa nội dung', '', 'Lưu', function (text, fail) {
        call('edit', { post: post, body: text }).then(function (r) { replaceCard(card, r.html); toast('Đã lưu.'); },
          function (e) { fail(); toast(e.message, true); });
      });
      var ed = card.querySelector('[data-esc-inline] textarea');
      ed.maxLength = 3000;
      ed.rows = 4;
      ed.value = bodyEl ? bodyEl.textContent : '';
    }
  }

  // xem anh lon
  var lb = { list: [], i: 0 };
  function lbShow() {
    var box = document.getElementById('esc-lb');
    box.querySelector('[data-esc-lb-img]').src = lb.list[lb.i];
    box.querySelector('[data-esc-lb-prev]').hidden = lb.list.length < 2;
    box.querySelector('[data-esc-lb-next]').hidden = lb.list.length < 2;
  }
  function lbOpen(btn) {
    var holder = btn.closest('[data-esc-photos]');
    lb.list = Array.prototype.map.call(holder.querySelectorAll('[data-src]'), function (x) { return x.getAttribute('data-src'); });
    lb.i = parseInt(btn.getAttribute('data-esc-ph'), 10) || 0;
    lb.back = btn;
    var box = document.getElementById('esc-lb');
    box.hidden = false;
    lbShow();
    box.querySelector('[data-esc-lb-close]').focus();
  }
  function lbClose() {
    var box = document.getElementById('esc-lb');
    if (box.hidden) return;
    box.hidden = true;
    box.querySelector('[data-esc-lb-img]').removeAttribute('src');
    if (lb.back) lb.back.focus();
  }

  // ------------------------------------------------------------------ su kien chung ------
  document.addEventListener('click', function (ev) {
    var t = ev.target;
    var b;
    if ((b = t.closest('[data-esc-menu]'))) {
      var open = b.getAttribute('aria-expanded') !== 'true';
      menuClose(b);
      b.setAttribute('aria-expanded', open ? 'true' : 'false');
      b.nextElementSibling.hidden = !open;
      if (open) { var first = b.nextElementSibling.querySelector('button'); if (first) first.focus(); }
      return;
    }
    if (!t.closest('.esc-menu')) menuClose();
    if ((b = t.closest('[data-esc-act]'))) return postAction(b);
    if ((b = t.closest('[data-esc-react]'))) {
      var card = cardOf(b);
      var key = b.getAttribute('data-esc-moment');
      busy(b, true);
      call('react', key ? { moment: key } : { post: card.getAttribute('data-esc-post') }).then(function (rx) { setRx(card, rx, b); },
        function (e) { toast(e.message, true); }).then(function () { busy(b, false); });
      return;
    }
    if ((b = t.closest('[data-esc-hr-react]'))) {
      var hr = cardOf(b);
      busy(b, true);
      window.ecApi.post('ecentric_workspace.internal_posts.api.toggle_reaction', { post: hr.getAttribute('data-esc-hr'), kind: 'heart' })
        .then(function (res) {
          if (!res || !res.success) throw new Error((res && res.message) || 'Có lỗi, thử lại sau.');
          var heart = (res.data.items || []).filter(function (i) { return i.kind === 'heart'; })[0] || {};
          var em = (res.data.items || []).filter(function (i) { return i.n; }).map(function (i) { return i.emoji; }).slice(0, 3).join('');
          setRx(hr, { total: res.data.total, emojis: em, mine: !!heart.mine }, b);
        }).catch(function (e) { toast(e.message || errMsg(e), true); }).then(function () { busy(b, false); });
      return;
    }
    if ((b = t.closest('[data-esc-rsvp]'))) {
      var ec = cardOf(b);
      busy(b, true);
      call('rsvp', { post: ec.getAttribute('data-esc-post'), answer: b.getAttribute('data-esc-rsvp') })
        .then(function (r) { replaceCard(ec, r.html); }, function (e) { busy(b, false); toast(e.message, true); });
      return;
    }
    if ((b = t.closest('[data-esc-cmt-open]'))) return loadComments(cardOf(b), true);
    if ((b = t.closest('[data-esc-cmt-toggle]'))) {
      var c2 = cardOf(b);
      var w = c2.querySelector('[data-esc-cmts-wrap]');
      if (w && !w.hidden) { w.hidden = true; return; }
      return loadComments(c2, false);
    }
    if ((b = t.closest('[data-esc-cmt-act]'))) return cmtAction(b);
    if ((b = t.closest('[data-esc-ph]'))) return lbOpen(b);
    if (t.closest('[data-esc-lb-close]') || t.id === 'esc-lb') return lbClose();
    if (t.closest('[data-esc-lb-prev]')) { lb.i = (lb.i - 1 + lb.list.length) % lb.list.length; return lbShow(); }
    if (t.closest('[data-esc-lb-next]')) { lb.i = (lb.i + 1) % lb.list.length; return lbShow(); }
    if ((b = t.closest('[data-esc-goto]'))) {
      var target = document.getElementById(b.getAttribute('data-esc-goto'));
      if (target) {
        ev.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        loadComments(target, true);
      }
      return;
    }
    if ((b = t.closest('[data-esc-more]'))) return more(b);
    if ((b = t.closest('[data-esc-join]'))) return join(b);
    if (t.closest('[data-esc-propose-open]')) return proposeOpen();
    if (t.closest('[data-esc-modal-close]') || t.matches('[data-esc-propose]')) return proposeClose();
    if ((b = t.closest('[data-esc-dismiss]'))) return moderate(b, 'dismiss');
    if ((b = t.closest('[data-esc-mod-hide]'))) return moderate(b, 'hide');
    if ((b = t.closest('[data-esc-decide]'))) return decide(b);
    if ((b = t.closest('[data-esc-status]'))) return clubStatus(b);
    if ((b = t.closest('[data-esc-set-lead]'))) return setLead(b);
  });

  document.addEventListener('keydown', function (ev) {
    var t = ev.target;
    if (ev.key === 'Escape') {
      menuClose();
      lbClose();
      proposeClose();
    }
    var box = document.getElementById('esc-lb');
    if (box && !box.hidden) {
      if (ev.key === 'ArrowLeft') { lb.i = (lb.i - 1 + lb.list.length) % lb.list.length; lbShow(); }
      if (ev.key === 'ArrowRight') { lb.i = (lb.i + 1) % lb.list.length; lbShow(); }
    }
    if (t.matches && t.matches('[data-esc-cmt-in]') && ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) {
      ev.preventDefault();
      sendComment(t);
    }
  });
  document.addEventListener('input', function (ev) {
    if (ev.target.matches && ev.target.matches('[data-esc-cmt-in]')) grow(ev.target);
  });
  document.addEventListener('submit', function (ev) {
    if (ev.target.matches('[data-esc-cmt-form]')) {
      ev.preventDefault();
      var ta = ev.target.querySelector('[data-esc-cmt-in]');
      if (ta) sendComment(ta);
    }
  });

  // ------------------------------------------------------------------ xem them ------
  function more(btn) {
    var feed = document.querySelector('[data-esc-feed]');
    var args = { before: btn.getAttribute('data-next') };
    if (feed.getAttribute('data-club')) { args.club = feed.getAttribute('data-club'); args.tab = feed.getAttribute('data-tab') || ''; }
    else args.loc = feed.getAttribute('data-loc') || '';
    busy(btn, true);
    call('more', args, true).then(function (r) {
      feed.appendChild(fromHTML(r.html));
      if (r.next) { btn.setAttribute('data-next', r.next); busy(btn, false); } else btn.remove();
    }, function (e) { busy(btn, false); toast(e.message, true); });
  }

  // ------------------------------------------------------------------ CLB ------
  function join(btn) {
    var club = btn.getAttribute('data-esc-join');
    var joined = btn.getAttribute('aria-pressed') === 'true';
    if (joined && !armed(btn, 'Bấm lần nữa để rời')) return;
    busy(btn, true);
    call(joined ? 'club_leave' : 'club_join', { club: club }).then(function (r) {
      if (btn.getAttribute('data-reload')) { location.reload(); return; }
      var pending = /muốn tham gia|Đã đăng ký/.test(btn.textContent);
      btn.setAttribute('aria-pressed', r.joined ? 'true' : 'false');
      btn.classList.toggle('esc-btn-pri', !r.joined);
      btn.textContent = r.joined ? (pending ? '✓ Đã đăng ký' : '✓ Đã tham gia') : (pending ? 'Tôi cũng muốn tham gia' : 'Tham gia');
      var n = btn.closest('[data-esc-club]') && btn.closest('[data-esc-club]').querySelector('[data-esc-mem-n]');
      if (n) n.textContent = r.members;
      busy(btn, false);
      toast(r.joined ? 'Đã tham gia CLB.' : 'Đã rời CLB.');
    }, function (e) { busy(btn, false); toast(e.message, true); });
  }

  var proposeBack = null;
  function proposeOpen() {
    var m = document.querySelector('[data-esc-propose]');
    if (!m) return;
    proposeBack = document.activeElement;
    m.hidden = false;
    m.querySelector('input[name="club_name"]').focus();
  }
  function proposeClose() {
    var m = document.querySelector('[data-esc-propose]');
    if (!m || m.hidden) return;
    m.hidden = true;
    if (proposeBack) proposeBack.focus();
  }
  var pf = document.querySelector('[data-esc-propose-form]');
  if (pf) {
    pf.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var btn = pf.querySelector('[type="submit"]');
      var data = {};
      ['club_name', 'emoji', 'category', 'description'].forEach(function (k) { data[k] = pf.elements[k].value; });
      var col = pf.querySelector('input[name="color"]:checked');
      data.color = col ? col.value : '';
      busy(btn, true);
      call('club_propose', { data: JSON.stringify(data) }).then(function (r) {
        toast(r.status === 'Đang hoạt động' ? 'Đã mở CLB.' : 'Đã gửi đề xuất. HR duyệt xong bạn sẽ nhận thông báo.');
        setTimeout(function () { location.href = r.status === 'Đang hoạt động' ? r.url : location.pathname; }, 900);
      }, function (e) { busy(btn, false); toast(e.message, true); });
    });
  }

  // ------------------------------------------------------------------ kiem duyet ------
  function moderate(btn, kind) {
    var post = btn.getAttribute(kind === 'hide' ? 'data-esc-mod-hide' : 'data-esc-dismiss');
    var box = btn.closest('[data-esc-case]');
    busy(btn, true);
    var p = kind === 'hide' ? call('hide', { post: post, hidden: 1, reason: 'Vi phạm quy định Bảng tin' }) : call('dismiss', { post: post });
    p.then(function () { box.remove(); toast(kind === 'hide' ? 'Đã ẩn bài.' : 'Đã đóng báo cáo, giữ bài.'); },
      function (e) { busy(btn, false); toast(e.message, true); });
  }
  function decide(btn) {
    var box = btn.closest('[data-esc-modclub]');
    var approve = btn.getAttribute('data-esc-decide') === '1';
    var note = box.querySelector('[data-esc-note]').value;
    if (!approve && !note.trim()) { toast('Ghi lý do từ chối để người đề xuất biết.', true); box.querySelector('[data-esc-note]').focus(); return; }
    busy(btn, true);
    call('club_decide', { club: box.getAttribute('data-esc-modclub'), approve: approve ? 1 : 0, note: note })
      .then(function () { location.reload(); }, function (e) { busy(btn, false); toast(e.message, true); });
  }
  function clubStatus(btn) {
    var box = btn.closest('[data-esc-modclub]');
    var active = btn.getAttribute('data-esc-status') === '1';
    if (!active && !armed(btn, 'Bấm lần nữa để ngừng')) return;
    busy(btn, true);
    call('club_status', { club: box.getAttribute('data-esc-modclub'), active: active ? 1 : 0 })
      .then(function () { location.reload(); }, function (e) { busy(btn, false); toast(e.message, true); });
  }
  function setLead(btn) {
    var box = btn.closest('[data-esc-modclub]');
    var who = picker(box.querySelector('[data-esc-pick]')).users();
    if (!who.length) { toast('Chọn người phụ trách mới.', true); return; }
    busy(btn, true);
    call('club_lead', { club: box.getAttribute('data-esc-modclub'), lead: who[0] })
      .then(function () { location.reload(); }, function (e) { busy(btn, false); toast(e.message, true); });
  }

  // ------------------------------------------------------------------ khoi dong ------
  document.querySelectorAll('[data-esc-composer]').forEach(initComposer);
  document.querySelectorAll('[data-esc-pick="lead"]').forEach(function (p) { picker(p); });
  // Link chuong "#m-..." / "#binh-luan": mo san khoi loi chuc / binh luan.
  if (location.hash && /^#m-/.test(location.hash)) {
    var m = document.getElementById(location.hash.slice(1));
    if (m) loadComments(m, false);
  }
})();
