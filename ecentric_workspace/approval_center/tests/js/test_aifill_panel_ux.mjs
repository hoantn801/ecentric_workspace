// Copyright (c) 2026, eCentric and contributors
// Panel "AI dien ho" (ec_aifill) - UX 03/11: nguoi dung biet AI dang lam gi, sai o dau, lam gi tiep.
//   * dang doc -> noi truoc mat bao lau (khong tuong treo)
//   * loi quyen -> cau THAT cua server, khong phai "Thu lai sau"
//   * dien xong -> noi bang chu con o bat buoc nao trong (dien thoai khong phai cuon ca form)
//   * Ctrl+Enter chay; o nhap co nhan cho doc man hinh; vung thong bao la role=status
//     node ecentric_workspace/approval_center/tests/js/test_aifill_panel_ux.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = readFileSync(join(here, "..", "..", "..", "public", "js", "ec_aifill.bundle.js"), "utf8");
let oks = 0, fails = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  HONG: " + n); } };
const flush = async (n) => { for (let k = 0; k < (n || 10); k++) await new Promise((r) => setTimeout(r, 4)); };
const fld = (m, l, req) => `<div class="fld" data-fld="${m}"><label>${l}${req ? ' <span class="req">*</span>' : ""}</label><input data-model="${m}"></div>`;
const FORM = `<div class="content"><div class="tabs"></div><div class="form">${fld("payee_full_name", "Người nhận", 1)}${fld("payment_amount", "Số tiền", 1)}${fld("reason", "Lý do / nội dung", 1)}${fld("brand", "Brand liên quan", 1)}${fld("note2", "Ghi chú", 0)}</div></div>`;

function boot(suggest) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + FORM + "</body></html>", { runScripts: "outside-only", url: "https://x.test/approvals/payment-request", pretendToBeVisual: true });
  const w = dom.window; w.__calls = [];
  // jsdom khong co layout: offsetParent luon null -> coi moi khoi la dang hien.
  Object.defineProperty(w.HTMLElement.prototype, "offsetParent", { get() { return this.parentNode; } });
  w.frappe = { csrf_token: "x", call: (o) => { const m = o.method.split(".").pop(); w.__calls.push(m);
    if (m === "bootstrap") return Promise.resolve({ message: { enabled: true, remaining: 5, cap: 20, max_chars: 8000, max_files: 5, file_exts: ["pdf"], batch: { max_drafts: 10, has_flags: false, ns: "a.b." } } });
    if (m === "suggest") return suggest();
    return Promise.resolve({ message: {} }); } };
  w.eval(SRC); return w;
}
const $ = (w, s) => w.document.querySelector(s);
const typeAndRun = (w, text) => { const n = $(w, ".ec-aifill-note"); n.value = text; n.dispatchEvent(new w.Event("input")); $(w, ".ec-aifill-run").click(); };

{ const w = boot(() => new Promise(() => {})); await flush();
  ok(!!$(w, ".ec-aifill-note"), "panel duoc ve");
  ok($(w, ".ec-aifill-note").getAttribute("aria-label") === "Nội dung cho AI đọc", "o nhap co nhan cho doc man hinh");
  ok($(w, ".ec-aifill-msg").getAttribute("role") === "status", "vung thong bao la role=status");
  ok($(w, ".ec-aifill-modes").getAttribute("role") === "group", "can gat che do la group co nhan");
  typeAndRun(w, "Thanh toan 5 trieu"); await flush();
  ok(/đang đọc/i.test($(w, ".ec-aifill-msg").textContent) && /giây/.test($(w, ".ec-aifill-msg").textContent), "dang doc -> noi truoc mat bao lau");
  ok($(w, ".ec-aifill-run").disabled, "nut chinh khoa khi dang doc"); }

{ const w = boot(() => Promise.reject({ _server_messages: JSON.stringify([JSON.stringify({ message: "Bạn chưa được bật tính năng AI điền hộ." })]) })); await flush();
  typeAndRun(w, "abc"); await flush();
  ok(/Bạn chưa được bật tính năng AI điền hộ/.test($(w, ".ec-aifill-msg").textContent), "loi quyen -> cau that cua server");
  ok(!$(w, ".ec-aifill-run").disabled, "loi xong mo lai nut"); }

{ const w = boot(() => Promise.resolve({ message: { fields: { payee_full_name: "Cty ABC", payment_amount: "500000" }, sources: {}, dropped_count: 0, files_read: [], files_rejected: [], probe: { ok: true }, remaining: 4 } }));
  await flush();
  typeAndRun(w, "Tra Cty ABC 500k"); await flush(20);
  const msg = $(w, ".ec-aifill-msg").textContent;
  ok(/Đã điền 2 ô/.test(msg), "bao so o da dien");
  ok(/Còn 2 ô bắt buộc/.test(msg) && /Lý do \/ nội dung/.test(msg) && /Brand liên quan/.test(msg), "noi ten o bat buoc con trong");
  ok(!/Người nhận,|Số tiền,|Ghi chú/.test(msg.split("Còn")[1] || ""), "khong ke o da dien / o khong bat buoc");
  ok(/tự bấm Gửi/.test(msg), "chi buoc tiep theo");
  ok(w.__ecAifill.gapLabels().join("|") === "Lý do / nội dung|Brand liên quan", "gapLabels bo dau * va dau AI dien"); }

{ const w = boot(() => new Promise(() => {})); await flush();
  const n = $(w, ".ec-aifill-note"); n.value = "x";
  n.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", ctrlKey: true, bubbles: true })); await flush();
  ok(w.__calls.includes("suggest"), "Ctrl+Enter -> chay AI");
  const w2 = boot(() => new Promise(() => {})); await flush();
  const n2 = w2.document.querySelector(".ec-aifill-note"); n2.value = "x";
  n2.dispatchEvent(new w2.KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await flush();
  ok(!w2.__calls.includes("suggest"), "Enter thuong van xuong dong, khong chay"); }

{ const w = boot(() => new Promise(() => {})); await flush();
  w.__ecAifill.B.rows.push({ key: "r1", file: { name: "hoadon.pdf", size: 10 }, fields: {}, busy: false });
  const h = w.__ecAifill.batchHtml();
  ok(/aria-label="Xem và sửa dòng hoadon\.pdf"/.test(h), "nut mo dong trong lo co nhan"); }

console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
