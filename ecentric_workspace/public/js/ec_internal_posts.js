// Copyright (c) 2026, eCentric and contributors
// ec_internal_posts.js - Tin noi bo, phia NGUOI DOC (+ nut Go / Xoa nhap o trang quan ly).
//
// Server da ve san moi trang thai dau (danh sach, so luot xem, cam xuc). File nay chi:
//   1. trang bai: gui POST "da xem" sau khi trang tai (mo bai = da xem, PO chot 01/10) roi
//      cap nhat con so; tha / bo cam xuc; danh dau muc dang doc trong "Trong bai nay";
//   2. trang quan ly: Go bai / Xoa nhap / Dang ngay (bai hen gio), co hop xac nhan trong trang;
//   3. (v6) trang bai: "Toi da doc va hieu", HR nhac nguoi chua xac nhan; binh luan (gui, tra loi,
//      sua, xoa, tim, HR an / hien) - server tra lai khoi binh luan VE SAN, JS chi thay vao.
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

    initAck(article, name);
    var cm = article.querySelector('[data-eip-cmts]');
    if (cm) initComments(article);

    // Muc dang doc trong "Trong bai nay"
    var toc = document.querySelector('.eip-toc');
    if (toc) {
      // Tinh theo vi tri cuon (khong dung IntersectionObserver): muc cuoi bai ngan khong bao gio
      // cham vung quan sat o dau trang nen "keo max cung khong nhay" (PO bao 10/10/2026).
      // Cuon toi day trang -> muc cuoi cung; bam vao muc luc -> sang muc do ngay.
      var links = all('a', toc);
      var byId = {};
      links.forEach(function (a) { byId[(a.getAttribute('href') || '').slice(1)] = a; });
      var heads = all('.eip-prose h2[id]', article).filter(function (h) { return byId[h.id]; });
      var mark = function (id) {
        links.forEach(function (a) { if (a === byId[id]) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current'); });
      };
      var pinned = null;
      var spy = function () {
        if (!heads.length) return;
        var doc = document.documentElement;
        var atEnd = window.innerHeight + (window.pageYOffset || doc.scrollTop) >= doc.scrollHeight - 4;
        if (atEnd) { mark(pinned || heads[heads.length - 1].id); return; }
        pinned = null;
        var cur = heads[0];
        heads.forEach(function (h) { if (h.getBoundingClientRect().top <= 120) cur = h; });
        mark(cur.id);
      };
      var ticking = false;
      window.addEventListener('scroll', function () {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(function () { ticking = false; spy(); });
      }, { passive: true });
      toc.addEventListener('click', function (ev) {
        var a = ev.target.closest('a');
        if (!a) return;
        var id = (a.getAttribute('href') || '').slice(1);
        if (byId[id]) { pinned = id; mark(id); }
      });
      spy();
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

  // ------------------------------------------------------------------ xac nhan da doc (v6)
  function initAck(article, name) {
    var bar = article.querySelector('[data-eip-ackbar]');
    var btn = article.querySelector('[data-eip-ack]');
    if (btn && bar) {
      btn.addEventListener('click', function () {
        btn.disabled = true;
        btn.setAttribute('aria-busy', 'true');
        call('ack', { post: name }).then(function (d) {
          bar.classList.add('eip-ackbar-ok');
          bar.textContent = '';
          var div = document.createElement('div');
          var b = document.createElement('b'); b.textContent = 'Bạn đã xác nhận đã đọc bài này.';
          var sp = document.createElement('span'); sp.textContent = 'Cảm ơn bạn. HR thấy bạn trong danh sách đã xác nhận.';
          div.appendChild(b); div.appendChild(sp); bar.appendChild(div);
          setText('[data-eip-acked]', d.acked, article);
          setText('[data-eip-notacked]', d.not_acked, article);
          all('[data-eip-ack-bar]', article).forEach(function (x) { x.style.width = (d.pct || 0) + '%'; });
          all('[data-eip-ack-badge]').forEach(function (x) { x.remove(); });
          toast('Đã ghi nhận bạn đã đọc và hiểu.');
        }, function (e) {
          btn.disabled = false;
          btn.removeAttribute('aria-busy');
          toast(e.message, true);
        });
      });
    }
    var remind = article.querySelector('[data-eip-ack-remind]');
    if (remind) {
      remind.addEventListener('click', function () {
        if (remind.disabled) return;
        if (remind.getAttribute('data-eip-armed') !== '1') {        // bam 2 lan: tranh nhac nham
          remind.setAttribute('data-eip-armed', '1');
          remind.setAttribute('data-eip-label', remind.textContent);
          remind.lastChild.textContent = 'Bấm lần nữa để gửi chuông nhắc';
          setTimeout(function () {
            if (remind.getAttribute('data-eip-armed') === '1' && !remind.disabled) {
              remind.removeAttribute('data-eip-armed');
              remind.lastChild.textContent = remind.getAttribute('data-eip-label') || 'Nhắc người chưa xác nhận';
            }
          }, 4000);
          return;
        }
        remind.removeAttribute('data-eip-armed');
        remind.disabled = true;
        call('ack_remind', { post: name }).then(function (d) {
          remind.lastChild.textContent = 'Hôm nay đã nhắc';
          setText('[data-eip-ack-reminded]', d.reminded_label, article);
          toast('Đã gửi chuông nhắc ' + d.sent + ' người.');
        }, function (e) {
          remind.disabled = false;
          remind.lastChild.textContent = remind.getAttribute('data-eip-label') || 'Nhắc người chưa xác nhận';
          toast(e.message, true);
        });
      });
    }
  }

  // ------------------------------------------------------------------ binh luan (v6) --
  function initComments(article) {
    function section() { return article.querySelector('[data-eip-cmts]'); }
    var sending = false;

    // Ve lai ca khoi nhung GIU chu dang go do: o binh luan chinh + moi o tra loi / sua dang mo
    // (tru o vua gui thanh cong - `done`).
    function keepDrafts(old, done) {
      var out = { main: '', forms: [] };
      var main = old.querySelector('[data-eip-cmt-in]');
      if (main && main !== done) out.main = main.value;
      all('.eip-cmt-form', old).forEach(function (f) {
        var ta = f.querySelector('textarea');
        var it = f.closest('[data-eip-cmt]');
        if (!ta || ta === done || !it) return;
        out.forms.push({ name: it.getAttribute('data-eip-cmt'), kind: f.getAttribute('data-eip-form-kind'), text: ta.value });
      });
      return out;
    }
    function restoreDrafts(fresh, d) {
      var main = fresh.querySelector('[data-eip-cmt-in]');
      if (main && d.main) main.value = d.main;
      d.forms.forEach(function (f) {
        var it = fresh.querySelector('[data-eip-cmt="' + (window.CSS && CSS.escape ? CSS.escape(f.name) : f.name) + '"]');
        if (it) openForm(f.kind, it, f.text, true);
      });
    }

    function replace(html, focusName, done) {
      var old = section();
      if (!old || !html) return;
      var drafts = keepDrafts(old, done);
      var tpl = document.createElement('template');
      tpl.innerHTML = html.trim();
      var fresh = tpl.content.firstElementChild;
      if (!fresh) return;
      old.parentNode.replaceChild(fresh, old);
      restoreDrafts(fresh, drafts);
      if (focusName) {
        var c = fresh.querySelector('[data-eip-cmt="' + (window.CSS && CSS.escape ? CSS.escape(focusName) : focusName) + '"]');
        if (c) { c.classList.add('eip-flash'); c.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
      }
    }

    function run(method, args, focusName, onFail, done) {
      if (sending) { if (onFail) onFail(); return Promise.resolve(null); }
      sending = true;
      return call(method, args).then(function (d) {
        replace(d.html, focusName, done);
        return d;
      }, function (e) {
        toast(e.message, true);
        if (onFail) onFail();
        return null;
      }).then(function (d) { sending = false; return d; });
    }

    function submitArea(area, method, args, focusName) {
      if (sending) { toast('Đang gửi, đợi chút nhé.'); return; }
      var text = (area.value || '').trim();
      if (!text) { area.focus(); return; }
      var max = parseInt((section() || {}).getAttribute && section().getAttribute('data-eip-cmt-max'), 10) || 2000;
      if (text.length > max) { toast('Bình luận dài quá ' + max + ' ký tự.', true); return; }
      args.content = text;
      area.readOnly = true;
      area.setAttribute('aria-busy', 'true');
      run(method, args, focusName, function () { area.readOnly = false; area.removeAttribute('aria-busy'); area.focus(); }, area);
    }

    function inlineForm(cb, value, okLabel, onSubmit, kind, quiet) {
      var ex = cb.querySelector(':scope > .eip-cmt-form');
      if (ex) { ex.querySelector('textarea').focus(); return; }
      var form = document.createElement('form');
      form.className = 'eip-cmt-form';
      form.setAttribute('data-eip-form-kind', kind || '');
      var ta = document.createElement('textarea');
      ta.rows = 2;
      ta.value = value || '';
      ta.setAttribute('aria-label', okLabel);
      ta.placeholder = 'Enter để gửi, Shift+Enter xuống dòng, Esc để huỷ';
      var acts = document.createElement('div');
      acts.className = 'eip-cmt-form-acts';
      var cancel = document.createElement('button');
      cancel.type = 'button'; cancel.className = 'eip-btn eip-btn-sm'; cancel.textContent = 'Huỷ';
      var ok = document.createElement('button');
      ok.type = 'submit'; ok.className = 'eip-btn eip-btn-sm eip-primary'; ok.textContent = okLabel;
      acts.appendChild(cancel); acts.appendChild(ok);
      form.appendChild(ta); form.appendChild(acts);
      var actsRow = cb.querySelector(':scope > .eip-ca');
      cb.insertBefore(form, actsRow ? actsRow.nextSibling : null);
      cancel.addEventListener('click', function () { form.remove(); });
      form.addEventListener('submit', function (ev) { ev.preventDefault(); onSubmit(ta); });
      ta.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape') { ev.preventDefault(); form.remove(); }
        else if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); onSubmit(ta); }
      });
      if (!quiet) {
        ta.focus();
        ta.setSelectionRange(ta.value.length, ta.value.length);
      }
      return form;
    }

    // Mo o tra loi / sua duoi mot binh luan. value = chu nhap san (khoi phuc sau khi ve lai).
    function openForm(kind, item, value, quiet) {
      var name = item.getAttribute('data-eip-cmt');
      var cb = item.querySelector(':scope > .eip-cb');
      if (!cb) return;
      var post = section().getAttribute('data-eip-cmts');
      if (kind === 'reply') {
        var who = item.querySelector('.eip-ch b');
        var f = inlineForm(cb, value || '', 'Gửi trả lời', function (ta) {
          submitArea(ta, 'comment_add', { post: post, parent: name }, null);
        }, 'reply', quiet);
        if (f && who) f.querySelector('textarea').placeholder = 'Trả lời ' + who.textContent + '…';
      } else if (kind === 'edit') {
        var textEl = item.querySelector('[data-eip-cmt-text]');
        inlineForm(cb, value != null ? value : (textEl ? textEl.textContent : ''), 'Lưu', function (ta) {
          submitArea(ta, 'comment_edit', { comment: name }, name);
        }, 'edit', quiet);
      }
    }

    article.addEventListener('keydown', function (ev) {
      var area = ev.target.closest && ev.target.closest('[data-eip-cmt-in]');
      if (!area || ev.key !== 'Enter' || ev.shiftKey || ev.isComposing) return;
      ev.preventDefault();
      var post = section().getAttribute('data-eip-cmts');
      submitArea(area, 'comment_add', { post: post }, null);
    });
    article.addEventListener('submit', function (ev) {
      if (!ev.target.matches('[data-eip-cmt-form]')) return;
      ev.preventDefault();
      var area = ev.target.querySelector('[data-eip-cmt-in]');
      if (area) submitArea(area, 'comment_add', { post: section().getAttribute('data-eip-cmts') }, null);
    });

    article.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-eip-cmt-act]');
      if (!btn || !section() || !section().contains(btn)) return;
      var item = btn.closest('[data-eip-cmt]');
      if (!item) return;
      var name = item.getAttribute('data-eip-cmt');
      var act = btn.getAttribute('data-eip-cmt-act');
      if (act === 'reply' || act === 'edit') {
        openForm(act, item, null);
        return;
      }
      if (sending) { toast('Đang gửi, đợi chút nhé.'); return; }
      if (act === 'delete') {
        if (btn.getAttribute('data-eip-armed') !== '1') {
          btn.setAttribute('data-eip-armed', '1');
          btn.textContent = 'Bấm lần nữa để xoá';
          setTimeout(function () { if (btn.isConnected) { btn.removeAttribute('data-eip-armed'); btn.textContent = 'Xoá'; } }, 3500);
          return;
        }
        btn.disabled = true;
        run('comment_delete', { comment: name }, null, function () { btn.disabled = false; });
      } else if (act === 'hide' || act === 'unhide') {
        btn.disabled = true;
        run('comment_hide', { comment: name, hidden: act === 'hide' ? 1 : 0 }, name, function () { btn.disabled = false; })
          .then(function (d) { if (d) toast(act === 'hide' ? 'Đã ẩn bình luận. Chỉ HR còn thấy.' : 'Đã hiện lại bình luận.'); });
      } else if (act === 'like') {
        btn.disabled = true;
        run('comment_like', { comment: name }, null, function () { btn.disabled = false; });
      }
    });

    // Mo tu chuong "... binh luan bai" (link co #binh-luan) -> cuon toi khoi binh luan
    if (location.hash === '#binh-luan' && section()) setTimeout(function () { section().scrollIntoView({ block: 'start' }); }, 300);
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
      var T = {
        unpublish: ['Gỡ bài "', 'Bài chuyển về Nháp: rút khỏi danh sách, trang chủ và popup. Không xoá nội dung, lượt xem; đăng lại được.', 'Gỡ bài'],
        delete: ['Xoá bản nháp "', 'Bản nháp bị xoá hẳn, không khôi phục được.', 'Xoá nháp'],
        publish_now: ['Đăng ngay "', 'Bài lên luôn, không chờ tới giờ hẹn. Chuông, Teams (nếu có chọn) và popup gửi ngay bây giờ.', 'Đăng ngay']
      }[act] || ['', '', 'Đồng ý'];
      box.querySelector('[data-eip-confirm-h]').textContent = T[0] + title + '"?';
      box.querySelector('[data-eip-confirm-p]').textContent = T[1];
      yes.textContent = T[2];
      yes.classList.toggle('eip-danger', act === 'delete');
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
      var method = { unpublish: 'unpublish', delete: 'delete_draft', publish_now: 'publish_now' }[p.act];
      call(method, { post: p.name }).then(function () {
        var row = document.querySelector('[data-eip-row="' + (window.CSS && CSS.escape ? CSS.escape(p.name) : p.name) + '"]');
        if (row) row.remove();
        box.hidden = true;
        pending = null;
        toast({ unpublish: 'Đã gỡ bài. Bài nằm ở tab Nháp.', delete: 'Đã xoá bản nháp.',
                publish_now: 'Đã đăng bài. Chuông đang gửi.' }[p.act]);
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
