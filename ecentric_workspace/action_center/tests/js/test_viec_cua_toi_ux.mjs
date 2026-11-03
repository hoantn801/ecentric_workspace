// UX /viec-cua-toi tren dien thoai (03/11/2026, ux2): huy hieu header doi NGAY sau khi duyet nhanh,
// bang duyet nhanh an toan hon (xac nhan Tu choi / Bo sung, chong mo 2 bang, chong bam 2 lan, Esc),
// so tien + han tuong doi tren the, loi tieng Viet (khong chu ky thuat), mat mang tu tai lai,
// tab Thong bao co thoi gian + chu tron + danh dau da doc, chuong thong bao doc gio site dung.
//     node ecentric_workspace/action_center/tests/js/test_viec_cua_toi_ux.mjs
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url));
const APP = join(here, "..", "..", "..");
const HTML = readFileSync(join(APP, "action_center", "pages", "my_work", "main_section.html"), "utf8");
const BUNDLE = readFileSync(join(APP, "public", "js", "ec_cho_duyet.bundle.js"), "utf8");
const CSS = readFileSync(join(APP, "public", "css", "ec_cho_duyet.bundle.css"), "utf8");
const NCJS = readFileSync(join(APP, "public", "js", "notification_center.js"), "utf8");
let fails = 0, oks = 0;
const ok = (c, n) => { if (c) oks++; else { fails++; console.log("  FAIL: " + n); } };
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setTimeout(r, 3)); };
const pad = (n) => String(n).padStart(2, "0");
const localDay = (off, hm = "18:00:00") => { const d = new Date(); d.setDate(d.getDate() + off);
  return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + " " + hm; };
// gio SITE (VN, UTC+7) cua "bay gio - mins phut"
const siteAgo = (mins) => new Date(Date.now() + 7 * 3600e3 - mins * 60e3).toISOString().replace("T", " ").slice(0, 19);

const CAPS = { can_approve: true, can_reject: true, can_request_info: true, needs_input: false, needs_input_reason: "", comment_required: false };
const ROWS = () => ([
  { request: "R1", approval_type: "PAY", type_label: "Thanh toán", title: "Thanh toán NCC quá hạn", requester_name: "Anh A",
    submitted_at: "2026-10-01 09:00:00", due_at: localDay(-2), level_name: "Manager", detail_url: "/approvals/payment-request?id=P-1",
    summary: [{ label: "Số tiền", value: "12.500.000" }, { label: "NCC", value: "Công ty X" }],
    amount: { label: "Số tiền", value: "12.500.000" }, capabilities: { ...CAPS } },
  { request: "R2", approval_type: "LEAVE", type_label: "Nghỉ phép", title: "Nghỉ phép 2 ngày", requester_name: "Chị B",
    submitted_at: "2026-10-05 09:00:00", due_at: localDay(0, "23:59:00"), level_name: "Manager", detail_url: "/approvals/leave?id=LV-1",
    summary: [{ label: "Loại nghỉ", value: "Annual" }], amount: null, capabilities: { ...CAPS } },
]);

