// Copyright (c) 2026, eCentric and contributors
// /ai-live/ban-quyen (17/11): trang Ban quyen AI Live - 4 o so, Cho duyet + duyet nhieu may, Khoa co hop thoai
// (nhac "lan mo app sau" + nhac khi Chi ghi nhan), doi cong tac phai xac nhan, link sau #may-LIC-…, cay phan phoi,
// chu tu may gui len hien nguyen chu (khong chay), 403 bao khong co quyen, khong Jinja trong trang.
//     node ecentric_workspace/ai_tools/tests/js/test_ai_live_ban_quyen_page.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const HTML = readFileSync(join(here, "..", "..", "pages", "ai_live_ban_quyen", "main_section.html"), "utf8");
const i = HTML.lastIndexOf("<script>");
const markup = HTML.slice(0, i), JS = HTML.slice(i + 8).replace(/<\/script>\s*$/, "");
let oks = 0, fails = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  HONG: " + n); } };
const flush = async () => { for (let k = 0; k < 12; k++) await new Promise((r) => setTimeout(r, 3)); };
const env = (data) => [200, { message: { success: true, message: "", data } }];

const NOW = "2026-11-17 20:00:00";
const apps = (on) => ["elive", "esync", "evoice"].map((p) => ({ product: p, label: { elive: "eLive", esync: "eSync", evoice: "eVoice" }[p], installed: on.includes(p), build_id: "1.0.40", last_checkin: "", waiting: false }));
const row = (name, over) => Object.assign({ name, label: "", host: "MAY-" + name.slice(-1), win_user: "live", status: "pending", apps: apps(["elive"]),
  dist: { name: "d1", label: "Gói Lix" }, parent: { name: "LIC-00001", label: "Máy Lix 1" }, reason: "bản chép từ máy LIC-00001 – chờ duyệt",
  last_ip: "1.2.3.4", last_seen: "2026-11-17 19:55:00.123456", first_seen: "", clone_warning: 0, blocked_manual: 0, via_checkin: 0 }, over || {});
const SUM = (mode) => ({ counts: { pending: 2, running: 5, blocked: 1, clone: 1 }, mode: Object.assign({ enabled: 1, log_only: 0, killed: 0 }, mode || {}),
  secrets: { elive: "ok", esync: "missing", evoice: "ok", dist: "ok" }, teams: true, office_ips: 1, now: NOW });
function routes(over) {
  return Object.assign({
    summary: env(SUM()),
    list_dists: env({ rows: [{ name: "d1", label: "Gói Lix", package_label: "Gói Lix", kind: "khach", kind_label: "Khách", package: "p1", created_at: "2026-11-10T00:00:00Z", first_machine: { name: "LIC-00001", label: "Máy Lix 1" }, first_seen: "", issued: 1, pending: 1 }], no_dist_pending: 1 }),
    list_machines: env({ rows: [row("LIC-00002", { host: "<img src=x onerror=alert(1)>" }), row("LIC-00003", { dist: { name: "", label: "" }, parent: { name: "", label: "" }, last_seen: "2026-11-10 08:00:00" })], more: false, now: NOW, stale_days: 3 }),
    get_machine: env({ machine: Object.assign(row("LIC-00002"), { os: "Windows-10", first_ip: "1.2.3.4", note: "", approved_by: "", approved_at: "", block_message: "", clone_host: "", dist_kind: "Khách" }),
      installs: [{ product: "elive", label: "eLive", build_id: "1.0.40", app_dir: "C:\\eLive", license_issued_at: "", last_checkin: "", last_checkin_ip: "", reissued_at: "", waiting: true }],
      events: [{ at: "2026-11-17 19:50:00", machine: "LIC-00002", product: "elive", kind: "pending", ip: "1.2.3.4", user: "Guest", detail: "bản chép" }],
      children: [], log_only: 0, default_block: "Máy này đã bị eCentric khoá. Liên hệ người phụ trách." }),
    approve: (b) => env({ approved: b.names, skipped: [], message: "Đã duyệt – app trên máy đó tự mở trong khoảng 30 giây." }),
    block: (b) => env({ name: b.name, log_only: 0 }),
    set_mode: (b) => env({ enabled: b.enabled, log_only: b.log_only }),
    tree: env({ tree: [{ name: "d1", label: "Gói Lix", kind: "khach", kind_label: "Khách", machines: [{ name: "LIC-00001", label: "Máy Lix 1", host: "A", status: "approved", children: [{ name: "LIC-00002", label: "", host: "B", status: "pending", children: [] }] }] },
      { name: "", label: "không có mã gói", kind: "", machines: [{ name: "LIC-00003", label: "", host: "C", status: "pending", children: [] }] }] }),
    events: env({ rows: [], more: false, kinds: [] }),
  }, over || {});
}
function boot(r, hash) {
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url: "https://x.test/ai-live/ban-quyen" + (hash || ""), pretendToBeVisual: true });
  const w = dom.window; w.__calls = [];
  w.frappe = { csrf_token: "CSRF1" };
  w.fetch = (u, o) => {
    const url = new URL(u, "https://x.test"), method = url.pathname.split(".").pop();
    const body = o && typeof o.body === "string" ? JSON.parse(o.body) : null;
    w.__calls.push({ method, qs: Object.fromEntries(url.searchParams), body, verb: (o && o.method) || "GET", headers: (o && o.headers) || {} });
    const h = r[method];
    const [status, payload] = h ? (typeof h === "function" ? h(body, url.searchParams) : h) : [404, {}];
    return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(payload) });
  };
  w.HTMLElement.prototype.scrollIntoView = function () {};
  w.eval(JS);
  return w;
}
const q = (w, s) => w.document.querySelector(s);
const qa = (w, s) => Array.prototype.slice.call(w.document.querySelectorAll(s));
const calls = (w, m) => w.__calls.filter((c) => c.method === m);

