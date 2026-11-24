// Copyright (c) 2026, eCentric and contributors
// Huong dan luong 7 quy trinh nhan su + trang tong quan (23/11/2026, brief HR Agent F).
// Khoa:
//   1. Moi trang: co h1, duong ve /huong-dan, so do, bang buoc (tru trang tong quan), 3-5 cau hoi,
//      loi vao form; nap CSS + mermaid + ec_guide_flow.js bang asset CUC BO (khong CDN), dung thu tu.
//   2. MOI so do mermaid parse duoc bang dung ban mermaid da vendor (public/vendor/mermaid).
//      Doi chung: so do bi lam hong thi parse PHAI loi (phep kiem khong mu).
//   3. ec_guide_flow.js: ve duoc -> data-state=ok + <svg>; thieu thu vien / render loi ->
//      data-state=error, thong bao ro, mo san so do dang chu. Khong khung nao con "pending".
//   4. 390px: bang buoc thanh the (moi o co data-label = tieu de cot), CSS co @media 640px,
//      so do qua rong thi khong thu nho qua tay (cuon ngang).
//     node ecentric_workspace/approval_center/tests/js/test_guides_hr_flows.mjs
import { JSDOM } from "jsdom";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
const PAGES = join(APP, "guides", "pages");
const PUB = join(APP, "public");
const MERMAID = readFileSync(join(PUB, "vendor", "mermaid", "mermaid.min.js"), "utf8");
const FLOWJS = readFileSync(join(PUB, "guides", "ec_guide_flow.js"), "utf8");
const CSS = readFileSync(join(PUB, "guides", "ec_guide.css"), "utf8");

// 24/11/2026: + 7 bai bo huong dan nhan su day du (Tuyen dung A-Z + 6 bai ngan) -> 17 so do.
const HR = ["nhan_su", "gan_phieu_duyet", "phe_duyet_dot_xuat", "offer_new_staff",
  "nghi_viec_clearance", "danh_gia_nhan_su", "khao_sat_nhan_su", "ky_luat",
  "tuyen_dung", "thang_chuc_dieu_chinh_luong", "dieu_chuyen_noi_bo", "cap_nhat_thong_tin_nhan_su",
  "gioi_thieu_ung_vien", "hoat_dong_nhan_su", "phan_bo_ty_trong_brand"];
const EXPECT_FLOWS = 17;

let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const html = (k) => readFileSync(join(PAGES, k, "main_section.html"), "utf8");
const flush = async () => { for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 5)); };

function dom(src, opts = {}) {
  const d = new JSDOM("<!doctype html><html><head></head><body>" + src + "</body></html>",
    { runScripts: "outside-only", pretendToBeVisual: true, url: "https://team.ecentric.vn/huong-dan/x" });
  d.window.structuredClone = structuredClone;
  if (opts.width) d.window.innerWidth = opts.width;
  return d;
}

