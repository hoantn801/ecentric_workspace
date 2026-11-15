/* pm_queue_css.test.js (15/11/2026): PO thấy nút chính (Giao việc, Xong) chữ navy trên nền navy.
   Nguyên nhân: reset ".pmq button{color:inherit}" (0,1,1) đè ".pmq-btn--pri{color:#fff}" (0,1,0).
   Khoá lại: không selector phần tử nào trong .pmq được đặt color mà có độ ưu tiên cao hơn class nút. */
"use strict";
const fs = require("fs"), path = require("path");
const CSS = fs.readFileSync(path.join(__dirname, "..", "..", "..", "css", "pm", "pm_queue.css"), "utf8");
let bad = 0; const ok = (n, c, x) => { if (!c) bad++; console.log((c ? "ok   " : "FAIL ") + n + (c || !x ? "" : "  -> " + x)); };
const rules = CSS.replace(/\/\*[\s\S]*?\*\//g, "").split("}").map(r => r.split("{")).filter(r => r.length === 2);
const offenders = rules.filter(([sel, body]) => /(^|[,\s])\.pmq\s+(button|input|select|textarea)\b/.test(sel) && /(^|;)\s*color\s*:/.test(body)).map(r => r[0].trim());
ok("reset trong .pmq không đè màu nút (dùng :where)", offenders.length === 0, offenders.join(" | "));
ok("nút chính chữ trắng", /\.pmq-btn--pri\{[^}]*color:#fff/.test(CSS));
ok("reset dùng :where(.pmq)", /:where\(\.pmq\) :where\(button,input,select,textarea\)\{font:inherit;color:inherit\}/.test(CSS));
console.log((3 - bad) + "/3 passed"); process.exit(bad ? 1 : 0);
