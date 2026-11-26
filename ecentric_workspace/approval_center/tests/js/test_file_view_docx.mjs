// Copyright (c) 2026, eCentric and contributors
// Xem online tep .docx dinh kem (26/11/2026, EC-CTR-2026-00130): ec_file_view.bundle.js bat click
// link /files|/private/files/*.docx (ca URL da encode, chu hoa) tren moi trang -> hop thoai "Xem tep",
// fetch cung origin bang session nguoi xem, ve trong iframe sandbox="allow-scripts" (KHONG
// allow-same-origin). Bo qua: pdf, khac origin, modifier/middle click, data-no-preview, download.
// Kiem them: link that do renderAttachments (form), popup hub, sheet Cho toi duyet ve ra deu bi bat.
//     node ecentric_workspace/approval_center/tests/js/test_file_view_docx.mjs
import { JSDOM, VirtualConsole } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const ROOT = join(here, "..", "..", "..");
const SRC = readFileSync(join(ROOT, "public", "js", "ec_file_view.bundle.js"), "utf8");
const CSS = readFileSync(join(ROOT, "public", "css", "ec_file_view.bundle.css"), "utf8");
const HOOKS = readFileSync(join(ROOT, "hooks.py"), "utf8");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 5)); };

const ZIP = [0x50, 0x4B, 0x03, 0x04, 1, 2, 3, 4];
const OLE = [0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1];
function env(html, mode, opts) {
  opts = opts || {};
  const dom = new JSDOM("<!doctype html><body>" + html + "</body>", { url: "https://team.ecentric.vn/approvals/all-requests?box=fulfil", runScripts: "outside-only", pretendToBeVisual: true, virtualConsole: new VirtualConsole() });
  const w = dom.window;
  w.__fetch = [];
  w.fetch = (url, o) => {
    w.__fetch.push([url, o]);
    if (mode === "neterr") return Promise.reject(new TypeError("Failed to fetch"));
    const st = { "403": 403, "404": 404, "500": 500 }[mode] || 200;
    const bytes = mode === "ole" ? OLE : mode === "html" ? [0x3C, 0x21, 0x64, 0x6F] : mode === "big" ? ZIP : ZIP;
    const hdr = { "content-length": mode === "big" ? String(25 * 1024 * 1024) : String(bytes.length) };
    return Promise.resolve({ status: st, ok: st < 400, headers: { get: (k) => hdr[k.toLowerCase()] || null },
      arrayBuffer: () => Promise.resolve(new Uint8Array(mode === "bigbody" ? 21 * 1024 * 1024 : 0).length
        ? (() => { const b = new Uint8Array(21 * 1024 * 1024); b.set(ZIP); return b.buffer; })() : new Uint8Array(bytes).buffer) });
  };
  if (opts.pageClick) w.document.addEventListener("click", opts.pageClick);   // handler cua trang (bubble)
  w.eval(SRC);
  return w;
}
function click(w, el, init) {
  const ev = new w.MouseEvent("click", Object.assign({ bubbles: true, cancelable: true, button: 0 }, init || {}));
  const notCancelled = el.dispatchEvent(ev);
  return { prevented: !notCancelled };
}
const ov = (w) => w.document.querySelectorAll(".ec-fv-ov");
const body = (w) => (w.document.querySelector(".ec-fv-b") || {}).textContent || "";

