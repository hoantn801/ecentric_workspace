/* pm_queue_qc4.test.js — QC round 4 (15/11/2026, nghiệm thu "một ngày dùng") màn "Việc cần làm". Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue_qc4.test.js
 *  D1 Xin dời hạn khép vòng: dòng của mình "Đã xin dời sang …" + ẩn nút (server deadline_ask); người giao: khối đề xuất kind "deadline"
 *     -> pm_inbox.answer_deadline(request, accept 1/0), nút "Đồng ý hạn mới" / "Giữ hạn cũ".
 *  D2 số giới hạn lấy từ server (`limit`).  D3 tab giao: lọc "Chưa mở việc", "Đã nhắc HH:MM" sau khi nhắc, "Trả lại" việc Chờ duyệt.
 *  D4 câu chữ: tóm tắt tab giao, toast giao "Cần đồng ý" có hạn.
 *  Phía server: ecentric_workspace/pm/tests/standalone/test_pm_queue_qc4.py */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_queue.js"), "utf8");
const PMRJS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_redesign.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "css", "pm", "pm_queue.css"), "utf8");
const res = [];
const ok = (n, c, x) => res.push({ n, c: !!c, x });
const tick = ms => new Promise(r => setTimeout(r, ms || 0));
const flush = async () => { for (let i = 0; i < 8; i++) await tick(0); };
const ME = "hoan@ecentric.vn", TODAY = "2026-11-13", NOW = "09:30";   /* server: T6 13/11; máy test chạy ngày khác */
const BUCKETS = [{ key: "late", label: "Quá hạn" }, { key: "today", label: "Hôm nay" }, { key: "tomorrow", label: "Ngày mai" }, { key: "week", label: "Còn lại tuần này" }, { key: "later", label: "Tuần sau trở đi" }, { key: "none", label: "Chưa có hạn" }];
const row = o => Object.assign({ workflow_state: "To Do", project: "", project_name: "", priority: "Medium", due: TODAY, due_time: null, bucket: "today", giver: "huyen@ecentric.vn",
  giver_name: "Huyền", self: false, assignees: [{ user: ME, name: "Trần Hoàn", opened: true }], unopened: false, group: 0, review: 0, parent_task: null }, o);
const pack = (tab, rows, extra) => { rows.forEach((r, i) => { r.rank = i + 1; }); const counts = {}; rows.forEach(r => { counts[r.bucket] = (counts[r.bucket] || 0) + 1; });
  return Object.assign({ today: TODAY, now: NOW, tab, rows, counts, buckets: BUCKETS, asks: [], personal_hidden: 0, waiting: [], truncated: 0 }, extra || {}); };
const W1 = () => row({ name: "W-1", subject: "Báo cáo đã gửi kiểm tra", workflow_state: "Review", bucket: "late", due: "2026-11-12", waiting: 1, rank: 0, review: 1 });
const meRows = () => [row({ name: "T-1", subject: "Việc một" }), row({ name: "T-2", subject: "Việc hai", bucket: "tomorrow", due: "2026-11-14" })];
const giveRows = () => [
  row({ name: "G-AW", subject: "Setup kho Long An", workflow_state: "Backlog", giver: ME, giver_name: "", awaiting: 1, assignees: [{ user: "lan@ecentric.vn", name: "Lan", opened: true, pending: 1 }] }),
  row({ name: "G-SP", subject: "Báo cáo tuần (3 người)", workflow_state: "In Progress", group: 1, giver: ME, giver_name: "", progress: { done: 1, total: 3 },
    assignees: [{ user: "a@ecentric.vn", name: "An", opened: true, done: 1 }, { user: "b@ecentric.vn", name: "Bình", opened: true }, { user: "c@ecentric.vn", name: "Chi", opened: true }] }),
  row({ name: "G-LEFT", subject: "Đối soát Q3", giver: ME, giver_name: "", assignees: [{ user: "old@ecentric.vn", name: "Người cũ", opened: true, left: 1 }] })];
const PEOPLE = [{ email: ME, full_name: "Trần Hoàn" }, { email: "lan@ecentric.vn", full_name: "Nguyễn Thị Lan" }];

