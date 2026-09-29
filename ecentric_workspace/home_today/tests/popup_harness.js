/* Chay ec_home_popup.js THAT tren trang chu da render (jsdom), in ket qua JSON.
 *   node popup_harness.js <trang_co_noi_dung.html> <trang_khong_noi_dung.html> <ec_home_popup.js> <payload.json>
 * Goi tu test_popup_js.py (can node + jsdom; thieu thi test SKIP, khong xanh gia). */
'use strict';
const fs = require('fs');
const { JSDOM } = require('jsdom');

const [htmlOn, htmlOff, src, payloadRaw] = process.argv.slice(2).map((f, i) => fs.readFileSync(f, 'utf8'));
const out = {};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function skeleton(doc) {
  const root = doc.querySelector('[data-ec2-home]');
  return [...root.querySelectorAll('*')].map((el) => el.tagName + '.' + el.className + '@' + [...el.parentElement.children].indexOf(el)).join('|');
}

async function boot(html, opts) {
  const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'https://team.ecentric.vn/' });
  const w = dom.window;
  const calls = [];
  const warns = [];
  const payload = opts.payload || JSON.parse(payloadRaw);
  if (opts.storage) w.localStorage.setItem('ec_home_today_hide', opts.storage);
  w.console.warn = (...a) => warns.push(a.map(String).join(' '));
  w.ecApi = {
    get: (m) => { calls.push({ get: m }); return opts.fail ? Promise.reject(new Error('boom')) : Promise.resolve(payload); },
    post: (m, d) => {
      calls.push({ post: m, d });
      const per = JSON.parse(JSON.stringify(payload.reactions[d.target]));
      per[d.kind].mine = !per[d.kind].mine; per[d.kind].n += per[d.kind].mine ? 1 : -1;
      return Promise.resolve({ target: d.target, reactions: per });
    },
  };
  const before = skeleton(w.document);
  const bodyKids = w.document.body.children.length;
  w.eval(src);
  await sleep(700);
  return { dom, w, d: w.document, calls, warns, before, bodyKids };
}

const txt = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : null);

