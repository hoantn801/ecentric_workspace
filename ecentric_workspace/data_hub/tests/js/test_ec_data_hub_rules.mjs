// Trung tam Du lieu dot 3 - ec_data_hub_rules.bundle.js (trang /du-lieu/quy-tac) tren HTML THAT
// (fixture render tu rules_service + jinja: test_data_hub_d3.TestRulesFixtures). Nap ca bundle chung
// (ECDataHub.call / busy) roi bundle quy tac - dung thu tu trang that.
//     node ecentric_workspace/data_hub/tests/js/test_ec_data_hub_rules.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
const FIX = join(here, "fixtures");
const MAIN = readFileSync(join(APP, "public", "js", "ec_data_hub.bundle.js"), "utf8");
const RULES = readFileSync(join(APP, "public", "js", "ec_data_hub_rules.bundle.js"), "utf8");
const CSS = readFileSync(join(APP, "public", "css", "ec_data_hub_rules.bundle.css"), "utf8");
const API = JSON.parse(readFileSync(join(FIX, "rules_api.json"), "utf8"));
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const eq = (a, b, n) => ok(JSON.stringify(a) === JSON.stringify(b), n + " -> " + JSON.stringify(a) + " != " + JSON.stringify(b));
const sorted = (o) => Object.keys(o).sort().reduce((a, k) => { a[k] = o[k]; return a; }, {});
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setTimeout(r, 2)); };

async function page(name, { failOn = {} } = {}) {
  const html = readFileSync(join(FIX, name + ".html"), "utf8");
  const dom = new JSDOM(html, { url: "https://team.ecentric.vn/du-lieu/quy-tac", runScripts: "outside-only", pretendToBeVisual: true });
  const w = dom.window;
  const calls = [];
  w.__edhNoReload = true;
  w.frappe = { csrf_token: "tok" };
  w.fetch = (u, opts = {}) => {
    const method = u.split("data_hub.api.")[1].split("?")[0];
    const args = opts.method === "POST" ? JSON.parse(opts.body || "{}") : {};
    calls.push({ method, args, post: opts.method === "POST", csrf: (opts.headers || {})["X-Frappe-CSRF-Token"] });
    const fail = failOn[method];
    return new Promise((res) => setTimeout(() => res({ ok: !fail, status: fail ? 417 : 200,
      json: () => Promise.resolve({ message: { success: !fail, message: fail || "", data: fail ? null : { name: "SLA-v2" } } }) }), 3));
  };
  w.eval(MAIN);
  w.eval(RULES);
  await flush();
  return { w, d: w.document, calls, P: w.ECDataHubRules };
}

// ------------------------------------------------------------------ validate = server ------
{
  const { w, d, P } = await page("rules_team");
  const boot = JSON.parse(d.getElementById("edh-boot").textContent);
  for (const c of API.validate) {
    const res = P.validate(c.input, boot);
    const label = JSON.stringify(c.input);
    if (c.ok) {
      eq(res.errors, [], "JS nhan nhu server: " + label);
      eq(sorted(res.days), sorted(c.days), "so ngay giong server: " + label);
      eq(sorted(res.mult), sorted(c.mult), "he so giong server: " + label);
      eq(res.changes, c.changes, "so thay doi giong server: " + label);
    } else {
      ok(res.errors.length > 0, "JS chan nhu server: " + label);
      eq(res.errors, c.errors, "thong diep loi giong server: " + label);
    }
  }
  eq(P.parseNum("0,5"), 0.5, "parseNum dau phay");
  eq(P.parseNum("1e3"), null, "parseNum khong nhan so mu");
  eq(P.fmtMult(1.5), "1,5", "fmtMult");
  ok(w.ECDataHubRules.page && w.ECDataHubRules.page.root, "boot tren trang quy tac");
}

