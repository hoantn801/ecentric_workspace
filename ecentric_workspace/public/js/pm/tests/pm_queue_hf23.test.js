/* pm_queue_hf23.test.js — hotfix 23 (PO 27/11/2026, thiết kế lại /pm v2, màn "1. Việc cần làm").
 * Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue_hf23.test.js
 * G  lưới: đầu cột / tên nhóm / dòng dùng MỘT grid-template-columns (--q-cols), bỏ cột "#", tên nhóm grid-column 2/-1 (= cột "Việc").
 *    jsdom không layout: kiểm cấu trúc DOM (con thứ 2 của đầu cột là "Việc", nhãn nhóm nằm trong .pmq-grp-l) + luật CSS.
 * W  dải tuần: Trễ hạn · Hôm nay · 6 ngày tới · Sau đó · Chưa có hạn; đếm đúng, không tính Tồn đọng, chấm ưu tiên ≤10, bấm lọc / bấm lại bỏ.
 * M  mỗi nhóm 7 việc + "Xem thêm N việc" / "Thu gọn"; J/K chỉ đi qua dòng đang hiện.
 * O  Enter / bấm dòng -> PMR.openTask(name, {nav: {names, onMove}}) đúng thứ tự đang hiện; vòng Xong không mở.
 * C  dòng 2: chấm màu dự án (PMR.projectColor, có dự phòng), bước / việc con / bình luận mới.
 * P  công tắc nhật ký cá nhân; E màn trống; S tĩnh (token, theme, không icon unicode, không còn .pmq-dr). */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_queue.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "css", "pm", "pm_queue.css"), "utf8");
const CSSX = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
const res = [];
const ok = (n, c, x) => res.push({ n, c: !!c, x });
const tick = ms => new Promise(r => setTimeout(r, ms || 0));
const flush = async () => { for (let i = 0; i < 8; i++) await tick(0); };
const ME = "hoan@ecentric.vn", TODAY = "2026-11-27", NOW = "09:30";   /* T6 27/11/2026 */
const BUCKETS = [{ key: "late", label: "Quá hạn" }, { key: "today", label: "Hôm nay" }, { key: "tomorrow", label: "Ngày mai" }, { key: "week", label: "Còn lại tuần này" },
  { key: "later", label: "Tuần sau trở đi" }, { key: "none", label: "Chưa có hạn" }, { key: "stale", label: "Tồn đọng" }];
const row = o => Object.assign({ workflow_state: "To Do", project: "", project_name: "", project_color: "", priority: "Medium", due: null, due_time: null, giver: "huyen@ecentric.vn",
  giver_name: "Nguyễn Khánh Huyền", giver_system: 0, self: false, assignees: [{ user: ME, name: "Trần Hoàn", opened: true }], unopened: false, group: 0, review: 0 }, o);
function pack(tab, rows, extra) {
  rows.forEach((r, i) => { r.rank = i + 1; });
  const counts = {}; BUCKETS.forEach(b => { counts[b.key] = rows.filter(r => r.bucket === b.key).length; });
  return Object.assign({ today: TODAY, now: NOW, tab, rows, counts, buckets: BUCKETS, asks: [], personal_hidden: 0, waiting: [], proposals: [] }, extra || {});
}
/* 2 trễ (1 Khẩn) · 10 hôm nay (để thử Xem thêm) · T7 28 · T2 30 · T4 02/12 (ngày thứ 5 tới) · 04/12 (sau 7 ngày -> Sau đó) · chưa có hạn · 2 tồn đọng */
const meRows = () => [
  row({ name: "L-1", subject: "Đối soát công nợ Shopee", priority: "Urgent", due: "2026-11-25", bucket: "late", project: "P1", project_name: "Pin Hà Nội", project_color: "rose",
    steps: { done: 2, total: 4 }, new_comments: 2 }),
  row({ name: "L-2", subject: "Trễ theo giờ hôm nay", priority: "High", due: TODAY, due_time: "08:00", bucket: "late" })]
  .concat(Array.from({ length: 10 }, (_, i) => row({ name: "D-" + i, subject: "Việc hôm nay " + i, due: TODAY, bucket: "today", priority: i === 0 ? "High" : "Medium",
    project: i === 1 ? "P2" : "", project_name: i === 1 ? "Affiliate Internal" : "", project_color: i === 1 ? "violet" : "", subtasks: i === 1 ? { done: 1, total: 3 } : null })))
  .concat([
    row({ name: "W-1", subject: "Thứ Bảy", due: "2026-11-28", bucket: "tomorrow" }),
    row({ name: "W-2", subject: "Thứ Hai", due: "2026-11-30", bucket: "later" }),
    row({ name: "W-3", subject: "Thứ Tư", due: "2026-12-02", bucket: "later" }),
    row({ name: "F-1", subject: "Xa", due: "2026-12-04", bucket: "later", project: "P3", project_name: "Không màu", project_color: "" }),
    row({ name: "N-1", subject: "Chưa hạn", bucket: "none", self: true, giver: ME, giver_name: "" }),
    row({ name: "S-1", subject: "Tồn 1", due: "2026-08-01", bucket: "stale", self: true, giver: ME, giver_name: "" }),
    row({ name: "S-2", subject: "Tồn 2", due: "2026-08-02", bucket: "stale", self: true, giver: ME, giver_name: "" })]);