// ---------------------------------------------------------------- 1. cau truc trang
let flowSources = [];
for (const k of HR) {
  const src = html(k);
  const d = dom(src);
  const doc = d.window.document;
  ok(doc.querySelectorAll("h1").length === 1, k + ": dung 1 h1");
  ok(doc.querySelector('a[href="/huong-dan"]'), k + ": co duong ve muc luc");
  const figs = doc.querySelectorAll('.ecg-flow[data-state="pending"]');
  ok(figs.length >= 1, k + ": co it nhat 1 so do");
  figs.forEach((f, i) => {
    ok(f.querySelector(".ecg-flow-canvas") && f.querySelector(".ecg-flow-code summary"),
      k + ": so do " + i + " co khung + so do dang chu");
    flowSources.push([k + "#" + i, f.querySelector(".ecg-flow-src").textContent]);
  });
  if (k !== "nhan_su") ok(doc.querySelectorAll("table.ecg-steps").length >= 1, k + ": co bang cac buoc");
  doc.querySelectorAll("table.ecg-steps").forEach((t) => {
    const heads = Array.from(t.querySelectorAll("thead th")).map((th) => th.textContent);
    ok(heads.join("|") === "Bước|Ai làm|Việc|Hạn|Hệ thống tự làm", k + ": tieu de bang buoc");
    t.querySelectorAll("tbody tr").forEach((tr) => {
      const labels = Array.from(tr.children).map((td) => td.getAttribute("data-label"));
      ok(labels.join("|") === heads.join("|"), k + ": moi o co data-label dung cot (the 390px)");
    });
  });
  const faq = doc.querySelectorAll(".ecg-faq details").length;
  ok(faq >= 3 && faq <= 5, k + ": 3-5 cau hoi thuong gap (co " + faq + ")");
  ok(doc.querySelectorAll(".ecg-links a.ecg-link").length >= 1, k + ": co loi vao form");
  doc.querySelectorAll('a[data-route-planned="1"]').forEach((a) =>
    ok(a.querySelector(".ecg-tag") && /sắp mở/.test(a.textContent), k + ": route du kien co nhan 'sắp mở'"));
  // asset cuc bo, co ?v=, dung thu tu; khong CDN; khong khoi <style>/<script> inline moi (A65)
  const link = doc.querySelector('link[rel="stylesheet"]');
  ok(link && /^\/assets\/ecentric_workspace\/guides\/ec_guide\.css\?v=[0-9a-f]{10}$/.test(link.getAttribute("href")),
    k + ": nap ec_guide.css co ?v=");
  const scripts = Array.from(doc.querySelectorAll("script")).map((s) => s.getAttribute("src") || "INLINE");
  ok(scripts.length === 2
     && /^\/assets\/ecentric_workspace\/vendor\/mermaid\/mermaid\.min\.js\?v=[0-9a-f]{10}$/.test(scripts[0])
     && /^\/assets\/ecentric_workspace\/guides\/ec_guide_flow\.js\?v=[0-9a-f]{10}$/.test(scripts[1]),
    k + ": mermaid roi ec_guide_flow, ca hai asset cuc bo (" + scripts.join(", ") + ")");
  ok(Array.from(doc.querySelectorAll("script")).every((s) => s.hasAttribute("defer")), k + ": script defer");
  ok(!/https?:\/\/(cdn|cdnjs|unpkg|jsdelivr)/i.test(src), k + ": khong goi CDN");
  ok(doc.querySelectorAll("style").length === 0, k + ": khong co khoi <style> inline");
  ok(/<aside class="ec-shell-mount" data-ec-shell="1"[^>]*><div class="ec-shell-head">/.test(src),
    k + ": vo shell da duc san (fallback.regenerate)");
}
ok(flowSources.length === EXPECT_FLOWS, "tong so so do = " + EXPECT_FLOWS + " (co " + flowSources.length + ")");

// ---------------------------------------------------------------- 2. mermaid parse
{
  const d = dom("");
  d.window.eval(MERMAID);
  const m = d.window.mermaid;
  ok(m && typeof m.parse === "function", "mermaid vendor nap duoc");
  for (const [name, src] of flowSources) {
    let good = false, err = "";
    try { good = (await m.parse(src)) !== false; } catch (e) { err = String(e.message || e).split("\n")[0]; }
    ok(good, "parse " + name + (err ? " -> " + err : ""));
    ok(!src.includes('""') , name + ": khong co nhan rong");
  }
  // doi chung: lam hong so do thi parse phai loi
  let broke = false;
  try { await m.parse(flowSources[0][1].replace("-->", "-->|")); } catch (e) { broke = true; }
  ok(broke, "doi chung: so do hong thi parse loi (phep kiem khong mu)");
}

// ---------------------------------------------------------------- 3. ve so do
async function runFlow(page, setup) {
  const d = dom(html(page));
  const w = d.window;
  if (setup) setup(w);
  w.eval(FLOWJS);
  await flush();
  const res = await w.ecGuideFlow.run();     // goi lai: khong con khung pending -> khong lam gi
  return { w, res };
}

