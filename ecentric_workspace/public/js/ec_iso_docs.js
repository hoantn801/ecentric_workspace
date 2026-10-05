// Copyright (c) 2026, eCentric and contributors
// ec_iso_docs.js - Thu vien tai lieu ISO (/tai-lieu, /tai-lieu/<ma>, /tai-lieu/quan-ly).
//
// Server da ve san moi trang. File nay chi:
//   1. trang tai lieu: ve so do mermaid (securityLevel strict), phong to / thu nho, chon vai tro
//      -> to sang cac buoc cua vai tro do + liet ke "viec cua <vai tro>";
//   2. trang quan ly: bam buoc duyet (POST iso_docs.api.action) roi tai lai trang;
//   3. nhap goi: doc goi.json + tep (base64), POST iso_docs.api.import_package.
// Goi server qua window.ecApi (CSRF tuoi). Loi -> thong bao tieng Viet tu server.
(function () {
  'use strict';

  const API = 'ecentric_workspace.iso_docs.api.';
  const FILE_MAX = 20 * 1024 * 1024;
  const TOTAL_MAX = 24 * 1024 * 1024;

  // ------------------------------------------------------------------ tien ich ------
  let toastTimer = null;
  function toast(msg, isErr) {
    const t = document.getElementById('eti-toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.toggle('eti-toast-err', !!isErr);
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, isErr ? 7000 : 2600);
  }

  function errMsg(e) {
    if (!e) return 'Có lỗi, thử lại sau.';
    if (e.csrf) return 'Phiên đăng nhập vừa đổi. Tải lại trang (Ctrl+Shift+R) rồi thử lại.';
    const m = e.body && e.body.message;
    if (m && typeof m === 'object' && m.message) return String(m.message);
    if (e.status === 413) return 'Tệp quá lớn so với giới hạn tải lên. Nén PDF hoặc bớt biểu mẫu.';
    if (e.status === 403) return 'Bạn không có quyền làm việc này.';
    if (!e.status) return 'Mất kết nối. Kiểm tra mạng rồi thử lại.';
    return 'Có lỗi, thử lại sau.';
  }

  async function call(method, args) {
    if (!window.ecApi) throw new Error('Trang chưa tải xong, thử lại sau giây lát.');
    let res;
    try {
      res = await window.ecApi.post(API + method, args || {});
    } catch (e) {
      throw new Error(errMsg(e));
    }
    if (res && res.success) return res.data;
    throw new Error((res && res.message) || 'Có lỗi, thử lại sau.');
  }

  function busy(btn, on) {
    if (!btn) return;
    btn.disabled = !!on;
    if (on) btn.setAttribute('aria-busy', 'true'); else btn.removeAttribute('aria-busy');
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // ------------------------------------------------------------------ 1. so do ------
  function initFlow() {
    const card = document.querySelector('[data-eti-flow]');
    if (!card) return;
    const box = document.getElementById('eti-flow');
    const msg = document.getElementById('eti-flow-msg');
    const srcEl = document.getElementById('eti-src');
    let roles = [];
    try { roles = JSON.parse(card.dataset.roles || '[]'); } catch (e) { roles = []; }
    const byCode = {};
    roles.forEach((r) => { byCode[r.ma] = r; });
    let svg = null;
    let vbw = 0;
    let zoom = 1;
    let fit = 1;
    let cur = '';

    // Mermaid 10: id phan tu nut = "flowchart-<id nut>-<so>".
    const nodeId = (g) => {
      const m = /^flowchart-(.+)-\d+$/.exec(g.id || '');
      return m ? m[1] : null;
    };

    function paint() {
      if (!svg) return;
      const keep = cur && byCode[cur] ? byCode[cur].nodes : null;
      svg.querySelectorAll('g.node').forEach((g) => {
        const on = !keep || keep.indexOf(nodeId(g)) >= 0;
        const hl = !!keep && on;
        g.classList.toggle('eti-hl', hl);
        g.classList.toggle('eti-dim', !on);
        // CSS cua mermaid gan theo #id (manh hon moi lop) -> to sang bang style truc tiep.
        g.querySelectorAll('rect, polygon').forEach((sh) => {
          sh.style.fill = hl ? '#eef0fb' : '';
          sh.style.stroke = hl ? '#2C3DA6' : '';
          sh.style.strokeWidth = hl ? '3px' : '';
        });
      });
      svg.querySelectorAll('.edgePaths path, .edgeLabels .edgeLabel').forEach((p) => {
        p.classList.toggle('eti-dim-edge', !!keep);
      });
    }

    function mine() {
      const wrap = document.getElementById('eti-mine');
      const list = document.getElementById('eti-mine-list');
      const r = byCode[cur];
      if (!wrap || !list) return;
      list.textContent = '';
      if (!r) { wrap.hidden = true; return; }
      document.getElementById('eti-mine-t').textContent = 'Việc của ' + r.ten;
      r.work.forEach((w) => {
        const li = el('li');
        li.appendChild(el('span', 'eti-no', w.stt));
        const body = el('span');
        body.appendChild(el('strong', null, w.ten));
        if (w.dien_giai) { body.appendChild(el('br')); body.appendChild(el('span', 'eti-mut', w.dien_giai)); }
        li.appendChild(body);
        list.appendChild(li);
      });
      wrap.hidden = false;
    }

    function size() {
      if (!svg) return;
      svg.style.maxWidth = 'none';
      svg.style.width = Math.round(vbw * zoom) + 'px';
      svg.style.height = 'auto';
    }
    function fitZoom() {
      const w = box.clientWidth - 32;
      // So do doc (TD) hep: khong phong qua 1.15 lan, chu se to qua khung.
      fit = Math.max(0.6, Math.min(1.15, w / vbw));
      zoom = fit;
      size();
    }

    card.addEventListener('click', (e) => {
      const chip = e.target.closest('.eti-chip');
      if (chip) {
        cur = chip.dataset.r || '';
        card.querySelectorAll('.eti-chip').forEach((c) => {
          const on = c === chip;
          c.classList.toggle('is-on', on);
          c.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        mine();
        paint();
        return;
      }
      const z = e.target.closest('[data-z]');
      if (z && svg) {
        const d = Number(z.dataset.z);
        if (d === 0) fitZoom(); else { zoom = Math.max(0.5, Math.min(2.5, zoom + d * 0.2)); size(); }
      }
    });

    async function draw() {
      if (!window.mermaid) {
        msg.textContent = 'Không tải được thư viện vẽ sơ đồ. Xem phần "Diễn giải từng bước" bên dưới.';
        return;
      }
      try {
        window.mermaid.initialize({
          startOnLoad: false, securityLevel: 'strict', theme: 'neutral',
          fontFamily: 'Inter, -apple-system, sans-serif',
          flowchart: { htmlLabels: true, nodeSpacing: 36, rankSpacing: 44, padding: 14 },
        });
        const out = await window.mermaid.render('etiFlow' + Date.now(), srcEl.textContent);
        box.innerHTML = out.svg;
        svg = box.querySelector('svg');
        const vb = (svg.getAttribute('viewBox') || '0 0 600 800').split(/\s+/);
        vbw = Number(vb[2]) || 600;
        fitZoom();
        paint();
      } catch (e) {
        msg.textContent = 'Sơ đồ chưa vẽ được. Xem phần "Diễn giải từng bước" bên dưới.';
      }
    }
    if (document.readyState === 'complete') draw(); else window.addEventListener('load', draw);
    window.addEventListener('resize', () => { if (svg && Math.abs(zoom - fit) < 0.001) fitZoom(); });
  }

  // ------------------------------------------------------------------ 2. bam buoc duyet ------
  function initActions() {
    document.addEventListener('submit', async (e) => {
      const form = e.target.closest('[data-eti-act]');
      if (!form) return;
      e.preventDefault();
      const btn = e.submitter;
      if (!btn || !btn.value) return;
      const note = (form.querySelector('textarea[name=note]') || {}).value || '';
      if (btn.value === 'Trả lại' && note.trim().length < 5) {
        toast('Trả lại cần ghi lý do (ít nhất 5 ký tự).', true);
        const ta = form.querySelector('textarea');
        if (ta) ta.focus();
        return;
      }
      form.querySelectorAll('button').forEach((b) => busy(b, true));
      try {
        const data = await call('action', { code: form.dataset.etiAct, action: btn.value, note: note });
        toast('Đã chuyển sang: ' + (data && data.state ? data.state : 'bước tiếp theo'));
        const u = new URL(location.href);
        u.searchParams.set('ma', form.dataset.etiAct);
        location.href = u.toString();
      } catch (err) {
        form.querySelectorAll('button').forEach((b) => busy(b, false));
        toast(err.message, true);
      }
    });
  }

  // ------------------------------------------------------------------ 3. nhap goi ------
  function readAs(file, how) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(new Error('Không đọc được tệp ' + file.name + '.'));
      if (how === 'text') r.readAsText(file, 'utf-8'); else r.readAsDataURL(file);
    });
  }

  async function blob(file) {
    if (!file) return null;
    return { name: file.name, data: await readAs(file, 'data') };
  }

  function initImport() {
    const dlg = document.getElementById('eti-import');
    if (!dlg) return;
    const form = document.getElementById('eti-import-form');
    const err = document.getElementById('eti-imp-err');
    const info = document.getElementById('eti-goi-info');
    const codeIn = document.getElementById('eti-f-code');
    let goiText = '';

    document.addEventListener('click', (e) => {
      if (e.target.closest('[data-eti-open="eti-import"]')) {
        if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
      }
      if (e.target.closest('[data-eti-close]')) dlg.close();
    });

    document.getElementById('eti-f-goi').addEventListener('change', async (e) => {
      const f = e.target.files[0];
      info.textContent = '';
      goiText = '';
      err.hidden = true;
      if (!f) return;
      try {
        goiText = await readAs(f, 'text');
        const g = JSON.parse(goiText);
        const kind = g.loai_goi === 'sua_doi' ? 'Sửa đổi ' + (g.ma_tai_lieu || '') : 'Tài liệu mới';
        info.textContent = kind + ' · ' + (g.loai || '') + ' · ' + (g.ten || '') + ' · ' + (g.phong_ban || '');
        if (!codeIn.value) codeIn.value = (g.loai_goi === 'sua_doi' ? g.ma_tai_lieu : g.ma_de_xuat) || '';
      } catch (ex) {
        info.textContent = 'goi.json không đọc được: kiểm tra lại tệp.';
      }
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      err.hidden = true;
      const go = document.getElementById('eti-imp-go');
      const pdf = document.getElementById('eti-f-pdf').files[0];
      const docx = document.getElementById('eti-f-docx').files[0];
      const forms = Array.from(document.getElementById('eti-f-forms').files);
      if (!goiText) { err.textContent = 'Chọn tệp goi.json trước.'; err.hidden = false; return; }
      const all = [pdf, docx].concat(forms).filter(Boolean);
      const big = all.find((f) => f.size > FILE_MAX);
      if (big) { err.textContent = 'Tệp ' + big.name + ' lớn hơn 20 MB.'; err.hidden = false; return; }
      if (all.reduce((s, f) => s + f.size, 0) > TOTAL_MAX) {
        err.textContent = 'Tổng dung lượng tệp vượt 24 MB.'; err.hidden = false; return;
      }
      busy(go, true);
      go.textContent = 'Đang nhập…';
      try {
        const payload = {
          goi: goiText, code: codeIn.value.trim().toUpperCase(),
          pdf: await blob(pdf), docx: await blob(docx),
          forms: await Promise.all(forms.map(blob)),
        };
        const data = await call('import_package', { data: JSON.stringify(payload) });
        toast((data.created ? 'Đã tạo bản nháp ' : 'Đã cập nhật bản nháp ') + data.code);
        location.href = data.url;
      } catch (ex) {
        err.textContent = ex.message;
        err.hidden = false;
        busy(go, false);
        go.textContent = 'Nhập gói';
      }
    });
  }

  function init() {
    initFlow();
    initActions();
    initImport();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
