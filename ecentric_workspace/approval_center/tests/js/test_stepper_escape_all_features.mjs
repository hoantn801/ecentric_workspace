// Stepper cua CA 26 feature phai esc() du lieu nguoi go - khong chi payment_request.
//
// 31/08 va stepper payment_request; 01/09 BOT A phat hien 25 feature con lai van chay
// ban copy CHUA va (stepper khong phai JS dung chung - moi feature om mot ban sao trong
// main_section.html). Suite nay quet ca 26 feature bang cung ky thuat voi
// test_stepper_escape.mjs: cat than ham theo dem ngoac roi CHAY THAT voi payload doc.
// Khong grep nguon - grep mu sau refactor.
//
// Moi feature dung 3 phep: comment Rejected, approver Approved, approver In Progress.
// Feature nao cau truc khac lam khong trich duoc ham thi BAO LOI TO (fail du 3 phep cua
// feature do), khong bo qua im lang.
//
// TU QUET, khong liet ke tay. Ban dau danh sach go tay 26 cai - va ngay trong dem do,
// PR #409 them form thu 27 (contract_review) copy dung stepper chua va, va bo test nay
// KHONG HE HAY BIET. Mot danh sach go tay chi canh duoc qua khu; thu muc features/ moi
// la hien tai.
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const FEAT_DIR = join(here, "..", "..", "features");
const FEATURES = readdirSync(FEAT_DIR, { withFileTypes: true })
  .filter(d => d.isDirectory() && existsSync(join(FEAT_DIR, d.name, "ui", "main_section.html")))
  .map(d => d.name).sort();
// Chan mu: it hon 27 nghia la cach quet hong (01/09 co 27 form), khong phai he thong gon lai.
if (FEATURES.length < 27) {
  console.error("HONG: chi quet duoc " + FEATURES.length + " feature (<27) - cach quet da mu");
  process.exit(1);
}

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

console.log(pass + " dat, " + fail + " hong (" + FEATURES.length + " feature x 3 phep)");
// Nguong PHAI theo so feature quet duoc, khong phai hang so. Hang 78 la cua thoi 26
// feature; sang 27 feature thanh 81 phep -> in "0 hong" ma van exit 1, va xoa bot mot
// feature lai lam no XANH (BOT 10, 01/09). Runner cua minh doc DONG CUOI chu khong doc
// ma thoat nen khong ai thay - hai loi do luong chong nhau.
const want = FEATURES.length * 3;
if (pass !== want) console.error("HONG: chay " + pass + " phep, ky vong " + want);
process.exit(fail || pass !== want ? 1 : 0);
