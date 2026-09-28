/* Kiem thu ec_api.js (khong can site, khong can jsdom):
 *   node ecentric_workspace/public/js/tests/test_ec_api.js
 * Moi test chay trong try/catch: NEM LOI = TRUOT (khong duoc tinh la dat).
 * EXPECT_TOTAL chot so test: lech la co test bi bo sot, bao HONG. */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'ec_api.js'), 'utf8');
const EXPECT_TOTAL = 12;

function resp(status, body) {
  return { ok: status >= 200 && status < 300, status: status, json: () => Promise.resolve(body) };
}

// Moi test mot sandbox moi: `routes(url, opts, n)` quyet dinh cau tra loi cho tung loi goi.
function load(routes, opts) {
  const calls = [];
  const win = { console };
  if (opts && opts.frappe) win.frappe = { csrf_token: 'OLD' };
  const fetchStub = (url, o) => {
    calls.push({ url: String(url), opts: o || {} });
    return Promise.resolve().then(() => routes(String(url), o || {}, calls.length));
  };
  win.fetch = fetchStub;
  win.window = win;
  const ctx = vm.createContext({ window: win, fetch: fetchStub, console, Promise, Date, JSON, Object, String, Error, encodeURIComponent });
  vm.runInContext(SRC, ctx);
  return { api: win.ecApi, calls, win, ctx, fetchStub };
}

const CSRF = u => u.indexOf('/api/method/get_csrf') >= 0;
const tick = () => new Promise(r => setTimeout(r, 0));

const tests = [];
function t(name, fn) { tests.push({ name, fn }); }

t('GET giong nhau dang bay dung chung MOT fetch', async () => {
  const { api, calls } = load(() => resp(200, { message: { n: 1 } }));
  const [a, b] = await Promise.all([api.get('m.x', { q: 1 }), api.get('m.x', { q: 1 })]);
  if (calls.length !== 1) throw new Error('fetch ' + calls.length + ' lan');
  if (a.n !== 1 || b !== a) throw new Error('ket qua khac nhau');
});

t('shareMs=0 sau khi xong thi goi lai; shareMs>0 trong han thi dung lai', async () => {
  const { api, calls } = load(() => resp(200, { message: 1 }));
  await api.get('m.x');
  await api.get('m.x');                       // mac dinh khong nho
  if (calls.length !== 2) throw new Error('shareMs=0 phai goi lai, dang ' + calls.length);
  await api.get('m.x', null, { shareMs: 15000 });
  if (calls.length !== 2) throw new Error('shareMs trong han van goi lai');
});

t('khoa theo args khong phu thuoc thu tu', async () => {
  const { api, calls } = load(() => resp(200, { message: 1 }));
  await Promise.all([api.get('m.x', { b: 1, a: 2 }), api.get('m.x', { a: 2, b: 1 })]);
  if (calls.length !== 1) throw new Error('fetch ' + calls.length + ' lan');
  if (calls[0].url !== '/api/method/m.x?a=2&b=1') throw new Error('url ' + calls[0].url);
});

t('loi KHONG duoc nho: lan sau goi lai', async () => {
  const { api, calls } = load((u, o, n) => n === 1 ? resp(500, { exc_type: 'Boom' }) : resp(200, { message: 7 }));
  let threw = false;
  try { await api.get('m.x', null, { shareMs: 15000 }); } catch (e) { threw = e.excType === 'Boom'; }
  if (!threw) throw new Error('lan 1 phai nem loi Boom');
  const v = await api.get('m.x', null, { shareMs: 15000 });
  if (v !== 7 || calls.length !== 2) throw new Error('lan 2 phai goi lai va thanh cong');
});

t('POST xin CSRF tuoi mot lan roi gui header', async () => {
  const { api, calls } = load(u => CSRF(u) ? resp(200, { message: { csrf_token: 'T1', is_guest: false } })
                                           : resp(200, { message: 'ok' }));
  const v = await api.post('m.save', { a: 1 });
  if (v !== 'ok') throw new Error('ket qua ' + v);
  const posts = calls.filter(c => !CSRF(c.url));
  if (calls.filter(c => CSRF(c.url)).length !== 1 || posts.length !== 1) throw new Error('so loi goi sai');
  if (posts[0].opts.headers['X-Frappe-CSRF-Token'] !== 'T1') throw new Error('thieu header token');
  if (posts[0].opts.method !== 'POST' || posts[0].opts.body !== '{"a":1}') throw new Error('body/method sai');
});

