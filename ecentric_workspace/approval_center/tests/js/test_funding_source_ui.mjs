// Copyright (c) 2026, eCentric and contributors
// Funding-source picker on the Payment Request form (bước 1+2).
// Runs the SHIPPED page script in a node:vm DOM stub - no jsdom, no network.
// Covers: source-type catalog load, document list per type, autofill (payee / remaining /
// title) WITHOUT clobbering what the user already typed, client-side over-limit guard with
// the SAME epsilon as the server, "No" wiping a stale source, and legacy-record promotion.
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
  throw new Error("payment_request main_section.html not found; roots tried: " + _ROOTS.join(", "));
})();
const HTML = fs.readFileSync(PAGE, "utf8");
const SRC = HTML.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];

let pass = 0, fail = 0;
const ok = (cond, msg) => { if (cond) { pass++; } else { fail++; console.log("  FAIL: " + msg); } };
const eq = (a, b, msg) => ok(a === b, `${msg} (got ${JSON.stringify(a)}, want ${JSON.stringify(b)})`);

// ---- DOM stub -------------------------------------------------------------
function mkEl(id) {
  return { id, _html: "", textContent: "", style: {}, value: "", disabled: false,
    _attrs: {}, children: [], classList: { add(){}, remove(){}, toggle(){} },
    getAttribute(k){ return k in this._attrs ? this._attrs[k] : null; },
    setAttribute(k, v){ this._attrs[k] = String(v); },
    appendChild(c){ this.children.push(c); return c; },
    replaceWith(){}, addEventListener(){}, removeEventListener(){},
    querySelectorAll(){ return []; }, querySelector(){ return null; },
    closest(){ return null; }, focus(){}, scrollIntoView(){},
    get innerHTML(){ return this._html; }, set innerHTML(v){ this._html = String(v); } };
}
const els = {};
const doc = {
  getElementById: (id) => els[id] || (els[id] = mkEl(id)),
  createElement: (t) => mkEl("_" + t),
  querySelectorAll: () => [], querySelector: () => null,
  addEventListener(){}, body: mkEl("body"), head: mkEl("head"),
};

// ---- backend stub ---------------------------------------------------------
const SOURCES = {
  "EC Purchase Request": [
    { value: "PURR-1", label: "PURR-1 — Mua KOC", title: "Mua KOC", payee: "Cty ABC",
      total: 100, used: 30, remaining: 70 },
  ],
  "Purchase Order": [
    { value: "PO-1", label: "PO-1 — PO thang 8", title: "PO thang 8", payee: "NCC-1",
      total: 200, used: 0, remaining: 200 },
  ],
};
const TYPES = [
  { value: "EC Purchase Request", label: "Đề nghị mua hàng (ĐNMH)" },
  { value: "Purchase Order", label: "PO mua ngoài (sổ EC)" },
];
const calls = [];
// The page calls window.frappe.call({method: NS+name, args}) - intercept THERE, not on the
// exported PaymentRequest._call (which the shipped code does not use internally).
function fakeCall(fullMethod, args) {
  const method = String(fullMethod).split(".").pop();
  calls.push({ method, args });
  if (method === "list_funding_sources") {
    const dt = (args || {}).source_doctype;
    return Promise.resolve({ types: TYPES, rows: dt ? (SOURCES[dt] || []) : [] });
  }
  if (method === "get_bootstrap") {
    return Promise.resolve({ tabs: {}, context: { user: "nv@ec", employee_name: "NV" },
                             form_options: { yes_no: ["Yes", "No"] } });
  }
  if (method === "funding_source_summary") {
    const rows = SOURCES[args.source_doctype] || [];
    const r = rows.find(x => x.value === args.source_name);
    return Promise.resolve(r ? { total: r.total, used: r.used, remaining: r.remaining } : null);
  }
  return Promise.resolve({});
}

