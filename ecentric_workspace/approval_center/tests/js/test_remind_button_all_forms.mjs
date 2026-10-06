// Nut "Nhac nguoi xu ly" 01/10/2026 tren MOI form phe duyet: co can_remind -> co nut; bam -> goi
// endpoint `remind` cua chinh form; dang cho 15 phut -> nut khoa + so phut; khong co quyen -> khong nut.
//     node ecentric_workspace/approval_center/tests/js/test_remind_button_all_forms.mjs
import { JSDOM } from "jsdom";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const FEAT = join(here, "..", "..", "features");
const BUNDLE = readFileSync(join(here, "..", "..", "..", "public", "js", "ec_remind.bundle.js"), "utf8");
const SKIP = new Set(["brand_weight"]);   // UI rieng (cancelBox), chua co khung nut duyet chung
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setTimeout(r, 5)); };
const DET = (cap) => ({ business: { name: "R-1", requested_by: "req@x", request_title: "T", approval_request: "AR" },
  approval: { name: "AR", approval_status: "Pending", current_level: 1 }, request: { name: "AR", approval_status: "Pending", current_level: 1 },
  levels: [{ level_no: 1, level_name: "Lead", level_status: "In Progress" }],
  approvers: [{ level_no: 1, approver: "lead@x", status: "Pending" }], attachments: [], timeline: [], extra: {}, items: [],
  capabilities: cap });
function boot(html, route, det) {
  const i = html.search(/<script[^>]*id="ec-[^"]+"[^>]*>/);
  const markup = html.slice(0, i);
  const js = html.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/" + route + "?id=R-1" });
  const w = dom.window; w.__calls = [];
  w.frappe = { csrf_token: "x", session: { user: "req@x" }, call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args]);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true, all: true }, context: { user: "req@x" }, form_options: {}, options: {} } });
    if (m === "get_detail" || m === "get_request_detail") return Promise.resolve({ message: det });
    if (m === "remind") return Promise.resolve({ message: { reminded: ["lead@x"], wait_seconds: 900, detail: det } });
    return Promise.resolve({ message: { rows: [], total: 0, data: [] } }); } };
  w.eval(BUNDLE);
  try { w.eval(js); } catch (e) { return { w, err: e }; }
  return { w };
}
const feats = readdirSync(FEAT).filter((f) => existsSync(join(FEAT, f, "ui", "main_section.html")) && !SKIP.has(f));
ok(feats.length >= 31, "du form: " + feats.length);
for (const f of feats) {
  const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
  const route = (readFileSync(join(FEAT, f, "infrastructure", "page_sync.py"), "utf8").match(/ROUTE = "([^"]+)"/) || [])[1];
  ok(/EcRemind\.buttonHTML\(cap\)/.test(html) && /a==="remind"/.test(html), f + ": co 2 dong noi nut");
  { const { w, err } = boot(html, route, DET({ can_remind: true, remind_wait_seconds: 0 })); await flush();
    ok(!err, f + ": trang chay duoc " + (err || ""));
    const b = w.document.querySelector('[data-act="remind"]');
    ok(!!b && /Nhắc người xử lý/.test(b.textContent), f + ": co nut nhac");
    if (b) { b.click(); await flush();
      ok(w.__calls.some((c) => c[0] === "remind" && c[1].name === "R-1"), f + ": bam -> goi remind(R-1)"); } }
  { const { w } = boot(html, route, DET({ can_remind: true, remind_wait_seconds: 301 })); await flush();
    const t = w.document.body.innerHTML;
    ok(/Nhắc lại sau 6 phút/.test(t) && !w.document.querySelector('[data-act="remind"]'), f + ": dang cho -> nut khoa 6 phut"); }
  { const { w } = boot(html, route, DET({ can_remind: false })); await flush();
    ok(!/Nhắc người xử lý|Nhắc lại sau/.test(w.document.body.innerHTML), f + ": khong quyen -> khong nut"); }
}
console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
