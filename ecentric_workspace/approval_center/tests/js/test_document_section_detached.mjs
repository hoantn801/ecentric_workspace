// Copyright (c) 2026, eCentric and contributors
// PR-E QC 23/11 (B1): tren form Hop dong khoi nam trong #ctr-esign-slot. Trang ve lai (danh sach,
// tab, back, go({id})) THAO slot -> khoi bi tach khoi cay DOM. document.getElementById tra null cho
// phan tu ben trong; truoc ban sua: closeDrawer nem TypeError, vong theo doi 350ms chet, phieu sau
// khong bao gio tai. DOM gia o day MO PHONG viec thao (getElementById chi thay phan tu con gan).
//   1. root KHONG co querySelector (truong hop xau nhat): khong nem loi, phieu Y van tai + gan.
//   2. root CO querySelector (trinh duyet that): nhu tren.
import fs from "fs"; import vm from "vm";
import { fileURLToPath } from "url"; import path from "path";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(HERE, "..", "..", "..", "platform", "esign", "ui",
                                       "document_signing_section.html"), "utf8");
const SRC = HTML.match(/<script id="ec-docsign-script">([\s\S]*?)<\/script>/)[1];

let pass = 0, fail = 0;
function ok(c, m) { if (c) { pass++; console.log("  ok  " + m); } else { fail++; console.log("  HONG " + m); } }

const INSIDE = ["ecdCount","ecdSummary","ecdBanner","ecdRows","ecdUpload","ecdUploadBtn","ecdUploadHint",
  "ecdDrawerOv","ecdDrawerName","ecdDrawerSummary","ecdDrawerClose","ecdViewer","ecdSignerCards",
  "ecdViewerMsg","ecdStage","ecdCanvas","ecdLayer","ecdProg","ecdSaveState","ecdRoBanner","ecdDrawerErr",
  "ecdPlaceHint","ecdTrySign"];

async function scenario(withQS) {
  const els = {};
  function mkEl(id) {
    const el = { id, _html: "", textContent: "", _attrs: {}, _children: [], parentNode: null, _cls: new Set(),
      style: { display: id === "ec-docsign" ? "none" : "" }, disabled: false,
      getAttribute(k) { return (k in this._attrs) ? this._attrs[k] : null; },
      setAttribute(k, v) { this._attrs[k] = String(v); },
      appendChild(c) { c.parentNode = this; this._children.push(c); return c; },
      insertBefore(c) { c.parentNode = this; this._children.unshift(c); return c; }, firstChild: null,
      querySelectorAll() { return []; } };
    el.classList = { add: c => el._cls.add(c), remove: c => el._cls.delete(c), contains: c => el._cls.has(c) };
    Object.defineProperty(el, "innerHTML", { get() { return this._html; }, set(v) { this._html = String(v); } });
    return el;
  }
  const BODY = mkEl("body");
  function chainHas(el, anc) { let p = el; while (p) { if (p === anc) return true; p = p.parentNode; } return false; }
  function attached(el) {
    let p = el;
    while (p) {
      if (p === BODY) return true;
      if (p.id === "ctr-esign-slot" && els["ctr-esign-slot"] !== p) return false;   // slot cu da bi thao
      p = p.parentNode;
    }
    return false;
  }
  els["ec-docsign"] = mkEl("ec-docsign"); els["ec-docsign"].parentNode = BODY;
  Object.defineProperty(els["ec-docsign"], "isConnected", { get() { return attached(this); } });
  if (withQS) {
    els["ec-docsign"].querySelector = function (sel) {
      const e = els[String(sel).replace(/^#/, "")]; return e && chainHas(e, this) ? e : null; };
  }
  INSIDE.forEach(id => { els[id] = mkEl(id); els[id].parentNode = els["ec-docsign"]; });
  els["ec-ctr-root"] = mkEl("ec-ctr-root"); els["ec-ctr-root"].parentNode = BODY;
  const handlers = {}, intervals = [], fetches = [], errors = [];
  const sb = { document: { getElementById: id => { const e = els[id]; return e && attached(e) ? e : null; },
      querySelector: () => null, createElement: t => mkEl("_new_" + t),
      addEventListener(ev, f) { (handlers[ev] = handlers[ev] || []).push(f); }, body: BODY,
      documentElement: { classList: { add() {}, remove() {}, contains() { return false; } } } },
    location: { search: "?tab=my-requests" }, URLSearchParams, Promise, String, Array, Object, JSON,
    encodeURIComponent, console: { log() {}, error() {}, warn() {} },
    setInterval: (f, ms) => { intervals.push({ f, ms }); return intervals.length; }, clearInterval: () => {},
    setTimeout: () => 0, clearTimeout: () => {},
    fetch: (url) => { fetches.push(url);
      let m = {}; if (/document_setup_state/.test(url)) m = { editable: false, can_classify: false, documents: [],
        summary: {}, esign_enabled: true };
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: m }) }); },
    addEventListener() {}, confirm: () => true, open: () => {} };
  vm.createContext(sb); sb.window = sb;
  sb.frappe = { call: () => Promise.resolve({ message: {} }), utils: { escape_html: x => String(x) }, show_alert() {} };
  vm.runInContext(SRC, sb);
  const tick = async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); };
  const watcher = intervals.find(i => i.ms === 350).f;
  const runTick = () => { try { watcher(); } catch (e) { errors.push(String(e)); } };
  function detail(name) {
    const s = mkEl("ctr-esign-slot"); s._attrs["data-business-doctype"] = "EC Contract Review Request";
    s._attrs["data-business-name"] = name; s.parentNode = BODY; els["ctr-esign-slot"] = s;
    for (const f of handlers["ctr:detail-rendered"] || []) {
      try { f({ detail: { business_doctype: "EC Contract Review Request", business_name: name, esign_flow: "x" } }); }
      catch (e) { errors.push("event: " + e); }
    }
  }
  const tag = withQS ? "[co querySelector]" : "[khong querySelector]";
  await tick(); runTick();
  detail("CTR-X"); await tick();
  ok(els["ec-docsign"].parentNode === els["ctr-esign-slot"], tag + " X: khoi gan vao slot X");
  delete els["ctr-esign-slot"]; runTick(); runTick(); runTick(); await tick();   // ve danh sach: slot bi thao
  ok(errors.length === 0, tag + " danh sach: khong TypeError (" + (errors[0] || "") + ")");
  const before = fetches.length;
  detail("CTR-Y"); await tick(); runTick(); await tick();
  ok(fetches.slice(before).filter(u => /CTR-Y/.test(u)).length === 3, tag + " Y: tai du 3 lenh cho phieu Y");
  ok(els["ec-docsign"].parentNode === els["ctr-esign-slot"], tag + " Y: khoi gan vao slot Y");
  ok(errors.length === 0, tag + " khong loi suot luot");
}

async function main() {
  await scenario(false);
  await scenario(true);
  console.log(`\n${pass} dat, ${fail} hong`); process.exit(fail ? 1 : 0);
}
main().catch(e => { console.error(e); process.exit(1); });