function setup(o) {
  o = o || {};
  const dom = new JSDOM("<!doctype html><body><div id=v></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#mywork", pretendToBeVisual: true });
  const w = dom.window, calls = [], opened = [];
  w.fetch = () => Promise.reject(new Error("no network"));
  if (o.pmr) w.PMR = o.pmr;   /* PMR giả (projectColor) — không có thì pm_queue dùng bảng dự phòng */
  if (o.personal) w.localStorage.setItem("pmr.showPersonal", "1");
  w.eval(JS);
  const H = Object.assign({
    "queue.list": a => (a.tab === "me" ? pack("me", meRows(), { personal_hidden: a.include_personal ? 0 : 5 }) : pack(a.tab, [])),
    "tasks.mark_done": () => ({ state: "Done" }),
    "assignment.list_assignable": () => ({ rows: [] })
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
  const rowEl = n => $(`.pmq-row[data-name="${n}"]`);
  const names = () => $$(".pmq-row").map(r => r.getAttribute("data-name"));
  const key = (k, tg) => (tg || w.document.body).dispatchEvent(new w.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
  const wk = k => $(`[data-wk="${k}"]`);
  const wkN = k => parseInt(wk(k).querySelector(".pmq-wk-n").textContent, 10);
  return { w, ctl, calls, opened, $, $$, count, last, rowEl, names, key, wk, wkN };
}

(async () => {
  /* ---------- G lưới chung */
  let t = setup(); await flush();
  const cols = t.$(".pmq-cols");
  ok("G không còn cột '#': đầu cột 6 ô, ô 2 là 'Việc', không ô nào ghi '#'; dòng không có .pmq-rk (trừ tồn đọng)",
    cols.children.length === 6 && cols.children[1].textContent === "Việc" && !Array.from(cols.children).some(x => x.textContent.trim() === "#") && !t.rowEl("L-1").querySelector(".pmq-rk"));
  ok("G dòng 6 ô cùng thứ tự đầu cột: ô tròn | Việc | Ưu tiên | Hạn | Người | thao tác",
    (() => { const r = t.rowEl("L-1").children; return r.length === 6 && r[0].classList.contains("pmq-chk") && r[1].classList.contains("pmq-tt") && r[2].classList.contains("pmq-hp") && r[3].classList.contains("pmq-dt") && r[4].classList.contains("pmq-hw") && r[5].classList.contains("pmq-ac"); })());
  ok("G CSS: .pmq-cols, .pmq-grp, .pmq-row dùng CHUNG một luật grid-template-columns:var(--q-cols) + cùng padding",
    /\.pmq-cols,\.pmq-grp,\.pmq-row,\.pmq-bulk,\.pmq-skel\{display:grid;grid-template-columns:var\(--q-cols\);column-gap:var\(--q-gap\);align-items:center;padding:0 14px 0 var\(--q-pad\)\}/.test(CSSX) &&
    !/\.pmq-(grp|row|cols)\{[^}]*padding(-left)?:/.test(CSSX.replace(/@media[\s\S]*$/, "")));
  ok("G tên nhóm bắt đầu đúng cột 'Việc': nhãn trong .pmq-grp-l, CSS grid-column:2/-1",
    t.$$(".pmq-grp").every(g => g.children.length === 1 && g.firstElementChild.classList.contains("pmq-grp-l")) && /\.pmq-grp>\.pmq-grp-l\{grid-column:2\/-1/.test(CSSX));
  ok("G tên nhóm chữ hoa nhỏ 11.5px xám + số đếm (viên em)", /\.pmq-grp\{[^}]*font-size:11\.5px;[^}]*text-transform:uppercase;color:var\(--q-g500\)/.test(CSSX) &&
    t.$(".pmq-g--today .pmq-grp em").textContent === "10" && t.$(".pmq-g--late .pmq-grp em").textContent === "2");
  ok("G 'Xem thêm' bắt đầu đúng cột Việc (padding-left = lề + cột 1 + khe)", /\.pmq-more-g\{[^}]*padding:8px 14px 8px calc\(var\(--q-pad\) \+ var\(--q-c1\) \+ var\(--q-gap\)\)/.test(CSSX));
  ok("G cột co: <1280 bỏ cột thao tác, 641–1100 bỏ cột người (vẫn qua --q-cols)", /@media \(max-width:1279px\)\{\s*\.pmq\{--q-cols:var\(--q-c1\) minmax\(0,1fr\) 90px 150px 150px\}/.test(CSSX) && /@media \(min-width:641px\) and \(max-width:1100px\)\{\s*\.pmq\{--q-cols:var\(--q-c1\) minmax\(0,1fr\) 90px 150px\}/.test(CSSX));
  /* Tồn đọng cùng lưới */
  t.$('[data-k="old:go"]').click(); await flush();
  ok("G Tồn đọng: tiêu đề là .pmq-grp (cùng lưới), ô chọn ở cột 1 của dòng + 'chọn tất cả' cột 1 thanh hàng loạt", t.$(".pmq-old-h").classList.contains("pmq-grp") &&
    t.rowEl("S-1").firstElementChild.classList.contains("pmq-rk") && !!t.rowEl("S-1").querySelector("[data-pick]") && t.$(".pmq-bulk").firstElementChild.querySelector("[data-pick-all]") && /\.pmq-bulk-m\{grid-column:2\/-1/.test(CSSX));
  t.check = (el, v) => { el.checked = v; el.dispatchEvent(new t.w.Event("change", { bubbles: true })); };
  t.check(t.$("[data-pick-all]"), true); await flush();
  ok("G Tồn đọng vẫn xử lý hàng loạt (chọn tất cả 2/2)", /Đã chọn\s*2\/2/.test(t.$(".pmq-bulk").textContent));
  t.ctl.destroy(); t.w.close();

  /* ---------- W dải tuần */
  t = setup(); await flush();
  const lbl = t.$$(".pmq-wk-c .pmq-wk-l").map(x => x.textContent);
  ok("W ô: Trễ hạn · Hôm nay · T6 · 6 ngày tới (thứ + ngày) · Sau đó · Chưa có hạn", lbl.join("|") === "Trễ hạn|Hôm nay · T6|T7 28|CN 29|T2 30|T3 01|T4 02|T5 03|Sau đó|Chưa có hạn", lbl.join("|"));
  ok("W đếm theo hạn thật: trễ 2 (gồm trễ theo giờ hôm nay), hôm nay 10, T7 1, CN 0, T2 1, T4 1, Sau đó 1, Chưa có hạn 1",
    t.wkN("late") === 2 && t.wkN("today") === 10 && t.wkN("d:2026-11-28") === 1 && t.wkN("d:2026-11-29") === 0 && t.wkN("d:2026-11-30") === 1 && t.wkN("d:2026-12-02") === 1 && t.wkN("far") === 1 && t.wkN("none") === 1);
  ok("W không tính Tồn đọng: tổng dải = 17 = số trên tab", t.$$(".pmq-wk-n").reduce((a, x) => a + parseInt(x.textContent, 10), 0) === 17 && t.$('[data-c="me"]').textContent === "17");
  ok("W chấm theo ưu tiên: ô Trễ = 1 đỏ (Khẩn) + 1 cam (Cao); Hôm nay tối đa 10 chấm", t.wk("late").querySelectorAll(".pmq-wk-d i.pmq-p4").length === 1 && t.wk("late").querySelectorAll(".pmq-wk-d i.pmq-p3").length === 1 &&
    t.wk("today").querySelectorAll(".pmq-wk-d i").length === 10);
  ok("W ô 0 việc: số xám + khoá, aria-pressed=false", t.wk("d:2026-11-29").disabled && t.wk("d:2026-11-29").querySelector(".pmq-wk-z") && t.wk("d:2026-11-29").getAttribute("aria-pressed") === "false");
  ok("W không còn hàng nút lọc theo nhóm", t.$$("[data-f]").length === 0 && !t.$(".pmq-dist"));
  t.wk("d:2026-11-30").click(); await flush();
  ok("W bấm 'T2 30' -> chỉ việc hạn 30/11, aria-pressed=true", t.names().join(",") === "W-2" && t.wk("d:2026-11-30").getAttribute("aria-pressed") === "true");
  ok("W đang lọc: ẩn Tồn đọng", !t.$(".pmq-g--old"));
  t.wk("late").click(); await flush();
  ok("W bấm ô khác -> đổi lọc (Trễ hạn: L-1, L-2)", t.names().join(",") === "L-1,L-2" && t.wk("d:2026-11-30").getAttribute("aria-pressed") === "false");
  t.wk("late").click(); await flush();
  ok("W bấm lại -> bỏ lọc (đủ dòng, Tồn đọng hiện lại)", t.wk("late").getAttribute("aria-pressed") === "false" && !!t.$(".pmq-g--old") && t.names().length === 14);
  ok("W điện thoại: dải cuộn ngang", /@media \(max-width:640px\)\{[\s\S]*\.pmq-wk\{display:flex;overflow-x:auto/.test(CSSX));
  t.ctl.destroy(); t.w.close();

  /* ---------- M Xem thêm 7 + J/K */
  t = setup(); await flush();
  const todayShown = t.$$(".pmq-g--today .pmq-row").length;
  const more = t.$('.pmq-g--today [data-act="grpmore"]');
  ok("M nhóm Hôm nay 10 việc: hiện 7 + 'Xem thêm 3 việc' (aria-expanded=false)", todayShown === 7 && more && /Xem thêm 3 việc/.test(more.textContent) && more.getAttribute("aria-expanded") === "false");
  ok("M số đếm nhóm vẫn là 10", t.$(".pmq-g--today .pmq-grp em").textContent === "10");
  for (let i = 0; i < 9; i++) t.key("j", t.w.document.activeElement);
  ok("M J đi qua dòng đang hiện: trễ 2 + 7 hôm nay -> J lần 9 tới D-6 (không vào D-7..D-9 đang ẩn)", t.ctl._state.sel === "D-6", t.ctl._state.sel);
  t.key("j", t.w.document.activeElement);
  ok("M J tiếp -> sang nhóm sau (W-1), bỏ qua việc đang ẩn", t.ctl._state.sel === "W-1", t.ctl._state.sel);
  t.$('.pmq-g--today [data-act="grpmore"]').click(); await flush();
  ok("M bấm Xem thêm -> đủ 10 dòng, nút thành 'Thu gọn' (aria-expanded=true), focus giữ trên nút", t.$$(".pmq-g--today .pmq-row").length === 10 &&
    /Thu gọn/.test(t.$('.pmq-g--today [data-act="grpmore"]').textContent) && t.$('.pmq-g--today [data-act="grpmore"]').getAttribute("aria-expanded") === "true" && t.w.document.activeElement === t.$('.pmq-g--today [data-act="grpmore"]'));
  t.rowEl("D-9").querySelector(".pmq-open").click(); await flush();
  ok("M sau Xem thêm: cửa sổ chi tiết nhận đủ 10 việc hôm nay trong nav", t.opened.slice(-1)[0][1].nav.names.slice(2, 12).join(",") === "D-0,D-1,D-2,D-3,D-4,D-5,D-6,D-7,D-8,D-9");
  t.$('.pmq-g--today [data-act="grpmore"]').click(); await flush();
  ok("M Thu gọn khi đang chọn D-9 (bị ẩn) -> bỏ chọn, còn 7 dòng", t.$$(".pmq-g--today .pmq-row").length === 7 && t.ctl._state.sel === null);
  t.ctl.destroy(); t.w.close();

  /* ---------- O Enter / bấm dòng -> PMR.openTask với nav */
  t = setup(); await flush();
  t.key("j"); t.key("j", t.w.document.activeElement); t.key("j", t.w.document.activeElement);
  t.key("Enter", t.w.document.body); await flush();
  let op = t.opened.slice(-1)[0];
  const shown = t.names();
  ok("O J J J + Enter -> openTask('D-0', {nav:{names: đúng thứ tự đang hiện}})", op && op[0] === "D-0" && JSON.stringify(op[1].nav.names) === JSON.stringify(shown) && shown.length === 14, op && op[1].nav.names.join(","));
  ok("O names là bản sao (đổi màn sau đó không làm hỏng danh sách của cửa sổ)", op[1].nav.names !== t.ctl._state.data.me.rows);
  op[1].nav.onMove("W-2"); await flush();
  ok("O nav.onMove('W-2') -> W-2 đang chọn (chỉ tô nền), D-0 bỏ chọn", t.rowEl("W-2").classList.contains("pmq-row--sel") && t.rowEl("W-2").getAttribute("aria-current") === "true" && !t.rowEl("D-0").classList.contains("pmq-row--sel"));
  op[1].nav.onMove("KHONG-CO"); await flush();
  ok("O onMove tên lạ -> bỏ qua, giữ W-2", t.ctl._state.sel === "W-2");
  const q0 = t.count("queue.list");
  op[1].onChange(); await flush();
  ok("O cửa sổ báo đổi -> làm mới hàng đợi", t.count("queue.list") > q0);
  t.rowEl("W-3").querySelector(".pmq-hw").click(); await flush();
  ok("O bấm ô người giao trên dòng -> mở W-3", t.opened.slice(-1)[0][0] === "W-3");
  t.rowEl("L-1").querySelector(".pmq-tt small").click(); await flush();
  ok("O bấm dòng 2 (dự án) -> mở L-1", t.opened.slice(-1)[0][0] === "L-1");
  const nOpen = t.opened.length;
  t.rowEl("W-1").querySelector('[data-act="done"]').click(); await flush();
  ok("O bấm vòng Xong -> mark_done, KHÔNG mở cửa sổ", t.opened.length === nOpen && t.last("tasks.mark_done").a.name === "W-1");
  ok("O không còn ngăn chi tiết trong DOM / code", !t.$(".pmq-dr") && !t.$("[data-drawer]") && !/pmq-dr|data-drawer|openDrawer|paintDrawer/.test(JS.replace(/\/\*[\s\S]*?\*\//g, "")) && !/\.pmq-dr/.test(CSSX));
  t.ctl.destroy(); t.w.close();
  /* thiếu openTask của host -> dùng PMR.openTask */
  {
    const seen = [];
    const dom = new JSDOM("<!doctype html><body><div id=v></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#mywork" });
    const w = dom.window;
    w.PMR = { openTask: (n, o) => seen.push([n, o]) };
    w.eval(JS);
    const ctl = w.PMQueue.render(w.document.getElementById("v"), { user: ME, api: (m, a) => Promise.resolve(/queue\.list/.test(m) ? pack(a.tab, a.tab === "me" ? meRows() : []) : {}) });
    await flush();
    w.document.querySelector('.pmq-row[data-name="W-1"] .pmq-open').click(); await flush();
    ok("O host không truyền openTask -> gọi window.PMR.openTask(name, {nav})", seen.length === 1 && seen[0][0] === "W-1" && seen[0][1].nav.names.indexOf("W-1") >= 0);
    ctl.destroy(); w.close();
  }

  /* ---------- C dòng 2: màu dự án + bước / việc con / bình luận */
  t = setup({ pmr: { projectColor: k => ({ rose: { fg: "#c01048", bg: "#fff1f3" }, violet: { fg: "#6941c6", bg: "#f4f3ff" } })[k] || { fg: "#475467", bg: "#f2f4f7" } } }); await flush();
  const dot = n => { const d = t.rowEl(n).querySelector(".pmq-pdot"); return d ? d.getAttribute("style") : null; };
  ok("C chấm màu dự án theo PMR.projectColor(project_color): rose / violet", /--pc:#c01048/.test(dot("L-1")) && /--pc:#6941c6/.test(dot("D-1")) && /Pin Hà Nội/.test(t.rowEl("L-1").querySelector("small").textContent));
  ok("C khoá trống -> màu PMR trả (xám)", /--pc:#475467/.test(dot("F-1")));
  ok("C việc không dự án: không chấm màu", dot("W-1") === null);
  ok("C dòng 2: 'Các bước 2/4' · '2 mới' (bình luận, icon SVG) ; 'Việc con 1/3'", /Các bước 2\/4/.test(t.rowEl("L-1").querySelector("small").textContent) && /2\s*mới/.test(t.rowEl("L-1").querySelector(".pmq-cm").textContent) &&
    !!t.rowEl("L-1").querySelector(".pmq-cm svg") && /Việc con 1\/3/.test(t.rowEl("D-1").querySelector("small").textContent));
  ok("C dữ liệu không có bước / bình luận -> không vẽ số 0", !/Các bước|Việc con|mới/.test(t.rowEl("D-2").querySelector("small").textContent));
  t.ctl.destroy(); t.w.close();
  t = setup({ pmr: { projectColor: () => ({ fg: "red;background:url(x)", bg: "" }) } }); await flush();
  ok("C PMR trả màu không phải #hex -> bỏ, dùng bảng dự phòng (không chèn CSS lạ)", /--pc:#c01048/.test(t.rowEl("L-1").querySelector(".pmq-pdot").getAttribute("style")) && !/url\(/.test(t.$("[data-list]").innerHTML));
  t.ctl.destroy(); t.w.close();
  t = setup(); await flush();
  ok("C không có PMR -> bảng màu dự phòng cùng giá trị hợp đồng (rose #c01048, violet #6941c6, trống = slate #475467)",
    /--pc:#c01048/.test(t.rowEl("L-1").querySelector(".pmq-pdot").getAttribute("style")) && /--pc:#6941c6/.test(t.rowEl("D-1").querySelector(".pmq-pdot").getAttribute("style")) && /--pc:#475467/.test(t.rowEl("F-1").querySelector(".pmq-pdot").getAttribute("style")));
  ok("C cột Hạn = tờ lịch: L-1 'T4 / 25' đỏ, D-0 cam (hôm nay), N-1 nét đứt", t.rowEl("L-1").querySelector(".pmq-dt-t").textContent === "T425" && /pmq-dt--late/.test(t.rowEl("L-1").querySelector(".pmq-dt").className) &&
    /pmq-dt--today/.test(t.rowEl("D-0").querySelector(".pmq-dt").className) && /pmq-dt--none/.test(t.rowEl("N-1").querySelector(".pmq-dt").className));

  /* ---------- P công tắc nhật ký cá nhân + chân bảng */
  const sw = t.$(".pmq-tools .pmq-sw");
  ok("P công tắc trên thanh công cụ: role=switch, aria-checked=false, 'Nhật ký cá nhân (5)'", sw && sw.getAttribute("role") === "switch" && sw.getAttribute("aria-checked") === "false" && /Nhật ký cá nhân\s*\(5\)/.test(sw.textContent));
  ok("P không còn dòng 'Đang ẩn N việc nhật ký cá nhân' dưới bảng", !/Đang ẩn/.test((t.$("[data-note]") || {}).textContent || ""));
  sw.click(); await flush();
  ok("P bật -> include_personal=1, công tắc bật", t.last("queue.list").a.include_personal === 1 && t.$(".pmq-tools .pmq-sw").getAttribute("aria-checked") === "true");
  ok("P phím tắt ở chân bảng một dòng (trong khối bảng)", !!t.$(".pmq-card > .pmq-keys") && /J/.test(t.$(".pmq-card > .pmq-keys").textContent) && /Bấm một dòng để xem chi tiết/.test(t.$(".pmq-keys").textContent));
  t.ctl.destroy(); t.w.close();

  /* ---------- E màn trống */
  t = setup({ h: { "queue.list": a => pack(a.tab, []) } }); await flush();
  ok("E hết việc: 'Không còn việc nào cần làm' + gợi ý + ô biểu tượng, không đầu cột, không dải tuần, không chân bảng",
    /Không còn việc nào cần làm/.test(t.$(".pmq-empty").textContent) && /Việc mới được giao sẽ hiện ở đây/.test(t.$(".pmq-empty").textContent) && !!t.$(".pmq-empty-art svg") &&
    !t.$(".pmq-cols") && t.$("[data-wkbar]").hidden && t.$("[data-keys]").hidden);
  t.$('.pmq-empty [data-act="focus-qa"]').click();
  ok("E nút 'Ghi việc mới' đưa con trỏ vào ô giao việc", t.w.document.activeElement === t.$("[data-qa]"));
  t.ctl.destroy(); t.w.close();

  /* ---------- S tĩnh */
  ok("S token Phê duyệt: chữ 14px, khối bo 14px viền #e5e7eb, dải tuần cùng khối", /\.pmq\{[^}]*font-size:14px/.test(CSSX) && /--q-r:14px/.test(CSSX) && /--q-g200:#e5e7eb/.test(CSSX) && /\.pmq-panel\{background:#fff;border:1px solid var\(--q-g200\);border-radius:var\(--q-r\)/.test(CSSX));
  ok("S theme trong .pmq: ::selection, caret-color, scrollbar", /\.pmq ::selection\{/.test(CSSX) && /\.pmq input,\.pmq textarea\{caret-color:var\(--q-navy\)\}/.test(CSSX) && /scrollbar-color:var\(--q-g300\) transparent/.test(CSSX));
  ok("S ô giao việc một lớp: section không có khung (.pmq-panel), chỉ ô nhập có viền", !/class="pmq-panel pmq-qa"/.test(JS) && /<section class="pmq-qa"/.test(JS));
  ok("S không khung trong khung: form trong khối Cần đồng ý không viền", /\.pmq-ask-form\{[^}]*\}/.test(CSSX) && !/\.pmq-ask-form\{[^}]*border:1px/.test(CSSX));
  ok("S dòng đang chọn chỉ tô nền: không border-left / box-shadow inset / ::before", !/pmq-row--sel[^{]*\{[^}]*(border-left|box-shadow)/.test(CSSX) && !/pmq-row--sel::before/.test(CSSX));
  ok("S không ký tự unicode làm biểu tượng trong JS (→ ← ↑ ↓ × ✓ ▸ ▾ ⋯ ✕ ★)", !/[→←↑↓×✓▸▾⋯✕★▲▼]/.test(JS.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "")));
  ok("S chỉ lớp nổi có bóng (toast, gợi ý @): không box-shadow trên dòng / khối / dải tuần", !/\.pmq-(row|card|wk|wk-c|grp|cols|panel|fbtn|sw)\{[^}]*box-shadow/.test(CSSX));
  ok("S CSS trong namespace .pmq-", CSSX.split("}").map(s => s.split("{")[0].trim()).filter(s => s && !/^@|^(from|to|\d+%)$/.test(s))
    .every(sel => sel.split(",").every(x => /^\s*(\.pmq|:where\(\.pmq\))/.test(x) || /^\s*(input|select|textarea|button|button:disabled)\)?\s*$/.test(x) || /^\s*(from|to|\d+%)\b/.test(x))));
  ok("S JS: không Jinja, không console.log", !/\{\{|\{%|\{#/.test(JS) && !/console\.log/.test(JS));

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
