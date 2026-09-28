// Copyright (c) 2026, eCentric and contributors
// ec_api.js -- MOT client goi app method cho moi trang web (A65 / NHIEU_LOP GD 1.2 + 1.3).
//
// VI SAO. Do 28/09/2026 tren live:
//   - trang chu goi get_reminder_summary 2 lan luc mo (khung menu + khoi trang chu),
//     /alerts/policies goi mot API 21 lan, form GBS goi get_csrf 3 lan;
//   - 32/85 trang mang ban va CSRF chep tay (`ec-csrf-fetch-patch`), 2 phien ban khac nhau.
// File nay la cho DUY NHAT lam hai viec do:
//
//   ecApi.get(method, args, {shareMs})
//     GET /api/method/<method>. Loi goi giong nhau (cung method + args) DANG BAY dung chung
//     MOT promise. shareMs > 0: ket qua THANH CONG con duoc dung lai neu chua qua shareMs ms
//     -- nguoi goi tu chon do tuoi chap nhan duoc, mac dinh 0 = khong dung lai. Loi khong
//     bao gio duoc nho. Tra ve `message` cua Frappe.
//
//   ecApi.post(method, data)
//     POST JSON. Xin CSRF TUOI tu /api/method/get_csrf truoc lan dau (cac lan xin dang bay
//     dung chung). HTML trang co the la ban cache mang token cua phien khac (su co 14/09
//     va 17/09), nen KHONG tin window.frappe.csrf_token. Gap CSRFTokenError -- doc theo
//     NOI DUNG `exc_type`, khong theo HTTP status -- thi xoa token, xin lai, thu DUNG mot
//     lan. Lan hai van loi: nem Error co `csrf = true` de trang bao "Ctrl+Shift+R".
//
// KHONG boc window.fetch. Chuoi wrapper fetch tung gay de quy vo han, trang /approval treo
// o "Loading GBS detail..." (07/2026). Trang cu giu ec-csrf-fetch-patch cho toi khi chuyen
// sang ecApi.post roi moi xoa khoi do.
//
// Test: node ecentric_workspace/public/js/tests/test_ec_api.js
(function () {
  'use strict';
  if (window.ecApi) return;                         // mot lan cho moi trang

  var METHOD = '/api/method/';
  var CSRF_URL = '/api/method/get_csrf';
  var CSRF_ERROR = 'CSRFTokenError';
  var memo = {};                                    // key -> { pending, at, promise }
  var csrf = { token: '', pending: null };

  function qs(args) {
    if (!args) return '';
    var keys = Object.keys(args).sort();
    var parts = [];
    for (var i = 0; i < keys.length; i++) {
      var v = args[keys[i]];
      if (v === undefined || v === null) continue;
      if (typeof v === 'object') v = JSON.stringify(v);
      parts.push(encodeURIComponent(keys[i]) + '=' + encodeURIComponent(String(v)));
    }
    return parts.join('&');
  }

  function readJson(r) {
    return r.json().then(function (j) { return j; }, function () { return null; });
  }

  function toError(status, body) {
    var e = new Error((body && (body.exc_type || body.exception)) || ('HTTP ' + status));
    e.status = status;
    e.excType = (body && body.exc_type) || '';
    e.body = body;
    return e;
  }

  function get(method, args, opts) {
    var q = qs(args);
    var key = method + (q ? '?' + q : '');
    var shareMs = (opts && opts.shareMs) || 0;
    var hit = memo[key];
    if (hit && (hit.pending || (shareMs > 0 && Date.now() - hit.at < shareMs))) return hit.promise;
    var entry = { pending: true, at: 0, promise: null };
    entry.promise = fetch(METHOD + key, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) {
        return readJson(r).then(function (j) {
          if (!r.ok || (j && j.exc_type)) throw toError(r.status, j);
          return j ? j.message : undefined;
        });
      })
      .then(function (m) {
        entry.pending = false;
        entry.at = Date.now();
        return m;
      }, function (e) {
        if (memo[key] === entry) delete memo[key];  // loi khong bao gio duoc nho
        throw e;
      });
    memo[key] = entry;
    return entry.promise;
  }

  function fetchCsrf(force) {
    if (!force && csrf.token) return Promise.resolve(csrf.token);
    if (csrf.pending) return csrf.pending;
    var p = fetch(CSRF_URL, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(readJson)
      .then(function (j) {
        var m = (j && j.message) || {};
        csrf.token = (m.csrf_token && !m.is_guest) ? String(m.csrf_token) : '';
        csrf.pending = null;
        // Code cu cua trang van doc frappe.csrf_token: dua no ve token tuoi luon.
        if (csrf.token && window.frappe) window.frappe.csrf_token = csrf.token;
        return csrf.token;
      }, function (e) {
        csrf.pending = null;
        throw e;
      });
    csrf.pending = p;
    return p;
  }

  function isCsrfError(j) {
    return !!j && j.exc_type === CSRF_ERROR;
  }

  function sendPost(method, data, token) {
    var headers = { Accept: 'application/json', 'Content-Type': 'application/json' };
    if (token) headers['X-Frappe-CSRF-Token'] = token;
    return fetch(METHOD + method, {
      method: 'POST', credentials: 'same-origin', headers: headers, body: JSON.stringify(data || {})
    }).then(function (r) {
      return readJson(r).then(function (j) { return { r: r, j: j }; });
    });
  }

  function post(method, data) {
    return fetchCsrf(false)
      .then(function (tok) { return sendPost(method, data, tok); })
      .then(function (res) {
        if (!isCsrfError(res.j)) return res;
        csrf.token = '';                             // token cu (HTML cache / phien khac)
        return fetchCsrf(true).then(function (tok) { return sendPost(method, data, tok); });
      })
      .then(function (res) {
        if (isCsrfError(res.j)) {
          var e = toError(res.r.status, res.j);
          e.csrf = true;                             // trang bao: Ctrl+Shift+R / dang nhap lai
          throw e;
        }
        if (!res.r.ok || (res.j && res.j.exc_type)) throw toError(res.r.status, res.j);
        return res.j ? res.j.message : undefined;
      });
  }

  window.ecApi = { get: get, post: post, csrfToken: fetchCsrf };
})();
