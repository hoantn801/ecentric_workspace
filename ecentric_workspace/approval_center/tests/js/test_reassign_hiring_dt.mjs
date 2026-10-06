// Nut "Chuyen nguoi xu ly" Hiring + Daily Target (05/10/2026): co can_reassign -> co nut; bam ->
// hoi danh sach tu server, chon nguoi -> goi reassign_fulfillment(name, new_user).
//     node ecentric_workspace/approval_center/tests/js/test_reassign_hiring_dt.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const FEAT = join(here, "..", "..", "features");
const BUNDLE = readFileSync(join(here, "..", "..", "..", "public", "js", "ec_reassign.bundle.js"), "utf8");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setTimeout(r, 5)); };
const DET = (cap) => ({ business: { name: "R-1", requested_by: "x@x", request_title: "T", approval_request: "AR", fulfillment_status: "In Progress", fulfillment_owner: "tuan@x" },
  approval: { name: "AR", approval_status: "Approved", current_level: 0 }, request: { name: "AR", approval_status: "Approved", current_level: 0 },
  levels: [{ level_no: 1, level_name: "CEO Review", level_status: "Approved" }], approvers: [], attachments: [], timeline: [], extra: {}, capabilities: cap });
for (const f of ["hiring_request", "daily_target"]) {
  const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
  const i = html.search(/<script[^>]*id="ec-[^"]+"[^>]*>/);
  const js = html.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");
  const route = (readFileSync(join(FEAT, f, "infrastructure", "page_sync.py"), "utf8").match(/ROUTE = "([^"]+)"/) || [])[1];
  for (const can of [true, false]) {
    const dom = new JSDOM("<!DOCTYPE html><html><body>" + html.slice(0, i) + "</body></html>", { runScripts: "outside-only", url: "https://x.test/" + route + "?id=R-1" });
    const w = dom.window; const calls = [];
    w.frappe = { csrf_token: "x", session: { user: "tuan@x" }, call: (o) => { const m = o.method.split(".").pop(); calls.push([m, o.args]);
      if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true, fulfillment: true }, context: { user: "tuan@x" }, form_options: {} } });
      if (m === "get_detail") return Promise.resolve({ message: DET({ can_reassign: can, can_complete: can }) });
      if (m === "list_reassign_targets") return Promise.resolve({ message: { current_owner: "tuan@x", targets: [{ name: "luc@x", full_name: "Luc" }] } });
      if (m === "reassign_fulfillment") return Promise.resolve({ message: { reassigned: true } });
      return Promise.resolve({ message: { rows: [], total: 0 } }); } };
    w.eval(BUNDLE); w.eval(js); await flush();
    const b = w.document.querySelector('[data-act="reassign"]');
    if (!can) { ok(!b, f + ": khong co quyen -> khong nut"); continue; }
    ok(!!b, f + ": chu viec thay nut Chuyen nguoi xu ly");
    if (!b) continue;
    b.click(); await flush();
    const sel = w.document.querySelector("#m-newowner");
    ok(!!sel && /luc@x/.test(sel.innerHTML), f + ": hop chon lay danh sach tu server");
    const okBtn = [...w.document.querySelectorAll("button")].find((x) => /^Chuyển$/.test(x.textContent.trim()));
    ok(!!okBtn, f + ": co nut xac nhan Chuyen");
    if (okBtn) { okBtn.click(); await flush(); }
    ok(calls.some((c) => c[0] === "reassign_fulfillment" && c[1].name === "R-1" && c[1].new_user === "luc@x"), f + ": goi reassign_fulfillment(R-1, luc@x)");
  }
}
console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