t('POST dong thoi dung chung MOT lan xin token', async () => {
  const { api, calls } = load(u => CSRF(u) ? resp(200, { message: { csrf_token: 'T1' } }) : resp(200, { message: 1 }));
  await Promise.all([api.post('m.a'), api.post('m.b'), api.post('m.c')]);
  if (calls.filter(c => CSRF(c.url)).length !== 1) throw new Error('xin token nhieu lan');
});

t('CSRFTokenError (doc theo noi dung) -> xin lai token, thu DUNG mot lan', async () => {
  let n = 0;
  const { api, calls } = load(u => {
    if (CSRF(u)) { n++; return resp(200, { message: { csrf_token: 'T' + n } }); }
    const tok = calls[calls.length - 1].opts.headers['X-Frappe-CSRF-Token'];
    return tok === 'T1' ? resp(400, { exc_type: 'CSRFTokenError' }) : resp(200, { message: 'saved' });
  });
  const v = await api.post('m.save');
  if (v !== 'saved') throw new Error('khong phuc hoi');
  if (n !== 2 || calls.filter(c => !CSRF(c.url)).length !== 2) throw new Error('phai dung 2 lan xin + 2 lan gui');
});

t('CSRF hong mai -> dung sau 2 lan gui, loi co csrf=true', async () => {
  const { api, calls } = load(u => CSRF(u) ? resp(200, { message: { csrf_token: 'T' } })
                                           : resp(400, { exc_type: 'CSRFTokenError' }));
  let e = null;
  try { await api.post('m.save'); } catch (x) { e = x; }
  if (!e || e.csrf !== true) throw new Error('phai nem loi csrf');
  if (calls.filter(c => !CSRF(c.url)).length !== 2) throw new Error('khong duoc lap vo han');
});

t('loi nghiep vu KHONG thu lai', async () => {
  const { api, calls } = load(u => CSRF(u) ? resp(200, { message: { csrf_token: 'T' } })
                                           : resp(417, { exc_type: 'ValidationError' }));
  let e = null;
  try { await api.post('m.save'); } catch (x) { e = x; }
  if (!e || e.excType !== 'ValidationError' || e.csrf) throw new Error('loi sai loai');
  if (calls.filter(c => !CSRF(c.url)).length !== 1) throw new Error('khong duoc thu lai');
});

t('Guest (is_guest) khong nhan token, khong gui header rac', async () => {
  const { api, calls } = load(u => CSRF(u) ? resp(200, { message: { csrf_token: 'X', is_guest: true } })
                                           : resp(200, { message: 1 }));
  await api.post('m.save');
  const post = calls.filter(c => !CSRF(c.url))[0];
  if ('X-Frappe-CSRF-Token' in post.opts.headers) throw new Error('khong duoc gui token cua Guest');
});

t('dong bo frappe.csrf_token cho code cu cua trang', async () => {
  const { api, win } = load(u => CSRF(u) ? resp(200, { message: { csrf_token: 'FRESH' } }) : resp(200, { message: 1 }),
                            { frappe: true });
  await api.post('m.save');
  if (win.frappe.csrf_token !== 'FRESH') throw new Error('frappe.csrf_token = ' + win.frappe.csrf_token);
});

t('cai mot lan va KHONG boc window.fetch', async () => {
  const env = load(() => resp(200, { message: 1 }));
  const first = env.api;
  vm.runInContext(SRC, env.ctx);
  if (env.win.ecApi !== first) throw new Error('nap lan 2 thay doi object');
  if (env.win.fetch !== env.fetchStub) throw new Error('window.fetch bi boc');
});

(async () => {
  let pass = 0, fail = 0;
  for (const x of tests) {
    try { await x.fn(); await tick(); pass++; console.log('ok   - ' + x.name); }
    catch (e) { fail++; console.error('FAIL - ' + x.name + ': ' + (e && e.message)); }
  }
  if (tests.length !== EXPECT_TOTAL) { console.error('HONG: EXPECT_TOTAL=' + EXPECT_TOTAL + ' nhung co ' + tests.length + ' test'); process.exit(1); }
  console.log(pass + ' dat, ' + fail + ' hong');
  process.exit(fail ? 1 : 0);
})();
