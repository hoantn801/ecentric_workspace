// Copyright (c) 2026, eCentric and contributors
// jsdom UI test for the Payment Request SCTS signing panel (S2B-B).
// Proves: the panel injects into the PR detail page, resolves the current record from
// window.PaymentRequest.state.id (real page state, not only form_dict/?name=), calls the
// backend signing_readiness gate, and persists a numeric placement through save_placements
// WITHOUT ever sending userId / signatureId. No CDN, no PDF.js.
//   node test_payment_request_signing_panel.js   (requires jsdom)
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const PANEL = path.join(__dirname, "..", "..", "esign", "ui", "payment_request_signing.html");
const html = fs.readFileSync(PANEL, "utf-8");
const divMatch = html.match(/<div id="ec-esign-panel"[^>]*><\/div>/);
const scriptMatch = html.match(/<script id="ec-esign-panel-js">([\s\S]*?)<\/script>/);
if (!divMatch || !scriptMatch) { console.error("FAIL: could not extract panel markup"); process.exit(1); }

const dom = new JSDOM(`<!DOCTYPE html><body>${divMatch[0]}</body>`,
  { runScripts: "dangerously", url: "https://team.ecentric.vn/approvals/payment-request?id=PR-1" });
const w = dom.window;
const calls = [];
const canned = {
  "get_signing_status": { message: { enabled: true, package: {
      name: "PKG-1", status: "Draft", package_version: 1,
      files: [{ name: "DSF-1", file_name: "sign.pdf", requires_signature: 1 }], placements: [] } } },
  "signing_readiness": { message: { ready: false, reasons: ["mandatory_placements_complete"] } },
  "pdf_page_geometry": { message: { page_count: 1, pages: [{ page: 1, width: 612, height: 792 }] } },
  "save_placements": { message: { saved: 1 } },
  "pr_approve_and_sign": { message: { signature_request: "DSR-1", status: "Queued" } },
};
w.frappe = { csrf_token: "x", msgprint() {}, show_alert() {},
  call(opts) { const s = opts.method.split(".").pop(); calls.push({ method: s, args: opts.args });
    return Promise.resolve(canned[s] || { message: {} }); } };
w.PaymentRequest = { state: { id: "PR-1", mode: "detail" } };
const s = w.document.createElement("script"); s.textContent = scriptMatch[1];
w.document.body.appendChild(s);

function assert(c, m) { if (!c) { console.error("FAIL: " + m); process.exit(1); } console.log("PASS: " + m); }
assert(typeof w.ECEsignPanel === "object", "panel defines window.ECEsignPanel");
w.ECEsignPanel.boot().then(function () {
  const p = w.document.getElementById("ec-esign-panel");
  assert(p && p.innerHTML.indexOf("sign.pdf") !== -1, "panel injected + rendered file package");
  assert(w.ECEsignPanel.state.pr === "PR-1", "PR resolved from window.PaymentRequest.state.id");
  assert(calls.some(c => c.method === "signing_readiness"), "boot used backend signing_readiness");
  w.ECEsignPanel.addPlacement({ signature_file: "DSF-1", page_index: 1, x: 50, y: 50,
                                width: 120, height: 40, level_no: 1, signature_type: "scts" });
  return w.ECEsignPanel.save();
}).then(function () {
  const c = calls.filter(x => x.method === "save_placements").pop();
  assert(c, "save() called save_placements");
  const pls = JSON.parse(c.args.placements);
  assert(pls.length === 1 && pls[0].x === 50 && pls[0].width === 120 && pls[0].page_index === 1,
         "save_placements received entered numeric placement");
  assert(!calls.some(x => x.args && ("userId" in x.args || "signatureId" in x.args ||
                                     "SignerSignatureId" in x.args)), "frontend never sends signer identity");
  console.log("\nJSDOM UI TEST: ALL PASS");
}).catch(e => { console.error("FAIL (exception):", e && e.message); process.exit(1); });
