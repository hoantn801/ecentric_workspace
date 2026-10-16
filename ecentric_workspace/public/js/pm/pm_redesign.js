/* pm_redesign.js — /pm làm lại (SPEC 16/10/2026, mockup pm_lam_lai_v4, DESIGN.md). Asset tĩnh, cú pháp ≤ ES2018, global DUY NHẤT window.PMR.
 * Server qua cfg.api("ecentric_workspace.pm.api.<m>.<fn>", args), danh sách gửi chuỗi JSON. Sự kiện: pmr:changed · pmr:timer · pmr:sheetclose · pmr:badge. */
(function (root) {
"use strict";
if (root.PMR && root.PMR.__pmr) return;
const D = root.document, PMA = "ecentric_workspace.pm.api.", HAS = Object.prototype.hasOwnProperty;
const cfg = { api: null, user: "", now: null, views: {}, navigate: null, openProject: null, openChat: null, onChange: null,
  onSheetClose: null, onViewChange: null, createProject: null };   /* go/el/esc/toast của host: bỏ qua */
const NAMES = {};
let inited = false;

/* == helpers == */
const esc = s => s == null ? "" : String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const truthy = v => v === true || v === 1 || v === "1" || v === "true" || v === "True" || v === "Yes";
function safe(fn, a, b) { try { return fn(a, b); } catch (e) { return; } }
function arr(v) {
  if (!v) return [];
  if (Array.isArray(v)) return v;
  if (typeof v === "string") { try { const j = JSON.parse(v); return Array.isArray(j) ? j : [v]; } catch (e) { return [v]; } }
  return [];
}
function pick(a, b, ...keys) { for (const k of keys) for (const o of [a, b]) if (o && o[k] != null) return o[k]; return null; }
function fold(s) {
  s = String(s || "").toLowerCase();
  if (s.normalize) s = s.normalize("NFD").replace(/[̀-ͯ]/g, "");
  return s.replace(/đ/g, "d");
}
const $ = (sel, r) => (r || D).querySelector(sel);
const $$ = (sel, r) => Array.from((r || D).querySelectorAll(sel));
const $S = sel => $(sel, S.el), $$S = sel => $$(sel, S.el);
const ga = (el, k) => el.getAttribute("data-" + k);

function call(m, args) {
  if (!cfg.api) return Promise.reject(new Error("PMR chưa init (thiếu api)."));
  const a = {};
  args = args || {};
  for (const k in args) if (HAS.call(args, k) && args[k] != null) a[k] = args[k];
  try { return Promise.resolve(cfg.api(PMA + m, a)); } catch (e) { return Promise.reject(e); }
}
const clean = t => String(t).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
function fromSM(sm) {
  if (!sm) return "";
  try {
    const list = typeof sm === "string" ? JSON.parse(sm) : sm;
    let o = list && list[0];
    if (typeof o === "string") { try { o = JSON.parse(o); } catch (x) { o = { message: o }; } }
    const t = o && (o.message || o.title);
    if (t) return clean(t);
  } catch (x) { }
  return "";
}
function errOf(e) {
  const fb = "Đã có lỗi. Vui lòng thử lại.";
  if (!e) return fb;
  let m = fromSM(e._server_messages || (e.responseJSON && e.responseJSON._server_messages));
  if (m) return m;
  let msg = e.message != null ? String(e.message) : (typeof e === "string" ? e : "");
  if (/^\s*\[/.test(msg) && (m = fromSM(msg))) return m;
  msg = clean(msg.replace(/^[\w.]*(Error|Exception)\s*:\s*/, ""));
  return msg || fb;
}
const isPermErr = e => /Permission|quyền|permitted|403/i.test(`${(e && (e.exc_type || e.name)) || ""} ${errOf(e)}`);

/* -- dates (giờ địa phương) -- */
const NOPROJ = "Không thuộc dự án";
const WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const now = () => cfg.now ? cfg.now() : new Date();
const pad = n => (n < 10 ? "0" : "") + n;
const ymdOf = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const todayYmd = () => ymdOf(now());
function parseYmd(s) { const m = String(s || "").match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? new Date(+m[1], m[2] - 1, +m[3]) : null; }
function parseDT(s) {
  const m = String(s || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  return m ? new Date(+m[1], m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)) : null;
}
const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const dayDiff = (a, b) => Math.round((Date.UTC(b.getFullYear(), b.getMonth(), b.getDate()) - Date.UTC(a.getFullYear(), a.getMonth(), a.getDate())) / 864e5);
function hm(t) { const m = String(t || "").match(/^(\d{1,2}):(\d{2})/); return m ? `${pad(+m[1])}:${m[2]}` : ""; }
function timeOfDT(s) { const m = String(s || "").match(/[ T](\d{2}:\d{2})/); return m && m[1] !== "00:00" ? m[1] : ""; }
const dm = d => `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
function dayLabel(ymd) { const d = parseYmd(ymd); return d ? `${WD[d.getDay()]} ${dm(d)}` : ""; }
function fullDue(ymd, t) { const s = dayLabel(ymd), h = hm(t) || timeOfDT(ymd); return s && h ? `${s} · ${h}` : s; }
function shortDate(ymd) { const d = parseYmd(ymd); return d ? dm(d) : ""; }
function dueInfo(ymd, t, ws) {
  const d = parseYmd(ymd);
  if (!d) return { text: "Chưa có hạn", cls: "pmr-none" };
  const h = hm(t) || timeOfDT(ymd), diff = dayDiff(parseYmd(todayYmd()), d), closed = isClosed(ws);
  if (!closed && diff < 0) return { text: `Trễ ${-diff} ngày`, cls: "pmr-late", late: true };
  if (diff === 0) return { text: "Hôm nay" + (h ? " " + h : ""), cls: closed ? "" : "pmr-soon" };
  if (diff === 1) return { text: h ? "Mai " + h : "Ngày mai", cls: closed ? "" : "pmr-soon" };
  return { text: dayLabel(ymd), cls: "" };
}
function lateDays(ymd) { const d = parseYmd(ymd); return d ? Math.max(0, dayDiff(d, parseYmd(todayYmd()))) : 0; }
function relTime(s) {
  const d = parseDT(s);
  if (!d) return "";
  const n = now(), mins = Math.floor((n - d) / 60000), dd = dayDiff(d, n), clock = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (mins < 1) return "vừa xong";
  if (dd === 0) return mins < 60 ? `${mins} phút trước` : `${Math.floor(mins / 60)} giờ trước`;
  if (dd === 1) return "hôm qua " + clock;
  return dm(d) + (d.getFullYear() !== n.getFullYear() ? "/" + d.getFullYear() : "") + " " + clock;
}
function relDay(s) { const d = parseDT(s), dd = d ? dayDiff(d, now()) : 0; return !d ? "" : dd <= 0 ? "hôm nay" : dd === 1 ? "hôm qua" : dm(d); }
const hoursFmt = h => (Math.round((+h || 0) * 10) / 10).toFixed(1).replace(".", ",");
function parseHours(v) { const n = parseFloat(String(v || "").replace(",", ".")); return isFinite(n) && n > 0 ? Math.round(n * 1e4) / 1e4 : 0; }
function weekRange() { const t = parseYmd(todayYmd()), dow = (t.getDay() + 6) % 7; return [ymdOf(addDays(t, -dow)), ymdOf(addDays(t, 6 - dow))]; }
const ymd10 = v => String(v || "").slice(0, 10);

/* -- nhãn dùng chung (SPEC mục 3) -- */
const LABELS = {
  state: { "Backlog": "Chưa làm", "To Do": "Chưa làm", "In Progress": "Đang làm", "Review": "Chờ duyệt", "Done": "Xong", "Cancelled": "Đã huỷ", "Blocked": "Bị chặn" },
  priority: { "Low": "Thấp", "Medium": "Bình thường", "High": "Cao", "Urgent": "Gấp" }
};
const SCLS = { "Backlog": 0, "To Do": 0, "Blocked": 0, "In Progress": 1, "Review": 2, "Done": 3, "Cancelled": 4 };
const stateLabel = ws => LABELS.state[ws] || (ws ? String(ws) : "Chưa làm");
const priorityLabel = p => LABELS.priority[p] || (p ? String(p) : "");
const stateIdx = ws => SCLS[ws] == null ? 0 : SCLS[ws];
const isClosed = ws => ws === "Done" || ws === "Cancelled";
const curBucket = ws => ws === "Backlog" ? "To Do" : (ws === "Blocked" ? "In Progress" : ws);
function pill(ws, attrs) {
  const tag = attrs ? "button" : "span";
  return `<${tag}${attrs ? ` type="button" ${attrs}` : ""} class="pmr-st pmr-s${stateIdx(ws)}">${esc(stateLabel(ws))}</${tag}>`;
}

/* -- người -- */
const nameOf = u => u ? NAMES[u] || String(u).split("@")[0] : "";
function learnNames(map) { if (map && typeof map === "object") for (const k in map) if (HAS.call(map, k) && map[k]) NAMES[k] = map[k]; }
function initials(nm) {
  let s = String(nm || "?").trim();
  if (s.indexOf("@") > 0) s = s.split("@")[0].replace(/[._-]+/g, " ");
  const w = s.split(/\s+/).filter(Boolean);
  if (!w.length) return "?";
  return (w.length === 1 ? w[0].slice(0, 2) : w[0].charAt(0) + w[w.length - 1].charAt(0)).toUpperCase();
}
function colorIdx(k) { let h = 0; const s = String(k || ""); for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return (Math.abs(h) % 7) + 1; }
function av(u, nm, cls) {
  nm = nm || nameOf(u);
  return `<span class="pmr-av pmr-a${colorIdx(u || nm)}${cls ? " " + cls : ""}" title="${esc(nm)}" aria-hidden="true">${esc(initials(nm))}</span>`;
}
function stack(users, max) {
  max = max || 5;
  return `<span class="pmr-stack">${users.slice(0, max).map(u => av(u)).join("")}${users.length > max ? `<span class="pmr-av pmr-more" aria-hidden="true">+${users.length - max}</span>` : ""}<span class="pmr-sr">${esc(users.map(nameOf).join(", "))}</span></span>`;
}
const who = (u, nm) => `<span class="pmr-who">${av(u, nm)}${esc(nm || nameOf(u))}</span>`;
let PEOPLE = null;
function people() {
  if (!PEOPLE) {
    PEOPLE = call("assignment.list_assignable", {}).then(r => {
      const rows = (r && r.rows) || [];
      rows.forEach(x => { if (x.email) NAMES[x.email] = x.full_name || x.email; });
      return rows;
    }, e => { PEOPLE = null; throw e; });
  }
  return PEOPLE;
}

/* -- icon: inline SVG symbol (không data: URI, không emoji) -- */
const ICONS = {
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  right: '<path d="m9 6 6 6-6 6"/>',
  pin: '<path d="M12 17v5"/><path d="M9 4h6l-1 6 3 4H7l3-4z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  cal: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  repeat: '<path d="M17 2l4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  userx: '<circle cx="9" cy="8" r="4"/><path d="M3 21v-1a6 6 0 0 1 9-5.2M17 15l4 4M21 15l-4 4"/>',
  calx: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M3 10h18M10 14l4 4M14 14l-4 4"/>',
  flag: '<path d="M4 22V4M4 4h12l-2 4 2 4H4"/>',
  clip: '<path d="m21.4 11-8.5 8.5a6 6 0 0 1-8.5-8.5l8.5-8.5a4 4 0 0 1 5.7 5.7L10 16.8a2 2 0 0 1-2.8-2.8l7.8-7.8"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  board: '<rect x="3" y="3" width="5" height="18" rx="1"/><rect x="10" y="3" width="5" height="12" rx="1"/><rect x="17" y="3" width="4" height="8" rx="1"/>',
  gantt: '<path d="M3 6h9M7 12h11M5 18h7"/>',
  appr: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>'
};
const ic = (n, cls) => `<svg class="pmr-i${cls ? " " + cls : ""}" aria-hidden="true" focusable="false"><use href="#pmr-i-${n}"></use></svg>`;
function ensureSprite() {
  if (D.getElementById("pmr-sprite")) return;
  const w = D.createElement("div");
  w.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" id="pmr-sprite" class="pmr-sprite" aria-hidden="true"><defs>${Object.keys(ICONS).map(k =>
    `<symbol id="pmr-i-${k}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${ICONS[k]}</symbol>`).join("")}</defs></svg>`;
  D.body.appendChild(w.firstChild);
}

/* -- sự kiện + DOM -- */
const changed = d => emit("pmr:changed", d);
function emit(name, detail) {
  try { D.dispatchEvent(new root.CustomEvent(name, { detail: detail || {} })); } catch (e) { }
  if (name === "pmr:changed" && cfg.onChange) safe(cfg.onChange, detail);
}
/* Một handler uỷ quyền cho mỗi (phần tử, loại sự kiện); gọi lại thì thay handler cũ. */
function on(el, handler, type) {
  type = type || "click";
  const key = "__pmr_" + type;
  if (el[key]) el.removeEventListener(type, el[key]);
  el[key] = e => {
    const t = e.target && e.target.closest ? e.target.closest("[data-act]") : null;
    if (t && el.contains(t)) handler(ga(t, "act"), t, e);
  };
  el.addEventListener(type, el[key]);
}
function busy(b, p) {
  if (b) { b.disabled = true; b.classList.add("pmr-busy"); b.setAttribute("aria-busy", "true"); }
  const done = () => { if (b) { b.disabled = false; b.classList.remove("pmr-busy"); b.removeAttribute("aria-busy"); } };
  return p.then(r => { done(); return r; }, e => { done(); throw e; });
}
const skel = n => `<div class="pmr-skel" aria-busy="true" aria-label="Đang tải">${'<div class="pmr-skel-row"><i></i><i></i><i></i></div>'.repeat(n || 5)}</div>`;
const emptyBox = (icon, title, body, act) => `<div class="pmr-empty">${ic(icon, "pmr-empty-i")}<h4>${esc(title)}</h4><div>${body || ""}</div>${act || ""}</div>`;
const pageHead = (title, sub, right) => `<div class="pmr-ph"><div class="pmr-grow"><h2>${esc(title)}</h2>${sub ? `<div class="pmr-sub">${sub}</div>` : ""}</div>${right || ""}</div>`;
const sectionT = (title, n) => `<div class="pmr-section-t">${esc(title)} <span class="pmr-cnt pmr-num">${n}</span></div>`;
/* Nút hành động (label là HTML đã an toàn) và nút dạng link. */
const B = (label, act, cls, extra) => `<button type="button" class="pmr-btn${cls ? " " + cls : ""}" data-act="${act}"${extra || ""}>${label}</button>`;
const Bs = (label, act, cls, extra) => B(label, act, "pmr-sm" + (cls ? " " + cls : ""), extra);
const L = (label, act, extra, cls) => `<button type="button" class="pmr-link${cls ? " " + cls : ""}" data-act="${act}"${extra || ""}>${label}</button>`;
const thead = (cols, cls) => `<table class="pmr-tb${cls ? " " + cls : ""}"><thead><tr>${cols.map(c => c[0] === ">" ? `<th class="pmr-r">${c.slice(1)}</th>` : `<th>${c}</th>`).join("")}</tr></thead><tbody>`;
const muted = t => `<span class="pmr-muted">${t}</span>`;
const dueSpan = di => `<span class="pmr-due ${di.cls}">${esc(di.text)}</span>`;
const onA = (on, k) => ` aria-${k || "pressed"}="${!!on}" class="${on ? "pmr-on" : ""}"`;
const dattr = (k, v) => ` data-${k}="${esc(v)}"`;
const errBox = (title, e, retry) => `<div class="pmr-errbox" role="alert"><b>${esc(title)}</b> <span>${esc(errOf(e))}</span>${retry ? " " + Bs("Thử lại", "retry") : ""}</div>`;
function prep(c) { if (!c || !c.nodeType) throw new Error("PMR: thiếu container"); ensureInit(); c.classList.add("pmr-root"); return c; }
function loadErr(c, e, retry, head) {
  c.innerHTML = (head || "") + errBox("Không tải được dữ liệu.", e, true);
  on(c, a => { if (a === "retry") retry(); });
}
function nav(hash) {
  if (cfg.navigate) return void safe(cfg.navigate, hash);
  try { root.location.hash = hash; } catch (e) { }
}
function openProject(name) { if (cfg.openProject) safe(cfg.openProject, name); else nav("#project/" + encodeURIComponent(name)); }
function gone(node) { node.classList.add("pmr-gone"); return () => node.classList.remove("pmr-gone"); }

/* -- nhật ký cá nhân: Hiện/Ẩn (localStorage) -- */
const LSK = "pmr.showPersonal";
function isPersonalShown() { try { return root.localStorage.getItem(LSK) === "1"; } catch (e) { return false; } }
function setPersonal(v) { try { root.localStorage.setItem(LSK, v ? "1" : "0"); } catch (e) { } }
function personalToggle(container, onChange, o) {
  o = o || {};
  const w = D.createElement("div");
  w.className = "pmr-hidenote";
  const paint = () => {
    const shown = isPersonalShown(), cnt = o.count != null ? o.count + " " : "";
    w.innerHTML = `${ic("eye", "pmr-s")}<span>${shown ? "Đang hiện " : "Đang ẩn "}${esc(cnt + (o.noun || "việc nhật ký cá nhân"))}${o.suffix && !shown ? esc(o.suffix) : ""}.</span><button type="button" class="pmr-link" aria-pressed="${shown}">${shown ? "Ẩn" : "Hiện"}</button>`;
  };
  paint();
  w.addEventListener("click", e => {
    if (!e.target.closest("button")) return;
    setPersonal(!isPersonalShown());
    paint();
    if (onChange) safe(onChange, isPersonalShown());
  });
  if (container) container.appendChild(w);
  return w;
}

/* == toast + ô ghi giờ == */
const T = { el: null, timer: null };
function hideToast() { if (T.el) T.el.classList.remove("pmr-on"); clearTimeout(T.timer); }
function toast(msg, o) {
  o = o || {};
  if (!T.el || !T.el.parentNode) {
    T.el = D.createElement("div");
    T.el.className = "pmr-toast";
    T.el.setAttribute("role", "status");
    T.el.setAttribute("aria-live", "polite");
    D.body.appendChild(T.el);
  }
  const t = T.el, acts = o.actions || [];
  clearTimeout(T.timer);
  t.innerHTML = '<span class="pmr-toast-m"></span>';
  t.firstChild.textContent = msg;
  t.classList.toggle("pmr-err", !!o.error);
  acts.forEach(a => {
    const b = D.createElement("button");
    b.type = "button";
    b.className = "pmr-toast-b";
    b.textContent = a.label;
    b.addEventListener("click", ev => { ev.stopPropagation(); hideToast(); try { a.run(); } catch (er) { bad(errOf(er)); } });
    t.appendChild(b);
  });
  t.classList.add("pmr-on");
  T.timer = setTimeout(hideToast, o.error || acts.length ? 6500 : 3200);
}
const bad = msg => toast(msg, { error: true });
const errToast = (e, prefix) => bad((prefix ? prefix + ": " : "") + errOf(e));

/* Ghi giờ dùng chung cho toast "Ghi giờ" và tab Thời gian: cùng Timesheet hiện có (timesheet.log). */
const logFields = hAttr => `<input class="pmr-in" type="date" aria-label="Ngày" value="${todayYmd()}"><input class="pmr-in pmr-in-h" inputmode="decimal" aria-label="Số giờ" ${hAttr}> giờ` +
  '<input class="pmr-in pmr-in-note" aria-label="Làm gì" placeholder="Làm gì (không bắt buộc)">';
function saveHours(task, box, b, after) {
  const ins = box.querySelectorAll("input"), hrs = parseHours(ins[1].value);
  if (!hrs) { bad("Nhập số giờ lớn hơn 0"); return ins[1].focus(); }
  busy(b, call("timesheet.log", { task, hours: hrs, log_date: ins[0].value || todayYmd(), description: ins[2].value || "" })).then(() => {
    toast(`Đã ghi ${hoursFmt(hrs)} giờ`); changed({ task, hours: hrs }); if (after) after();
  }, e => errToast(e, "Chưa ghi được giờ"));
}
/* Nhắc / trả lời / rút đề xuất dời hạn: dùng chung cho mọi màn. */
function nudge(b, task, u, n) {
  busy(b, call("pm_inbox.nudge", u ? { task, users: JSON.stringify([u]) } : { task })).then(r => {
    const sent = r && r.sent != null ? (r.sent.length != null ? r.sent.length : r.sent) : n;
    toast(u ? "Đã nhắc " + nameOf(u) : `Đã nhắc ${sent} người`);
  }, e => errToast(e, "Chưa nhắc được"));
}
const answerDl = (b, request, accept, ok, fail) => busy(b, call("pm_inbox.answer_deadline", { request, accept })).then(ok, e => { if (fail) fail(); errToast(e, "Chưa trả lời được"); });
const withdrawDl = (b, request, ok, fail) => busy(b, call("pm_inbox.withdraw_deadline", { request })).then(() => { toast("Đã rút lại đề xuất"); ok(); }, e => { if (fail) fail(); errToast(e, "Chưa rút được đề xuất"); });
let POP = null;
function closeLogPop() { if (POP && POP.parentNode) POP.parentNode.removeChild(POP); POP = null; }
function openLogPop(task, subject, after) {
  closeLogPop();
  const p = POP = D.createElement("div");
  p.className = "pmr-pop pmr-root";
  p.setAttribute("role", "dialog");
  p.setAttribute("aria-label", "Ghi giờ");
  p.innerHTML = `<h4>Ghi giờ cho “<span></span>”</h4><div class="pmr-row">${logFields('value="1"')}</div><div class="pmr-acts">${Bs("Bỏ qua", "lp-x")}${Bs("Lưu", "lp-save", "pmr-pri")}</div>`;
  p.querySelector("h4 span").textContent = subject || task;
  D.body.appendChild(p);
  const ins = p.querySelectorAll("input");
  safe(() => { ins[1].focus(); ins[1].select(); });
  on(p, (a, b) => {
    if (a === "lp-x") closeLogPop();
    else if (a === "lp-save") saveHours(task, p, b, () => { closeLogPop(); if (after) safe(after); });
  });
  p.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.tagName === "INPUT") { e.preventDefault(); $("[data-act=lp-save]", p).click(); } });
  return p;
}

