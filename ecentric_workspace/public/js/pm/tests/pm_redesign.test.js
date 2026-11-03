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
const CONTRACT = {"tasks.get": ["subtasks", "task", "user_names"], "tasks.get.task+": ["auto_close", "can_edit", "can_manage", "children_progress", "followers", "giver", "history", "is_follower", "is_leader", "pending_deadline_request", "recurrence", "review_required", "split"], "tasks.get.giver": ["full_name", "user"], "tasks.get.recurrence": ["label", "name"], "tasks.get.pending_deadline_request": ["created", "from_name", "new_end", "reason", "recipient", "request", "requested_by", "status"], "tasks.get.children_progress": ["done", "open", "people", "total"], "tasks.get.history": ["at", "by", "by_name", "from", "to"], "person": ["done_on", "full_name", "late", "opened", "state", "steps", "task", "user"], "tasks.mark_done": ["blocked_reason", "missing", "parent_state", "state", "withdrew_request"], "tasks.create": ["name", "parent_task", "project", "subject"], "tasks.create.split": ["children", "name", "parent_task", "project", "split", "subject"], "pm_inbox.received": ["badge", "my_deadline_requests", "needs_reply", "unopened"], "pm_inbox.received.needs_reply": ["created", "from_name", "from_user", "message", "project_name", "proposed_end", "request", "subject", "task"], "pm_inbox.received.unopened": ["exp_end_date", "from_name", "from_user", "project_name", "subject", "task", "workflow_state"], "pm_inbox.received.my_deadline_requests": ["answer", "answered_at", "new_end", "old_end", "reason", "request", "status", "subject", "task", "unseen"], "pm_inbox.given": ["banner", "batches", "rules"], "pm_inbox.given.banner": ["created", "from_name", "from_user", "new_end", "old_end", "project_name", "reason", "request", "subject", "task"], "pm_inbox.given.batches": ["auto_close", "done_count", "exp_end_date", "people", "project_name", "recurrence", "review_required", "split", "subject", "task", "total", "workflow_state"], "pm_inbox.given.rules": ["assignees", "name", "next_run", "schedule_label", "status", "subject"], "pm_inbox.coordinate": ["kpi", "people", "personal_hidden", "projects", "todo"], "pm_inbox.coordinate.kpi": ["done_week", "late", "on_time_pct_30d", "open", "unassigned"], "pm_inbox.coordinate.todo.late": ["assignees", "days_late", "exp_end_date", "full_name", "kind", "opened", "project", "project_name", "subject", "task", "user", "workflow_state"], "pm_inbox.coordinate.todo.group": ["count", "kind", "projects", "tasks"], "pm_inbox.coordinate.todo.overload": ["full_name", "kind", "late", "open", "user"], "pm_inbox.coordinate.people": ["done_week", "full_name", "late", "open", "user"], "pm_inbox.coordinate.projects": ["done", "late", "name", "open", "owner", "owner_name", "project_name", "total", "unassigned"], "pm_inbox.request_deadline": ["new_end", "old_end", "request", "status", "task"], "pm_inbox.answer_deadline": ["exp_end_date", "parent_extended", "request", "status", "task"], "pm_inbox.withdraw_deadline": ["request", "status"], "pm_inbox.nudge": ["sent", "skipped", "task"], "pm_inbox.close_parent": ["returned", "state", "task"], "dashboard.rail_badges": ["assignments", "mywork", "received"], "assignment.create_with_task": ["request", "task"], "assignment.create_with_task.split": ["children", "requests", "split", "task"], "recurrence.create_from_task+": ["auto_close", "name", "review_required", "split_per_assignee"]};
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
        giver: { user: ME, full_name: "Tôi Đây" }, split: 1, subtasks: [
          { name: "T-P1", subject: "x — Lan", workflow_state: "Done", _assign: JSON.stringify([U2]) },
          { name: "T-P2", subject: "x — Nga", workflow_state: "To Do", _assign: JSON.stringify([U3]), exp_end_date: dayOff(-2) }],
        children_progress: { done: 1, total: 2, open: 1, people: [
          { user: U2, full_name: "Lan Anh", task: "T-P1", state: "Done", opened: true, done_on: dayOff(-1), late: false, steps: null },
          { user: U3, full_name: "Phương Nga", task: "T-P2", state: "To Do", opened: false, done_on: null, late: true, steps: null }] } },
    /* việc con đặt tên riêng (không chia người) — tab Việc con */
    "T-S": { task: { name: "T-S", subject: "Thanh toán server Cloud", project: "P2", project_name: "Mua sắm", workflow_state: "In Progress", exp_end_date: dayOff(3), owner: ME, _assign: JSON.stringify([ME]) },
      giver: { user: ME, full_name: "Tôi Đây" }, split: 0, subtasks: [
        { name: "T-S1", subject: "Nhận báo giá", workflow_state: "Done", _assign: JSON.stringify([U2]) },
        { name: "T-S2", subject: "Làm Payment Request", workflow_state: "To Do", exp_end_date: dayOff(-1), _assign: null }] },
    "T-S2": { task: { name: "T-S2", subject: "Làm Payment Request", project: "P2", project_name: "Mua sắm", parent_task: "T-S", workflow_state: "To Do", owner: ME, _assign: null }, giver: { user: ME, full_name: "Tôi Đây" } },
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
    "pm_inbox.cc_suggest": (a) => { const asg = JSON.parse(a.assignees || "[]");
      return { suggest: asg.indexOf(U3) >= 0 && asg.indexOf(BOSS) < 0 ? [{ user: BOSS, full_name: "Hương Lê", for: [U3], for_names: ["Phương Nga"] }] : [],
        conflicts: asg.indexOf(BOSS) >= 0 && asg.indexOf(U3) >= 0 ? [{ head: BOSS, head_name: "Hương Lê", members: [U3], member_names: ["Phương Nga"] }] : [] }; },
    "tasks.set_followers": (a) => ({ task: a.name, followers: [] }),
    "pm_inbox.given": (a) => a.tab === "follow" ? { banner: [], rules: [], batches: [{ task: "B-F", subject: "Monthly Plan 11", project_name: "Mua sắm", split: true, exp_end_date: dayOff(2), workflow_state: "In Progress",
        giver: { user: U2, full_name: "Lan Anh" }, people: [{ user: U3, full_name: "Phương Nga", task: "B-Fa", state: "To Do", opened: false, late: true }], done_count: 0, total: 1 }] } : a.tab === "rep" ? { banner: [], batches: [], rules: [{ name: "REC-1", subject: "Báo cáo tháng — ANDROS", schedule_label: "Ngày 7 hằng tháng · 18:00", assignees: [U2, U3], next_run: dayOff(20), status: "Active" }] } : ({
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
    "comments.list": () => ({ rows: [{ name: "C1", content: "Thêm so sánh cùng kỳ <img src=x onerror=alert(1)><script>alert(2)</script>", owner: BOSS, creation: dayOff(-1) + " 16:20:00", pinned: 0 }], pinned: [], can_pin: 1 }),
    "comments.add": (a) => ({ name: "C-NEW", content: a.content, owner: ME, creation: dayOff(0) + " 10:00:00" }),
    "comments.pin": (a) => ({ pinned: +a.pinned ? [a.comment] : [] }),
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
    ok("ngân sách: JS ≤ 165 KB, CSS ≤ 40 KB (nâng 03/11 rà soát 5 agent: gợi ý hạn, nút việc tiếp theo, ghi nhanh, Việc cần làm theo hạn, lọc nhớ, thẻ điện thoại, sửa race; xem đề xuất tách asset danh sách)", Buffer.byteLength(JS) <= 165 * 1024 && Buffer.byteLength(CSS) <= 40 * 1024, Buffer.byteLength(JS) + " / " + Buffer.byteLength(CSS));

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
    ok("coordinate: có dự án nhật ký bị ẩn → hiện dòng “Đang ẩn 1 …”", !!E.$(".pmr-hidenote", E.main) && !E.$(".pmr-hidenote", E.main).hidden);
    { const orig = E.H["pm_inbox.coordinate"]; E.H["pm_inbox.coordinate"] = (x) => Object.assign(orig(x), { personal_hidden: 0 });
      await E.w.PMR.render.coordinate(E.main); await flush();
      ok("coordinate: không ẩn dự án nào → không hiện dòng “Đang ẩn 0 …”", !E.$(".pmr-hidenote", E.main) || E.$(".pmr-hidenote", E.main).hidden);
      E.H["pm_inbox.coordinate"] = orig; await E.w.PMR.render.coordinate(E.main); await flush(); }
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
    ok("Xin dời hạn: ô chọn ngày (cả khối bọc của ec_datepicker) ẩn tới khi bấm “Chọn ngày…”", E.$(".pmr-ask-date-w", sh).hidden === true && E.$(".pmr-ask-date-w .pmr-ask-date", sh) !== null);
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
    ok("Bình luận ở cột phải (không còn là tab) + đếm 1", !E.byText(".pmr-stabs button", "Bình luận", sh) && !!E.$(".pmr-side .pmr-cms", sh) && E.$(".pmr-side-n", sh).textContent === "1");
    ok("bình luận: làm sạch HTML (không script, không onerror)", !E.$(".pmr-cm-c script", sh) && !E.$(".pmr-cm-c img[onerror]", sh) && E.$(".pmr-cm-c", sh).textContent.includes("Thêm so sánh"));
    E.$(".pmr-cm-in", sh).value = "Em gửi chiều nay https://x.vn/a";
    E.click(E.byText(".pmr-btn", "Gửi", sh)); await flush();
    const ca = E.last("comments.add");
    ok("gửi bình luận → comments.add(Task, nội dung có link)", ca && ca.args.reference_name === "T-1" && /<a href="https:\/\/x\.vn\/a"/.test(ca.args.content) && E.$$(".pmr-cm", sh).length === 2 && E.$(".pmr-side-n", sh).textContent === "2");
    E.click(E.$('.pmr-cm-pin[data-cm="C1"]', sh)); await flush();
    ok("ghim bình luận → comments.pin(C1, 1) + lên khối “Đã ghim” vàng ở đầu", E.last("comments.pin").args.comment === "C1" && E.last("comments.pin").args.pinned === 1 && !!E.$('.pmr-pins .pmr-cm-pinned [data-cm="C1"]', sh) && E.$(".pmr-pins-h", sh).textContent.includes("Đã ghim · 1") && E.$$(".pmr-cms .pmr-cm", sh).length === 1);
    E.click(E.$('.pmr-cm-pin[data-cm="C1"]', sh)); await flush();
    ok("bỏ ghim → comments.pin(C1, 0), khối Đã ghim biến mất", E.last("comments.pin").args.pinned === 0 && !E.$(".pmr-pins", sh) && E.$$(".pmr-cms .pmr-cm", sh).length === 2);
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
    E.db.tasks["T-P"].task.exp_end_date = dayOff(3) + " 00:00:00"; E.db.tasks["T-P"].task.pm_end_time = "0:00:00";
    await E.w.PMR.openTask("T-P", { tab: "people" }); await flush();
    E.click(E.byText(".pmr-link", "+ Thêm người", E.$(".pmr-sub-list", sh))); await flush();
    E.click(E.$$(".pmr-sub-list .pmr-picker [data-act=pick]", sh)[0]); await flush();
    const ap = E.last("tasks.create");
    ok("thêm người vào việc chung: hạn dạng Datetime “… 00:00:00” / giờ “0:00:00” được chuẩn hoá (lỗi 02/11)", ap && ap.args.parent_task === "T-P" && ap.args.exp_end_date === dayOff(3) && ap.args.pm_end_time == null, ap && JSON.stringify(ap.args));
    E.db.tasks["T-P"].task.exp_end_date = dayOff(3); delete E.db.tasks["T-P"].task.pm_end_time;
    await E.w.PMR.openTask("T-S"); await flush();
    ok("việc con đặt tên (không chia người): tab “Việc con 1/2” mở sẵn, còn ô Người nhận", E.$(".pmr-stabs [aria-selected=true]", sh).textContent === "Việc con 1/2" && !E.byText(".pmr-stabs button", "Từng người", sh) && sh.textContent.includes("Người nhận") && E.$$(".pmr-srow", sh).length === 2);
    ok("việc con: dòng xong gạch ngang, dòng trễ cảnh báo, chưa có người → vòng trống", E.$$(".pmr-srow", sh)[0].classList.contains("pmr-done") && !!E.$(".pmr-srow-due.pmr-warn", sh) && !!E.$(".pmr-srow-noone", sh));
    E.click(E.$$(".pmr-srow [data-act=sub-tick]", sh)[1]); await flush();
    ok("nút tròn việc con → tasks.mark_done(T-S2)", E.last("tasks.mark_done").args.name === "T-S2");
    E.click(E.$$(".pmr-srow [data-act=sub-tick]", sh)[0]); await flush();
    ok("bỏ tick việc con đã xong → set_status To Do", E.last("tasks.set_status").args.name === "T-S1" && E.last("tasks.set_status").args.action === "To Do");
    E.click(E.$('[data-act=sub-assign][data-task="T-S2"]', sh)); await flush();
    ok("bấm vòng người nhận việc con → mở chọn người ngay tại dòng", !!E.$(".pmr-srow-who .pmr-picker", sh));
    E.click(E.$$(".pmr-srow-who .pmr-picker [data-act=pick]", sh)[0]); await flush();
    ok("chọn người → tasks.assign(T-S2) không cần mở việc con", E.last("tasks.assign").args.name === "T-S2" && JSON.parse(E.last("tasks.assign").args.users).length === 1);
    ok("việc con đã Xong: chỉ hiện avatar, không có nút giao nhanh (G4.3)", !E.$('[data-act=sub-assign][data-task="T-S1"]', sh) && !!E.$$(".pmr-srow", sh)[0].querySelector(".pmr-srow-who .pmr-stack"));
    E.db.tasks["T-S"].subtasks[1]._assign = JSON.stringify([U2]);
    await E.w.PMR.openTask("T-S"); await flush();
    ok("việc con đang mở đã có người: chồng avatar + nhãn “giao thêm” (không phải đổi)", /giao thêm/i.test(E.$('[data-act=sub-assign][data-task="T-S2"]', sh).getAttribute("aria-label")) && !!E.$('[data-act=sub-assign][data-task="T-S2"] .pmr-stack', sh));
    E.db.tasks["T-S"].subtasks[1]._assign = null;
    await E.w.PMR.openTask("T-S"); await flush();
    E.$(".pmr-sub-in", sh).value = "Chờ kế toán gửi UNC";
    E.click(E.$("[data-act=sub-add]", sh)); await flush();
    const cs = E.last("tasks.create");
    ok("Thêm việc con → tasks.create(parent_task, cùng dự án)", cs && cs.args.parent_task === "T-S" && cs.args.project === "P2" && cs.args.subject === "Chờ kế toán gửi UNC");
    await E.w.PMR.openTask("T-S2"); await flush();
    ok("việc đã Xong: không có “+ Thêm người” (server G4.3: mở lại trước khi giao)", (await (async () => { E.db.tasks["T-S2"].task.workflow_state = "Done"; await E.w.PMR.openTask("T-S2"); await flush(); return !E.byText(".pmr-link", "+ Thêm người", sh); })()));
    E.db.tasks["T-S2"].task.workflow_state = "To Do";
    E.db.tasks["T-S"].can_edit = 0;
    await E.w.PMR.openTask("T-S"); await flush();
    ok("chỉ xem (can_edit=0): trạng thái khoá, có dòng “Chỉ xem”, không thêm/tick/giao việc con, không “+ Thêm người”",
      E.$$(".pmr-statusbar button", sh).every(b => b.disabled) && !!E.$(".pmr-ro-hint", sh) && !E.$(".pmr-sub-in", sh) && E.$$("[data-act=sub-tick]", sh).every(b => b.disabled) && !E.$("[data-act=sub-assign]", sh) && !E.byText(".pmr-link", "+ Thêm người", sh) && !!E.$(".pmr-side", sh));
    E.click(E.byText(".pmr-stabs button", "Các bước", sh)); await flush();
    ok("chỉ xem: tab Các bước không có ô thêm bước", !E.$(".pmr-step-in", sh));
    delete E.db.tasks["T-S"].can_edit;
    await E.w.PMR.openTask("T-S2"); await flush();
    ok("mở việc con: không có tab Việc con (2 cấp) + có nút ‹ Việc cha", !E.byText(".pmr-stabs button", "Việc con", sh) && !!E.$("[data-act=open-sub][data-task=T-S]", sh));
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
    ok("newTask: chip người nhận + nút “Gửi yêu cầu cho 2 người” (Cần đồng ý bật mặc định)", E.$$(".pmr-chips .pmr-pc", sh).length === 2 && E.$("[data-act=nt-submit]", sh).textContent === "Gửi yêu cầu cho 2 người");
    E.click(E.$$(".pmr-chips .pmr-rm", sh)[1]);
    ok("bỏ người (nút ×) → người đó quay lại danh sách chọn", E.$$(".pmr-chips .pmr-pc", sh).length === 1 && E.$(".pmr-picker [data-act=pick]", sh).getAttribute("data-u") === U3);
    E.click(E.$$(".pmr-picker [data-act=pick]", sh)[0]); await flush();
    E.click(E.$("[data-act=tog][data-k=ask]", sh));   /* tắt Cần đồng ý (mặc định bật) để thử nhánh giao thẳng */
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
    ok("Cần người nhận đồng ý BẬT mặc định (PO 16/10)", E.$("[data-act=tog][data-k=ask]", sh).getAttribute("aria-checked") === "true");
    ok("chế độ Cần đồng ý: nút đổi thành “Gửi yêu cầu cho …”", /Gửi yêu cầu cho/.test(E.$("[data-act=nt-submit]", sh).textContent));
    E.click(E.$("[data-act=nt-submit]", sh)); await flush();
    const cw = E.last("assignment.create_with_task");
    ok("Cần đồng ý (1 người) → assignment.create_with_task(recipient)", cw && cw.args.subject === "Cần đồng ý" && cw.args.recipient === U2 && cw.args.recipients === undefined);
    E.w.PMR.newTask({}); await flush();
    E.$(".pmr-title-in", sh).value = "Lỗi server";
    E.fail["tasks.create"] = "Dự án đã đóng";
    E.click(E.$("[data-act=nt-submit]", sh)); await flush();
    ok("create lỗi → giữ ngăn kéo + giữ dữ liệu + toast lỗi server", sh.classList.contains("pmr-on") && E.$(".pmr-title-in", sh).value === "Lỗi server" && E.toastText().includes("Dự án đã đóng") && !E.$("[data-act=nt-submit]", sh).disabled);
    ok("Cần đồng ý bật nhưng không chọn ai → vẫn tạo việc thường (tasks.create)", !!E.last("tasks.create") && E.last("tasks.create").args.subject === "Lỗi server");
    const qd = E.w.PMR._pure.quickDue;
    ok("Hạn nhanh: Hôm nay ≠ Cuối tuần (thứ Sáu → thứ Sáu tuần sau), Cuối tuần luôn là thứ Sáu", qd("today") !== qd("weekend") && new Date(qd("weekend") + "T00:00:00").getDay() === 5, qd("today") + " / " + qd("weekend"));
    const plan = E.w.PMR._pure.buildCreatePlan({ subject: "x", assignees: [U2, U3], ask: true, split: true, auto: false, review: false, steps: [], labels: [], due: "", time: "", rep: false, priority: "Medium", project: "" });
    ok("Cần đồng ý + Mỗi người một việc → recipients + split_per_assignee (SPEC mục 7)", plan.method === "assignment.create_with_task" && JSON.parse(plan.args.recipients).length === 2 && plan.args.split_per_assignee === 1 && plan.args.auto_close === 0);
  });

  /* ---------------- Dự án + nhật ký cá nhân ---------------- */
  await block('Theo dõi (CC) #13', async () => {
    const E = makeEnv();
    E.w.PMR.newTask({}); await flush();
    const sh = E.sheet();
    ok("form Giao việc có hàng “Theo dõi (CC)”", !!E.$(".pmr-fl-cc .pmr-cc-chips", sh));
    E.$(".pmr-title-in", sh).value = "Monthly Plan 11";
    E.click(E.byText(".pmr-link", "+ Thêm người", sh)); await flush();
    E.click(E.$('.pmr-picker [data-act=pick][data-u="' + U3 + '"]', sh)); await flush(8);
    ok("chọn người phòng khác → gọi cc_suggest, tự thêm trưởng phòng (chip “trưởng phòng”)", E.last("pm_inbox.cc_suggest") && E.$$(".pmr-cc-chips .pmr-pc-auto", sh).length === 1 && E.$(".pmr-cc-chips", sh).textContent.includes("Hương Lê"));
    E.click(E.$('.pmr-cc-chips [data-act=nt-cc-rm][data-u="' + BOSS + '"]', sh)); await flush();
    E.click(E.byText(".pmr-link", "+ Thêm người", sh)); await flush();
    E.click(E.$('.pmr-picker [data-act=pick][data-u="' + U2 + '"]', sh)); await flush(8);
    ok("bỏ CC tự động → không bị thêm lại khi đổi người nhận", !E.$$(".pmr-cc-chips .pmr-pc", sh).some(x => x.textContent.includes("Hương Lê")));
    E.click(E.byText(".pmr-link", "+ Thêm", E.$(".pmr-fl-cc", sh))); await flush();
    E.click(E.$('.pmr-fl-cc .pmr-picker [data-act=pick][data-u="' + BOSS + '"]', sh)); await flush();
    ok("thêm CC tay được", E.$$(".pmr-cc-chips .pmr-pc", sh).some(x => x.textContent.includes("Hương Lê")) && !E.$(".pmr-cc-chips .pmr-pc-auto", sh));
    E.click(E.$("[data-act=tog][data-k=ask]", sh));
    E.click(E.$("[data-act=nt-submit]", sh)); await flush(10);
    const cr = E.last("tasks.create");
    ok("giao → tasks.create(cc=[Hương Lê]) gửi danh sách cuối cùng", cr && JSON.parse(cr.args.cc).map(x => x.user).join() === BOSS, cr && cr.args.cc);
    E.w.PMR.newTask({}); await flush();
    E.$(".pmr-title-in", sh).value = "Có trưởng phòng";
    E.click(E.byText(".pmr-link", "+ Thêm người", sh)); await flush();
    E.click(E.$('.pmr-picker [data-act=pick][data-u="' + BOSS + '"]', sh)); await flush();
    E.click(E.$('.pmr-picker [data-act=pick][data-u="' + U3 + '"]', sh)); await flush(8);
    ok("chọn cả trưởng phòng lẫn nhân viên → gợi ý (không tự đổi)", !!E.$(".pmr-cc-conf", sh) && E.$$(".pmr-chips .pmr-pc", sh).length === 2);
    E.click(E.$("[data-act=nt-cc-move]", sh)); await flush(8);
    ok("“Chuyển sang Theo dõi” → bỏ khỏi người nhận, vào CC", E.$$(".pmr-chips .pmr-pc", sh).length === 1 && E.$(".pmr-cc-chips", sh).textContent.includes("Hương Lê"));
    const plan = E.w.PMR._pure.buildCreatePlan({ subject: "x", assignees: [U2], ask: true, split: false, auto: false, review: false, steps: [], labels: [], due: "", time: "", rep: false, priority: "Medium", project: "", cc: [{ user: BOSS, for: [] }], ccOff: [], ccReady: true });
    ok("chế độ Cần đồng ý cũng gửi cc", plan.method === "assignment.create_with_task" && JSON.parse(plan.args.cc)[0].user === BOSS);
    E.db.tasks["T-1"].followers = [{ user: U2, full_name: "Lan Anh", source: "Tự động", inherited: 0 }];
    await E.w.PMR.openTask("T-1"); await flush();
    ok("chi tiết việc: hàng “Theo dõi” hiện người CC; người nhận (không sửa được ds) thấy nút “Theo dõi việc này”? → không, vì là người nhận", sh.textContent.includes("Theo dõi") && sh.textContent.includes("Lan Anh") && !E.byText(".pmr-link", "Theo dõi việc này", sh));
    E.db.tasks["T-1"].can_edit = 0; E.db.tasks["T-1"].task._assign = JSON.stringify([U2]);
    await E.w.PMR.openTask("T-1"); await flush();
    E.click(E.byText(".pmr-link", "Theo dõi việc này", sh)); await flush();
    ok("người xem → “Theo dõi việc này” → set_followers(add=[me])", E.last("tasks.set_followers") && JSON.parse(E.last("tasks.set_followers").args.add)[0] === ME);
    delete E.db.tasks["T-1"].followers; delete E.db.tasks["T-1"].can_edit; E.db.tasks["T-1"].task._assign = JSON.stringify([ME]);
    E.w.PMR.closeSheet();
    await E.w.PMR.render.given(E.main, "follow"); await flush();
    ok("Tôi đã giao → tab “Tôi theo dõi”: có người giao, chỉ nút Mở (không Nhắc/Đóng)", E.$('[data-act=gtab][data-tab=follow][aria-selected=true]', E.main) && E.main.textContent.includes("Lan Anh giao") && !E.byText(".pmr-btn", "Nhắc", E.main) && !E.byText(".pmr-btn", "Đóng việc", E.main) && !!E.byText(".pmr-btn", "Mở", E.main));
  });

  /* ---------------- u1 03/11: giao việc nhanh + chi tiết việc dễ đọc ---------------- */
  await block('Gợi ý hạn từ tên việc (parseDue) #14', async () => {
    const E = makeEnv(), pd = E.w.PMR._pure.parseDue, B0 = new E.w.Date(2026, 10, 3, 9, 0);   /* thứ Ba 03/11/2026 09:00 */
    const r = (s) => pd(s, B0) || {};
    ok("“Báo cáo GMV thứ 6” → T6 06/11, tên còn “Báo cáo GMV”", r("Báo cáo GMV thứ 6").due === "2026-11-06" && r("Báo cáo GMV thứ 6").rest === "Báo cáo GMV" && r("Báo cáo GMV thứ 6").from === "thứ 6");
    ok("“gửi file mai 17h” → 04/11 17:00, tên “gửi file”", r("gửi file mai 17h").due === "2026-11-04" && r("gửi file mai 17h").time === "17:00" && r("gửi file mai 17h").rest === "gửi file");
    ok("“Nộp hợp đồng trước 25/11” → 25/11, bỏ cả chữ “trước”", r("Nộp hợp đồng trước 25/11").due === "2026-11-25" && r("Nộp hợp đồng trước 25/11").rest === "Nộp hợp đồng");
    ok("“Họp 3h chiều t2 tuần sau” → T2 09/11 15:00", r("Họp 3h chiều t2 tuần sau").due === "2026-11-09" && r("Họp 3h chiều t2 tuần sau").time === "15:00" && r("Họp 3h chiều t2 tuần sau").rest === "Họp");
    ok("cuối tuần → thứ Sáu, cuối tháng → 30/11, hôm nay, ngày kia", r("Chốt số cuối tuần").due === "2026-11-06" && r("Đối soát cuối tháng").due === "2026-11-30" && r("gửi hôm nay").due === "2026-11-03" && r("gọi ngày kia").due === "2026-11-05");
    ok("chỉ có giờ: 15h → hôm nay (còn kịp), 8h → ngày mai (đã qua)", r("gọi brand 15h").due === "2026-11-03" && r("gọi brand 15h").time === "15:00" && r("gọi brand 8h30").due === "2026-11-04");
    ok("chữ có dấu tách rời (NFD, gõ trên Mac) vẫn nhận", r("báo cáo thứ 6".normalize("NFD")).due === "2026-11-06");
    ok("không gợi ý nhầm: ngày đã qua, tên người “Mai”, “T6/2026”, “làm 2h”, “Thu 2 triệu”, “thứ tự”",
      ["Báo cáo 15/10", "Gửi chị Mai bảng giá", "Kiểm kho T6/2026", "làm 2h", "Thu 2 triệu tiền cọc", "Sắp thứ tự SKU", "Gia hạn Metric"].every(s => pd(s, B0) === null),
      ["Báo cáo 15/10", "Gửi chị Mai bảng giá", "Kiểm kho T6/2026", "làm 2h", "Thu 2 triệu tiền cọc", "Sắp thứ tự SKU", "Gia hạn Metric"].filter(s => pd(s, B0) !== null).join(" | "));
  });

  await block('Một bộ đọc hạn cho form và ô ghi nhanh (parseDue tail) #14b', async () => {
    const E = makeEnv(), pd = E.w.PMR._pure.parseDue, B0 = new E.w.Date(2026, 10, 3, 9, 0);
    ok("“Chuẩn bị 11.11” / “Deal 12.12” (tên đợt sale) → không gợi ý", pd("Chuẩn bị 11.11", B0) === null && pd("Deal 12.12 Shopee", B0) === null);
    ok("“Họp CN Hà Nội” (chi nhánh) → không gợi ý; “Dọn kho cn” ở cuối ô ghi nhanh → Chủ nhật", pd("Họp CN Hà Nội", B0) === null && pd("Dọn kho cn", { base: B0, tail: true }).due === "2026-11-08");
    ok("“mai 3h” → 15:00, “sáng mai 6h” → 06:00, “lúc 2h” → 14:00", pd("gọi mai 3h", B0).time === "15:00" && pd("chạy sáng mai 6h", B0).time === "06:00" && pd("gọi lúc 2h", B0).time === "14:00");
    ok("tail: “Báo cáo cuối tháng” giữ nguyên tên (tên việc định kỳ), form vẫn gợi ý", pd("Báo cáo cuối tháng", { base: B0, tail: true }) === null && pd("Báo cáo cuối tháng", B0).due === "2026-11-30");
    ok("tail: “Báo cáo thu 6” (không dấu) → T6; giữa câu “Thu 2 triệu” vẫn không", pd("Báo cáo thu 6", { base: B0, tail: true }).due === "2026-11-06" && pd("Thu 2 triệu tiền cọc", { base: B0, tail: true }) === null);
  });

  await block('Giao việc nhanh: Tôi mặc định + Enter + gợi ý hạn #15', async () => {
    const E = makeEnv();
    E.w.PMR.newTask({}); await flush();
    const sh = E.sheet(), ti = E.$(".pmr-title-in", sh), sb = () => E.$("[data-act=nt-submit]", sh);
    ok("mở từ nút chung: Người nhận có sẵn chip “Tôi” (nằm trong markup), nút “Tạo việc cho tôi”", E.$(".pmr-chips .pmr-pc-self", sh).textContent.includes("Tôi") && sb().textContent === "Tạo việc cho tôi");
    ok("ô tên có ví dụ cách ghi hạn", /thứ 6/.test(ti.getAttribute("placeholder")));
    ok("chưa gõ gì: không có gợi ý hạn", !E.$(".pmr-sug", sh));
    E.type(ti, "Báo cáo GMV thứ 6");
    const sug = E.$(".pmr-sug", sh);
    ok("gõ “… thứ 6” → hiện gợi ý “Đặt hạn …” (chưa tự đặt)", sug && sug.textContent.includes("thứ 6") && !E.$(".pmr-nt-date", sh).value);
    E.click(sug); await flush();
    let fri = 0; while (new Date(dayOff(fri) + "T00:00:00").getDay() !== 5) fri++;
    ok("bấm gợi ý → đặt hạn T6, bỏ “thứ 6” khỏi tên, gợi ý biến mất", E.$(".pmr-nt-date", sh).value === dayOff(fri) && ti.value === "Báo cáo GMV" && !E.$(".pmr-sug", sh), E.$(".pmr-nt-date", sh).value + " / " + ti.value);
    const kc = new E.w.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true, isComposing: true });
    ti.dispatchEvent(kc); await flush();
    ok("Enter khi đang gõ dấu (IME) → không gửi", !E.last("tasks.create"));
    ti.dispatchEvent(new E.w.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })); await flush(10);
    const cr = E.last("tasks.create");
    ok("Enter ở ô tên → tạo ngay, giao cho chính mình, kèm hạn đã chọn", cr && cr.args.subject === "Báo cáo GMV" && JSON.parse(cr.args.assignees).join() === ME && cr.args.exp_end_date === dayOff(fri) && !E.last("assignment.create_with_task"), cr && JSON.stringify(cr.args));
    ok("tạo xong: đóng form + toast “… cho bạn” có nút Mở", !sh.classList.contains("pmr-on") && E.toastText().includes("cho bạn") && !!E.byText(".pmr-toast-b", "Mở"));
    E.w.PMR.newTask({}); await flush();
    E.click(E.$("[data-act=nt-self-rm]", sh));
    ok("bỏ chip “Tôi” → nút “Tạo việc (chưa giao ai)”", sb().textContent === "Tạo việc (chưa giao ai)" && !E.$(".pmr-pc-self", sh));
    E.$(".pmr-title-in", sh).value = "Việc chung của dự án";
    E.click(sb()); await flush(10);
    ok("chưa giao ai → tasks.create không có assignees", E.last("tasks.create").args.subject === "Việc chung của dự án" && E.last("tasks.create").args.assignees === undefined);
    E.w.PMR.newTask({}); await flush();
    E.click(E.byText(".pmr-link", "+ Thêm người", sh)); await flush();
    E.click(E.$('.pmr-picker [data-act=pick][data-u="' + U2 + '"]', sh)); await flush(8);
    ok("chọn người khác → thay chỗ “Tôi” (không giao kèm mình), nút “Gửi yêu cầu cho Lan Anh”", !E.$(".pmr-pc-self", sh) && E.$$(".pmr-chips .pmr-pc", sh).length === 1 && sb().textContent === "Gửi yêu cầu cho Lan Anh");
    E.click(E.$("[data-act=tog][data-k=ask]", sh));
    ok("tắt Cần đồng ý, 1 người → nút “Giao cho Lan Anh”", sb().textContent === "Giao cho Lan Anh");
    E.w.PMR.closeSheet();
    E.w.PMR.newTask({ project: "P1" }); await flush();
    ok("mở từ dự án: không tự giao cho mình (việc chung của dự án)", !E.$(".pmr-pc-self", sh) && sb().textContent === "Tạo việc (chưa giao ai)");
    E.w.PMR.closeSheet();
    const plan = E.w.PMR._pure.buildCreatePlan({ subject: "x", assignees: [], ask: false, split: false, steps: [], labels: [], due: "", time: "", rep: false, priority: "Medium", project: "", desc: "Dòng 1\nFile mẫu https://x.vn/m" });
    ok("mô tả gõ thường → giữ xuống dòng + link bấm được khi lưu", /Dòng 1<br>File mẫu <a href="https:\/\/x\.vn\/m"/.test(plan.args.description), plan.args.description);
    ok("CSS điện thoại: ô nhập 16px (iOS không tự phóng to), nút ≥40px, ẩn gợi ý phím tắt trên màn cảm ứng",
      /@media \(max-width:640px\)\{[^}]*\.pmr-sheet \.pmr-in,[^}]*font-size:16px/.test(CSS) && /min-height:40px/.test(CSS) && /@media \(hover:none\),\(max-width:640px\)\{\.pmr-kbd\{display:none\}/.test(CSS));
  });

  await block('Chi tiết việc: nút việc tiếp theo + mô tả lên đầu #16', async () => {
    const E = makeEnv(), sh0 = () => E.sheet(), cta = () => E.$(".pmr-cta", sh0());
    E.db.tasks["T-1"].task.description = "<p>Dùng file mẫu https://x.vn/mau.xlsx. Gửi trước 17h</p>";
    await E.w.PMR.openTask("T-1"); await flush();
    const sh = sh0();
    ok("người nhận, Đang làm → nút chính “Đánh dấu Xong” ngoài thanh trạng thái, được focus", cta() && cta().textContent === "Đánh dấu Xong" && !cta().closest(".pmr-statusbar") && E.w.document.activeElement === cta());
    const fls = E.$$(".pmr-main .pmr-sh-b .pmr-fl > .pmr-lb", sh).map(x => x.textContent);
    ok("Mô tả nằm ngay sau Hạn (trước Theo dõi / Dự án)", fls[0] === "Hạn" && fls[1] === "Mô tả", fls.join(","));
    const a = E.$('.pmr-desc a[href="https://x.vn/mau.xlsx"]', sh);
    ok("URL trong mô tả thành link mở tab mới, dấu chấm cuối câu không dính vào link", a && a.getAttribute("target") === "_blank" && /noopener/.test(a.getAttribute("rel")) && E.$(".pmr-desc", sh).textContent.includes("mau.xlsx. Gửi"));
    E.click(cta()); await flush();
    ok("bấm nút chính → tasks.mark_done(T-1), Xong thì nút chính biến mất", E.last("tasks.mark_done").args.name === "T-1" && !cta() && E.$(".pmr-statusbar .pmr-on", sh).textContent === "Xong");
    delete E.db.tasks["T-1"].task.description;
    E.db.tasks["T-1"].task.workflow_state = "To Do";
    await E.w.PMR.openTask("T-1"); await flush();
    ok("Chưa làm → nút “Bắt đầu làm”", cta() && cta().textContent === "Bắt đầu làm");
    E.click(cta()); await flush();
    ok("Bắt đầu làm → set_status(In Progress), nút đổi sang “Đánh dấu Xong”", E.last("tasks.set_status").args.action === "In Progress" && cta().textContent === "Đánh dấu Xong");
    E.db.tasks["T-1"].task.workflow_state = "In Progress";
    await E.w.PMR.openTask("T-R"); await flush();
    ok("cần kiểm tra → nút chính “Gửi kiểm tra”", cta() && cta().textContent === "Gửi kiểm tra");
    E.click(cta()); await flush();
    ok("gửi kiểm tra xong → “Đang chờ Hương Lê kiểm tra”, không còn nút chính", !cta() && E.$(".pmr-cta-wait", sh).textContent === "Đang chờ Hương Lê kiểm tra");
    await E.w.PMR.openTask("T-G"); await flush();
    ok("người giao, việc Đang làm → không có nút chính (không bấm Xong thay người nhận)", !cta() && !E.$(".pmr-cta-wait", sh));
    E.db.tasks["T-G"].task.workflow_state = "Review";
    await E.w.PMR.openTask("T-G"); await flush();
    ok("người giao, Chờ duyệt → “Duyệt và đóng việc”", cta() && cta().textContent === "Duyệt và đóng việc");
    E.click(cta()); await flush();
    ok("Duyệt và đóng → tasks.mark_done(T-G)", E.last("tasks.mark_done").args.name === "T-G");
    E.db.tasks["T-G"].task.workflow_state = "In Progress";
    E.db.tasks["T-1"].can_edit = 0;
    await E.w.PMR.openTask("T-1"); await flush();
    ok("chỉ xem → không có nút chính, dòng Chỉ xem ngắn gọn", !cta() && E.$(".pmr-ro-hint", sh).textContent.length < 110);
    delete E.db.tasks["T-1"].can_edit;
    const P = E.w.PMR._pure;
    ok("sanitize: link có sẵn không bị bọc lần 2, javascript: không thành link", (P.sanitize('<a href="https://a.vn">https://a.vn</a>').match(/<a /g) || []).length === 1 && !/<a/.test(P.sanitize("javascript:alert(1)")));
  });

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
      const std = ["name", "subject", "project", "project_name", "workflow_state", "exp_end_date", "owner", "_assign", "priority", "creation", "parent_task"];   /* trường gốc của Task (doc.as_dict) */
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

  /* ---------------- tester t2 (03/11): dữ liệu thật + race + chỉ xem + a11y ---------------- */
  await block('t2: giờ "0:00:00" + đổi hạn xoá giờ #14', async () => {
    const E = makeEnv(), P = E.w.PMR._pure;
    ok("t2 hạn: pm_end_time “0:00:00” (Time trống) không hiện “00:00”", P.dueInfo(dayOff(0), "0:00:00").text === "Hôm nay" && P.dueInfo(dayOff(1) + " 00:00:00", "0:00:00").text === "Ngày mai", P.dueInfo(dayOff(0), "0:00:00").text);
    E.db.tasks["T-G"].task.exp_end_date = dayOff(1) + " 00:00:00"; E.db.tasks["T-G"].task.pm_end_time = "0:00:00";
    await E.w.PMR.openTask("T-G"); await flush();
    const sh = E.sheet();
    ok("t2 chi tiết: hạn Datetime + “0:00:00” → không có “· 00:00”", !/00:00/.test(E.$(".pmr-due-sec", sh).textContent), E.$(".pmr-due-sec", sh).textContent);
    E.click(E.byText(".pmr-link", "Đổi hạn", sh)); await flush();
    ok("t2 Đổi hạn: ô giờ trống khi “0:00:00”, ô ngày dạng YYYY-MM-DD", E.$(".pmr-due-t", sh).value === "" && E.$(".pmr-due-d", sh).value === dayOff(1));
    E.db.tasks["T-G"].task.pm_end_time = "17:00:00";
    await E.w.PMR.openTask("T-G"); await flush();
    E.click(E.byText(".pmr-link", "Đổi hạn", sh)); await flush();
    E.$(".pmr-due-t", sh).value = "";
    E.click(E.byText(".pmr-btn", "Lưu hạn", sh)); await flush();
    const up = E.last("tasks.update");
    ok("t2 Đổi hạn: xoá ô giờ → gửi pm_end_time=\"\" (xoá giờ), hạn không còn 17:00", up && up.args.pm_end_time === "" && up.args.exp_end_date === dayOff(1) && !/17:00/.test(E.$(".pmr-due-sec", sh).textContent), up && JSON.stringify(up.args));
  });
  await block('t2: race phản hồi muộn sau khi đã chuyển việc #15', async () => {
    const E = makeEnv(), sh = () => E.sheet();
    let rej = null;
    E.H["tasks.set_status"] = () => new Promise((_, r) => { rej = r; });
    await E.w.PMR.openTask("T-1"); await flush();
    E.click(E.byText(".pmr-statusbar button", "Chưa làm", sh())); await flush();
    await E.w.PMR.openTask("T-S2"); await flush();
    rej(smErr("Không có quyền")); await flush();
    ok("t2 race trạng thái: lỗi của việc cũ không hoàn nguyên thanh trạng thái của việc đang mở", E.$(".pmr-statusbar .pmr-on", sh()).textContent === "Chưa làm" && E.$(".pmr-crumb2", sh()).textContent === "T-S2");
    E.hold["comments.add"] = [];
    await E.w.PMR.openTask("T-1"); await flush();
    E.$(".pmr-cm-in", sh()).value = "Bình luận của T-1";
    E.click(E.byText(".pmr-btn", "Gửi", sh())); await flush();
    await E.w.PMR.openTask("T-R"); await flush();
    E.hold["comments.add"].forEach(f => f()); delete E.hold["comments.add"]; await flush();
    ok("t2 race bình luận: bình luận gửi ở T-1 không hiện trong T-R", !sh().textContent.includes("Bình luận của T-1") && E.$(".pmr-side-n", sh()).textContent === "1");
    E.hold["checklist.set_item"] = [];
    await E.w.PMR.openTask("T-1"); await flush();
    const box = E.$$(".pmr-ck input", sh())[1]; box.checked = true; E.change(box); await flush();
    await E.w.PMR.openTask("T-R"); await flush();
    E.hold["checklist.set_item"].forEach(f => f()); delete E.hold["checklist.set_item"]; await flush();
    ok("t2 race bước: tích bước ở T-1 không ghi đè số bước của T-R", E.byText(".pmr-stabs button", "Các bước", sh()).textContent === "Các bước");
    E.db.tasks["T-1"].can_edit = 0; E.db.tasks["T-1"].task._assign = JSON.stringify([U2]);
    E.hold["tasks.set_followers"] = [];
    await E.w.PMR.openTask("T-1"); await flush();
    E.click(E.byText(".pmr-link", "Theo dõi việc này", sh())); await flush();
    await E.w.PMR.openTask("T-R"); await flush();
    E.hold["tasks.set_followers"].forEach(f => f()); delete E.hold["tasks.set_followers"]; await flush();
    ok("t2 race theo dõi: xong set_followers của T-1 không kéo ngăn kéo về T-1", E.$(".pmr-crumb2", sh()).textContent === "T-R" && E.last("tasks.get").args.name === "T-R");
    delete E.db.tasks["T-1"].can_edit; E.db.tasks["T-1"].task._assign = JSON.stringify([ME]);
    E.hold["tasks.create"] = [];
    await E.w.PMR.openTask("T-S"); await flush();
    E.$(".pmr-sub-in", sh()).value = "Việc con chậm";
    E.click(E.$("[data-act=sub-add]", sh())); await flush();
    E.w.PMR.closeSheet(); await flush();
    E.hold["tasks.create"].forEach(f => f()); delete E.hold["tasks.create"]; await flush();
    ok("t2 race việc con: thêm việc con xong sau khi đã đóng ngăn kéo → không tự mở lại", !sh().classList.contains("pmr-on"));
    E.hold["comments.upload"] = []; E.H["comments.upload"] = () => ({ file_url: "/private/files/a.png", is_image: 1, file_name: "a.png" });
    await E.w.PMR.openTask("T-1"); await flush();
    const fin = E.$(".pmr-file", sh());
    Object.defineProperty(fin, "files", { value: [new E.w.File(["x"], "a.png", { type: "image/png" })], configurable: true });
    E.change(fin); await tick(20); await flush();
    await E.w.PMR.openTask("T-R"); await flush();
    E.hold["comments.upload"].forEach(f => f()); delete E.hold["comments.upload"]; await flush();
    ok("t2 race đính kèm: file tải lên cho T-1 không gắn vào ô bình luận của T-R", E.$$(".pmr-atts .pmr-pc", sh()).length === 0);
  });
  await block('t2: onClose của host + Esc khi đang viết + focus chỉ xem #16', async () => {
    const E = makeEnv(), sh = () => E.sheet();
    let closed = 0;
    await E.w.PMR.openTask("T-S2", { onClose: () => { closed++; } }); await flush();
    E.click(E.$("[data-act=open-sub][data-task=T-S]", sh())); await flush();
    E.w.document.dispatchEvent(new E.w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    ok("t2 mở việc cha trong ngăn kéo rồi đóng → onClose của host vẫn được gọi (hash #task không kẹt)", closed === 1 && !sh().classList.contains("pmr-on"), "closed=" + closed);
    await E.w.PMR.openTask("T-1"); await flush();
    E.$(".pmr-cm-in", sh()).value = "đang viết dở";
    E.w.document.dispatchEvent(new E.w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    E.click(E.$(".pmr-scrim"));
    ok("t2 Esc / bấm nền xám khi đang viết bình luận → không đóng, nhắc bấm ×", sh().classList.contains("pmr-on") && /viết dở/.test(E.toastText()) && E.$(".pmr-cm-in", sh()).value === "đang viết dở");
    E.click(E.$("[data-act=close]", sh()));
    ok("t2 bấm × vẫn đóng được", !sh().classList.contains("pmr-on"));
    E.db.tasks["T-S"].can_edit = 0;
    await E.w.PMR.openTask("T-S"); await flush();
    const ae = E.w.document.activeElement;
    ok("t2 chỉ xem: focus vào trong popup (nút trạng thái bị khoá không nhận focus)", sh().contains(ae) && !ae.disabled, ae && ae.outerHTML.slice(0, 60));
    delete E.db.tasks["T-S"].can_edit;
    E.db.tasks["T-P"].can_edit = 0;
    await E.w.PMR.openTask("T-P", { tab: "people" }); await flush();
    ok("t2 chỉ xem: tab Từng người không có “+ Thêm người” (server require_edit sẽ từ chối)", !E.byText(".pmr-link", "+ Thêm người", sh()));
    delete E.db.tasks["T-P"].can_edit;
  });
  await block('t2: Giao việc — CC đang gợi ý + việc cha sau lỗi #17', async () => {
    const E = makeEnv(), sh = () => E.sheet();
    E.w.PMR.newTask({}); await flush();
    E.$(".pmr-title-in", sh()).value = "Giao nhanh";
    E.click(E.$("[data-act=tog][data-k=ask]", sh()));
    E.click(E.byText(".pmr-link", "+ Thêm người", sh())); await flush();
    E.click(E.$('.pmr-picker [data-act=pick][data-u="' + U2 + '"]', sh())); await flush(8);
    E.hold["pm_inbox.cc_suggest"] = [];
    E.click(E.$('.pmr-picker [data-act=pick][data-u="' + U3 + '"]', sh())); await flush();
    E.click(E.$("[data-act=nt-submit]", sh())); await flush();
    E.hold["pm_inbox.cc_suggest"].forEach(f => f()); delete E.hold["pm_inbox.cc_suggest"]; await flush(10);
    const cr = E.last("tasks.create");
    ok("t2 CC: bấm Giao khi gợi ý CC còn đang chạy → vẫn CC trưởng phòng (không gửi cc=[] cũ)", cr && cr.args.cc && JSON.parse(cr.args.cc).some(x => x.user === BOSS), cr && cr.args.cc);
    E.w.PMR.newTask({}); await flush();
    E.$(".pmr-title-in", sh()).value = "Có việc cha";
    E.click(E.byText(".pmr-link", "+ Chọn việc cha", sh())); await flush();
    const ps = E.$(".pmr-nt-parent", sh()); ps.value = "A4";
    E.fail["tasks.create"] = "Lỗi tạm";
    E.click(E.$("[data-act=nt-submit]", sh())); await flush();
    ps.value = "";
    E.click(E.$("[data-act=nt-submit]", sh())); await flush(10);
    ok("t2 việc cha: lỗi rồi chọn lại “Không thuộc việc nào” → không còn gửi parent_task cũ", E.last("tasks.create") && !E.last("tasks.create").args.parent_task, E.last("tasks.create") && E.last("tasks.create").args.parent_task);
  });
  await block('t2: màn danh sách — phản hồi cũ về muộn không vẽ đè #18', async () => {
    const E = makeEnv();
    E.hold["pm_inbox.given"] = [];
    E.w.PMR.render.given(E.main, "run"); E.w.PMR.render.given(E.main, "rep"); await flush();
    const hs = E.hold["pm_inbox.given"]; delete E.hold["pm_inbox.given"];
    hs[1](); await flush(); hs[0](); await flush();
    ok("t2 Tôi đã giao: bấm tab nhanh, phản hồi tab cũ về sau không đè tab đang chọn", !!E.$('[data-act=gtab][data-tab=rep][aria-selected=true]', E.main) && !!E.$('tr[data-rule="REC-1"]', E.main));
    E.hold["tasks.list"] = [];
    E.w.PMR.render.allWork(E.main, "list"); await flush();
    await E.w.PMR.render.allWork(E.main, "due", { renderDue: el => { el.innerHTML = "<p class=host-due>host</p>"; } });
    E.hold["tasks.list"].forEach(f => f()); delete E.hold["tasks.list"]; await flush();
    ok("t2 Tất cả việc: chuyển sang Theo hạn khi danh sách chưa tải xong → lịch của host không bị danh sách đè", !!E.$(".host-due", E.main) && !E.$("tbody tr[data-task]", E.main));
  });
  /* ---------------- u2 03/11: màn danh sách thân thiện hơn ---------------- */
  await block('u2: ghi nhanh — hiểu hạn trong câu #u2a', async () => {
    const E = makeEnv(), P = E.w.PMR._pure, wd = (n) => { const d = new Date(); return ymd(new Date(d.getFullYear(), d.getMonth(), d.getDate() + ((n - d.getDay() + 7) % 7))); };
    const q = s => P.parseQuick(s), eq = (s, subject, due, time) => { const r = q(s); return r.subject === subject && r.due === due && r.time === time; };
    ok("parseQuick: “Gọi khách mai 10h” → mai 10:00", eq("Gọi khách mai 10h", "Gọi khách", dayOff(1), "10:00"));
    ok("parseQuick: “Báo cáo thứ 6” / “thu 6” / “t6” → thứ Sáu gần nhất", eq("Báo cáo thứ 6", "Báo cáo", wd(5), null) && eq("Báo cáo thu 6", "Báo cáo", wd(5), null) && eq("Báo cáo t6", "Báo cáo", wd(5), null));
    ok("parseQuick: “Họp 3h chiều mai” / “Họp mai 3h” → 15:00; “làm 2h” (thời lượng) không đoán", eq("Họp 3h chiều mai", "Họp", dayOff(1), "15:00") && eq("Họp mai 3h", "Họp", dayOff(1), "15:00") && eq("làm 2h", "làm 2h", null, null));
    ok("parseQuick: “Nộp hồ sơ trước thứ 2 lúc 9h30” → bỏ chữ “trước”", eq("Nộp hồ sơ trước thứ 2 lúc 9h30", "Nộp hồ sơ", wd(1), "09:30"));
    const nx = new Date(), y = nx.getFullYear(), past = new Date(y, 10, 25) < new Date(nx.getFullYear(), nx.getMonth(), nx.getDate());
    ok("parseQuick: “Báo giá 25/11” → 25/11 (đã qua thì không đoán, như form Giao việc), “ngày mốt” → +2", (past ? eq("Báo giá 25/11", "Báo giá 25/11", null, null) : eq("Báo giá 25/11", "Báo giá", y + "-11-25", null)) && eq("Đi ngân hàng ngày mốt", "Đi ngân hàng", dayOff(2), null));
    ok("parseQuick dùng chung parseDue: cụm ngày giữa câu không tính (“Gửi mai cho chị Lan”), cùng câu cho cùng hạn", eq("Gửi mai cho chị Lan", "Gửi mai cho chị Lan", null, null) && P.parseDue("Gọi khách mai 10h").due === q("Gọi khách mai 10h").due);
    ok("parseQuick: không đoán bừa — tên “Mai”, “một”, “này”, 31/02, 11.11, chỉ có hạn", ["Gửi file cho chị Mai", "Gửi thêm một", "Làm cái này", "Thanh toán 31/02", "Chuẩn bị 11.11", "mai"].every(s => { const r = q(s); return r.subject === s && r.due === null; }));
  });

  await block('u2: Việc của tôi — nhóm theo hạn + hành động trên dòng + ghi nhanh #u2b', async () => {
    const E = makeEnv();
    const rows = [
      { name: "M1", subject: "Báo cáo trễ", workflow_state: "In Progress", exp_end_date: dayOff(-2), owner: BOSS, project_name: "ANDROS - SHOPEE" },
      { name: "M2", subject: "Gọi khách", workflow_state: "To Do", exp_end_date: dayOff(0), pm_end_time: "15:00:00", owner: ME },
      { name: "M3", subject: "Lên kế hoạch", workflow_state: "To Do", exp_end_date: dayOff(3), owner: BOSS },
      { name: "M4", subject: "Đọc tài liệu", workflow_state: "To Do", exp_end_date: null, owner: ME },
      { name: "M5", subject: "Chờ sếp duyệt", workflow_state: "Review", exp_end_date: dayOff(-1), owner: BOSS },
      { name: "M6", subject: "Xong từ tuần trước", workflow_state: "Done", exp_end_date: dayOff(-5), owner: ME },
      { name: "M7", subject: "Việc chia người", workflow_state: "In Progress", exp_end_date: dayOff(2), owner: ME, is_group: 1 }];
    E.w.PMR.render.myDay(E.main, { rows }); await flush();
    const grp = k => E.$(`.pmr-md-g[data-g="${k}"]`, E.main), inG = (k, t) => !!grp(k) && !!E.$(`.pmr-md-row[data-task="${t}"]`, grp(k));
    ok("myDay: Quá hạn / Hôm nay / Sắp tới mở sẵn, đúng việc từng nhóm", inG("late", "M1") && inG("today", "M2") && inG("soon", "M3") && grp("late").tagName === "DIV" && grp("soon").tagName === "DIV");
    ok("myDay: Chưa có hạn + Chờ duyệt thu gọn (details, có số), việc Xong cũ không hiện", grp("nodue").tagName === "DETAILS" && !grp("nodue").open && inG("wait", "M5") && grp("wait").textContent.includes("1") && !E.$('[data-task="M6"]', E.main));
    const r1 = E.$('.pmr-md-row[data-task="M1"]', E.main), r2 = E.$('.pmr-md-row[data-task="M2"]', E.main), r5 = E.$('.pmr-md-row[data-task="M5"]', E.main);
    ok("myDay: việc người khác giao có “Xin dời hạn” + tên người giao; việc tự ghi có “Đổi hạn”", !!E.byText(".pmr-link", "Xin dời hạn", r1) && E.$(".pmr-m", r1).textContent === "ANDROS - SHOPEE · Hương Lê giao" && !!E.byText(".pmr-link", "Đổi hạn", r2) && !E.$(".pmr-m", r2));
    ok("myDay: Chưa làm có “Bắt đầu”, Đang làm không có; Chờ duyệt không có nút", !!E.byText(".pmr-btn", "Bắt đầu", r2) && !E.byText(".pmr-btn", "Bắt đầu", r1) && !!E.byText(".pmr-btn", "Xong", r1) && !E.$(".pmr-btn", r5));
    ok("myDay: việc cha “mỗi người một việc” không có nút Xong (server sẽ chặn vì còn việc con)", !E.byText(".pmr-btn", "Xong", E.$('.pmr-md-row[data-task="M7"]', E.main)));
    E.click(E.byText(".pmr-btn", "Bắt đầu", r2)); await flush();
    ok("myDay: Bắt đầu → set_status(In Progress) + pill Đang làm (không mở popup)", E.last("tasks.set_status").args.name === "M2" && E.last("tasks.set_status").args.action === "In Progress" && E.$('.pmr-md-row[data-task="M2"] .pmr-st', E.main).textContent === "Đang làm" && !E.sheet());
    E.click(E.byText(".pmr-btn", "Xong", E.$('.pmr-md-row[data-task="M1"]', E.main))); await flush();
    ok("myDay: Xong → mark_done, dòng gạch ngang tại chỗ + toast Hoàn tác", E.last("tasks.mark_done").args.name === "M1" && E.$('.pmr-md-row[data-task="M1"]', E.main).classList.contains("pmr-done") && E.toastText().includes("Hoàn tác"));
    E.click(E.byText(".pmr-link", "Xin dời hạn", E.$('.pmr-md-row[data-task="M3"]', E.main))); await flush();
    ok("myDay: Xin dời hạn → mở việc ở form xin dời hạn", E.last("tasks.get").args.name === "M3" && !!E.sheet());
    E.w.PMR.closeSheet(); await flush();
    const inp = E.$(".pmr-qa-in", E.main);
    E.type(inp, "Gửi báo giá mai 10h");
    ok("ghi nhanh: gõ tới đâu báo hạn tới đó + nút Không đặt hạn", E.$(".pmr-qa-hint", E.main).textContent.includes("Hạn:") && E.$(".pmr-qa-hint", E.main).textContent.includes("10:00") && !!E.byText(".pmr-link", "Không đặt hạn", E.main));
    inp.dispatchEvent(new E.w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await flush();
    const cr = E.last("tasks.create").args;
    ok("ghi nhanh: Enter → tasks.create(tên đã bỏ hạn, hạn mai 10:00, giao cho chính mình)", cr.subject === "Gửi báo giá" && cr.exp_end_date === dayOff(1) && cr.pm_end_time === "10:00:00" && JSON.parse(cr.assignees)[0] === ME && cr.project === "");
    ok("ghi nhanh: dòng mới hiện ngay, ô trống + vẫn focus để ghi tiếp, phát pmr:changed", E.$(".pmr-qa-in", E.main).value === "" && E.w.document.activeElement === E.$(".pmr-qa-in", E.main) && !!E.$('.pmr-md-row[data-task="NEW-1"]', E.main) && E.events.some(e => e.n === "pmr:changed" && e.d.created));
    const inp2 = E.$(".pmr-qa-in", E.main); E.type(inp2, "Đặt lịch họp thứ 6");
    E.click(E.byText(".pmr-link", "Không đặt hạn", E.main));
    inp2.dispatchEvent(new E.w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await flush();
    ok("ghi nhanh: “Không đặt hạn” → giữ nguyên chữ, không gửi hạn", E.last("tasks.create").args.subject === "Đặt lịch họp thứ 6" && !E.last("tasks.create").args.exp_end_date);
    E.fail["tasks.create"] = "Không có quyền tạo việc";
    const inp3 = E.$(".pmr-qa-in", E.main); E.type(inp3, "Việc lỗi");
    inp3.dispatchEvent(new E.w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await flush();
    ok("ghi nhanh: lỗi server → giữ chữ đã gõ + toast lỗi", inp3.value === "Việc lỗi" && !inp3.disabled && E.toastText().includes("Không có quyền tạo việc"));
    const E2 = makeEnv(); E2.w.PMR.render.myDay(E2.main, { rows: [] }); await flush();
    ok("myDay rỗng: lời mời ghi việc (khuyến khích), vẫn có ô ghi nhanh", E2.main.textContent.includes("Ghi việc định làm") && !!E2.$(".pmr-qa-in", E2.main));
  });

  await block('u2: Tôi đã giao — gom việc cần bạn lên đầu, giao 1 người thấy chưa mở #u2c', async () => {
    const E = makeEnv(), base = E.H["pm_inbox.given"];
    E.H["pm_inbox.given"] = (a) => a.tab !== "run" ? base(a) : { banner: [], rules: [], batches: [
      { task: "S-OK", subject: "Bình thường", split: false, exp_end_date: dayOff(1), workflow_state: "In Progress", people: [{ user: U2, full_name: "Lan Anh", task: "S-OK", state: "In Progress", opened: true }], done_count: 0, total: 1 },
      { task: "S-UN", subject: "Chưa mở", split: false, exp_end_date: dayOff(4), workflow_state: "To Do", people: [{ user: U3, full_name: "Phương Nga", task: "S-UN", state: "To Do", opened: false }], done_count: 0, total: 1 },
      { task: "S-LATE", subject: "Trễ", split: false, exp_end_date: dayOff(-2), workflow_state: "In Progress", people: [{ user: U2, full_name: "Lan Anh", task: "S-LATE", state: "In Progress", opened: true, late: true }], done_count: 0, total: 1 },
      { task: "S-RV", subject: "Chờ duyệt", split: false, exp_end_date: dayOff(5), workflow_state: "Review", people: [{ user: U2, full_name: "Lan Anh", task: "S-RV", state: "Review", opened: true }], done_count: 0, total: 1 }] };
    await E.w.PMR.render.given(E.main, "run"); await flush();
    ok("given: thứ tự Chờ bạn duyệt → trễ → chưa mở → còn lại", E.$$(".pmr-batch", E.main).map(b => b.getAttribute("data-task")).join() === "S-RV,S-LATE,S-UN,S-OK");
    const un = E.$('.pmr-batch[data-task="S-UN"]', E.main), late = E.$('.pmr-batch[data-task="S-LATE"]', E.main), okb = E.$('.pmr-batch[data-task="S-OK"]', E.main);
    ok("given: giao 1 người → hiện “chưa mở việc” / “trễ 2 ngày” ngay trên dòng", E.$(".pmr-solo .pmr-warn", un).textContent.includes("chưa mở việc") && E.$(".pmr-solo .pmr-warn", late).textContent.includes("trễ 2 ngày") && !E.$(".pmr-solo .pmr-warn", okb));
    E.click(E.byText(".pmr-btn", "Nhắc", un)); await flush();
    ok("given: giao 1 người chưa mở → nút Nhắc → nudge(task, đúng người)", E.last("pm_inbox.nudge").args.task === "S-UN" && JSON.parse(E.last("pm_inbox.nudge").args.users)[0] === U3 && !E.byText(".pmr-btn", "Nhắc", okb));
  });

  await block('u2: Tất cả việc / Điều phối / Dự án — lọc nhớ, số đếm, KPI bấm được #u2d', async () => {
    const E = makeEnv();
    await E.w.PMR.render.allWork(E.main, "list"); await flush();
    const chip = t => E.byText(".pmr-aw-chip", t, E.main), cnt = t => +E.$(".pmr-cnt", chip(t)).textContent;
    ok("allWork: chip có số đếm đúng (Trễ hạn 1, Chưa có người 2, Của tôi 1)", cnt("Trễ hạn") === 1 && cnt("Chưa có người") === 2 && cnt("Của tôi") === 1);
    E.click(chip("Của tôi"));
    ok("allWork: chip “Của tôi” chỉ còn việc giao cho mình + hiện nút Xoá lọc", E.$$("tbody tr[data-task]", E.main).map(t => t.getAttribute("data-task")).join() === "A1" && !E.$(".pmr-aw-clear", E.main).classList.contains("pmr-hide"));
    E.change(E.$(".pmr-aw-grp", E.main), "none");
    const c2 = E.w.document.createElement("div"); E.w.document.body.appendChild(c2);
    await E.w.PMR.render.allWork(c2, "list"); await flush();
    ok("allWork: mở lại (màn khác) vẫn nhớ chip + kiểu nhóm (localStorage)", E.byText(".pmr-aw-chip", "Của tôi", c2).classList.contains("pmr-on") && E.$(".pmr-aw-grp", c2).value === "none" && E.$$("tbody tr[data-task]", c2).length === 1);
    E.click(E.$(".pmr-aw-clear", c2));
    ok("allWork: Xoá lọc → đủ danh sách, nút Xoá lọc ẩn lại", E.$$("tbody tr[data-task]", c2).length === 4 && E.$(".pmr-aw-clear", c2).classList.contains("pmr-hide"));
    E.w.localStorage.setItem("pmr.prefs", "{hỏng");
    await E.w.PMR.render.allWork(E.w.document.createElement("div"), "list"); await flush();
    ok("allWork: localStorage hỏng → không lỗi, như mặc định", true);
    await E.w.PMR.render.coordinate(E.main); await flush();
    const kpi = E.$$(".pmr-strip button[data-act=c-kpi]", E.main);
    ok("coordinate: 3 ô KPI bấm được (đang mở / trễ / chưa có người)", kpi.length === 3);
    E.click(E.$('.pmr-strip [data-f="late"]', E.main));
    ok("coordinate: bấm “trễ hạn” → sang Tất cả việc", E.navs[E.navs.length - 1] === "#work/list");
    await E.w.PMR.render.allWork(E.main, "list"); await flush();
    ok("coordinate → allWork: chip Trễ hạn bật, bỏ lọc dự án đã nhớ", E.byText(".pmr-aw-chip", "Trễ hạn", E.main).classList.contains("pmr-on") && E.$(".pmr-aw-proj", E.main).value === "" && E.$$("tbody tr[data-task]", E.main).map(t => t.getAttribute("data-task")).join() === "A1");
    await E.w.PMR.render.projects(E.main); await flush();
    ok("projects: chip có số (Đang chạy 2, Hoàn thành 1, Của tôi 1)", ["Đang chạy 2", "Hoàn thành 1", "Của tôi 1"].every(t => !!E.$$("[data-act=p-filter]", E.main).find(b => b.textContent.replace(/\s+/g, " ").trim() === t)));
    E.click(E.byText(".pmr-chip", "Hoàn thành", E.main));
    await E.w.PMR.render.projects(E.main); await flush();
    ok("projects: mở lại vẫn nhớ bộ lọc Hoàn thành", E.byText(".pmr-chip", "Hoàn thành", E.main).classList.contains("pmr-on") && E.$$("tbody tr", E.main).length === 1);
  });

  /* ---------------- pure helpers ---------------- */
  await block('pure helpers #11', async () => {
    const E = makeEnv();
    const P = E.w.PMR._pure;
    ok("ngày tiếng Việt: Hôm nay 17:00 / T? dd/mm / Trễ N ngày", P.dueInfo(dayOff(0), "17:00:00").text === "Hôm nay 17:00" && /^(CN|T[2-7]) \d\d\/\d\d$/.test(P.dayLabel(dayOff(9))) && P.dueInfo(dayOff(-2)).text === "Trễ 2 ngày");
    ok("errOf lấy đúng thông điệp server (_server_messages)", P.errOf(smErr("Bạn không có quyền <b>x</b>")) === "Bạn không có quyền x");
    ok("sanitize: bỏ script/on*/javascript:", !/script|onerror|javascript/i.test(P.sanitize('<a href="javascript:alert(1)">a</a><img src="/files/a.png" onerror="x()"><script>1</script>')));
    ok("sanitize: chặn link/ảnh “//host” (ra ngoài không rõ giao thức), giữ “/files/…”", !/evil/.test(P.sanitize('<a href="//evil.example/x">a</a><img src="//evil.example/p.gif">')) && /src="\/files\/a.png"/.test(P.sanitize('<img src="/files/a.png">')));
  });

  const pass = results.filter(r => r.pass).length;
  results.forEach(r => console.log((r.pass ? "PASS " : "FAIL ") + r.name + (r.pass || r.extra == null ? "" : "  -> " + r.extra)));
  console.log(`\n${pass}/${results.length} passed`);
  process.exit(pass === results.length ? 0 : 1);
})().catch(e => { console.error("CRASH", e); process.exit(2); });
