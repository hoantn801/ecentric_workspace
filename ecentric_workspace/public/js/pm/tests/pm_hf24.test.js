/* Hotfix 24 (27/11/2026): lỗi nhỏ sau hotfix 23 — kiểm nguồn (jsdom không tính bố cục). */
const fs = require("fs"), path = require("path");
const R = p => fs.readFileSync(path.join(__dirname, "..", "..", "..", p), "utf8");
const qcss = R("css/pm/pm_queue.css"), rcss = R("css/pm/pm_redesign.css"), rjs = R("js/pm/pm_redesign.js");
let pass = 0, fail = 0;
const ok = (n, c) => { if (c) { pass++; console.log("ok   " + n); } else { fail++; console.log("FAIL " + n); } };
ok("dòng Việc cần làm: nút thao tác chỉ còn biểu tượng (không tràn đè tên người giao)",
  /\.pmq-row \.pmq-ac \.pmq-btn\{width:32px/.test(qcss) && /\.pmq-row \.pmq-ac \.pmq-btn>span\{position:absolute/.test(qcss) && /\.pmq-row \.pmq-ac\{min-width:0;overflow:hidden\}/.test(qcss));
ok("chi tiết việc: Hạn không lặp ngày (chỉ thêm phần còn thiếu)", rjs.indexOf("fd.indexOf(dsTxt) === 0") > 0);
ok("Dự án: tên phụ trách 1 dòng, có dấu …", /\.pmr-pr \.pmr-ell\{white-space:nowrap;overflow:hidden;text-overflow:ellipsis/.test(rcss) && rjs.indexOf('class="pmr-ell"') > 0);
console.log(pass + "/" + (pass + fail) + " passed");
process.exit(fail ? 1 : 0);
