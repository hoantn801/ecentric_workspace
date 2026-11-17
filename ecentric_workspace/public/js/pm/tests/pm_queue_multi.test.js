/* pm_queue_multi.test.js — Việc cần làm, ô giao 1 dòng (PO duyệt 16/11/2026). Chạy: NODE_PATH=<node_modules có jsdom> node pm_queue_multi.test.js
 *  M1 nhiều @ trong một dòng: chip từng người + ×, trùng tên / không tìm thấy xử lý theo từng @, bỏ trùng người, không tính chính mình,
 *     gợi ý @ cho từng @ (không gợi ý lại người đã có), hai người cùng tên gọi.
 *  M2 từ 2 người: radio "Mỗi người một việc" (mặc định) / "Làm chung 1 việc", nhớ trong phiên; "Cần đồng ý" + nhiều người khoá "Làm chung".
 *  M3 tham số gửi lên: chia / chung × có / không Cần đồng ý × 1 / nhiều người; câu thông báo.
 *  M4 "Thêm chi tiết" (nút + Shift+Enter) -> PMR.newTask điền sẵn; ô chỉ xoá khi form tạo xong; ô trống -> form trống.
 *  M5 XSS trong tên người (chip, nút chọn, gợi ý). */
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
  /* ---------- M1 đọc nhiều @ */
  let t = setup(); await flush();
  const P = s => t.w.PMQueue._parseLine(s, { parseDue: t.w.PMR._pure.parseDue, base: new t.w.Date(2026, 10, 13, 9, 30) });
  let p = P("@Lan @Phú @Vũ báo cáo tuần thứ 6");
  ok("M1 '@Lan @Phú @Vũ báo cáo tuần thứ 6' -> 3 @, tên việc sạch, hạn thứ Sáu tuần sau", JSON.stringify(p.tokens) === '["Lan","Phú","Vũ"]' && p.token === "Lan" && p.subject === "báo cáo tuần" && p.due === "2026-11-20", JSON.stringify(p));
  p = P("@Lan, @Phú và @Vũ: gửi file tồn kho gấp");
  ok("M1 '@Lan, @Phú và @Vũ: …' -> bỏ dấu phẩy / 'và' / ':' giữa các @, tên việc không dính chữ nối", p.tokens.length === 3 && p.subject === "gửi file tồn kho" && p.priority === "Urgent", JSON.stringify(p));
  p = P("Gửi @Lan báo cáo cho @Phú");
  ok("M1 @ nằm giữa câu vẫn nhận, tên việc giữ thứ tự chữ", p.tokens.join() === "Lan,Phú" && p.subject === "Gửi báo cáo cho", JSON.stringify(p));
  p = P("@lan @Lan @LAN việc A");
  ok("M1 cùng một @ gõ nhiều lần (khác hoa thường) -> 1 token", p.tokens.length === 1 && p.subject === "việc A");
  p = P("@lan.nguyen@ecentric.vn @Phú gửi file");
  ok("M1 @email đầy đủ + @tên trong cùng dòng", p.tokens.join() === "lan.nguyen@ecentric.vn,Phú" && p.subject === "gửi file", JSON.stringify(p));
  p = P("Gặp khách và chốt giá");
  ok("M1 không có @ -> tokens rỗng, 'và' trong câu giữ nguyên", p.tokens.length === 0 && p.token === "" && p.subject === "Gặp khách và chốt giá");

  /* ---------- M1/M2 giao diện nhiều người */
  ok("M4 nút 'Thêm chi tiết' cạnh 'Giao việc' (type=button, phím tắt Shift+Enter)", (() => { const b = t.$('[data-act="qa-more"]'); return b && b.type === "button" && b.textContent === "Thêm chi tiết" && b.getAttribute("aria-keyshortcuts") === "Shift+Enter" && b.previousElementSibling === t.$("[data-qa-go]"); })());
  t.qi().focus(); await flush();
  ok("M4 dòng gợi ý khi trống (đang ở trong ô): ví dụ nhiều @, Enter để giao, Thêm chi tiết", /@Lan @Phú gửi báo cáo thứ 6 gấp/.test(t.parse()) && /Enter để giao/.test(t.parse()) && /Thêm chi tiết để ghi mô tả, các bước, lặp lại/.test(t.parse()));
  await t.type("@Lan @Phú gửi báo cáo");
  ok("M1 2 người -> 2 chip, mỗi chip có nút × có nhãn", t.chips().length === 2 && /Nguyễn Thị Lan/.test(t.chips()[0].textContent) && /Trần Văn Phú/.test(t.chips()[1].textContent) &&
    t.chips().every(c => { const x = c.querySelector('[data-act="qa-rm"]'); return x && /^Bỏ /.test(x.getAttribute("aria-label")); }));
  const radios = () => t.$$('[data-qa-f="mode"]');
  ok("M2 từ 2 người: radiogroup 2 lựa chọn + chú thích; mặc định Mỗi người một việc", t.$('.pmq-mode[role="radiogroup"]') && radios().length === 2 && radios()[0].checked && radios()[0].value === "split" &&
    /mỗi người có việc riêng; mọi người xong thì việc về Chờ duyệt để bạn đóng/.test(t.$(".pmq-mode").textContent) && /một người bấm Xong là xong cho cả nhóm/.test(t.$(".pmq-mode").textContent) && radios().every(r => r.type === "radio" && r.name === radios()[0].name));
  ok("M2 Cần đồng ý bật (mặc định) + 2 người -> khoá 'Làm chung' + chú thích; nút 'Gửi cho 2 người'", radios()[1].disabled && /Cần đồng ý với nhiều người: mỗi người nhận và trả lời phần của mình/.test(t.parse()) && t.$("[data-qa-go]").textContent === "Gửi cho 2 người");
  /* ask + nhiều người -> create_with_task(recipients, split 1) */
  await t.submit();
  let cw = t.last("assignment.create_with_task");
  ok("M3 Cần đồng ý × 2 người -> create_with_task(recipients JSON, split_per_assignee=1, proposed_end, priority), không có recipient", cw && cw.a.recipients === JSON.stringify(["lan@ecentric.vn", "phu@ecentric.vn"]) && cw.a.split_per_assignee === 1 && !("recipient" in cw.a) && cw.a.proposed_end === "2026-11-14 18:00:00" && cw.a.priority === "Medium" && cw.a.subject === "gửi báo cáo" && t.count("tasks.create") === 0, JSON.stringify(cw && cw.a));
  ok("M3 thông báo: 'Đã gửi cho 2 người, chờ từng người nhận: “…” · hạn …'", /^Đã gửi cho 2 người, chờ từng người nhận: “gửi báo cáo” · hạn T7 14\/11$/.test(t.toast()), t.toast());
  /* bỏ Cần đồng ý -> mở khoá Làm chung, giao thẳng chia người */
  await t.type("@Lan @Phú @Thái chốt số tuần mai 10h");
  await t.setF('[data-qa-f="ask"]', false);
  ok("M2 bỏ Cần đồng ý -> 'Làm chung' bấm được, nút 'Giao cho 3 người'", !radios()[1].disabled && !/Cần đồng ý với nhiều người/.test(t.parse()) && t.$("[data-qa-go]").textContent === "Giao cho 3 người");
  await t.submit();
  let tc = t.last("tasks.create");
  ok("M3 chia × không Cần đồng ý × 3 người -> tasks.create(project='', assignees JSON 3, split_per_assignee=1, hạn, giờ)", tc && tc.a.project === "" && tc.a.assignees === JSON.stringify(["lan@ecentric.vn", "phu@ecentric.vn", "thai@ecentric.vn"]) && tc.a.split_per_assignee === 1 && tc.a.exp_end_date === "2026-11-14" && tc.a.pm_end_time === "10:00:00" && tc.a.subject === "chốt số tuần", JSON.stringify(tc && tc.a));
  ok("M3 thông báo 'Đã giao cho 3 người (mỗi người một việc): “…” · hạn …' + nút Xem", /^Đã giao cho 3 người \(mỗi người một việc\): “chốt số tuần” · hạn T7 14\/11 10:00$/.test(t.toast()) && t.$$(".pmq-toast-b").some(b => b.textContent === "Xem"), t.toast());
  /* Làm chung */
  await t.type("@Lan @Phú dọn kho");
  ok("M2 nhớ trong phiên: Cần đồng ý đã tắt, vẫn Mỗi người một việc", !t.$('[data-qa-f="ask"]').checked && radios()[0].checked);
  await t.setF('[data-qa-f="mode"][value="shared"]', true);
  ok("M2 chọn 'Làm chung' -> radio đổi + focus ở radio (bàn phím đi tiếp được)", radios()[1].checked && t.$(".pmq-mode-o--on input").value === "shared" && t.w.document.activeElement === radios()[1]);
  await t.submit();
  tc = t.last("tasks.create");
  ok("M3 chung × không Cần đồng ý × 2 người -> tasks.create(split_per_assignee=0)", tc.a.split_per_assignee === 0 && tc.a.assignees === JSON.stringify(["lan@ecentric.vn", "phu@ecentric.vn"]) && tc.a.subject === "dọn kho");
  ok("M3 thông báo '(làm chung 1 việc)'", /^Đã giao cho 2 người \(làm chung 1 việc\): “dọn kho”/.test(t.toast()), t.toast());
  await t.type("@Lan @Phú việc kế");
  ok("M2 nhớ 'Làm chung' cho việc giao kế tiếp", radios()[1].checked);
  await t.setF('[data-qa-f="ask"]', true);
  ok("M2 bật lại Cần đồng ý -> ép về Mỗi người một việc + khoá Làm chung", radios()[0].checked && radios()[1].disabled);
  await t.submit();
  cw = t.last("assignment.create_with_task");
  ok("M3 chung (đã chọn) × Cần đồng ý × 2 người -> vẫn split_per_assignee=1 (server chỉ hỗ trợ chia)", cw.a.split_per_assignee === 1 && JSON.parse(cw.a.recipients).length === 2 && cw.a.subject === "việc kế");
  await t.type("@Lan @Phú việc sau");
  await t.setF('[data-qa-f="ask"]', false);
  ok("M2 tắt Cần đồng ý lại -> trở về lựa chọn 'Làm chung' của người dùng", radios()[1].checked && !radios()[1].disabled);
  /* 1 người: giữ nguyên như cũ */
  await t.type("@Lan gọi khách");
  ok("M2 1 người -> không hiện lựa chọn chia người", !t.$(".pmq-mode") && t.$("[data-qa-go]").textContent === "Giao việc");
  await t.submit();
  tc = t.last("tasks.create");
  ok("M3 không Cần đồng ý × 1 người -> tasks.create không gửi split_per_assignee", tc.a.assignees === JSON.stringify(["lan@ecentric.vn"]) && !("split_per_assignee" in tc.a) && /^Đã giao cho Nguyễn Thị Lan: “gọi khách”/.test(t.toast()));
  await t.type("@Lan gọi khách lần 2");
  await t.setF('[data-qa-f="ask"]', true);
  await t.submit();
  cw = t.last("assignment.create_with_task");
  ok("M3 Cần đồng ý × 1 người -> create_with_task(recipient) như cũ, không recipients/split", cw.a.recipient === "lan@ecentric.vn" && !("recipients" in cw.a) && !("split_per_assignee" in cw.a) && /Chờ người nhận bấm Nhận việc/.test(t.toast()));
  t.ctl.destroy(); t.w.close();

  /* ---------- M1 theo từng @: trùng tên, không tìm thấy, ×, bỏ trùng, chính mình */
  t = setup(); await flush();
  await t.type("@Lan @vu kiểm kho");
  ok("M1 @vu trùng 2 người -> chỉ token đó bắt chọn (2 nút), @Lan vẫn rõ", /Nguyễn Thị Lan/.test(t.chips()[0].textContent) && t.$$('.pmq-pick[data-tok="vu"]').length === 2 && /@vu · Chọn:/.test(t.parse()));
  let n0 = t.sends();
  await t.submit();
  ok("M1 gửi khi chưa chọn -> báo riêng 'Có nhiều người tên “vu”', không gọi server", t.sends() === n0 && /Có nhiều người tên “vu”, chọn một người\./.test(t.parse()));
  t.$$('.pmq-pick[data-tok="vu"]')[1].click(); await flush();
  ok("M1 chọn Lê Vũ -> ô nhập đổi @Vũ, 2 chip, hiện lựa chọn chia người", t.qi().value === "@Lan @Vũ kiểm kho" && t.chips().length === 2 && /Lê Vũ/.test(t.chips()[1].textContent) && !!t.$(".pmq-mode"), t.qi().value);
  await t.type("@Lan @khongcoai @Phú việc X");
  ok("M1 @ không có -> chip lỗi riêng 'Không tìm thấy “@khongcoai”', người khác vẫn rõ", /Không tìm thấy “@khongcoai”/.test(t.parse()) && t.chips().length === 3 && t.chips()[1].classList.contains("pmq-chip--bad") && !t.chips()[0].classList.contains("pmq-chip--bad"));
  n0 = t.sends();
  await t.submit();
  ok("M1 gửi -> báo lỗi đúng token không tìm thấy, không gọi server", t.sends() === n0 && /Không tìm thấy “@khongcoai”\. Gõ @ rồi chọn người/.test(t.$(".pmq-ferr").textContent));
  t.$('[data-act="qa-rm"][data-tok="khongcoai"]').click(); await flush();
  ok("M1 × trên chip lỗi -> bỏ đúng @ đó khỏi ô, còn 2 người, focus về ô nhập", t.qi().value === "@Lan @Phú việc X" && t.chips().length === 2 && t.w.document.activeElement === t.qi(), t.qi().value);
  t.$('[data-act="qa-rm"][data-email="phu@ecentric.vn"]').click(); await flush();
  ok("M1 × trên chip người -> bỏ người đó, còn 1 người (ẩn lựa chọn chia người)", t.qi().value === "@Lan việc X" && t.chips().length === 1 && !t.$(".pmq-mode"), t.qi().value);
  await t.type("@Lan @Nguyễn @lan@ecentric.vn gửi file");
  ok("M1 nhiều @ cùng trỏ một người -> bỏ trùng: 1 chip, coi như 1 người nhận", t.chips().length === 1 && !t.$(".pmq-mode") && t.$("[data-qa-go]").textContent === "Gửi yêu cầu");
  await t.submit();
  cw = t.last("assignment.create_with_task");
  ok("M1 ...gửi 1 người (recipient), tên việc sạch", cw.a.recipient === "lan@ecentric.vn" && cw.a.subject === "gửi file", JSON.stringify(cw.a));
  await t.type("@Hoàn @Lan @Phú họp tuần");
  ok("M1 có @chính mình kèm người khác -> chip 'Tôi · không tính', vẫn là 2 người nhận", /Tôi/.test(t.chips()[0].textContent) && /không tính/.test(t.chips()[0].textContent) && t.$("[data-qa-go]").textContent === "Gửi cho 2 người" && /Giao cho 2 người:/.test(t.$(".pmq-mode").textContent));
  await t.submit();
  cw = t.last("assignment.create_with_task");
  ok("M1 ...gửi không kèm chính mình", cw.a.recipients === JSON.stringify(["lan@ecentric.vn", "phu@ecentric.vn"]));
  await t.type("@Hoàn @Lan sửa slide");
  ok("M1 @mình + 1 người -> 1 người nhận (không bật chia người)", !t.$(".pmq-mode") && t.$("[data-qa-go]").textContent === "Gửi yêu cầu");
  await t.type("@Hoàn đọc tài liệu");
  ok("M1 chỉ @mình -> việc của tôi (Thêm việc)", t.$("[data-qa-go]").textContent === "Thêm việc" && /Tôi/.test(t.parse()));
  /* gợi ý @ cho từng @ */
  await t.type("@Lan gửi @Th");
  ok("M1 gợi ý @ ở @ thứ hai (combobox)", !t.$(".pmq-acl").hidden && t.$$(".pmq-ac-i").length === 1 && /Đỗ Thái/.test(t.$(".pmq-ac-i").textContent));
  t.kd("Enter"); await flush();
  ok("M1 Enter chọn -> chèn @Thái, 2 chip, không gửi", t.qi().value === "@Lan gửi @Thái " && t.chips().length === 2 && t.$(".pmq-acl").hidden);
  await t.type("@Lan @la");
  ok("M1 gợi ý không lặp lại người đã có ở @ khác (chỉ còn Phạm Lành)", t.$$(".pmq-ac-i").length === 1 && /Phạm Lành/.test(t.$(".pmq-ac-i").textContent));
  t.kd("Escape");
  await t.type("@vu");
  t.kd("ArrowDown"); t.kd("Enter"); await flush();   /* Lê Vũ (xếp theo tên: Đặng Vũ, Lê Vũ) */
  const qv = t.qi(); qv.value += "@vu"; qv.setSelectionRange(qv.value.length, qv.value.length); qv.dispatchEvent(new t.w.Event("input", { bubbles: true })); await flush();
  ok("M1 thêm @vu lần hai: gợi ý vẫn có cả 2 người tên Vũ", t.$$(".pmq-ac-i").length === 2);
  t.kd("Enter"); await flush();   /* Đặng Vũ */
  ok("M1 hai người cùng tên gọi 'Vũ' -> người sau chèn theo email (@vu.dang), đủ 2 người nhận", t.qi().value === "@Vũ @vu.dang " && t.chips().length === 2 && /Lê Vũ/.test(t.chips()[0].textContent) && /Đặng Vũ/.test(t.chips()[1].textContent), t.qi().value);

  /* ---------- M5 XSS trong tên người */
  await t.type("@Bông @Lan việc");
  ok("M5 tên người có HTML (trùng tên -> nút chọn): không chèn phần tử, chữ hiện nguyên văn", !t.$("[data-parse] img") && !t.$("[data-parse] .pmq-pick b") && t.w.__x === undefined && t.$$(".pmq-pick").some(b => b.textContent === XN) && t.$$(".pmq-pick").some(b => b.textContent === XN2));
  t.$$(".pmq-pick").find(b => b.textContent === XN).click(); await flush();
  ok("M5 chip người tên HTML: esc trong chữ, title, aria-label của ×", !t.$("[data-parse] img") && t.w.__x === undefined && t.chips().some(c => c.textContent.indexOf(XN) >= 0) && t.$$('[data-act="qa-rm"]').some(x => x.getAttribute("aria-label") === "Bỏ " + XN), t.parse());
  await t.type("@bon");
  ok("M5 gợi ý @ với tên HTML: esc", !t.$(".pmq-acl").hidden && !t.$(".pmq-acl img") && !t.$(".pmq-acl b b") && t.w.__x === undefined);
  t.kd("Escape");
  await t.submit();
  t.ctl.destroy(); t.w.close();

  /* ---------- M4 Thêm chi tiết */
  t = setup(); await flush();
  const refreshes = () => t.count("queue.list");
  t.$('[data-act="qa-more"]').click(); await flush();
  ok("M4 ô trống + Thêm chi tiết -> PMR.newTask chỉ với onCreated (form trống như nút menu)", t.nt.length === 1 && JSON.stringify(Object.keys(t.nt[0])) === '["onCreated"]' && typeof t.nt[0].onCreated === "function");
  await t.type("@Lan @Phú báo cáo tuần thứ 6 gấp");
  await t.setF('[data-qa-f="ask"]', false);
  await t.setF('[data-qa-f="mode"][value="shared"]', true);
  t.$('[data-act="qa-more"]').click(); await flush();
  let o = t.nt[1];
  ok("M4 điền sẵn: tên (bỏ @, hạn, gấp), 2 người, hạn, ưu tiên, làm chung, không Cần đồng ý", o && o.subject === "báo cáo tuần" && JSON.stringify(o.assignees) === JSON.stringify(["lan@ecentric.vn", "phu@ecentric.vn"]) && o.due === "2026-11-20" && o.time === "" && o.priority === "Urgent" && o.split === false && o.requestMode === false, JSON.stringify(o));
  ok("M4 mở form KHÔNG gửi gì, ô 1 dòng còn nguyên", t.sends() === 0 && t.qi().value === "@Lan @Phú báo cáo tuần thứ 6 gấp");
  const r0 = refreshes();
  o.onCreated({ name: "T-X" }); await flush();
  t.qi().focus(); await flush();
  ok("M4 form tạo xong -> xoá ô 1 dòng + hàng đợi làm mới", t.qi().value === "" && refreshes() > r0 && /Ví dụ:/.test(t.parse()));
  await t.type("@Lan @Phú việc A");
  await t.setF('[data-qa-f="ask"]', true);
  t.$('[data-act="qa-more"]').click(); await flush();
  o = t.nt[2];
  ok("M4 Cần đồng ý + 2 người -> requestMode true, split true", o.requestMode === true && o.split === true && o.assignees.length === 2);
  t.qi().value = "đã gõ việc khác";
  o.onCreated({}); await flush();
  ok("M4 tạo xong khi ô đã gõ việc khác -> không xoá chữ mới", t.qi().value === "đã gõ việc khác");
  await t.type("Đọc hợp đồng mai 10h");
  t.kd("Enter", { shiftKey: true }); await flush();
  o = t.nt[3];
  ok("M4 Shift+Enter = Thêm chi tiết; việc của tôi -> assignees [], Cần đồng ý theo lựa chọn đang nhớ (QA5: form tự bỏ qua khi chỉ có Tôi), hạn + giờ", o && JSON.stringify(o.assignees) === "[]" && o.requestMode === true && o.due === "2026-11-14" && o.time === "10:00" && o.subject === "Đọc hợp đồng" && o.split === false && t.sends() === 0, JSON.stringify(o));
  await t.type("Việc chỉ có tên");
  ok("M4 không ghi hạn -> điền hạn mặc định đang hiện (ngày mai), ưu tiên Bình thường", (t.$('[data-act="qa-more"]').click(), t.nt[4].due === "2026-11-14" && t.nt[4].priority === "Medium"));
  await t.type("@Lan @vu kiểm kho");
  const nn = t.nt.length;
  t.$('[data-act="qa-more"]').click(); await flush();
  ok("M4 còn @ trùng tên -> không mở form, báo chọn người cho đúng token", t.nt.length === nn && /Có nhiều người tên “vu”/.test(t.parse()));
  t.w.document.querySelector("[data-qa]").dispatchEvent(new t.w.Event("compositionstart"));
  t.kd("Enter", { shiftKey: true, isComposing: true }); await flush();
  ok("M4 Shift+Enter khi bộ gõ đang ghép chữ -> bỏ qua", t.nt.length === nn);
  t.w.document.querySelector("[data-qa]").dispatchEvent(new t.w.Event("compositionend"));
  t.ctl.destroy(); t.w.close();
  t = setup({ noNewTask: true }); await flush();
  await t.type("Việc A");
  t.$('[data-act="qa-more"]').click(); await flush();
  ok("M4 thiếu PMR.newTask -> báo tải lại, không vỡ", /Chưa mở được form Giao việc/.test(t.toast()) && t.qi().value === "Việc A");
  t.ctl.destroy(); t.w.close();

  /* ---------- CSS: vùng bấm + namespace */
  ok("CSS × trên chip: 24px + vùng bấm mở rộng 4px = 32px; điện thoại 32px + 4px = 40px", /\.pmq-chip-x\{[^}]*width:24px;height:24px/.test(CSS) && /\.pmq-chip-x::after\{content:"";position:absolute;inset:-4px\}/.test(CSS) && /@media \(max-width:640px\)\{[\s\S]*\.pmq-chip-x\{width:32px;height:32px\}/.test(CSS));
  ok("CSS radio chia người: ≥32px máy tính, ≥40px điện thoại; nút Thêm chi tiết ≥40px điện thoại", /\.pmq-mode-o\{[^}]*min-height:32px/.test(CSS) && /@media \(max-width:640px\)\{[\s\S]*\.pmq-mode-o\{[^}]*min-height:40px/.test(CSS) && /@media \(max-width:640px\)\{[\s\S]*\.pmq-qa-more\{min-height:42px\}/.test(CSS));
  ok("CSS mới đều trong namespace .pmq-", ["pmq-chip", "pmq-chip-x", "pmq-mode", "pmq-mode-o", "pmq-mode-note", "pmq-qa-more"].every(k => CSS.indexOf("." + k) >= 0));

  let fail = 0;
  res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
  console.log(`${res.length - fail}/${res.length} passed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
