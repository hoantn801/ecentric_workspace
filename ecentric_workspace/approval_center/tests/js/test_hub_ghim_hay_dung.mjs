// Copyright (c) 2026, eCentric and contributors
// Approval Center (23/11/2026, Hoan chon mockup A): ghim + "Ban hay dung" + thanh loc MOT dong +
// tim khong dau + the chua dung duoc gom cuoi. Chay CODE THAT cua trang tren jsdom.
//     node ecentric_workspace/approval_center/tests/js/test_hub_ghim_hay_dung.mjs
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(HERE, "..", "..", "ui", "hub", "main_section.html"), "utf8");
const i = HTML.indexOf('<script id="ec-approval-center">');
const markup = HTML.slice(0, i);
const JS = HTML.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };
const flush = async () => { for (let k = 0; k < 8; k++) await new Promise((r) => setTimeout(r, 3)); };

const T = (code, title, cat, status, route, extra) => Object.assign({ approval_code: code, approval_title: title,
  description: "", icon: "", category_code: cat, category_name: cat === "FIN" ? "Finance & Budget" : "Human Resources",
  category_icon: "", card_status: status, process_status: "Live", route, sort_order: 0, category_sort_order: cat === "FIN" ? 5 : 10 }, extra || {});
const FIX = {
  is_admin: false,
  categories: [{ category_code: "FIN", category_name: "Finance & Budget", sort_order: 5 },
               { category_code: "HR", category_name: "Human Resources", sort_order: 10 }],
  types: [T("PAYMENT_REQUEST", "Payment Request", "FIN", "Active", "/approvals/payment-request"),
          T("PURCHASE_REQUEST", "Purchase Request", "FIN", "Active", "/approvals/purchase-request"),
          T("LEAVE", "Nghỉ phép", "HR", "Active", "/ec-hr/leave"),
          T("RESIGNATION", "Nghỉ việc", "HR", "Active", "/approvals/resignation"),
          T("SOON", "Sắp có", "HR", "Coming Soon", null)],
  my_pins: ["PAYMENT_REQUEST"],
  my_usage: { PURCHASE_REQUEST: 7, LEAVE: 3, PAYMENT_REQUEST: 9, SOON: 2 },
};

function boot(fix, onPin) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/approvals" });
  const w = dom.window; w.__calls = [];
  w.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
  w.frappe = { call: (o) => { w.__calls.push(o);
    if (/list_catalog$/.test(o.method)) return Promise.resolve({ message: JSON.parse(JSON.stringify(fix)) });
    if (/set_pin$/.test(o.method)) return onPin ? onPin(o) : Promise.resolve({ message: { my_pins: [] } });
    return Promise.resolve({ message: {} }); } };
  w.eval(JS);
  return w;
}