// ------------------------------------------------------------------ team Data: de xuat -----
{
  const { w, d, calls } = await page("rules_team");
  const root = d.querySelector("[data-edh-rules]");
  ok(!root.classList.contains("is-editing"), "trang thai dau: xem (o nhap an bang CSS)");
  ok(/\.edh-rules \.edh-rules-edit\{display:none\}/.test(CSS) && /\.edh-rules\.is-editing \.edh-rules-view\{display:none\}/.test(CSS),
     "CSS an / hien theo .is-editing");
  d.querySelector("[data-edh-rules-edit]").click();
  ok(root.classList.contains("is-editing"), "bam Sua quy tac -> che do sua");
  eq(d.activeElement && d.activeElement.getAttribute("data-edh-rules-days"), "pbi_new", "focus o dau tien");
  const pbi = d.querySelector('[data-edh-rules-days="pbi_new"]');
  pbi.value = "10";
  pbi.dispatchEvent(new w.Event("input", { bubbles: true }));
  ok(pbi.classList.contains("is-changed"), "o doi -> to mau");
  eq(d.querySelector("[data-edh-rules-count]").textContent, "1 thay đổi so với quy tắc đang áp dụng.", "dem thay doi");
  const intake = d.querySelector('[data-edh-rules-days="intake"]');
  intake.value = "0";
  intake.dispatchEvent(new w.Event("input", { bubbles: true }));
  eq(intake.getAttribute("aria-invalid"), "true", "o sai -> aria-invalid");
  const send = d.querySelector('[data-edh-rules-send="edit"]');
  send.click();
  await flush();
  eq(calls.length, 0, "so sai -> khong goi server");
  ok(/số ngày từ 1 đến 60/.test(d.querySelector("[data-edh-rules-err]").textContent), "bao loi so ngay");
  ok(/Ghi lý do/.test(d.querySelector("[data-edh-rules-err]").textContent), "gui duyet ma thieu ly do -> bao");
  intake.value = "1";
  const mult = d.querySelector('[data-edh-rules-mult="Khẩn"]');
  mult.value = "0,6";
  d.querySelector("[data-edh-rules-reason]").value = "Dashboard mới cần 3+ nguồn";
  d.querySelector("[data-edh-rules-save]").click();
  await flush();
  eq(calls.map((c) => c.method), ["save_rule_draft"], "Luu nhap -> save_rule_draft");
  eq(calls[0].args.data.submit, 0, "luu nhap: submit 0");
  eq(calls[0].args.data.days.pbi_new, 10, "so ngay moi");
  eq(calls[0].args.data.mult["Khẩn"], 0.6, "he so moi (dau phay -> so)");
  ok(calls[0].post && calls[0].csrf === "tok", "POST kem CSRF");
  ok(w.__edhReloaded, "xong -> tai lai trang");
  send.click();
  await flush();
  eq(calls.length, 2, "Gui duyet");
  eq(calls[1].args.data.submit, 1, "gui duyet: submit 1");
  eq(calls[1].args.data.reason, "Dashboard mới cần 3+ nguồn", "ly do di kem");
  d.querySelector("[data-edh-rules-cancel-edit]").click();
  ok(!root.classList.contains("is-editing"), "Thoi -> ve che do xem");
  eq(pbi.value, "7", "Thoi -> tra o ve gia tri ban dau");
}

// ------------------------------------------------------------------ loi server + bam 2 lan --
{
  const { w, d, calls } = await page("rules_team", { failOn: { save_rule_draft: "Linh Vương đang có bản nháp v2 - mỗi lúc chỉ một thay đổi quy tắc." } });
  d.querySelector("[data-edh-rules-edit]").click();
  const pbi = d.querySelector('[data-edh-rules-days="pbi_new"]');
  pbi.value = "9";
  const save = d.querySelector("[data-edh-rules-save]");
  save.click();
  save.click();
  await flush();
  eq(calls.length, 1, "bam 2 lan -> 1 lan goi");
  ok(/mỗi lúc chỉ một thay đổi/.test(d.querySelector("[data-edh-rules-err]").textContent), "loi server hien trong khung sua");
  ok(!w.__edhReloaded, "loi -> khong tai lai");
}

