// Clearance Request 29/09/2026: phieu tu tao tu Don nghi viec - khong co tab tao, checklist
// tung nhom kem muc ban giao, nut "Da ban giao xong", khong Tu choi.
//     node ecentric_workspace/approval_center/tests/js/test_clearance_page.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const HTML = readFileSync(join(here, "..", "..", "features", "clearance_request", "ui", "main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-clearance-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setTimeout(r, 5)); };
const DET = { business: { name: "EC-CLR-2026-00001", request_title: "Clearance - Ni Le - 2026-10-15", employee_name: "Ni <b>Le</b>",
    employee_email: "ni@x", last_working_day: "2026-10-15", resignation_reason: "Personal", line_manager: "lm@x",
    department: "Ops - EC", resignation_request: "EC-RESN-2026-00009" },
  approval: { name: "AR", approval_status: "Pending", current_level: 1 },
  levels: [{ level_no: 1, level_name: "Bàn giao nghỉ việc", approval_mode: "Each Group", level_status: "In Progress" }],
  approvers: [], attachments: [], timeline: [],
  extra: { greeting: "A handover clearance process has been initiated.", resignation_route: "/approvals/resignation?id=EC-RESN-2026-00009",
    groups: [{ group: "Line Manager", done: true, by: "lm@x", at: "2026-10-01 10:00", note: "ok", members: ["lm@x"], items: ["Role handover"] },
             { group: "Operation", done: false, members: ["dong@x"], items: ["Asset return", "Microsoft 365"] }] },
  capabilities: { can_approve: true, can_reject: false, can_request_information: true } };
function boot(url) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url });
  const w = dom.window; w.__calls = [];
  w.frappe = { csrf_token: "x", call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args]);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: false, my_requests: true, my_approvals: true, all: true }, context: { user: "u@x" }, form_options: {} } });
    if (m === "get_detail") return Promise.resolve({ message: DET });
    return Promise.resolve({ message: { rows: [], total: 0 } }); } };
  w.eval(JS); return w;
}
{ const w = boot("https://x.test/approvals/clearance-request"); await flush();
  const tabs = [...w.document.querySelectorAll(".tab")].map((t) => t.getAttribute("data-tab"));
  ok(!tabs.includes("create"), "khong co tab tao");
  ok(w.ClearanceRequest.state.tab === "my-approvals", "mac dinh Cho toi xu ly");
  ok(/bàn giao/i.test(w.document.getElementById("clr-body").innerHTML), "tieu de muc ban giao"); }
{ const w = boot("https://x.test/approvals/clearance-request?id=EC-CLR-2026-00001"); await flush();
  const d = w.document, h = d.getElementById("clr-body").innerHTML;
  ok(/Line Manager/.test(h) && /Operation/.test(h) && /Đã bàn giao/.test(h) && /Đang bàn giao/.test(h), "checklist tung nhom");
  ok(/Asset return/.test(h) && /Microsoft 365/.test(h), "muc ban giao cua nhom");
  ok([...d.querySelectorAll("input.ro")].some((i) => i.value === "Ni <b>Le</b>") && !d.querySelector("#clr-body .card b b"), "ten hien dung chu, khong thanh the HTML");
  ok(/EC-RESN-2026-00009/.test(h), "link ve Don nghi viec");
  const ap = d.querySelector('[data-act="approve"]');
  ok(!!ap && /Đã bàn giao xong/.test(ap.textContent), "nut Da ban giao xong");
  ok(!d.querySelector('[data-act="reject"]'), "khong co Tu choi");
  ok(!/onboard|Offer/.test(h), "khong sot chu cua New Staff Preparation"); }
console.log(`${oks} dat, ${fails} hong`);
process.exit(fails ? 1 : 0);
