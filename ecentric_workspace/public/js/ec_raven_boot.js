// Copyright (c) 2026, eCentric and contributors
// ec_raven_boot.js - chen vao trang /raven (chat/boot.py after_request), NGAY SAU the <script>
// dat frappe.boot cua Raven va TRUOC module React cua Raven (module la defer). KHONG sua Raven.
//   1. Raven 3.0.0 dich bang window.frappe._messages nhung chi gan no o che do dev/offline ->
//      noi vao boot.__messages (da co ban dich tieng Viet tu hook extend_bootinfo).
//   2. ERP chi co giao dien sang; Raven mac dinh theo he dieu hanh -> may de che do toi ra khung
//      den giua trang ERP trang. Nguoi CHUA tu chon chu de trong Raven -> chon san "light".
(function () {
  'use strict';
  var f = window.frappe;
  if (f && f.boot && !f._messages) f._messages = f.boot.__messages || {};
  try {
    if (!window.localStorage.getItem('raven-theme')) window.localStorage.setItem('raven-theme', 'light');
  } catch (e) { /* chan luu tru: Raven tu xu ly */ }
})();
