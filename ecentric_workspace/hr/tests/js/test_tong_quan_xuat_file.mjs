// /tong-quan - nut "Xuat Excel" / "File tong hop thang" (03/11/2026, UX quan ly).
// Tai qua fetch: nut bao "Dang tao file..." khi cho, xong thi luu dung ten file server dat; server
// tu choi -> cau cua server hien ngay duoi hang nut (khong de trinh duyet bao "tai that bai").
//     node ecentric_workspace/hr/tests/js/test_tong_quan_xuat_file.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const HTML = readFileSync(join(here, "..", "..", "pages", "tong_quan", "main_section.html"), "utf8");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setTimeout(r, 3)); };

const SLA = { period: "2026-10", periods: ["2026-11", "2026-10"], current: "2026-11",
  stats: { people: 3, scored: 9, band: "good", rate: 91, good: 2, warn: 1, bad: 0, none: 0 },
  groups: [{ key: "g", label: "Báo cáo", counts: true, rate: 91, scored: 9 }],
  departments: [{ department: "D", label: "Vận hành", manager: "A", people: 3, band: "good", rate: 91, bad: 0, warn: 1, members: [] }] };

function boot(exportRes) {
  const i = HTML.indexOf('<div class="ecq"');
  const s = HTML.indexOf('<script id="ec-tongquan-js">');
  const markup = HTML.slice(i, s);
  const js = HTML.slice(s).replace(/^<script[^>]*>/, "").split("</script>")[0];
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url: "https://x.test/tong-quan#nhan-su/sla" });
  const w = dom.window;
  const calls = [], saved = [];
  let release;
  const gate = new Promise((r) => { release = r; });
  w.fetch = (url) => {
    calls.push(String(url));
    const env = (data) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: { success: true, data } }) });
    if (/get_hr_overview/.test(url)) return env({ stats: { active: 3 }, directory: [], by_dept: [] });
    if (/get_sla_summary/.test(url)) return env(SLA);
    if (/export_summary_xlsx/.test(url)) return gate.then(() => exportRes);
    return env({});
  };
  w.URL.createObjectURL = () => "blob:x";
  w.URL.revokeObjectURL = () => {};
  w.HTMLAnchorElement.prototype.click = function () { saved.push({ href: this.href, download: this.download }); };
  w.eval(js);
  return { w, calls, saved, release };
}
const $ = (w, q) => w.document.querySelector(q);

ok((HTML.match(/<a class="btn" data-xlsx href=/g) || []).length === 2, "hai nut xuat file deu gan data-xlsx");
ok(!/<script id="ec-(?!tongquan-js")/.test(HTML), "khong them khoi <script id=ec-...> moi");

{ // 1) thanh cong: dang tao file -> luu dung ten file
  const res = { ok: true, status: 200, headers: { get: (k) => (/disposition/i.test(k) ? 'attachment; filename="SLA_2026-10.xlsx"' : null) },
    blob: () => Promise.resolve(new Blob(["x"])) };
  const { w, calls, saved, release } = boot(res); await flush();
  const a = $(w, "a[data-xlsx]");
  ok(a && /Xuất Excel/.test(a.textContent), "tab SLA co nut Xuat Excel");
  a.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true })); await flush();
  ok(a.getAttribute("aria-busy") === "true" && /Đang tạo file/.test(a.textContent), "dang cho: nut bao 'Dang tao file...'");
  a.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true })); await flush();
  ok(calls.filter((u) => /export_summary_xlsx/.test(u)).length === 1, "bam lai khi dang cho -> khong goi them");
  release(); await flush();
  ok(saved.length === 1 && saved[0].download === "SLA_2026-10.xlsx", "luu file dung ten server dat: " + JSON.stringify(saved));
  ok(!a.hasAttribute("aria-busy") && a.textContent === "Xuất Excel", "xong: nut tro lai binh thuong");
  ok(!$(w, ".xerr"), "khong co loi");
}
{ // 2) server tu choi: cau server hien duoi hang nut, khong tai file
  const body = { _server_messages: JSON.stringify([JSON.stringify({ message: "Tháng 10/2026 <b>chưa chốt công</b>" })]) };
  const res = { ok: false, status: 417, headers: { get: () => null }, json: () => Promise.resolve(body) };
  const { w, saved, release } = boot(res); await flush();
  release();
  const a = w.document.querySelectorAll("a[data-xlsx]")[1];
  a.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true })); await flush();
  const e = $(w, ".sbbar .xerr");
  ok(e && /Không xuất được file: Tháng 10\/2026 chưa chốt công/.test(e.textContent) && !e.querySelector("b"), "loi server hien nguyen van (bo the HTML): " + (e && e.textContent));
  ok(e && e.getAttribute("role") === "alert", "loi duoc doc cho trinh doc man hinh");
  ok(saved.length === 0, "khong tai tep loi ve may");
  ok(/File tổng hợp tháng/.test(a.textContent) && !a.hasAttribute("aria-busy"), "nut tro lai sau loi");
}
{ // 3) 403
  const res = { ok: false, status: 403, headers: { get: () => null }, json: () => Promise.resolve({}) };
  const { w, release } = boot(res); await flush(); release();
  $(w, "a[data-xlsx]").dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true })); await flush();
  ok(/không có quyền/.test(($(w, ".xerr") || {}).textContent || ""), "403 -> bao khong co quyen");
}
console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
