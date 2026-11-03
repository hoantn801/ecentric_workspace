// Hien thi dung chung cho trang phe duyet (03/11/2026): ec_approval_ui.bundle.js + 31 form + hub.
//
//  1. Lich su: KHONG con chu tieng Anh tho ("Attachment Added", "Reminded", "System Transition"...)
//     tren BAT KY form nao lan popup hub; moi option cua EC Approval Action.action deu co nhan.
//  2. Thanh tien trinh: cham tron cua cap duyet hien DUNG so cap engine (Cap 1 -> "1"), buoc
//     "Da gui" / "Hoan tat" khong danh so; ten buoc "Cap N · <ten>". Cot "Tien do" cung theo so cap.
//  3. Loi ky thuat (Traceback, NoneType, CSRF...) -> cau tieng Viet; cau nghiep vu giu nguyen.
//  4. Hub: lich su MOI NHAT len dau + co gio (action_time); gui trao doi loi khong khoa nut Gui.
//     node ecentric_workspace/approval_center/tests/js/test_approval_ui_labels.mjs
import { JSDOM } from "jsdom";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const AC = join(here, "..", "..");
const FEAT = join(AC, "features");
const ROOT = join(AC, "..");
const BUNDLE = readFileSync(join(ROOT, "public", "js", "ec_approval_ui.bundle.js"), "utf8");
const REMIND = readFileSync(join(ROOT, "public", "js", "ec_remind.bundle.js"), "utf8");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 5)); };

// Moi option that cua DocType - them option moi ma quen dich thi test nay do.
const ACTION_JSON = JSON.parse(readFileSync(join(AC, "doctype", "ec_approval_action", "ec_approval_action.json"), "utf8"));
const ACTIONS = ACTION_JSON.fields.find((x) => x.fieldname === "action").options.split("\n").filter(Boolean);
const EN = new RegExp("\\b(" + ACTIONS.map((a) => a.replace(/ /g, "\\s")).join("|") + ")\\b");

// ---- 1. bundle don le ------------------------------------------------------------------------
const U = (() => { const d = new JSDOM("<!DOCTYPE html><body></body>", { runScripts: "outside-only" });
  d.window.eval(BUNDLE); return d.window.EcApprovalUI; })();
ok(ACTIONS.length >= 15, "doc duoc option action: " + ACTIONS.length);
for (const a of ACTIONS) {
  const v = U.actionLabel(a);
  ok(v && v !== a && !EN.test(v), "nhan tieng Viet cho '" + a + "' -> " + v);
}
for (const s of ["Draft", "Pending", "Approved", "Rejected", "Information Required", "Cancelled", "In Progress", "Skipped"])
  ok(U.statusLabel(s) !== s, "nhan trang thai " + s);
ok(U.fmtDateTime("2026-11-03 14:05:22.123") === "03/11/2026 14:05", "gio dd/mm/yyyy HH:mm");
ok(U.fmtDateTime("2026-11-03") === "03/11/2026" && U.fmtDateTime(null) === "—", "ngay + rong");
ok(U.levelText(1, "Trưởng phòng duyệt") === "Cấp 1 · Trưởng phòng duyệt", "levelText");
ok(U.levelText(2, "Finance", 4) === "Cấp 2/4 · Finance", "levelText co tong");
ok(U.levelText(1, "Cấp 1") === "Cấp 1" && U.levelText(1, "Level 1") === "Cấp 1", "khong lap 'Cap 1 · Cap 1'");
{ const h = U.timelineHTML([{ action: "Reminded", actor: "Administrator", action_time: "2026-11-03 09:00:00",
    previous_status: "Pending", new_status: "Approved", level_no: 1, level_name: "Lead", comment: "<img src=x onerror=1>" }]);
  ok(/Đã nhắc người xử lý · Cấp 1 · Lead/.test(h), "lich su: nhan + cap");
  ok(/Hệ thống · 03\/11\/2026 09:00 · Chờ duyệt → Đã duyệt/.test(h), "lich su: nguoi he thong + gio + trang thai tieng Viet");
  ok(!/<img/.test(h) && /&lt;img/.test(h), "lich su: ghi chu duoc esc"); }