function boot(opts = {}) {
  const i = HTML.indexOf('<div class="ecw"');
  const s = HTML.search(/<script id="ec-mywork-js">/);
  const markup = HTML.slice(i, s);
  const rest = HTML.slice(s).replace(/^<script[^>]*>/, "");
  const js = rest.slice(0, rest.indexOf("</script>"));
  const header = '<button data-ec-shell-action-slot="1"><span id="hb" data-ec-shell-reminder-badge="1">3</span></button>'
    + '<nav class="ec-tab"><i id="tb" data-ec-shell-reminder-badge="1">3</i></nav>';
  const dom = new JSDOM("<!DOCTYPE html><html><body>" + header + markup + "</body></html>",
    { runScripts: "outside-only", url: "https://x.test/viec-cua-toi" + (opts.hash || ""), pretendToBeVisual: true });
  const w = dom.window; w.innerWidth = 390;
  const st = { calls: [], rows: opts.rows || ROWS(), attention: 3, online: !opts.offline, workFail: opts.workFail || 0,
    notis: opts.notis || [], unread: (opts.notis || []).filter((n) => !n.is_read).length, dispatched: [] };
  Object.defineProperty(w.navigator, "onLine", { configurable: true, get: () => st.online });
  w.frappe = { csrf_token: "tok" };
  ["ec:notif-changed", "ec:action-feed-changed"].forEach((n) => w.document.addEventListener(n, (e) => st.dispatched.push([n, e.detail])));
  const res = (status, obj) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(obj) });
  w.fetch = (url, init) => {
    const m = String(url).split("?")[0].split(".").pop();
    const body = init && init.body ? JSON.parse(init.body) : null;
    st.calls.push([m, body, init]);
    if (!st.online) return Promise.reject(new w.TypeError("Failed to fetch"));
    if (m === "list_my_pending") return res(200, { message: { rows: st.rows, count: st.rows.length } });
    if (m === "quick_decide") {
      if (opts.decide) return opts.decide(res, body);
      st.rows = st.rows.filter((r) => r.request !== body.request_name);
      st.attention = Math.max(0, st.attention - 1);
      return res(200, { message: { ok: true, remaining: st.rows.length } });
    }
    if (m === "get_action_items") {
      if (st.workFail) { st.workFail--; return res(500, { exception: "pymysql.err.OperationalError: (1205, 'Lock wait')" }); }
      if (opts.slowWork) return new Promise((r) => setTimeout(() => r({ ok: true, status: 200,
        json: () => Promise.resolve({ message: { success: true, items: [], counts: {}, total: 0, next_cursor: null, attention_count: st.attention } }) }), 30));
      return res(200, { message: { success: true, items: [], counts: {}, total: st.attention, next_cursor: null, attention_count: st.attention } });
    }
    if (m === "get_notifications") return res(200, { message: { success: true, items: st.notis, unread: st.unread } });
    if (m === "mark_all_read") return opts.readAllFail ? res(500, {}) : res(200, { message: { success: true } });
    if (m === "mark_read") return res(200, { message: { success: true } });
    return res(200, { message: {} });
  };
  w.eval(js);
  w.eval(BUNDLE);
  return { w, st };
}
const $ = (w, q) => w.document.querySelector(q);
const $$ = (w, q) => [...w.document.querySelectorAll(q)];
const open1 = async (w, id) => { $(w, `[data-cd-open="${id}"] .cd-title`).click(); await flush(); };

{ // 1) VAN DE CHINH: duyet xong -> huy hieu header + thanh tab doi NGAY (tu get_action_items.attention_count)
  const { w, st } = boot(); await flush();
  ok($(w, "#hb").textContent === "3", "truoc khi duyet: huy hieu 3 (do shell ve)");
  await open1(w, "R2");
  $(w, '.cd-sheet [data-cd-do="approve"]').click(); await flush();
  ok($(w, "#hb").textContent === "2" && $(w, "#tb").textContent === "2", "duyet xong: header + tab duoi = 2 ngay, khong can tai lai trang");
  ok(st.dispatched.some(([n, d]) => n === "ec:action-feed-changed" && d.attention_count === 2), "phat ec:action-feed-changed cho shell (sua goc sau nay)");
  st.attention = 0; w.document.dispatchEvent(new w.CustomEvent("ec:cho-duyet-doi")); await flush();
  ok($(w, "#hb").hidden && $(w, "#hb").textContent === "", "het viec can chu y -> an huy hieu");
  st.attention = 14; w.document.dispatchEvent(new w.CustomEvent("ec:cho-duyet-doi")); await flush();
  ok($(w, "#hb").textContent === "9+" && !$(w, "#hb").hidden, ">9 -> '9+' dung luat shell");
}
{ // 1b) quyet dinh den luc lan tai dang bay -> tai lai them MOT lan (khong bo qua)
  const { w, st } = boot({ slowWork: true }); await flush(); await new Promise((r) => setTimeout(r, 40));
  w.document.dispatchEvent(new w.CustomEvent("ec:cho-duyet-doi"));                 // lan 1 bat dau bay
  st.attention = 1; w.document.dispatchEvent(new w.CustomEvent("ec:cho-duyet-doi")); // trung luc dang bay
  await new Promise((r) => setTimeout(r, 120)); await flush();
  ok($(w, "#hb").textContent === "1", "quyet dinh trong luc dang tai: lan tai sau cung thang, huy hieu = 1");
}

