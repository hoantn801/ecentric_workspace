// Copyright (c) 2026, eCentric and contributors
// ec_feedback.js - Gop y cong ty (/gop-y, /gop-y/<ma>, /gop-y/xu-ly, /gop-y/tong-quan).
//
// Server da ve san moi trang thai dau (danh sach, nhan trang thai, han, so +1). File nay chi:
//   1. form gui gop y: dem ky tu, doc tep (base64), bat/tat an danh, gui;
//   2. trang mot gop y: POST "da doc cap nhat", nhan them, "Chua on";
//   3. bang chung: bam +1 (cap nhat con so tai cho);
//   4. hop xu ly: mo gop y "Moi" -> "Dang xem", tra loi / doi trang thai / ghi chu, bang chung,
//      chuyen chu de, trung / spam;
//   5. tong quan: "Tom tat ngay".
// Goi server qua window.ecApi (CSRF tuoi, khong boc fetch). Loi -> thong bao tieng Viet.
// Thao tac lam doi bo cuc (gui, doi trang thai) thi tai lai trang - server ve lai, JS khong dung
// lai giao dien.
(function () {
  'use strict';

  var API = 'ecentric_workspace.feedback.api.';
  var MAX_FILES = 5;
  var FILE_MAX = 5 * 1024 * 1024;
  var FILES_TOTAL_MAX = 12 * 1024 * 1024;

  // ------------------------------------------------------------------ tien ich ------
  var toastTimer = null;
  function toast(msg, isErr) {
    var t = document.getElementById('egy-toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.toggle('egy-toast-err', !!isErr);
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, isErr ? 6000 : 2600);
  }

  function errMsg(e) {
    if (!e) return 'Có lỗi, thử lại sau.';
    if (e.csrf) return 'Phiên đăng nhập vừa đổi. Tải lại trang (Ctrl+Shift+R) rồi thử lại.';
    var m = e.body && e.body.message;
    if (m && typeof m === 'object' && m.message) return String(m.message);
    if (e.status === 413) return 'Tệp đính kèm quá lớn. Bớt tệp hoặc chọn tệp nhỏ hơn.';
    if (e.status === 403) return 'Bạn không có quyền làm việc này.';
    if (e.status === 404) return 'Không tìm thấy góp ý.';
    if (!e.status) return 'Mất kết nối. Kiểm tra mạng rồi thử lại.';
    return 'Có lỗi, thử lại sau.';
  }

  function call(method, args) {
    if (!window.ecApi) return Promise.reject(new Error('Trang chưa tải xong, thử lại sau giây lát.'));
    return window.ecApi.post(API + method, args || {}).then(function (res) {
      if (res && res.success) return res.data;
      throw new Error((res && res.message) || 'Có lỗi, thử lại sau.');
    }, function (e) {
      throw new Error(errMsg(e));
    });
  }

  function busy(btn, on) {
    if (!btn) return;
    btn.disabled = !!on;
    if (on) btn.setAttribute('aria-busy', 'true'); else btn.removeAttribute('aria-busy');
  }

  // Gui form: chan bam hai lan, bao loi, thanh cong thi tai lai (hoac chuyen trang).
  function run(form, method, args, done) {
    var btn = form.querySelector('[type="submit"]');
    busy(btn, true);
    return call(method, args).then(function (data) {
      if (done) done(data); else location.reload();
    }, function (e) {
      busy(btn, false);
      toast(e.message, true);
    });
  }

  function val(form, name) {
    var el = form.elements[name];
    if (!el) return '';
    if (el.length !== undefined && !el.tagName) {               // nhom radio
      for (var i = 0; i < el.length; i++) if (el[i].checked) return el[i].value;
      return '';
    }
    if (el.type === 'checkbox') return el.checked ? 1 : 0;
    if (el.type === 'radio') return el.checked ? el.value : '';
    return (el.value || '').trim();
  }

  function readFile(f) {
    return new Promise(function (ok, fail) {
      var r = new FileReader();
      r.onload = function () { ok({ name: f.name, data: String(r.result || '') }); };
      r.onerror = function () { fail(new Error('Không đọc được tệp: ' + f.name)); };
      r.readAsDataURL(f);
    });
  }

  // ------------------------------------------------------------------ gui gop y -----
  function initForm(form) {
    var body = form.elements.body;
    var count = form.querySelector('[data-egy-count]');
    if (body && count) {
      var upd = function () { count.textContent = String(body.value.length); };
      body.addEventListener('input', upd);
      upd();
    }
    var anon = form.querySelector('[data-egy-anon]');
    var on = form.querySelector('[data-egy-anon-on]');
    var off = form.querySelector('[data-egy-anon-off]');
    if (anon && on && off) {
      var sync = function () { on.hidden = !anon.checked; off.hidden = anon.checked; };
      anon.addEventListener('change', sync);
      sync();
    }
    var fileIn = form.querySelector('[data-egy-files]');
    var fileList = form.querySelector('[data-egy-file-list]');
    if (fileIn && fileList) {
      fileIn.addEventListener('change', function () {
        var names = Array.prototype.map.call(fileIn.files || [], function (f) { return f.name; });
        fileList.textContent = names.length ? names.join(', ') : '';
      });
    }

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var errs = [];
      var topic = val(form, 'topic');
      var title = val(form, 'title');
      var text = val(form, 'body');
      if (!topic) errs.push('Chọn một chủ đề.');
      if (!title) errs.push('Chưa có tiêu đề.');
      if (!text) errs.push('Chưa có nội dung.');
      var files = fileIn ? Array.prototype.slice.call(fileIn.files || []) : [];
      if (files.length > MAX_FILES) errs.push('Tối đa ' + MAX_FILES + ' tệp đính kèm.');
      var total = 0;
      var anonOn = !!(anon && anon.checked);
      files.forEach(function (f) {
        if (anonOn && !/\.(png|jpe?g|gif|webp)$/i.test(f.name)) errs.push('Gửi ẩn danh chỉ đính kèm được ảnh: ' + f.name);
        total += f.size;
        if (f.size > FILE_MAX) errs.push('Tệp quá 5 MB: ' + f.name);
      });
      if (total > FILES_TOTAL_MAX) errs.push('Tổng dung lượng tệp tối đa 12 MB.');
      if (errs.length) { toast(errs.join('\n'), true); return; }

      var btn = form.querySelector('[data-egy-submit]');
      busy(btn, true);
      Promise.all(files.map(readFile)).then(function (encoded) {
        var payload = {
          topic: topic, kind: val(form, 'kind'), title: title, body: text,
          is_anonymous: val(form, 'is_anonymous'), files: encoded
        };
        return call('submit', { data: JSON.stringify(payload) });
      }).then(function (data) {
        toast('Đã gửi góp ý. Cảm ơn bạn!');
        setTimeout(function () { location.href = (data && data.url) || '/gop-y?tab=cua-toi'; }, 600);
      }, function (e) {
        busy(btn, false);
        toast(e.message, true);
      });
    });
  }

  // ------------------------------------------------------------------ mot gop y -----
  function initDetail(root) {
    var name = root.getAttribute('data-egy-detail');
    setTimeout(function () { call('mark_read', { feedback: name }).catch(function () { /* phu */ }); }, 300);
    var msg = root.querySelector('[data-egy-msg]');
    if (msg) {
      msg.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var text = val(msg, 'message');
        if (!text) { toast('Chưa có nội dung.', true); return; }
        run(msg, 'send_message', { feedback: name, message: text });
      });
    }
    var re = root.querySelector('[data-egy-reopen]');
    if (re) {
      re.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var text = val(re, 'message');
        if (!text) { toast('Viết điều gì chưa ổn để người xử lý biết.', true); return; }
        run(re, 'reopen', { feedback: name, message: text });
      });
    }
  }

  // ------------------------------------------------------------------ bang chung ----
  function initVotes() {
    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-egy-vote]');
      if (!btn || btn.disabled) return;
      var name = btn.getAttribute('data-egy-vote');
      btn.disabled = true;
      call('toggle_vote', { feedback: name }).then(function (d) {
        btn.disabled = false;
        btn.classList.toggle('is-on', !!d.voted);
        btn.setAttribute('aria-pressed', d.voted ? 'true' : 'false');
        btn.setAttribute('aria-label', (d.voted ? 'Bỏ +1, ' : 'Tôi cũng vậy, ') + d.votes + ' người');
        var n = btn.querySelector('[data-egy-vote-n]');
        var l = btn.querySelector('[data-egy-vote-l]');
        if (n) n.textContent = String(d.votes);
        if (l) l.textContent = d.voted ? 'Bạn đã +1' : 'Tôi cũng vậy';
        var card = btn.closest('.egy-board');
        var hot = card && card.querySelector('[data-egy-hot]');
        if (hot) hot.hidden = !d.hot;
        var mine = document.querySelector('[data-egy-myvotes]');
        if (mine) mine.textContent = String(Math.max(0, (parseInt(mine.textContent, 10) || 0) + (d.voted ? 1 : -1)));
      }, function (e) {
        btn.disabled = false;
        toast(e.message, true);
      });
    });
  }

  // ------------------------------------------------------------------ hop xu ly -----
  function initHandle(panel) {
    var name = panel.getAttribute('data-egy-handle');
    if (panel.getAttribute('data-egy-status') === 'Mới' && panel.getAttribute('data-egy-opened') === '1') {
      // BAM mo gop y moi = nhan xem (dong dau tu chon khi vao hop thi khong tinh).
      // Khong dung dong ho han (chi tra loi / ket qua moi dung).
      call('mark_viewing', { feedback: name }).then(function (d) {
        if (d && d.changed) location.reload();
      }, function (e) { toast(e.message, true); });
    }
    var act = panel.querySelector('[data-egy-act]');
    if (act) {
      act.addEventListener('submit', function (ev) {
        ev.preventDefault();
        run(act, 'act', { feedback: name, status: val(act, 'status'), message: val(act, 'message'),
          internal: val(act, 'internal') });
      });
    }
    var pub = panel.querySelector('[data-egy-publish]');
    if (pub) {
      pub.addEventListener('submit', function (ev) {
        ev.preventDefault();
        if (!val(pub, 'title')) { toast('Cần tiêu đề công khai.', true); return; }
        run(pub, 'publish', { feedback: name, on: 1, title: val(pub, 'title'), answer: val(pub, 'answer') });
      });
      var un = pub.querySelector('[data-egy-unpublish]');
      if (un) {
        un.addEventListener('click', function () {
          busy(un, true);
          call('publish', { feedback: name, on: 0 }).then(function () { location.reload(); },
            function (e) { busy(un, false); toast(e.message, true); });
        });
      }
    }
    var tp = panel.querySelector('[data-egy-topic]');
    if (tp) {
      tp.addEventListener('submit', function (ev) {
        ev.preventDefault();
        run(tp, 'set_topic', { feedback: name, topic: val(tp, 'topic') });
      });
    }
    var dup = panel.querySelector('[data-egy-dup]');
    if (dup) {
      dup.addEventListener('submit', function (ev) {
        ev.preventDefault();
        if (!val(dup, 'of') && !val(dup, 'spam')) { toast('Nhập mã góp ý gốc hoặc chọn spam.', true); return; }
        run(dup, 'mark_duplicate', { feedback: name, of: val(dup, 'of'), spam: val(dup, 'spam'),
          message: val(dup, 'message') });
      });
    }
  }

  // ------------------------------------------------------------------ tong quan -----
  function initOverview(root) {
    var btn = root.querySelector('[data-egy-summarize]');
    if (!btn) return;
    btn.addEventListener('click', function () {
      busy(btn, true);
      toast('Đang nhờ AI gom chủ đề… (có thể mất nửa phút)');
      call('summarize_now', { month: root.getAttribute('data-egy-overview') }).then(function () {
        location.reload();
      }, function (e) { busy(btn, false); toast(e.message, true); });
    });
  }

  function init() {
    var form = document.querySelector('[data-egy-form]');
    if (form) initForm(form);
    var detail = document.querySelector('[data-egy-detail]');
    if (detail) initDetail(detail);
    if (document.querySelector('[data-egy-vote]')) initVotes();
    var panel = document.querySelector('[data-egy-handle]');
    if (panel) initHandle(panel);
    var ov = document.querySelector('[data-egy-overview]');
    if (ov) initOverview(ov);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
