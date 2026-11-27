/* pm_queue_qc2.test.js — QC round 2 (15/11/2026) màn "Việc cần làm". Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue_qc2.test.js
 *  A1 "Đang chờ duyệt (n)": việc mình đã gửi kiểm tra (server `waiting`) thu gọn cuối danh sách, không số thứ tự / số đếm / J-K.
 *  A2/A4 tab giao: "x/y người xong", "Chờ nhận" (không có Nhắc), "Người nhận đã nghỉ"; A5 `truncated` báo nhẹ.
 *  A6 giao 1 dòng: "cao"/"thấp" cuối câu = ưu tiên; "thứ 6" gõ đúng thứ Sáu = thứ Sáu tuần sau (PMR._pure.parseDue không đổi).
 *  B  đồng hồ server (không dùng giờ máy), tự làm mới không vẽ lại khi dữ liệu y hệt, quay lại tab -> làm mới,
 *     không rò listener/timer sau 20 lần chuyển màn, focus sau thao tác, tên đọc màn hình, dữ liệu bẩn. */
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
    "assignment.respond": () => ({ ok: 1 }), "pm_inbox.nudge": a => ({ task: a.task, sent: [], skipped: [] }), "assignment.list_assignable": () => ({ rows: PEOPLE }),
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

(async () => {
  /* ---------- A1 Đang chờ duyệt */
  let t = setup(); await flush();
  const sec = t.$(".pmq-g--wait"), tg = t.$('[data-act="wait"]');
  ok("A1 nhóm 'Đang chờ duyệt (1)' ở CUỐI danh sách, thu gọn mặc định", !!sec && sec === t.$$("[data-list] .pmq-g").slice(-1)[0] && /Đang chờ duyệt\s*1/.test(tg.textContent) && tg.getAttribute("aria-expanded") === "false" && !t.rowEl("W-1"));
  /* hotfix 23 (sửa): hàng nút lọc -> dải tuần; tổng dải tuần cũng không tính việc chờ duyệt, ô Trễ hạn = 0 (khoá) */
  ok("A1 không tính vào số đếm: tab 'Việc tôi làm' = 2, tổng dải tuần 2, ô Trễ hạn 0", t.$('[data-c="me"]').textContent === "2" && t.$$(".pmq-wk-n").reduce((a, x) => a + parseInt(x.textContent, 10), 0) === 2 && t.$('[data-wk="late"]').disabled);
  tg.click(); await flush();
  const w1 = t.rowEl("W-1");
  ok("A1 bấm mở: aria-expanded=true, aria-controls trỏ đúng danh sách, dòng hiện, focus vẫn ở nút", t.$('[data-act="wait"]').getAttribute("aria-expanded") === "true" && !!w1 &&
    t.w.document.getElementById(t.$('[data-act="wait"]').getAttribute("aria-controls")).contains(w1) && t.w.document.activeElement === t.$('[data-act="wait"]'));
  ok("A1 dòng chờ duyệt: không số thứ tự, ô tròn khoá 'Đang chờ người giao kiểm tra', không Bắt đầu", !w1.querySelector(".pmq-rk") && w1.querySelector(".pmq-chk").disabled &&
    /chờ người giao kiểm tra/i.test(w1.querySelector(".pmq-chk").title) && !w1.querySelector('[data-act="start"]'));
  t.key("j"); t.key("j"); t.key("j"); t.key("j");
  ok("A1 J/K chỉ đi trong hàng đợi chính (không nhảy vào việc chờ duyệt)", t.ctl._state.sel === "T-2", t.ctl._state.sel);
  t.key("x"); await flush();
  ok("A1 X trên hàng đợi chính vẫn chạy (T-2)", t.last("tasks.mark_done") && t.last("tasks.mark_done").a.name === "T-2");
  t.rowEl("W-1").querySelector(".pmq-open").click(); await flush();
  /* hotfix 23 (sửa): ngăn chi tiết -> cửa sổ chung; nav = các việc chờ duyệt đang hiện */
  ok("A1 mở chi tiết việc chờ duyệt được (openTask, nav trong nhóm chờ duyệt)", t.opened.slice(-1)[0][0] === "W-1" && t.opened.slice(-1)[0][1].nav.names.join(",") === "W-1");
  t.ctl.destroy(); t.w.close();
  t = setup({ h: { "queue.list": a => (a.tab === "give" ? pack("give", []) : pack("me", [], { waiting: [W1()] })) } }); await flush();
  ok("A1 chỉ còn việc chờ duyệt: 'Không còn việc nào cần bạn làm' + nhóm chờ duyệt (không mời ghi việc như trống trơn)",
    /Không còn việc nào cần bạn làm/.test(t.$("[data-list]").textContent) && !!t.$(".pmq-g--wait") && /Không còn việc nào cần bạn làm/.test(t.$(".sub").textContent));
  t.ctl.destroy(); t.w.close();
  t = setup({ tab: "give" }); await flush();
  ok("A1 tab giao không có nhóm chờ duyệt", !t.$(".pmq-g--wait"));

  /* ---------- A2/A4 tab giao */
  const aw = t.rowEl("G-AW"), sp = t.rowEl("G-SP"), lf = t.rowEl("G-LEFT");
  ok("A4 'Chờ nhận': nhãn, KHÔNG có nút Nhắc, ô tròn 'Chờ người nhận đồng ý'", /Chờ nhận/.test(aw.textContent) && !aw.querySelector('[data-act="nudge"]') && /Chờ người nhận đồng ý/.test(aw.querySelector(".pmq-chk").title));
  ok("A2 việc cha chia người: '1/3 người xong' + Nhắc (người chưa xong)", /1\/3 người xong/.test(sp.textContent) && !/Nhiều người/.test(sp.textContent) && !!sp.querySelector('[data-act="nudge"]'));
  ok("B người nhận đã nghỉ: nhãn cảnh báo", /Người nhận đã nghỉ/.test(lf.textContent));
  ok("A4 dòng tiêu đề tab giao đếm 'chờ nhận'", /1 chờ nhận/.test(t.$(".sub").textContent), t.$(".sub").textContent);
  /* hotfix 23 (sửa): "Lan (chờ nhận)" / "An (xong)" từng ở ngăn chi tiết -> cửa sổ PMR hiện người nhận; ở đây chỉ kiểm mở đúng việc */
  aw.querySelector(".pmq-open").click(); await flush();
  ok("A4 bấm việc chờ nhận -> openTask('G-AW', {nav})", t.opened.slice(-1)[0][0] === "G-AW" && t.opened.slice(-1)[0][1].nav.names.indexOf("G-AW") >= 0);
  sp.querySelector(".pmq-open").click(); await flush();
  ok("A2 bấm việc chia người -> openTask('G-SP')", t.opened.slice(-1)[0][0] === "G-SP");
  t.ctl.destroy(); t.w.close();

  /* ---------- A5 truncated */
  t = setup({ h: { "queue.list": a => pack(a.tab, meRows(), { truncated: 1, limit: 500 }) } }); await flush();
  ok("A5 truncated -> báo nhẹ 'Đang hiện 500 việc có hạn gần nhất' (500 = limit của server)", !t.$("[data-note]").hidden && /500 việc có hạn gần nhất/.test(t.$("[data-note]").textContent));
  t.ctl.destroy(); t.w.close();
  t = setup(); await flush();
  ok("A5 không truncated, không nhật ký -> không có ghi chú", t.$("[data-note]").hidden);
  t.ctl.destroy(); t.w.close();

  /* ---------- A6 đọc câu giao việc */
  t = setup(); await flush();
  const P = (s, base) => t.w.PMQueue._parseLine(s, { parseDue: t.w.PMR._pure.parseDue, base: base || new t.w.Date(2026, 10, 13, 9, 30) });
  const cases = [
    ["Gửi báo cáo thứ 6", { due: "2026-11-20", subject: "Gửi báo cáo" }],
    ["Gửi báo cáo t6", { due: "2026-11-20" }],
    ["Gửi báo cáo thứ sáu", { due: "2026-11-20" }],
    ["Gửi báo cáo thứ 2", { due: "2026-11-16" }],
    ["Gửi báo cáo hôm nay", { due: "2026-11-13" }],
    ["Gửi báo cáo thứ 6 tuần sau", { due: "2026-11-20" }],
    ["Làm báo cáo cao", { priority: "High", subject: "Làm báo cáo" }],
    ["Làm báo cáo thấp", { priority: "Low", subject: "Làm báo cáo" }],
    ["Làm báo cáo CAO", { priority: "High" }],
    ["Báo cáo cao điểm", { priority: null, subject: "Báo cáo cao điểm" }],
    ["Đo chiều cao", { priority: null, subject: "Đo chiều cao" }],
    ["Khoá đào tạo nâng cao", { priority: null }],
    ["Chốt giá thấp", { priority: null }],
    ["cao", { priority: null, subject: "cao" }],
    ["Gửi file thứ 6 cao", { priority: "High", due: "2026-11-20", subject: "Gửi file" }],
    ["Gửi file cao thứ 6", { priority: "High", due: "2026-11-20", subject: "Gửi file" }],
    ["@Lan gửi file thấp", { priority: "Low", token: "Lan", subject: "gửi file" }],
    ["Gửi file gấp cao", { priority: "Urgent" }]];
  cases.forEach(cs => { const p = P(cs[0]), bad = Object.keys(cs[1]).filter(k => p[k] !== cs[1][k]); ok("A6 " + JSON.stringify(cs[0]) + " -> " + JSON.stringify(cs[1]), !bad.length, JSON.stringify(p)); });
  const raw = t.w.PMR._pure.parseDue("Gửi báo cáo thứ 6", { base: new t.w.Date(2026, 10, 13, 9, 30), tail: true });
  ok("A6 PMR._pure.parseDue dùng chung KHÔNG đổi (thứ 6 vào thứ Sáu = hôm nay)", raw && raw.due === "2026-11-13");
  ok("A6 thứ Năm gõ 'thứ 6' -> ngày mai (không cộng tuần)", P("Gửi báo cáo thứ 6", new t.w.Date(2026, 10, 12, 9, 0)).due === "2026-11-13");
  await t.type("Gửi báo cáo thứ 6"); t.submit(); await flush();
  ok("A6 giao qua ô: hạn = thứ Sáu tuần sau theo NGÀY SERVER (2026-11-20)", t.last("tasks.create") && t.last("tasks.create").a.exp_end_date === "2026-11-20", JSON.stringify(t.last("tasks.create")));
  await t.type("Việc không ghi hạn"); t.submit(); await flush();
  ok("B không ghi hạn -> mặc định ngày mai theo ngày server (14/11), không theo đồng hồ máy", t.last("tasks.create").a.exp_end_date === "2026-11-14");
  t.ctl.destroy(); t.w.close();

  /* ---------- B đồng hồ server */
  t = setup({ h: { "queue.list": a => pack(a.tab, [row({ name: "L-1", subject: "Trễ", bucket: "late", due: "2026-11-12" }), row({ name: "D-1", subject: "Hôm nay", bucket: "today" })]) } }); await flush();
  ok("B 'Trễ 1 ngày' tính theo ngày server (máy test chạy ngày khác)", /Trễ 1 ngày/.test(t.rowEl("L-1").textContent));
  ok("B nhóm Hôm nay ghi T6 13/11 (ngày server)", /T6 13\/11/.test(t.$(".pmq-g--today .pmq-grp").textContent));
  ok("B dòng tiêu đề: 'Thứ Sáu, 13/11'", /Thứ Sáu, 13\/11/.test(t.$(".sub").textContent));
  t.ctl.destroy(); t.w.close();
  t = setup({ h: { "queue.list": a => Object.assign(pack(a.tab, [row({ name: "S-1", bucket: "tomorrow", due: "2026-11-16" }), row({ name: "S-2", bucket: "later", due: "2026-11-17" })]), { today: "2026-11-15" }) } }); await flush();
  ok("B Chủ nhật: không có nhóm 'Còn lại tuần này', Ngày mai = T2 16/11", !t.$(".pmq-g--week") && /T2 16\/11/.test(t.$(".pmq-g--tomorrow .pmq-grp").textContent));
  t.ctl.destroy(); t.w.close();

  /* ---------- B tự làm mới không vẽ lại khi dữ liệu y hệt */
  let ver = 1;
  t = setup({ h: { "queue.list": a => pack(a.tab, ver === 1 ? meRows() : meRows().concat([row({ name: "T-3", subject: "Việc ba", bucket: "none", due: null })])) } }); await flush();
  const list = t.$("[data-list]"), firstRow = t.rowEl("T-1");
  t.rowEl("T-1").querySelector(".pmq-open").focus(); await flush();
  let muts = 0;
  const mo = new t.w.MutationObserver(ms => { muts += ms.length; });
  mo.observe(t.$("[data-pmq]"), { childList: true, subtree: true, attributes: true, characterData: true });
  const n0 = t.count("queue.list");
  t.intervals.find(x => x.ms === 60000).fn(); await flush();
  await flush(); mo.takeRecords();
  ok("B tự làm mới 60 giây, dữ liệu y hệt: có gọi server nhưng 0 thay đổi DOM, giữ nguyên node + focus",
    t.count("queue.list") > n0 && muts === 0 && t.rowEl("T-1") === firstRow && t.w.document.activeElement === firstRow.querySelector(".pmq-open"), "muts=" + muts);
  ver = 2;
  t.intervals.find(x => x.ms === 60000).fn(); await flush();
  ok("B dữ liệu đổi -> vẽ lại (thấy việc mới), focus giữ ở dòng đang đứng", !!t.rowEl("T-3") && t.w.document.activeElement === t.rowEl("T-1").querySelector(".pmq-open"));
  mo.disconnect();
  /* quay lại tab trình duyệt */
  const n1 = t.count("queue.list");
  t.ctl._state.lastFetch = Date.now() - 20000;
  t.w.document.dispatchEvent(new t.w.Event("visibilitychange")); await flush();
  ok("B quay lại tab sau >15 giây -> làm mới (2 tab cùng mở)", t.count("queue.list") > n1);
  const n2 = t.count("queue.list");
  t.w.document.dispatchEvent(new t.w.Event("visibilitychange")); await flush();
  ok("B quay lại ngay (<15 giây) -> không gọi lại", t.count("queue.list") === n2);
  t.ctl.destroy(); t.w.close();

  /* ---------- B rò rỉ khi chuyển màn 20 lần */
  t = setup({ noRender: true });
  const baseL = t.docL.size, baseI = t.live.size;
  for (let i = 0; i < 20; i++) { const k = t.mk(); await flush(); k.destroy(); t.c.innerHTML = "<p>màn khác</p>"; }
  ok("B 20 lần mở/đóng màn: 0 listener document còn sót, 0 setInterval còn chạy", t.docL.size === baseL && t.live.size === baseI, "listeners=" + (t.docL.size - baseL) + " intervals=" + (t.live.size - baseI));
  const k2 = t.mk(); await flush(); t.c.innerHTML = "<p>host thay nội dung, không gọi destroy</p>";
  t.w.document.body.dispatchEvent(new t.w.KeyboardEvent("keydown", { key: "j", bubbles: true }));
  ok("B host thay nội dung không gọi destroy: phím đầu tiên tự dọn (listener + timer)", t.docL.size === baseL && t.live.size === baseI && k2._state.dead);
  t.w.close();

  /* ---------- B focus sau thao tác */
  let asks = [{ request: "R-1", task: "T-R1", subject: "Việc chờ nhận 1", from_name: "Trọng" }, { request: "R-2", task: "T-R2", subject: "Việc chờ nhận 2", from_name: "Trọng" }];
  t = setup({ h: { "queue.list": a => pack(a.tab, meRows(), { asks: a.tab === "me" ? asks : [] }), "assignment.respond": a => { asks = asks.filter(x => x.request !== a.name); return { ok: 1 }; } } }); await flush();
  const acc = t.$('[data-act="ask-accept"][data-req="R-1"]');
  acc.focus(); acc.click(); await flush();
  ok("B Nhận việc xong (dòng biến mất) -> focus sang nút Nhận việc kế tiếp, không rơi ra <body>", t.w.document.activeElement === t.$('[data-act="ask-accept"][data-req="R-2"]'), (t.w.document.activeElement || {}).outerHTML);
  /* hotfix 23 (sửa): chip lọc nhóm -> ô dải tuần (T7 14/11) */
  const chip = t.$('[data-wk="d:2026-11-14"]'); chip.focus(); chip.click(); await flush();
  ok("B bấm ô dải tuần -> focus vẫn ở ô đó sau khi vẽ lại", t.w.document.activeElement === t.$('[data-wk="d:2026-11-14"]'));
  t.ctl.destroy(); t.w.close();

  /* ---------- B khả năng tiếp cận */
  t = setup(); await flush();
  t.$('[data-act="wait"]').click(); await flush();
  const unnamed = t.$$("[data-pmq] button").filter(b => !(b.textContent.trim() || b.getAttribute("aria-label") || b.getAttribute("title")));
  ok("B mọi nút có tên đọc được (chữ / aria-label / title)", unnamed.length === 0, unnamed.map(b => b.outerHTML.slice(0, 80)).join(" | "));
  const ids = t.$$("[data-pmq] [id]").map(x => x.id), dup = ids.filter((x, i) => ids.indexOf(x) !== i);
  ok("B không trùng id", dup.length === 0, dup.join(","));
  const refs = t.$$("[data-pmq] [aria-controls]").map(x => x.getAttribute("aria-controls")).filter(id => !t.w.document.getElementById(id));
  ok("B aria-controls trỏ tới phần tử có thật", refs.length === 0, refs.join(","));
  ok("B danh sách chờ duyệt có role=list + tiêu đề nhóm (aria-labelledby)", t.$(".pmq-g--wait .pmq-rows").getAttribute("role") === "list" && !!t.w.document.getElementById(t.$(".pmq-g--wait").getAttribute("aria-labelledby")));
  ok("B CSS nhóm chờ duyệt: vùng bấm ≥32px, màu chữ token xám đậm (AA)", /\.pmq-wait-t\{[^}]*min-height:32px/.test(CSS) && /\.pmq-st--wait\{color:var\(--q-g600\)/.test(CSS));
  t.ctl.destroy(); t.w.close();

  /* ---------- B dữ liệu bẩn tới client */
  t = setup({ h: { "queue.list": a => pack(a.tab, [row({ name: "X-1", subject: null, priority: "Siêu gấp", due: "16/10/2026", bucket: "none" }),
    row({ name: "X-2", subject: "<b>đậm</b>", priority: "", assignees: null, giver_name: null, giver: null, progress: { done: "x", total: null } })]) } }); await flush();
  ok("B việc không tiêu đề -> hiện mã việc; ưu tiên lạ -> 'Bình thường'; ngày sai -> 'Chưa có hạn'",
    /X-1/.test(t.rowEl("X-1").querySelector(".pmq-open").textContent) && /Bình thường/.test(t.rowEl("X-1").textContent) && /Chưa có hạn/.test(t.rowEl("X-1").textContent));
  ok("B tiêu đề có HTML được esc, người giao rỗng -> '—', progress hỏng không vẽ '0/0'", !t.rowEl("X-2").querySelector("b.x") && /<b>đậm<\/b>/.test(t.rowEl("X-2").querySelector(".pmq-open").textContent) && !/\/0 người xong|NaN/.test(t.rowEl("X-2").textContent));
  t.ctl.destroy(); t.w.close();

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || r.x === undefined ? "" : "  -> " + r.x)); });
  console.log((res.length - fail) + "/" + res.length + " passed");
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
