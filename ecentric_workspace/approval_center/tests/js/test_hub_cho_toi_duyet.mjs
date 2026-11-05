// Copyright (c) 2026, eCentric and contributors
// Hub /approvals: dai "N phieu dang cho ban duyet" (03/11/2026, UX quan ly).
//
// Nguoi duyet mo Approval Center la thay viec CUA MINH truoc danh muc tao moi. Dai chi DEM va
// dan sang /viec-cua-toi (noi duyet that); khong co phieu / loi mang -> dai an, danh muc khong
// bi anh huong. Chay tren CODE THAT cua trang qua vm voi DOM gia toi thieu.
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = path.join(HERE, "..", "..", "ui", "hub", "main_section.html");
const HTML = fs.readFileSync(PAGE, "utf8");
const SRC = HTML.match(/<script id="ec-approval-center">([\s\S]*?)<\/script>/)[1];

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };

function mkEl(id) {
  const cls = new Set();
  return { id, innerHTML: "", textContent: "", value: "", hidden: true, style: {}, _attrs: {},
    classList: { add(c){ cls.add(c); }, remove(c){ cls.delete(c); }, toggle(c, on){ if (on) cls.add(c); else cls.delete(c); }, contains(c){ return cls.has(c); } },
    getAttribute(k){ return k in this._attrs ? this._attrs[k] : null; },
    setAttribute(k, v){ this._attrs[k] = String(v); },
    addEventListener(){}, appendChild(){}, remove(){}, focus(){},
    querySelector(){ return null; }, querySelectorAll(){ return []; } };
}
function boot(fetchImpl) {
  const els = {};
  const calls = [];
  const win = { location: { href: "" } };
  if (fetchImpl) win.fetch = (url, init) => { calls.push([url, init]); return fetchImpl(url, init); };
  const sandbox = { console, setTimeout, clearTimeout,
    document: { readyState: "complete", getElementById(id){ return els[id] || (els[id] = mkEl(id)); }, addEventListener(){} },
    window: win };
  win.document = sandbox.document;
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox);
  return { AC: win.ApprovalCenter, els, calls };
}
const flush = async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 2)); };
const NOW = new Date(2026, 10, 3, 10, 0);

// 0) markup: dai nam san (an), tro sang khung "Cho toi duyet" cua /viec-cua-toi
ok(/<a class="apc-mine" id="apc-mine" href="\/viec-cua-toi#mw-cho-duyet" hidden>/.test(HTML), "dai co san trong markup, an mac dinh, link sang /viec-cua-toi#mw-cho-duyet");
ok(/\.apc-mine\{[^}]*min-height:56px/.test(HTML), "vung bam cao >= 44px");
ok(!/<script id="ec-(?!approval-center")/.test(HTML), "khong them khoi <script id=ec-...> moi");

{ // 1) co phieu, 1 qua han
  const { AC, els } = boot();
  AC._mineRender([{ due_at: "2026-11-02 08:00:00" }, { due_at: "2026-11-05 10:00:00" }, { due_at: null }], NOW);
  ok(els["apc-mine"].hidden === false, "co phieu cho -> hien dai");
  ok(els["apc-mine-n"].textContent === "3" && /^3 phiếu đang chờ bạn duyệt$/.test(els["apc-mine-t"].textContent), "dem dung so phieu");
  ok(/^1 phiếu đã quá hạn/.test(els["apc-mine-s"].textContent) && els["apc-mine"].classList.contains("is-late"), "co phieu qua han -> dong do 'N phieu da qua han'");
  ok(/3 phiếu đang chờ bạn duyệt, 1 phiếu quá hạn/.test(els["apc-mine"].getAttribute("aria-label")), "aria-label doc du thong tin");
}
{ // 2) khong qua han
  const { AC, els } = boot();
  AC._mineRender([{ due_at: "2026-11-05 10:00:00" }], NOW);
  ok(!els["apc-mine"].classList.contains("is-late") && /duyệt nhanh/.test(els["apc-mine-s"].textContent), "khong qua han -> mau thuong");
}
{ // 3) khong co phieu -> an
  const { AC, els } = boot();
  AC._mineRender([], NOW);
  ok(els["apc-mine"].hidden === true, "0 phieu -> dai an");
}
{ // 4) init goi GET list_my_pending (khong POST) va ve tu ket qua; loi mang -> van an
  const good = boot((url) => Promise.resolve({ ok: true, json: () => Promise.resolve({ message: { rows: [{ due_at: null }, { due_at: null }] } }) }));
  await flush();
  const c = good.calls.find((x) => /reporting\.actions\.list_my_pending$/.test(x[0]));
  ok(c && !(c[1] && c[1].method), "goi GET reporting.actions.list_my_pending");
  ok(good.els["apc-mine"].hidden === false && good.els["apc-mine-n"].textContent === "2", "ve dai tu ket qua server");
  const bad = boot(() => Promise.reject(new Error("offline")));
  await flush();
  ok(bad.els["apc-mine"].hidden === true, "loi mang -> dai an, khong vo trang");
  const forb = boot(() => Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({}) }));
  await flush();
  ok(forb.els["apc-mine"].hidden === true, "403 -> dai an");
}
{ // 5) khong co fetch (moi truong cu / test khac) -> khong nem loi
  const { AC, els } = boot(null);
  ok(!!AC && (!els["apc-mine"] || els["apc-mine"].hidden === true), "khong co fetch -> im lang, trang van chay");
}
console.log(`${pass} dat, ${fail} hong`); process.exit(fail ? 1 : 0);
