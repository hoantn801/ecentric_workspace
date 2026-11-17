// Copyright (c) 2026, eCentric and contributors
// /weekly-update (17/11/2026): tuan mac dinh theo LICH + hoi lai khi nop nham tuan.
//
// Su co that: 15/11 (CN) va 16/11 (T2) hai ban bao cao W46 roi vao W47 vi trang tu nhay
// sang tuan sau tu T6 18:00. Test chay CHINH cac ham trong main_section.html (cat ra theo
// ten, chay trong vm) - khong chep lai logic.
//
//   node ecentric_workspace/approval_center/tests/js/test_weekly_update_week_default.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = readFileSync(path.join(here, "../../../weekly_report/pages/weekly_update/main_section.html"), "utf8");

// Cat nguyen than ham theo dau ngoac (bo qua ngoac trong chuoi / regex don gian la du o day).
function grab(signature) {
  const start = html.indexOf(signature);
  if (start < 0) throw new Error("khong thay: " + signature);
  let i = html.indexOf("{", start), depth = 0;
  for (; i < html.length; i++) {
    const c = html[i];
    if (c === "{") depth++;
    else if (c === "}") { depth--; if (depth === 0) break; }
  }
  return html.slice(start, i + 1);
}

const src = [
  "function pad2(n) { return n < 10",
  "function fmtDate(d) {",
  "function fmtDateFull(d) {",
  "function weekFromMonday(mondayIn) {",
  "function mondayFromLabel(label) {",
  "function weekFromLabel(label) {",
  "function calculateCurrentWeek(nowIn) {",
  "async function pickDefaultWeek(cur, nowIn) {",
  "function wuIsoWeekOf(d) {",
  "function wuWeekInName(name) {",
  "function wuWeekMismatch(files, label, nowIn) {",
].map(grab).join("\n");

const ctx = { console: { ...console, warn: () => {} }, CTX: { employeeId: "HR-EMP-1" }, apiGet: null, URL, encodeURIComponent };
vm.createContext(ctx);
vm.runInContext(src, ctx);

let pass = 0, fail = 0;
function ok(cond, msg) { if (cond) { pass++; } else { fail++; console.log("HONG:", msg); } }
const at = (y, m, d, h = 9, mi = 0) => new Date(y, m - 1, d, h, mi);

// 1. Tuan mac dinh = tuan lich, KHONG nhay tu T6 18:00
ok(ctx.calculateCurrentWeek(at(2026, 11, 13, 17, 0)).weekLabel === "2026-W46", "T6 17:00 -> W46");
ok(ctx.calculateCurrentWeek(at(2026, 11, 13, 18, 30)).weekLabel === "2026-W46", "T6 18:30 van W46 (truoc day nhay W47)");
ok(ctx.calculateCurrentWeek(at(2026, 11, 14, 10)).weekLabel === "2026-W46", "T7 -> W46");
ok(ctx.calculateCurrentWeek(at(2026, 11, 15, 22)).weekLabel === "2026-W46", "CN 22:00 (thien.vo) -> W46");
ok(ctx.calculateCurrentWeek(at(2026, 11, 16, 10, 22)).weekLabel === "2026-W47", "T2 -> W47");
ok(ctx.calculateCurrentWeek(at(2027, 1, 1)).weekLabel === "2026-W53", "1/1/2027 thuoc 2026-W53");
const w47 = ctx.weekFromLabel("2026-W47");
ok(w47.weekLabel === "2026-W47" && w47.monday.getDate() === 16 && w47.friday.getDate() === 20, "weekFromLabel W47 = 16-20/11");
ok(ctx.weekFromLabel("2026-W46").weekStartDisplay === "09/11", "W46 bat dau 09/11");

// 2. Tuan truoc con Draft
async function pick(prevStatus, now, throws) {
  ctx.apiGet = async () => { if (throws) throw new Error("mang"); return { data: prevStatus ? [{ name: "x", status: prevStatus }] : [] }; };
  return ctx.pickDefaultWeek(ctx.calculateCurrentWeek(now), now);
}
let r = await pick("Draft", at(2026, 11, 16, 10, 22));
ok(r.week.weekLabel === "2026-W46" && r.hint && r.hint.kind === "opened-prev", "T2 + W46 con Draft -> mo W46 (kieu.nguyen)");
r = await pick("Draft", at(2026, 11, 18, 9));
ok(r.week.weekLabel === "2026-W46", "T4 van mo tuan truoc");
r = await pick("Draft", at(2026, 11, 19, 9));
ok(r.week.weekLabel === "2026-W47" && r.hint && r.hint.kind === "prev-missing", "T5 -> mo tuan nay + nhac");
r = await pick("Submitted", at(2026, 11, 16, 9));
ok(r.week.weekLabel === "2026-W47" && r.hint === null, "da nop tuan truoc -> tuan nay, khong nhac");
r = await pick(null, at(2026, 11, 16, 9));
ok(r.week.weekLabel === "2026-W47" && r.hint === null, "khong co ban ghi tuan truoc -> tuan nay");
r = await pick("Draft", at(2026, 11, 16, 9), true);
ok(r.week.weekLabel === "2026-W47" && r.hint === null, "loi mang -> giu tuan nay, khong chan trang");

// 3. Hoi lai khi nop nham tuan
const now = at(2026, 11, 16, 10);
const f = (name) => [{ name }];
ok(ctx.wuWeekMismatch(f("Bao_cao_tuan_46_2026_Team_Production.pptx"), "2026-W47", now).includes("tuần 46"), "kieu.nguyen: tuan_46 nop W47 -> hoi");
ok(ctx.wuWeekMismatch(f("Weekly Report W46 (09–15 11 2026) – Thiện.pdf"), "2026-W47", now).includes("tuần 46"), "thien.vo: W46 nop W47 -> hoi");
ok(ctx.wuWeekMismatch(f("Báo cáo Tuần 46.pdf"), "2026-W47", now) !== "", "co dau: Tuần 46 -> hoi");
ok(ctx.wuWeekMismatch(f("Weekly_Report_W46_2026.pdf"), "2026-W46", now) === "", "dung tuan -> im");
ok(ctx.wuWeekMismatch(f("Weekly_Report_W2_Nov_2026_09-15.pptx"), "2026-W46", now) === "", "W2_Nov (tuan 2 cua thang) -> im");
ok(ctx.wuWeekMismatch(f("weekly report 1.11-14.11.pdf"), "2026-W46", now) === "", "'weekly' khong co so -> im");
ok(ctx.wuWeekMismatch(f("deck.pdf"), "2026-W48", now).includes("CHƯA tới"), "nop tuan tuong lai -> hoi");
ok(ctx.wuWeekMismatch(f("deck.pdf"), "2026-W47", now) === "", "tuan nay, ten trung tinh -> im");
ok(ctx.wuWeekMismatch([], "2026-W46", now) === "", "khong tep, tuan truoc -> im");

// 4. Khong mo them duong nop (bai hoc 409, p230): goi xac nhan nam TRONG doServerSubmit
const body = grab("async function doServerSubmit() {");
ok(/wuWeekMismatch\(files, data\.week_label\)/.test(body), "doServerSubmit goi wuWeekMismatch");
ok(body.indexOf("wuWeekMismatch(") < body.indexOf("wuUploadDeck("), "hoi TRUOC khi tai tep len");
ok(!/Rollover sau deadline T6 18:00/.test(html), "da bo nhay tuan T6 18:00");

console.log("JS: " + pass + " dat / " + fail + " hong");
process.exit(fail ? 1 : 0);
