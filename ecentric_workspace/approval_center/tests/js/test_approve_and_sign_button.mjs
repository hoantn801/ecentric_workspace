// Copyright (c) 2026, eCentric and contributors
// Nút "Duyệt & Ký" ở cấp duyệt yêu cầu chữ ký số.
//
// Sự cố pilot UAT VOID 5 (27/08/2026): backend chặn đúng — "Cấp duyệt này yêu cầu ký số.
// Vui lòng dùng chức năng 'Duyệt & Ký'" — nhưng giao diện chỉ có Duyệt / Yêu cầu bổ sung /
// Từ chối. Người duyệt vào ngõ cụt: hệ thống bảo dùng một chức năng mà nó không hiển thị.
// Duyệt cấp có ký số chỉ làm được bằng cách gọi API tay.
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const _ROOTS = ["../../features/payment_request/ui", "../../../features/payment_request/ui"];
const PAGE = (() => {
  for (const r of _ROOTS) {
    const p = path.join(HERE, r, "main_section.html");
    if (fs.existsSync(p)) return p;
  }
  throw new Error("main_section.html not found; roots tried: " + _ROOTS.join(", "));
})();
const SRC = fs.readFileSync(PAGE, "utf8").match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };

function mkEl(id) {
  return { id, _html: "", textContent: "", style: {}, value: "", disabled: false, _attrs: {},
    children: [], classList: { add(){}, remove(){}, toggle(){} },
    getAttribute(k){ return k in this._attrs ? this._attrs[k] : null; },
    setAttribute(k, v){ this._attrs[k] = String(v); },
    appendChild(c){ this.children.push(c); return c; }, removeChild(){}, replaceWith(){},
    addEventListener(){}, removeEventListener(){}, querySelectorAll(){ return []; },
    querySelector(){ return null; }, closest(){ return null; }, focus(){}, scrollIntoView(){},
    get innerHTML(){ return this._html; }, set innerHTML(v){ this._html = String(v); } };
}
const els = {};
const doc = { getElementById: (id) => els[id] || (els[id] = mkEl(id)),
  createElement: (t) => mkEl(t), querySelectorAll: () => [], querySelector: () => null,
  addEventListener(){}, body: mkEl("body"), head: mkEl("head") };

const calls = [];
const win = { location: { pathname: "/approvals/payment-request", search: "" },
  addEventListener(){}, matchMedia: () => ({ matches: false, addEventListener(){} }),
  requestAnimationFrame: (f) => f(), setTimeout, clearTimeout, console };
win.frappe = { csrf_token: "x", call: (o) => {
  calls.push({ method: o.method, args: o.args, type: o.type });
  if (String(o.method).endsWith("get_bootstrap")) {
    return Promise.resolve({ message: { tabs: {}, context: {}, form_options: { yes_no: ["Yes", "No"] } } });
  }
  if (String(o.method).endsWith("signing_readiness")) {
    return Promise.resolve({ message: SIGNING_READINESS });
  }
  if (String(o.method).endsWith("pr_approve_and_sign")) {
    return Promise.resolve({ message: { signature_request: "EC-DSR-9", status: "Queued", duplicate: false } });
  }
  return Promise.resolve({ message: {} });
} };
let SIGNING_READINESS = { ready: false, checks: { level_requires_signature: true } };

const sandbox = { window: win, document: doc, console, setTimeout, clearTimeout,
  frappe: win.frappe, fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
  navigator: { userAgent: "node" } };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
try { vm.runInContext(SRC, sandbox, { filename: "payment_request.js" }); }
catch (e) { console.log("BOOT ERROR: " + e.message); process.exit(1); }

const PR = win.PaymentRequest;
if (!PR) { console.log("FAIL: PaymentRequest not exported"); process.exit(1); }
const st = PR.state;
st.boot = { tabs: {}, context: {}, form_options: { yes_no: ["Yes", "No"] } };

