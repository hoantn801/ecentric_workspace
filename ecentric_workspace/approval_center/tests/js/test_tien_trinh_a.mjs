// Copyright (c) 2026, eCentric and contributors
// Tien trinh phe duyet - phuong an A (24/11/2026, PO chot): EcApprovalUI.stepsHTML ve stepper ngang gon +
// bang "Viec cua ban" (det.viewer do server tinh). 3 tinh huong mockup, gom pha, mine, escape, ban hep,
// nut bang bam ho DUNG nut [data-act] cua trang, va 33 form that truyen det.
//     node ecentric_workspace/approval_center/tests/js/test_tien_trinh_a.mjs
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
const CSS = readFileSync(join(ROOT, "public", "css", "ec_approval_ui.bundle.css"), "utf8");
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 5)); };

function makeWin(body) {
  const dom = new JSDOM("<!DOCTYPE html><body>" + (body || "") + "</body>", { runScripts: "outside-only" });
  dom.window.eval(BUNDLE);
  return dom.window;
}
const W = makeWin();
const U = W.EcApprovalUI;
const J = [
  { label: "Chuẩn bị nhân sự mới", meta: "Tự tạo khi CEO duyệt: HR, HOF, Vận hành, Lương chuẩn bị", kind: "form" },
  { label: "Onboard", meta: "Ngày đi làm: chào mừng trên Teams + trang chủ", kind: "info" },
  { label: "Thử việc", meta: "Hồ sơ có ngày hết thử việc → khảo sát mốc", kind: "info" },
];
const JF = [{ label: "HR tuyển dụng", meta: "HR nhận việc, tìm ứng viên", kind: "fulfillment" }].concat(J);
// Buoc nhu buildStepper cua trang ve (Da gui -> cap duyet -> Hoan tat).
function pageSteps(states) {
  const st = [{ name: "Đã gửi", state: "done", meta: "" }];
  [["Line Manager", 1], ["CnB/HR", 2], ["CEO", 4]].forEach(([n, l], i) => st.push({ level: l, name: n, state: states[i], meta: states[i] === "done" ? "Duyệt bởi x · 24/11/2026 10:22" : "" }));
  st.push({ name: "Hoàn tất", state: states.every((s) => s === "done" || s === "skipped") ? "done" : "upcoming", meta: "" });
  return st;
}
const parse = (html) => new JSDOM("<body>" + html + "</body>").window.document;
const DET1 = () => ({
  approval: { approval_status: "Pending", current_level: 2 },
  levels: [{ level_no: 1, mine: false }, { level_no: 2, mine: true }, { level_no: 4, mine: false }],
  capabilities: { can_approve: true, can_request_information: true, can_reject: true },
  viewer: { kind: "approve", role: "approver", level_no: 2, level_name: "CnB/HR", waiting_since: "2026-11-23 16:40:00",
    waiting_seconds: 17 * 3600, next_level_no: 4, next_level_name: "CEO", waiting_on: [] },
});