(async () => {
  // 1) server noi "khong co noi dung" -> khong goi API, khong popup
  {
    const b = await boot(htmlOff, {});
    out.off = { calls: b.calls.length, pop: !!b.d.getElementById('ech-pop') };
  }
  // 2) co noi dung -> popup noi, dung thu tu o, bo cuc trang khong doi
  {
    const b = await boot(htmlOn, {});
    const pop = b.d.getElementById('ech-pop');
    const m = { calls: b.calls, pop: !!pop };
    m.parentIsBody = pop && pop.parentElement === b.d.body;
    m.bodyKidsAdded = b.d.body.children.length - b.bodyKids;
    m.skeletonSame = skeleton(b.d) === b.before;
    const css = (b.d.getElementById('ech-pop-css') || {}).textContent || '';
    m.z = (css.match(/#ech-pop\{[^}]*?z-index:(\d+)/) || [])[1];
    m.fixed = /#ech-pop\{[^}]*position:fixed;inset:0/.test(css);
    m.tiles = [...pop.querySelectorAll('.th .tt')].map(txt);
    m.sub = [...pop.querySelectorAll('.th .ts')].map(txt);
    m.badges = [...pop.querySelectorAll('.th')].map((t) => txt(t.querySelector('.ct')));
    m.focusInDialog = b.d.activeElement === pop.querySelector('.dlg');
    m.hero = txt(pop.querySelector('.hero h3'));
    // o dau: poster "chi anh" - anh phu kin khung, khong co khung chu hero
    m.poster = { img: pop.querySelector('.poster img') && pop.querySelector('.poster img').getAttribute('src'),
      bar: txt(pop.querySelector('.pbar')), open: pop.querySelector('.poster a') && pop.querySelector('.poster a').getAttribute('target'),
      heroless: !pop.querySelector('.stage .hero'),
      thumb: pop.querySelector('.th[data-i="0"] img') && pop.querySelector('.th[data-i="0"] img').getAttribute('src') };
    pop.querySelector('[data-i="1"]').click();
    m.textHero = txt(pop.querySelector('.hero h3'));
    m.date = txt(pop.querySelector('.dh p'));
    m.role = pop.querySelector('.dlg').getAttribute('role') + '/' + pop.querySelector('.dlg').getAttribute('aria-modal');
    // chi tiet tin: mo rong tai cho
    pop.querySelector('[data-more]').click();
    m.expanded = txt(pop.querySelector('.nw .body'));
    m.links = [...pop.querySelectorAll('.nw a')].map((a) => [a.getAttribute('href'), txt(a), a.getAttribute('target')]);
    // sang o Sinh nhat, tha tim
    pop.querySelector('[data-i="2"]').click();
    m.bdHero = txt(pop.querySelector('.hero h3'));
    m.soon = [...pop.querySelectorAll('.sl')].map(txt);
    const heart = pop.querySelector('[data-rx="bd:E1:2026|heart"]');
    m.heartBefore = [heart.getAttribute('aria-pressed'), txt(heart.querySelector('.c'))];
    heart.click();
    await sleep(30);
    const heart2 = pop.querySelector('[data-rx="bd:E1:2026|heart"]');
    m.heartAfter = [heart2.getAttribute('aria-pressed'), txt(heart2.querySelector('.c')), txt(heart2.querySelector('.tip'))];
    m.post = b.calls.filter((c) => c.post);
    // phim mui ten tren cot o
    pop.querySelector('[data-i="2"]').focus();
    pop.querySelector('[data-i="2"]').dispatchEvent(new b.w.KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    m.afterArrow = txt(pop.querySelector('.th[aria-selected="true"] .tt'));
    // tich "khong hien lai hom nay" roi Esc
    const cb = pop.querySelector('[data-hide]');
    cb.checked = true; cb.dispatchEvent(new b.w.Event('change', { bubbles: true }));
    m.stored = JSON.parse(b.w.localStorage.getItem('ec_home_today_hide'));
    b.d.dispatchEvent(new b.w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    m.closedByEsc = !b.d.getElementById('ech-pop');
    m.skeletonSameAtEnd = skeleton(b.d) === b.before;
    out.main = m;
  }
  // 3) tu chuyen o khi thanh tien do chay het (khong re chuot, khong bam)
  {
    const b = await boot(htmlOn, {});
    const pop = b.d.getElementById('ech-pop');
    const bar = pop.querySelector('.th[aria-selected="true"] .prog i');
    bar.dispatchEvent(new b.w.Event('animationend'));
    out.auto = { now: txt(pop.querySelector('.th[aria-selected="true"] .tt')) };
    pop.querySelector('.dlg').dispatchEvent(new b.w.Event('mouseenter'));
    pop.querySelector('.th[aria-selected="true"] .prog i').dispatchEvent(new b.w.Event('animationend'));
    out.auto.pausedStays = txt(pop.querySelector('.th[aria-selected="true"] .tt'));
    // Esc khi dang go trong eC Mate (ngoai popup) -> KHONG dong popup
    const mate = b.d.createElement('textarea'); mate.id = 'ec-khay-fake'; b.d.body.appendChild(mate);
    mate.focus();
    mate.dispatchEvent(new b.w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    out.auto.escInMateKeepsOpen = !!b.d.getElementById('ech-pop');
    pop.dispatchEvent(new b.w.MouseEvent('click', { bubbles: true }));
    out.auto.closedByBackdrop = !b.d.getElementById('ech-pop');
  }
  // 3b) nguoi dung ban phim da vao popup -> khong tu chuyen o nua (khong mat focus)
  {
    const b = await boot(htmlOn, {});
    const pop = b.d.getElementById('ech-pop');
    pop.querySelector('[data-hide]').focus();
    pop.querySelector('.th[aria-selected="true"] .prog i').dispatchEvent(new b.w.Event('animationend'));
    out.focusPause = { stays: txt(pop.querySelector('.th[aria-selected="true"] .tt')), focusKept: b.d.activeElement === pop.querySelector('[data-hide]') };
  }
  // 4) da tich hom nay -> khong hien; co muc moi -> hien lai; ngay khac -> hien
  {
    const p = JSON.parse(payloadRaw);
    const all = JSON.stringify({ d: p.date, k: p.keys });
    out.hidden = { same: !!(await boot(htmlOn, { storage: all })).d.getElementById('ech-pop') };
    const p2 = JSON.parse(payloadRaw); p2.keys = p2.keys.concat(['new:EC-NSP-0099']);
    out.hidden.newItem = !!(await boot(htmlOn, { storage: all, payload: p2 })).d.getElementById('ech-pop');
    out.hidden.otherDay = !!(await boot(htmlOn, { storage: JSON.stringify({ d: '2026-09-28', k: p.keys }) })).d.getElementById('ech-pop');
    out.hidden.junk = !!(await boot(htmlOn, { storage: '{rac' })).d.getElementById('ech-pop');
  }
  // 5) du lieu doc hai duoc escape; o rong bi an
  {
    const p = JSON.parse(payloadRaw);
    p.news = []; p.onboard = []; p.anniversaries = []; p.holidays = [];
    p.birthdays.today[0].name = '<img src=x onerror="window.__pwn=1">';
    p.birthdays.today[0].role = '<b>x</b>';
    const b = await boot(htmlOn, { payload: p });
    const pop = b.d.getElementById('ech-pop');
    out.xss = { pwn: !!b.w.__pwn, imgs: pop.querySelectorAll('img').length, tiles: [...pop.querySelectorAll('.th .tt')].map(txt),
      escaped: pop.innerHTML.includes('&lt;img src=x') };
  }
  // 6) API hong -> im lang (console), khong popup
  {
    const b = await boot(htmlOn, { fail: true });
    out.fail = { pop: !!b.d.getElementById('ech-pop'), warns: b.warns.length };
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