function setup(o) {
  o = o || {};
  const dom = new JSDOM("<!doctype html><body><div id=v></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#mywork", pretendToBeVisual: true });
  const w = dom.window, calls = [], opened = [], intervals = [], live = new Map();
  w.fetch = () => Promise.reject(new Error("no network"));
  const si = w.setInterval.bind(w), ci = w.clearInterval.bind(w);
  w.setInterval = (fn, ms) => { const id = si(fn, ms); intervals.push({ id, fn, ms }); live.set(id, ms); return id; };
  w.clearInterval = id => { live.delete(id); return ci(id); };
  const docL = new Map(), add = w.document.addEventListener.bind(w.document), rem = w.document.removeEventListener.bind(w.document);
  const QT = { keydown: 1, click: 1, visibilitychange: 1, "pmr:changed": 1 };   /* loại sự kiện màn này gắn lên document (jsdom tự gắn load/DOMContentLoaded) */
  w.document.addEventListener = (t, f, x) => { if (QT[t]) docL.set(f, t); return add(t, f, x); };
  w.document.removeEventListener = (t, f, x) => { docL.delete(f); return rem(t, f, x); };
  w.eval(PMRJS);
  w.eval(JS);
  const H = Object.assign({
    "queue.list": a => (a.tab === "give" ? pack("give", giveRows()) : pack("me", meRows(), { waiting: [W1()] })),
    "tasks.mark_done": () => ({ state: "Done" }), "tasks.set_status": () => ({ ok: 1 }), "tasks.create": () => ({ name: "T-NEW" }),
    "assignment.respond": () => ({ ok: 1 }), "assignment.requester_action": a => ({ name: a.name, status: a.action === "resend" ? "Pending" : "Accepted" }), "pm_inbox.nudge": a => ({ task: a.task, sent: ["lan@ecentric.vn"], skipped: [] }), "pm_inbox.answer_deadline": a => ({ request: a.request, status: a.accept ? "Accepted" : "Rejected" }), "assignment.list_assignable": () => ({ rows: PEOPLE }),
    "tasks.get": a => ({ task: { name: a.name, description: "" } })
  }, o.h || {});
  const api = (method, args) => { const m = method.replace("ecentric_workspace.pm.api.", ""); calls.push({ m, a: args }); const fn = H[m]; if (!fn) return Promise.reject(new Error("no " + m));
    try { return Promise.resolve(fn(args || {}, calls)); } catch (e) { return Promise.reject(e); } };
  const c = w.document.getElementById("v");
  const mk = () => w.PMQueue.render(c, { api, user: ME, tab: o.tab || "me", openTask: (n, oo) => opened.push([n, oo || null]),
    head: (t, s, r) => `<div class="pm-head"><div><h1>${t}</h1><div class="sub">${s}</div></div><div>${r || ""}</div></div>` });
  const ctl = o.noRender ? null : mk();
  const $ = s => w.document.querySelector(s), $$ = s => Array.from(w.document.querySelectorAll(s));
  const key = (k, target) => (target || w.document.body).dispatchEvent(new w.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
  const count = m => calls.filter(x => x.m === m).length;
  const last = m => calls.filter(x => x.m === m).slice(-1)[0];
  const rowEl = n => $(`.pmq-row[data-name="${n}"]`);
  const type = async v => { const i = $("[data-qa]"); i.focus(); i.value = v; try { i.setSelectionRange(v.length, v.length); } catch (_) { } i.dispatchEvent(new w.Event("input", { bubbles: true })); await flush(); };
  const submit = () => $("[data-qa-form]").dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true }));
  return { w, c, ctl, mk, calls, opened, intervals, live, docL, H, $, $$, key, count, last, rowEl, type, submit };
}


const DL = o => row(Object.assign({ name: "G-DL", subject: "Đối soát Shopee", giver: ME, giver_name: "", rank: 0, assignees: [{ user: "lan@ecentric.vn", name: "Nguyễn Thị Lan", opened: true }],
  counter: { kind: "deadline", request: "DL-1", recipient: "lan@ecentric.vn", recipient_name: "Nguyễn Thị Lan", due: "2026-11-19", time: "15:00", start: null, old_due: "2026-11-13", old_time: "15:00", reason: "Chờ sàn xuất file" } }, o || {}));
const give2 = () => [
  row({ name: "G-UN", subject: "Chưa mở đây", giver: ME, giver_name: "", unopened: true, assignees: [{ user: "lan@ecentric.vn", name: "Nguyễn Thị Lan", opened: false }] }),
  row({ name: "G-RV", subject: "Báo cáo tồn kho", giver: ME, giver_name: "", workflow_state: "Review", bucket: "late", due: "2026-11-12", assignees: [{ user: "minh@ecentric.vn", name: "Lê Minh", opened: true }] }),
  row({ name: "G-OK", subject: "Đã mở", giver: ME, giver_name: "", bucket: "tomorrow", due: "2026-11-14", assignees: [{ user: "an@ecentric.vn", name: "An", opened: true }] })];