// ---- boot the shipped script ---------------------------------------------
const win = { location: { pathname: "/approvals/payment-request", search: "" },
  addEventListener(){}, matchMedia: () => ({ matches: false, addEventListener(){} }),
  requestAnimationFrame: (f) => f(), setTimeout, clearTimeout, console };
// The page reads window.frappe (not the bare global), so it MUST live on `win`.
win.frappe = { csrf_token: "x",
  call: (o) => fakeCall(o.method, o.args).then(m => ({ message: m })) };
const sandbox = { window: win, document: doc, console, setTimeout, clearTimeout,
  frappe: win.frappe,
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
  navigator: { userAgent: "node" }, localStorage: undefined };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
try {
  vm.runInContext(SRC, sandbox, { filename: "payment_request_main_section.js" });
} catch (e) {
  console.log("BOOT ERROR: " + e.message);
  process.exit(1);
}

const PR = win.PaymentRequest;
if (!PR) { console.log("FAIL: window.PaymentRequest not exported"); process.exit(1); }

// The page normally gets these from get_bootstrap; supply them so the real render path runs
// (the shipped code calls its own internal renderCreate, not the exported reference).
const st = PR.state;
st.boot = { tabs: {}, context: { user: "nv@ec", employee_name: "NV", department: "Ops - EC" },
            form_options: { yes_no: ["Yes", "No"] } };
st.draft = {};

// A macrotask flush: the page chains several promises per action, and microtask-only
// flushing silently under-runs them (a test that then reports "0 rows" instead of failing loudly).
const tick = () => new Promise(r => setTimeout(r, 5));

