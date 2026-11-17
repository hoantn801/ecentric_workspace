/* pm_queue_hf16_qa.test.js (QA tester 17/11, harness chép từ pm_queue_hf16.test.js) — mỗi check mô tả hành vi ĐÚNG; FAIL = lỗi còn.
 * Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue_hf16_qa.test.js (PMQ_JS / PMQ_CSS: thử một bản pm_queue.js / .css khác)
 * (gốc) pm_queue_hf16.test.js — hotfix 16 (PO 17/11/2026). Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue_hf16.test.js
 * H1 Tồn đọng: một dòng thu gọn trên đầu, không vào số đếm / J,K khi đóng; mở ra chọn nhiều -> Dời hạn / Bỏ hạn (bấm 2 lần) / Xong
 *    (bấm 2 lần) = queue_actions.bulk; việc người khác giao không tính vào dời / bỏ hạn (ghi chú), server bỏ qua thì toast nói rõ.
 * H2 3 tab: Tôi theo dõi (tab=follow) chỉ xem — không Xong / Bắt đầu / Nhắc, người giao ở dòng phụ.
 * H3 cột gọn: ưu tiên Bình thường trống, Tự ghi trống, người giao hệ thống = "Hệ thống" + không Xin dời hạn, không chữ "Thao tác".
 * H4 trạng thái một cách: vòng tròn không còn kiểu "đang làm" (nửa tô), chữ Đang làm ở dòng phụ.
 * H5 ô giao việc gọn: gợi ý chỉ khi ở trong ô và < 3 lần dùng; focusQa() cho nút menu.
 * H6 ngăn chi tiết: mô tả sửa tại chỗ (chỉ mô tả thường), các bước tích được, việc con, 3 bình luận + gửi (Ctrl+Enter),
 *    tự làm mới không xoá chữ đang gõ.
 * H7 Phòng họp: nút "+ Đặt phòng" luôn chữ trắng. */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..");
const JS = fs.readFileSync(process.env.PMQ_JS || path.join(ROOT, "js", "pm", "pm_queue.js"), "utf8");
const CSS = fs.readFileSync(process.env.PMQ_CSS || path.join(ROOT, "css", "pm", "pm_queue.css"), "utf8");
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
  if (o.mobile) w.matchMedia = q => ({ matches: /max-width:\s*640px/.test(q), addListener() {}, removeListener() {} });
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

const defer = () => { let res, rej; const p = new Promise((a, b) => { res = a; rej = b; }); return { p, res, rej }; };
const stdTask = name => ({ task: { name, description: name === "M-2" ? "<p>Có <b>đậm</b></p>" : "<p>Mô tả " + name + "</p>", can_edit: 1,
  pm_checklist: [{ name: "C1", item_label: "Lấy số", is_required: 1, is_done: 0 }, { name: "C2", item_label: "Gửi sếp", is_required: 0, is_done: 1 }] }, subtasks: [], user_names: {} });
const typeIn = (t, el, v) => { el.value = v; el.dispatchEvent(new t.w.Event("input", { bubbles: true })); };
const ctrlEnter = (t, el) => el.dispatchEvent(new t.w.KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true, cancelable: true }));

