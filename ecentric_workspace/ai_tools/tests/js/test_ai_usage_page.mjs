// Copyright (c) 2026, eCentric and contributors
// /ai-usage (03/11 UX): khoi "Tra loi nhanh", danh sach nguoi gon, tim kiem khong ve lai ca trang,
// sap xep bang ban phim, trang thai rong / loi co huong di tiep. Hop dong backend giu nguyen
// (usage_api.summary: days | from_date, department).
//     node ecentric_workspace/ai_tools/tests/js/test_ai_usage_page.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const HTML = readFileSync(join(here, "..", "..", "pages", "ai_usage", "main_section.html"), "utf8");
const i = HTML.lastIndexOf("<script>");
const markup = HTML.slice(0, i), JS = HTML.slice(i + 8).replace(/<\/script>\s*$/, "");
let oks = 0, fails = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  HONG: " + n); } };
const flush = async () => { for (let k = 0; k < 8; k++) await new Promise((r) => setTimeout(r, 3)); };

function feat(purpose, label, calls, ok_rate, extra) {
  return Object.assign({ purpose, label, calls, users: 3, system_calls: 0, ok_rate, error_calls: Math.round(calls * (100 - ok_rate) / 100),
    p50_ms: 4000, p90_ms: 9000, credits: 10, usd: 0.05 }, extra || {});
}
function data(kind, over) {
  const people = Array.from({ length: 12 }, (_, k) => ({ user: "u" + k + "@x", name: "Nguoi " + String.fromCharCode(65 + k), department: k % 2 ? "Ops" : "Acc",
    calls: 30 - k, days: 5, ok_rate: 100, credits: 1, usd: 0.01, last: "2026-11-02 10:00", features: [{ purpose: "khay", label: "eC Mate", calls: 3 }] }));
  return Object.assign({
    scope: { kind, departments: kind === "dept" ? ["Acc", "Ops"] : [] }, department: "", period: { from: "2026-10-04", to: "2026-11-02" },
    totals: { calls: 300, user_calls: 250, system_calls: 50, active_users: 12, headcount: 20, adoption_pct: 60, ok_rate: 93, credits: 100, usd: 0.5, cost_unpriced_calls: 0 },
    by_feature: [feat("khay", "eC Mate", 200, 99), feat("formfill", "AI điền hộ phiếu", 40, 70, { usd: 0.3 }), feat("image", "Tạo ảnh", 3, 0),
      feat("weekly_report", "Chấm báo cáo tuần", 50, 100, { system_calls: 50 })],
    by_department: [{ department: "Acc", headcount: 10, active: 8, calls: 200, adoption_pct: 80, usd: 0.3 },
      { department: "Ops", headcount: 10, active: 4, calls: 50, adoption_pct: 40, usd: 0.2 }],
    by_person: kind === "self" ? people.slice(0, 1) : people,
    daily: [{ date: "2026-11-01", calls: 5, users: 2 }, { date: "2026-11-02", calls: 9, users: 3 }],
    never: Array.from({ length: 25 }, (_, k) => ({ user: "n" + k + "@x", name: "Chua " + k, department: "Ops" })),
    formfill: null, departments: kind === "self" ? [] : ["Acc", "Ops"], usd_per_credit: 0.005,
  }, over || {});
}
function boot(responder) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url: "https://x.test/ai-usage", pretendToBeVisual: true });
  const w = dom.window; w.__q = [];
  w.fetch = (u) => { const qs = new URL(u, "https://x.test").searchParams; w.__q.push(Object.fromEntries(qs));
    const [status, body] = responder(qs); return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) }); };
  w.eval(JS); return w;
}
const $ = (w, s) => w.document.querySelector(s);
const $$ = (w, s) => [...w.document.querySelectorAll(s)];