/* == ngăn kéo bên phải (dùng chung) == */
const S = { el: null, scrim: null, prev: null, kind: null, onClose: null, task: null };
let TS = {}, NT = null, TICK = null;
const stopTick = () => { if (TICK) { clearInterval(TICK); TICK = null; } };
function sheetOpen(kind, label, onClose) {
  if (!S.el || !S.el.parentNode) {
    S.scrim = D.createElement("div");
    S.scrim.className = "pmr-scrim";
    S.scrim.addEventListener("click", onScrimClick);
    S.el = D.createElement("aside");
    S.el.className = "pmr-sheet pmr-root";
    S.el.setAttribute("role", "dialog");
    S.el.setAttribute("aria-modal", "true");
    S.el.setAttribute("tabindex", "-1");
    D.body.appendChild(S.scrim);
    D.body.appendChild(S.el);
  }
  if (S.kind && S.kind !== kind) firedClose();
  if (!S.kind) S.prev = D.activeElement;
  stopTick();
  closeLogPop();
  if (kind !== "new") NT = null;
  if (kind !== "task") TS = {};
  S.kind = kind;
  S.onClose = onClose || null;
  S.el.setAttribute("aria-label", label);
  S.el.setAttribute("data-kind", kind);
  S.el.onkeydown = null;
  S.el.classList.add("pmr-on");
  S.scrim.classList.add("pmr-on");
  D.body.classList.add("pmr-noscroll");
  return S.el;
}
function firedClose() {
  const k = S.kind, t = S.task, cb = S.onClose;
  S.onClose = null;
  if (cb) safe(cb);
  if (cfg.onSheetClose) safe(cfg.onSheetClose, k, t);
  emit("pmr:sheetclose", { kind: k, task: t });
}
/* Bấm vùng xám: (1) đang mở danh sách chọn (người / dự án / ghi giờ) -> chỉ đóng danh sách đó;
   (2) form Giao việc đang soạn dở -> KHÔNG đóng, nhắc bấm Huỷ (tránh mất nội dung); (3) còn lại đóng. */
function closeFloating() {
  let n = 0;
  $$(".pmr-picker").forEach(x => { x.parentNode.removeChild(x); n++; });
  $$(".pmr-pj-list").forEach(x => { if (!x.hidden) { x.hidden = true; n++; } });
  if (POP) { closeLogPop(); n++; }
  if (n && NT) safe(paintProjectSel);
  return n;
}
function newDirty() {
  if (S.kind !== "new" || !NT) return false;
  const t = $S(".pmr-title-in"), d = $S(".pmr-nt-desc");
  return !!((t && t.value.trim()) || NT.assignees.length || (d && d.value.trim()) || NT.steps.length);
}
function onScrimClick() {
  if (closeFloating()) return;
  if (newDirty()) { toast("Bạn đang soạn dở việc này. Bấm Huỷ nếu muốn bỏ."); const c = $S("[data-act=close]"); if (c) safe(() => c.focus()); return; }
  sheetClose();
}
function sheetClose() {
  if (!S.el || !S.kind) return;
  stopTick();
  closeLogPop();
  S.el.classList.remove("pmr-on");
  S.scrim.classList.remove("pmr-on");
  D.body.classList.remove("pmr-noscroll");
  firedClose();
  S.kind = S.task = null;
  TS = {};
  NT = null;
  const p = S.prev;
  S.prev = null;
  if (p && p.focus && D.contains(p)) safe(() => p.focus());
}
const focusables = r => $$("button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex]:not([tabindex='-1'])", r)
  .filter(x => !x.closest(".pmr-hide"));
function focusFirst(r, sel) { const t = (sel && $(sel, r)) || focusables(r)[0]; if (t) safe(() => t.focus()); }
function onDocKey(e) {
  if (e.key === "Escape") {
    if (closeFloating()) { /* chỉ đóng danh sách đang mở */ }
    else if (newDirty()) toast("Bạn đang soạn dở việc này. Bấm Huỷ nếu muốn bỏ.");
    else if (S.kind) sheetClose();
    else return;
    e.preventDefault();
    return;
  }
  if (e.key === "Tab" && S.kind && S.el.contains(D.activeElement)) {
    const f = focusables(S.el), first = f[0], last = f[f.length - 1];
    if (!f.length) return;
    if (e.shiftKey && D.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && D.activeElement === last) { e.preventDefault(); first.focus(); }
  }
}

/* -- làm sạch HTML (bình luận, mô tả) -- */
const OK_TAGS = /^(A|B|STRONG|I|EM|U|BR|P|DIV|SPAN|UL|OL|LI|IMG|CODE|PRE|BLOCKQUOTE|H4)$/;
const DROP_TAGS = /^(SCRIPT|STYLE|IFRAME|OBJECT|EMBED|LINK|META|SVG|MATH|FORM|INPUT|TEXTAREA|BUTTON|SELECT|TEMPLATE|NOSCRIPT)$/;
function walk(node) {
  Array.from(node.childNodes).forEach(n => {
    if (n.nodeType === 8) return void n.parentNode.removeChild(n);
    if (n.nodeType !== 1) return;
    const tag = n.tagName.toUpperCase();
    if (!OK_TAGS.test(tag)) {
      if (DROP_TAGS.test(tag)) return void n.parentNode.removeChild(n);
      walk(n);
      while (n.firstChild) n.parentNode.insertBefore(n.firstChild, n);
      return void n.parentNode.removeChild(n);
    }
    Array.from(n.attributes).forEach(a => {
      const nm = a.name.toLowerCase(), v = (a.value || "").trim();
      const keep = (tag === "A" && nm === "href" && /^(https?:|\/|mailto:)/i.test(v)) || (tag === "IMG" && ((nm === "src" && /^(https?:|\/)/i.test(v)) || nm === "alt"));
      if (!keep) n.removeAttribute(a.name);
    });
    if (tag === "A") { n.setAttribute("target", "_blank"); n.setAttribute("rel", "noopener noreferrer"); }
    walk(n);
  });
}
function sanitize(html) {
  const tpl = D.createElement("template");
  tpl.innerHTML = String(html || "");
  const frag = tpl.content || tpl, d = D.createElement("div");
  walk(frag);
  d.appendChild(frag.cloneNode(true));
  return d.innerHTML;
}
const linkify = text => esc(text || "").replace(/\n/g, "<br>").replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
const buildComment = (text, atts) => linkify(text) + (atts || []).map(x => x.is_image
  ? `<br><img src="${esc(x.url)}" alt="${esc(x.name)}">` : `<br><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.name)}</a>`).join("");

/* == chọn người (một kiểu cho toàn module) == */
function pickPeople(host, onPick, o) {
  o = o || {};
  const old = $(".pmr-picker", host);
  if (old) { old.parentNode.removeChild(old); return null; }
  const p = D.createElement("div");
  p.className = "pmr-picker";
  p.innerHTML = `<input class="pmr-in" role="combobox" aria-expanded="true" aria-autocomplete="list" aria-label="Tìm người" placeholder="Gõ tên hoặc email"><div class="pmr-pick-list" role="listbox">${skel(3)}</div>`;
  host.appendChild(p);
  const inp = p.firstChild, list = p.lastChild;
  let rows = [], act = 0, shown = [];
  const paint = () => {
    const q = fold(inp.value), ex = (typeof o.exclude === "function" ? o.exclude() : o.exclude) || [];
    shown = rows.filter(r => ex.indexOf(r.email) < 0 && (!q || fold(r.full_name + " " + r.email).indexOf(q) >= 0)).slice(0, 30);
    if (act >= shown.length) act = 0;
    list.innerHTML = shown.length ? shown.map((r, i) => `<button type="button" role="option" class="pmr-popt${i === act ? " pmr-act" : ""}" aria-selected="${i === act}" data-act="pick"${dattr("u", r.email)}>${av(r.email, r.full_name)}<span><b>${esc(r.full_name)}</b><small>${esc(r.email)}</small></span></button>`).join("")
      : `<div class="pmr-pick-empty">Không thấy ai khớp “${esc(inp.value)}”.</div>`;
  };
  const choose = u => {
    if (!u) return;
    if (!o.keepOpen && p.parentNode) p.parentNode.removeChild(p);
    onPick(u);
    if (o.keepOpen) { inp.value = ""; paint(); safe(() => inp.focus()); }
  };
  p.repaint = paint;
  people().then(r => { rows = r; paint(); }, e => { list.innerHTML = `<div class="pmr-pick-empty">${esc(errOf(e))}</div>`; });
  inp.addEventListener("input", () => { act = 0; paint(); });
  inp.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); act = Math.min(act + 1, shown.length - 1); paint(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); act = Math.max(act - 1, 0); paint(); }
    else if (e.key === "Enter") { e.preventDefault(); if (shown[act]) choose(shown[act].email); }
  });
  p.addEventListener("click", e => { e.stopPropagation(); const b = e.target.closest("[data-act=pick]"); if (b) choose(ga(b, "u")); });
  safe(() => inp.focus());
  return p;
}

/* == markDone — nút Xong ở mọi nơi (SPEC mục 4) == */
const BLOCKED = {
  required_steps: 'Chưa xong được: còn bước bắt buộc chưa tích. Tích đủ các bước rồi bấm Xong.',
  open_children: 'Chưa xong được: còn việc con đang mở. Đóng hết việc con trước.'
};
function undoState(name, prev, o) {
  return call("tasks.set_status", { name, action: prev }).then(() => {
    if (o && o.revert) safe(o.revert, prev);
    toast("Đã hoàn tác");
    changed({ task: name, state: prev });
  }, e => errToast(e, "Chưa hoàn tác được"));
}
/* o: {subject, prevState, reviewRequired, isGiver, predict, apply(state), revert(prev), button, onDone(result)}.
 * Không bao giờ reject: lỗi trả {error}. Bị chặn trả {blocked_reason}. */
function markDone(name, o) {
  o = o || {};
  if (!name) { bad("Thiếu mã việc"); return Promise.resolve({ error: "missing" }); }
  const predicted = o.predict || (o.reviewRequired && !o.isGiver ? "Review" : "Done"), prev = o.prevState || "In Progress";
  if (o.apply) safe(o.apply, predicted);
  let p = call("tasks.mark_done", { name });
  if (o.button) p = busy(o.button, p);
  return p.then(r => {
    r = r || {};
    if (r.blocked_reason) {
      if (o.revert) safe(o.revert, prev);
      bad(r.blocked_message || BLOCKED[r.blocked_reason] || "Chưa xong được: " + r.blocked_reason);
      return r;
    }
    const st = r.state || "Done", acts = [];
    if (st !== predicted && o.apply) safe(o.apply, st);
    if (st === "Done") acts.push({ label: "Ghi giờ", run: () => openLogPop(name, o.subject) });
    if (prev !== st) acts.push({ label: "Hoàn tác", run: () => undoState(name, prev, o) });
    toast((st === "Review" ? "Đã gửi kiểm tra" : "Đã xong") + (o.subject ? `: “${o.subject}”` : "") + (r.withdrew_request ? " · đã rút đề xuất dời hạn" : ""), { actions: acts });
    changed({ task: name, state: st });
    if (o.onDone) safe(o.onDone, r);
    return r;
  }, e => {
    if (o.revert) safe(o.revert, prev);
    errToast(e, "Chưa đánh dấu xong được");
    return { error: errOf(e) };
  });
}
/* Đổi trạng thái thường (không phải Xong): lạc quan, lỗi thì hoàn nguyên. */
function setState(name, target, prev, o) {
  o = o || {};
  if (o.apply) safe(o.apply, target);
  let p = call("tasks.set_status", { name, action: target });
  if (o.button) p = busy(o.button, p);
  return p.then(r => {
    toast(`Đã chuyển sang “${stateLabel(target)}”` + (o.subject ? `: “${o.subject}”` : ""),
      { actions: prev && prev !== target ? [{ label: "Hoàn tác", run: () => setState(name, prev, null, o) }] : [] });
    changed({ task: name, state: target });
    return r;
  }, e => {
    if (o.revert) safe(o.revert, prev);
    errToast(e, "Chưa đổi được trạng thái");
    return { error: errOf(e) };
  });
}

