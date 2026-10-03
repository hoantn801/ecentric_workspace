# Copyright (c) 2026, eCentric and contributors
"""Gop y cong ty - quy tac THUAN (khong frappe, khong DB). Service goi vao day; test chay thang.

Moi quy tac PO chot 04/10/2026 nam o mot cho:
  * gui: tieu de + noi dung + chu de + loai bat buoc, toi da 5 gop y / nguoi / ngay;
  * trang thai: Moi -> Dang xem -> Da tra loi / Da lam / Khong lam. "Da tra loi" va "Khong lam"
    bat buoc co loi nhan; nguoi gui mo lai ("Chua on") mot lan khi da dong;
  * han phan hoi dau: 5 ngay lam viec. CHI tra loi hoac chuyen sang trang thai ket qua moi dung
    dong ho - "Dang xem" thi khong (khong ai ne han bang cach bam Dang xem);
  * bang chung: chi gop y nguoi xu ly da dua len, chi hien tieu de + cau tra loi cong khai.
"""
import datetime as _dt
import re

from ecentric_workspace.feedback import constants as C

_WS_RE = re.compile(r"\s+")


class Invalid(Exception):
    """Du lieu nguoi dung sai - mang danh sach loi doc duoc."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


def clean_text(s, limit):
    """Chuan hoa chuoi nguoi nhap: bo khoang trang dau cuoi, gop dong trong lien tiep, cat do dai."""
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s[:limit] if limit else s


def one_line(s, limit):
    return _WS_RE.sub(" ", (s or "")).strip()[:limit]


def as_bool(v):
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


# ------------------------------------------------------------------ gui gop y ------
def normalize_submission(data, topics, sent_today):
    """data (dict tu trang) -> dict sach. Nem Invalid neu sai.

    topics = {ma: chu de dang dung}; sent_today = so gop y nguoi nay da gui hom nay."""
    errs = []
    title = one_line(data.get("title"), C.TITLE_MAX)
    body = clean_text(data.get("body"), C.BODY_MAX + 1)
    topic = (data.get("topic") or "").strip()
    kind = (data.get("kind") or C.KIND_DEFAULT).strip()
    if sent_today >= C.DAILY_LIMIT:
        errs.append("Hôm nay bạn đã gửi đủ {0} góp ý. Mai gửi tiếp nhé.".format(C.DAILY_LIMIT))
    if not title:
        errs.append("Chưa có tiêu đề.")
    if not body:
        errs.append("Chưa có nội dung.")
    elif len(body) > C.BODY_MAX:
        errs.append("Nội dung dài quá {0} ký tự.".format(C.BODY_MAX))
    if topic not in topics:
        errs.append("Chọn một chủ đề.")
    if kind not in C.KINDS:
        errs.append("Loại góp ý không hợp lệ.")
    if errs:
        raise Invalid(errs)
    return {"title": title, "body": body, "topic": topic, "kind": kind,
            "is_anonymous": 1 if as_bool(data.get("is_anonymous")) else 0}


def check_files(files, anonymous=False):
    """files = [{name, size}] -> loi (tep an toan de luu private). An danh: chi nhan anh."""
    errs = []
    allowed = C.ANON_FILE_EXTS if anonymous else C.FILE_EXTS
    if len(files or ()) > C.MAX_FILES:
        errs.append("Tối đa {0} tệp đính kèm.".format(C.MAX_FILES))
    for f in files or ():
        name = (f.get("name") or "").strip()
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in allowed:
            errs.append(("Gửi ẩn danh chỉ đính kèm được ảnh (tệp khác lưu tên tác giả bên trong): {0}"
                         if anonymous and ext in C.FILE_EXTS else "Không nhận loại tệp này: {0}").format(name or "?"))
        elif (f.get("size") or 0) > C.FILE_MAX_BYTES:
            errs.append("Tệp quá {0} MB: {1}".format(C.FILE_MAX_BYTES // (1024 * 1024), name))
        elif not f.get("size"):
            errs.append("Tệp rỗng: {0}".format(name))
    if sum(int(f.get("size") or 0) for f in files or ()) > C.FILES_TOTAL_MAX_BYTES:
        errs.append("Tổng dung lượng tệp tối đa {0} MB.".format(C.FILES_TOTAL_MAX_BYTES // (1024 * 1024)))
    return errs


# ------------------------------------------------------------------ trang thai -----
def file_ext(name):
    return name.rsplit(".", 1)[-1].lower() if "." in (name or "") else ""


def anon_file_name(i, name):
    """Ten tep cua gop y an danh: ten goc ("Screenshot lan.nguyen.png") co the lo nguoi gui."""
    ext = file_ext(name)
    return "anh-%d.%s" % (i + 1, "jpg" if ext == "jpeg" else ext)


def is_closed(status):
    return status in C.CLOSED


def check_handler_status(current, new, message):
    """Nguoi xu ly doi trang thai -> danh sach loi (rong = duoc)."""
    if new not in C.HANDLER_STATUSES:
        return ["Trạng thái không hợp lệ."]
    if new == current:
        return []
    if new in C.NEEDS_MESSAGE and not (message or "").strip():
        if new == C.ST_DECLINED:
            return ["Chuyển sang \"Không làm\" thì phải ghi lý do cho người gửi."]
        return ["Chuyển sang \"Đã trả lời\" thì phải có câu trả lời."]
    return []


def can_reopen(status, reopen_count):
    return is_closed(status) and int(reopen_count or 0) < C.REOPEN_MAX


def stops_clock(new_status, has_reply):
    """Hanh dong nay co tinh la PHAN HOI (dung dong ho han) khong."""
    return bool(has_reply) or new_status in C.CLOSED


# ------------------------------------------------------------------ han -----------
def sla_hours(hours_per_day):
    return C.SLA_DAYS * float(hours_per_day or 0)


def sla_state(fb, now, business_left_seconds, hours_per_day):
    """Trang thai han cua mot gop y -> {key: late|soon|ok|done, label, short}.

    business_left_seconds = so giay LAM VIEC con lai toi han (am khong co nghia: qua han thi
    truyen so giay lam viec da tre voi dau am)."""
    if fb.get("responded_at") or is_closed(fb.get("status")):
        return {"key": "done", "label": "Đã phản hồi", "short": "Đã phản hồi"}
    due = fb.get("due_at")
    if not due:
        return {"key": "ok", "label": "", "short": ""}
    day = max(1.0, float(hours_per_day or 8)) * 3600.0
    if business_left_seconds is not None and business_left_seconds < 0:
        days = int(-business_left_seconds // day) or 0
        if days >= 1:
            txt = "Quá {0} ngày".format(days)
        else:
            txt = "Quá {0} giờ".format(max(1, int(-business_left_seconds // 3600)))
        return {"key": "late", "label": "Quá hạn phản hồi · " + txt.split(" ", 1)[1], "short": txt}
    left = business_left_seconds if business_left_seconds is not None else day * C.SLA_DAYS
    if left <= day * C.REMIND_DAYS_LEFT:
        hours = max(1, int(left // 3600))
        return {"key": "soon", "label": "Còn {0} giờ làm việc tới hạn".format(hours),
                "short": "Còn {0} giờ".format(hours)}
    return {"key": "ok", "label": "Hạn phản hồi " + fmt_date(due), "short": "Hạn " + fmt_date(due)}


# ------------------------------------------------------------------ hien thi ------
def fmt_date(v):
    if not v:
        return ""
    if isinstance(v, str):
        try:
            v = _dt.datetime.fromisoformat(v[:19])
        except ValueError:
            return v[:10]
    return v.strftime("%d/%m")


def fmt_date_full(v):
    if not v:
        return ""
    if isinstance(v, str):
        try:
            v = _dt.datetime.fromisoformat(v[:19])
        except ValueError:
            return v[:10]
    return v.strftime("%d/%m/%Y")


def fmt_time(v, anonymous=False):
    """Gio phut cua mot moc. Gop y AN DANH chi hien ngay: gio phut + ai dang online = lo nguoi gui."""
    if not v:
        return ""
    if anonymous:
        return fmt_date(v)
    if isinstance(v, str):
        try:
            v = _dt.datetime.fromisoformat(v[:19])
        except ValueError:
            return v[:16]
    return v.strftime("%H:%M %d/%m")


def topic_view(t):
    color = t.get("color") if t.get("color") in C.COLORS else C.COLOR_DEFAULT
    bg, ink = C.COLORS[color]
    return {"name": t.get("name"), "label": t.get("topic_name") or t.get("name"), "hint": t.get("hint") or "",
            "icon": t.get("icon") if t.get("icon") in C.ICONS else C.ICONS[0], "bg": bg, "ink": ink,
            "enabled": int(t.get("enabled") if t.get("enabled") is not None else 1)}


def steps(fb):
    """Thanh tien do 3 buoc cho nguoi gui: Da gui -> Dang xem -> ket qua."""
    st = fb.get("status")
    final = st if st in C.CLOSED else "Có kết quả"
    viewed = st != C.ST_NEW
    return [
        {"label": "Đã gửi", "date": fmt_date(fb.get("creation")), "done": True, "current": st == C.ST_NEW},
        {"label": C.ST_VIEWING, "date": fmt_date(fb.get("viewed_at")) if viewed else "", "done": viewed,
         "current": st == C.ST_VIEWING},
        {"label": final, "date": fmt_date(fb.get("closed_at")) if st in C.CLOSED else "",
         "done": st in C.CLOSED, "current": st in C.CLOSED},
    ]


def sender_label(fb, names):
    """Ten nguoi gui hien cho NGUOI XU LY. An danh -> "An danh", khong bao gio la ten."""
    if fb.get("is_anonymous"):
        return "Ẩn danh"
    user = fb.get("submitter")
    return names.get(user) or user or "Ẩn danh"


def board_card(fb, topic_map, my_votes):
    """The tren bang chung - CHI cac truong cong khai (khong noi dung goc, khong nguoi gui)."""
    t = topic_map.get(fb.get("topic")) or {}
    votes = int(fb.get("vote_count") or 0)
    return {"name": fb["name"], "title": fb.get("public_title") or "", "answer": fb.get("public_answer") or "",
            "status": fb.get("status"), "status_css": C.STATUS_CSS.get(fb.get("status"), "new"),
            "topic": t.get("label") or "", "date": fmt_date(fb.get("public_on") or fb.get("creation")),
            "votes": votes, "voted": fb["name"] in my_votes, "hot": votes >= C.HOT_VOTES}


def board_sort(cards, sort):
    if sort == "moi-nhat":
        return cards
    return sorted(cards, key=lambda c: -c["votes"])


# ------------------------------------------------------------------ tong quan -----
def month_range(month):
    """'2026-10' -> (date dau thang, date dau thang sau). Sai dinh dang -> None."""
    m = re.match(r"^(\d{4})-(\d{2})$", month or "")
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if not 1 <= mo <= 12:
        return None
    start = _dt.date(y, mo, 1)
    end = _dt.date(y + (mo == 12), 1 if mo == 12 else mo + 1, 1)
    return start, end


def prev_month(d):
    first = d.replace(day=1)
    last_prev = first - _dt.timedelta(days=1)
    return last_prev.strftime("%Y-%m")


def stats(rows, now, topic_map, response_seconds):
    """Thong ke mot ky tu cac gop y TAO trong ky.

    rows = [{name, topic, status, is_anonymous, due_at, first_response_at, vote_count}];
    response_seconds = {name: so giay lam viec tu luc gui toi phan hoi dau}."""
    total = len(rows)
    anon = sum(1 for r in rows if r.get("is_anonymous"))
    # Dung han: chi xet gop y DA toi han hoac DA phan hoi (gop y moi gui hom qua chua "tre" duoc).
    judged, on_time = 0, 0
    overdue = []
    for r in rows:
        fr, due = r.get("first_response_at"), r.get("due_at")
        if fr and due:
            judged += 1
            on_time += 1 if fr <= due else 0
        elif due and due < now:
            judged += 1
            overdue.append(r["name"])
    secs = [v for v in response_seconds.values() if v is not None]
    by_topic = {}
    for r in rows:
        key = r.get("topic") or ""
        b = by_topic.setdefault(key, {"topic": (topic_map.get(key) or {}).get("label") or key, "total": 0,
                                      "done": 0, "open": 0, "declined": 0})
        b["total"] += 1
        st = r.get("status")
        if st in (C.ST_DONE, C.ST_ANSWERED):
            b["done"] += 1
        elif st == C.ST_DECLINED:
            b["declined"] += 1
        else:
            b["open"] += 1
    topics = sorted(by_topic.values(), key=lambda b: -b["total"])
    top = max([b["total"] for b in topics] or [1])
    for b in topics:
        b["pct"] = int(round(100.0 * b["total"] / top)) if top else 0
        b["done_pct"] = _pct(b["done"], b["total"]) * b["pct"] // 100
        b["open_pct"] = _pct(b["open"], b["total"]) * b["pct"] // 100
        b["declined_pct"] = _pct(b["declined"], b["total"]) * b["pct"] // 100
    return {"total": total, "anonymous": anon, "on_time_pct": _pct(on_time, judged) if judged else None,
            "judged": judged, "overdue_count": len(overdue),
            "avg_response_hours": round(sum(secs) / len(secs) / 3600.0, 1) if secs else None,
            "topics": topics}


def _pct(a, b):
    return int(round(100.0 * a / b)) if b else 0


def digest_prompt(items):
    """Loi nhac cho AI gom chu de nong. CHI tieu de + noi dung + so +1: khong ten, khong phong ban."""
    lines = []
    used = 0
    for it in items:
        line = "- [{0} +1] {1}: {2}".format(int(it.get("vote_count") or 0), one_line(it.get("title"), 140),
                                             one_line(it.get("body"), 600))
        if used + len(line) > C.AI_TEXT_MAX_CHARS:
            break
        lines.append(line)
        used += len(line)
    return ("Dưới đây là các góp ý nhân viên gửi Ban Giám đốc trong tháng (mỗi dòng: số người +1, tiêu đề, nội "
            "dung). Gom thành tối đa {0} chủ đề được nhắc nhiều nhất. Mỗi chủ đề: tên ngắn (≤ 6 từ), số góp ý "
            "thuộc chủ đề, một câu tóm tắt vấn đề. Không nêu tên người, không đoán ai gửi. Trả JSON.\n\n{1}"
            ).format(C.DIGEST_HOT_MAX, "\n".join(lines))


DIGEST_SCHEMA = {
    "type": "object",
    "properties": {"topics": {"type": "array", "items": {
        "type": "object",
        "properties": {"name": {"type": "string"}, "count": {"type": "integer"}, "summary": {"type": "string"}},
        "required": ["name", "count", "summary"]}}},
    "required": ["topics"],
}


def clean_hot(data):
    """Ket qua AI -> danh sach chu de nong an toan de luu / hien."""
    out = []
    for t in (data or {}).get("topics") or []:
        if not isinstance(t, dict):
            continue
        name = one_line(str(t.get("name") or ""), 60)
        if not name:
            continue
        try:
            count = max(0, int(t.get("count") or 0))
        except (TypeError, ValueError):
            count = 0
        out.append({"name": name, "count": count, "summary": one_line(str(t.get("summary") or ""), 240)})
        if len(out) >= C.DIGEST_HOT_MAX:
            break
    return out
