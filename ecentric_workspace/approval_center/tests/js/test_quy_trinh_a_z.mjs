// Copyright (c) 2026, eCentric and contributors
// Quy trinh A-Z (24/11/2026): EcApprovalUI.withJourney chen cac buoc sau duyet; 33 form goi no.
//     node ecentric_workspace/approval_center/tests/js/test_quy_trinh_a_z.mjs
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, "..", "..", "..");
const UI = fs.readFileSync(path.join(ROOT, "public", "js", "ec_approval_ui.bundle.js"), "utf8");
const FEAT = path.join(HERE, "..", "..", "features");
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };
const w = new JSDOM("<!DOCTYPE html><body></body>", { runScripts: "outside-only" }).window;
w.eval(UI);
const U = w.EcApprovalUI;
const J = [
  { label: "HR tuyển dụng", meta: "HR nhận việc", kind: "fulfillment" },
  { label: "Offer từng ứng viên", meta: "Tạo Offer <b>x</b>", kind: "form" },
  { label: "Onboard", meta: "Ngày đi làm", kind: "info" },
];
const names = (st) => st.map((s) => s.name).join(" > ");

// 1. Xem truoc (chua gui): Tao -> cap duyet -> HR tuyen dung -> Hoan tat -> Offer -> Onboard
{
  const base = [{ name: "Tạo yêu cầu", state: "current" }, { name: "Direct Manager review", state: "upcoming" },
    { name: "HR review", state: "upcoming" }, { name: "CEO review", state: "upcoming" }];
  const st = U.withJourney(base, J);
  ok(names(st) === "Tạo yêu cầu > Direct Manager review > HR review > CEO review > HR tuyển dụng > Hoàn tất > Offer từng ứng viên > Onboard", "xem truoc du A-Z: " + names(st));
  ok(st[4].statusLabel === "Sau duyệt" && st[4].after && st[6].statusLabel === "Tiếp theo", "nhan Sau duyet / Tiep theo");
  ok(st[6].meta === "Tạo Offer &lt;b&gt;x&lt;/b&gt;", "mo ta duoc escape");
  ok(base.length === 4, "khong sua mang goc");
  const html = U.stepsHTML(st);
  ok((html.match(/step-after/g) || []).length === 3 && /border-style:dashed/.test(html), "buoc sau duyet ve khac nhe");
}
// 2. Chi tiet da duyet, fulfillment chua nhan: HR tuyen dung current, Hoan tat chua xong
{
  const base = [{ name: "Đã gửi", state: "done" }, { level: 1, name: "DM", state: "done" }, { level: 2, name: "CEO", state: "done" },
    { name: "Hoàn tất", state: "done" }];
  const st = U.withJourney(base, J);
  ok(names(st) === "Đã gửi > DM > CEO > HR tuyển dụng > Hoàn tất > Offer từng ứng viên > Onboard", "chi tiet: " + names(st));
  ok(st[3].state === "current" && st[3].statusLabel === "Chờ nhận việc", "buoc xu ly dang cho");
  ok(st[4].state === "upcoming", "Hoan tat chua xong khi con viec xu ly");
}
// 3. Trang da tu ve buoc xu ly (trang thai that) -> giu cua trang, khong lap
{
  const base = [{ name: "Đã gửi", state: "done" }, { level: 1, name: "CEO", state: "done" },
    { name: "HR tuyển dụng", state: "done", meta: "Hoàn tất bởi x" }, { name: "Hoàn tất", state: "done" }];
  const st = U.withJourney(base, J);
  ok(st.filter((s) => s.name === "HR tuyển dụng").length === 1 && st[2].meta === "Hoàn tất bởi x", "giu buoc cua trang");
  ok(st[3].name === "Hoàn tất" && st[3].state === "done", "xu ly xong -> Hoan tat xong");
}
// 4. auto -> done khi duyet; tu choi -> giu nguyen
{
  const A = [{ label: "Ghi hồ sơ", meta: "tự ghi", kind: "auto" }];
  const st = U.withJourney([{ name: "Đã gửi", state: "done" }, { level: 1, name: "HR", state: "done" }, { name: "Hoàn tất", state: "done" }], A);
  ok(st[2].name === "Ghi hồ sơ" && st[2].state === "done" && st[3].state === "done", "auto da lam");
  const rj = [{ name: "Đã gửi", state: "done" }, { level: 1, name: "HR", state: "rejected" }];
  ok(U.withJourney(rj, A).length === 2, "tu choi -> khong ve tiep");
  ok(U.withJourney(rj, []).length === 2 && U.withJourney(rj, null).length === 2, "khong co journey -> giu nguyen");
}
// 5. 33 form goi withJourney voi journey cua bootstrap
{
  let n = 0;
  for (const d of fs.readdirSync(FEAT)) {
    const f = path.join(FEAT, d, "ui", "main_section.html");
    if (!fs.existsSync(f) || d === "brand_weight") continue;
    const h = fs.readFileSync(f, "utf8");
    n++;
    ok(/EcApprovalUI\.stepsHTML\(\(EcApprovalUI\.withJourney\?EcApprovalUI\.withJourney\(steps,\(state\.boot\|\|\{\}\)\.journey_after\):steps\)/.test(h), d + ": goi withJourney");
  }
  ok(n >= 33, "du 33 form: " + n);
}
console.log("JS: " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
