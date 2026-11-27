/* pm_queue_qc3.test.js — QC round 3 (15/11/2026) màn "Việc cần làm". Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue_qc3.test.js
 *  C2 tab "Việc tôi giao": khối "Đề xuất hạn" (server `proposals`) trên đầu tab, ngoài danh sách / số đếm; nhãn "Đề xuất hạn: <ngày>"
 *     + hạn cũ + lý do; "Đồng ý hạn mới" = assignment.requester_action(accept_counter), "Giữ hạn cũ, gửi lại" = requester_action(resend);
 *     đang gửi khoá nút (aria-busy), lỗi -> toast + nút mở lại + làm mới; thành công -> làm mới, focus không rơi ra body.
 *  Phía server (queue.list.proposals, rail badge = hàng đợi chính): ecentric_workspace/pm/tests/standalone/test_pm_queue_qc3.py */
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
    "assignment.respond": () => ({ ok: 1 }), "assignment.requester_action": a => ({ name: a.name, status: a.action === "resend" ? "Pending" : "Accepted" }), "pm_inbox.nudge": a => ({ task: a.task, sent: [], skipped: [] }), "assignment.list_assignable": () => ({ rows: PEOPLE }),
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

const PROP = (o) => row(Object.assign({ name: "P-1", subject: "Setup kho Bình Dương", workflow_state: "Backlog", giver: ME, giver_name: "", rank: 0,
  assignees: [{ user: "lan@ecentric.vn", name: "Nguyễn Thị Lan", opened: true, pending: 1 }],
  counter: { request: "AR-1", recipient: "lan@ecentric.vn", recipient_name: "Nguyễn Thị Lan", due: "2026-11-19", time: "17:30", start: null,
    old_due: "2026-11-14", old_time: "18:00", reason: "Tuần này đang kiểm kê <kho>" } }, o || {}));
const giveWithProps = props => a => (a.tab === "give" ? pack("give", giveRows(), { proposals: props }) : pack("me", meRows()));

