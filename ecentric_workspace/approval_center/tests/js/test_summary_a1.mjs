// Copyright (c) 2026, eCentric and contributors
// Khoi "Tom tat" A1 "Luoi can bang" (Hoan chot 24/11/2026): renderer dung chung public/js/ec_summary.bundle.js
// + kieu public/css/ec_summary.bundle.css + moi form phe duyet chi khai cau hinh.
//     node ecentric_workspace/approval_center/tests/js/test_summary_a1.mjs
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP = path.join(HERE, "..", "..", "..");
const FEAT = path.join(HERE, "..", "..", "features");
const JS = fs.readFileSync(path.join(APP, "public", "js", "ec_summary.bundle.js"), "utf8");
const CSS = fs.readFileSync(path.join(APP, "public", "css", "ec_summary.bundle.css"), "utf8");
const MONEY = fs.readFileSync(path.join(APP, "public", "js", "ec_money.bundle.js"), "utf8");
const HOOKS = fs.readFileSync(path.join(APP, "hooks.py"), "utf8");
let pass = 0, fail = 0;
const ok = (c, m) => { if (c) pass++; else { fail++; console.log("  FAIL: " + m); } };
const flush = async () => { for (let k = 0; k < 8; k++) await new Promise((r) => setTimeout(r, 3)); };
const win = (body) => { const d = new JSDOM("<!DOCTYPE html><html><body>" + (body || "") + "</body></html>", { runScripts: "outside-only" }); d.window.eval(JS); return d.window; };

// ---- 1. chia hang can bang -------------------------------------------------------------------
{ const S = win().EcSummary;
  ok(JSON.stringify(S.rowSpans(5, 4)) === "[4,4,4,6,6]", "5 o -> 3+2");
  ok(JSON.stringify(S.rowSpans(7, 4)) === "[3,3,3,3,4,4,4]", "7 o -> 4+3");
  ok(JSON.stringify(S.rowSpans(1, 4)) === "[12]" && JSON.stringify(S.rowSpans(0, 4)) === "[]", "1 o chiem tron hang, 0 o rong");
  ok(JSON.stringify(S.rowSpans(3, 2)) === "[6,6,12]", "390px: 3 o -> 2+1 (o le chiem tron hang, khong lo)");
  for (const max of [2, 3, 4]) for (let n = 1; n <= 20; n++) {
    const sp = S.rowSpans(n, max); let rows = [], cur = [], sum = 0;
    sp.forEach((s) => { cur.push(s); sum += s; if (sum === 12) { rows.push(cur.length); cur = []; sum = 0; } });
    const okRows = sp.length === n && cur.length === 0 && Math.max(...rows) - Math.min(...rows) <= 1 && Math.max(...rows) <= max
      && sp.every((s) => Number.isInteger(s));
    ok(okRows, "can bang n=" + n + " max=" + max + " -> " + JSON.stringify(rows));
  }
}

// ---- 2. so tien / ngay -----------------------------------------------------------------------
{ const S = win().EcSummary;
  ok(S.fmtNumber(25000000) === "25.000.000" && S.fmtNumber(0) === "0" && S.fmtNumber(-1500) === "-1.500", "dau cham phan cach");
  ok(S.fmtNumber(20.5) === "20,5" && S.fmtNumber(1234.05) === "1.234,05", "so le dau phay");
  ok(S.toNumber("25.000.000") === 25000000 && S.toNumber("25000000") === 25000000 && S.toNumber("20.5") === 20.5
    && S.toNumber("1.234,5") === 1234.5 && S.toNumber("Theo HĐ") === null && S.toNumber("") === null, "doc so tu chuoi");
  ok(S.fmtDate("2026-12-31") === "31/12/2026" && S.fmtDate("2026-12-31 09:05:00") === "31/12/2026 09:05" && S.fmtDate("Q4") === "Q4", "ngay dd/mm/yyyy");
  const fl = S.flowSteps("Tạo yêu cầu → HOF → CEO (theo cấu hình)");
  ok(JSON.stringify(fl.steps) === '["HOF","CEO"]' && fl.note === "theo cấu hình", "tach luong: bo 'Tao yeu cau', giu ghi chu");
}

