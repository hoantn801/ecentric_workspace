// Copyright (c) 2026, eCentric and contributors
// Khao sat noi bo - asset JS (public/surveys/). Chay: node approval_center/tests/js/test_survey_core.mjs
//  1. ECSvy.path() la ban sao cua surveys/domain/answers.py::path - cung bo ca voi
//     surveys/tests/test_domain.py::TestPath. Lech = trang "Tiep" dua nguoi dung sang phan
//     khac voi phan server se kiem bat buoc.
//  2. Ve duoc moi loai cau hoi (form tra loi, ban soan, tong hop) ma khong nem loi, va KHONG
//     chen chuoi nguoi dung chua thoat (XSS).
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pub = path.resolve(here, "../../../public/surveys");
let pass = 0, fail = 0;
const ok = (c, m) => { console.log((c ? "  ok - " : "  FAIL - ") + m); c ? pass++ : fail++; };

const ctx = { console, URLSearchParams, Math, JSON, Date, Promise, setTimeout, clearTimeout,
  window: {}, document: { getElementById: () => null, readyState: "complete", addEventListener() {} },
  location: { search: "" }, Array, Object, String, Number, RegExp };
ctx.window = ctx;
ctx.window.location = { search: "" };
vm.createContext(ctx);
for (const f of ["ec_survey_core.js", "ec_survey_form.js", "ec_survey_summary.js", "ec_survey_editor.js"]) {
  vm.runInContext(fs.readFileSync(path.join(pub, f), "utf8"), ctx, { filename: f });
}
const S = ctx.ECSvy, F = ctx.ECSvyForm, SUM = ctx.ECSvySummary, E = ctx.ECSvyEditor;
ok(S && F && SUM && E, "4 asset nap duoc, dang ky window.ECSvy / ECSvyForm / ECSvySummary / ECSvyEditor");

// ---------------------------------------------------------------- 1. duong di --
const opts = (ids, goto = {}) => ids.map((i) => ({ id: i, label: i.toUpperCase(), goto: goto[i] || "" }));
const form = { items: [
  { id: "q1", kind: "question", type: "single", title: "Q1", branch: true, options: opts(["yes", "no", "skip"], { no: "s3", skip: "__submit__" }) },
  { id: "s2", kind: "section", title: "S2", next: "" }, { id: "q2", kind: "question", type: "short_text", title: "Q2" },
  { id: "s3", kind: "section", title: "S3", next: "" }, { id: "q3", kind: "question", type: "short_text", title: "Q3" },
] };
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
ok(eq(S.path(form, {}), ["__start__", "s2", "s3"]), "mac dinh di qua moi phan");
ok(eq(S.path(form, { q1: { sel: ["no"] } }), ["__start__", "s3"]), "re nhanh nhay toi phan 3");
ok(eq(S.path(form, { q1: { sel: ["skip"] } }), ["__start__"]), "re nhanh 'Gui bieu mau' dung luon");
const f2 = { items: [{ id: "s1", kind: "section", next: "s3" }, { id: "q1", kind: "question", type: "short_text" },
  { id: "s2", kind: "section" }, { id: "q2", kind: "question", type: "short_text" }, { id: "s3", kind: "section" }, { id: "q3", kind: "question", type: "short_text" }] };
ok(eq(S.path(f2, {}), ["s1", "s3"]), "'Sau phan nay' cua section duoc dung khi khong co re nhanh");
const f3 = { items: [{ id: "s1", kind: "section" }, { id: "q1", kind: "question", type: "single", branch: true, options: opts(["a"], { a: "s1" }) }, { id: "s2", kind: "section" }] };
ok(eq(S.path(f3, { q1: { sel: ["a"] } }), ["s1", "s2"]), "nhay lui khong tao vong lap");
ok(S.isEmpty({ type: "single" }, { sel: [] }) && !S.isEmpty({ type: "single" }, { sel: [], other: "x" }), "isEmpty: 'Khac' co chu la da tra loi");
const r1 = S.seeded("KS-1|a@x"), r2 = S.seeded("KS-1|a@x");
ok(eq([r1(), r1(), r1()], [r2(), r2(), r2()]), "xao tron co hat giong: cung nguoi cung thu tu");

// -------------------------------------------------------------- 2. ve moi loai --
const EVIL = '<img src=x onerror=alert(1)>';
const all = [
  { type: "short_text", validation: { kind: "email" } }, { type: "paragraph" },
  { type: "single", options: opts(["a", "b"]), allow_other: true }, { type: "multi", options: opts(["a", "b"]), min_select: 1, max_select: 2 },
  { type: "dropdown", options: opts(["a"]) }, { type: "scale", scale_min: 0, scale_max: 10, min_label: "x", max_label: "y" },
  { type: "rating", rating_max: 5 }, { type: "grid_single", rows: [{ id: "r1", label: "R" }], cols: [{ id: "c1", label: "C" }] },
  { type: "grid_multi", rows: [{ id: "r1", label: "R" }], cols: [{ id: "c1", label: "C" }] },
  { type: "ranking", options: opts(["a", "b"]) }, { type: "date" }, { type: "time" }, { type: "file", max_files: 2 },
].map((q, i) => Object.assign({ id: "q" + i, kind: "question", title: EVIL, description: EVIL, required: true }, q));
let threw = null, leaked = [];
for (const q of all) {
  try {
    const h = F.question(q, undefined, { err: "Loi" }) + F.question(q, q.type === "file" ? [{ url: "/private/files/a", name: EVIL }] : undefined, {});
    if (h.indexOf(EVIL) >= 0) leaked.push(q.type);
    if (h.indexOf('data-q="' + q.id + '"') < 0 && q.type !== "file") leaked.push(q.type + ":no-data-q");
  } catch (e) { threw = q.type + ": " + e.message; }
}
ok(!threw, "form tra loi ve du 13 loai" + (threw ? " - " + threw : ""));
ok(!leaked.length, "form tra loi thoat chuoi nguoi dung" + (leaked.length ? " - " + leaked.join(",") : ""));

const sum = { total: 2, questions: {} };
all.forEach((q) => { sum.questions[q.id] = { answered: 1, counts: { a: 1 }, other: 1, other_samples: [EVIL], distribution: { 1: 1 }, average: 1, table: { r1: { c1: 1 } }, average_rank: { a: 1, b: 2 }, samples: [EVIL] }; });
let sh = "";
try { sh = SUM.render({ items: all }, sum, {}); } catch (e) { threw = e.message; }
ok(sh.length > 0 && !threw, "tong hop ve du 13 loai");
ok(sh.indexOf(EVIL) < 0, "tong hop thoat cau tra loi chu tu do");

const B = { form: { items: all.concat([{ id: "s9", kind: "section", title: EVIL, next: "" }, { id: "n9", kind: "note", title: EVIL }]) },
  settings: { title: EVIL, is_quiz: 1, accent_color: "#2C3DA6" }, data: { stats: { responses: 0 }, status: "Draft" }, active: null };
let eh = "";
try {
  eh += E.render(B);
  B.form.items.forEach((it) => { B.active = it.id; eh += E.render(B); });
} catch (e) { threw = e.message; }
ok(eh.length > 0 && !threw, "trinh soan ve duoc moi loai o ca hai che do (gon / dang soan)" + (threw ? " - " + threw : ""));
ok(eh.indexOf(EVIL) < 0, "trinh soan thoat tieu de / mo ta");

console.log(pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
