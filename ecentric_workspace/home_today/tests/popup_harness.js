/* Chay ec_home_popup.js THAT tren trang chu da render (jsdom), in ket qua JSON.
 *   node popup_harness.js <trang_co_noi_dung.html> <trang_khong_noi_dung.html> <ec_home_popup.js> <payload.json>
 * Goi tu test_popup_js.py (can node + jsdom; thieu thi test SKIP, khong xanh gia). */
'use strict';
const fs = require('fs');
const { JSDOM } = require('jsdom');

const [htmlOn, htmlOff, src, payloadRaw, drawSrc] = process.argv.slice(2).map((f, i) => fs.readFileSync(f, 'utf8'));
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
  if (opts.draw) { w.HTMLCanvasElement.prototype.getContext = () => null; w.eval(drawSrc); }
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
    // chi hien o cam xuc DA co nguoi tha; moi the co 1 nut mat cuoi + bang chon 4 icon
    const chips = (k) => [...pop.querySelectorAll('.pc')].map((c) => [...c.querySelectorAll('.rx .rb')].map((b) => b.dataset.rx.split('|')[1] + ':' + txt(b.querySelector('.c'))));
    m.chipsBefore = chips();
    m.pickers = [...pop.querySelectorAll('.pc .rxadd')].map((w) => w.querySelectorAll('.rxpick button').length);
    const heart = pop.querySelector('.rx [data-rx="bd:E1:2026|heart"]');
    m.heartBefore = [heart.getAttribute('aria-pressed'), txt(heart.querySelector('.c'))];
    heart.click();
    await sleep(30);
    const heart2 = pop.querySelector('.rx [data-rx="bd:E1:2026|heart"]');
    m.heartAfter = [heart2.getAttribute('aria-pressed'), txt(heart2.querySelector('.c')), txt(heart2.querySelector('.tip'))];
    // cham nut mat cuoi (dien thoai) -> mo bang chon; chon hoa cho Khoa (chua ai tha) -> o moi hien
    pop.querySelector('[data-rxopen="bd:E2:2026"]').click();
    m.pickOpen = pop.querySelector('[data-rxopen="bd:E2:2026"]').parentElement.classList.contains('open');
    pop.querySelector('.rxpick [data-rx="bd:E2:2026|flower"]').click();
    await sleep(30);
    m.afterPick = chips()[1];
    m.pickClosed = !pop.querySelector('.rxadd.open');
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
  // 4b) da tich an roi bam nut mo lai -> o tich VAN tich; bo tich -> xoa co an
  {
    const p = JSON.parse(payloadRaw);
    const b = await boot(htmlOn, { storage: JSON.stringify({ d: p.date, k: p.keys }) });
    await b.w.EcHomePopup.load(true);
    const cb = b.d.querySelector('#ech-pop [data-hide]');
    out.reopen = { checked: !!(cb && cb.checked) };
    cb.checked = false; cb.dispatchEvent(new b.w.Event('change', { bubbles: true }));
    out.reopen.clearedAfterUntick = b.w.localStorage.getItem('ec_home_today_hide') === null;
    const f = await boot(htmlOn, {});
    out.reopen.freshUnchecked = !f.d.querySelector('#ech-pop [data-hide]').checked;
  }
  // 5) du lieu doc hai duoc escape; o rong bi an
  {
    const p = JSON.parse(payloadRaw);
    p.news = []; p.onboard = []; p.anniversaries = []; p.holidays = [];
    p.birthdays.today[0].name = '<img src=x onerror="window.__pwn=1">';
    p.birthdays.today[0].role = '<b>x</b>';
    p.events[0].title = '<img src=x onerror="window.__pwn=2">';
    p.events[0].club = '<img src=x onerror="window.__pwn=3">';
    const b = await boot(htmlOn, { payload: p });
    const pop = b.d.getElementById('ech-pop');
    out.xss = { pwn: !!b.w.__pwn, imgs: pop.querySelectorAll('img').length, tiles: [...pop.querySelectorAll('.th .tt')].map(txt),
      escaped: pop.innerHTML.includes('&lt;img src=x') };
  }
  // 5b) poster co duong dan -> bam anh di toi duong dan (cung tab); khong co -> mo anh goc (tab moi)
  {
    const p = JSON.parse(payloadRaw);
    p.news[0].url = '/huong-dan/chot-cong-thang'; p.news[0].link_label = 'Xem hướng dẫn →';
    const b = await boot(htmlOn, { payload: p });
    const a = b.d.querySelector('#ech-pop .poster a.pimg');
    out.posterLink = { href: a.getAttribute('href'), target: a.getAttribute('target'), btn: txt(b.d.querySelector('#ech-pop .pbar a')) };
  }
  // 7) O "Quay so may man" (module Khao sat): dung dau, dem nguoc, luot quay tiep theo, ket qua
  {
    const p = JSON.parse(payloadRaw);
    const day = p.date;
    const draw = { name: 'KS-1', title: 'Year End Party', mode: 'lucky_number', state: 'countdown', draw_at: day + ' 10:00:00',
      range: [1, 100], holders: 47, my_number: '027', joined: true, url: '/khao-sat/lam?s=KS-1', racers: [], results: [], racer_total: 0,
      prizes: [{ rank: 1, label: 'Tai nghe', quantity: 1 }, { rank: 2, label: 'Trà sữa', quantity: 1 }] };
    p.draws = { server_now: day + ' 09:57:00', soon: true, timers: [], draws: [draw], upcoming: [
      { name: 'KS-2', title: 'Pantry tháng 10', mode: 'race', draw_at: '2026-10-09 15:00:00', days_left: 2, me: 'joined', url: '/khao-sat/lam?s=KS-2',
        prizes: [{ rank: 1, label: 'Voucher <b>500K</b>', quantity: 1 }, { rank: 2, label: 'Trà sữa', quantity: 3 }], note: 'Nhận quà ở lễ tân' },
      { name: 'KS-3', title: 'Đào tạo Q3', mode: 'lucky_number', draw_at: '2026-10-15 16:30:00', days_left: 8, me: 'not_submitted', url: '/khao-sat/lam?s=KS-3' }] };
    const oldKeys = p.keys.slice();
    p.keys = oldKeys.concat(['draw:KS-1']);
    const b = await boot(htmlOn, { payload: p, draw: true, storage: JSON.stringify({ d: p.date, k: oldKeys }) });
    const pop = b.d.getElementById('ech-pop');
    const o = { pop: !!pop };
    o.firstTile = txt(pop.querySelector('.th[data-i="0"] .tt'));
    o.badge = txt(pop.querySelector('.th[data-i="0"] .ct'));
    o.chip = txt(pop.querySelector('.ecd-chip'));
    o.mine = txt(pop.querySelector('.ecd-mine b'));
    o.clock = txt(pop.querySelector('[data-ecd-clock]'));
    o.upcoming = [...pop.querySelectorAll('.upn-i')].map((r) => [txt(r.querySelector('.upn-b b')), txt(r.querySelector('.upn-r span')), txt(r.querySelector('.upn-left'))]);
    o.cta = [...pop.querySelectorAll('.upn-r a')].map((a) => [txt(a), a.getAttribute('href')]);
    // hop qua dau dong: so luong tong + danh sach qua (ten da escape); cham -> bat / tat
    const g = pop.querySelectorAll('.upn-i .ugift');
    o.gift = { n: g.length, cnt: txt(g[0].querySelector('.cnt')), noCnt: !g[1].querySelector('.cnt'),
      items: [...g[0].querySelectorAll('.ugpop li')].map(txt), note: txt(g[0].querySelector('.ugpop .w')),
      raw: !!g[0].querySelector('.ugpop li b b') };
    g[0].querySelector('[data-ugift]').click();
    o.gift.on1 = g[0].classList.contains('on');
    g[1].querySelector('[data-ugift]').click();
    o.gift.swap = [g[0].classList.contains('on'), g[1].classList.contains('on')];
    await sleep(7500);                                    // khong tu chuyen o khi dang o quay so
    o.stillDraw = txt(pop.querySelector('.th[aria-selected="true"] .tt'));
    // ket qua da chot (mo trang sau gio quay): so tinh + nguoi trung + so trong "qua de lai"
    const done = Object.assign({}, draw, { state: 'done', results: [
      { rank: 2, prize: 'Trà sữa', number: '012', name: 'Trần Minh Anh', is_me: false },
      { rank: 1, prize: 'Tai nghe', number: '083', name: '', is_me: false }] });
    b.w.ECSvyDraw.mount(pop.querySelector('[data-drmount]'), done, { serverNow: day + ' 11:00:00' });
    o.done = { chip: txt(pop.querySelector('.ecd-chip')), nums: [...pop.querySelectorAll('.ecd-reels')].map(txt),
      res: [...pop.querySelectorAll('.ecd-res')].map(txt), replay: !!pop.querySelector('[data-ecd-replay]') };
    out.draw = o;
  }
  // 7b) Chua toi T-5 + da tich "khong hien hom nay": popup TU MO dung gio, nhay toi o quay so
  {
    const p = JSON.parse(payloadRaw);
    const now = new Date(Date.now() + 2000);
    const pad = (n) => String(n).padStart(2, '0');
    const fmt = (d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
    const srv = new Date();
    p.draws = { server_now: fmt(srv), soon: true, draws: [], timers: [{ name: 'KS-9', open_at: fmt(now), draw_at: fmt(new Date(now.getTime() + 300000)) }],
      upcoming: [{ name: 'KS-9', title: 'Quay trưa nay', mode: 'lucky_number', draw_at: fmt(new Date(now.getTime() + 300000)), days_left: 0, me: 'pick', url: '/khao-sat/lam?s=KS-9' }] };
    const b = await boot(htmlOn, { payload: p, draw: true, storage: JSON.stringify({ d: p.date, k: p.keys }) });
    const before = !!b.d.getElementById('ech-pop');
    await sleep(4200);
    const pop = b.d.getElementById('ech-pop');
    out.timer = { before, after: !!pop, slide: pop && txt(pop.querySelector('.th[aria-selected="true"] .tt')),
      cta: pop && txt(pop.querySelector('.upn-r a')) };
  }
  // 6) API hong -> im lang (console), khong popup
  {
    const b = await boot(htmlOn, { fail: true });
    out.fail = { pop: !!b.d.getElementById('ech-pop'), warns: b.warns.length };
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
