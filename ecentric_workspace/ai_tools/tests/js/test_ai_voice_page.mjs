// Copyright (c) 2026, eCentric and contributors
// /ai-voice (15/11): trang Giong doc AI - quyen theo vai tro (nguoi dung / quan ly / System Manager),
// nut Doc chi bat khi du dieu kien, gui dung payload, chong XSS, may mat ket noi, poll cap nhat phieu,
// 403 co huong di tiep, khong Jinja trong trang.
//     node ecentric_workspace/ai_tools/tests/js/test_ai_voice_page.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const HTML = readFileSync(join(here, "..", "..", "pages", "ai_voice", "main_section.html"), "utf8");
const i = HTML.lastIndexOf("<script>");
const markup = HTML.slice(0, i), JS = HTML.slice(i + 8).replace(/<\/script>\s*$/, "");
let oks = 0, fails = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  HONG: " + n); } };
const flush = async () => { for (let k = 0; k < 10; k++) await new Promise((r) => setTimeout(r, 3)); };

const QUAL = [["quality_lightning", "Nhanh", "15 bước"], ["quality_fast", "Chuẩn", "20 bước"], ["quality_standard", "Cao", "32 bước"], ["quality_ultra", "Tối đa", "50 bước"]]
  .map(([value, label, hint]) => ({ value, label, hint }));
function state(over) {
  return Object.assign({
    user: "u@x", is_manager: false, is_admin: false, configured: true,
    defaults: { quality: "quality_fast", speed: 1.1, language: "vi" }, qualities: QUAL,
    languages: [{ value: "vi", label: "Tiếng Việt" }, { value: "en", label: "Tiếng Anh" }], genders: ["Nữ", "Nam", "Khác"],
    limits: { max_chars: 15000, speed_min: 0.5, speed_max: 2, max_active: 10, max_voice_mb: 25, voice_exts: [".wav", ".mp3"] },
    voices: [
      { name: "P1", voice_id: "v1", voice_name: "Lan", gender: "Nữ", status: "active", has_consent: true, restricted: 0 },
      { name: "P2", voice_id: "v2", voice_name: "Minh", gender: "Nam", status: "active", has_consent: true, restricted: 0 },
    ],
    jobs: [],
  }, over || {});
}
const env = (data) => [200, { message: { success: true, message: "", data } }];
function boot(routes, opts) {
  opts = opts || {};
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + markup + "</body></html>", { runScripts: "outside-only", url: "https://x.test/ai-voice" + (opts.hash || ""), pretendToBeVisual: true });
  const w = dom.window; w.__calls = [];
  w.frappe = { csrf_token: "CSRF1", session: { user: opts.guest ? "Guest" : "u@x" } };
  w.fetch = (u, o) => {
    const url = new URL(u, "https://x.test"), method = url.pathname.split(".").pop();
    const body = o && o.body && typeof o.body === "string" ? JSON.parse(o.body) : null;
    w.__calls.push({ method, qs: Object.fromEntries(url.searchParams), body, headers: (o && o.headers) || {}, verb: (o && o.method) || "GET" });
    const h = routes[method];
    const [status, payload] = h ? (typeof h === "function" ? h(body, url.searchParams) : h) : [404, {}];
    return Promise.resolve({ ok: status < 400, status, headers: { get: () => "application/json" }, json: () => Promise.resolve(payload) });
  };
  w.HTMLMediaElement.prototype.play = () => Promise.resolve();
  w.HTMLMediaElement.prototype.pause = () => {};
  w.eval(JS);
  return w;
}
const $ = (w, s) => w.document.querySelector(s);
const $$ = (w, s) => [...w.document.querySelectorAll(s)];
const typeText = (w, id, v) => { const t = w.document.getElementById(id); t.value = v; t.dispatchEvent(new w.Event("input", { bubbles: true })); };