(async () => {
  /* ---------- hiển thị */
  let t = setup({ tab: "give", h: { "queue.list": giveWithProps([PROP()]) } }); await flush();
  const box = t.$(".pmq-prop"), first = t.$("[data-ask]").nextElementSibling;
  ok("C2 khối 'Đề xuất hạn' nằm TRÊN danh sách (trong [data-ask], trước thanh lọc)", !!box && t.$("[data-ask]").contains(box) && first === t.$("[data-bar]"));
  ok("C2 tiêu đề '1 đề xuất hạn chờ bạn'", /1\s*đề xuất hạn chờ bạn/.test(box.querySelector(".pmq-ask-h").textContent));
  const li = box.querySelector('.pmq-ask-row[data-req="AR-1"]');
  ok("C2 nhãn 'Đề xuất hạn: T5 19/11 · 17:30' + hạn cũ + người nhận", !!li && /Đề xuất hạn: T5 19\/11 · 17:30/.test(li.textContent) && /hạn cũ T7 14\/11 · 18:00/.test(li.textContent) && /Nguyễn Thị Lan/.test(li.textContent), li && li.textContent);
  ok("C2 lý do hiện (đã esc, không thành thẻ)", li.querySelector(".pmq-quote").textContent === "Tuần này đang kiểm kê <kho>" && !li.querySelector("kho"));
  ok("C2 2 nút: 'Đồng ý hạn mới' (chính) + 'Giữ hạn cũ, gửi lại'", /Đồng ý hạn mới/.test(li.querySelector('[data-act="prop-accept"]').textContent) && li.querySelector('[data-act="prop-accept"]').classList.contains("pmq-btn--pri") &&
    /Giữ hạn cũ, gửi lại/.test(li.querySelector('[data-act="prop-resend"]').textContent));
  /* hotfix 23 (sửa): "Tất cả 3" (hàng nút lọc) -> tổng dải tuần */
  ok("C2 không vào danh sách / số đếm: tab giao = 3, tổng dải tuần 3, không có dòng P-1", t.$('[data-c="give"]').textContent === "3" && t.$$(".pmq-wk-n").reduce((a, x) => a + parseInt(x.textContent, 10), 0) === 3 && !t.rowEl("P-1"));
  ok("C2 dòng phụ đầu trang nói có 1 đề xuất hạn chờ bạn trả lời", /1\s*đề xuất hạn chờ bạn trả lời/.test(t.$(".sub").textContent), t.$(".sub").textContent);
  li.querySelector('[data-act="full"]').click(); await flush();
  ok("C2 bấm tên việc -> mở đầy đủ đúng việc", t.opened.length === 1 && t.opened[0][0] === "P-1");
  t.ctl.destroy(); t.w.close();

  /* tab Việc tôi làm không hiện khối đề xuất */
  t = setup({ tab: "me", h: { "queue.list": giveWithProps([PROP()]) } }); await flush();
  ok("C2 tab Việc tôi làm: không có khối đề xuất hạn", !t.$(".pmq-prop"));
  t.$('[data-tab="give"]').click(); await flush();
  ok("C2 chuyển sang tab giao -> khối đề xuất hiện", !!t.$(".pmq-prop"));
  t.$('[data-tab="me"]').click(); await flush();
  ok("C2 quay lại tab tôi làm -> khối đề xuất biến mất", !t.$(".pmq-prop"));
  t.ctl.destroy(); t.w.close();

  /* ---------- Đồng ý hạn mới */
  let release, state = [PROP()];
  t = setup({ tab: "give", h: { "queue.list": a => giveWithProps(state)(a),
    "assignment.requester_action": a => new Promise(r => { release = () => { state = []; r({ name: a.name, status: "Accepted" }); }; }) } }); await flush();
  const acc = t.$('[data-act="prop-accept"]');
  acc.focus(); acc.click(); await flush();
  const call1 = t.last("assignment.requester_action");
  ok("C2 Đồng ý hạn mới -> requester_action(name=AR-1, action=accept_counter)", call1 && call1.a.name === "AR-1" && call1.a.action === "accept_counter" && Object.keys(call1.a).length === 2, call1 && call1.a);
  ok("C2 đang gửi: 2 nút khoá + aria-busy (không bấm đúp)", t.$('[data-act="prop-accept"]').disabled && t.$('[data-act="prop-resend"]').disabled && t.$('[data-act="prop-accept"]').getAttribute("aria-busy") === "true");
  t.$('[data-act="prop-accept"]').click(); await flush();
  ok("C2 bấm lại khi đang gửi không gọi thêm", t.count("assignment.requester_action") === 1);
  const lists0 = t.count("queue.list");
  release(); await flush(); await flush();
  ok("C2 thành công: toast 'Đã đồng ý hạn mới T5 19/11 · 17:30 ... đã giao cho Nguyễn Thị Lan' + nút Mở", /Đã đồng ý hạn mới T5 19\/11 · 17:30/.test(t.$("[data-tm]").textContent) && /giao cho Nguyễn Thị Lan/.test(t.$("[data-tm]").textContent) &&
    /Mở/.test(t.$("[data-tacts]").textContent), t.$("[data-tm]").textContent);
  ok("C2 thành công: làm mới danh sách, khối đề xuất biến mất", t.count("queue.list") > lists0 && !t.$(".pmq-prop"));
  ok("C2 focus không rơi ra <body>", t.w.document.activeElement && t.w.document.activeElement !== t.w.document.body);
  t.ctl.destroy(); t.w.close();

  /* ---------- Giữ hạn cũ, gửi lại + lỗi */
  let fail1 = true;
  t = setup({ tab: "give", h: { "queue.list": giveWithProps([PROP(), PROP({ name: "P-2", subject: "Việc hai", counter: { request: "AR-2", recipient: "b@ecentric.vn", recipient_name: "Bình", due: null, time: null, start: "2026-11-17", old_due: null, old_time: null, reason: "" } })]),
    "assignment.requester_action": () => { if (fail1) { fail1 = false; const e = new Error("x"); e._server_messages = JSON.stringify([JSON.stringify({ message: "Việc này đã xong hoặc đã huỷ, không cần giao lại." })]); throw e; } return { status: "Pending" }; } } }); await flush();
  const li2 = t.$('.pmq-ask-row[data-req="AR-2"]');
  ok("C2 không có hạn đề xuất -> 'Đề xuất bắt đầu: T3 17/11', không có hạn cũ -> 'trước đó chưa có hạn', không lý do -> không có <q>",
    /Đề xuất bắt đầu: T3 17\/11/.test(li2.textContent) && /trước đó chưa có hạn/.test(li2.textContent) && !li2.querySelector(".pmq-quote"), li2.textContent);
  const lists1 = t.count("queue.list");
  li2.querySelector('[data-act="prop-resend"]').click(); await flush(); await flush();
  const call2 = t.last("assignment.requester_action");
  ok("C2 Giữ hạn cũ -> requester_action(name=AR-2, action=resend)", call2 && call2.a.name === "AR-2" && call2.a.action === "resend");
  ok("C2 lỗi: toast đỏ đọc câu của server, nút mở lại, làm mới theo server", t.$(".pmq-toast").classList.contains("pmq-toast--bad") && /đã xong hoặc đã huỷ/.test(t.$("[data-tm]").textContent) &&
    !t.$('.pmq-ask-row[data-req="AR-2"] [data-act="prop-resend"]').disabled && t.count("queue.list") > lists1, t.$("[data-tm]").textContent);
  t.$('.pmq-ask-row[data-req="AR-2"] [data-act="prop-resend"]').click(); await flush(); await flush();
  ok("C2 thử lại thành công: toast 'Đã giữ hạn cũ và gửi lại cho Bình ... Chờ Bình nhận.' (không Hoàn tác)", /Đã giữ hạn cũ và gửi lại cho Bình/.test(t.$("[data-tm]").textContent) && /Chờ Bình nhận/.test(t.$("[data-tm]").textContent) &&
    !/Hoàn tác/.test(t.$("[data-tacts]").textContent));
  t.ctl.destroy(); t.w.close();

  /* ---------- dữ liệu bẩn / chỉ có đề xuất */
  t = setup({ tab: "give", h: { "queue.list": a => (a.tab === "give" ? pack("give", [], { proposals: [PROP(), { name: "BAD" }, null, PROP({ name: "P-3", subject: "<img src=x onerror=alert(1)>", counter: { request: "AR-3", recipient_name: "<b>x</b>" } })] }) : pack("me", meRows())) } }); await flush();
  ok("C2 đề xuất thiếu counter bị bỏ qua, tên việc / người được esc", t.$$(".pmq-prop .pmq-ask-row").length === 2 && !t.$(".pmq-prop img") && !t.$(".pmq-prop b b") && /<img/.test(t.$('.pmq-ask-row[data-req="AR-3"] .pmq-prop-t').textContent));
  ok("C2 chỉ có đề xuất, không việc giao nào: không nói 'chưa giao việc nào' mà 'không còn việc đã giao nào khác'", /Không còn việc đã giao nào khác đang mở/.test(t.$("[data-list]").textContent) && !/Bạn chưa giao việc nào/.test(t.$("[data-list]").textContent) &&
    /2\s*đề xuất hạn chờ bạn trả lời/.test(t.$(".sub").textContent));
  t.ctl.destroy(); t.w.close();

  /* ---------- tĩnh */
  ok("C2 CSS khối đề xuất trong namespace .pmq-", /\.pmq-ask-main \.pmq-prop-t\{/.test(CSS) && /\.pmq-prop-due\{/.test(CSS));
  ok("không console.log sót, không ký tự Jinja", !/console\.log\(/.test(JS) && !/\{\{|\{%|\{#/.test(JS));

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || r.x === undefined ? "" : "  -> " + r.x)); });
  console.log((res.length - fail) + "/" + res.length + " passed");
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