/* == Chi tiết việc (openTask) — góc người giao và người nhận == */
function normTask(res) {
  res = res || {};
  const t = res.task || {}, me = cfg.user;
  learnNames(res.user_names);
  let g = pick(res, t, "giver");
  if (!g) { const gu = t.requested_by || t.owner; if (gu) g = { user: gu, full_name: nameOf(gu) }; }
  if (g && g.user && g.full_name) NAMES[g.user] = g.full_name;
  const asg = arr(t._assign);
  return {
    t, subs: res.subtasks || [], giver: g, asg,
    review: truthy(pick(res, t, "review_required", "ec_review_required")),
    auto: truthy(pick(res, t, "auto_close", "ec_auto_close")),
    split: truthy(pick(res, t, "split", "ec_split_parent")),
    pdr: pick(res, t, "pending_deadline_request"),
    cp: pick(res, t, "children_progress"),
    rec: pick(res, t, "recurrence"),
    history: pick(res, t, "history"),
    isGiver: !!(g && g.user === me), isAssignee: asg.indexOf(me) >= 0,
    canManage: truthy(pick(res, t, "can_manage", "is_leader"))
  };
}
const giverName = d => d.giver ? d.giver.full_name || nameOf(d.giver.user) : "người giao";
const xBtn = `<button type="button" class="pmr-x" data-act="close" aria-label="Đóng">${ic("x")}</button>`;
function openTask(name, o) {
  o = o || {};
  if (!name) { bad("Thiếu mã việc"); return Promise.resolve(null); }
  const sh = sheetOpen("task", "Chi tiết việc", o.onClose), token = {};
  S.task = name;
  sh.innerHTML = `<div class="pmr-sh-h"><div class="pmr-sh-top"><span class="pmr-crumb">Đang mở việc…</span>${xBtn}</div></div><div class="pmr-sh-b">${skel(6)}</div>`;
  on(sh, a => { if (a === "close") sheetClose(); });
  focusFirst(sh);
  TS = { name, token, o, tab: o.tab || null };
  return Promise.all([call("tasks.get", { name }), call("checklist.get_for_task", { task: name }).then(null, () => null)]).then(rs => {
    if (TS.token !== token) return null;
    TS.d = normTask(rs[0]);
    TS.chk = rs[1];
    TS.askOpen = !!o.askDeadline;
    paintTask();
    return TS.d;
  }, e => {
    if (TS.token !== token) return null;
    $(".pmr-sh-b", sh).innerHTML = errBox("Không mở được việc.", e, true);
    on(sh, a => { if (a === "close") sheetClose(); else if (a === "retry") openTask(name, o); });
    return null;
  });
}
const reviewVariant = d => d.review && !d.isGiver && !d.canManage && d.t.workflow_state !== "Done";
function statusBarHtml(d) {
  const cur = curBucket(d.t.workflow_state);
  const set = [["To Do", "Chưa làm"], ["In Progress", "Đang làm"]].concat(reviewVariant(d) ? [["Review", "Gửi kiểm tra"]] : [["Review", "Chờ duyệt"], ["Done", "Xong"]]);
  return `<div class="pmr-statusbar" role="radiogroup" aria-label="Trạng thái">${set.map(s => {
    const onS = s[0] === cur;
    return `<button type="button" role="radio" aria-checked="${onS}" class="pmr-sb-${stateIdx(s[0])}${onS ? " pmr-on" : ""}" data-act="state"${dattr("s", s[0])}>${esc(s[1])}</button>`;
  }).join("")}</div>`;
}
const fl = (label, body, cls) => `<div class="pmr-fl${cls ? " " + cls : ""}"><span class="pmr-lb">${label}</span><div>${body}</div></div>`;
function paintTask() {
  const d = TS.d, t = d.t, sh = S.el, gname = giverName(d), terminal = isClosed(t.workflow_state), ck = TS.chk;
  /* 2 card cao bằng nhau (PO 16/10): card trái = tiêu đề + trạng thái + thông tin + tab; card phải = Bình luận. */
  let h = `<div class="pmr-sh-cols"><div class="pmr-main"><div class="pmr-sh-h"><div class="pmr-sh-top"><span class="pmr-crumb">${esc(t.project_name || NOPROJ)}</span>${ic("right", "pmr-s pmr-faint")}<span class="pmr-crumb2">${esc(t.name)}</span>${t.parent_task ? L("‹ Việc cha", "open-sub", dattr("task", t.parent_task), "pmr-ml pmr-crumb-up") : ""}` +
    `<button type="button" class="pmr-x" data-act="copy" aria-label="Sao chép liên kết">${ic("link", "pmr-s")}</button>${xBtn}</div><h3 class="pmr-dtitle">${esc(t.subject || t.name)}</h3>`;
  if (d.giver && d.isAssignee && !d.isGiver) {
    const line = [];
    if (t.creation) line.push(shortDate(t.creation));
    if (t.parent_task) line.push("phần của bạn trong một việc chung");
    h += `<div class="pmr-giver">${av(d.giver.user, gname)}<div><b>${esc(gname)}</b> giao cho bạn${line.length ? `<div class="pmr-muted">${esc(line.join(" · "))}</div>` : ""}</div>${cfg.openChat ? Bs("Nhắn", "chat", "pmr-ghost") : ""}</div>`;
  }
  h += statusBarHtml(d);
  if (reviewVariant(d) && !terminal) h += `<div class="pmr-hint">${esc(gname)} cần kiểm tra việc này: bấm <b>Gửi kiểm tra</b> khi làm xong, ${esc(gname)} sẽ đóng việc.</div>`;
  h += '</div><div class="pmr-sh-b"><div class="pmr-due-sec"></div>';
  if (!d.isAssignee || d.isGiver) h += fl("Người giao", d.giver ? (d.isGiver ? `<span class="pmr-who">${av(cfg.user)}Bạn</span>` : who(d.giver.user, gname)) : muted("—"));
  if (!(d.split && d.subs.length)) {
    h += `<div class="pmr-fl"><span class="pmr-lb">Người nhận</span><div class="pmr-pick-wrap">${d.asg.length ? d.asg.map(u => `<span class="pmr-pc">${av(u)}${esc(nameOf(u))}</span>`).join("") : muted("Chưa có người nhận") + " "}${t.workflow_state === "Cancelled" ? "" : L("+ Thêm người", "add-assignee")}</div></div>`;
  }
  h += fl("Dự án", t.project ? L(esc(t.project_name || t.project), "project", "", "pmr-link-ink") : muted(NOPROJ));
  if (d.rec) h += fl("Lặp lại", `<span class="pmr-tag">${ic("repeat", "pmr-s")}${esc(typeof d.rec === "string" ? d.rec : d.rec.label || d.rec.name || "")}</span>`);
  if (t.priority) h += fl("Ưu tiên", esc(priorityLabel(t.priority)));
  if (d.review) h += fl("Kiểm tra", muted("Cần người giao kiểm tra trước khi xong"));
  if (t.description && clean(t.description)) h += fl("Mô tả", `<div class="pmr-desc">${sanitize(t.description)}</div>`, "pmr-fl-top");
  const tabs = [];
  const people = d.split && d.subs.length, nDone = d.subs.filter(s => s.workflow_state === "Done").length;
  if (people) tabs.push(["people", `Từng người ${nDone}/${d.subs.length}`]);
  else if (!t.parent_task) tabs.push(["subs", "Việc con" + (d.subs.length ? ` ${nDone}/${d.subs.length}` : "")]);   /* 2 cấp: việc con không có việc con */
  tabs.push(["steps", "Các bước" + (ck && ck.total ? ` ${ck.done}/${ck.total}` : "")], ["time", "Thời gian"], ["his", "Lịch sử"]);
  if (!TS.tab || TS.tab === "cmt") TS.tab = people ? "people" : (d.subs.length ? "subs" : "steps");   /* "cmt" cũ: bình luận giờ ở cột phải */
  h += `<div class="pmr-stabs" role="tablist">${tabs.map(x => `<button type="button" role="tab"${onA(x[0] === TS.tab, "selected")} data-act="tab" data-tab="${x[0]}">${esc(x[1])}</button>`).join("")}</div><div class="pmr-tp" role="tabpanel"></div></div></div>` +
    '<aside class="pmr-side" aria-label="Bình luận"><h4 class="pmr-side-h">Bình luận <span class="pmr-side-n"></span></h4><div class="pmr-side-b"></div></aside></div>';
  sh.innerHTML = h;
  paintDue();
  loadTab(TS.tab);
  loadComments();
  on(sh, onTaskClick);
  on(sh, onTaskChange, "change");
  sh.onkeydown = e => {
    const cl = e.target.classList, ctrl = e.ctrlKey || e.metaKey;
    if (e.key !== "Enter") return;
    if (ctrl && cl.contains("pmr-cm-in")) { e.preventDefault(); $("[data-act=cm-send]", sh).click(); }
    else if (cl.contains("pmr-step-in")) { e.preventDefault(); $("[data-act=step-add]", sh).click(); }
    else if (cl.contains("pmr-sub-in")) { e.preventDefault(); $("[data-act=sub-add]", sh).click(); }
  };
  focusFirst(sh, TS.askOpen ? ".pmr-ask-reason" : ".pmr-statusbar .pmr-on");
}
function myPdr(d) {
  const p = d.pdr;
  if (!p || (p.status && p.status !== "Pending")) return null;
  const by = p.requested_by || p.from_user;
  return (by ? by === cfg.user : d.isAssignee && !d.isGiver) ? p : null;
}
function askOptions(d) {
  const today = parseYmd(todayYmd());
  let base = parseYmd(d.t.exp_end_date);
  if (!base || base < today) base = today;
  return [1, 3, 7].map(n => { const x = ymdOf(addDays(base, n)); return [x, n === 1 && dayDiff(today, addDays(base, 1)) === 1 ? "Ngày mai" : dayLabel(x)]; });
}
const qdBtn = (act, key, val, label, onB) => `<button type="button" data-act="${act}" data-${key}="${esc(val)}"${onA(onB)}>${esc(label)}</button>`;
function paintDue() {
  const d = TS.d, t = d.t, sec = $S(".pmr-due-sec");
  if (!sec) return;
  const di = dueInfo(t.exp_end_date, t.pm_end_time, t.workflow_state), mine = myPdr(d), open = !isClosed(t.workflow_state);
  const other = d.pdr && !mine && (!d.pdr.status || d.pdr.status === "Pending") ? d.pdr : null;
  const canAsk = d.isAssignee && !d.isGiver && open, canEdit = (d.isGiver || d.canManage) && open;
  let h = `<div class="pmr-fl pmr-fl-first"><span class="pmr-lb">Hạn</span><div class="pmr-due-row">${dueSpan(di)}${t.exp_end_date ? muted(esc(fullDue(t.exp_end_date, t.pm_end_time))) : ""}`;
  if (canAsk && !mine) h += Bs("Xin dời hạn", "ask-open", "pmr-wash pmr-ml", ` aria-expanded="${!!TS.askOpen}"`);
  else if (canEdit) h += L("Đổi hạn", "due-edit", "", "pmr-ml");
  h += "</div></div>";
  if (TS.dueEdit && canEdit) {
    h += `<div class="pmr-rs"><div class="pmr-row"><input class="pmr-in pmr-due-d" type="date" aria-label="Hạn mới" value="${esc(ymd10(t.exp_end_date))}"><input class="pmr-in pmr-due-t" type="time" aria-label="Giờ" value="${esc(hm(t.pm_end_time))}"></div>` +
      `<div class="pmr-acts">${Bs("Huỷ", "due-cancel")}${Bs("Lưu hạn", "due-save", "pmr-pri")}</div></div>`;
  }
  if (canAsk && !mine && TS.askOpen) {
    const opts = askOptions(d);
    TS.askPick = TS.askPick || opts[0][0];
    h += `<div class="pmr-rs"><h4>Xin ${esc(giverName(d))} dời hạn</h4><div class="pmr-row"><span class="pmr-lb pmr-lb-w">Hạn mới</span><div class="pmr-qd" role="group" aria-label="Hạn mới">` +
      opts.map(x => qdBtn("ask-pick", "d", x[0], x[1], !TS.askCustom && TS.askPick === x[0])).join("") + qdBtn("ask-custom", "d", "", "Chọn ngày…", TS.askCustom) + "</div>" +
      `<input class="pmr-in pmr-ask-date${TS.askCustom ? "" : " pmr-hide"}" type="date" aria-label="Chọn ngày" value="${esc(TS.askPick)}"></div>` +
      '<textarea class="pmr-ta pmr-ask-reason" placeholder="Lý do (người giao sẽ thấy)" aria-label="Lý do"></textarea><div class="pmr-err-t pmr-hide" role="alert"></div>' +
      `<div class="pmr-acts">${Bs("Huỷ", "ask-cancel")}${Bs("Gửi đề xuất", "ask-send", "pmr-pri")}</div></div>`;
  }
  if (mine) {
    h += `<div class="pmr-sent" role="status">${ic("cal", "pmr-s")}<span>Đã xin dời sang <b>${esc(dayLabel(mine.new_end || mine.proposed_end))}</b> · đang chờ ${esc(giverName(d))} duyệt. Hạn cũ vẫn giữ cho tới khi được đồng ý.</span>${L("Rút lại", "ask-withdraw", "", "pmr-ml")}</div>`;
  }
  if (other && (d.isGiver || d.canManage)) {
    const nm = other.from_name || other.requested_by_name || nameOf(other.requested_by || other.from_user), ne = other.new_end || other.proposed_end, why = other.reason || other.message;
    h += `<div class="pmr-alert" role="status">${ic("cal")}<div><b>${esc(nm)} xin dời hạn</b> sang <b>${esc(dayLabel(ne))}</b>${why ? ` — “${esc(why)}”` : ""}</div><div class="pmr-alert-act">${Bs("Giữ hạn cũ", "dl-keep")}${B("Đồng ý " + esc(shortDate(ne)), "dl-accept", "pmr-sm pmr-wash")}</div></div>`;
  }
  sec.innerHTML = h;
}
function setTaskState(st) {
  if (!TS.d) return;
  TS.d.t.workflow_state = st;
  const sb = $S(".pmr-statusbar"), hint = $S(".pmr-hint");
  if (sb) sb.outerHTML = statusBarHtml(TS.d);
  if (hint && isClosed(st) && hint.closest(".pmr-sh-h")) hint.parentNode.removeChild(hint);
}
function keepReason(fn) { const r = $S(".pmr-ask-reason"), v = r ? r.value : ""; fn(); const r2 = $S(".pmr-ask-reason"); if (r2) r2.value = v; }
function onTaskClick(a, b) {
  const d = TS.d;
  if (a === "close") return sheetClose();
  if (!d) return;
  const t = d.t, name = t.name;
  switch (a) {
    case "copy": {
      const url = root.location.origin + root.location.pathname + "#task/" + encodeURIComponent(name), cb = root.navigator && root.navigator.clipboard;
      if (cb && cb.writeText) cb.writeText(url).then(() => toast("Đã sao chép liên kết"), () => toast(url)); else toast(url);
      return;
    }
    case "chat": if (cfg.openChat && d.giver) safe(cfg.openChat, d.giver.user); return;
    case "project": sheetClose(); return openProject(t.project);
    case "state": {
      const s = ga(b, "s"), cur = t.workflow_state;
      if (curBucket(cur) === s) return;
      const opts = { subject: t.subject, prevState: cur, apply: setTaskState, revert: setTaskState, button: b, reviewRequired: d.review, isGiver: d.isGiver || d.canManage,
        onDone: r => { if (r.withdrew_request) { d.pdr = null; paintDue(); } } };
      if (s === "Done" || (s === "Review" && reviewVariant(d))) { opts.predict = s; markDone(name, opts); } else setState(name, s, cur, opts);
      return;
    }
    case "tab":
      TS.tab = ga(b, "tab");
      $$S(".pmr-stabs [data-act=tab]").forEach(x => { x.classList.toggle("pmr-on", x === b); x.setAttribute("aria-selected", x === b); });
      return loadTab(TS.tab);
    case "ask-open": TS.askOpen = !TS.askOpen; paintDue(); if (TS.askOpen) focusFirst(S.el, ".pmr-ask-reason"); return;
    case "ask-cancel": TS.askOpen = TS.askCustom = false; return paintDue();
    case "ask-pick": TS.askPick = ga(b, "d"); TS.askCustom = false; return keepReason(paintDue);
    case "ask-custom": TS.askCustom = true; keepReason(paintDue); return focusFirst(S.el, ".pmr-ask-date");
    case "ask-send": return sendDeadline(b);
    case "ask-withdraw": {
      const m = myPdr(d);
      return withdrawDl(b, m && (m.request || m.name), () => { d.pdr = null; TS.askOpen = false; paintDue(); changed({ task: name }); });
    }
    case "dl-keep": case "dl-accept": {
      const acc = a === "dl-accept" ? 1 : 0, p = d.pdr;
      return answerDl(b, p.request || p.name, acc, () => {
        if (acc) t.exp_end_date = ymd10(p.new_end || p.proposed_end);
        d.pdr = null; paintDue();
        toast(acc ? "Đã đổi hạn sang " + dayLabel(t.exp_end_date) : "Đã giữ hạn cũ và báo lại người xin");
        changed({ task: name });
      });
    }
    case "due-edit": TS.dueEdit = !TS.dueEdit; paintDue(); return focusFirst(S.el, ".pmr-due-d");
    case "due-cancel": TS.dueEdit = false; return paintDue();
    case "due-save": {
      const nd = ($S(".pmr-due-d") || {}).value, nt = ($S(".pmr-due-t") || {}).value, args = { name, exp_end_date: nd };
      if (!nd) return bad("Chọn ngày hạn");
      if (nt) args.pm_end_time = nt + ":00";
      busy(b, call("tasks.update", args)).then(() => {
        t.exp_end_date = nd; if (nt) t.pm_end_time = nt + ":00";
        TS.dueEdit = false; paintDue(); toast("Đã đổi hạn sang " + fullDue(nd, nt)); changed({ task: name });
      }, e => errToast(e, "Chưa đổi được hạn"));
      return;
    }
    case "add-assignee":
      pickPeople(b.parentNode, u => call("tasks.assign", { name, users: JSON.stringify([u]) }).then(() => {
        d.asg.push(u); toast("Đã giao thêm cho " + nameOf(u)); paintTask(); changed({ task: name });
      }, e => errToast(e, "Chưa giao được")), { exclude: d.asg });
      return;
    case "open-sub": return openTask(ga(b, "task"));
    case "add-person": return addPersonChild(b);
    case "sub-add": return addSubtask(b);
    case "sub-tick": return tickSubtask(b);
    case "sub-assign": return assignSubtask(b);
    case "nudge-sub": return nudge(b, name, ga(b, "u"));
    case "step-add": return addStep(b);
    case "timer": return toggleTimer(b);
    case "log-open": { const f = $S(".pmr-logform"); f.classList.toggle("pmr-on"); return focusFirst(f, ".pmr-in-h"); }
    case "log-save": return saveHours(name, $S(".pmr-logform"), b, () => tabTime(tp()));
    case "cm-send": return sendComment(b);
    case "cm-pin": return togglePin(b);
    case "cm-attach": return $S(".pmr-file").click();
    case "cm-unatt": TS.atts.splice(+ga(b, "i"), 1); return paintAtts();
  }
}
function sendDeadline(b) {
  const d = TS.d, t = d.t, errEl = $S(".pmr-rs .pmr-err-t"), reasonIn = $S(".pmr-ask-reason");
  const nd = TS.askCustom ? ($S(".pmr-ask-date") || {}).value : TS.askPick, reason = ((reasonIn && reasonIn.value) || "").trim();
  const err = !nd ? "Chọn hạn mới." : (nd === ymd10(t.exp_end_date) ? "Hạn mới đang trùng hạn cũ." : (!reason ? `Ghi lý do để ${giverName(d)} hiểu vì sao cần dời.` : ""));
  if (err) {
    if (errEl) { errEl.textContent = err; errEl.classList.remove("pmr-hide"); }
    if (!reason && reasonIn) reasonIn.focus();
    return;
  }
  busy(b, call("pm_inbox.request_deadline", { task: t.name, new_end: nd, reason })).then(r => {
    r = r || {};
    d.pdr = { request: r.request || r.name, new_end: nd, old_end: t.exp_end_date, reason, requested_by: cfg.user, status: "Pending" };
    TS.askOpen = TS.askCustom = false; TS.askPick = null;
    paintDue();
    toast(`Đã gửi ${giverName(d)} đề xuất dời hạn sang ${dayLabel(nd)}`);
    changed({ task: t.name });
  }, e => errToast(e, "Chưa gửi được đề xuất"));
}
function onTaskChange(a, el) {
  if (a === "cm-file") return uploadFiles(el);
  if (a !== "step-tick") return;
  const want = el.checked, lab = el.closest(".pmr-ck"), name = TS.d.t.name;
  if (lab) lab.classList.toggle("pmr-done", want);
  el.disabled = true;
  call("checklist.set_item", { task: name, row_name: ga(el, "row"), is_done: want ? 1 : 0 }).then(sum => {
    el.disabled = false;
    if (sum && sum.rows) { TS.chk = sum; paintStepsCount(); }
    changed({ task: name });
  }, e => {
    el.disabled = false; el.checked = !want;
    if (lab) lab.classList.toggle("pmr-done", !want);
    errToast(e, "Chưa lưu được bước");
  });
}

/* -- các tab trong ngăn kéo chi tiết -- */
const tp = () => $S(".pmr-tp");
const smallEmpty = msg => `<div class="pmr-empty pmr-empty-sm">${msg}</div>`;
function loadTab(tab) {
  stopTick();
  const p = tp();
  if (!p) return;
  if (tab === "people") tabPeople(p);
  else if (tab === "subs") tabSubs(p);
  else if (tab === "steps") tabSteps(p);
  else if (tab === "time") { p.innerHTML = skel(3); tabTime(p); }
  else tabHis(p);
}
function tabPeople(p) {
  const d = TS.d, prog = {}, mgr = d.isGiver || d.canManage;
  arr(Array.isArray(d.cp) ? d.cp : d.cp && d.cp.people).forEach(x => { if (x && x.task) prog[x.task] = x; });
  p.innerHTML = `<div class="pmr-sub-list">${d.subs.map(s => {
    const u = arr(s._assign)[0], pr = prog[s.name] || {}, done = s.workflow_state === "Done", unopened = pr.opened === false || pr.opened === 0;
    const last = done ? (pr.done_on ? "xong " + shortDate(pr.done_on) : "đã xong") : (unopened ? "chưa mở" : (pr.steps ? pr.steps + " bước" : (s.exp_end_date ? dueInfo(s.exp_end_date, s.pm_end_time, s.workflow_state).text : "")));
    const warn = !done && (unopened || dueInfo(s.exp_end_date, null, s.workflow_state).late);
    return `<div class="pmr-prow"><button type="button" class="pmr-nm pmr-nm-b" data-act="open-sub"${dattr("task", s.name)}>${u ? av(u) + esc(nameOf(u)) : esc(s.subject)}</button>${pill(s.workflow_state)}` +
      `<span class="pmr-last${warn ? " pmr-warn" : ""}">${esc(last)}</span><span>${warn && mgr && u ? L("Nhắc", "nudge-sub", dattr("u", u)) : ""}</span></div>`;
  }).join("")}${isClosed(d.t.workflow_state) ? "" : `<div class="pmr-pick-wrap pmr-pad">${L("+ Thêm người", "add-person")}</div>`}</div>`;
}
/* Việc con đặt tên riêng (không phải "Mỗi người một việc"): danh sách + nút tròn Xong + thêm nhanh.
   Khôi phục tính năng của /pm cũ (G4.8), giới hạn 2 cấp. */
