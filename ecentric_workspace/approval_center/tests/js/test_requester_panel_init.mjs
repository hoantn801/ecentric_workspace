// Copyright (c) 2026, eCentric and contributors
// Requester panel INITIALIZATION behaviour (fix/scts-requester-panel-init +
// fix/scts-requester-panel-call-ready). Runs the shipped panel <script> in a hand-rolled DOM
// stub with a FAKE CLOCK via node:vm - no jsdom needed.
//   node ecentric_workspace/approval_center/tests/js/test_requester_panel_init.mjs
// Covers: ?id / ?name / ?payment_request_name / window-state resolution; missing id safe;
// boolean visibility; AND the call-readiness timing: frappe.call available immediately;
// frappe present but call installed later; frappe entirely absent then appears; bounded
// timeout -> hidden + one dev diagnostic + no throw; repeated init makes no duplicate
// timers/calls/handlers; Prepare/Lock use the guarded window.frappe.call.
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
function mkFrappe(state, readiness) {
  return { call(opts) { state.callCount++; state.lastMethod = opts.method;
      return Promise.resolve({ message: readiness || {} }); },
    utils: { escape_html: (x) => x }, show_alert() {}, boot: { developer_mode: true } };
}

// Build a sandbox with a controllable fake clock. Returns handles; does NOT auto-advance.
function mk(sc) {
  const els = {};
  ["ec-req-sign", "ecReqStatus", "ecReqMsg", "ecReqGate", "ecReqPrepare", "ecReqLock"]
    .forEach((id) => { els[id] = mkEl(id); });
  const state = { callCount: 0, lastMethod: null, debugCount: 0 };
  const timers = new Map(); let tid = 0;
  const sandbox = {
    document: { getElementById: (id) => els[id] || null },
    location: { search: sc.search || "", reload() {} },
    URLSearchParams,
    console: { debug: () => { state.debugCount++; }, log() {}, error() {} },
    setInterval: (fn, ms) => { tid++; timers.set(tid, fn); return tid; },
    clearInterval: (id) => { timers.delete(id); },
    Promise, String, Object, Array };
  vm.createContext(sandbox);
  sandbox.window = sandbox;
  sandbox.frappe = sc.frappe;                 // may be undefined / partial / full
  sandbox.EC_PPH_PR = sc.EC_PPH_PR;
  sandbox.PaymentRequest = sc.PaymentRequest;
  const api = {
    els, state, sandbox, timers,
    exec() { vm.runInContext(src, sandbox); },
    fire() { Array.from(timers.values()).forEach((fn) => fn()); },      // one interval elapse
    fireN(n) { for (let i = 0; i < n; i++) this.fire(); },
    installCall(readiness) {
      const f = sandbox.frappe || (sandbox.frappe = {});
      const ready = mkFrappe(state, readiness);
      f.call = ready.call; f.utils = ready.utils; f.show_alert = ready.show_alert;
      f.boot = f.boot || ready.boot;
    } };
  return api;
}

const VIS = { checks: { is_requester: true, pending_requester_signature: true,
  requester_signature_required: true, verified_mapping: true, gates_enabled: false } };
let pass = 0, fail = 0, threwAny = false;
const check = (n, c) => { if (c) { pass++; console.log("  ok -", n); } else { fail++; console.log("  FAIL -", n); } };
const tick = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };

