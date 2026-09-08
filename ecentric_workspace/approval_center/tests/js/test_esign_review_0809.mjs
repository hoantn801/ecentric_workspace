// Copyright (c) 2026, eCentric and contributors
// Rà soát SCTS đêm 08/09 — phần giao diện.
//
//  1. Payment Request: chân ký đã DỪNG của chính người duyệt (signing_readiness.stopped):
//     chưa gửi gì -> vẫn có "Duyệt & Ký" + ghi chú; có thể đã gửi -> KHÔNG có nút, nói rõ.
//  2. Trang ops: {queued:true} (Thử lại / Gửi lại có kiểm) phải báo "Xong", không báo đỏ.
//  3. Panel người đề nghị: startWait() không đặt lại mốc 6 phút khi đã chạy; Failed ->
//     "Gửi & ký lại"; Reconciliation Required -> "Đang đối soát".
//  4. Khối Tài liệu & ký số: openDrawer có mã phiên (stale) cho mọi phản hồi; DRW.signed reset
//     khi đổi phiếu; bảng lỗi tải được gỡ khi tải lại thành công; văn bản chỉ-xem theo lý do;
//     tải tệp: khoá nút khi đang tải + lý do 413.
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
function find(rel, name) {
  for (const r of ["../../", "../../../"]) {
    const p = path.join(HERE, r, rel, name);
    if (fs.existsSync(p)) return p;
  }
  throw new Error(name + " not found");
}
const PR_PAGE = find("features/payment_request/ui", "main_section.html");
const ESIGN_UI = path.dirname(find("../platform/esign/ui", "document_signing_section.html"));
const script = (p) => fs.readFileSync(p, "utf8").match(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/)[1];

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };

// ---------------------------------------------------------------- 1. PR page
{
  const SRC = script(PR_PAGE);
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
  const win = { location: { pathname: "/approvals/payment-request", search: "" },
    addEventListener(){}, matchMedia: () => ({ matches: false, addEventListener(){} }),
    requestAnimationFrame: (f) => f(), setTimeout, clearTimeout, console,
    setInterval: () => 1, clearInterval(){} };
  win.frappe = { csrf_token: "x", call: () => Promise.resolve({ message: {} }) };
  const sandbox = { window: win, document: doc, console, setTimeout, clearTimeout,
    setInterval: win.setInterval, clearInterval: win.clearInterval, frappe: win.frappe,
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }), navigator: { userAgent: "node" } };
  sandbox.globalThis = sandbox; vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "payment_request.js" });
  const PR = win.PaymentRequest; const st = PR.state;
  st.boot = { tabs: {}, context: {}, form_options: { yes_no: ["Yes", "No"] } };
  const DET = { capabilities: { can_approve: true, can_reject: true },
                approval: { approval_status: "Pending", current_level: 2 },
                business: { name: "EC-PAYR-2026-00099" } };
  console.log("PR: chân ký đã dừng (stopped)");
  st._signReady = { checks: { level_requires_signature: true }, in_flight: null,
                    stopped: { name: "EC-DSR-1", status: "Permanent Failure", error_code: "binding_refused", can_resign: true } };
  let html = PR.actionPanelHTML(DET);
  ok(html.includes('data-act="approvesign"'), "chưa gửi gì -> vẫn có Duyệt & Ký");
  ok(html.includes("đã dừng") && html.includes("binding_refused"), "ghi chú nêu trạng thái + mã lỗi");
  ok(html.includes("gửi lại"), "ghi chú mời gửi lại");
  st._signReady.stopped = { name: "EC-DSR-1", status: "Cancelled", error_code: null, can_resign: false };
  html = PR.actionPanelHTML(DET);
  ok(!html.includes('data-act="approvesign"'), "có thể đã gửi -> KHÔNG có nút Duyệt & Ký");
  ok(!html.includes('data-act="reject"'), "…và không có nút nào khác (khu hành động là ghi chú)");
  ok(html.includes("ký đúp") && html.includes("Cancelled"), "nói rõ lý do: tránh ký đúp, quản trị đối soát");
  st._signReady.stopped = { status: "Permanent Failure", error_code: "<img src=x onerror=1>", can_resign: true };
  html = PR.actionPanelHTML(DET);
  ok(!html.includes("<img"), "mã lỗi được esc() (không XSS)");
  st._signReady = { checks: { level_requires_signature: true }, in_flight: null, stopped: null };
  html = PR.actionPanelHTML(DET);
  ok(html.includes('data-act="approvesign"') && !html.includes("đã dừng"), "không có chân dừng -> như cũ");
  html = PR.actionPanelHTML({ capabilities: { can_reject: true }, approval: { current_level: 2 }, business: {} });
  st._signReady.stopped = { status: "Cancelled", can_resign: false };
  html = PR.actionPanelHTML({ capabilities: { can_reject: true }, approval: { current_level: 2 }, business: {} });
  ok(html.includes('data-act="reject"'), "không phải người duyệt (can_approve=false) thì ghi chú không áp dụng");
}