ok(!/\{\{|\{%|\{#|%\}|#\}/.test(HTML), "khong co cu phap Jinja trong trang");
ok(HTML.includes('data-ec-shell="1"') && HTML.includes("ec-shell-nav"), "vo shell tinh co san");

// 1. Mo trang: 4 o so, tab Cho duyet, chu tu may hien nguyen chu
{ const w = boot(routes()); await flush();
  ok(qa(w, "#lc-stats b").map((b) => b.textContent).join(",") === "2,5,1,1", "4 o so");
  ok(q(w, "#lc-tabn").textContent === "2" && !q(w, "#lc-tabn").hidden, "so cho duyet tren tab");
  ok(calls(w, "list_machines")[0].qs.filters.includes('"tab":"pending"'), "mac dinh tab Cho duyet");
  ok(!q(w, "#lc-view img") && /<img src=x/.test(q(w, "#lc-view").textContent), "host <img onerror> hien nguyen chu, khong chay");
  ok(/eSync thiếu/.test(q(w, "#lc-keys").textContent), "bao thieu khoa eSync (khong lo noi dung)");
  ok(/Chưa có khoá ký eSync/.test(q(w, "#lc-bands").textContent), "bang nhac dan khoa");
  ok(/mất liên lạc/.test(q(w, '[data-open="LIC-00003"] [data-k="seen"]').textContent), "qua 3 ngay -> mat lien lac");
  ok(/5 phút trước/.test(q(w, '[data-open="LIC-00002"] [data-k="seen"]').textContent), "bao ve tuong doi");
  ok(/không có mã gói/.test(q(w, '[data-open="LIC-00003"]').textContent), "may khong co ma goi");
  // duyet nhieu may
  qa(w, "[data-pick]").forEach((c) => c.click()); await flush();
  ok(/Duyệt 2 máy/.test(q(w, "#lc-bulk").textContent) && !q(w, "#lc-bulk").disabled, "chon 2 may -> nut duyet hang loat");
  q(w, "#lc-bulk").click(); await flush();
  const ap = calls(w, "approve")[0];
  ok(ap && ap.verb === "POST" && ap.body.names.join() === "LIC-00002,LIC-00003" && ap.headers["X-Frappe-CSRF-Token"] === "CSRF1", "POST approve 2 may + CSRF");
  ok(q(w, "#lc-drawer").hidden, "bam o chon khong mo ngan chi tiet");
}

// 2. Khoa: hop thoai co loi nhan dien san + nhac lan mo app sau; Chi ghi nhan -> nhac them
{ const w = boot(routes({ summary: env(SUM({ log_only: 1 })) })); await flush();
  ok(/chỉ ghi nhận/.test(q(w, "#lc-bands").textContent), "bang vang Chi ghi nhan");
  q(w, '[data-open="LIC-00002"] [data-block]').click(); await flush();
  ok(!q(w, "#lc-modal").hidden && q(w, "#lc-bmsg").value === "Máy này đã bị eCentric khoá. Liên hệ người phụ trách.", "hop thoai khoa + loi nhan mac dinh");
  ok(/lần mở app sau/.test(q(w, "#lc-mbox").textContent) && /khoá chưa có hiệu lực/.test(q(w, "#lc-mbox").textContent), "nhac lan mo app sau + chi ghi nhan");
  ok(q(w, "#lc-drawer").hidden, "bam Khoa tren dong khong mo ngan");
  q(w, "#lc-bmsg").value = "Gọi anh Hoàn";
  q(w, "[data-confirm-block]").click(); await flush();
  const b = calls(w, "block")[0];
  ok(b && b.body.name === "LIC-00002" && b.body.message === "Gọi anh Hoàn", "POST block kem loi nhan");
  ok(q(w, "#lc-modal").hidden, "xong dong hop thoai");
}

// 3. Cong tac: phai xac nhan, chua doi truoc khi xac nhan
{ const w = boot(routes()); await flush();
  const lo = q(w, "#lc-logonly"); lo.checked = true; lo.dispatchEvent(new w.Event("change", { bubbles: true })); await flush();
  ok(!lo.checked && !q(w, "#lc-modal").hidden, "doi cong tac -> hoi xac nhan, chua doi");
  q(w, "[data-confirm-mode]").click(); await flush();
  const m = calls(w, "set_mode")[0];
  ok(m && m.body.enabled === 1 && m.body.log_only === 1, "xac nhan -> set_mode(enabled=1, log_only=1)");
}

// 4. Link sau tu tin Teams mo dung may
{ const w = boot(routes(), "#may-LIC-00002"); await flush();
  ok(!q(w, "#lc-drawer").hidden && calls(w, "get_machine")[0].qs.name === "LIC-00002", "#may-LIC-00002 mo ngan chi tiet dung may");
  ok(/Lịch sử/.test(q(w, "#lc-dbox").textContent) && q(w, "#lc-dbox [data-approve]"), "ngan chi tiet co lich su + nut Duyet");
  w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  ok(q(w, "#lc-drawer").hidden && !/may-/.test(w.location.hash), "Esc dong ngan, bo hash");
}

// 5. Cay phan phoi: goi -> may dau -> ban chep; tim may tu mo toi may
{ const w = boot(routes(), "#tab-tree"); await flush();
  ok(q(w, '.lc-tree [data-open="LIC-00001"] + ul [data-open="LIC-00002"]'), "ban chep nam duoi may dau");
  ok(/không có mã gói/.test(q(w, ".lc-tree").textContent), "nhanh khong co ma goi");
  const t = q(w, "#lc-tq"); t.value = "lic-00003"; t.dispatchEvent(new w.Event("input", { bubbles: true }));
  ok(q(w, '[data-open="LIC-00003"]').classList.contains("hit"), "tim may -> to sang node");
  q(w, '.lc-tree [data-open="LIC-00002"]').click(); await flush();
  ok(!q(w, "#lc-drawer").hidden, "bam node mo ngan chi tiet");
}

// 6. Khong co quyen
{ const w = boot(routes({ summary: [403, { message: { success: false, message: "Chỉ quản trị Bản quyền AI Live được làm việc này.", data: null } }] })); await flush();
  ok(/không có quyền|Chỉ quản trị/.test(q(w, "#ec-aiv-root").textContent) && !calls(w, "list_machines").length, "403 -> bao khong co quyen, khong tai bang");
}

console.log((fails ? "THAT BAI" : "OK") + ": " + oks + " dung, " + fails + " hong");
process.exit(fails ? 1 : 0);
