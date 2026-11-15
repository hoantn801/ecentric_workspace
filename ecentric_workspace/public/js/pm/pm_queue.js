/* pm_queue.js — Việc cần làm (PO 15/11/2026, demo phương án A "Hàng đợi"). Asset tĩnh, /pm tải lười khi mở #mywork
 * (pm_app.html pmQueueAssets, cùng ?v= với pm_redesign.js). Một global: window.PMQueue.render(el, opts) -> {refresh, destroy, root}.
 *   opts: {api(method, args) -> Promise (host truyền api() của trang, POST); thiếu thì tự POST /api/method kèm CSRF,
 *          head(title, sub, right) của host, openTask(name, o) của host (giữ hash #task/..), user, tab: "me"|"give"}.
 * Dữ liệu: pm.api.queue.list (MỘT quy tắc xếp ở server: Hạn -> Ưu tiên -> Giờ). Client KHÔNG tự xếp lại, chỉ vẽ theo `rank`.
 * Ghi đi qua endpoint sẵn có: tasks.mark_done / set_status / create, assignment.respond / create_with_task, pm_inbox.nudge.
 * Đọc hạn tiếng Việt: dùng lại PMR._pure.parseDue (pm_redesign.js), không viết bộ mới.
 * Sự kiện: phát pmr:changed {source:"pmq"} + pmr:badge {key:"mywork"}; nghe pmr:changed của màn khác để làm mới.
 * Mọi chuỗi từ server đi qua esc(). Sửa giao diện: chỉ sửa file này + pm_queue.css.
 * Rà UX 15/11: xong/bỏ một việc -> chọn sang việc kế tiếp (làm từ trên xuống bằng phím); giao nhanh nhớ lựa chọn "Cần đồng ý"
 * trong phiên, không tự chuyển tab (toast có nút Xem); toast dừng đếm khi rê chuột / focus; "Cần đồng ý" > 3 việc thì thu gọn.
 * QC 15/11 (tests/pm_queue_qc1.test.js): người giao "Duyệt xong" việc Chờ duyệt (pm_inbox.close_parent); giao liên tiếp không khoá ô
 * nhập (lỗi thì trả chữ); bỏ qua Enter/Tab khi bộ gõ đang ghép chữ (IME); ghi đi ecApi.post (CSRF tươi) khi trang có ec_api;
 * đọc lỗi từ server không gọi lại frappe.call; S không mở lại việc vừa Xong; làm mới sau lỗi ghi; @email; số đếm ép kiểu số.
 * QC2 15/11 (tests/pm_queue_qc2.test.js): việc mình đã gửi kiểm tra chờ người khác duyệt = `waiting` của server -> nhóm "Đang chờ duyệt (n)"
 * thu gọn cuối danh sách (không số thứ tự, không vào J/K, không vào số đếm); tab giao: "Chờ nhận", "x/y người xong", "đã nghỉ";
 * `truncated` -> báo nhẹ; giao 1 dòng: "cao"/"thấp" cuối câu = ưu tiên, "thứ 6" gõ đúng thứ Sáu = thứ Sáu tuần sau (chỉ ở lớp gọi,
 * không đổi PMR._pure.parseDue); tự làm mới 60 giây không vẽ lại khi dữ liệu không đổi; quay lại tab trình duyệt -> làm mới.
 * QC3 15/11 (tests/pm_queue_qc3.test.js): tab giao có khối "Đề xuất hạn" trên đầu (`proposals` của server: người nhận Đề xuất hạn khác,
 * chờ chính mình) -> Đồng ý hạn mới = assignment.requester_action(accept_counter), Giữ hạn cũ, gửi lại = requester_action(resend).
 * Không có Hoàn tác: cả hai đã báo người nhận (giống Nhận việc).
 * QC4 15/11 (nghiệm thu "một ngày dùng", tests/pm_queue_qc4.test.js): "Xin dời hạn" khép vòng — dòng của mình ghi "Đã xin dời sang …"
 * (server deadline_ask) và ẩn nút; người giao thấy yêu cầu ở khối đề xuất (counter.kind "deadline" -> pm_inbox.answer_deadline,
 * Đồng ý hạn mới / Giữ hạn cũ); tab giao: lọc "Chưa mở việc", dòng vừa nhắc ghi "Đã nhắc HH:MM", việc Chờ duyệt có "Trả lại"
 * (tasks.set_status In Progress, như "Tôi đã giao"); số giới hạn lấy từ server (`limit`).
 * 16/11 (PO duyệt, tests/pm_queue_multi.test.js): giao 1 dòng nhận NHIỀU @ (chip + × từng người; trùng tên / không tìm thấy theo từng @;
 * bỏ trùng, không tính chính mình); từ 2 người chọn "Mỗi người một việc" (split_per_assignee=1, mặc định) / "Làm chung 1 việc" (0),
 * nhớ trong phiên; Cần đồng ý + nhiều người -> assignment.create_with_task(recipients, split 1), khoá "Làm chung".
 * "Thêm chi tiết" (Shift+Enter) -> PMR.newTask điền sẵn {subject, assignees, due, time, priority, split, requestMode}.
 * QA5 16/11 (tests/pm_queue_multi_qa5.test.js): × / chọn người sửa trên chữ đã chuẩn hoá (atNorm: NFC + bỏ ",", "và" giữa hai @);
 * gợi ý @ khi con trỏ giữa một @ thay cả @ và giữ người đang chọn đứng đầu; chèn theo email khi tên gọi trùng một @ chưa chọn;
 * "Thêm chi tiết" chuyển đúng Cần đồng ý đang nhớ (cả việc của tôi). */