function tabSubs(p) {
  const d = TS.d, closed = isClosed(d.t.workflow_state);
  const rows = d.subs.map(s => {
    const done = s.workflow_state === "Done", us = arr(s._assign), u = us[0], di = s.exp_end_date ? dueInfo(s.exp_end_date, s.pm_end_time, s.workflow_state) : null;
    return `<div class="pmr-srow${done ? " pmr-done" : ""}"><button type="button" class="pmr-cb" data-act="sub-tick"${dattr("task", s.name)} aria-pressed="${done}" aria-label="${done ? "Bỏ đánh dấu xong" : "Đánh dấu xong"}: ${esc(s.subject)}"></button>` +
      `<button type="button" class="pmr-tname" data-act="open-sub"${dattr("task", s.name)}>${esc(s.subject || s.name)}</button>` +
      `<span class="pmr-srow-due${di && di.late ? " pmr-warn" : ""}">${di ? esc(di.text) : ""}</span>` +
      `<span class="pmr-srow-who">${closed && !u ? "" : `<button type="button" class="pmr-srow-asg" data-act="sub-assign"${dattr("task", s.name)} aria-label="${u ? "Giao thêm người cho việc con (đang giao: " + esc(us.map(nameOf).join(", ")) + ")" : "Giao việc con cho…"}" title="${u ? esc(us.map(nameOf).join(", ")) + " · bấm để giao thêm người" : "Giao cho…"}">${u ? stack(us, 3) : '<span class="pmr-srow-noone"></span>'}</button>`}</span></div>`;
  }).join("");
  p.innerHTML = `<div class="pmr-sub-list">${rows || (closed ? smallEmpty("Không có việc con.") : "")}</div>` + (closed ? "" :
    `<div class="pmr-row pmr-sub-add"><input class="pmr-in pmr-sub-in" aria-label="Việc con mới" placeholder="Thêm việc con, Enter để lưu">${Bs("Thêm việc con", "sub-add")}</div>` +
    (rows ? "" : '<p class="pmr-muted pmr-sub-hint">Chia việc lớn thành các việc nhỏ có người nhận và hạn riêng. Bấm vào việc con để giao người, đặt hạn.</p>'));
}
/* Bấm vòng người nhận của việc con -> chọn người, giao ngay (tasks.assign), không phải mở việc con. */
function assignSubtask(b) {
  const name = ga(b, "task"), s = (TS.d.subs || []).find(x => x.name === name), parent = TS.d.t.name;
  if (!s) return;
  pickPeople(b.parentNode, u => call("tasks.assign", { name, users: JSON.stringify([u]) }).then(() => {
    toast(`Đã giao “${s.subject}” cho ${nameOf(u)}`);
    changed({ task: name });
    openTask(parent, { tab: "subs" });
  }, e => errToast(e, "Chưa giao được")), { exclude: arr(s._assign) });
}
function addSubtask(b) {
  const t = TS.d.t, inp = $S(".pmr-sub-in"), subject = ((inp && inp.value) || "").trim();
  if (!subject) return inp && inp.focus();
  busy(b, call("tasks.create", { project: t.project || "", subject, parent_task: t.name, priority: t.priority || null })).then(() => {
    toast(`Đã thêm việc con “${subject}”`);
    changed({ task: t.name });
    openTask(t.name, { tab: "subs" }).then(() => focusFirst(S.el, ".pmr-sub-in"));
  }, e => errToast(e, "Chưa thêm được việc con"));
}
function tickSubtask(b) {
  const name = ga(b, "task"), s = TS.d.subs.find(x => x.name === name), parent = TS.d.t.name;
  if (!s) return;
  const prev = s.workflow_state, row = b.closest(".pmr-srow");
  const apply = st => { s.workflow_state = st; b.setAttribute("aria-pressed", String(st === "Done")); if (row) row.classList.toggle("pmr-done", st === "Done"); };
  const refresh = () => { if (TS.d && TS.d.t.name === parent) openTask(parent, { tab: "subs" }); };
  if (prev === "Done") return setState(name, "To Do", prev, { subject: s.subject, button: b, apply, revert: apply }).then(refresh);
  return markDone(name, { subject: s.subject, prevState: prev, button: b, apply, revert: apply, onDone: refresh });
}
function addPersonChild(b) {
  const t = TS.d.t, have = [];
  TS.d.subs.forEach(s => have.push(...arr(s._assign)));
  pickPeople(b.parentNode, u => call("tasks.create", { project: t.project || "", subject: `${String(t.subject || "").slice(0, 120)} — ${nameOf(u)}`, parent_task: t.name,
    priority: t.priority, exp_end_date: t.exp_end_date, pm_end_time: t.pm_end_time, assignees: JSON.stringify([u]) }).then(() => {
    toast(`Đã thêm ${nameOf(u)} vào việc chung`);
    changed({ task: t.name });
    openTask(t.name, { tab: "people" });
  }, e => errToast(e, "Chưa thêm được người")), { exclude: have });
}
function paintStepsCount() {
  const ck = TS.chk, tb = $S(".pmr-stabs [data-tab=steps]");
  if (tb && ck) tb.textContent = "Các bước" + (ck.total ? ` ${ck.done}/${ck.total}` : "");
}
function tabSteps(p) {
  const rows = (TS.chk && TS.chk.rows) || [], terminal = isClosed(TS.d.t.workflow_state);
  p.innerHTML = (rows.length ? rows.map(r => `<label class="pmr-ck${r.is_done ? " pmr-done" : ""}"><input type="checkbox" data-act="step-tick"${dattr("row", r.name)}${r.is_done ? " checked" : ""}${terminal ? " disabled" : ""}><span>${esc(r.item_label)}</span>${r.is_required ? '<em class="pmr-tag">Bắt buộc</em>' : ""}</label>`).join("")
    : smallEmpty("Chưa có bước nào. Chia việc thành vài bước để người nhận biết cần làm gì và bạn theo dõi được tiến độ.")) +
    (terminal ? "" : `<div class="pmr-row pmr-step-add"><input class="pmr-in pmr-step-in" aria-label="Bước mới" placeholder="Thêm bước, Enter để lưu">${Bs("Thêm bước", "step-add")}</div>`);
}
function addStep(b) {
  const inp = $S(".pmr-step-in"), title = ((inp && inp.value) || "").trim();
  if (!title) return inp && inp.focus();
  busy(b, call("checklist.add_item", { task: TS.d.t.name, title })).then(sum => {
    if (sum && sum.rows) TS.chk = sum;
    paintStepsCount(); tabSteps(tp()); focusFirst(S.el, ".pmr-step-in");
  }, e => errToast(e, "Chưa thêm được bước"));
}
function fmtClock(s) { s = Math.max(0, Math.floor(s)); return `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s % 3600 / 60))}:${pad(s % 60)}`; }
function tabTime(p) {
  const name = TS.d.t.name, token = TS.token;
  Promise.all([call("timesheet.list", { task: name }), call("timer.get_active", {}).then(null, () => ({ active: false }))]).then(rs => {
    if (TS.token !== token || TS.tab !== "time") return;
    const ts = rs[0] || {}, tm = rs[1] || {}, rows = ts.rows || [], mine = tm.active && tm.task === name, other = tm.active && !mine, terminal = isClosed(TS.d.t.workflow_state);
    TS.timer = { mine, base: +tm.elapsed_seconds || 0, at: Date.now() };
    const tb = $S(".pmr-stabs [data-tab=time]");
    if (tb) tb.textContent = `Thời gian ${hoursFmt(ts.total_hours)} giờ`;
    p.innerHTML = `<div class="pmr-logsum"><button type="button" class="pmr-timer${mine ? " pmr-run" : ""}" data-act="timer"${other || (terminal && !mine) ? " disabled" : ""}><span class="pmr-dot"></span><span class="pmr-timer-t">` +
      (mine ? `Đang bấm giờ · ${fmtClock(TS.timer.base)} · Dừng` : (other ? "Đang bấm giờ việc khác" : "Bắt đầu bấm giờ")) + "</span></button>" +
      `<span>Đã ghi <b>${hoursFmt(ts.total_hours)} giờ</b> cho việc này${ts.subtask_hours ? ` · việc con ${hoursFmt(ts.subtask_hours)} giờ` : ""}</span>${L("+ Ghi giờ", "log-open", "", "pmr-ml")}</div>` +
      `<div class="pmr-logform">${logFields('placeholder="1,5"')}${Bs("Lưu", "log-save", "pmr-pri")}</div>` +
      (rows.length ? `<div class="pmr-logs">${rows.map(r => `<div class="pmr-lg"><span class="pmr-num">${esc(shortDate(r.from_time))}</span><span class="pmr-muted">${esc(nameOf(r.owner))}</span><span>${esc(r.description || "")}</span><span class="pmr-h pmr-num">${hoursFmt(r.hours)}</span></div>`).join("")}</div>`
        : smallEmpty("Chưa ghi giờ nào. Bấm giờ khi bắt đầu làm, hoặc ghi tay số giờ đã làm.")) +
      '<div class="pmr-hint">Tổng hợp giờ của mọi việc xem ở mục <b>Timesheet</b>. Giờ từ Lịch làm việc (khối đã xác nhận) cũng tự vào đây.</div>';
    if (mine && tm.status !== "Paused") {
      TICK = setInterval(() => {
        const el = $S(".pmr-timer-t");
        if (!el || !TS.timer) return stopTick();
        el.textContent = `Đang bấm giờ · ${fmtClock(TS.timer.base + (Date.now() - TS.timer.at) / 1000)} · Dừng`;
      }, 1000);
    }
  }, e => { if (TS.token === token) p.innerHTML = errBox("Không tải được giờ đã ghi.", e); });
}
function toggleTimer(b) {
  const name = TS.d.t.name, mine = TS.timer && TS.timer.mine;
  busy(b, mine ? call("timer.stop", { description: "" }) : call("timer.start", { task: name })).then(r => {
    if (mine) toast(`Đã dừng và ghi ${hoursFmt(r && r.hours)} giờ`);
    emit("pmr:timer", { active: !mine, task: name });
    changed({ task: name });
    if (TS.tab === "time") tabTime(tp());
  }, e => errToast(e, mine ? "Chưa dừng được" : "Chưa bấm giờ được"));
}
const cmHtml = (c, pending) => {
  const pin = !pending && c.name && TS.canPin ? `<button type="button" class="pmr-cm-pin" data-act="cm-pin"${dattr("cm", c.name)} aria-pressed="${!!c.pinned}" aria-label="${c.pinned ? "Bỏ ghim" : "Ghim bình luận"}" title="${c.pinned ? "Bỏ ghim" : "Ghim lên đầu"}">${ic("pin", "pmr-s")}</button>` : "";
  return `<div class="pmr-cm${pending ? " pmr-pending" : ""}${c.pinned ? " pmr-cm-pinned" : ""}">${av(c.owner)}<div class="pmr-cm-b"><div class="pmr-cm-hd"><b>${esc(nameOf(c.owner))}</b><time>${esc(pending ? "đang gửi…" : relTime(c.creation))}</time>${pin}</div><div class="pmr-cm-c">${sanitize(c.content)}</div></div></div>`;
};
/* Bình luận: phần "Đã ghim" (vàng nhạt) luôn ở đầu card, không cuộn theo; dưới là dòng trao đổi. */
function paintComments() {
  const rows = TS.cmRows || [], pins = rows.filter(c => c.pinned), rest = rows.filter(c => !c.pinned), pw = $S(".pmr-pins-w"), list = $S(".pmr-cms"), cnt = $S(".pmr-side-n");
  if (cnt) cnt.textContent = rows.length ? String(rows.length) : "";
  if (pw) pw.innerHTML = pins.length ? `<div class="pmr-pins"><div class="pmr-pins-h">${ic("pin", "pmr-s")}Đã ghim · ${pins.length}</div>${pins.map(c => cmHtml(c)).join("")}</div>` : "";
  if (list) list.innerHTML = rest.length ? rest.map(c => cmHtml(c)).join("") : (pins.length ? "" : smallEmpty("Chưa có bình luận. Ghi chú, hỏi lại, báo tiến độ hay gửi file ngay tại đây, mọi người trong việc đều thấy. Ghi chú quan trọng thì bấm ghim để luôn nằm trên cùng."));
  if (list) list.scrollTop = list.scrollHeight;
}
function togglePin(b) {
  const id = ga(b, "cm"), c = (TS.cmRows || []).find(x => x.name === id), name = TS.d.t.name, token = TS.token;
  if (!c) return;
  const want = !c.pinned;
  busy(b, call("comments.pin", { reference_doctype: "Task", reference_name: name, comment: id, pinned: want ? 1 : 0 })).then(r => {
    if (TS.token !== token) return;
    const on = arr(r && r.pinned);
    TS.cmRows.forEach(x => { x.pinned = on.indexOf(x.name) >= 0 ? 1 : 0; });
    paintComments();
    toast(want ? "Đã ghim bình luận lên đầu" : "Đã bỏ ghim");
  }, e => errToast(e, "Chưa ghim được"));
}
function loadComments() {
  const p = $S(".pmr-side-b");
  if (!p) return;
  p.innerHTML = skel(3);
  tabCmt(p);
}
function tabCmt(p) {
  const d = TS.d, name = d.t.name, token = TS.token;
  TS.atts = TS.atts || [];
  call("comments.list", { reference_doctype: "Task", reference_name: name }).then(r => {
    if (TS.token !== token || !p.isConnected) return;
    TS.cmRows = ((r && r.rows) || []).slice();
    TS.canPin = !!(r && r.can_pin);
    const ph = d.isAssignee && !d.isGiver && d.giver ? `Trả lời ${giverName(d)}…` : "Viết bình luận, ghi chú…";
    p.innerHTML = '<div class="pmr-pins-w"></div><div class="pmr-cms"></div>' +
      `<div class="pmr-compose"><textarea class="pmr-ta pmr-cm-in" aria-label="Bình luận" placeholder="${esc(ph)}"></textarea><div class="pmr-atts"></div><div class="pmr-row">` +
      `<button type="button" class="pmr-x" data-act="cm-attach" aria-label="Đính kèm file">${ic("clip", "pmr-s")}</button><input type="file" class="pmr-file pmr-hide" data-act="cm-file" multiple>` +
      `<span class="pmr-hint pmr-grow">Ctrl+Enter để gửi</span>${Bs("Gửi", "cm-send", "pmr-wash")}</div></div>`;
    paintComments();
    paintAtts();
  }, e => { if (TS.token === token) p.innerHTML = errBox("Không tải được bình luận.", e); });
}
function paintAtts() {
  const w = $S(".pmr-atts");
  if (w) w.innerHTML = (TS.atts || []).map((x, i) => `<span class="pmr-pc">${esc(x.name)}<button type="button" class="pmr-rm" data-act="cm-unatt" data-i="${i}" aria-label="Bỏ ${esc(x.name)}">${ic("x", "pmr-s")}</button></span>`).join("");
}
function uploadFiles(input) {
  const name = TS.d.t.name;
  Array.from(input.files || []).forEach(f => {
    if (f.size > 10 * 1024 * 1024) return bad(`File “${f.name}” lớn hơn 10MB`);
    const rd = new root.FileReader();
    rd.onload = () => call("comments.upload", { reference_doctype: "Task", reference_name: name, filename: f.name, dataurl: rd.result }).then(r => {
      TS.atts.push({ url: r.file_url, is_image: !!r.is_image, name: r.file_name || f.name }); paintAtts();
    }, e => errToast(e, "Chưa tải được file"));
    rd.readAsDataURL(f);
  });
  input.value = "";
}
function sendComment(b) {
  const inp = $S(".pmr-cm-in"), text = ((inp && inp.value) || "").trim(), atts = TS.atts || [], name = TS.d.t.name;
  if (!text && !atts.length) return inp && inp.focus();
  const content = buildComment(text, atts), list = $S(".pmr-cms"), em = list && $(".pmr-empty", list), tmp = D.createElement("div");
  if (em) em.parentNode.removeChild(em);
  tmp.innerHTML = cmHtml({ owner: cfg.user, content }, true);
  const node = tmp.firstChild;
  if (list) list.appendChild(node);
  inp.value = ""; TS.atts = []; paintAtts();
  busy(b, call("comments.add", { reference_doctype: "Task", reference_name: name, content })).then(res => {
    (TS.cmRows = TS.cmRows || []).push({ name: res && res.name, owner: cfg.user, content: (res && res.content) || content, creation: (res && res.creation) || new Date().toISOString(), pinned: 0 });
    paintComments();
    changed({ task: name });
  }, e => {
    if (node.parentNode) node.parentNode.removeChild(node);
    inp.value = text; TS.atts = atts; paintAtts();
    errToast(e, "Chưa gửi được bình luận");
  });
}
function tabHis(p) {   /* history: [{at, by, by_name, from, to}] mới nhất trước (test_contract_shapes.py) */
  const t = TS.d.t, rows = arr(TS.d.history).slice();
  if (t.creation) rows.push({ at: t.creation, by: t.owner, text: "tạo việc" });
  p.innerHTML = rows.length ? `<div class="pmr-his">${rows.map(r => {
    const by = r.by_name || nameOf(r.by), txt = r.text || (r.from ? `“${stateLabel(r.from)}” → ` : "→ ") + `“${stateLabel(r.to)}”`;
    return `<div class="pmr-his-r"><time class="pmr-num">${esc(relTime(r.at))}</time><span>${by ? `<b>${esc(by)}</b> ` : ""}${esc(txt)}</span></div>`;
  }).join("")}</div>` : smallEmpty("Chưa có lịch sử.");
}

/* == Giao việc (newTask) == */
const LAST_KEY = "pmr.lastAssign";
function loadLast() { try { return JSON.parse(root.localStorage.getItem(LAST_KEY) || "null"); } catch (e) { return null; } }
function saveLast(st) { try { root.localStorage.setItem(LAST_KEY, JSON.stringify({ assignees: st.assignees, project: st.project })); } catch (e) { } }
function quickDue(k) {
  const t = parseYmd(todayYmd());
  const toFri = (5 - t.getDay() + 7) % 7 || 7;   /* Cuối tuần = thứ Sáu tới; hôm nay là thứ Sáu thì sang thứ Sáu tuần sau */
  return ymdOf(k === "today" ? t : (k === "tomorrow" ? addDays(t, 1) : addDays(t, toFri)));
}
const FREQ = [["Daily", "Hằng ngày"], ["Weekly", "Hằng tuần"], ["Biweekly", "2 tuần một lần"], ["Monthly", "Hằng tháng"]];
function newTask(o) {
  o = o || {};
  const sh = sheetOpen("new", "Giao việc mới", o.onClose);
  NT = { o, subject: o.subject || "", assignees: (o.assignees || []).slice(), due: o.due || "", time: o.time || "", project: o.project || "", parent: o.parent || null,
    split: false, auto: false, review: false, rep: false, ask: o.requestMode === undefined ? true : !!o.requestMode, freq: "Monthly", mday: "", desc: "", steps: [], priority: "Medium", labels: [], disc: false, projects: null, labelsAll: null };
  paintNew();
  focusFirst(sh, ".pmr-title-in");
  call("projects.list", { page_length: 500 }).then(r => {
    if (!NT) return;
    NT.projects = ((r && r.rows) || []).filter(p => p.name === NT.project || ((!p.status || p.status === "Open") && (isPersonalShown() || !truthy(p.ec_personal_log))));
    paintProjectSel();
  }, () => { if (NT) { NT.projects = []; paintProjectSel(); } });
  people().then(() => paintChips(), () => { /* picker hiện lỗi riêng */ });
  return sh;
}
const tog = (key, label, onT) => `<button type="button" class="pmr-tog" role="switch" aria-checked="${!!onT}" aria-label="${esc(label)}" data-act="tog" data-k="${key}"></button>`;
function splitHint() {
  const n = NT.assignees.length;
  return n > 1 ? `${n} người → ${n} việc con, theo dõi được ai đã xong. Tắt đi thì một người xong là cả việc xong.` : "Mỗi người nhận có một việc con riêng, theo dõi được ai đã xong. Cần từ 2 người nhận.";
}
const autoHint = () => NT.auto ? "Đang bật: người cuối cùng xong thì việc tự đóng, bạn chỉ nhận thông báo."
  : "Đang tắt: khi người cuối cùng xong, việc chuyển sang <b>Chờ duyệt</b> và báo bạn kiểm tra rồi đóng.";
