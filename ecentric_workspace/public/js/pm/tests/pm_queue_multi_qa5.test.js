/* pm_queue_multi_qa5.test.js — QA 16/11 cho giao 1 dòng nhiều người + "Thêm chi tiết" (commit 4e387a7). Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue_multi_qa5.test.js
 *  Q1 × trên chip khi các @ nối bằng dấu phẩy ("@Lan,@Phú"): trước đây × Phú không làm gì, × Lan biến phần còn lại thành chữ thường
 *     -> việc tự giao cho chính mình với tên ",@Phú …".
 *  Q2 × trên chip khi các @ nối bằng "và": chữ "và" không được dính vào tên việc.
 *  Q3 chọn gợi ý @ khi con trỏ nằm GIỮA một @ đã có: gợi ý không loại chính người đó (đứng đầu, Enter không đổi người), chọn xong thay cả @
 *     (không để lại đuôi chữ).
 *  Q4 chữ dán dạng Unicode tổ hợp (NFD, vd copy từ PDF / macOS): × và nút chọn người vẫn có tác dụng.
 *  Q5 chọn người qua gợi ý mà tên gọi trùng với một @ CHƯA chọn (@vu đang hỏi "Chọn") -> chèn theo email, không nuốt mất @ kia.
 *  Q6 "Thêm chi tiết" cho việc của tôi: chuyển đúng lựa chọn "Cần đồng ý" đang nhớ (form tự bỏ qua khi chỉ có Tôi).
 *  Q7 A11y: radio "Làm chung" bị khoá có aria-describedby trỏ tới câu giải thích. Hướng dẫn nói rõ Cần đồng ý + nhiều người = mỗi người một việc. */
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
const ME = "hoan@ecentric.vn", TODAY = "2026-11-13", NOW = "09:30";   /* server: T6 13/11 */
const BUCKETS = [{ key: "today", label: "Hôm nay" }];
const pack = tab => ({ today: TODAY, now: NOW, tab, rows: [], counts: {}, buckets: BUCKETS, asks: [], personal_hidden: 0, waiting: [], truncated: 0 });
const XN = '<img src=x onerror="window.__x=1"> Bông', XN2 = "<b onmouseover=window.__x=2>Bông</b> Bông";
const PEOPLE = [{ email: ME, full_name: "Trần Hoàn" }, { email: "lan@ecentric.vn", full_name: "Nguyễn Thị Lan" }, { email: "lanh@ecentric.vn", full_name: "Phạm Lành" },
  { email: "phu@ecentric.vn", full_name: "Trần Văn Phú" }, { email: "thai@ecentric.vn", full_name: "Đỗ Thái" },
  { email: "vu.dang@ecentric.vn", full_name: "Đặng Vũ" }, { email: "vu.le@ecentric.vn", full_name: "Lê Vũ" },
  { email: "bong1@ecentric.vn", full_name: XN }, { email: "bong2@ecentric.vn", full_name: XN2 }];

function setup(o) {
  o = o || {};
  const dom = new JSDOM("<!doctype html><body><div id=v></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#mywork", pretendToBeVisual: true });
  const w = dom.window, calls = [], nt = [];
  w.fetch = () => Promise.reject(new Error("no network"));
  w.eval(PMRJS);
  w.eval(JS);
  if (!o.noNewTask) w.PMR.newTask = x => { nt.push(x); return null; };
  else w.PMR.newTask = undefined;
  const H = Object.assign({
    "queue.list": a => pack(a.tab === "give" ? "give" : "me"),
    "tasks.create": () => ({ name: "T-NEW" }), "assignment.create_with_task": a => (a.recipients ? { task: "T-SP", children: ["T-C1", "T-C2"], requests: ["R1", "R2"], split: 1 } : { task: "T-REQ", request: "R-1" }),
    "assignment.list_assignable": () => ({ rows: PEOPLE })
  }, o.h || {});
  const api = (method, args) => { const m = method.replace("ecentric_workspace.pm.api.", ""); calls.push({ m, a: args }); const fn = H[m]; if (!fn) return Promise.reject(new Error("no " + m));
    try { return Promise.resolve(fn(args || {}, calls)); } catch (e) { return Promise.reject(e); } };
  const c = w.document.getElementById("v");
  const ctl = w.PMQueue.render(c, { api, user: ME, tab: "me", openTask: () => { },
    head: (t, s, r) => `<div class="pm-head"><div><h1>${t}</h1><div class="sub">${s}</div></div><div>${r || ""}</div></div>` });
  const $ = s => w.document.querySelector(s), $$ = s => Array.from(w.document.querySelectorAll(s));
  const count = m => calls.filter(x => x.m === m).length;
  const last = m => calls.filter(x => x.m === m).slice(-1)[0];
  const qi = () => $("[data-qa]");
  const type = async v => { const i = qi(); i.focus(); i.value = v; try { i.setSelectionRange(v.length, v.length); } catch (_) { } i.dispatchEvent(new w.Event("input", { bubbles: true })); await flush(); };
  const submit = async () => { $("[data-qa-form]").dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true })); await flush(); };
  const toast = () => ($(".pmq-toast [data-tm]") || {}).textContent || "";
  const parse = () => $("[data-parse]").textContent;
  const chips = () => $$("[data-parse] .pmq-tok--who .pmq-chip");
  const setF = async (sel, v) => { const n = $(sel); if (n.type === "checkbox" || n.type === "radio") n.checked = v; else n.value = v; n.dispatchEvent(new w.Event("change", { bubbles: true })); await flush(); };
  const kd = (k, x) => qi().dispatchEvent(new w.KeyboardEvent("keydown", Object.assign({ key: k, bubbles: true, cancelable: true }, x || {})));
  const sends = () => count("tasks.create") + count("assignment.create_with_task");
  return { w, c, ctl, calls, nt, $, $$, count, last, qi, type, submit, toast, parse, chips, setF, kd, sends };
}

