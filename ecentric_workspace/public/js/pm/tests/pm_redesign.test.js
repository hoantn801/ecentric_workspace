/* pm_redesign (jsdom):  NODE_PATH=/tmp/jsenv/node_modules node ecentric_workspace/public/js/pm/tests/pm_redesign.test.js
 *
 * Nạp pm_redesign.js vào JSDOM, init với api giả theo hợp đồng SPEC (pm_inbox.*, tasks.mark_done, tasks.get mở rộng,
 * include_personal) + các endpoint cũ (checklist/comments/timesheet/timer/recurrence/assignment). Có tiêm lỗi.
 * Kiểm hành vi: mỗi màn render đủ phần, markDone lạc quan + blocked_reason + review_required → "Gửi kiểm tra",
 * form xin dời hạn → tham số api, công tắc Giao việc → tham số create, nhật ký cá nhân, chip lọc + tìm kiếm, hoàn nguyên khi lỗi.
 */
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");
const JS_PATH = path.join(__dirname, "..", "pm_redesign.js");
const CSS_PATH = path.join(__dirname, "..", "..", "..", "css", "pm", "pm_redesign.css");
const JS = fs.readFileSync(JS_PATH, "utf8");
const CSS = fs.readFileSync(CSS_PATH, "utf8");
const PMA = "ecentric_workspace.pm.api.";
/* Hợp đồng BE <-> FE: bộ khoá CHÍNH XÁC backend trả về. Bảng này phải GIỐNG HỆT CONTRACT trong
 * pm/tests/standalone/test_contract_shapes.py (test Python parse khối dưới đây và so sánh; nó cũng chạy
 * backend thật trên fake frappe để khẳng định từng bộ khoá). Khối "hợp đồng" ở cuối file này kiểm mọi
 * fixture của api giả nằm TRONG bảng: đổi shape backend thì phải sửa cả 2 file. Mục có "+" = tập con bắt buộc. */
// CONTRACT-BEGIN (JSON thuần — đồng bộ với test_contract_shapes.py::CONTRACT)
const CONTRACT = {"tasks.get": ["subtasks", "task", "user_names"], "tasks.get.task+": ["auto_close", "can_manage", "children_progress", "giver", "history", "is_leader", "pending_deadline_request", "recurrence", "review_required", "split"], "tasks.get.giver": ["full_name", "user"], "tasks.get.recurrence": ["label", "name"], "tasks.get.pending_deadline_request": ["created", "from_name", "new_end", "reason", "recipient", "request", "requested_by", "status"], "tasks.get.children_progress": ["done", "open", "people", "total"], "tasks.get.history": ["at", "by", "by_name", "from", "to"], "person": ["done_on", "full_name", "late", "opened", "state", "steps", "task", "user"], "tasks.mark_done": ["blocked_reason", "missing", "parent_state", "state", "withdrew_request"], "tasks.create": ["name", "parent_task", "project", "subject"], "tasks.create.split": ["children", "name", "parent_task", "project", "split", "subject"], "pm_inbox.received": ["badge", "my_deadline_requests", "needs_reply", "unopened"], "pm_inbox.received.needs_reply": ["created", "from_name", "from_user", "message", "project_name", "proposed_end", "request", "subject", "task"], "pm_inbox.received.unopened": ["exp_end_date", "from_name", "from_user", "project_name", "subject", "task", "workflow_state"], "pm_inbox.received.my_deadline_requests": ["answer", "answered_at", "new_end", "old_end", "reason", "request", "status", "subject", "task", "unseen"], "pm_inbox.given": ["banner", "batches", "rules"], "pm_inbox.given.banner": ["created", "from_name", "from_user", "new_end", "old_end", "project_name", "reason", "request", "subject", "task"], "pm_inbox.given.batches": ["auto_close", "done_count", "exp_end_date", "people", "project_name", "recurrence", "review_required", "split", "subject", "task", "total", "workflow_state"], "pm_inbox.given.rules": ["assignees", "name", "next_run", "schedule_label", "status", "subject"], "pm_inbox.coordinate": ["kpi", "people", "personal_hidden", "projects", "todo"], "pm_inbox.coordinate.kpi": ["done_week", "late", "on_time_pct_30d", "open", "unassigned"], "pm_inbox.coordinate.todo.late": ["assignees", "days_late", "exp_end_date", "full_name", "kind", "opened", "project", "project_name", "subject", "task", "user", "workflow_state"], "pm_inbox.coordinate.todo.group": ["count", "kind", "projects", "tasks"], "pm_inbox.coordinate.todo.overload": ["full_name", "kind", "late", "open", "user"], "pm_inbox.coordinate.people": ["done_week", "full_name", "late", "open", "user"], "pm_inbox.coordinate.projects": ["done", "late", "name", "open", "owner", "owner_name", "project_name", "total", "unassigned"], "pm_inbox.request_deadline": ["new_end", "old_end", "request", "status", "task"], "pm_inbox.answer_deadline": ["exp_end_date", "parent_extended", "request", "status", "task"], "pm_inbox.withdraw_deadline": ["request", "status"], "pm_inbox.nudge": ["sent", "skipped", "task"], "pm_inbox.close_parent": ["returned", "state", "task"], "dashboard.rail_badges": ["assignments", "mywork", "received"], "assignment.create_with_task": ["request", "task"], "assignment.create_with_task.split": ["children", "requests", "split", "task"], "recurrence.create_from_task+": ["auto_close", "name", "review_required", "split_per_assignee"]};
// CONTRACT-END

const results = [];
const ok = (name, cond, extra) => { results.push({ name, pass: !!cond, extra }); };
const tick = (ms) => new Promise(r => setTimeout(r, ms || 0));
const flush = async (n) => { for (let i = 0; i < (n || 6); i++) await tick(0); };

const ME = "me@ecentric.vn", BOSS = "boss@ecentric.vn", U2 = "lan@ecentric.vn", U3 = "nga@ecentric.vn";
const pad = n => (n < 10 ? "0" : "") + n;
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const dayOff = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return ymd(d); };
const smErr = (msg) => ({ _server_messages: JSON.stringify([JSON.stringify({ message: msg })]) });

