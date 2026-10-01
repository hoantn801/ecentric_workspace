// Copyright (c) 2026, eCentric and contributors
// ec_internal_posts.js - Tin noi bo, phia NGUOI DOC (+ nut Go / Xoa nhap o trang quan ly).
//
// Server da ve san moi trang thai dau (danh sach, so luot xem, cam xuc). File nay chi:
//   1. trang bai: gui POST "da xem" sau khi trang tai (mo bai = da xem, PO chot 01/10) roi
//      cap nhat con so; tha / bo cam xuc; danh dau muc dang doc trong "Trong bai nay";
//   2. trang quan ly: Go bai / Xoa nhap, co hop xac nhan trong trang.
// Goi server qua window.ecApi (CSRF tuoi, khong boc fetch). Loi -> thong bao tieng Viet.
// window.eipUI dung chung voi ec_internal_posts_editor.js.
(function () {
  'use strict';

  var API = 'ecentric_workspace.internal_posts.api.';

  // ------------------------------------------------------------------ tien ich ------
  var toastTimer = null;
  function toast(msg, isErr) {
    var t = document.getElementById('eip-toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.toggle('eip-toast-err', !!isErr);
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, isErr ? 5000 : 2600);
  }

  function errMsg(e) {
    if (!e) return 'Có lỗi, thử lại sau.';
    if (e.csrf) return 'Phiên đăng nhập vừa đổi. Tải lại trang (Ctrl+Shift+R) rồi thử lại.';
    var m = e.body && e.body.message;
    if (m && typeof m === 'object' && m.message) return String(m.message);
    if (e.status === 403) return 'Bạn không có quyền làm việc này.';
    if (e.status === 404) return 'Không tìm thấy bài.';
    if (!e.status) return 'Mất kết nối. Kiểm tra mạng rồi thử lại.';
    return 'Có lỗi, thử lại sau.';
  }

  // Goi API cua module. Tra data khi success, nem Error(thong diep doc duoc) khi khong.
  function call(method, args, get) {
    if (!window.ecApi) return Promise.reject(new Error('Trang chưa tải xong, thử lại sau giây lát.'));
    var p = get ? window.ecApi.get(API + method, args) : window.ecApi.post(API + method, args);
    return p.then(function (res) {
      if (res && res.success) return res.data;
      throw new Error((res && res.message) || 'Có lỗi, thử lại sau.');
    }, function (e) {
      throw new Error(errMsg(e));
    });
  }

  function all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function setText(sel, val, root) { all(sel, root).forEach(function (el) { el.textContent = String(val); }); }

  window.eipUI = { toast: toast, call: call, errMsg: errMsg };

  // ------------------------------------------------------------------ trang bai -----
  function initPost(article) {
    var name = article.getAttribute('data-eip-post');
    if (article.getAttribute('data-eip-published') === '1') {
      // De trinh duyet ve xong roi moi gui; khong chan doc bai neu loi.
      setTimeout(function () {
        call('mark_seen', { post: name }).then(function (d) {
          if (!d) return;
          setText('[data-eip-seen]', d.seen, article);
          setText('[data-eip-notseen]', d.not_seen, article);
          setText('[data-eip-total]', d.total, article);
          all('[data-eip-bar]', article).forEach(function (b) { b.style.width = (d.pct || 0) + '%'; });
          all('.eip-bar[role="progressbar"]', article).forEach(function (b) { b.setAttribute('aria-valuenow', d.pct || 0); });
        }, function () { /* luot xem la phu: im lang, lan mo sau ghi lai */ });
      }, 400);
    }

    // Cam xuc
    var rxPanel = article.querySelector('[data-eip-rx-panel]');
    if (rxPanel) {
      rxPanel.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-eip-rx]');
        if (!btn || btn.disabled) return;
        var kind = btn.getAttribute('data-eip-rx');
        var was = btn.getAttribute('aria-pressed') === 'true';
        var nEl = btn.querySelector('[data-eip-rx-n]');
        var oldN = parseInt((nEl && nEl.textContent) || '0', 10) || 0;
        // phan hoi ngay, sua lai theo server
        btn.setAttribute('aria-pressed', was ? 'false' : 'true');
        if (nEl) nEl.textContent = String(Math.max(0, oldN + (was ? -1 : 1)) || '');
        btn.disabled = true;
        call('toggle_reaction', { post: name, kind: kind }).then(function (d) {
          renderReactions(rxPanel, d);
        }, function (e) {
          btn.setAttribute('aria-pressed', was ? 'true' : 'false');
          if (nEl) nEl.textContent = oldN ? String(oldN) : '';
          toast(e.message, true);
        }).then(function () { btn.disabled = false; });
      });
    }

    // Muc dang doc trong "Trong bai nay"
    var toc = document.querySelector('.eip-toc');
    if (toc && 'IntersectionObserver' in window) {
      var links = all('a', toc);
      var byId = {};
      links.forEach(function (a) { byId[(a.getAttribute('href') || '').slice(1)] = a; });
      var heads = all('.eip-prose h2[id]', article).filter(function (h) { return byId[h.id]; });
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          links.forEach(function (a) { a.removeAttribute('aria-current'); });
          byId[en.target.id].setAttribute('aria-current', 'true');
        });
      }, { rootMargin: '-80px 0px -65% 0px' });
      heads.forEach(function (h) { io.observe(h); });
    }
  }

  function renderReactions(panel, d) {
    if (!d || !d.items) return;
    d.items.forEach(function (it) {
      var b = panel.querySelector('[data-eip-rx="' + it.kind + '"]');
      if (!b) return;
      b.setAttribute('aria-pressed', it.mine ? 'true' : 'false');
      var n = b.querySelector('[data-eip-rx-n]');
      if (n) n.textContent = it.n ? String(it.n) : '';
    });
    var who = panel.querySelector('[data-eip-rx-who]');
    if (who) who.textContent = d.who || '';
  }

  // ------------------------------------------------------------------ trang quan ly --
  function initManage() {
    var box = document.querySelector('[data-eip-confirm]');
    if (!box) return;
    var pending = null;
    var lastFocus = null;
    var yes = box.querySelector('[data-eip-confirm-yes]');
    var no = box.querySelector('[data-eip-confirm-no]');

    function close() {
      box.hidden = true;
      pending = null;
      if (lastFocus) lastFocus.focus();
    }

    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-eip-manage]');
      if (!btn) return;
      var act = btn.getAttribute('data-eip-manage');
      var title = btn.getAttribute('data-eip-title') || 'bài này';
      pending = { act: act, name: btn.getAttribute('data-eip-name'), btn: btn };
      lastFocus = btn;
      box.querySelector('[data-eip-confirm-h]').textContent =
        (act === 'unpublish' ? 'Gỡ bài "' : 'Xoá bản nháp "') + title + '"?';
      box.querySelector('[data-eip-confirm-p]').textContent = act === 'unpublish'
        ? 'Bài chuyển về Nháp: rút khỏi danh sách, trang chủ và popup. Không xoá nội dung, lượt xem; đăng lại được.'
        : 'Bản nháp bị xoá hẳn, không khôi phục được.';
      yes.textContent = act === 'unpublish' ? 'Gỡ bài' : 'Xoá nháp';
      yes.classList.toggle('eip-danger', act !== 'unpublish');
      box.hidden = false;
      no.focus();
    });
    no.addEventListener('click', close);
    box.addEventListener('click', function (ev) { if (ev.target === box) close(); });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && !box.hidden) close(); });
    yes.addEventListener('click', function () {
      if (!pending) return;
      var p = pending;
      yes.disabled = true;
      call(p.act === 'unpublish' ? 'unpublish' : 'delete_draft', { post: p.name }).then(function () {
        var row = document.querySelector('[data-eip-row="' + (window.CSS && CSS.escape ? CSS.escape(p.name) : p.name) + '"]');
        if (row) row.remove();
        box.hidden = true;
        pending = null;
        toast(p.act === 'unpublish' ? 'Đã gỡ bài. Bài nằm ở tab Nháp.' : 'Đã xoá bản nháp.');
        setTimeout(function () { window.location.reload(); }, 900);   // cap nhat so dem cac tab
      }, function (e) {
        toast(e.message, true);
      }).then(function () { yes.disabled = false; });
    });
  }

  function init() {
    var article = document.querySelector('[data-eip-post]');
    if (article) initPost(article);
    initManage();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