{ // 2) the: so tien noi bat, han tuong doi, qua han to do, nhom ghi "N qua han"
  const { w } = boot(); await flush();
  const c1 = $(w, '[data-cd-open="R1"]');
  ok(/12\.500\.000/.test(c1.querySelector(".cd-amt").textContent), "so tien noi bat tren the");
  ok(![...c1.querySelectorAll(".cd-chip")].some((x) => /12\.500\.000/.test(x.textContent)) && /Công ty X/.test(c1.textContent), "chip khong lap lai so tien, van co truong khac");
  ok(c1.classList.contains("cd-card-od") && /Quá hạn 2 ngày/.test(c1.textContent), "the qua han: vien do + 'Qua han 2 ngay'");
  ok(/Hạn hôm nay 23:59/.test($(w, '[data-cd-open="R2"]').textContent), "han hom nay: 'Han hom nay 23:59'");
  ok(/1 quá hạn/.test($$(w, ".cd-gh")[0].textContent), "tieu de nhom: '1 qua han'");
  ok(!$(w, '[data-cd-open="R2"] .cd-amt'), "phieu khong co so tien -> khong ve o so tien");
  ok(/-webkit-line-clamp:3/.test(CSS.match(/\.cd-title\{[^}]*\}/)[0]), "tieu de dai: cat o 3 dong, bang van hien du");
}

{ // 3) bang: so tien to, "Buoc ...", khong mo 2 bang chong nhau, Esc dong + tra cuon trang
  const { w } = boot(); await flush();
  await open1(w, "R1");
  ok(/12\.500\.000/.test($(w, ".cd-sh-amt").textContent) && /Bước Manager/.test($(w, ".cd-sh-type").textContent), "bang: so tien to + 'Buoc Manager'");
  $(w, '[data-cd-open="R1"] .cd-title').click(); $(w, '[data-cd-open="R2"] [data-cd-quick]').click(); await flush();
  ok($$(w, ".cd-ov").length === 1, "cham them lan nua khi bang dang mo -> van MOT bang");
  ok(w.document.activeElement === $(w, ".cd-sheet") && w.document.activeElement !== $(w, "#cd-cmt"), "focus vao khung bang, KHONG vao o nhan xet (khong bat ban phim)");
  w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape" })); await flush();
  ok(!$(w, ".cd-ov") && w.document.documentElement.style.overflow === "", "Esc dong bang, tra cuon trang");
  ok(w.document.activeElement === $(w, '[data-cd-open="R1"]'), "dong bang -> focus ve the vua cham");
  await open1(w, "R2");
  ok($$(w, ".cd-ov").length === 1, "dong roi mo lai binh thuong");
  w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape" })); await flush();
  const card = $(w, '[data-cd-open="R1"]');
  card.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })); await flush();
  ok(card.getAttribute("tabindex") === "0" && $$(w, ".cd-ov").length === 1, "ban phim: Enter tren the mo bang");
}

