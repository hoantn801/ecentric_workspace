/* pm_queue_hf16.test.js — hotfix 16 (PO 17/11/2026). Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue_hf16.test.js
 * H1 Tồn đọng: một dòng thu gọn trên đầu, không vào số đếm / J,K khi đóng; mở ra chọn nhiều -> Dời hạn / Bỏ hạn (bấm 2 lần) / Xong
 *    (bấm 2 lần) = queue_actions.bulk; việc người khác giao không tính vào dời / bỏ hạn (ghi chú), server bỏ qua thì toast nói rõ.
 * H2 3 tab: Tôi theo dõi (tab=follow) chỉ xem — không Xong / Bắt đầu / Nhắc, người giao ở dòng phụ.
 * H3 cột gọn: ưu tiên Bình thường trống, Tự ghi trống, người giao hệ thống = "Hệ thống" + không Xin dời hạn, không chữ "Thao tác".
 * H4 trạng thái một cách: vòng tròn không còn kiểu "đang làm" (nửa tô), chữ Đang làm ở dòng phụ.
 * H5 ô giao việc gọn: gợi ý chỉ khi ở trong ô và < 3 lần dùng; focusQa() cho nút menu.
 * H6 (hotfix 23 thay ngăn chi tiết): bấm dòng -> cửa sổ chung openTask(name, {nav}); mô tả / bước / việc con / bình luận / đổi tên
 *    do cửa sổ PMR lo, hàng đợi không còn tự gọi tasks.get / comments / checklist / tasks.update.
 * H7 Phòng họp: nút "+ Đặt phòng" luôn chữ trắng. */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_queue.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "css", "pm", "pm_queue.css"), "utf8");
const RMCSS = fs.readFileSync(path.join(ROOT, "css", "pm", "pm_rooms.css"), "utf8");
const PMRJS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_redesign.js"), "utf8");
const res = [];
const ok = (n, c, x) => res.push({ n, c: !!c, x });
const tick = ms => new Promise(r => setTimeout(r, ms || 0));
const flush = async () => { for (let i = 0; i < 8; i++) await tick(0); };
const ME = "hoan@ecentric.vn", TODAY = "2026-11-17", NOW = "09:30";   /* T3 17/11/2026 */
const BUCKETS = [{ key: "late", label: "Quá hạn" }, { key: "today", label: "Hôm nay" }, { key: "tomorrow", label: "Ngày mai" }, { key: "week", label: "Còn lại tuần này" },
  { key: "later", label: "Tuần sau trở đi" }, { key: "none", label: "Chưa có hạn" }, { key: "stale", label: "Tồn đọng" }];
const row = o => Object.assign({ workflow_state: "To Do", project: "", project_name: "", priority: "Medium", due: null, due_time: null, giver: "huyen@ecentric.vn",
  giver_name: "Nguyễn Khánh Huyền", giver_system: 0, self: false, assignees: [{ user: ME, name: "Trần Hoàn", opened: true }], unopened: false, group: 0, review: 0 }, o);
function pack(tab, rows, extra) {
  rows.forEach((r, i) => { r.rank = i + 1; });
  const counts = {}; BUCKETS.forEach(b => { counts[b.key] = rows.filter(r => r.bucket === b.key).length; });
  return Object.assign({ today: TODAY, now: NOW, tab, rows, counts, buckets: BUCKETS, asks: [], personal_hidden: 0, waiting: [], proposals: [] }, extra || {});
}
const meRows = () => [
  row({ name: "M-1", subject: "Chốt GMV tuần", priority: "High", due: "2026-11-16", bucket: "late", workflow_state: "In Progress" }),
  row({ name: "M-2", subject: "Gọi brand", due: TODAY, bucket: "today", self: true, giver: ME, giver_name: "" }),
  row({ name: "M-3", subject: "Việc nhập từ hệ thống", due: "2026-11-20", bucket: "week", giver: "Administrator", giver_name: "Hệ thống", giver_system: 1 }),
  row({ name: "S-1", subject: "Update MSO workflow", priority: "High", due: "2026-07-26", bucket: "stale", self: true, giver: ME, giver_name: "" }),
  row({ name: "S-2", subject: "Testing flow", due: "2026-07-31", bucket: "stale", giver: "Administrator", giver_name: "Hệ thống", giver_system: 1 }),
  row({ name: "S-3", subject: "Approval center", due: "2026-07-31", bucket: "stale" })];
