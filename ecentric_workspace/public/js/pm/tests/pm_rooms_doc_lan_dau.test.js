/* pm_rooms_doc_lan_dau.test.js (09/11/2026): mở /pm#rooms lần đầu báo "Invalid Request" (HTTP 400 CSRF:
 * frappe.call dùng frappe.csrf_token cũ của trang cache) và bật hộp thoại. Đọc lịch (day / mine...) nay đi
 * window.ecApi.get (GET, không cần CSRF) khi có; hỏng mới đi đường cũ (api của host). Ghi giữ đường cũ.
 * Chạy: NODE_PATH=<node_modules có jsdom> node pm_rooms_doc_lan_dau.test.js */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const JS = fs.readFileSync(path.join(__dirname, "..", "pm_rooms.js"), "utf8");
const res = [];
const ok = (n, c) => res.push({ n, c: !!c });
const tick = ms => new Promise(r => setTimeout(r, ms || 0));
const flush = async () => { for (let i = 0; i < 8; i++) await tick(0); };
const D0 = "2026-11-09";
const DAY = { date: D0, now: D0 + " 10:00:00", sync_on: true, rooms: [
  { name: "1.1", code: "1.1", title: "Hoả", label: "1.1 - Hoả", floor: "Lầu 1", note: "Lớn", capacity: 8, bookings: [] },
  { name: "5.2", code: "5.2", title: "Cabin", label: "5.2 - Cabin", floor: "Lầu 5", note: "", capacity: 2, bookings: [] }] };

function setup(ecOk, withEc) {
  const dom = new JSDOM("<!doctype html><body><div id=v></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#rooms", pretendToBeVisual: true });
  const w = dom.window, viaApi = [], viaEc = [];
  w.fetch = () => Promise.reject(new Error("không được fetch thẳng"));
  if (withEc) w.ecApi = { get: (m, a) => { viaEc.push(m); return ecOk ? Promise.resolve(/rooms\.day/.test(m) ? DAY : { sync_on: true, rows: [] }) : Promise.reject(new Error("mất mạng")); } };
  w.eval(JS);
  /* api của host = frappe.call với token cũ -> 400 Invalid Request */
  const api = (m) => { viaApi.push(m.replace("ecentric_workspace.pm.api.", "")); const e = new Error("Invalid Request"); e.status = 400; return Promise.reject(e); };
  w.PMRooms.render(w.document.getElementById("v"), { api, toast: () => {}, head: (t) => "<h1>" + t + "</h1>", mode: "page", pollMs: [100000] });
  return { w, viaApi, viaEc, $$: s => Array.from(w.document.querySelectorAll(s)) };
}

(async () => {
  let T = setup(true, true); await flush();
  ok("có ecApi: lần mở đầu hiện đủ phòng, không lỗi, không cần bấm Thử lại", T.$$(".pmrm-row").length === 2 && !/Chưa tải được/.test(T.w.document.body.textContent));
  ok("đọc day + mine qua ecApi.get", T.viaEc.some(m => /rooms\.day$/.test(m)) && T.viaEc.some(m => /rooms\.mine$/.test(m)));
  ok("KHÔNG gọi api host (frappe.call) để đọc -> không bật hộp thoại Invalid Request", T.viaApi.length === 0);
  T = setup(false, true); await flush();
  ok("ecApi hỏng -> đi api host, báo lỗi + nút Thử lại như cũ", T.viaApi.indexOf("rooms.day") >= 0 && /Invalid Request/.test(T.w.document.body.textContent) && /Thử lại/.test(T.w.document.body.textContent));
  T = setup(true, false); await flush();
  ok("không có ecApi (trang khác / test cũ) -> giữ nguyên đường api host", T.viaApi.indexOf("rooms.day") >= 0 && T.viaEc.length === 0);
  /* F5: ecApi (ec_api.bundle.js cuối body) tới SAU khi pm_rooms gọi lần đầu */
  {
    const dom = new JSDOM('<!doctype html><body><div id=v></div><script src="/assets/ecentric_workspace/dist/js/ec_api.bundle.ABC.js"></script></body>', { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#rooms", pretendToBeVisual: true });
    const w = dom.window, viaApi = [];
    w.fetch = () => Promise.reject(new Error("không được fetch thẳng"));
    w.eval(JS);
    const api = (m) => { viaApi.push(m); const e = new Error("Invalid Request"); e.status = 400; return Promise.reject(e); };
    w.PMRooms.render(w.document.getElementById("v"), { api, toast: () => {}, head: (t) => "<h1>" + t + "</h1>", mode: "page", pollMs: [100000] });
    setTimeout(() => { w.ecApi = { get: (m) => Promise.resolve(/rooms\.day/.test(m) ? DAY : { sync_on: true, rows: [] }) }; }, 300);
    await tick(900); await flush();
    ok("F5: ecApi tới muộn -> chờ, hiện đủ phòng, không gọi frappe.call (không hộp thoại)", w.document.querySelectorAll(".pmrm-row").length === 2 && viaApi.length === 0);
  }
  let pass = 0;
  for (const r of res) { console.log((r.c ? "ok  " : "FAIL") + " " + r.n); if (r.c) pass++; }
  console.log(pass + "/" + res.length + " passed");
  process.exit(pass === res.length ? 0 : 1);
})();