{ // 4) Tu choi: ly do bat buoc -> buoc xac nhan -> Quay lai khong goi server
  const { w, st } = boot(); await flush();
  await open1(w, "R2");
  $(w, '.cd-sheet [data-cd-do="reject"]').click(); await flush();
  ok($(w, "[data-cd-confirm]").hidden && /lý do/.test($(w, "[data-cd-msg]").textContent), "chua ghi ly do: khong hien xac nhan, nhac ghi ly do");
  ok(w.document.activeElement === $(w, "#cd-cmt"), "bam Tu choi khi trong -> dua con tro vao o ly do (do nguoi dung bam)");
  $(w, "#cd-cmt").value = "Sai ngay";
  $(w, '.cd-sheet [data-cd-do="reject"]').click(); await flush();
  const box = $(w, "[data-cd-confirm]");
  ok(!box.hidden && $(w, "[data-cd-btns]").hidden && /Xác nhận từ chối/.test(box.textContent), "co ly do: hien buoc xac nhan 'Xac nhan tu choi'");
  $(w, "[data-cd-confirm-no]").click(); await flush();
  ok(box.hidden && !$(w, "[data-cd-btns]").hidden && !st.calls.some((c) => c[0] === "quick_decide"), "Quay lai: ve hang nut, KHONG goi server");
  $(w, '.cd-sheet [data-cd-do="request_information"]').click(); await flush();
  ok(/Trả phiếu về người gửi/.test(box.textContent) && /Xác nhận trả về bổ sung/.test(box.textContent), "Yeu cau bo sung cung co buoc xac nhan rieng");
  $(w, "[data-cd-confirm-go]").click(); await flush();
  const q = st.calls.filter((c) => c[0] === "quick_decide");
  ok(q.length === 1 && q[0][1].action === "request_information" && q[0][1].comment === "Sai ngay", "xac nhan -> dung MOT lan quick_decide request_information");
}

{ // 5) chong bam 2 lan: nut khoa + chu "Dang duyet..." trong luc gui
  let release;
  const { w, st } = boot({ decide: (res) => new Promise((r) => { release = () => r(res(200, { message: { ok: true, remaining: 1 } })); }).then((x) => x) });
  await flush();
  await open1(w, "R2");
  const b = $(w, '.cd-sheet [data-cd-do="approve"]');
  b.click(); b.click(); await flush();
  ok(st.calls.filter((c) => c[0] === "quick_decide").length === 1, "bam Duyet 2 lan -> chi MOT lenh");
  ok(b.disabled && /Đang duyệt/.test(b.textContent) && $(w, "#cd-cmt").readOnly, "dang gui: nut khoa, 'Dang duyet...', o nhan xet khoa");
  release(); await flush();
  ok(/Đã duyệt: Nghỉ phép 2 ngày · còn 1 phiếu chờ bạn/.test($(w, "[data-cd-toast]").textContent), "thong bao xong kem so phieu con lai");
}

{ // 6) loi: 500 co exception tho -> cau tieng Viet chung; mat mang -> cau mang; CSRF -> tai lai trang
  const mk = (status, obj) => boot({ decide: (res) => res(status, obj) });
  let t = mk(500, { exc_type: "OperationalError", exception: "pymysql.err.OperationalError: (1205, 'Lock wait timeout')" }); await flush();
  await open1(t.w, "R2"); $(t.w, '.cd-sheet [data-cd-do="approve"]').click(); await flush();
  let m = $(t.w, "[data-cd-msg]").textContent;
  ok(/Hệ thống đang bận/.test(m) && !/1205|Lock|pymysql/.test(m), "500: khong lo exception tho: " + m);
  ok(!$(t.w, '.cd-sheet [data-cd-do="approve"]').disabled && /^Duyệt$/.test($(t.w, '.cd-sheet [data-cd-do="approve"]').textContent), "loi: mo khoa nut, tra lai chu 'Duyet'");
  t = mk(400, { exc_type: "CSRFTokenError" }); await flush();
  await open1(t.w, "R2"); $(t.w, '.cd-sheet [data-cd-do="approve"]').click(); await flush();
  ok(/tải lại trang/.test($(t.w, "[data-cd-msg]").textContent), "CSRF: bao tai lai trang");
  t = mk(417, { exc_type: "ValidationError", _server_messages: JSON.stringify([JSON.stringify({ message: "Phiếu <b>đã</b> được duyệt" })]) }); await flush();
  await open1(t.w, "R2"); $(t.w, '.cd-sheet [data-cd-do="approve"]').click(); await flush();
  ok($(t.w, "[data-cd-msg]").textContent === "Phiếu đã được duyệt", "417: cau nghiep vu nguyen van, bo the HTML");
  t = boot(); await flush();
  await open1(t.w, "R2"); t.st.online = false; $(t.w, '.cd-sheet [data-cd-do="approve"]').click(); await flush();
  m = $(t.w, "[data-cd-msg]").textContent;
  ok(/mất mạng/.test(m) && !/Failed to fetch/.test(m), "mat mang luc duyet: cau tieng Viet, khong 'Failed to fetch': " + m);
}