const followRows = () => [row({ name: "F-1", subject: "Theo dõi việc kho", due: "2026-11-18", bucket: "tomorrow", giver: "phu@ecentric.vn", giver_name: "Phú",
  assignees: [{ user: "lan@ecentric.vn", name: "Lan", opened: true }] })];

function setup(o) {
  o = o || {};
  const dom = new JSDOM("<!doctype html><body><div id=v></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#mywork", pretendToBeVisual: true });
  const w = dom.window, calls = [], opened = [], events = [], intervals = [];
  w.fetch = () => Promise.reject(new Error("no network"));
  const si = w.setInterval.bind(w);
  w.setInterval = (fn, ms) => { const id = si(fn, ms); intervals.push({ id, fn, ms }); return id; };
  if (o.uses != null) w.localStorage.setItem("pmq.qaUses", String(o.uses));
  w.eval(PMRJS);
  w.eval(JS);
  ["pmr:changed", "pmr:badge"].forEach(n => w.document.addEventListener(n, e => events.push({ n, d: e.detail })));
  const H = Object.assign({
    "queue.list": a => (a.tab === "follow" ? pack("follow", followRows()) : (a.tab === "give" ? pack("give", []) : pack("me", meRows(), { asks: [{ request: "R1", task: "T-R", subject: "Nhận việc kho" }] }))),
    "queue_actions.bulk": a => ({ action: a.action, ok: JSON.parse(a.names).filter(n => n !== "S-3"), states: {}, skipped: JSON.parse(a.names).includes("S-3") ? [{ name: "S-3", reason: "others" }] : [] }),
    "tasks.get": a => ({ task: { name: a.name, description: a.name === "M-1" ? "<div class=\"ql-editor\"><p>Dòng một</p><p>Dòng hai</p></div>" : "<p>Có <b>đậm</b></p>", can_edit: 1,
      pm_checklist: [{ name: "C1", item_label: "Lấy số", is_required: 1, is_done: 0 }, { name: "C2", item_label: "Gửi sếp", is_required: 0, is_done: 1 }] },
      subtasks: [{ name: "SUB-1", subject: "Phần của Lan", workflow_state: "Done", _assign: '["lan@ecentric.vn"]' }, { name: "SUB-2", subject: "Phần của Phú", workflow_state: "In Progress", _assign: '["phu@ecentric.vn"]' }],
      user_names: { "lan@ecentric.vn": "Lan", "phu@ecentric.vn": "Phú" } }),
    "comments.list": () => ({ rows: [1, 2, 3, 4].map(i => ({ name: "CM" + i, content: "<p>Bình luận " + i + "</p>", owner: i === 4 ? ME : "lan@ecentric.vn", creation: "2026-11-1" + i + " 08:0" + i + ":00", pinned: 0 })) }),
    "comments.add": a => ({ name: "CM9", content: a.content, owner: ME, creation: "2026-11-17 09:31:00" }),
    "tasks.update": () => ({ name: "M-1", changed: ["description"] }),
    "checklist.set_item": a => ({ rows: [{ name: "C1", item_label: "Lấy số", is_required: 1, is_done: +a.is_done }, { name: "C2", item_label: "Gửi sếp", is_required: 0, is_done: 1 }] }),
    "assignment.list_assignable": () => ({ rows: [{ email: ME, full_name: "Trần Hoàn" }, { email: "lan@ecentric.vn", full_name: "Lan" }] })
  }, o.h || {});
  const api = (method, args) => {
    const m = method.replace("ecentric_workspace.pm.api.", "");
    calls.push({ m, a: args });
    const fn = H[m];
    if (!fn) return Promise.reject(new Error("no " + m));
    try { return Promise.resolve(fn(args || {})); } catch (e) { return Promise.reject(e); }
  };
  const c = w.document.getElementById("v");
  const ctl = w.PMQueue.render(c, { api, user: ME, tab: o.tab || "me", openTask: (n, oo) => opened.push([n, oo || null]),
    head: (t, s, r) => `<div class="pm-head"><div><h1>${t}</h1><div class="sub">${s}</div></div><div>${r || ""}</div></div>` });
  const $ = s => w.document.querySelector(s), $$ = s => Array.from(w.document.querySelectorAll(s));
  const count = m => calls.filter(x => x.m === m).length;
  const last = m => calls.filter(x => x.m === m).slice(-1)[0];
  const toast = () => ($(".pmq-toast [data-tm]") || {}).textContent || "";
  const rowEl = n => $(`.pmq-row[data-name="${n}"]`);
  const key = (k, x) => w.document.body.dispatchEvent(new w.KeyboardEvent("keydown", Object.assign({ key: k, bubbles: true, cancelable: true }, x || {})));
  const check = (el, v) => { el.checked = v; el.dispatchEvent(new w.Event("change", { bubbles: true })); };
  return { w, ctl, calls, opened, events, intervals, $, $$, count, last, toast, rowEl, key, check };
}

