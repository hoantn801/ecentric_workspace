// Copyright (c) 2026, eCentric and contributors
//
// 14/09: form Booking Request len production, o Brand hien "Danh muc brand dang trong" trong
// khi he thong co 28 brand. Goi thang API thi `get_bootstrap` tra DU 28 - tuc server dung,
// man hinh sai: no doc `state.boot.options.brands`, ma bootstrap tra khoa `form_options`.
//
// Mot chu sai, khong loi, khong cảnh bao - chi la mot danh sach rong. Nguoi dung se go tay
// ten brand da co san, sinh brand trung, dung cai form nay sinh ra de tranh.
//
// Suite nay CAT than ham that ra khoi main_section.html roi CHAY voi dung hinh dang ma
// bootstrap that tra ve (do duoc tren production, khong bia).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = readFileSync(
  join(here, "..", "..", "features", "booking_request", "ui", "main_section.html"), "utf8");

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

let pass = 0, fail = 0;
const ok = (c, m) => { console.log((c ? "  ok - " : "  FAIL - ") + m); pass += c ? 1 : 0; fail += c ? 0 : 1; };

const than = braceSlice(SRC, "function brandRows()");
if (!than) { console.error("HONG: khong trich duoc brandRows - cau truc khac mau"); process.exit(1); }
const thanChung = braceSlice(SRC, "function ttChung()");
if (!thanChung) { console.error("HONG: khong trich duoc ttChung - cau truc khac mau"); process.exit(1); }

// Hinh dang THAT cua bootstrap, do tren production 14/09.
const BOOT_THAT = { context: {}, is_system_manager: 1, tabs: {},
  form_options: { booking_types: ["KOL/KOC Chi dinh", "Middle KOL/KOC", "Massive"],
                  brands: [{ value: "AND-VN", label: "AND-VN - Andros" },
                           { value: "Anlene", label: "Anlene" }] } };

function chay(boot) {
  const f = new Function("state", `
    function ttChung() ${thanChung}
    function brandRows() ${than}
    return brandRows();`);
  return f({ boot: boot });
}

ok(chay(BOOT_THAT).length === 2,
   "doc duoc brand tu khoa form_options (hinh dang THAT cua get_bootstrap)");
ok(chay({ options: { brands: [{ value: "X" }] } }).length === 1,
   "van doc duoc neu ban sau doi sang khoa options - khong gay ra hoi quy");
ok(chay({}).length === 0, "bootstrap rong thi tra mang rong, khong nem loi");
ok(chay(null) !== undefined && chay(null).length === 0, "boot null cung khong nem loi");

// Chan mu: ten khoa THAT phai xuat hien trong nguon, khong chi trong chu thich.
const js = SRC.slice(SRC.indexOf('<script id="ec-booking-request">'));
const khongChuThich = js.replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");
ok(khongChuThich.includes("form_options"),
   "ma nguon (khong ke chu thich) phai nhac toi form_options");

console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
