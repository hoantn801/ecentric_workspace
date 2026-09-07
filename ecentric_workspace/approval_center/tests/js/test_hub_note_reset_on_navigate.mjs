// Copyright (c) 2026, eCentric and contributors
// Hub "Tất cả yêu cầu": ô lý do từ chối không được dính sang hồ sơ kế (07/09, Hoàn).
//
// Khung popup dựng MỘT LẦN (ensureShell) nên #apl-note sống qua các lần bấm ‹ ›: gõ lý do
// cho A, sang B vẫn thấy ô đó với chữ của A; "Xác nhận" vẫn từ chối A (đúng) nhưng người
// dùng nhìn tưởng đang từ chối B. Kịch bản chạy trên CODE THẬT của trang qua vm với một DOM
// giả tối thiểu: mở A -> bấm Từ chối -> gõ -> vẽ B -> ô phải đóng và rỗng, hàng nút phải
// hiện lại. Kèm kiểm chứng ngược: Xác nhận (khi còn ở A) gửi đúng request_name = A.
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = path.join(HERE, "..", "..", "ui", "all_requests", "main_section.html");
if (!fs.existsSync(PAGE)) throw new Error("main_section.html not found: " + PAGE);
const SRC = fs.readFileSync(PAGE, "utf8").match(/<script id="ec-approval-all">([\s\S]*?)<\/script>/)[1];

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };

// ---- DOM giả: chỉ đủ cho ensureShell / fillHeader / drawDetail / askNote / resetNote ----
function mkEl(id) {
  const el = { id, _html: "", textContent: "", hidden: false, value: "", disabled: false,
    _attrs: {}, children: [], dataset: {}, style: {},
    classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    getAttribute(k){ return k in this._attrs ? this._attrs[k] : null; },
    setAttribute(k, v){ this._attrs[k] = String(v); },
    appendChild(c){ this.children.push(c); return c; }, remove(){}, focus(){},
    addEventListener(){}, querySelectorAll(){ return []; }, querySelector(){ return null; } };
  Object.defineProperty(el, "innerHTML", { configurable: true,
    get(){ return this._html; }, set(v){ this._html = String(v); } });
  return el;
}
// Ô ghi chú: các con (#apl-note-in, #apl-note-err, #apl-note-cancel, #apl-note-ok) tra theo id.
function mkNote() {
  const n = mkEl("apl-note"); n.hidden = true;
  n._kids = {};
  n.querySelector = (sel) => { const id = sel.replace(/^#/, ""); return n._kids[id] || (n._kids[id] = mkEl(id)); };
  // Đổ innerHTML mới = con cũ biến mất (như DOM thật), innerHTML "" = không còn con nào.
  Object.defineProperty(n, "innerHTML", { get(){ return n._html; },
    set(v){ n._html = String(v); n._kids = {}; } });
  return n;
}
function mkBox() {
  const box = mkEl("wrap");
  const parts = { av: mkEl("av"), title: mkEl("title"), sub: mkEl("sub"), nav: mkEl("nav"),
    body: mkEl("body"), foot: mkEl("apl-foot") };
  const note = mkNote();
  let card = null;
  box.querySelector = (sel) => {
    if (sel === ".ec-apl-modal") return card;
    if (sel === "#apl-note") return note;
    if (sel === "#apl-foot") return parts.foot;
    if (sel === ".ec-apl-aside") return null;
    const m = sel.match(/^\[data-h="(\w+)"\]$/); if (m) return parts[m[1]] || null;
    return null;
  };
  Object.defineProperty(box, "innerHTML", { get(){ return box._html; },
    set(v){ box._html = String(v); card = mkEl("card"); } });
  // Nút hành động: đọc data-a từ HTML chân thẻ (drawDetail vừa đổ) như querySelectorAll thật.
  box.querySelectorAll = (sel) => {
    if (sel !== "[data-a]") return [];
    const out = []; const re = /data-a="([a-z_]+)"/g; let m;
    while ((m = re.exec(parts.foot._html))) { const b = mkEl("btn-" + m[1]); b._attrs["data-a"] = m[1]; out.push(b); }
    box._lastButtons = out; return out;
  };
  box._note = note; box._parts = parts;
  return box;
}

const calls = [];
const doc = { readyState: "loading", getElementById: () => null, createElement: (t) => mkEl(t),
  querySelectorAll: () => [], querySelector: () => null, addEventListener(){},
  body: mkEl("body"), documentElement: { clientWidth: 1000 } };
const win = { location: { pathname: "/approvals/all-requests", search: "", href: "" },
  innerWidth: 1000, addEventListener(){}, setTimeout, clearTimeout, console,
  history: { replaceState(){} } };
win.frappe = { call: (o) => { calls.push({ method: o.method, args: o.args, type: o.type }); return Promise.resolve({ message: {} }); } };
const sandbox = { window: win, document: doc, console, setTimeout, clearTimeout,
  frappe: win.frappe, URLSearchParams, navigator: { userAgent: "node" } };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
try { vm.runInContext(SRC, sandbox, { filename: "all_requests.js" }); }
catch (e) { console.log("BOOT ERROR: " + e.message); process.exit(1); }
const AA = win.ApprovalAll;
if (!AA || typeof AA.drawDetail !== "function") { console.log("FAIL: ApprovalAll.drawDetail not exported"); process.exit(1); }

const detail = (name) => ({ approval: { name, current_level: 1 }, business: { request_title: "Phiếu " + name },
  capabilities: { can_reject: true, can_approve: true }, levels: [], display_fields: [], attachments: [], timeline: [] });
const box = mkBox();
AA.state.rowNames = ["EC-APR-A", "EC-APR-B"];

// 1. Mở A, bấm Từ chối, gõ lý do.
AA.drawDetail(box, "EC-APR-A", detail("EC-APR-A"));
const rejectA = box._lastButtons.find((b) => b.getAttribute("data-a") === "reject");
ok(!!rejectA, "A: có nút Từ chối");
rejectA.onclick();
const note = box._note, foot = box._parts.foot;
ok(note.hidden === false && foot.hidden === true, "A: bấm Từ chối mở ô lý do, ẩn hàng nút");
ok(/Lý do từ chối/.test(note.innerHTML), "A: ô ghi nhãn 'Lý do từ chối'");
const ta = note.querySelector("#apl-note-in");
ta.value = "Trùng với bộ EC-APR-2026-00156";

// 2. Sang B (như bấm ›): ô phải đóng, rỗng, hàng nút trở lại.
AA.drawDetail(box, "EC-APR-B", detail("EC-APR-B"));
ok(note.hidden === true, "B: ô lý do phải ĐÓNG sau khi chuyển hồ sơ");
ok(note.innerHTML === "", "B: ô lý do phải RỖNG (không còn chữ gõ cho A)");
ok(foot.hidden === false, "B: hàng nút hành động phải hiện lại");
ok(box._lastButtons.some((b) => b.getAttribute("data-a") === "reject"), "B: có nút Từ chối riêng của B");

// 3. Kiểm chứng ngược: khi CÒN ở A, Xác nhận gửi đúng A (hành vi cũ đúng, phải giữ).
AA.drawDetail(box, "EC-APR-A", detail("EC-APR-A"));
box._lastButtons.find((b) => b.getAttribute("data-a") === "reject").onclick();
note.querySelector("#apl-note-in").value = "Lý do X";
note.querySelector("#apl-note-ok").onclick();
const rej = calls.find((c) => String(c.method).endsWith(".reject"));
ok(!!rej && rej.args.request_name === "EC-APR-A" && rej.args.comment === "Lý do X" && rej.type === "POST",
   "A: Xác nhận từ chối gửi đúng request_name=A kèm lý do, POST");

// 4. Huỷ ô cũng trả lại hàng nút (đường cũ, không được hỏng theo).
box._lastButtons.find((b) => b.getAttribute("data-a") === "reject").onclick();
note.querySelector("#apl-note-cancel").onclick();
ok(note.hidden === true && foot.hidden === false, "Huỷ: đóng ô, hiện lại hàng nút");

console.log(`${pass} đạt, ${fail} hỏng`);
if (pass < 9) { console.log("HONG: so phep kiem thap bat thuong (" + pass + ") - bo test mo cau truc?"); process.exit(1); }
process.exit(fail ? 1 : 0);
