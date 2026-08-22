// Copyright (c) 2026, eCentric and contributors
// FULL E2E — drives the REAL document_signing_section script against a STATEFUL fake server with
// controllable network latency/ordering, through the whole requester journey A->Z:
// unsaved -> save-draft identity -> upload -> classify -> drawer -> place -> drag (in-flight race)
// -> reopen persistence -> out-of-order edits -> delete-while-in-flight (orphan cleanup) ->
// multi-position -> identity switch mid-flight -> post-submit read-only -> approver reveal.
// The final audit asserts the SERVER-side record store: exact row count, no duplicates, no orphans.
import fs from "fs"; import vm from "vm";
import { fileURLToPath } from "url"; import path from "path";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(process.env.E2E_SECTION || path.join(HERE, "..", "..", "..",
  "platform", "esign", "ui", "document_signing_section.html"), "utf8");
const SRC = HTML.match(/<script id="ec-docsign-script">([\s\S]*?)<\/script>/)[1]
  .replace(/import\(/g, "__import(");

let pass = 0, fail = 0;
const ok = (c, m) => { console.log((c ? "  ok - " : "  FAIL - ") + m); pass += c ? 1 : 0; fail += c ? 0 : 1; };

/* ---------------- upgraded DOM stub ---------------- */
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
    getContext() { return {}; },
    scrollIntoView() {},
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

/* ---------------- timers (cancelable) + intervals ---------------- */
let _tid = 0; const timers = new Map(); const intervals = [];
function fireTimers() { const fns = [...timers.values()]; timers.clear(); fns.forEach(f => f()); }
function fireIntervals() { intervals.forEach(f => f()); }

/* ---------------- STATEFUL fake server ---------------- */
const db = { req: {}, files: {}, placements: {}, seq: 0, submitted: {}, approver: false,
  stats: { createCalls: 0, updateCalls: 0, deleteCalls: 0, pdfLoads: {} } };
function seedRequest(id) { db.req[id] = true; db.files[id] = []; db.placements[id] = {}; }
function addFile(id, name) { const ref = "F" + (++db.seq);
  db.files[id].push({ ref, name, url: "/private/files/" + name, supporting: false }); return ref; }
const REQUIRED = [
  { slot_key: "requester", label: "Người đề nghị", kind: "requester",
    candidates: [{ user: "h@x", display_name: "Hoan", scts_mapping_status: "verified" }] },
  { slot_key: "level:L2:any-one", label: "Finance (một trong)", kind: "approval_level",
    candidates: [{ user: "f@x", display_name: "Fin", scts_mapping_status: "missing" }] }];
function plRows(id, ref) { return Object.values(db.placements[id] || {}).filter(p => p.ref === ref); }
function coveredOf(id, ref) {
  return new Set(plRows(id, ref).map(p => p.signer_slot_key)).size; }
function placementState(id, ref) {
  const f = (db.files[id] || []).find(x => x.ref === ref);
  const rows = plRows(id, ref).map(p => ({ name: p.name, page_index: p.page_index, x: p.x, y: p.y,
    width: p.width, height: p.height, signer_slot_key: p.signer_slot_key }));
  return { ok: true, document_ref: ref, display_name: f ? f.name : "?", file_url: f ? f.url : "",
    is_pdf: true, requires_signature: !(f && f.supporting), editable: !db.submitted[id],
    setup_editable_reason: db.submitted[id] ? "already_submitted" : null, needs_review: false,
    slot_key_version: 1, signer_plan_resolved: true, required_slots: REQUIRED,
    placements: rows, covered_slot_count: coveredOf(id, ref), required_slot_count: 2,
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
    setup_editable_reason: db.submitted[id] ? "already_submitted" : null,
    current_package_status: null, signer_plan: { resolved: true, summary: { required_slots: 2 } },
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
    if (db.submitted[id]) return { ok: false, reason: "already_submitted" };
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
    if (db.submitted[id]) return { ok: false, reason: "already_submitted" };
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
/* network with controllable delivery */
const net = [];
function frappeCall(o) {
  return new Promise((resolve, reject) => {
    net.push({ method: o.method, args: o.args || {}, resolve, reject }); });
}
function deliver(i) { const r = net.splice(i === undefined ? 0 : i, 1)[0];
  if (!r) return null; r.resolve({ message: handle(r.method, r.args) }); return r; }
async function deliverAll() { while (net.length) { deliver(0); await tick(); } }
const pendingOf = m => net.filter(r => r.method.endsWith(m));

/* ---------------- sandbox ---------------- */
const sb = { document: doc, console,
  location: { search: "" }, URLSearchParams, Promise, String, Array, Object, JSON, Math,
  setTimeout: (f) => { const id = ++_tid; timers.set(id, f); return id; },
  clearTimeout: (id) => { timers.delete(id); },
  setInterval: (f) => { intervals.push(f); return intervals.length; },
  clearInterval: () => {},
  FormData: function () { this._d = {}; this.append = (k, v) => { this._d[k] = v; }; },
  fetch: (url, o) => {                                        // native upload -> immediate file row
    const id = new URLSearchParams(sb.location.search).get("id");
    const fname = (o && o.body && o.body._d && o.body._d.file && o.body._d.file.name) || ("up" + (++db.seq) + ".pdf");
    const ref = addFile(id, fname);
    return Promise.resolve({ json: () => Promise.resolve({ message: { file_url: "/private/files/" + fname, name: ref } }) }); },
  confirm: () => true, open: () => {}, addEventListener() {} };
sb.window = sb;
sb.frappe = { call: frappeCall, utils: { escape_html: x => String(x == null ? "" : x) },
  show_alert() {}, csrf_token: "t", boot: {} };
sb.__import = (u) => { return Promise.resolve({ GlobalWorkerOptions: {},
  getDocument: (opts) => { const u2 = opts.url; db.stats.pdfLoads[u2] = (db.stats.pdfLoads[u2] || 0) + 1;
    return { promise: Promise.resolve({ getPage: () => Promise.resolve({
      getViewport: ({ scale }) => ({ width: 612 * (scale || 1), height: 792 * (scale || 1) }),
      render: () => ({ promise: Promise.resolve() }) }) }) }; } }); };
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

/* ================= JOURNEY ================= */
async function main() {
  vm.runInContext(SRC, sb); await tick();

  // A. new/unsaved request
  ok(els["ecdBanner"]._html.indexOf("Vui lòng lưu nháp") >= 0, "A1: trang Tạo mới -> trạng thái unsaved");
  ok(els["ecdUploadBtn"].disabled === true, "A2: upload bị khóa khi chưa lưu nháp");

  // B. save-draft -> identity appears (what 'Tiếp tục: Thêm chứng từ' does via go({id}))
  seedRequest("PR-1"); sb.location.search = "?id=PR-1";
  fireIntervals(); await tick(); await deliverAll(); await tick();
  ok(els["ecdCount"].textContent.indexOf("0") >= 0 || els["ecdRows"]._html === "",
     "B1: có id -> section load (0 tài liệu)");

  // C. upload 2 PDFs
  els["ecdUpload"].files = [{ name: "hopdong.pdf" }, { name: "bienban.pdf" }];
  els["ecdUpload"].onchange({ target: els["ecdUpload"] }); await tick(); await deliverAll(); await tick();
  ok(db.files["PR-1"].length === 2, "C1: server có đúng 2 File");
  ok(els["ecdRows"]._html.indexOf("hopdong.pdf") >= 0 && els["ecdRows"]._html.indexOf("bienban.pdf") >= 0,
     "C2: 2 dòng tài liệu hiển thị");
  const doc1 = db.files["PR-1"][0].ref, doc2 = db.files["PR-1"][1].ref;

  // D. classify doc2 as supporting
  const chk = els["ec-docsign"].querySelectorAll("[data-support]")
    .find(c => c.getAttribute("data-support") === doc2);
  chk.checked = true; chk.onchange(); await tick(); await deliverAll(); await tick();
  ok(db.files["PR-1"][1].supporting === true, "D1: phân loại bộ chứng từ ghi xuống server");

  // E. open drawer doc1, place, drag WHILE create in flight
  const btnSetup = els["ec-docsign"].querySelectorAll("[data-setup]")
    .find(b => b.getAttribute("data-setup") === doc1);
  btnSetup.onclick(); await tick(); await deliverAll(); await tick();
  ok(els["ecdDrawerOv"].style.display === "block", "E1: drawer mở");
  ok(doc.documentElement.classList.has("ecd-drawer-open"), "E2: cờ ẩn legacy layer bật khi drawer mở");
  ok(els["ecdProg"].textContent === "0/2", "E3: tiến độ 0/2");
  selectSlot("requester"); await tick();
  ok(els["ecdSignerCards"]._html.indexOf("Đang chọn vị trí") >= 0, "E4: nút chuyển '● Đang chọn vị trí…'");
  ok(els["ecdPlaceHint"].style.display === "block", "E5: hint 'Bấm vào tài liệu…' hiện");
  clickLayer(100, 100); await tick();
  ok(els["ecdLayer"]._kids.length === 1, "E6: box hiện NGAY (optimistic)");
  const box1 = els["ecdLayer"]._kids[0];
  fireTimers(); await tick();                                  // debounce -> CREATE dispatched (held)
  ok(pendingOf("save_placement").length === 1, "E7: 1 create đang bay");
  dragBox(box1, 150, 80); await tick();                        // user kéo NGAY khi create chưa về
  fireTimers(); await tick();                                  // debounce của lần kéo
  ok(pendingOf("save_placement").length === 1, "E8: KHÔNG bắn create thứ 2 khi đang bay (queued)");
  deliver(net.findIndex(r => r.method.endsWith("save_placement"))); await tick();  // create về
  ok(box1._p && box1._p.name, "E9: box nhận tên server tại chỗ");
  ok(pendingOf("save_placement").length === 1, "E10: bản kéo được gửi tiếp sau khi create về (serialized)");
  deliver(net.findIndex(r => r.method.endsWith("save_placement"))); await tick();
  const rowsE = plRows("PR-1", doc1);
  ok(rowsE.length === 1, "E11: SERVER chỉ có ĐÚNG 1 placement (không nhân đôi)");
  ok(Math.abs(rowsE[0].x - 250) < 1 && Math.abs(rowsE[0].y - 180) < 1,
     "E12: geometry server = vị trí SAU KHI kéo (250,180)");
  ok(els["ecdLayer"]._kids[0] === box1, "E13: response không rebuild box (giữ nguyên element)");
  ok(els["ecdProg"].textContent === "1/2", "E14: tiến độ 1/2");

  // F. close + reopen -> persisted; PDF cache
  els["ecdDrawerClose"].onclick(); await tick(); await deliverAll(); await tick();
  ok(!doc.documentElement.classList.has("ecd-drawer-open"), "F1: đóng drawer -> trả lại legacy layer");
  btnSetup.onclick(); await tick(); await deliverAll(); await tick();
  const re = els["ecdLayer"]._kids[0];
  ok(re && Math.abs(parseFloat(re.style.left) - 250) < 1, "F2: mở lại -> geometry giữ nguyên sau kéo");
  ok(db.stats.pdfLoads["/private/files/hopdong.pdf"] === 1, "F3: PDF chỉ tải 1 lần (cache khi mở lại)");

  // G. hai lần kéo liên tiếp, response về ĐÚNG THỨ TỰ serialize -> kết quả = lần cuối
  dragBox(re, 20, 20); fireTimers(); await tick();             // update #1 bay
  dragBox(re, 40, 40); fireTimers(); await tick();             // update #2 queued
  ok(pendingOf("save_placement").length === 1, "G1: chỉ 1 update đang bay, bản mới queued");
  await deliverAll(); await tick();
  const g = plRows("PR-1", doc1)[0];
  ok(Math.abs(g.x - 310) < 1 && Math.abs(g.y - 240) < 1, "G2: server = geometry lần kéo CUỐI (310,240)");
  ok(Math.abs(parseFloat(re.style.left) - 310) < 1, "G3: UI = geometry lần kéo cuối (không giật về)");

  // H. đặt box mới rồi XÓA khi create còn đang bay -> orphan cleanup
  selectSlot("level:L2:any-one"); await tick(); clickLayer(300, 300); await tick();
  const box2 = els["ecdLayer"]._kids[1];
  fireTimers(); await tick();                                  // create #2 bay (held)
  box2.querySelector(".del").onclick({ stopPropagation() {} }); await tick();
  ok(els["ecdLayer"]._kids.length === 1, "H1: xóa -> box biến mất ngay (local-first)");
  deliver(net.findIndex(r => r.method.endsWith("save_placement"))); await tick();  // create #2 về sau khi xóa
  ok(pendingOf("delete_placement").length === 1, "H2: client tự bắn delete dọn orphan");
  await deliverAll(); await tick();
  ok(plRows("PR-1", doc1).length === 1, "H3: server KHÔNG còn orphan (vẫn 1 placement)");

  // I. thêm vị trí thứ 2 cho cùng người ký (explicit)
  selectSlot("requester"); await tick(); clickLayer(400, 500); await tick();
  fireTimers(); await tick(); await deliverAll(); await tick();
  ok(plRows("PR-1", doc1).length === 2, "I1: 2 vị trí cho requester trên server");
  ok(els["ecdProg"].textContent === "1/2", "I2: progress vẫn 1/2 (unique slot, không đếm trùng)");

  // J. identity switch khi placement_state đang bay
  els["ecdDrawerClose"].onclick(); await tick(); await deliverAll(); await tick();
  btnSetup.onclick(); await tick();                            // placement_state của PR-1 đang bay
  sb.location.search = "";                                     // bấm 'Tạo mới'
  fireIntervals(); await tick();
  ok(els["ecdRows"]._html === "", "J1: chuyển 'Tạo mới' -> danh sách tài liệu cũ biến mất NGAY");
  ok(els["ecdDrawerOv"].style.display === "none", "J2: drawer đang mở bị đóng khi đổi request");
  await deliverAll(); await tick();                            // stale responses của PR-1 về muộn
  ok(els["ecdRows"]._html === "" && els["ecdBanner"]._html.indexOf("Vui lòng lưu nháp") >= 0,
     "J3: response muộn của PR-1 KHÔNG render vào trang mới");

  // K. post-submit read-only
  db.submitted["PR-1"] = true; sb.location.search = "?id=PR-1";
  fireIntervals(); await tick(); await deliverAll(); await tick();
  const btnSetup2 = els["ec-docsign"].querySelectorAll("[data-setup]")
    .find(b => b.getAttribute("data-setup") === doc1);
  btnSetup2.onclick(); await tick(); await deliverAll(); await tick();
  ok(els["ecdRoBanner"].style.display === "block", "K1: banner 'đã gửi - chỉ xem'");
  ok(els["ecdSignerCards"]._html.indexOf("data-add=") < 0, "K2: không còn nút đặt vị trí");
  const savesBefore = db.stats.createCalls + db.stats.updateCalls;
  clickLayer(50, 50); await tick(); fireTimers(); await tick(); await deliverAll(); await tick();
  ok(db.stats.createCalls + db.stats.updateCalls === savesBefore, "K3: click PDF không tạo save nào");
  const roBox = els["ecdLayer"]._kids[0];
  ok(roBox && (roBox.className || "").indexOf("ro") >= 0, "K4: box read-only (không kéo/xóa)");

  // L. approver reveal
  db.approver = true; els["ecdDrawerClose"].onclick(); await tick(); await deliverAll(); await tick();
  sb.location.search = ""; fireIntervals(); await tick();      // rời trang (identity đổi thật)
  sb.location.search = "?id=PR-1"; fireIntervals(); await tick(); await deliverAll(); await tick();
  ok(els["ec-approver-wrap"].style.display !== "none", "L1: approver đang chờ duyệt -> panel hiện");

  // M. FINAL SERVER AUDIT
  const all = Object.values(db.placements["PR-1"]);
  ok(all.length === 2, "M1: server audit - đúng 2 placement, không dư không thiếu");
  ok(all.every(p => p.signer_slot_key === "requester"), "M2: cả 2 đều slot requester (đúng journey)");
  ok(all.every(p => p.width > 0 && p.height > 0 && p.x >= 0 && p.y >= 0), "M3: không có geometry âm/0");
  ok(db.stats.createCalls === 3 && db.stats.deleteCalls === 1,
     "M4: đúng 3 create + 1 delete (orphan) trên cả hành trình - không double-create");
  ok(net.length === 0, "M5: không còn request treo");

  console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
}
main().catch(e => { console.error(e); process.exit(1); });