{ // 7) mat mang luc mo trang -> bao ro + tu tai lai khi co mang (ca 'Cho toi duyet' lan lan Viec)
  const { w, st } = boot({ offline: true }); await flush();
  ok(/mất mạng/.test($(w, "[data-cd-body]").textContent) && /mất mạng/.test($(w, "#mw-body").textContent), "offline: hai khoi deu bao mat mang");
  ok(!/HTTP|Failed/.test($(w, "#mw-body").textContent), "khong chu ky thuat");
  st.online = true; w.dispatchEvent(new w.Event("online")); await flush();
  ok($$(w, ".cd-card").length === 2 && !$(w, "#mw-body .err"), "co mang lai: tu tai lai, khong can bam Thu lai");
  const b = boot({ workFail: 1 }); await flush();
  const txt = $(b.w, "#mw-body").textContent;
  ok(/hệ thống đang bận/.test(txt) && !/HTTP 500|1205/.test(txt), "loi 500 lan Viec: cau tieng Viet: " + txt.trim().slice(0, 80));
  ok(/min-height:44px/.test(HTML.match(/\.ecw \.err button\{[^}]*\}/)[0]), "nut Thu lai cao >= 44px");
}

{ // 8) tab Thong bao: chu tron, thoi gian theo gio site, bam -> danh dau da doc + bao chuong
  const notis = [
    { name: "N1", subject: "<b>Anh A</b> gửi phiếu <i>PAY-1</i>", source_label: "Phê duyệt", action_url: "/approvals/payment-request?id=P-1", is_read: 0, created_at: siteAgo(125) },
    { name: "N2", subject: "Đã đọc", action_url: "/x", is_read: 1, created_at: siteAgo(3) },
  ];
  const { w, st } = boot({ notis }); await flush();
  $(w, '#mw-switch [data-view="noti"]').click(); await flush();
  const a = $(w, 'a[data-nc="N1"]');
  ok(a && a.querySelector(".ec-shell-nc-title").textContent === "Anh A gửi phiếu PAY-1", "tieu de bo the HTML");
  ok(/Phê duyệt · 2 giờ trước/.test(a.textContent), "co nguon + thoi gian theo gio site: " + a.textContent);
  ok(/3 phút trước/.test($(w, 'a[data-nc="N2"]').textContent), "3 phut truoc (khong phai 'vua xong' do lech mui gio)");
  a.addEventListener("click", (e) => e.preventDefault());       // jsdom khong dieu huong
  a.click(); await flush();
  const mr = st.calls.find((c) => c[0] === "mark_read");
  ok(mr && mr[1].notification_name === "N1" && mr[2].keepalive === true && mr[2].method === "POST", "bam thong bao chua doc -> POST mark_read keepalive");
  ok(st.dispatched.some(([n]) => n === "ec:notif-changed"), "bao chuong header lay lai so chua doc");
}
{ // 8b) "Doc het" loi server -> KHONG danh dau da doc tren man hinh
  const notis = [{ name: "N1", subject: "x", is_read: 0, created_at: siteAgo(5) }];
  const { w } = boot({ notis, readAllFail: true }); await flush();
  $(w, '#mw-switch [data-view="noti"]').click(); await flush();
  $(w, "#mw-readall").click(); await flush();
  ok($(w, 'a[data-nc="N1"]').classList.contains("ec-shell-nc-unread") && /thử lại/.test($(w, "#mw-readall").textContent), "doc het loi: van chua doc + nut 'thu lai'");
}
{ // 9) han lan Viec theo chu
  const { w } = boot(); await flush();
  const dt = w.eval("(" + HTML.match(/function dayDiff[\s\S]*?\n  }\n  function dueText[\s\S]*?\n  }/)[0].replace(/^/, "function(){") + "; return dueText; })")();
  const now = new Date(2026, 10, 3, 10, 0);
  ok(dt("2026-11-03", now) === "Hôm nay" && dt("2026-11-04", now) === "Ngày mai" && dt("2026-10-31", now) === "Quá 3 ngày"
     && dt("2026-11-20", now) === "20/11" && dt("", now) === "Không hạn", "han: Hom nay / Ngay mai / Qua 3 ngay / 20/11 / Khong han");
  ok(/\.ecw \.ec-shell-rm-title\{white-space:normal; display:-webkit-box; -webkit-line-clamp:2/.test(HTML), "tieu de viec dai: 2 dong thay vi 1 dong '...'");
  ok(/\.ecw \.mw-switch button::after\{content:""; position:absolute; inset:-7px/.test(HTML), "nut gat: vung cham mo rong >= 44px");
}
{ // 10) giu quyet dinh cua PO: khong duyet hang loat, khong tu focus; tab bar van gan duoc
  ok(!/data-cd-pick|data-cd-bulk/.test(BUNDLE), "khong co duyet hang loat");
  ok(/id="ec-mywork-root"/.test(HTML), "moc #ec-mywork-root cua thanh tab duoi con nguyen");
  ok(!/<script id="ec-(?!mywork-js)/.test(HTML) && !/<style id="ec-(?!mywork-css)/.test(HTML), "khong them khoi ec-... moi");
}

// 11) chuong thong bao (notification_center.js): gio site + nghe ec:notif-changed + trang thai dang tai / loi
{
  const dom = new JSDOM('<!DOCTYPE html><html><body><a data-ec-notification-bell="1" href="/app/notification-log">b</a></body></html>',
    { runScripts: "outside-only", url: "https://x.test/", pretendToBeVisual: true });
  const w = dom.window; const calls = []; let fail = false, hold = null;
  w.console.log = () => {}; w.console.warn = () => {};
  w.frappe = { call: (o) => { calls.push(o.method.split(".").pop());
    const m = o.method.split(".").pop();
    const go = () => { if (fail) return o.error && o.error();
      if (m === "get_notifications") o.callback({ message: { success: true, unread: 1, items: [{ name: "N1", subject: "S", is_read: 0, created_at: siteAgo(125) }] } });
      else if (m === "get_unread_count") o.callback({ message: { success: true, unread: 1 } });
      else o.callback({ message: { success: true } }); };
    if (hold && m === "get_notifications") hold.push(go); else go(); } };
  w.eval(NCJS); await flush();
  hold = [];
  w.document.querySelector("[data-ec-notification-bell]").dispatchEvent(new w.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
  ok(/Đang tải thông báo/.test(w.document.querySelector("#ec-nc-list").textContent), "mo chuong lan dau: 'Dang tai', khong noi 'Chua co thong bao'");
  hold.forEach((f) => f()); hold = null; await flush();
  ok(/2 giờ trước/.test(w.document.querySelector(".ec-nc-time").textContent), "chuong: gio site +07:00 -> '2 gio truoc' (truoc day 'vua xong')");
  const n0 = calls.length;
  w.document.dispatchEvent(new w.CustomEvent("ec:notif-changed")); await flush();
  ok(calls.length === n0 + 1, "ec:notif-changed -> lay lai so ngay, MOT lan goi");
  const d2 = new JSDOM('<!DOCTYPE html><html><body><a data-ec-notification-bell="1" href="/app/notification-log">b</a></body></html>',
    { runScripts: "outside-only", url: "https://x.test/", pretendToBeVisual: true });
  d2.window.console.log = () => {}; d2.window.console.warn = () => {};
  d2.window.frappe = { call: (o) => o.error && o.error() };
  d2.window.eval(NCJS); await flush();
  d2.window.document.querySelector("[data-ec-notification-bell]").dispatchEvent(new d2.window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
  await flush();
  ok(/Chưa tải được thông báo/.test(d2.window.document.querySelector("#ec-nc-list").textContent), "chuong loi mang: bao chua tai duoc, khong noi 'Chua co thong bao'");
}
console.log(`${oks} dat, ${fails} hong`); process.exit(fails ? 1 : 0);