{
  const w = boot(FIX);
  await flush();
  const d = w.document;
  const tops = d.getElementById("apc-tops");
  ok(tops && !tops.hidden, "khoi ghim / hay dung hien");
  const pins = [...d.querySelectorAll(".apc-pin")].map((a) => a.querySelector("b").textContent);
  ok(pins.length === 1 && pins[0] === "Payment Request", "Da ghim: chi Payment Request");
  const used = [...d.querySelectorAll(".apc-use a .u-t")].map((x) => x.textContent);
  ok(used.join("|") === "Purchase Request|Nghỉ phép", "Hay dung: xep theo so lan, bo muc da ghim + the chua dung duoc");
  ok(/đã gửi 7 lần/.test(d.querySelector(".apc-use").textContent), "hien so lan da gui");
  // thanh loc 1 dong: o tim nam CUNG hang voi chip
  const tools = d.querySelector(".apc-tools");
  ok(tools && tools.querySelector("#apc-q") && tools.querySelector("#apc-cats"), "o tim + chip cung mot hang");
  // Tat ca: chia nhom theo thu tu danh muc server (Tai chinh truoc)
  const secs = [...d.querySelectorAll(".apc-sec")].map((x) => x.textContent);
  ok(secs.length === 2 && /^Finance/.test(secs[0]) && /^Human/.test(secs[1]), "nhom Tai chinh dung dau");
  const soon = d.querySelector("details.apc-soon");
  ok(soon && /Chưa dùng được \(1\)/.test(soon.textContent) && soon.querySelector('[data-code="SOON"]'), "the chua dung duoc gom cuoi, thu gon");
  ok(!soon.querySelector("[data-pin]"), "the chua dung duoc khong co nut ghim");
  const pay = d.querySelector('.apc-grid .card[data-code="PAYMENT_REQUEST"]');
  ok(pay && pay.classList.contains("pinned") && pay.querySelector(".star.on"), "the da ghim duoc to sang + sao dac");
  ok(/đã gửi 9 lần/.test(pay.textContent), "the co so lan da gui");
  // tim khong dau
  const q = d.getElementById("apc-q");
  q.value = "nghi phep"; q.dispatchEvent(new w.Event("input", { bubbles: true }));
  const codes = [...d.querySelectorAll("#apc-body .card")].map((c) => c.getAttribute("data-code"));
  ok(codes.join() === "LEAVE", "tim 'nghi phep' khong dau -> Nghỉ phép");
  q.value = "nghi"; q.dispatchEvent(new w.Event("input", { bubbles: true }));
  ok(d.querySelectorAll("#apc-body .card").length === 2, "tim 'nghi' -> 2 the");
  q.value = ""; q.dispatchEvent(new w.Event("input", { bubbles: true }));
}
{
  // Ghim: bam sao -> POST set_pin, KHONG chuyen trang; server tra my_pins thi ve lai theo server.
  let loc = null;
  const w = boot(FIX, (o) => Promise.resolve({ message: { my_pins: ["PAYMENT_REQUEST", "LEAVE"] } }));
  await flush();
  const d = w.document;
  const star = d.querySelector('.card[data-code="LEAVE"] [data-pin]');
  star.dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
  await flush();
  const call = w.__calls.find((c) => /set_pin$/.test(c.method));
  ok(call && call.type === "POST" && call.args.approval_type === "LEAVE" && call.args.pinned === 1, "POST set_pin LEAVE pinned=1");
  ok(w.location.pathname === "/approvals", "bam sao khong nhay sang form");
  ok([...d.querySelectorAll(".apc-pin b")].map((b) => b.textContent).join("|") === "Payment Request|Nghỉ phép", "ve lai Da ghim theo server");
  // bo ghim tu khoi Da ghim
  const ev = new w.MouseEvent("click", { bubbles: true, cancelable: true });
  d.querySelector('.apc-pin [data-pin="PAYMENT_REQUEST"]').dispatchEvent(ev);
  ok(ev.defaultPrevented, "sao nam trong link Da ghim: chan mo link");
  const c2 = w.__calls.filter((c) => /set_pin$/.test(c.method)).pop();
  ok(c2.args.approval_type === "PAYMENT_REQUEST" && c2.args.pinned === 0, "bo ghim -> pinned=0");
}
{
  // Loi server -> tra lai trang thai cu + bao loi
  const w = boot(FIX, () => Promise.reject({ _server_messages: JSON.stringify([JSON.stringify({ message: "Chỉ ghim tối đa 12 loại phiếu." })]) }));
  await flush();
  const d = w.document;
  d.querySelector('.card[data-code="LEAVE"] [data-pin]').dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true }));
  await flush();
  ok(d.querySelectorAll(".apc-pin").length === 1, "loi -> tra ve 1 muc ghim nhu cu");
  ok(/tối đa 12/.test(d.getElementById("apc-toast").textContent), "toast thong diep server");
}
{
  // Khong ghim, khong lich su: van co khoi Da ghim voi goi y; khong co khoi Hay dung
  const w = boot(Object.assign({}, FIX, { my_pins: [], my_usage: {} }));
  await flush();
  const d = w.document;
  ok(!d.getElementById("apc-tops").hidden && /bấm ☆/.test(d.getElementById("apc-tops").textContent), "goi y cach ghim");
  ok(!d.querySelector(".apc-use"), "khong lich su -> khong ve Hay dung");
  ok(d.getElementById("apc-tops").className.indexOf("one") >= 0, "mot cot khi khong co Hay dung");
}
console.log(pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
