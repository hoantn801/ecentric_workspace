// Copyright (c) 2026, eCentric and contributors
// O soan kieu mail dung chung (public/js/ec_richtext.bundle.js) + Phe duyet dot xuat (23/11/2026).
//     node ecentric_workspace/approval_center/tests/js/test_richtext_adhoc.mjs
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, "..", "..", "..");
const RT = fs.readFileSync(path.join(ROOT, "public", "js", "ec_richtext.bundle.js"), "utf8");
const ADHOC = fs.readFileSync(path.join(HERE, "..", "..", "features", "adhoc_approval", "ui", "main_section.html"), "utf8");
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };
const flush = async () => { for (let k = 0; k < 10; k++) await new Promise((r) => setTimeout(r, 4)); };

// ---- 1. Loc HTML dan vao (Outlook / Word / Excel / trang web doc) ----
{
  const w = new JSDOM("<!DOCTYPE html><body></body>", { runScripts: "outside-only" }).window;
  w.eval(RT);
  const R = w.EcRichText;
  const evil = '<p onclick="alert(1)">Chào <b>anh</b><script>alert(2)</script></p>'
    + '<a href="javascript:alert(3)">x</a><a href="https://ecentric.vn/a">ok</a>'
    + '<img src=x onerror=alert(4)><iframe src="//evil"></iframe><style>body{display:none}</style>'
    + '<span style="color:red;position:fixed;background:url(javascript:x)">đỏ</span>'
    + '<!--[if gte mso 9]><xml><o:OfficeDocumentSettings/></xml><![endif]--><o:p></o:p>'
    + '<table class="MsoTable"><tr><td colspan="2" style="background-color:#fff3a3">A</td><td width="5">B</td></tr></table>';
  const res = R.sanitize(evil);
  const h = res.html;
  ok(!/onclick|onerror|script|iframe|<style|javascript:|<img|o:p|xml|position/i.test(h), "loai bo the / thuoc tinh nguy hiem: " + h);
  ok(/<strong>anh<\/strong>/.test(h), "giu in dam (b -> strong)");
  ok(/<a href="https:\/\/ecentric.vn\/a" target="_blank" rel="noopener">ok<\/a>/.test(h), "giu link https, mo tab moi");
  ok(!/<a[^>]*>x<\/a>/.test(h) && />x</.test(h), "link javascript: -> chi con chu");
  ok(/<span style="color:red;">đỏ<\/span>/.test(h), "giu mau chu, bo thuoc tinh style khac");
  ok(/<td colspan="2" style="background-color:#fff3a3">A<\/td>/.test(h) && !/MsoTable|width=/.test(h), "giu bang Excel (colspan, to nen), bo class/width");
  ok(res.droppedImages === 1, "dem anh bi bo");
  ok(R.toText("<p>Dòng 1</p><ul><li>a</li><li>b</li></ul><p>x&nbsp;y</p>") === "Dòng 1\na\nb\nx y", "toText giu xuong dong");
  ok(R.isEmpty("<p><br></p>") && !R.isEmpty("<p>a</p>"), "isEmpty");
  ok(R.safeUrl("ecentric.vn") === "https://ecentric.vn" && R.safeUrl("javascript:x") === "" && R.safeUrl("/approvals") === "/approvals", "safeUrl");
  // Google Docs boc ca bai trong <b style=font-weight:normal>
  ok(!/<strong>/.test(R.clean('<b style="font-weight:normal" id="docs-internal-guid-1"><p>a</p></b>')), "khong in dam ca bai Google Docs");
}

