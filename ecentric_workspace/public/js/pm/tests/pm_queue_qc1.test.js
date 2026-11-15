/* pm_queue_qc1.test.js — QC round 1 (15/11/2026) màn "Việc cần làm": mỗi lỗi một test tái hiện (fail trước khi sửa).
 * Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue_qc1.test.js
 *  Q1 Chờ duyệt: người giao không duyệt được (tab giao chỉ có "Nhắc"; việc cha chia nhiều người ở Chờ duyệt bị khoá "chờ người giao").
 *  Q2 Giao liên tiếp: ô nhập readOnly lúc đang lưu -> chữ gõ cho việc kế tiếp bị nuốt / bị xoá khi lưu xong.
 *  Q3 Bộ gõ tiếng Việt (IME): Enter/Tab khi đang ghép chữ chọn nhầm người gợi ý / gửi việc.
 *  Q4 F5 / trang cache: ghi qua frappe.call mang CSRF cũ -> dùng ecApi.post (token tươi); đọc lỗi quyền không gọi lại frappe.call.
 *  Q5 Phím S trên dòng vừa Xong mở lại việc.
 *  Q6 Lỗi "yêu cầu không còn mở" / việc đã mất: dòng cũ còn nguyên -> làm mới sau lỗi ghi.
 *  Q7 @email đầy đủ làm bẩn tên việc.
 *  Q8 Số đếm từ server chèn thẳng vào innerHTML.
 *  Q9 Host chưa có user (F5 sớm): "Thêm việc" tạo việc KHÔNG người nhận (mất khỏi hàng đợi). */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_queue.js"), "utf8");
const PMRJS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_redesign.js"), "utf8");
const res = [];
const ok = (n, c, x) => res.push({ n, c: !!c, x });
const tick = ms => new Promise(r => setTimeout(r, ms || 0));
const flush = async () => { for (let i = 0; i < 8; i++) await tick(0); };
const ME = "hoan@ecentric.vn", TODAY = "2026-11-13", NOW = "09:30";
const BUCKETS = [{ key: "late", label: "Quá hạn" }, { key: "today", label: "Hôm nay" }, { key: "tomorrow", label: "Ngày mai" }, { key: "week", label: "Còn lại tuần này" }, { key: "later", label: "Tuần sau trở đi" }, { key: "none", label: "Chưa có hạn" }];
const row = o => Object.assign({ workflow_state: "To Do", project: "", project_name: "", priority: "Medium", due: TODAY, due_time: null, bucket: "today", giver: "huyen@ecentric.vn",
  giver_name: "Huyền", self: false, assignees: [{ user: ME, name: "Trần Hoàn", opened: true }], unopened: false, group: 0, review: 0, parent_task: null }, o);
const pack = (tab, rows, extra) => { rows.forEach((r, i) => { r.rank = i + 1; }); const counts = {}; rows.forEach(r => { counts[r.bucket] = (counts[r.bucket] || 0) + 1; });
  return Object.assign({ today: TODAY, now: NOW, tab, rows, counts, buckets: BUCKETS, asks: [], personal_hidden: 0 }, extra || {}); };
const meRows = () => [row({ name: "T-1", subject: "Việc một" }), row({ name: "T-2", subject: "Việc hai" }),
  row({ name: "T-SP", subject: "Báo cáo tuần (chia 3 người)", workflow_state: "Review", group: 1, self: true, giver: ME, giver_name: "" }),
  row({ name: "T-RV", subject: "Việc tôi đã gửi kiểm tra", workflow_state: "Review", review: 1 })];
const giveRows = () => [row({ name: "G-RV", subject: "Banner 12.12", workflow_state: "Review", giver: ME, giver_name: "", assignees: [{ user: "lan@ecentric.vn", name: "Lan", opened: true }] }),
  row({ name: "G-1", subject: "File tồn kho", giver: ME, giver_name: "", assignees: [{ user: "trong@ecentric.vn", name: "Trọng", opened: false }], unopened: true })];
const PEOPLE = [{ email: ME, full_name: "Trần Hoàn" }, { email: "lan@ecentric.vn", full_name: "Nguyễn Thị Lan" }, { email: "lanh@ecentric.vn", full_name: "Phạm Lành" }, { email: "lan.nguyen@ecentric.vn", full_name: "Nguyễn Lan Anh" }];
const smErr = msg => { const e = new Error("HTTP 417"); e._server_messages = JSON.stringify([JSON.stringify({ message: msg })]); return e; };

