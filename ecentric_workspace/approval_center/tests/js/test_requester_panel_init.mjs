// Copyright (c) 2026, eCentric and contributors
// Requester panel INITIALIZATION behaviour (fix/scts-requester-panel-init).
// Runs the shipped panel <script> in a hand-rolled DOM stub via node:vm - no jsdom needed.
//   node ecentric_workspace/approval_center/tests/js/test_requester_panel_init.mjs
// Covers: ?id= initializes+shows; ?name / ?payment_request_name / window-state fallbacks;
// missing identifier exits safely (hidden, no readiness call, one dev diagnostic, no throw);
// blank id treated as missing; readiness called exactly once per init; repeated init does not
// duplicate click handlers; boolean visibility (is_requester / pending / required) is correct.
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PANEL = path.join(HERE, "..", "..", "esign", "ui", "requester_signing_panel.html");
const html = fs.readFileSync(PANEL, "utf8");
const src = html.match(/<script id="ec-req-sign-script">([\s\S]*?)<\/script>/)[1];

function mkEl(id) {
  const el = { id, dataset: {}, textContent: "", innerHTML: "", _attrs: {}, _onclickAssigns: 0,
    _onclick: null, style: { display: (id === "ec-req-sign" || id === "ecReqGate") ? "none" : "" },
    getAttribute(k) { return (k in this._attrs) ? this._attrs[k] : null; },
    setAttribute(k, v) { this._attrs[k] = String(v); } };
  Object.defineProperty(el, "onclick", { get() { return this._onclick; },
    set(fn) { this._onclickAssigns++; this._onclick = fn; } });
  return el;
}

function run(sc) {
  const els = {};
  ["ec-req-sign", "ecReqStatus", "ecReqMsg", "ecReqGate", "ecReqPrepare", "ecReqLock"]
    .forEach((id) => { els[id] = mkEl(id); });
  let callCount = 0, lastMethod = null, debugCount = 0, threw = null;
  const frappe = {
    call(opts) { callCount++; lastMethod = opts.method; return Promise.resolve({ message: sc.readiness || {} }); },
    utils: { escape_html: (x) => x }, show_alert() {}, boot: { developer_mode: true } };
  const sandbox = {
    document: { getElementById: (id) => els[id] || null },
    location: { search: sc.search || "", reload() {} },
    URLSearchParams, console: { debug: () => { debugCount++; }, log() {}, error() {} },
    Promise, String, Object, Array };
  vm.createContext(sandbox);
  sandbox.window = sandbox; sandbox.frappe = frappe;
  sandbox.EC_PPH_PR = sc.EC_PPH_PR; sandbox.PaymentRequest = sc.PaymentRequest;
  try { for (let i = 0; i < (sc.runs || 1); i++) vm.runInContext(src, sandbox); } catch (e) { threw = e; }
  return { els, callCount, lastMethod, debugCount, threw };
}

const VIS = { checks: { is_requester: true, pending_requester_signature: true,
  requester_signature_required: true, verified_mapping: true, gates_enabled: false,
  package_present: false, placements_ready: false, package_locked: false } };
let pass = 0, fail = 0;
const check = (n, c) => { if (c) { pass++; console.log("  ok -", n); } else { fail++; console.log("  FAIL -", n); } };
const tick = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };

async function main() {
  let r = run({ search: "?id=EC-PAYR-2026-00009", readiness: VIS }); await tick();
  check("?id= initializes without throwing", r.threw === null);
  check("?id= calls readiness exactly once", r.callCount === 1);
  check("?id= calls requester_signing_readiness", /requester_signing_readiness$/.test(r.lastMethod));
  check("?id= shows the panel", r.els["ec-req-sign"].style.display === "block");

  r = run({ search: "?name=EC-PAYR-2026-00009", readiness: VIS }); await tick();
  check("?name= fallback shows the panel", r.els["ec-req-sign"].style.display === "block" && r.callCount === 1);
  r = run({ search: "?payment_request_name=EC-PAYR-2026-00009", readiness: VIS }); await tick();
  check("?payment_request_name= fallback shows the panel", r.els["ec-req-sign"].style.display === "block");
  r = run({ search: "", EC_PPH_PR: "EC-PAYR-2026-00009", readiness: VIS }); await tick();
  check("window.EC_PPH_PR fallback shows the panel", r.els["ec-req-sign"].style.display === "block");
  r = run({ search: "", PaymentRequest: { state: { id: "EC-PAYR-2026-00009" } }, readiness: VIS }); await tick();
  check("window.PaymentRequest.state.id fallback shows the panel", r.els["ec-req-sign"].style.display === "block");

  r = run({ search: "", readiness: VIS }); await tick();
  check("missing id does not throw", r.threw === null);
  check("missing id keeps the panel hidden", r.els["ec-req-sign"].style.display === "none");
  check("missing id does NOT call readiness", r.callCount === 0);
  check("missing id logs one dev diagnostic", r.debugCount === 1);
  r = run({ search: "?id=%20%20", readiness: VIS }); await tick();
  check("blank id treated as missing", r.els["ec-req-sign"].style.display === "none" && r.callCount === 0);

  r = run({ search: "?id=EC-PAYR-2026-00009", readiness: VIS, runs: 3 }); await tick();
  check("repeated init binds prepare handler once", r.els["ecReqPrepare"]._onclickAssigns === 1);
  check("repeated init binds lock handler once", r.els["ecReqLock"]._onclickAssigns === 1);
  check("repeated init calls readiness once per init", r.callCount === 3);

  r = run({ search: "?id=EC-PAYR-2026-00009",
    readiness: { checks: { is_requester: false, pending_requester_signature: true, requester_signature_required: true } } });
  await tick();
  check("not requester -> hidden", r.els["ec-req-sign"].style.display === "none");
  r = run({ search: "?id=EC-PAYR-2026-00009",
    readiness: { checks: { is_requester: true, pending_requester_signature: false, requester_signature_required: true } } });
  await tick();
  check("not pending -> hidden", r.els["ec-req-sign"].style.display === "none");

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}
main();