/* "Cần người nhận đồng ý" chỉ có hiệu lực khi giao cho người khác và không phải việc con
   (bật mặc định, PO 16/10): không chọn ai hoặc chỉ chọn mình thì tạo việc thường. */
function effAsk(st) {
  const a = st.assignees || [];
  return !!st.ask && !st.parent && a.length > 0 && !(a.length === 1 && a[0] === cfg.user);
}
function submitLabel() {
  const n = NT.assignees.length;
  if (effAsk(NT)) return "Gửi yêu cầu cho " + (n > 1 ? n + " người" : nameOf(NT.assignees[0]));
  return n > 1 ? `Giao cho ${n} người` : (n === 1 ? "Giao việc" : "Tạo việc");
}
function nextRunText() {
  const due = parseYmd(NT.due);
  if (!due) return "chọn hạn để biết lần tới";
  const f = NT.freq;
  let nx;
  if (f === "Monthly") { const md = +NT.mday || due.getDate(), last = new Date(due.getFullYear(), due.getMonth() + 2, 0).getDate(); nx = new Date(due.getFullYear(), due.getMonth() + 1, Math.min(md, last)); }
  else nx = addDays(due, f === "Daily" ? 1 : (f === "Weekly" ? 7 : 14));
  return "lần tới: " + dayLabel(ymdOf(nx));
}
const opt = (key, title, desc, onO, more) => `<div class="pmr-opt${onO ? " pmr-open" : ""}" data-o="${key}"><div><b>${title}</b><span class="pmr-${key}-hint">${desc}</span></div>${tog(key, title, onO)}${more || ""}</div>`;
function paintNew() {
  const sh = S.el, st = NT, sub = !!st.parent, md = parseYmd(st.due);
  let h = `<div class="pmr-sh-h"><div class="pmr-sh-top"><span>${sub ? "Thêm việc con" : "Giao việc mới"}</span>${xBtn}</div>` +
    `<input class="pmr-title-in" aria-label="Tên việc" placeholder="Tên việc cần giao" value="${esc(st.subject)}"></div><div class="pmr-sh-b">` +
    `<div class="pmr-fl pmr-fl-first"><span class="pmr-lb">Người nhận</span><div class="pmr-pick-wrap"><span class="pmr-chips"></span>${L("+ Thêm người", "nt-add")}<div class="pmr-suggest"></div></div></div>` +
    fl("Hạn", `<div class="pmr-qd" role="group" aria-label="Hạn">${[["today", "Hôm nay"], ["tomorrow", "Ngày mai"], ["week", "Cuối tuần"]].map(x => { const v = quickDue(x[0]); return qdBtn("nt-due", "d", v, x[1], st.due === v); }).join("")}` +
      `<input class="pmr-in pmr-nt-date" type="date" aria-label="Ngày hạn" value="${esc(st.due)}"><input class="pmr-in pmr-nt-time" type="time" aria-label="Giờ hạn" value="${esc(st.time)}"></div>`) +
    fl("Dự án", `<div class="pmr-pj" data-ec-no-formkit><input type="hidden" class="pmr-nt-proj" value="${esc(st.project)}"><input class="pmr-in pmr-pj-in" aria-label="Dự án" autocomplete="off" placeholder="Đang tải dự án…"${sub ? " disabled" : ""}><div class="pmr-pj-list" role="listbox" hidden></div></div>`);
  if (!sub) h += opt("split", "Mỗi người một việc riêng", esc(splitHint()), st.split, `<div class="pmr-subopt"><div><b>Tự đóng khi mọi người xong</b><span class="pmr-auto-hint">${autoHint()}</span></div>${tog("auto", "Tự đóng khi mọi người xong", st.auto)}</div>`);
  h += opt("review", "Cần tôi kiểm tra trước khi xong", "Người nhận không bấm Xong thẳng được, mà bấm “Gửi kiểm tra”. Bạn kiểm tra rồi đóng hoặc trả lại.", st.review);
  if (!sub) {
    h += opt("rep", "Lặp lại", "Tự giao lại cho cùng nhóm, không phải tạo tay mỗi kỳ.", st.rep, `<div class="pmr-more"><select class="pmr-sel pmr-nt-freq" aria-label="Tần suất">${FREQ.map(f => `<option value="${f[0]}"${st.freq === f[0] ? " selected" : ""}>${f[1]}</option>`).join("")}</select>` +
      `<span class="pmr-mday-w">vào ngày <input class="pmr-in pmr-in-xs pmr-nt-mday" type="number" min="1" max="31" aria-label="Ngày trong tháng" placeholder="${md ? md.getDate() : 7}" value="${esc(st.mday)}"></span><span class="pmr-muted pmr-next"></span></div>`);
  }
  h += opt("ask", "Cần người nhận đồng ý", "Người nhận chấp nhận, từ chối hoặc đề xuất hạn khác trước khi bắt đầu.", st.ask) +
    `<button type="button" class="pmr-disc" data-act="disc" aria-expanded="${st.disc}">${ic("right", "pmr-s")}Thêm mô tả, các bước, ưu tiên, nhãn</button>` +
    `<div class="pmr-extra${st.disc ? " pmr-on" : ""}"><textarea class="pmr-ta pmr-nt-desc" aria-label="Mô tả" placeholder="Mô tả, link file mẫu…">${esc(st.desc)}</textarea>` +
    fl("Các bước", `<div class="pmr-steps"></div><div class="pmr-row"><input class="pmr-in pmr-nt-step" aria-label="Bước mới" placeholder="Thêm bước, Enter để thêm">${Bs("Thêm", "nt-step")}</div>`, "pmr-fl-top") +
    fl("Ưu tiên", `<div class="pmr-qd" role="group" aria-label="Ưu tiên">${["Low", "Medium", "High", "Urgent"].map(p => qdBtn("nt-pri", "p", p, priorityLabel(p), st.priority === p)).join("")}</div>`) +
    fl("Nhãn", `<div class="pmr-lbls">${L("+ Chọn nhãn", "nt-labels")}</div>`, "pmr-fl-top") +
    (sub ? "" : fl("Thuộc việc", `<div class="pmr-parent-w">${L("+ Chọn việc cha", "nt-parent")}</div>`)) +
    `</div></div><div class="pmr-sh-f"><span class="pmr-hint pmr-grow">Chỉ tên việc là bắt buộc · Ctrl+Enter để giao</span>${B("Huỷ", "close")}${B(esc(submitLabel()), "nt-submit", "pmr-pri")}</div>`;
  sh.innerHTML = h;
  paintChips(); paintSteps(); paintProjectSel(); paintRep();
  on(sh, onNewClick);
  on(sh, () => {}, "change");   /* thay handler change của ngăn kéo chi tiết; input của form xử lý ở bindNewInputs */
  sh.onkeydown = e => {
    if (e.key !== "Enter") return;
    if (e.ctrlKey || e.metaKey) { e.preventDefault(); const b = $("[data-act=nt-submit]", sh); if (b && !b.disabled) b.click(); }
    else if (e.target.classList.contains("pmr-nt-step")) { e.preventDefault(); addNtStep(); }
  };
  $(".pmr-title-in", sh).addEventListener("input", e => { NT.subject = e.target.value; });
}
function paintChips() {
  const w = NT && $S(".pmr-chips");
  if (!w) return;
  w.innerHTML = NT.assignees.map(u => `<span class="pmr-pc">${av(u)}${esc(nameOf(u))}<button type="button" class="pmr-rm" data-act="nt-rm"${dattr("u", u)} aria-label="Bỏ ${esc(nameOf(u))}">${ic("x", "pmr-s")}</button></span>`).join("");
  const last = loadLast(), sg = $S(".pmr-suggest"), sh = $S(".pmr-split-hint"), sb = $S("[data-act=nt-submit]");
  if (sg) sg.innerHTML = !NT.assignees.length && last && last.assignees && last.assignees.length
    ? L(`Gợi ý: nhóm lần giao trước (${esc(last.assignees.map(nameOf).slice(0, 3).join(", "))}${last.assignees.length > 3 ? "…" : ""})`, "nt-last", "", "pmr-link-muted") : "";
  if (sh) sh.textContent = splitHint();
  if (sb) sb.textContent = submitLabel();
}
function paintSteps() {
  const w = $S(".pmr-steps");
  if (w) w.innerHTML = NT.steps.map((s, i) => `<span class="pmr-pc">${esc(s)}<button type="button" class="pmr-rm" data-act="nt-step-rm" data-i="${i}" aria-label="Bỏ bước ${esc(s)}">${ic("x", "pmr-s")}</button></span>`).join("");
}
/* Dự án: ô gõ-để-tìm. Mặc định TRỐNG ("Không thuộc dự án") trừ khi mở từ trang dự án; danh sách đưa
   5 dự án bạn giao gần nhất lên đầu ("Gần đây"), còn lại xếp A-Z; gõ để lọc theo tên. Không tự đoán. */
const RECENT_PJ = "pmr.recentProjects";
function recentProjects() { try { return JSON.parse(root.localStorage.getItem(RECENT_PJ) || "[]") || []; } catch (e) { return []; } }
function pushRecentProject(p) { if (!p) return; try { root.localStorage.setItem(RECENT_PJ, JSON.stringify([p].concat(recentProjects().filter(x => x !== p)).slice(0, 5))); } catch (e) { } }
function pjName(p) { const r = (NT && NT.projects || []).find(x => x.name === p); return r ? (r.project_name || r.name) : (p || ""); }
function paintProjectSel() {
  const inp = $S(".pmr-pj-in"), hid = $S(".pmr-nt-proj"), rows = NT && NT.projects;
  if (!inp || !rows) return;
  hid.value = NT.project || "";
  inp.value = NT.project ? pjName(NT.project) : "";
  inp.placeholder = "Không thuộc dự án · gõ để tìm";
}
function paintProjectList(q) {
  const box = $S(".pmr-pj-list"), rows = (NT && NT.projects) || [];
  if (!box) return;
  const f = fold(q || ""), rec = recentProjects().filter(n => rows.some(r => r.name === n));
  const match = r => !f || fold((r.project_name || "") + " " + r.name).indexOf(f) >= 0;
  const recent = f ? [] : rec.map(n => rows.find(r => r.name === n));
  const rest = rows.filter(r => match(r) && recent.indexOf(r) < 0).sort((a, b) => fold(a.project_name || a.name).localeCompare(fold(b.project_name || b.name)));
  const item = r => `<button type="button" class="pmr-pj-opt${r.name === NT.project ? " pmr-on" : ""}" role="option" data-act="nt-pj" data-p="${esc(r.name)}">${esc(r.project_name || r.name)}</button>`;
  box.innerHTML = `<button type="button" class="pmr-pj-opt pmr-pj-none" role="option" data-act="nt-pj" data-p="">Không thuộc dự án</button>` +
    (recent.length ? `<div class="pmr-pj-g">Gần đây</div>` + recent.map(item).join("") + `<div class="pmr-pj-g">Tất cả dự án</div>` : "") +
    (rest.length ? rest.map(item).join("") : `<div class="pmr-pj-empty">Không có dự án khớp “${esc(q)}”</div>`);
  box.hidden = false;
}
function choseProject(p) {
  NT.project = p || "";
  const hid = $S(".pmr-nt-proj"); if (hid) hid.value = NT.project;
  const box = $S(".pmr-pj-list"); if (box) box.hidden = true;
  paintProjectSel();
  const pw = $S(".pmr-parent-w"); if (pw) pw.innerHTML = L("+ Chọn việc cha", "nt-parent");
}
function paintRep() {
  const mw = NT && $S(".pmr-mday-w"), nx = $S(".pmr-next");
  if (mw) mw.classList.toggle("pmr-hide", NT.freq !== "Monthly");
  if (nx && NT) nx.textContent = "· " + nextRunText();
}
function addNtStep() {
  const i = $S(".pmr-nt-step"), v = ((i && i.value) || "").trim();
  if (!v) return;
  NT.steps.push(v); i.value = ""; paintSteps(); i.focus();
}
function setDue(v) {
  NT.due = v || "";
  $$S("[data-act=nt-due]").forEach(x => { const onB = ga(x, "d") === NT.due; x.classList.toggle("pmr-on", onB); x.setAttribute("aria-pressed", onB); });
  const di = $S(".pmr-nt-date");
  if (di && di.value !== NT.due) di.value = NT.due;
  paintRep();
}
function setTog(k, v) {
  NT[k] = v;
  const b = $S(`[data-act=tog][data-k=${k}]`), o2 = b && b.closest(".pmr-opt");
  if (b) b.setAttribute("aria-checked", v);
  if (k === "auto") { const ah = $S(".pmr-auto-hint"); if (ah) ah.innerHTML = autoHint(); }
  else if (o2) o2.classList.toggle("pmr-open", v);
}
function onNewClick(a, b) {
  if (!NT) return;
  switch (a) {
    case "close": return sheetClose();
    case "nt-add": pickPeople(b.parentNode, u => { if (NT.assignees.indexOf(u) < 0) NT.assignees.push(u); paintChips(); }, { exclude: () => NT.assignees, keepOpen: true }); return;
    case "nt-rm": { const u = ga(b, "u"), pk = $S(".pmr-picker"); NT.assignees = NT.assignees.filter(x => x !== u); if (pk) pk.repaint(); return paintChips(); }
    case "nt-last": {
      const l = loadLast();
      if (l) { NT.assignees = (l.assignees || []).slice(); if (!NT.project && l.project) { NT.project = l.project; paintProjectSel(); } }
      return paintChips();
    }
    case "nt-due": return setDue(ga(b, "d") === NT.due ? "" : ga(b, "d"));
    case "nt-pj": return choseProject(ga(b, "p"));
    case "tog": {
      const k = ga(b, "k");
      setTog(k, !NT[k]);
      if (k === "split" && !NT.split) setTog("auto", false);
      paintChips(); paintRep();
      return;
    }
    case "disc": NT.disc = !NT.disc; b.setAttribute("aria-expanded", NT.disc); $S(".pmr-extra").classList.toggle("pmr-on", NT.disc); return;
    case "nt-step": return addNtStep();
    case "nt-step-rm": NT.steps.splice(+ga(b, "i"), 1); return paintSteps();
    case "nt-pri":
      NT.priority = ga(b, "p");
      $$S("[data-act=nt-pri]").forEach(x => { x.classList.toggle("pmr-on", x === b); x.setAttribute("aria-pressed", x === b); });
      return;
    case "nt-labels": return openLabels(b.parentNode);
    case "nt-lbl": {
      const ln = ga(b, "l"), ix = NT.labels.indexOf(ln);
      if (ix < 0) NT.labels.push(ln); else NT.labels.splice(ix, 1);
      b.setAttribute("aria-pressed", ix < 0); b.classList.toggle("pmr-on", ix < 0);
      return;
    }
    case "nt-parent": return openParents(b.parentNode);
    case "nt-submit": return submitNew(b);
  }
}
function openLabels(w) {
  const paint = () => {
    w.innerHTML = NT.labelsAll.length ? NT.labelsAll.map(l => { const onL = NT.labels.indexOf(l.name) >= 0; return `<button type="button" class="pmr-chip${onL ? " pmr-on" : ""}" data-act="nt-lbl"${dattr("l", l.name)} aria-pressed="${onL}">${esc(l.label_name || l.name)}</button>`; }).join(" ")
      : muted("Chưa có nhãn nào. Trưởng nhóm tạo nhãn trong /pm.");
  };
  if (NT.labelsAll) return paint();
  w.innerHTML = muted("Đang tải nhãn…");
  call("labels.list_labels", {}).then(r => { if (NT) { NT.labelsAll = (r && r.rows) || []; paint(); } }, e => { w.innerHTML = muted(esc(errOf(e))); });
}
function openParents(w) {
  const proj = ($S(".pmr-nt-proj") || {}).value || "";
  w.innerHTML = muted("Đang tải việc…");
  call("tasks.list", { project: proj || null, page_length: 200 }).then(r => {
    if (!NT) return;
    const rows = ((r && r.rows) || []).filter(t => !t.parent_task && !isClosed(t.workflow_state) && (t.project || "") === proj);
    w.innerHTML = `<select class="pmr-sel pmr-nt-parent" aria-label="Việc cha"><option value="">Không thuộc việc nào</option>${rows.map(t => `<option value="${esc(t.name)}">${esc(t.subject || t.name)}</option>`).join("")}</select>`;
  }, e => { w.innerHTML = muted(esc(errOf(e))); });
}
/* Thuần: trạng thái form -> kế hoạch gọi server. Lộ ra PMR._pure.buildCreatePlan cho test/integrator. */
function buildCreatePlan(st) {
  const n = st.assignees.length, end = st.due || null, tm = st.time ? st.time + ":00" : null;
  /* PO 16/10: "Cần người nhận đồng ý" bật mặc định -> chỉ áp khi giao cho NGƯỜI KHÁC (bỏ qua khi chưa
     có người nhận hoặc chỉ giao cho chính mình); nhiều người + cần đồng ý = mỗi người nhận phần riêng
     (backend chỉ hỗ trợ đồng ý theo từng người). */
  const ask = effAsk(st);
  const split = n > 1 && !st.parent && (!!st.split || ask);
  const lbl = st.labels.length ? JSON.stringify(st.labels) : null, plan = { method: null, args: null, followups: [] };
  if (ask) {
    const a = { subject: st.subject, project: st.project || "", parent_task: st.parent || null, description: st.desc || null, priority: st.priority || null,
      proposed_end: end ? `${end} ${tm || "18:00:00"}` : null, labels: lbl, review_required: st.review ? 1 : 0 };
    if (n > 1) Object.assign(a, { recipients: JSON.stringify(st.assignees), split_per_assignee: split ? 1 : null, auto_close: split ? (st.auto ? 1 : 0) : null });
    else a.recipient = st.assignees[0];
    plan.method = "assignment.create_with_task";
    plan.args = a;
  } else {
    plan.method = "tasks.create";
    plan.args = { project: st.project || "", subject: st.subject, parent_task: st.parent || null, priority: st.priority || null, exp_end_date: end, pm_end_time: end ? tm : null,
      description: st.desc || null, assignees: n ? JSON.stringify(st.assignees) : null, split_per_assignee: split ? 1 : null, auto_close: split ? (st.auto ? 1 : 0) : null, review_required: st.review ? 1 : 0 };
    if (lbl) plan.followups.push({ method: "labels.set_task_labels", args: { labels: lbl }, target: "task" });
  }
  st.steps.forEach(s => plan.followups.push({ method: "checklist.add_item", args: { title: s, is_required: 0 }, target: split ? "children" : "task" }));
  if (st.rep && !st.parent) {
    const due = parseYmd(st.due) || parseYmd(todayYmd()), ra = { frequency: st.freq, start_date: ymdOf(addDays(due, 1)), interval: 1 };
    if (st.freq === "Monthly") ra.monthly_day = +st.mday || due.getDate();
    else if (st.freq !== "Daily") ra.weekly_days = JSON.stringify([(due.getDay() + 6) % 7]);
    plan.followups.push({ method: "recurrence.create_from_task", args: ra, target: "task" });
  }
  return plan;
}
function submitNew(b) {
  const st = NT, sh = S.el, v = sel => ($(sel, sh) || {}).value;
  st.subject = (v(".pmr-title-in") || "").trim();
  st.project = v(".pmr-nt-proj") || st.project || "";
  st.desc = v(".pmr-nt-desc") || "";
  if (v(".pmr-nt-parent")) st.parent = v(".pmr-nt-parent");
  if (v(".pmr-nt-freq")) st.freq = v(".pmr-nt-freq");
  if (v(".pmr-nt-mday") != null) st.mday = v(".pmr-nt-mday");
  if (v(".pmr-nt-time") != null) st.time = v(".pmr-nt-time");
  const pend = (v(".pmr-nt-step") || "").trim();
  if (pend) { st.steps.push(pend); $(".pmr-nt-step", sh).value = ""; paintSteps(); }
  if (!st.subject) { bad("Nhập tên việc"); return focusFirst(sh, ".pmr-title-in"); }
  if (st.rep && !st.due) return bad("Việc lặp lại cần có hạn cho lần đầu");
  const plan = buildCreatePlan(st);
  busy(b, call(plan.method, plan.args).then(r => {
    r = r || {};
    const task = r.name || r.task, kids = r.children || [], warn = [];
    let chain = Promise.resolve();
    plan.followups.forEach(f => (f.target === "children" && kids.length ? kids : [task]).forEach(tn => {
      chain = chain.then(() => call(f.method, Object.assign({}, f.args, { task: tn })).then(null, e => { warn.push(errOf(e)); }));
    }));
    return chain.then(() => ({ r, task, warn }));
  })).then(res => {
    const n = st.assignees.length, cb = st.o.onCreated;
    const msg = effAsk(st) ? `Đã gửi yêu cầu “${st.subject}”` : (n ? `Đã giao “${st.subject}” cho ${n > 1 ? n + " người" : nameOf(st.assignees[0])}` : `Đã tạo việc “${st.subject}”`);
    saveLast(st); pushRecentProject(st.project);
    sheetClose();
    if (res.warn.length) bad(`${msg}. Một phần chưa lưu được: ${res.warn[0]}`);
    else toast(msg, { actions: res.task ? [{ label: "Mở", run: () => openTask(res.task) }] : [] });
    changed({ task: res.task, created: true });
    if (cb) safe(cb, res.r);
  }, e => errToast(e, "Chưa giao được"));
}
function bindNewInputs() {   /* các ô nhập của form giao việc (không có data-act) */
  D.addEventListener("click", e => {
    $$(".pmr-picker").forEach(pk => { const host = pk.parentNode; if (host && !host.contains(e.target)) host.removeChild(pk); });
  }, true);
  D.addEventListener("focusin", e => { if (NT && e.target.classList && e.target.classList.contains("pmr-pj-in")) { e.target.select(); paintProjectList(""); } });
  D.addEventListener("input", e => { if (NT && e.target.classList && e.target.classList.contains("pmr-pj-in")) paintProjectList(e.target.value); });
  D.addEventListener("click", e => { const box = NT && $S(".pmr-pj-list"); if (box && !box.hidden && !e.target.closest(".pmr-pj")) { box.hidden = true; paintProjectSel(); } }, true);
  D.addEventListener("change", e => {
    const t = e.target, cl = t.classList;
    if (!NT || !S.el || !S.el.contains(t)) return;
    if (cl.contains("pmr-nt-date")) setDue(t.value);
    else if (cl.contains("pmr-nt-time")) NT.time = t.value;
    else if (cl.contains("pmr-nt-proj")) { NT.project = t.value; const pw = $S(".pmr-parent-w"); if (pw) pw.innerHTML = L("+ Chọn việc cha", "nt-parent"); }
    else if (cl.contains("pmr-nt-freq")) { NT.freq = t.value; paintRep(); }
    else if (cl.contains("pmr-nt-mday")) { NT.mday = t.value; paintRep(); }
  });
}

