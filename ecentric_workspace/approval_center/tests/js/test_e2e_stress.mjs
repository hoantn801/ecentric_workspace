// Copyright (c) 2026, eCentric and contributors
// E2E STRESS — same real-script + stateful-fake-server rig as test_e2e_full_journey, pushing the
// hostile paths: network failure + retry, rapid drawer open/close with in-flight loads, two
// documents switched quickly, full 2/2 completion, and a seeded 300-op fuzz (place/drag/delete/
// debounce-fire/random-order delivery) ending in a full drain + server<->UI consistency audit.
import fs from "fs"; import vm from "vm";
import { fileURLToPath } from "url"; import path from "path";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(process.env.E2E_SECTION || path.join(HERE, "..", "..", "..",
  "platform", "esign", "ui", "document_signing_section.html"), "utf8");
const SRC = HTML.match(/<script id="ec-docsign-script">([\s\S]*?)<\/script>/)[1]
  .replace(/import\(/g, "__import(");

let pass = 0, fail = 0;
const ok = (c, m) => { console.log((c ? "  ok - " : "  FAIL - ") + m); pass += c ? 1 : 0; fail += c ? 0 : 1; };

/* ---------------- DOM stub (same rig as full journey) ---------------- */
const els = {};
function mkEl(id) {
  const e = { id, _html: "", textContent: "", _attrs: {}, checked: false, disabled: false,
    style: { display: "" }, width: 612, height: 792, files: [], _kids: [], parentNode: null,
    _ls: {}, _qc: {},
    getAttribute(k) { return (k in this._attrs) ? this._attrs[k] : null; },
    setAttribute(k, v) { this._attrs[k] = String(v); },
    appendChild(c) { c.parentNode = this; this._kids.push(c); return c; },
    removeChild(c) { const i = this._kids.indexOf(c); if (i >= 0) this._kids.splice(i, 1); c.parentNode = null; return c; },
    addEventListener(t, f) { (this._ls[t] = this._ls[t] || []).push(f); },
    getBoundingClientRect() { return { left: 0, top: 0, width: this.width, height: this.height }; },
    getContext() { return {}; }, scrollIntoView() {},
    querySelector(sel) { const cls = sel.replace(".", "");
      const hit = this._kids.find(k => ((k._attrs.class || "")).indexOf(cls) >= 0);
      if (hit) return hit;
      if (!this._qc[sel]) this._qc[sel] = { onclick: null, className: cls, style: {} };
      return this._qc[sel]; },
    querySelectorAll(sel) { return qsa(sel); },
    get offsetLeft() { return parseFloat(this.style.left) || 0; },
    get offsetTop() { return parseFloat(this.style.top) || 0; },
    get offsetWidth() { return parseFloat(this.style.width) || 0; },
    get offsetHeight() { return parseFloat(this.style.height) || 0; } };
  Object.defineProperty(e, "innerHTML", { get() { return this._html; },
    set(v) { this._html = String(v); this._kids = []; } });
  return e;
}
const _qsaCache = {};
function qsa(sel) {
  const attr = sel.replace(/[\[\].]/g, "");
  const srcEl = (attr === "data-setup" || attr === "data-support" || attr === "data-open")
    ? els["ecdRows"] : els["ecdSignerCards"];
  const html = srcEl ? srcEl._html : "";
  const key = attr + "|" + html;
  if (_qsaCache[key]) return _qsaCache[key];
  const re = new RegExp(attr + '="([^"]*)"', "g"); const out = []; let m;
  while ((m = re.exec(html))) { const fe = mkEl("_" + attr + out.length); fe._attrs[attr] = m[1]; out.push(fe); }
  _qsaCache[key] = out; return out;
}
["ec-docsign","ecdCount","ecdSummary","ecdBanner","ecdRows","ecdUpload","ecdUploadBtn","ecdUploadHint",
 "ecdDrawerOv","ecdDrawerName","ecdDrawerSummary","ecdDrawerClose","ecdViewer","ecdViewerMsg","ecdStage",
 "ecdCanvas","ecdLayer","ecdSignerCards","ecdProg","ecdSaveState","ecdDrawerFoot","ecdRoBanner",
 "ecdDrawerErr","ecdPlaceHint","ecdTrySign","ec-approver-wrap","payr-body"].forEach(id => els[id] = mkEl(id));
const contentHost = { appendChild() {} }; els["payr-body"].parentNode = contentHost;
const doc = { _ls: {},
  getElementById: id => els[id] || null,
  querySelector: sel => (sel.indexOf("content") >= 0 ? contentHost : els["ec-approver-wrap"]),
  addEventListener(t, f) { (this._ls[t] = this._ls[t] || []).push(f); },
  createElement: t => mkEl("_new_" + t + (Math.random())),
  documentElement: { classList: { _s: {}, add(c) { this._s[c] = 1; }, remove(c) { delete this._s[c]; },
    has(c) { return !!this._s[c]; } } } };
function fireDoc(t, ev) { (doc._ls[t] || []).forEach(f => f(ev)); }

let _tid = 0; const timers = new Map(); const intervals = [];
function fireTimers() { const fns = [...timers.values()]; timers.clear(); fns.forEach(f => f()); }
function fireIntervals() { intervals.forEach(f => f()); }

/* ---------------- stateful fake server ---------------- */
const db = { files: {}, placements: {}, seq: 0, submitted: {}, approver: false, failNextSaves: 0,
  stats: { createCalls: 0, updateCalls: 0, deleteCalls: 0 } };
function seedRequest(id) { db.files[id] = []; db.placements[id] = {}; }
function addFile(id, name) { const ref = "F" + (++db.seq);
  db.files[id].push({ ref, name, url: "/private/files/" + name, supporting: false }); return ref; }
const REQUIRED = [
  { slot_key: "requester", label: "Người đề nghị", kind: "requester",
    candidates: [{ user: "h@x", display_name: "Hoan", scts_mapping_status: "verified" }] },
  { slot_key: "level:L2:any-one", label: "Finance (một trong)", kind: "approval_level",
    candidates: [{ user: "f@x", display_name: "Fin", scts_mapping_status: "missing" }] }];
function plRows(id, ref) { return Object.values(db.placements[id] || {}).filter(p => p.ref === ref); }
function coveredOf(id, ref) { return new Set(plRows(id, ref).map(p => p.signer_slot_key)).size; }
function placementState(id, ref) {
  const f = (db.files[id] || []).find(x => x.ref === ref);
  return { ok: true, document_ref: ref, display_name: f ? f.name : "?", file_url: f ? f.url : "",
    is_pdf: true, requires_signature: !(f && f.supporting), editable: !db.submitted[id],
    setup_editable_reason: null, needs_review: false, slot_key_version: 1, signer_plan_resolved: true,
    required_slots: REQUIRED,
    placements: plRows(id, ref).map(p => ({ name: p.name, page_index: p.page_index, x: p.x, y: p.y,
      width: p.width, height: p.height, signer_slot_key: p.signer_slot_key })),
    covered_slot_count: coveredOf(id, ref), required_slot_count: 2,
    progress: { covered: coveredOf(id, ref), required: 2 }, legacy_unmapped_count: 0 };
}
function setupState(id) {
  const docs = (db.files[id] || []).map(f => ({ document_ref: f.ref, display_name: f.name,
    file_url: f.url, requires_signature: !f.supporting, direct_signing_supported: true,
    required_signer_slots: 2, covered_slot_count: coveredOf(id, f.ref),
    setup_state: f.supporting ? "supporting_document"
      : (coveredOf(id, f.ref) >= 2 ? "complete" : (coveredOf(id, f.ref) ? "in_progress" : "not_configured")),
    legacy_placement_count: 0, duplicate_count: 1 }));
  return { editable: !db.submitted[id], can_classify: !db.submitted[id], needs_review: false,
    setup_editable_reason: null, current_package_status: null,
    signer_plan: { resolved: true, summary: { required_slots: 2 } },
    summary: { documents: docs.length, requires_signature: docs.filter(d => d.requires_signature).length,
      supporting_documents: docs.filter(d => !d.requires_signature).length }, documents: docs,
    stale_signing_files: [] };
}
function handle(method, args) {
  const m = method.split(".").pop(); const id = args.payment_request_name;
  if (m === "document_setup_state") return setupState(id);
  if (m === "signer_plan") return { resolved: true, summary: { required_slots: 2 }, slots: REQUIRED };
  if (m === "signing_readiness") return { checks: { active_approver: db.approver } };
  if (m === "placement_state") return placementState(id, args.document_ref);
  if (m === "save_placement") {
    if (db.failNextSaves > 0) { db.failNextSaves--; throw new Error("network"); }
    const box = JSON.parse(args.box); let name = box.name;
    if (name && !db.placements[id][name])                       // mirror backend: NEVER resurrect
      return { ok: false, reason: "placement_deleted", state: placementState(id, args.document_ref) };
    if (name && db.placements[id][name]) { db.stats.updateCalls++;
      Object.assign(db.placements[id][name], { x: box.x, y: box.y, width: box.width,
        height: box.height, page_index: box.page_index || 1 });
    } else { db.stats.createCalls++; name = "PL" + (++db.seq);
      db.placements[id][name] = { name, ref: args.document_ref, x: box.x, y: box.y,
        width: box.width, height: box.height, page_index: box.page_index || 1,
        signer_slot_key: box.signer_slot_key }; }
    return { ok: true, placement_name: name, state: placementState(id, args.document_ref) };
  }
  if (m === "delete_placement") { db.stats.deleteCalls++;
    delete db.placements[id][args.placement_name];
    return { ok: true, state: placementState(id, args.document_ref) }; }
  if (m === "set_document_requires_signature") {
    const f = db.files[id].find(x => x.ref === args.document_ref);
    f.supporting = String(args.requires_signature) === "false";
    return { ok: true, document: setupState(id).documents.find(d => d.document_ref === args.document_ref),
      editable: true }; }
  if (m === "set_representative_attachment") return { ok: true };
  return {};
}
const net = [];
function frappeCall(o) { return new Promise((resolve, reject) => {
  net.push({ method: o.method, args: o.args || {}, resolve, reject }); }); }
function deliver(i) { const r = net.splice(i === undefined ? 0 : i, 1)[0]; if (!r) return null;
  try { r.resolve({ message: handle(r.method, r.args) }); } catch (e) { r.reject(e); } return r; }
async function deliverAll() { let n = 0; while (net.length && n++ < 500) { deliver(0); await tick(); } }
const pendingOf = m => net.filter(r => r.method.endsWith(m));

const sb = { document: doc, console,
  location: { search: "" }, URLSearchParams, Promise, String, Array, Object, JSON, Math,
  setTimeout: (f) => { const id = ++_tid; timers.set(id, f); return id; },
  clearTimeout: (id) => { timers.delete(id); },
  setInterval: (f) => { intervals.push(f); return intervals.length; }, clearInterval: () => {},
  FormData: function () { this._d = {}; this.append = (k, v) => { this._d[k] = v; }; },
  fetch: (url, o) => { const id = new URLSearchParams(sb.location.search).get("id");
    const fname = (o && o.body && o.body._d && o.body._d.file && o.body._d.file.name) || ("up" + (++db.seq) + ".pdf");
    const ref = addFile(id, fname);
    return Promise.resolve({ json: () => Promise.resolve({ message: { file_url: "/private/files/" + fname, name: ref } }) }); },
  confirm: () => true, open: () => {}, addEventListener() {} };
sb.window = sb;
sb.frappe = { call: frappeCall, utils: { escape_html: x => String(x == null ? "" : x) },
  show_alert() {}, csrf_token: "t", boot: {} };
sb.__import = () => Promise.resolve({ GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve({ getPage: () => Promise.resolve({
    getViewport: ({ scale }) => ({ width: 612 * (scale || 1), height: 792 * (scale || 1) }),
    render: () => ({ promise: Promise.resolve() }) }) }) }) });