// ---------------------------------------------------------------- 1b. UNC state không theo sang phiếu khác
{
  const SRC = script(PR_PAGE);
  ok(/var prev=state\.id; state\.id=q\.get\("id"\)\|\|null;[\s\S]{0,400}if\(prev!==state\.id\) state\.unc=\{\};/.test(SRC),
     "readRoute: đổi phiếu thì xoá state.unc (UNC của A không gắn vào B)");
}

// ---------------------------------------------------------------- 2. ops page
{
  const src = script(path.join(ESIGN_UI, "ops_page.html"));
  console.log("Ops: queued = xong");
  const m = src.match(/var done = o && \(([^;]+)\);/);
  ok(!!m, "tìm thấy biểu thức done");
  const expr = m ? m[1] : "";
  const done = (o) => new Function("o", "return o && (" + expr + ");")(o);
  ok(done({ queued: true }) === true, "{queued:true} là xong (Thử lại / Gửi lại có kiểm)");
  ok(!done({ reason: "x" }), "không có cờ nào -> chưa xong");
  ok(done({ cancelled: true }) === true, "cancelled vẫn xong");
}

// ---------------------------------------------------------------- 3. requester panel
{
  const src = script(path.join(ESIGN_UI, "requester_signing_panel.html"));
  console.log("Panel người đề nghị");
  // Trích WAIT/stopWait/startWait; refresh() giả để không kéo theo DOM.
  const i = src.indexOf("var WAIT = {"), j = src.indexOf("function relocate()");
  ok(i > 0 && j > i, "tìm thấy khối WAIT");
  const block = src.slice(i, j);
  let now = 1000, intervals = 0;
  const ctx = { Date: { now: () => now }, setInterval: () => { intervals++; return intervals; },
    clearInterval(){}, refresh(){}, document: { getElementById: () => ({}) } };
  vm.createContext(ctx);
  vm.runInContext(block + "\nthis.WAIT = WAIT; this.startWait = startWait; this.stopWait = stopWait;", ctx);
  ctx.startWait(); const until1 = ctx.WAIT.until;
  now = 5000; ctx.startWait();
  ok(ctx.WAIT.until === until1, "startWait lần 2 KHÔNG đặt lại mốc 6 phút (trước đây đẩy mãi)");
  ok(intervals === 1, "chỉ một đồng hồ");
  ctx.stopWait(); now = 9000; ctx.startWait();
  ok(ctx.WAIT.until === 9000 + 6 * 60 * 1000, "sau stopWait thì startWait đặt mốc mới");
  ok(/WAIT\.expired = true/.test(src), "hết giờ đặt cờ expired");
  ok(/cur === "Failed"[\s\S]*Gửi & ký lại/.test(src), "Failed -> nút Gửi & ký lại");
  ok(/cur === "Reconciliation Required"[\s\S]*Đang đối soát/.test(src), "Reconciliation Required -> Đang đối soát, không nút");
  ok(/current_status/.test(src), "đọc current_status từ API");
  // Failed phải đến TRƯỚC nhánh "locked" (nhánh cũ nói 'Đã khoá gói ký và gửi chữ ký')
  ok(src.indexOf('cur === "Failed"') < src.indexOf("Đã khoá gói ký và gửi chữ ký"), "Failed xử lý trước nhánh 'đã gửi'");
  ok(/serverMsg\(e\) \|\| \(e && e\.message\)/.test(src), "lỗi gửi lại hiện thông điệp máy chủ");
}

