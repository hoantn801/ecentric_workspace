// Stepper cua CA 26 feature phai esc() du lieu nguoi go - khong chi payment_request.
//
// 31/08 va stepper payment_request; 01/09 BOT A phat hien 25 feature con lai van chay
// ban copy CHUA va (stepper khong phai JS dung chung - moi feature om mot ban sao trong
// main_section.html). Suite nay quet ca 26 feature bang cung ky thuat voi
// test_stepper_escape.mjs: cat than ham theo dem ngoac roi CHAY THAT voi payload doc.
// Khong grep nguon - grep mu sau refactor.
//
// Moi feature dung 3 phep: comment Rejected, approver Approved, approver In Progress
// (26 x 3 = 78). Feature nao cau truc khac lam khong trich duoc ham thi BAO LOI TO
// (fail du 3 phep cua feature do), khong bo qua im lang.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const FEATURES = [
  "affiliate_bonus", "ai_topup", "asset_damage_loss", "asset_request", "budget_setting",
  "compensation_leave", "daily_target", "data_request", "document_request",
  "employee_info_update", "employee_referral", "hiring_request", "hr_activity",
  "late_early_out", "lateral_move", "leave", "livestream_sample", "livestream_supplies",
  "outside_work", "payment_request", "promotion", "purchase_request", "resignation",
  "service_referral", "special_bonus", "system_request",
];
if (FEATURES.length !== 26) { console.error("HONG: danh sach feature phai du 26"); process.exit(1); }

const EVIL = '<img src=x onerror=alert(1)>';
let pass = 0, fail = 0;
function ok(cond, msg) { if (cond) pass++; else { fail++; console.error("  HONG:", msg); } }

// Cat than ham theo dau hieu + dem ngoac (khong cat theo do dai co dinh).
function braceSlice(src, marker, from) {
  const i = src.indexOf(marker, from || 0);
  if (i < 0) return null;
  let depth = 0, start = src.indexOf("{", i + marker.length - 1);
  for (let j = start; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}") { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  return null;
}

for (const feat of FEATURES) {
  let escFn, buildMeta;
  try {
    const src = readFileSync(
      join(here, "..", "..", "features", feat, "ui", "main_section.html"), "utf8");

    const escSrc = braceSlice(src, "function esc(s)");
    if (!escSrc) throw new Error("khong trich duoc ham esc() - cau truc khac mau, cap nhat test");
    escFn = new Function("s", escSrc.slice(1, -1));

    // Than levels.forEach BEN TRONG buildStepper (buildDraftStepper cung co forEach rieng).
    const bs = src.indexOf("function buildStepper(");
    if (bs < 0) throw new Error("khong tim thay function buildStepper - cau truc khac mau");
    const feIdx = src.indexOf("levels.forEach(function(l)", bs);
    if (feIdx < 0) throw new Error("khong tim thay levels.forEach trong buildStepper");
    const body = braceSlice(src, "levels.forEach(function(l)", feIdx - 1);
    if (!body || body.length < 100) throw new Error("khong trich duoc than levels.forEach");

    // Chay that: stub steps/approvers/ap, de than ham tu khai var rows/st/meta.
    buildMeta = new Function("l", "ROWS", "esc", "fmt", `
      var steps = { push: function () {} };
      var approvers = { filter: function () { return ROWS; } };
      var ap = { approval_status: "x", current_level: 0 };
      var meta;
      ${body.slice(1, -1)}
      return meta;`);
  } catch (e) {
    fail += 3;
    console.error("HONG TO [" + feat + "]: " + e.message + " - 3 phep cua feature nay tinh la DO.");
    continue;
  }

  function metaFor(levelStatus, row) {
    return buildMeta(
      { level_status: levelStatus, level_no: 1, approval_mode: "All",
        completed_at: null, due_at: null, level_name: "Cap 1" },
      [Object.assign({ level_no: 1 }, row)], escFn, function () { return ""; });
  }

  let rej, ap, cur;
  try {
    rej = metaFor("Rejected", { status: "Rejected", comment: EVIL, approver: "a@x" });
    ap  = metaFor("Approved", { status: "Approved", approver: EVIL, comment: "" });
    cur = metaFor("In Progress", { status: "Pending", approver: EVIL, comment: "" });
  } catch (e) {
    fail += 3;
    console.error("HONG TO [" + feat + "]: than ham trich ra khong chay duoc (" + e.message + ") - 3 phep tinh la DO.");
    continue;
  }
  ok(!rej.includes("<img") && rej.includes("&lt;img"),
     "[" + feat + "] comment tu choi khong duoc esc - stored XSS quay lai");
  ok(!ap.includes("<img"), "[" + feat + "] ten approver (Approved) khong duoc esc");
  ok(!cur.includes("<img"), "[" + feat + "] ten approver (In Progress) khong duoc esc");
}

console.log(pass + " dat, " + fail + " hong (ky vong 78 phep / 26 feature)");
process.exit(fail || pass !== 78 ? 1 : 0);
