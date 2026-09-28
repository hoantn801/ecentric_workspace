// Popup "Chao mung thanh vien moi" tren trang chu ERP (28/09/2026, Hoan chot: tu 08:30 ngay
// onboard). Du lieu: ecentric_workspace.approval_center.api.new_staff_preparation.welcome_today
// - server tu chan truoc 08:30 va chi tra phieu New Staff Preparation co ngay onboard = hom nay
// (chua Huy / Tu choi). Khong co gi ve luong.
//
// MOI NGUOI THAY MOT LAN / nhan vien moi: bam dong (hoac Esc / bam ra ngoai) la nho vao
// localStorage cua trinh duyet. Doi may / xoa du lieu trinh duyet thi thay lai - chap nhan
// duoc cho mot loi chao; luu phia server cho viec nay la ghi DB moi lan mot nguoi mo trang chu.
//
// LOI THI IM: day la loi chao trang tri, khong phai thao tac cua nguoi dung. Hien toast loi
// cho ca cong ty moi lan API hong con te hon khong co popup - chi ghi console de debug.
// ES6, khong co cap ngoac nhon kep hay ngoac-phan-tram cua Jinja (trang chu la Web Page Jinja).
//
// CHUA NAP O DAU (28/09/2026). A65 §6 (PO duyet cung ngay): module KHONG chen DOM / khoi
// <script id="ec-..."> vao trang chu; hien tren trang chu phai di qua KHE WIDGET co khai bao
// (chat Trang chu/Shell dang lam). Khi khe co: dang ky file nay vao khe - KHONG cam bang patch
// vao Web Page home, KHONG them vao web_include_js. Den luc do chi thiep Teams 10:00 chay.
(() => {
  'use strict';
  if (window._ecWelcomePopup) return;
  window._ecWelcomePopup = true;

  const METHOD = '/api/method/ecentric_workspace.approval_center.api.new_staff_preparation.welcome_today';
  const SEEN_KEY = 'ec_welcome_seen_';
  const ROOT_ID = 'ec-welcome-popup';

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const seen = (name) => {
    try { return window.localStorage.getItem(SEEN_KEY + name) === '1'; } catch (e) { return false; }
  };
  const markSeen = (rows) => {
    rows.forEach((r) => {
      try { window.localStorage.setItem(SEEN_KEY + r.name, '1'); } catch (e) { /* private mode */ }
    });
  };

  const injectStyle = () => {
    if (document.getElementById(ROOT_ID + '-style')) return;
    const st = document.createElement('style');
    st.id = ROOT_ID + '-style';
    st.textContent = [
      '#' + ROOT_ID + '{--ecw-navy:#2C3DA6;--ecw-navy-50:#eef0fb;--ecw-yellow:#FFC000;--ecw-ink:#111827;',
      '--ecw-muted:#6b7280;--ecw-line:#e5e7eb;--ecw-radius:16px;--ecw-gap:14px;',
      'position:fixed;inset:0;z-index:10050;display:flex;align-items:center;justify-content:center;',
      'padding:16px;background:rgba(17,24,39,.45);font-family:Inter,-apple-system,Segoe UI,sans-serif;}',
      '#' + ROOT_ID + ' .ecw-card{background:#fff;border-radius:var(--ecw-radius);width:min(520px,calc(100vw - 32px));',
      'max-height:calc(100vh - 48px);overflow:auto;box-shadow:0 24px 60px rgba(0,0,0,.25);}',
      '#' + ROOT_ID + ' .ecw-head{background:linear-gradient(135deg,var(--ecw-navy),#EF7CAF);color:#fff;',
      'padding:20px 22px;border-radius:var(--ecw-radius) var(--ecw-radius) 0 0;}',
      '#' + ROOT_ID + ' .ecw-title{margin:0;font-size:20px;font-weight:800;line-height:1.3;}',
      '#' + ROOT_ID + ' .ecw-sub{margin:6px 0 0;font-size:13.5px;opacity:.92;}',
      '#' + ROOT_ID + ' .ecw-body{padding:18px 22px;display:flex;flex-direction:column;gap:var(--ecw-gap);}',
      '#' + ROOT_ID + ' .ecw-person{border:1px solid var(--ecw-line);border-radius:12px;padding:14px 16px;}',
      '#' + ROOT_ID + ' .ecw-name{margin:0 0 8px;font-size:17px;font-weight:800;color:var(--ecw-ink);letter-spacing:.2px;}',
      '#' + ROOT_ID + ' .ecw-row{display:flex;gap:10px;font-size:13.5px;padding:3px 0;color:var(--ecw-ink);}',
      '#' + ROOT_ID + ' .ecw-row span{min-width:70px;color:var(--ecw-muted);}',
      '#' + ROOT_ID + ' .ecw-intro{margin:10px 0 0;padding:10px 12px;border-left:3px solid var(--ecw-yellow);',
      'background:var(--ecw-navy-50);border-radius:8px;font-size:13.5px;font-style:italic;color:#374151;white-space:pre-wrap;}',
      '#' + ROOT_ID + ' .ecw-foot{padding:0 22px 20px;display:flex;justify-content:flex-end;}',
      '#' + ROOT_ID + ' .ecw-btn{border:none;background:var(--ecw-navy);color:#fff;font-weight:700;font-size:14px;',
      'padding:10px 18px;border-radius:10px;cursor:pointer;}',
      '#' + ROOT_ID + ' .ecw-btn:focus-visible{outline:3px solid var(--ecw-yellow);outline-offset:2px;}',
      '@media (max-width:640px){#' + ROOT_ID + ' .ecw-title{font-size:18px;}#' + ROOT_ID + ' .ecw-body{padding:16px;}}',
    ].join('');
    document.head.appendChild(st);
  };

  const personHTML = (r) => {
    const ten = esc((r.candidate_name || '').toUpperCase());
    return '<section class="ecw-person">'
      + '<h3 class="ecw-name">' + ten + '</h3>'
      + '<div class="ecw-row"><span>Vị trí</span><b>' + esc(r.position || '—') + '</b></div>'
      + '<div class="ecw-row"><span>Bộ phận</span><b>' + esc(r.department || '—') + '</b></div>'
      + (r.welcome_intro ? '<p class="ecw-intro">' + esc(r.welcome_intro) + '</p>' : '')
      + '</section>';
  };

  const show = (rows) => {
    injectStyle();
    const prevFocus = document.activeElement;
    const ov = document.createElement('div');
    ov.id = ROOT_ID;
    ov.setAttribute('role', 'dialog');
    ov.setAttribute('aria-modal', 'true');
    ov.setAttribute('aria-labelledby', ROOT_ID + '-title');
    const many = rows.length > 1;
    ov.innerHTML = '<div class="ecw-card">'
      + '<header class="ecw-head"><h2 class="ecw-title" id="' + ROOT_ID + '-title">🌟 Chào mừng thành viên mới 🌟</h2>'
      + '<p class="ecw-sub">Hôm nay eCentric chính thức chào đón ' + (many ? rows.length + ' thành viên mới' : 'thành viên mới') + '. Cả nhà cùng say hi nhé!</p></header>'
      + '<main class="ecw-body">' + rows.map(personHTML).join('') + '</main>'
      + '<footer class="ecw-foot"><button type="button" class="ecw-btn" data-ecw-close>Chào mừng! 👋</button></footer>'
      + '</div>';
    const close = () => {
      markSeen(rows);
      ov.remove();
      document.removeEventListener('keydown', onKey, true);
      if (prevFocus && prevFocus.focus) { try { prevFocus.focus(); } catch (e) { /* ignore */ } }
    };
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    ov.addEventListener('click', (e) => {
      if (e.target === ov || (e.target.closest && e.target.closest('[data-ecw-close]'))) close();
    });
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(ov);
    const btn = ov.querySelector('[data-ecw-close]');
    if (btn) btn.focus();
  };

  const run = async () => {
    if (document.getElementById(ROOT_ID)) return;
    try {
      const res = await fetch(METHOD, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!res.ok) return;                                   // Guest / loi: im lang (xem dau file)
      const data = await res.json();
      const rows = ((data && data.message && data.message.rows) || []).filter((r) => r && r.name && !seen(r.name));
      if (rows.length) show(rows);
    } catch (err) {
      if (window.console && console.warn) console.warn('ec_welcome_popup:', err);
    }
  };

  window.EcWelcomePopup = { run, show, _seen: seen };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();