function setup(o) {
  o = o || {};
  const dom = new JSDOM("<!doctype html><body><div id=v></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#mywork", pretendToBeVisual: true });
  const w = dom.window, calls = [], opened = [], ecCalls = [];
  w.fetch = () => Promise.reject(new Error("no network"));
  if (o.cookie) w.document.cookie = o.cookie;
  w.eval(PMRJS);
  w.eval(JS);
  const H = Object.assign({
    "queue.list": a => (a.tab === "give" ? pack("give", giveRows()) : pack("me", meRows())),
    "tasks.mark_done": () => ({ state: "Done" }), "tasks.set_status": () => ({ ok: 1 }), "tasks.create": () => ({ name: "T-NEW" }),
    "pm_inbox.close_parent": a => ({ task: a.task, state: "Done", returned: [] }),
    "assignment.create_with_task": () => ({ task: "T-REQ", request: "REQ-9" }), "assignment.respond": () => ({ ok: 1 }),
    "pm_inbox.nudge": a => ({ task: a.task, sent: [], skipped: [] }), "assignment.list_assignable": () => ({ rows: PEOPLE }),
    "tasks.get": a => ({ task: { name: a.name, description: "" } })
  }, o.h || {});
  const run = (m, args) => { const fn = H[m]; if (!fn) return Promise.reject(new Error("no " + m)); try { const v = fn(args || {}, calls); return v && typeof v.then === "function" ? v : Promise.resolve(v); } catch (e) { return Promise.reject(e); } };
  const api = (method, args) => { const m = method.replace("ecentric_workspace.pm.api.", ""); calls.push({ m, a: args, via: "host" }); return run(m, args); };
  if (o.ec) w.ecApi = {
    get: (method, args) => { const m = method.replace("ecentric_workspace.pm.api.", ""); ecCalls.push({ k: "get", m, a: args }); if (o.ec.get) return o.ec.get(m, args); calls.push({ m, a: args, via: "ecget" }); return run(m, args); },
    post: (method, args) => { const m = method.replace("ecentric_workspace.pm.api.", ""); ecCalls.push({ k: "post", m, a: args }); if (o.ec.post) return o.ec.post(m, args); calls.push({ m, a: args, via: "ecpost" }); return run(m, args); }
  };
  const c = w.document.getElementById("v");
  const ctl = w.PMQueue.render(c, { api, user: o.user === undefined ? ME : o.user, tab: o.tab || "me", openTask: (n, oo) => opened.push([n, oo || null]),
    head: (t, s, r) => `<div class="pm-head"><div><h1>${t}</h1><div class="sub">${s}</div></div><div>${r || ""}</div></div>` });
  const $ = s => w.document.querySelector(s), $$ = s => Array.from(w.document.querySelectorAll(s));
  const key = (k, target, extra) => (target || w.document.body).dispatchEvent(new w.KeyboardEvent("keydown", Object.assign({ key: k, bubbles: true, cancelable: true }, extra || {})));
  const count = m => calls.filter(x => x.m === m).length;
  const last = m => calls.filter(x => x.m === m).slice(-1)[0];
  const toast = () => ($(".pmq-toast [data-tm]") || {}).textContent || "";
  const toastBtn = label => $$(".pmq-toast-b").find(b => b.textContent === label);
  const rowEl = n => $(`.pmq-row[data-name="${n}"]`);
  const type = async v => { const i = $("[data-qa]"); i.focus(); i.value = v; try { i.setSelectionRange(v.length, v.length); } catch (_) { } i.dispatchEvent(new w.Event("input", { bubbles: true })); await flush(); };
  const submit = () => $("[data-qa-form]").dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true }));
  return { w, c, ctl, calls, ecCalls, opened, $, $$, key, count, last, toast, toastBtn, rowEl, type, submit };
}