(async () => {
  console.log("Funding source UI");
  // Guard against the failure mode this suite itself hit once: if the page cannot reach the
  // stubbed backend, every list comes back empty and the assertions below would quietly test
  // nothing. Prove the wiring works before trusting any result.
  await tick();
  ok(calls.length > 0, "page reached the stubbed backend at all (wiring sane)");
  if (!calls.length) { console.log("ABORT: window.frappe.call never fired"); process.exit(1); }

  // -- exports -------------------------------------------------------------
  ok(typeof PR.handleSrcTypeChange === "function", "handleSrcTypeChange exported");
  ok(typeof PR.handleSrcPick === "function", "handleSrcPick exported");
  ok(typeof PR.promoteLegacySource === "function", "promoteLegacySource exported");
  ok(typeof PR.fmtVnd === "function", "fmtVnd exported");
  ok(typeof PR.handleHPRChange === "function", "handleHPRChange exported");

  // -- number formatting is vi-VN ------------------------------------------
  ok(/[.,]/.test(PR.fmtVnd(1000000)), "fmtVnd groups thousands");
  eq(PR.fmtVnd(0), "0", "fmtVnd zero");
  eq(PR.fmtVnd(null), "0", "fmtVnd null is 0 not NaN");

  // -- legacy promotion ----------------------------------------------------
  const legacy = { purchase_request: "PURR-9" };
  PR.promoteLegacySource(legacy);
  eq(legacy.funding_source_doctype, "EC Purchase Request", "legacy doc promoted to pair (type)");
  eq(legacy.funding_source_name, "PURR-9", "legacy doc promoted to pair (name)");

  const already = { purchase_request: "PURR-9", funding_source_doctype: "Purchase Order",
                    funding_source_name: "PO-7" };
  PR.promoteLegacySource(already);
  eq(already.funding_source_name, "PO-7", "promotion never overwrites an existing pair");

  // -- picking a type loads that type's documents --------------------------
  st.draft = {};
  PR.handleSrcTypeChange("EC Purchase Request");
  await tick();
  eq((st._fundRows || []).length, 1, "rows loaded for ĐNMH");
  eq(st._fundRows[0].value, "PURR-1", "correct row");
  eq(st._fundLoading, false, "loading flag cleared");

  // -- picking a document autofills ---------------------------------------
  st.draft = { funding_source_doctype: "EC Purchase Request" };
  PR.handleSrcPick("PURR-1");
  await tick();
  eq(st.draft.payee_full_name, "Cty ABC", "payee autofilled from source");
  eq(st.draft.payment_amount, 70, "amount autofilled with REMAINING (not total)");
  eq(st.draft.request_title, "Mua KOC", "title autofilled");
  ok(st._fundSummary && st._fundSummary.remaining === 70, "summary stored for the hint");

  // -- autofill must not clobber what the user typed -----------------------
  st.draft = { funding_source_doctype: "EC Purchase Request",
               payee_full_name: "Người tôi tự gõ", payment_amount: 25,
               request_title: "Tiêu đề của tôi" };
  PR.handleSrcPick("PURR-1");
  await tick();
  eq(st.draft.payee_full_name, "Người tôi tự gõ", "does not overwrite typed payee");
  eq(st.draft.payment_amount, 25, "does not overwrite typed amount");
  eq(st.draft.request_title, "Tiêu đề của tôi", "does not overwrite typed title");

  // -- switching type clears the previously picked document ----------------
  st.draft = { funding_source_doctype: "EC Purchase Request", funding_source_name: "PURR-1" };
  PR.handleSrcTypeChange("Purchase Order");
  await tick();
  eq(st.draft.funding_source_name, "", "changing type clears the chosen document");
  eq(st._fundRows[0].value, "PO-1", "rows switched to PO");
  ok(st._fundSummary === null, "stale summary dropped on type change");

  // -- PO source autofills too --------------------------------------------
  st.draft = { funding_source_doctype: "Purchase Order" };
  PR.handleSrcPick("PO-1");
  await tick();
  eq(st.draft.payee_full_name, "NCC-1", "PO supplier autofilled as payee");
  eq(st.draft.payment_amount, 200, "PO remaining autofilled");

  // -- client guard uses the SAME epsilon as the server (0.5) --------------
  st.draft = { reason: "x", payment_date: "2026-08-26", payee_full_name: "A",
    account_bank: "B", bank_account_number: "1", has_purchase_request: "Yes",
    is_cost_valid: "Yes", details_and_attachments_correct: "Yes", request_attachment: "f.pdf",
    funding_source_doctype: "EC Purchase Request", funding_source_name: "PURR-1",
    payment_amount: 70 };
  st._fundSummary = { total: 100, used: 30, remaining: 70 };
  ok(!PR.validateSubmit(), "exactly the remaining amount is accepted");

  st.draft.payment_amount = 71;
  let errs = PR.validateSubmit() || {};
  ok(!!errs.payment_amount, "one dong over the remainder is refused");

  st.draft.payment_amount = 70.4;
  ok(!PR.validateSubmit(), "float noise below 0.5 tolerated (matches server epsilon)");

  // -- missing source when 'Yes' ------------------------------------------
  st.draft.payment_amount = 10;
  st.draft.funding_source_name = "";
  errs = PR.validateSubmit() || {};
  ok(!!errs.funding_source_name, "'Yes' without a document is refused");

  st.draft.funding_source_doctype = "";
  errs = PR.validateSubmit() || {};
  ok(!!errs.funding_source_doctype, "'Yes' without a type is refused");

  // -- switching to "No" wipes any stale source ---------------------------
  st.draft = { has_purchase_request: "Yes", funding_source_doctype: "EC Purchase Request",
               funding_source_name: "PURR-1" };
  st._fundSummary = { total: 100, used: 0, remaining: 100 };
  st.draft.has_purchase_request = "No";
  PR.handleHPRChange("No");
  eq(st.draft.funding_source_name || "", "", "'No' clears the source document");
  eq(st.draft.funding_source_doctype || "", "", "'No' clears the source type");

  // -- endpoint contract ---------------------------------------------------
  ok(calls.some(c => c.method === "list_funding_sources"), "calls list_funding_sources");
  ok(calls.some(c => c.method === "funding_source_summary"), "re-reads balance from server");
  const sum = calls.find(c => c.method === "funding_source_summary");
  ok("exclude_request" in (sum.args || {}), "summary call passes exclude_request (edit case)");

  console.log(`${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