// ---- 3. ve that tren form gia lap ------------------------------------------------------------
const FORM = '<div class="x-formwrap">'
  + '<div class="fld" data-fld="payee"><label>Người nhận <span class="req">*</span></label><input data-model="payee"></div>'
  + '<div class="fld" data-fld="amount"><label>Số tiền <span class="req">*</span></label><input data-model="amount"></div>'
  + '<div class="fld" data-fld="bank"><label>Ngân hàng <span class="req">*</span></label><input data-model="bank"></div>'
  + '<div class="fld" data-fld="note"><label>Ghi chú</label><textarea data-model="note"></textarea></div>'
  + '<div class="fld" data-fld="secret"><label>Ô ẩn <span class="req">*</span></label><input data-model="secret"></div>'
  + '<div class="fld" data-fld="reason"><label>Lý do <span class="req">*</span></label><textarea data-model="reason"></textarea></div>'
  + '<div hidden><div class="fld" data-fld="hid"><label>Ẩn theo điều kiện <span class="req">*</span></label><input data-model="hid"></div></div>'
  + '<div class="fld" data-fld="_r1"><label>Người yêu cầu <span class="req">*</span></label><input readonly></div>'
  + '</div>';
const cfgOf = (d) => ({ draft: d, by: "Nguyễn <b>A</b>",
  hero: [["Người nhận", d.payee, "payee"], ["Số tiền", d.amount, "amount", "money"], ["Ngày", d.day, "day", "date"]],
  groups: [{ title: "Thanh toán", fields: [["Ngân hàng", d.bank, "bank"], ["Ghi chú", d.note, "note"], ["A", "1"], ["B", "2"], ["C", "3"]] },
    { title: "Nội dung", fields: [["Lý do", d.reason, "reason", "long"], null] },
    { title: "Các đợt", lines: [["Đợt 1", 1000000], ["Đợt 2", "2.500.000"]], total: true }],
  flow: "Direct Manager → Finance → CEO", after: ["Finance lập UNC"] });
{ const w = win(FORM); const S = w.EcSummary; const doc = w.document;
  const wrap = doc.querySelector(".x-formwrap");
  wrap.insertAdjacentHTML("beforeend", S.cardHTML("x-summary", '<div class="actions"><button class="btn" id="x-save">Lưu nháp</button><button class="btn primary" id="x-submit">Gửi yêu cầu</button></div>'));
  const host = doc.getElementById("x-summary");
  let d = { payee: '<img src=x onerror="alert(1)">', amount: 48500000, note: "—" };
  let st = S.render(host, cfgOf(d));
  const card = doc.getElementById("ec-sum");
  ok(card && card.classList.contains("ec-sum") && card.querySelector("#x-summary") && card.querySelector(".ec-sum-f #x-submit"), "khung: noi dung + thanh duoi chua nut cua trang (giu id)");
  ok(!card.querySelector("img"), "escape: khong sinh the img");
  ok(/onerror/.test(host.textContent), "escape: gia tri hien nguyen van");
  ok(!host.querySelector(".ec-sum-h b") && /Nguyễn <b>A<\/b>/.test(host.querySelector(".ec-sum-h p").textContent), "escape nguoi gui");
  const heroCells = [...host.querySelectorAll(".ec-sum-hc")];
  ok(heroCells.length === 3 && heroCells[2].classList.contains("is-num") && heroCells[2].getAttribute("data-sum-f") === "amount", "o so tien xep cuoi dai so chinh (mep phai)");
  ok(/48\.500\.000/.test(heroCells[2].textContent) && heroCells[2].querySelector(".ec-sum-num .ec-sum-cur") && /₫/.test(heroCells[2].textContent), "so tien dau cham + ₫ + tabular");
  ok(heroCells.filter((c) => c.classList.contains("is-lead")).length === 1 && heroCells[2].classList.contains("is-lead"), "3 o so chinh: o tien dan dau o man hep");
  const g1 = [...host.querySelectorAll(".ec-sum-g")][0].querySelectorAll(".ec-sum-c");
  const s4 = [...g1].map((c) => c.style.getPropertyValue("--ec-sum-s4").trim()).join(","), s2 = [...g1].map((c) => c.style.getPropertyValue("--ec-sum-s2").trim()).join(",");
  ok(s4 === "4,4,4,6,6" && s2 === "6,6,6,6,12", "nhom 5 o: 3+2 (may tinh), 2+2+1 (390px): " + s4 + " / " + s2);
  const lg = host.querySelector('.ec-sum-c.is-long[data-sum-f="reason"]');
  ok(lg && lg.style.getPropertyValue("--ec-sum-s4").trim() === "12" && lg.style.getPropertyValue("--ec-sum-s2").trim() === "12", "doan chu dai chiem tron hang");
  ok(host.querySelectorAll(".ec-sum-g").length === 3, "F null bi bo qua, nhom van ve");
  const tb = host.querySelector("table.ec-sum-lines");
  ok(tb && /3\.500\.000/.test(tb.querySelector("tfoot").textContent) && /Tổng cộng/.test(tb.querySelector("tfoot").textContent), "bang khoan chi co dong tong");
  // con thieu: bank, reason (cau hinh) + secret (o co sao khong nam trong cau hinh) ; khong tinh o an / o _r1
  ok(st.required === 5 && st.done === 2 && !st.ok, "dem bat buoc tu dau sao (ke ca o ngoai cau hinh), bo o an: " + JSON.stringify(st));
  const miss = st.missing.map((m) => m.field).sort().join(",");
  ok(miss === "bank,reason,secret,x".replace(",x", "") , "danh sach thieu: " + miss);
  const bank = host.querySelector('[data-sum-f="bank"]');
  ok(bank.classList.contains("is-miss") && bank.querySelector(".ec-sum-vl").textContent === "Cần nhập", "o thieu: 'Can nhap'");
  const note = host.querySelector('[data-sum-f="note"]');
  ok(note.classList.contains("is-none") && note.querySelector(".ec-sum-vl").textContent === "—", "o khong bat buoc de trong: '—' xam (ke ca gia tri '—')");
  ok(host.querySelector('[data-sum-f="day"]').classList.contains("is-none"), "khong khai req va khong co o tren form -> khong bat buoc");
  const msg = card.querySelector(".ec-sum-msg");
  ok(/Còn thiếu 3 mục/.test(msg.textContent) && msg.querySelectorAll("[data-sum-goto]").length === 3, "thanh duoi: con thieu + link: " + msg.textContent);
  ok(/Bắt buộc 2\/5/.test(host.querySelector(".ec-sum-prog").textContent), "tien do bat buoc x/y");
  ok(!doc.getElementById("x-submit").disabled, "khong tu khoa nut Gui");
  // bam link -> cuon + focus o nhap + nhay vien
  let scrolled = 0; w.HTMLElement.prototype.scrollIntoView = function () { scrolled++; };
  msg.querySelector('[data-sum-goto="secret"]').dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  ok(doc.activeElement === doc.querySelector('[data-model="secret"]') && scrolled === 1, "bam link -> focus dung o + cuon");
  ok(doc.querySelector('[data-fld="secret"]').classList.contains("ec-sum-flash"), "o duoc nhay vien");
  ok(S.goto("khong_co") === false && S.goto('x"]') === false, "goto o khong ton tai / ten la -> false, khong loi");
  // du truong -> thong diep xanh + buoc dau
  d = Object.assign(d, { bank: "VCB", reason: "OK", secret: "s" });
  st = S.render(host, cfgOf(d));
  ok(st.ok && /✓ Đủ thông tin\. Gửi xong, Direct Manager nhận phiếu đầu tiên/.test(msg.textContent) && card.classList.contains("is-ok"), "du: '✓ Du thong tin' + ai nhan phieu dau");
  ok(/✓ Đủ 5\/5/.test(host.querySelector(".ec-sum-prog").textContent), "tien do du");
  S.render(host, Object.assign(cfgOf(d), { resubmit: true }));
  ok(/có thể gửi lại/.test(msg.textContent), "dang gui lai: cau rieng");
  const chips = host.querySelectorAll(".ec-sum-chip");
  ok(chips.length === 4 && chips[3].classList.contains("is-after") && /Sau duyệt/.test(host.querySelector(".ec-sum-flow").textContent), "luong 1 dong + buoc sau duyet");
  ok(host.querySelectorAll(".ec-sum-sep").length === 2 && !host.querySelector(".ec-sum-chips").lastElementChild.lastElementChild.classList.contains("ec-sum-sep"), "dau › khong treo cuoi");
  // nhieu thieu -> rut gon
  const many = { groups: [{ title: "G", fields: Array.from({ length: 9 }, (_, i) => ({ label: "F" + i, value: "", field: "f" + i, req: 1 })) }] };
  S.render(host, many);
  ok(/Còn thiếu 9 mục/.test(msg.textContent) && msg.querySelectorAll("[data-sum-goto]").length === 6 && /và 3 mục khác/.test(msg.textContent), "qua 6 muc -> 'va N muc khac'");
  // nhan / ten nhom / buoc duyet / sau duyet cung duoc esc (khong chi gia tri)
  const ev = doc.createElement("div"); doc.body.appendChild(ev);
  S.render(ev, { hero: [["<i id=e1>H</i>", "1"]], groups: [{ title: "<i id=e2>G</i>", fields: [["<i id=e3>L</i>", "v"], ["<i id=e4>M</i>", ""]] }],
    flow: ["<i id=e5>B</i>"], after: ["<i id=e6>A</i>"] });
  ok(!ev.querySelector("i") && /<i id=e3>L<\/i>/.test(ev.textContent) && /<i id=e5>B<\/i>/.test(ev.textContent), "escape nhan, nhom, buoc duyet");
  // khong co khung (trang chua doi markup) -> van ve, thong diep nam trong host
  const lone = doc.createElement("div"); doc.body.appendChild(lone); S.render(lone, cfgOf({}));
  ok(lone.querySelector(".ec-sum-msg") && lone.querySelector(".ec-sum-hero"), "khong co khung: thong diep trong host");
}