/* == render.received — Được giao cho tôi == */
const taskBtn = (task, subject) => `<button type="button" class="pmr-t pmr-tname" data-act="open"${dattr("task", task)}>${esc(subject || task)}</button>`;
function renderReceived(c) {
  prep(c);
  const head = pageHead("Được giao cho tôi", `Việc cần bạn trả lời và các lần xin dời hạn. Toàn bộ việc của bạn vẫn ở ${L("Việc của tôi", "mywork")}.`);
  c.innerHTML = head + skel(5);
  on(c, a => { if (a === "mywork") nav("#mywork"); });
  return call("pm_inbox.received", {}).then(d => {
    d = d || {};
    const nr = d.needs_reply || [], un = d.unopened || [], my = d.my_deadline_requests || [];
    let h = head;
    emit("pmr:badge", { key: "received", count: d.badge || 0 });
    if (!nr.length && !un.length && !my.length) h += emptyBox("appr", "Không có gì cần bạn trả lời", `Việc mới giao cho bạn và các lần xin dời hạn sẽ hiện ở đây. Danh sách đầy đủ việc của bạn ở ${L("Việc của tôi", "mywork")}.`);
    if (nr.length) {
      h += sectionT("Cần bạn trả lời", nr.length) + `<div class="pmr-panel">${nr.map((r, i) => {
        const from = r.from_name || nameOf(r.from_user);
        return `<div class="pmr-req"${dattr("req", r.request)}><div><div class="pmr-from">${av(r.from_user, from)}<b>${esc(from)}</b> giao cho bạn${r.created ? " · " + esc(relTime(r.created)) : ""}</div>` +
          `<div class="pmr-rt">${esc(r.subject || r.task)}</div><div class="pmr-rm-t">${r.project_name ? esc(r.project_name) + " · " : ""}${r.proposed_end ? `đề xuất hạn <b>${esc(fullDue(r.proposed_end))}</b>` : "chưa có hạn"}</div>` +
          `${r.message ? `<div class="pmr-quote">“${esc(r.message)}”</div>` : ""}<div class="pmr-req-form"></div></div>` +
          `<div class="pmr-acts">${Bs("Từ chối", "rq-reject")}${Bs("Đề xuất hạn khác", "rq-propose")}${B("Nhận việc", "rq-accept", "pmr-sm " + (i ? "pmr-wash" : "pmr-pri"))}</div></div>`;
      }).join("")}</div>`;
    }
    if (un.length) {
      h += sectionT("Mới được giao, bạn chưa mở", un.length) + `<div class="pmr-panel">${un.map(r => {
        const di = dueInfo(r.exp_end_date, null, r.workflow_state), from = r.from_name || nameOf(r.from_user);
        return `<div class="pmr-rrow"><div>${taskBtn(r.task, r.subject)}<div class="pmr-m">${av(r.from_user, from, "pmr-av-xs")} ${esc(from)} giao${r.project_name ? " · " + esc(r.project_name) : ""}</div></div>` +
          `${pill(r.workflow_state)}${dueSpan(di)}${L("Xin dời hạn", "ask", dattr("task", r.task))}</div>`;
      }).join("")}</div>`;
    }
    if (my.length) {
      h += sectionT("Xin dời hạn của bạn", my.length) + `<div class="pmr-panel">${my.map(r => {
        let badge, m, act = L("Mở", "open", dattr("task", r.task));
        if (r.status === "Rejected") {
          badge = '<span class="pmr-pend pmr-pend-no">Không được đồng ý · giữ hạn cũ</span>';
          m = r.answer ? `Người giao trả lời${r.answered_at ? " " + esc(relTime(r.answered_at)) : ""}: “${esc(r.answer)}”` : "Người giao giữ hạn cũ";
        } else if (r.status === "Accepted") {
          badge = `<span class="pmr-pend pmr-pend-ok">Đã đồng ý · hạn mới ${esc(dayLabel(r.new_end))}</span>`;
          m = r.answer ? `“${esc(r.answer)}”` : "Người giao đã đồng ý";
        } else {
          badge = `<span class="pmr-pend">${ic("cal", "pmr-s")}Đang chờ duyệt: ${esc(dayLabel(r.old_end))} → ${esc(dayLabel(r.new_end))}</span>`;
          m = "lý do: " + esc(r.reason || "—");
          act = L("Rút lại", "withdraw", dattr("req", r.request));
        }
        const di = dueInfo(r.status === "Accepted" ? r.new_end : r.old_end, null, null);
        return `<div class="pmr-rrow"><div>${taskBtn(r.task, r.subject)}<div class="pmr-m">${m}</div>${badge}</div><span></span>${dueSpan(di)}${act}</div>`;
      }).join("")}</div>`;
    }
    c.innerHTML = h;
    on(c, (a, b) => onReceived(c, a, b, nr));
  }, e => loadErr(c, e, () => renderReceived(c), head));
}
function onReceived(c, a, b, nr) {
  if (a === "mywork") return nav("#mywork");
  if (a === "open") return openTask(ga(b, "task"));
  if (a === "ask") return openTask(ga(b, "task"), { askDeadline: true });
  if (a === "withdraw") {
    return withdrawDl(b, ga(b, "req"), () => { changed({}); renderReceived(c); }, gone(b.closest(".pmr-rrow")));
  }
  const req = b.closest(".pmr-req");
  if (!req) return;
  const name = ga(req, "req"), form = $(".pmr-req-form", req), item = nr.filter(x => x.request === name)[0] || {}, from = item.from_name || nameOf(item.from_user) || "người giao";
  if (a === "rq-accept") {
    const restore = gone(req);
    busy(b, call("assignment.respond", { name, decision: "accept" })).then(() => {
      toast(`Đã nhận việc. ${from} được báo`, { actions: item.task ? [{ label: "Mở", run: () => openTask(item.task) }] : [] });
      changed({ task: item.task }); renderReceived(c);
    }, e => { restore(); errToast(e, "Chưa nhận được việc"); });
  } else if (a === "rq-reject" || a === "rq-propose") {
    const rej = a === "rq-reject", base = parseYmd(item.proposed_end) || parseYmd(todayYmd());
    form.innerHTML = `<div class="pmr-rs">${rej ? "" : `<div class="pmr-row"><span class="pmr-lb pmr-lb-w">Hạn đề xuất</span><input class="pmr-in pmr-rq-date" type="date" aria-label="Hạn đề xuất" value="${ymdOf(addDays(base, 2))}"><input class="pmr-in pmr-rq-time" type="time" aria-label="Giờ" value="18:00"></div>`}` +
      `<textarea class="pmr-ta pmr-rq-reason" aria-label="Lý do" placeholder="${rej ? "Lý do từ chối (bắt buộc, người giao sẽ thấy)" : "Lý do cần hạn khác (bắt buộc)"}"></textarea>` +
      `<div class="pmr-acts">${Bs("Huỷ", "rq-cancel")}${Bs(rej ? "Gửi từ chối" : "Gửi đề xuất", rej ? "rq-reject-send" : "rq-propose-send", "pmr-wash")}</div></div>`;
    focusFirst(form, rej ? ".pmr-rq-reason" : ".pmr-rq-date");
  } else if (a === "rq-cancel") form.innerHTML = "";
  else if (a === "rq-reject-send" || a === "rq-propose-send") {
    const rIn = $(".pmr-rq-reason", form), reason = rIn.value.trim(), args = { name, decision: a === "rq-reject-send" ? "reject" : "reschedule", reason };
    if (!reason) { bad("Ghi lý do để người giao hiểu"); return rIn.focus(); }
    if (args.decision === "reschedule") {
      const dd = $(".pmr-rq-date", form).value;
      if (!dd) return bad("Chọn hạn đề xuất");
      args.counter_end = `${dd} ${$(".pmr-rq-time", form).value || "18:00"}:00`;
    }
    busy(b, call("assignment.respond", args)).then(() => {
      toast(args.decision === "reject" ? `Đã từ chối và gửi lý do cho ${from}` : "Đã gửi đề xuất hạn " + dayLabel(args.counter_end));
      changed({ task: item.task }); renderReceived(c);
    }, e => errToast(e, "Chưa gửi được"));
  }
}

/* == render.given — Tôi đã giao == */
const OPEN_BATCH = {};
const isDoneP = p => p.state === "Done" || !!p.done_on;
function batchStats(b) {
  const people = b.people || [], total = b.total != null ? +b.total : people.length, dc = b.done_count != null ? +b.done_count : people.filter(isDoneP).length;
  const notDone = people.filter(p => !isDoneP(p));
  return { people, total, dc, notDone, lateP: notDone.filter(p => truthy(p.late)), ready: truthy(b.split) && !isClosed(b.workflow_state) && total > 0 && (b.workflow_state === "Review" || dc >= total) };
}
function givenSub(d, tab) {
  const b = d.batches || [];
  if (tab === "rep") return (d.rules || []).length + " lịch lặp lại";
  if (tab === "done") return b.length + " lần giao đã xong";
  let ready = 0, late = 0;
  b.forEach(x => { const s = batchStats(x); if (s.ready) ready++; late += s.lateP.length; });
  const parts = [b.length + " lần giao đang chạy"];
  if (ready) parts.push(ready + " việc chờ bạn đóng");
  if (late) parts.push(late + " người trễ hạn");
  if ((d.banner || []).length) parts.push(d.banner.length + " đề xuất dời hạn");
  return parts.join(" · ");
}
function personLast(p, b) {
  if (isDoneP(p)) {
    const due = ymd10(b.exp_end_date), don = ymd10(p.done_on);
    return { text: (don ? "xong " + shortDate(don) : "đã xong") + (due && don ? (don <= due ? " · đúng hạn" : " · trễ hạn") : ""), warn: false };
  }
  const parts = [], opened = !(p.opened === false || p.opened === 0);
  if (p.steps) parts.push(p.steps + " bước");
  if (!opened) parts.push("chưa mở việc");
  if (truthy(p.late)) { const ld = lateDays(b.exp_end_date); parts.push(ld ? `trễ ${ld} ngày` : "trễ hạn"); }
  return { text: parts.join(" · ") || "đã mở", warn: !opened || truthy(p.late) };
}
const pname = p => p.full_name || nameOf(p.user);
function batchHtml(b) {
  const s = batchStats(b), people = s.people, split = truthy(b.split), ws = b.workflow_state, closed = isClosed(ws), expandable = people.length > 1 || split;
  const open = expandable && (OPEN_BATCH[b.task] != null ? OPEN_BATCH[b.task] : (s.ready || s.lateP.length > 0)), meta = [];
  if (b.project_name) meta.push(`<span class="pmr-proj">${esc(b.project_name)}</span>`);
  if (b.recurrence) meta.push(`<span class="pmr-tag">${ic("repeat", "pmr-s")}${esc(b.recurrence.label || b.recurrence.name || "lặp lại")}</span>`);
  if (split) meta.push("<span>Mỗi người một việc</span>");
  else if (people.length > 1) meta.push(`<span>${people.length} người cùng làm · một người xong là xong</span>`);
  if (truthy(b.review_required)) meta.push("<span>Cần bạn kiểm tra</span>");
  const segs = people.map(p => `<i class="${isDoneP(p) ? "pmr-ok" : (truthy(p.late) ? "pmr-late" : (p.state === "In Progress" || p.state === "Review" ? "pmr-doing" : ""))}"></i>`).join("");
  const prog = split ? `<div class="pmr-prog"><span class="pmr-t pmr-num">${s.dc}/${s.total} người xong</span><div class="pmr-segbar" aria-hidden="true">${segs}</div></div>`
    : `<div class="pmr-solo">${people.length > 1 ? stack(people.map(p => p.user), 4) + `<span>${esc(people.map(p => pname(p).split(" ").pop()).join(", "))}</span>`
      : (people[0] ? av(people[0].user, people[0].full_name) + `<span>${esc(pname(people[0]))}</span>` : muted("Chưa có người nhận"))}</div>`;
  const di = dueInfo(b.exp_end_date, null, ws), taskAttr = dattr("task", b.task);
  const dueCol = s.ready ? pill("Review") + `<div class="pmr-muted pmr-xs">hạn ${esc(shortDate(b.exp_end_date))}</div>`
    : (closed ? pill(ws) : `${dueSpan(di)}${b.exp_end_date ? `<div class="pmr-muted pmr-xs">hạn ${esc(fullDue(b.exp_end_date))}</div>` : ""}`);
  let act;
  if (s.ready) act = Bs("Đóng việc", "close-batch", "pmr-wash");
  else if (split && s.lateP.length) act = Bs(`Nhắc ${s.notDone.length} người`, "nudge", "pmr-wash");
  else if (!split && !closed && ws === "Review") act = Bs("Trả lại", "return-solo") + Bs("Đóng việc", "close-solo", "pmr-wash");
  else if (split || closed) act = Bs("Mở", "open", "", taskAttr);
  else act = pill(ws);
  let h = `<div class="pmr-batch${open ? " pmr-open" : ""}"${taskAttr}><div class="pmr-bhead" data-act="toggle">` +
    (expandable ? `<button type="button" class="pmr-chev-b" data-act="toggle" aria-expanded="${open}" aria-label="Xem từng người">${ic("right", "pmr-chev")}</button>` : "<span></span>") +
    `<div class="pmr-minw"><button type="button" class="pmr-btitle" data-act="open"${taskAttr}>${esc(b.subject || b.task)}</button><div class="pmr-bmeta">${meta.join('<span class="pmr-dot-sep"></span>')}</div></div>` +
    `${prog}<div>${dueCol}</div><div class="pmr-bact">${act}</div></div>`;
  if (s.ready) {
    h += `<div class="pmr-ready">${ic("appr", "pmr-s")}<span>Cả ${s.total} người đã xong. Việc chuyển sang <b>Chờ duyệt</b> để bạn kiểm tra rồi đóng.</span>${Bs("Trả lại", "return-open")}</div>` +
      `<div class="pmr-retform pmr-hide"><div class="pmr-rs"><h4>Trả lại cho ai?</h4><div class="pmr-row">${people.map(p => `<label class="pmr-ck"><input type="checkbox" value="${esc(p.user)}"><span>${esc(pname(p))}</span></label>`).join("")}</div>` +
      `<textarea class="pmr-ta pmr-ret-note" aria-label="Lời nhắn" placeholder="Cần sửa gì (người nhận sẽ thấy)"></textarea><div class="pmr-acts">${Bs("Huỷ", "return-cancel")}${Bs("Trả lại", "return-send", "pmr-wash")}</div></div></div>`;
  }
  if (expandable) {
    h += `<div class="pmr-people">${people.map(p => {
      const l = personLast(p, b);
      const pa = isDoneP(p) || closed ? "<span></span>" : (l.warn ? L("Nhắc", "nudge-one", dattr("u", p.user)) : L("Mở", "open", dattr("task", p.task || b.task)));
      return `<div class="pmr-prow"><span class="pmr-nm">${av(p.user, pname(p))}${esc(pname(p))}</span>${pill(p.state)}<span class="pmr-last${l.warn ? " pmr-warn" : ""}">${esc(l.text)}</span>${pa}</div>`;
    }).join("")}</div>`;
  }
  return h + "</div>";
}
function rulesHtml(rules) {
  if (!rules.length) return emptyBox("repeat", "Chưa có việc lặp lại", "Bật <b>Lặp lại</b> khi giao việc để hệ thống tự giao lại cho cùng nhóm mỗi kỳ.");
  return thead(["Việc lặp lại", "Lịch", "Giao cho", "Lần tới", "Trạng thái", ""]) + rules.map(r => {
    const users = arr(r.assignees).map(x => typeof x === "string" ? x : x.user || x.email).filter(Boolean), active = r.status === "Active", cancelled = r.status === "Cancelled";
    return `<tr${dattr("rule", r.name)}><td class="pmr-strong">${esc(r.subject || r.name)}</td><td>${esc(r.schedule_label || "")}</td><td>${users.length ? stack(users) : muted("—")}</td>` +
      `<td class="pmr-num">${esc(dayLabel(r.next_run))}</td><td><span class="pmr-st ${active ? "pmr-s3" : "pmr-s0"}">${active ? "Đang chạy" : (cancelled ? "Đã huỷ" : "Tạm dừng")}</span></td>` +
      `<td>${cancelled ? "" : Bs(active ? "Tạm dừng" : "Chạy lại", active ? "rule-pause" : "rule-resume")}</td></tr>`;
  }).join("") + "</tbody></table>";
}
function renderGiven(c, tab) {
  prep(c);
  tab = tab === "rep" || tab === "done" ? tab : "run";
  const right = B(ic("plus", "pmr-s") + "Giao việc", "new", "pmr-pri"), again = () => renderGiven(c, tab);
  const h0 = pageHead("Tôi đã giao", "", right);
  c.innerHTML = h0 + skel(6);
  on(c, a => { if (a === "new") newTask({ onCreated: again }); });
  return call("pm_inbox.given", { tab }).then(d => {
    d = d || {};
    const banner = d.banner || [], batches = d.batches || [], rules = d.rules || [], counts = d.counts || {};
    let h = pageHead("Tôi đã giao", esc(givenSub(d, tab)), right) + banner.map(x => {
      const nm = x.from_name || nameOf(x.from_user);
      return `<div class="pmr-alert" role="status"${dattr("req", x.request)}>${ic("cal")}<div><b>${esc(nm)} đề xuất dời hạn</b> “${esc(x.subject || x.task)}” từ ${esc(dayLabel(x.old_end))} sang <b>${esc(dayLabel(x.new_end))}</b>${x.reason ? ` — “${esc(x.reason)}”` : ""}</div>` +
        `<div class="pmr-alert-act">${Bs("Giữ hạn cũ", "dl-keep")}${B("Đồng ý " + esc(shortDate(x.new_end)), "dl-accept", "pmr-sm pmr-wash")}</div></div>`;
    }).join("");
    h += `<div class="pmr-tabs" role="tablist">${[["run", "Đang chạy"], ["rep", "Lặp lại"], ["done", "Đã xong"]].map(x => {
      const n = x[0] === tab ? (tab === "rep" ? rules.length : batches.length) : counts[x[0]];
      return `<button type="button" role="tab"${onA(x[0] === tab, "selected")} data-act="gtab" data-tab="${x[0]}">${x[1]}${n != null ? ` <span class="pmr-cnt pmr-num">${n}</span>` : ""}</button>`;
    }).join("")}</div>`;
    if (tab === "rep") h += `<div class="pmr-panel">${rulesHtml(rules)}</div>`;
    else if (!batches.length) {
      h += '<div class="pmr-panel">' + (tab === "done" ? emptyBox("appr", "Chưa có lần giao nào xong", "Việc bạn giao, khi người nhận làm xong và bạn đóng, sẽ chuyển sang đây.")
        : emptyBox("list", "Bạn chưa giao việc nào đang chạy", "Giao việc cho một hay nhiều người, rồi theo dõi ai đã mở, ai đang làm, ai trễ ngay tại đây.", `<div class="pmr-mt">${B(ic("plus", "pmr-s") + "Giao việc", "new", "pmr-wash")}</div>`)) + "</div>";
    } else h += `<div class="pmr-panel pmr-batches">${batches.map(batchHtml).join("")}</div>`;
    c.innerHTML = h;
    on(c, (a, b) => onGiven(c, tab, d, a, b));
  }, e => loadErr(c, e, again, h0));
}
function onGiven(c, tab, d, a, b) {
  const again = () => renderGiven(c, tab);
  if (a === "new") return newTask({ onCreated: again });
  if (a === "gtab") return renderGiven(c, ga(b, "tab"));
  if (a === "dl-keep" || a === "dl-accept") {
    const al = b.closest(".pmr-alert"), rq = ga(al, "req"), acc = a === "dl-accept" ? 1 : 0, x = (d.banner || []).filter(z => z.request === rq)[0] || {}, restore = gone(al);
    return answerDl(b, rq, acc, () => {
      toast(acc ? "Đã đổi hạn sang " + dayLabel(x.new_end) : `Đã giữ hạn ${dayLabel(x.old_end)} và báo lại ${x.from_name || "người xin"}`);
      changed({ task: x.task });
      if (al.parentNode) al.parentNode.removeChild(al);
    }, restore);
  }
  if (a === "rule-pause" || a === "rule-resume") {
    const tr = b.closest("tr"), pau = a === "rule-pause", prevHtml = $(".pmr-st", tr).outerHTML;
    $(".pmr-st", tr).outerHTML = `<span class="pmr-st ${pau ? "pmr-s0" : "pmr-s3"}">${pau ? "Tạm dừng" : "Đang chạy"}</span>`;
    busy(b, call(pau ? "recurrence.pause" : "recurrence.resume", { name: ga(tr, "rule") })).then(() => {
      b.textContent = pau ? "Chạy lại" : "Tạm dừng"; b.setAttribute("data-act", pau ? "rule-resume" : "rule-pause");
      toast(pau ? "Đã tạm dừng lịch lặp lại" : "Đã chạy lại lịch lặp lại");
    }, e => { $(".pmr-st", tr).outerHTML = prevHtml; errToast(e, "Chưa đổi được lịch"); });
    return;
  }
  const bt = b.closest(".pmr-batch"), task = bt && ga(bt, "task"), batch = (d.batches || []).filter(z => z.task === task)[0] || {};
  switch (a) {
    case "toggle": {
      if (!$(".pmr-people", bt)) return;
      const op = !bt.classList.contains("pmr-open"), cb = $(".pmr-chev-b", bt);
      bt.classList.toggle("pmr-open", op);
      OPEN_BATCH[task] = op;
      if (cb) cb.setAttribute("aria-expanded", op);
      return;
    }
    case "open": return openTask(ga(b, "task") || task);
    case "nudge": case "nudge-one": return nudge(b, task, ga(b, "u"), batchStats(batch).notDone.length);
    case "close-batch": {
      const restore = gone(bt);
      busy(b, call("pm_inbox.close_parent", { task })).then(() => {
        toast(`Đã đóng “${batch.subject || task}”`, { actions: [{ label: "Hoàn tác", run: () => undoState(task, "Review", { revert: again }) }] });
        changed({ task, state: "Done" });
        if (bt.parentNode) bt.parentNode.removeChild(bt);
      }, e => { restore(); errToast(e, "Chưa đóng được việc"); });
      return;
    }
    case "return-open": { const f = $(".pmr-retform", bt); f.classList.toggle("pmr-hide"); return focusFirst(f, "input"); }
    case "return-cancel": return $(".pmr-retform", bt).classList.add("pmr-hide");
    case "return-send": {
      const users = $$(".pmr-retform input[type=checkbox]", bt).filter(x => x.checked).map(x => x.value);
      if (!users.length) return bad("Chọn ít nhất một người để trả lại");
      busy(b, call("pm_inbox.close_parent", { task, return_users: JSON.stringify(users), note: $(".pmr-ret-note", bt).value.trim() || null })).then(() => {
        toast(`Đã mở lại việc của ${users.map(nameOf).join(", ")}, kèm lời nhắn`); changed({ task }); again();
      }, e => errToast(e, "Chưa trả lại được"));
      return;
    }
    case "close-solo": markDone(task, { subject: batch.subject, prevState: "Review", isGiver: true, button: b, onDone: r => { if (!r.blocked_reason) again(); } }); return;
    case "return-solo": setState(task, "In Progress", "Review", { subject: batch.subject, button: b }).then(r => { if (!r || !r.error) again(); });
  }
}