// ---- 1. Cho ban duyet Cap 2 ----
{
  const det = DET1();
  const html = U.stepsHTML(U.withJourney(pageSteps(["skipped", "current", "upcoming"]), J), { detail: det });
  const d = parse(html);
  const you = d.querySelector(".ec-aps-you");
  ok(you && !you.classList.contains("ec-aps-you--watch"), "TH1: co bang Viec cua ban (khong phai bang xam)");
  ok(/Duyệt Cấp 2 · CnB\/HR/.test(you.querySelector(".ec-aps-you-title").textContent), "TH1: tieu de bang");
  const sub = you.querySelector(".ec-aps-you-sub").textContent;
  ok(/Phiếu chờ bạn 17 giờ \(từ 23\/11 16:40\)/.test(sub) && /Sau bạn: Cấp 4 · CEO/.test(sub), "TH1: cho bao lau + cap sau: " + sub);
  const btns = [...you.querySelectorAll("[data-ec-aps-act]")].map((b) => b.getAttribute("data-ec-aps-act") + ":" + b.textContent);
  ok(btns.join("|") === "reqinfo:Trả lại|approve:Duyệt", "TH1: nut Tra lai + Duyet: " + btns.join("|"));
  const items = [...d.querySelectorAll(".ec-aps-track > .ec-aps-item")];
  ok(items.length <= 6, "TH1: toi da 6 cot (" + items.length + ")");
  const l2 = items.find((x) => /CnB\/HR/.test(x.textContent));
  ok(l2 && l2.classList.contains("ec-aps-item--mine") && l2.querySelector(".ec-aps-node--mine") && l2.querySelector(".ec-aps-me"), "TH1: cap 2 la cua ban (nut navy + nhan Ban)");
  ok(l2 && /chờ 17 giờ/.test(l2.querySelector(".ec-aps-meta").textContent), "TH1: cap dang cho hien thoi gian cho");
  ok(l2 && l2.querySelector(".ec-aps-lbl").textContent === "Chờ bạn duyệt", "TH1: nhan 'Cho ban duyet'");
  ok(/Chưa tới/.test(items.find((x) => /CEO/.test(x.textContent)).textContent), "TH1: cap sau 'Chua toi'");
  ok(d.querySelectorAll(".ec-aps-item--mine").length === 1, "TH1: chi 1 buoc la cua ban");
  const g = items[items.length - 1];
  ok(g.classList.contains("ec-aps-item--group") && /Sau duyệt · 3 bước/.test(g.textContent), "TH1: pha sau duyet gom 1 nut: " + g.textContent);
  ok(d.querySelector(".ec-aps-panel").hidden === true && g.querySelector("[aria-expanded=false]"), "TH1: nhom dong san trong markup");
  ok(items.every((it) => it.querySelectorAll(".ec-aps-text > div, .ec-aps-text > button").length === 3), "TH1: moi cot dung 3 dong");
  const sk = items.find((x) => x.classList.contains("ec-aps-item--skipped"));
  ok(sk && !/minmax\(92px/.test(html) && /grid-template-columns:minmax\(0,1fr\)/.test(html), "TH1: cot bang nhau (can giua 24/11)");
  ok(/Bước 3\/8 · Phê duyệt/.test(d.querySelector(".ec-aps-now-k").textContent), "TH1 ban hep: Buoc 3/8 · Phe duyet");
  ok(d.querySelectorAll(".ec-aps-vrow").length === 8 && d.querySelectorAll(".ec-aps-seg:not(.ec-aps-seg--gap)").length === 8, "TH1 ban hep: du 8 dong + 8 doan");
  ok(d.querySelectorAll(".ec-aps-vrow .ec-aps-desc").length === 3, "TH1 ban hep: mo ta hien trong danh sach (mobile khong hover)");
  ok(d.querySelector(".ec-aps-more") && !d.querySelector(".ec-aps-more").open, "TH1 ban hep: danh sach gap san");
  ok(d.querySelector(".ec-aps-seg--mine"), "TH1 ban hep: doan cua ban mau navy");
  // Duyet & Ky khi cap yeu cau ky so
  const det2 = DET1(); det2.capabilities.requires_signature = true;
  ok(/Duyệt &amp; Ký/.test(U.stepsHTML(pageSteps(["skipped", "current", "upcoming"]), { detail: det2 })), "TH1: cap ky so -> Duyet & Ky");
  // khong co quyen bo sung -> chi Duyet
  const det3 = DET1(); det3.capabilities.can_request_information = false;
  ok(!/data-ec-aps-act="reqinfo"/.test(U.stepsHTML(pageSteps(["skipped", "current", "upcoming"]), { detail: det3 })), "TH1: khong quyen -> khong nut Tra lai");
}

// ---- 2. Da duyet, cho ban xu ly (buoc sau duyet) ----
{
  const det = { approval: { approval_status: "Approved", current_level: 4 }, levels: [], capabilities: { can_complete: true },
    viewer: { kind: "fulfill", role: "fulfiller", step_label: "HR tuyển dụng", due_at: "2026-11-28", waiting_seconds: 7200,
      waiting_since: "2026-11-24 14:05:00", claimable: false } };
  const steps = U.withJourney(pageSteps(["done", "done", "done"]), JF);
  const html = U.stepsHTML(steps, { detail: det });
  const d = parse(html);
  const you = d.querySelector(".ec-aps-you");
  ok(you && /HR tuyển dụng/.test(you.textContent) && /Hạn 28\/11\/2026/.test(you.textContent), "TH2: bang viec sau duyet + han");
  const b = you.querySelector("[data-ec-aps-act]");
  ok(b && b.getAttribute("data-ec-aps-act") === "open" && b.textContent === "Mở việc của tôi", "TH2: nut Mo viec cua toi");
  const items = [...d.querySelectorAll(".ec-aps-track > .ec-aps-item")];
  ok(items[0].classList.contains("ec-aps-item--group") && /Phê duyệt/.test(items[0].textContent) && /Đã duyệt 3\/3 cấp/.test(items[0].textContent), "TH2: pha duyet da xong gom 1 nut: " + items[0].textContent);
  const mine = d.querySelector(".ec-aps-track .ec-aps-item--mine");
  ok(mine && /HR tuyển dụng/.test(mine.textContent) && /chờ 2 giờ/.test(mine.textContent), "TH2: buoc xu ly la cua ban + cho 2 gio");
  ok(mine && /Chờ bạn xử lý/.test(mine.textContent), "TH2: nhan 'Cho ban xu ly'");
  ok(items.length <= 6, "TH2: <= 6 cot");
  ok(d.querySelector(".ec-aps-tip-pop") && /HR nhận việc/.test(d.querySelector(".ec-aps-tip-pop").textContent), "TH2: mo ta vao tooltip");
  ok(/Sau khi duyệt/.test(d.querySelector(".ec-aps-now-k").textContent), "TH2 ban hep: dang o pha sau duyet");
  // nhan viec: tieu de bao "Nhan viec"
  det.viewer.claimable = true;
  ok(/Nhận việc: HR tuyển dụng/.test(U.stepsHTML(steps, { detail: det })), "TH2: chua ai nhan -> Nhan viec");
}

// ---- 3. Chi theo doi ----
{
  const det = { approval: { approval_status: "Pending", current_level: 4 }, levels: [{ level_no: 4, mine: false }], capabilities: { can_remind: true },
    viewer: { kind: "watch", role: "requester", level_no: 4, level_name: "CEO", waiting_seconds: 4 * 3600, waiting_on: ["Nguyễn Quốc Bảo"] } };
  const d = parse(U.stepsHTML(U.withJourney(pageSteps(["skipped", "done", "current"]), J), { detail: det }));
  const you = d.querySelector(".ec-aps-you");
  ok(you && you.classList.contains("ec-aps-you--watch"), "TH3: bang xam");
  ok(you && !you.querySelector("button"), "TH3: khong co nut");
  ok(/Đang chờ Nguyễn Quốc Bảo \(Cấp 4 · CEO\) duyệt · 4 giờ/.test(you.textContent), "TH3: dang cho ai: " + (you && you.textContent));
  ok(/người gửi phiếu, không có việc cần làm/.test(you.textContent), "TH3: vai nguoi gui");
  ok(!d.querySelector(".ec-aps-item--mine"), "TH3: khong buoc nao la cua ban");
  ok(d.querySelector(".ec-aps-node--current .ec-aps-num").textContent === "4", "TH3: cap dang cho hien dung so cap");
}

// ---- 4. Khong lien quan / khong co detail -> khong ve bang ----
{
  const s = pageSteps(["skipped", "current", "upcoming"]);
  ok(!/ec-aps-you/.test(U.stepsHTML(s)), "khong detail (xem truoc luc tao) -> khong bang");
  ok(!/ec-aps-you/.test(U.stepsHTML(s, { detail: { viewer: { kind: "" } } })), "kind rong -> khong bang");
  ok(!/ec-aps-you/.test(U.stepsHTML(s, { detail: { viewer: null } })), "viewer null (man sua) -> khong bang");
  // Server khong danh dau -> client KHONG tu suy ra mine (khong doan theo ten nguoi).
  ok(!/ec-aps-item--mine/.test(U.stepsHTML(s, { detail: { levels: [{ level_no: 2 }], viewer: { kind: "watch", role: "approver" } } })), "khong co levels.mine -> khong mine");
  // mine chi khi dang cho: cap da duyet co mine (du lieu cu) cung khong to navy
  ok(!/ec-aps-item--mine/.test(U.stepsHTML(pageSteps(["done", "done", "current"]), { detail: { levels: [{ level_no: 2, mine: true }] } })), "mine chi ap cho buoc dang cho");
}

// ---- 5. Gom: qua nhieu cap -> <= 6 cot ----
{
  const st = [{ name: "Đã gửi", state: "done" }];
  for (let i = 1; i <= 8; i++) st.push({ level: i, name: "L" + i, state: i <= 4 ? "done" : (i === 5 ? "current" : "upcoming") });
  st.push({ name: "Hoàn tất", state: "upcoming" });
  const d = parse(U.stepsHTML(st));
  const items = [...d.querySelectorAll(".ec-aps-track > .ec-aps-item")];
  ok(items.length === 6, "8 cap -> 6 cot: " + items.length);
  ok(/Đã xong · 5 bước/.test(items[0].textContent), "gom dau da xong: " + items[0].textContent);
  ok(/L8/.test(items[4].textContent) && /Hoàn tất/.test(items[5].textContent), "sau khi gom dau con dung 6 cot");
  const st10 = [{ name: "Đã gửi", state: "done" }];
  for (let i = 1; i <= 10; i++) st10.push({ level: i, name: "L" + i, state: i === 1 ? "current" : "upcoming" });
  st10.push({ name: "Hoàn tất", state: "upcoming" });
  const d10 = parse(U.stepsHTML(st10));
  const it10 = [...d10.querySelectorAll(".ec-aps-track > .ec-aps-item")];
  ok(it10.length === 6 && /Còn 7 bước/.test(it10[5].textContent), "10 cap chua duyet -> gom duoi 'Con 7 buoc': " + it10.length + " " + it10[5].textContent);
  ok(d.querySelector(".ec-aps-item--current .ec-aps-num").textContent === "5", "cap dang cho van hien rieng");
  const total = [...d.querySelectorAll(".ec-aps-panel")].reduce((n, p) => n + p.querySelectorAll(".ec-aps-mini").length, 0);
  ok(total + items.filter((x) => !x.classList.contains("ec-aps-item--group")).length === st.length, "khong mat buoc nao khi gom");
  // tu choi: khong co buoc sau duyet, khong gom
  const rj = U.withJourney(pageSteps(["done", "rejected", "upcoming"]), J);
  const dr = parse(U.stepsHTML(rj));
  ok(!dr.querySelector(".ec-aps-item--group") && dr.querySelector(".ec-aps-node--rejected"), "tu choi: khong gom, nut do");
  ok(/is-cancelled/.test(U.stepsHTML([], { cancelled: true })), "phieu huy giu class is-cancelled");
}

// ---- 6. Escape moi chuoi nguoi dung ----
{
  const EVIL = '<img src=x onerror=alert(1)>';
  const st = [{ name: EVIL, state: "done", meta: "" }, { level: 1, name: EVIL, state: "current", statusLabel: EVIL, meta: "&lt;ok&gt;" },
    { name: EVIL, state: "upcoming", after: true, desc: EVIL, meta: "" }];
  const det = { approval: { approval_status: "Pending" }, levels: [{ level_no: 1, mine: true }], capabilities: { can_approve: true },
    viewer: { kind: "approve", level_no: 1, level_name: EVIL, next_level_no: 2, next_level_name: EVIL, waiting_on: [EVIL], step_label: EVIL } };
  const outs = [U.stepsHTML(st, { detail: det })];
  det.viewer.kind = "watch"; outs.push(U.stepsHTML(st, { detail: det }));
  det.viewer.kind = "fulfill"; outs.push(U.stepsHTML(st, { detail: det }));
  const st2 = [{ name: "a", state: "done" }].concat([1, 2, 3, 4, 5, 6, 7].map((i) => ({ level: i, name: EVIL, state: "done", meta: "" }))).concat([{ name: EVIL, state: "upcoming", after: true, desc: EVIL }]);
  outs.push(U.stepsHTML(st2));
  outs.forEach((h, i) => ok(!/<img/.test(h) && /&lt;img/.test(h), "escape #" + i));
  ok(/&lt;ok&gt;/.test(outs[0]), "meta cua trang chen nguyen van (trang tu esc)");
}

// ---- 7. Nut bang bam ho dung nut cua trang ----
{
  const det = DET1();
  const stepper = U.stepsHTML(U.withJourney(pageSteps(["skipped", "current", "upcoming"]), J), { detail: det });
  const w = makeWin('<div id="ec-x-root"><div class="stepper">' + stepper + '</div><div class="actions"><button data-act="approve">Duyệt</button><button data-act="reqinfo">Yêu cầu bổ sung</button></div></div>'
    + '<div id="ec-y-root"><button data-act="approve" id="other">khac trang</button></div>');
  const doc = w.document, hits = [];
  doc.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => hits.push(b.id || b.getAttribute("data-act"))));
  doc.querySelector('[data-ec-aps-act="approve"]').click();
  ok(hits.join(",") === "approve", "Duyet tren bang -> bam DUNG 1 lan nut Duyet cua trang (cung root): " + hits.join(","));
  doc.querySelector('[data-ec-aps-act="reqinfo"]').click();
  ok(hits.join(",") === "approve,reqinfo", "Tra lai -> nut Yeu cau bo sung cua trang");
  // Duyet & Ky uu tien
  const w2 = makeWin('<div id="ec-p-root">' + stepper + '<button data-act="approvesign">Duyệt &amp; Ký</button><button data-act="approve">Duyệt</button></div>');
  const h2 = []; w2.document.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => h2.push(b.getAttribute("data-act"))));
  w2.document.querySelector('[data-ec-aps-act="approve"]').click();
  ok(h2.join(",") === "approvesign", "co Duyet & Ky -> bam Duyet & Ky");
  // nut bi khoa (dang xu ly) -> khong bam, bao chu
  const w3 = makeWin('<div id="ec-q-root">' + stepper + '<button data-act="approve" disabled>Duyệt</button></div>');
  w3.document.querySelector('[data-ec-aps-act="approve"]').click();
  const note = w3.document.querySelector(".ec-aps-you-note");
  ok(!note.hidden && /Không tìm thấy nút/.test(note.textContent), "khong co nut trang -> bao, khong goi gi");
  // Mo viec cua toi: cuon + focus nut Hoan tat, KHONG bam ho
  const detF = { approval: { approval_status: "Approved" }, capabilities: {}, viewer: { kind: "fulfill", step_label: "HR tuyển dụng" } };
  const w4 = makeWin('<div id="ec-f-root">' + U.stepsHTML(U.withJourney(pageSteps(["done", "done", "done"]), JF), { detail: detF }) + '<button data-act="complete" id="cmp">Hoàn tất xử lý</button></div>');
  let clicked = 0, scrolled = 0; const cmp = w4.document.getElementById("cmp");
  cmp.addEventListener("click", () => clicked++); cmp.scrollIntoView = () => { scrolled++; };
  w4.document.querySelector('[data-ec-aps-act="open"]').click();
  ok(clicked === 0 && scrolled === 1 && w4.document.activeElement === cmp, "Mo viec cua toi -> cuon + focus, khong bam ho");
  // nhom: bam mo / dong
  const g = doc.querySelector(".ec-aps-node--group"), panel = doc.getElementById(g.getAttribute("aria-controls"));
  g.click();
  ok(!panel.hidden && g.getAttribute("aria-expanded") === "true" && doc.querySelector(".ec-aps-gbtn").getAttribute("aria-expanded") === "true", "bam nhom -> mo panel + aria-expanded");
  doc.querySelector(".ec-aps-gbtn").click();
  ok(panel.hidden && g.getAttribute("aria-expanded") === "false", "bam lan nua -> dong");
}

