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
  // Huong so do (PO 05/10): ngang cho quy trinh ngan tren may tinh, doc cho quy trinh dai va tren
  // dien thoai; nguoi xem doi duoc (nho trong trinh duyet). Quy trinh nhieu phan (subgraph trong
  // nguon) ve thanh nhieu so do xep chong, moi phan mot tieu de - mermaid ve "direction" trong
  // subgraph khong on dinh, tach ra thi phan nao cung vua khung.
  const NODE_LINE = /^\s*S\w+\s*[\[{(]/;
  const DIR_KEY = 'eti-flow-dir';

  function splitParts(src) {
    const parts = [];
    let cur = null;
    src.split('\n').forEach((raw) => {
      const l = raw.trim();
      if (!l || /^flowchart\b/.test(l)) return;
      const sg = /^subgraph\s+\w+\s*(?:\["(.*)"\])?/.exec(l);
      if (sg) { cur = { title: sg[1] || '', lines: [] }; parts.push(cur); return; }
      if (l === 'end') { cur = null; return; }
      if (!cur) { cur = { title: '', lines: [] }; parts.push(cur); }
      cur.lines.push(l);
    });
    return parts.filter((p) => p.lines.length);
  }

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
    const parts = splitParts(srcEl.textContent);
    const longest = parts.reduce((m, p) => Math.max(m, p.lines.filter((l) => NODE_LINE.test(l)).length), 0);
    let svgs = [];          // [{svg, vbw}]
    let zoom = 1;           // he so tren muc "vua khung" cua tung so do
    let cur = '';
    let dir = '';
    try { dir = localStorage.getItem(DIR_KEY) || ''; } catch (e) { dir = ''; }
    if (dir !== 'TD' && dir !== 'LR') dir = (window.innerWidth >= 1024 && longest <= 7) ? 'LR' : 'TD';

    // Mermaid 10: id phan tu nut = "flowchart-<id nut>-<so>".
    const nodeId = (g) => {
      const m = /^flowchart-(.+)-\d+$/.exec(g.id || '');
      return m ? m[1] : null;
    };

    function paint() {
      const keep = cur && byCode[cur] ? byCode[cur].nodes : null;
      box.querySelectorAll('g.node').forEach((g) => {
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
      box.querySelectorAll('.edgePaths path, .edgeLabels .edgeLabel').forEach((p) => {
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
      const w = Math.max(240, box.clientWidth - 32);
      svgs.forEach((x) => {
        // ngang: khong nho hon 0.8 (chu con doc duoc, thieu cho thi cuon ngang); doc: khong phong qua 1
        const fit = dir === 'LR' ? Math.max(0.8, Math.min(1.1, w / x.vbw)) : Math.max(0.6, Math.min(1, w / x.vbw));
        x.svg.style.maxWidth = 'none';
        x.svg.style.width = Math.round(x.vbw * fit * zoom) + 'px';
        x.svg.style.height = 'auto';
      });
    }

    function markDir() {
      card.querySelectorAll('[data-dir]').forEach((b) => b.setAttribute('aria-pressed', b.dataset.dir === dir ? 'true' : 'false'));
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
      if (z && svgs.length) {
        const d = Number(z.dataset.z);
        zoom = d === 0 ? 1 : Math.max(0.5, Math.min(2.5, zoom + d * 0.2));
        size();
        return;
      }
      const b = e.target.closest('[data-dir]');
      if (b && b.dataset.dir !== dir) {
        dir = b.dataset.dir;
        try { localStorage.setItem(DIR_KEY, dir); } catch (x) { /* che do rieng tu: chi doi lan nay */ }
        markDir();
        draw();
      }
    });

    async function draw() {
      if (!window.mermaid) {
        msg.textContent = 'Không tải được thư viện vẽ sơ đồ. Xem phần "Diễn giải từng bước" bên dưới.';
        return;
      }
      const wide = dir === 'LR';
      try {
        window.mermaid.initialize({
          startOnLoad: false, securityLevel: 'strict', theme: 'neutral',
          fontFamily: 'Inter, -apple-system, sans-serif',
          flowchart: { htmlLabels: true, nodeSpacing: wide ? 28 : 24, rankSpacing: wide ? 36 : 30, padding: 12 },
        });
        const out = [];
        for (let i = 0; i < parts.length; i += 1) {
          const src = 'flowchart ' + dir + '\n' + parts[i].lines.join('\n');
          out.push(await window.mermaid.render('etiFlow' + Date.now() + '_' + i, src));
        }
        box.textContent = '';
        svgs = [];
        out.forEach((r, i) => {
          const wrap = el('div', 'eti-part');
          if (parts.length > 1) wrap.appendChild(el('h3', 'eti-part-t', parts[i].title || ('Phần ' + (i + 1))));
          const holder = el('div', 'eti-part-svg');
          holder.innerHTML = r.svg;
          wrap.appendChild(holder);
          box.appendChild(wrap);
          const svg = holder.querySelector('svg');
          const vb = (svg.getAttribute('viewBox') || '0 0 600 800').split(/\s+/);
          svgs.push({ svg: svg, vbw: Number(vb[2]) || 600 });
        });
        box.classList.toggle('is-wide', wide);
        size();
        paint();
      } catch (e) {
        msg.textContent = 'Sơ đồ chưa vẽ được. Xem phần "Diễn giải từng bước" bên dưới.';
        if (!box.contains(msg)) { box.textContent = ''; box.appendChild(msg); }
      }
    }
    markDir();
    if (document.readyState === 'complete') draw(); else window.addEventListener('load', draw);
    window.addEventListener('resize', () => { if (svgs.length) size(); });
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
      if (btn.name === 'review') {
        form.querySelectorAll('button').forEach((b) => busy(b, true));
        try {
          const r = await call('confirm_review', { code: form.dataset.etiAct, note: note });
          toast('Đã ghi rà soát. Hạn rà soát kế tiếp: ' + r.next_review);
          const u = new URL(location.href);
          u.searchParams.set('ma', form.dataset.etiAct);
          location.href = u.toString();
        } catch (err) {
          form.querySelectorAll('button').forEach((b) => busy(b, false));
          toast(err.message, true);
        }
        return;
      }
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
        if (data && data.next) { location.href = data.next; return; }
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


  // ------------------------------------------------------------------ 4. trang soan ------
  function initEditor() {
    const form = document.getElementById('eti-ed');
    const bootEl = document.getElementById('eti-ed-boot');
    if (!form || !bootEl) return;
    let boot = {};
    try { boot = JSON.parse(bootEl.textContent || '{}'); } catch (e) { boot = {}; }
    const editable = !form.querySelector('fieldset[disabled]');
    const box = document.getElementById('eti-steps-ed');
    const formsUl = document.getElementById('eti-forms');
    let forms = (boot.forms || []).slice();
    let dirty = false;
    let n = 0;

    function field(lbl, name, val, opts) {
      const o = opts || {};
      const l = el('label', o.cls || '');
      l.appendChild(document.createTextNode(lbl));
      const i = document.createElement(o.area ? 'textarea' : 'input');
      if (!o.area) i.type = 'text'; else i.rows = 2;
      i.name = name;
      i.value = val || '';
      i.maxLength = o.max || 120;
      if (o.ph) i.placeholder = o.ph;
      l.appendChild(i);
      return l;
    }

    function renumber() {
      const rows = Array.from(box.children);
      rows.forEach((r, i) => {
        const up = r.querySelector('[data-step-up]');
        const dn = r.querySelector('[data-step-down]');
        if (up) up.disabled = !editable || i === 0;
        if (dn) dn.disabled = !editable || i === rows.length - 1;
        const s = r.querySelector('input[name=stt]');
        if (s && !s.dataset.touched) s.value = String(i + 1);
      });
    }

    function addRow(r, after) {
      n += 1;
      const d = el('div', 'eti-step-ed');
      d.setAttribute('role', 'group');
      d.setAttribute('aria-label', 'Bước');
      const stt = field('STT', 'stt', r.stt, { max: 8 });
      stt.querySelector('input').addEventListener('input', (e) => { e.target.dataset.touched = '1'; });
      if (r.stt && !/^\d+$/.test(r.stt)) stt.querySelector('input').dataset.touched = '1';
      d.appendChild(stt);
      d.appendChild(field('Tên bước', 'ten', r.ten, { ph: 'Ví dụ: Lập đề nghị thanh toán' }));
      d.appendChild(field('Chịu trách nhiệm', 'A', r.A, { max: 80, ph: 'Một vai trò' }));
      d.appendChild(field('Người thực hiện', 'R', r.R, { max: 300, ph: 'Cách nhau dấu phẩy' }));
      d.appendChild(field('Diễn giải', 'dien_giai', r.dien_giai, { area: true, max: 1500, cls: 'eti-se-wide' }));
      d.appendChild(field('Thuộc phần', 'phan', r.phan, { cls: 'eti-se-phan', ph: 'Để trống nếu chỉ có một quy trình' }));
      const t = el('div', 'eti-se-tools');
      [['data-step-up', '↑', 'Chuyển lên'], ['data-step-down', '↓', 'Chuyển xuống'], ['data-step-del', '×', 'Xoá bước']]
        .forEach(([a, txt, title]) => {
          const b = el('button', 'eti-icon-btn', txt);
          b.type = 'button';
          b.setAttribute(a, '');
          b.title = title;
          b.setAttribute('aria-label', title);
          b.disabled = !editable;
          t.appendChild(b);
        });
      d.appendChild(t);
      if (after) after.after(d); else box.appendChild(d);
      return d;
    }

    function drawForms() {
      formsUl.textContent = '';
      if (!forms.length) { formsUl.appendChild(el('li', 'eti-mut', 'Chưa có biểu mẫu.')); return; }
      forms.forEach((f, i) => {
        const li = el('li', 'eti-form-row');
        const a = el('a', 'eti-link', (f.ma ? f.ma + ' · ' : '') + (f.ten || f.url));
        a.href = f.url;
        a.target = '_blank';
        a.rel = 'noopener';
        li.appendChild(a);
        if (editable) {
          const b = el('button', 'eti-icon-btn', '×');
          b.type = 'button';
          b.title = 'Bỏ biểu mẫu này';
          b.setAttribute('aria-label', 'Bỏ biểu mẫu ' + (f.ten || ''));
          b.addEventListener('click', () => { forms.splice(i, 1); dirty = true; drawForms(); });
          li.appendChild(b);
        }
        formsUl.appendChild(li);
      });
    }

    (boot.rows && boot.rows.length ? boot.rows : [{}]).forEach((r) => addRow(r));
    renumber();
    drawForms();

    form.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b || !editable) return;
      const row = b.closest('.eti-step-ed');
      if (b.hasAttribute('data-step-add')) {
        const r = addRow({});
        renumber();
        r.querySelector('input[name=ten]').focus();
      } else if (row && b.hasAttribute('data-step-del')) {
        const filled = Array.from(row.querySelectorAll('input,textarea')).some((i) => i.name !== 'stt' && i.value.trim());
        if (filled && !window.confirm('Xoá bước này?')) return;
        row.remove();
        if (!box.children.length) addRow({});
        renumber();
      } else if (row && b.hasAttribute('data-step-up') && row.previousElementSibling) {
        row.previousElementSibling.before(row);
        renumber();
      } else if (row && b.hasAttribute('data-step-down') && row.nextElementSibling) {
        row.nextElementSibling.after(row);
        renumber();
      } else return;
      dirty = true;
    });
    form.addEventListener('input', () => { dirty = true; });

    const wide = document.getElementById('f-wide');
    const notify = document.getElementById('f-notify');
    function sync() {
      const w = wide && wide.checked;
      document.getElementById('f-scope').hidden = !!w;
      document.getElementById('f-notify-w').hidden = !w;
      document.getElementById('f-nsum-w').hidden = !(w && notify && notify.checked);
    }
    if (wide) wide.addEventListener('change', sync);
    if (notify) notify.addEventListener('change', sync);
    window.addEventListener('beforeunload', (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!editable) return;
      const err = document.getElementById('eti-ed-err');
      const go = document.getElementById('eti-ed-save');
      err.hidden = true;
      const v = (name) => { const i = form.elements[name]; return i ? i.value.trim() : ''; };
      const pdf = document.getElementById('f-pdf').files[0];
      const docx = document.getElementById('f-docx').files[0];
      const fnew = Array.from(document.getElementById('f-forms').files);
      const fail = (m, focus) => { err.textContent = m; err.hidden = false; if (focus) focus.focus(); };
      if (boot.mode === 'new' && !v('code')) return fail('Nhập mã tài liệu.', form.elements.code);
      if (!v('quality_procedure_name')) return fail('Nhập tên tài liệu.', form.elements.quality_procedure_name);
      if (!v('ec_department')) return fail('Chọn phòng ban chủ trì.', form.elements.ec_department);
      const all = [pdf, docx].concat(fnew).filter(Boolean);
      const big = all.find((f) => f.size > FILE_MAX);
      if (big) return fail('Tệp ' + big.name + ' lớn hơn 20 MB.');
      if (all.reduce((s, f) => s + f.size, 0) > TOTAL_MAX) return fail('Tổng dung lượng tệp vượt 24 MB.');
      const rows = Array.from(box.children).map((r) => {
        const o = {};
        r.querySelectorAll('input,textarea').forEach((i) => { o[i.name] = i.value.trim(); });
        return o;
      }).filter((o) => o.ten);
      const kind = form.querySelector('input[name=ec_change_kind]:checked');
      const payload = {
        code: boot.mode === 'new' ? v('code').toUpperCase() : boot.code,
        existing: boot.mode === 'edit' ? 1 : 0,
        quality_procedure_name: v('quality_procedure_name'),
        ec_doc_type: v('ec_doc_type'),
        ec_department: v('ec_department'),
        ec_review_months: parseInt(v('ec_review_months'), 10) || 12,
        ec_company_wide: wide && wide.checked ? 1 : 0,
        ec_notify_home: notify && notify.checked ? 1 : 0,
        ec_notify_summary: v('ec_notify_summary'),
        scope: Array.from(form.querySelectorAll('input[name=scope]:checked')).map((i) => i.value),
        tom_tat: { muc_dich: v('tt_muc_dich'), dung_khi: v('tt_dung_khi'), chuan_bi: v('tt_chuan_bi'), ket_qua: v('tt_ket_qua') },
        rows: rows,
        forms_keep: forms,
      };
      if (form.elements.ec_change_summary) {
        payload.ec_change_kind = kind ? kind.value : '';
        payload.ec_change_summary = v('ec_change_summary');
        payload.ec_changed_sections = v('ec_changed_sections');
        payload.ec_draft_version = v('ec_draft_version');
      }
      busy(go, true);
      const label = go.textContent;
      go.textContent = 'Đang lưu…';
      try {
        payload.pdf = await blob(pdf);
        payload.docx = await blob(docx);
        payload.forms_new = await Promise.all(fnew.map(blob));
        const data = await call('save_draft', { data: JSON.stringify(payload) });
        dirty = false;
        toast(data.created ? 'Đã tạo bản nháp ' + data.code : 'Đã lưu bản nháp');
        location.href = data.url;
      } catch (ex) {
        fail(ex.message);
        busy(go, false);
        go.textContent = label;
      }
    });
  }

  function init() {
    initFlow();
    initActions();
    initImport();
    initEditor();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
