// Copyright (c) 2026, eCentric and contributors
// ec_internal_posts_aiw.js - "AI viet giup" tren /tin-noi-bo/viet-bai (mockup v6, PO duyet 03/10/2026).
//
// HR dan y chinh + chon giong van -> server (api.ai_write) goi AI, tra tieu de + tom tat + noi dung
// (HTML server da dung va escape). Hop hien BAN XEM TRUOC; chi khi bam "Dung bai nay" moi thay
// vao o soan. Noi dung chen bang execCommand('insertHTML') de Ctrl+Z trong o noi dung quay lai duoc.
// Gioi han 10 lan / bai / ngay do server dem; trang chi hien so con lai.
// Dung chung: window.eipUI (ec_internal_posts.js), window.eipEditor (ec_internal_posts_editor.js).
(function () {
  'use strict';

  var box = document.querySelector('[data-eip-aiw]');
  var openBtn = document.querySelector('[data-eip-aiw-open]');
  if (!box || !openBtn) return;

  var data = {};
  try { data = JSON.parse((document.getElementById('eip-data') || {}).textContent || '{}'); } catch (e) { data = {}; }
  var Q = data.ai_write || { used: 0, limit: 10, enabled: false };
  var UI = window.eipUI || { toast: function () {}, call: function () { return Promise.reject(new Error('Trang chưa tải xong.')); } };

  var points = box.querySelector('[data-eip-aiw-points]');
  var tone = box.querySelector('[data-eip-aiw-tone]');
  var go = box.querySelector('[data-eip-aiw-go]');
  var out = box.querySelector('[data-eip-aiw-out]');
  var hint = box.querySelector('[data-eip-aiw-hint]');
  var use = box.querySelector('[data-eip-aiw-use]');
  var result = null;
  var busy = false;
  var lastFocus = null;

  function left() { return Math.max(0, (Q.limit || 10) - (Q.used || 0)); }
  function renderHint() {
    var t = 'AI chỉ dùng ý bạn đưa, không tự thêm số liệu.';
    if (!Q.enabled) t = 'AI đang tắt trên hệ thống. Bạn viết tay giúp nhé.';
    else if (left() <= 0) t += ' Bài này đã dùng hết ' + Q.limit + ' lượt hôm nay.';
    else t += ' Còn ' + left() + '/' + Q.limit + ' lượt hôm nay cho bài này.';
    hint.textContent = t;
    go.disabled = busy || !Q.enabled || left() <= 0;
    go.textContent = busy ? 'Đang viết…' : (result ? '✦ Viết lại' : '✦ Viết bài');
    go.setAttribute('aria-busy', busy ? 'true' : 'false');
    use.disabled = busy || !result;
  }

  function showSkeleton() {
    out.textContent = '';
    var lab = document.createElement('span');
    lab.className = 'eip-legacy';
    lab.textContent = 'AI ĐANG VIẾT · thường mất 10–30 giây';
    out.appendChild(lab);
    [60, 90, 100, 80, 95, 70].forEach(function (w) {
      var sk = document.createElement('div');
      sk.className = 'eip-ai-sk';
      sk.style.width = w + '%';
      out.appendChild(sk);
    });
  }

  function showResult(r) {
    out.textContent = '';
    var lab = document.createElement('span');
    lab.className = 'eip-legacy';
    lab.textContent = 'BẢN AI VIẾT · xem trước';
    var t = document.createElement('b');
    t.className = 'eip-aiw-t';
    t.textContent = r.title || '';
    var s = document.createElement('p');
    s.className = 'eip-aiw-s';
    s.textContent = r.summary || '';
    var prose = document.createElement('div');
    prose.className = 'eip-prose';
    // HTML do server dung tu chuoi da escape; van qua bo lam sach cua trang soan cho chac.
    var ed = window.eipEditor;
    prose.innerHTML = ed && ed.sanitize ? ed.sanitize(r.content || '') : '';
    out.appendChild(lab);
    out.appendChild(t);
    if (r.summary) out.appendChild(s);
    out.appendChild(prose);
  }

  function showError(msg) {
    out.textContent = '';
    var p = document.createElement('p');
    p.className = 'eip-note';
    p.setAttribute('role', 'alert');
    p.textContent = msg;
    out.appendChild(p);
  }

  function open() {
    lastFocus = document.activeElement;
    box.hidden = false;
    renderHint();
    points.focus();
  }
  function close() {
    if (busy) return;              // dang cho AI: khong dong ngang (ket qua ve se mat)
    box.hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function write() {
    if (busy) return;
    var text = points.value.trim();
    if (text.length < 10) { UI.toast('Dán vài ý chính (ít nhất một câu) để AI viết.', true); points.focus(); return; }
    var ed = window.eipEditor;
    busy = true;
    result = null;
    showSkeleton();
    renderHint();
    // Bai da co ten thi dem luot theo bai; bai moi chua luu thi server dem theo nguoi.
    var name = ed && ed.name ? ed.name() : '';
    UI.call('ai_write', { post: name || '', points: text, tone: tone.value }).then(function (r) {
      result = r;
      if (typeof r.used === 'number') Q.used = r.used;
      showResult(r);
    }, function (e) {
      showError(e.message || 'AI chưa viết được lần này. Thử lại sau ít phút.');
    }).then(function () {
      busy = false;
      renderHint();
      if (result) use.focus();
    });
  }

  function apply() {
    var ed = window.eipEditor;
    if (!result || !ed) return;
    var f = ed.fields;
    f.title.value = result.title || f.title.value;
    if (result.summary) f.summary.value = result.summary.slice(0, 240);
    // Chon het o noi dung roi insertHTML: Ctrl+Z trong o noi dung quay lai ban cu.
    f.editor.focus();
    var range = document.createRange();
    range.selectNodeContents(f.editor);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    var html = ed.sanitize ? ed.sanitize(result.content || '') : '';
    var ok = false;
    try { ok = document.execCommand('insertHTML', false, html || '<p><br></p>'); } catch (e) { ok = false; }
    if (!ok) f.editor.innerHTML = html;
    ed.afterContent();
    box.hidden = true;
    UI.toast('Đã thay bằng bài AI viết. Đọc lại, sửa số liệu nếu cần rồi lưu.');
  }

  openBtn.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
  openBtn.addEventListener('click', open);
  go.addEventListener('click', write);
  use.addEventListener('click', apply);
  box.addEventListener('click', function (ev) {
    if (ev.target === box || ev.target.closest('[data-eip-aiw-close]')) close();
  });
  document.addEventListener('keydown', function (ev) {
    if (box.hidden) return;
    if (ev.key === 'Escape') { ev.stopPropagation(); close(); }
    if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey) && ev.target === points) { ev.preventDefault(); write(); }
  }, true);
  renderHint();
})();