// ---- 8. CSS: ban hep do CSS chon, mau dung bo nhan dien ----
{
  ok(/@container ec-aps \(max-width: 600px\)[^@]*\.ec-aps-track[^}]*display: none[^@]*\.ec-aps-compact \{ display: block; \}/.test(CSS), "<=600px: an stepper ngang, hien ban hep");
  ok(/\.ec-aps \{ container-type: inline-size/.test(CSS), "container query theo be ngang khung (khong theo man hinh)");
  ok(/--ec-aps-navy: #2f3a8f/.test(CSS) && /--ec-aps-green: #16a34a/.test(CSS), "mau navy / xanh la dung");
  const rules = CSS.slice(CSS.indexOf("}") + 1);
  ok(!/#[0-9a-fA-F]{3,8}\b/.test(rules), "mau chi khai o :root (bien), khong rai trong rule");
  ok(!/!important/.test(CSS), "khong !important");
}

// ---- 9. 33 form that: truyen det, man sua khong ve bang, nut bang bam ho nut that cua trang ----
const DETP = () => ({ business: { name: "R-1", requested_by: "req@x", request_title: "T", approval_request: "AR", creation: "2026-11-01 08:00:00" },
  approval: { name: "AR", approval_status: "Pending", current_level: 2 }, request: { name: "AR", approval_status: "Pending", current_level: 2 },
  levels: [{ level_no: 1, level_name: "Department Manager Review", level_status: "Approved", mine: false },
    { level_no: 2, level_name: "Finance Review", level_status: "In Progress", mine: true, activated_at: "2026-11-24 08:00:00" }],
  approvers: [{ level_no: 1, approver: "lead@x", status: "Approved" }, { level_no: 2, approver: "fin@x", status: "Pending" }],
  attachments: [], timeline: [], extra: {}, items: [], fulfillment: {},
  capabilities: { can_approve: true, can_request_information: true, can_reject: true },
  viewer: { kind: "approve", role: "approver", level_no: 2, level_name: "Finance Review", waiting_seconds: 3600, next_level_no: null, waiting_on: [] } });
function boot(html, route, det) {
  const i = html.search(/<script[^>]*id="ec-[^"]+"[^>]*>/);
  const markup = html.slice(0, i);
  const js = html.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/" + route + "?id=R-1" });
  const w = dom.window;
  w.frappe = { csrf_token: "x", session: { user: "fin@x" }, call: (o) => { const m = o.method.split(".").pop();
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true, all: true }, context: { user: "fin@x" }, form_options: {}, options: {} } });
    if (m === "get_detail" || m === "get_request_detail") return Promise.resolve({ message: det });
    return Promise.resolve({ message: { rows: [], total: 0, data: [] } }); } };
  w.eval(BUNDLE); w.eval(REMIND);
  try { w.eval(js); } catch (e) { return { w, err: e }; }
  return { w };
}
const NO_STEPPER = new Set(["clearance_request", "new_staff_preparation"]);
const feats = readdirSync(FEAT).filter((f) => existsSync(join(FEAT, f, "ui", "main_section.html")) && f !== "brand_weight");
ok(feats.length >= 33, "du 33 form: " + feats.length);
let banners = 0;
for (const f of feats) {
  const html = readFileSync(join(FEAT, f, "ui", "main_section.html"), "utf8");
  ok(/EcApprovalUI\.withJourney\(steps,\(state\.boot\|\|\{\}\)\.journey_after\):steps\),\{[^;]*detail:det[,}]/.test(html), f + ": truyen {detail:det} cho asset");
  if (/_editDet/.test(html) && /buildStepper\(state\._editDet/.test(html)) ok(false, f + ": man sua phai truyen viewer:null");
  const route = (readFileSync(join(FEAT, f, "infrastructure", "page_sync.py"), "utf8").match(/ROUTE = "([^"]+)"/) || [])[1];
  const { w, err } = boot(html, route, DETP()); await flush();
  ok(!err, f + ": trang chay duoc " + (err || ""));
  if (NO_STEPPER.has(f)) continue;
  const doc = w.document;
  const you = doc.querySelector(".ec-aps-you");
  if (f === "employee_review") {
    // luong rieng tung cap -> bang chi "Mo viec cua toi" dua toi khoi Hanh dong (khong Duyet / Tra lai chung)
    ok(you && /Đến lượt bạn: Cấp 2 · Finance Review/.test(you.textContent) && !you.querySelector('[data-ec-aps-act="approve"]'), f + ": bang kieu mo viec");
    const pb = you && you.querySelector('[data-ec-aps-act="panel"]');
    const tgt = [...doc.querySelectorAll(".actions [data-act]")].filter((b) => !b.closest(".ec-aps"))[0];
    if (pb && tgt) { tgt.scrollIntoView = () => {}; pb.click(); }
    ok(pb && tgt && doc.activeElement === tgt, f + ": Mo viec cua toi -> focus nut dau tien cua khoi Hanh dong");
    banners++;
    continue;
  }
  ok(you && /Duyệt Cấp 2 · Finance Review/.test(you.textContent), f + ": bang Viec cua ban hien tren trang chi tiet");
  const real = [...doc.querySelectorAll('[data-act="approvesign"],[data-act="approve"]')].filter((b) => !b.closest(".ec-aps"))[0];
  ok(real, f + ": trang co nut Duyet that");
  if (!you || !real) continue;
  banners++;
  let hit = 0; real.addEventListener("click", (e) => { hit++; e.stopImmediatePropagation(); e.preventDefault(); }, true);
  you.querySelector('[data-ec-aps-act="approve"]').click();
  ok(hit === 1, f + ": bam Duyet tren bang -> nut Duyet that cua trang nhan dung 1 click (" + hit + ")");
}
ok(banners >= 31, "bang hien tren >= 31 form: " + banners);