// 1. Tra loi nhanh: 4 cau, tinh nang loi nhieu bi goi ten; tinh nang < 10 luot khong bi ket luan.
{ const w = boot(() => [200, { message: data("all") }]); await flush();
  ok(w.__q[0].days === "30" && !("department" in w.__q[0]), "goi lan dau days=30, khong gui department rong");
  const a = $$(w, ".au-a");
  ok(a.length === 4, "co 4 cau tra loi nhanh");
  const okq = a[2].textContent;
  ok(/AI điền hộ phiếu lỗi nhiều/.test(okq) && a[2].classList.contains("bad"), "cau 'co on khong' goi ten tinh nang < 80%");
  ok(!/Tạo ảnh/.test(okq), "tinh nang 3 luot 0% khong bi ket luan loi nhieu");
  ok(/eC Mate/.test(a[1].textContent) && !/Chấm báo cáo tuần/.test(a[1].textContent.split("tiếp theo")[0]), "dung gi nhieu nhat bo qua luot he thong tu chay");
  ok(/Ops — 4\/10/.test(a[0].textContent), "chi ra phong dung it nhat");
  ok(/Tốn nhất: AI điền hộ phiếu/.test(a[3].textContent), "chi ra tinh nang ton nhat");
  // a11y: khong de ca trang aria-live (moi lan ve lai doc ca trang), co vung status rieng.
  ok(!$(w, "#au-view").hasAttribute("aria-live") && $(w, "#au-status").getAttribute("role") === "status", "aria-live chi o vung status");
  ok(/250 lượt/.test($(w, "#au-status").textContent), "status bao da tai");
  ok($(w, "#au-view").getAttribute("aria-busy") === "false", "het aria-busy sau khi tai");
  ok($$(w, ".au-bar title").length === 2, "moi cot bieu do co <title> cho doc man hinh/cham");
  // 2. Danh sach nguoi gon 10 dong + Xem tat ca.
  ok($$(w, "#au-people tbody tr").length === 10, "mac dinh 10 nguoi");
  $(w, '[data-act="more"]').click(); await flush();
  ok($$(w, "#au-people tbody tr").length === 12, "Xem tat ca -> 12 nguoi");
  // 3. Sap xep la <button> trong th, bam doi aria-sort.
  const sb = $(w, '#au-people button[data-sort="name"]');
  ok(!!sb, "tieu de cot sap xep la button (ban phim dung duoc)");
  sb.click(); await flush();
  ok($(w, '#au-people button[data-sort="name"]').closest("th").getAttribute("aria-sort") === "ascending", "bam Nguoi -> ascending");
  ok(/Nguoi A/.test($(w, "#au-people tbody tr").textContent), "sap theo ten A truoc");
  // 4. Tim kiem: o tim KHONG bi thay (giu con tro), chi khoi bang ve lai.
  const q = $(w, "#au-q"); q.value = "Nguoi C"; q.dispatchEvent(new w.Event("input", { bubbles: true })); await flush();
  ok($(w, "#au-q") === q, "o tim khong bi ve lai");
  ok($$(w, "#au-people tbody tr").length === 1, "tim -> 1 nguoi khop");
  q.value = "zzz"; q.dispatchEvent(new w.Event("input", { bubbles: true })); await flush();
  ok(/Không ai khớp/.test($(w, "#au-people").textContent), "khong khop -> huong dan");
  // 5. Danh sach chua dung > 20 nguoi thi gap lai.
  ok(!!$(w, "details.au-never") && !$(w, "details.au-never").open, "chua dung 25 nguoi -> gap trong details");
  // 6. Doi khoang ngay + phong -> dung tham so cu.
  $(w, '[data-period="7"]').click(); await flush();
  ok(w.__q.at(-1).days === "7", "bam 7 ngay -> days=7");
  ok($(w, '[data-period="7"]').getAttribute("aria-pressed") === "true", "chip dang chon co aria-pressed");
  const sel = $(w, "#au-dept"); sel.value = "Ops"; sel.dispatchEvent(new w.Event("change", { bubbles: true })); await flush();
  ok(w.__q.at(-1).department === "Ops" && w.__q.at(-1).days === "7", "chon phong -> department=Ops giu days");
  $(w, '[data-period="month"]').click(); await flush();
  ok(/^\d{4}-\d{2}-01$/.test(w.__q.at(-1).from_date) && !("days" in w.__q.at(-1)), "Thang nay -> from_date ngay 1"); }

// 7. Rong: noi vi sao + nut xem 90 ngay.
{ const w = boot((qs) => [200, { message: data("self", { totals: { calls: 0, user_calls: 0 }, by_feature: [], by_person: [], daily: [], never: [] }) }]); await flush();
  ok(!!$(w, ".au-zero") && /eC Mate/.test($(w, ".au-zero").textContent), "rong (ca nhan) -> huong dan dung eC Mate");
  ok(!$(w, ".au-ans") && !$(w, ".au-trend"), "rong -> khong ve bieu do phang / tra loi nhanh");
  $(w, '.au-zero [data-period="90"]').click(); await flush();
  ok(w.__q.at(-1).days === "90", "nut Xem 90 ngay -> days=90"); }

// 8. Ca nhan: khong co bang phong, khong o tim.
{ const w = boot(() => [200, { message: data("self") }]); await flush();
  ok(!$(w, "#au-q") && !/Theo phòng/.test($(w, "#au-view").textContent), "ca nhan: khong o tim, khong bang phong");
  ok(/Bạn dùng AI/.test($$(w, ".au-a")[0].textContent), "ca nhan: cau 1 noi ve chinh minh"); }

// 9. Loi 403 khi loc phong -> nut ve pham vi cua minh (Thu lai se loi y het).
{ let n = 0;
  const w = boot((qs) => { n++; if (qs.get("department") === "Ops") return [403, { _server_messages: JSON.stringify([JSON.stringify({ message: "Không có quyền" })]) }]; return [200, { message: data("dept") }]; });
  await flush();
  const sel = $(w, "#au-dept"); sel.value = "Ops"; sel.dispatchEvent(new w.Event("change", { bubbles: true })); await flush();
  ok(/Không có quyền/.test($(w, ".au-err").textContent), "hien cau loi that cua server");
  const b = $(w, '[data-act="reset-dept"]'); ok(!!b, "403 khi loc phong -> nut Xem pham vi cua toi");
  b.click(); await flush();
  ok(!("department" in w.__q.at(-1)) && !!$(w, ".au-hero"), "bam -> tai lai khong department"); }
// 10. Loi mang -> Thu lai.
{ let first = true;
  const w = boot(() => { if (first) { first = false; return [500, {}]; } return [200, { message: data("all") }]; }); await flush();
  ok(/500/.test($(w, ".au-err").textContent) && !!$(w, '[data-act="retry"]'), "loi 500 -> nut Thu lai");
  $(w, '[data-act="retry"]').click(); await flush();
  ok(!!$(w, ".au-hero"), "Thu lai -> tai duoc"); }

console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
