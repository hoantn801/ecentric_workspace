// Daily Target 01/10/2026: tab "Toi xu ly" cho team Data, the "Team Data xu ly", stepper "Data xu ly".
//     node ecentric_workspace/approval_center/tests/js/test_daily_target_data_page.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const HTML = readFileSync(join(here, "..", "..", "features", "daily_target", "ui", "main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-daily-target">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 5)); };
const DET = (fs, cap) => ({ business: { name: "DT-1", request_title: "T", request_scope: "Consolidated / Total", brand: "EC",
    fulfillment_status: fs, fulfillment_owner: fs === "In Progress" ? "linh@x" : null },
  approval: { name: "AR", approval_status: "Approved", current_level: 0 },
  levels: [{ level_no: 1, level_name: "CEO Review", level_status: "Approved" }], approvers: [], attachments: [], timeline: [], extra: {}, capabilities: cap || {} });
function boot(url, det, fulfil) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url });
  const w = dom.window; w.__calls = [];
  w.frappe = { csrf_token: "x", call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args]);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true, all: true, fulfillment: fulfil }, context: { user: "linh@x" }, form_options: {} } });
    if (m === "get_detail") return Promise.resolve({ message: det });
    if (m === "list_fulfillment_queue") return Promise.resolve({ message: { rows: o.args.section === "unclaimed" ? [{ name: "DT-1", request_title: "T", fulfillment_status: "Assigned" }] : [] } });
    if (m === "claim_fulfillment") return Promise.resolve({ message: { claimed: true } });
    return Promise.resolve({ message: { rows: [], total: 0 } }); } };
  w.eval(JS); return w;
}
{ const w = boot("https://x.test/approvals/daily-target", null, true); await flush();
  ok([...w.document.querySelectorAll(".tab")].some((t) => t.getAttribute("data-tab") === "fulfillment"), "team Data thay tab Toi xu ly");
  w.document.querySelector('.tab[data-tab="fulfillment"]').click(); await flush();
  const b = w.document.querySelector("[data-claimq]");
  ok(!!b, "hang doi co nut Nhan xu ly");
  b.click(); await flush();
  ok(w.__calls.some((c) => c[0] === "claim_fulfillment" && c[1].name === "DT-1"), "bam -> claim_fulfillment"); }
{ const w = boot("https://x.test/approvals/daily-target", null, false); await flush();
  ok(![...w.document.querySelectorAll(".tab")].some((t) => t.getAttribute("data-tab") === "fulfillment"), "nguoi ngoai khong thay tab"); }
{ const w = boot("https://x.test/approvals/daily-target?id=DT-1", DET("Assigned", { can_claim: true }), true); await flush();
  const h = w.document.getElementById("dtgt-body").innerHTML;
  ok(/Team Data xử lý/.test(h) && /Data xử lý/.test(w.document.getElementById("d-stepper").innerHTML), "the + stepper Data xu ly");
  ok(!!w.document.querySelector('[data-act="claim"]'), "nut Nhan xu ly o chi tiet"); }
{ const w = boot("https://x.test/approvals/daily-target?id=DT-1", DET("In Progress", { can_complete: true }), true); await flush();
  w.document.querySelector('[data-act="complete"]').click(); await flush();
  const ov = w.document.querySelector("[data-ok]"); ov.click(); await flush();
  ok(!w.__calls.some((c) => c[0] === "complete_fulfillment"), "hoan tat khong ghi chu -> chan");
  w.document.querySelector("#m-cmt").value = "Da cap nhat"; ov.click(); await flush();
  ok(w.__calls.some((c) => c[0] === "complete_fulfillment" && JSON.parse(c[1].payload).fulfillment_summary === "Da cap nhat"), "hoan tat co ghi chu"); }
console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