ok(/Chưa có hoạt động/.test(U.timelineHTML([])), "lich su rong");
{ const h = U.stepsHTML([{ name: "Đã gửi", state: "done" }, { level: 1, name: "Lead", state: "done" },
    { level: 2, name: "HOF", state: "current", meta: '<span class="ov">Quá hạn</span>' }, { name: "Hoàn tất", state: "upcoming" }]);
  const d = new JSDOM("<body>" + h + "</body>").window.document;
  const dots = [...d.querySelectorAll(".step-dot")].map((x) => x.textContent);
  ok(dots.join("|") === "✓|✓|2|", "cham: Da gui ✓, cap 1 ✓, cap 2 -> '2', Hoan tat khong so: " + dots.join("|"));
  const names = [...d.querySelectorAll(".step-name")].map((x) => x.textContent);
  ok(names[2] === "Cấp 2 · HOF" && names[0] === "Đã gửi" && names[3] === "Hoàn tất", "ten buoc: " + names.join("|"));
  ok(d.querySelector(".step.current[aria-current=step] .ov"), "meta giu nguyen HTML trang + aria-current");
  ok(/--n:4;--k:2/.test(h), "giu bien CSS --n/--k cua thanh tien trinh"); }
ok(/is-cancelled/.test(U.stepsHTML([], { cancelled: true })), "phieu huy giu class is-cancelled");
// loi
const sm = (m) => ({ _server_messages: JSON.stringify([JSON.stringify({ message: m })]) });
ok(!/NoneType/.test(U.errorText(sm("AttributeError: 'NoneType' object has no attribute 'get'"))), "loi Python -> cau tieng Viet");
ok(/Hệ thống gặp lỗi/.test(U.errorText({ responseJSON: { exception: "pymysql.err.IntegrityError: (1062, \"Duplicate entry 'x' for key 'name'\")" } })), "loi SQL -> cau tieng Viet");
ok(/phản hồi chậm/.test(U.errorText({ status: 504, responseJSON: {} })), "504 -> he thong cham");
ok(/Phiên đăng nhập/.test(U.errorText({ exc_type: "CSRFTokenError", status: 400 })), "CSRF -> phien het han");
ok(/Mất kết nối/.test(U.errorText({ status: 0, message: "Failed to fetch" })), "mang -> mat ket noi");
ok(U.errorText(sm("Vui lòng nhập lý do.")) === "Vui lòng nhập lý do.", "cau nghiep vu giu nguyen");
ok(U.isTechnical(sm("Traceback (most recent call last)")) && !U.isTechnical(sm("Bạn không còn quyền.")), "isTechnical");
ok(U.errorText(null, "X") === "X", "khong co gi -> fallback");

// ---- 2. 31 form: chay CODE THAT cua trang -----------------------------------------------------
const LEVELS = [{ level_no: 1, level_name: "Department Manager Review", level_status: "Approved" },
  { level_no: 2, level_name: "Finance Review", level_status: "In Progress" }];
const TL = ACTIONS.map((a, i) => ({ seq: i + 1, action: a, actor: "lead@x", action_time: "2026-11-0" + (1 + (i % 3)) + " 09:3" + (i % 10) + ":00",
  previous_status: "Pending", new_status: i % 2 ? "Pending" : "Information Required", level_no: i % 2 ? 1 : null }));
// Hai form nay khong ve thanh tien trinh o man chi tiet (bang ban giao song song thay the).
const NO_STEPPER = new Set(["clearance_request", "new_staff_preparation"]);
const DET = () => ({ business: { name: "R-1", requested_by: "req@x", request_title: "T", approval_request: "AR", creation: "2026-11-01 08:00:00" },
  approval: { name: "AR", approval_status: "Pending", current_level: 2 }, request: { name: "AR", approval_status: "Pending", current_level: 2 },
  levels: LEVELS, approvers: [{ level_no: 1, approver: "lead@x", status: "Approved" }, { level_no: 2, approver: "fin@x", status: "Pending" }],
  attachments: [], timeline: TL, extra: {}, items: [], capabilities: {}, fulfillment: {} });
