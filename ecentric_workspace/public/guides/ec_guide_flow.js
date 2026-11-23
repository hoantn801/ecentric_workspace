/* Huong dan su dung - ve so do luong (mermaid) ngay tai trang.
 *
 * 23/11/2026 (Agent F). Nap SAU vendor/mermaid/mermaid.min.js (ca hai `defer`, cung thu tu).
 * Markup ban dau da du nghia khi KHONG co JS: khung "Đang tải sơ đồ…" + so do dang chu
 * (<details>) + bang cac buoc ngay ben duoi. JS chi lam MOT viec: thay khung bang hinh ve.
 *   - ve duoc     -> data-state="ok", khung chua <svg>
 *   - khong ve duoc (thieu thu vien, cu phap sai, trinh duyet cu) -> data-state="error",
 *     khung noi ro + mo san so do dang chu. Khong bao gio de khung trong.
 * Khong goi CDN, khong goi API. securityLevel strict: nhan so do khong chay duoc script.
 */
(function () {
  'use strict';

  const SEL = '.ecg-flow[data-state="pending"]';
  const MSG_FAIL = 'Không vẽ được sơ đồ trên trình duyệt này. Xem sơ đồ dạng chữ ngay dưới, '
    + 'hoặc bảng các bước.';
  // So do rong hon khung nhieu lan thi khong thu nho cho vua (chu se qua be): giu ty le
  // doc duoc va cho cuon ngang trong khung.
  const MAX_SHRINK = 1.6;

  function parts(fig) {
    return {
      canvas: fig.querySelector('.ecg-flow-canvas'),
      src: fig.querySelector('.ecg-flow-src'),
      code: fig.querySelector('.ecg-flow-code'),
    };
  }

  function fail(fig) {
    const p = parts(fig);
    fig.setAttribute('data-state', 'error');
    if (p.canvas) p.canvas.textContent = MSG_FAIL;
    if (p.code) p.code.open = true;
  }

  function fit(canvas) {
    const svg = canvas.querySelector('svg');
    if (!svg) return;
    // viewBox="minX minY width height" - doc chuoi thuoc tinh (an toan voi moi trinh duyet).
    const vb = String(svg.getAttribute('viewBox') || '').trim().split(/[\s,]+/);
    const natural = vb.length === 4 ? parseFloat(vb[2]) : 0;
    const room = canvas.clientWidth;
    if (natural && room && natural > room * MAX_SHRINK) {
      svg.style.maxWidth = 'none';
      svg.style.width = Math.round(natural / MAX_SHRINK) + 'px';
    }
  }

  function setup(m) {
    m.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'base',
      fontFamily: "'Segoe UI', Inter, system-ui, -apple-system, Roboto, sans-serif",
      themeVariables: {
        primaryColor: '#F3F6FA', primaryBorderColor: '#7E859E', primaryTextColor: '#141A2E',
        lineColor: '#4C5372', fontSize: '14px',
      },
      flowchart: { htmlLabels: true, useMaxWidth: true, curve: 'basis' },
    });
  }

  async function run() {
    const figs = Array.from(document.querySelectorAll(SEL));
    if (!figs.length) return { ok: 0, error: 0 };
    const m = window.mermaid;
    if (!m || typeof m.render !== 'function' || typeof m.initialize !== 'function') {
      figs.forEach(fail);
      return { ok: 0, error: figs.length };
    }
    let ok = 0;
    let error = 0;
    try {
      setup(m);
    } catch (e) {
      figs.forEach(fail);
      return { ok: 0, error: figs.length };
    }
    for (let i = 0; i < figs.length; i += 1) {
      const fig = figs[i];
      const p = parts(fig);
      if (!p.canvas || !p.src) { fail(fig); error += 1; continue; }
      try {
        const out = await m.render('ecgFlow' + i + '_' + Date.now(), p.src.textContent);
        const svg = out && (out.svg || out);
        if (typeof svg !== 'string' || svg.indexOf('<svg') < 0) throw new Error('no svg');
        p.canvas.innerHTML = svg;
        fig.setAttribute('data-state', 'ok');
        fit(p.canvas);
        ok += 1;
      } catch (e) {
        fail(fig);
        error += 1;
      }
    }
    return { ok, error };
  }

  window.ecGuideFlow = { run };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { run(); });
  } else {
    run();
  }
}());