// ------------------------------------------------------------------ ban nhap cua toi --------
{
  const { d, calls } = await page("rules_draft");
  ok(/Bạn đang có bản nháp v2/.test(d.body.textContent), "bang ban nhap");
  eq(d.querySelector('[data-edh-rules-days="pbi_new"]').value, "10", "o sua mang gia tri ban nhap");
  d.querySelector('[data-edh-rules-send="view"]').click();
  await flush();
  eq(calls.map((c) => [c.method, c.args.name]), [["submit_rule", "SLA-v2"]], "Gui duyet ban nhap da co ly do");
  d.querySelector('[data-edh-rules-ask="discard"]').click();
  const panel = d.querySelector("[data-edh-rules-panel]");
  ok(!panel.hidden, "Huy ban nhap -> hoi xac nhan tai cho");
  eq(d.querySelector("[data-edh-rules-panel-ok]").textContent, "Huỷ bản nháp", "nut xac nhan dung viec");
  d.querySelector("[data-edh-rules-panel-ok]").click();
  await flush();
  eq(calls[1].method, "cancel_rule", "xac nhan -> cancel_rule");
}

// ------------------------------------------------------------------ nguoi duyet --------------
{
  const { w, d, calls } = await page("rules_approver", { failOn: {} });
  ok(/chờ bạn duyệt/.test(d.querySelector("[data-edh-rules-banner]").textContent), "bang cho nguoi duyet");
  eq(d.querySelectorAll("[data-edh-rules-days]").length, 0, "nguoi duyet khong co o sua");
  d.querySelector('[data-edh-rules-ask="reject"]').click();
  ok(d.querySelector("[data-edh-rules-panel]").classList.contains("is-reject"), "khung tu choi");
  d.querySelector("[data-edh-rules-panel-ok]").click();
  await flush();
  eq(calls.length, 0, "tu choi khong ly do -> khong goi");
  ok(/lý do từ chối/.test(d.querySelector("[data-edh-rules-panel-err]").textContent), "bao can ly do");
  d.querySelector("[data-edh-rules-note]").value = "7 ngày vẫn đủ";
  d.querySelector("[data-edh-rules-panel-ok]").click();
  await flush();
  eq(calls.map((c) => [c.method, c.args.verdict, c.args.note]), [["decide_rule", "reject", "7 ngày vẫn đủ"]], "Tu choi kem ly do");
  d.querySelector('[data-edh-rules-ask="approve"]').click();
  ok(!d.querySelector("[data-edh-rules-panel]").classList.contains("is-reject"), "khung duyet");
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  ok(d.querySelector("[data-edh-rules-panel]").hidden, "Esc dong khung");
  d.querySelector('[data-edh-rules-ask="approve"]').click();
  d.querySelector("[data-edh-rules-panel-ok]").click();
  await flush();
  eq([calls[1].method, calls[1].args.verdict, calls[1].args.name], ["decide_rule", "approve", "SLA-v2"], "Duyet");
}
{
  const { d, calls } = await page("rules_approver", { failOn: { decide_rule: "Bản v2 không ở trạng thái chờ duyệt (đang: Đang áp dụng). Tải lại trang." } });
  d.querySelector('[data-edh-rules-ask="approve"]').click();
  d.querySelector("[data-edh-rules-panel-ok]").click();
  await flush();
  eq(calls.length, 1, "goi 1 lan");
  ok(/Tải lại trang/.test(d.querySelector("[data-edh-rules-panel-err]").textContent), "loi server hien trong khung");
}

// ------------------------------------------------------------------ 390px ------------------
ok(/@media \(max-width:640px\)\{[^@]*\.edh-rules-tbl tr\{display:grid !important/.test(CSS), "390px: bang quy tac thanh the");
ok(!/(^|\})\s*(body|html|\*|a|button|table|input)\s*[{,]/.test(CSS), "CSS khong dung selector tran");

console.log(`${oks} dat, ${fails} hong`);
process.exit(fails ? 1 : 0);
