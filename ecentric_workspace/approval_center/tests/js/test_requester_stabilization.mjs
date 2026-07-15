// Copyright (c) 2026, eCentric and contributors
// Requester panel STABILIZATION behaviour (fix/scts-requester-stabilization). Runs the shipped
// panel <script> in a node:vm DOM stub - no jsdom. Covers: package_invalid -> recovery action;
// prepare opens the editor IN PLACE via window.ecMountPlacementEditor with NO location.reload;
// pre-submission 'Chưa gửi duyệt' owner note; relocation into #ec-payr-root .content; and the
// state->button mapping (missing/incomplete/ready/locked/invalid).
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PANEL = path.join(HERE, "..", "..", "esign", "ui", "requester_signing_panel.html");
const src = fs.readFileSync(PANEL, "utf8").match(/<script id="ec-req-sign-script">([\s\S]*?)<\/script>/)[1];

function mkEl(id) {
  const el = { id, dataset: {}, textContent: "", innerHTML: "", _attrs: {}, _onclick: null,
    _children: [], parentNode: null,
    style: { display: (id === "ec-req-sign") ? "none" : (id === "ecReqGate" ? "none" : "") },
    getAttribute(k) { return (k in this._attrs) ? this._attrs[k] : null; },
    setAttribute(k, v) { this._attrs[k] = String(v); },
    appendChild(c) { c.parentNode = this; this._children.push(c); return c; } };
  Object.defineProperty(el, "onclick", { get() { return this._onclick; }, set(f) { this._onclick = f; } });
  return el;
}
function mkFrappe(state) {
  return { call(opts) {
      state.calls.push(opts.method);
      if (/requester_signing_readiness$/.test(opts.method)) return Promise.resolve({ message: state.readiness });
      if (/prepare_requester_signing_package$/.test(opts.method))
        return Promise.resolve({ message: { config: { package: "PKG", files: [{ name: "f1", file_name: "a.pdf", is_pdf: 1, requires_signature: 1 }] } } });
      return Promise.resolve({ message: { recovered: true } });
    },
    utils: { escape_html: (x) => x }, show_alert() {}, boot: { developer_mode: true } };
}

function run(readiness) {
  const els = {};
  ["ec-req-sign", "ecReqStatus", "ecReqMsg", "ecReqGate", "ecReqPrepare", "ecReqLock", "ecReqFix"]
    .forEach((id) => { els[id] = mkEl(id); });
  const startParent = mkEl("body-holder"); els["ec-req-sign"].parentNode = startParent;
  const contentHost = mkEl("content-host");
  const state = { calls: [], readiness: { checks: readiness }, reloadCount: 0, mountCalls: [] };
  const sandbox = {
    document: { getElementById: (id) => els[id] || null,
      querySelector: (sel) => (sel === "#ec-payr-root .content" ? contentHost : null) },
    location: { search: "?id=EC-PAYR-2026-00009", get reload() { return () => { state.reloadCount++; }; } },
    URLSearchParams, console: { debug() {}, log() {}, error() {} }, Promise, String, Object, Array,
    setInterval: (f) => 1, clearInterval: () => {} };
  vm.createContext(sandbox);
  sandbox.window = sandbox; sandbox.frappe = mkFrappe(state);
  sandbox.window.ecMountPlacementEditor = (cfg) => { state.mountCalls.push(cfg); };
  vm.runInContext(src, sandbox);
  return { els, state, contentHost };
}

let pass = 0, fail = 0;
const check = (n, c) => { if (c) { pass++; console.log("  ok -", n); } else { fail++; console.log("  FAIL -", n); } };
const tick = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };
const VIS = { is_requester: true, pending_requester_signature: true, requester_signature_required: true,
  verified_mapping: true, gates_enabled: false };

async function main() {
  // invalid: Locked + 0 placements
  let r = run(Object.assign({}, VIS, { package_present: true, package_invalid: true }));
  await tick();
  check("invalid -> status 'Gói lỗi'", r.els["ecReqStatus"].textContent.indexOf("Gói lỗi") === 0);
  check("invalid -> recovery button shown", r.els["ecReqFix"].style.display === "inline-block");
  check("invalid -> prepare hidden", r.els["ecReqPrepare"].style.display === "none");
  check("invalid -> lock hidden", r.els["ecReqLock"].style.display === "none");
  check("panel relocated into content", r.els["ec-req-sign"].parentNode === r.contentHost);

  // ready to lock
  r = run(Object.assign({}, VIS, { package_present: true, placements_ready: true }));
  await tick();
  check("ready -> 'Sẵn sàng khoá'", r.els["ecReqStatus"].textContent === "Sẵn sàng khoá");
  check("ready -> lock shown", r.els["ecReqLock"].style.display === "inline-block");

  // locked (valid)
  r = run(Object.assign({}, VIS, { package_present: true, package_locked: true }));
  await tick();
  check("locked -> 'Gói đã khoá'", r.els["ecReqStatus"].textContent === "Gói đã khoá");
  check("locked -> no buttons", r.els["ecReqPrepare"].style.display === "none" && r.els["ecReqLock"].style.display === "none");

  // missing package
  r = run(Object.assign({}, VIS, {}));
  await tick();
  check("missing -> 'Chưa chuẩn bị gói'", r.els["ecReqStatus"].textContent === "Chưa chuẩn bị gói");

  // prepare click: inline mount, NO reload
  r = run(Object.assign({}, VIS, {}));
  await tick();
  r.els["ecReqPrepare"]._onclick(); await tick();
  check("prepare -> ecMountPlacementEditor called", r.state.mountCalls.length === 1);
  check("prepare -> config has files", r.state.mountCalls[0].files.length === 1);
  check("prepare -> NO location.reload", r.state.reloadCount === 0);

  // recovery click: calls reset endpoint, no reload
  r = run(Object.assign({}, VIS, { package_present: true, package_invalid: true }));
  await tick();
  r.els["ecReqFix"]._onclick(); await tick();
  check("recovery -> reset endpoint called",
    r.state.calls.some((m) => /requester_reset_invalid_package$/.test(m)));
  check("recovery -> NO reload", r.state.reloadCount === 0);

  // pre-submission owner note
  r = run({ not_submitted: true, is_owner: true, requester_signature_required: true });
  await tick();
  check("pre-submit -> panel visible", r.els["ec-req-sign"].style.display === "block");
  check("pre-submit -> 'Chưa gửi duyệt'", r.els["ecReqStatus"].textContent === "Chưa gửi duyệt");
  check("pre-submit -> no action buttons", r.els["ecReqPrepare"].style.display === "none"
    && r.els["ecReqLock"].style.display === "none" && r.els["ecReqFix"].style.display === "none");

  // not owner + not submitted -> hidden
  r = run({ not_submitted: true, is_owner: false, requester_signature_required: true });
  await tick();
  check("not owner pre-submit -> hidden", r.els["ec-req-sign"].style.display === "none");

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}
main();
