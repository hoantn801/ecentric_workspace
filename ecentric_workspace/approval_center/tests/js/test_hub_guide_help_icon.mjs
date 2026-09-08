// Copyright (c) 2026, eCentric and contributors
// Icon "?" tren the Approval Center -> bai huong dan cua chinh loai yeu cau do.
//
// Hai dieu de hong, ca hai deu im lang:
//   1. Ve icon cho MOI the, ke ca loai chua co bai -> nguoi dung bam ra 404. Nen
//      icon chi duoc ve khi server tra `guide_route`.
//   2. Ve dung icon nhung the NUOT cu nhap: onClick cua hub bat ".card" va day
//      window.location sang trang tao yeu cau. Bam "?" ma nhay sang form la kieu
//      hong khong ai bao cao, chi thay "huong dan bam khong duoc".
// Chay tren CODE THAT cua trang qua vm voi DOM gia toi thieu.
import fs from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import path from "path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = path.join(HERE, "..", "..", "ui", "hub", "main_section.html");
if (!fs.existsSync(PAGE)) throw new Error("main_section.html not found: " + PAGE);
const SRC = fs.readFileSync(PAGE, "utf8")
  .match(/<script id="ec-approval-center">([\s\S]*?)<\/script>/)[1];

let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };

function mkEl(id) {
  return { id, innerHTML: "", textContent: "", value: "", hidden: false, _t: null,
    classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    style: {}, dataset: {}, _attrs: {},
    getAttribute(k){ return k in this._attrs ? this._attrs[k] : null; },
    setAttribute(k, v){ this._attrs[k] = String(v); },
    addEventListener(){}, appendChild(){}, remove(){}, focus(){},
    querySelector(){ return null; }, querySelectorAll(){ return []; } };
}
const els = {};
const loc = { href: "" };
const sandbox = {
  console, setTimeout, clearTimeout,
  document: {
    readyState: "complete",
    getElementById(id){ return els[id] || (els[id] = mkEl(id)); },
    addEventListener(){},
  },
  window: { location: loc },
};
sandbox.window.document = sandbox.document;
vm.createContext(sandbox);
vm.runInContext(SRC, sandbox);
const AC = sandbox.window.ApprovalCenter;
ok(!!AC && typeof AC._cardHtml === "function", "trang phai lo _cardHtml cho test");

// ---- 1. chi ve "?" khi co bai --------------------------------------------------------
const withGuide = { approval_code: "PAYMENT_REQUEST", approval_title: "Đề nghị thanh toán",
  card_status: "Active", route: "/approvals/payment-request",
  guide_route: "/huong-dan/dnmh-dntt", guide_title: "DNMH → DNTT" };
const noGuide = { approval_code: "LEAVE", approval_title: "Nghỉ phép",
  card_status: "Active", route: "/approvals/leave" };

const h1 = AC._cardHtml(withGuide);
const h2 = AC._cardHtml(noGuide);
ok(h1.includes('class="card-help"'), "the co bai phai co icon ?");
ok(h1.includes('href="/huong-dan/dnmh-dntt"'), "icon ? phai tro dung route cua bai");
ok(h1.includes("DNMH → DNTT"), "tooltip phai mang ten ngan cua bai");
ok(!h2.includes('class="card-help"'), "the KHONG co bai thi khong duoc ve icon ?");
ok(!h2.includes("undefined") && !h2.includes("null"),
   "the khong co bai khong duoc lo chu undefined/null ra man hinh");

// the "Sap ra mat" van duoc doc huong dan: khong tao duoc yeu cau khong co nghia
// la khong duoc tim hieu quy trinh.
const soon = AC._cardHtml({ approval_code: "PURCHASE_REQUEST", approval_title: "Đề nghị mua hàng",
  card_status: "Coming Soon", guide_route: "/huong-dan/dnmh-dntt", guide_title: "DNMH → DNTT" });
ok(soon.includes('class="card-help"'), "the chua khả dụng van phai co icon huong dan");

// ---- 2. bam "?" khong bi the nuot -----------------------------------------------------
// closest("[data-go]") KHONG duoc gia dinh - no doc tu chinh the <a> ma cardHtml
// vua sinh ra. Nho vay, go thuoc tinh data-go khoi ma trang la test nay do, chu
// khong phai "vong dung DOM gia van xanh".
const helpTag = (h1.match(/<a class="card-help"[^>]*>/) || [""])[0];
ok(/\sdata-go="1"/.test(helpTag),
   "the <a> cua icon ? phai mang data-go=1 - do la quy uoc 'de link tu di' cua onClick");
function target(cls, attrs) {
  const isGo = cls === "help" && /\sdata-go=/.test(helpTag);
  return { closest(sel){
    if (sel === "[data-apc]") return null;
    if (sel === ".chip") return null;
    if (sel === "[data-go]") return isGo ? {} : null;
    if (sel === ".card") return { getAttribute: (k) => attrs[k] || null };
    return null;
  } };
}
loc.href = "";
AC._onClick({ target: target("help", { "data-status": "Active", "data-route": "/approvals/payment-request" }) });
ok(loc.href === "", "bam icon ? KHONG duoc bi the day sang trang tao yeu cau");

loc.href = "";
AC._onClick({ target: target("body", { "data-status": "Active", "data-route": "/approvals/payment-request" }) });
ok(loc.href === "/approvals/payment-request", "bam vao than the thi van sang trang tao yeu cau");

console.log((pass + " dat, " + fail + " hong"));
process.exit(fail ? 1 : 0);