// ---------------------------------------------------------------- 4. document section
{
  const src = script(path.join(ESIGN_UI, "document_signing_section.html"));
  console.log("Khối Tài liệu & ký số");
  const od = src.slice(src.indexOf("function openDrawer(ref)"), src.indexOf("function refreshRow()"));
  ok(/var myTok = DRW\.docToken, myPr = pr\(\)/.test(od), "openDrawer chụp mã phiên + phiếu");
  ok((od.match(/if \(stale\(\)\) return;/g) || []).length >= 6, "mọi phản hồi async đều kiểm stale (>=6 chỗ)");
  ok(/call\("placement_state"[\s\S]*?\.then\(function \(res\) \{\s*if \(stale\(\)\) return;/.test(od), "placement_state: kiểm stale TRƯỚC khi ghi DRW.st");
  ok(/getDocument\([\s\S]*?\.then\(function \(pdf\) \{[\s\S]*?if \(stale\(\)\) return;[\s\S]*?DRW\.pdf = pdf/.test(od), "PDF về muộn: kiểm stale trước khi gán DRW.pdf");
  ok(/document_signature_overlay[\s\S]*\.catch\(function \(\) \{ if \(stale\(\)\) return; DRW\.signed = \[\]; _applySigned\(\); \}\)/.test(od),
     "overlay lỗi -> xoá dấu 'Đã ký' cũ (không giữ ảnh chữ ký phiếu trước)");
  ok(/_ly\.innerHTML = ""/.test(od) && /ecdStage"\)\.style\.display = "none"/.test(od), "mở drawer xoá trang/ô của tệp trước ngay");
  ok(/DRW\.st\.ok === false/.test(od) && /không còn thuộc phiếu/.test(od), "stale_or_foreign_attachment nói đúng lý do");
  ok(/DRW\.signed = \[\];\s*\/\/ chu ky THAT/.test(src.slice(src.indexOf("function _clearDocState()"))), "_clearDocState reset DRW.signed");
  const ld = src.slice(src.indexOf("function load()"), src.indexOf("// one-time wiring"));
  ok(/ecdLoadErr"\);[^\n]*\n\s*if \(_le && _le\.parentNode\) _le\.parentNode\.removeChild\(_le\)/.test(ld), "tải lại thành công thì gỡ bảng lỗi");
  // _roText: theo lý do
  const rt = src.slice(src.indexOf("function _roText(st)"), src.indexOf("function refreshRow()"));
  const ctx = {}; vm.createContext(ctx); vm.runInContext(rt + "\nthis._roText = _roText;", ctx);
  ok(ctx._roText({ setup_editable_reason: "already_submitted" }).includes("đã được gửi"), "already_submitted");
  ok(ctx._roText({ setup_editable_reason: "package_locked" }).includes("đã khoá"), "package_locked");
  ok(ctx._roText({ setup_editable_reason: "needs_review" }).includes("rà soát"), "needs_review");
  ok(ctx._roText({ setup_editable_reason: null }).includes("người đề nghị"), "không phải người đề nghị -> nói đúng");
  // upload
  ok(/var UP = \{ busy: false, notice: "" \}/.test(src), "trạng thái tải tệp");
  ok(/if \(UP\.busy\) return;/.test(src), "đang tải thì không nhận đợt thứ hai");
  ok(/\|\| UP\.busy;/.test(src), "nút tải khoá khi đang tải");
  const ur = src.slice(src.indexOf("function _uploadReason("), src.indexOf("function uploadFiles("));
  const c2 = {}; vm.createContext(c2); vm.runInContext(ur + "\nthis._uploadReason = _uploadReason;", c2);
  ok(c2._uploadReason(413, null).includes("quá lớn"), "413 -> tệp quá lớn");
  ok(c2._uploadReason(403, null).includes("quyền"), "403 -> quyền");
  ok(c2._uploadReason(417, { _server_messages: JSON.stringify([JSON.stringify({ message: "<b>Chỉ PDF</b>" })]) }) === "Chỉ PDF", "thông điệp máy chủ, bỏ HTML");
  ok(/r\.text\(\)\.then/.test(src), "đọc text trước rồi mới parse JSON (413 trả HTML)");
  ok(/if \(UP\.notice\) \{ upHint\.textContent = UP\.notice; UP\.notice = ""; \}/.test(src), "render: dòng lỗi hiện một lần rồi trả lại gợi ý");
}

console.log("----");
console.log(pass + " đạt, " + fail + " hỏng");
process.exit(fail ? 1 : 0);