function boot(html, route, det, withBundle, detailErr) {
  const i = html.search(/<script[^>]*id="ec-[^"]+"[^>]*>/);
  const markup = html.slice(0, i);
  const js = html.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/" + route + "?id=R-1" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", session: { user: "req@x" }, call: (o) => { const m = o.method.split(".").pop();
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true, all: true }, context: { user: "req@x" }, form_options: {}, options: {} } });
    if (m === "get_detail" || m === "get_request_detail") return detailErr ? Promise.reject(detailErr) : Promise.resolve({ message: det });
    return Promise.resolve({ message: { rows: [], total: 0, data: [] } }); } };
  if (withBundle) w.eval(BUNDLE);
  w.eval(REMIND);
  try { w.eval(js); } catch (e) { return { w, err: e }; }
  return { w };
}
const feats = readdirSync(FEAT).filter((f) => existsSync(join(FEAT, f, "ui", "main_section.html")) && f !== "brand_weight");
ok(feats.length >= 31, "du form: " + feats.length);
for (const f of feats) {
  const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
  const route = (readFileSync(join(FEAT, f, "infrastructure", "page_sync.py"), "utf8").match(/ROUTE = "([^"]+)"/) || [])[1];
  ok(!/"Bước "\+/.test(html), f + ": khong con dem 'Buoc X/N' (Da gui = buoc 1)");
  const { w, err } = boot(html, route, DET(), true); await flush();
  ok(!err, f + ": trang chay duoc " + (err || ""));
  const doc = w.document;
  const steps = [...doc.querySelectorAll(".stepline .step")];
  if (NO_STEPPER.has(f)) ok(steps.length === 0, f + ": (khong co thanh tien trinh o chi tiet)");
  else {
  ok(steps.length >= 3, f + ": co thanh tien trinh (" + steps.length + " buoc)");
  const byName = (re) => steps.find((s) => re.test(s.querySelector(".step-name").textContent));
  const s1 = byName(/Department Manager Review/), s2 = byName(/Finance Review/), sent = byName(/^Đã gửi$/);
  ok(s1 && /^Cấp 1 · /.test(s1.querySelector(".step-name").textContent), f + ": ten cap 1 = 'Cap 1 · ...'");
  ok(s2 && s2.querySelector(".step-dot").textContent === "2", f + ": cham cap 2 hien '2' (truoc la '3')");
  ok(sent && !/\d/.test(sent.querySelector(".step-dot").textContent), f + ": 'Da gui' khong danh so");
  }
  if (/function timelineHTML\(/.test(html)) {
    const tl = [...doc.querySelectorAll(".tl-item")];
    ok(tl.length === TL.length, f + ": lich su du " + TL.length + " dong (co " + tl.length + ")");
    const txt = tl.map((x) => x.textContent).join("\n");
    ok(!EN.test(txt), f + ": lich su khong con chu tieng Anh tho: " + (txt.match(EN) || [""])[0]);
    ok(/Đã nhắc người xử lý/.test(txt) && /Đã thêm tệp đính kèm/.test(txt) && /Hệ thống tự chuyển bước/.test(txt), f + ": nhan moi");
    ok(/0[1-3]\/11\/2026 09:3\d/.test(txt) && !/2026-11-0/.test(txt), f + ": gio lich su dd/mm/yyyy");
    ok(/Chờ duyệt → Cần bổ sung/.test(txt), f + ": trang thai chuyen doi tieng Viet");
  }
  // mapErr: loi ky thuat khong lot ra nguoi dung (trang nao co mapErr thi kiem qua ham that)
  if (/function mapErr\(e\)\{ if\(window\.EcApprovalUI&&EcApprovalUI\.isTechnical\(e\)\)/.test(html)) {
    const api = Object.values(w).find((v) => v && typeof v === "object" && typeof v.mapErr === "function" && v.state);
    if (api) { const m = api.mapErr(sm("AttributeError: 'NoneType' object has no attribute 'name'"));
      ok(!/NoneType|AttributeError/.test(m) && /Hệ thống gặp lỗi/.test(m), f + ": mapErr che loi ky thuat -> " + m); }
  } else ok(f === "booking_request", f + ": mapErr chua uy quyen loi ky thuat");
  // Mo chi tiet loi: khong quyen (thong diep o _server_messages) -> noi ro; loi ky thuat -> cau tieng Viet
  if (f !== "booking_request") {
    { const { w: w2 } = boot(html, route, DET(), true, Object.assign(sm("Bạn không có quyền xem yêu cầu này."), { exc_type: "PermissionError" })); await flush();
      ok(/Bạn không có quyền xem yêu cầu này/.test(w2.document.body.textContent), f + ": loi quyen -> bao khong co quyen"); }
    { const { w: w2 } = boot(html, route, DET(), true, sm("KeyError: 'approval_status'")); await flush();
      const t = w2.document.body.textContent;
      ok(/Không tải được yêu cầu/.test(t) && /Hệ thống gặp lỗi/.test(t) && !/KeyError/.test(t), f + ": loi ky thuat khi mo chi tiet -> cau tieng Viet"); }
  }
  // Khong co bundle (vd test cu, asset chua build): trang van chay, ban cu lam du phong.
  { const { err: e2 } = boot(html, route, DET(), false); await flush(); ok(!e2, f + ": khong bundle van chay"); }
}

// ---- 3. hub /approvals/all-requests ----------------------------------------------------------
{
  const html = readFileSync(join(AC, "ui", "all_requests", "main_section.html"), "utf8");
  ok(!/ACT_VI/.test(html), "hub: bo bang nhan rieng");
  const i = html.search(/<script[^>]*id="ec-approval-all"[^>]*>/);
  const markup = html.slice(0, i);
  const js = html.slice(i).match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/approvals/all-requests" });
  const w = dom.window; let commentFail = false;
  const tl = Array.from({ length: 10 }, (_, k) => ({ seq: k + 1, action: k === 9 ? "Attachment Added" : (k === 0 ? "Submitted" : "Reminded"),
    actor: "u" + k + "@x", action_time: "2026-11-" + String(10 + k) + " 08:0" + k + ":00" }));
  const det = { business: { name: "B-1", request_title: "T" }, approval: { name: "AR", approval_status: "Pending", current_level: 2 },
    levels: [{ level_no: 1, level_name: "Trưởng phòng duyệt", level_status: "Approved" }, { level_no: 2, level_name: "Finance duyệt", level_status: "In Progress" }],
    timeline: tl, attachments: [], capabilities: {}, display_fields: [], type_title: "X", detail_route: "/approvals/x?id=B-1" };
  w.frappe = { csrf_token: "t", call: (o) => { const m = o.method.split(".").pop();
    if (m === "get_request_detail") return Promise.resolve({ message: det });
    if (m === "list_requests") return Promise.resolve({ message: { total: 1, rows: [{ name: "AR", status: "Pending", current_level: 2, current_level_name: "Finance duyệt", requester_info: { name: "A" } }] } });
    if (m === "add_comment" && commentFail) return Promise.reject({ _server_messages: JSON.stringify([JSON.stringify({ message: "Traceback (most recent call last): KeyError 'x'" })]) });
    if (m === "list_comments") return Promise.resolve({ message: { comments: [] } });
    return Promise.resolve({ message: {} }); } };
  w.eval(BUNDLE);
  w.eval(js); await flush();
  const cell = [...w.document.querySelectorAll("#apl-body tbody td")].map((t) => t.textContent);
  ok(cell.includes("Cấp 2 · Finance duyệt"), "hub: cot Cap hien tai = 'Cap 2 · ...' (" + cell.join("|") + ")");
  w.ApprovalAll.openDetail("AR"); await flush();
  const li = [...w.document.querySelectorAll(".ec-apl-tl li")].map((x) => x.textContent);
  ok(/^Đã thêm tệp đính kèm/.test(li[0] || ""), "hub: lich su moi nhat len dau: " + li[0]);
  ok(/19\/11\/2026 08:09/.test(li[0] || ""), "hub: lich su co gio (action_time) " + li[0]);
  ok(li.length === 9 && /Còn 2 hoạt động cũ hơn/.test(li[8]), "hub: 8 dong + 'Con 2 hoat dong cu hon'");
  ok(!li.some((x) => /Reminded|Attachment Added|Submitted/.test(x)), "hub: khong chu tieng Anh tho");
  const bul = [...w.document.querySelectorAll(".ec-apl-step .bul")].map((x) => x.textContent);
  const lb = [...w.document.querySelectorAll(".ec-apl-step .lb")].map((x) => x.textContent);
  ok(bul.join("|") === "✓|✓|2|", "hub: cham = Da gui ✓, cap1 ✓, cap2 '2', Hoan tat trong: " + bul.join("|"));
  ok(lb[2] === "Cấp 2 · Finance duyệt", "hub: ten buoc cap 2: " + lb[2]);
  // trao doi loi: truoc day goi mapErr() KHONG TON TAI tren trang -> ReferenceError, nut Gui khoa vinh vien
  commentFail = true;
  const aside = w.document.querySelector(".ec-apl-aside");
  aside.querySelector("textarea").value = "xin chao";
  const send = aside.querySelector("[data-send]");
  send.click(); await flush();
  ok(!send.disabled, "hub: gui trao doi loi -> nut Gui bat lai");
  const toast = w.document.getElementById("ec-apl-toast");
  ok(toast && /Hệ thống gặp lỗi/.test(toast.textContent) && !/Traceback/.test(toast.textContent) && toast.className === "err", "hub: bao loi tieng Viet, khong Traceback");
}

// ---- 4. asset dung chung khac: tab "Tat ca" + nut "Them tep" ----------------------------------
{
  const AT_SRC = readFileSync(join(ROOT, "public", "js", "ec_alltab.bundle.js"), "utf8");
  const w = {}; new Function("window", AT_SRC)(w);
  const h = w.EcAllTab._dongHTML({ name: "EC-X-1", status: "Pending", current_level: 3, total_levels: 7, current_level_name: "Finance review" });
  ok(/Cấp 3\/7 · Finance review/.test(h), "tab Tat ca: 'Cap 3/7 · <ten cap>'");
  ok((AT_SRC.match(/EcApprovalUI\.errorText/g) || []).length === 2, "tab Tat ca: loi tai/xuat qua cau tieng Viet");
  ok(AT_SRC === readFileSync(join(ROOT, "public", "js", "ec_alltab.js"), "utf8"), "ban sao ec_alltab.js giong het");
}
{
  const ADDF = readFileSync(join(ROOT, "public", "js", "ec_addfile.bundle.js"), "utf8");
  const f = "contract_review";
  const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
  for (const [mode, re, nm] of [["tech", /Hệ thống gặp lỗi/, "loi ky thuat -> cau tieng Viet"],
                                ["deny", /Chỉ người đang xử lý/, "cau nghiep vu giu nguyen"]]) {
    const det = Object.assign(DET(), { capabilities: { can_approve: true, can_add_attachment: true, add_attachment_request: "AR" } });
    const { w } = boot(html, "approvals/contract-review", det, true);
    w.eval(ADDF);
    w.fetch = (url) => {
      const res = (status, body) => Promise.resolve({ status, ok: status < 400, json: () => Promise.resolve(body) });
      if (url === "/api/method/upload_file") return res(200, { message: { file_url: "/private/files/a.pdf" } });
      if (mode === "tech") return res(500, { exception: "AttributeError: 'NoneType' object has no attribute 'name'" });
      return res(403, { _server_messages: JSON.stringify([JSON.stringify({ message: "Chỉ người đang xử lý phiếu ở bước hiện tại mới thêm được tệp." })]) });
    };
    await flush();
    // trang da ve truoc khi nap ADDF -> ve lai khu nut bang du lieu that
    w.ContractReview && w.ContractReview.route && w.ContractReview.route(); await flush();
    const inp = w.document.querySelector("input[data-ec-addfile]");
    ok(!!inp, "them tep: co nut (" + mode + ")");
    if (!inp) continue;
    Object.defineProperty(inp, "files", { configurable: true, value: [new w.File(["x"], "a.pdf")] });
    inp.dispatchEvent(new w.Event("change", { bubbles: true })); await flush();
    w.document.querySelector("[data-ec-addfile-ok]").click(); await flush();
    const err = w.document.querySelector(".ec-addfile-err");
    ok(err && re.test(err.textContent) && !/NoneType/.test(err.textContent), "them tep: " + nm + " -> " + (err && err.textContent));
  }
}
console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
