// Copyright (c) 2026, eCentric and contributors
// ec_internal_posts_editor.js - trang /tin-noi-bo/viet-bai (HR soan / sua bai). Mockup v5.
//
// Server ve san moi o (tieu de, tom tat, noi dung, chuyen muc, phong ban...). File nay gan:
//   * o soan: thanh dinh dang, dan anh chup man hinh (tai len thanh tep CONG KHAI gan vao bai),
//     lam sach HTML dan tu Word / Google Docs (server con lam sach lan nua);
//   * anh bia 3 kieu: Mau nen (8 mau + bieu tuong chuyen muc) / Tai anh len / AI tao anh
//     (AI doc thang tieu de + tom tat + noi dung dang nhap; toi da 5 lan / bai / ngay);
//   * pham vi phong ban + "Bai se toi N nguoi" (tinh tai cho tu cay phong ban);
//   * tep dinh kem RIENG TU; kiem truoc khi dang; hop xac nhan; luu / dang / go.
// Bai moi chua co ten: lan dau can tai tep / goi AI thi tu luu NHAP truoc (tep phai gan vao bai).
// v6 (03/10): Thoi diem dang (Dang ngay / Hen gio), Gui kem Teams, Doc va phan hoi (bat buoc xac
// nhan + han, cho phep binh luan). AI viet giup nam o ec_internal_posts_aiw.js (dung window.eipEditor).
(function () {
  'use strict';

  var root = document.querySelector('[data-eip-compose]');
  var dataEl = document.getElementById('eip-data');
  if (!root || !dataEl) return;

  var D;
  try { D = JSON.parse(dataEl.textContent || '{}'); } catch (e) { D = {}; }
  var UI = window.eipUI || {
    toast: function (m) { window.console && console.log(m); },
    call: function () { return Promise.reject(new Error('Trang chưa tải xong.')); }
  };
  var P = D.post || {};
  var DOCTYPE = 'EC Internal Post';
  var MB = 1024 * 1024;
  var LIMIT = { cover: 5 * MB, image: 10 * MB, file: 20 * MB, files: 10 };

  function $(sel, el) { return (el || root).querySelector(sel); }
  function $$(sel, el) { return Array.prototype.slice.call((el || root).querySelectorAll(sel)); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function today() { var d = new Date(); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function fmtDate(iso) { var p = String(iso || '').split('-'); return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : ''; }
  function slugify(t) {
    var s = String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D')
      .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80).replace(/-+$/, '');
    return s || 'tieu-de-bai-viet';
  }
  function plain(html) { var d = document.createElement('div'); d.innerHTML = html || ''; return (d.textContent || '').trim(); }

  // ------------------------------------------------------------------ du lieu ------
  var CATS = {};
  (D.categories || []).forEach(function (c) { CATS[c.slug] = c; });
  var DEPTS = {};
  (D.departments || []).forEach(function (d) { DEPTS[d.name] = d; });

  var S = {
    name: P.name || '',
    published: !!P.published,
    notified: !!P.notified,
    pinned: !!P.pinned,
    notify_bell: P.name ? !!P.notify_bell : true,
    push_to_home: P.name ? !!P.push_to_home : true,
    popup_image_link: P.name ? !!P.popup_image_link : true,
    notify_teams: !!P.notify_teams,
    allow_comments: P.name ? !!P.allow_comments : true,
    require_ack: !!P.require_ack,
    when: P.scheduled ? 'schedule' : 'now',
    scheduled: !!P.scheduled,
    scope: P.scope === 'dept' ? 'dept' : 'all',
    depts: (P.departments || []).filter(function (d) { return DEPTS[d]; }),
    files: (P.attachments || []).slice(),
    cover: {
      kind: P.cover_kind === 'image' && P.cover_image ? 'image' : 'color',
      color: P.cover_color || '',
      icon: P.name ? !!P.cover_icon : true,
      image: P.cover_image || '',
      ai: !!P.cover_ai
    },
    colorTouched: !!P.cover_color,
    uploadImg: P.cover_image && !P.cover_ai ? P.cover_image : '',
    ai: {
      enabled: !!D.ai_enabled, used: D.ai_used || 0, limit: D.ai_limit || 5,
      state: 'idle', job: '', images: P.cover_image && P.cover_ai ? [P.cover_image] : [], timer: null,
      pick: P.cover_image && P.cover_ai ? 0 : null
    },
    tab: 'color',
    dirty: false,
    busy: false
  };
  S.tab = S.cover.kind === 'image' ? (S.cover.ai ? 'ai' : 'upload') : 'color';

  var el = {
    title: $('[data-eip-f="title"]'),
    summary: $('[data-eip-f="summary"]'),
    editor: $('[data-eip-f="content"]'),
    category: $('[data-eip-f="category"]'),
    author: $('[data-eip-f="author_label"]'),
    expires: $('[data-eip-f="expires_on"]'),
    pubDate: $('[data-eip-f="publish_date"]'),
    pubTime: $('[data-eip-f="publish_time"]'),
    whenBox: $('[data-eip-when-box]'),
    whenHelp: $('[data-eip-when-help]'),
    pubBtn: $('[data-eip-publish-btn]'),
    ackBox: $('[data-eip-ack-box]'),
    ackDate: $('[data-eip-f="ack_deadline"]'),
    slug: $('[data-eip-slug]'),
    sumN: $('[data-eip-sum-n]'),
    saveState: $('[data-eip-save-state]'),
    formErr: $('[data-eip-form-err]'),
    preview: $('[data-eip-cover-preview]'),
    reach: $('[data-eip-reach]'),
    deptBox: $('[data-eip-dept-box]'),
    files: $('[data-eip-files]'),
    fileInput: $('[data-eip-file-input]'),
    coverFile: $('[data-eip-cover-file]'),
    imgFile: $('[data-eip-img-file]'),
    aiGrid: $('[data-eip-ai-grid]'),
    aiMsg: $('[data-eip-ai-msg]'),
    aiGo: $('[data-eip-ai-go]'),
    aiHint: $('[data-eip-ai-hint]'),
    modal: document.querySelector('[data-eip-modal]'),
    previewBox: document.querySelector('[data-eip-preview]')
  };

  // ------------------------------------------------------------------ bieu tuong ---
  var iconTpl = document.getElementById('eip-icons');
  function icon(key) {
    if (!iconTpl) return null;
    var holder = iconTpl.content.querySelector('[data-icon="' + key + '"]') ||
      iconTpl.content.querySelector('[data-icon="megaphone"]');
    return holder && holder.firstElementChild ? holder.firstElementChild.cloneNode(true) : null;
  }

  // ------------------------------------------------------------------ trang thai luu
  function setSaveState(text, dirty) {
    var span = el.saveState && el.saveState.querySelector('span');
    if (span) span.textContent = text;
    if (el.saveState) el.saveState.classList.toggle('eip-dirty', !!dirty);
  }
  var edits = 0;
  function markDirty() {
    edits++;
    if (S.dirty) return;
    S.dirty = true;
    setSaveState('Có thay đổi chưa lưu', true);
  }
  window.addEventListener('beforeunload', function (ev) {
    if (!S.dirty) return;
    ev.preventDefault();
    ev.returnValue = '';
  });
  function showFormErr(msg) {
    if (!el.formErr) return;
    el.formErr.textContent = msg || '';
    el.formErr.hidden = !msg;
    if (msg) el.formErr.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  function fieldErr(key, on) {
    var e = $('[data-eip-err="' + key + '"]');
    if (e) e.hidden = !on;
    var f = key === 'title' ? el.title : key === 'category' ? el.category : key === 'expires_on' ? el.expires
      : key === 'publish_at' ? el.pubDate : key === 'ack_deadline' ? el.ackDate : null;
    if (f) { f.classList.toggle('eip-bad', !!on); f.setAttribute('aria-invalid', on ? 'true' : 'false'); }
  }

  // ------------------------------------------------------------------ anh bia ------
  function catColor() { var c = CATS[el.category.value]; return (c && c.color) || 'navy'; }
  function catIcon() { var c = CATS[el.category.value]; return (c && c.icon) || 'megaphone'; }

  function renderCover() {
    var box = el.preview;
    if (!box) return;
    box.textContent = '';
    var c = S.cover;
    if (c.kind === 'image' && c.image) {
      var img = document.createElement('img');
      img.src = c.image;
      img.alt = '';
      var wrap = document.createElement('span');
      wrap.className = 'eip-cover eip-cover-img';
      wrap.appendChild(img);
      box.appendChild(wrap);
      box.setAttribute('aria-label', c.ai ? 'Ảnh bìa do AI tạo' : 'Ảnh bìa đã tải lên');
    } else {
      var color = c.color || catColor();
      var span = document.createElement('span');
      span.className = 'eip-cover eip-cv-' + color;
      if (c.icon) { var ic = icon(catIcon()); if (ic) span.appendChild(ic); }
      box.appendChild(span);
      box.setAttribute('aria-label', 'Ảnh bìa màu nền');
    }
    $$('[data-eip-color]').forEach(function (b) {
      b.setAttribute('aria-pressed', c.kind === 'color' && (c.color || catColor()) === b.getAttribute('data-eip-color') ? 'true' : 'false');
    });
    var chk = $('[data-eip-cover-icon]');
    if (chk) chk.checked = !!c.icon;
    var dl = $('[data-eip-cover-drop-label]');
    if (dl) dl.textContent = S.uploadImg ? 'Đổi ảnh khác' : '+ Chọn ảnh';
  }

  function setTab(tab) {
    S.tab = tab;
    $$('[data-eip-cvtab]').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-eip-cvtab') === tab ? 'true' : 'false'); });
    $$('[data-eip-cvpane]').forEach(function (p) { p.hidden = p.getAttribute('data-eip-cvpane') !== tab; });
    // Xem truoc di theo tab dang mo (giong mockup): Mau nen -> nen mau; tab anh -> anh cua tab do neu co.
    if (tab === 'color' && S.cover.kind !== 'color') {
      S.cover.kind = 'color'; S.cover.ai = false; markDirty();
    } else if (tab === 'upload' && S.uploadImg && S.cover.image !== S.uploadImg) {
      S.cover.kind = 'image'; S.cover.image = S.uploadImg; S.cover.ai = false; markDirty();
    } else if (tab === 'ai' && S.ai.pick != null && S.ai.images[S.ai.pick] && S.cover.image !== S.ai.images[S.ai.pick]) {
      S.cover.kind = 'image'; S.cover.image = S.ai.images[S.ai.pick]; S.cover.ai = true; markDirty();
    }
    renderCover();
    renderAI();
  }

  root.addEventListener('click', function (ev) {
    var t = ev.target.closest('[data-eip-cvtab]');
    if (t) { setTab(t.getAttribute('data-eip-cvtab')); return; }
    var sw = ev.target.closest('[data-eip-color]');
    if (sw) {
      S.cover.kind = 'color'; S.cover.ai = false;
      S.cover.color = sw.getAttribute('data-eip-color');
      S.colorTouched = true;
      markDirty(); renderCover();
      return;
    }
    var opt = ev.target.closest('[data-eip-ai-pick]');
    if (opt) {
      S.ai.pick = parseInt(opt.getAttribute('data-eip-ai-pick'), 10) || 0;
      S.cover.kind = 'image'; S.cover.image = S.ai.images[S.ai.pick]; S.cover.ai = true;
      markDirty(); renderCover(); renderAI();
    }
  });
  var iconChk = $('[data-eip-cover-icon]');
  if (iconChk) iconChk.addEventListener('change', function () { S.cover.icon = iconChk.checked; markDirty(); renderCover(); });

  // ------------------------------------------------------------------ luu tren server
  function payload() {
    var cover = S.cover;
    var imageOk = cover.kind === 'image' && cover.image;
    return {
      name: S.name || null,
      title: el.title.value.trim(),
      summary: el.summary.value.trim(),
      content: cleanEditorHtml(),
      category: el.category.value || '',
      author_label: el.author ? el.author.value.trim() : '',
      pinned: S.pinned ? 1 : 0,
      expires_on: el.expires.value || '',
      notify_bell: S.notify_bell ? 1 : 0,
      push_to_home: S.scope === 'all' && S.push_to_home ? 1 : 0,
      popup_image_link: S.popup_image_link ? 1 : 0,
      notify_teams: S.notify_bell && S.notify_teams ? 1 : 0,
      allow_comments: S.allow_comments ? 1 : 0,
      require_ack: S.require_ack ? 1 : 0,
      ack_deadline: S.require_ack && el.ackDate ? el.ackDate.value : '',
      publish_mode: scheduling() ? 'schedule' : 'now',
      publish_date: el.pubDate ? el.pubDate.value : '',
      publish_time: el.pubTime ? el.pubTime.value : '',
      scope: S.scope,
      departments: S.scope === 'dept' ? S.depts.slice() : [],
      cover_kind: imageOk ? 'image' : 'color',
      cover_color: cover.color || '',
      cover_icon: cover.icon ? 1 : 0,
      cover_image: imageOk ? cover.image : '',
      cover_ai: imageOk && cover.ai ? 1 : 0,
      attachments: S.files.map(function (f) { return { file_url: f.file_url, file_name: f.file_name }; })
    };
  }

  function setBusy(on) {
    S.busy = on;
    $$('[data-eip-act]').forEach(function (b) { b.disabled = on; b.setAttribute('aria-busy', on ? 'true' : 'false'); });
  }

  function afterSaved(res) {
    var firstName = !S.name && res && res.name;
    S.name = res.name;
    S.published = !!res.published;
    S.scheduled = !!res.scheduled;
    if (firstName && window.history && history.replaceState) {
      history.replaceState(null, '', '/tin-noi-bo/viet-bai?bai=' + encodeURIComponent(res.name));
    }
    if (!S.published && el.slug && res.slug) el.slug.textContent = res.slug;
  }

  function save(action) {
    if (S.busy) return Promise.resolve(null);
    showFormErr('');
    setBusy(true);
    var startEdits = edits;
    // Dang tu luu nhap (tai tep / AI) -> doi xong de lan luu nay mang ten bai, khong tao bai thu hai.
    return (ensuring || Promise.resolve()).then(function () {
      return UI.call('save_post', { data: payload(), action: action });
    }).then(function (res) {
      afterSaved(res);
      if (edits === startEdits) S.dirty = false;
      return res;
    }, function (e) {
      showFormErr(e.message);
      throw e;
    }).then(function (res) { setBusy(false); return res; }, function (e) { setBusy(false); throw e; });
  }

  // Bai moi: tep / anh / AI deu phai gan vao MOT bai co that -> luu nhap truoc (can tieu de).
  var ensuring = null;
  function ensureSaved(why) {
    if (S.name) return Promise.resolve(S.name);
    if (ensuring) return ensuring;
    if (!el.title.value.trim()) {
      fieldErr('title', true);
      el.title.focus();
      return Promise.reject(new Error('Nhập tiêu đề trước để lưu nháp, rồi ' + why + '.'));
    }
    ensuring = UI.call('save_post', { data: payload(), action: 'save' }).then(function (res) {
      afterSaved(res);
      setSaveState('Đã tự lưu nháp lúc ' + timeNow(), false);
      ensuring = null;
      return res.name;     // S.dirty giu nguyen: nguoi dung van con thay doi chua luu
    }, function (e) {
      ensuring = null;
      showFormErr(e.message);
      throw e;
    });
    return ensuring;
  }
  function timeNow() { var d = new Date(); return pad(d.getHours()) + ':' + pad(d.getMinutes()); }

  // Tai tep len Frappe (upload_file), gan vao bai. isPrivate: tep dinh kem = 1, anh = 0.
  function uploadFile(file, isPrivate, retried) {
    if (!window.ecApi) return Promise.reject(new Error('Trang chưa tải xong, thử lại sau giây lát.'));
    return window.ecApi.csrfToken(!!retried).then(function (token) {
      var fd = new FormData();
      fd.append('file', file, file.name || ('anh-dan-' + Date.now() + '.png'));
      fd.append('is_private', isPrivate ? '1' : '0');
      fd.append('doctype', DOCTYPE);
      fd.append('docname', S.name);
      if (!isPrivate && /^image\/(png|jpe?g|webp)$/.test(file.type || '')) fd.append('optimize', '1');
      return fetch('/api/method/upload_file', {
        method: 'POST', credentials: 'same-origin', body: fd,
        headers: { Accept: 'application/json', 'X-Frappe-CSRF-Token': token || '' }
      });
    }).then(function (r) {
      return r.json().then(function (j) { return { r: r, j: j }; }, function () { return { r: r, j: null }; });
    }).then(function (res) {
      var j = res.j || {};
      if (j.exc_type === 'CSRFTokenError' && !retried) return uploadFile(file, isPrivate, true);
      if (!res.r.ok || j.exc_type || !j.message || !j.message.file_url) throw new Error(serverMsg(j) || 'Không tải tệp lên được.');
      return j.message;
    });
  }
  function serverMsg(j) {
    try {
      var arr = JSON.parse((j && j._server_messages) || '[]');
      if (arr.length) {
        var m = JSON.parse(arr[0]);
        return plain(m.message || '');
      }
    } catch (e) { /* bo qua */ }
    if (j && j.exc_type === 'FileSizeError') return 'Tệp quá lớn.';
    return '';
  }

  // ------------------------------------------------------------------ tai anh bia --
  var coverDrop = $('[data-eip-cover-drop]');
  function pickCover() { if (el.coverFile) el.coverFile.click(); }
  function handleCoverFile(file) {
    if (!file) return;
    if (!/^image\/(png|jpe?g|webp)$/.test(file.type || '')) { UI.toast('Ảnh bìa cần là PNG, JPG hoặc WebP.', true); return; }
    if (file.size > LIMIT.cover) { UI.toast('Ảnh bìa tối đa 5 MB.', true); return; }
    var label = $('[data-eip-cover-drop-label]');
    if (label) label.textContent = 'Đang tải ảnh…';
    ensureSaved('tải ảnh bìa').then(function () { return uploadFile(file, false); }).then(function (f) {
      S.uploadImg = f.file_url;
      S.cover.kind = 'image'; S.cover.image = f.file_url; S.cover.ai = false;
      markDirty(); renderCover();
      UI.toast('Đã tải ảnh bìa. Nhớ lưu bài.');
    }, function (e) {
      UI.toast(e.message, true);
      renderCover();
    });
  }
  if (coverDrop) {
    coverDrop.addEventListener('click', pickCover);
    coverDrop.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pickCover(); } });
    dropZone(coverDrop, function (files) { handleCoverFile(files[0]); });
  }
  if (el.coverFile) el.coverFile.addEventListener('change', function () { handleCoverFile(el.coverFile.files[0]); el.coverFile.value = ''; });

  function dropZone(zone, onFiles) {
    zone.addEventListener('dragover', function (ev) { ev.preventDefault(); zone.classList.add('eip-over'); });
    zone.addEventListener('dragleave', function () { zone.classList.remove('eip-over'); });
    zone.addEventListener('drop', function (ev) {
      ev.preventDefault();
      zone.classList.remove('eip-over');
      var files = ev.dataTransfer && ev.dataTransfer.files;
      if (files && files.length) onFiles(Array.prototype.slice.call(files));
    });
  }

  // ------------------------------------------------------------------ AI anh bia ---
  function sources() {
    return {
      title: el.title.value.trim().length > 0,
      summary: el.summary.value.trim().length > 0,
      content: plain(el.editor.innerHTML).length > 10
    };
  }
  function renderAI() {
    var src = sources();
    $$('[data-eip-src]').forEach(function (s) {
      var k = s.getAttribute('data-eip-src');
      var on = !!src[k];
      s.classList.toggle('eip-on', on);
      s.textContent = (on ? '✓ ' : '○ ') + { title: 'Tiêu đề', summary: 'Tóm tắt', content: 'Nội dung' }[k];
    });
    var ai = S.ai;
    var left = Math.max(0, ai.limit - ai.used);
    var loading = ai.state === 'loading';
    if (el.aiGo) {
      el.aiGo.disabled = !ai.enabled || !src.title || left <= 0 || loading;
      el.aiGo.textContent = ai.images.length && !loading ? '✦ Tạo lại' : '✦ Tạo ảnh bìa';
      el.aiGo.classList.toggle('eip-primary', !ai.images.length || loading);
    }
    var hint = '';
    if (!ai.enabled) hint = 'AI tạo ảnh đang tắt trên hệ thống. Dùng Màu nền hoặc Tải ảnh lên.';
    else if (loading) hint = '';
    else if (left <= 0) hint = 'Bài này đã dùng hết ' + ai.used + '/' + ai.limit + ' lượt hôm nay. Mai thử lại, hoặc chọn Màu nền.';
    else if (!src.title) hint = 'Nhập tiêu đề ở ô bên dưới là bấm được. Có thêm nội dung thì ảnh sát bài hơn.';
    else if (ai.images.length) hint = 'Bấm một ảnh để dùng làm ảnh bìa. Còn ' + left + '/' + ai.limit + ' lượt hôm nay.';
    else hint = 'Còn ' + left + '/' + ai.limit + ' lượt hôm nay cho bài này.';
    if (el.aiHint) el.aiHint.textContent = hint;

    if (!el.aiGrid) return;
    el.aiGrid.textContent = '';
    if (loading) {
      for (var i = 0; i < 3; i++) { var sk = document.createElement('div'); sk.className = 'eip-ai-sk'; el.aiGrid.appendChild(sk); }
      el.aiGrid.hidden = false;
    } else if (ai.images.length) {
      ai.images.forEach(function (u, idx) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'eip-ai-opt';
        b.setAttribute('data-eip-ai-pick', String(idx));
        b.setAttribute('aria-pressed', S.cover.kind === 'image' && S.cover.ai && S.cover.image === u ? 'true' : 'false');
        b.setAttribute('aria-label', 'Phương án ' + (idx + 1));
        var img = document.createElement('img');
        img.src = u; img.alt = 'Phương án ' + (idx + 1); img.loading = 'lazy';
        b.appendChild(img);
        el.aiGrid.appendChild(b);
      });
      el.aiGrid.hidden = false;
    } else {
      el.aiGrid.hidden = true;
    }
  }
  function aiMsg(text) {
    if (!el.aiMsg) return;
    el.aiMsg.textContent = text || '';
    el.aiMsg.hidden = !text;
  }

  function startAI() {
    if (S.ai.state === 'loading') return;
    showFormErr('');
    S.ai.state = 'loading';
    renderAI();
    aiMsg('Đang lưu nháp để gắn ảnh vào bài…');
    ensureSaved('tạo ảnh bìa').then(function (name) {
      aiMsg('Đang tạo 3 phương án, mất khoảng 20–60 giây. Bạn cứ tiếp tục viết bài.');
      return UI.call('cover_ai_start', {
        post: name, title: el.title.value.trim(), summary: el.summary.value.trim(), content: el.editor.innerHTML
      });
    }).then(function (d) {
      S.ai.job = d.job;
      S.ai.used = d.used;
      pollAI(Date.now());
    }, function (e) {
      S.ai.state = 'idle';
      aiMsg('');
      renderAI();
      UI.toast(e.message, true);
    });
  }
  function pollAI(started) {
    clearTimeout(S.ai.timer);
    S.ai.timer = setTimeout(function () {
      UI.call('cover_ai_status', { job: S.ai.job }, true).then(function (d) {
        if (typeof d.used === 'number') S.ai.used = d.used;
        if (d.status === 'Done' && d.images && d.images.length) {
          S.ai.state = 'done';
          S.ai.images = d.images;
          S.ai.pick = 0;
          if (S.tab === 'ai') {
            S.cover.kind = 'image'; S.cover.image = d.images[0]; S.cover.ai = true;
            markDirty(); renderCover();
          }
          aiMsg('');
          renderAI();
          UI.toast('AI đã tạo ' + d.images.length + ' ảnh bìa. Đang dùng ảnh thứ nhất.');
        } else if (d.status === 'Failed' || d.status === 'Done') {
          S.ai.state = 'idle';
          aiMsg(d.error || 'AI chưa tạo được ảnh lần này. Bấm Tạo lại sau ít phút, hoặc chọn Màu nền.');
          renderAI();
        } else if (Date.now() - started > 240000) {
          S.ai.state = 'idle';
          aiMsg('AI đang chậm hơn thường lệ. Thử lại sau ít phút, hoặc chọn Màu nền.');
          renderAI();
        } else {
          pollAI(started);
        }
      }, function () {
        if (Date.now() - started > 240000) { S.ai.state = 'idle'; aiMsg('Mất kết nối khi chờ AI. Thử lại sau.'); renderAI(); }
        else pollAI(started);
      });
    }, 3000);
  }
  if (el.aiGo) el.aiGo.addEventListener('click', startAI);

  var aiTimer = null;
  function refreshAISoon() { clearTimeout(aiTimer); aiTimer = setTimeout(renderAI, 300); }

  // ------------------------------------------------------------------ o soan -------
  try { document.execCommand('defaultParagraphSeparator', false, 'p'); } catch (e) { /* trinh duyet cu */ }
  var lastRange = null;
  document.addEventListener('selectionchange', function () {
    var sel = window.getSelection();
    if (sel && sel.rangeCount && el.editor.contains(sel.getRangeAt(0).commonAncestorContainer)) lastRange = sel.getRangeAt(0).cloneRange();
  });
  function restoreRange() {
    el.editor.focus();
    if (!lastRange) {
      var r = document.createRange();
      r.selectNodeContents(el.editor);
      r.collapse(false);
      lastRange = r;
    }
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(lastRange);
  }
  function currentBlock() {
    var sel = window.getSelection();
    if (!sel || !sel.rangeCount) return '';
    var n = sel.getRangeAt(0).startContainer;
    while (n && n !== el.editor) {
      if (n.nodeType === 1 && /^(H2|H3|BLOCKQUOTE|P|LI)$/.test(n.nodeName)) return n.nodeName;
      n = n.parentNode;
    }
    return '';
  }
  function exec(cmd, val) { try { document.execCommand(cmd, false, val); } catch (e) { /* bo qua */ } }
  function insertHtml(html) { restoreRange(); exec('insertHTML', html); markDirty(); refreshAISoon(); }

  $$('[data-eip-tb]').forEach(function (b) {
    b.addEventListener('mousedown', function (ev) { ev.preventDefault(); });   // giu vung chon trong o soan
    b.addEventListener('click', function () {
      var k = b.getAttribute('data-eip-tb');
      restoreRange();
      if (k === 'h2' || k === 'h3') exec('formatBlock', currentBlock() === k.toUpperCase() ? '<p>' : '<' + k + '>');
      else if (k === 'quote') exec('formatBlock', currentBlock() === 'BLOCKQUOTE' ? '<p>' : '<blockquote>');
      else if (k === 'bold' || k === 'italic') exec(k);
      else if (k === 'ul') exec('insertUnorderedList');
      else if (k === 'ol') exec('insertOrderedList');
      else if (k === 'clear') { exec('removeFormat'); exec('formatBlock', '<p>'); }
      else if (k === 'table') {
        exec('insertHTML', '<table><thead><tr><th>Cột 1</th><th>Cột 2</th><th>Cột 3</th></tr></thead>' +
          '<tbody><tr><td><br></td><td><br></td><td><br></td></tr><tr><td><br></td><td><br></td><td><br></td></tr></tbody></table><p><br></p>');
      } else if (k === 'link') { askLink(); return; }
      else if (k === 'img') { if (el.imgFile) el.imgFile.click(); return; }
      markDirty();
      refreshAISoon();
    });
  });

  function safeUrl(u) {
    u = String(u || '').trim();
    if (!u) return '';
    if (/^(https?:\/\/|mailto:|\/(?!\/)|#)/i.test(u)) return u;
    if (/^[\w.-]+\.[a-z]{2,}(\/|$)/i.test(u)) return 'https://' + u;
    return '';
  }
  function askLink() {
    var saved = lastRange && lastRange.cloneRange();
    var hasText = saved && !saved.collapsed;
    openModal({
      title: 'Chèn link',
      html: '<label class="eip-fld"><span class="eip-lb">Địa chỉ</span><input class="eip-inp" data-eip-link-url placeholder="https://… hoặc /tin-noi-bo/…" autocomplete="off"></label>' +
        (hasText ? '' : '<label class="eip-fld" style="margin-top:10px"><span class="eip-lb">Chữ hiển thị</span><input class="eip-inp" data-eip-link-text autocomplete="off"></label>'),
      ok: 'Chèn link',
      cancel: 'Thôi',
      onOpen: function (box) { var i = box.querySelector('[data-eip-link-url]'); if (i) i.focus(); },
      onOk: function (box) {
        var url = safeUrl(box.querySelector('[data-eip-link-url]').value);
        if (!url) { UI.toast('Link cần bắt đầu bằng https://, mailto: hoặc /', true); return false; }
        lastRange = saved;
        restoreRange();
        if (hasText) exec('createLink', url);
        else {
          var t = box.querySelector('[data-eip-link-text]');
          var text = (t && t.value.trim()) || url;
          exec('insertHTML', '<a href="' + esc(url) + '">' + esc(text) + '</a>&nbsp;');
        }
        markDirty();
        return true;
      }
    });
  }

  // Anh trong bai: CONG KHAI (giong anh popup, PO chot) - tai len roi chen <img>.
  function insertImages(files) {
    var imgs = files.filter(function (f) { return /^image\//.test(f.type || ''); });
    if (!imgs.length) return;
    var saved = lastRange && lastRange.cloneRange();
    imgs.forEach(function (file) {
      if (file.size > LIMIT.image) { UI.toast('Ảnh "' + (file.name || 'dán') + '" quá 10 MB.', true); return; }
      UI.toast('Đang tải ảnh lên…');
      ensureSaved('chèn ảnh').then(function () { return uploadFile(file, false); }).then(function (f) {
        lastRange = saved;
        insertHtml('<img src="' + esc(f.file_url) + '" alt=""><p><br></p>');
        saved = lastRange;
        UI.toast('Đã chèn ảnh.');
      }, function (e) { UI.toast(e.message, true); });
    });
  }
  if (el.imgFile) el.imgFile.addEventListener('change', function () {
    insertImages(Array.prototype.slice.call(el.imgFile.files || []));
    el.imgFile.value = '';
  });

  el.editor.addEventListener('paste', function (ev) {
    var cd = ev.clipboardData;
    if (!cd) return;
    var files = Array.prototype.slice.call(cd.files || []);
    if (files.length && files.some(function (f) { return /^image\//.test(f.type || ''); })) {
      ev.preventDefault();
      insertImages(files);
      return;
    }
    var html = cd.getData('text/html');
    ev.preventDefault();
    if (html) {
      var res = sanitize(html);
      exec('insertHTML', res.html);
      if (res.droppedImages) UI.toast('Ảnh dán kèm từ trang khác không giữ được. Chụp màn hình rồi dán, hoặc dùng nút Ảnh.', true);
    } else {
      var text = cd.getData('text/plain') || '';
      exec('insertHTML', text.split(/\r?\n\r?\n/).map(function (para) {
        return '<p>' + esc(para).replace(/\r?\n/g, '<br>') + '</p>';
      }).join(''));
    }
    markDirty();
    refreshAISoon();
  });
  el.editor.addEventListener('drop', function (ev) {
    var files = ev.dataTransfer && ev.dataTransfer.files;
    if (files && files.length) {
      ev.preventDefault();
      if (document.caretRangeFromPoint) lastRange = document.caretRangeFromPoint(ev.clientX, ev.clientY);
      insertImages(Array.prototype.slice.call(files));
    }
  });
  el.editor.addEventListener('input', function () { markDirty(); refreshAISoon(); });

  // Lam sach HTML dan vao (Word / Google Docs / web). Server lam sach lan nua khi luu.
  var KEEP = { P: 'p', BR: 'br', H1: 'h2', H2: 'h2', H3: 'h3', H4: 'h3', H5: 'h3', H6: 'h3', STRONG: 'strong', B: 'strong',
    EM: 'em', I: 'em', U: 'u', UL: 'ul', OL: 'ol', LI: 'li', A: 'a', BLOCKQUOTE: 'blockquote', TABLE: 'table',
    THEAD: 'thead', TBODY: 'tbody', TR: 'tr', TH: 'th', TD: 'td', IMG: 'img', HR: 'hr', CODE: 'code', PRE: 'pre' };
  var DROP = /^(SCRIPT|STYLE|IFRAME|OBJECT|EMBED|META|LINK|TITLE|HEAD|SVG|MATH|NOSCRIPT|TEMPLATE|FORM|INPUT|BUTTON|SELECT|TEXTAREA|VIDEO|AUDIO|CANVAS)$/;
  var BLOCKISH = /^(DIV|SECTION|ARTICLE|HEADER|FOOTER|MAIN|ASIDE|FIGURE|FIGCAPTION|CENTER)$/;
  function sanitize(html) {
    var tpl = document.createElement('template');
    tpl.innerHTML = html;
    var dropped = 0;
    function walk(src, dst) {
      Array.prototype.slice.call(src.childNodes).forEach(function (n) {
        if (n.nodeType === 3) { dst.appendChild(document.createTextNode(n.nodeValue)); return; }
        if (n.nodeType !== 1) return;
        var tag = n.nodeName.toUpperCase();
        if (DROP.test(tag)) return;
        var style = (n.getAttribute('style') || '').toLowerCase();
        // Google Docs: <b style="font-weight:normal" id="docs-internal-guid-..."> boc ca bai
        if (tag === 'B' && /font-weight:\s*normal/.test(style)) { walk(n, dst); return; }
        if (tag === 'SPAN') {
          var wrapTag = /font-weight:\s*(bold|[6-9]00)/.test(style) ? 'strong' : /font-style:\s*italic/.test(style) ? 'em' : '';
          if (wrapTag) { var w = document.createElement(wrapTag); walk(n, w); dst.appendChild(w); } else walk(n, dst);
          return;
        }
        if (BLOCKISH.test(tag)) { var p = document.createElement('p'); walk(n, p); if (p.childNodes.length) dst.appendChild(p); return; }
        var keep = KEEP[tag];
        if (!keep) { walk(n, dst); return; }
        var out = document.createElement(keep);
        if (keep === 'a') {
          var href = safeUrl(n.getAttribute('href'));
          if (!href) { walk(n, dst); return; }
          out.setAttribute('href', href);
        } else if (keep === 'img') {
          var srcAttr = n.getAttribute('src') || '';
          var local = srcAttr.replace(location.origin, '');
          if (!/^\/files\/[^"'<>\s]+$/.test(local)) { dropped++; return; }
          out.setAttribute('src', local);
          out.setAttribute('alt', (n.getAttribute('alt') || '').slice(0, 200));
          dst.appendChild(out);
          return;
        } else if (keep === 'td' || keep === 'th') {
          ['colspan', 'rowspan'].forEach(function (a) { var v = parseInt(n.getAttribute(a), 10); if (v > 1 && v < 50) out.setAttribute(a, String(v)); });
        }
        walk(n, out);
        dst.appendChild(out);
      });
    }
    var box = document.createElement('div');
    walk(tpl.content, box);
    // bo doan rong lien tiep
    $$('p', box).forEach(function (p) { if (!p.textContent.trim() && !p.querySelector('img,br')) p.remove(); });
    return { html: box.innerHTML, droppedImages: dropped };
  }

  // HTML gui len: bo the rong cuoi bai, bo thuoc tinh trinh duyet tu chen.
  function cleanEditorHtml() {
    var box = document.createElement('div');
    box.innerHTML = el.editor.innerHTML;
    $$('[style]', box).forEach(function (n) { n.removeAttribute('style'); });
    $$('img.eip-uploading', box).forEach(function (n) { n.remove(); });
    var last;
    while ((last = box.lastElementChild) && /^(P|DIV)$/.test(last.nodeName) && !last.textContent.trim() && !last.querySelector('img,table')) last.remove();
    return box.innerHTML.trim();
  }

  // ------------------------------------------------------------------ o nhap thuong -
  el.title.addEventListener('input', function () {
    if (el.title.value.trim()) fieldErr('title', false);
    if (!S.published && el.slug) el.slug.textContent = slugify(el.title.value);
    markDirty();
    refreshAISoon();
  });
  el.summary.addEventListener('input', function () {
    if (el.sumN) el.sumN.textContent = el.summary.value.length + '/240';
    markDirty();
    refreshAISoon();
  });
  el.category.addEventListener('change', function () {
    if (el.category.value) fieldErr('category', false);
    if (!S.colorTouched) S.cover.color = '';            // mau mac dinh di theo chuyen muc
    markDirty();
    renderCover();
  });
  if (el.author) el.author.addEventListener('input', markDirty);
  el.expires.addEventListener('change', function () {
    fieldErr('expires_on', false);
    markDirty();
  });

  // ------------------------------------------------------------------ thoi diem dang (v6)
  function scheduling() { return !S.published && S.when === 'schedule' && !!el.pubDate; }
  function startDateIso() { return scheduling() && el.pubDate.value ? el.pubDate.value : today(); }
  function whenText() {
    if (!el.pubDate || !el.pubDate.value) return '';
    var t = el.pubTime ? el.pubTime.value : '';
    var d = new Date(el.pubDate.value + 'T00:00:00');
    var wd = ['chủ Nhật', 'thứ Hai', 'thứ Ba', 'thứ Tư', 'thứ Năm', 'thứ Sáu', 'thứ Bảy'][d.getDay()];
    return t + ' ' + wd + ' ' + fmtDate(el.pubDate.value).slice(0, 5);
  }
  function scheduleAt() {
    if (!el.pubDate || !el.pubDate.value || !el.pubTime || !el.pubTime.value) return null;
    var d = new Date(el.pubDate.value + 'T' + el.pubTime.value + ':00');
    return isNaN(d.getTime()) ? null : d;
  }
  function renderWhen() {
    var sched = scheduling();
    if (el.whenBox) el.whenBox.hidden = !sched;
    if (el.whenHelp) {
      el.whenHelp.hidden = !sched;
      el.whenHelp.textContent = (sched && whenText() ? 'Lên lúc ' + whenText() + '. ' : '') +
        'Hệ thống kiểm mỗi 5 phút, bài lên trễ tối đa 5 phút.';
    }
    if (el.pubBtn) el.pubBtn.textContent = sched ? 'Hẹn đăng' : 'Đăng bài';
    if (!sched) fieldErr('publish_at', false);
    renderReach();
  }
  $$('input[name="eip-when"]').forEach(function (r) {
    r.addEventListener('change', function () {
      if (!r.checked) return;
      S.when = r.value === 'schedule' ? 'schedule' : 'now';
      if (S.when === 'schedule' && el.pubDate && !el.pubDate.value) {
        var tmr = new Date(); tmr.setDate(tmr.getDate() + 1);
        el.pubDate.value = tmr.getFullYear() + '-' + pad(tmr.getMonth() + 1) + '-' + pad(tmr.getDate());
      }
      markDirty();
      renderWhen();
    });
  });
  [el.pubDate, el.pubTime].forEach(function (x) {
    if (x) x.addEventListener('change', function () { fieldErr('publish_at', false); markDirty(); renderWhen(); });
  });
  if (el.pubDate) el.pubDate.min = today();

  // Doc va phan hoi: o han xac nhan chi hien khi bat "Bat buoc xac nhan"
  function renderAck() {
    if (el.ackBox) el.ackBox.hidden = !S.require_ack;
    if (!S.require_ack) fieldErr('ack_deadline', false);
  }
  if (el.ackDate) el.ackDate.addEventListener('change', function () { fieldErr('ack_deadline', false); markDirty(); });

  // ------------------------------------------------------------------ cong tac -----
  $$('[data-eip-sw]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (b.disabled) return;
      var k = b.getAttribute('data-eip-sw');
      S[k] = !S[k];
      b.setAttribute('aria-checked', S[k] ? 'true' : 'false');
      markDirty();
      renderReach();
    });
  });

  // O tich "Gui chuong" / "Hien thi tren popup trang chu" (PO 01/10: can o tich chon)
  $$('[data-eip-chk]').forEach(function (c) {
    c.addEventListener('change', function () {
      S[c.getAttribute('data-eip-chk')] = c.checked;
      markDirty();
      renderReach();
      renderAck();
    });
  });

  // ------------------------------------------------------------------ pham vi ------
  $$('input[name="eip-scope"]').forEach(function (r) {
    r.addEventListener('change', function () {
      if (!r.checked) return;
      S.scope = r.value;
      if (el.deptBox) el.deptBox.hidden = S.scope !== 'dept';
      if (S.scope === 'all') fieldErr('departments', false);
      markDirty();
      renderReach();
    });
  });
  if (el.deptBox) el.deptBox.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-eip-dept]');
    if (!b) return;
    var d = b.getAttribute('data-eip-dept');
    var i = S.depts.indexOf(d);
    if (i >= 0) S.depts.splice(i, 1); else S.depts.push(d);
    if (S.depts.length) fieldErr('departments', false);
    markDirty();
    renderReach();
  });

  function selectedRanges() {
    return S.depts.map(function (d) { var x = DEPTS[d]; return x ? [x.lft, x.rgt] : null; }).filter(Boolean);
  }
  function inRanges(ranges, lft) {
    for (var i = 0; i < ranges.length; i++) if (ranges[i][0] <= lft && lft <= ranges[i][1]) return true;
    return false;
  }
  function reachCount() {
    if (S.scope !== 'dept') return D.company_size || 0;
    var ranges = selectedRanges();
    return (D.employee_lfts || []).filter(function (l) { return inRanges(ranges, l); }).length;
  }
  function deptLabels() { return S.depts.map(function (d) { return DEPTS[d] ? DEPTS[d].label : d; }); }

  function renderReach() {
    // chip phong ban: chon / da gom trong phong cha
    var ranges = selectedRanges();
    $$('[data-eip-dept]').forEach(function (b) {
      var d = b.getAttribute('data-eip-dept');
      var on = S.depts.indexOf(d) >= 0;
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      var x = DEPTS[d];
      var implied = !on && x && ranges.some(function (r) { return r[0] < x.lft && x.lft <= r[1]; });
      if (implied) { b.setAttribute('data-eip-implied', '1'); b.title = 'Đã gồm trong phòng cha'; }
      else { b.removeAttribute('data-eip-implied'); b.removeAttribute('title'); }
    });
    var popupOk = S.scope === 'all';
    var row = $('[data-eip-popup-row]');
    var box = $('[data-eip-chk="push_to_home"]');
    if (row) row.classList.toggle('eip-dis', !popupOk);
    if (box) { box.disabled = !popupOk; box.checked = popupOk && S.push_to_home; }
    // "Bam vao anh mo bai": chi co nghia khi bai len popup
    var imgOk = popupOk && S.push_to_home;
    var imgRow = $('[data-eip-imglink-row]');
    var imgBox = $('[data-eip-chk="popup_image_link"]');
    if (imgRow) imgRow.classList.toggle('eip-dis', !imgOk);
    if (imgBox) { imgBox.disabled = !imgOk; imgBox.checked = imgOk && S.popup_image_link; }
    // "Gui kem Teams" di kem chuong: tat chuong (hoac da gui) thi tat theo
    var teamsOk = S.notify_bell && !S.notified;
    var teamsRow = $('[data-eip-teams-row]');
    var teamsBox = $('[data-eip-chk="notify_teams"]');
    if (teamsRow) teamsRow.classList.toggle('eip-dis', !teamsOk);
    if (teamsBox) { teamsBox.disabled = !teamsOk; teamsBox.checked = S.notify_bell && S.notify_teams; }
    var help = $('[data-eip-popup-help]');
    if (help) help.textContent = popupOk
      ? 'Hiện 7 ngày trong "Hôm nay ở eCentric". Bỏ tích trên bài đang hiện thì popup rút ngay.'
      : 'Popup hiện cho mọi người nên chỉ dùng cho bài toàn công ty.';
    if (!el.reach) return;
    var n = reachCount();
    var via = [];
    if (S.notify_bell && !S.notified) via.push(S.notify_teams ? 'chuông, Teams' : 'chuông');
    if (popupOk && S.push_to_home) via.push('popup trang chủ');
    var at = scheduling() && whenText() ? ', lúc ' + esc(whenText()) : '';
    el.reach.innerHTML = 'Bài sẽ tới <b>' + n + ' người</b>' + (via.length ? ' qua ' + via.join(' và ') : '') + at + '.' +
      (S.notified ? ' Chuông đã gửi khi đăng, sửa bài không gửi lại.' : '');
  }

  // ------------------------------------------------------------------ tep dinh kem -
  function extOf(name) { var m = /\.([a-z0-9]{1,5})$/i.exec(name || ''); return m ? m[1].toUpperCase().slice(0, 4) : 'TỆP'; }
  function renderFiles() {
    if (!el.files) return;
    el.files.textContent = '';
    S.files.forEach(function (f, i) {
      var row = document.createElement('div');
      row.className = 'eip-file';
      row.innerHTML = '<span class="eip-file-ic">' + esc(extOf(f.file_name || f.file_url)) + '</span>' +
        '<div><b title="' + esc(f.file_name) + '">' + esc(f.file_name || f.file_url) + '</b><small>' +
        'Chỉ người được đọc bài mới tải được</small></div>' +
        '<button type="button" class="eip-file-x" data-eip-file-x="' + i + '" aria-label="Bỏ tệp ' + esc(f.file_name) + '">×</button>';
      var lock = icon('lock');
      if (lock) row.querySelector('small').insertBefore(lock, row.querySelector('small').firstChild);
      el.files.appendChild(row);
    });
  }
  if (el.files) el.files.addEventListener('click', function (ev) {
    var x = ev.target.closest('[data-eip-file-x]');
    if (!x) return;
    S.files.splice(parseInt(x.getAttribute('data-eip-file-x'), 10), 1);
    markDirty();
    renderFiles();
  });
  function addFiles(files) {
    files.forEach(function (file) {
      if (S.files.length >= LIMIT.files) { UI.toast('Tối đa ' + LIMIT.files + ' tệp đính kèm.', true); return; }
      if (file.size > LIMIT.file) { UI.toast('Tệp "' + file.name + '" quá 20 MB.', true); return; }
      UI.toast('Đang tải "' + file.name + '"…');
      ensureSaved('đính kèm tệp').then(function () { return uploadFile(file, true); }).then(function (f) {
        S.files.push({ file_url: f.file_url, file_name: f.file_name || file.name });
        markDirty();
        renderFiles();
        UI.toast('Đã đính kèm "' + (f.file_name || file.name) + '". Nhớ lưu bài.');
      }, function (e) { UI.toast(e.message, true); });
    });
  }
  var fileDrop = $('[data-eip-file-drop]');
  if (fileDrop) {
    fileDrop.addEventListener('click', function () { el.fileInput.click(); });
    fileDrop.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); el.fileInput.click(); } });
    dropZone(fileDrop, addFiles);
  }
  if (el.fileInput) el.fileInput.addEventListener('change', function () {
    addFiles(Array.prototype.slice.call(el.fileInput.files || []));
    el.fileInput.value = '';
  });

  // ------------------------------------------------------------------ kiem truoc khi luu
  function check(action) {
    var errs = [];
    var t = !el.title.value.trim();
    fieldErr('title', t);
    if (t) errs.push('Bài cần có tiêu đề.');
    if (action === 'publish') {
      var c = !el.category.value;
      fieldErr('category', c);
      if (c) errs.push('Chọn một chuyên mục.');
      var d = S.scope === 'dept' && !S.depts.length;
      fieldErr('departments', d);
      if (d) errs.push('Chọn ít nhất một phòng ban.');
      var start = startDateIso();
      var x = !S.published && el.expires.value && el.expires.value < start;
      fieldErr('expires_on', x);
      if (x) errs.push(scheduling() ? 'Ngày hết hạn đang trước ngày hẹn đăng.' : 'Ngày hết hạn phải từ hôm nay trở đi.');
      if (scheduling()) {
        var at = scheduleAt();
        var bad = !at || at.getTime() <= Date.now();
        fieldErr('publish_at', bad);
        if (bad) errs.push('Chọn ngày và giờ đăng ở tương lai.');
      }
      if (S.require_ack) {
        var dl = el.ackDate ? el.ackDate.value : '';
        var badAck = !dl || (!S.published && dl < start);
        fieldErr('ack_deadline', badAck);
        if (badAck) errs.push('Chọn hạn xác nhận từ ngày bài lên trở đi.');
      }
    }
    if (errs.length) {
      UI.toast('Còn thiếu thông tin, xem chữ đỏ.', true);
      var first = root.querySelector('.eip-bad,[data-eip-err]:not([hidden])');
      if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return !errs.length;
  }

  // ------------------------------------------------------------------ hop thoai -----
  var modalCfg = null;
  var modalReturn = null;
  function openModal(cfg) {
    var m = el.modal;
    if (!m) return;
    modalCfg = cfg;
    modalReturn = document.activeElement;
    m.querySelector('[data-eip-modal-h]').textContent = cfg.title;
    var list = m.querySelector('[data-eip-modal-list]');
    var custom = m.querySelector('[data-eip-modal-custom]');
    if (custom) custom.remove();
    if (cfg.items) {
      list.hidden = false;
      list.innerHTML = cfg.items.map(function (i) { return '<li>' + esc(i) + '</li>'; }).join('');
    } else {
      list.hidden = true;
    }
    if (cfg.html) {
      var div = document.createElement('div');
      div.setAttribute('data-eip-modal-custom', '1');
      div.innerHTML = cfg.html;
      list.parentNode.insertBefore(div, list.nextSibling);
    }
    var ok = m.querySelector('[data-eip-modal-ok]');
    ok.textContent = cfg.ok || 'Đồng ý';
    m.querySelector('[data-eip-modal-close]').textContent = cfg.cancel || 'Quay lại sửa';
    ok.classList.toggle('eip-danger', !!cfg.danger);
    ok.classList.toggle('eip-primary', !cfg.danger);
    m.hidden = false;
    if (cfg.onOpen) cfg.onOpen(m); else ok.focus();
  }
  function closeModal() {
    if (!el.modal) return;
    el.modal.hidden = true;
    modalCfg = null;
    if (modalReturn && modalReturn.focus) modalReturn.focus();
  }
  if (el.modal) {
    el.modal.addEventListener('click', function (ev) {
      if (ev.target === el.modal || ev.target.closest('[data-eip-modal-close]')) { closeModal(); return; }
      if (ev.target.closest('[data-eip-modal-ok]') && modalCfg) {
        var cfg = modalCfg;
        var res = cfg.onOk ? cfg.onOk(el.modal) : true;
        if (res !== false) closeModal();
      }
    });
    el.modal.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' && ev.target.matches('input') && modalCfg) {
        ev.preventDefault();
        el.modal.querySelector('[data-eip-modal-ok]').click();
      }
    });
  }
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') {
      if (el.modal && !el.modal.hidden) closeModal();
      if (el.previewBox && !el.previewBox.hidden) closePreview();
    }
    if ((ev.ctrlKey || ev.metaKey) && (ev.key === 's' || ev.key === 'S')) {
      ev.preventDefault();
      if (S.published) UI.toast('Bài đang hiện: bấm "Lưu thay đổi" để lưu.');
      else if (S.scheduled) UI.toast('Bài đang hẹn giờ: bấm "Hẹn đăng" để lưu và giữ giờ hẹn.');
      else doAction('save');
    }
  });

  function publishItems() {
    var n = reachCount();
    var cat = CATS[el.category.value];
    var items = [(scheduling() ? 'Bài tự lên lúc ' + whenText() + ', chuyên mục ' : 'Hiện ngay ở Tin nội bộ, chuyên mục ') +
      (cat ? cat.name : '') + (S.pinned ? ', ghim trên cùng' : '') + '.'];
    items.push(S.scope === 'all' ? 'Toàn công ty đọc được (' + n + ' người).'
      : 'Chỉ ' + deptLabels().join(', ') + ' đọc được (' + n + ' người, gồm cả phòng con).');
    if (S.notify_bell && !S.notified) items.push('Gửi chuông' + (S.notify_teams ? ' và tin nhắn Teams (không rút lại được)' : ' thông báo') + ' cho ' + n + ' người' + (scheduling() ? ' lúc bài lên.' : '.'));
    if (S.scope === 'all' && S.push_to_home) {
      items.push('Hiện trên popup trang chủ ' + (el.expires.value ? 'tối đa 7 ngày (tới hạn của bài)' : '7 ngày') + (scheduling() ? ', tính từ lúc bài lên.' : '.'));
      if (S.popup_image_link && S.cover.kind === 'image' && S.cover.image) items.push('Bấm vào ảnh trên popup là mở bài.');
    }
    if (el.expires.value) items.push('Tự rút khỏi danh sách sau ngày ' + fmtDate(el.expires.value) + '.');
    if (S.require_ack && el.ackDate && el.ackDate.value) {
      var dl = new Date(el.ackDate.value + 'T00:00:00');
      var before = new Date(dl.getTime() - 86400000);
      items.push('Mọi người cần xác nhận đã đọc trước ' + fmtDate(el.ackDate.value).slice(0, 5) + '; ERP tự nhắc ' +
        pad(before.getDate()) + '/' + pad(before.getMonth() + 1) + ' và ' + fmtDate(el.ackDate.value).slice(0, 5) + ' lúc 09:00.');
    }
    if (!S.allow_comments) items.push('Tắt bình luận.');
    return items;
  }

  function doAction(act) {
    if (S.busy) return;
    if (act === 'preview') { openPreview(); return; }
    if (act === 'save') {
      if (!check('save')) return;
      save('save').then(function () {
        var sb = $('[data-eip-act="save"]');
        if (sb) sb.textContent = 'Lưu nháp';         // bai hen gio vua bi bo hen
        setSaveState('Đã lưu nháp lúc ' + timeNow(), false);
        UI.toast('Đã lưu nháp. Chỉ HR thấy bài này.');
      }, function () { /* loi da hien */ });
      return;
    }
    if (act === 'publish') {
      if (!check('publish')) return;
      if (S.published) {             // bai dang hien: luu thay doi, khong bao tin lai
        save('publish').then(function (res) {
          UI.toast('Đã lưu thay đổi.');
          setTimeout(function () { window.location.href = res.url; }, 500);
        }, function () {});
        return;
      }
      var sched = scheduling();
      openModal({
        title: (sched ? 'Hẹn đăng "' : 'Đăng bài "') + el.title.value.trim() + '"?',
        items: publishItems(),
        ok: sched ? 'Hẹn đăng' : 'Đăng bài',
        onOk: function () {
          save('publish').then(function (res) {
            if (res.scheduled) {
              S.dirty = false;
              UI.toast('Đã hẹn đăng ' + (res.publish_at_label || whenText()) + '. Bài nằm ở tab Hẹn giờ.');
              setTimeout(function () { window.location.href = '/tin-noi-bo/quan-ly?tab=scheduled'; }, 900);
              return;
            }
            UI.toast(S.notify_bell ? 'Đã đăng. Chuông đang gửi tới ' + reachCount() + ' người.' : 'Đã đăng bài.');
            setTimeout(function () { window.location.href = res.url; }, 700);
          }, function () {});
          return true;
        }
      });
      return;
    }
    if (act === 'unpublish') {
      openModal({
        title: 'Gỡ bài "' + el.title.value.trim() + '"?',
        items: ['Bài chuyển về Nháp: rút khỏi danh sách, trang chủ và popup.',
          'Không xoá nội dung và lượt xem; đăng lại được.',
          'Thay đổi chưa lưu trên trang này cũng được lưu vào bản nháp.'],
        ok: 'Gỡ bài',
        danger: true,
        onOk: function () {
          save('unpublish').then(function () {
            UI.toast('Đã gỡ bài.');
            setTimeout(function () { window.location.href = '/tin-noi-bo/quan-ly?tab=draft'; }, 500);
          }, function () {});
          return true;
        }
      });
    }
  }
  $$('[data-eip-act]').forEach(function (b) {
    b.addEventListener('click', function () { doAction(b.getAttribute('data-eip-act')); });
  });

  // ------------------------------------------------------------------ xem truoc -----
  function openPreview() {
    var box = el.previewBox;
    if (!box) return;
    var body = box.querySelector('[data-eip-preview-body]');
    var cat = CATS[el.category.value];
    var hero = document.createElement('header');
    hero.className = 'eip-hero';
    var cv = el.preview.firstElementChild ? el.preview.firstElementChild.cloneNode(true) : document.createElement('span');
    cv.classList.add('eip-cover-fill');
    hero.appendChild(cv);
    var hb = document.createElement('div');
    hb.className = 'eip-hero-body';
    hb.innerHTML = '<span class="eip-meta">' + (cat ? '<span class="eip-badge eip-tag-' + esc(cat.color) + '">' + esc(cat.name) + '</span>' : '') +
      (S.published ? '' : '<span class="eip-badge eip-b-draft">Bản nháp</span>') + '</span>' +
      '<h1>' + esc(el.title.value.trim() || 'Tiêu đề bài viết') + '</h1>' +
      '<span class="eip-meta"><span>' + esc((el.author && el.author.value.trim()) || 'Người đăng') + '</span></span>';
    hero.appendChild(hb);
    var main = document.createElement('div');
    main.className = 'eip-read-main';
    if (el.summary.value.trim()) {
      var lede = document.createElement('p');
      lede.className = 'eip-lede';
      lede.textContent = el.summary.value.trim();
      main.appendChild(lede);
    }
    var prose = document.createElement('div');
    prose.className = 'eip-prose';
    prose.innerHTML = sanitize(cleanEditorHtml()).html || '<p class="eip-note">Chưa có nội dung.</p>';
    main.appendChild(prose);
    body.textContent = '';
    body.appendChild(hero);
    body.appendChild(main);
    box.hidden = false;
    var close = box.querySelector('[data-eip-preview-close]');
    if (close) close.focus();
  }
  function closePreview() { if (el.previewBox) el.previewBox.hidden = true; }
  if (el.previewBox) el.previewBox.addEventListener('click', function (ev) {
    if (ev.target === el.previewBox || ev.target.closest('[data-eip-preview-close]')) closePreview();
  });

  // ------------------------------------------------------------------ khoi dong ------
  setTab(S.tab);
  S.dirty = false;                   // setTab o tren khong tinh la sua
  renderFiles();
  renderWhen();
  renderAck();
  renderAI();

  // Cho ec_internal_posts_aiw.js (AI viet giup) dung lai luu nhap + danh dau sua.
  window.eipEditor = {
    name: function () { return S.name; },
    ensureSaved: ensureSaved,
    markDirty: markDirty,
    fields: el,
    afterContent: function () {
      if (el.sumN) el.sumN.textContent = el.summary.value.length + '/240';
      if (!S.published && el.slug) el.slug.textContent = slugify(el.title.value);
      fieldErr('title', !el.title.value.trim());
      markDirty();
      refreshAISoon();
    },
    sanitize: function (html) { return sanitize(html).html; }
  };
  if (!P.name) {
    var cat0 = new URLSearchParams(location.search).get('chuyen-muc');
    if (cat0 && CATS[cat0]) { el.category.value = cat0; renderCover(); }
    el.title.focus();
  }
})();
