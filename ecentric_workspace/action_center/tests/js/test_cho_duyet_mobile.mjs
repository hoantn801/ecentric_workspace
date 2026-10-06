// "Cho toi duyet" tren /viec-cua-toi (06/10/2026): the theo loai, bang truot, duyet / tu choi /
// bo sung, phieu can nhap them chi mo trang chi tiet, duyet hang loat chi loai duyet nhanh duoc,
// loi server hien nguyen van (403 khong bao "dang nhap lai").
//     node ecentric_workspace/action_center/tests/js/test_cho_duyet_mobile.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
const HTML = readFileSync(join(APP, "action_center", "pages", "my_work", "main_section.html"), "utf8");
const BUNDLE = readFileSync(join(APP, "public", "js", "ec_cho_duyet.bundle.js"), "utf8");
const CSS = readFileSync(join(APP, "public", "css", "ec_cho_duyet.bundle.css"), "utf8");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 3)); };

const ROWS = () => ([
  { request: "R1", approval_type: "LEAVE", type_label: "Nghỉ phép", title: "Nghỉ phép 2 ngày", requester_name: "Anh A", requested_by: "a@x",
    submitted_at: "2026-10-05 09:00:00", due_at: "2026-10-07 18:00:00", level_name: "Manager", detail_url: "/approvals/leave?id=LV-1",
    summary: [{ label: "Loại nghỉ", value: "Annual" }, { label: "Số ngày", value: "2" }],
    capabilities: { can_approve: true, can_reject: true, can_request_info: true, needs_input: false, needs_input_reason: "", comment_required: false } },
  { request: "R2", approval_type: "LEAVE", type_label: "Nghỉ phép", title: "Nghỉ ốm", requester_name: "Chị B", requested_by: "b@x",
    submitted_at: "2026-10-05 10:00:00", due_at: null, level_name: "Manager", detail_url: "/approvals/leave?id=LV-2", summary: [],
    capabilities: { can_approve: true, can_reject: true, can_request_info: true, needs_input: false, needs_input_reason: "", comment_required: false } },
  { request: "R3", approval_type: "PAY", type_label: "Thanh toán", title: "Thanh toán NCC", requester_name: "Anh A", requested_by: "a@x",
    submitted_at: "2026-10-04 09:00:00", due_at: null, level_name: "CEO", detail_url: "/approvals/payment-request?id=PAY-1",
    summary: [{ label: "Số tiền", value: "12.500.000" }],
    capabilities: { can_approve: true, can_reject: true, can_request_info: true, needs_input: true, needs_input_reason: "Cần ký số - mở trang chi tiết để duyệt & ký.", comment_required: false } },
  { request: "R4", approval_type: "PROM", type_label: "Thăng chức", title: "Promotion X", requester_name: "Anh C", requested_by: "c@x",
    submitted_at: "2026-10-03 09:00:00", due_at: null, level_name: "CnB", detail_url: "/approvals/promotion?id=P-1", summary: [],
    capabilities: { can_approve: true, can_reject: true, can_request_info: true, needs_input: false, needs_input_reason: "", comment_required: true } },
]);

function boot(opts = {}) {
  const i = HTML.indexOf('<div class="ecw"');
  const s = HTML.search(/<script id="ec-mywork-js">/);
  const markup = HTML.slice(i, s);
  const rest = HTML.slice(s).replace(/^<script[^>]*>/, "");
  const js = rest.slice(0, rest.indexOf("</script>"));
  const dom = new JSDOM("<!DOCTYPE html><html><head><meta name=viewport content='width=390'></head><body>" + markup + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/viec-cua-toi", pretendToBeVisual: true });
  const w = dom.window; w.innerWidth = 390;
  const calls = []; let rows = ROWS();
  w.frappe = { csrf_token: "tok" };
  w.confirm = () => true;
  w.fetch = (url, init) => {
    const m = String(url).split("?")[0].split(".").pop();
    const body = init && init.body ? JSON.parse(init.body) : null;
    calls.push([m, body, init && init.headers]);
    const res = (status, obj) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(obj) });
    if (m === "list_my_pending") return res(200, { message: { rows, count: rows.length } });
    if (m === "quick_decide") {
      if (opts.fail) return res(opts.fail.status, { exc_type: "QuickDecideError", _server_messages: JSON.stringify([JSON.stringify({ message: opts.fail.msg })]) });
      rows = rows.filter((r) => r.request !== body.request_name);
      return res(200, { message: { ok: true, remaining: rows.length } });
    }
    if (m === "get_action_items") return res(200, { message: { items: [], counts: {}, total: 0, next_cursor: null } });
    return res(200, { message: { items: [], unread: 0 } });
  };
  w.eval(js);
  w.eval(BUNDLE);
  return { w, calls };
}
const $ = (w, q) => w.document.querySelector(q);
const $$ = (w, q) => [...w.document.querySelectorAll(q)];