// ---- 1. Docx thuong: bat, mo modal, fetch dung URL + credentials same-origin, iframe sandbox
{
  const href = "/private/files/[S31814 - ECENTRIC - VitaDairy]_HĐ- Nov.26 .docx";
  let rowOpened = 0;
  const w = env('<div class="row"><a id="a" href="' + href + '" target="_blank" rel="noopener">Mở</a></div>', "ok",
    { pageClick: () => { rowOpened++; } });
  const a = w.document.getElementById("a"); a.focus();
  const r = click(w, a);
  ok(r.prevented, "docx: chan hanh vi mac dinh (tai ve)");
  ok(rowOpened === 0, "docx: click khong lot xuong handler cua trang");
  ok(ov(w).length === 1, "docx: mo dung 1 hop thoai");
  const dlg = w.document.querySelector(".ec-fv-modal");
  ok(dlg && dlg.getAttribute("role") === "dialog" && dlg.getAttribute("aria-modal") === "true", "hop thoai co role dialog + aria-modal");
  ok(/Đang tải tệp/.test(body(w)) && w.document.querySelector(".ec-fv-b").getAttribute("aria-busy") === "true", "co trang thai dang tai");
  ok(w.document.getElementById("ec-fv-t").textContent === "[S31814 - ECENTRIC - VitaDairy]_HĐ- Nov.26 .docx", "ten tep giai ma dung");
  await flush();
  const [furl, fo] = w.__fetch[0] || [];
  ok(w.__fetch.length === 1 && fo && fo.credentials === "same-origin", "fetch 1 lan, credentials same-origin");
  ok(furl && furl.indexOf("/private/files/") === 0 && /%20Nov\.26%20\.docx$/.test(furl), "fetch cung origin, URL tuong doi da encode: " + furl);
  const fr = w.document.querySelector("iframe.ec-fv-frame");
  ok(!!fr, "co iframe xem");
  ok(fr && fr.getAttribute("sandbox") === "allow-scripts", "iframe sandbox=allow-scripts");
  ok(fr && !/allow-same-origin/.test(fr.getAttribute("sandbox") || ""), "iframe KHONG allow-same-origin");
  ok(fr && fr.getAttribute("referrerpolicy") === "no-referrer", "iframe no-referrer");
  const sd = fr ? fr.getAttribute("srcdoc") : "";
  ok(/Content-Security-Policy/.test(sd) && /script-src 'nonce-\d+' https:\/\/team\.ecentric\.vn\/assets\/ecentric_workspace\/vendor\/docx_preview\//.test(sd), "srcdoc co CSP nonce + chi script tu vendor");
  ok(/jszip\.min\.js/.test(sd) && /docx-preview\.min\.js/.test(sd), "srcdoc nap jszip + docx-preview vendored");
  ok(/default-src 'none'/.test(sd), "CSP default-src none");
  // Tai ve
  const dl = w.document.querySelector("[data-fv-dl]");
  ok(dl && dl.getAttribute("href") === href, "Tai ve tro dung href goc");
  ok(dl && dl.hasAttribute("download") && dl.hasAttribute("data-no-preview"), "Tai ve co download + data-no-preview");
  // bam Tai ve khong mo them hop thoai, khong bi chan
  const r2 = click(w, dl);
  ok(!r2.prevented && ov(w).length === 1, "bam Tai ve: khong bi bat lai");
  // postMessage: ready -> gui byte; ok -> hien khung
  const sent = [];
  fr.contentWindow.postMessage = (m) => sent.push(m);
  w.dispatchEvent(new w.MessageEvent("message", { data: { t: "ecfv", ready: true }, source: fr.contentWindow }));
  ok(sent.length === 1 && sent[0].t === "ecfv" && sent[0].b && sent[0].b.length === ZIP.length && sent[0].b[0] === 0x50, "ready -> gui byte tep vao khung");
  w.dispatchEvent(new w.MessageEvent("message", { data: { t: "ecfv", ready: true }, source: fr.contentWindow }));
  ok(sent.length === 1, "ready lan 2 khong gui lai");
  // tin gia mao tu nguon khac bi bo qua
  w.dispatchEvent(new w.MessageEvent("message", { data: { t: "ecfv", ok: false, msg: "x" }, source: w }));
  ok(!w.document.querySelector(".ec-fv-err"), "tin tu nguon khac khung bi bo qua");
  w.dispatchEvent(new w.MessageEvent("message", { data: { t: "ecfv", ok: true }, source: fr.contentWindow }));
  ok(fr.style.visibility === "visible" && !w.document.querySelector(".ec-fv-st"), "ok -> hien khung, bo trang thai tai");
  // Esc dong + tra focus; Esc khong lot xuong trang (popup hub)
  let pageEsc = 0; w.document.addEventListener("keydown", (e) => { if (e.key === "Escape") pageEsc++; });
  w.document.querySelector("[data-fv-close]").dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
  ok(ov(w).length === 0, "Esc dong hop thoai");
  ok(pageEsc === 0, "Esc khong lot xuong trang ben duoi");
  ok(w.document.activeElement === a, "dong xong tra focus ve link");
  // mo lai duoc sau khi dong
  click(w, a); ok(ov(w).length === 1, "dong xong mo lai duoc");
  w.document.querySelector("[data-fv-close]").click(); ok(ov(w).length === 0, "nut Dong dong hop thoai");
}

// ---- 2. Chu hoa + URL encode san + absolute cung origin + /files cong khai
for (const href of ["/private/files/HOP%20DONG%20MAU.DOCX", "https://team.ecentric.vn/files/a%5Bb%5D.Docx?fid=1", "/files/x.docx"]) {
  const w = env('<a id="a" href="' + href + '">x</a>', "ok");
  const r = click(w, w.document.getElementById("a"));
  ok(r.prevented && ov(w).length === 1, "bat link: " + href);
}
{
  const w = env('<a id="a" href="/private/files/HOP%20DONG%20MAU.DOCX">x</a>', "ok");
  click(w, w.document.getElementById("a"));
  ok(w.document.getElementById("ec-fv-t").textContent === "HOP DONG MAU.DOCX", "ten tep tu URL encode duoc giai ma");
}

// ---- 3. Bo qua: pdf, xlsx, khac origin, modifier, middle, data-no-preview (ca to tien), download, duoi gia
const SKIPS = [
  ['<a id="a" href="/private/files/hd.pdf">x</a>', {}, "pdf"],
  ['<a id="a" href="/private/files/hd.xlsx">x</a>', {}, "xlsx"],
  ['<a id="a" href="/private/files/hd.docx.pdf">x</a>', {}, "duoi .docx.pdf"],
  ['<a id="a" href="/private/files/hd.docxx">x</a>', {}, "duoi .docxx"],
  ['<a id="a" href="https://boxmeglobal.sharepoint.com/sites/x/hd.docx">x</a>', {}, "SharePoint khac origin"],
  ['<a id="a" href="/app/file/hd.docx">x</a>', {}, "khong phai /files"],
  ['<a id="a" href="https://other.example.com/private/files/hd.docx">x</a>', {}, "/private/files nhung khac origin"],
  ['<a id="a" href="javascript:alert(1)//x.docx">x</a>', {}, "javascript: URL"],
  ['<a id="a" href="/private/files/hd.docx">x</a>', { ctrlKey: true }, "Ctrl-click"],
  ['<a id="a" href="/private/files/hd.docx">x</a>', { metaKey: true }, "Cmd-click"],
  ['<a id="a" href="/private/files/hd.docx">x</a>', { shiftKey: true }, "Shift-click"],
  ['<a id="a" href="/private/files/hd.docx">x</a>', { button: 1 }, "middle-click"],
  ['<a id="a" data-no-preview href="/private/files/hd.docx">x</a>', {}, "data-no-preview"],
  ['<div data-no-preview><a id="a" href="/private/files/hd.docx">x</a></div>', {}, "data-no-preview o to tien"],
  ['<a id="a" download href="/private/files/hd.docx">x</a>', {}, "co thuoc tinh download"],
];
for (const [html, init, name] of SKIPS) {
  const w = env(html, "ok");
  const r = click(w, w.document.getElementById("a"), init);
  ok(!r.prevented && ov(w).length === 0 && w.__fetch.length === 0, "bo qua: " + name);
}
// click vao phan tu con ben trong link van bat
{
  const w = env('<a id="a" href="/private/files/hd.docx"><svg></svg><span id="s">ten</span></a>', "ok");
  const r = click(w, w.document.getElementById("s"));
  ok(r.prevented && ov(w).length === 1, "click vao span trong link van bat");
}

// ---- 4. Mo 2 lan -> 1 hop thoai, 1 fetch
{
  const w = env('<a id="a" href="/private/files/hd.docx">1</a><a id="b" href="/private/files/k.docx">2</a>', "ok");
  click(w, w.document.getElementById("a")); click(w, w.document.getElementById("a")); click(w, w.document.getElementById("b"));
  await w.EcFileView.open("/private/files/z.docx", "z.docx");
  await flush();
  ok(ov(w).length === 1 && w.__fetch.length === 1, "bam nhieu lan: 1 hop thoai, 1 fetch");
}

// ---- 5. Loi
const ERRS = [
  ["403", /Bạn không có quyền xem tệp này/, "403"],
  ["404", /Không tìm thấy tệp/, "404"],
  ["500", /mã lỗi 500/, "500"],
  ["neterr", /Kiểm tra kết nối mạng/, "mat mang"],
  ["ole", /Word cũ \(\.doc\)/, ".doc cu"],
  ["html", /không phải Word \.docx hợp lệ/, "khong phai zip (vd trang dang nhap)"],
  ["big", /Tệp lớn \(25 MB/, ">20MB theo content-length"],
  ["bigbody", /Tệp lớn \(21 MB/, ">20MB theo so byte that"],
];
for (const [mode, re, name] of ERRS) {
  const w = env('<a id="a" href="/private/files/hd.docx">x</a>', mode);
  click(w, w.document.getElementById("a"));
  await flush();
  ok(re.test(body(w)), "loi " + name + ": " + body(w).slice(0, 80));
  ok(/Tải về/.test(body(w)), "loi " + name + ": goi y tai ve");
  ok(!w.document.querySelector("iframe"), "loi " + name + ": khong tao iframe");
  ok(w.document.querySelector(".ec-fv-b").getAttribute("aria-busy") === "false", "loi " + name + ": het busy");
}
// trinh xem bao loi / Esc trong khung
{
  const w = env('<a id="a" href="/private/files/hd.docx">x</a>', "ok");
  click(w, w.document.getElementById("a")); await flush();
  const fr = w.document.querySelector("iframe");
  w.dispatchEvent(new w.MessageEvent("message", { data: { t: "ecfv", ok: false, msg: "corrupt" }, source: fr.contentWindow }));
  ok(/không đọc được tệp này/.test(body(w)), "trinh xem loi -> thong bao tep hong");
  w.EcFileView.close(); click(w, w.document.getElementById("a")); await flush();
  const fr2 = w.document.querySelector("iframe");
  w.dispatchEvent(new w.MessageEvent("message", { data: { t: "ecfv", esc: true }, source: fr2.contentWindow }));
  ok(ov(w).length === 0, "Esc trong khung xem -> dong");
}
// dong khi dang tai -> ket qua fetch den sau khong lam gi / khong loi
{
  const w = env('<a id="a" href="/private/files/hd.docx">x</a>', "403");
  click(w, w.document.getElementById("a")); w.EcFileView.close(); await flush();
  ok(ov(w).length === 0 && !w.document.querySelector(".ec-fv-err"), "dong khi dang tai: khong ve lai");
}
// bam nen ngoai -> dong
{
  const w = env('<a id="a" href="/private/files/hd.docx">x</a>', "ok");
  click(w, w.document.getElementById("a"));
  w.document.querySelector(".ec-fv-ov").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  ok(ov(w).length === 0, "bam nen ngoai -> dong");
}
// escape ten tep
{
  const w = env("", "ok");
  w.EcFileView.open("/private/files/x.docx", '<img src=x onerror=alert(1)>.docx');
  ok(!w.document.querySelector(".ec-fv-ov img") && /&lt;img/.test(w.document.querySelector(".ec-fv-name").innerHTML), "ten tep duoc escape");
}

// ---- 6. Link THAT do cac noi ve dinh kem sinh ra -> deu bi bat (khong sua trang)
{
  const fileUrl = "/private/files/[S31814 - ECENTRIC - VitaDairy]_HĐ- Nov.26 .docx";
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const samples = {
    "form renderAttachments": '<a href="' + esc(fileUrl) + '" target="_blank" rel="noopener">Mở</a>',
    "popup hub ec-apl-file": '<a class="ec-apl-file" href="' + esc(fileUrl) + '" target="_blank" rel="noopener"><svg class="icon"></svg><span class="nm">x</span></a>',
    "cho duyet cd-a": '<div class="cd-kv"><b><a class="cd-a" href="' + esc(fileUrl) + '" target="_blank" rel="noopener">Mở</a></b></div>',
  };
  for (const [name, html] of Object.entries(samples)) {
    const w = env(html, "ok");
    const r = click(w, w.document.querySelector("a span") || w.document.querySelector("a"));
    ok(r.prevented && ov(w).length === 1, "bat link that: " + name);
  }
  // nguon that van ve <a href=file_url> (chong troi: neu ai doi sang button/JS tai thi test do)
  const CR = readFileSync(join(ROOT, "approval_center", "features", "contract_review", "ui", "main_section.html"), "utf8");
  const HUB = readFileSync(join(ROOT, "approval_center", "ui", "all_requests", "main_section.html"), "utf8");
  const CD = readFileSync(join(ROOT, "public", "js", "ec_cho_duyet.bundle.js"), "utf8");
  ok(/<a href="'\+esc\(f\.file_url\)\+'" target="_blank"/.test(CR), "contract_review renderAttachments van la <a href=file_url>");
  ok(/class="ec-apl-file" href="'\+esc\(online\?linkMo:a\.file_url\)\+'"/.test(HUB) && /ec-apl-alt" href="'\+esc\(a\.file_url\)/.test(HUB), "popup hub van la <a href=file_url>");
  ok(/class="cd-a" href="'\s*\+ esc\(url\)/.test(CD), "cho duyet van la <a href=url>");
}

// ---- 7. Khai bao asset + CSS
ok(/web_include_js\.append\("ec_file_view\.bundle\.js"\)/.test(HOOKS) && /web_include_css\.append\("ec_file_view\.bundle\.css"\)/.test(HOOKS), "hooks.py khai bundle js + css");
ok(/@media \(max-width: 640px\)/.test(CSS) && /min-height: 44px/.test(CSS), "CSS 390px: toan man hinh, nut 44px");
ok(/border-radius: var\(--fv-radius\)/.test(CSS) && /--fv-radius: 12px/.test(CSS), "the bo 12px");

console.log(oks + " dat, " + fails + " hong");
process.exit(fails ? 1 : 0);