async function main() {
  // --- resolution + visibility (frappe.call ready immediately) ---
  let a = mk({ search: "?id=EC-PAYR-2026-00009", frappe: mkFrappe({ callCount: 0 }, VIS) });
  // rebuild with shared state so we can assert callCount
  a = mk({ search: "?id=EC-PAYR-2026-00009", frappe: undefined }); a.installCall(VIS);
  try { a.exec(); } catch (e) { threwAny = true; } await tick();
  check("immediate call: readiness called once", a.state.callCount === 1);
  check("immediate call: panel shown", a.els["ec-req-sign"].style.display === "block");
  check("immediate call: no timer left", a.timers.size === 0);

  for (const q of ["?name=EC-PAYR-1", "?payment_request_name=EC-PAYR-1"]) {
    const b = mk({ search: q, frappe: undefined }); b.installCall(VIS); b.exec(); await tick();
    check("fallback " + q + " shows panel", b.els["ec-req-sign"].style.display === "block");
  }
  let w = mk({ search: "", EC_PPH_PR: "EC-PAYR-1", frappe: undefined }); w.installCall(VIS); w.exec(); await tick();
  check("window.EC_PPH_PR fallback shows panel", w.els["ec-req-sign"].style.display === "block");

  // --- boolean visibility ---
  for (const [nm, chk] of [["not requester", { is_requester: false, pending_requester_signature: true, requester_signature_required: true }],
                           ["not pending", { is_requester: true, pending_requester_signature: false, requester_signature_required: true }]]) {
    const v = mk({ search: "?id=EC-PAYR-1", frappe: undefined }); v.installCall({ checks: chk }); v.exec(); await tick();
    check(nm + " -> hidden", v.els["ec-req-sign"].style.display === "none");
  }

  // --- missing id: safe, hidden, one diagnostic, no readiness ---
  let m = mk({ search: "", frappe: undefined }); m.installCall(VIS); m.exec(); await tick();
  check("missing id: hidden", m.els["ec-req-sign"].style.display === "none");
  check("missing id: readiness NOT called", m.state.callCount === 0);
  check("missing id: one dev diagnostic", m.state.debugCount === 1);

  // --- frappe present but call installed LATER ---
  let c = mk({ search: "?id=EC-PAYR-1", frappe: { boot: { developer_mode: true } } });
  try { c.exec(); } catch (e) { threwAny = true; } await tick();
  check("call-later: no readiness before call exists", c.state.callCount === 0);
  check("call-later: a timer is pending", c.timers.size === 1);
  c.fireN(3); await tick();
  check("call-later: still not called while call absent", c.state.callCount === 0);
  c.installCall(VIS); c.fire(); await tick();
  check("call-later: refresh runs once after call appears", c.state.callCount === 1);
  check("call-later: panel shown", c.els["ec-req-sign"].style.display === "block");
  check("call-later: timer cleared", c.timers.size === 0);
  c.fireN(3); await tick();
  check("call-later: no extra readiness after init", c.state.callCount === 1);

  // --- frappe ENTIRELY absent then appears ---
  let d = mk({ search: "?id=EC-PAYR-1", frappe: undefined });
  try { d.exec(); } catch (e) { threwAny = true; } await tick();
  check("absent: no throw", true);
  check("absent: timer pending", d.timers.size === 1);
  d.fireN(2); await tick();
  d.installCall(VIS); d.fire(); await tick();
  check("absent->appears: refresh runs once", d.state.callCount === 1);
  check("absent->appears: panel shown", d.els["ec-req-sign"].style.display === "block");

  // --- bounded timeout: call never appears ---
  let t = mk({ search: "?id=EC-PAYR-1", frappe: { boot: { developer_mode: true } } });
  t.exec(); t.fireN(45); await tick();          // > MAX_TRIES(40)
  check("timeout: panel stays hidden", t.els["ec-req-sign"].style.display === "none");
  check("timeout: readiness never called", t.state.callCount === 0);
  check("timeout: one dev diagnostic", t.state.debugCount === 1);
  check("timeout: timer cleared", t.timers.size === 0);

  // --- repeated init: no duplicate timers/handlers/calls ---
  let r = mk({ search: "?id=EC-PAYR-1", frappe: undefined });
  r.exec(); r.exec(); r.exec(); await tick();     // 3 executions on the SAME element
  check("repeated init: single timer", r.timers.size === 1);
  check("repeated init: prepare handler bound once", r.els["ecReqPrepare"]._onclickAssigns === 1);
  check("repeated init: lock handler bound once", r.els["ecReqLock"]._onclickAssigns === 1);
  r.installCall(VIS); r.fire(); await tick();
  check("repeated init: readiness called once total", r.state.callCount === 1);

  // --- Prepare/Lock use guarded window.frappe.call (cannot throw on timing) ---
  let g = mk({ search: "?id=EC-PAYR-1", frappe: undefined }); g.installCall(VIS); g.exec(); await tick();
  const before = g.state.callCount;
  g.sandbox.frappe.call = undefined;              // simulate call vanished at click time
  let clickThrew = false;
  try { g.els["ecReqPrepare"]._onclick(); g.els["ecReqLock"]._onclick(); } catch (e) { clickThrew = true; }
  check("guarded click: Prepare/Lock do not throw when call unavailable", clickThrew === false);
  check("guarded click: no API call made when unavailable", g.state.callCount === before);

  check("no scenario threw during init", threwAny === false);
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}
main();