(async () => {
  /* ---------- Q1 "@Lan,@Phú" */
  let t = setup(); await flush();
  await t.type("@Lan,@Phú gửi file");
  ok("Q1 '@Lan,@Phú gửi file' -> 2 chip", t.chips().length === 2, t.parse());
  t.$('[data-act="qa-rm"][data-email="phu@ecentric.vn"]').click(); await flush();
  ok("Q1 × Phú (sau dấu phẩy) -> bỏ được Phú, còn Lan", t.chips().length === 1 && /Nguyễn Thị Lan/.test(t.chips()[0].textContent) && !/Phú/.test(t.qi().value), t.qi().value);
  await t.type("@Lan,@Phú gửi file");
  t.$('[data-act="qa-rm"][data-email="lan@ecentric.vn"]').click(); await flush();
  ok("Q1 × Lan (trước dấu phẩy) -> còn Phú là người nhận, không thành việc của tôi", t.chips().length === 1 && /Trần Văn Phú/.test(t.chips()[0].textContent) && t.$("[data-qa-go]").textContent !== "Thêm việc", t.qi().value + " | " + t.$("[data-qa-go]").textContent);
  await t.submit();
  let cw = t.last("assignment.create_with_task");
  ok("Q1 ...gửi cho Phú, tên việc sạch 'gửi file' (không có ',@Phú')", cw && cw.a.recipient === "phu@ecentric.vn" && cw.a.subject === "gửi file" && t.count("tasks.create") === 0, JSON.stringify(cw && cw.a));

  /* ---------- Q2 "@Lan và @Phú" */
  await t.type("@Lan và @Phú báo cáo tồn");
  t.$('[data-act="qa-rm"][data-email="phu@ecentric.vn"]').click(); await flush();
  await t.submit();
  cw = t.last("assignment.create_with_task");
  ok("Q2 '@Lan và @Phú báo cáo tồn' × Phú -> tên việc 'báo cáo tồn' (không còn 'và')", cw && cw.a.recipient === "lan@ecentric.vn" && cw.a.subject === "báo cáo tồn", JSON.stringify(cw && cw.a));
  await t.type("@Lan và @Phú báo cáo tồn");
  t.$('[data-act="qa-rm"][data-email="lan@ecentric.vn"]').click(); await flush();
  ok("Q2 × Lan -> ô còn '@Phú báo cáo tồn'", t.qi().value === "@Phú báo cáo tồn", t.qi().value);
  t.ctl.destroy(); t.w.close();

  /* ---------- Q3 con trỏ giữa một @ đã có */
  t = setup(); await flush();
  await t.type("@Lan @Phú báo cáo");
  let i = t.qi(); i.setSelectionRange(8, 8);   /* "@Lan @Ph|ú báo cáo" */
  i.dispatchEvent(new t.w.MouseEvent("click", { bubbles: true })); await flush();
  const items = () => t.$$(".pmq-ac-i").map(x => x.textContent);
  ok("Q3 bấm vào giữa '@Phú' -> gợi ý vẫn có Trần Văn Phú (không coi là 'đã có')", !t.$(".pmq-acl").hidden && items().some(x => /Trần Văn Phú/.test(x)), JSON.stringify(items()));
  ok("Q3 ...người đang chọn (Phú) đứng đầu: Enter ngay không đổi người nhận", /Trần Văn Phú/.test(items()[0]));
  t.kd("Enter"); await flush();
  ok("Q3 Enter khi con trỏ giữa '@Phú' -> giữ '@Lan @Phú báo cáo'", t.qi().value === "@Lan @Phú báo cáo" && t.chips().length === 2, t.qi().value);
  i.setSelectionRange(8, 8); i.dispatchEvent(new t.w.MouseEvent("click", { bubbles: true })); await flush();
  const li = items().findIndex(x => /Phạm Lành/.test(x));
  for (let k = 0; k < li; k++) t.kd("ArrowDown");
  t.kd("Enter"); await flush();
  ok("Q3 chọn Phạm Lành -> thay cả '@Phú' thành '@Lành', không để lại đuôi 'ú'", t.qi().value === "@Lan @Lành báo cáo", t.qi().value);
  ok("Q3 ...2 người nhận: Lan + Lành", t.chips().length === 2 && /Phạm Lành/.test(t.chips()[1].textContent));
  t.ctl.destroy(); t.w.close();

  /* ---------- Q4 NFD */
  t = setup(); await flush();
  const NFD = "@Lan @Phú việc X";
  await t.type(NFD);
  ok("Q4 chữ NFD: vẫn nhận 2 người", t.chips().length === 2, t.parse());
  t.$('[data-act="qa-rm"][data-email="phu@ecentric.vn"]').click(); await flush();
  ok("Q4 × Phú trên chữ NFD -> bỏ được (còn 1 chip)", t.chips().length === 1 && /Nguyễn Thị Lan/.test(t.chips()[0].textContent), t.qi().value);
  await t.type("@Lan @vũ kiểm kho");
  t.$$('.pmq-pick[data-tok]')[0].click(); await flush();   /* Đặng Vũ */
  t.$$('.pmq-pick[data-tok]').length;
  ok("Q4 chọn người cho @vũ (NFD) -> ô nhập đổi theo, 2 người rõ", t.chips().length === 2 && !t.$("[data-parse] .pmq-chip--bad") && t.qi().value.normalize("NFC") === "@Lan @Vũ kiểm kho", t.qi().value);
  t.ctl.destroy(); t.w.close();

  /* ---------- Q5 tên gọi trùng với @ chưa chọn */
  t = setup(); await flush();
  await t.type("@vu @Lê");
  ok("Q5 gợi ý '@Lê' -> Lê Vũ", !t.$(".pmq-acl").hidden && /Lê Vũ/.test(t.$(".pmq-ac-i").textContent));
  t.kd("Enter"); await flush();
  ok("Q5 chọn Lê Vũ khi '@vu' còn chờ chọn -> chèn '@vu.le' (không trùng tên gọi), '@vu' vẫn hỏi Chọn", t.qi().value === "@vu @vu.le " && t.$$('.pmq-pick[data-tok="vu"]').length === 2, t.qi().value + " | " + t.parse());
  t.ctl.destroy(); t.w.close();

  /* ---------- Q6 Thêm chi tiết: Cần đồng ý đang nhớ */
  t = setup(); await flush();
  await t.type("Đọc hợp đồng");
  t.$('[data-act="qa-more"]').click(); await flush();
  ok("Q6 việc của tôi + Cần đồng ý đang bật (mặc định) -> requestMode true (thêm người trong form vẫn cần đồng ý như nút menu)", t.nt[0] && t.nt[0].requestMode === true && JSON.stringify(t.nt[0].assignees) === "[]", JSON.stringify(t.nt[0]));
  await t.type("@Lan gọi khách");
  await t.setF('[data-qa-f="ask"]', false);
  await t.type("Đọc hợp đồng 2");
  t.$('[data-act="qa-more"]').click(); await flush();
  ok("Q6 đã tắt Cần đồng ý trước đó -> việc của tôi mở form với requestMode false", t.nt[1] && t.nt[1].requestMode === false, JSON.stringify(t.nt[1]));
  t.ctl.destroy(); t.w.close();

  /* ---------- Q7 a11y + Hướng dẫn */
  t = setup(); await flush();
  await t.type("@Lan @Phú việc");
  const sh = t.$('[data-qa-f="mode"][value="shared"]'), note = t.$(".pmq-mode-note");
  ok("Q7 radio 'Làm chung' bị khoá -> aria-describedby trỏ tới câu giải thích", sh.disabled && note && note.id && sh.getAttribute("aria-describedby") === note.id);
  t.ctl.destroy(); t.w.close();
  const GUIDE = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_guide.js"), "utf8");
  ok("Q7 Hướng dẫn: Cần đồng ý + nhiều người luôn là mỗi người một việc", /Cần đồng ý<\/b>[^"]*luôn[^"]*mỗi người một việc/i.test(GUIDE));
  ok("Q7 Hướng dẫn ≤ 24.576 byte", Buffer.byteLength(GUIDE, "utf8") <= 24576, Buffer.byteLength(GUIDE, "utf8"));

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
