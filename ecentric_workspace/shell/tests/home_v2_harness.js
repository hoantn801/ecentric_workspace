/* Chay ec_home_v2.js THAT tren HTML trang chu da render (jsdom), in ket qua JSON.
 *   node home_v2_harness.js <rendered.html> <ec_home_v2.js>
 * Goi tu test_home_source.py (can node + jsdom; thieu thi test SKIP, khong xanh gia).
 * Kiem hai thu: (1) du lieu do dung cho, (2) BO CUC KHONG DOI - khong phan tu nao cua dai
 * navy / dong thoi gian / luoi bi tao them, xoa, doi cho, an hay doi lop, ngoai cac nut du
 * lieu duoc phep (hang doi, chip su kien, cau "viec gap"). */
'use strict';
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2], 'utf8');
const src = fs.readFileSync(process.argv[3], 'utf8');
const out = {};

function skeleton(doc) {
  // moi phan tu trong vung bo cuc, TRU cac cay du lieu duoc phep
  const root = doc.querySelector('[data-ec2-home]');
  const allowed = el => el.closest('.ec2-qbody') && !el.classList.contains('ec2-qbody')
    || el.classList.contains('ec2-ev') || el.classList.contains('ec2-hot') || !!el.closest('.ec2-ev')
    || (!!el.closest('.stat-value') && !el.classList.contains('stat-value'));   // so do script khac do vao
  const rows = [];
  root.querySelectorAll('*').forEach(el => {
    if (allowed(el)) { return; }
    if (el.closest('[data-ec2-cal-off]') && !el.hasAttribute('data-ec2-cal-off')) { return; } // widget Lich so huu ben trong
    if (el.closest('script,style,svg') && !['SVG'].includes(el.tagName)) { return; }
    const attrs = [...el.attributes].map(a => a.name + '=' + a.value)
      .filter(a => !/^style=/.test(a) && !/^class=/.test(a) && !/^data-ec2-hydrated=/.test(a) && !/^hidden=/.test(a) && !/^data-ec2-cal-pop=/.test(a) && !/^data-ec2-tl-loading=/.test(a) && !/^stroke-dasharray=/.test(a))
      .join(' ');
    const cls = [...el.classList].filter(c => c !== 'ec2-tlflat' && c !== 'ec2-hasev').join('.');
    rows.push(el.tagName + '.' + cls + '[' + attrs + ']@' + (el.parentElement ? [...el.parentElement.children].indexOf(el) : -1));
  });
  return rows;
}