function makeEnv(opts) {
  opts = opts || {};
  const dom = new JSDOM("<!doctype html><html><body><div id=main></div></body></html>", { runScripts: "outside-only", pretendToBeVisual: true, url: "https://team.ecentric.vn/pm" });
  const w = dom.window;
  const before = new Set(Object.getOwnPropertyNames(w));
  w.eval(JS);
  const added = Object.getOwnPropertyNames(w).filter(k => !before.has(k));
  const calls = [], fail = {}, hold = {};
  const db = {
    markResult: { "T-B": { blocked_reason: "required_steps" }, "T-R": { state: "Review" }, "T-W": { state: "Done", withdrew_request: 1 } },
    tasks: {
      "T-1": { task: { name: "T-1", subject: "Báo cáo tháng 9", project: "P1", project_name: "ANDROS - SHOPEE", workflow_state: "In Progress", exp_end_date: dayOff(-1), owner: BOSS, _assign: JSON.stringify([ME]), priority: "High", creation: dayOff(-5) + " 09:00:00" },
        giver: { user: BOSS, full_name: "Hương Lê" }, review_required: 0, auto_close: 0, pending_deadline_request: null, user_names: { [ME]: "Tôi Đây", [BOSS]: "Hương Lê" },
        can_manage: 0, is_leader: 0, recurrence: { name: "REC-1", label: "Hằng tháng ngày 7" },
        history: [{ at: dayOff(-1) + " 10:00:00", by: ME, by_name: "Tôi Đây", from: "To Do", to: "In Progress" }] },
      "T-R": { task: { name: "T-R", subject: "Đối chiếu đơn hoàn", project: "P1", project_name: "ANDROS - SHOPEE", workflow_state: "In Progress", exp_end_date: dayOff(2), owner: BOSS, _assign: JSON.stringify([ME]) },
        giver: { user: BOSS, full_name: "Hương Lê" }, review_required: 1 },
      "T-G": { task: { name: "T-G", subject: "Đối soát hoàn tiền", project: "P2", project_name: "Mua sắm", workflow_state: "In Progress", exp_end_date: dayOff(1), owner: ME, _assign: JSON.stringify([U2]) },
        giver: { user: ME, full_name: "Tôi Đây" }, pending_deadline_request: { request: "REQ-9", requested_by: U2, from_name: "Lan Anh", new_end: dayOff(4), reason: "đợi file", status: "Pending" } },
      "T-P": { task: { name: "T-P", subject: "Báo cáo tháng — cha", project: "P1", project_name: "ANDROS - SHOPEE", workflow_state: "In Progress", exp_end_date: dayOff(3), owner: ME, _assign: JSON.stringify([ME]) },
        giver: { user: ME, full_name: "Tôi Đây" }, subtasks: [
          { name: "T-P1", subject: "x — Lan", workflow_state: "Done", _assign: JSON.stringify([U2]) },
          { name: "T-P2", subject: "x — Nga", workflow_state: "To Do", _assign: JSON.stringify([U3]), exp_end_date: dayOff(-2) }],
        children_progress: { done: 1, total: 2, open: 1, people: [
          { user: U2, full_name: "Lan Anh", task: "T-P1", state: "Done", opened: true, done_on: dayOff(-1), late: false, steps: null },
          { user: U3, full_name: "Phương Nga", task: "T-P2", state: "To Do", opened: false, done_on: null, late: true, steps: null }] } }
    },
    checklist: { "T-1": { rows: [{ name: "r1", item_label: "Kéo số liệu", is_required: 1, is_done: 1 }, { name: "r2", item_label: "Nhận xét SKU", is_required: 0, is_done: 0 }], total: 2, done: 1 } },
    listRows: [
      { name: "A1", subject: "Báo cáo ANDROS", project: "P1", project_name: "ANDROS - SHOPEE", workflow_state: "In Progress", exp_end_date: dayOff(-1), _assign: JSON.stringify([ME]) },
      { name: "C1", subject: "Báo cáo ANDROS — Nga", project: "P1", project_name: "ANDROS - SHOPEE", parent_task: "A1", workflow_state: "To Do", _assign: JSON.stringify([U3]) },
      { name: "A2", subject: "Đối chiếu đơn hoàn tuần 40", project: "P1", project_name: "ANDROS - SHOPEE", workflow_state: "Review", exp_end_date: dayOff(0), _assign: JSON.stringify([U2]) },
      { name: "A3", subject: "Viết kịch bản livestream", project: "P2", project_name: "AI Livestream", workflow_state: "To Do", exp_end_date: dayOff(20), _assign: null },
      { name: "A4", subject: "Gia hạn Metric", project: null, workflow_state: "To Do", exp_end_date: null, _assign: null },
      { name: "A6", subject: "Đã xong rồi", project: "P2", project_name: "AI Livestream", workflow_state: "Done", exp_end_date: dayOff(-3), _assign: JSON.stringify([U2]), modified: dayOff(-1) },
      { name: "A7", subject: "Đã huỷ", project: "P2", project_name: "AI Livestream", workflow_state: "Cancelled", _assign: null }
    ],
    personalRow: { name: "WL1", subject: "Worklog backfill", project: "PW", project_name: "ERP - GBS", workflow_state: "In Progress", exp_end_date: dayOff(-30), _assign: JSON.stringify([ME]), ec_personal_log: 1 }
  };
  const H = {
    "pm_inbox.received": () => opts.receivedEmpty ? { needs_reply: [], unopened: [], my_deadline_requests: [], badge: 0 } : ({
      needs_reply: [{ request: "AR-1", task: "T-N", subject: "Đối soát tồn kho tháng 10", project_name: "Mua sắm", from_user: BOSS, from_name: "Minh Phạm", proposed_end: dayOff(6) + " 18:00:00", message: "Làm giúp anh", created: dayOff(0) + " 08:00:00" }],
      unopened: [{ task: "T-U", subject: "Lên kế hoạch 11.11", project_name: "ANDROS - SHOPEE", from_user: BOSS, from_name: "Hương Lê", exp_end_date: dayOff(5), workflow_state: "To Do" }],
      my_deadline_requests: [
        { request: "DL-1", task: "T-1", subject: "Cập nhật giá sàn", old_end: dayOff(1), new_end: dayOff(4), reason: "đợi số liệu", status: "Pending" },
        { request: "DL-2", task: "T-2", subject: "Duyệt GMV", old_end: dayOff(0), new_end: dayOff(2), reason: "x", status: "Rejected", answer: "Không dời được", answered_at: dayOff(0) + " 08:30:00" }],
      badge: 3 }),
    "pm_inbox.given": (a) => a.tab === "rep" ? { banner: [], batches: [], rules: [{ name: "REC-1", subject: "Báo cáo tháng — ANDROS", schedule_label: "Ngày 7 hằng tháng · 18:00", assignees: [U2, U3], next_run: dayOff(20), status: "Active" }] } : ({
      banner: [{ request: "DL-7", task: "T-G", subject: "Đối soát hoàn tiền", from_user: U2, from_name: "Thảo Trần", old_end: dayOff(1), new_end: dayOff(4), reason: "đợi Boxme" }],
      batches: [
        { task: "B-1", subject: "Báo cáo tháng 9 — Dutch Lady", project_name: "FCV - Dutch Lady", split: true, auto_close: 0, review_required: 0, recurrence: null, exp_end_date: dayOff(-1), workflow_state: "Review",
          people: [{ user: U2, full_name: "Lan Anh", task: "B-1a", state: "Done", opened: true, done_on: dayOff(-2) }, { user: U3, full_name: "Phương Nga", task: "B-1b", state: "Done", opened: true, done_on: dayOff(-1) }], done_count: 2, total: 2 },
        { task: "B-2", subject: "Báo cáo tháng 9 — ANDROS", project_name: "ANDROS - SHOPEE", split: true, recurrence: { name: "REC-1", label: "ngày 7 hằng tháng" }, exp_end_date: dayOff(-1), workflow_state: "In Progress",
          people: [{ user: U2, full_name: "Lan Anh", task: "B-2a", state: "Done", opened: true, done_on: dayOff(-2) }, { user: U3, full_name: "Ngọc Lâm", task: "B-2b", state: "To Do", opened: false, late: true }, { user: BOSS, full_name: "Dũng Lý", task: "B-2c", state: "In Progress", opened: true, steps: "2/4" }], done_count: 1, total: 3 },
        { task: "B-3", subject: "Cập nhật giá sàn", project_name: "ANDROS - LAZADA", split: false, exp_end_date: dayOff(2), workflow_state: "Review", people: [{ user: U2, full_name: "Lan Anh", task: "B-3", state: "Review", opened: true }], done_count: 0, total: 1 }],
      rules: [] }),
    "pm_inbox.coordinate": () => ({
      kpi: { open: 18, late: 3, unassigned: 4, done_week: 11, on_time_pct_30d: 82 },
      todo: [{ kind: "late", task: "T-L", subject: "Báo cáo ANDROS", user: U3, full_name: "Ngọc Lâm", days_late: 1, opened: false, workflow_state: "To Do" },
        { kind: "unassigned", count: 4, projects: [{ project: "P2", project_name: "AI Livestream", count: 3 }] },
        { kind: "nodue", count: 2, projects: [{ project_name: "Pin Hà Nội", count: 2 }] },
        { kind: "overload", user: U2, full_name: "Lan Anh", open: 7, late: 0 }],
      people: [{ user: U2, full_name: "Lan Anh", open: 7, late: 0, done_week: 3 }, { user: U3, full_name: "Ngọc Lâm", open: 3, late: 2, done_week: 1 }],
      projects: [{ name: "P1", project_name: "ANDROS - SHOPEE", done: 5, total: 8, open: 3, late: 1, unassigned: 0, owner: BOSS, owner_name: "Hương Lê" }],
      personal_hidden: 1
    }),
    "pm_inbox.request_deadline": (a) => ({ request: "DL-NEW", task: a.task, status: "Pending", old_end: null, new_end: a.new_end }),
    "pm_inbox.withdraw_deadline": (a) => ({ request: a.request, status: "Cancelled" }),
    "pm_inbox.answer_deadline": (a) => ({ request: a.request, status: a.accept ? "Accepted" : "Rejected", task: "T-G", exp_end_date: dayOff(4), parent_extended: false }),
    "pm_inbox.nudge": (a) => ({ task: a.task, sent: a.users ? JSON.parse(a.users) : [U3, BOSS], skipped: [] }),
    "pm_inbox.close_parent": (a) => ({ task: a.task, state: a.return_users ? "In Progress" : "Done", returned: [] }),
    "tasks.mark_done": (a) => db.markResult[a.name] || { state: "Done" },
    "tasks.set_status": (a) => ({ name: a.name, workflow_state: a.action }),
    "tasks.get": (a) => {   /* như backend: các trường redesign nằm TRONG task (tasks._redesign_detail) */
      const t = db.tasks[a.name]; if (!t) throw new Error("Not found");
      const src = JSON.parse(JSON.stringify(t)), out = { task: src.task, subtasks: src.subtasks || [], user_names: src.user_names || {} };
      Object.keys(src).forEach(k => { if (!(k in out)) out.task[k] = src[k]; });
      return out;
    },
    "tasks.list": (a) => ({ rows: JSON.parse(JSON.stringify(db.listRows.concat(a.include_personal == 1 ? [db.personalRow] : []))), user_names: { [ME]: "Tôi Đây", [U2]: "Lan Anh", [U3]: "Phương Nga" } }),
    "tasks.create": (a) => Object.assign({ name: "NEW-1", subject: a.subject, project: a.project, parent_task: a.parent_task || null },
      a.split_per_assignee ? { children: ["NEW-1a", "NEW-1b"], split: 1 } : {}),
    "tasks.assign": (a) => ({ name: a.name, assigned: JSON.parse(a.users) }),
    "tasks.update": (a) => ({ name: a.name }),
    "checklist.get_for_task": (a) => db.checklist[a.task] || { rows: [], total: 0, done: 0 },
    "checklist.set_item": (a) => { const c = db.checklist[a.task]; c.rows.forEach(r => { if (r.name === a.row_name) r.is_done = +a.is_done; }); c.done = c.rows.filter(r => r.is_done).length; return c; },
    "checklist.add_item": (a) => ({ rows: [{ name: "n1", item_label: a.title, is_done: 0 }], total: 1, done: 0 }),
    "comments.list": () => ({ rows: [{ name: "C1", content: "Thêm so sánh cùng kỳ <img src=x onerror=alert(1)><script>alert(2)</script>", owner: BOSS, creation: dayOff(-1) + " 16:20:00" }] }),
    "comments.add": () => ({ ok: 1 }),
    "timesheet.list": () => ({ rows: [{ from_time: dayOff(-1) + " 09:00:00", hours: 2, description: "Đối chiếu", owner: ME }], total_hours: 3.5 }),
    "timesheet.log": (a) => ({ timesheet: "TS-1", hours: a.hours }),
    "timer.get_active": () => ({ active: false }),
    "timer.start": (a) => ({ active: true, task: a.task, status: "Running", elapsed_seconds: 0 }),
    "assignment.list_assignable": () => ({ rows: [{ email: U2, full_name: "Lan Anh" }, { email: U3, full_name: "Phương Nga" }, { email: BOSS, full_name: "Hương Lê" }] }),
    "assignment.respond": () => ({ ok: 1 }),
    "assignment.create_with_task": (a) => a.split_per_assignee ? { task: "NEW-R", children: ["NEW-Ra", "NEW-Rb"], requests: [{ name: "AR-1a" }, { name: "AR-1b" }], split: 1 }
      : { task: "NEW-R", request: { name: "AR-NEW" } },
    "projects.list": (a) => ({ rows: [
      { name: "P1", project_name: "ANDROS - SHOPEE", status: "Open", task_total: 8, task_done: 5, ec_manager: ME, ec_department: "E-commerce", modified: dayOff(0) + " 10:00:00" },
      { name: "P2", project_name: "AI Livestream", status: "Open", task_total: 16, task_done: 7, ec_manager: BOSS, modified: dayOff(-1) + " 10:00:00" },
      { name: "P3", project_name: "Brand Refresh", status: "Completed", task_total: 9, task_done: 9, ec_manager: BOSS }]
      .concat(a.include_personal == 1 ? [{ name: "PW", project_name: "ERP - GBS", status: "Open", task_total: 125, task_done: 0, ec_personal_log: 1 }] : []) }),
    "labels.list_labels": () => ({ rows: [{ name: "L1", label_name: "Gấp brand" }] }),
    "labels.set_task_labels": () => ({ labels: [] }),
    "recurrence.create_from_task": () => ({ name: "REC-NEW", split_per_assignee: 0, auto_close: 0, review_required: 0 }),
    "recurrence.pause": () => ({ status: "Paused" }),
    "recurrence.resume": () => ({ status: "Active" })
  };
  const api = (method, args) => {
    const m = method.indexOf(PMA) === 0 ? method.slice(PMA.length) : method;
    calls.push({ m, args: args || {}, full: method });
    if (fail[m]) { const f = fail[m]; delete fail[m]; return Promise.reject(typeof f === "string" ? smErr(f) : f); }
    if (hold[m]) return new Promise(res => { hold[m].push(() => res(H[m](args || {}))); });
    try { return Promise.resolve(H[m] ? H[m](args || {}) : {}); } catch (e) { return Promise.reject(e); }
  };
  const events = [];
  ["pmr:changed", "pmr:sheetclose", "pmr:timer", "pmr:badge"].forEach(n => w.document.addEventListener(n, e => events.push({ n, d: e.detail })));
  const navs = [];
  w.PMR.init({ api, user: ME, navigate: h => navs.push(h) });
  const main = w.document.getElementById("main");
  const $ = (s, r) => (r || w.document).querySelector(s);
  const $$ = (s, r) => Array.from((r || w.document).querySelectorAll(s));
  const click = (el) => { if (!el) throw new Error("click: element missing"); el.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true })); };
  const byText = (sel, txt, r) => $$(sel, r).find(e => e.textContent.trim().indexOf(txt) >= 0);
  const last = (m) => calls.filter(c => c.m === m).slice(-1)[0];
  const toastText = () => { const t = $(".pmr-toast"); return t ? t.textContent : ""; };
  const sheet = () => $(".pmr-sheet");
  const type = (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input", { bubbles: true })); };
  const change = (el, v) => { if (v !== undefined) el.value = v; el.dispatchEvent(new w.Event("change", { bubbles: true })); };
  return { w, api, H, calls, fail, hold, db, main, $, $$, click, byText, last, toastText, sheet, type, change, events, navs, added };
}

