// Copyright (c) 2026, eCentric and contributors
// ec_people_picker.bundle.js - o CHON NGUOI dung chung cho moi form (24/11/2026, Hoan: "o mail nay
// khong co dropdown").
//
// Trang khai trong markup NGUON: <input data-model="line_manager" data-ec-people> (mot nguoi) hoac
// data-ec-people="multi" (nhieu nguoi, gia tri "a@x, b@y"). Gia tri gui server GIU NGUYEN la email
// (khong doi schema): asset chi goi y + dien email vao CHINH o goc roi phat 'input' + 'change' de
// handler san co cua trang (attachModel...) nhan. Go asset di la o tro lai o nhap email nhu cu.
//   * mot nguoi: o goc giu nguyen, go >= 2 ky tu -> danh sach goi y (ten, email, phong ban);
//     ↑ ↓ chon, Enter dien, Esc dong; da chon thi hien ten + phong ban duoi o.
//   * nhieu nguoi: o goc an, hien chip + o tim; Backspace o trong xoa chip cuoi.
// Danh ba: ecentric_workspace.approval_center.api.people.search_users (GET, chi System User dang bat,
// chi email / ho ten / phong ban). Ten nguoi luon esc() truoc khi ve.
(function () {
  'use strict';
  if (window.EcPeoplePicker) return;
  var API = 'ecentric_workspace.approval_center.api.people.search_users';
  var MAX_MULTI = 30;
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function isEmail(s) { return /^[^\s@,;]+@[^\s@,;]+\.[a-z]{2,}$/i.test(String(s || '').trim()); }
  function search(q) {
    var fr = window.frappe;
    if (!fr || !fr.call) return Promise.reject(new Error('no frappe'));
    return fr.call({ method: API, args: { q: q }, type: 'GET' }).then(function (r) { return (r && r.message) || []; });
  }
  function fire(inp) {
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function split(v) {
    return String(v || '').split(/[,;\n]/).map(function (x) { return x.trim(); }).filter(Boolean);
  }

  // Khung goi y dung chung (gan vao mot o go chu).
  function suggest(typeEl, host, onPick, exclude) {
    var drop = document.createElement('div');
    drop.className = 'ec-pp-drop';
    drop.setAttribute('role', 'listbox');
    drop.hidden = true;
    host.appendChild(drop);
    var timer = null, seq = 0, items = [], idx = -1;
    function close() { drop.hidden = true; items = []; idx = -1; typeEl.setAttribute('aria-expanded', 'false'); }
    function paint() {
      drop.innerHTML = items.length ? items.map(function (r, i) {
        return '<div class="ec-pp-opt' + (i === idx ? ' on' : '') + '" role="option" data-i="' + i + '"><b>' + esc(r.full_name || r.user)
          + '</b><small>' + esc(r.user) + (r.department ? ' · ' + esc(r.department) : '') + '</small></div>';
      }).join('') : '<div class="ec-pp-none">Không tìm thấy người phù hợp.</div>';
      drop.hidden = false;
      typeEl.setAttribute('aria-expanded', 'true');
    }
    function pick(i) { var r = items[i]; if (!r) return; close(); onPick(r); }
    function run() {
      var t = typeEl.value.trim();
      if (t.length < 2) { close(); return; }
      var my = ++seq;
      search(t).then(function (rows) {
        if (my !== seq) return;
        var ex = exclude ? exclude() : [];
        items = (rows || []).filter(function (r) { return ex.indexOf(String(r.user).toLowerCase()) < 0; });
        idx = items.length ? 0 : -1;
        paint();
      }).catch(function () { if (my !== seq) return; items = []; drop.innerHTML = '<div class="ec-pp-none">Không tải được danh bạ.</div>'; drop.hidden = false; });
    }
    typeEl.setAttribute('autocomplete', 'off');
    typeEl.setAttribute('aria-autocomplete', 'list');
    typeEl.addEventListener('input', function () { if (typeEl.__ecPPSilent) return; clearTimeout(timer); timer = setTimeout(run, 220); });
    typeEl.addEventListener('keydown', function (e) {
      if (drop.hidden) return;
      if (e.key === 'ArrowDown' && items.length) { e.preventDefault(); idx = (idx + 1) % items.length; paint(); }
      else if (e.key === 'ArrowUp' && items.length) { e.preventDefault(); idx = (idx - 1 + items.length) % items.length; paint(); }
      else if (e.key === 'Enter' && idx >= 0) { e.preventDefault(); pick(idx); }
      else if (e.key === 'Escape') { e.preventDefault(); close(); }
    });
    typeEl.addEventListener('blur', function () { setTimeout(close, 150); });
    drop.addEventListener('mousedown', function (e) {
      var o = e.target.closest('[data-i]');
      if (!o) return;
      e.preventDefault();
      pick(+o.getAttribute('data-i'));
    });
    return { close: close };
  }

  function enhanceSingle(inp) {
    var host = document.createElement('div');
    host.className = 'ec-pp';
    inp.parentNode.insertBefore(host, inp);
    host.appendChild(inp);
    var who = document.createElement('div');
    who.className = 'ec-pp-who';
    host.appendChild(who);
    function showWho(r) { who.innerHTML = r ? esc(r.full_name || r.user) + (r.department ? ' <span>· ' + esc(r.department) + '</span>' : '') : ''; }
    suggest(inp, host, function (r) {
      inp.value = r.user;
      inp.__ecPPSilent = true;
      try { fire(inp); } finally { inp.__ecPPSilent = false; }
      showWho(r);
    });
    inp.addEventListener('input', function () { if (!inp.__ecPPSilent && who.innerHTML) showWho(null); });
  }

  function enhanceMulti(inp) {
    var host = document.createElement('div');
    host.className = 'ec-pp ec-pp-multi';
    inp.parentNode.insertBefore(host, inp);
    var chips = document.createElement('div');
    chips.className = 'ec-pp-chips';
    var q = document.createElement('input');
    q.type = 'text';
    q.className = 'ec-pp-q';
    q.placeholder = inp.getAttribute('placeholder') || 'Gõ tên hoặc email…';
    q.setAttribute('aria-label', inp.getAttribute('aria-label') || 'Thêm người');
    chips.appendChild(q);
    host.appendChild(chips);
    host.appendChild(inp);
    inp.style.display = 'none';
    var names = {};
    function list() { return split(inp.value); }
    function set(l) { inp.value = l.join(', '); paint(); fire(inp); }
    function paint() {
      Array.prototype.slice.call(chips.querySelectorAll('.ec-pp-chip')).forEach(function (c) { c.remove(); });
      list().forEach(function (u) {
        var c = document.createElement('span');
        c.className = 'ec-pp-chip';
        c.title = u;
        c.innerHTML = esc(names[u.toLowerCase()] || u) + '<button type="button" aria-label="Bỏ ' + esc(names[u.toLowerCase()] || u) + '" data-rm="' + esc(u) + '">&times;</button>';
        chips.insertBefore(c, q);
      });
    }
    function add(u, name) {
      u = String(u || '').trim().toLowerCase();
      if (!u) return;
      var l = list();
      if (l.map(function (x) { return x.toLowerCase(); }).indexOf(u) >= 0) return;
      if (l.length >= MAX_MULTI) return;
      if (name) names[u] = name;
      l.push(u);
      set(l);
    }
    chips.addEventListener('click', function (e) {
      var b = e.target.closest('[data-rm]');
      if (b) { var u = b.getAttribute('data-rm'); set(list().filter(function (x) { return x !== u; })); q.focus(); return; }
      q.focus();
    });
    suggest(q, host, function (r) { add(r.user, r.full_name); q.value = ''; q.focus(); },
      function () { return list().map(function (x) { return x.toLowerCase(); }); });
    q.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && isEmail(q.value)) { e.preventDefault(); add(q.value); q.value = ''; }
      else if (e.key === 'Backspace' && !q.value && list().length) { var l = list(); l.pop(); set(l); }
    });
    q.addEventListener('blur', function () { if (isEmail(q.value)) { add(q.value); q.value = ''; } });
    paint();
  }

  function enhance(inp) {
    if (!inp || inp.__ecPP || inp.type === 'hidden' || inp.disabled || inp.readOnly) return;
    inp.__ecPP = true;
    if ((inp.getAttribute('data-ec-people') || '').toLowerCase() === 'multi') enhanceMulti(inp);
    else enhanceSingle(inp);
  }
  function scan(root) {
    (root || document).querySelectorAll('input[data-ec-people]').forEach(enhance);
  }
  function start() {
    scan();
    var pending = null;
    new MutationObserver(function () { clearTimeout(pending); pending = setTimeout(scan, 60); })
      .observe(document.documentElement, { childList: true, subtree: true });
  }
  window.EcPeoplePicker = { scan: scan, enhance: enhance, isEmail: isEmail };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
