/* pm_queue.test.js — Việc cần làm (asset pm_queue.js). Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue.test.js
 * API giả (không mạng). Kiểm: vẽ theo rank / nhóm / bộ lọc (client không xếp lại), hạn 2 tầng + ưu tiên 4 mức, Xong + Hoàn tác,
 * Xong bị chặn (bước bắt buộc -> mở việc), Review ("Đã gửi kiểm tra"), Bắt đầu, Xin dời hạn, Nhắc, Cần đồng ý (nhận / từ chối có lý do /
 * đề xuất hạn), giao việc 1 dòng (@người, hạn, ưu tiên, Cần đồng ý -> đúng endpoint + tham số; thiếu hạn -> mai), gợi ý @,
 * phím tắt J/K/X/S/Enter/N/Esc (không bắt khi đang gõ), ngăn chi tiết (tasks.get, Mở đầy đủ), mobile mở thẳng việc, lỗi server,
 * rỗng, Thử lại, nhật ký cá nhân, XSS, chặn bấm 2 lần, pmr:changed / pmr:badge, tự làm mới 60 giây, destroy dừng timer. */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_queue.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "css", "pm", "pm_queue.css"), "utf8");
const PMRJS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_redesign.js"), "utf8");
const res = [];
const ok = (n, c, x) => res.push({ n, c: !!c, x });
const tick = ms => new Promise(r => setTimeout(r, ms || 0));
const flush = async () => { for (let i = 0; i < 8; i++) await tick(0); };
const ME = "hoan@ecentric.vn", TODAY = "2026-11-13", NOW = "09:30";   /* T6 13/11/2026 */
const XSS = '<img src=x onerror="window.__xss=1">';
const smErr = msg => { const e = new Error("HTTP 417"); e._server_messages = JSON.stringify([JSON.stringify({ message: msg, indicator: "red" })]); return e; };

const row = (o) => Object.assign({ workflow_state: "To Do", project: "", project_name: "", priority: "Medium", due: null, due_time: null, giver: "huyen@ecentric.vn",
  giver_name: "Nguyễn Khánh Huyền", self: false, assignees: [{ user: ME, name: "Trần Hoàn", opened: true }], unopened: false, group: 0, review: 0, parent_task: null, modified: "" }, o);
function meData() {
  /* thứ tự = server (queue.ordered); cố ý KHÔNG theo tên / mã để chắc client không tự xếp */
  const rows = [
    row({ name: "T-Z1", subject: "Gửi báo giá ANDROS cho Shopee Mall", priority: "Urgent", due: "2026-11-12", due_time: "17:00", bucket: "late", workflow_state: "In Progress", project: "P1", project_name: "ANDROS - Shopee" }),
    row({ name: "T-A2", subject: "Duyệt kế hoạch livestream", priority: "Medium", due: "2026-11-11", bucket: "late", giver: "huong@ecentric.vn", giver_name: "Lê Hương" }),
    row({ name: "T-Q3", subject: "Sửa lỗi đồng bộ SKU " + XSS, priority: "Urgent", due: TODAY, bucket: "today", giver: "thai@ecentric.vn", giver_name: XSS }),
    row({ name: "T-B4", subject: "Chốt số GMV tuần 45", priority: "High", due: TODAY, due_time: "11:00", bucket: "today", review: 1 }),
    row({ name: "T-C5", subject: "Gọi brand FES-VN", priority: "Medium", due: TODAY, due_time: "14:00", bucket: "today", self: true, giver: ME, giver_name: "" }),
    row({ name: "T-D6", subject: "Review slide pitching", priority: "High", due: "2026-11-14", due_time: "10:00", bucket: "tomorrow", giver: "phu@ecentric.vn", giver_name: "Phú" }),
    row({ name: "T-E7", subject: "Chuẩn bị agenda họp BOD", priority: "High", due: "2026-11-15", bucket: "week" }),
    row({ name: "T-F8", subject: "Đối soát hoàn tiền tháng 10", priority: "Low", due: "2026-11-25", bucket: "later", project_name: XSS }),
    row({ name: "T-G9", subject: "Đọc tài liệu Microsoft Places", priority: "Low", due: null, bucket: "none", self: true, giver: ME, giver_name: "" })];
  rows.forEach((r, i) => { r.rank = i + 1; r.priority_rank = { Urgent: 4, High: 3, Medium: 2, Low: 1 }[r.priority]; });
  return { today: TODAY, now: NOW, tab: "me", rows, counts: { late: 2, today: 3, tomorrow: 1, week: 1, later: 1, none: 1 },
    buckets: [{ key: "late", label: "Quá hạn" }, { key: "today", label: "Hôm nay" }, { key: "tomorrow", label: "Ngày mai" }, { key: "week", label: "Còn lại tuần này" }, { key: "later", label: "Tuần sau trở đi" }, { key: "none", label: "Chưa có hạn" }],
    asks: [{ request: "REQ-1", task: "T-R1", subject: "Hỗ trợ setup kho mới Long An", project_name: "", from_user: "trong@ecentric.vn", from_name: "Trọng", proposed_end: "2026-11-18", message: "Cần gấp " + XSS, created: "" }],
    personal_hidden: 2 };
}
function giveData() {
  const rows = [
    row({ name: "G-1", subject: "Gửi file tồn kho Bình Dương", priority: "Urgent", due: "2026-11-12", bucket: "late", giver: ME, giver_name: "", assignees: [{ user: "trong@ecentric.vn", name: "Trọng", opened: false }], unopened: true }),
    row({ name: "G-2", subject: "Thiết kế banner 12.12", priority: "High", due: TODAY, due_time: "16:00", bucket: "today", giver: ME, giver_name: "", workflow_state: "In Progress", assignees: [{ user: "phuong@ecentric.vn", name: "Phương", opened: true }, { user: "lan@ecentric.vn", name: "Lan", opened: true }] })];
  rows.forEach((r, i) => { r.rank = i + 1; });
  return { today: TODAY, now: NOW, tab: "give", rows, counts: { late: 1, today: 1, tomorrow: 0, week: 0, later: 0, none: 0 }, buckets: meData().buckets, asks: [], personal_hidden: 0 };
}
const PEOPLE = [{ email: ME, full_name: "Trần Hoàn" }, { email: "lan@ecentric.vn", full_name: "Nguyễn Thị Lan" }, { email: "lanh@ecentric.vn", full_name: "Phạm Lành" },
  { email: "thai@ecentric.vn", full_name: "Đỗ Thái" }, { email: "vu.dang@ecentric.vn", full_name: "Đặng Vũ" }, { email: "vu.le@ecentric.vn", full_name: "Lê Vũ" }];

