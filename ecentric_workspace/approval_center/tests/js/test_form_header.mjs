// Copyright (c) 2026, eCentric and contributors
// Dau trang form phe duyet kieu thanh cong cu dinh (phuong an C, 23/11/2026): markup that cua form
// Payment Request + asset public/js/ec_form_header.bundle.js tren jsdom.
//     node ecentric_workspace/approval_center/tests/js/test_form_header.mjs
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, "..", "..", "..");
const FH = fs.readFileSync(path.join(ROOT, "public", "js", "ec_form_header.bundle.js"), "utf8");
const FEAT = path.join(HERE, "..", "..", "features");
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };
const flush = async () => { for (let k = 0; k < 8; k++) await new Promise((r) => setTimeout(r, 3)); };

// 1. Moi form (tru brand_weight) co dung mot thanh #ec-fh, tab nam TRONG thanh, khong con h1.pg cu
const forms = fs.readdirSync(FEAT).filter((d) => fs.existsSync(path.join(FEAT, d, "ui", "main_section.html")));
let n = 0;
for (const d of forms) {
  const h = fs.readFileSync(path.join(FEAT, d, "ui", "main_section.html"), "utf8");
  if (d === "brand_weight") continue;
  n++;
  const m = h.match(/<div class="ec-fh" id="ec-fh" data-ec-fh-type="([A-Z_]+)">([\s\S]*?)\n\s*<\/div>\n\s*<p class="pg-sub ec-fh-sub">/);
  ok(!!m, d + ": co thanh #ec-fh");
  ok(!/<h1 class="pg">/.test(h), d + ": bo h1.pg cu");
  ok(m && /class="tabs ec-fh-tabs" id="[a-z]+-tabs"/.test(m[2]), d + ": hang tab nam trong thanh, giu id cu");
  ok(m && /<h1 class="ec-fh-h1">[^<]+<\/h1>/.test(m[2]) && /data-ec-fh-pin/.test(m[2]) && /data-ec-fh-switch/.test(m[2]), d + ": ten / sao / nut doi loai");
}
ok(n >= 33, "du 33 form: " + n);

// 2. Hanh vi tren form Payment Request
const PAY = fs.readFileSync(path.join(FEAT, "payment_request", "ui", "main_section.html"), "utf8");
const mk = PAY.slice(PAY.indexOf('<div class="ec-fh"'), PAY.indexOf("</p>", PAY.indexOf("ec-fh-sub")) + 4);
const CAT = { types: [
  { approval_code: "PAYMENT_REQUEST", title_vi: "Đề nghị thanh toán", route: "/approvals/payment-request", card_status: "Active", category_icon: "wallet" },
  { approval_code: "PURCHASE_REQUEST", title_vi: "Đề nghị mua hàng", route: "/approvals/purchase-request", card_status: "Active", category_icon: "wallet" },
  { approval_code: "AI_TOPUP", title_vi: "Nạp credit <b>AI</b>", route: "/approvals/ai-topup", card_status: "Active", category_icon: "database" },
  { approval_code: "SOON", title_vi: "Sắp có", route: null, card_status: "Coming Soon" }],
  my_pins: ["PAYMENT_REQUEST", "PURCHASE_REQUEST", "SOON"], my_usage: { AI_TOPUP: 5, PURCHASE_REQUEST: 9, PAYMENT_REQUEST: 3 } };
function boot(pinResp) {
  const dom = new JSDOM('<!DOCTYPE html><body><div class="content">' + mk + "</div></body>", { runScripts: "outside-only", url: "https://x.test/approvals/payment-request" });
  const w = dom.window; w.__calls = [];
  w.frappe = { call: (o) => { w.__calls.push(o);
    if (/list_catalog$/.test(o.method)) return Promise.resolve({ message: JSON.parse(JSON.stringify(CAT)) });
    if (/set_pin$/.test(o.method)) return pinResp ? pinResp(o) : Promise.resolve({ message: { my_pins: [] } });
    return Promise.resolve({ message: {} }); }, show_alert: (a) => { w.__alert = a.message; } };
  w.eval(FH);
  return w;
}
{
  const w = boot();
  await flush();
  const d = w.document;
  const star = d.querySelector("[data-ec-fh-pin]");
  ok(star.getAttribute("aria-pressed") === "true", "da ghim -> sao bat");
  ok(/\/huong-dan\/dnmh-dntt/.test(d.querySelector(".ec-fh-right a.ec-fh-btn").getAttribute("href")), "nut ? tro dung bai huong dan");
  // mo menu doi loai phieu
  d.querySelector("[data-ec-fh-switch]").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  await flush();
  const menu = d.querySelector(".ec-fh-menu");
  ok(!menu.hidden && d.querySelector("[data-ec-fh-switch]").getAttribute("aria-expanded") === "true", "mo menu");
  const links = [...menu.querySelectorAll("a")].map((a) => a.textContent.trim());
  ok(links[0] === "Đề nghị mua hàng", "Da ghim: bo form dang mo + the chua dung duoc: " + links.join("|"));
  ok(!links.includes("Đề nghị thanh toán") && !links.includes("Sắp có"), "khong lap form hien tai / the Coming Soon");
  ok(links.includes("Nạp credit <b>AI</b>") && !menu.innerHTML.includes("<b>AI</b>"), "Ban hay dung co AI Topup, ten duoc escape");
  ok(/\/approvals$/.test(menu.querySelector("a.all").getAttribute("href")), "link xem tat ca");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  ok(menu.hidden, "Esc dong menu");
  // bo ghim
  star.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  await flush();
  const c = w.__calls.find((x) => /set_pin$/.test(x.method));
  ok(c && c.type === "POST" && c.args.approval_type === "PAYMENT_REQUEST" && c.args.pinned === 0, "POST set_pin pinned=0");
  ok(star.getAttribute("aria-pressed") === "false" && /bỏ ghim/i.test(w.__alert || ""), "sao tat + thong bao");
}
{
  // loi server -> sao tra ve nhu cu
  const w = boot(() => Promise.reject({ _server_messages: JSON.stringify([JSON.stringify({ message: "Chỉ ghim tối đa 12 loại phiếu." })]) }));
  await flush();
  const star = w.document.querySelector("[data-ec-fh-pin]");
  star.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  await flush();
  ok(star.getAttribute("aria-pressed") === "true" && /tối đa 12/.test(w.__alert || ""), "loi -> tra trang thai, bao loi server");
}
console.log("JS: " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