(async () => {
  /* ---------- D1 người nhận: đã xin dời hạn */
  let t = setup({ h: { "queue.list": a => (a.tab === "give" ? pack("give", []) : pack("me", [row({ name: "T-1", subject: "Việc một", deadline_ask: { due: "2026-11-18" } }), row({ name: "T-2", subject: "Việc hai" })])) } }); await flush();
  ok("D1 dòng đã xin dời: nhãn 'Đã xin dời sang T4 18/11'", /Đã xin dời sang T4 18\/11/.test(t.rowEl("T-1").textContent), t.rowEl("T-1").textContent);
  ok("D1 dòng đã xin dời: ẩn nút Xin dời hạn; dòng khác vẫn có", !t.rowEl("T-1").querySelector('[data-act="ask"]') && !!t.rowEl("T-2").querySelector('[data-act="ask"]'));
  t.rowEl("T-1").querySelector(".pmq-open").click(); await flush();
  ok("D1 ngăn chi tiết: 'Đã xin dời sang T4 18/11, chờ Huyền trả lời', không có nút Xin dời hạn", /Đã xin dời sang T4 18\/11, chờ Huyền trả lời/.test(t.$("[data-drawer]").textContent) && !t.$('[data-drawer] [data-act="ask"]'));
  t.ctl.destroy(); t.w.close();

  t = setup({ h: { "queue.list": a => pack(a.tab, [row({ name: "T-1", subject: "x", deadline_ask: { due: "rác" } })]) } }); await flush();
  ok("D1 deadline_ask hỏng -> như chưa xin (không vỡ, còn nút)", !/Đã xin dời/.test(t.rowEl("T-1").textContent) && !!t.rowEl("T-1").querySelector('[data-act="ask"]'));
  t.ctl.destroy(); t.w.close();

  /* ---------- D1 người giao: khối đề xuất kind deadline */
  let state = [DL()];
  t = setup({ tab: "give", h: { "queue.list": a => (a.tab === "give" ? pack("give", giveRows(), { proposals: state }) : pack("me", meRows())),
    "pm_inbox.answer_deadline": a => { state = []; return { request: a.request, status: a.accept ? "Accepted" : "Rejected" }; } } }); await flush();
  const li = t.$('.pmq-prop .pmq-ask-row[data-req="DL-1"]');
  ok("D1 khối đề xuất: 'Xin dời sang: T5 19/11 · 15:00', hạn cũ, lý do, người xin", !!li && /Xin dời sang: T5 19\/11 · 15:00/.test(li.textContent) && /hạn cũ T6 13\/11 · 15:00/.test(li.textContent) && /Chờ sàn xuất file/.test(li.textContent) && /Nguyễn Thị Lan/.test(li.textContent), li && li.textContent);
  ok("D1 nút: 'Đồng ý hạn mới' + 'Giữ hạn cũ' (không 'gửi lại')", /Đồng ý hạn mới/.test(li.textContent) && !!li.querySelector('[data-act="prop-keep"]') && !li.querySelector('[data-act="prop-resend"]') && !/gửi lại/.test(li.textContent));
  li.querySelector('[data-act="prop-accept"]').click(); await flush(); await flush();
  const c1 = t.last("pm_inbox.answer_deadline");
  ok("D1 Đồng ý -> pm_inbox.answer_deadline(request=DL-1, accept=1), không gọi requester_action", c1 && c1.a.request === "DL-1" && c1.a.accept === 1 && t.count("assignment.requester_action") === 0, c1 && c1.a);
  ok("D1 toast 'Đã đồng ý dời hạn “Đối soát Shopee” sang T5 19/11 · 15:00. Nguyễn Thị Lan được báo.' + khối biến mất", /Đã đồng ý dời hạn “Đối soát Shopee” sang T5 19\/11 · 15:00\. Nguyễn Thị Lan được báo\./.test(t.$("[data-tm]").textContent) && !t.$(".pmq-prop"), t.$("[data-tm]").textContent);
  t.ctl.destroy(); t.w.close();

  state = [DL()];
  let fail = true;
  t = setup({ tab: "give", h: { "queue.list": a => (a.tab === "give" ? pack("give", giveRows(), { proposals: state }) : pack("me", meRows())),
    "pm_inbox.answer_deadline": a => { if (fail) { fail = false; const e = new Error("x"); e._server_messages = JSON.stringify([JSON.stringify({ message: "Đề xuất này không còn chờ trả lời." })]); throw e; } state = []; return { status: "Rejected" }; } } }); await flush();
  t.$('[data-act="prop-keep"]').click(); await flush(); await flush();
  ok("D1 Giữ hạn cũ lỗi -> toast lỗi tiếng Việt của server, nút mở lại", /không còn chờ trả lời/.test(t.$("[data-tm]").textContent) && !t.$('[data-act="prop-keep"]').disabled);
  t.$('[data-act="prop-keep"]').click(); await flush(); await flush();
  const c2 = t.last("pm_inbox.answer_deadline");
  ok("D1 Giữ hạn cũ -> answer_deadline(accept=0) + toast 'Đã giữ hạn cũ cho …'", c2.a.accept === 0 && /Đã giữ hạn cũ cho “Đối soát Shopee”\. Nguyễn Thị Lan được báo\./.test(t.$("[data-tm]").textContent));
  t.ctl.destroy(); t.w.close();

  /* ---------- D2 limit */
  t = setup({ h: { "queue.list": a => pack(a.tab, meRows(), { truncated: 1, limit: 300 }) } }); await flush();
  ok("D2 truncated: số lấy từ server (300), không ghi cứng 500", /Đang hiện 300 việc/.test(t.$("[data-note]").textContent) && !/500/.test(t.$("[data-note]").textContent));
  t.ctl.destroy(); t.w.close();
  ok("D2 asset không còn số 500 ghi cứng", !/>500</.test(JS) && !/\b500\b<\/b>/.test(JS));

  /* ---------- D3 tab giao */
  t = setup({ tab: "give", h: { "queue.list": a => (a.tab === "give" ? pack("give", give2()) : pack("me", meRows())) } }); await flush();
  ok("D4 tóm tắt: '1 việc người nhận chưa mở'", /1 việc người nhận chưa mở/.test(t.$(".sub").textContent), t.$(".sub").textContent);
  const chip = t.$('[data-f="unopened"]');
  ok("D3 có ô lọc 'Chưa mở việc 1'", !!chip && /Chưa mở việc\s*1/.test(chip.textContent));
  chip.click(); await flush();
  ok("D3 lọc Chưa mở: chỉ còn dòng chưa mở", t.$$(".pmq-row").length === 1 && !!t.rowEl("G-UN") && t.$('[data-f="unopened"]').getAttribute("aria-pressed") === "true");
  t.rowEl("G-UN").querySelector('[data-act="nudge"]').click(); await flush();
  ok("D3 sau Nhắc: dòng ghi 'Đã nhắc HH:MM', nút Nhắc nói đã nhắc lúc mấy giờ", /Đã nhắc \d\d:\d\d/.test(t.rowEl("G-UN").textContent) && /Đã nhắc lúc \d\d:\d\d/.test(t.rowEl("G-UN").querySelector('[data-act="nudge"]').title));
  await t.ctl.refresh(); await flush();
  ok("D3 'Đã nhắc' còn sau khi làm mới; lọc vẫn giữ", /Đã nhắc/.test(t.rowEl("G-UN").textContent) && t.$$(".pmq-row").length === 1);
  t.$('[data-f="all"]').click(); await flush();
  const rv = t.rowEl("G-RV");
  ok("D3 việc Chờ duyệt (tab giao): 'Duyệt xong' + 'Trả lại'", !!rv.querySelector('[data-act="approve"]') && /Trả lại/.test(rv.querySelector('[data-act="return"]').textContent));
  rv.querySelector('[data-act="return"]').click(); await flush(); await flush();
  const rs = t.last("tasks.set_status");
  ok("D3 Trả lại -> tasks.set_status(G-RV, In Progress) + toast có Mở + Hoàn tác", rs && rs.a.name === "G-RV" && rs.a.action === "In Progress" && /Đã trả lại “Báo cáo tồn kho” cho Lê Minh/.test(t.$("[data-tm]").textContent) && /Mở/.test(t.$("[data-tacts]").textContent) && /Hoàn tác/.test(t.$("[data-tacts]").textContent));
  Array.from(t.$$("[data-tacts] button")).find(b => b.textContent === "Hoàn tác").click(); await flush();
  ok("D3 Hoàn tác trả lại -> set_status(Review)", t.last("tasks.set_status").a.action === "Review");
  t.ctl.destroy(); t.w.close();

  t = setup({ tab: "me", h: { "queue.list": a => pack(a.tab, [row({ name: "S-RV", subject: "Tự ghi chờ duyệt", workflow_state: "Review", self: true, giver: ME, giver_name: "" })]) } }); await flush();
  ok("D3 tab tôi làm: việc tự ghi Chờ duyệt có Duyệt xong, không có Trả lại", !!t.rowEl("S-RV").querySelector('[data-act="approve"]') && !t.rowEl("S-RV").querySelector('[data-act="return"]'));
  t.ctl.destroy(); t.w.close();

  /* ---------- tĩnh */
  ok("không console sót, không Jinja", !/console\.(log|debug|info)/.test(JS) && !/\{\{|\{%|\{#/.test(JS));
  ok("CSS: không còn luật chết .pmq-qa-in[readonly]; có màu ô lọc Chưa mở", !/pmq-qa-in\[readonly\]/.test(CSS) && /pmq-f--warn/.test(CSS));

  let pass = 0;
  res.forEach(r => { console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || r.x === undefined ? "" : "  -> " + JSON.stringify(r.x))); if (r.c) pass++; });
  console.log(pass + "/" + res.length + " passed");
  process.exit(pass === res.length ? 0 : 1);
})();