(async () => {
  /* ---------- H1 Tồn đọng */
  let t = setup(); await flush();
  ok("H1 Tồn đọng thu gọn: không có dòng S-* trên màn, có một dòng 'Tồn đọng (3)' + nút Xem và dọn", !t.rowEl("S-1") && /Tồn đọng\s*3/.test(t.$(".pmq-g--old").textContent) && !!t.$('[data-k="old:go"]'));
  ok("H1 Tồn đọng nằm TRÊN nhóm Quá hạn", (() => { const a = t.$(".pmq-g--old"), b = t.$(".pmq-g--late"); return a && b && (a.compareDocumentPosition(b) & 4); })());
  /* hotfix 23 (sửa): "Tất cả N" (hàng nút lọc) đã bỏ -> tổng số trên dải tuần cũng không tính tồn đọng */
  const wkSum = () => t.$$(".pmq-wk-n").reduce((a, x) => a + parseInt(x.textContent, 10), 0);
  ok("H1 số đếm không tính tồn đọng: tab 3, tổng dải tuần 3, tóm tắt có '3 tồn đọng'", t.$('[data-c="me"]').textContent === "3" && wkSum() === 3 && /3 tồn đọng/.test(t.$("[data-sub]").textContent) && !t.$('[data-wk="stale"]'));
  ok("H1 số menu = 3 việc chính + 1 Cần đồng ý = 4", t.events.some(e => e.n === "pmr:badge" && e.d.count === 4));
  t.key("j"); t.key("j"); t.key("j"); t.key("j");
  ok("H1 J/K khi tồn đọng đóng: chỉ đi qua 3 việc chính", t.$(".pmq-row--sel") && t.$(".pmq-row--sel").getAttribute("data-name") === "M-3");
  t.$('[data-k="old:go"]').click(); await flush();
  ok("H1 mở Tồn đọng: 3 dòng có ô chọn, thanh xử lý, ô ngày mặc định +7", t.$$(".pmq-g--old .pmq-row").length === 3 && t.$$(".pmq-pick-c").length === 3 && t.$("[data-bulk-due]").value === "2026-11-24");
  ok("H1 tồn đọng: hạn không tô đỏ (chữ xám), không có số thứ tự", /pmq-row--old/.test(t.rowEl("S-1").className) && !/^\d+$/.test(t.rowEl("S-1").querySelector(".pmq-rk").textContent.trim()));
  ok("H1 chưa chọn gì: Dời hạn / Bỏ hạn / Xong khoá", t.$('[data-act="bulk-move"]').disabled && t.$('[data-act="bulk-clear"]').disabled && t.$('[data-act="bulk-done"]').disabled);
  t.check(t.$("[data-pick-all]"), true); await flush();
  ok("H1 chọn tất cả: 'Đã chọn 3/3' + ghi chú 1 việc người khác giao giữ nguyên hạn", /Đã chọn\s*3\/3/.test(t.$(".pmq-bulk").textContent) && /1 việc người khác giao/.test(t.$(".pmq-bulk-note").textContent));
  const dd = t.$("[data-bulk-due]"); dd.value = "2026-11-30"; dd.dispatchEvent(new t.w.Event("change", { bubbles: true }));
  t.$('[data-act="bulk-move"]').click(); await flush();
  const mv = t.last("queue_actions.bulk");
  ok("H1 Dời hạn: bulk(move) chỉ gửi việc của mình + hệ thống, đúng ngày", mv && mv.a.action === "move" && mv.a.due === "2026-11-30" && JSON.stringify(JSON.parse(mv.a.names).sort()) === '["S-1","S-2"]');
  ok("H1 toast: đã dời 2 việc sang T2 30/11", /Đã dời hạn 2 việc sang T2 30\/11/.test(t.toast()));
  t.check(t.$('[data-pick="S-3"]'), true); await flush();
  t.$('[data-act="bulk-done"]').click(); await flush();
  ok("H1 Xong hàng loạt: lần bấm đầu chỉ hỏi lại ('Xong 1 việc?'), chưa gọi server", t.count("queue_actions.bulk") === 1 && /Xong 1 việc\?/.test(t.$('[data-act="bulk-done"]').textContent));
  await tick(600); t.$('[data-act="bulk-done"]').click(); await flush();
  ok("H1 bấm lần 2 -> bulk(done) gửi cả việc người khác giao (Xong đi đúng đường mark_done)", t.count("queue_actions.bulk") === 2 && t.last("queue_actions.bulk").a.action === "done" && JSON.parse(t.last("queue_actions.bulk").a.names)[0] === "S-3");
  ok("H1 server bỏ qua (others) -> toast nói rõ", /giữ nguyên/.test(t.toast()) || /Chưa xử lý/.test(t.toast()));
  t.key("j");
  ok("H1 mở Tồn đọng: J đi vào cả dòng tồn đọng (thứ tự trên màn)", !!t.$(".pmq-row--sel"));
  t.ctl.destroy(); t.w.close();

  /* ---------- H1b nhiều việc: chia lô 50 (server nhận tối đa 50 / lần), lý do bỏ qua nói thẳng; 2 tab kia không tải lại mỗi phút */
  const many = Array.from({ length: 120 }, (_, i) => row({ name: "X" + i, subject: "Tồn " + i, due: "2026-07-01", bucket: "stale", self: true, giver: ME, giver_name: "" }));
  t = setup({ h: { "queue.list": a => pack(a.tab, a.tab === "me" ? many.map(x => Object.assign({}, x)) : []),
    "queue_actions.bulk": a => { const n = JSON.parse(a.names); return { action: a.action, ok: n.slice(1), states: {}, skipped: [{ name: n[0], reason: "blocked", message: "Còn 1 việc con chưa xong." }] }; } } }); await flush();
  t.$('[data-k="old:go"]').click(); await flush();
  t.check(t.$("[data-pick-all]"), true); await flush();
  t.$('[data-act="bulk-done"]').click(); await flush(); await tick(600);
  t.$('[data-act="bulk-done"]').click(); await flush(); await flush();
  const lots = t.calls.filter(c => c.m === "queue_actions.bulk").map(c => JSON.parse(c.a.names).length);
  ok("H1b chọn 120 việc -> 3 lô 50/50/20", lots.join(",") === "50,50,20", lots.join(","));
  ok("H1b toast: số việc xong + lý do bỏ qua nói thẳng", /Đã xong 117 việc/.test(t.toast()) && /3 việc chưa được: Còn 1 việc con chưa xong\./.test(t.toast()), t.toast());
  const q0 = t.count("queue.list");
  t.intervals.find(x => x.ms === 60000).fn(); await flush();
  ok("H1b tự làm mới 60 giây: chỉ tải tab đang xem (2 tab kia mỗi 5 lần)", t.count("queue.list") - q0 === 1, t.count("queue.list") - q0);
  t.ctl.destroy(); t.w.close();

  /* ---------- H2 Tôi theo dõi */
  t = setup({ tab: "follow" }); await flush();
  ok("H2 3 tab: Việc tôi làm / Việc tôi giao / Tôi theo dõi, gọi queue.list cả 3", t.$$("[data-tab]").map(b => b.getAttribute("data-tab")).join(",") === "me,give,follow" && t.count("queue.list") === 3 && t.calls.some(c => c.m === "queue.list" && c.a.tab === "follow"));
  ok("H2 tab theo dõi: dòng có 'Phú giao', người nhận Lan, vòng Xong khoá, không nút thao tác", /Phú giao/.test(t.rowEl("F-1").textContent) && /Lan/.test(t.rowEl("F-1").querySelector(".pmq-hw").textContent) &&
    t.rowEl("F-1").querySelector(".pmq-chk").disabled && !t.rowEl("F-1").querySelector(".pmq-ac [data-act]"));
  ok("H2 tóm tắt tab theo dõi", /1 việc bạn đang theo dõi/.test(t.$("[data-sub]").textContent));
  t.ctl.destroy(); t.w.close();
  t = setup({ tab: "follow", h: { "queue.list": a => pack(a.tab, []) } }); await flush();
  ok("H2 chưa theo dõi gì: nói rõ CC là gì", /chưa theo dõi việc nào/.test(t.$(".pmq-state").textContent));
  t.ctl.destroy(); t.w.close();
  t = setup({ tab: "give" }); await flush();
  ok("H2 tab giao: đường vào Việc lặp lại / Đã xong (#given/rep, #given/done)", !!t.$('a[href="#given/rep"]') && !!t.$('a[href="#given/done"]'));
  t.ctl.destroy(); t.w.close();

  /* ---------- H3 / H4 cột gọn, trạng thái một cách */
  t = setup(); await flush();
  ok("H3 Bình thường: ô ưu tiên trống (chỉ chữ cho máy đọc), Cao vẫn hiện", !t.rowEl("M-2").querySelector(".pmq-pri") && /Cao/.test(t.rowEl("M-1").querySelector(".pmq-hp").textContent));
  ok("H3 Tự ghi: cột người giao trống", t.rowEl("M-2").querySelector(".pmq-hw").textContent.trim() === "Tự ghi" && !!t.rowEl("M-2").querySelector(".pmq-hw .pmq-vh"));
  ok("H3 hệ thống giao: 'Hệ thống', không nút Xin dời hạn (không ai để xin)", /Hệ thống/.test(t.rowEl("M-3").querySelector(".pmq-hw").textContent) && !t.rowEl("M-3").querySelector('[data-act="ask"]') && !!t.rowEl("M-1").querySelector('[data-act="ask"]'));
  ok("H3 tiêu đề cột không còn chữ 'Thao tác'", !/Thao tác/.test(t.$(".pmq-cols").textContent));
  ok("H4 việc Đang làm: vòng tròn KHÔNG nửa tô, chữ 'Đang làm' ở dòng phụ", !/pmq-chk--doing/.test(t.rowEl("M-1").querySelector(".pmq-chk").className) && /Đang làm/.test(t.rowEl("M-1").querySelector("small").textContent) && !/chk--doing|chk--review/.test(CSS));

  /* ---------- H5 ô giao việc gọn + focusQa */
  ok("H5 chưa bấm vào ô: không có dòng gợi ý", t.$("[data-parse]").classList.contains("pmq-parse--off"));
  t.ctl.focusQa(); await flush();
  ok("H5 focusQa(): con trỏ vào ô giao việc + hiện gợi ý (mới dùng < 3 lần)", t.w.document.activeElement === t.$("[data-qa]") && /Ví dụ/.test(t.$("[data-parse]").textContent));
  t.ctl.destroy(); t.w.close();
  t = setup({ uses: 3 }); await flush();
  t.$("[data-qa]").focus(); await flush();
  ok("H5 đã dùng 3 lần: bấm vào ô cũng không hiện gợi ý", t.$("[data-parse]").classList.contains("pmq-parse--off"));
  t.ctl.destroy(); t.w.close();

  /* ---------- H6 / H8 (hotfix 23, thay ngăn chi tiết): mọi chi tiết đi qua cửa sổ chung của /pm */
  t = setup(); await flush();
  t.rowEl("M-1").querySelector(".pmq-open").click(); await flush();
  const o6 = t.opened.slice(-1)[0];
  ok("H6 bấm tên việc -> openTask('M-1', {nav}) theo thứ tự đang hiện (tồn đọng đóng: 3 việc chính)", o6 && o6[0] === "M-1" && o6[1].nav.names.join(",") === "M-1,M-2,M-3" && typeof o6[1].nav.onMove === "function");
  ok("H6 không còn ngăn .pmq-dr; hàng đợi không tự gọi tasks.get / comments.list / checklist (cửa sổ PMR lo)", !t.$("[data-drawer]") && !t.$(".pmq-dr") && t.count("tasks.get") + t.count("comments.list") + t.count("checklist.set_item") === 0);
  t.rowEl("M-3").querySelector(".pmq-dt").click(); await flush();
  ok("H6 bấm bất kỳ đâu trên dòng (ô hạn) -> mở việc đó", t.opened.slice(-1)[0][0] === "M-3");
  const n6 = t.opened.length;
  t.rowEl("M-1").querySelector('[data-act="done"]').click(); await flush();
  ok("H6 bấm vòng Xong không mở cửa sổ", t.opened.length === n6);
  o6[1].onChange(); await flush();
  ok("H8 cửa sổ báo việc đổi (đổi tên / mô tả) -> hàng đợi làm mới", t.count("queue.list") >= 4);
  t.ctl.destroy(); t.w.close();

  /* ---------- H7 Phòng họp + CSS */
  const rm = RMCSS.replace(/\/\*[\s\S]*?\*\//g, "");
  ok("H7 '+ Đặt phòng': chữ trắng mọi trạng thái, lúc chờ tải không mờ cả nút", /\.pm-head \.pmrm-btn--pri\{[^}]*color:#fff/.test(rm) && /\.pm-head \.pmrm-btn--pri\[disabled\]\{opacity:1;[^}]*color:#fff/.test(rm));
  const css = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
  ok("CSS: chừa chỗ nút trợ lý (padding-bottom), dòng quy tắc không co (flex:none)", /padding-bottom:88px/.test(css) && /\.pmq-rule\{[^}]*flex:none/.test(css));
  ok("CSS mới đều trong namespace .pmq-", css.split("}").map(s => s.split("{")[0].trim()).filter(s => s && !/^@|^(from|to|\d+%)$/.test(s))
    .every(sel => sel.split(",").every(x => /^\s*(\.pmq|:where\(\.pmq\))/.test(x) || /^\s*(input|select|textarea|button|button:disabled)\)?\s*$/.test(x) || /^\s*(from|to|\d+%)\b/.test(x))));
  ok("hotfix 17: ô ngày ec_datepicker (.ec-dp-wrap) trong thanh tồn đọng / form đề xuất hạn không chiếm cả dòng", /\.pmq-af-row \.ec-dp-wrap,\.pmq-bulk \.ec-dp-wrap\{width:auto;flex:0 0 156px\}/.test(css));
  ok("JS: không Jinja, không console.log", !/\{\{|\{%|\{#/.test(JS) && !/console\.log/.test(JS));

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
