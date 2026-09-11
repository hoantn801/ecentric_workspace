// Copyright (c) 2026, eCentric and contributors
//
// 11/09: hai phieu nhap AI Topup cua hon.nguyen treo tu 16:51 den 17:11. Phieu LUU duoc
// (`save_draft` chay), chi `submit_request` bi server chan - vi ho chon "Tai khoan moi" cho
// cap (Heygen, ai@ecentric.vn) ma cap do DA co trong EC AI Account. Luat chan la DUNG; cai
// sai la man hinh: `applyBackendError` khong khop cau nao nen roi xuong `friendlyErr` va hien
// "Da co loi khi luu/gui yeu cau. Vui long thu lai" - mot loi khuyen KHONG BAO GIO dung, vi
// thu lai khong phai cach sua.
//
// Suite nay CAT than ham `applyBackendError` THAT ra khoi main_section.html roi CHAY no voi
// dung cau server nem ra. Khong grep nguon: grep chi chung minh co mot doan chu, khong chung
// minh duoc no khop.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = readFileSync(
  join(here, "..", "..", "features", "ai_topup", "ui", "main_section.html"), "utf8");

function braceSlice(src, marker) {
  const i = src.indexOf(marker);
  if (i < 0) return null;
  let depth = 0; const start = src.indexOf("{", i + marker.length - 1);
  for (let j = start; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}") { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  return null;
}

const body = braceSlice(SRC, "function applyBackendError(e)");
if (!body) { console.error("HONG: khong trich duoc applyBackendError - cau truc khac mau"); process.exit(1); }

// Chay than ham that, stub dung nhung thu no cham toi.
let daToast = null, daTo = null;
const apply = new Function("e", "extractServerMsg", "showFieldErrors", "toast", `
  ${body.slice(1, -1)}
`);
const run = (msg) => {
  daToast = null; daTo = null;
  const r = apply({message: msg},
    () => msg,
    (errs) => { daTo = errs; },
    (t, err) => { daToast = {t, err}; });
  return r;
};

let pass = 0, fail = 0;
const ok = (c, m) => { console.log((c ? "  ok - " : "  FAIL - ") + m); pass += c ? 1 : 0; fail += c ? 0 : 1; };

// --- cau THAT cua server (application/service.py) ---
const CAU_THAT = "AI Account đã tồn tại cho tool và email này. Vui lòng chọn Tài khoản hiện có.";
ok(run(CAU_THAT) === true, "cau 'AI Account da ton tai' PHAI duoc nhan (khong roi xuong loi chung chung)");
ok(daTo && daTo.account_mode, "phai to do o 'Hinh thuc tai khoan' - do la o nguoi dung can sua");
ok(daToast && daToast.err === true && String(daToast.t).includes("Tài khoản hiện có"),
   "phai hien NGUYEN VAN cau cua server, khong tu bia loi khac");

// --- o 'Hinh thuc tai khoan' phai nam trong danh sach showFieldErrors quet ---
// Dat loi vao mot o KHONG co trong danh sach = khong ai hien, va cung khong ai xoa di.
const sfe = braceSlice(SRC, "function showFieldErrors(errs)");
ok(!!sfe && sfe.includes('"account_mode"'),
   "showFieldErrors phai quet ca account_mode, neu khong thi to do xong khong hien ra");

// --- KHONG duoc bat bua: nhung cau khac phai di dung nhanh cua no ---
ok(run("New Account requests require ai_tool") === true, "cau 'New Account requests require' van duoc nhan");
ok(run("Bạn không có quyền xem yêu cầu này.") === false,
   "loi quyen KHONG duoc nhan nham vao nhanh trung tai khoan");
ok(run("Something went wrong") === false, "loi la van tra false de roi xuong loi chung");

console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
