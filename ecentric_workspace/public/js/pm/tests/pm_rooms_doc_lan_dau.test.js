/* pm_rooms_doc_lan_dau.test.js (09/11/2026): mở /pm#rooms lần đầu báo "Invalid Request" (HTTP 400 CSRF,
 * frappe chưa sẵn lúc trang vừa tải). Đọc lịch (day / mine) hỏng -> tự thử lại bằng GET; ghi vẫn POST.
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

function setup(getOk) {
  const dom = new JSDOM("<!doctype html><body><div id=v></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#rooms", pretendToBeVisual: true });
  const w = dom.window, posts = [], gets = [];
  w.fetch = (url, init) => {
    gets.push({ url, method: (init && init.method) || "GET" });
    if (!getOk) return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
    const body = /rooms\.day/.test(url) ? DAY : { sync_on: true, rows: [] };
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ message: body }) });
  };
  w.eval(JS);
  const api = (m) => { posts.push(m); const e = new Error("Invalid Request"); e.status = 400; return Promise.reject(e); };
  w.PMRooms.render(w.document.getElementById("v"), { api, toast: () => {}, head: (t) => "<h1>" + t + "</h1>", mode: "page", pollMs: [100000] });
  return { w, posts, gets, $$: s => Array.from(w.document.querySelectorAll(s)) };
}

(async () => {
  let T = setup(true); await flush();
  ok("POST đọc lịch bị 400 -> tự thử lại GET, hiện đủ phòng (không cần bấm Thử lại)", T.$$(".pmrm-row").length === 2);
  ok("thử lại bằng GET, không gửi CSRF", T.gets.some(g => g.method === "GET" && /rooms\.day/.test(g.url)) && T.gets.every(g => g.method === "GET"));
  ok("danh sách Phòng bạn đã đặt cũng thử lại GET", T.gets.some(g => /rooms\.mine/.test(g.url)));
  T = setup(false); await flush();
  ok("GET cũng hỏng -> vẫn báo lỗi gốc + nút Thử lại", /Invalid Request/.test(T.w.document.body.textContent) && /Thử lại/.test(T.w.document.body.textContent));
  let pass = 0;
  for (const r of res) { console.log((r.c ? "ok  " : "FAIL") + " " + r.n); if (r.c) pass++; }
  console.log(pass + "/" + res.length + " passed");
  process.exit(pass === res.length ? 0 : 1);
})();