async function run(opts) {
  const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://team.ecentric.vn/home' });
  const w = dom.window, d = w.document;
  const calls = [];
  if (opts.api !== 'none') {
    w.ecApi = { get: (m, a, o) => { calls.push({ m, a, o }); return opts.api === 'fail' ? Promise.reject(new Error('x')) : Promise.resolve(opts.summary); } };
  }
  w.fetch = (url) => { calls.push({ fetch: String(url) }); return Promise.resolve({ json: () => Promise.resolve({ message: opts.summary }) }); };
  const before = skeleton(d);
  const beforeStyles = [...d.querySelectorAll('[data-ec2-home] *')].filter(el => el.style && el.style.display).length;
  w.eval(src);
  if (opts.twice) { w.eval(src); }
  await new Promise(r => setTimeout(r, 20));
  const res = { calls, owns: w.ecTimelineOwnsEvents === true, hydrated: d.querySelector('[data-ec2-home]').getAttribute('data-ec2-hydrated') };
  res.tlLoading0 = d.querySelector('.ec2-tl').getAttribute('data-ec2-tl-loading');
  res.tlFlat0 = d.querySelector('.ec2-tl').classList.contains('ec2-tlflat');
  // vong tien do: HR do so vao o NGAY CONG
  const att = d.querySelector('[data-ec-att-hours]').parentElement.querySelector('.stat-value');
  res.ringBefore = d.querySelector('.ec2-ring em').textContent;
  att.innerHTML = '12<span class="unit">/22 ngày</span>';
  await new Promise(r => setTimeout(r, 10));
  res.ringEm = d.querySelector('.ec2-ring em').textContent;
  res.ringB = d.querySelector('.ec2-ringtx b').textContent;
  res.ringArc = d.querySelector('.ec2-ringarc').getAttribute('stroke-dasharray');
  const now = new Date(); let wd = 0; const last = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  for (let i = 1; i <= last; i++) { const g = new Date(now.getFullYear(), now.getMonth(), i).getDay(); if (g >= 1 && g <= 5) wd++; }
  res.expectRing = Math.round(Math.min(1, 12 / wd) * 100) + '%';
  // hang doi
  res.qi = d.querySelectorAll('.ec2-qi').length;
  res.qg = [...d.querySelectorAll('.ec2-qg')].map(x => x.textContent);
  res.qBadge = { text: d.querySelector('.ec2-qn').textContent, hidden: d.querySelector('.ec2-qn').hidden };
  res.qEmpty = d.querySelector('.ec2-qempty') ? d.querySelector('.ec2-qempty').textContent : null;
  res.qHtml = d.querySelector('.ec2-qbody').innerHTML;
  res.hot = [...d.querySelectorAll('.ec2-hot')].map(x => x.textContent);
  // dong thoi gian
  w.ecCalEvents = () => opts.events || [];
  d.dispatchEvent(new w.Event('ec-cal-today'));
  res.ev = [...d.querySelectorAll('.ec2-ev')].map(e => ({ t: e.textContent, l: e.style.getPropertyValue('--ec2-l'), left: e.style.left, width: e.style.width, b: e.classList.contains('ec2-ev-b') }));
  res.lanes = d.querySelector('.ec2-tlbody').style.getPropertyValue('--ec2-lanes');
  res.flat = d.querySelector('.ec2-tl').classList.contains('ec2-tlflat');
  res.hasev = d.querySelector('.ec2-tlbody').classList.contains('ec2-hasev');
  // bam mot su kien -> popover; bam ra ngoai -> dong
  const cal = d.querySelector('[data-ec2-cal-off]');
  const ev0 = d.querySelector('.ec2-ev');
  if (ev0) {
    ev0.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    res.popOpen = cal.getAttribute('data-ec2-cal-pop');
    await new Promise(r => setTimeout(r, 5));
    d.body.dispatchEvent(new w.MouseEvent('mousedown', { bubbles: true }));
    res.popAfter = cal.getAttribute('data-ec2-cal-pop');
  }
  // het su kien -> ve lai trang thai phang
  w.ecCalEvents = () => [];
  d.dispatchEvent(new w.Event('ec-cal-today'));
  res.flatAgain = d.querySelector('.ec2-tl').classList.contains('ec2-tlflat');
  res.emptyTxt = d.querySelector('.ec2-tlempty').textContent;
  res.tlLoadingEnd = d.querySelector('.ec2-tl').getAttribute('data-ec2-tl-loading');
  res.evAgain = d.querySelectorAll('.ec2-ev').length;
  // bo cuc
  const after = skeleton(d);
  res.skeletonSame = JSON.stringify(before) === JSON.stringify(after);
  if (!res.skeletonSame) {
    res.skeletonDiff = after.filter(x => before.indexOf(x) < 0).slice(0, 5).concat(['--'], before.filter(x => after.indexOf(x) < 0).slice(0, 5));
  }
  res.displayWrites = [...d.querySelectorAll('[data-ec2-home] *')].filter(el => el.style && el.style.display).length - beforeStyles;
  res.appClasses = d.querySelector('.ecentric-app').className;
  w.close();   // dung setInterval cua trang (dong ho, ghim) - neu khong node chay mai
  return res;
}

const SUMMARY = {
  success: true, total: 7, counts: { overdue: 2, act_now: 1, upcoming: 4 },
  bucket_items: {
    overdue: [{ title: 'Duyệt <b>PO</b> 01', subtitle: 'GBS', source_type: 'approval', action_url: '/approvals/x?a=1&b=2', due_at: '2026-09-28 10:00:00' },
              { title: 'Báo cáo tuần', subtitle: '', source_type: 'weekly_report', action_url: '/weekly-update', due_at: '' }],
    act_now: [{ title: 'Task A', subtitle: 'PM', source_type: 'task', action_url: '/pm#t', due_at: '2026-09-30' }],
    upcoming: [{ title: 'U1', source_type: 'fulfillment' }, { title: 'U2' }, { title: 'U3' }, { title: 'U4' }]
  }
};
const EVENTS = [
  { key: 'k1', subject: 'Họp giao ban', start: '2026-09-29 09:00:00', end: '2026-09-29 10:00:00', kind: 'm' },
  { key: 'k2', subject: 'Review <x>', start: '2026-09-29T09:30:00', end: '2026-09-29T11:00:00', kind: 'm' },
  { key: 'k3', subject: 'Viết spec', start: '2026-09-29 14:00:00', end: '2026-09-29 15:30:00', kind: 'b' },
  { key: 'k4', subject: 'Sớm quá', start: '2026-09-29 06:00:00', end: '2026-09-29 07:00:00', kind: 'm' }
];

(async () => {
  out.main = await run({ summary: SUMMARY, events: EVENTS });
  out.twice = await run({ summary: SUMMARY, events: EVENTS, twice: true });
  out.fail = await run({ api: 'fail', summary: SUMMARY });
  out.noApi = await run({ api: 'none', summary: { success: true, total: 0, counts: {}, bucket_items: {} } });
  process.stdout.write(JSON.stringify(out), () => process.exit(0));
})().catch(e => { process.stdout.write(JSON.stringify({ crash: String(e && e.stack || e) })); process.exit(3); });