// ---- 4. CSS / hooks --------------------------------------------------------------------------
{ const c = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
  ok(/#2f3a8f/i.test(c) && /#16a34a/i.test(c) && /#dc2626/i.test(c) && !/#2C3DA6|#1e8449/i.test(c) && !/gradient/i.test(c), "mau chuan, khong gradient");
  ok(/container-type:\s*inline-size/.test(c) && /@container \(max-width: 760px\)/.test(c), "tu co theo be rong khoi (390px)");
  ok(/@container[^{]*\{[\s\S]*grid-column: span var\(--ec-sum-s2/.test(c) && /grid-column: span var\(--ec-sum-s4/.test(c), "span 12 cot / 2 o dung bien do JS tinh");
  ok(/\.is-miss > \.ec-sum-lb::after/.test(c) && !/span::after/.test(c) && (c.match(/::after/g) || []).length === 1, "mot cham do duy nhat (sau nhan)");
  ok(/\.btn\[disabled\][^}]*opacity: 1/.test(c), "nut khoa: nen xam dac, khong mo");
  ok(/border-radius: 12px/.test(c) && /font-variant-numeric: tabular-nums/.test(c), "bo 12px, so tabular");
  ok(/web_include_js\.append\("ec_summary\.bundle\.js"\)/.test(HOOKS) && /web_include_css\.append\("ec_summary\.bundle\.css"\)/.test(HOOKS), "hooks nap asset");
}

// ---- 5. moi form: khai cau hinh, khong tu dung HTML tom tat -----------------------------------
const forms = fs.readdirSync(FEAT).filter((f) => fs.existsSync(path.join(FEAT, f, "ui", "main_section.html")));
const using = [];
for (const f of forms) {
  const html = fs.readFileSync(path.join(FEAT, f, "ui", "main_section.html"), "utf8");
  if (!/EcSummary\./.test(html)) continue;
  using.push(f);
  ok(!/<h3>Tóm tắt<\/h3>/.test(html) && !/summary-row"><span>'\+esc\(r\[0\]\)/.test(html), f + ": bo khoi tom tat tu dung");
  ok(/EcSummary\.cardHTML\("[a-z]+-summary",actions\)/.test(html) && /EcSummary\.render\(h,\{/.test(html), f + ": markup khung + render cau hinh");
  ok(!/<(script|style) id="ec-sum/.test(html), f + ": khong chen khoi ec- moi (A65)");
}
ok(using.length === 32, "32 form dung khoi chung: " + using.length);

// ---- 6. chay that tung form tren jsdom (tab Tao moi) ------------------------------------------
// chi mo form tu phieu tra lai (khong co form Tao moi): Clearance, Danh gia NS, Chuan bi NS moi, Data Request (da chuyen /du-lieu)
const SKIP_RUN = { clearance_request: 1, employee_review: 1, new_staff_preparation: 1, data_request: 1 };
for (const f of using) {
  if (SKIP_RUN[f]) continue;
  if (process.env.TT_DEBUG) console.log("RUN " + f);
  if (process.env.TT_ONLY && process.env.TT_ONLY !== f) continue;
  const html = fs.readFileSync(path.join(FEAT, f, "ui", "main_section.html"), "utf8");
  const i = html.search(/<script[^>]*id="ec-[^"]+"[^>]*>/);
  const js = html.slice(i).replace(/^<script[^>]*>/, "").replace(/<\/script>\s*$/, "");
  const route = (fs.readFileSync(path.join(FEAT, f, "infrastructure", "page_sync.py"), "utf8").match(/ROUTE = "([^"]+)"/) || [])[1];
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + html.slice(0, i) + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/" + route + "?tab=create" + (f === "offer_request" ? "&hiring=EC-HIRE-1" : "") });
  const w = dom.window;
  w.HTMLElement.prototype.scrollIntoView = function () {};
  w.frappe = { csrf_token: "x", session: { user: "u@x" }, call: (o) => { const m = o.method.split(".").pop();
    if (m === "get_bootstrap") return Promise.resolve({ message: { tabs: { create: true, my_requests: true, my_approvals: true }, context: { user: "u@x", employee_name: "U", department: "D" }, form_options: {}, options: {} } });
    if (m === "hiring_prefill") return Promise.resolve({ message: { hiring_request: "EC-HIRE-1", position: "Content Creator", department: "Marketing" } });
    return Promise.resolve({ message: { rows: [], total: 0, data: [] } }); } };
  w.eval(MONEY); w.eval(JS);
  let err = null; try { w.eval(js); } catch (e) { err = e; }
  await flush();
  const card = w.document.getElementById("ec-sum");
  ok(!err && card, f + ": trang chay, co khoi tom tat " + (err || ""));
  if (!card) continue;
  ok(card.querySelector(".ec-sum-f .actions .btn.primary") && card.querySelector(".ec-sum-h h3").textContent === "Tóm tắt", f + ": nut nam o thanh duoi, Gui o phai");
  const prog = card.querySelector(".ec-sum-prog");
  const req = w.document.querySelectorAll(".fld[data-fld] label .req").length;
  ok(!req || (prog && /Bắt buộc 0\/|Bắt buộc \d+\//.test(prog.textContent)), f + ": tien do bat buoc hien");
  // go vao o bat buoc dau tien -> tom tat cap nhat (link thieu cua o do bien mat)
  const first = [...card.querySelectorAll(".ec-sum-msg [data-sum-goto]")].map((b) => b.getAttribute("data-sum-goto"))
    .map((k) => w.document.querySelector('[data-fld="' + k + '"] input[data-model="' + k + '"]:not([type=hidden]):not([type=checkbox]):not([type=date]):not([data-ec-people]), [data-fld="' + k + '"] textarea[data-model="' + k + '"]'))
    .filter(Boolean)[0];
  if (first) {
    const k = first.getAttribute("data-model");
    first.value = "12"; first.dispatchEvent(new w.Event("input", { bubbles: true })); await flush();
    const card2 = w.document.getElementById("ec-sum");
    ok(!card2.querySelector('.ec-sum-msg [data-sum-goto="' + k + '"]'), f + ": go o '" + k + "' -> het bao thieu");
  }
}
console.log(`${pass} dat, ${fail} hong`); process.exit(fail ? 1 : 0);