// ---- 2. Form Phe duyet dot xuat dung o soan ----
function boot(route, det) {
  const i = ADHOC.search(/<script[^>]*id="ec-[^"]+"[^>]*>/);
  const markup = ADHOC.slice(0, i);
  const js = ADHOC.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url: "https://x.test/" + route });
  const w = dom.window; w.__calls = [];
  w.document.execCommand = () => true;
  w.frappe = { csrf_token: "t", session: { user: "req@x" }, call: (o) => { const m = o.method.split(".").pop(); w.__calls.push([m, o.args]);
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true }, context: { user: "req@x", employee_name: "Hoàn", department: "Management - EC" }, form_options: { urgency_levels: ["Bình thường", "Gấp"] } } });
    if (m === "get_detail") return Promise.resolve({ message: det });
    if (m === "save_draft") return Promise.resolve({ message: { name: "EC-ADHOC-1" } });
    return Promise.resolve({ message: { rows: [] } }); } };
  w.fetch = () => Promise.resolve({ status: 200, json: () => Promise.resolve({ message: { file_url: "/private/files/a.png", file_name: "a.png" } }) });
  w.confirm = () => true;
  w.eval(RT);
  w.eval(js);
  return w;
}
{
  const w = boot("approvals/adhoc-approval");
  await flush();
  const d = w.document;
  ok(/Gửi tới/.test(d.body.textContent) && d.querySelector(".mail-to") && /CEO/.test(d.querySelector(".mail-to").textContent), "dong Gui toi: CEO");
  ok(/Management - EC/.test(d.querySelector(".card.mail").textContent), "dong Tu co phong ban");
  const ed = d.querySelector("#adhc-editor .ecrt-ed");
  ok(!!ed && ed.getAttribute("contenteditable") === "true", "co o soan dinh dang");
  ok(d.querySelectorAll("#adhc-editor .ecrt-b").length >= 14, "thanh cong cu day du");
  ok(!d.getElementById("adhc-content"), "khong con textarea tran khi co asset");
  // go noi dung -> content_html + content (chu tran)
  ed.innerHTML = "<p>Kính gửi anh, xin duyệt <strong>80tr</strong></p><ul><li>KOL A</li></ul>";
  ed.dispatchEvent(new w.Event("input", { bubbles: true }));
  const t = d.getElementById("adhc-title"); t.value = "Tăng ngân sách"; t.dispatchEvent(new w.Event("input", { bubbles: true }));
  d.getElementById("adhc-submit").click();
  await flush();
  const sd = w.__calls.find((x) => x[0] === "save_draft");
  const pl = sd ? JSON.parse(sd[1].payload) : {};
  ok(/<strong>80tr<\/strong>/.test(pl.content_html || "") && /<li>KOL A<\/li>/.test(pl.content_html || ""), "gui content_html giu dinh dang");
  ok(pl.content === "Kính gửi anh, xin duyệt 80tr\nKOL A", "gui kem content chu tran");
  // noi dung rong -> bao loi tai o noi dung, khong goi server
  const w2 = boot("approvals/adhoc-approval");
  await flush();
  const t2 = w2.document.getElementById("adhc-title"); t2.value = "T"; t2.dispatchEvent(new w2.Event("input", { bubbles: true }));
  w2.document.getElementById("adhc-submit").click();
  await flush();
  ok(!w2.__calls.some((x) => x[0] === "save_draft"), "noi dung rong -> khong gui");
  ok(w2.document.querySelector('[data-fld="content"]').classList.contains("invalid"), "bao loi tai o noi dung");
  // dan anh -> dua xuong tep dinh kem
  const ed2 = w2.document.querySelector("#adhc-editor .ecrt-ed");
  const file = new w2.File(["x"], "chup.png", { type: "image/png" });
  const ev = new w2.Event("paste", { bubbles: true, cancelable: true });
  ev.clipboardData = { files: [file], getData: () => "" };
  ed2.dispatchEvent(ev);
  await flush();
  ok(ev.defaultPrevented && /chup\.png|a\.png/.test(w2.document.getElementById("adhc-att-name").textContent), "dan anh -> len Tep dinh kem");
}
{
  // Chi tiet: ve HTML da loc lai (phong thu lop 2), phieu cu khong co HTML -> chu tran
  const det = (biz) => ({ business: Object.assign({ name: "R-1", requested_by: "req@x", request_title: "T", urgency: "Bình thường" }, biz),
    approval: { approval_status: "Pending", current_level: 1 }, levels: [], approvers: [], attachments: [], timeline: [], capabilities: {}, privacy: {} });
  const w = boot("approvals/adhoc-approval?id=R-1", det({ content: "x", content_html: '<p>Chào <b>CEO</b></p><img src=x onerror=alert(1)><table><tr><td>1</td></tr></table>' }));
  await flush();
  const v = w.document.querySelector(".ec-rt-view");
  ok(v && /<strong>CEO<\/strong>/.test(v.innerHTML) && v.querySelector("table") && !/onerror|<img/.test(v.innerHTML), "chi tiet ve HTML da loc");
  const w2 = boot("approvals/adhoc-approval?id=R-1", det({ content: "Dòng <b>cũ</b>" }));
  await flush();
  const ta = w2.document.querySelector("textarea.ro");
  ok(!w2.document.querySelector(".ec-rt-view") && ta && ta.value === "Dòng <b>cũ</b>", "phieu cu: chu tran, khong dich HTML");
}
console.log("JS: " + pass + " dat, " + fail + " hong");
process.exit(fail ? 1 : 0);
