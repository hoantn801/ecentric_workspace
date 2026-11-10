# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu - quy tac THUAN (khong cham DB, khong import frappe): kiem du lieu nhap, tinh
han theo ngay lam viec, he so uu tien, tam dung, hang doi, KPI, sap xep, Gantt, cot Dieu phoi.

Ngay le luon TRUYEN VAO (tap `date`); dem ngay lam viec dung lai helper chung cua cong ty
(approval_center/shared/workflow/ngay_lam_viec.py) - module nay khong tu viet lich rieng.

QUY UOC HAN (PO chot 09/11/2026, ghi o README):
  * han = ngay bat dau + N ngay lam viec (khong tinh chinh ngay bat dau; bo T7/CN + ngay le);
  * N = ceil(so ngay theo loai x he so uu tien), toi thieu 1;
  * tam dung (cho nguoi gui) -> khi tiep tuc, han cong them so ngay lam viec da dung;
  * hang doi: Khan > Cao > Binh thuong > Thap, cung muc thi gui truoc lam truoc.
"""
import datetime as _dt
import math
import re

from ecentric_workspace.approval_center.shared.workflow import ngay_lam_viec as NLV
from ecentric_workspace.data_hub import constants as C

_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"^https?://[^\s<>\"']+$", re.I)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Invalid(Exception):
    """Du lieu nhap sai - mang danh sach loi tieng Viet."""

    def __init__(self, errors):
        self.errors = list(errors if isinstance(errors, (list, tuple)) else [errors])
        super().__init__(" ".join(self.errors))


# ------------------------------------------------------------------ chuoi / ngay ----------
def clean_text(s, limit):
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s[:limit] if limit else s


def one_line(s, limit):
    return _WS_RE.sub(" ", (s or "")).strip()[:limit]


def as_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        return None


def as_datetime(v):
    if not v:
        return None
    if isinstance(v, _dt.datetime):
        return v
    if isinstance(v, _dt.date):
        return _dt.datetime(v.year, v.month, v.day)
    try:
        return _dt.datetime.fromisoformat(str(v).strip()[:19])
    except ValueError:
        return None


def fmt_date(v):
    d = as_date(v)
    return d.strftime("%d/%m") if d else ""


def fmt_date_full(v):
    d = as_date(v)
    return d.strftime("%d/%m/%Y") if d else ""


def fmt_dt(v):
    d = as_datetime(v)
    return d.strftime("%d/%m %H:%M") if d else ""


def iso(v):
    d = as_date(v)
    return d.isoformat() if d else ""


def valid_link(s):
    return bool(_URL_RE.match(s or ""))


# ------------------------------------------------------------------ ngay lam viec ---------
def is_working_day(d, holidays=()):
    return NLV.la_ngay_lam_viec(d, holidays)


def add_working_days(d, n, holidays=()):
    return NLV.cong_ngay_lam_viec(d, n, holidays)


def working_days_between(a, b, holidays=()):
    """So ngay lam viec x voi a < x <= b."""
    return NLV.dem_ngay_lam_viec(a, b, holidays)


def default_start(today, holidays=()):
    """Hom nay neu la ngay lam viec, khong thi ngay lam viec ke tiep."""
    return add_working_days(today, 0, holidays)


# ------------------------------------------------------------------ quy tac han -----------
def rules_view(rule_set):
    """Ban ghi EC Data SLA Rule Set (dict, items = [{rule_key, label, days, note}]) -> dang dung chung
    {version, days{key}, labels{key}, notes{key}, mult{priority}}. Thieu dong nao -> lay mac dinh v1
    (khong bao gio de han tinh khong ra)."""
    rs = rule_set or {}
    days, labels, notes = {}, {}, {}
    for key, _type_label, table_label, d, note in C.RULE_DEFAULTS:
        days[key], labels[key], notes[key] = d, table_label, note
    for it in rs.get("items") or []:
        key = it.get("rule_key")
        if key in days:
            try:
                v = int(it.get("days") or 0)
            except (TypeError, ValueError):
                v = 0
            if v > 0:
                days[key] = v
            labels[key] = it.get("label") or labels[key]
            notes[key] = it.get("note") or ""
    mult = {}
    for p, field in C.MULT_FIELDS.items():
        try:
            v = float(rs.get(field) or 0)
        except (TypeError, ValueError):
            v = 0
        mult[p] = v if v > 0 else C.MULT_DEFAULTS[p]
    return {"version": rs.get("name") or "", "days": days, "labels": labels, "notes": notes, "mult": mult}


def sla_days(base_days, multiplier):
    """ceil(so ngay x he so), toi thieu 1. round() truoc ceil: 7 x 0.8 = 5.6000000000000005."""
    return max(1, int(math.ceil(round(float(base_days) * float(multiplier), 6))))


def ticket_sla_days(rules, request_type, priority):
    key = C.TYPE_RULE_KEY.get(request_type, "other")
    return sla_days(rules["days"][key], rules["mult"].get(priority, 1.0))


def due_from(start, days, holidays=()):
    return add_working_days(start, days, holidays)


def intake_due(created, rules, holidays=()):
    """Han team Data phai nhan viec (quy tac "Tiep nhan yeu cau moi")."""
    return add_working_days(as_date(created), rules["days"][C.RULE_INTAKE], holidays)


def type_hints(rules):
    """{loai: {muc: N}} cho goi y "Han du kien N ngay lam viec" tren form tao (JS doc thang)."""
    return {t: {p: ticket_sla_days(rules, t, p) for p in C.PRIORITIES} for t in C.REQUEST_TYPES}


# ------------------------------------------------------------------ tao yeu cau -----------
def normalize_create(data, sent_today=0):
    """data tu form -> dict sach. Nem Invalid. Khan: nguoi gui chi DE XUAT, bat buoc ly do."""
    errs = []
    title = one_line(data.get("title"), C.TITLE_MAX + 1)
    desc = clean_text(data.get("description"), C.BODY_MAX + 1)
    rtype = (data.get("request_type") or "").strip()
    pri = (data.get("proposed_priority") or C.PRI_NORMAL).strip()
    reason = clean_text(data.get("urgent_reason"), C.REASON_MAX + 1)
    used = clean_text(data.get("data_used"), C.DATA_USED_MAX + 1)
    link = (data.get("reference_link") or "").strip()
    if sent_today >= C.DAILY_LIMIT:
        errs.append("Hôm nay bạn đã gửi {0} yêu cầu. Mai gửi tiếp nhé.".format(C.DAILY_LIMIT))
    if rtype not in C.REQUEST_TYPES:
        errs.append("Chọn loại yêu cầu.")
    if pri not in C.PRIORITIES:
        errs.append("Mức độ không hợp lệ.")
    if not title:
        errs.append("Chưa có tiêu đề.")
    elif len(title) > C.TITLE_MAX:
        errs.append("Tiêu đề dài quá {0} ký tự.".format(C.TITLE_MAX))
    if not desc:
        errs.append("Chưa có mô tả / đầu ra mong muốn.")
    elif len(desc) > C.BODY_MAX:
        errs.append("Mô tả dài quá {0} ký tự.".format(C.BODY_MAX))
    if len(used) > C.DATA_USED_MAX:
        errs.append("Ô dữ liệu cần dùng dài quá {0} ký tự.".format(C.DATA_USED_MAX))
    if pri == C.PRI_URGENT and not reason:
        errs.append("Mức Khẩn cần ghi lý do để team Data xác nhận.")
    elif len(reason) > C.REASON_MAX:
        errs.append("Lý do dài quá {0} ký tự.".format(C.REASON_MAX))
    if link and (len(link) > C.LINK_MAX or not valid_link(link)):
        errs.append("Link mẫu phải bắt đầu bằng http:// hoặc https://")
    if errs:
        raise Invalid(errs)
    return {"title": title, "description": desc, "request_type": rtype, "proposed_priority": pri,
            "urgent_reason": reason if pri == C.PRI_URGENT else "", "data_used": used, "reference_link": link}


def file_ext(name):
    return name.rsplit(".", 1)[-1].lower() if "." in (name or "") else ""


def check_files(files):
    """files = [{name, size}] -> danh sach loi."""
    errs = []
    if len(files or ()) > C.MAX_FILES:
        errs.append("Tối đa {0} tệp mỗi lần.".format(C.MAX_FILES))
    for f in files or ():
        name = (f.get("name") or "").strip()
        if file_ext(name) not in C.FILE_EXTS:
            errs.append("Không nhận loại tệp này: {0}".format(name or "?"))
        elif (f.get("size") or 0) > C.FILE_MAX_BYTES:
            errs.append("Tệp quá {0} MB: {1}".format(C.FILE_MAX_BYTES // (1024 * 1024), name))
        elif not f.get("size"):
            errs.append("Tệp rỗng: {0}".format(name))
    if sum(int(f.get("size") or 0) for f in files or ()) > C.FILES_TOTAL_MAX_BYTES:
        errs.append("Tổng dung lượng tệp tối đa {0} MB.".format(C.FILES_TOTAL_MAX_BYTES // (1024 * 1024)))
    return errs


def clean_mentions(raw, limit=10):
    out = []
    for m in raw or ():
        m = (m or "").strip().lower() if isinstance(m, str) else ""
        if m and _EMAIL_RE.match(m) and m not in out:
            out.append(m)
    return out[:limit]


# ------------------------------------------------------------------ chuyen trang thai -----
#: (tu, toi) team Data duoc phep qua o "Cap nhat" (Cho tiep nhan -> Dang xu ly chi qua accept).
_TEAM_MOVES = {
    (C.ST_DOING, C.ST_PAUSED), (C.ST_PAUSED, C.ST_DOING),
    (C.ST_DOING, C.ST_REVIEW), (C.ST_PAUSED, C.ST_REVIEW),
    (C.ST_REVIEW, C.ST_DOING),
}


def can_team_move(cur, new):
    return cur == new or (cur, new) in _TEAM_MOVES


def check_due_change(old_due, new_due, reason, start=None):
    """Doi han: ly do bat buoc, khong truoc ngay bat dau."""
    errs = []
    if new_due is None:
        errs.append("Hạn không hợp lệ.")
    elif old_due != new_due and not (reason or "").strip():
        errs.append("Đổi hạn cần ghi lý do (người gửi sẽ thấy).")
    if new_due and start and new_due < start:
        errs.append("Hạn không được trước ngày bắt đầu.")
    return errs


def paused_working_days(paused_since, resumed_on, holidays=()):
    """So ngay lam viec da dung: ngay x voi ngay_dung < x <= ngay_tiep_tuc (dung + tiep tuc trong
    ngay = 0). Han cong them chung ay ngay khi tiep tuc."""
    a, b = as_date(paused_since), as_date(resumed_on)
    if not a or not b:
        return 0
    return working_days_between(a, b, holidays)


def extend_due(due, days, holidays=()):
    due = as_date(due)
    if not due or days <= 0:
        return due
    return add_working_days(due, days, holidays)


# ------------------------------------------------------------------ hien thi han / SLA ----
def effective_due(t):
    """Han dang tinh: Cho tiep nhan -> han nhan viec; con lai -> han xu ly."""
    if t.get("status") == C.ST_WAITING:
        return as_date(t.get("intake_due_date"))
    return as_date(t.get("due_date"))


def is_overdue(t, today):
    if t.get("status") not in (C.ST_WAITING, C.ST_DOING):
        return False
    d = effective_due(t)
    return bool(d) and d < today


def on_time(t):
    """Dung han = ngay team Data bam Hoan tat <= han da chot (ke ca han da doi co ly do)."""
    done, due = as_date(t.get("done_at")), as_date(t.get("due_date"))
    return bool(done and due and done <= due)


def sla_view(t, today, holidays=()):
    """-> {label, pct (0-100), css ('' | near | late | hold | done)} cho cot Han + thanh SLA nho."""
    st = t.get("status")
    if st == C.ST_CANCELLED:
        return {"label": "đã huỷ", "pct": 0, "css": "off"}
    if st == C.ST_DONE:
        lab = "xong " + fmt_date(t.get("done_at") or t.get("closed_at"))
        lab += " · đúng hạn" if on_time(t) else " · trễ hạn"
        return {"label": lab, "pct": 100, "css": "done"}
    if st == C.ST_REVIEW:
        return {"label": "xong " + fmt_date(t.get("done_at")) + " · chờ nghiệm thu", "pct": 100, "css": "done"}
    if st == C.ST_PAUSED:
        return {"label": fmt_date(t.get("due_date")) + " · SLA tạm dừng", "pct": _pct(t, today, holidays),
                "css": "hold"}
    due = effective_due(t)
    if not due:
        return {"label": "—", "pct": 0, "css": ""}
    if st == C.ST_WAITING:
        late = due < today
        return {"label": "hạn nhận " + fmt_date(due) + (" · trễ" if late else ""), "pct": 100 if late else 10,
                "css": "late" if late else ""}
    pct = _pct(t, today, holidays)
    if due < today:
        n = working_days_between(due, today, holidays) or (today - due).days
        return {"label": "%s · quá hạn %d ngày" % (fmt_date(due), n), "pct": 100, "css": "late"}
    left = working_days_between(today, due, holidays)
    if left == 0:
        return {"label": fmt_date(due) + " · hạn hôm nay", "pct": max(pct, 90), "css": "near"}
    css = "near" if left <= C.DUE_SOON_DAYS else ""
    return {"label": "%s · còn %d ngày" % (fmt_date(due), left), "pct": pct, "css": css}


def _pct(t, today, holidays):
    start, due = as_date(t.get("start_date")), as_date(t.get("due_date"))
    if not start or not due:
        return 0
    total = working_days_between(start, due, holidays) or 1
    used = working_days_between(start, min(today, due), holidays)
    return max(0, min(100, int(round(100.0 * used / total))))


def sort_key(t, today):
    """Danh sach: Khan truoc -> qua han -> han gan nhat; da dong xuong cuoi (moi dong truoc)."""
    if t.get("status") in C.CLOSED:
        closed = as_datetime(t.get("closed_at") or t.get("creation")) or _dt.datetime.min
        return (3, 0, 0, -closed.timestamp() if closed != _dt.datetime.min else 0, t.get("name") or "")
    urgent = 0 if t.get("priority") == C.PRI_URGENT or (
        t.get("status") == C.ST_WAITING and t.get("proposed_priority") == C.PRI_URGENT) else 1
    late = 0 if is_overdue(t, today) else 1
    due = effective_due(t) or _dt.date.max
    created = as_datetime(t.get("creation")) or _dt.datetime.max
    return (0 if t.get("status") != C.ST_REVIEW else 1, urgent, late, due.toordinal(),
            created.isoformat())


def sort_rows(rows, today):
    return sorted(rows, key=lambda t: (sort_key(t, today), t.get("name") or ""))


def queue_priority(t):
    """Muc dung de xep hang doi: muc team Data da chot, chua chot thi muc nguoi gui de xuat."""
    return t.get("priority") or t.get("proposed_priority") or C.PRI_NORMAL


def queue(tickets, members, today, holidays=(), rules=None):
    """Vi tri + ngay bat dau du kien cua yeu cau CHO TIEP NHAN. Cong thuc (README):

      1. Moi nguoi team Data ranh tu: max(hom nay (ngay lam viec), han muon nhat cua viec dang
         lam / tam dung cua ho). Viec da qua han coi nhu ranh tu hom nay.
      2. Yeu cau cho xep theo (muc uu tien, gio gui).
      3. Lan luot: giao cho nguoi ranh som nhat (bang nhau -> theo ten), bat dau du kien = ngay
         ranh do; nguoi do ranh lai tu ngay bat dau + N ngay lam viec (N = so ngay theo quy tac).
    Khong co ai trong team Data -> moi yeu cau xep sau nhau tren mot "lan" chung.
    -> {ma: {"position": i, "expected_start": date, "expected_due": date}}"""
    rules = rules or rules_view(None)
    base = default_start(today, holidays)
    free = {}
    for m in members or ():
        free[m] = base
    if not free:
        free[""] = base
    for t in tickets:
        who = t.get("assignee")
        if t.get("status") in (C.ST_DOING, C.ST_PAUSED) and who in free:
            due = as_date(t.get("due_date"))
            if due and due > free[who]:
                free[who] = due
    waiting = [t for t in tickets if t.get("status") == C.ST_WAITING and t.get("kind", C.KIND_REQUEST) == C.KIND_REQUEST]
    waiting.sort(key=lambda t: (C.PRIORITY_RANK.get(queue_priority(t), 9),
                                (as_datetime(t.get("creation")) or _dt.datetime.max).isoformat(), t.get("name") or ""))
    out = {}
    for i, t in enumerate(waiting, start=1):
        who = min(free, key=lambda m: (free[m], m))
        start = free[who]
        n = ticket_sla_days(rules, t.get("request_type"), queue_priority(t))
        due = add_working_days(start, n, holidays)
        free[who] = due
        out[t["name"]] = {"position": i, "expected_start": start, "expected_due": due, "sla_days": n}
    return out


# ------------------------------------------------------------------ KPI -------------------
def kpis(tickets, today):
    """5 o KPI tren /du-lieu (chi yeu cau du lieu - kind request)."""
    rows = [t for t in tickets if t.get("kind", C.KIND_REQUEST) == C.KIND_REQUEST]
    month = (today.year, today.month)
    done_month = [t for t in rows if t.get("status") == C.ST_DONE and as_date(t.get("closed_at"))
                  and (as_date(t.get("closed_at")).year, as_date(t.get("closed_at")).month) == month]
    ok = sum(1 for t in done_month if on_time(t))
    return {
        "doing": sum(1 for t in rows if t.get("status") == C.ST_DOING),
        "waiting": sum(1 for t in rows if t.get("status") == C.ST_WAITING),
        "overdue": sum(1 for t in rows if is_overdue(t, today)),
        "paused": sum(1 for t in rows if t.get("status") == C.ST_PAUSED),
        "review": sum(1 for t in rows if t.get("status") == C.ST_REVIEW),
        "done_month": len(done_month),
        "on_time_pct": int(round(100.0 * ok / len(done_month))) if done_month else None,
    }


# ------------------------------------------------------------------ Gantt -----------------
def gantt_window(today, start=None):
    """Thu Hai cua tuan truoc (hoac `start` da cho, keo ve thu Hai) + GANTT_DAYS ngay."""
    s = as_date(start) or (today - _dt.timedelta(days=7 * C.GANTT_BACK_WEEKS))
    s = s - _dt.timedelta(days=s.weekday())
    return s, s + _dt.timedelta(days=C.GANTT_DAYS - 1)


def gantt(tickets, members, names, today, holidays=(), start=None, q=None):
    """Du lieu Gantt: hang = tung nguoi team Data + "Chua phan cong" + "Da xong (7 ngay)".
    Thanh mang NGAY (iso) - JS tinh vi tri (ec_data_hub.bundle.js ganttLayout)."""
    w0, w1 = gantt_window(today, start)
    days = []
    d = w0
    while d <= w1:
        days.append({"date": d.isoformat(), "label": "%d/%d" % (d.day, d.month),
                     "off": not is_working_day(d, holidays), "today": d == today})
        d += _dt.timedelta(days=1)
    q = q or {}
    lanes, order = {}, []

    def lane(key, label):
        if key not in lanes:
            lanes[key] = {"key": key, "label": label, "bars": [], "n_req": 0, "n_da": 0}
            order.append(key)
        return lanes[key]

    for m in members or ():
        lane(m, names.get(m) or m)
    recent = today - _dt.timedelta(days=C.DONE_RECENT_DAYS)
    for t in tickets:
        st = t.get("status")
        if st == C.ST_CANCELLED:
            continue
        bar = {"code": t["name"], "title": t.get("title") or "", "kind": t.get("kind") or C.KIND_REQUEST,
               "status": st, "priority": t.get("priority") or t.get("proposed_priority") or "",
               "start": iso(t.get("start_date")), "due": iso(t.get("due_date")),
               "original_due": iso(t.get("original_due_date")), "css": ""}
        if st == C.ST_DONE:
            closed = as_date(t.get("closed_at"))
            if not closed or closed < recent:
                continue
            bar["css"] = "done"
            bar["due"] = iso(closed)       # hang "Da xong": thanh toi ngay dong (nghiem thu)
            target = lane("__done", "Đã xong (7 ngày)")
        elif st == C.ST_WAITING or not t.get("assignee"):
            info = q.get(t["name"]) or {}
            bar["start"] = iso(info.get("expected_start")) or iso(today)
            bar["due"] = iso(info.get("expected_due")) or bar["start"]
            bar["css"] = "wait"
            target = lane("__none", "Chưa phân công")
        else:
            if st == C.ST_REVIEW:
                bar["css"] = "done"
                bar["due"] = iso(t.get("done_at")) or bar["due"]
            elif st == C.ST_PAUSED:
                bar["css"] = "hold"
            elif is_overdue(t, today):
                bar["css"] = "late"
                bar["late_to"] = iso(today)
            else:
                bar["css"] = "run"
            if bar["kind"] == C.KIND_AVAILABILITY:
                bar["css"] = "da" if bar["css"] in ("run", "wait") else bar["css"]
            target = lane(t["assignee"], names.get(t["assignee"]) or t["assignee"])
        if not bar["start"]:
            bar["start"] = bar["due"] or iso(today)
        if not bar["due"]:
            bar["due"] = bar["start"]
        # Thanh nam han ngoai cua so -> bo (van dem vao so viec cua hang).
        end = bar.get("late_to") or bar["due"]
        inside = not (end < days[0]["date"] or bar["start"] > days[-1]["date"])
        if inside:
            target["bars"].append(bar)
        if bar["kind"] == C.KIND_AVAILABILITY:
            target["n_da"] += 1
        else:
            target["n_req"] += 1
    out = []
    for key in order:
        ln = lanes[key]
        if key == "__done" and not ln["bars"]:
            continue
        if key == "__none":
            ln["sub"] = "%d chờ nhận" % ln["n_req"] if ln["n_req"] else "không có"
        elif key == "__done":
            ln["sub"] = "%d việc" % len(ln["bars"])
        else:
            parts = ["%d yêu cầu" % ln["n_req"]]
            if ln["n_da"]:
                parts.append("%d bổ sung data" % ln["n_da"])
            ln["sub"] = " + ".join(parts)
        ln["bars"].sort(key=lambda b: (b["start"], b["code"]))
        out.append(ln)
    # "Chua phan cong" + "Da xong" luon o cuoi.
    out.sort(key=lambda ln: {"__none": 1, "__done": 2}.get(ln["key"], 0))
    return {"start": days[0]["date"], "end": days[-1]["date"], "today": today.isoformat(), "days": days,
            "lanes": out}


# ------------------------------------------------------------------ Dieu phoi ------------
def ops_columns(tickets, today):
    """4 cot kanban: Cho tiep nhan / Dang xu ly (+ Cho nghiem thu) / Tam dung / Xong 7 ngay."""
    cols = {"waiting": [], "doing": [], "paused": [], "done": []}
    recent = today - _dt.timedelta(days=C.DONE_RECENT_DAYS)
    for t in tickets:
        st = t.get("status")
        if st == C.ST_WAITING:
            cols["waiting"].append(t)
        elif st in (C.ST_DOING, C.ST_REVIEW):
            cols["doing"].append(t)
        elif st == C.ST_PAUSED:
            cols["paused"].append(t)
        elif st == C.ST_DONE and (as_date(t.get("closed_at")) or _dt.date.min) >= recent:
            cols["done"].append(t)
    cols["waiting"].sort(key=lambda t: (C.PRIORITY_RANK.get(queue_priority(t), 9),
                                        (as_datetime(t.get("creation")) or _dt.datetime.max).isoformat()))
    cols["doing"].sort(key=lambda t: sort_key(t, today))
    cols["paused"].sort(key=lambda t: sort_key(t, today))
    cols["done"].sort(key=lambda t: (as_datetime(t.get("closed_at")) or _dt.datetime.min), reverse=True)
    return cols
