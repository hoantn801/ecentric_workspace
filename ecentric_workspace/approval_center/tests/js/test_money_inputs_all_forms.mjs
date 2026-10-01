// O nhap so tien 01/10/2026 (Hoan): dau cham phan cach hang nghin + can phai, tren moi form co tien.
//     node ecentric_workspace/approval_center/tests/js/test_money_inputs_all_forms.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const FEAT = join(here, "..", "..", "features");
const APP = join(here, "..", "..", "..");
const MONEY = readFileSync(join(APP, "public", "js", "ec_money.bundle.js"), "utf8");
const CSS = readFileSync(join(APP, "public", "css", "ec_money.bundle.css"), "utf8");
const HOOKS = readFileSync(join(APP, "hooks.py"), "utf8");
// form -> cac o tien (data-model). ai_topup la so le (USD) -> data-money="dec".
const FORMS = {
  affiliate_bonus: ["total_amount", "budget"], ai_topup: ["requested_amount"],
  asset_damage_loss: ["estimated_repair_cost", "estimated_value_lost_stolen_asset"],
  booking_request: ["expected_budget"],
  budget_setting: ["approved_budget_current_period", "actual_spending_current_period", "forecast_budget_next_period"],
  contract_review: ["contract_value"], hiring_request: ["suggested_salary"], hr_activity: ["estimated_budget"],
  promotion: ["current_salary", "proposed_salary"], purchase_request: ["payment_amount"],
  service_referral: ["estimated_contract_value"], special_bonus: ["total_bonus"],
  payment_request: [],   // da co data-money tu 09/2026 - chi can CSS can phai
};
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };

// 1) bundle + css + hooks
{ const dom = new JSDOM("<!DOCTYPE html><body><input id=a data-money><input id=b data-money=dec></body>", { runScripts: "outside-only" });
  const w = dom.window; w.eval(MONEY); const M = w.EcMoney;
  ok(M.fmt(10000000) === "10.000.000" && M.fmt("") === "" && M.fmt(null) === "" && M.fmt(0) === "0", "fmt VND dau cham");
  ok(M.fmt(1234.5, 1) === "1.234,5" && M.fmt(20, 1) === "20", "fmt so le dau phay");
  ok(M.parse("10.000.000") === 10000000 && M.parse("") === null && M.parse("1.234,56", 1) === 1234.56, "parse");
  const a = w.document.getElementById("a"); a.value = "1234567"; a.dispatchEvent(new w.Event("input", { bubbles: true }));
  ok(a.value === "1.234.567" && M.val(a) === 1234567, "go -> tu chen dau cham");
  const b = w.document.getElementById("b"); b.value = "12345,6"; b.dispatchEvent(new w.Event("input", { bubbles: true }));
  ok(b.value === "12.345,6" && M.val(b) === 12345.6, "so le: giu dau phay");
  b.value = "12,"; b.dispatchEvent(new w.Event("input", { bubbles: true }));
  ok(b.value === "12,", "dang go dau phay khong bi nuot");
  ok(/input\[data-money\][^}]*text-align:\s*right/.test(CSS), "css can phai");
  ok(/web_include_js\.append\("ec_money\.bundle\.js"\)/.test(HOOKS) && /web_include_css\.append\("ec_money\.bundle\.css"\)/.test(HOOKS), "hooks nap asset"); }

// 2) moi form: o tien la text + data-money, KHONG con type=number cho tien; ve + go thu
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setTimeout(r, 5)); };
for (const [f, fields] of Object.entries(FORMS)) {
  const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
  for (const k of fields) {
    const re = new RegExp('<input[^>]*data-model="' + k + '"[^>]*>');
    const tag = (html.match(re) || [""])[0];
    ok(/data-money/.test(tag) && !/type="number"/.test(tag), f + "." + k + ": o tien data-money");
  }
  // model phai nhan SO: binder doc qua EcMoney.val (booking: soTien bo dau cham khi gui)
  if (fields.length) ok(f === "booking_request" ? /expected_budget:soTien\(d\.expected_budget\)/.test(html) : /EcMoney\.val\(el\)/.test(html), f + ": binder doc so qua EcMoney");
  if (!fields.length) { ok(/data-money/.test(html), f + ": co data-money"); continue; }
  const i = html.search(/<script[^>]*id="ec-[^"]+"[^>]*>/);
  const js = html.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");
  const route = (readFileSync(join(FEAT, f, "infrastructure", "page_sync.py"), "utf8").match(/ROUTE = "([^"]+)"/) || [])[1];
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + html.slice(0, i) + "</body></html>", { runScripts: "outside-only", url: "https://x.test/" + route + "?tab=create" });
  const w = dom.window; const saved = [];
  w.frappe = { csrf_token: "x", session: { user: "u@x" }, call: (o) => { const m = o.method.split(".").pop();
    if (m === "save_draft") saved.push(o.args);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true }, context: { user: "u@x", employee_name: "U", department: "D" }, form_options: {}, options: {} } });
    return Promise.resolve({ message: { rows: [], total: 0, data: [] } }); } };
  w.eval(MONEY);
  let err = null; try { w.eval(js); } catch (e) { err = e; }
  await flush();
  ok(!err, f + ": trang chay duoc " + (err || ""));
  for (const k of fields) {
    const el = w.document.querySelector('[data-model="' + k + '"]');
    if (!el) { ok(false, f + "." + k + ": khong ve o (co the an theo dieu kien)"); continue; }
    el.value = "25000000"; el.dispatchEvent(new w.Event("input", { bubbles: true }));
    ok(el.value === "25.000.000", f + "." + k + ": go 25000000 -> 25.000.000 (" + el.value + ")");
  }
}
console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
