/* Kiem thu HOP DONG TOKEN cua cac bundle CSS dung chung (khong can jsdom, khong can site):
 *   node ecentric_workspace/public/js/tests/test_shared_css_tokens.js <duong-dan-repo>
 *
 * Vi sao can cai nay. ec_formkit tung hardcode 33 lan mau hex du no la component
 * DUNG CHUNG. Khong ai thay sai, vi khong co cai gi kiem ca - va thuc te luc do
 * cung khong co cach nao khac: token --ec-* chi song trong .ec-shell-*, nen tang
 * component khong voi toi duoc. Sau khi A59 dua primitive len :root va chuan hoa
 * ec_formkit, cong nay giu cho no khong troi ve cho cu.
 *
 * Kiem 3 dieu:
 *   1. ec_formkit KHONG con literal mau/z-index trong phan rule (khoi alias :root
 *      duoc phep giu literal - do la luoi an toan co chu y, A59 dieu 2).
 *   2. ec_shell van khai primitive o :root (neu mat, moi bundle con im lang roi ve
 *      fallback va hop dong token vo hieu ma khong ai bao).
 *   3. Khong bundle dung chung nao xoa/doi ten token da co consumer.
 *
 * Ma thoat: 0 = dat, 1 = hong. */
"use strict";
const fs = require("fs");
const path = require("path");

const repo = process.argv[2] || ".";
const CSSDIR = path.join(repo, "ecentric_workspace", "public", "css");
const read = (f) => fs.readFileSync(path.join(CSSDIR, f), "utf8");
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "");

let fail = 0;
function ok(cond, msg) {
  console.log((cond ? "PASS - " : "FAIL - ") + msg);
  if (!cond) fail++;
}

// --- 1. ec_formkit: phan rule phai sach literal --------------------------------
const fk = stripComments(read("ec_formkit.bundle.css"));
const fkFirstBrace = fk.indexOf("}");
const fkRules = fkFirstBrace >= 0 ? fk.slice(fkFirstBrace + 1) : fk;

const hex = fkRules.match(/#[0-9A-Fa-f]{3,8}\b/g) || [];
const rgba = fkRules.match(/rgba?\([^)]*\)/g) || [];
const zlit = fkRules.match(/z-index:\s*[0-9]+/g) || [];

ok(hex.length === 0, "ec_formkit: khong con mau hex trong phan rule" + (hex.length ? " (con: " + hex.join(", ") + ")" : ""));
ok(rgba.length === 0, "ec_formkit: khong con rgb/rgba trong phan rule" + (rgba.length ? " (con: " + rgba.join(", ") + ")" : ""));
ok(zlit.length === 0, "ec_formkit: z-index dung token, khong phai so tran" + (zlit.length ? " (con: " + zlit.join(", ") + ")" : ""));
ok(/var\(--ec-fk-/.test(fkRules), "ec_formkit: phan rule that su dung token --ec-fk-*");

// Khoi alias phai tro ve primitive dung chung, khong phai chi literal.
const fkRoot = fkFirstBrace >= 0 ? fk.slice(0, fkFirstBrace) : "";
const aliasToPrimitive = (fkRoot.match(/var\(--ec-(?!fk-)[a-z0-9-]+/g) || []).length;
ok(aliasToPrimitive >= 10, "ec_formkit: khoi alias tro ve primitive dung chung (" + aliasToPrimitive + " alias)");

// --- 2. ec_shell: primitive phai o :root --------------------------------------
const shell = stripComments(read("ec_shell.bundle.css"));
const rootBlock = (shell.match(/:root\s*\{[^}]*\}/) || [""])[0];
const MUST_BE_ON_ROOT = [
  "--ec-navy", "--ec-navy-50", "--ec-gray-100", "--ec-gray-200",
  "--ec-gray-300", "--ec-gray-500", "--ec-gray-700", "--ec-gray-900", "--ec-surface",
];
const missing = MUST_BE_ON_ROOT.filter((t) => !new RegExp(t + "\\s*:").test(rootBlock));
ok(missing.length === 0, "ec_shell: primitive khai o :root" + (missing.length ? " (thieu: " + missing.join(", ") + ")" : ""));

const SEMANTIC = ["--ec-border-default", "--ec-focus-ring", "--ec-selected-bg", "--ec-selected-text"];
const missingSem = SEMANTIC.filter((t) => !new RegExp(t + "\\s*:").test(rootBlock));
ok(missingSem.length === 0, "ec_shell: token semantic co mat" + (missingSem.length ? " (thieu: " + missingSem.join(", ") + ")" : ""));

// --- 3. khong xoa token dang co consumer --------------------------------------
const allCss = ["ec_shell.bundle.css", "ec_formkit.bundle.css", "ec_datepicker.bundle.css"]
  .map(read).join("\n");
const declared = new Set((stripComments(allCss).match(/(--ec-[a-z0-9-]+)\s*:/g) || [])
  .map((s) => s.replace(/\s*:$/, "")));
const consumed = new Set((stripComments(allCss).match(/var\((--ec-[a-z0-9-]+)/g) || [])
  .map((s) => s.replace("var(", "")));
const dangling = [...consumed].filter((t) => !declared.has(t));
ok(dangling.length === 0, "khong co var(--ec-*) tro toi token chua khai" + (dangling.length ? " (treo: " + dangling.join(", ") + ")" : ""));

console.log(fail === 0 ? "\nALL_PASS" : "\n" + fail + " HONG");
process.exit(fail === 0 ? 0 : 1);
