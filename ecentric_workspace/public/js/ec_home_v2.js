// Copyright (c) 2026, eCentric and contributors
// Trang chu v2 -- CHI DO DU LIEU vao bo cuc da nam san trong HTML server
// (ecentric_workspace/legacy_pages/home/main_section.html).
//
// VI SAO FILE NAY NHO VA "NGHEO" (NHIEU_LOP giai doan 2, 29/09/2026). Ban truoc (khoi
// <script id="ec-home-v2"> do deploy_home_v2.ps1 chen vao trang) nhan HTML bo cuc CU tu
// server roi DUNG LAI DOM luc DOMContentLoaded, chen CSS vao cuoi <body>, sau do do chieu
// cao trang de gan lop ec2-fit1/fit2 va do offsetTop de gan ec2-bw1/bw2. Nguoi dung thay
// bo cuc cu nhay sang bo cuc moi roi co chu co lai. Gio bo cuc, CSS va cac nac gon
// (@container / @media) deu nam trong nguon trang, trinh duyet quyet dinh truoc lan ve dau.
// File nay:
//   - KHONG tao/di chuyen/an phan tu bo cuc, KHONG gan lop bo cuc, KHONG do kich thuoc
//     de chon co chu;
//   - chi ghi DU LIEU: vong tien do, ghim "bay gio", su kien dong thoi gian, hang doi,
//     cau "N viec gap"; va mo popover Lich khi NGUOI DUNG bam mot su kien.
// ES5, noi chuoi, khong template literal, khong token Jinja (hai ngoac nhon, ngoac-phan-tram...).
(function () {
  'use strict';
  var root = document.querySelector('[data-ec2-home]');
  if (!root || root.getAttribute('data-ec2-hydrated')) { return; }
  root.setAttribute('data-ec2-hydrated', '1');

  // Dong thoi gian la cua trang nay: bao widget Lich (pm_home_calendar.js) dung ve chip
  // vao .ec2-tlbody. Widget van ve panel Lich (an ngoai man) - popover dung chinh panel do.
  window.ecTimelineOwnsEvents = true;

  function q(sel) { return root.querySelector(sel); }
  function escH(x) {
    return String(x == null ? '' : x).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // ---------------------------------------------------------------- vong tien do ----
  // Tu so = o NGAY CONG (script cham cong cua trang do so vao), mau so = so ngay T2-T6
  // cua thang (giu nguyen cach tinh cua ban v2).
  function weekdaysInMonth(d) {
    var y = d.getFullYear(), m = d.getMonth(), n = 0, last = new Date(y, m + 1, 0).getDate();
    for (var i = 1; i <= last; i++) { var w = new Date(y, m, i).getDay(); if (w >= 1 && w <= 5) { n++; } }
    return n || 21;
  }
  var ring = q('[data-ec2-ring]');
  var attLabel = q('[data-ec-att-hours]');
  var attValue = attLabel && attLabel.parentElement && attLabel.parentElement.querySelector('.stat-value');
  function updRing() {
    if (!ring || !attValue) { return false; }
    var v = parseFloat(String(attValue.textContent || '').replace(',', '.'));
    if (isNaN(v)) { return false; }
    var den = weekdaysInMonth(new Date()), pct = Math.max(0, Math.min(1, v / den));
    var arc = ring.querySelector('.ec2-ringarc'), em = ring.querySelector('em'), b = ring.querySelector('.ec2-ringtx b');
    if (arc) { arc.setAttribute('stroke-dasharray', (pct * 100.5).toFixed(1) + ' 100.5'); }
    if (em) { em.textContent = Math.round(pct * 100) + '%'; }
    if (b) { b.textContent = v + ' / ' + den + ' ngày công'; }
    return true;
  }
  if (attValue) {
    updRing();
    // Doi o NGAY CONG doi chu (thay cho vong hoi 800 ms x 15 cua ban cu).
    if (window.MutationObserver) {
      try { new MutationObserver(updRing).observe(attValue, { childList: true, characterData: true, subtree: true }); } catch (e) { /* bo qua */ }
    }
  }

  // -------------------------------------------------------------- ghim "bay gio" ----
  var pin = q('.ec2-nowpin');
  function updPin() {
    if (!pin) { return; }
    var d = new Date(), h = d.getHours() + d.getMinutes() / 60;
    pin.style.left = (Math.min(Math.max((h - 8) / 10, 0), 1) * 100).toFixed(1) + '%';
  }
  updPin();
  setInterval(updPin, 60000);

  // ------------------------------------------------------------ dong thoi gian ----
  var tl = q('.ec2-tl'), tlBody = q('.ec2-tlbody');
  var cal = q('[data-ec2-cal-off]');   // panel "Lich hom nay" that, nam ngoai man

  // Lay su kien tu API cua widget Lich; widget cu khong co API thi doc chu cua panel.
  function apiEvents() {
    if (typeof window.ecCalEvents !== 'function') { return null; }
    try {
      var list = window.ecCalEvents() || [], out = [];
      // API tra "2026-08-26 16:00:00" (dau cach) hoac ISO co chu T - nhan ca hai.
      var RX = /[T ](\d{2}):(\d{2})/;
      for (var i = 0; i < list.length; i++) {
        var v = list[i], sm = RX.exec(v.start || ''), em = RX.exec(v.end || '');
        if (!sm || !em) { continue; }
        var sh = (+sm[1]) + (+sm[2]) / 60, eh = (+em[1]) + (+em[2]) / 60;
        if (!(eh > sh) || eh < 8 || sh > 18) { continue; }
        out.push({ s: Math.max(sh, 8), e: Math.min(eh, 18), t: v.subject || '',
                   lbl: sm[1] + ':' + sm[2] + '–' + em[1] + ':' + em[2],
                   key: v.key || v.id || '', kind: v.kind || 'm' });
      }
      return out;
    } catch (e) { return null; }
  }
  function parseCal() {
    if (!cal) { return []; }
    var lines = String(cal.innerText || '').split('\n');
    var re = /(\d{1,2}):(\d{2})\s*[–—-]\s*(\d{1,2}):(\d{2})/;
    var skip = /^(room|phòng|teams|microsoft|online|tham gia|bạn là|xem lịch|họp sắp)/i;
    function okTitle(x) { return x && !re.test(x) && !skip.test(x); }
    var evs = [], seen = {}, prev = '';
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i].trim();
      if (!ln) { continue; }
      var m = ln.match(re);
      if (!m) { prev = ln; continue; }
      var t = ln.replace(re, '').replace(/^[\s·.,-]+|[\s·.,-]+$/g, '');
      var nx = (lines[i + 1] || '').trim();
      if (!okTitle(t)) { t = okTitle(nx) ? nx : (okTitle(prev) ? prev : ''); }
      if (!t) { continue; }
      var sh = (+m[1]) + (+m[2]) / 60, eh = (+m[3]) + (+m[4]) / 60;
      if (!(eh > sh) || eh < 8 || sh > 18) { continue; }
      var key = m[0] + '|' + t.toLowerCase();
      if (seen[key]) { continue; }
      seen[key] = 1;
      evs.push({ s: Math.max(sh, 8), e: Math.min(eh, 18), t: t, lbl: m[0] });
    }
    return evs;
  }

  // Xep su kien vao lan (tham lam). Tra ve so lan; moi su kien duoc gan .lane.
  function assignLanes(evs) {
    var ends = [];
    for (var i = 0; i < evs.length; i++) {
      var lane = 0;
      while (lane < ends.length && ends[lane] > evs[i].s + 0.01) { lane++; }
      ends[lane] = evs[i].e;
      evs[i].lane = lane;
    }
    return ends.length;
  }

  var EMPTY_TXT = 'H\u00f4m nay ch\u01b0a c\u00f3 h\u1ecdp hay vi\u1ec7c \u0111\u00e3 x\u1ebfp gi\u1edd \u2014 s\u1ef1 ki\u1ec7n s\u1ebd hi\u1ec7n \u1edf \u0111\u00e2y.';
  function renderTl(evs) {
    if (!tl || !tlBody) { return; }
    // Nguoi co quyen PM: server ve san trang thai "dang tai lich" (du chieu cao) de su kien
    // ve KHONG day luoi ben duoi xuong. Co du lieu roi thi het trang thai do.
    tl.removeAttribute('data-ec2-tl-loading');
    var old = tlBody.querySelectorAll('.ec2-ev');
    for (var o = 0; o < old.length; o++) { old[o].parentNode.removeChild(old[o]); }
    evs = (evs || []).slice(0, 6);
    // Khong co su kien -> the "phang": o man thap CSS thu dai gio con mot dong chu.
    tl.classList.toggle('ec2-tlflat', !evs.length);
    tlBody.classList.toggle('ec2-hasev', evs.length > 0);
    if (!evs.length) {
      tlBody.style.removeProperty('--ec2-lanes');
      var emp = tlBody.querySelector('.ec2-tlempty');
      if (emp && emp.textContent !== EMPTY_TXT) { emp.textContent = EMPTY_TXT; }
      return;
    }
    var lanes = assignLanes(evs);
    // Chieu cao khung / vi tri doc / be ngang toi thieu cua chip nam trong CSS (bien
    // --ec2-lane, --ec2-tlminh, --ec2-evmin theo co man). O day chi ghi DU LIEU.
    tlBody.style.setProperty('--ec2-lanes', String(lanes));
    for (var i = 0; i < evs.length; i++) {
      var ev = evs[i], el = document.createElement('div');
      el.className = 'ec2-ev' + (ev.kind === 'b' ? ' ec2-ev-b' : '');
      el.style.left = (((ev.s - 8) / 10) * 100) + '%';
      el.style.width = Math.max(((ev.e - ev.s) / 10) * 100, 6) + '%';
      el.style.setProperty('--ec2-l', String(ev.lane));
      // Khong dung thuoc tinh title (tooltip native khong style duoc, PO 26/08); ten day du
      // nam trong popover khi bam.
      el.setAttribute('aria-label', ev.t + ' ' + ev.lbl);
      el.setAttribute('role', 'button');
      el.tabIndex = 0;
      el.textContent = ev.t;
      bindOpen(el, ev.key || '');
      tlBody.appendChild(el);
    }
  }
  function refreshTl() {
    var evs = apiEvents();
    // null = widget khong co API; MANG RONG trong khi panel VAN co su kien = payload doi
    // dang -> cung doc chu cua panel, neu khong dong thoi gian trong ma khong ai biet vi sao.
    if (evs === null || (evs.length === 0 && parseCal().length > 0)) { evs = parseCal(); }
    renderTl(evs);
  }
  // Widget Lich ban su kien nay moi lan tai xong du lieu.
  document.addEventListener('ec-cal-today', refreshTl);
  // Widget Lich khong bao gio bao (API loi / widget khong nap): sau 8 giay coi nhu khong co su
  // kien, de the khong treo o "dang tai" mai.
  if (tl && tl.getAttribute('data-ec2-tl-loading')) {
    setTimeout(function () { if (tl.getAttribute('data-ec2-tl-loading')) { refreshTl(); } }, 8000);
  }

  // ---- popover: bam mot su kien -> mo chinh panel Lich (nut Tham gia / RSVP la cua widget)
  var calAnchor = null;
  function placeCalPop() {
    var a = calAnchor;
    if (!a || !cal || !cal.getAttribute('data-ec2-cal-pop')) { return; }
    var r = a.getBoundingClientRect();
    var vw = window.innerWidth || 1280, vh = window.innerHeight || 800;
    var w = Math.min(430, vw - 32), s = cal.style;
    s.setProperty('width', w + 'px', 'important');
    s.setProperty('right', 'auto', 'important');
    var h = Math.min(cal.offsetHeight || 320, Math.round(vh * 0.72));
    var left = Math.max(16, Math.min(r.left + r.width / 2 - w / 2, vw - w - 16));
    // San duoi = day khung su kien: popover khong de len chip o lan duoi (PO 26/08).
    var floorY = tlBody ? tlBody.getBoundingClientRect().bottom + 6 : r.bottom + 8;
    var top = Math.max(r.bottom + 8, floorY);
    if (top + h > vh - 16) {
      var above = r.top - h - 10;
      top = (above >= 16) ? above : Math.max(16, vh - h - 16);
    }
    s.setProperty('left', Math.round(left) + 'px', 'important');
    s.setProperty('top', Math.round(top) + 'px', 'important');
  }
  function outsideCal(e) { if (cal && !cal.contains(e.target)) { closeCalPop(); } }
  function closeCalPop() {
    if (!cal) { return; }
    cal.removeAttribute('data-ec2-cal-pop');
    calAnchor = null;
    var s = cal.style;
    s.removeProperty('left'); s.removeProperty('top'); s.removeProperty('right'); s.removeProperty('width');
    window.removeEventListener('resize', placeCalPop);
    window.removeEventListener('scroll', placeCalPop, true);
    document.removeEventListener('mousedown', outsideCal, true);
  }
  function openCalPop(key, anchor) {
    if (!cal) { return; }
    calAnchor = anchor || null;
    cal.setAttribute('data-ec2-cal-pop', '1');
    placeCalPop();
    // widget dua su kien len the "hero" sau vai chuc ms -> chieu cao doi, dat lai vi tri
    setTimeout(placeCalPop, 90);
    setTimeout(placeCalPop, 320);
    window.addEventListener('resize', placeCalPop);
    window.addEventListener('scroll', placeCalPop, true);
    setTimeout(function () { document.addEventListener('mousedown', outsideCal, true); }, 0);
    if (key && typeof window.ecCalFocus === 'function') {
      setTimeout(function () { try { window.ecCalFocus(key); } catch (e) { /* bo qua */ } }, 60);
    }
  }
  function bindOpen(node, key) {
    node.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); openCalPop(key, node); });
    node.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCalPop(key, node); }
    });
  }

  // ------------------------------------------------------------------ hang doi ----
  var qPanel = q('.ec2-queue');
  var qBody = qPanel && qPanel.querySelector('.ec2-qbody');
  var qBadge = qPanel && qPanel.querySelector('.ec2-qn');
  var ICO = {
    approval: "<svg viewBox='0 0 24 24'><path d='M9 11 12 14 22 4'/><path d='M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11'/></svg>",
    fulfillment: "<svg viewBox='0 0 24 24'><path d='M4 13h4l2 3h4l2-3h4'/><path d='M4 13V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7'/><path d='M4 13v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5'/></svg>",
    task: "<svg viewBox='0 0 24 24'><rect x='3' y='7' width='18' height='13' rx='2'/><path d='M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2'/></svg>",
    weekly_report: "<svg viewBox='0 0 24 24'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/></svg>",
    generic: "<svg viewBox='0 0 24 24'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><path d='M14 2v6h6'/></svg>"
  };
  var GROUPS = [['overdue', 'GẤP', 'hot'], ['act_now', 'ĐANG XỬ LÝ', 'now'], ['upcoming', 'SẮP TỚI', 'ok']];
  function due(it) {
    var d = String(it.due_at || '').slice(0, 10);
    return d ? escH(d.slice(8, 10) + '/' + d.slice(5, 7)) : '';
  }
  function qEmpty(msg) { return '<div class="ec2-qempty">' + msg + '</div>'; }
  function renderQueue(m) {
    if (!qBody) { return; }
    if (!m || !m.success) { qBody.innerHTML = qEmpty('Không tải được danh sách việc.'); return; }
    if (qBadge && m.total) { qBadge.textContent = m.total; qBadge.hidden = false; }
    var html = '';
    for (var gi = 0; gi < GROUPS.length; gi++) {
      var g = GROUPS[gi], items = (m.bucket_items && m.bucket_items[g[0]]) || [];
      if (!items.length) { continue; }
      html += '<div class="ec2-qg ec2-qg-' + g[2] + '">' + g[1] + '</div>';
      for (var ii = 0; ii < Math.min(items.length, 3); ii++) {
        var it = items[ii], dd = due(it);
        html += '<a class="ec2-qi" href="' + escH(it.action_url || '#') + '">' +
          '<span class="ec2-qtile ec2-qtile-' + g[2] + '">' + (ICO[it.source_type] || ICO.generic) + '</span>' +
          '<span class="ec2-qtx"><b>' + escH(it.title || '') + '</b><span>' + escH(it.subtitle || '') + '</span></span>' +
          (dd ? '<i class="ec2-qp ec2-qp-' + g[2] + '">' + dd + '</i>' : '') +
          '<i class="ec2-qch">›</i></a>';
      }
    }
    qBody.innerHTML = html || qEmpty('Bạn không có việc nào cần xử lý. 🎉');
    // "— N viec gap dang cho" noi sau dong ngay tren dai navy
    var od = (m.counts && m.counts.overdue) || 0, gp = q('.ec2-who .greeting p');
    if (od > 0 && gp && !gp.querySelector('.ec2-hot')) {
      var sp = document.createElement('span');
      sp.className = 'ec2-hot';
      sp.textContent = ' — ' + od + ' việc gấp đang chờ';
      gp.appendChild(sp);
    }
  }
  var METHOD = 'ecentric_workspace.action_center.api.get_reminder_summary';
  if (qBody) {
    // Khung menu (ec_shell) cung xin dung ban tom tat nay luc mo trang. Di qua ecApi thi hai
    // ben dung chung MOT request (NHIEU_LOP GD 1.2).
    var req = window.ecApi
      ? window.ecApi.get(METHOD, null, { shareMs: 15000 })
      : fetch('/api/method/' + METHOD, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
          .then(function (r) { return r.json(); }).then(function (j) { return j && j.message; });
    req.then(renderQueue, function () { renderQueue(null); });
  }
})();
