// Copyright (c) 2026, eCentric and contributors
// Web Push client (PWA) - dang ky service worker + xin quyen + dong bo dang ky.
//
// TAI SAO KHONG TU DONG HIEN HOP XIN QUYEN
//   Chrome/Firefox chan requestPermission() khi khong co cu cham cua nguoi dung, va
//   mot hop thoai bat ra ngay khi vua mo trang gan nhu chac chan bi bam "Chan" -
//   ma "Chan" la vinh vien, khong xin lai duoc. Vi the o day chi hien MOT dai nho
//   co the tat, va chi goi requestPermission() tu su kien click that su.
//
// IPHONE
//   iOS chi cho web push khi trang da duoc "Them vao man hinh chinh" (PWA standalone).
//   Trong Safari thong thuong, window.PushManager KHONG ton tai -> dai se khong hien
//   va ta huong dan qua kenh khac. Day la gioi han cua iOS, khong phai loi cau hinh.
(function () {
  'use strict';
  if (window._ecWebPushInstalled) { return; }
  var p = window.location.pathname || '';
  if (p === '/app' || p.indexOf('/app/') === 0) { return; }   // Desk co he thong rieng
  window._ecWebPushInstalled = true;

  var API = '/api/method/ecentric_workspace.notification_center.api.';
  var DISMISS_KEY = 'ec_webpush_banner_dismissed';
  var SYNC_KEY = 'ec_webpush_synced_endpoint';

  function supported() {
    return ('serviceWorker' in navigator) && ('PushManager' in window) &&
           ('Notification' in window);
  }

  function ls(get, key, val) {
    try { return get ? window.localStorage.getItem(key) : window.localStorage.setItem(key, val); }
    catch (e) { return null; }
  }

  function post(method, params) {
    var body = new URLSearchParams();
    Object.keys(params || {}).forEach(function (k) { body.append(k, params[k] == null ? '' : params[k]); });
    var h = { 'Content-Type': 'application/x-www-form-urlencoded' };
    if (window.frappe && window.frappe.csrf_token) { h['X-Frappe-CSRF-Token'] = window.frappe.csrf_token; }
    return fetch(API + method, { method: 'POST', credentials: 'include', headers: h, body: body.toString() })
      .then(function (r) { return r.json(); });
  }

  // base64url -> Uint8Array (dinh dang bat buoc cua applicationServerKey)
  function keyToBytes(b64) {
    var pad = '='.repeat((4 - (b64.length % 4)) % 4);
    var s = (b64 + pad).replace(/-/g, '+').replace(/_/g, '/');
    var raw = window.atob(s);
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) { out[i] = raw.charCodeAt(i); }
    return out;
  }

  var _reg = null;
  function register() {
    if (_reg) { return Promise.resolve(_reg); }
    return navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(function (r) {
      _reg = r; return r;
    });
  }

  function serverConfig() {
    return fetch(API + 'webpush_public_key', { credentials: 'include' })
      .then(function (r) { return r.json(); })
      .then(function (j) { return (j && j.message) || { enabled: false }; })
      .catch(function () { return { enabled: false }; });
  }

  function sendSubscription(sub) {
    var j = sub.toJSON();
    // Chi goi server khi endpoint THAY DOI so voi lan truoc -> moi lan mo trang khong
    // ban them mot POST vo ich (70 nguoi x nhieu trang = rat nhieu ghi DB thua).
    if (ls(true, SYNC_KEY) === j.endpoint) { return Promise.resolve({ cached: true }); }
    return post('webpush_subscribe', {
      endpoint: j.endpoint,
      p256dh: (j.keys && j.keys.p256dh) || '',
      auth: (j.keys && j.keys.auth) || '',
      user_agent: navigator.userAgent || '',
      platform: navigator.platform || ''
    }).then(function (res) {
      if (res && res.message && res.message.success) { ls(false, SYNC_KEY, j.endpoint); }
      return res;
    });
  }

  function subscribe(reg, publicKey) {
    return reg.pushManager.getSubscription().then(function (existing) {
      if (existing) { return existing; }
      return reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyToBytes(publicKey)
      });
    });
  }

  // ---- API cong khai: goi TU MOT CU CLICK that su -------------------------------
  window.ecEnableWebPush = function () {
    if (!supported()) {
      return Promise.resolve({ ok: false, reason: 'unsupported' });
    }
    return serverConfig().then(function (cfg) {
      if (!cfg.enabled || !cfg.public_key) { return { ok: false, reason: 'server_disabled' }; }
      return Notification.requestPermission().then(function (perm) {
        if (perm !== 'granted') { return { ok: false, reason: perm }; }
        return register()
          .then(function (reg) { return subscribe(reg, cfg.public_key); })
          .then(sendSubscription)
          .then(function () { return { ok: true }; });
      });
    }).catch(function (e) {
      return { ok: false, reason: String(e && e.message || e) };
    });
  };

  window.ecDisableWebPush = function () {
    if (!supported()) { return Promise.resolve({ ok: false }); }
    return register().then(function (reg) {
      return reg.pushManager.getSubscription();
    }).then(function (sub) {
      if (!sub) { return { ok: true }; }
      var ep = sub.toJSON().endpoint;
      return sub.unsubscribe().then(function () {
        ls(false, SYNC_KEY, '');
        return post('webpush_unsubscribe', { endpoint: ep });
      }).then(function () { return { ok: true }; });
    }).catch(function () { return { ok: false }; });
  };

  // ---- dai moi bat thong bao (chi khi CHUA tra loi quyen bao gio) ---------------
  function banner() {
    if (ls(true, DISMISS_KEY) === '1') { return; }
    var box = document.createElement('div');
    box.setAttribute('role', 'region');
    box.setAttribute('aria-label', 'Bat thong bao');
    box.style.cssText = [
      'position:fixed', 'left:12px', 'right:12px', 'bottom:12px', 'z-index:9998',
      'max-width:460px', 'margin:0 auto', 'padding:12px 14px', 'border-radius:12px',
      'background:#111827', 'color:#f9fafb', 'box-shadow:0 8px 24px rgba(0,0,0,.28)',
      'font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif',
      'display:flex', 'gap:10px', 'align-items:center', 'flex-wrap:wrap'
    ].join(';');

    var txt = document.createElement('div');
    txt.style.cssText = 'flex:1 1 200px;min-width:0';
    txt.textContent = 'Bật thông báo để không quên chấm công — báo ngay trên màn hình điện thoại.';

    var yes = document.createElement('button');
    yes.type = 'button';
    yes.textContent = 'Bật';
    yes.style.cssText = 'flex:0 0 auto;padding:7px 16px;border:0;border-radius:8px;background:#2563eb;color:#fff;font-weight:600;cursor:pointer';

    var no = document.createElement('button');
    no.type = 'button';
    no.textContent = 'Để sau';
    no.style.cssText = 'flex:0 0 auto;padding:7px 12px;border:0;border-radius:8px;background:transparent;color:#9ca3af;cursor:pointer';

    function close() { if (box.parentNode) { box.parentNode.removeChild(box); } }
    no.addEventListener('click', function () { ls(false, DISMISS_KEY, '1'); close(); });
    yes.addEventListener('click', function () {
      yes.disabled = true;
      yes.textContent = 'Đang bật…';
      window.ecEnableWebPush().then(function (r) {
        ls(false, DISMISS_KEY, '1');
        if (r && r.ok) {
          txt.textContent = 'Đã bật. Từ giờ thông báo sẽ hiện ngay trên máy của bạn.';
          yes.style.display = 'none'; no.textContent = 'Đóng';
          setTimeout(close, 4000);
        } else {
          close();
        }
      });
    });

    box.appendChild(txt); box.appendChild(yes); box.appendChild(no);
    document.body.appendChild(box);
  }

  function boot() {
    if (!supported()) { return; }
    register().then(function (reg) {
      return serverConfig().then(function (cfg) {
        if (!cfg.enabled || !cfg.public_key) { return; }
        if (Notification.permission === 'granted') {
          // Da cap quyen tu truoc -> chi dam bao server van con dang ky dung.
          return subscribe(reg, cfg.public_key).then(sendSubscription);
        }
        if (Notification.permission === 'default') {
          banner();
        }
        // 'denied' -> khong lam gi: trinh duyet khong cho xin lai.
      });
    }).catch(function () { /* fail-open: khong bao gio lam hong trang */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(boot, 1200); });
  } else {
    setTimeout(boot, 1200);
  }
})();
