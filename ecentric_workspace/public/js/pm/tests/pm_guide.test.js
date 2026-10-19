/* pm_guide.test.js — Hướng dẫn /pm (asset pm_guide.js). Chạy: NODE_PATH=<node_modules có jsdom> node pm_guide.test.js
 * Kiểm: đủ 10 mục + mục lục, thẻ "Bạn là ai", bước có màu vai trò, sơ đồ làn có bản dọc cho màn hẹp,
 * mọi ảnh trỏ tới file có thật trong public/images/pm_guide, mỗi ảnh dùng đúng 1 lần, không lời gọi server. */
"use strict";
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "js", "pm", "pm_guide.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "css", "pm", "pm_guide.css"), "utf8");
const IMGDIR = path.join(ROOT, "images", "pm_guide");
const res = [];
const ok = (n, c, x) => res.push({ n, c: !!c, x });

const dom = new JSDOM("<!doctype html><body><div id=v></div></body>", { runScripts: "outside-only", url: "https://team.ecentric.vn/pm#guide" });
const w = dom.window;
let calls = 0;
w.fetch = () => { calls++; return Promise.reject(new Error("no server")); };
w.eval(JS);
const c = w.document.getElementById("v");
w.PMGuide.render(c, { head: (t, s) => `<header><h1>${t}</h1><p>${s}</p></header>` });
const $$ = s => Array.from(c.querySelectorAll(s));

ok("render: tiêu đề + 10 mục + mục lục 10 nút", c.querySelector("h1").textContent === "Hướng dẫn quản lý công việc" && $$(".pmg-sec").length === 10 && $$(".pmg-toc button").length === 10);
ok("mục lục trỏ đúng id mục", $$(".pmg-toc button").every(b => !!c.querySelector("#" + b.getAttribute("data-pmg-jump"))));
ok("3 thẻ “Bạn là ai” (nhận / giao / trưởng nhóm) trỏ tới mục có thật", $$(".pmg-card").length === 3 && $$(".pmg-card").every(a => !!c.querySelector("#" + a.getAttribute("data-pmg-jump"))));
ok("bước có màu vai trò: người nhận, người giao, hệ thống đều xuất hiện", $$(".pmg-li-n").length >= 6 && $$(".pmg-li-g").length >= 6 && $$(".pmg-li-s").length >= 1);
const boxes = $$(".pmg-flowbox");
ok("≥5 sơ đồ làn, mỗi sơ đồ có bản dọc cho màn hẹp với cùng số bước", boxes.length >= 5 && boxes.every(bx => bx.querySelectorAll(".pmg-node").length === bx.querySelectorAll(".pmg-lanes-m li").length && bx.querySelectorAll(".pmg-node").length >= 4));
const imgs = $$(".pmg-shot img").map(i => i.getAttribute("src"));
const keys = imgs.map(s => s.replace("/assets/ecentric_workspace/images/pm_guide/", "").replace(".jpg", ""));
ok("10 ảnh, mỗi khoá dùng đúng 1 lần, khớp PMGuide._keys", imgs.length === 10 && new Set(keys).size === 10 && w.PMGuide._keys.every(k => keys.indexOf(k) >= 0));
ok("mọi ảnh có file thật trong public/images/pm_guide", keys.every(k => fs.existsSync(path.join(IMGDIR, k + ".jpg"))), keys.filter(k => !fs.existsSync(path.join(IMGDIR, k + ".jpg"))).join(","));
ok("mọi ảnh có chú thích + alt", $$(".pmg-shot").every(f => f.querySelector("figcaption").textContent.trim() && f.querySelector("img").getAttribute("alt")));
ok("bảng “Ai được làm gì” có cột người nhận / giao / trưởng phòng", /Ai được làm gì/.test(c.textContent) && $$("#pmg-s9 th .pmg-r").length === 3);
ok("nút mục lục cuộn tới mục (không đổi hash)", (() => { let hit = null; const t = c.querySelector("#pmg-s6"); t.scrollIntoView = () => { hit = "pmg-s6"; }; c.querySelector('[data-pmg-jump="pmg-s6"]').click(); return hit === "pmg-s6" && w.location.hash === "#guide"; })());
ok("ảnh lỗi → ẩn khung (không hiện icon vỡ)", (() => { const im = c.querySelector(".pmg-shot img"); im.onerror(); return im.parentNode.classList.contains("pmg-shot-off"); })());
ok("không gọi server, không ký tự Jinja", calls === 0 && !/\{\{|\{%|\{#/.test(JS));
ok("CSS có màu vai trò + làn + bản dọc màn hẹp", [".pmg-r-n", ".pmg-r-g", ".pmg-r-l", ".pmg-lanes", ".pmg-lanes-m", "@media (max-width:900px)"].every(x => CSS.indexOf(x) >= 0));
ok("ngân sách: JS ≤ 24 KB, CSS ≤ 10 KB, ảnh ≤ 120 KB/ảnh", Buffer.byteLength(JS) <= 24 * 1024 && Buffer.byteLength(CSS) <= 10 * 1024 && fs.readdirSync(IMGDIR).every(f => fs.statSync(path.join(IMGDIR, f)).size <= 120 * 1024));

let fail = 0;
res.forEach(r => { if (!r.c) fail++; console.log((r.c ? "ok   " : "FAIL ") + r.n + (r.c || !r.x ? "" : "  -> " + r.x)); });
console.log(`${res.length - fail}/${res.length} passed`);
process.exit(fail ? 1 : 0);