// 0) markup: khung + "dang tai" co san truoc khi JS chay (khong che roi hien)
ok(/data-ec-cho-duyet/.test(HTML) && /cd-loading/.test(HTML), "khung Cho toi duyet nam san trong markup");
ok(!/<script id="ec-(?!mywork-js)/.test(HTML), "khong them khoi <script id=ec-...> moi");
ok(/\.cd-btn\{[^}]*min-height:44px/.test(CSS) && /\.cd-x\{[^}]*height:44px/.test(CSS), "nut cao >= 44px cho ngon tay");
ok(/\.cd,\.cd-ov,\.cd-toast\{/.test(CSS), "bien mau khai cho ca bang truot gan vao body");
ok(/font-size:16px/.test(CSS.match(/\.cd-sheet textarea\{[^}]*\}/)[0]), "o nhap 16px (iOS khong tu phong to)");

{ // 1) danh sach nhom theo loai
  const { w } = boot(); await flush();
  const gh = $$(w, ".cd-gh").map((x) => x.textContent);
  ok(gh.length === 3 && /Nghỉ phép 2/.test(gh[0]), "nhom theo loai phieu: " + gh.join(" | "));
  ok($(w, "[data-cd-count]").textContent === "4", "so dem = so phieu cho");
  const r3 = $(w, '[data-cd-open="R3"]');
  ok(!r3.querySelector("[data-cd-quick]") && r3.querySelector('a[href="/approvals/payment-request?id=PAY-1"]'), "phieu can ky so: chi co link mo trang chi tiet");
  ok(!r3.querySelector("[data-cd-pick]") && !$(w, '[data-cd-open="R4"] [data-cd-pick]'), "khong cho chon hang loat: can nhap them / bat buoc nhan xet");
}

{ // 2) duyet trong bang truot -> goi quick_decide approve, the bien mat, trang tai lai lan Viec
  const { w, calls } = boot(); await flush();
  $(w, '[data-cd-open="R1"] .cd-title').click(); await flush();
  ok(!!$(w, ".cd-sheet") && /Annual/.test($(w, ".cd-sheet").textContent), "bam the mo bang truot co tom tat");
  $(w, '.cd-sheet [data-cd-do="approve"]').click(); await flush();
  const q = calls.find((c) => c[0] === "quick_decide");
  ok(q && q[1].request_name === "R1" && q[1].action === "approve" && q[2]["X-Frappe-CSRF-Token"] === "tok", "duyet -> quick_decide(R1, approve) kem CSRF");
  ok(!$(w, '[data-cd-open="R1"]') && !$(w, ".cd-ov"), "duyet xong: dong bang, the bien mat");
  ok(calls.some((c) => c[0] === "get_action_items"), "phat su kien -> trang tai lai lan Viec (dong bo badge)");
}

{ // 3) tu choi bat buoc ly do
  const { w, calls } = boot(); await flush();
  $(w, '[data-cd-open="R2"] .cd-title').click(); await flush();
  $(w, '.cd-sheet [data-cd-do="reject"]').click(); await flush();
  ok(!calls.some((c) => c[0] === "quick_decide") && /lý do/.test($(w, "[data-cd-msg]").textContent), "tu choi khong ly do -> chan, khong goi server");
  $(w, "#cd-cmt").value = "Trung lich"; $(w, '.cd-sheet [data-cd-do="reject"]').click(); await flush();
  const q = calls.find((c) => c[0] === "quick_decide");
  ok(q && q[1].action === "reject" && q[1].comment === "Trung lich", "tu choi co ly do -> quick_decide reject");
}

{ // 4) yeu cau bo sung + bat buoc nhan xet khi duyet
  const { w, calls } = boot(); await flush();
  $(w, '[data-cd-open="R4"] .cd-title').click(); await flush();
  $(w, '.cd-sheet [data-cd-do="approve"]').click(); await flush();
  ok(!calls.some((c) => c[0] === "quick_decide") && /nhận xét/.test($(w, "[data-cd-msg]").textContent), "loai bat buoc nhan xet: duyet trong -> chan");
  $(w, "#cd-cmt").value = "Can them KPI"; $(w, '.cd-sheet [data-cd-do="request_information"]').click(); await flush();
  ok(calls.some((c) => c[0] === "quick_decide" && c[1].action === "request_information"), "yeu cau bo sung -> quick_decide request_information");
}

{ // 5) phieu can nhap them: bang truot chi co nut mo trang chi tiet
  const { w } = boot(); await flush();
  $(w, '[data-cd-open="R3"] .cd-title').click(); await flush();
  ok(!$(w, ".cd-sheet [data-cd-do]") && $(w, '.cd-sheet a[href="/approvals/payment-request?id=PAY-1"]'), "needs_input: khong co nut quyet dinh, chi mo trang chi tiet");
}

{ // 6) duyet hang loat: chi R1 + R2
  const { w, calls } = boot(); await flush();
  $(w, "[data-cd-pickall]").click(); await flush();
  $(w, "[data-cd-bulk]").click(); await flush(); await flush();
  const sent = calls.filter((c) => c[0] === "quick_decide").map((c) => c[1].request_name).sort();
  ok(JSON.stringify(sent) === '["R1","R2"]', "hang loat chi gui phieu duyet nhanh duoc: " + sent);
}

{ // 7) loi server: hien nguyen van; 403 khong bao dang nhap lai
  const { w } = boot({ fail: { status: 417, msg: "Bạn không còn là người duyệt của bước hiện tại" } }); await flush();
  $(w, '[data-cd-open="R1"] .cd-title').click(); await flush();
  $(w, '.cd-sheet [data-cd-do="approve"]').click(); await flush();
  ok(/không còn là người duyệt/.test($(w, "[data-cd-msg]").textContent) && !!$(w, ".cd-sheet"), "loi 417 hien nguyen van, giu bang");
  const b = boot({ fail: { status: 403, msg: "not allowed" } }); await flush();
  $(b.w, '[data-cd-open="R1"] .cd-title').click(); await flush();
  $(b.w, '.cd-sheet [data-cd-do="approve"]').click(); await flush();
  const t = $(b.w, "[data-cd-msg]").textContent;
  ok(/Không đủ quyền/.test(t) && !/đăng nhập/i.test(t), "403 -> 'Khong du quyen', khong bao dang nhap lai: " + t);
}
console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