(async () => {
  /* ---------- Q1 Chờ duyệt: người giao duyệt ngay trên hàng đợi */
  let t = setup({ tab: "give" }); await flush();
  const gr = t.rowEl("G-RV");
  ok("Q1 tab giao: dòng Chờ duyệt có nút 'Duyệt xong', không có 'Nhắc' (nhắc người đã làm xong là sai)",
    !!gr.querySelector('[data-act="approve"]') && !gr.querySelector('[data-act="nudge"]') && !!t.rowEl("G-1").querySelector('[data-act="nudge"]'));
  ok("Q1 tab giao: ô tròn của dòng Chờ duyệt bấm được (Duyệt xong), dòng thường vẫn khoá", !gr.querySelector(".pmq-chk").disabled && t.rowEl("G-1").querySelector(".pmq-chk").disabled);
  (gr.querySelector('[data-act="approve"]') || gr.querySelector(".pmq-chk")).click(); await flush();
  ok("Q1 Duyệt xong -> pm_inbox.close_parent(task) đúng 1 lần, toast 'Đã duyệt xong' + Hoàn tác",
    t.count("pm_inbox.close_parent") === 1 && t.last("pm_inbox.close_parent").a.task === "G-RV" && t.count("tasks.mark_done") === 0 && /Đã duyệt xong/.test(t.toast()) && !!t.toastBtn("Hoàn tác"));
  if (t.toastBtn("Hoàn tác")) { t.toastBtn("Hoàn tác").click(); await flush(); }
  ok("Q1 Hoàn tác duyệt -> set_status(Review)", t.last("tasks.set_status") && t.last("tasks.set_status").a.action === "Review");
  t.ctl.destroy(); t.w.close();
  t = setup(); await flush();
  const sp = t.rowEl("T-SP").querySelector(".pmq-chk");
  ok("Q1 tab tôi làm: việc cha chia nhiều người ở Chờ duyệt (tôi là người giao) -> bấm được Duyệt xong", !sp.disabled && !/chờ người giao/i.test(sp.getAttribute("title") || ""));
  ok("Q1 ...việc tôi đã gửi kiểm tra (người khác duyệt) vẫn khoá", t.rowEl("T-RV").querySelector(".pmq-chk").disabled);
  sp.click(); await flush();
  ok("Q1 ...bấm -> close_parent(T-SP)", t.count("pm_inbox.close_parent") === 1 && t.last("pm_inbox.close_parent").a.task === "T-SP");
  t.ctl.destroy(); t.w.close();

  /* ---------- Q2 giao liên tiếp bằng bàn phím */
  let pend = [];
  t = setup({ h: { "tasks.create": a => new Promise((r, j) => pend.push({ r, j, a })) } }); await flush();
  await t.type("Việc A mai");
  t.submit(); await flush();
  const qi = t.$("[data-qa]");
  ok("Q2 vừa Enter: ô trống ngay + gõ tiếp được (không readOnly)", qi.value === "" && qi.readOnly === false);
  await t.type("Việc B");
  pend[0].r({ name: "T-A" }); await flush();
  ok("Q2 việc A lưu xong KHÔNG xoá chữ đang gõ cho việc B", qi.value === "Việc B", qi.value);
  t.submit(); await flush();
  await t.type("Việc C"); t.submit(); await flush();
  await t.type("Việc D"); t.submit(); await flush();
  await t.type("Việc E"); t.submit(); await flush();
  pend.slice(1).forEach((p, i) => p.r({ name: "T-" + i })); await flush();
  ok("Q2 giao 5 việc liên tiếp (chưa chờ server) -> 5 lần tasks.create đúng tên", t.calls.filter(c => c.m === "tasks.create").map(c => c.a.subject).join("|") === "Việc A|Việc B|Việc C|Việc D|Việc E",
    t.calls.filter(c => c.m === "tasks.create").map(c => c.a.subject).join("|"));
  t.submit(); t.submit(); await flush();
  ok("Q2 Enter thêm khi ô trống ngay sau khi giao: không gọi server", t.count("tasks.create") === 5);
  pend = [];
  await t.type("Việc lỗi"); t.submit(); await flush();
  pend[0].j(smErr("Không có quyền tạo việc.")); await flush();
  ok("Q2 lỗi server khi ô còn trống -> trả lại chữ đã gõ + báo lỗi", qi.value === "Việc lỗi" && /Không có quyền tạo việc/.test(t.$("[data-parse]").textContent));
  pend = [];
  qi.value = ""; qi.dispatchEvent(new t.w.Event("input", { bubbles: true }));
  await t.type("Việc X"); t.submit(); await flush();
  await t.type("Việc Y đang gõ");
  pend[0].j(smErr("Lỗi mạng")); await flush();
  ok("Q2 lỗi server khi đã gõ việc khác -> giữ chữ mới, toast nêu tên việc lỗi", qi.value === "Việc Y đang gõ" && /Việc X/.test(t.toast()) && /Lỗi mạng/.test(t.toast()));
  t.ctl.destroy(); t.w.close();

  /* ---------- Q3 IME */
  t = setup(); await flush();
  await t.type("Gửi file @la");
  const q3 = t.$("[data-qa]");
  ok("Q3 (tiền đề) gợi ý @ đang mở", !t.$(".pmq-acl").hidden);
  q3.dispatchEvent(new t.w.KeyboardEvent("keydown", { key: "Enter", keyCode: 229, isComposing: true, bubbles: true, cancelable: true }));
  await flush();
  ok("Q3 Enter khi đang ghép chữ (isComposing) KHÔNG chọn người gợi ý", q3.value === "Gửi file @la" && !t.$(".pmq-acl").hidden, q3.value);
  q3.dispatchEvent(new t.w.KeyboardEvent("keydown", { key: "Process", keyCode: 229, bubbles: true, cancelable: true }));
  ok("Q3 keyCode 229 (Safari) cũng bỏ qua", q3.value === "Gửi file @la");
  await t.type("Gọi khách hàng");
  q3.dispatchEvent(new t.w.CompositionEvent("compositionstart", { bubbles: true }));
  t.submit(); await flush();
  ok("Q3 submit lúc đang ghép chữ -> không gửi", t.count("tasks.create") === 0);
  q3.dispatchEvent(new t.w.CompositionEvent("compositionend", { bubbles: true, data: "g" }));
  t.submit(); await flush();
  ok("Q3 ghép xong rồi Enter -> gửi bình thường", t.count("tasks.create") === 1);
  t.ctl.destroy(); t.w.close();

  /* ---------- Q4 F5 / CSRF */
  t = setup({ ec: {} }); await flush();
  t.rowEl("T-1").querySelector('[data-act="done"]').click(); await flush();
  ok("Q4 có ecApi: Xong đi ecApi.post (token tươi), không qua frappe.call của host", t.ecCalls.some(c => c.k === "post" && c.m === "tasks.mark_done") && !t.calls.some(c => c.m === "tasks.mark_done" && c.via === "host"));
  t.ctl.destroy(); t.w.close();
  const ecErr = (exc, msg, status) => { const e = new Error(exc); e.status = status || 417; e.excType = exc; e.body = { exc_type: exc, _server_messages: JSON.stringify([JSON.stringify({ message: msg })]) }; return e; };
  t = setup({ ec: { post: m => Promise.reject(ecErr("ValidationError", "Việc đã huỷ. Hãy mở lại trước khi bấm Xong.")) } }); await flush();
  t.rowEl("T-1").querySelector('[data-act="done"]').click(); await flush();
  ok("Q4 lỗi từ ecApi.post: hiện đúng thông điệp server (không phải 'ValidationError')", t.toast() === "Việc đã huỷ. Hãy mở lại trước khi bấm Xong.", t.toast());
  t.ctl.destroy(); t.w.close();
  t = setup({ ec: { get: m => Promise.reject(ecErr("PermissionError", "You do not have access to the PM module.", 403)) } }); await flush();
  ok("Q4 user không có PM: không gọi lại frappe.call (tránh hộp thoại thứ 2), báo tiếng Việt rõ ràng",
    !t.calls.some(c => c.m === "queue.list" && c.via === "host") && /chưa có quyền/i.test(t.$("[data-list]").textContent), t.$("[data-list]").textContent);
  t.ctl.destroy(); t.w.close();
  t = setup({ ec: { get: m => Promise.reject(new TypeError("Failed to fetch")) } }); await flush();
  ok("Q4 ecApi.get lỗi mạng -> vẫn thử đường host như cũ", t.calls.some(c => c.m === "queue.list" && c.via === "host") && !!t.rowEl("T-1"));
  t.ctl.destroy(); t.w.close();

  /* ---------- Q5 phím S trên dòng vừa Xong */
  t = setup(); await flush();
  t.rowEl("T-1").querySelector(".pmq-open").focus(); await flush();
  t.rowEl("T-1").querySelector('[data-act="done"]').click(); await flush();
  t.key("s", t.w.document.body); await flush();
  ok("Q5 S trên dòng vừa Xong không mở lại việc (không set_status In Progress)", !t.calls.some(c => c.m === "tasks.set_status" && c.a.name === "T-1"));
  t.ctl.destroy(); t.w.close();

  /* ---------- Q6 làm mới sau lỗi ghi */
  let gone = false;
  t = setup({ h: { "queue.list": a => (a.tab === "give" ? pack("give", giveRows()) : pack("me", meRows(), { asks: gone ? [] : [{ request: "REQ-1", task: "T-R1", subject: "Hỗ trợ kho", from_name: "Trọng", proposed_end: "2026-11-18" }] })),
    "assignment.respond": () => { gone = true; return Promise.reject(smErr("Yêu cầu này không còn mở.")); } } }); await flush();
  const q0 = t.count("queue.list");
  t.$('[data-act="ask-accept"]').click(); await flush();
  ok("Q6 Nhận việc lỗi 'không còn mở' -> báo lỗi + làm mới, dải Cần đồng ý biến mất", /không còn mở/.test(t.toast()) && t.count("queue.list") > q0 && !t.$(".pmq-ask"));
  t.ctl.destroy(); t.w.close();

  /* ---------- Q7 @email */
  t = setup(); await flush();
  const p7 = t.w.PMQueue._parseLine("@lan.nguyen@ecentric.vn gửi file tồn kho", {});
  ok("Q7 @email đầy đủ: token = email, tên việc sạch", p7.token === "lan.nguyen@ecentric.vn" && p7.subject === "gửi file tồn kho", JSON.stringify(p7));
  await t.type("@lan.nguyen@ecentric.vn gửi file tồn kho");
  ok("Q7 ...khớp đúng người theo email", /Nguyễn Lan Anh/.test(t.$("[data-parse]").textContent));
  t.ctl.destroy(); t.w.close();

  /* ---------- Q8 số đếm từ server */
  t = setup({ h: { "queue.list": a => { const d = pack(a.tab === "give" ? "give" : "me", a.tab === "give" ? giveRows() : meRows()); d.counts.late = '<img src=x onerror="window.__x=1">'; d.counts.today = "4"; d.personal_hidden = "<b>2</b>"; return d; } } }); await flush();
  ok("Q8 counts/personal_hidden không phải số -> không chèn HTML", !t.$(".pmq img") && !t.$(".pmq-note b b") && t.w.__x === undefined);
  t.ctl.destroy(); t.w.close();

  /* ---------- Q9 chưa biết user */
  t = setup({ user: "", cookie: "user_id=" + encodeURIComponent(ME) }); await flush();
  await t.type("Đọc hợp đồng"); t.submit(); await flush();
  ok("Q9 host chưa có user -> lấy user_id cookie, việc tự ghi có người nhận", t.last("tasks.create") && t.last("tasks.create").a.assignees === JSON.stringify([ME]));
  t.ctl.destroy(); t.w.close();
  t = setup({ user: "" }); await flush();
  await t.type("Đọc hợp đồng"); t.submit(); await flush();
  ok("Q9 không xác định được user -> không tạo việc mồ côi, báo tải lại", t.count("tasks.create") === 0 && /tải lại/i.test(t.$("[data-parse]").textContent));
  t.ctl.destroy(); t.w.close();

  /* ---------- kiểm thêm (đã đúng từ trước, giữ để khỏi lùi): auto_closed, gõ <script> vào ô giao việc */
  t = setup({ h: { "queue.list": a => (a.tab === "give" ? pack("give", giveRows()) : pack("me", meRows(), { asks: [{ request: "REQ-2", task: "T-R2", subject: "Việc đã xong", from_name: "Trọng" }] })),
    "assignment.respond": () => ({ name: "REQ-2", status: "Cancelled", auto_closed: 1, message: "Việc này đã xong hoặc đã huỷ, không cần trả lời nữa." }) } }); await flush();
  t.$('[data-act="ask-accept"]').click(); await flush();
  ok("Cần đồng ý: việc đã có người làm xong (auto_closed) -> báo 'không cần trả lời', không báo 'Đã nhận việc'", /không cần trả lời/.test(t.toast()) && !/Đã nhận việc/.test(t.toast()));
  t.ctl.destroy(); t.w.close();
  t = setup(); await flush();
  const XS = '<script>window.__s=1</script><img src=x onerror="window.__s=1">';
  await t.type("Gửi " + XS + " mai");
  ok("gõ <script>/<img onerror> vào ô giao việc: không chèn phần tử vào ô phân tích", !t.$("[data-parse] img") && !t.$("[data-parse] script") && t.w.__s === undefined);
  t.submit(); await flush();
  ok("...gửi nguyên chữ (server lưu chữ thường), toast là textContent", t.last("tasks.create").a.subject === "Gửi " + XS && !t.$(".pmq-toast img") && t.w.__s === undefined);
  await t.type("@<img src=x onerror=window.__s=1> việc");
  ok("...@<img> không tìm thấy người: tên được esc", !t.$("[data-parse] img") && t.w.__s === undefined);
  t.ctl.destroy(); t.w.close();

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