// 0. Trang khong chua cu phap Jinja (Web Page render qua Jinja -> vo trang)
ok(!/\{\{|\{%|\{#/.test(HTML), "khong co {{ / {% / {# trong trang");
ok(HTML.includes('data-ec-shell="1"') && HTML.includes('ec-shell-active" href="/ai-voice"'), "vo shell tinh co san, muc Giong doc AI dang sang");

// 1. Nguoi dung thuong: 3 tab, khong co Cai dat, khong co nut quan ly giong
{ const w = boot({ get_state: env(state()), machine_status: env({ online: true, ready: true, voices: 2, engine: "PV" }), list_jobs: env({ jobs: [] }) });
  await flush();
  const tabs = $$(w, "#av-tabs [role=tab]").map((t) => t.textContent);
  ok(tabs.length === 3 && !tabs.some((t) => /Cài đặt/.test(t)), "nguoi dung khong thay tab Cai dat");
  ok(/Máy sẵn sàng/.test($(w, "#av-machine").textContent), "chip may sẵn sàng");
  const gen = $(w, '[data-act="create"]');
  ok(gen.disabled, "chua nhap noi dung -> nut Doc tat");
  ok(/Nhập nội dung/.test($(w, "#av-gen-hint").textContent), "goi y vi sao nut tat");
  typeText(w, "av-text", "Xin chào cả nhà");
  ok(gen.disabled && /Chọn giọng/.test($(w, "#av-gen-hint").textContent), "co chu nhung chua chon giong -> van tat (2 giong, khong tu chon)");
  $(w, '[data-act="pick-voice"]').click(); await flush();
  ok(!$(w, "#av-modal").hidden && $$(w, '#av-pick-list [data-act="pick"]').length === 2, "popup chon giong liet ke giong dung duoc");
  $$(w, '#av-pick-list [data-act="pick"]')[1].click(); await flush();
  ok($(w, "#av-modal").hidden, "chon xong dong popup");
  ok(/Minh/.test($(w, ".av-vsel").textContent), "the giong hien giong da chon");
  ok(!$(w, '[data-act="create"]').disabled, "du dieu kien -> nut Doc bat");
  $(w, '[data-act="pick-voice"]').click(); await flush();
  w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  ok($(w, "#av-modal").hidden, "Esc dong popup");
  $(w, '[data-tab="giong"]').click(); await flush();
  ok(!$(w, '[data-act="add-voice"]') && !$(w, '[data-act="edit-voice"]') && !$(w, '[data-act="sync-voices"]'), "nguoi dung khong co nut them / sua / dong bo giong");
  ok($$(w, ".av-vcard").length === 2, "thu vien hien 2 giong");
}

// 2. Tao phieu: payload dung, CSRF, phieu moi hien o Phieu gan day, poll cap nhat -> Xong
{ let jobsState = [];
  const created = { name: "J1", title: "Bài <b>1</b>", status: "pending", voice_label: "Lan", quality: "quality_fast", chars: 12, owner: "u@x", creation: "2026-11-15 09:00:00", has_audio: false };
  const w = boot({
    get_state: env(state({ voices: [state().voices[0]] })), machine_status: env({ online: true, ready: true, voices: 1 }),
    create_job: () => env(created), list_jobs: () => env({ jobs: jobsState }),
  });
  await flush();
  ok(/Lan/.test($(w, ".av-vsel").textContent), "chi 1 giong -> tu chon san");
  typeText(w, "av-text", "Xin chào <script>x</script>");
  typeText(w, "av-title-in", "Bài <b>1</b>");
  $(w, '[data-q="quality_standard"]').click();
  const sp = $(w, "#av-speed"); sp.value = "1.3"; sp.dispatchEvent(new w.Event("input", { bubbles: true }));
  $(w, '[data-act="breath"]').click();
  $(w, '[data-act="create"]').click(); await flush();
  const c = w.__calls.find((x) => x.method === "create_job");
  ok(c && c.verb === "POST" && c.headers["X-Frappe-CSRF-Token"] === "CSRF1", "POST kem CSRF");
  ok(c && c.body.data.voice === "profile:P1" && c.body.data.quality === "quality_standard" && c.body.data.speed === 1.3 && c.body.data.breath === 0 && c.body.data.text === "Xin chào <script>x</script>",
    "payload dung giong / chat luong / toc do / lay hoi / noi dung nguyen van");
  const row = $(w, '#av-recent [data-job="J1"]');
  ok(row && /Đang chờ gửi/.test(row.textContent), "phieu moi hien ngay o Phieu gan day");
  ok(row && !row.querySelector("b").innerHTML.includes("<b>1") && row.querySelector("b").textContent === "Bài <b>1</b>", "tieu de duoc escape (chong XSS)");
  ok(!$(w, "#av-recent script"), "khong chen the script");
  jobsState = [Object.assign({}, created, { status: "running", progress: "2/4" })];
  await new Promise((r) => setTimeout(r, 1700)); await flush();
  ok(/Đang đọc · 50%/.test($(w, '#av-recent [data-job="J1"]').textContent), "poll cap nhat tien do 2/4 = 50%");
  ok(/1/.test($(w, '#av-tab-lich-su').textContent), "tab Lich su dem phieu dang chay");
  jobsState = [Object.assign({}, created, { status: "done", has_audio: true, seconds: 5 })];
  await new Promise((r) => setTimeout(r, 4200)); await flush();
  const done = $(w, '#av-recent [data-job="J1"]');
  ok(done && /Xong/.test(done.textContent) && done.querySelector('[data-act="play"]') && done.querySelector('[data-act="download"]'), "xong -> co nut nghe + tai");
  ok(/Xong: Bài <b>1<\/b>/.test($(w, "#av-toast").textContent), "toast bao xong (textContent, khong render HTML)");
  w.close();
}

// 3. May mat ket noi: banner giai thich, van tao duoc (phieu cho)
{ const w = boot({ get_state: env(state()), machine_status: env({ online: false, ready: false, message: "Máy giọng đọc đang không kết nối" }), list_jobs: env({ jobs: [] }) });
  await flush();
  ok(/mất kết nối/.test($(w, "#av-machine").textContent) && $(w, "#av-machine").classList.contains("bad"), "chip do khi may tat");
  ok(/tự gửi khi máy bật lại/.test($(w, "#av-banner").textContent), "banner noi phieu se tu gui");
  w.close();
}

// 4. Chua cai dat: nguoi dung bi chan + System Manager co nut mo Cai dat; token khong bao gio dien san
{ const w = boot({ get_state: env(state({ configured: false, is_admin: true, is_manager: true })), get_settings: env({ base_url: "https://voice.ecentric.asia", token_set: false, default_quality: "quality_fast", default_speed: 1.1, timeout: 30 }),
    save_settings: (b) => env(Object.assign({ token_set: true, base_url: b.data.base_url }, b.data)), machine_status: env({ online: true, ready: true }), list_jobs: env({ jobs: [] }) });
  await flush();
  typeText(w, "av-text", "abc");
  ok($(w, '[data-act="create"]').disabled && /Chưa cài đặt/.test($(w, "#av-gen-hint").textContent), "chua cai dat -> khong tao duoc");
  ok($(w, '#av-banner [data-tab="cai-dat"]'), "admin co nut Mo Cai dat");
  $(w, '#av-banner [data-tab="cai-dat"]').click(); await flush();
  ok($(w, "#st-token") && $(w, "#st-token").value === "" && $(w, "#st-token").type === "password", "o token rong, kieu password");
  $(w, "#st-token").value = "secret-123";
  $(w, "#av-set").dispatchEvent(new w.Event("submit", { bubbles: true, cancelable: true })); await flush();
  const s = w.__calls.find((x) => x.method === "save_settings");
  ok(s && s.body.data.token === "secret-123" && s.body.data.base_url === "https://voice.ecentric.asia", "luu gui token + dia chi");
  ok(!$(w, "#av-banner .av-banner.bad"), "luu xong het banner chua cai dat");
  w.close();
}

// 5. Quan ly: tab Thu vien co Them / Dong bo / Sua; form them giong bat buoc dong y
{ const st = state({ is_manager: true, voices: [
    { name: "P1", voice_id: "v1", voice_name: "Lan", gender: "Nữ", status: "active", has_consent: true },
    { name: "P3", voice_id: "v3", voice_name: "Từ máy", gender: "", status: "disabled", has_consent: false, source: "machine" },
    { name: "P4", voice_id: "", voice_name: "Hỏng", gender: "Nam", status: "failed", has_consent: true, source: "erp", upload_error: "File quá ngắn" }] });
  const w = boot({ get_state: env(st), machine_status: env({ online: true, ready: true }), list_jobs: env({ jobs: [] }), brands: env({ online: true, brands: [{ name: "Lix", current_name: "Lan" }] }),
    add_voice: (b) => env({ name: "P9", voice_name: b.data.voice_name, status: "processing", has_consent: true }) }, { hash: "#/giong" });
  await flush();
  ok($(w, '[data-act="add-voice"]') && $(w, '[data-act="sync-voices"]'), "quan ly co nut Them giong + Dong bo");
  ok(/Thiếu bằng chứng đồng ý/.test(w.document.body.textContent), "giong thieu dong y duoc nhac");
  ok(/File quá ngắn/.test(w.document.body.textContent) && $(w, '[data-act="retry-voice"][data-name="P4"]'), "giong loi hien ly do + nut Thu lai");
  ok(/Lix/.test(w.document.body.textContent), "hien giong dang dung cua brand");
  $(w, '[data-lfilter="attention"]').click(); await flush();
  ok($$(w, ".av-vcard").length === 2, "loc Can xu ly: thieu dong y + loi");
  $(w, '[data-act="add-voice"]').click(); await flush();
  typeText(w, "vf-name", "Giọng mới");
  $(w, '[data-act="save-voice"]').click(); await flush();
  ok(!$(w, "#vf-err").hidden && /đồng ý/.test($(w, "#vf-err").textContent), "thieu dong y -> bao loi, khong goi API");
  ok(!w.__calls.some((x) => x.method === "add_voice"), "chua goi add_voice");
  $(w, "#vf-cby").value = "Lan"; $(w, "#vf-cdate").value = "2026-11-10"; $(w, "#vf-cok").checked = true;
  $(w, '[data-act="save-voice"]').click(); await flush();
  ok(/file giọng mẫu/i.test($(w, "#vf-err").textContent), "chua co file mau -> bao loi");
  w.close();
}

// 6. Khong co quyen / chua dang nhap
{ const w = boot({ get_state: [403, { message: { success: false, message: "Cần quyền dùng Giọng đọc AI", data: null } }] });
  await flush();
  ok(/chưa có quyền/.test($(w, "#av-view").textContent) && /EC AI Voice User/.test($(w, "#av-view").textContent), "403 -> huong dan xin role");
  ok($$(w, "#av-tabs [role=tab]").length === 0, "khong ve tab khi khong co quyen");
  const g = boot({ get_state: [403, { message: { success: false, message: "x", data: null } }] }, { guest: true });
  await flush();
  ok($(g, '#av-view a[href="/login?redirect-to=/ai-voice"]'), "Guest -> nut Dang nhap");
  const e = boot({ get_state: [500, { exc: "Traceback..." }] });
  await flush();
  ok($(e, '[data-act="retry-boot"]') && !/Traceback/.test($(e, "#av-view").textContent), "500 -> nut Thu lai, khong lo traceback");
}

// 7. Ban nhap giu qua lan tai lai (localStorage) + loi tao phieu hien toast
{ const w = boot({ get_state: env(state()), machine_status: env({ online: true, ready: true }), list_jobs: env({ jobs: [] }),
    create_job: [200, { message: { success: false, message: "Bạn đang có 10 phiếu chờ", data: null } }] });
  await flush();
  typeText(w, "av-text", "nháp dở dang");
  $(w, '[data-act="pick-voice"]').click(); await flush(); $$(w, '#av-pick-list [data-act="pick"]')[0].click(); await flush();
  await new Promise((r) => setTimeout(r, 450));
  const saved = JSON.parse(w.localStorage.getItem("ec-aiv-draft") || "{}");
  ok(saved.text === "nháp dở dang" && saved.voice === "profile:P1", "luu ban nhap");
  $(w, '[data-act="create"]').click(); await flush();
  ok(/10 phiếu chờ/.test($(w, "#av-toast").textContent) && $(w, "#av-toast").classList.contains("err"), "loi server -> toast do");
  ok(!$(w, '[data-act="create"]').disabled, "loi xong nut Doc bat lai");
  w.close();
}

// 8. Het phien dang nhap giua chung: poll gap 403 -> dung poll, hien man hinh quyen; khong ve lai khi khong doi
{ let n = 0, deny = false;
  const job = { name: "J1", title: "A", status: "running", progress: "1/4", voice_label: "Lan", quality: "quality_fast", owner: "u@x", creation: "2026-11-15 09:00:00" };
  const w = boot({ get_state: env(state({ jobs: [job] })), machine_status: env({ online: true, ready: true }),
    list_jobs: () => { n++; return deny ? [403, { message: { success: false, message: "x", data: null } }] : env({ jobs: [job] }); } });
  await flush();
  const row = $(w, '#av-recent [data-job="J1"]');
  await new Promise((r) => setTimeout(r, 4300)); await flush();
  ok($(w, '#av-recent [data-job="J1"]') === row, "khong doi gi -> khong ve lai (giu thanh tua dang nghe)");
  deny = true;
  await new Promise((r) => setTimeout(r, 4300)); await flush();
  const after = n;
  ok(/chưa có quyền|Cần đăng nhập/.test($(w, "#av-view").textContent), "403 khi dang poll -> man hinh quyen");
  await new Promise((r) => setTimeout(r, 4300)); await flush();
  ok(n === after, "dung poll sau 403");
  w.close();
}

console.log((fails ? "THAT BAI" : "OK") + ": " + oks + " dat, " + fails + " hong");
process.exit(fails ? 1 : 0);