const tick = () => new Promise(r => setTimeout(r, 5));
const DET = { capabilities: { can_approve: true, can_reject: true, can_request_information: true },
              approval: { approval_status: "Pending", current_level: 1 },
              business: { name: "EC-PAYR-2026-00026", payee_full_name: "X", payment_amount: 12345 } };

(async () => {
  console.log("Approve & Sign button");

  ok(typeof PR.doApproveAndSign === "function", "doApproveAndSign exported");
  ok(typeof PR.loadSignReady === "function", "loadSignReady exported");
  ok(typeof PR.callEsign === "function", "callEsign exported");

  // --- cấp YÊU CẦU ký số: phải có "Duyệt & Ký", KHÔNG có "Duyệt" thường ------
  st._signReady = { checks: { level_requires_signature: true } };
  let html = PR.actionPanelHTML(DET);
  ok(html.includes('data-act="approvesign"'), "hiện nút Duyệt & Ký khi cấp yêu cầu ký");
  ok(!html.includes('data-act="approve"'), "KHÔNG hiện nút Duyệt thường (backend sẽ chặn)");
  ok(html.includes("Ký"), "nhãn nút nói rõ có ký");

  // --- cấp KHÔNG yêu cầu ký: giữ nguyên hành vi cũ ---------------------------
  st._signReady = { checks: { level_requires_signature: false } };
  html = PR.actionPanelHTML(DET);
  ok(html.includes('data-act="approve"'), "cấp thường vẫn có nút Duyệt");
  ok(!html.includes('data-act="approvesign"'), "cấp thường KHÔNG có nút Duyệt & Ký");

  // --- CHƯA biết (chưa nạp xong): hiện cả hai để không ai bị kẹt --------------
  st._signReady = null;
  html = PR.actionPanelHTML(DET);
  ok(html.includes('data-act="approvesign"'), "chưa biết -> vẫn có Duyệt & Ký");
  ok(html.includes('data-act="approve"'), "chưa biết -> vẫn có Duyệt (không ai bị kẹt)");

  // --- không phải người duyệt: không có nút nào -------------------------------
  html = PR.actionPanelHTML({ capabilities: {}, approval: {}, business: {} });
  ok(!html.includes('data-act="approvesign"'), "không phải người duyệt thì không có nút ký");

  // --- loadSignReady gọi ĐÚNG endpoint, và chỉ gọi một lần cho mỗi bản ghi ----
  calls.length = 0;
  st.id = "EC-PAYR-2026-00026"; st._signReadyFor = null; st.tab = "list";
  PR.loadSignReady();
  await tick();
  const rd = calls.filter(c => String(c.method).endsWith("signing_readiness"));
  ok(rd.length === 1, "gọi signing_readiness đúng 1 lần");
  ok(String(rd[0].method).startsWith("ecentric_workspace.platform.esign.api."),
     "gọi đúng namespace esign");
  ok(rd[0].type === "GET", "readiness là lệnh đọc (GET)");
  PR.loadSignReady();
  await tick();
  ok(calls.filter(c => String(c.method).endsWith("signing_readiness")).length === 1,
     "gọi lại cho cùng bản ghi KHÔNG nạp lại (tránh vòng lặp render)");

  // --- callEsign định tuyến đúng namespace + đúng phương thức ---------------
  calls.length = 0;
  await PR.callEsign("pr_approve_and_sign", { payment_request_name: "PR-1", comment: "x" });
  const sign = calls[calls.length - 1];
  ok(sign.method === "ecentric_workspace.platform.esign.api.pr_approve_and_sign",
     "gọi đúng endpoint ký của platform.esign");
  ok(sign.type === "POST", "hành động ký phải là POST (không được đi qua GET)");
  ok(sign.args.payment_request_name === "PR-1", "truyền đúng tên bản ghi");

  await PR.callEsign("signing_readiness", { payment_request_name: "PR-1" });
  ok(calls[calls.length - 1].type === "GET", "lệnh đọc vẫn là GET");

  await PR.callEsign("my_signature_preview", { payment_request_name: "PR-1" });
  ok(calls[calls.length - 1].type === "GET", "my_* là lệnh đọc");

  console.log(`${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