(async () => {
  let t;
  /* B1 */
  t = setup(); await flush();
  t.$('[data-k="old:go"]').click(); await flush();
  const dueS1 = t.rowEl("S-1").querySelector(".pmq-due b").textContent;
  ok("B1 🔴 dòng Tồn đọng (hạn 26/07, hôm nay 17/11) phải ghi 'Trễ 114 ngày', không phải 'Còn 1 ngày'", /Trễ 114 ngày/.test(dueS1), "thấy: " + dueS1);
  t.rowEl("S-1").querySelector(".pmq-open").click(); await flush();
  const dueDr = t.$("[data-drawer] .pmq-due b").textContent;
  ok("B1 🔴 ngăn chi tiết việc tồn đọng: hạn cũng phải 'Trễ … ngày'", /Trễ/.test(dueDr), "thấy: " + dueDr);
  t.ctl.destroy(); t.w.close();

  /* B2 bấm đúp = xác nhận luôn */
  for (const act of ["bulk-clear", "bulk-done"]) {
    t = setup(); await flush();
    t.$('[data-k="old:go"]').click(); await flush();
    t.check(t.$("[data-pick-all]"), true); await flush();
    t.$(`[data-act="${act}"]`).click(); t.$(`[data-act="${act}"]`).click();   /* double-click = 2 click liền nhau */
    await flush();
    ok(`B2 🔴 bấm ĐÚP '${act}' không được coi là đã xác nhận (không có Hoàn tác cho cả loạt)`, t.count("queue_actions.bulk") === 0, "đã gọi bulk " + t.count("queue_actions.bulk") + " lần, action=" + (t.last("queue_actions.bulk") || { a: {} }).a.action);
    t.ctl.destroy(); t.w.close();
  }
  /* B2b hẹn giờ 4 giây cũ gỡ mất lần hỏi lại mới */
  t = setup(); await flush();
  t.$('[data-k="old:go"]').click(); await flush();
  t.check(t.$("[data-pick-all]"), true); await flush();
  t.$('[data-act="bulk-clear"]').click(); await flush();
  await tick(3000);
  t.check(t.$('[data-pick="S-1"]'), false); await flush(); t.check(t.$('[data-pick="S-1"]'), true); await flush();
  await tick(700);
  t.$('[data-act="bulk-clear"]').click(); await flush();
  await tick(500);
  ok("B2b 🟢 hỏi lại lần 2 (sau khi đổi chọn) còn hiệu lực ~4 giây, không bị hẹn giờ của lần trước gỡ sau 0,3 giây", /Bỏ hạn \d+ việc\?/.test(t.$('[data-act="bulk-clear"]').textContent), "nút: " + t.$('[data-act="bulk-clear"]').textContent);
  t.ctl.destroy(); t.w.close();

  /* B3 thu gọn Tồn đọng khi đang chọn một dòng tồn đọng -> X đánh dấu xong việc đang ẩn */
  t = setup({ h: { "tasks.mark_done": () => ({ state: "Done" }) } }); await flush();
  t.$('[data-k="old:go"]').click(); await flush();
  t.key("j"); await flush();
  const selName = (t.$(".pmq-row--sel") || { getAttribute: () => "" }).getAttribute("data-name");
  t.$('[data-k="old"]').click(); await flush();
  t.key("x"); await flush();
  ok("B3 🔴 thu gọn Tồn đọng rồi bấm X: KHÔNG được đánh dấu xong việc tồn đọng đang ẩn (" + selName + ")", t.count("tasks.mark_done") === 0, "mark_done(" + ((t.last("tasks.mark_done") || { a: {} }).a.name) + ")");
  t.ctl.destroy(); t.w.close();

  /* B4 ngăn chi tiết cache vĩnh viễn -> sửa mô tả ghi đè bản mới hơn */
  let ver = 1;
  t = setup({ h: { "tasks.get": a => { const r = stdTask(a.name); if (a.name === "M-1") r.task.description = "<p>Bản " + ver + "</p>"; return r; } } }); await flush();
  t.rowEl("M-1").querySelector(".pmq-open").click(); await flush();
  t.$('[data-act="close"]').click(); await flush();
  ver = 2;   /* người dùng sửa mô tả ở "Mở đầy đủ" (PMR) -> màn đó phát pmr:changed */
  t.w.document.dispatchEvent(new t.w.CustomEvent("pmr:changed", { detail: { source: "pmr", task: "M-1" } }));
  await tick(400); await flush();
  t.rowEl("M-1").querySelector(".pmq-open").click(); await flush();
  t.$('[data-act="desc-edit"]').click(); await flush();
  const deVal = t.$("[data-desc]").value;
  ok("B4 🟡 mở lại ngăn sau khi mô tả đổi ở chỗ khác: ô sửa phải là 'Bản 2' (không thì Lưu ghi đè mất bản mới)", deVal === "Bản 2", "ô sửa có: " + JSON.stringify(deVal) + ", tasks.get gọi " + t.count("tasks.get") + " lần");
  t.ctl.destroy(); t.w.close();

  /* B5 lưu mô tả trả về muộn khi đã sang việc khác */
  let upd = defer();
  t = setup({ h: { "tasks.get": a => stdTask(a.name), "tasks.update": () => upd.p } }); await flush();
  t.rowEl("M-1").querySelector(".pmq-open").click(); await flush();
  t.$('[data-act="desc-edit"]').click(); await flush();
  typeIn(t, t.$("[data-desc]"), "Mô tả M-1 mới"); ctrlEnter(t, t.$("[data-desc]")); await flush();
  t.rowEl("M-3").querySelector(".pmq-open").click(); await flush();
  t.$('[data-act="desc-edit"]').click(); await flush();
  t.$("[data-desc]").focus(); typeIn(t, t.$("[data-desc]"), "Đang gõ cho M-3");
  upd.res({ name: "M-1" }); await flush();
  const de3 = t.$("[data-desc]");
  ok("B5 🟡 lưu mô tả M-1 trả về muộn: KHÔNG xoá ô đang sửa mô tả của M-3 (mất chữ)", !!de3 && de3.value === "Đang gõ cho M-3", de3 ? "ô có: " + de3.value : "ô sửa M-3 đã biến mất");
  ok("B5 🟡 … và không cướp focus khỏi ô đang gõ", !!de3 && t.w.document.activeElement === de3, "focus ở: " + (t.w.document.activeElement && (t.w.document.activeElement.getAttribute("data-k") || t.w.document.activeElement.tagName)));
  t.ctl.destroy(); t.w.close();
  /* B5b gửi bình luận M-1 trả về muộn khi đang gõ bình luận M-3 */
  let add = defer();
  t = setup({ h: { "tasks.get": a => stdTask(a.name), "comments.add": () => add.p } }); await flush();
  t.rowEl("M-1").querySelector(".pmq-open").click(); await flush();
  typeIn(t, t.$("[data-cm]"), "BL cho M-1"); ctrlEnter(t, t.$("[data-cm]")); await flush();
  t.rowEl("M-3").querySelector(".pmq-open").click(); await flush();
  t.$('[data-act="desc-edit"]').click(); await flush();
  t.$("[data-desc]").focus(); typeIn(t, t.$("[data-desc]"), "Gõ dở M-3");
  add.res({ name: "CMX", content: "<p>BL cho M-1</p>", owner: ME, creation: "2026-11-17 09:40:00" }); await flush();
  ok("B5b 🟡 gửi bình luận M-1 xong muộn: focus vẫn ở ô mô tả M-3 đang gõ", t.w.document.activeElement === t.$("[data-desc]"), "focus ở: " + (t.w.document.activeElement && (t.w.document.activeElement.getAttribute("data-k") || t.w.document.activeElement.tagName)));
  t.ctl.destroy(); t.w.close();

  /* B6 mobile: ô chọn từng việc tồn đọng bị ẩn */
  const media = (CSS.match(/@media \(max-width:640px\)\{([\s\S]*?)\n\}/) || [])[1] || "";
  const hidesRk = /\.pmq-row \.pmq-rk[^{]*\{[^}]*display:none/.test(media);
  const showsOld = /\.pmq-row--old \.pmq-rk[^{]*\{[^}]*display:(grid|flex|block|inline)/.test(media);
  ok("B6 🟡 ≤640px: '.pmq-row .pmq-rk{display:none}' ẩn luôn ô chọn của dòng Tồn đọng -> chỉ còn 'Chọn tất cả' (bấm dòng = mở việc)", !hidesRk || showsOld, "media ẩn .pmq-rk, không có luật hiện lại cho .pmq-row--old");
  /* B7 dời hạn xong nhưng làm mới lỗi -> thanh xử lý kẹt "Đang dời…" */
  let failList = false;
  t = setup({ h: { "queue.list": a => { if (failList) throw new Error("mạng chập chờn"); return a.tab === "give" ? pack("give", []) : (a.tab === "follow" ? pack("follow", []) : pack("me", meRows())); },
    "queue_actions.bulk": a => { failList = true; return { action: a.action, ok: JSON.parse(a.names), states: {}, skipped: [] }; } } }); await flush();
  t.$('[data-k="old:go"]').click(); await flush();
  t.check(t.$('[data-pick="S-1"]'), true); await flush();
  t.$('[data-act="bulk-move"]').click(); await flush();
  const mvBtn = t.$('[data-act="bulk-move"]');
  ok("B7 🟡 dời hạn thành công + làm mới lỗi: nút không còn kẹt 'Đang dời…' / disabled, ô chọn không khoá", mvBtn && !/Đang dời/.test(mvBtn.textContent) && !t.$("[data-pick-all]").disabled, "nút: " + (mvBtn && mvBtn.textContent) + ", pick-all disabled=" + t.$("[data-pick-all]").disabled);
  t.ctl.destroy(); t.w.close();

  /* B8 rơi focus */
  t = setup(); await flush();
  t.$('[data-k="old:go"]').click(); await flush();
  t.$("[data-pick-all]").focus(); t.check(t.$("[data-pick-all]"), true); await flush();
  ok("B8 🟡 Space trên 'Chọn tất cả': focus phải ở lại ô đó (không rơi ra <body>)", t.w.document.activeElement === t.$("[data-pick-all]"), "focus ở: " + t.w.document.activeElement.tagName);
  t.$("[data-bulk-due]").focus();
  t.check(t.$('[data-pick="S-2"]'), false);   /* đổi chọn bằng chuột khi con trỏ đang ở ô ngày (hoặc tự làm mới / hẹn giờ 4s vẽ lại) */
  t.$("[data-bulk-due]").focus(); t.ctl.refresh(); await flush();
  ok("B8 🟡 đang ở ô 'Hạn mới' mà danh sách vẽ lại (làm mới): focus ở lại ô ngày", t.w.document.activeElement === t.$("[data-bulk-due]"), "focus ở: " + t.w.document.activeElement.tagName);
  t.ctl.destroy(); t.w.close();
  let setp = defer();
  t = setup({ h: { "tasks.get": a => stdTask(a.name), "checklist.set_item": () => setp.p } }); await flush();
  t.rowEl("M-1").querySelector(".pmq-open").click(); await flush();
  const c1 = t.$('[data-step="C1"]'); c1.focus(); t.check(c1, true); await flush();
  setp.res({ rows: [{ name: "C1", item_label: "Lấy số", is_required: 1, is_done: 1 }, { name: "C2", item_label: "Gửi sếp", is_required: 0, is_done: 1 }] }); await flush();
  const ae = t.w.document.activeElement;
  ok("B8 🟡 tích bước bằng bàn phím: lưu xong focus về lại đúng ô bước (không rơi ra <body>)", ae && ae.getAttribute("data-step") === "C1", "focus ở: " + (ae && (ae.getAttribute("data-k") || ae.tagName)));
  t.ctl.destroy(); t.w.close();

  /* B9 tab giao: số "chưa mở / chờ nhận" tính cả tồn đọng, lệch với tổng + chip lọc */
  t = setup({ tab: "give", h: { "queue.list": a => a.tab !== "give" ? pack(a.tab, []) : pack("give", [
    row({ name: "G-1", subject: "Việc mới", due: "2026-11-18", bucket: "tomorrow", giver: ME, giver_name: "", assignees: [{ user: "lan@ecentric.vn", name: "Lan", opened: true }] }),
    row({ name: "G-2", subject: "Cũ 1", due: "2026-08-01", bucket: "stale", giver: ME, unopened: true, assignees: [{ user: "lan@ecentric.vn", name: "Lan", opened: false }] }),
    row({ name: "G-3", subject: "Cũ 2", due: "2026-08-02", bucket: "stale", giver: ME, unopened: true, assignees: [{ user: "phu@ecentric.vn", name: "Phú", opened: false }] }),
    row({ name: "G-4", subject: "Cũ 3", due: "2026-08-03", bucket: "stale", giver: ME, awaiting: 1, assignees: [{ user: "phu@ecentric.vn", name: "Phú", opened: false, pending: 1 }] })]) } }); await flush();
  const subG = t.$("[data-sub]").textContent;
  ok("B9 🟡 tab giao: '1 việc còn mở' mà tóm tắt lại ghi '2 việc người nhận chưa mở, 1 chờ nhận' (đếm cả tồn đọng; chip 'Chưa mở việc' = 0)", !/chưa mở|chờ nhận/.test(subG.replace(/tồn đọng.*/, "")), "tóm tắt: " + subG);
  t.ctl.destroy(); t.w.close();

  /* B10 đang gõ bình luận, việc rời danh sách (người khác đóng) -> ngăn đóng, mất chữ */
  let gone = false;
  t = setup({ h: { "tasks.get": a => stdTask(a.name), "queue.list": a => a.tab !== "me" ? pack(a.tab, []) : pack("me", meRows().filter(r => !(gone && r.name === "M-1"))) } }); await flush();
  t.rowEl("M-1").querySelector(".pmq-open").click(); await flush();
  t.$("[data-cm]").focus(); typeIn(t, t.$("[data-cm]"), "Em gửi file rồi ạ, anh xem giúp");
  gone = true; t.ctl.refresh(); await flush();
  const cmEl = t.$("[data-cm]");
  ok("B10 🟡 đang gõ bình luận mà việc rời hàng đợi: ngăn không bị đóng dưới tay, chữ còn", !!cmEl && cmEl.value === "Em gửi file rồi ạ, anh xem giúp", cmEl ? cmEl.value : "ngăn đã đóng, chữ mất");
  t.ctl.destroy(); t.w.close();

  /* B11 chữ hướng dẫn sai tab */
  t = setup({ tab: "follow", h: { "queue.list": a => a.tab !== "follow" ? pack(a.tab, []) : pack("follow", [row({ name: "F-9", subject: "Theo dõi cũ", due: "2026-07-01", bucket: "stale" })]) } }); await flush();
  const lf = t.$("[data-list]").textContent;
  ok("B11 🟢 tab Tôi theo dõi chỉ có tồn đọng: không mời 'dời hạn, bỏ hạn hoặc đánh dấu xong' (không có thao tác nào)", !/đánh dấu xong|dời hạn/.test(lf.replace(/Tồn đọng.*?Người nhận chưa đóng\./, "")), "list: " + lf.slice(0, 160));
  t.ctl.destroy(); t.w.close();
  t = setup({ tab: "give", h: { "queue.list": a => a.tab !== "give" ? pack(a.tab, []) : pack("give", [row({ name: "G-9", subject: "Giao cũ", due: "2026-07-01", bucket: "stale", giver: ME })]) } }); await flush();
  ok("B11 🟢 tab Việc tôi giao: dòng Tồn đọng không hứa 'đánh dấu xong' (chỉ tab tôi làm có)", !/đánh dấu xong/.test(t.$(".pmq-g--old").textContent + t.$("[data-list]").textContent), t.$(".pmq-old-h small").textContent);
  t.ctl.destroy(); t.w.close();

  /* B12 ngày quá khứ / xoá trống bị thay im lặng bằng +7 */
  t = setup(); await flush();
  t.$('[data-k="old:go"]').click(); await flush();
  t.check(t.$('[data-pick="S-1"]'), true); await flush();
  const di = t.$("[data-bulk-due]"); di.value = "2026-11-10"; di.dispatchEvent(new t.w.Event("change", { bubbles: true }));
  t.$('[data-act="bulk-move"]').click(); await flush();
  const mv = t.last("queue_actions.bulk");
  ok("B12 🟢 gõ ngày đã qua (10/11): không âm thầm dời sang +7 (24/11) — báo chọn lại ngày", !mv || mv.a.due !== "2026-11-24", "bulk(due=" + (mv && mv.a.due) + ")");
  t.ctl.destroy(); t.w.close();

  /* B14 mô tả p/div có class/style (Quill căn giữa, thụt lề) vẫn bị coi là "thuần" */
  t = setup({ h: { "tasks.get": a => { const r = stdTask(a.name); r.task.description = '<p class="ql-align-center">Tiêu đề giữa</p><p class="ql-indent-1">Ý thụt lề</p><p style="color:#e00">Chữ đỏ</p>'; return r; } } }); await flush();
  t.rowEl("M-1").querySelector(".pmq-open").click(); await flush();
  ok("B14 🟢 mô tả có căn giữa / thụt lề / màu: không cho sửa tại chỗ (lưu sẽ mất định dạng)", !t.$('[data-act="desc-edit"]'), "vẫn có nút Sửa tại chỗ");
  t.ctl.destroy(); t.w.close();

  /* B15 thu gọn khi đang gửi -> bấm lại gửi trùng */
  let bk = defer();
  t = setup({ h: { "queue_actions.bulk": () => bk.p } }); await flush();
  t.$('[data-k="old:go"]').click(); await flush();
  t.check(t.$('[data-pick="S-1"]'), true); await flush();
  t.$('[data-act="bulk-move"]').click(); await flush();
  t.$('[data-k="old"]').click(); await flush(); t.$('[data-k="old:go"]').click(); await flush();
  t.check(t.$('[data-pick="S-1"]'), true); await flush();
  const mb = t.$('[data-act="bulk-move"]'); if (mb && !mb.disabled) mb.click(); await flush();
  ok("B15 🟢 đang dời hạn mà thu gọn / mở lại Tồn đọng: không gửi bulk lần 2 trùng việc", t.count("queue_actions.bulk") === 1, "bulk gọi " + t.count("queue_actions.bulk") + " lần");
  bk.res({ ok: ["S-1"], states: {}, skipped: [] }); await flush();
  t.ctl.destroy(); t.w.close();

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
