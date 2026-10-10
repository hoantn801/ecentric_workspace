# Copyright (c) 2026, eCentric and contributors
"""Tin noi bo - quy tac THUAN (khong frappe, khong DB). Test chay khong can bench.

Cac quy tac quan trong deu nam o day de MOT noi quyet dinh:
  * ai nam trong pham vi mot bai (toan cong ty / phong ban + phong con)  -> in_scope()
  * bai nao hien o danh sach (da dang, chua het han)                      -> listed()
  * bai nao doc duoc qua link (da dang; het han van doc duoc)            -> readable()
  * mot bai luu co hop le khong                                           -> validate()
  * so nguoi da xem / chua xem (va da xac nhan / chua)                   -> seen_summary()
  * gio hen dang hop le khong, khi nao tu nhac xac nhan                   -> check_schedule(), ack_*()
"""
import datetime
import html as _html
import re
import unicodedata

from ecentric_workspace.internal_posts import constants as C

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_H2_RE = re.compile(r"<h2(\s[^>]*)?>(.*?)</h2\s*>", re.I | re.S)
_ID_ATTR_RE = re.compile(r"\sid\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)


# ------------------------------------------------------------------ chu / ngay ----
def as_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def date_label(v):
    d = as_date(v)
    return d.strftime("%d/%m/%Y") if d else ""


def short_date(v):
    d = as_date(v)
    return d.strftime("%d/%m") if d else ""


def as_datetime(v):
    """'2026-10-06 08:30:00' / datetime -> datetime (khong mui gio: gio he thong = gio VN)."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime.datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, datetime.date):
        return datetime.datetime(v.year, v.month, v.day)
    t = str(v).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def when_label(v):
    """'08:30 thứ Hai 06/10' (mockup v6: gio hen dang)."""
    d = as_datetime(v)
    if not d:
        return ""
    return "%s %s %s" % (d.strftime("%H:%M"), C.WEEKDAYS[d.weekday()][0].lower() + C.WEEKDAYS[d.weekday()][1:],
                         d.strftime("%d/%m"))


def short_when(v):
    """'08:30 · T2 06/10' (bang quan ly)."""
    d = as_datetime(v)
    if not d:
        return ""
    wd = "CN" if d.weekday() == 6 else "T%d" % (d.weekday() + 2)
    return "%s · %s %s" % (d.strftime("%H:%M"), wd, d.strftime("%d/%m"))


def ago(v, now):
    """'vừa xong' / '5 phút trước' / '2 giờ trước' / 'hôm qua' / '28/09' (binh luan)."""
    d = as_datetime(v)
    if not d or not now:
        return ""
    sec = (now - d).total_seconds()
    if sec < 60:
        return "vừa xong"
    if sec < 3600:
        return "%d phút trước" % int(sec // 60)
    if sec < 86400 and d.date() == now.date():
        return "%d giờ trước" % int(sec // 3600)
    if (now.date() - d.date()).days == 1:
        return "hôm qua lúc " + d.strftime("%H:%M")
    return d.strftime("%d/%m/%Y" if d.year != now.year else "%d/%m")


def plain_text(html, limit=None):
    """HTML -> chu tron (de AI doc, de tim, de tinh thoi gian doc)."""
    t = _TAG_RE.sub(" ", str(html or ""))
    t = _WS_RE.sub(" ", _html.unescape(t)).strip()
    if limit and len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t


def slugify(text):
    """'Lịch nghỉ Tết 2027!' -> 'lich-nghi-tet-2027'. Chi a-z 0-9 va gach ngang."""
    t = str(text or "").replace("đ", "d").replace("Đ", "D")
    t = unicodedata.normalize("NFD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    t = t[:C.SLUG_MAX].strip("-")
    return t


def unique_slug(wanted, taken):
    """`taken(slug) -> bool`. Slug trung hoac nam trong RESERVED_SLUGS -> them -2, -3..."""
    base = slugify(wanted) or "bai-viet"
    cand, n = base, 1
    while cand in C.RESERVED_SLUGS or taken(cand):
        n += 1
        suffix = "-%d" % n
        cand = base[:C.SLUG_MAX - len(suffix)].rstrip("-") + suffix
    return cand


# ------------------------------------------------------------------ noi dung ------
def add_heading_ids(html):
    """Gan id cho moi <h2> (muc luc o cot phai) -> (html_moi, [{id, text}]).

    Chay SAU khi lam sach HTML: id do server dat (muc-1, muc-2...), id cu cua nguoi soan
    bi bo de khong trung / khong tro lung tung."""
    toc = []

    def repl(m):
        text = plain_text(m.group(2))
        if not text:
            return m.group(0)
        hid = "muc-%d" % (len(toc) + 1)
        toc.append({"id": hid, "text": text})
        attrs = _ID_ATTR_RE.sub("", m.group(1) or "")
        return '<h2 id="%s"%s>%s</h2>' % (hid, attrs, m.group(2))

    return _H2_RE.sub(repl, str(html or "")), toc


def reading_minutes(html):
    words = len(plain_text(html).split())
    return max(1, int(round(words / 220.0)))


# ------------------------------------------------------------------ pham vi -------
def in_scope(selected, viewer_lft):
    """selected: [(lft, rgt)] cua cac phong ban duoc chon; rong = toan cong ty.

    Phong cha bao gom phong con (PO chot 01/10): phong D chua phong E khi
    D.lft <= E.lft <= D.rgt (cay Department cua Frappe la nested set)."""
    if not selected:
        return True
    if viewer_lft is None:
        return False
    for lft, rgt in selected:
        if lft is not None and rgt is not None and lft <= viewer_lft <= rgt:
            return True
    return False


def expired(post, today):
    exp = as_date(post.get("expires_on"))
    return bool(exp and exp < today)


def readable(post, viewer_lft, selected, is_editor):
    """Doc qua link: nguoi soan doc moi bai; nhan vien doc bai DA DANG trong pham vi
    (het han van doc duoc - chi rut khoi danh sach)."""
    if is_editor:
        return True
    return bool(post.get("published")) and in_scope(selected, viewer_lft)


def listed(post, viewer_lft, selected, is_editor, today):
    """Hien o danh sach / trang chu. Nguoi soan thay ca nhap + het han (co nhan rieng)."""
    if is_editor:
        return True
    return readable(post, viewer_lft, selected, False) and not expired(post, today)


def reach(selected, employee_lfts):
    """So nguoi trong pham vi (trang viet bai: "Bai se toi N nguoi")."""
    return sum(1 for lft in employee_lfts if in_scope(selected, lft))


# ------------------------------------------------------------------ hop le --------
def validate(post, today, category_exists, dept_count):
    """-> danh sach loi (tieng Viet, hien thang cho nguoi soan). Rong = hop le.

    post: dict cac truong; category_exists(name) -> bool; dept_count = so phong da chon."""
    errs = []
    if not str(post.get("title") or "").strip():
        errs.append("Bài cần có tiêu đề.")
    if post.get("category") and not category_exists(post.get("category")):
        errs.append("Chuyên mục không tồn tại.")
    elif post.get("published") and not post.get("category"):
        errs.append("Chọn một chuyên mục.")
    if post.get("scope") == "dept" and dept_count == 0:
        errs.append("Chọn ít nhất một phòng ban, hoặc để bài cho toàn công ty.")
    exp = as_date(post.get("expires_on"))
    if exp and post.get("published") and exp < today and not post.get("_was_published"):
        errs.append("Ngày hết hạn đã qua - bài sẽ không hiện ở đâu cả.")
    color = post.get("cover_color")
    if color and color not in C.COVER_COLORS:
        errs.append("Màu ảnh bìa không hợp lệ.")
    if post.get("cover_kind") == C.COVER_KIND_IMAGE and not post.get("cover_image"):
        errs.append("Chọn ảnh bìa, hoặc chuyển sang Màu nền.")
    return errs


def check_schedule(publish_at, now):
    """Gio hen dang (trang viet bai). -> loi (chuoi) hoac "" neu hop le."""
    at = as_datetime(publish_at)
    if not at:
        return "Chọn ngày và giờ đăng."
    if at <= now:
        return "Giờ hẹn đã qua. Chọn giờ muộn hơn, hoặc chọn Đăng ngay."
    if at > now + datetime.timedelta(days=C.SCHEDULE_MAX_DAYS):
        return "Chỉ hẹn được trong %d ngày tới." % C.SCHEDULE_MAX_DAYS
    return ""


def check_dates(post, today):
    """Han hien / han xac nhan so voi ngay bai LEN (hen gio: ngay hen; khong: hom nay)."""
    errs = []
    start = (as_datetime(post.get("publish_at")) or datetime.datetime(today.year, today.month, today.day)).date()
    exp = as_date(post.get("expires_on"))
    if exp and post.get("publish_at") and exp < start:
        errs.append("Ngày hết hạn đang trước ngày hẹn đăng.")
    if post.get("require_ack"):
        dl = as_date(post.get("ack_deadline"))
        if not dl:
            errs.append("Chọn hạn xác nhận đã đọc.")
        elif dl < start and not post.get("_was_published"):
            errs.append("Hạn xác nhận phải từ ngày bài lên trở đi.")
    return errs


def ack_remind_dates(deadline):
    """Ngay ERP tu nhac nguoi chua xac nhan: 1 ngay truoc han + dung ngay han."""
    dl = as_date(deadline)
    if not dl:
        return []
    return [dl - datetime.timedelta(days=C.ACK_REMIND_DAYS_BEFORE), dl]


def ack_remind_due(deadline, today):
    return today in ack_remind_dates(deadline)


def ack_days_left(deadline, today):
    """'còn 7 ngày' / 'hôm nay là hạn' / 'quá hạn 2 ngày'."""
    dl = as_date(deadline)
    if not dl:
        return ""
    n = (dl - today).days
    if n > 0:
        return "còn %d ngày" % n
    if n == 0:
        return "hôm nay là hạn"
    return "quá hạn %d ngày" % -n


def popup_allowed(dept_count):
    """Popup "Hom nay o eCentric" hien cho MOI nguoi -> chi bai toan cong ty."""
    return dept_count == 0


def popup_window(today, expires_on):
    start = today
    end = as_date(expires_on) or (today + datetime.timedelta(days=C.POPUP_DAYS - 1))
    if end < start:
        end = start
    return start, end


# ------------------------------------------------------------------ hien thi ------
def cover(post, category):
    """Anh bia de ve: anh that, hoac nen mau + bieu tuong chuyen muc."""
    category = category or {}
    if post.get("cover_kind") == C.COVER_KIND_IMAGE and post.get("cover_image"):
        return {"kind": "image", "image": post.get("cover_image"), "icon": "", "color": ""}
    color = post.get("cover_color") or category.get("color") or C.COVER_COLOR_DEFAULT
    if color not in C.COVER_COLORS:
        color = C.COVER_COLOR_DEFAULT
    show_icon = post.get("cover_icon")
    show_icon = True if show_icon is None else bool(int(show_icon))
    return {"kind": "color", "image": "", "color": color,
            "icon": (category.get("icon") or C.ICON_DEFAULT) if show_icon else ""}


def category_view(row):
    if not row:
        return {"slug": "", "name": "", "color": C.COVER_COLOR_DEFAULT, "icon": C.ICON_DEFAULT}
    color = row.get("color") if row.get("color") in C.COVER_COLORS else C.COVER_COLOR_DEFAULT
    return {"slug": row.get("name") or row.get("slug"), "name": row.get("category_name") or row.get("name"),
            "color": color, "icon": row.get("icon") if row.get("icon") in C.ICONS else C.ICON_DEFAULT,
            "home_category": row.get("home_category") or C.HOME_CATEGORY_DEFAULT}


def card(post, categories, seen, today, scope_label="", author="", acked=None):
    """Mot the bai cho danh sach / trang chu. `seen` = tap ten bai nguoi xem da mo;
    `acked` = tap ten bai nguoi xem da bam xac nhan (None = khong tinh nhan "Can xac nhan")."""
    cat = category_view(categories.get(post.get("category")))
    pub = post.get("published_on") or post.get("creation")
    return {
        "name": post.get("name"), "slug": post.get("slug"),
        "url": "%s/%s" % (C.ROUTE, post.get("slug")),
        "title": post.get("title") or "", "summary": post.get("summary") or "",
        "category": cat, "pinned": bool(post.get("pinned")),
        "date": as_date(pub), "date_label": date_label(pub), "short_date": short_date(pub),
        "draft": not post.get("published"), "expired": expired(post, today),
        "expires_label": date_label(post.get("expires_on")),
        "unseen": bool(post.get("published")) and post.get("name") not in seen and not expired(post, today),
        "scope_label": scope_label, "author": author, "legacy": False, "audience": "",
        "cover": cover(post, categories.get(post.get("category"))),
        "scheduled": not post.get("published") and bool(post.get("publish_at")),
        "need_ack": (acked is not None and bool(post.get("published")) and bool(post.get("require_ack"))
                     and post.get("name") not in acked),
        "ack_deadline_label": short_date(post.get("ack_deadline")),
        "survey_badge": None,          # service._cards dien (khao sat kem bai)
    }


def legacy_card(guide, category):
    """Bai huong dan cu (guides.registry, trang tinh /huong-dan/<slug>) - hien chung chuyen muc."""
    upd = as_date(guide.get("updated"))
    return {
        "name": "guide:" + str(guide.get("slug") or guide.get("route")), "slug": "",
        "url": guide.get("route"), "title": guide.get("title") or "",
        "summary": guide.get("summary") or "", "category": category_view(category),
        "pinned": False, "date": upd, "date_label": date_label(upd), "short_date": short_date(upd),
        "draft": False, "expired": False, "expires_label": "", "unseen": False,
        "scope_label": "", "author": "", "legacy": True, "audience": guide.get("audience") or "",
        "cover": cover({}, category), "scheduled": False, "need_ack": False, "ack_deadline_label": "",
        "survey_badge": None,
    }


def sort_cards(cards):
    """Bai ghim truoc, roi moi nhat truoc."""
    return sorted(cards, key=lambda c: (0 if c["pinned"] else 1,
                                        -(c["date"].toordinal() if c["date"] else 0)))


def home_cards(cards, limit=C.HOME_MAX):
    """Trang chu (PO chot 6a): bai ghim truoc roi bai moi nhat; khong nhap, khong het han."""
    live = [c for c in cards if not c["draft"] and not c["expired"] and not c["legacy"]]
    return sort_cards(live)[:limit]


def sections(cards, categories_ordered):
    """Trang "Tat ca" (huong C): moi chuyen muc mot hang, SECTION_SIZE bai moi nhat."""
    out = []
    for cat in categories_ordered:
        items = sort_cards([c for c in cards if c["category"]["slug"] == cat["slug"]])
        if items:
            # "cards", khong phai "items": trong Jinja s.items la ham dict.items()
            out.append({"category": cat, "total": len(items), "cards": items[:C.SECTION_SIZE]})
    return out


def featured(cards):
    """Dau trang: bai ghim moi nhat (neu co) + FEATURE_SIDE bai moi nhat con lai."""
    ordered = sort_cards([c for c in cards if not c["legacy"]])
    pin = next((c for c in ordered if c["pinned"]), None)
    rest = [c for c in ordered if c is not pin and not c["draft"] and not c["expired"]]
    rest.sort(key=lambda c: -(c["date"].toordinal() if c["date"] else 0))
    return pin, rest[:C.FEATURE_SIDE]


def seen_summary(audience, seen_users, full_names, me, is_editor):
    """audience: tap user trong pham vi; seen_users: tap user da mo bai.

    Ai cung thay con so + vai ten nguoi DA xem; ten nguoi CHUA xem chi nguoi soan thay."""
    audience = set(audience or ())
    seen = [u for u in (seen_users or ()) if u in audience]
    seen_set = set(seen)
    not_seen = sorted(audience - seen_set, key=lambda u: (full_names.get(u) or u).lower())
    others = [u for u in seen if u != me]
    out = {
        "total": len(audience), "seen": len(seen_set), "not_seen": len(audience) - len(seen_set),
        "pct": int(round(100.0 * len(seen_set) / len(audience))) if audience else 0,
        "faces": [{"name": full_names.get(u) or u} for u in others[:C.SEEN_FACES]],
        "me_in_audience": me in audience, "me_seen": me in seen_set,
        "not_seen_names": [], "not_seen_more": 0,
    }
    if is_editor:
        names = [full_names.get(u) or u for u in not_seen]
        out["not_seen_names"] = names[:30]
        out["not_seen_more"] = max(0, len(names) - 30)
    return out


def seen_line(summary):
    """'Lan, Minh và 20 người khác' - chi ten nguoi DA xem."""
    faces = [f["name"] for f in summary.get("faces") or []]
    if not faces:
        return ""
    shown = faces[:2]
    more = summary["seen"] - len(shown) - (1 if summary.get("me_seen") else 0)
    head = ", ".join(_given(n) for n in shown)
    return head + (" và %d người khác" % more if more > 0 else "")


def who_line(names, total, me_reacted):
    """Ai da tha cam xuc: 'Lan, Minh và 5 người khác' (tinh ca nhung nguoi tha nhieu loai 1 lan
    theo ten; `total` la tong luot tha nen chi dung khi khong co ten)."""
    shown = [_given(n) for n in (names or [])[:2] if _given(n)]
    if me_reacted:
        shown = ["Bạn"] + shown[:1]
    people = len(names or []) + (1 if me_reacted else 0)
    if not shown:
        return ""
    more = people - len(shown)
    return ", ".join(shown) + (" và %d người khác" % more if more > 0 else "")


def _given(name):
    parts = str(name or "").split()
    return parts[-1] if parts else ""


def initials(name):
    parts = [p for p in str(name or "").split() if p]
    if not parts:
        return "?"
    return (parts[-1][0]).upper()