/* == render.coordinate — Điều phối (leader) == */
let PENDING = null;
function goAllWork(f) { PENDING = f; nav("#work/list"); }
function todoHtml(x) {
  const k = x.kind, projs = arr(x.projects).map(p => (p.project_name || p.project || p.name) + (p.count ? ` (${p.count})` : "")).join(", ");
  let icon = "flag", tone = "pmr-g", t, m, act = "";
  if (k === "late") {
    const ld = x.days_late != null ? +x.days_late : lateDays(x.exp_end_date), notOpened = x.opened === false || x.opened === 0;
    icon = "alert"; tone = "pmr-r"; t = x.subject || x.task;
    m = [x.full_name || nameOf(x.user), ld ? `trễ ${ld} ngày` : "trễ hạn", notOpened ? "chưa mở việc" : stateLabel(x.workflow_state).toLowerCase()].join(" · ");
    act = (notOpened || x.workflow_state === "To Do" || x.workflow_state === "Backlog") && x.user
      ? Bs("Nhắc", "c-nudge", "pmr-wash", dattr("task", x.task) + dattr("u", x.user)) : Bs("Mở", "c-open", "", dattr("task", x.task));
  } else if (k === "unassigned") { icon = "userx"; tone = "pmr-a"; t = `${x.count || 0} việc chưa có người nhận`; m = projs; act = Bs("Giao", "c-unassigned"); }
  else if (k === "nodue") { icon = "calx"; t = `${x.count || 0} việc mở hơn 7 ngày chưa có hạn`; m = projs; act = Bs("Đặt hạn", "c-nodue"); }
  else if (k === "overload") {
    t = `${x.full_name || nameOf(x.user)} đang giữ ${x.open || 0} việc mở`; m = "nhiều nhất nhóm" + (x.due_48h ? ` · ${x.due_48h} việc hạn trong 48 giờ` : "");
    act = Bs("Xem việc", "c-person", "", dattr("u", x.user));
  } else { t = x.subject || ""; m = ""; }
  return `<div class="pmr-todo-row"><span class="pmr-ticon ${tone}">${ic(icon, "pmr-s")}</span><div class="pmr-minw"><div class="pmr-t">${esc(t)}</div><div class="pmr-m">${esc(m)}</div></div>${act}</div>`;
}
const kv = (v, l, cls) => `<div class="${cls || ""}"><div class="pmr-v pmr-num">${v}</div><div class="pmr-l">${l}</div></div>`;
const bar = pc => `<span class="pmr-bar"><i class="${pc >= 85 ? "pmr-ok" : ""}" style="width:${pc}%"></i></span>`;
const rc = (v, warn) => `<td class="pmr-r${warn ? " pmr-late" : ""}">${v}</td>`;
function renderCoordinate(c) {
  prep(c);
  const head = pageHead("Điều phối", "Việc của cả nhóm: ai trễ, việc nào chưa có người, ai đang ôm nhiều việc."), again = () => renderCoordinate(c);
  c.innerHTML = head + skel(6);
  return call("pm_inbox.coordinate", { include_personal: isPersonalShown() ? 1 : 0 }).then(d => {
    d = d || {};
    const k = d.kpi || {}, todo = d.todo || [], ppl = (d.people || []).slice(), prj = (d.projects || []).slice();
    const byLate = (a, b) => (b.late || 0) - (a.late || 0) || (b.open || 0) - (a.open || 0);
    ppl.sort(byLate); prj.sort(byLate);
    c.innerHTML = head + `<div class="pmr-strip">${kv(k.open || 0, "việc đang mở")}${kv(k.late || 0, "trễ hạn", k.late ? "pmr-late" : "")}${kv(k.unassigned || 0, "chưa có người nhận")}${kv(k.done_week || 0, "xong tuần này")}` +
      `${kv(k.on_time_pct_30d == null ? "—" : Math.round(+k.on_time_pct_30d) + "%", "xong đúng hạn (30 ngày)")}</div><div class="pmr-pt"></div>` +
      `<div class="pmr-grid2"><div class="pmr-panel"><div class="pmr-panel-h"><h3>Cần xử lý</h3><span class="pmr-meta">${todo.length} mục</span></div>` +
      (todo.length ? todo.map(todoHtml).join("") : emptyBox("appr", "Không có gì cần xử lý", "Không có việc trễ, việc chưa có người hay người quá tải. Kiểm tra lại sau.")) + "</div>" +
      '<div class="pmr-panel"><div class="pmr-panel-h"><h3>Theo người</h3><span class="pmr-meta">tuần này</span></div>' +
      (ppl.length ? '<div class="pmr-tbw">' + thead(["Người", ">Đang mở", ">Trễ", ">Xong"]) +
        ppl.map(p => `<tr><td><button type="button" class="pmr-who-b" data-act="c-person"${dattr("u", p.user)}>${who(p.user, p.full_name)}</button></td>${rc(p.open || 0)}${rc(p.late || 0, p.late)}${rc(p.done_week || 0)}</tr>`).join("") + "</tbody></table></div>"
        : emptyBox("flag", "Chưa có ai đang giữ việc", "")) + "</div></div>" +
      `<div class="pmr-panel"><div class="pmr-panel-h"><h3>Dự án đang chạy</h3><span class="pmr-meta">sắp theo việc trễ</span>${L("Tất cả dự án", "c-projects", "", "pmr-ml")}</div>` +
      (prj.length ? '<div class="pmr-tbw">' + thead(["Dự án", "Tiến độ", ">Mở", ">Trễ", ">Chưa giao", "Phụ trách"]) +
        prj.map(p => {
          const pc = p.total ? Math.round((p.done || 0) * 100 / p.total) : 0;
          return `<tr><td><button type="button" class="pmr-pname" data-act="c-project"${dattr("p", p.name)}>${esc(p.project_name || p.name)}</button></td><td class="pmr-nowrap">${bar(pc)}<span class="pmr-num">${pc}%</span></td>` +
            `${rc(p.open || 0)}${rc(p.late || 0, p.late)}${rc(p.unassigned || 0, p.unassigned)}<td>${p.owner ? who(p.owner, p.owner_name) : muted("—")}</td></tr>`;
        }).join("") + "</tbody></table></div>" : emptyBox("list", "Chưa có dự án đang chạy", "")) + "</div>";
    personalToggle($(".pmr-pt", c), again, { count: d.personal_hidden, noun: "dự án nhật ký cá nhân", suffix: " — không tính vào số liệu nhóm" });
    on(c, (a, b) => {
      if (a === "c-nudge") nudge(b, ga(b, "task"), ga(b, "u"));
      else if (a === "c-open") openTask(ga(b, "task"));
      else if (a === "c-unassigned") goAllWork({ f: "none" });
      else if (a === "c-nodue") goAllWork({ f: "nodue" });
      else if (a === "c-person") goAllWork({ assignee: ga(b, "u") });
      else if (a === "c-projects") nav("#projects");
      else if (a === "c-project") openProject(ga(b, "p"));
    });
  }, e => {
    if (isPermErr(e)) c.innerHTML = head + emptyBox("flag", "Chỉ trưởng nhóm xem được Điều phối", esc(errOf(e)));
    else loadErr(c, e, again, head);
  });
}