function setup(o) {
  o = o || {};
  const dom = new JSDOM("<!doctype html><body><div id=v></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#mywork", pretendToBeVisual: true });
  const w = dom.window, calls = [], opened = [], events = [], intervals = [], cleared = [];
  w.fetch = () => { calls.push({ m: "FETCH" }); return Promise.reject(new Error("no network")); };
  if (o.mobile) w.matchMedia = q => ({ matches: /max-width: 640px/.test(q), addListener() { }, removeListener() { } });
  const si = w.setInterval.bind(w), ci = w.clearInterval.bind(w);
  w.setInterval = (fn, ms) => { const id = si(fn, ms); intervals.push({ id, fn, ms }); return id; };
  w.clearInterval = id => { cleared.push(id); return ci(id); };
  if (o.personal) w.localStorage.setItem("pmr.showPersonal", "1");
  w.eval(PMRJS);
  w.eval(JS);
  ["pmr:changed", "pmr:badge"].forEach(n => w.document.addEventListener(n, e => events.push({ n, d: e.detail })));
  const H = Object.assign({
    "queue.list": a => (a.tab === "give" ? giveData() : meData()),
    "tasks.mark_done": () => ({ state: "Done" }),
    "tasks.set_status": () => ({ ok: 1 }),
    "tasks.create": a => ({ name: "T-NEW" }),
    "assignment.create_with_task": a => ({ task: "T-REQ", request: "REQ-9" }),
    "assignment.respond": () => ({ ok: 1 }),
    "pm_inbox.nudge": a => ({ task: a.task, sent: ["trong@ecentric.vn"], skipped: [] }),
    "assignment.list_assignable": () => ({ rows: PEOPLE }),
    "tasks.get": a => ({ task: { name: a.name, description: "<p>Bản báo giá Q4 <b>kèm</b> freeship</p><p>" + XSS + "</p>" } })
  }, o.h || {});
  const api = (method, args) => {
    const m = method.replace("ecentric_workspace.pm.api.", "");
    calls.push({ m, a: args });
    try {
      const fn = H[m];
      if (!fn) return Promise.reject(new Error("no " + m));
      const v = fn(args || {}, calls);
      return v && typeof v.then === "function" ? v : Promise.resolve(v);
    } catch (e) { return Promise.reject(e); }
  };
  const c = w.document.getElementById("v");
  const ctl = w.PMQueue.render(c, { api, user: ME, tab: o.tab || "me", openTask: (n, oo) => opened.push([n, oo || null]),
    head: (t, s, r) => `<div class="pm-head"><div><h1>${t}</h1><div class="sub">${s}</div></div><div>${r || ""}</div></div>` });
  const $ = s => w.document.querySelector(s), $$ = s => Array.from(w.document.querySelectorAll(s));
  const key = (k, target) => (target || w.document.body).dispatchEvent(new w.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
  const count = m => calls.filter(x => x.m === m).length;
  const last = m => calls.filter(x => x.m === m).slice(-1)[0];
  const toast = () => ($(".pmq-toast [data-tm]") || {}).textContent || "";
  const toastBtn = label => $$(".pmq-toast-b").find(b => b.textContent === label);
  const rowEl = n => $(`.pmq-row[data-name="${n}"]`);
  const type = async v => { const i = $("[data-qa]"); i.focus(); i.value = v; try { i.setSelectionRange(v.length, v.length); } catch (_) { } i.dispatchEvent(new w.Event("input", { bubbles: true })); await flush(); };
  return { w, c, ctl, calls, opened, events, intervals, cleared, $, $$, key, count, last, toast, toastBtn, rowEl, type };
}