async function block(name, fn) {
  try { await fn(); } catch (e) { ok("khối chạy trọn: " + name, false, e && e.message); }
}

(async () => {
  /* ---------------- global surface + labels + jinja safety + budget ---------------- */
  await block('global surface + labels + jinja safety + budget #1', async () => {
    const E = makeEnv();
    ok("chỉ thêm đúng 1 global: PMR", E.added.length === 1 && E.added[0] === "PMR", E.added.join(","));
    const P = E.w.PMR;
    ok("API công khai đủ theo SPEC", ["init", "openTask", "newTask", "markDone", "stateLabel", "priorityLabel", "personalToggle"].every(k => typeof P[k] === "function")
      && ["received", "given", "coordinate", "allWork", "projects"].every(k => typeof P.render[k] === "function") && P.LABELS && P.LABELS.state && P.LABELS.priority);
    ok("nhãn trạng thái dùng chung (Backlog+To Do → Chưa làm …)", P.stateLabel("Backlog") === "Chưa làm" && P.stateLabel("To Do") === "Chưa làm" && P.stateLabel("In Progress") === "Đang làm"
      && P.stateLabel("Review") === "Chờ duyệt" && P.stateLabel("Done") === "Xong" && P.stateLabel("Cancelled") === "Đã huỷ");
    ok("nhãn ưu tiên Thấp/Bình thường/Cao/Gấp", P.priorityLabel("Low") === "Thấp" && P.priorityLabel("Medium") === "Bình thường" && P.priorityLabel("High") === "Cao" && P.priorityLabel("Urgent") === "Gấp");
    ok("không có '{{' '{%' '{#' trong JS/CSS (an toàn Jinja)", !/\{\{|\{%|\{#/.test(JS) && !/\{\{|\{%|\{#/.test(CSS));
    ok("không data: URI, không emoji trong JS/CSS", !/data:(image|text|application)/.test(JS + CSS) && !/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(JS + CSS));
    ok("ngân sách: JS ≤ 120 KB, CSS ≤ 30 KB", Buffer.byteLength(JS) <= 120 * 1024 && Buffer.byteLength(CSS) <= 30 * 1024, Buffer.byteLength(JS) + " / " + Buffer.byteLength(CSS));
    ok("mọi selector CSS có namespace .pmr- (trừ :root/@keyframes)", CSS.replace(/\/\*[\s\S]*?\*\//g, "").replace(/@keyframes[^{]+\{([^{}]*\{[^}]*\})*[^}]*\}/g, "").split("}").map(b => b.split("{")[0].trim()).filter(s => s && !/^@media|^:root$|^from|^to|^\d+%/.test(s))
      .every(sel => sel.split(",").every(x => /\.pmr-/.test(x))));
    let threw = false;
    const dom2 = new JSDOM("<body></body>", { runScripts: "outside-only" }); dom2.window.eval(JS);
    try { dom2.window.PMR.init({}); } catch (e) { threw = /api/.test(e.message); }
    ok("init thiếu api → báo lỗi rõ", threw);
  });

  /* ---------------- Được giao cho tôi ---------------- */
  await block('Được giao cho tôi #2', async () => {
    const E = makeEnv();
    await E.w.PMR.render.received(E.main); await flush();
    const txt = E.main.textContent;
    ok("received: đủ 3 nhóm (trả lời / chưa mở / xin dời hạn)", txt.includes("Cần bạn trả lời") && txt.includes("Mới được giao, bạn chưa mở") && txt.includes("Xin dời hạn của bạn"));
    ok("received: badge đang chờ + bị từ chối hiển thị", !!E.$(".pmr-pend:not(.pmr-pend-no)", E.main) && E.$(".pmr-pend-no", E.main).textContent.includes("Không được đồng ý"));
    ok("received: phát pmr:badge = received().badge", E.events.some(e => e.n === "pmr:badge" && e.d.count === 3));
    E.click(E.byText(".pmr-btn", "Từ chối", E.main)); await flush();
    E.click(E.byText(".pmr-btn", "Gửi từ chối", E.main)); await flush();
    ok("received: Từ chối bắt buộc lý do (chưa ghi → không gọi api)", !E.last("assignment.respond") && /lý do/i.test(E.toastText()));
    E.$(".pmr-rq-reason", E.main).value = "Đang kẹt việc khác";
    E.click(E.byText(".pmr-btn", "Gửi từ chối", E.main)); await flush();
    const rj = E.last("assignment.respond");
    ok("received: Từ chối gửi assignment.respond(reject, reason)", rj && rj.args.name === "AR-1" && rj.args.decision === "reject" && rj.args.reason === "Đang kẹt việc khác");
    E.click(E.byText(".pmr-btn", "Nhận việc", E.main)); await flush();
    ok("received: Nhận việc → respond(accept)", E.calls.some(c => c.m === "assignment.respond" && c.args.decision === "accept"));
    E.click(E.byText(".pmr-link", "Rút lại", E.main)); await flush();
    ok("received: Rút lại đề xuất → pm_inbox.withdraw_deadline(DL-1)", E.last("pm_inbox.withdraw_deadline") && E.last("pm_inbox.withdraw_deadline").args.request === "DL-1");
    const E2 = makeEnv({ receivedEmpty: true });
    await E2.w.PMR.render.received(E2.main); await flush();
    ok("received: trạng thái rỗng có hướng dẫn + link Việc của tôi", E2.main.textContent.includes("Không có gì cần bạn trả lời") && !!E2.byText(".pmr-link", "Việc của tôi", E2.main));
    E2.click(E2.byText(".pmr-link", "Việc của tôi", E2.main));
    ok("received: link Việc của tôi điều hướng #mywork qua host", E2.navs.indexOf("#mywork") >= 0);
  });

  /* ---------------- Tôi đã giao ---------------- */
  await block('Tôi đã giao #3', async () => {
    const E = makeEnv();
    await E.w.PMR.render.given(E.main, "run"); await flush();
    const b1 = E.$('.pmr-batch[data-task="B-1"]', E.main), b2 = E.$('.pmr-batch[data-task="B-2"]', E.main);
    ok("given: mỗi lần giao 1 dòng, segbar đúng số người + màu", E.$$(".pmr-segbar i", b2).length === 3 && E.$$(".pmr-segbar i.pmr-ok", b2).length === 1 && E.$$(".pmr-segbar i.pmr-late", b2).length === 1 && E.$$(".pmr-segbar i.pmr-doing", b2).length === 1);
    ok("given: banner sẵn sàng (Chờ duyệt) + Đóng việc + Trả lại", E.$(".pmr-ready", b1).textContent.includes("Chờ duyệt") && !!E.byText(".pmr-btn", "Đóng việc", b1) && !!E.byText(".pmr-btn", "Trả lại", b1));
    ok("given: banner xin dời hạn ở đầu trang", E.$(".pmr-alert", E.main).textContent.includes("Thảo Trần đề xuất dời hạn"));
    ok("given: người chưa mở việc hiện cảnh báo + nút Nhắc", E.$$(".pmr-last.pmr-warn", b2).some(x => x.textContent.includes("chưa mở việc")) && !!E.byText(".pmr-link", "Nhắc", b2));
    E.click(E.byText(".pmr-btn", "Đồng ý", E.$(".pmr-alert", E.main))); await flush();
    ok("given: Đồng ý dời hạn → answer_deadline(accept=1)", E.last("pm_inbox.answer_deadline").args.request === "DL-7" && E.last("pm_inbox.answer_deadline").args.accept === 1 && !E.$(".pmr-alert", E.main));
    E.click(E.byText(".pmr-btn", "Nhắc 2 người", b2)); await flush();
    const ng = E.last("pm_inbox.nudge");
    ok("given: Nhắc N người → nudge(task) không kèm users", ng && ng.args.task === "B-2" && ng.args.users === undefined && /Đã nhắc 2 người/.test(E.toastText()));
    E.click(E.byText(".pmr-btn", "Trả lại", b1)); await flush();
    E.$('.pmr-retform input[value="' + U3 + '"]', b1).checked = true;
    E.$(".pmr-ret-note", b1).value = "Thiếu so sánh";
    E.click(E.byText(".pmr-retform .pmr-btn", "Trả lại", b1)); await flush();
    const rt = E.last("pm_inbox.close_parent");
    ok("given: Trả lại 1 người → close_parent(return_users, note)", rt && rt.args.task === "B-1" && JSON.parse(rt.args.return_users)[0] === U3 && rt.args.note === "Thiếu so sánh");
    await flush();
    E.fail["pm_inbox.close_parent"] = "Việc đã thay đổi, tải lại";
    const b1b = E.$('.pmr-batch[data-task="B-1"]', E.main);
    E.click(E.byText(".pmr-btn", "Đóng việc", b1b)); await flush();
    ok("given: Đóng việc lỗi → dòng hiện lại + toast lỗi từ server", !!E.$('.pmr-batch[data-task="B-1"]:not(.pmr-gone)', E.main) && E.toastText().includes("Việc đã thay đổi, tải lại") && E.$(".pmr-toast").classList.contains("pmr-err"));
    E.click(E.byText(".pmr-btn", "Đóng việc", E.$('.pmr-batch[data-task="B-1"]', E.main))); await flush();
    ok("given: Đóng việc → close_parent(task) + dòng biến mất + toast Hoàn tác", E.last("pm_inbox.close_parent").args.task === "B-1" && !E.$('.pmr-batch[data-task="B-1"]', E.main) && E.toastText().includes("Hoàn tác"));
    E.click(E.byText(".pmr-tabs button", "Lặp lại", E.main)); await flush();
    ok("given tab Lặp lại: bảng lịch + lần tới", E.main.textContent.includes("Ngày 7 hằng tháng") && !!E.$('tr[data-rule="REC-1"]', E.main));
    E.click(E.byText(".pmr-btn", "Tạm dừng", E.main)); await flush();
    ok("given: Tạm dừng lịch → recurrence.pause + nút thành Chạy lại", E.last("recurrence.pause").args.name === "REC-1" && !!E.byText(".pmr-btn", "Chạy lại", E.main));
  });

  /* ---------------- Điều phối ---------------- */
  await block('Điều phối #4', async () => {
    const E = makeEnv();
    await E.w.PMR.render.coordinate(E.main); await flush();
    const vs = E.$$(".pmr-strip .pmr-v", E.main).map(x => x.textContent);
    ok("coordinate: dải 5 KPI (gồm % đúng hạn tổng)", vs.length === 5 && vs[0] === "18" && vs[4] === "82%");
    const peopleHead = E.$$(".pmr-grid2 .pmr-panel", E.main)[1].textContent;
    ok("coordinate: bảng Theo người KHÔNG có % đúng hạn theo người", peopleHead.includes("Đang mở") && !/Đúng hạn|%/.test(peopleHead));
    ok("coordinate: Cần xử lý có đủ loại + nút hành động", E.$$(".pmr-todo-row", E.main).length === 4 && !!E.byText(".pmr-btn", "Giao", E.main) && !!E.byText(".pmr-btn", "Đặt hạn", E.main) && !!E.byText(".pmr-btn", "Xem việc", E.main));
    E.click(E.byText(".pmr-todo-row .pmr-btn", "Nhắc", E.main)); await flush();
    ok("coordinate: Nhắc → nudge(task, users=[người trễ])", E.last("pm_inbox.nudge").args.task === "T-L" && JSON.parse(E.last("pm_inbox.nudge").args.users)[0] === U3);
    ok("coordinate: mặc định loại nhật ký cá nhân (include_personal=0)", E.last("pm_inbox.coordinate").args.include_personal === 0);
    E.click(E.byText(".pmr-btn", "Giao", E.main));
    ok("coordinate: Giao → sang Tất cả việc", E.navs.slice(-1)[0] === "#work/list");
    await E.w.PMR.render.allWork(E.main, "list"); await flush();
    ok("coordinate → allWork: chip Chưa có người bật sẵn", E.byText(".pmr-chip", "Chưa có người", E.main).classList.contains("pmr-on") && E.$$("tbody tr[data-task]", E.main).every(tr => tr.textContent.includes("+ Giao người")));
    const E2 = makeEnv();
    E2.fail["pm_inbox.coordinate"] = { exc_type: "PermissionError", message: "Không có quyền xem Điều phối" };
    await E2.w.PMR.render.coordinate(E2.main); await flush();
    ok("coordinate: không phải leader → thông báo thân thiện", E2.main.textContent.includes("Chỉ trưởng nhóm xem được Điều phối"));
  });

  /* ---------------- Tất cả việc: danh sách, lọc, Xong lạc quan ---------------- */
  await block('Tất cả việc: danh sách, lọc, Xong lạc quan #5', async () => {
    const E = makeEnv();
    await E.w.PMR.render.allWork(E.main, "list"); await flush();
    const groups = E.$$(".pmr-grp-row", E.main).map(x => x.textContent);
    ok("allWork: nhóm theo dự án, “Không thuộc dự án” cuối", groups.length === 3 && groups[2].indexOf("Không thuộc dự án") === 0);
    ok("allWork: ẩn Đã huỷ + Xong, việc con gộp vào cha (· 1 việc con)", !E.main.textContent.includes("Đã huỷ</") && !E.$('tr[data-task="A7"]', E.main) && !E.$('tr[data-task="A6"]', E.main) && !E.$('tr[data-task="C1"]', E.main) && E.$('tr[data-task="A1"] .pmr-subn', E.main).textContent.includes("1 việc con"));
    ok("allWork: việc chưa có người có “+ Giao người”, có dòng thêm nhanh theo dự án", !!E.$('tr[data-task="A3"] [data-act=assign]', E.main) && E.$$(".pmr-addrow", E.main).length === 3);
    E.type(E.$(".pmr-aw-q", E.main), "kich ban"); await tick(90);
    ok("allWork: lọc khi gõ (không dấu vẫn khớp)", E.$$("tbody tr[data-task]", E.main).length === 1 && !!E.$('tr[data-task="A3"]', E.main));
    E.type(E.$(".pmr-aw-q", E.main), ""); await tick(90);
    E.click(E.byText(".pmr-chip", "Trễ hạn", E.main));
    ok("allWork: chip Trễ hạn", E.$$("tbody tr[data-task]", E.main).map(t => t.getAttribute("data-task")).join() === "A1");
    E.click(E.byText(".pmr-chip", "Trễ hạn", E.main)); E.click(E.byText(".pmr-chip", "Hạn tuần này", E.main));
    ok("allWork: chip Hạn tuần này", E.$$("tbody tr[data-task]", E.main).some(t => t.getAttribute("data-task") === "A2") && !E.$('tr[data-task="A3"]', E.main));
    E.click(E.byText(".pmr-chip", "Chưa có người", E.main));
    ok("allWork: kết hợp chip không khớp → rỗng có nút xoá lọc", E.main.textContent.includes("Không có việc nào khớp") && !!E.byText(".pmr-link", "xoá tất cả bộ lọc", E.main));
    E.click(E.byText(".pmr-link", "xoá tất cả bộ lọc", E.main));
    ok("allWork: xoá lọc trả lại danh sách", E.$$("tbody tr[data-task]", E.main).length === 4);
    E.hold["tasks.mark_done"] = [];
    E.click(E.$('tr[data-task="A2"] .pmr-cb', E.main));
    ok("markDone: lạc quan (dòng thành Xong trước khi server trả)", E.$('tr[data-task="A2"]', E.main).classList.contains("pmr-done") && E.calls.some(c => c.m === "tasks.mark_done" && c.args.name === "A2"));
    E.hold["tasks.mark_done"].forEach(f => f()); delete E.hold["tasks.mark_done"]; await flush();
    ok("markDone: toast có Ghi giờ + Hoàn tác, không popup", E.toastText().includes("Đã xong") && !!E.byText(".pmr-toast-b", "Ghi giờ") && !!E.byText(".pmr-toast-b", "Hoàn tác") && !E.$(".pmr-pop"));
    E.click(E.byText(".pmr-toast-b", "Ghi giờ")); await flush();
    const pop = E.$(".pmr-pop");
    pop.querySelectorAll("input")[1].value = "1,5"; pop.querySelectorAll("input")[2].value = "Đối chiếu";
    E.click(E.byText(".pmr-btn", "Lưu", pop)); await flush();
    const tl = E.last("timesheet.log");
    ok("Ghi giờ từ toast → timesheet.log(task, 1.5, hôm nay)", tl && tl.args.task === "A2" && tl.args.hours === 1.5 && tl.args.log_date === dayOff(0) && tl.args.description === "Đối chiếu" && !E.$(".pmr-pop"));
    E.click(E.$('tr[data-task="A1"] .pmr-cb', E.main)); await flush();
    E.click(E.byText(".pmr-toast-b", "Hoàn tác")); await flush();
    ok("Hoàn tác → set_status về trạng thái cũ", E.last("tasks.set_status").args.name === "A1" && E.last("tasks.set_status").args.action === "In Progress" && !E.$('tr[data-task="A1"]', E.main).classList.contains("pmr-done"));
    E.db.markResult["A3"] = { blocked_reason: "required_steps" };
    E.click(E.$('tr[data-task="A3"] .pmr-cb', E.main)); await flush();
    ok("markDone bị chặn (bước bắt buộc) → hoàn nguyên + báo rõ lý do", !E.$('tr[data-task="A3"]', E.main).classList.contains("pmr-done") && E.toastText().includes("bước bắt buộc") && E.$(".pmr-toast").classList.contains("pmr-err"));
    E.fail["tasks.mark_done"] = "Mất kết nối máy chủ";
    E.click(E.$('tr[data-task="A4"] .pmr-cb', E.main)); await flush();
    ok("markDone lỗi api → hoàn nguyên + toast lỗi từ server", !E.$('tr[data-task="A4"]', E.main).classList.contains("pmr-done") && E.toastText().includes("Mất kết nối máy chủ"));
    E.fail["tasks.set_status"] = "Không có quyền";
    E.click(E.$('tr[data-task="A4"] [data-act=cycle]', E.main)); await flush();
    ok("đổi trạng thái lỗi → pill quay lại “Chưa làm”", E.$('tr[data-task="A4"] .pmr-st', E.main).textContent === "Chưa làm" && E.toastText().includes("Không có quyền"));
    E.click(E.$('tr[data-task="A4"] [data-act=cycle]', E.main)); await flush();
    ok("pill bấm → chuyển trạng thái kế tiếp (set_status In Progress)", E.last("tasks.set_status").args.action === "In Progress" && E.$('tr[data-task="A4"] .pmr-st', E.main).textContent === "Đang làm");
    E.click(E.$('.pmr-addrow[data-project="P1"] [data-act=quick]', E.main)); await flush();
    const qi = E.$(".pmr-quick-in", E.main); qi.value = "Việc thêm nhanh";
    qi.dispatchEvent(new E.w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await flush();
    ok("thêm nhanh trong nhóm → tasks.create(project của nhóm)", E.last("tasks.create").args.subject === "Việc thêm nhanh" && E.last("tasks.create").args.project === "P1");
    E.click(E.$('tr[data-task="A3"] [data-act=assign]', E.main)); await flush();
    E.click(E.$(".pmr-picker [data-act=pick]", E.main)); await flush();
    ok("+ Giao người → tasks.assign(users JSON)", E.last("tasks.assign").args.name === "A3" && JSON.parse(E.last("tasks.assign").args.users)[0] === U2);
  });

  /* ---------------- Kanban + Theo hạn/Gantt uỷ quyền ---------------- */
  await block('Kanban + Theo hạn/Gantt uỷ quyền #6', async () => {
    const E = makeEnv();
    let dueCalled = false;
    await E.w.PMR.render.allWork(E.main, "board"); await flush();
    const cols = E.$$(".pmr-kcol", E.main);
    ok("Kanban: 4 cột tiếng Việt, cột Xong có việc đã xong", cols.length === 4 && cols.map(c => c.querySelector(".pmr-st").textContent).join("|") === "Chưa làm|Đang làm|Chờ duyệt|Xong" && !!E.$('.pmr-kcol[data-s="Done"] [data-task="A6"]', E.main));
    const card = E.$('.pmr-kc[data-task="A3"]', E.main);
    card.dispatchEvent(new E.w.Event("dragstart", { bubbles: true }));
    E.$('.pmr-kcol[data-s="Done"]', E.main).dispatchEvent(new E.w.Event("drop", { bubbles: true, cancelable: true })); await flush();
    ok("Kanban: kéo vào cột Xong → tasks.mark_done", E.last("tasks.mark_done").args.name === "A3");
    await E.w.PMR.render.allWork(E.main, "due", { renderDue: el => { dueCalled = true; el.innerHTML = "<p class=host-due>host</p>"; } });
    ok("Theo hạn: uỷ cho hàm của host qua opts", dueCalled && !!E.$(".host-due", E.main) && E.byText(".pmr-seg button", "Theo hạn", E.main).getAttribute("aria-pressed") === "true");
  });

  /* ---------------- Chi tiết việc ---------------- */
  await block('Chi tiết việc #7', async () => {
    const E = makeEnv();
    await E.w.PMR.openTask("T-1"); await flush();
    const sh = E.sheet();
    ok("openTask: một ngăn kéo gắn vào body, z-index qua class, có role dialog", sh && sh.parentNode === E.w.document.body && sh.classList.contains("pmr-on") && sh.getAttribute("role") === "dialog");
    ok("openTask (người nhận): khối người giao “Hương Lê giao cho bạn”", E.$(".pmr-giver", sh).textContent.includes("Hương Lê giao cho bạn"));
    ok("openTask: thanh trạng thái 4 nút tiếng Việt, đúng nút đang chọn", E.$$(".pmr-statusbar button", sh).map(b => b.textContent).join("|") === "Chưa làm|Đang làm|Chờ duyệt|Xong" && E.$(".pmr-statusbar .pmr-on", sh).textContent === "Đang làm");
    ok("openTask: hạn trễ + Xin dời hạn + tab Các bước 1/2", E.$(".pmr-due.pmr-late", sh).textContent === "Trễ 1 ngày" && !!E.byText(".pmr-btn", "Xin dời hạn", sh) && E.byText(".pmr-stabs button", "Các bước", sh).textContent === "Các bước 1/2");
    E.click(E.byText(".pmr-btn", "Xin dời hạn", sh)); await flush();
    ok("Xin dời hạn: form ngay tại chỗ (không modal), có ngày nhanh + lý do", !!E.$(".pmr-rs .pmr-qd", sh) && !!E.$(".pmr-ask-reason", sh) && E.$$(".pmr-rs .pmr-qd button", sh).length === 4);
    E.click(E.byText(".pmr-btn", "Gửi đề xuất", sh)); await flush();
    ok("Xin dời hạn: thiếu lý do → không gọi api, báo lỗi tại form", !E.last("pm_inbox.request_deadline") && !E.$(".pmr-rs .pmr-err-t", sh).classList.contains("pmr-hide"));
    const pick = E.$$(".pmr-rs .pmr-qd button", sh)[1], newEnd = pick.getAttribute("data-d");
    E.click(pick); await flush();
    E.$(".pmr-ask-reason", sh).value = "Brand gửi số liệu trễ";
    E.click(E.byText(".pmr-btn", "Gửi đề xuất", sh)); await flush();
    const rd = E.last("pm_inbox.request_deadline");
    ok("Xin dời hạn → request_deadline(task, new_end, reason)", rd && rd.args.task === "T-1" && rd.args.new_end === newEnd && rd.args.reason === "Brand gửi số liệu trễ");
    ok("Xin dời hạn: trạng thái đã gửi + Rút lại, ẩn nút xin", !!E.$(".pmr-sent", sh) && !E.byText(".pmr-btn", "Xin dời hạn", sh));
    E.click(E.byText(".pmr-link", "Rút lại", sh)); await flush();
    ok("Rút lại → withdraw_deadline(request mới)", E.last("pm_inbox.withdraw_deadline").args.request === "DL-NEW" && !E.$(".pmr-sent", sh));
    const box = E.$$(".pmr-ck input", sh)[1];
    E.fail["checklist.set_item"] = "Không lưu được";
    box.checked = true; E.change(box); await flush();
    ok("tích bước lỗi → bỏ tích lại + toast", box.checked === false && E.toastText().includes("Không lưu được"));
    box.checked = true; E.change(box); await flush();
    ok("tích bước → checklist.set_item(row, 1) + cập nhật 2/2", E.last("checklist.set_item").args.row_name === "r2" && E.last("checklist.set_item").args.is_done === 1 && E.byText(".pmr-stabs button", "Các bước", sh).textContent === "Các bước 2/2");
    E.click(E.byText(".pmr-statusbar button", "Chưa làm", sh)); await flush();
    ok("thanh trạng thái → set_status(To Do) lạc quan", E.last("tasks.set_status").args.action === "To Do" && E.$(".pmr-statusbar .pmr-on", sh).textContent === "Chưa làm");
    E.click(E.byText(".pmr-stabs button", "Thời gian", sh)); await flush();
    ok("tab Thời gian: bấm giờ + đã ghi 3,5 giờ + log", E.$(".pmr-timer", sh).textContent.includes("Bắt đầu bấm giờ") && sh.textContent.includes("3,5 giờ") && E.$$(".pmr-lg", sh).length === 1);
    E.click(E.$(".pmr-timer", sh)); await flush();
    ok("bấm giờ → timer.start(task) + phát pmr:timer", E.last("timer.start").args.task === "T-1" && E.events.some(e => e.n === "pmr:timer" && e.d.active));
    E.click(E.byText(".pmr-stabs button", "Bình luận", sh)); await flush();
    ok("bình luận: làm sạch HTML (không script, không onerror)", !E.$(".pmr-cm-c script", sh) && !E.$(".pmr-cm-c img[onerror]", sh) && E.$(".pmr-cm-c", sh).textContent.includes("Thêm so sánh"));
    E.$(".pmr-cm-in", sh).value = "Em gửi chiều nay https://x.vn/a";
    E.click(E.byText(".pmr-btn", "Gửi", sh)); await flush();
    const ca = E.last("comments.add");
    ok("gửi bình luận → comments.add(Task, nội dung có link)", ca && ca.args.reference_name === "T-1" && /<a href="https:\/\/x\.vn\/a"/.test(ca.args.content) && E.$$(".pmr-cm", sh).length === 2);
    ok("tasks.get recurrence → dòng Lặp lại có nhãn lịch", sh.textContent.includes("Hằng tháng ngày 7"));
    E.click(E.byText(".pmr-stabs button", "Lịch sử", sh)); await flush();
    ok("tab Lịch sử: history {from,to,by_name} → “Chưa làm” → “Đang làm” + dòng tạo việc", E.$$(".pmr-his-r", sh).length === 2 && E.$(".pmr-his-r", sh).textContent.includes("Tôi Đây") && E.$(".pmr-his-r", sh).textContent.includes("“Chưa làm” → “Đang làm”") && sh.textContent.includes("tạo việc"));
    E.w.document.dispatchEvent(new E.w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    ok("Esc đóng ngăn kéo + phát pmr:sheetclose(task)", !sh.classList.contains("pmr-on") && E.events.some(e => e.n === "pmr:sheetclose" && e.d.task === "T-1"));
  });
  await block('Chi tiết việc #8', async () => {
    const E = makeEnv();
    await E.w.PMR.openTask("T-R"); await flush();
    const sh = E.sheet();
    ok("review_required + người nhận: nút thành “Gửi kiểm tra”, không có Xong", E.$$(".pmr-statusbar button", sh).map(b => b.textContent).join("|") === "Chưa làm|Đang làm|Gửi kiểm tra" && sh.textContent.includes("cần kiểm tra việc này"));
    E.click(E.byText(".pmr-statusbar button", "Gửi kiểm tra", sh)); await flush();
    ok("Gửi kiểm tra → tasks.mark_done, toast “Đã gửi kiểm tra”, trạng thái Chờ duyệt", E.last("tasks.mark_done").args.name === "T-R" && E.toastText().includes("Đã gửi kiểm tra") && E.$(".pmr-statusbar .pmr-on", sh).getAttribute("data-s") === "Review");
    await E.w.PMR.openTask("T-G"); await flush();
    ok("góc người giao: không có Xin dời hạn, có Đổi hạn + banner đề xuất của người nhận", !E.byText(".pmr-btn", "Xin dời hạn", sh) && !!E.byText(".pmr-link", "Đổi hạn", sh) && E.$(".pmr-alert", sh).textContent.includes("Lan Anh xin dời hạn"));
    E.click(E.byText(".pmr-btn", "Đồng ý", sh)); await flush();
    ok("người giao Đồng ý trong ngăn kéo → answer_deadline(REQ-9, 1) + hạn mới", E.last("pm_inbox.answer_deadline").args.request === "REQ-9" && E.last("pm_inbox.answer_deadline").args.accept === 1 && !E.$(".pmr-alert", sh));
    const r = await E.w.PMR.markDone("T-W", { subject: "x" }); await flush();
    ok("markDone tự rút đề xuất dời hạn → toast báo", r.withdrew_request && E.toastText().includes("đã rút đề xuất dời hạn"));
    await E.w.PMR.openTask("T-P"); await flush();
    ok("việc cha: tab Từng người 1/2, người trễ có Nhắc", E.byText(".pmr-stabs button", "Từng người", sh).textContent === "Từng người 1/2" && E.$$(".pmr-sub-list .pmr-prow", sh).length === 2 && !!E.byText(".pmr-sub-list .pmr-link", "Nhắc", sh));
    const rowsP = E.$$(".pmr-sub-list .pmr-prow .pmr-last", sh).map(x => x.textContent);
    ok("việc cha: children_progress.people → “chưa mở” + ngày xong theo từng người", rowsP[1] === "chưa mở" && /^xong /.test(rowsP[0]));
    E.click(E.byText(".pmr-statusbar button", "Xong", sh)); await flush();
    ok("markDone(T-P) chạy qua tasks.mark_done (không popup giờ)", E.last("tasks.mark_done").args.name === "T-P" && !E.$(".pmr-pop"));
  });

  /* ---------------- Giao việc ---------------- */
  await block('Giao việc #9', async () => {
    const E = makeEnv();
    E.w.PMR.newTask({ project: "P1" }); await flush();
    const sh = E.sheet();
    E.click(E.byText(".pmr-btn", "Tạo việc", sh)); await flush();
    ok("newTask: thiếu tên → không gọi create, báo lỗi", !E.last("tasks.create") && E.toastText().includes("Nhập tên việc"));
    E.$(".pmr-title-in", sh).value = "Báo cáo tháng 10";
    E.click(E.byText(".pmr-link", "+ Thêm người", sh)); await flush();
    E.click(E.$$(".pmr-picker [data-act=pick]", sh)[0]); await flush();
    E.click(E.$$(".pmr-picker [data-act=pick]", sh)[0]); await flush();
    ok("newTask: chip người nhận + nút “Giao cho 2 người”", E.$$(".pmr-chips .pmr-pc", sh).length === 2 && E.$("[data-act=nt-submit]", sh).textContent === "Giao cho 2 người");
    E.click(E.$$(".pmr-chips .pmr-rm", sh)[1]);
    ok("bỏ người (nút ×) → người đó quay lại danh sách chọn", E.$$(".pmr-chips .pmr-pc", sh).length === 1 && E.$(".pmr-picker [data-act=pick]", sh).getAttribute("data-u") === U3);
    E.click(E.$$(".pmr-picker [data-act=pick]", sh)[0]); await flush();
    E.click(E.$("[data-act=tog][data-k=split]", sh));
    ok("công tắc là role=switch + aria-checked, mở tuỳ chọn con Tự đóng", E.$("[data-k=split]", sh).getAttribute("role") === "switch" && E.$("[data-k=split]", sh).getAttribute("aria-checked") === "true" && E.$('.pmr-opt[data-o="split"]', sh).classList.contains("pmr-open"));
    E.click(E.$("[data-act=tog][data-k=auto]", sh));
    ok("Tự đóng bật → đổi lời giải thích", E.$(".pmr-auto-hint", sh).textContent.includes("Đang bật"));
    E.click(E.$("[data-act=tog][data-k=review]", sh));
    E.click(E.$("[data-act=tog][data-k=rep]", sh));
    E.click(E.byText(".pmr-qd button", "Ngày mai", sh));
    E.change(E.$(".pmr-nt-time", sh), "17:00");
    E.click(E.$("[data-act=disc]", sh));
    E.$(".pmr-nt-step", sh).value = "Kéo số liệu GMV"; E.click(E.byText(".pmr-btn", "Thêm", E.$(".pmr-extra", sh)));
    E.click(E.byText(".pmr-qd button", "Cao", sh));
    await flush();
    E.click(E.$("[data-act=nt-submit]", sh)); await flush(10);
    const cr = E.calls.find(c => c.m === "tasks.create");
    ok("toggles → create(split_per_assignee=1, auto_close=1, review_required=1, hạn+giờ, ưu tiên)", cr && cr.args.split_per_assignee === 1 && cr.args.auto_close === 1 && cr.args.review_required === 1
      && cr.args.exp_end_date === dayOff(1) && cr.args.pm_end_time === "17:00:00" && cr.args.priority === "High" && JSON.parse(cr.args.assignees).length === 2 && cr.args.project === "P1", JSON.stringify(cr && cr.args));
    const steps = E.calls.filter(c => c.m === "checklist.add_item");
    ok("các bước gắn vào từng việc con khi Mỗi người một việc", steps.length === 2 && steps.map(s => s.args.task).sort().join() === "NEW-1a,NEW-1b");
    const rec = E.last("recurrence.create_from_task");
    ok("Lặp lại → recurrence.create_from_task(task, Monthly, monthly_day, bắt đầu sau hạn)", rec && rec.args.task === "NEW-1" && rec.args.frequency === "Monthly" && rec.args.monthly_day === new Date(dayOff(1)).getDate() && rec.args.start_date === dayOff(2));
    ok("giao xong: đóng ngăn kéo + toast “Đã giao … cho 2 người”", !sh.classList.contains("pmr-on") && E.toastText().includes("cho 2 người"));
    E.w.PMR.newTask({}); await flush();
    E.$(".pmr-title-in", sh).value = "Cần đồng ý";
    E.click(E.byText(".pmr-link", "+ Thêm người", sh)); await flush();
    E.click(E.$$(".pmr-picker [data-act=pick]", sh)[0]); await flush();
    E.click(E.$("[data-act=tog][data-k=ask]", sh));
    ok("chế độ Cần đồng ý: nút đổi thành “Gửi yêu cầu cho …”", /Gửi yêu cầu cho/.test(E.$("[data-act=nt-submit]", sh).textContent));
    E.click(E.$("[data-act=nt-submit]", sh)); await flush();
    const cw = E.last("assignment.create_with_task");
    ok("Cần đồng ý (1 người) → assignment.create_with_task(recipient)", cw && cw.args.subject === "Cần đồng ý" && cw.args.recipient === U2 && cw.args.recipients === undefined);
    E.w.PMR.newTask({}); await flush();
    E.$(".pmr-title-in", sh).value = "Lỗi server";
    E.fail["tasks.create"] = "Dự án đã đóng";
    E.click(E.$("[data-act=nt-submit]", sh)); await flush();
    ok("create lỗi → giữ ngăn kéo + giữ dữ liệu + toast lỗi server", sh.classList.contains("pmr-on") && E.$(".pmr-title-in", sh).value === "Lỗi server" && E.toastText().includes("Dự án đã đóng") && !E.$("[data-act=nt-submit]", sh).disabled);
    const plan = E.w.PMR._pure.buildCreatePlan({ subject: "x", assignees: [U2, U3], ask: true, split: true, auto: false, review: false, steps: [], labels: [], due: "", time: "", rep: false, priority: "Medium", project: "" });
    ok("Cần đồng ý + Mỗi người một việc → recipients + split_per_assignee (SPEC mục 7)", plan.method === "assignment.create_with_task" && JSON.parse(plan.args.recipients).length === 2 && plan.args.split_per_assignee === 1 && plan.args.auto_close === 0);
  });

  /* ---------------- Dự án + nhật ký cá nhân ---------------- */
  await block('Dự án + nhật ký cá nhân #10', async () => {
    const E = makeEnv();
    await E.w.PMR.render.projects(E.main); await flush();
    ok("projects: bảng Đang chạy, tiến độ dạng xong/tổng", E.$$("tbody tr", E.main).length === 2 && E.main.textContent.includes("5/8") && E.last("projects.list").args.include_personal === 0);
    E.click(E.byText(".pmr-chip", "Hoàn thành", E.main));
    ok("projects: chip Hoàn thành", E.$$("tbody tr", E.main).length === 1 && E.main.textContent.includes("Brand Refresh"));
    const hn = E.$(".pmr-hidenote", E.main);
    E.click(E.byText("button", "Hiện", hn)); await flush();
    ok("personalToggle: bấm Hiện → nhớ localStorage + tải lại kèm include_personal=1", E.w.localStorage.getItem("pmr.showPersonal") === "1" && E.last("projects.list").args.include_personal === 1);
    let flipped = null;
    const box = E.w.document.createElement("div");
    E.w.PMR.personalToggle(box, v => { flipped = v; });
    E.click(E.$("button", box));
    ok("personalToggle(container, onChange): gọi onChange + đổi chữ Hiện/Ẩn", flipped === false && E.$("button", box).textContent === "Hiện" && box.textContent.includes("Đang ẩn"));
    E.w.localStorage.setItem("pmr.showPersonal", "1");
    await E.w.PMR.render.allWork(E.main, "list"); await flush();
    ok("allWork khi Hiện nhật ký → include_personal=1 và hiện dòng worklog", E.last("tasks.list").args.include_personal === 1 && !!E.$('tr[data-task="WL1"]', E.main));
  });

  /* ---------------- hợp đồng BE <-> FE: fixture nằm trong CONTRACT ---------------- */
  await block('hợp đồng fixture #12', async () => {
    const E = makeEnv(), H = E.H, bad = [];
    const within = (name, o) => {
      if (!o || typeof o !== "object") return bad.push(name + ": không phải object");
      const allow = CONTRACT[name];
      if (!allow) return bad.push(name + ": không có trong CONTRACT");
      Object.keys(o).forEach(k => { if (allow.indexOf(k) < 0 && !(/\+$/.test(name))) bad.push(name + "." + k); });
    };
    const rec = H["pm_inbox.received"]({});
    within("pm_inbox.received", rec);
    ["needs_reply", "unopened", "my_deadline_requests"].forEach(k => rec[k].forEach(r => within("pm_inbox.received." + k, r)));
    ["run", "rep"].forEach(tab => {
      const g = H["pm_inbox.given"]({ tab });
      within("pm_inbox.given", g);
      g.banner.forEach(r => within("pm_inbox.given.banner", r));
      g.batches.forEach(b => { within("pm_inbox.given.batches", b); b.people.forEach(p => within("person", p)); });
      g.rules.forEach(r => within("pm_inbox.given.rules", r));
    });
    const co = H["pm_inbox.coordinate"]({});
    within("pm_inbox.coordinate", co); within("pm_inbox.coordinate.kpi", co.kpi);
    co.todo.forEach(x => within("pm_inbox.coordinate.todo." + (x.kind === "late" || x.kind === "overload" ? x.kind : "group"), x));
    co.people.forEach(x => within("pm_inbox.coordinate.people", x));
    co.projects.forEach(x => within("pm_inbox.coordinate.projects", x));
    within("pm_inbox.request_deadline", H["pm_inbox.request_deadline"]({ task: "T", new_end: dayOff(2) }));
    within("pm_inbox.answer_deadline", H["pm_inbox.answer_deadline"]({ request: "R", accept: 1 }));
    within("pm_inbox.withdraw_deadline", H["pm_inbox.withdraw_deadline"]({ request: "R" }));
    within("pm_inbox.nudge", H["pm_inbox.nudge"]({ task: "T" }));
    within("pm_inbox.close_parent", H["pm_inbox.close_parent"]({ task: "T" }));
    Object.keys(E.db.markResult).forEach(k => within("tasks.mark_done", E.db.markResult[k]));
    within("tasks.create", H["tasks.create"]({ subject: "x" }));
    within("tasks.create.split", H["tasks.create"]({ subject: "x", split_per_assignee: 1 }));
    within("assignment.create_with_task", H["assignment.create_with_task"]({}));
    within("assignment.create_with_task.split", H["assignment.create_with_task"]({ split_per_assignee: 1 }));
    Object.keys(E.db.tasks).forEach(n => {
      const r = H["tasks.get"]({ name: n }), t = r.task;
      within("tasks.get", r);
      const std = ["name", "subject", "project", "project_name", "workflow_state", "exp_end_date", "owner", "_assign", "priority", "creation"];
      Object.keys(t).forEach(k => { if (std.indexOf(k) < 0 && CONTRACT["tasks.get.task+"].indexOf(k) < 0) bad.push("tasks.get.task." + k); });
      if (t.giver) within("tasks.get.giver", t.giver);
      if (t.recurrence) within("tasks.get.recurrence", t.recurrence);
      if (t.pending_deadline_request) within("tasks.get.pending_deadline_request", t.pending_deadline_request);
      if (t.children_progress) { within("tasks.get.children_progress", t.children_progress); t.children_progress.people.forEach(p => within("person", p)); }
      (t.history || []).forEach(h => within("tasks.get.history", h));
    });
    ok("mọi fixture api giả nằm trong CONTRACT (khớp test_contract_shapes.py)", bad.length === 0, bad.join(", "));
    ok("CONTRACT có đủ endpoint PMR gọi", ["pm_inbox.received", "pm_inbox.given", "pm_inbox.coordinate", "pm_inbox.request_deadline", "pm_inbox.answer_deadline", "pm_inbox.withdraw_deadline",
      "pm_inbox.nudge", "pm_inbox.close_parent", "tasks.get", "tasks.mark_done", "tasks.create", "dashboard.rail_badges", "assignment.create_with_task", "recurrence.create_from_task+"].every(k => Array.isArray(CONTRACT[k])));
  });

  /* ---------------- pure helpers ---------------- */
  await block('pure helpers #11', async () => {
    const E = makeEnv();
    const P = E.w.PMR._pure;
    ok("ngày tiếng Việt: Hôm nay 17:00 / T? dd/mm / Trễ N ngày", P.dueInfo(dayOff(0), "17:00:00").text === "Hôm nay 17:00" && /^(CN|T[2-7]) \d\d\/\d\d$/.test(P.dayLabel(dayOff(9))) && P.dueInfo(dayOff(-2)).text === "Trễ 2 ngày");
    ok("errOf lấy đúng thông điệp server (_server_messages)", P.errOf(smErr("Bạn không có quyền <b>x</b>")) === "Bạn không có quyền x");
    ok("sanitize: bỏ script/on*/javascript:", !/script|onerror|javascript/i.test(P.sanitize('<a href="javascript:alert(1)">a</a><img src="/files/a.png" onerror="x()"><script>1</script>')));
  });

  const pass = results.filter(r => r.pass).length;
  results.forEach(r => console.log((r.pass ? "PASS " : "FAIL ") + r.name + (r.pass || r.extra == null ? "" : "  -> " + r.extra)));
  console.log(`\n${pass}/${results.length} passed`);
  process.exit(pass === results.length ? 0 : 1);
})().catch(e => { console.error("CRASH", e); process.exit(2); });