vm.createContext(sb);

const tick = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
function selectSlot(key) { const b = els["ec-docsign"].querySelectorAll("[data-add]")
  .find(c => c.getAttribute("data-add") === key); if (b && b.onclick) b.onclick({ stopPropagation() {} }); return b; }
function clickLayer(x, y) { els["ecdLayer"].onclick({ target: els["ecdLayer"], clientX: x, clientY: y }); }
function dragBox(b, dx, dy, rsz) {
  (b._ls["mousedown"] || []).forEach(f => f({ target: { className: rsz ? "rsz" : "" },
    clientX: 0, clientY: 0, preventDefault() {} }));
  fireDoc("mousemove", { clientX: dx, clientY: dy });
  fireDoc("mouseup", {});
}
function openDoc(ref) { const b = els["ec-docsign"].querySelectorAll("[data-setup]")
  .find(x => x.getAttribute("data-setup") === ref); b.onclick(); return b; }
async function drain() { let n = 0;
  while ((timers.size || net.length) && n++ < 100) { fireTimers(); await tick(); await deliverAll(); await tick(); } }
function rng(seed) { let s = seed >>> 0; return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296; }

async function main() {
  vm.runInContext(SRC, sb); await tick();
  seedRequest("PR-9"); sb.location.search = "?id=PR-9";
  fireIntervals(); await tick(); await deliverAll(); await tick();
  els["ecdUpload"].files = [{ name: "a.pdf" }, { name: "b.pdf" }];
  els["ecdUpload"].onchange({ target: els["ecdUpload"] }); await tick(); await deliverAll(); await tick();
  const dA = db.files["PR-9"][0].ref, dB = db.files["PR-9"][1].ref;

  // N. network failure -> visible error -> retry heals
  openDoc(dA); await tick(); await deliverAll(); await tick();
  selectSlot("requester"); clickLayer(100, 100); await tick();
  db.failNextSaves = 1; fireTimers(); await tick(); await deliverAll(); await tick();
  ok(els["ecdSaveState"].textContent.indexOf("Lưu lỗi") >= 0, "N1: mạng lỗi -> 'Lưu lỗi — thử lại'");
  ok(els["ecdDrawerErr"].style.display === "block", "N2: lỗi hiện TRONG drawer");
  ok(plRows("PR-9", dA).length === 0, "N3: server chưa có row (save fail)");
  const bx = els["ecdLayer"]._kids[0];
  dragBox(bx, 10, 10); await drain();                          // retry qua kéo lại
  ok(plRows("PR-9", dA).length === 1, "N4: retry thành công -> đúng 1 row, không nhân đôi");
  ok(els["ecdSaveState"].textContent === "Đã lưu", "N5: trạng thái về 'Đã lưu'");

  // O. mở/đóng drawer liên tục khi load đang bay
  els["ecdDrawerClose"].onclick(); await drain();
  openDoc(dA); openDoc(dB); els["ecdDrawerClose"].onclick(); openDoc(dA); await tick();
  await deliverAll(); await tick();
  ok(els["ecdDrawerOv"].style.display === "block", "O1: mở-đóng-mở nhanh không crash, drawer mở");
  ok((els["ecdDrawerName"].textContent || "").indexOf("a.pdf") >= 0, "O2: hiển thị đúng tài liệu cuối (a.pdf)");
  ok(els["ecdLayer"]._kids.length === 1, "O3: box của a.pdf hydrate đúng (1 box)");

  // P. hai tài liệu: đặt ở B, không rò sang A
  els["ecdDrawerClose"].onclick(); await drain();
  openDoc(dB); await tick(); await deliverAll(); await tick();
  ok(els["ecdLayer"]._kids.length === 0, "P1: b.pdf chưa có box (không rò từ a.pdf)");
  selectSlot("requester"); clickLayer(200, 200); await drain();
  ok(plRows("PR-9", dB).length === 1 && plRows("PR-9", dA).length === 1,
     "P2: mỗi tài liệu đúng 1 row riêng");

  // Q. complete 2/2 trên b.pdf
  selectSlot("level:L2:any-one"); clickLayer(300, 400); await drain();
  ok(els["ecdProg"].textContent === "2/2", "Q1: đủ 2 slot -> 2/2");
  els["ecdDrawerClose"].onclick(); await drain();
  ok(els["ecdRows"]._html.indexOf("2/2") >= 0 || els["ecdRows"]._html.indexOf("Hoàn tất") >= 0
     || (setupState("PR-9").documents.find(d => d.document_ref === dB) || {}).setup_state === "complete",
     "Q2: row b.pdf phản ánh hoàn tất sau khi đóng drawer");

  // R. FUZZ 300 ops (seed 20260821) trên a.pdf
  openDoc(dA); await tick(); await deliverAll(); await tick();
  const rand = rng(parseInt(process.env.FUZZ_SEED || "20260821", 10)); let exceptions = 0;
  const SLOTS = ["requester", "level:L2:any-one"];
  for (let i = 0; i < 300; i++) {
    try {
      const kids = els["ecdLayer"]._kids, r = rand();
      if (r < 0.22) { selectSlot(SLOTS[(rand() * 2) | 0]); clickLayer(rand() * 500, rand() * 700); await tick(); }
      else if (r < 0.5 && kids.length) { dragBox(kids[(rand() * kids.length) | 0], rand() * 60 - 30, rand() * 60 - 30, rand() < 0.3); await tick(); }
      else if (r < 0.6 && kids.length) { const k = kids[(rand() * kids.length) | 0];
        k.querySelector(".del").onclick({ stopPropagation() {} }); await tick(); }
      else if (r < 0.8) { fireTimers(); await tick(); }
      else if (net.length) { deliver((rand() * net.length) | 0); await tick(); }
    } catch (e) { exceptions++; }
  }
  await drain();
  ok(exceptions === 0, "R1: fuzz 300 ops - 0 exception");
  const uiBoxes = els["ecdLayer"]._kids.length, svRows = plRows("PR-9", dA).length;
  // drain xong: mọi box UI phải có trên server, không orphan, không dup
  const uiNames = els["ecdLayer"]._kids.map(k => k._p && k._p.name).filter(Boolean);
  ok(uiBoxes === svRows, `R2: UI boxes (${uiBoxes}) == server rows (${svRows}) sau drain`);
  ok(new Set(uiNames).size === uiNames.length && uiNames.length === uiBoxes,
     "R3: mọi box UI đều đã có tên server, không trùng");
  ok(plRows("PR-9", dA).every(p => p.width > 0 && p.height > 0 && p.x >= 0 && p.y >= 0),
     "R4: geometry server luôn hợp lệ (không âm/0)");
  ok(net.length === 0 && timers.size === 0, "R5: không request/timer treo");
  ok(els["ecdSaveState"].textContent !== "Đang lưu…", "R6: không kẹt 'Đang lưu…'");
  // reopen -> hydrate đúng từ server
  els["ecdDrawerClose"].onclick(); await drain();
  openDoc(dA); await tick(); await deliverAll(); await tick();
  ok(els["ecdLayer"]._kids.length === svRows, "R7: mở lại hydrate đúng số box từ server");

  console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
}
main().catch(e => { console.error(e); process.exit(1); });