// ---- Phieu DA HUY / TU CHOI (25/11, Hoan): khong con "Cho duyet" o cap dang do, khong bang ----
{
  const det = DET1(); det.approval.approval_status = "Cancelled";
  const html = U.stepsHTML(pageSteps(["done", "current", "upcoming"]), { detail: det });
  const d = parse(html);
  ok(!/Chờ duyệt|Chờ bạn duyệt/.test(d.body.textContent), "HUY: khong con chu Cho duyet");
  ok(/Đã hủy/.test(d.body.textContent), "HUY: cap dang do ghi Da huy");
  ok(!d.querySelector(".ec-aps-you"), "HUY: khong ve bang Viec cua ban");
  ok(d.querySelector(".ec-aps.is-cancelled"), "HUY: class is-cancelled");
  const det2 = DET1(); det2.approval.approval_status = "Rejected";
  const t2 = parse(U.stepsHTML(pageSteps(["done", "current", "upcoming"]), { detail: det2 })).body.textContent;
  ok(/Từ chối/.test(t2) && !/Chờ duyệt/.test(t2), "TU CHOI: cap dang do -> Tu choi");
  const t3 = parse(U.stepsHTML(pageSteps(["done", "rejected", "upcoming"]), { detail: det2 })).body.textContent;
  ok((t3.match(/Từ chối/g) || []).length >= 1 && !/Chờ duyệt/.test(t3), "TU CHOI: trang da ve rejected thi giu");
  const t4 = parse(U.stepsHTML(pageSteps(["done", "current", "upcoming"]), { detail: DET1() })).body.textContent;
  ok(/Chờ bạn duyệt/.test(t4), "PENDING: van nhu cu");
}
console.log("JS: " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
