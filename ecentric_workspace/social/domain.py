# Copyright (c) 2026, eCentric and contributors
"""Bang tin - quy tac THUAN (khong DB, khong frappe): ai thay bai nao, kiem du lieu bai / su kien /
CLB, nhan ngay gio, the bai. Test chay khong can bench."""
import datetime
import hashlib
import re

from ecentric_workspace.internal_posts import domain as ID
from ecentric_workspace.social import constants as C

WEEKDAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")
_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")
_SLUG_SRC = "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
_SLUG_DST = "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd"
_SLUG_MAP = {ord(a): b for a, b in zip(_SLUG_SRC, _SLUG_DST)}

as_date = ID.as_date
as_datetime = ID.as_datetime
ago = ID.ago


class SocialError(Exception):
    """Loi nguoi dung gay ra - api tra success False + thong diep nay."""


class Forbidden(SocialError):
    pass


class NotFound(SocialError):
    pass


# ------------------------------------------------------------------ nguoi --------
def initials(name):
    parts = [p for p in str(name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[-2][0] + parts[-1][0]).upper()


def avatar(user):
    """Mau avatar on dinh theo tai khoan (cung cong thuc voi binh luan Tin noi bo)."""
    return int(hashlib.md5(str(user or "").encode("utf-8")).hexdigest()[:2], 16) % C.AV_COLORS


def person(user, names, depts=None):
    nm = names.get(user) or user or ""
    return {"user": user, "name": nm, "initials": initials(nm), "av": avatar(user),
            "dept": (depts or {}).get(user) or ""}


def given(name):
    words = [w for w in str(name or "").split() if w]
    return words[-1] if words else ""


# ------------------------------------------------------------------ ai thay gi ---
def in_dept(tree, dept, viewer_lft):
    """Bai "Chi phong toi": phong cua bai VA cac phong con (cung luat Tin noi bo)."""
    lr = tree.get(dept) if dept else None
    if not lr or viewer_lft is None or lr[0] is None:
        return False
    return lr[0] <= viewer_lft <= lr[1]


def can_see(post, user, viewer_lft, tree, moderator=False):
    """post: dict co author / hidden / dept_only / department / kind."""
    if moderator:
        return True
    if post.get("hidden") and post.get("author") != user:
        return False
    if post.get("dept_only") and post.get("author") != user:
        return in_dept(tree, post.get("department"), viewer_lft)
    return True


# ------------------------------------------------------------------ kiem du lieu --
def clean_text(text, limit, empty_msg=None):
    t = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = "\n".join(_WS_RE.sub(" ", line).strip() for line in t.split("\n"))
    t = _NL_RE.sub("\n\n", t).strip()
    if not t and empty_msg:
        raise SocialError(empty_msg)
    if len(t) > limit:
        raise SocialError("Nội dung dài quá %d ký tự." % limit)
    return t


def kudos_label(value):
    return dict(C.KUDOS_VALUES).get(value or "", "")


def parse_event(data, now):
    """data: {event_title, event_start ('2026-10-12T06:00' / '2026-10-12 06:00'), event_place}."""
    title = clean_text(data.get("event_title"), C.EVENT_TITLE_MAX, "Sự kiện cần có tên.")
    start = as_datetime(data.get("event_start"))
    if not start:
        raise SocialError("Chọn ngày giờ diễn ra sự kiện.")
    if start < now - datetime.timedelta(minutes=5):
        raise SocialError("Ngày giờ sự kiện đã qua.")
    if start > now + datetime.timedelta(days=366):
        raise SocialError("Sự kiện xa quá một năm. Kiểm tra lại năm.")
    place = clean_text(data.get("event_place"), C.EVENT_PLACE_MAX)
    return {"event_title": title, "event_start": start.replace(second=0, microsecond=0), "event_place": place}


def slugify(text):
    t = str(text or "").lower().translate(_SLUG_MAP)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:50].strip("-") or "clb"


# ------------------------------------------------------------------ ngay gio -----
def date_block(v):
    d = as_datetime(v)
    if not d:
        return {"mon": "", "day": ""}
    return {"mon": "TH%d" % d.month, "day": "%02d" % d.day}


def event_when(v):
    """'06:00 Chủ Nhật 12/10'."""
    d = as_datetime(v)
    if not d:
        return ""
    return "%s %s %s" % (d.strftime("%H:%M"), WEEKDAYS[d.weekday()], d.strftime("%d/%m"))


def event_short(v):
    """'CN 12/10' / 'T5 09/10'."""
    d = as_datetime(v)
    if not d:
        return ""
    wd = "CN" if d.weekday() == 6 else "T%d" % (d.weekday() + 2)
    return "%s %s" % (wd, d.strftime("%d/%m"))


def event_state(v, now):
    """'soon' (chua dien ra) / 'live' (dang trong EVENT_PAST_GRACE_HOURS gio) / 'past'."""
    d = as_datetime(v)
    if not d:
        return "past"
    if d > now:
        return "soon"
    if now - d <= datetime.timedelta(hours=C.EVENT_PAST_GRACE_HOURS):
        return "live"
    return "past"


def ts(v):
    """Khoa sap xep / con tro "Xem them" (chuoi ISO, so sanh duoc). Giu micro giay: con tro cat ve giay
    thi bai cung giay voi bai cuoi trang bi bo qua (creation < con tro)."""
    d = as_datetime(v)
    return d.strftime("%Y-%m-%d %H:%M:%S.%f") if d else ""


def parse_cursor(v):
    d = as_datetime(v)
    return d if d else None


# ------------------------------------------------------------------ cam xuc ------
def rx_summary(rows, target, user, my_kind=C.RX_KIND):
    """rows EC Home Reaction cua MOT target -> {total, emojis, mine} (mine = toi da tha `my_kind`)."""
    total, kinds, mine = 0, [], False
    for r in rows:
        if r.get("target") != target:
            continue
        total += 1
        if r.get("kind") not in kinds:
            kinds.append(r.get("kind"))
        if r.get("user") == user and r.get("kind") == my_kind:
            mine = True
    order = [k for k in ("heart", "party", "flower", "cake") if k in kinds]
    return {"total": total, "emojis": "".join(C.RX_EMOJI[k] for k in order[:3]), "mine": mine}


def moment_kind(key):
    return str(key or "").split(":", 1)[0]