(function (root) {
"use strict";
if (root.PMQueue) return;

const D = root.document, NS = "ecentric_workspace.pm.api.";
const REFRESH_MS = 60000, JUST_MS = 1600, SOFT_MS = 500, LSK = "pmr.showPersonal", ASK_FOLD = 3, TITLE_TIP = 40;
const PRI = { Urgent: [4, "Khẩn cấp"], High: [3, "Cao"], Medium: [2, "Bình thường"], Low: [1, "Thấp"] };
const PRI_KEYS = ["Urgent", "High", "Medium", "Low"];
const STATE = { Backlog: "Chưa làm", "To Do": "Chưa làm", "In Progress": "Đang làm", Review: "Chờ duyệt", Blocked: "Bị chặn", Done: "Xong" };
const WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const WDN = ["Chủ nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"];
const BLOCKED = { required_steps: "Chưa xong được: còn bước bắt buộc chưa tích. Đã mở việc để bạn tích đủ các bước.",
  open_children: "Chưa xong được: còn việc con đang mở. Đóng hết việc con trước." };
/* từ ưu tiên trong câu (dài trước ngắn). "gap" không dấu bỏ qua: dễ là "gặp" (gặp khách). */
const PRI_WORDS = [["không gấp", "Low"], ["ưu tiên thấp", "Low"], ["uu tien thap", "Low"], ["khẩn cấp", "Urgent"], ["khan cap", "Urgent"],
  ["rất gấp", "Urgent"], ["gấp", "Urgent"], ["ưu tiên cao", "High"], ["uu tien cao", "High"], ["quan trọng", "High"], ["quan trong", "High"]];
const AT_RX = /(^|\s)@([^\s@,;:()]+(?:@[^\s@,;:()]+\.[^\s@,;:()]+)?)/;   /* @tên hoặc @email đầy đủ */
/* "@Lan, @Phú", "@Lan và @Phú", "@Lan & @Phú": bỏ chữ nối giữa hai @ (không để "và" dính vào tên việc) */
const AT_JOIN = /(^|\s)(@[^\s@,;:()]+(?:@[^\s@,;:()]+\.[^\s@,;:()]+)?)\s*(?:[,;&+]|\s(?:và|va)\s)\s*(?=@)/i;
const SUBJECT_MAX = 140;
/* "cao" / "thấp" đứng một mình ở CUỐI câu = ưu tiên Cao / Thấp, trừ khi là nửa sau của một từ ghép ("chiều cao", "nâng cao",
   "giá thấp"...). "báo cáo cao điểm" không đổi vì "cao" không ở cuối. So khớp trên chữ đã bỏ dấu. */
const TAIL_PRI_BLOCK = ["chieu", "do", "nang", "cap", "toi", "muc", "gia", "diem", "tam", "ha", "bac", "voc", "luong", "ap", "dat", "len", "xuong", "hon", "rat", "kha", "qua", "nhat"];
const WEEKDAY_RX = /(^|\s)(thu ?([2-7]|hai|ba|tu|nam|sau|bay)|t[2-7]|chu nhat|cn)(\s|$)/;
const VISIT_STALE_MS = 15000;
/* Hàm CHỈ ĐỌC đi window.ecApi.get (GET, không cần CSRF) khi có: tránh "Invalid Request" khi mở thẳng / F5 (xem pm_rooms.js). */
const READ_GET = { "queue.list": 1, "assignment.list_assignable": 1, "tasks.get": 1 };
let UID = 0, LAST_TAB = "me", LAST_ASK = true, LAST_WAIT = false, LAST_SPLIT = true;   /* nhớ trong phiên: tab đang xem, ô "Cần đồng ý" + cách chia người của giao nhanh */

/* ------------------------------------------------------------------ helpers thuần */
const pad = n => (n < 10 ? "0" : "") + n;
const esc = s => (s == null ? "" : String(s)).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const utc = ymd => { const p = String(ymd).split("-").map(Number); return Date.UTC(p[0], p[1] - 1, p[2]); };
function ymdAdd(ymd, n) { const t = new Date(utc(ymd) + n * 86400000); return t.getUTCFullYear() + "-" + pad(t.getUTCMonth() + 1) + "-" + pad(t.getUTCDate()); }
const dayDiff = (a, b) => Math.round((utc(b) - utc(a)) / 86400000);
const dow = ymd => new Date(utc(ymd)).getUTCDay();
const dm = ymd => WD[dow(ymd)] + " " + ymd.slice(8, 10) + "/" + ymd.slice(5, 7);
const toMin = t => { const x = /^(\d{1,2}):(\d{2})/.exec(t || ""); return x ? (+x[1]) * 60 + (+x[2]) : null; };
const isYmd = s => /^\d{4}-\d{2}-\d{2}$/.test(String(s || ""));
function localYmd() { const d = new Date(); return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
function localHm() { const d = new Date(); return pad(d.getHours()) + ":" + pad(d.getMinutes()); }
function fold(s) { s = String(s || "").toLowerCase(); if (s.normalize) s = s.normalize("NFD").replace(/[̀-ͯ]/g, ""); return s.replace(/đ/g, "d"); }
const truthy = v => v === true || v === 1 || v === "1" || v === "true";
const num = v => { const n = Math.floor(+v); return isFinite(n) && n > 0 ? n : 0; };   /* số đếm từ server -> số nguyên ≥ 0 (không chèn chuỗi vào HTML) */
function cookieUser() { try { const m = D.cookie.match(/(?:^|;\s*)user_id=([^;]+)/), u = m ? decodeURIComponent(m[1]) : ""; return u && u !== "Guest" ? u : ""; } catch (_) { return ""; } }
const priOf = p => (PRI[p] ? p : "Medium");
function initials(name) { const w = String(name || "?").trim().split(/\s+/); return (w.length > 1 ? w[w.length - 1].charAt(0) : w[0].charAt(0)).toUpperCase() || "?"; }
/* tên việc trong toast: cắt ~60 ký tự để toast không chiếm cả màn */
const qt = s => { s = String(s == null ? "" : s); return "“" + (s.length > 60 ? s.slice(0, 57).trim() + "…" : s) + "”"; };
function handleOf(p) { const w = String(p.full_name || "").trim().split(/\s+/).filter(Boolean); return (w.length ? w[w.length - 1] : String(p.email || "").split("@")[0]).replace(/[@,;:()]/g, ""); }
function cleanMsg(s) { return String(s).replace(/<[^>]*>/g, " ").replace(/^\s*[\w.]*(Error|Exception):\s*/, "").replace(/\s+/g, " ").trim(); }
function serverMsg(sm) {
  try {
    const arr = typeof sm === "string" ? JSON.parse(sm) : sm;
    for (let i = 0; i < (arr || []).length; i++) {
      let o = arr[i];
      if (typeof o === "string") { try { o = JSON.parse(o); } catch (_) { o = { message: o }; } }
      const m = o && (o.message || o.title);
      if (m) return cleanMsg(m);
    }
  } catch (_) { /* không phải danh sách thông báo */ }
  return "";
}
function msgOf(e, fb) {
  fb = fb || "Đã có lỗi, thử lại.";
  if (!e) return fb;
  if (e.csrf) return "Phiên đăng nhập đã đổi. Bấm Ctrl+Shift+R để tải lại trang.";
  const sm = e._server_messages || (e.responseJSON && e.responseJSON._server_messages) || (e.body && e.body._server_messages);
  let m = sm ? serverMsg(sm) : "";
  if (!m && typeof e.message === "string" && e.message.trim()) {
    const t = e.message.trim();
    m = t.charAt(0) === "[" ? serverMsg(t) : "";
    if (!m && t.charAt(0) !== "{" && t.charAt(0) !== "[") m = cleanMsg(t);
  }
  if (!m && typeof e === "string") m = cleanMsg(e);
  if (m && e.excType && m === e.excType) m = "";   /* ecApi: message = tên lỗi ("ValidationError"), không phải câu cho người dùng */
  return m || fb;
}
const excOf = e => (e && (e.excType || e.exc_type || (e.responseJSON && e.responseJSON.exc_type) || (e.body && e.body.exc_type))) || "";
const noAccess = e => !!e && (excOf(e) === "PermissionError" || e.status === 403);
/* mô tả HTML của Task -> chữ thường (tài liệu trơ: không chạy script, không tải ảnh) */
function htmlText(h) {
  if (!h) return "";
  const s = String(h).replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|h[1-6]|tr)>/gi, "\n");
  let t;
  try { const doc = D.implementation.createHTMLDocument(""); doc.body.innerHTML = s; t = doc.body.textContent || ""; }
  catch (_) { t = s.replace(/<[^>]*>/g, " "); }
  return t.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

/* ---- giao việc 1 dòng: tách @người, từ ưu tiên, hạn (PMR._pure.parseDue) ---- */
function stripPriority(s) {
  let pri = null;
  PRI_WORDS.forEach(pw => {
    const rx = new RegExp("(^|[\\s,.;:()!?-])" + pw[0].replace(/ /g, "\\s+") + "(?=$|[\\s,.;:()!?-])", "g");
    let m, low = s.toLowerCase();
    while ((m = rx.exec(low))) {
      const at = m.index + m[1].length, len = m[0].length - m[1].length;
      if (!pri) pri = pw[1];
      s = s.slice(0, at) + " ".repeat(len) + s.slice(at + len);   /* thay bằng khoảng trắng: giữ nguyên vị trí */
      low = s.toLowerCase();
    }
  });
  return { text: s.replace(/\s+/g, " ").trim(), pri };
}
function tailPriority(s) {
  const low = String(s || "").toLowerCase(), m = /(^|[\s,;:()-])(cao|thấp)[\s,.;:!?-]*$/.exec(low);
  if (!m) return null;
  const before = s.slice(0, m.index + m[1].length).replace(/[\s,;:()-]+$/, "");
  if (!before) return null;   /* cả câu chỉ có "cao": là tên việc */
  const w = fold(before.split(/\s+/).pop());
  if (TAIL_PRI_BLOCK.indexOf(w) >= 0) return null;
  return { text: before, pri: m[2] === "cao" ? "High" : "Low" };
}
const ymdOfDate = d => d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
/* -> {subject, tokens (mọi @, theo thứ tự, bỏ trùng không dấu), token (= tokens[0] | ""), priority (Urgent|High|Medium|Low|null),
   due (YYYY-MM-DD|null), time (HH:MM|null), from}
   o: {parseDue, base (Date)}. Hạn: cụm ở CUỐI câu trước (an toàn); không có thì tìm trong câu, trừ "cuối tuần/tháng"
   ("Báo cáo cuối tháng" là tên việc). */
function parseLine(text, o) {
  o = o || {};
  let s = String(text || "");
  if (s.normalize) s = s.normalize("NFC");
  s = s.replace(/\s+/g, " ").trim();
  while (AT_JOIN.test(s)) s = s.replace(AT_JOIN, "$1$2 ");
  const tokens = [], seen = {};
  let m;
  while ((m = AT_RX.exec(s))) {
    const tk = m[2].replace(/[.\-]+$/, "");
    if (tk && !seen[fold(tk)]) { seen[fold(tk)] = 1; tokens.push(tk); }
    s = (s.slice(0, m.index) + m[1] + s.slice(m.index + m[0].length)).replace(/\s+/g, " ").trim();
  }
  if (tokens.length) s = s.replace(/^[\s,;:&+-]+/, "");   /* "@Lan, @Phú: báo cáo" -> "báo cáo" */
  const sp = stripPriority(s);
  s = sp.text;
  let pri = sp.pri;
  if (!pri) { const tp = tailPriority(s); if (tp) { s = tp.text; pri = tp.pri; } }
  let due = null, time = null, from = "";
  if (typeof o.parseDue === "function" && s) {
    let p = null;
    try { p = o.parseDue(s, { base: o.base, tail: true }); } catch (_) { p = null; }
    if (!p) {
      try { p = o.parseDue(s, { base: o.base }); } catch (_) { p = null; }
      if (p && /cu[oố]i (tu[aầ]n|th[aá]ng)/i.test(p.from || "")) p = null;
    }
    if (p && p.due) { due = p.due; time = p.time || null; from = p.from || ""; s = p.rest || s; }
    /* "thứ 6" gõ đúng vào thứ Sáu: muốn hôm nay thì người ta gõ "hôm nay" -> thứ Sáu tuần sau */
    if (due && o.base instanceof Date && due === ymdOfDate(o.base) && WEEKDAY_RX.test(fold(from))) due = ymdAdd(due, 7);
    if (!pri) { const tp = tailPriority(s); if (tp) { s = tp.text; pri = tp.pri; } }   /* "gửi file cao thứ 6" */
  }
  return { subject: s, tokens, token: tokens[0] || "", priority: pri, due, time, from };
}
/* chữ trong ô trước khi sửa theo từng @ (× / chọn người): NFC (chữ dán dạng tổ hợp NFD) + bỏ chữ nối giữa hai @ như parseLine
   ("@Lan,@Phú", "@Lan và @Phú"). Không thì × không khớp @ sau dấu phẩy, hoặc bỏ @ đầu để lại ",@Phú" / "và" trong tên việc (QA 16/11). */
function atNorm(v) {
  v = String(v || "");
  if (v.normalize) v = v.normalize("NFC");
  while (AT_JOIN.test(v)) v = v.replace(AT_JOIN, "$1$2 ");
  return v;
}
/* khớp @tên không dấu: email (4) > tên gọi = chữ cuối (3) > một chữ trong tên (2) > bắt đầu bằng (1) */
function matchPeople(token, people) {
  const t = fold(token);
  if (!t) return [];
  const out = [];
  (people || []).forEach(p => {
    const nm = fold(p.full_name || ""), words = nm.split(/\s+/).filter(Boolean), loc = fold(String(p.email || "").split("@")[0]);
    let sc = 0;
    if (loc === t || fold(p.email) === t) sc = 4;
    else if (words.length && words[words.length - 1] === t) sc = 3;
    else if (words.indexOf(t) >= 0) sc = 2;
    else if (nm.replace(/\s+/g, "").indexOf(t) === 0 || loc.indexOf(t) === 0 || words.some(w => w.indexOf(t) === 0)) sc = 1;
    if (sc) out.push({ p, sc });
  });
  out.sort((a, b) => b.sc - a.sc || String(a.p.full_name || "").localeCompare(String(b.p.full_name || "")));
  return out;
}
function resolvePerson(token, people, pick) {
  if (!token) return null;
  if (pick && fold(pick.token) === fold(token)) return { email: pick.email, name: pick.name };
  if (!people) return { loading: true };
  const ms = matchPeople(token, people);
  if (!ms.length) return { missing: true };
  const top = ms.filter(x => x.sc === ms[0].sc);
  if (top.length === 1) return { email: top[0].p.email, name: top[0].p.full_name || top[0].p.email };
  return { ambiguous: top.slice(0, 5).map(x => x.p) };
}

/* ------------------------------------------------------------------ mạng */
function csrf() { return (root.frappe && root.frappe.csrf_token) || root.csrf_token || ((D.cookie.match(/csrf_token=([^;]+)/) || [])[1]) || ""; }
async function fetchApi(method, args) {
  const r = await fetch("/api/method/" + method, { method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-Frappe-CSRF-Token": csrf() }, body: JSON.stringify(args || {}) });
  let j = {};
  try { j = await r.json(); } catch (_) { /* thân rỗng */ }
  if (!r.ok || j.exc_type) { const e = new Error(j.exception || ("HTTP " + r.status)); e._server_messages = j._server_messages; e.status = r.status; throw e; }
  return j.message;
}
/* F5: asset có thể chạy TRƯỚC ec_api.bundle.js -> chờ ecApi tối đa ~3 giây nếu trang còn tải / có thẻ ec_api */
function waitEcApi() {
  if (root.ecApi) return Promise.resolve(root.ecApi);
  const later = () => {
    if (root.ecApi || !D.querySelector('script[src*="ec_api"]')) return Promise.resolve(root.ecApi || null);
    return new Promise(res => { let n = 0; const t = setInterval(() => { if (root.ecApi || ++n > 40) { clearInterval(t); res(root.ecApi || null); } }, 75); });
  };
  if (D.readyState === "loading") return new Promise(r => D.addEventListener("DOMContentLoaded", r, { once: true })).then(later);
  return later();
}

/* ------------------------------------------------------------------ icon (SVG một nét) */
const IC = {
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>', play: '<path d="M8 5.5v13l10-6.5z"/>', clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>',
  bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  sort: '<path d="M7 4v16M3.5 16.5L7 20l3.5-3.5M17 20V4M13.5 7.5L17 4l3.5 3.5"/>',
  user: '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/>',
  hand: '<path d="M7 11V6.5a1.5 1.5 0 0 1 3 0V11M10 10.5V5a1.5 1.5 0 0 1 3 0v5.5M13 10.5V6a1.5 1.5 0 0 1 3 0v6M16 11.5a1.5 1.5 0 0 1 3 0V15a6 6 0 0 1-6 6h-1.5a6 6 0 0 1-5-2.7L4 14.5a1.5 1.5 0 0 1 2.4-1.8L7 13.5"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  inbox: '<path d="M3.5 13.5l2.5-7h12l2.5 7v4.5a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1z"/><path d="M3.5 13.5h5l1.5 2.5h4l1.5-2.5h5"/>',
  send: '<path d="M20.5 3.5l-17 7.2 6.8 2.5 2.5 6.8z"/><path d="M10.3 13.2l4.2-4.2"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  alert: '<circle cx="12" cy="12" r="8.5"/><path d="M12 8v4.5M12 16h.01"/>',
  retry: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>'
};
const ic = (n, cls) => `<svg class="pmq-i${cls ? " " + cls : ""}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${IC[n]}</svg>`;

/* ------------------------------------------------------------------ component */
function render(el, opts) {
  opts = opts || {};
  if (el._pmq) el._pmq.destroy();
  const uid = ++UID, idp = "pmq" + uid + "-";
  let user = String(opts.user || "");
  /* F5 sớm: host có thể chưa biết user (window._pmUser điền sau) -> đọc lại khi cần, cookie user_id của Frappe */
  const me = () => { if (!user) user = cookieUser() || (root._pmUser && root._pmUser !== "User" && root._pmUser !== "Guest" ? String(root._pmUser) : ""); return user; };
  const S = { tab: opts.tab === "give" || opts.tab === "me" ? opts.tab : LAST_TAB, filter: "all", data: { me: null, give: null }, err: null,
    sel: null, open: null, openKey: false, detail: {}, busy: {}, just: {}, people: null, peopleP: null, peopleErr: null,
    qa: null, ac: null, askForm: null, askBusy: {}, timers: [], dead: false, seq: 0, lastFetch: 0, stale: false, sig: { me: "", give: "" }, waitOpen: LAST_WAIT,
    inflight: null, pending: false, chT: null, nudged: {}, toastT: null, toastMs: 0, personal: false, askAll: false, qaN: 0, qaLast: 0, composing: false, lostK: null };
  try { S.personal = root.localStorage.getItem(LSK) === "1"; } catch (_) { S.personal = false; }

  function call(m, a) {
    const args = {};
    for (const k in (a || {})) if (Object.prototype.hasOwnProperty.call(a, k) && a[k] != null) args[k] = a[k];
    const go = () => { try { return Promise.resolve(typeof opts.api === "function" ? opts.api(NS + m, args) : fetchApi(NS + m, args)); } catch (e) { return Promise.reject(e); } };
    /* GHI: ecApi.post (xin CSRF tươi, thử lại 1 lần khi token cũ) nếu trang có ec_api; HTML /pm có thể là bản cache mang token
       cũ -> frappe.call báo "Invalid Request" + bật hộp thoại (sự cố #rooms 09/11). Không có ecApi thì như cũ (api của host). */
    if (!READ_GET[m]) {
      const ec = root.ecApi;
      return ec && typeof ec.post === "function" ? Promise.resolve().then(() => ec.post(NS + m, args)) : go();
    }
    /* ĐỌC: ecApi.get; server đã trả lỗi Frappe (vd không có quyền PM) thì báo luôn, chỉ lỗi mạng mới thử lại đường host
       (frappe.call lỗi còn bật thêm một hộp thoại). */
    return waitEcApi().then(ec => (ec && typeof ec.get === "function" ? Promise.resolve().then(() => ec.get(NS + m, args)).catch(e => (excOf(e) ? Promise.reject(e) : go())) : go()));
  }
  function alive() { if (!S.dead && R && !R.isConnected) destroy(); return !S.dead; }
  function later(ms, fn) { const t = setTimeout(() => { S.timers = S.timers.filter(x => x !== t); if (alive()) fn(); }, ms); S.timers.push(t); return t; }
  const today = () => { const d = S.data.me || S.data.give; return (d && isYmd(d.today)) ? d.today : localYmd(); };
  const nowHm = () => { const d = S.data.me || S.data.give; return (d && d.now) || localHm(); };
  const baseDate = () => { const t = today().split("-").map(Number), h = (nowHm().split(":").map(Number)); return new Date(t[0], t[1] - 1, t[2], h[0] || 0, h[1] || 0); };
  const parseDueFn = () => { const p = root.PMR && root.PMR._pure; return p && typeof p.parseDue === "function" ? p.parseDue : null; };
  const mobile = () => { try { return !!(root.matchMedia && root.matchMedia("(max-width: 640px)").matches); } catch (_) { return false; } };
  function emit(name, detail) { try { D.dispatchEvent(new root.CustomEvent(name, { detail })); } catch (_) { /* trình duyệt cũ */ } }
  const changed = d => emit("pmr:changed", Object.assign({ source: "pmq" }, d || {}));
  function openFull(name, o) {
    const f = typeof opts.openTask === "function" ? opts.openTask : (root.PMR && typeof root.PMR.openTask === "function" ? root.PMR.openTask : null);
    if (!f) { toast("Chưa mở được việc. Bấm Ctrl+Shift+R để tải lại trang.", { bad: true }); return; }
    try { f(name, o); } catch (e) { toast(msgOf(e), { bad: true }); }
  }

  /* ---------------- khung (trạng thái đầu nằm trong markup: tiêu đề cố định + xương 6 dòng) */
  const tabsHtml = '<div class="pmq-seg" role="group" aria-label="Xem việc">' +
    `<button type="button" data-tab="me" aria-pressed="${S.tab === "me"}">Việc tôi làm <span class="pmq-c pmq-num" data-c="me"></span></button>` +
    `<button type="button" data-tab="give" aria-pressed="${S.tab === "give"}">Việc tôi giao <span class="pmq-c pmq-num" data-c="give"></span></button></div>`;
  const headHtml = typeof opts.head === "function" ? opts.head("Việc cần làm", "Đang tải…", tabsHtml)
    : '<div class="pm-head pmq-head"><div><h1>Việc cần làm</h1><div class="sub">Đang tải…</div></div><div>' + tabsHtml + "</div></div>";
  el.innerHTML = '<div class="pmq" data-pmq>' + headHtml +
    `<section class="pmq-panel pmq-qa" aria-label="Giao việc nhanh"><form class="pmq-qa-line" data-qa-form novalidate autocomplete="off">` +
      `<div class="pmq-qa-field">${ic("plus")}<label class="pmq-vh" for="${idp}qa">Giao việc nhanh</label>` +
      `<input id="${idp}qa" class="pmq-qa-in" data-qa type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${idp}ac" aria-describedby="${idp}parse" maxlength="240" enterkeyhint="send" spellcheck="false" placeholder="Giao việc: @Lan gửi báo cáo GMV thứ 6 gấp">` +
      `<kbd class="pmq-kbd pmq-qa-kn" aria-hidden="true">N</kbd>` +
      `<ul class="pmq-acl" id="${idp}ac" role="listbox" aria-label="Chọn người nhận" hidden></ul></div>` +
      `<button type="submit" class="pmq-btn pmq-btn--pri pmq-qa-go" data-qa-go>Giao việc</button>` +
      `<button type="button" class="pmq-btn pmq-btn--q pmq-qa-more" data-act="qa-more" aria-keyshortcuts="Shift+Enter" title="Mở form đầy đủ: mô tả, các bước, lặp lại (Shift+Enter)">Thêm chi tiết</button>` +
      `</form>` +
      `<div class="pmq-parse" id="${idp}parse" data-parse></div></section>` +
    '<div data-ask></div>' +
    '<div class="pmq-bar" data-bar><div class="pmq-dist" role="group" aria-label="Lọc theo hạn" data-dist><span class="pmq-skel-chip"></span><span class="pmq-skel-chip"></span><span class="pmq-skel-chip"></span></div>' +
      `<span class="pmq-rule" title="Một quy tắc cho web, tin Teams buổi sáng và trợ lý: nhóm hạn trước, cùng nhóm thì ưu tiên cao trước, rồi tới giờ">${ic("sort")}<span class="pmq-rule-l">Thứ tự:</span> <b>Hạn</b><span aria-hidden="true">→</span><b>Ưu tiên</b><span aria-hidden="true">→</span><b>Giờ</b></span></div>` +
    `<div class="pmq-wrap" data-wrap><div class="pmq-panel pmq-list" data-list aria-busy="true">${skelHtml()}</div>` +
      `<aside class="pmq-panel pmq-dr" id="${idp}dr" data-drawer aria-label="Chi tiết việc" hidden></aside></div>` +
    '<div class="pmq-note" data-note hidden></div>' +   /* dưới danh sách: hiện sau khi tải không đẩy danh sách xuống */
    `<p class="pmq-keys" data-keys>${keysHtml(S.tab)}</p>` +
    '<div class="pmq-toast" role="status" aria-live="polite"><span data-tm></span><span class="pmq-toast-acts" data-tacts></span></div></div>';
  const R = el.querySelector("[data-pmq]");
  const $ = (s, r) => (r || R).querySelector(s), $$ = (s, r) => Array.prototype.slice.call((r || R).querySelectorAll(s));
  const SUB = $(".pm-head .sub, .sub");
  if (SUB) SUB.setAttribute("data-sub", "1");
  const QIN = $("[data-qa]");

  function keysHtml(tab) {
    const K = (k, t) => `<span>${k.map(x => `<kbd class="pmq-kbd">${x}</kbd>`).join("")} ${t}</span>`;
    return K(["J", "K"], "lên / xuống") + (tab === "me" ? K(["X"], "xong") + K(["S"], "bắt đầu") : "") + K(["Enter"], "xem chi tiết") + K(["N"], "giao việc") + K(["Esc"], "đóng");
  }
  function skelHtml() {
    let h = '<div class="pmq-cols" aria-hidden="true"><span></span><span></span><span>Việc</span><span class="pmq-hp">Ưu tiên</span><span>Hạn</span><span class="pmq-hw"></span><span class="pmq-ha"></span></div>';
    for (let i = 0; i < 6; i++) h += '<div class="pmq-skel" aria-hidden="true"><i></i><i></i><b></b><i></i><i></i></div>';
    return h + '<span class="pmq-vh">Đang tải danh sách việc…</span>';
  }

  /* ---------------- toast (có nút Hoàn tác) */
  function toast(msg, o) {
    o = o || {};
    if (!alive()) return;
    const t = $(".pmq-toast"), acts = $("[data-tacts]");
    $("[data-tm]").textContent = msg;
    acts.innerHTML = "";
    (o.actions || []).forEach(a => {
      const b = D.createElement("button");
      b.type = "button"; b.className = "pmq-toast-b"; b.textContent = a.label;
      b.addEventListener("click", () => { hideToast(); try { a.run(); } catch (e) { toast(msgOf(e), { bad: true }); } });
      acts.appendChild(b);
    });
    t.setAttribute("role", o.bad ? "alert" : "status");
    t.className = "pmq-toast pmq-toast--on" + (o.bad ? " pmq-toast--bad" : "");
    clearTimeout(S.toastT);
    S.toastMs = o.bad ? 6000 : (o.actions && o.actions.length ? 8000 : 3200);   /* có Hoàn tác: 8 giây cho người đọc chậm */
    S.toastT = setTimeout(hideToast, S.toastMs);
  }
  function hideToast() { clearTimeout(S.toastT); const t = R && $(".pmq-toast"); if (t) t.className = "pmq-toast"; }
  /* rê chuột / focus vào toast -> dừng đếm (kịp bấm Hoàn tác); rời ra -> đóng sau 2,5 giây */
  function toastHold() { clearTimeout(S.toastT); }
  function toastResume() { const t = R && $(".pmq-toast"); if (t && t.classList.contains("pmq-toast--on")) { clearTimeout(S.toastT); S.toastT = setTimeout(hideToast, 2500); } }

  /* ---------------- dữ liệu */
  const cur = () => S.data[S.tab];
  const rowsAll = () => ((cur() || {}).rows) || [];
  /* bộ lọc: "all", một nhóm hạn, hoặc (tab giao) "unopened" = người nhận chưa mở việc */
  const inFilter = (r, f) => f === "all" || (f === "unopened" ? !!r.unopened : r.bucket === f);
  const visible = () => rowsAll().filter(r => inFilter(r, S.filter));
  const filterCount = f => rowsAll().filter(r => inFilter(r, f)).length;
  const waitRows = () => (S.tab === "me" && cur() && cur().waiting) || [];
  const rowOf = name => rowsAll().find(r => r.name === name) || waitRows().find(r => r.name === name) || null;
  function norm(d) {
    d = d || {};
    const counts = {};
    Object.keys(d.counts || {}).forEach(k => { counts[k] = num(d.counts[k]); });
    return { today: d.today, now: d.now, tab: d.tab, rows: Array.isArray(d.rows) ? d.rows : [], counts,
      buckets: Array.isArray(d.buckets) && d.buckets.length ? d.buckets : [{ key: "late", label: "Quá hạn" }, { key: "today", label: "Hôm nay" }, { key: "tomorrow", label: "Ngày mai" },
        { key: "week", label: "Còn lại tuần này" }, { key: "later", label: "Tuần sau trở đi" }, { key: "none", label: "Chưa có hạn" }],
      asks: Array.isArray(d.asks) ? d.asks : [], personal_hidden: num(d.personal_hidden),
      waiting: Array.isArray(d.waiting) ? d.waiting : [], truncated: truthy(d.truncated), limit: num(d.limit),
      proposals: Array.isArray(d.proposals) ? d.proposals.filter(p => p && p.counter && p.counter.request) : [] };
  }
  /* chữ ký dữ liệu: tự làm mới 60 giây mà server trả y hệt -> không vẽ lại (giữ focus, hover, chỗ cuộn, không đọc lại cho trình đọc màn hình).
     `now` chỉ tính khi có việc trễ theo giờ hôm nay ("Trễ 25 phút" phải nhảy số). */
  function sigOf(d) {
    if (!d) return "";
    const minute = (d.rows || []).concat(d.waiting || []).some(r => r && r.bucket === "late" && r.due === d.today && r.due_time);
    try { return JSON.stringify([d.today, minute ? d.now : "", d.rows, d.counts, d.asks, d.waiting, d.proposals, d.personal_hidden, d.truncated]); } catch (_) { return String(Math.random()); }
  }
  function refresh(o) {
    o = o || {};
    if (!alive()) return Promise.resolve();
    if (o.since && S.lastFetch >= o.since) return Promise.resolve();   /* đã có lần tải bắt đầu SAU thay đổi: đủ mới */
    if (S.inflight && !o.force) { S.pending = true; return S.inflight; }
    const seq = ++S.seq, tab = S.tab, other = tab === "me" ? "give" : "me", inc = S.personal ? 1 : 0;
    S.lastFetch = Date.now();
    if (!S.data[tab] && !S.err) paintList();
    const p = Promise.all([call("queue.list", { tab, include_personal: inc }), call("queue.list", { tab: other, include_personal: inc }).catch(() => null)]).then(res => {
      if (S.dead || seq !== S.seq) return;
      const before = S.data[tab] ? visible().map(r => r.name) : [];
      const sig = sigOf(res[0]), osig = res[1] ? sigOf(res[1]) : S.sig[other];
      /* chỉ lần tự làm mới (60 giây / quay lại tab / màn khác báo đổi) mới được bỏ qua; sau thao tác (force) luôn vẽ */
      const same = !o.force && !!S.data[tab] && !S.err && sig === S.sig[tab] && osig === S.sig[other] && !Object.keys(S.just).length;
      S.data[tab] = norm(res[0]); S.sig[tab] = sig;
      if (res[1]) { S.data[other] = norm(res[1]); S.sig[other] = osig; }
      S.err = null; S.stale = false;
      if (same) return;   /* không đổi gì: không đụng DOM */
      const vis = visible().map(r => r.name);
      if (S.filter !== "all" && !filterCount(S.filter)) S.filter = "all";
      if (S.sel && vis.indexOf(S.sel) < 0 && !waitRows().some(r => r.name === S.sel)) S.sel = nextSel(before, S.sel, vis);
      if (S.open && !rowOf(S.open)) closeDrawer(true);
      paint();
      const me = S.data.me;
      if (me && !S.personal) emit("pmr:badge", { key: "mywork", count: me.rows.length });
    }, e => {
      if (S.dead || seq !== S.seq) return;
      if (!S.data[tab]) { S.err = e; paint(); }
      else if (o.manual) toast(msgOf(e, "Chưa làm mới được danh sách."), { bad: true });
      else S.stale = true;
    }).then(() => {
      if (S.inflight === p) S.inflight = null;
      if (S.pending && !S.dead) { S.pending = false; refresh(); }
    });
    S.inflight = p;
    return p;
  }
  /* việc đang chọn vừa rời danh sách (xong / huỷ / đổi hạn): chọn việc kế tiếp còn lại, hết thì việc ngay trước — làm từ trên xuống
     bằng phím không phải bấm J lại. Không thấy vị trí cũ -> bỏ chọn. */
  function nextSel(before, gone, vis) {
    const i = before.indexOf(gone);
    if (i < 0 || !vis.length) return null;
    for (let j = i + 1; j < before.length; j++) if (vis.indexOf(before[j]) >= 0) return before[j];
    for (let j = i - 1; j >= 0; j--) if (vis.indexOf(before[j]) >= 0) return before[j];
    return null;
  }
  function people() {
    if (S.people) return Promise.resolve(S.people);
    if (!S.peopleP) {
      S.peopleP = call("assignment.list_assignable", {}).then(r => {
        S.people = ((r && r.rows) || []).filter(x => x && x.email);
        S.peopleErr = null;
        return S.people;
      }, e => { S.peopleP = null; S.peopleErr = e; throw e; });
    }
    return S.peopleP;
  }

  /* ---------------- hiển thị dùng chung */
  const priHtml = p => { p = priOf(p); return `<span class="pmq-pri pmq-p${PRI[p][0]}"><span class="pmq-bars" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span class="pmq-pri-l">${PRI[p][1]}</span></span>`; };
  function dueInfo(r) {
    const due = isYmd(r.due) ? r.due : null, tm = r.due_time || "", b = r.bucket;
    if (!due) return { rel: "Chưa có hạn", abs: "", cls: "none" };
    const abs = dm(due) + (tm ? " · " + tm : ""), td = today();
    let rel;
    if (b === "late") {
      const n = dayDiff(due, td);
      if (n > 0) rel = "Trễ " + n + " ngày";
      else { const mins = Math.max(1, (toMin(nowHm()) || 0) - (toMin(tm) || 0)); rel = mins >= 60 ? "Trễ " + Math.floor(mins / 60) + " giờ" : "Trễ " + mins + " phút"; }
    } else if (b === "today") rel = tm ? "Hôm nay " + tm : "Hôm nay";
    else if (b === "tomorrow") rel = tm ? "Ngày mai " + tm : "Ngày mai";
    else rel = "Còn " + Math.max(1, dayDiff(td, due)) + " ngày";
    return { rel, abs, cls: b === "late" ? "late" : (b === "today" ? "today" : "") };
  }
  const dueHtml = r => { const d = dueInfo(r); return `<span class="pmq-due${d.cls ? " pmq-due--" + d.cls : ""}"><b>${esc(d.rel)}</b><small class="pmq-num">${d.abs ? esc(d.abs) : "&nbsp;"}</small></span>`; };
  const av = (key, name) => `<span class="pmq-av" aria-hidden="true">${esc(initials(name || key))}</span>`;   /* trung tính: màu chỉ dành cho trạng thái */
  function personHtml(r) {
    if (S.tab === "me") {
      if (r.self) return `<span class="pmq-who pmq-who--self">${av(me(), "Tôi")}<span>Tự ghi</span></span>`;
      const n = r.giver_name || r.giver || "—";
      return `<span class="pmq-who" title="${esc(n)}">${av(r.giver, n)}<span>${esc(n)}</span></span>`;
    }
    const a = r.assignees || [];
    if (!a.length) return '<span class="pmq-who pmq-muted">—</span>';
    const all = a.map(x => x.name || x.user).join(", ");
    return `<span class="pmq-who" title="${esc(all)}">${av(a[0].user, a[0].name || a[0].user)}<span>${esc(a[0].name || a[0].user)}</span>${a.length > 1 ? `<span class="pmq-more pmq-num">+${a.length - 1}</span>` : ""}</span>`;
  }
  const stateOf = r => S.just[r.name] || r.workflow_state || "To Do";
  const canDone = r => S.tab === "me" && !r.group && stateOf(r) !== "Review" && stateOf(r) !== "Done";
  /* Chờ duyệt mà TÔI là người giao (tab giao; tab tôi làm: việc tự ghi / việc cha chia nhiều người) -> tôi duyệt (close_parent) */
  const canApprove = r => stateOf(r) === "Review" && (S.tab === "give" || (S.tab === "me" && !!r.self));
  function chkHtml(r, k) {
    const st = stateOf(r), done = st === "Done", busy = !!S.busy[r.name];
    let label = "Đánh dấu xong", dis = false;
    if (canApprove(r)) label = "Duyệt xong";
    else if (S.tab !== "me") { label = r.awaiting ? "Chờ người nhận đồng ý" : (r.progress ? "Xong khi mọi người xong phần của mình" : "Người nhận đánh dấu xong"); dis = true; }
    else if (r.group) { label = "Việc chia nhiều người: xong khi mọi người xong phần của mình"; dis = true; }
    else if (st === "Review") { label = "Đang chờ người giao kiểm tra"; dis = true; }
    else if (done) { label = "Đã xong"; dis = true; }
    const cls = done ? " pmq-chk--done" : (st === "In Progress" ? " pmq-chk--doing" : (st === "Review" ? " pmq-chk--review" : ""));
    return `<button type="button" class="pmq-chk${cls}" data-act="done" data-name="${esc(r.name)}" data-k="${k}:done:${esc(r.name)}" aria-label="${esc(label + ": " + (r.subject || r.name))}" title="${esc(label)}"${dis || busy ? " disabled" : ""}${busy ? ' aria-busy="true"' : ""}>${ic("check")}</button>`;
  }
  function tagsHtml(r) {
    const st = stateOf(r), t = [];
    if (r.project_name) t.push(`<span class="pmq-tag">${esc(r.project_name)}</span>`);
    if (st === "In Progress") t.push('<span class="pmq-st pmq-st--doing">Đang làm</span>');
    if (st === "Review") t.push('<span class="pmq-st pmq-st--review">Chờ duyệt</span>');
    if (st === "Blocked") t.push('<span class="pmq-st pmq-st--blocked">Bị chặn</span>');
    if (r.awaiting) t.push('<span class="pmq-st pmq-st--wait">Chờ nhận</span>');
    if (r.unopened) t.push('<span class="pmq-tag pmq-tag--warn">Chưa mở việc</span>');
    if (S.tab === "give" && S.nudged[r.name]) t.push(`<span class="pmq-tag pmq-num">Đã nhắc ${esc(S.nudged[r.name])}</span>`);
    const ask = askedDue(r);
    if (ask) t.push(`<span class="pmq-st pmq-st--wait">Đã xin dời sang ${esc(dm(ask))}</span>`);
    const pg = r.progress;
    if (pg && num(pg.total)) t.push(`<span class="pmq-tag pmq-num">${num(pg.done)}/${num(pg.total)} người xong</span>`);
    else if (r.group) t.push('<span class="pmq-tag">Nhiều người</span>');
    if (S.tab === "give" && (r.assignees || []).some(a => truthy(a.left))) t.push('<span class="pmq-tag pmq-tag--warn">Người nhận đã nghỉ</span>');
    if (S.tab === "me" && truthy(r.giver_left)) t.push('<span class="pmq-tag">Người giao đã nghỉ</span>');
    return t.join("");
  }
  /* hạn mới mình đã xin (Xin dời hạn đang chờ người giao) — chỉ tab tôi làm */
  const askedDue = r => (S.tab === "me" && r.deadline_ask && isYmd(r.deadline_ask.due) ? r.deadline_ask.due : "");
  function actsHtml(r, k, full) {
    const st = stateOf(r), n = esc(r.name), busy = S.busy[r.name] ? " disabled" : "";
    const B = (act, icon, label, title, cls) => `<button type="button" class="pmq-btn pmq-btn--sm ${cls || "pmq-btn--q"}" data-act="${act}" data-name="${n}" data-k="${k}:${act}:${n}"${title ? ` title="${esc(title)}"` : ""}${busy}>${ic(icon)}<span>${label}</span></button>`;
    if (st === "Done") return "";
    if (canApprove(r)) return B("approve", "check", "Duyệt xong", "Người nhận đã gửi kiểm tra: duyệt và đóng việc", "pmq-btn--pri") +
      (S.tab === "give" && !r.group ? B("return", "retry", "Trả lại", "Chưa đạt: trả lại cho người nhận làm tiếp") : "");
    if (S.tab === "give") return r.awaiting ? "" : B("nudge", "bell", "Nhắc", S.nudged[r.name] ? "Đã nhắc lúc " + S.nudged[r.name] + ". Mỗi người nhắc lại được sau 1 giờ"
      : (r.progress ? "Nhắc những người chưa xong phần của mình" : "Nhắc người nhận qua thông báo + Teams"));
    let h = "";
    if (full && canDone(r)) h += B("done", "check", "Xong", "Đánh dấu xong (X)", "pmq-btn--pri");
    if (st !== "In Progress" && st !== "Review" && !r.group) h += B("start", "play", "Bắt đầu", "Bắt đầu làm (S)");
    if (!r.self && !askedDue(r)) h += B("ask", "clock", "Xin dời hạn", "Xin người giao dời hạn");
    return h;
  }

  /* ---------------- vẽ */
  function captureFocus() {
    const a = D.activeElement;
    return a && R.contains(a) ? a.getAttribute("data-k") : null;
  }
  function restoreFocus(k) {
    if (!k) return;
    const n = R.querySelector('[data-k="' + (root.CSS && root.CSS.escape ? root.CSS.escape(k) : k.replace(/"/g, '\\"')) + '"]');
    if (n && !n.disabled) { S.lostK = null; try { n.focus({ preventScroll: true }); } catch (_) { n.focus(); } return; }
    if (S.sel && rowEl(S.sel) && /^[rd]:/.test(k)) { focusRow(S.sel); return; }
    /* nút đang bận (disabled) không giữ được focus: nhớ lại, lần vẽ sau (có kết quả) đưa focus về đúng chỗ */
    if (n) { S.lostK = k; return; }
    S.lostK = null;
    /* nút vừa bấm đã biến mất (việc chờ nhận đã nhận, dòng cuối đã xong): đưa focus về chỗ gần nhất thay vì rơi ra <body> */
    if (D.activeElement && D.activeElement !== D.body && R.contains(D.activeElement)) return;
    const next = k.indexOf("ask:") === 0 ? $(".pmq-ask [data-act='ask-accept']:not([disabled])")
      : (k.indexOf("prop:") === 0 ? $(".pmq-prop [data-act='prop-accept']:not([disabled])") : null);
    const tgt = next || $(".pmq-row .pmq-open") || $("[data-list] [data-act]") || QIN;
    if (tgt) { try { tgt.focus({ preventScroll: true }); } catch (_) { tgt.focus(); } }
  }
  function lostFocus() { const a = D.activeElement; return S.lostK && (!a || a === D.body || !a.isConnected) ? S.lostK : null; }
  /* vẽ lại một phần mà vẫn giữ focus (nút đang đứng / nút vừa bấm) */
  function keep(fn) { if (!alive()) return; const k = captureFocus() || lostFocus(); fn(); restoreFocus(k); }
  function paint() { keep(() => { paintHead(); paintAsk(); paintBar(); paintNote(); paintList(); paintDrawer(); }); }
  function paintHead() {
    $$("[data-tab]").forEach(b => b.setAttribute("aria-pressed", String(b.getAttribute("data-tab") === S.tab)));
    const kb = $("[data-keys]");
    if (kb && kb.getAttribute("data-for") !== S.tab) { kb.innerHTML = keysHtml(S.tab); kb.setAttribute("data-for", S.tab); }
    ["me", "give"].forEach(t => { const c = $('[data-c="' + t + '"]'); if (c) c.textContent = S.data[t] ? String(S.data[t].rows.length) : ""; });
    if (!SUB) return;
    const d = cur();
    if (!d) { SUB.textContent = S.err ? "Chưa tải được danh sách việc." : "Đang tải…"; return; }
    const n = d.rows.length, late = d.counts.late || 0, td = d.counts.today || 0;
    if (S.tab === "me") {
      const day = isYmd(d.today) ? WDN[dow(d.today)] + ", " + d.today.slice(8, 10) + "/" + d.today.slice(5, 7) + " · " : "";
      SUB.innerHTML = n ? `${esc(day)}<b class="pmq-num">${n}</b> việc đang mở` + (late ? `, <b class="pmq-num pmq-late">${late}</b> quá hạn` : "") +
        (td ? `, <b class="pmq-num">${td}</b> hạn hôm nay` : "") + ". Làm từ trên xuống." : esc(day) + (d.waiting.length ? "Không còn việc nào cần bạn làm." : "Không còn việc nào đang mở.");
    } else {
      const un = d.rows.filter(r => r.unopened).length, aw = d.rows.filter(r => r.awaiting).length, pr = d.proposals.length;
      const prTxt = pr ? `<b class="pmq-num">${pr}</b> đề xuất hạn chờ bạn trả lời` : "";
      SUB.innerHTML = n ? `<b class="pmq-num">${n}</b> việc bạn đã giao còn mở` + (late ? `, <b class="pmq-num pmq-late">${late}</b> quá hạn` : "") +
        (un ? `, <b class="pmq-num">${un}</b> việc người nhận chưa mở` : "") + (aw ? `, <b class="pmq-num">${aw}</b> chờ nhận` : "") + (pr ? ", " + prTxt : "") + ". Nhắc người nhận ngay trên dòng."
        : (pr ? prTxt + "." : "Không có việc bạn giao nào đang mở.");
    }
  }
  function paintAsk() {
    const box = $("[data-ask]"), d = S.data.me, asks = S.tab === "me" && d ? d.asks : [];
    if (S.tab === "give") { S.askForm = null; box.innerHTML = propsHtml(); return; }
    if (!asks.length) { box.innerHTML = ""; S.askForm = null; return; }
    if (S.askForm && !asks.some(a => a.request === S.askForm.req)) S.askForm = null;
    const fold = asks.length > ASK_FOLD + 1 && !S.askAll, shown = fold ? asks.slice(0, ASK_FOLD) : asks;
    box.innerHTML = `<section class="pmq-ask" aria-labelledby="${idp}askh"><h2 class="pmq-ask-h" id="${idp}askh">${ic("hand")}<span><b class="pmq-num">${asks.length}</b> việc chờ bạn nhận</span><small>Cần đồng ý</small></h2><ul class="pmq-ask-list" id="${idp}askl">` +
      shown.map(a => {
        const rq = esc(a.request), busy = S.askBusy[a.request] ? " disabled" : "", f = S.askForm && S.askForm.req === a.request ? S.askForm : null;
        const meta = [esc(a.from_name || a.from_user || "Người giao") + " giao", a.proposed_end && isYmd(String(a.proposed_end).slice(0, 10)) ? "hạn đề xuất " + esc(dm(String(a.proposed_end).slice(0, 10))) : "chưa có hạn", a.project_name ? esc(a.project_name) : ""].filter(Boolean).join(" · ");
        const Bk = (act, label, cls) => `<button type="button" class="pmq-btn pmq-btn--sm ${cls}" data-act="${act}" data-req="${rq}" data-k="ask:${act}:${rq}"${busy}${f && f.kind === act.slice(4) ? ' aria-expanded="true"' : ""}>${label}</button>`;
        const subj = String(a.subject || a.task || "");
        return `<li class="pmq-ask-row" data-req="${rq}"><div class="pmq-ask-main"><b${subj.length > TITLE_TIP ? ` title="${esc(subj)}"` : ""}>${esc(subj)}</b><small>${meta}</small>${a.message ? `<q class="pmq-quote">${esc(a.message)}</q>` : ""}</div>` +
          `<div class="pmq-ask-acts">${Bk("ask-accept", "Nhận việc", "pmq-btn--pri")}${Bk("ask-propose", "Đề xuất hạn khác", "")}${Bk("ask-reject", "Từ chối", "pmq-btn--q")}</div>` +
          (f ? askFormHtml(a, f) : "") + "</li>";
      }).join("") + "</ul>" +
      (asks.length > ASK_FOLD + 1 ? `<div class="pmq-ask-more"><button type="button" class="pmq-link" data-act="ask-more" data-k="ask:more" aria-expanded="${!fold}" aria-controls="${idp}askl">${fold ? "Xem thêm " + (asks.length - ASK_FOLD) + " việc chờ nhận" : "Thu gọn"}</button></div>` : "") +
      "</section>";
  }
  function askFormHtml(a, f) {
    const rej = f.kind === "reject", rq = esc(a.request), busy = S.askBusy[a.request] ? " disabled" : "";
    return `<div class="pmq-ask-form" role="group" aria-label="${rej ? "Từ chối việc" : "Đề xuất hạn khác"}">` +
      (rej ? "" : `<div class="pmq-af-row"><label for="${idp}afd">Hạn đề xuất</label><input id="${idp}afd" class="pmq-in" type="date" data-af="date" value="${esc(f.date)}" min="${esc(today())}">` +
        `<label class="pmq-vh" for="${idp}aft">Giờ</label><input id="${idp}aft" class="pmq-in" type="time" data-af="time" value="${esc(f.time)}"></div>`) +
      `<label class="pmq-af-l" for="${idp}afr">${rej ? "Lý do từ chối" : "Lý do cần hạn khác"} <span class="pmq-muted">(bắt buộc, người giao sẽ thấy)</span></label>` +
      `<textarea id="${idp}afr" class="pmq-in pmq-ta" data-af="reason" rows="2" maxlength="500"${f.err ? ` aria-invalid="true" aria-describedby="${idp}afe"` : ""}>${esc(f.reason)}</textarea>` +
      (f.err ? `<p class="pmq-ferr" id="${idp}afe" role="alert">${esc(f.err)}</p>` : "") +
      `<div class="pmq-af-acts"><button type="button" class="pmq-btn pmq-btn--sm pmq-btn--q" data-act="ask-cancel" data-req="${rq}">Huỷ</button>` +
      `<button type="button" class="pmq-btn pmq-btn--sm pmq-btn--pri" data-act="ask-send" data-req="${rq}" data-k="ask:send:${rq}"${busy}>${rej ? "Gửi từ chối" : "Gửi đề xuất"}</button></div></div>`;
  }
  /* tab giao: người nhận "Đề xuất hạn khác" (kind counter) hoặc "Xin dời hạn" (kind deadline) -> chờ chính mình quyết
     (trên đầu tab, ngoài danh sách / số đếm) */
  const isDl = c => c && c.kind === "deadline";
  const whenTxt = (d, t) => dm(d) + (t ? " · " + t : "");
  function propsHtml() {
    const d = S.data.give, ps = d ? d.proposals : [];
    if (!ps.length) return "";
    return `<section class="pmq-ask pmq-prop" aria-labelledby="${idp}proph"><h2 class="pmq-ask-h" id="${idp}proph">${ic("clock")}<span><b class="pmq-num">${ps.length}</b> đề xuất hạn chờ bạn</span><small>Người nhận muốn hạn khác</small></h2><ul class="pmq-ask-list">` +
      ps.map(p => {
        const c = p.counter, rq = esc(c.request), busy = S.askBusy[c.request] ? " disabled" : "", subj = String(p.subject || p.name || "");
        const who = esc(c.recipient_name || c.recipient || "Người nhận");
        const dl = isDl(c);
        const prop = isYmd(c.due) ? (dl ? "Xin dời sang: " : "Đề xuất hạn: ") + whenTxt(c.due, c.time) : (isYmd(c.start) ? "Đề xuất bắt đầu: " + dm(c.start) : "Đề xuất lịch khác");
        const old = isYmd(c.old_due) ? "hạn cũ " + whenTxt(c.old_due, c.old_time) : "trước đó chưa có hạn";
        const Bp = (act, label, cls, title) => `<button type="button" class="pmq-btn pmq-btn--sm ${cls}" data-act="${act}" data-req="${rq}" data-k="prop:${act}:${rq}" title="${esc(title)}"${busy}${busy ? ' aria-busy="true"' : ""}>${label}</button>`;
        return `<li class="pmq-ask-row" data-req="${rq}"><div class="pmq-ask-main"><button type="button" class="pmq-link pmq-prop-t" data-act="full" data-name="${esc(p.name)}" data-k="prop:open:${rq}"${subj.length > TITLE_TIP ? ` title="${esc(subj)}"` : ""}>${esc(subj)}</button>` +
          `<small>${who} · <b class="pmq-prop-due">${esc(prop)}</b> · ${esc(old)}</small>${c.reason ? `<q class="pmq-quote">${esc(c.reason)}</q>` : ""}</div>` +
          (dl ? `<div class="pmq-ask-acts">${Bp("prop-accept", "Đồng ý hạn mới", "pmq-btn--pri", "Đổi hạn việc sang ngày người nhận xin, báo cho họ")}` +
            `${Bp("prop-keep", "Giữ hạn cũ", "", "Giữ nguyên hạn, báo cho người nhận")}</div></li>`
          : `<div class="pmq-ask-acts">${Bp("prop-accept", "Đồng ý hạn mới", "pmq-btn--pri", "Nhận lịch người nhận đề xuất: việc giao cho họ với hạn mới")}` +
            `${Bp("prop-resend", "Giữ hạn cũ, gửi lại", "", "Giữ hạn cũ, gửi lại yêu cầu để người nhận trả lời lần nữa")}</div></li>`);
      }).join("") + "</ul></section>";
  }
  function paintBar() {
    const box = $("[data-dist]"), d = cur();
    if (!d) return;
    const total = d.rows.length;
    box.innerHTML = `<button type="button" data-f="all" data-k="f:all" aria-pressed="${S.filter === "all"}">Tất cả <b class="pmq-num">${total}</b></button>` +
      d.buckets.filter(b => (d.counts[b.key] || 0) > 0).map(b =>
        `<button type="button" data-f="${esc(b.key)}" data-k="f:${esc(b.key)}" class="${b.key === "late" ? "pmq-f--late" : ""}" aria-pressed="${S.filter === b.key}">${esc(b.label)} <b class="pmq-num">${d.counts[b.key]}</b></button>`).join("") +
      (S.tab === "give" && filterCount("unopened") ? `<button type="button" data-f="unopened" data-k="f:unopened" class="pmq-f--warn" aria-pressed="${S.filter === "unopened"}" title="Việc người nhận chưa mở: bấm Nhắc trên từng dòng">Chưa mở việc <b class="pmq-num">${filterCount("unopened")}</b></button>` : "");
  }
  function paintNote() {
    const box = $("[data-note]"), d = cur();
    const n = d ? d.personal_hidden : 0, tr = !!(d && d.truncated);
    if (!d || (!S.personal && !n && !tr)) { box.hidden = true; box.innerHTML = ""; return; }
    box.hidden = false;
    box.innerHTML = (tr ? `<span class="pmq-note-l">${ic("alert")}<span>Đang hiện <b class="pmq-num">${d.limit || d.rows.length}</b> việc có hạn gần nhất. Việc hạn xa hơn xem ở danh sách Công việc.</span></span>` : "") +
      (S.personal || n ? `<span class="pmq-note-l">${ic("eye")}` + (S.personal ? "<span>Đang hiện việc nhật ký cá nhân.</span>" : `<span>Đang ẩn <b class="pmq-num">${n}</b> việc nhật ký cá nhân.</span>`) +
      `<button type="button" class="pmq-link" data-act="personal">${S.personal ? "Ẩn nhật ký cá nhân" : "Hiện nhật ký cá nhân (" + n + ")"}</button></span>` : "");
  }
  function groupRange(key) {
    const td = today();
    if (key === "today") return dm(td);
    if (key === "tomorrow") return dm(ymdAdd(td, 1));
    if (key === "week") { const end = ymdAdd(td, (7 - dow(td)) % 7), st = ymdAdd(td, 2); return st <= end ? (st === end ? dm(st) : dm(st) + " – " + dm(end)) : ""; }
    return "";
  }
  function paintList() {
    const box = $("[data-list]"), d = cur();
    if (!d) {
      if (S.err) {
        box.removeAttribute("aria-busy");
        const na = noAccess(S.err);   /* user chưa được cấp quyền PM: nói rõ, không để câu tiếng Anh của server */
        box.innerHTML = `<div class="pmq-state pmq-state--err" role="alert">${ic("alert", "pmq-state-i")}<b>${na ? "Bạn chưa có quyền dùng Công việc" : "Không tải được danh sách việc"}</b><span>${na ? "Nhờ quản trị hệ thống cấp quyền Công việc (PM) cho tài khoản của bạn." : esc(msgOf(S.err))}</span>` +
          `<button type="button" class="pmq-btn pmq-btn--sm" data-act="retry" data-k="retry">${ic("retry")}<span>Thử lại</span></button></div>`;
      } else { box.setAttribute("aria-busy", "true"); if (!box.querySelector(".pmq-skel")) box.innerHTML = skelHtml(); }
      return;
    }
    box.removeAttribute("aria-busy");
    const rows = visible(), wait = S.filter === "all" ? waitHtml() : "";
    if (!rows.length) {
      const all = S.filter === "all", me = S.tab === "me";
      if (all && me && wait) {   /* chỉ còn việc chờ người khác duyệt: không mời "ghi việc mới" như thể trống trơn */
        box.innerHTML = `<div class="pmq-state">${ic("inbox", "pmq-state-i")}<b>Không còn việc nào cần bạn làm</b><span>Các việc bạn đã gửi kiểm tra đang chờ người giao duyệt.</span></div>` + wait;
        return;
      }
      const props = !me && d.proposals.length;   /* chỉ còn đề xuất hạn (khối trên): không nói "chưa giao việc nào" */
      box.innerHTML = `<div class="pmq-state">${ic(me ? "inbox" : "send", "pmq-state-i")}<b>${all ? (me ? "Không còn việc nào đang mở" : (props ? "Không còn việc đã giao nào khác đang mở" : "Bạn chưa giao việc nào đang mở")) : (S.filter === "unopened" ? "Người nhận đã mở hết việc" : "Không có việc trong nhóm này")}</b>` +
        `<span>${all ? (me ? "Ghi việc mới vào ô phía trên: gõ tên việc, hạn rồi Enter." : "Giao việc bằng ô phía trên, thêm @tên người nhận.") : "Bấm Tất cả để xem lại toàn bộ hàng đợi."}</span>` +
        (all ? `<button type="button" class="pmq-btn pmq-btn--sm" data-act="focus-qa">${ic("plus")}<span>${me ? "Ghi việc" : "Giao việc"}</span></button>` : `<button type="button" class="pmq-btn pmq-btn--sm" data-act="all" data-k="all">Xem tất cả</button>`) + "</div>";
      return;
    }
    const groups = [];
    d.buckets.forEach(b => { const g = rows.filter(r => r.bucket === b.key); if (g.length) groups.push({ b, g }); });
    const known = d.buckets.map(b => b.key), rest = rows.filter(r => known.indexOf(r.bucket) < 0);
    if (rest.length) groups.push({ b: { key: "other", label: "Khác" }, g: rest });
    box.innerHTML = `<div class="pmq-cols" aria-hidden="true"><span></span><span class="pmq-r">#</span><span>Việc</span><span class="pmq-hp">Ưu tiên</span><span>Hạn</span><span class="pmq-hw">${S.tab === "me" ? "Người giao" : "Người nhận"}</span><span class="pmq-r pmq-ha">Thao tác</span></div>` +
      groups.map(x => {
        const hid = idp + "g-" + esc(x.b.key), rg = groupRange(x.b.key);
        return `<section class="pmq-g pmq-g--${esc(x.b.key)}" aria-labelledby="${hid}"><h3 class="pmq-grp" id="${hid}">${esc(x.b.label)}${rg ? ` <small class="pmq-num">${esc(rg)}</small>` : ""}<small class="pmq-num">· ${x.g.length} việc</small></h3>` +
          `<ul class="pmq-rows" role="list">${x.g.map(rowHtml).join("")}</ul></section>`;
      }).join("") + wait;
  }
  /* "Đang chờ duyệt (n)": việc mình đã gửi kiểm tra, người giao chưa duyệt. Thu gọn mặc định (nhớ trong phiên), cuối danh sách. */
  function waitHtml() {
    const w = waitRows();
    if (!w.length) return "";
    const hid = idp + "wait", open = !!S.waitOpen;
    return `<section class="pmq-g pmq-g--wait" aria-labelledby="${hid}h"><h3 class="pmq-grp" id="${hid}h"><button type="button" class="pmq-wait-t" data-act="wait" data-k="wait" aria-expanded="${open}" aria-controls="${hid}">` +
      `<span class="pmq-caret" aria-hidden="true"></span>Đang chờ duyệt <span class="pmq-num">(${w.length})</span></button><small>Bạn đã gửi kiểm tra, chờ người giao duyệt</small></h3>` +
      `<ul class="pmq-rows" role="list" id="${hid}"${open ? "" : " hidden"}>${open ? w.map(rowHtml).join("") : ""}</ul></section>`;
  }
  function rowHtml(r) {
    const n = esc(r.name), sel = S.sel === r.name, st = stateOf(r);
    const cls = "pmq-row" + (sel ? " pmq-row--sel" : "") + (st === "Done" ? " pmq-row--done" : "") + (S.busy[r.name] ? " pmq-row--busy" : "") + (r.bucket === "late" ? " pmq-row--late" : "");
    return `<li class="${cls}" data-name="${n}"${sel ? ' aria-current="true"' : ""}>${chkHtml(r, "r")}${r.waiting ? '<span class="pmq-rk" aria-hidden="true"></span>' : `<span class="pmq-rk pmq-num" title="Thứ tự làm">${esc(r.rank)}</span>`}` +
      `<div class="pmq-tt"><button type="button" class="pmq-open" data-act="open" data-name="${n}" data-k="r:open:${n}" aria-expanded="${S.open === r.name}" aria-controls="${idp}dr"${String(r.subject || "").length > TITLE_TIP ? ` title="${esc(r.subject)}"` : ""}>${esc(r.subject || r.name)}</button>` +
      `<small>${tagsHtml(r) || "&nbsp;"}</small></div><span class="pmq-hp">${priHtml(r.priority)}</span>${dueHtml(r)}<span class="pmq-hw">${personHtml(r)}</span>` +
      `<span class="pmq-ac">${actsHtml(r, "r", false)}</span></li>`;
  }
  function paintDrawer() {
    const dr = $("[data-drawer]"), wrap = $("[data-wrap]"), r = S.open ? rowOf(S.open) : null;
    wrap.classList.toggle("pmq-wrap--open", !!r);
    if (!r) { dr.hidden = true; dr.innerHTML = ""; return; }
    dr.hidden = false;
    const det = S.detail[r.name] || {}, st = stateOf(r);
    const giver = r.self ? "Tôi (tự ghi)" : (r.giver_name || r.giver || "—");
    const asg = S.tab === "me" ? "Tôi" : ((r.assignees || []).map(a => (a.name || a.user) + (truthy(a.pending) ? " (chờ nhận)" : (truthy(a.done) ? " (xong)" : (a.opened ? "" : " (chưa mở)"))) + (truthy(a.left) ? " (đã nghỉ)" : "")).join(", ") || "—");
    let desc;
    if (det.loading) desc = '<div class="pmq-dr-skel" aria-hidden="true"><i></i><i></i><i></i></div><span class="pmq-vh">Đang tải mô tả…</span>';
    else if (det.err) desc = `<p class="pmq-ferr">Không tải được mô tả. <button type="button" class="pmq-link" data-act="desc-retry" data-name="${esc(r.name)}">Thử lại</button></p>`;
    else desc = det.desc ? `<div class="pmq-dr-text">${esc(det.desc)}</div>` : '<p class="pmq-muted">Chưa có mô tả.</p>';
    dr.innerHTML = `<div class="pmq-dr-h">${chkHtml(r, "d")}<h2 class="pmq-dr-t" tabindex="-1" data-k="d:title">${esc(r.subject || r.name)}</h2>` +
      `<button type="button" class="pmq-x" data-act="close" data-k="d:close" aria-label="Đóng chi tiết" title="Đóng (Esc)">${ic("x")}</button></div>` +
      `<dl class="pmq-dr-meta"><dt>Hạn</dt><dd>${dueHtml(r)}${askedDue(r) ? `<small class="pmq-muted">Đã xin dời sang ${esc(dm(askedDue(r)))}, chờ ${esc(r.giver_name || "người giao")} trả lời</small>` : ""}</dd><dt>Ưu tiên</dt><dd>${priHtml(r.priority)}</dd>` +
      `<dt>Trạng thái</dt><dd><span class="pmq-st pmq-st--${st === "In Progress" ? "doing" : (st === "Review" ? "review" : (st === "Done" ? "done" : "todo"))}">${esc(STATE[st] || st)}</span>${r.review ? ' <span class="pmq-tag">Cần người giao kiểm tra</span>' : ""}</dd>` +
      `<dt>Người giao</dt><dd>${esc(giver)}${truthy(r.giver_left) ? ' <span class="pmq-muted">(đã nghỉ)</span>' : ""}</dd><dt>Người nhận</dt><dd>${esc(asg)}</dd><dt>Dự án</dt><dd>${r.project_name ? esc(r.project_name) : '<span class="pmq-muted">—</span>'}</dd>` +
      `<dt>Mã việc</dt><dd class="pmq-num pmq-muted">${esc(r.name)}</dd></dl>` +
      `<div class="pmq-dr-desc" aria-live="polite">${desc}</div>` +
      `<div class="pmq-dr-acts">${actsHtml(r, "d", true)}<button type="button" class="pmq-btn pmq-btn--sm" data-act="full" data-name="${esc(r.name)}" data-k="d:full">${ic("ext")}<span>Mở đầy đủ</span></button></div>`;
  }

  /* ---------------- chọn dòng / ngăn chi tiết */
  function rowEl(name) { return $$(".pmq-row").find(x => x.getAttribute("data-name") === name) || null; }
  function focusRow(name) {
    const r = rowEl(name), b = r && r.querySelector(".pmq-open");
    if (!b) return;
    try { b.focus({ preventScroll: true }); } catch (_) { b.focus(); }
    if (r.scrollIntoView) { try { r.scrollIntoView({ block: "nearest" }); } catch (_) { /* jsdom */ } }
  }
  function select(name, o) {
    o = o || {};
    S.sel = name;
    if (S.open && name && S.open !== name) openDrawer(name, { quiet: true });
    $$(".pmq-row").forEach(x => { const on = x.getAttribute("data-name") === name; x.classList.toggle("pmq-row--sel", on); if (on) x.setAttribute("aria-current", "true"); else x.removeAttribute("aria-current"); });
    if (o.focus !== false && name) focusRow(name);
  }
  function openDrawer(name, o) {
    o = o || {};
    if (!rowOf(name)) return;
    if (mobile() && !o.quiet) { S.sel = name; openFull(name); return; }
    S.open = name; S.sel = name;
    if (!S.detail[name] || S.detail[name].err) loadDetail(name);
    paintDrawer();
    $$(".pmq-row").forEach(x => {
      const on = x.getAttribute("data-name") === name, b = x.querySelector(".pmq-open");
      x.classList.toggle("pmq-row--sel", on); if (on) x.setAttribute("aria-current", "true"); else x.removeAttribute("aria-current");
      if (b) b.setAttribute("aria-expanded", String(on));
    });
    if (o.focus) { const t = $(".pmq-dr-t"); if (t) t.focus(); }
  }
  function closeDrawer(silent) {
    const was = S.open;
    S.open = null;
    if (silent) return;
    paintDrawer();
    $$(".pmq-open").forEach(b => b.setAttribute("aria-expanded", "false"));
    if (was) focusRow(was);
  }
  function loadDetail(name) {
    S.detail[name] = { loading: true };
    call("tasks.get", { name }).then(res => {
      const t = (res && res.task) || {};
      S.detail[name] = { desc: htmlText(t.description), task: t };
      if (alive() && S.open === name) paintDrawer();
    }, e => {
      S.detail[name] = { err: e };
      if (alive() && S.open === name) paintDrawer();
    });
  }

  /* ---------------- thao tác trên dòng */
  function setBusy(name, on) { if (on) S.busy[name] = 1; else delete S.busy[name]; }
  function doDone(name, o) {
    o = o || {};
    const r = rowOf(name);
    if (r && !S.busy[name] && canApprove(r)) return doApprove(name, o);
    if (!r || S.busy[name] || !canDone(r)) return;
    const prev = r.workflow_state || "To Do", subj = r.subject || name;
    setBusy(name, 1); S.just[name] = "Done"; paint();
    call("tasks.mark_done", { name }).then(res => {
      res = res || {};
      setBusy(name, 0);
      if (res.blocked_reason) {
        delete S.just[name]; paint();
        toast(res.blocked_message || BLOCKED[res.blocked_reason] || ("Chưa xong được: " + res.blocked_reason), { bad: true });
        openFull(name);
        return;
      }
      const st = res.state || "Done";
      if (st === "Done") S.just[name] = "Done"; else { delete S.just[name]; r.workflow_state = st; }
      paint();
      /* phím X: chọn ngay việc kế tiếp (dòng vừa xong còn gạch ~1,6 giây) -> X, X, X đi hết hàng đợi */
      if (o.advance && S.sel === name) {
        const all = visible().map(x => x.name), nx = nextSel(all, name, all.filter(x => x !== name && S.just[x] !== "Done"));
        if (nx) select(nx);
      }
      const giver = !r.self && r.giver_name ? r.giver_name : "";
      const msg = (st === "Review" ? "Đã gửi kiểm tra" : "Đã xong") + ": " + qt(subj) + (st === "Review" && giver ? ". " + giver + " sẽ kiểm tra" : "") + (res.withdrew_request ? " · đã rút yêu cầu xin dời hạn" : "");
      toast(msg, { actions: prev !== st ? [{ label: "Hoàn tác", run: () => undo(name, prev, subj) }] : [] });
      changed({ task: name, state: st });
      later(JUST_MS, () => { delete S.just[name]; refresh({ force: true }); });
    }, e => {
      setBusy(name, 0); delete S.just[name]; paint();
      toast(msgOf(e, "Chưa đánh dấu xong được."), { bad: true });
      refresh({ force: true });   /* việc có thể đã đổi / bị huỷ ở chỗ khác: vẽ lại theo server */
    });
  }
  /* người giao duyệt việc Chờ duyệt: pm_inbox.close_parent (đường "đóng việc" của người giao; việc cha chia nhiều người cũng vậy) */
  function doApprove(name, o) {
    o = o || {};
    const r = rowOf(name);
    if (!r || S.busy[name] || !canApprove(r)) return;
    const subj = r.subject || name;
    setBusy(name, 1); S.just[name] = "Done"; paint();
    call("pm_inbox.close_parent", { task: name }).then(res => {
      res = res || {};
      setBusy(name, 0);
      const st = res.state || "Done";
      if (st !== "Done") { delete S.just[name]; r.workflow_state = st; }
      paint();
      if (o.advance && S.sel === name) {
        const all = visible().map(x => x.name), nx = nextSel(all, name, all.filter(x => x !== name && S.just[x] !== "Done"));
        if (nx) select(nx);
      }
      toast("Đã duyệt xong: " + qt(subj), { actions: [{ label: "Hoàn tác", run: () => undo(name, "Review", subj) }] });
      changed({ task: name, state: st });
      later(JUST_MS, () => { delete S.just[name]; refresh({ force: true }); });
    }, e => {
      setBusy(name, 0); delete S.just[name]; paint();
      toast(msgOf(e, "Chưa duyệt được."), { bad: true });
      refresh({ force: true });
    });
  }
  function undo(name, prev, subj) {
    if (S.busy[name]) return;
    setBusy(name, 1); paint();
    call("tasks.set_status", { name, action: prev }).then(() => {
      setBusy(name, 0); delete S.just[name];
      toast("Đã hoàn tác: " + qt(subj));
      changed({ task: name, state: prev });
      refresh({ force: true });
    }, e => { setBusy(name, 0); paint(); toast(msgOf(e, "Chưa hoàn tác được."), { bad: true }); refresh({ force: true }); });
  }
  function doStart(name) {
    const r = rowOf(name);
    if (!r || S.busy[name] || S.tab !== "me" || r.group) return;
    const prev = r.workflow_state || "To Do", subj = r.subject || name, st = stateOf(r);
    if (st === "In Progress" || st === "Review" || st === "Done") return;   /* Done: vừa bấm Xong (dòng còn gạch) -> S không mở lại */
    setBusy(name, 1); r.workflow_state = "In Progress"; paint();
    call("tasks.set_status", { name, action: "In Progress" }).then(() => {
      setBusy(name, 0); paint();
      toast("Đã bắt đầu: " + qt(subj), { actions: [{ label: "Hoàn tác", run: () => undo(name, prev, subj) }] });
      changed({ task: name, state: "In Progress" });
    }, e => { setBusy(name, 0); r.workflow_state = prev; paint(); toast(msgOf(e, "Chưa bắt đầu được."), { bad: true }); refresh({ force: true }); });
  }
  function doNudge(name) {
    const r = rowOf(name);
    if (!r || S.busy[name] || S.tab !== "give") return;
    setBusy(name, 1); paint();
    call("pm_inbox.nudge", { task: name }).then(res => {
      setBusy(name, 0); paint();
      res = res || {};
      const nm = u => { const a = (r.assignees || []).find(x => x.user === u); return a ? (a.name || u) : u; };
      const sent = (res.sent || []).map(nm), skip = (res.skipped || []).map(nm);
      if (sent.length) { S.nudged[name] = localHm(); keep(paintList); }
      if (sent.length) toast("Đã nhắc " + sent.join(", ") + (skip.length ? ". " + skip.join(", ") + " vừa được nhắc trong 1 giờ qua" : ""));
      else if (skip.length) toast(skip.join(", ") + " vừa được nhắc trong 1 giờ qua, chưa nhắc lại được.");
      else toast("Đã gửi nhắc việc.");
      changed({ task: name, nudged: true });
    }, e => { setBusy(name, 0); paint(); toast(msgOf(e, "Chưa nhắc được."), { bad: true }); refresh({ force: true }); });
  }

  /* người giao trả lại việc Chờ duyệt (chưa đạt) -> Đang làm, như "Trả lại" ở Tôi đã giao; Hoàn tác = về lại Chờ duyệt */
  function doReturn(name) {
    const r = rowOf(name);
    if (!r || S.busy[name] || S.tab !== "give" || r.group || stateOf(r) !== "Review") return;
    const subj = r.subject || name, a = (r.assignees || [])[0], who = a ? (a.name || a.user) : "người nhận";
    setBusy(name, 1); paint();
    call("tasks.set_status", { name, action: "In Progress" }).then(() => {
      setBusy(name, 0); r.workflow_state = "In Progress"; paint();
      toast("Đã trả lại " + qt(subj) + " cho " + who + ". Mở việc, ghi ở Bình luận cần sửa gì.",
        { actions: [{ label: "Mở", run: () => openFull(name) }, { label: "Hoàn tác", run: () => undo(name, "Review", subj) }] });
      changed({ task: name, state: "In Progress" });
      refresh({ force: true });
    }, e => { setBusy(name, 0); paint(); toast(msgOf(e, "Chưa trả lại được."), { bad: true }); refresh({ force: true }); });
  }

  /* ---------------- Cần đồng ý */
  const askOf = req => ((S.data.me || {}).asks || []).find(a => a.request === req) || null;
  function askAccept(req) {
    const a = askOf(req);
    if (!a || S.askBusy[req]) return;
    S.askBusy[req] = 1; keep(paintAsk);
    call("assignment.respond", { name: req, decision: "accept" }).then(r => {
      delete S.askBusy[req];
      if (r && truthy(r.auto_closed)) toast(r.message || "Việc này đã xong hoặc đã huỷ, không cần trả lời nữa.");
      else toast("Đã nhận việc: " + qt(a.subject || a.task) + ". " + (a.from_name || "Người giao") + " được báo.", { actions: a.task ? [{ label: "Mở", run: () => openFull(a.task) }] : [] });
      S.askForm = null;
      changed({ task: a.task, accepted: true });
      refresh({ force: true });
    }, e => { delete S.askBusy[req]; keep(paintAsk); toast(msgOf(e, "Chưa nhận được việc."), { bad: true }); refresh({ force: true }); });
  }
  function askOpenForm(req, kind) {
    const a = askOf(req);
    if (!a) return;
    if (S.askForm && S.askForm.req === req && S.askForm.kind === kind) { S.askForm = null; paintAsk(); focusK("ask:ask-" + kind + ":" + req); return; }
    const base = isYmd(String(a.proposed_end || "").slice(0, 10)) && String(a.proposed_end).slice(0, 10) >= today() ? String(a.proposed_end).slice(0, 10) : today();
    S.askForm = { req, kind, reason: "", date: ymdAdd(base, 2), time: "18:00", err: "" };
    paintAsk();
    const f = $(kind === "reject" ? '[data-af="reason"]' : '[data-af="date"]');
    if (f) f.focus();
  }
  function askSend(req) {
    const a = askOf(req), f = S.askForm;
    if (!a || !f || f.req !== req || S.askBusy[req]) return;
    const reason = String(f.reason || "").trim(), args = { name: req, decision: f.kind === "reject" ? "reject" : "reschedule", reason };
    if (!reason) { f.err = "Ghi lý do để người giao hiểu."; paintAsk(); const t = $('[data-af="reason"]'); if (t) t.focus(); return; }
    if (args.decision === "reschedule") {
      if (!isYmd(f.date)) { f.err = "Chọn hạn đề xuất."; paintAsk(); const t = $('[data-af="date"]'); if (t) t.focus(); return; }
      args.counter_end = f.date + " " + (f.time || "18:00") + ":00";
    }
    f.err = ""; S.askBusy[req] = 1; keep(paintAsk);
    call("assignment.respond", args).then(r => {
      delete S.askBusy[req]; S.askForm = null;
      if (r && truthy(r.auto_closed)) toast(r.message || "Việc này đã xong hoặc đã huỷ, không cần trả lời nữa.");
      else toast(args.decision === "reject" ? "Đã từ chối và gửi lý do cho " + (a.from_name || "người giao") + "." : "Đã gửi đề xuất hạn " + dm(f.date) + (f.time ? " · " + f.time : "") + ".");
      changed({ task: a.task });
      refresh({ force: true });
    }, e => { delete S.askBusy[req]; keep(paintAsk); toast(msgOf(e, "Chưa gửi được."), { bad: true }); refresh({ force: true }); });
  }
  const propOf = req => ((S.data.give || {}).proposals || []).find(p => p.counter.request === req) || null;
  function propAct(req, action) {
    const p = propOf(req);
    if (!p || S.askBusy[req]) return;
    const c = p.counter, who = c.recipient_name || c.recipient || "người nhận", subj = p.subject || p.name, dl = isDl(c);
    /* Xin dời hạn: "Đồng ý hạn mới" / "Giữ hạn cũ" = pm_inbox.answer_deadline; Đề xuất hạn khác: assignment.requester_action */
    const accept = action === "accept_counter";
    S.askBusy[req] = 1; keep(paintAsk);
    const go = dl ? call("pm_inbox.answer_deadline", { request: req, accept: accept ? 1 : 0 }) : call("assignment.requester_action", { name: req, action });
    go.then(() => {
      delete S.askBusy[req];
      const nd = isYmd(c.due) ? " " + whenTxt(c.due, c.time) : "";
      if (dl) toast(accept ? "Đã đồng ý dời hạn " + qt(subj) + " sang" + nd + ". " + who + " được báo." : "Đã giữ hạn cũ cho " + qt(subj) + ". " + who + " được báo.",
        { actions: [{ label: "Mở", run: () => openFull(p.name) }] });
      else if (accept) toast("Đã đồng ý hạn mới" + nd + ": " + qt(subj) + " đã giao cho " + who + ".", { actions: [{ label: "Mở", run: () => openFull(p.name) }] });
      else toast("Đã giữ hạn cũ và gửi lại cho " + who + ": " + qt(subj) + ". Chờ " + who + " nhận.");
      changed({ task: p.name, request: req });
      refresh({ force: true });
    }, e => { delete S.askBusy[req]; keep(paintAsk); toast(msgOf(e, accept ? "Chưa đồng ý được hạn mới." : (dl ? "Chưa gửi được câu trả lời." : "Chưa gửi lại được.")), { bad: true }); refresh({ force: true }); });
  }
  function focusK(k) { const n = $('[data-k="' + k.replace(/"/g, '\\"') + '"]'); if (n) n.focus(); }

  /* ---------------- giao việc 1 dòng (nhiều @ = nhiều người nhận; mỗi @ tự giải riêng: trùng tên -> chọn, không có -> báo) */
  function freshQa() { const t = today(); return { text: "", p: null, w: null, due: ymdAdd(t, 1), dueDefault: true, time: "", pri: "Medium", ask: LAST_ASK, split: LAST_SPLIT, edited: {}, picks: {}, busy: false, err: "" }; }
  S.qa = freshQa();
  /* -> {list: [{tok, r, dup}], bad (mục đầu chưa giải được), rcpt (email người nhận, bỏ trùng, bỏ chính mình), names, self} */
  function qaWho(q) {
    const toks = (q.p && q.p.tokens) || [], mine = me(), seen = {}, rcpt = [], names = {};
    let bad = null, hasMe = false;
    const list = toks.map(tok => {
      const r = resolvePerson(tok, S.people, q.picks[fold(tok)]), x = { tok, r, dup: false };
      if (r && r.email) {
        if (seen[r.email]) x.dup = true;
        else { seen[r.email] = 1; names[r.email] = r.name || r.email; if (r.email === mine) hasMe = true; else rcpt.push(r.email); }
      } else if (!bad) bad = x;
      return x;
    });
    return { list, bad, rcpt, names, hasMe, self: !toks.length || (!bad && !rcpt.length) };
  }
  function qaParse() {
    const q = S.qa;
    q.p = parseLine(q.text, { parseDue: parseDueFn(), base: baseDate() });
    if (!q.edited.due) { q.due = q.p.due || ymdAdd(today(), 1); q.dueDefault = !q.p.due; q.time = q.p.time || ""; }
    if (!q.edited.pri) q.pri = q.p.priority || "Medium";
    q.w = qaWho(q);
    if (q.p.tokens.length && !S.people && !S.peopleErr) people().then(() => { if (alive() && S.qa === q) { q.w = qaWho(q); paintParse(); } }, () => { if (alive() && S.qa === q) paintParse(); });
  }
  const qaSelf = () => !S.qa.w || S.qa.w.self;
  /* chế độ khi giao từ 2 người: "split" (mỗi người một việc) | "shared" (làm chung). Cần đồng ý + nhiều người: server chỉ có split. */
  const qaSplit = (q, n) => n > 1 && (q.ask || q.split);
  const rxEsc = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  /* chèn @tên khi chọn người: tên gọi trùng với người KHÁC đã chọn (vd hai "Vũ") -> dùng phần trước @ của email cho khỏi lẫn */
  /* rep = @ đang được thay (chính nó không tính là trùng). Một @ KHÁC trong câu cùng tên gọi mà chưa chọn / là người khác (vd "@vu"
     đang hỏi Chọn): chèn "@Vũ" sẽ bị gộp với @ đó (bỏ trùng theo chữ) -> mất một người nhận, nên cũng dùng phần trước @ của email. */
  function handleFor(p, rep) {
    const h = handleOf(p), k = fold(h), cur = S.qa.picks[k], loc = String(p.email || "").split("@")[0] || h;
    if (cur) return cur.email !== p.email ? loc : h;
    const clash = ((S.qa.w && S.qa.w.list) || []).some(x => fold(x.tok) === k && k !== fold(rep || "") && !(x.r && x.r.email === p.email));
    return clash ? loc : h;
  }
  function chipHtml(x, w) {
    const r = x.r, multi = w.list.length > 1;
    if (r && r.email) {
      const name = r.name || r.email, mine = r.email === me();
      return `<span class="pmq-chip${mine ? " pmq-chip--me" : ""}" title="${esc(mine ? "Bạn là người giao, không tính là người nhận" : r.email)}"><b>${esc(mine ? "Tôi" : name)}</b>${mine ? '<small>không tính</small>' : ""}` +
        `<button type="button" class="pmq-chip-x" data-act="qa-rm" data-email="${esc(r.email)}" aria-label="Bỏ ${esc(mine ? "Tôi" : name)}">${ic("x")}</button></span>`;
    }
    const rm = `<button type="button" class="pmq-chip-x" data-act="qa-rm" data-tok="${esc(x.tok)}" aria-label="Bỏ @${esc(x.tok)}">${ic("x")}</button>`;
    if (r && r.loading) return S.peopleErr ? "" : `<span class="pmq-chip pmq-chip--wait"><span class="pmq-muted">@${esc(x.tok)} · Đang tìm…</span></span>`;
    if (r && r.ambiguous) return `<span class="pmq-chip pmq-chip--bad"><span class="pmq-miss">${multi ? "@" + esc(x.tok) + " · " : ""}Chọn:</span> ` +
      r.ambiguous.map(p => `<button type="button" class="pmq-pick" data-act="qa-pick" data-tok="${esc(x.tok)}" data-email="${esc(p.email)}" title="${esc(p.email)}">${esc(p.full_name || p.email)}</button>`).join("") + rm + "</span>";
    return `<span class="pmq-chip pmq-chip--bad"><span class="pmq-miss">Không tìm thấy “@${esc(x.tok)}”</span>${rm}</span>`;
  }
  function modeHtml(q, n) {
    const lock = q.ask, split = qaSplit(q, n);
    const o = (v, on, title, sub, dis) => `<label class="pmq-mode-o${on ? " pmq-mode-o--on" : ""}${dis ? " pmq-mode-o--off" : ""}" for="${idp}qm-${v}">` +
      `<input id="${idp}qm-${v}" type="radio" name="${idp}qm" value="${v}" data-qa-f="mode"${on ? " checked" : ""}${dis ? ` disabled aria-describedby="${idp}qm-n"` : ""}><span><b>${title}</b><small>${sub}</small></span></label>`;
    return `<div class="pmq-mode" role="radiogroup" aria-labelledby="${idp}qm-l"><span class="pmq-mode-l" id="${idp}qm-l">Giao cho ${n} người:</span>` +
      o("split", split, "Mỗi người một việc", "mỗi người có việc riêng; mọi người xong thì việc về Chờ duyệt để bạn đóng") +
      o("shared", !split, "Làm chung 1 việc", "một người bấm Xong là xong cho cả nhóm", lock) +
      (lock ? `<small class="pmq-mode-note" id="${idp}qm-n">Cần đồng ý với nhiều người: mỗi người nhận và trả lời phần của mình</small>` : "") + "</div>";
  }
  function paintParse() {
    const box = $("[data-parse]"), q = S.qa, go = $("[data-qa-go]");
    const self = qaSelf(), ask = !self && q.ask, n = self || !q.w ? 1 : q.w.rcpt.length;
    /* giao liên tiếp: nút + ô nhập KHÔNG khoá trong lúc lưu (S.qaN việc đang gửi) -> gõ việc kế tiếp không mất chữ */
    if (go) {
      go.textContent = !q.text.trim() ? "Giao việc" : (self ? "Thêm việc" : (n > 1 ? (ask ? "Gửi cho " : "Giao cho ") + n + " người" : (ask ? "Gửi yêu cầu" : "Giao việc")));
      go.disabled = false; if (S.qaN > 0) go.setAttribute("aria-busy", "true"); else go.removeAttribute("aria-busy");
    }
    if (!q.text.trim()) {
      box.innerHTML = `<span class="pmq-hint">Ví dụ: <i>@Lan @Phú gửi báo cáo thứ 6 gấp</i> · không ghi @người nhận là việc của bạn · <kbd class="pmq-kbd">Enter</kbd> để giao · <b>Thêm chi tiết</b> để ghi mô tả, các bước, lặp lại</span>` +
        (q.err ? `<span class="pmq-ferr" role="alert">${esc(q.err)}</span>` : "");
      return;
    }
    const w = q.w;
    let who;
    if (self && !(w && w.hasMe)) who = `<b>Tôi</b>`;
    else if (S.peopleErr && !S.people) who = `<span class="pmq-miss">Chưa tải được danh sách người.</span> <button type="button" class="pmq-link" data-act="people-retry">Thử lại</button>`;
    else who = w.list.filter(x => !x.dup && !(x.r && x.r.email === me() && self)).map(x => chipHtml(x, w)).join("") || `<b>Tôi</b>`;
    box.innerHTML = `<div class="pmq-tok pmq-tok--who">${ic("user")}<span class="pmq-tok-l">Người nhận</span>${who}</div>` +
      `<div class="pmq-tok">${ic("clock")}<label class="pmq-tok-l" for="${idp}qd">Hạn</label><input id="${idp}qd" class="pmq-in pmq-in--sm" type="date" data-qa-f="due" value="${esc(q.due)}">` +
        `<label class="pmq-vh" for="${idp}qt">Giờ</label><input id="${idp}qt" class="pmq-in pmq-in--sm" type="time" data-qa-f="time" value="${esc(q.time)}">` +
        (q.dueDefault && q.due ? '<small class="pmq-def">mặc định ngày mai</small>' : (!q.due ? '<small class="pmq-def">không có hạn</small>' : "")) + "</div>" +
      `<div class="pmq-tok"><label class="pmq-tok-l" for="${idp}qp">Ưu tiên</label><select id="${idp}qp" class="pmq-in pmq-in--sm" data-qa-f="pri">${PRI_KEYS.map(k => `<option value="${k}"${k === q.pri ? " selected" : ""}>${PRI[k][1]}</option>`).join("")}</select></div>` +
      `<div class="pmq-tok pmq-tok--ask${self ? " pmq-tok--off" : ""}"><input id="${idp}qa-ask" type="checkbox" data-qa-f="ask"${ask ? " checked" : ""}${self ? " disabled" : ""}>` +
        `<label for="${idp}qa-ask" title="${self ? "Việc của bạn không cần đồng ý" : "Người nhận bấm Nhận việc / Từ chối / Đề xuất hạn trước khi việc bắt đầu"}">Cần đồng ý</label></div>` +
      (!self && n > 1 ? modeHtml(q, n) : "") +
      (q.err ? `<span class="pmq-ferr" role="alert">${esc(q.err)}</span>` : "");
  }
  function onQaInput() {
    S.qa.text = QIN.value; S.qa.err = "";
    if (!QIN.value.trim()) S.qa = freshQa();
    else qaParse();
    paintParse();
    acUpdate();
  }
  /* lỗi người nhận theo từng @ (mục đầu chưa giải được) */
  function whoErr(x) {
    const r = x.r || {};
    return r.ambiguous ? "Có nhiều người tên “" + x.tok + "”, chọn một người." : (r.loading ? "Đang tải danh sách người, thử lại sau giây lát." : "Không tìm thấy “@" + x.tok + "”. Gõ @ rồi chọn người trong danh sách.");
  }
  function qaSubmit() {
    const q = S.qa;
    if (S.composing) return;   /* IME: Enter đang ghép chữ tiếng Việt, không phải lệnh gửi */
    if (S.ac) { acChoose(S.ac.act); return; }
    if (!q.text.trim()) {
      if (Date.now() - S.qaLast < 1500) return;   /* Enter / bấm thêm ngay sau khi vừa giao: ô đã trống, im lặng */
      q.err = "Nhập tên việc rồi Enter."; paintParse(); QIN.focus(); return;
    }
    qaParse();
    const subj = (q.p.subject || "").trim();
    if (!subj) { q.err = "Thiếu tên việc."; paintParse(); QIN.focus(); return; }
    if (subj.length > SUBJECT_MAX) { q.err = "Tên việc dài quá " + SUBJECT_MAX + " ký tự, rút gọn lại nhé."; paintParse(); QIN.focus(); return; }
    const self = qaSelf(), w = q.w;
    if (!self && w.bad) { q.err = whoErr(w.bad); paintParse(); QIN.focus(); return; }
    /* việc của tôi mà chưa biết tôi là ai (F5 sớm): KHÔNG tạo việc không người nhận (việc mồ côi, không hiện ở đâu) */
    if (self && !me()) { q.err = "Chưa xác định được tài khoản của bạn. Bấm Ctrl+Shift+R để tải lại trang."; paintParse(); QIN.focus(); return; }
    const rc = self ? [me()] : w.rcpt.slice(), n = rc.length, toName = self ? "" : (n > 1 ? n + " người" : w.names[rc[0]]), ask = !self && q.ask, split = qaSplit(q, n);
    const due = isYmd(q.due) ? q.due : null, tm = due && /^\d{2}:\d{2}$/.test(q.time) ? q.time : "";
    let m, args;
    if (ask && n > 1) { m = "assignment.create_with_task"; args = { subject: subj, recipients: JSON.stringify(rc), split_per_assignee: 1, priority: q.pri, proposed_end: due ? due + " " + (tm || "18:00") + ":00" : null, project: "" }; }
    else if (ask) { m = "assignment.create_with_task"; args = { subject: subj, recipient: rc[0], priority: q.pri, proposed_end: due ? due + " " + (tm || "18:00") + ":00" : null, project: "" }; }
    else { m = "tasks.create"; args = { project: "", subject: subj, assignees: JSON.stringify(rc), split_per_assignee: n > 1 ? (split ? 1 : 0) : null, exp_end_date: due, pm_end_time: tm ? tm + ":00" : null, priority: q.pri }; }
    /* Giao liên tiếp bằng bàn phím: xoá ô + cho gõ tiếp NGAY (không readOnly chờ server); lỗi thì trả chữ lại (ô còn trống)
       hoặc báo kèm nút "Ghi lại" (đã gõ việc khác). */
    const text = QIN.value;
    q.busy = true; q.err = "";
    S.qaN++; S.qaLast = Date.now();
    QIN.value = ""; S.qa = freshQa(); paintParse(); acClose(); QIN.focus();
    const restore = () => { if (!alive()) return; q.busy = false; S.qa = q; QIN.value = text; q.text = text; qaParse(); paintParse(); QIN.focus(); };
    call(m, args).then(res => {
      S.qaN = Math.max(0, S.qaN - 1); q.busy = false;
      if (!alive()) return;
      res = res || {};
      const name = res.name || res.task;
      paintParse();
      const dueTxt = due ? " · hạn " + dm(due) + (tm ? " " + tm : "") : "";
      /* giao trực tiếp cho người khác: việc nằm ở "Việc tôi giao". KHÔNG tự chuyển tab (đang giao liền nhiều việc / đang xem danh sách
         của mình) — toast có nút Xem để sang đúng dòng đó. */
      const toGive = !self && !ask && S.tab !== "give";
      const msg = self ? "Đã thêm vào việc của bạn: " + qt(subj) + dueTxt
        : (ask ? (n > 1 ? "Đã gửi cho " + toName + ", chờ từng người nhận: " + qt(subj) + dueTxt : "Đã gửi cho " + toName + ": " + qt(subj) + dueTxt + ". Chờ người nhận bấm Nhận việc.")
          : "Đã giao cho " + toName + (n > 1 ? (split ? " (mỗi người một việc)" : " (làm chung 1 việc)") : "") + ": " + qt(subj) + dueTxt);
      toast(msg, { actions: !name ? [] : (toGive ? [{ label: "Xem", run: () => showGiven(name) }] : [{ label: "Mở", run: () => openFull(name) }]) });
      changed({ task: name, created: true });
      refresh({ force: true });
    }, e => {
      S.qaN = Math.max(0, S.qaN - 1); q.busy = false;
      if (!alive()) return;
      const msg = msgOf(e, "Chưa giao được việc.");
      if (!QIN.value.trim()) { restore(); q.err = msg; paintParse(); toast(msg, { bad: true }); }
      else { paintParse(); toast("Chưa giao được " + qt(subj) + ": " + msg, { bad: true, actions: [{ label: "Ghi lại", run: () => { restore(); q.err = msg; paintParse(); } }] }); }
    });
  }
  /* "Thêm chi tiết" (Shift+Enter): mở form Giao việc đầy đủ (PMR.newTask) điền sẵn những gì đã gõ; ô 1 dòng chỉ xoá khi form tạo xong */
  function qaMore() {
    if (S.composing) return;
    acClose();
    const f = typeof opts.newTask === "function" ? opts.newTask : (root.PMR && typeof root.PMR.newTask === "function" ? root.PMR.newTask : null);
    if (!f) { toast("Chưa mở được form Giao việc. Bấm Ctrl+Shift+R để tải lại trang.", { bad: true }); return; }
    const text = QIN.value, onCreated = () => {
      if (!alive()) return;
      if (text.trim() && QIN.value === text) { QIN.value = ""; S.qa = freshQa(); paintParse(); }
      refresh({ force: true });
    };
    let o = { onCreated };
    if (text.trim()) {
      const q = S.qa;
      q.text = text; q.err = ""; qaParse();
      const w = q.w, self = qaSelf();
      if (!self && w.bad) { q.err = whoErr(w.bad); paintParse(); QIN.focus(); return; }   /* không bỏ rơi @ chưa rõ (form sẽ tự giao cho mình) */
      const rc = self ? [] : w.rcpt.slice();
      o = { onCreated, subject: (q.p.subject || "").trim(), assignees: rc, due: isYmd(q.due) ? q.due : "", time: isYmd(q.due) && /^\d{2}:\d{2}$/.test(q.time) ? q.time : "",
        priority: q.pri, split: qaSplit(q, rc.length), requestMode: !!q.ask };   /* form tự bỏ qua Cần đồng ý khi chỉ có Tôi (effAsk); thêm người trong form thì giữ lựa chọn đang nhớ */
    }
    try { f(o); } catch (e) { toast(msgOf(e), { bad: true }); }
  }
  /* bỏ một người (chip ×): xoá mọi @ trỏ tới người đó (hoặc đúng @ chưa giải được) khỏi ô nhập */
  function qaDrop(email, tok) {
    const q = S.qa, toks = tok ? [tok] : ((q.w && q.w.list) || []).filter(x => x.r && x.r.email === email).map(x => x.tok);
    let v = atNorm(QIN.value);
    toks.forEach(t => { v = v.replace(new RegExp("(^|\\s)@" + rxEsc(t) + "[.\\-]*(?=$|[\\s,;:()])", "g"), "$1"); delete q.picks[fold(t)]; });
    QIN.value = v.replace(/\s{2,}/g, " ").replace(/^\s+/, "");
    try { QIN.setSelectionRange(QIN.value.length, QIN.value.length); } catch (_) { /* jsdom */ }
    onQaInput();
    QIN.focus();
  }
  /* gợi ý @người (combobox) — dùng được cho từng @ trong câu */
  function acUpdate() {
    const v = QIN.value, pos = QIN.selectionStart == null ? v.length : QIN.selectionStart;
    const m = /(^|\s)@([^\s@,;:()]*)$/.exec(v.slice(0, pos));
    if (!m) { acClose(); return; }
    /* con trỏ GIỮA một @ đã có ("@Ph|ú"): thay cả @ (tới hết chữ), và chính @ đó không tính là "đã có" */
    const start = m.index + m[1].length, q = m[2], tail = /^[^\s@,;:()]*(?:@[^\s@,;:()]+\.[^\s@,;:()]+)?/.exec(v.slice(pos))[0];
    const whole = fold((q + tail).replace(/[.\-]+$/, ""));
    if (!S.people) {
      if (!S.peopleErr) people().then(() => { if (alive() && D.activeElement === QIN) acUpdate(); }, () => { if (alive()) { acClose(); paintParse(); } });
      return;
    }
    /* đã có ở @ khác trong câu -> không gợi ý lại */
    const taken = {};
    ((S.qa.w && S.qa.w.list) || []).forEach(x => { if (x.r && x.r.email && fold(x.tok) !== whole) taken[x.r.email] = 1; });
    let items = (q ? matchPeople(q, S.people).map(x => x.p) : S.people.filter(p => p.email !== me())).filter(p => !taken[p.email]);
    /* con trỏ giữa một @ đã ra một người (bấm vào giữa "@Phú" rồi Enter): người đó đứng đầu, Enter giữ nguyên chứ không đổi người.
       Chỉ khi con trỏ GIỮA chữ: gõ "@vu" lần hai ở cuối câu (đã có "@Vũ" khác) vẫn xếp như thường. */
    const curP = tail && ((S.qa.w && S.qa.w.list) || []).filter(x => x.r && x.r.email && fold(x.tok) === whole).map(x => S.people.find(p => p.email === x.r.email))[0];
    if (curP) items = [curP].concat(items.filter(p => p.email !== curP.email));
    items = items.slice(0, 6);
    if (!items.length) { acClose(); return; }
    S.ac = { start, end: pos + tail.length, items, act: S.ac && S.ac.items.length === items.length ? Math.min(S.ac.act, items.length - 1) : 0 };
    paintAc();
  }
  function paintAc() {
    const ul = $(".pmq-acl"), a = S.ac;
    if (!a) return;
    ul.innerHTML = a.items.map((p, i) => `<li role="option" id="${idp}ac${i}" class="pmq-ac-i" data-i="${i}" aria-selected="${i === a.act}">${av(p.email, p.full_name || p.email)}<span><b>${esc(p.full_name || p.email)}</b><small>${esc(p.email)}</small></span></li>`).join("");
    ul.hidden = false;
    QIN.setAttribute("aria-expanded", "true");
    QIN.setAttribute("aria-activedescendant", idp + "ac" + a.act);
  }
  function acClose() {
    S.ac = null;
    const ul = R && $(".pmq-acl");
    if (ul) { ul.hidden = true; ul.innerHTML = ""; }
    if (QIN) { QIN.setAttribute("aria-expanded", "false"); QIN.removeAttribute("aria-activedescendant"); }
  }
  function acChoose(i) {
    const a = S.ac, p = a && a.items[i];
    if (!p) return;
    const v = QIN.value, h = handleFor(p, v.slice(a.start + 1, a.end)), ins = "@" + h + " ";
    QIN.value = v.slice(0, a.start) + ins + v.slice(a.end).replace(/^\s+/, "");
    const caret = a.start + ins.length;
    try { QIN.setSelectionRange(caret, caret); } catch (_) { /* jsdom */ }
    S.qa.picks[fold(h)] = { token: h, email: p.email, name: p.full_name || p.email };
    acClose();
    S.qa.text = QIN.value; S.qa.err = ""; qaParse(); paintParse();
    QIN.focus();
  }

  /* ---------------- đổi tab / lọc / nhật ký cá nhân */
  function switchTab(t) {
    if (t !== "me" && t !== "give") return Promise.resolve();
    const same = t === S.tab;
    S.tab = t; LAST_TAB = t;
    if (!same) { S.filter = "all"; S.sel = null; S.open = null; S.askForm = null; }
    paint();
    return refresh({ force: !same || !S.data[t] });
  }
  function showGiven(name) {
    return switchTab("give").then(() => { if (alive() && S.tab === "give" && rowOf(name)) select(name); });
  }
  function setPersonal(v) {
    S.personal = !!v;
    try { root.localStorage.setItem(LSK, v ? "1" : "0"); } catch (_) { /* chế độ riêng tư */ }
    S.seq++; S.inflight = null;   /* bỏ phản hồi cũ (khác tham số) */
    refresh({ force: true, manual: true });
  }

  /* ---------------- sự kiện */
  function onClick(e) {
    const t = e.target;
    const opt = t.closest && t.closest(".pmq-ac-i");
    if (opt) { e.preventDefault(); acChoose(+opt.getAttribute("data-i")); return; }
    const tb = t.closest && t.closest("[data-tab]");
    if (tb && R.contains(tb)) { switchTab(tb.getAttribute("data-tab")); return; }
    const fb = t.closest && t.closest("[data-f]");
    if (fb && R.contains(fb)) { S.filter = fb.getAttribute("data-f"); S.sel = null; paint(); return; }
    const b = t.closest && t.closest("[data-act]");
    if (b && R.contains(b)) {
      if (b.disabled) return;
      const a = b.getAttribute("data-act"), name = b.getAttribute("data-name"), req = b.getAttribute("data-req");
      e.stopPropagation();
      switch (a) {
        case "done": return doDone(name);
        case "start": return doStart(name);
        case "ask": return openFull(name, { askDeadline: true });
        case "nudge": return doNudge(name);
        case "approve": return doApprove(name);
        case "return": return doReturn(name);
        case "open": if (S.open === name) closeDrawer(); else openDrawer(name); return;
        case "close": return closeDrawer();
        case "full": return openFull(name);
        case "desc-retry": loadDetail(name); return paintDrawer();
        case "retry": S.err = null; paintList(); return refresh({ force: true, manual: true });
        case "all": S.filter = "all"; return paint();
        case "focus-qa": return QIN.focus();
        case "personal": return setPersonal(!S.personal);
        case "ask-accept": return askAccept(req);
        case "ask-reject": return askOpenForm(req, "reject");
        case "ask-propose": return askOpenForm(req, "propose");
        case "ask-cancel": { const k = S.askForm ? "ask:ask-" + S.askForm.kind + ":" + req : ""; S.askForm = null; paintAsk(); if (k) focusK(k); return; }
        case "ask-send": return askSend(req);
        case "prop-accept": return propAct(req, "accept_counter");
        case "prop-resend": return propAct(req, "resend");
        case "prop-keep": return propAct(req, "keep");
        case "ask-more": S.askAll = !S.askAll; paintAsk(); return focusK("ask:more");
        case "wait": S.waitOpen = LAST_WAIT = !S.waitOpen; paintList(); return focusK("wait");
        case "qa-pick": {
          const p = (S.people || []).find(x => x.email === b.getAttribute("data-email")), tk = b.getAttribute("data-tok") || S.qa.p.token;
          if (!p || !tk) return;
          const h = handleFor(p, tk);
          QIN.value = atNorm(QIN.value).replace(new RegExp("(^|\\s)@" + rxEsc(tk) + "[.\\-]*(?=$|[\\s,;:()])"), "$1@" + h);
          delete S.qa.picks[fold(tk)];
          S.qa.picks[fold(h)] = { token: h, email: p.email, name: p.full_name || p.email };
          S.qa.text = QIN.value; S.qa.err = ""; qaParse(); paintParse(); QIN.focus();
          return;
        }
        case "qa-rm": return qaDrop(b.getAttribute("data-email"), b.getAttribute("data-tok"));
        case "qa-more": return qaMore();
        case "people-retry": S.peopleErr = null; people().then(() => { if (alive()) { qaParse(); paintParse(); } }, () => { if (alive()) paintParse(); }); return;
        default: return;
      }
    }
    const row = t.closest && t.closest(".pmq-row");
    if (row && R.contains(row)) {
      const name = row.getAttribute("data-name");
      if (S.open === name) closeDrawer(); else openDrawer(name);
    }
  }
  function onInput(e) {
    const t = e.target;
    if (t === QIN) { onQaInput(); return; }
    const af = t.getAttribute && t.getAttribute("data-af");
    if (af && S.askForm) { S.askForm[af] = t.value; if (af === "reason" && S.askForm.err && t.value.trim()) { S.askForm.err = ""; t.removeAttribute("aria-invalid"); const er = $(".pmq-ask-form .pmq-ferr"); if (er) er.remove(); } }
  }
  function onChange(e) {
    const t = e.target, f = t.getAttribute && t.getAttribute("data-qa-f");
    if (f) {
      const q = S.qa;
      if (f === "due") { q.due = t.value; q.edited.due = true; q.dueDefault = false; }
      else if (f === "time") { q.time = t.value; q.edited.due = true; q.dueDefault = false; if (!q.due && t.value) q.due = ymdAdd(today(), 1); }
      else if (f === "pri") { q.pri = PRI[t.value] ? t.value : "Medium"; q.edited.pri = true; }
      else if (f === "ask") { q.ask = !!t.checked; q.edited.ask = true; LAST_ASK = q.ask; }
      else if (f === "mode") { q.split = t.value !== "shared"; LAST_SPLIT = q.split; }
      const k = t.id; paintParse(); const n = k && D.getElementById(k); if (n) n.focus();
      return;
    }
    const af = t.getAttribute && t.getAttribute("data-af");
    if (af && S.askForm) S.askForm[af] = t.value;
  }
  function onQaKey(e) {
    /* bộ gõ tiếng Việt / IME đang ghép chữ: Enter / Tab / mũi tên là của bộ gõ (Safari: keyCode 229 ngay sau compositionend) */
    if (e.isComposing || e.keyCode === 229 || S.composing) { if (e.key === "Enter") e.preventDefault(); return; }
    if (e.key === "Enter" && e.shiftKey && !S.ac) { e.preventDefault(); qaMore(); return; }   /* Shift+Enter = Thêm chi tiết */
    if (S.ac) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); S.ac.act = (S.ac.act + (e.key === "ArrowDown" ? 1 : -1) + S.ac.items.length) % S.ac.items.length; paintAc(); return; }
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); acChoose(S.ac.act); return; }
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); acClose(); return; }
    }
    if (e.key === "Escape" && !QIN.value) { QIN.blur(); }
  }
  function modalOpen() {
    const ms = D.querySelectorAll('[aria-modal="true"]');
    for (let i = 0; i < ms.length; i++) { const m = ms[i]; if (!m.hidden && (!m.classList.contains("pmr-sheet") || m.classList.contains("pmr-on"))) return true; }
    const ld = D.getElementById("pm-drawer");
    return !!(ld && ld.classList.contains("open"));
  }
  function onDocKey(e) {
    if (!alive() || e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target, tag = t && t.tagName;
    if (t && (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || t.isContentEditable)) return;
    if (modalOpen()) return;
    if (t && t !== D.body && t !== D.documentElement && !R.contains(t)) return;   /* phím của vùng khác (menu, vỏ shell) */
    const k = e.key, kl = k.length === 1 ? k.toLowerCase() : k, rows = visible(), names = rows.map(r => r.name);
    const i = S.sel ? names.indexOf(S.sel) : -1;
    const inList = t && t.closest && !!t.closest("[data-list]");
    if (kl === "n") { e.preventDefault(); QIN.focus(); return; }
    if (kl === "j" || (k === "ArrowDown" && inList)) { if (!names.length) return; e.preventDefault(); select(names[i < 0 ? 0 : Math.min(names.length - 1, i + 1)]); return; }
    if (kl === "k" || (k === "ArrowUp" && inList)) { if (!names.length) return; e.preventDefault(); select(names[i < 0 ? 0 : Math.max(0, i - 1)]); return; }
    if (kl === "x" && S.sel) { e.preventDefault(); doDone(S.sel, { advance: true }); return; }
    if (kl === "s" && S.sel) { e.preventDefault(); doStart(S.sel); return; }
    if (k === "Enter" && S.sel && !(t && t.closest && t.closest("button,a,input,select,textarea"))) { e.preventDefault(); openDrawer(S.sel, { focus: true }); return; }
    if (k === "Escape") {
      if (S.askForm) { const kk = "ask:ask-" + S.askForm.kind + ":" + S.askForm.req; S.askForm = null; paintAsk(); focusK(kk); e.preventDefault(); return; }
      if (S.open) { e.preventDefault(); closeDrawer(); return; }
      if (S.sel) { e.preventDefault(); const s = S.sel; select(null, { focus: false }); const b = rowEl(s); if (b && b.querySelector(".pmq-open")) b.querySelector(".pmq-open").blur(); }
    }
  }
  function onFocusIn(e) {
    const row = e.target.closest && e.target.closest(".pmq-row");
    if (row && R.contains(row) && S.sel !== row.getAttribute("data-name")) select(row.getAttribute("data-name"), { focus: false });
  }
  function onDocClick(e) { if (S.ac && !e.target.closest(".pmq-qa")) acClose(); }
  function onSubmit(e) { e.preventDefault(); qaSubmit(); }
  function onCompStart() { S.composing = true; }
  function onCompEnd() { S.composing = false; }
  /* quay lại tab trình duyệt (có thể vừa xong việc ở tab khác): làm mới nếu lần tải cuối đã quá 15 giây */
  function onVis() { if (!D.hidden && (S.stale || Date.now() - S.lastFetch > VISIT_STALE_MS)) refresh(); }
  function onChanged(e) {
    const d = (e && e.detail) || {};
    if (d.source === "pmq" || !alive()) return;
    const at = Date.now();
    clearTimeout(S.chT);
    S.chT = setTimeout(() => { if (alive()) refresh({ since: at }); }, 300);
  }

  R.addEventListener("click", onClick);
  R.addEventListener("input", onInput);
  R.addEventListener("change", onChange);
  R.addEventListener("focusin", onFocusIn);
  $("[data-qa-form]").addEventListener("submit", onSubmit);
  QIN.addEventListener("keydown", onQaKey);
  QIN.addEventListener("compositionstart", onCompStart);
  QIN.addEventListener("compositionend", onCompEnd);
  const TO = $(".pmq-toast");
  TO.addEventListener("mouseenter", toastHold); TO.addEventListener("focusin", toastHold);
  TO.addEventListener("mouseleave", toastResume); TO.addEventListener("focusout", toastResume);
  QIN.addEventListener("click", acUpdate);
  QIN.addEventListener("focus", () => { if (!S.people && !S.peopleP && !S.peopleErr) people().catch(() => { /* báo khi cần */ }); });
  D.addEventListener("keydown", onDocKey);
  D.addEventListener("click", onDocClick);
  D.addEventListener("visibilitychange", onVis);
  D.addEventListener("pmr:changed", onChanged);
  const iv = setInterval(() => {
    if (!alive()) return;
    if (D.hidden) { S.stale = true; return; }
    if (S.askForm || S.qaN > 0 || Object.keys(S.busy).length) { S.stale = true; return; }   /* đang gõ lý do / đang ghi: để sau */
    refresh();
  }, REFRESH_MS);
  function destroy() {
    if (S.dead) return;
    S.dead = true;
    clearInterval(iv); clearTimeout(S.chT); clearTimeout(S.toastT);
    S.timers.forEach(clearTimeout); S.timers = [];
    D.removeEventListener("keydown", onDocKey);
    D.removeEventListener("click", onDocClick);
    D.removeEventListener("visibilitychange", onVis);
    D.removeEventListener("pmr:changed", onChanged);
    if (el._pmq === ctl) el._pmq = null;
  }
  const ctl = { refresh: o => refresh(o && o.soft ? { since: Date.now() - SOFT_MS } : { force: true }), destroy, root: R, _state: S };   /* soft: host làm mới ~400 ms sau pmr:changed; bỏ qua nếu hàng đợi vừa tự tải */
  el._pmq = ctl;
  paintParse();
  refresh();
  return ctl;
}

root.PMQueue = { render, _parseLine: parseLine, _matchPeople: matchPeople, _resolvePerson: resolvePerson, _esc: esc };
})(window);
