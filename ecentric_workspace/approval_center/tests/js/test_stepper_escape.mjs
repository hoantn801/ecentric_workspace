// Stepper phai esc() du lieu nguoi go - cho da bi BOT 3 bat ngay 31/08.
//
// meta cua tung buoc la HTML (span "Qua han" la chu dich), nen ten approver va comment
// tu choi phai duoc esc() NGAY TAI CHO di vao chuoi. Truoc 31/08 timeline/banner esc dung
// ma stepper bo sot - stored XSS cho bat ky ai xem phieu.
//
// Kiem bang cach CHAY that: dung lai ham esc + doan dung meta voi du lieu doc, roi soi
// chuoi ra co con the <script> song khong. Khong grep nguon - grep mu sau refactor.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(
  join(here, "..", "..", "features", "payment_request", "ui", "main_section.html"), "utf8");

let pass = 0, fail = 0;
function ok(cond, msg) { if (cond) pass++; else { fail++; console.error("  HONG:", msg); } }

// Cat than ham theo dau hieu + dem ngoac (bai hoc: cat theo do dai co dinh thi them code
// la truot cua so).
function braceSlice(marker) {
  const i = src.indexOf(marker);
  ok(i >= 0, "khong tim thay marker: " + marker + " - phep kiem lac hau, phai cap nhat");
  if (i < 0) return "";
  let depth = 0, start = src.indexOf("{", i);
  for (let j = start; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}") { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  return "";
}

// 1. Dung lai moi truong toi thieu va CHAY doan dung meta voi payload doc.
const escSrc = braceSlice("function esc(");
ok(escSrc.includes("&lt;") || escSrc.includes("&amp;") || escSrc.includes("replace"),
   "khong trich duoc ham esc()");
const esc = new Function("s", escSrc.slice(1, -1));

const EVIL = '<img src=x onerror=alert(1)>';
const forEachBody = braceSlice('levels.forEach(function(l){ var rows=approvers.filter');
ok(forEachBody.length > 100, "khong trich duoc than levels.forEach cua stepper");

const buildMeta = new Function("l", "rows", "esc", "fmt", `
  var st="upcoming", meta="";
  var approvers = rows; var ap = {approval_status:"x", current_level: 0};
  ${forEachBody.slice(1, -1).replace(/^\s*var rows=approvers\.filter\([^;]*;\s*var st="upcoming", meta="";/, "")
    .replace(/steps\.push\([^;]*\);\s*$/, "")}
  return meta;`);

function metaFor(levelStatus, row) {
  return buildMeta({ level_status: levelStatus, level_no: 1, approval_mode: "All",
                     completed_at: null, due_at: null, level_name: "Cap 1" },
                   [Object.assign({ level_no: 1 }, row)], esc, function () { return ""; });
}

// 2. Comment tu choi doc phai bi trung hoa.
const rejMeta = metaFor("Rejected", { status: "Rejected", comment: EVIL, approver: "a@x" });
ok(!rejMeta.includes("<img"), "comment tu choi khong duoc esc - stored XSS quay lai");
ok(rejMeta.includes("&lt;img"), "comment phai hien duoi dang van ban da trung hoa");

// 3. Ten approver doc (o ca nhanh Approved lan In Progress) phai bi trung hoa.
const apMeta = metaFor("Approved", { status: "Approved", approver: EVIL, comment: "" });
ok(!apMeta.includes("<img"), "ten approver (Approved) khong duoc esc");
const curMeta = metaFor("In Progress", { status: "Pending", approver: EVIL, comment: "" });
ok(!curMeta.includes("<img"), "ten approver (In Progress) khong duoc esc");

// 4. Span "Qua han" van la HTML that (esc qua tay se giet tinh nang nay).
const dueLevel = { level_status: "In Progress", level_no: 1, approval_mode: "All",
                   completed_at: null, due_at: "2000-01-01", level_name: "Cap 1" };
const dueMeta = buildMeta(dueLevel, [{ level_no: 1, status: "Pending", approver: "a@x" }],
                          esc, function () { return "d"; });
ok(dueMeta.includes('<span class="ov">'), "span Qua han phai con la HTML that, khong bi esc oan");

console.log(pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