(async () => {
  /* ---------- 1. vẽ theo rank / nhóm / hạn / ưu tiên */
  let t = setup(); await flush();
  const names = t.$$(".pmq-row").map(r => r.getAttribute("data-name"));
  ok("vẽ đúng thứ tự server (rank), client không xếp lại", names.join(",") === "T-Z1,T-A2,T-Q3,T-B4,T-C5,T-D6,T-E7,T-F8,T-G9", names.join(","));
  ok("cột # = rank của server", t.$$(".pmq-row .pmq-rk").map(x => x.textContent).join("") === "123456789");
  ok("nhóm theo hạn, đúng thứ tự + đếm", t.$$(".pmq-grp").map(h => h.firstChild.textContent.trim()).join("|") === "Quá hạn|Hôm nay|Ngày mai|Còn lại tuần này|Tuần sau trở đi|Chưa có hạn" && /3 việc/.test(t.$(".pmq-g--today .pmq-grp").textContent));
  ok("nhóm Hôm nay ghi ngày tuyệt đối (T6 13/11), Còn lại tuần này có khoảng ngày", /T6 13\/11/.test(t.$(".pmq-g--today .pmq-grp").textContent) && /CN 15\/11/.test(t.$(".pmq-g--week .pmq-grp").textContent));
  const due = n => { const d = t.rowEl(n).querySelector(".pmq-due"); return [d.querySelector("b").textContent, d.querySelector("small").textContent, d.className]; };
  ok("hạn 2 tầng: 'Trễ 1 ngày' đỏ + 'T5 12/11 · 17:00'", due("T-Z1")[0] === "Trễ 1 ngày" && due("T-Z1")[1] === "T5 12/11 · 17:00" && /pmq-due--late/.test(due("T-Z1")[2]));
  ok("hạn: Hôm nay 11:00 (màu hôm nay), Ngày mai 10:00, Còn 2 ngày, Chưa có hạn", due("T-B4")[0] === "Hôm nay 11:00" && /today/.test(due("T-B4")[2]) && due("T-D6")[0] === "Ngày mai 10:00" && due("T-E7")[0] === "Còn 2 ngày" && due("T-G9")[0] === "Chưa có hạn");
  ok("ưu tiên 4 mức = cột sóng + chữ", t.rowEl("T-Z1").querySelector(".pmq-pri.pmq-p4 .pmq-bars i") && /Khẩn cấp/.test(t.rowEl("T-Z1").querySelector(".pmq-pri").textContent) && /Cao/.test(t.rowEl("T-B4").textContent) && /Bình thường/.test(t.rowEl("T-A2").textContent) && /Thấp/.test(t.rowEl("T-F8").textContent));
  ok("người giao / Tự ghi", /Lê Hương/.test(t.rowEl("T-A2").querySelector(".pmq-hw").textContent) && /Tự ghi/.test(t.rowEl("T-C5").querySelector(".pmq-hw").textContent));
  ok("dòng quy tắc 'Thứ tự: Hạn → Ưu tiên → Giờ'", /Thứ tự:\s*Hạn\s*→\s*Ưu tiên\s*→\s*Giờ/.test(t.$(".pmq-rule").textContent));
  ok("tiêu đề + tóm tắt + số trên tab", t.$("h1").textContent === "Việc cần làm" && /9 việc đang mở, 2 quá hạn, 3 hạn hôm nay/.test(t.$("[data-sub]").textContent) && t.$('[data-c="me"]').textContent === "9" && t.$('[data-c="give"]').textContent === "2");
  ok("tải cả 2 tab, chỉ đọc (queue.list), ẩn nhật ký cá nhân mặc định", t.count("queue.list") === 2 && t.calls.filter(x => x.m === "queue.list").every(x => x.a.include_personal === 0));
  ok("Việc tôi làm: dòng không tự ghi có Bắt đầu + Dời hạn; tự ghi thì không có Dời hạn", !!t.rowEl("T-A2").querySelector('[data-act="start"]') && !!t.rowEl("T-A2").querySelector('[data-act="ask"]') && !t.rowEl("T-C5").querySelector('[data-act="ask"]') && !t.rowEl("T-Z1").querySelector('[data-act="start"]'));
  ok("pmr:badge mywork = số việc đang mở (đã ẩn nhật ký)", t.events.some(e => e.n === "pmr:badge" && e.d.key === "mywork" && e.d.count === 9));
  /* bộ lọc */
  t.$('[data-f="today"]').click(); await flush();
  ok("bấm 'Hôm nay 3' -> chỉ còn 3 dòng, vẫn giữ # gốc", t.$$(".pmq-row").length === 3 && t.$$(".pmq-row .pmq-rk").map(x => x.textContent).join(",") === "3,4,5" && t.$('[data-f="today"]').getAttribute("aria-pressed") === "true");
  t.$('[data-f="all"]').click(); await flush();
  ok("Tất cả -> đủ 9 dòng", t.$$(".pmq-row").length === 9);
  ok("bộ đếm chỉ hiện nhóm có việc + Quá hạn tô đỏ", t.$$("[data-f]").length === 7 && t.$('[data-f="late"]').classList.contains("pmq-f--late"));

  /* XSS */
  ok("XSS: chuỗi server được esc (tên việc, người giao, dự án, lời nhắn)", !t.$(".pmq img") && t.w.__xss === undefined && /<img src=x/.test(t.rowEl("T-Q3").textContent) && /<img/.test(t.$(".pmq-ask").textContent));

  /* ---------- 2. Xong + Hoàn tác */
  t.rowEl("T-A2").querySelector('[data-act="done"]').click();
  ok("Xong lạc quan: gạch ngang + chặn bấm 2 lần", t.rowEl("T-A2").classList.contains("pmq-row--done") && t.rowEl("T-A2").querySelector(".pmq-chk").disabled);
  t.rowEl("T-A2").querySelector(".pmq-chk").click();
  await flush();
  ok("tasks.mark_done(T-A2) đúng 1 lần", t.count("tasks.mark_done") === 1 && t.last("tasks.mark_done").a.name === "T-A2");
  ok("toast 'Đã xong' có nút Hoàn tác", /Đã xong: “Duyệt kế hoạch livestream”/.test(t.toast()) && !!t.toastBtn("Hoàn tác"));
  ok("phát pmr:changed {source:pmq, state:Done}", t.events.some(e => e.n === "pmr:changed" && e.d.source === "pmq" && e.d.task === "T-A2" && e.d.state === "Done"));
  t.toastBtn("Hoàn tác").click(); await flush();
  ok("Hoàn tác -> tasks.set_status(T-A2, trạng thái cũ 'To Do') + làm mới", t.last("tasks.set_status").a.name === "T-A2" && t.last("tasks.set_status").a.action === "To Do" && /Đã hoàn tác/.test(t.toast()));
  t.ctl.destroy(); t.w.close();

  /* Xong bị chặn bởi bước bắt buộc */
  t = setup({ h: { "tasks.mark_done": () => ({ state: "In Progress", blocked_reason: "required_steps", missing: 2 }) } }); await flush();
  t.rowEl("T-Z1").querySelector('[data-act="done"]').click(); await flush();
  ok("bị chặn (bước bắt buộc): báo rõ, KHÔNG gạch dòng, mở việc", /còn bước bắt buộc/.test(t.toast()) && t.$(".pmq-toast").classList.contains("pmq-toast--bad") && !t.rowEl("T-Z1").classList.contains("pmq-row--done") && t.opened.length === 1 && t.opened[0][0] === "T-Z1");
  t.ctl.destroy(); t.w.close();

  /* Review */
  t = setup({ h: { "tasks.mark_done": () => ({ state: "Review" }) } }); await flush();
  t.rowEl("T-B4").querySelector('[data-act="done"]').click(); await flush();
  ok("Review: toast 'Đã gửi kiểm tra' + Hoàn tác, dòng thành 'Chờ duyệt'", /Đã gửi kiểm tra: “Chốt số GMV tuần 45”/.test(t.toast()) && /sẽ kiểm tra/.test(t.toast()) && !!t.toastBtn("Hoàn tác") && /Chờ duyệt/.test(t.rowEl("T-B4").textContent) && t.rowEl("T-B4").querySelector(".pmq-chk").disabled);
  t.ctl.destroy(); t.w.close();

  /* lỗi server khi Xong */
  t = setup({ h: { "tasks.mark_done": () => Promise.reject(smErr("Bạn không có quyền sửa việc này.")) } }); await flush();
  t.rowEl("T-A2").querySelector('[data-act="done"]').click(); await flush();
  ok("lỗi server: hiện đúng _server_messages, trả dòng về như cũ", t.toast() === "Bạn không có quyền sửa việc này." && !t.rowEl("T-A2").classList.contains("pmq-row--done") && !t.rowEl("T-A2").querySelector(".pmq-chk").disabled);
  t.ctl.destroy(); t.w.close();

  /* ---------- 3. Bắt đầu / Xin dời hạn / Nhắc */
  t = setup(); await flush();
  t.rowEl("T-A2").querySelector('[data-act="start"]').click();
  t.rowEl("T-A2").querySelector('[data-act="start"]') && t.rowEl("T-A2").querySelector('[data-act="start"]').click();
  await flush();
  ok("Bắt đầu: tasks.set_status(In Progress) đúng 1 lần, dòng 'Đang làm', toast có Hoàn tác", t.count("tasks.set_status") === 1 && t.last("tasks.set_status").a.action === "In Progress" && /Đang làm/.test(t.rowEl("T-A2").textContent) && /Đã bắt đầu/.test(t.toast()) && !!t.toastBtn("Hoàn tác"));
  t.rowEl("T-D6").querySelector('[data-act="ask"]').click();
  ok("Xin dời hạn -> openTask(name, {askDeadline:true})", t.opened.some(x => x[0] === "T-D6" && x[1] && x[1].askDeadline === true));
  t.$('[data-tab="give"]').click(); await flush();
  ok("tab Việc tôi giao: hàng của tôi giao, cột Người nhận, nhãn 'Chưa mở việc', nút Nhắc, không có dấu xong bấm được", t.$$(".pmq-row").length === 2 && /Người nhận/.test(t.$(".pmq-cols").textContent) && /Chưa mở việc/.test(t.rowEl("G-1").textContent) && !!t.rowEl("G-1").querySelector('[data-act="nudge"]') && t.rowEl("G-1").querySelector(".pmq-chk").disabled && /\+1/.test(t.rowEl("G-2").textContent));
  ok("tab giao: tóm tắt + không có dải Cần đồng ý", /2 việc bạn đã giao còn mở, 1 quá hạn, 1 việc người nhận chưa mở/.test(t.$("[data-sub]").textContent) && !t.$(".pmq-ask"));
  const nb = t.rowEl("G-1").querySelector('[data-act="nudge"]');
  nb.click(); nb.click(); await flush();
  ok("Nhắc: pm_inbox.nudge(task) đúng 1 lần, toast tên người", t.count("pm_inbox.nudge") === 1 && t.last("pm_inbox.nudge").a.task === "G-1" && /Đã nhắc Trọng/.test(t.toast()));
  t.ctl.destroy(); t.w.close();
  t = setup({ tab: "give", h: { "pm_inbox.nudge": () => Promise.reject(smErr("Không còn ai cần nhắc.")) } }); await flush();
  t.rowEl("G-1").querySelector('[data-act="nudge"]').click(); await flush();
  ok("Nhắc lỗi: thông điệp server", t.toast() === "Không còn ai cần nhắc.");
  t.ctl.destroy(); t.w.close();

  /* ---------- 4. Cần đồng ý */
  t = setup(); await flush();
  ok("dải Cần đồng ý ở đầu danh sách (trước bộ lọc)", !!t.$(".pmq-ask") && /1 việc chờ bạn nhận/.test(t.$(".pmq-ask-h").textContent) && /Trọng giao · hạn đề xuất T4 18\/11/.test(t.$(".pmq-ask-row").textContent) &&
    (t.$(".pmq-ask").compareDocumentPosition(t.$("[data-bar]")) & 4) > 0);
  const ab = t.$('[data-act="ask-accept"]');
  ab.click(); ab.click(); await flush();
  ok("Nhận việc: assignment.respond(accept) đúng 1 lần + làm mới", t.count("assignment.respond") === 1 && t.last("assignment.respond").a.name === "REQ-1" && t.last("assignment.respond").a.decision === "accept" && /Đã nhận việc/.test(t.toast()) && t.count("queue.list") >= 4);
  t.ctl.destroy(); t.w.close();
  t = setup(); await flush();
  t.$('[data-act="ask-reject"]').click();
  ok("Từ chối mở form lý do, con trỏ ở ô lý do", !!t.$(".pmq-ask-form") && t.w.document.activeElement === t.$('[data-af="reason"]'));
  t.$('[data-act="ask-send"]').click(); await flush();
  ok("Từ chối thiếu lý do -> báo lỗi tại chỗ, không gọi server", t.count("assignment.respond") === 0 && /Ghi lý do/.test(t.$(".pmq-ask-form").textContent) && t.$('[data-af="reason"]').getAttribute("aria-invalid") === "true");
  const rs = t.$('[data-af="reason"]'); rs.value = "Đang kẹt dự án khác"; rs.dispatchEvent(new t.w.Event("input", { bubbles: true }));
  t.intervals.find(x => x.ms === 60000).fn(); await flush();
  ok("đang gõ lý do: tự làm mới 60 giây tạm hoãn, chữ còn nguyên", t.$('[data-af="reason"]').value === "Đang kẹt dự án khác" && t.count("queue.list") === 2);
  t.$('[data-act="ask-send"]').click(); await flush();
  ok("Từ chối có lý do -> respond(reject, reason)", t.last("assignment.respond").a.decision === "reject" && t.last("assignment.respond").a.reason === "Đang kẹt dự án khác" && /Đã từ chối/.test(t.toast()));
  t.ctl.destroy(); t.w.close();
  t = setup(); await flush();
  t.$('[data-act="ask-propose"]').click();
  ok("Đề xuất hạn: form có ngày (mặc định hạn đề xuất + 2) + giờ 18:00", t.$('[data-af="date"]').value === "2026-11-20" && t.$('[data-af="time"]').value === "18:00");
  const dd = t.$('[data-af="date"]'); dd.value = "2026-11-24"; dd.dispatchEvent(new t.w.Event("change", { bubbles: true }));
  const r2 = t.$('[data-af="reason"]'); r2.value = "Chờ kho bàn giao"; r2.dispatchEvent(new t.w.Event("input", { bubbles: true }));
  t.$('[data-act="ask-send"]').click(); await flush();
  const rq = t.last("assignment.respond").a;
  ok("Đề xuất hạn -> respond(reschedule, reason, counter_end)", rq.decision === "reschedule" && rq.reason === "Chờ kho bàn giao" && rq.counter_end === "2026-11-24 18:00:00" && /Đã gửi đề xuất hạn T3 24\/11/.test(t.toast()));
  t.ctl.destroy(); t.w.close();

  /* ---------- 5. giao việc 1 dòng */
  t = setup(); await flush();
  ok("ô giao việc: gợi ý cách gõ khi trống", /@người nhận/.test(t.$("[data-parse]").textContent));
  await t.type("@Lan gửi báo cáo GMV thứ 7 gấp");
  await flush();
  const tok = t.$("[data-parse]").textContent;
  ok("phân tích: người nhận Nguyễn Thị Lan, hạn T7 14/11, ưu tiên Khẩn cấp, Cần đồng ý bật", /Nguyễn Thị Lan/.test(tok) && t.$('[data-qa-f="due"]').value === "2026-11-14" && t.$('[data-qa-f="pri"]').value === "Urgent" && t.$('[data-qa-f="ask"]').checked && t.$("[data-qa-go]").textContent === "Gửi yêu cầu");
  t.$("[data-qa-form]").dispatchEvent(new t.w.Event("submit", { bubbles: true, cancelable: true }));
  t.$("[data-qa-form]").dispatchEvent(new t.w.Event("submit", { bubbles: true, cancelable: true }));
  await flush();
  const cw = t.last("assignment.create_with_task");
  ok("Cần đồng ý -> assignment.create_with_task đúng tham số, chặn gửi 2 lần", t.count("assignment.create_with_task") === 1 && cw.a.subject === "gửi báo cáo GMV" && cw.a.recipient === "lan@ecentric.vn" && cw.a.priority === "Urgent" && cw.a.proposed_end === "2026-11-14 18:00:00" && t.count("tasks.create") === 0);
  ok("sau khi gửi: ô trống, toast 'chờ nhận', pmr:changed created", t.$("[data-qa]").value === "" && /Đã gửi cho Nguyễn Thị Lan: “gửi báo cáo GMV” · hạn T7 14\/11\. Chờ người nhận bấm Nhận việc\./.test(t.toast()) && t.events.some(e => e.n === "pmr:changed" && e.d.created));
  await t.type("@lan gọi lại khách ưu tiên cao mai 10h");
  t.$('[data-qa-f="ask"]').click(); await flush();
  ok("bỏ tick Cần đồng ý -> nút 'Giao việc', ưu tiên Cao, hạn mai 10:00", t.$("[data-qa-go]").textContent === "Giao việc" && t.$('[data-qa-f="pri"]').value === "High" && t.$('[data-qa-f="due"]').value === "2026-11-14" && t.$('[data-qa-f="time"]').value === "10:00");
  t.$("[data-qa-form]").dispatchEvent(new t.w.Event("submit", { bubbles: true, cancelable: true })); await flush();
  const tc = t.last("tasks.create");
  ok("giao trực tiếp -> tasks.create(project='', assignees JSON, hạn, giờ, High)", tc && tc.a.project === "" && tc.a.subject === "gọi lại khách" && tc.a.assignees === JSON.stringify(["lan@ecentric.vn"]) && tc.a.exp_end_date === "2026-11-14" && tc.a.pm_end_time === "10:00:00" && tc.a.priority === "High");
  ok("giao trực tiếp cho người khác -> KHÔNG tự chuyển tab (đang giao liền nhiều việc), toast có nút Xem", t.$('[data-tab="me"]').getAttribute("aria-pressed") === "true" && /Đã giao cho Nguyễn Thị Lan: “gọi lại khách”/.test(t.toast()) && !!t.toastBtn("Xem"));
  await t.type("@lan gửi file kho thứ 6");
  ok("nhớ lựa chọn Cần đồng ý (đã bỏ tick) cho việc giao kế tiếp", !t.$('[data-qa-f="ask"]').checked && t.$("[data-qa-go]").textContent === "Giao việc");
  t.$("[data-qa]").value = ""; t.$("[data-qa]").dispatchEvent(new t.w.Event("input", { bubbles: true })); await flush();
  t.toastBtn("Xem").click(); await flush();
  ok("bấm Xem -> sang tab Việc tôi giao", t.$('[data-tab="give"]').getAttribute("aria-pressed") === "true");
  t.$('[data-tab="me"]').click(); await flush();
  await t.type("Đọc hợp đồng FES không gấp");
  ok("không @, không hạn -> việc của tôi, hạn mặc định NGÀY MAI hiện rõ, ưu tiên Thấp, Cần đồng ý tắt", /Tôi/.test(t.$("[data-parse]").textContent) && t.$('[data-qa-f="due"]').value === "2026-11-14" && /mặc định ngày mai/.test(t.$("[data-parse]").textContent) && t.$('[data-qa-f="pri"]').value === "Low" && t.$('[data-qa-f="ask"]').disabled && t.$("[data-qa-go]").textContent === "Thêm việc");
  const di = t.$('[data-qa-f="due"]'); di.value = "2026-11-20"; di.dispatchEvent(new t.w.Event("change", { bubbles: true }));
  t.$("[data-qa-form]").dispatchEvent(new t.w.Event("submit", { bubbles: true, cancelable: true })); await flush();
  const ts = t.last("tasks.create");
  ok("việc của tôi -> tasks.create(assignees=[tôi]); sửa ô ngày được (20/11)", ts.a.subject === "Đọc hợp đồng FES" && ts.a.assignees === JSON.stringify([ME]) && ts.a.exp_end_date === "2026-11-20" && ts.a.priority === "Low" && !("pm_end_time" in ts.a) && /Đã thêm vào việc của bạn/.test(t.toast()));
  await t.type("Báo cáo cuối tháng");
  ok("'cuối tháng' giữa tên việc không bị hiểu thành hạn", t.w.PMQueue._parseLine("Báo cáo cuối tháng", { parseDue: t.w.PMR._pure.parseDue, base: new t.w.Date(2026, 10, 13, 9, 30) }).subject === "Báo cáo cuối tháng" && /mặc định ngày mai/.test(t.$("[data-parse]").textContent));
  ok("'gặp khách' không bị hiểu là 'gấp'", t.w.PMQueue._parseLine("gặp khách Unilever", {}).priority === null && t.w.PMQueue._parseLine("Gấp: gửi hồ sơ", {}).priority === "Urgent" && t.w.PMQueue._parseLine("làm khẩn cấp", {}).priority === "Urgent");
  await t.type("@vu kiểm kho");
  ok("@tên trùng nhiều người -> phải chọn, Enter không gửi", /Chọn:/.test(t.$("[data-parse]").textContent) && t.$$(".pmq-pick").length === 2);
  const nCreate = t.count("tasks.create") + t.count("assignment.create_with_task");
  t.$("[data-qa-form]").dispatchEvent(new t.w.Event("submit", { bubbles: true, cancelable: true })); await flush();
  ok("...gửi khi chưa chọn -> báo 'Có nhiều người tên', không gọi server", t.count("tasks.create") + t.count("assignment.create_with_task") === nCreate && /Có nhiều người tên “vu”/.test(t.$("[data-parse]").textContent));
  t.$$(".pmq-pick")[1].click(); await flush();
  ok("chọn 1 người -> ô nhập đổi @tên, người nhận rõ", /Lê Vũ/.test(t.$("[data-parse] .pmq-tok").textContent) && /@Vũ/.test(t.$("[data-qa]").value));
  await t.type("@khongcoai việc X");
  ok("@tên không có -> 'Không tìm thấy'", /Không tìm thấy “@khongcoai”/.test(t.$("[data-parse]").textContent));
  /* gợi ý @ */
  await t.type("Gửi file @la");
  ok("gõ '@la' -> danh sách gợi ý (combobox) khớp không dấu", !t.$(".pmq-acl").hidden && t.$$(".pmq-ac-i").length === 2 && t.$("[data-qa]").getAttribute("aria-expanded") === "true");
  const qi = t.$("[data-qa]");
  qi.dispatchEvent(new t.w.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
  qi.dispatchEvent(new t.w.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })); await flush();
  ok("ArrowDown + Enter chọn người thứ 2 (Phạm Lành), không gửi", /@Lành /.test(qi.value) && /Phạm Lành/.test(t.$("[data-parse]").textContent) && t.$(".pmq-acl").hidden && t.count("tasks.create") + t.count("assignment.create_with_task") === nCreate);
  t.ctl.destroy(); t.w.close();
  t = setup({ h: { "tasks.create": () => Promise.reject(smErr("Tên nhiệm vụ là bắt buộc.")) } }); await flush();
  await t.type("Việc A");
  t.$("[data-qa-form]").dispatchEvent(new t.w.Event("submit", { bubbles: true, cancelable: true })); await flush();
  ok("giao việc lỗi: giữ chữ đã gõ, báo đúng thông điệp server, mở lại nút", t.$("[data-qa]").value === "Việc A" && /Tên nhiệm vụ là bắt buộc/.test(t.$("[data-parse]").textContent) && !t.$("[data-qa-go]").disabled);
  t.ctl.destroy(); t.w.close();

  /* ---------- 6. phím tắt + ngăn chi tiết */
  t = setup(); await flush();
  t.key("j");
  ok("J chọn dòng đầu, focus vào dòng", t.rowEl("T-Z1").classList.contains("pmq-row--sel") && t.rowEl("T-Z1").getAttribute("aria-current") === "true" && t.w.document.activeElement === t.rowEl("T-Z1").querySelector(".pmq-open"));
  t.key("j", t.w.document.activeElement); t.key("j", t.w.document.activeElement); t.key("k", t.w.document.activeElement);
  ok("J J K -> dòng 2", t.rowEl("T-A2").classList.contains("pmq-row--sel") && t.$$(".pmq-row--sel").length === 1);
  t.key("Enter", t.rowEl("T-A2"));
  await flush();
  ok("Enter mở ngăn chi tiết bên phải (không popup) + tasks.get + mô tả chữ thường", !t.$("[data-drawer]").hidden && t.$("[data-wrap]").classList.contains("pmq-wrap--open") && t.last("tasks.get").a.name === "T-A2" && /Bản báo giá Q4 kèm freeship/.test(t.$(".pmq-dr-text").textContent) && !t.$(".pmq-dr img") && !t.$('[role="dialog"]'));
  ok("ngăn chi tiết: meta + nút Xong / Bắt đầu / Xin dời hạn / Mở đầy đủ", /Người giao/.test(t.$(".pmq-dr-meta").textContent) && ["done", "start", "ask", "full"].every(a => !!t.$('.pmq-dr [data-act="' + a + '"]')));
  t.$('.pmq-dr [data-act="full"]').click();
  ok("Mở đầy đủ -> openTask(name)", t.opened.some(x => x[0] === "T-A2" && !x[1]));
  t.key("j", t.w.document.body); await flush();
  ok("ngăn đang mở: J đổi dòng thì ngăn theo dòng mới", /Sửa lỗi đồng bộ SKU/.test(t.$(".pmq-dr-t").textContent));
  t.key("Escape"); await flush();
  ok("Esc đóng ngăn chi tiết", t.$("[data-drawer]").hidden && !t.$("[data-wrap]").classList.contains("pmq-wrap--open"));
  t.key("s", t.w.document.body); await flush();
  ok("S bắt đầu dòng đang chọn", t.last("tasks.set_status") && t.last("tasks.set_status").a.name === "T-Q3" && t.last("tasks.set_status").a.action === "In Progress");
  t.key("x", t.w.document.body); await flush();
  ok("X đánh dấu xong dòng đang chọn", t.last("tasks.mark_done") && t.last("tasks.mark_done").a.name === "T-Q3");
  const n0 = t.count("tasks.mark_done");
  await t.type("x");
  t.key("x", t.$("[data-qa]"));
  ok("phím tắt không bắt khi đang gõ trong ô nhập", t.count("tasks.mark_done") === n0);
  t.$("[data-qa]").blur(); t.key("n");
  ok("N đưa con trỏ vào ô giao việc", t.w.document.activeElement === t.$("[data-qa]"));
  t.ctl.destroy(); t.w.close();

  /* mobile: bấm dòng mở thẳng việc */
  t = setup({ mobile: true }); await flush();
  t.rowEl("T-B4").querySelector(".pmq-tt small").click();
  ok("mobile ≤640px: bấm dòng -> openTask (không ngăn chi tiết)", t.opened.length === 1 && t.opened[0][0] === "T-B4" && t.$("[data-drawer]").hidden);
  ok("CSS: mobile hàng 2 tầng + ô nhập 16px, tablet 1024px", /@media \(max-width:640px\)[\s\S]*grid-template-areas:"chk tt due" "chk hp hw"/.test(CSS) && /\.pmq-qa-in\{font-size:16px\}/.test(CSS) && /@media \(max-width:1279px\)/.test(CSS) && /@media \(min-width:641px\) and \(max-width:1100px\)/.test(CSS) && /font-variant-numeric:tabular-nums/.test(CSS));
  t.ctl.destroy(); t.w.close();

  /* ---------- 7. rỗng / lỗi / nhật ký cá nhân */
  t = setup({ h: { "queue.list": a => Object.assign(a.tab === "give" ? giveData() : meData(), { rows: [], counts: {}, asks: [], personal_hidden: 0 }) } }); await flush();
  ok("rỗng: hướng dẫn + nút Ghi việc, không có dòng nhật ký", /Không còn việc nào đang mở/.test(t.$("[data-list]").textContent) && /gõ tên việc, hạn rồi Enter/.test(t.$("[data-list]").textContent) && t.$("[data-note]").hidden);
  t.$('[data-act="focus-qa"]').click();
  ok("nút trong trạng thái rỗng đưa con trỏ vào ô giao việc", t.w.document.activeElement === t.$("[data-qa]"));
  t.ctl.destroy(); t.w.close();
  let fail1 = true;
  t = setup({ h: { "queue.list": a => (fail1 ? Promise.reject(smErr("Bạn không có quyền vào Công việc.")) : (a.tab === "give" ? giveData() : meData())) } }); await flush();
  ok("tải lỗi: thông điệp server + nút Thử lại", /Không tải được danh sách việc/.test(t.$("[data-list]").textContent) && /Bạn không có quyền vào Công việc/.test(t.$("[data-list]").textContent) && !!t.$('[data-act="retry"]'));
  fail1 = false; t.$('[data-act="retry"]').click(); await flush();
  ok("Thử lại -> tải được, vẽ danh sách", t.$$(".pmq-row").length === 9);
  t.ctl.destroy(); t.w.close();
  t = setup(); await flush();
  ok("nhật ký cá nhân: 'Đang ẩn 2' + nút 'Hiện nhật ký cá nhân (2)'", /Đang ẩn 2 việc nhật ký cá nhân/.test(t.$("[data-note]").textContent) && t.$('[data-act="personal"]').textContent === "Hiện nhật ký cá nhân (2)");
  t.$('[data-act="personal"]').click(); await flush();
  ok("bấm Hiện -> gọi lại queue.list include_personal=1, nhớ localStorage pmr.showPersonal", t.last("queue.list").a.include_personal === 1 && t.w.localStorage.getItem("pmr.showPersonal") === "1" && /Ẩn nhật ký cá nhân/.test(t.$("[data-note]").textContent));
  t.ctl.destroy(); t.w.close();

  /* ---------- 8. pmr:changed từ màn khác / tự làm mới / destroy */
  t = setup(); await flush();
  const q0 = t.count("queue.list");
  t.w.document.dispatchEvent(new t.w.CustomEvent("pmr:changed", { detail: { task: "T-A2" } })); await tick(350); await flush();
  ok("nghe pmr:changed của màn khác -> làm mới", t.count("queue.list") > q0);
  const q1 = t.count("queue.list");
  t.w.document.dispatchEvent(new t.w.CustomEvent("pmr:changed", { detail: { source: "pmq" } })); await tick(350); await flush();
  ok("bỏ qua pmr:changed của chính mình", t.count("queue.list") === q1);
  const iv = t.intervals.find(x => x.ms === 60000);
  iv.fn(); await flush();
  ok("tự làm mới mỗi 60 giây khi tab đang hiện", !!iv && t.count("queue.list") > q1);
  const q2 = t.count("queue.list");
  t.ctl.destroy();
  iv.fn(); await flush();
  t.w.document.dispatchEvent(new t.w.CustomEvent("pmr:changed", { detail: {} })); await tick(350);
  t.key("j");
  ok("destroy: dừng timer (clearInterval), không gọi server, không nghe phím", t.cleared.indexOf(iv.id) >= 0 && t.count("queue.list") === q2 && !t.$(".pmq-row--sel"));
  t.w.close();
  t = setup(); await flush();
  const iv2 = t.intervals.find(x => x.ms === 60000);
  t.c.innerHTML = "<p>màn khác</p>";
  iv2.fn(); await flush();
  ok("host thay #pm-view -> lần tick sau tự dừng", t.cleared.indexOf(iv2.id) >= 0);
  t.w.close();

  /* ---------- 9. rà UX 15/11: đi hết hàng đợi bằng phím, thu gọn Cần đồng ý, toast, tên dài, phím theo tab */
  t = setup(); await flush();
  t.key("j"); t.key("x", t.w.document.activeElement); await flush();
  ok("X: dòng vừa xong còn gạch, chọn + focus ngay việc kế tiếp", t.rowEl("T-Z1").classList.contains("pmq-row--done") && t.rowEl("T-A2").classList.contains("pmq-row--sel") && t.w.document.activeElement === t.rowEl("T-A2").querySelector(".pmq-open"));
  t.key("x", t.w.document.activeElement); await flush();
  ok("X, X: đi tiếp xuống dòng 3, mỗi việc gọi mark_done đúng 1 lần", t.rowEl("T-Q3").classList.contains("pmq-row--sel") && t.calls.filter(c => c.m === "tasks.mark_done").map(c => c.a.name).join(",") === "T-Z1,T-A2");
  t.ctl.destroy(); t.w.close();
  let dropB4 = false;
  t = setup({ h: { "queue.list": a => { if (a.tab === "give") return giveData(); const d = meData(); if (dropB4) { d.rows = d.rows.filter(r => r.name !== "T-B4"); d.counts.today = 2; } return d; } } }); await flush();
  t.rowEl("T-B4").querySelector(".pmq-open").focus(); await flush();
  dropB4 = true; await t.ctl.refresh(); await flush();
  ok("việc đang chọn rời danh sách khi làm mới -> chọn việc kế tiếp (T-C5), focus theo", t.rowEl("T-C5").classList.contains("pmq-row--sel") && t.w.document.activeElement === t.rowEl("T-C5").querySelector(".pmq-open"));
  t.ctl.destroy(); t.w.close();
  const manyAsks = () => { const d = meData(); d.asks = [1, 2, 3, 4, 5, 6].map(i => ({ request: "REQ-" + i, task: "T-R" + i, subject: "Việc chờ nhận số " + i, from_user: "trong@ecentric.vn", from_name: "Trọng", proposed_end: "2026-11-18", message: "" })); return d; };
  t = setup({ h: { "queue.list": a => (a.tab === "give" ? giveData() : manyAsks()) } }); await flush();
  ok("Cần đồng ý 6 việc: hiện 3 + 'Xem thêm 3 việc chờ nhận', tiêu đề vẫn đếm 6", t.$$(".pmq-ask-row").length === 3 && /Xem thêm 3 việc chờ nhận/.test(t.$('[data-act="ask-more"]').textContent) && /6 việc chờ bạn nhận/.test(t.$(".pmq-ask-h").textContent));
  t.$('[data-act="ask-more"]').click(); await flush();
  ok("bấm Xem thêm -> đủ 6, nút thành 'Thu gọn' (aria-expanded=true), focus giữ trên nút", t.$$(".pmq-ask-row").length === 6 && t.$('[data-act="ask-more"]').textContent === "Thu gọn" && t.$('[data-act="ask-more"]').getAttribute("aria-expanded") === "true" && t.w.document.activeElement === t.$('[data-act="ask-more"]'));
  t.ctl.destroy(); t.w.close();
  const LONG = "Chuẩn bị toàn bộ hồ sơ đấu thầu gói tư vấn vận hành gian hàng Shopee Mall và TikTok Shop cho nhãn hàng ANDROS quý 1 năm 2027";
  t = setup({ h: { "queue.list": a => { if (a.tab === "give") return giveData(); const d = meData(); d.rows[1].subject = LONG; return d; } } }); await flush();
  ok("tên việc dài: có title đủ chữ trên dòng; tên ngắn thì không gắn title", t.rowEl("T-A2").querySelector(".pmq-open").getAttribute("title") === LONG && !t.rowEl("T-B4").querySelector(".pmq-open").hasAttribute("title"));
  t.rowEl("T-A2").querySelector('[data-act="done"]').click(); await flush();
  ok("toast cắt tên dài (≤ 60 ký tự + …), vẫn có Hoàn tác, thời gian 8 giây", /^Đã xong: “.{50,58}…”$/.test(t.toast()) && !!t.toastBtn("Hoàn tác") && t.ctl._state.toastMs === 8000);
  const to = t.$(".pmq-toast");
  to.dispatchEvent(new t.w.MouseEvent("mouseenter")); await tick(20);
  ok("rê chuột vào toast -> dừng đếm (toast còn hiện)", to.classList.contains("pmq-toast--on"));
  ok("phím tắt ở chân trang theo tab: Việc tôi làm có X / S", /X xong/.test(t.$("[data-keys]").textContent) && /S bắt đầu/.test(t.$("[data-keys]").textContent));
  t.$('[data-tab="give"]').click(); await flush();
  ok("...Việc tôi giao không có X / S (không áp dụng)", !/xong|bắt đầu/.test(t.$("[data-keys]").textContent) && /J/.test(t.$("[data-keys]").textContent));
  t.$('[data-tab="me"]').click();
  await flush();
  ok("dòng: nút 'Xin dời hạn' cùng chữ với ngăn chi tiết; avatar không tô màu theo tên", t.rowEl("T-D6").querySelector('[data-act="ask"]').textContent === "Xin dời hạn" && !t.$(".pmq-av[style]"));
  ok("nhật ký cá nhân nằm DƯỚI danh sách (hiện sau khi tải không đẩy danh sách xuống)", !!t.$("[data-wrap] ~ [data-note]") && !t.$("[data-note] ~ [data-wrap]"));
  t.ctl.destroy(); t.w.close();
  const cssNoCmt = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
  ok("CSS AA: chữ số thứ tự / 'Chưa có hạn' / placeholder không dùng g400 (2.5:1); cam ưu tiên Cao #c2410c", /\.pmq-rk\{color:var\(--q-g500\)/.test(cssNoCmt) && /\.pmq-due--none b\{color:var\(--q-g500\)/.test(cssNoCmt) && /::placeholder\{color:var\(--q-g500\)\}/.test(cssNoCmt) && /--q-p3:#c2410c/.test(cssNoCmt));
  ok("CSS vùng bấm: nút ≥32px, nút tròn có vùng bấm mở rộng (::after), ≥40px trên điện thoại", /\.pmq-btn\{[^}]*min-height:32px/.test(cssNoCmt) && /\.pmq-chk::after\{content:"";position:absolute;inset:-6px/.test(cssNoCmt) && /@media \(max-width:640px\)[\s\S]*\.pmq-btn--sm,\.pmq-pick\{min-height:40px\}/.test(cssNoCmt) && /\.pmq-x\{width:32px;height:32px/.test(cssNoCmt));
  ok("CSS: không viền trái màu cho dòng đang chọn, avatar trung tính, ô giao việc cao 100px như xương host", !/pmq-row--sel::before/.test(cssNoCmt) && !/hsl\(var\(--h/.test(cssNoCmt) && /\.pmq-qa\{padding:10px 14px 8px\}/.test(cssNoCmt) && /min-height:32px\}/.test(cssNoCmt));

  ok("không gọi fetch trực tiếp khi host truyền api; không ký tự Jinja; một global", !/\{\{|\{%|\{#/.test(JS) && !/\{\{|\{%|\{#/.test(CSS) && /root\.PMQueue = \{/.test(JS));
  ok("CSS chỉ namespace .pmq- (trừ .pm-head của host lồng trong .pmq)", CSS.replace(/\/\*[\s\S]*?\*\//g, "").split("}").map(s => s.split("{")[0].trim()).filter(s => s && !/^@|^(from|to|\d+%)$/.test(s))
    .every(sel => sel.split(",").every(x => /^\s*(\.pmq|:where\(\.pmq\))/.test(x) || /^\s*(from|to)\b/.test(x) || /^\s*(input|select|textarea)\)?\s*$/.test(x))));

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
