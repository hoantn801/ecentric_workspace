// Copyright (c) 2026, eCentric and contributors
// /approvals/data-request sau khi Data Request chuyen sang Trung tam Du lieu (data_hub dot 3, 09/11/2026).
//   * bang "da chuyen" nam SAN trong markup (khong che roi hien), link /du-lieu;
//   * tab "Tao yeu cau" -> the "Gui Data Request moi tai Trung tam Du lieu" (khong con form tao moi);
//   * chi tiet phieu cu ?id=EC-DATA-... -> "Xem tren Trung tam Du lieu" /du-lieu?ma=<ma cu>;
//   * phieu cho bo sung thong tin van mo form sua + gui lai (form cu chi con cho truong hop nay).
// Chay JS THAT cua trang tren jsdom voi frappe.call gia.
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(HERE, "..", "..", "features", "data_request", "ui", "main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-data-request">');
const JS = rest.replace(/<\/script>\s*$/, "");
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };
const flush = () => new Promise((r) => setTimeout(r, 5));
const calls = [];

function detail(over) {
  return Object.assign({
    business: { name: "EC-DATA-2026-00007", request_title: "New BI report", request_type: "New BI report",
      expected_resolution_date: "2026-07-20", urgency: "U2: within next 3 days", importance: "I2: minor",
      detailed_description: "need a report", requested_by: "u@x", department: "D", fulfillment_status: "Not Started" },
    approval: { name: "AR-1", approval_status: "Pending", current_level: 1 },
    levels: [{ level_no: 1, level_name: "Data Review", approval_mode: "Any One", level_status: "In Progress" }],
    approvers: [{ level_no: 1, approver: "linh@x", status: "Pending" }], attachments: [],
    timeline: [{ action: "Submitted", actor: "u@x", action_time: "2026-07-06 09:00" }],
    fulfillment: { status: "Not Started" }, process_preview: [], capabilities: {} }, over || {});
}

function boot(url, det) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url });
  const w = dom.window;
  w.frappe = { csrf_token: "x", call: (o) => {
    calls.push(o.method.split(".").pop());
    if (o.method.endsWith("get_bootstrap")) return Promise.resolve({ message: { tabs: { create: true, my_requests: true },
      context: { user: "u@x", employee_name: "U" }, form_options: { request_types: ["New BI report"], urgencies: [], importances: [] } } });
    if (o.method.endsWith("get_detail")) return Promise.resolve({ message: det || detail() });
    return Promise.resolve({ message: { rows: [], total: 0 } });
  } };
  w.eval(JS);
  return w;
}

{
  const pre = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>").window.document;
  const banner = pre.getElementById("dreq-moved");
  ok(banner && !banner.hidden, "bang da chuyen co san trong markup (truoc khi JS chay)");
  ok(banner && /Data Request đã chuyển sang Trung tâm Dữ liệu/.test(banner.textContent), "noi dung bang");
  ok(banner && banner.querySelector('a[href="/du-lieu"]'), "link /du-lieu");
  ok(!/<script id="ec-(?!data-request")/.test(HTML), "khong them khoi <script id=\"ec-...\"> moi");
}
{
  const w = boot("https://x.test/approvals/data-request?tab=create");
  await flush(); await flush();
  const body = w.document.getElementById("dreq-body");
  ok(body.querySelector("#dreq-moved-card"), "tab Tao yeu cau -> the chuyen sang Trung tam");
  ok(body.querySelector('#dreq-moved-card a[href="/du-lieu"]'), "nut Mo Trung tam Du lieu");
  ok(!body.querySelector('[data-model="request_title"]') && !w.document.getElementById("dreq-submit"), "khong con form gui phieu moi");
  ok(!calls.includes("save_draft") && !calls.includes("submit_request"), "khong goi luu / gui");
}
{
  const w = boot("https://x.test/approvals/data-request?id=EC-DATA-2026-00007");
  await flush(); await flush();
  const link = w.document.querySelector("#dreq-moved-detail a");
  ok(link && link.getAttribute("href") === "/du-lieu?ma=EC-DATA-2026-00007", "chi tiet phieu cu -> /du-lieu?ma=<ma cu>");
  ok(link && /Xem trên Trung tâm Dữ liệu/.test(link.textContent), "nhan link");
  ok(/class="stepper"/.test(w.document.getElementById("dreq-body").innerHTML), "chi tiet cu van hien day du (doi chieu)");
}
{
  const w = boot("https://x.test/approvals/data-request?id=EC-DATA-2026-00007", detail({
    approval: { name: "AR-1", approval_status: "Information Required", current_level: 1, information_requested_from_level: 1 },
    approvers: [{ level_no: 1, approver: "linh@x", status: "Information Requested", comment: "thêm chi tiết" }],
    capabilities: { can_edit: true } }));
  await flush(); await flush();
  w.DataRequest.startEditResubmit(w.DataRequest.state.detail);
  await flush();
  ok(!!w.document.querySelector('[data-model="request_title"]') && !!w.document.getElementById("dreq-resubmit"),
     "phieu cho bo sung van sua + gui lai duoc");
}
{
  const id = "EC-DATA-2026-<b>x</b>";
  const w = boot("https://x.test/approvals/data-request?id=" + encodeURIComponent(id), detail({ business: { name: id } }));
  await flush(); await flush();
  const a = w.document.querySelector("#dreq-moved-detail a");
  ok(a && a.getAttribute("href") === "/du-lieu?ma=" + encodeURIComponent(id), "ma la duoc ma hoa trong link");
  ok(!w.document.querySelector("#dreq-moved-detail b"), "khong chen HTML tu ma phieu");
}

console.log(pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