/* == render.allWork — Tất cả việc (Danh sách + Kanban; Theo hạn/Gantt uỷ cho host) == */
let AW = null, DRAG = null;
const BOARD = ["To Do", "In Progress", "Review", "Done"];
const CYCLE = { "Backlog": "In Progress", "To Do": "In Progress", "Blocked": "In Progress", "In Progress": "Review", "Review": "Done", "Done": "To Do" };
const NOF = () => ({ late: false, none: false, week: false, nodue: false });
function rowAssignees(r) {   /* việc cha chia người: hiện người nhận của các việc con */
  const u = [];
  (r._kids || []).forEach(k => arr(k._assign).forEach(x => { if (u.indexOf(x) < 0) u.push(x); }));
  return u.length ? u : arr(r._assign);
}
function awPrepare(rows) {
  const by = {}, top = [];
  rows.forEach(r => { by[r.name] = r; r._kids = []; });
  rows.forEach(r => { if (r.parent_task && by[r.parent_task]) by[r.parent_task]._kids.push(r); else top.push(r); });
  return top;
}
function awFiltered() {
  const st = AW, wk = weekRange(), td = todayYmd(), q = fold(st.q), f = st.f;
  return st.top.filter(r => {
    const ws = r.workflow_state, due = ymd10(r.exp_end_date), asg = rowAssignees(r);
    if (ws === "Cancelled" || (!isPersonalShown() && truthy(r.ec_personal_log))) return false;
    if (st.view === "list" && ws === "Done" && !st.justDone[r.name]) return false;
    if ((f.late && !(due && due < td && !isClosed(ws))) || (f.none && asg.length) || (f.week && !(due && due >= wk[0] && due <= wk[1])) || (f.nodue && due)) return false;
    if (st.project && (r.project || "") !== (st.project === "__none" ? "" : st.project)) return false;
    if (st.assignee && asg.indexOf(st.assignee) < 0) return false;
    return !q || fold([r.subject, r.project_name, asg.map(nameOf).join(" "), asg.join(" ")].join(" ")).indexOf(q) >= 0;
  });
}
const awActive = () => { const f = AW.f; return !!(f.late || f.none || f.week || f.nodue || AW.q || AW.assignee); };
function awRow(r) {
  const asg = rowAssignees(r), ws = r.workflow_state, done = ws === "Done", di = dueInfo(r.exp_end_date, r.pm_end_time, ws);
  return `<tr${dattr("task", r.name)} class="${done ? "pmr-done" : ""}"><td><div class="pmr-tcell"><button type="button" class="pmr-cb" data-act="tick" aria-pressed="${done}" aria-label="${done ? "Bỏ đánh dấu xong" : "Đánh dấu xong"}: ${esc(r.subject)}"></button>` +
    `<button type="button" class="pmr-tname" data-act="open">${esc(r.subject || r.name)}</button>${r._kids.length ? `<span class="pmr-subn">· ${r._kids.length} việc con</span>` : ""}</div></td>` +
    `<td class="pmr-pick-wrap">${asg.length ? (asg.length > 1 ? stack(asg) : who(asg[0])) : (done ? "" : L("+ Giao người", "assign"))}</td>` +
    `<td>${r.exp_end_date ? dueSpan(di) : muted("Chưa có hạn")}</td>` +
    `<td>${pill(ws, `data-act="cycle" aria-label="Trạng thái ${esc(stateLabel(ws))}, bấm để chuyển"`)}</td></tr>`;
}
function awGroups(rows) {
  const g = AW.group, map = {}, order = [];
  rows.forEach(r => {
    let key = "*", label = "";
    if (g === "assignee") { const a = rowAssignees(r)[0]; key = a || ""; label = a ? nameOf(a) : "Chưa có người"; }
    else if (g !== "none") { key = r.project || ""; label = r.project ? r.project_name || r.project : NOPROJ; }
    if (!map[key]) order.push(map[key] = { key, label, rows: [] });
    map[key].rows.push(r);
  });
  return order.sort((a, b) => (!a.key && b.key) ? 1 : ((a.key && !b.key) ? -1 : a.label.localeCompare(b.label, "vi")));
}
function paintList(body) {
  const rows = awFiltered();
  if (!rows.length) {
    body.innerHTML = '<div class="pmr-panel">' + (awActive() || AW.project ? emptyBox("search", "Không có việc nào khớp", `Bỏ bớt bộ lọc, hoặc ${L("xoá tất cả bộ lọc", "clear")}.`)
      : emptyBox("list", "Chưa có việc nào đang mở", "Việc bạn được giao, việc bạn giao và việc trong dự án bạn xem được sẽ hiện ở đây.", `<div class="pmr-mt">${B(ic("plus", "pmr-s") + "Giao việc", "new", "pmr-wash")}</div>`)) + "</div>";
    return;
  }
  const none = AW.group === "none";
  let h = '<div class="pmr-panel pmr-tbw">' + thead(["Việc", "Người nhận", "Hạn", "Trạng thái"], "pmr-tasks");
  awGroups(rows).forEach(g => {
    if (!none) h += `<tr class="pmr-grp-row"><td colspan="4">${esc(g.label)}<span class="pmr-cnt">${g.rows.length}</span></td></tr>`;
    h += g.rows.map(awRow).join("");
    if (!awActive() && AW.group !== "assignee") {
      const proj = none ? (AW.project && AW.project !== "__none" ? AW.project : "") : g.key;
      h += `<tr class="pmr-addrow"${dattr("project", proj)}><td colspan="4"><button type="button" class="pmr-link-muted" data-act="quick">${ic("plus", "pmr-s")}${none ? " Thêm việc" : " Thêm việc vào " + esc(g.label)}</button></td></tr>`;
    }
  });
  body.innerHTML = h + "</tbody></table></div>" + (AW.capped ? `<div class="pmr-hint pmr-mt">Đang hiện ${AW.rows.length} việc cập nhật gần nhất. Dùng ô lọc hoặc chọn dự án để thu hẹp.</div>` : "");
}
function paintBoard(body) {
  const cols = {};
  BOARD.forEach(b => { cols[b] = []; });
  awFiltered().forEach(r => { const k = curBucket(r.workflow_state); if (cols[k]) cols[k].push(r); });
  const doneTotal = cols.Done.length;
  cols.Done = cols.Done.sort((a, b) => String(b.modified || "").localeCompare(String(a.modified || ""))).slice(0, 30);
  body.innerHTML = `<div class="pmr-kanban">${BOARD.map(b => {
    const list = cols[b];
    return `<div class="pmr-kcol" data-s="${b}"><h4>${pill(b)}<span class="pmr-cnt">${b === "Done" ? doneTotal : list.length}</span></h4>` + list.map(r => {
      const asg = rowAssignees(r), di = dueInfo(r.exp_end_date, r.pm_end_time, r.workflow_state);
      const left = r._kids.length ? `${r._kids.filter(k => k.workflow_state === "Done").length}/${r._kids.length} người xong` : (asg.length ? av(asg[0]) : esc(r.project_name || ""));
      return `<div class="pmr-kc" draggable="true" tabindex="0" role="button" data-act="open"${dattr("task", r.name)}><div class="pmr-t">${esc(r.subject || r.name)}</div><div class="pmr-m"><span>${left}</span>` +
        `${b !== "Done" && r.exp_end_date ? dueSpan(di) : ""}</div></div>`;
    }).join("") + (list.length ? "" : '<div class="pmr-kempty">Kéo việc vào đây</div>') + "</div>";
  }).join("")}</div>`;
}
function awPaintBody() {
  const c = AW.c, body = $(".pmr-aw-body", c), sub = $(".pmr-aw-sub", c), nd = $(".pmr-chip-nodue", c);
  if (!body) return;
  (AW.view === "board" ? paintBoard : paintList)(body);
  $$(".pmr-aw-chip", c).forEach(ch => { const onC = !!AW.f[ga(ch, "f")]; ch.classList.toggle("pmr-on", onC); ch.setAttribute("aria-pressed", onC); });
  if (nd) nd.classList.toggle("pmr-hide", !AW.f.nodue);
  if (sub) {
    const open = AW.top.filter(r => !isClosed(r.workflow_state) && (isPersonalShown() || !truthy(r.ec_personal_log))).length;
    sub.textContent = `Mọi việc bạn được xem · ${open} đang mở · việc đã huỷ${isPersonalShown() ? "" : " và nhật ký cá nhân"} đang ẩn`;
  }
}
const awFindRow = name => AW.rows.filter(r => r.name === name)[0] || null;
const awSetState = name => st => { const r = awFindRow(name); if (r) { r.workflow_state = st; if (st === "Done") AW.justDone[name] = true; } awPaintBody(); };
function awMove(name, target, button) {
  const r = awFindRow(name);
  if (!r || curBucket(r.workflow_state) === target) return;
  const o = { subject: r.subject, prevState: r.workflow_state, apply: awSetState(name), revert: awSetState(name), button };
  if (target === "Done") markDone(name, o); else setState(name, target, r.workflow_state, o);
}
function renderAllWork(c, view, opts) {
  prep(c);
  opts = opts || {};
  view = { list: 1, board: 1, due: 1, gantt: 1 }[view] ? view : "list";
  const keep = AW && AW.c === c ? AW : {};
  AW = { c, view, opts, q: keep.q || "", f: keep.f || NOF(), project: keep.project || "", assignee: keep.assignee || "", group: keep.group || "project", rows: [], top: [], justDone: {}, capped: false };
  if (PENDING) { AW.f = NOF(); AW.q = ""; AW.assignee = PENDING.assignee || ""; if (PENDING.f) AW.f[PENDING.f] = true; PENDING = null; }
  const seg = `<div class="pmr-seg" role="group" aria-label="Kiểu xem">${[["list", "list", "Danh sách"], ["board", "board", "Kanban"], ["due", "cal", "Theo hạn"], ["gantt", "gantt", "Gantt"]].map(v =>
    `<button type="button" data-act="view" data-v="${v[0]}"${onA(v[0] === view)}>${ic(v[1], "pmr-s")}${v[2]}</button>`).join("")}</div>`;
  const head = `<div class="pmr-ph"><div class="pmr-grow"><h2>Tất cả việc</h2><div class="pmr-sub pmr-aw-sub">Mọi việc bạn được xem</div></div>${seg}</div>`;
  if (view === "due" || view === "gantt") {
    c.innerHTML = head + '<div class="pmr-aw-body"></div>';
    const fn = view === "due" ? opts.renderDue || cfg.views.due : opts.renderGantt || cfg.views.gantt, body = $(".pmr-aw-body", c);
    if (fn) { try { fn(body); } catch (e) { body.innerHTML = errBox("Không mở được kiểu xem này.", e); } }
    else body.innerHTML = `<div class="pmr-panel">${emptyBox("cal", "Kiểu xem này chưa sẵn sàng", "Dùng Danh sách hoặc Kanban trong lúc chờ.")}</div>`;
    on(c, (a, b) => { if (a === "view") awSwitch(c, ga(b, "v")); });
    return Promise.resolve();
  }
  c.innerHTML = head + `<div class="pmr-toolbar"><label class="pmr-search">${ic("search", "pmr-s")}<input class="pmr-aw-q" type="search" aria-label="Lọc việc" placeholder="Lọc theo tên việc, người, dự án" value="${esc(AW.q)}"></label>` +
    [["late", "Trễ hạn"], ["none", "Chưa có người"], ["week", "Hạn tuần này"], ["nodue", "Chưa có hạn"]].map(x =>
      `<button type="button" class="pmr-chip pmr-aw-chip${x[0] === "nodue" ? " pmr-chip-nodue pmr-hide" : ""}" data-act="chip" data-f="${x[0]}" aria-pressed="false">${x[1]}</button>`).join("") +
    '<span class="pmr-grow"></span><select class="pmr-sel pmr-aw-proj" aria-label="Dự án"></select><select class="pmr-sel pmr-aw-asg" aria-label="Người nhận"></select>' +
    `<select class="pmr-sel pmr-aw-grp" aria-label="Nhóm theo"${view === "board" ? " hidden" : ""}><option value="project">Nhóm theo: Dự án</option><option value="assignee">Nhóm theo: Người nhận</option><option value="none">Không nhóm</option></select></div>` +
    `<div class="pmr-pt"></div><div class="pmr-aw-body">${skel(8)}</div>`;
  $(".pmr-aw-grp", c).value = AW.group;
  personalToggle($(".pmr-pt", c), () => renderAllWork(c, view, opts), { noun: "nhật ký cá nhân" });
  const qIn = $(".pmr-aw-q", c);
  let qt = null;
  qIn.addEventListener("input", () => { const v = qIn.value; clearTimeout(qt); qt = setTimeout(() => { AW.q = v; awPaintBody(); }, 60); });
  c.onchange = e => {
    const cl = e.target.classList;
    if (cl.contains("pmr-aw-proj")) AW.project = e.target.value;
    else if (cl.contains("pmr-aw-asg")) AW.assignee = e.target.value;
    else if (cl.contains("pmr-aw-grp")) AW.group = e.target.value;
    else return;
    awPaintBody();
  };
  c.onkeydown = e => {
    const t = e.target;
    if (t.classList.contains("pmr-kc") && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openTask(ga(t, "task")); }
    else if (t.classList.contains("pmr-quick-in")) {
      if (e.key === "Escape") { e.stopPropagation(); awPaintBody(); }
      else if (e.key === "Enter") { e.preventDefault(); quickAdd(t); }
    }
  };
  bindBoardDnD(c);
  on(c, onAllWork);
  return call("tasks.list", { page_length: 500, include_personal: isPersonalShown() ? 1 : 0 }).then(r => {
    if (!AW || AW.c !== c) return;
    r = r || {};
    learnNames(r.user_names);
    AW.rows = r.rows || [];
    AW.capped = AW.rows.length >= 500;
    AW.top = awPrepare(AW.rows);
    const projs = {}, users = {};
    AW.rows.forEach(x => { if (x.project) projs[x.project] = x.project_name || x.project; arr(x._assign).forEach(u => { users[u] = nameOf(u); }); });
    if (AW.assignee) users[AW.assignee] = nameOf(AW.assignee);
    const opt2 = (m, k) => `<option value="${esc(k)}">${esc(m[k])}</option>`, sorted = m => Object.keys(m).sort((a, b) => m[a].localeCompare(m[b], "vi"));
    $(".pmr-aw-proj", c).innerHTML = '<option value="">Dự án: Tất cả</option>' + sorted(projs).map(k => opt2(projs, k)).join("") + '<option value="__none">Không thuộc dự án</option>';
    $(".pmr-aw-asg", c).innerHTML = '<option value="">Người nhận: Tất cả</option>' + sorted(users).map(k => opt2(users, k)).join("");
    $(".pmr-aw-proj", c).value = AW.project;
    $(".pmr-aw-asg", c).value = AW.assignee;
    awPaintBody();
  }, e => { const body = $(".pmr-aw-body", c); if (body) body.innerHTML = errBox("Không tải được danh sách việc.", e, true); });
}
function awSwitch(c, v) {
  const cb = (AW && AW.opts && AW.opts.onViewChange) || cfg.onViewChange;
  if (cb) safe(cb, v);
  renderAllWork(c, v, AW ? AW.opts : {});
}
function bindBoardDnD(c) {
  if (c.__pmrDnD) return;
  c.__pmrDnD = true;
  const kc = e => e.target.closest && e.target.closest(".pmr-kc"), col = e => e.target.closest && e.target.closest(".pmr-kcol");
  c.addEventListener("dragstart", e => {
    const k = kc(e);
    if (!k) return;
    DRAG = ga(k, "task");
    try { e.dataTransfer.setData("text/plain", DRAG); e.dataTransfer.effectAllowed = "move"; } catch (x) { }
  });
  c.addEventListener("dragover", e => { const k = col(e); if (k && DRAG) { e.preventDefault(); k.classList.add("pmr-over"); } });
  c.addEventListener("dragleave", e => { const k = col(e); if (k) k.classList.remove("pmr-over"); });
  c.addEventListener("drop", e => {
    const k = col(e), name = DRAG;
    if (!k || !name) return;
    e.preventDefault();
    k.classList.remove("pmr-over");
    DRAG = null;
    awMove(name, ga(k, "s"));
  });
}
function quickAdd(inp) {
  const v = inp.value.trim(), tr = inp.closest("tr"), proj = (tr && ga(tr, "project")) || "";
  if (!v) return inp.focus();
  inp.disabled = true;
  call("tasks.create", { project: proj, subject: v }).then(r => {
    r = r || {};
    const pn = proj ? (AW.rows.filter(x => x.project === proj)[0] || {}).project_name || proj : null;
    const row = { name: r.name, subject: r.subject || v, project: r.project || proj, project_name: pn, workflow_state: r.workflow_state || "To Do", _assign: null, exp_end_date: null, _kids: [] };
    AW.rows.unshift(row); AW.top.unshift(row);
    toast(`Đã thêm “${v}”`, { actions: [{ label: "Mở", run: () => openTask(row.name) }] });
    changed({ task: row.name, created: true });
    awPaintBody();
    const again = $$(".pmr-addrow", AW.c).filter(x => ga(x, "project") === proj)[0];
    if (again) $("[data-act=quick]", again).click();
  }, e => { inp.disabled = false; inp.focus(); errToast(e, "Chưa thêm được việc"); });
}
function onAllWork(a, b) {
  const c = AW.c;
  switch (a) {
    case "view": return awSwitch(c, ga(b, "v"));
    case "retry": return renderAllWork(c, AW.view, AW.opts);
    case "chip": { const k = ga(b, "f"); AW.f[k] = !AW.f[k]; return awPaintBody(); }
    case "clear":
      Object.assign(AW, { f: NOF(), q: "", project: "", assignee: "" });
      $(".pmr-aw-q", c).value = $(".pmr-aw-proj", c).value = $(".pmr-aw-asg", c).value = "";
      return awPaintBody();
    case "new": return newTask({ onCreated: () => renderAllWork(c, AW.view, AW.opts) });
    case "quick": {
      const td = b.parentNode;
      td.innerHTML = '<input class="pmr-in pmr-quick-in" aria-label="Tên việc mới" placeholder="Tên việc, Enter để thêm, Esc để huỷ">';
      return focusFirst(td, ".pmr-quick-in");
    }
  }
  const tr = b.closest("tr"), name = ga(b, "task") || (tr && ga(tr, "task")), r = name && awFindRow(name);
  if (a === "open") return openTask(name);
  if (!r) return;
  if (a === "tick") {
    const o = { subject: r.subject, prevState: r.workflow_state, apply: awSetState(name), revert: awSetState(name), button: b };
    if (r.workflow_state === "Done") setState(name, "In Progress", "Done", o); else markDone(name, o);
  } else if (a === "cycle") awMove(name, CYCLE[r.workflow_state] || "In Progress", b);
  else if (a === "assign") {
    pickPeople(b.parentNode, u => {
      const prev = r._assign;
      r._assign = JSON.stringify([u]); awPaintBody();
      call("tasks.assign", { name, users: JSON.stringify([u]) }).then(() => {
        toast(`Đã giao “${r.subject}” cho ${nameOf(u)}`); changed({ task: name });
      }, e => { r._assign = prev; awPaintBody(); errToast(e, "Chưa giao được"); });
    });
  }
}

/* == render.projects — Dự án == */
function renderProjects(c) {
  prep(c);
  const right = cfg.createProject ? B(ic("plus", "pmr-s") + "Tạo dự án", "p-create", "pmr-pri") : "", again = () => renderProjects(c);
  const h0 = pageHead("Dự án", "", right);
  c.innerHTML = h0 + skel(6);
  on(c, a => { if (a === "p-create") safe(cfg.createProject); });
  return call("projects.list", { page_length: 500, include_personal: isPersonalShown() ? 1 : 0 }).then(r => {
    const raw = (r && r.rows) || [], all = raw.filter(p => isPersonalShown() || !truthy(p.ec_personal_log)), isOpen = p => !p.status || p.status === "Open";
    const hidden = r && r.personal_hidden != null ? r.personal_hidden : (raw.length - all.length || null);
    const paint = () => {
      const filt = c.__pmrProjFilter || "run";
      const rows = all.filter(p => filt === "run" ? isOpen(p) : (filt === "done" ? p.status === "Completed" : p.ec_manager === cfg.user || p.owner === cfg.user));
      let h = pageHead("Dự án", esc(all.filter(isOpen).length + " dự án đang chạy"), right) + '<div class="pmr-toolbar">' +
        [["run", "Đang chạy"], ["done", "Hoàn thành"], ["mine", "Của tôi"]].map(x => `<button type="button" class="pmr-chip${filt === x[0] ? " pmr-on" : ""}" aria-pressed="${filt === x[0]}" data-act="p-filter" data-f="${x[0]}">${x[1]}</button>`).join("") +
        '<span class="pmr-grow"></span><span class="pmr-pt"></span></div>';
      if (!rows.length) {
        h += `<div class="pmr-panel">${emptyBox("list", filt === "mine" ? "Bạn chưa phụ trách dự án nào" : "Không có dự án nào ở đây", filt === "run" ? "Dự án gom các việc cùng mục tiêu để cả nhóm theo dõi tiến độ." : "Đổi bộ lọc phía trên để xem dự án khác.")}</div>`;
      } else {
        h += '<div class="pmr-panel pmr-tbw">' + thead(["Dự án", "Phụ trách", "Tiến độ", ">Mở", ">Trễ", ">Chưa giao", "Cập nhật"]) + rows.map(p => {
          const tot = +p.task_total || 0, dn = +p.task_done || 0, pc = tot ? Math.round(dn * 100 / tot) : (+p.progress || 0), mgr = p.ec_manager || p.owner;
          return `<tr><td><button type="button" class="pmr-pname" data-act="p-open"${dattr("p", p.name)}>${esc(p.project_name || p.name)}</button>${p.ec_department ? `<div class="pmr-pdept">${esc(p.ec_department)}</div>` : ""}${truthy(p.ec_personal_log) ? '<span class="pmr-tag">nhật ký cá nhân</span>' : ""}</td>` +
            `<td>${mgr ? who(mgr, p.ec_manager_name) : muted("—")}</td><td class="pmr-nowrap">${bar(pc)}<span class="pmr-num">${dn}/${tot}</span></td>` +
            `${rc(p.open != null ? p.open : tot - dn)}${rc(p.late != null ? p.late : "—", p.late)}${rc(p.unassigned != null ? p.unassigned : "—", p.unassigned)}<td class="pmr-muted">${esc(relDay(p.modified))}</td></tr>`;
        }).join("") + "</tbody></table></div>";
      }
      c.innerHTML = h;
      personalToggle($(".pmr-pt", c), again, { count: isPersonalShown() ? null : hidden, noun: "dự án nhật ký cá nhân" });
    };
    paint();
    on(c, (a, b) => {
      if (a === "p-filter") { c.__pmrProjFilter = ga(b, "f"); paint(); }
      else if (a === "p-open") openProject(ga(b, "p"));
      else if (a === "p-create") safe(cfg.createProject);
    });
  }, e => loadErr(c, e, again, h0));
}

/* == init + API công khai == */
function ensureInit() { if (!inited) throw new Error("PMR.init({api, user}) phải được gọi trước."); }
function init(o) {
  o = o || {};
  for (const k in o) if (HAS.call(o, k) && HAS.call(cfg, k)) cfg[k] = o[k];
  if (typeof cfg.api !== "function") throw new Error("PMR.init: thiếu api(method, args).");
  cfg.views = cfg.views || {};
  if (!inited) {
    inited = true;
    ensureSprite();
    D.addEventListener("keydown", onDocKey);
    bindNewInputs();
  }
  return PMR;
}
const PMR = {
  __pmr: '2026-10-16',
  init, LABELS, stateLabel, priorityLabel,
  statePill: ws => pill(ws),
  openTask: (name, o) => { ensureInit(); return openTask(name, o); },
  newTask: o => { ensureInit(); return newTask(o); },
  markDone: (name, o) => { ensureInit(); return markDone(name, o); },
  closeSheet: sheetClose,
  render: { received: renderReceived, given: renderGiven, coordinate: renderCoordinate, allWork: renderAllWork, projects: renderProjects },
  personalToggle, isPersonalShown,
  _pure: { dueInfo, dayLabel, sanitize, buildCreatePlan, errOf, quickDue }
};
root.PMR = PMR;
})(window);