{ // thu vien khong tai duoc
  const { w } = await runFlow("ky_luat");
  const figs = w.document.querySelectorAll(".ecg-flow");
  ok(figs.length === 2, "ky_luat co 2 so do");
  figs.forEach((f) => {
    ok(f.getAttribute("data-state") === "error", "thieu mermaid -> error");
    ok(/Không vẽ được sơ đồ/.test(f.querySelector(".ecg-flow-canvas").textContent), "thieu mermaid -> thong bao ro");
    ok(f.querySelector(".ecg-flow-code").open === true, "thieu mermaid -> mo san so do dang chu");
  });
}
{ // ve duoc (mermaid gia tra svg)
  const calls = [];
  const { w } = await runFlow("offer_new_staff", (w) => {
    w.mermaid = { initialize: (cfg) => { calls.push(["init", cfg]); },
      render: async (id, src) => { calls.push(["render", id, src]);
        return { svg: '<svg viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg"><g/></svg>' }; } };
  });
  const f = w.document.querySelector(".ecg-flow");
  ok(f.getAttribute("data-state") === "ok", "ve duoc -> ok");
  ok(f.querySelector(".ecg-flow-canvas svg"), "ve duoc -> khung chua svg");
  ok(!f.querySelector(".ecg-flow-code").open, "ve duoc -> so do dang chu van gap");
  const init = calls.find((c) => c[0] === "init");
  ok(init && init[1].securityLevel === "strict" && init[1].startOnLoad === false, "mermaid strict, khong tu chay");
  const r = calls.find((c) => c[0] === "render");
  ok(r && r[2].startsWith("flowchart") && r[2].includes("<br/>"), "render nhan dung ma so do (giai ma HTML)");
  ok(calls.filter((c) => c[0] === "render").length === 1, "goi lai run() khong ve lai so do da xong");
}
{ // render nem loi o so do thu 2 -> chi so do do error
  let n = 0;
  const { w } = await runFlow("khao_sat_nhan_su", (w) => {
    w.mermaid = { initialize() {}, render: async () => { n++; if (n === 2) throw new Error("x");
      return { svg: '<svg viewBox="0 0 10 10"></svg>' }; } };
  });
  const st = Array.from(w.document.querySelectorAll(".ecg-flow")).map((f) => f.getAttribute("data-state"));
  ok(st.join(",") === "ok,error", "loi rieng tung so do (" + st.join(",") + ")");
}
{ // mermaid THAT trong jsdom (khong co layout SVG) -> khong duoc treo o pending
  const { w } = await runFlow("phe_duyet_dot_xuat", (w) => { w.eval(MERMAID); });
  const st = w.document.querySelector(".ecg-flow").getAttribute("data-state");
  ok(st === "ok" || st === "error", "mermaid that: khung khong treo pending (" + st + ")"); console.log("  (mermaid that trong jsdom: " + st + ")");
}

// ---------------------------------------------------------------- 4. 390px
{
  ok(/@media \(max-width:640px\)\{[\s\S]*table\.ecg-steps td::before\{content:attr\(data-label\)/.test(CSS),
    "CSS: <=640px bang buoc thanh the, nhan cot tu data-label");
  ok(/\.ecg-flow-canvas\{[^}]*overflow-x:auto/.test(CSS), "CSS: khung so do cuon ngang duoc");
  ok(!/[^-]width:\s*[4-9]\d\dpx|[^-]width:\s*\d{4,}px/.test(CSS), "CSS: khong co chieu rong co dinh > 390px");
  const { w } = await runFlow("nghi_viec_clearance", (w) => {
    w.innerWidth = 390;
    w.mermaid = { initialize() {}, render: async () => ({ svg: '<svg viewBox="0 0 1200 2000"></svg>' }) };
    const c = w.document.querySelector(".ecg-flow-canvas");
    Object.defineProperty(c, "clientWidth", { get: () => 340 });
  });
  const svg = w.document.querySelector(".ecg-flow-canvas svg");
  ok(svg && svg.style.maxWidth === "none" && svg.style.width === "750px",
    "390px: so do rong 1200 trong khung 340 -> 750px + cuon ngang (" + (svg && svg.style.width) + ")");
  const { w: w2 } = await runFlow("nghi_viec_clearance", (w) => {
    w.mermaid = { initialize() {}, render: async () => ({ svg: '<svg viewBox="0 0 400 600"></svg>' }) };
    Object.defineProperty(w.document.querySelector(".ecg-flow-canvas"), "clientWidth", { get: () => 340 });
  });
  ok(w2.document.querySelector(".ecg-flow-canvas svg").style.width === "", "so do vua khung -> giu thu nho mac dinh");
}

console.log(`${oks} dat, ${fails} hong`);
process.exit(fails ? 1 : 0);
