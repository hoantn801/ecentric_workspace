# Copyright (c) 2026, eCentric and contributors
"""Popup "Hom nay o eCentric" - phan TINH TOAN THUAN (khong import frappe).

Moi ham nhan du lieu da doc san (dict) + ngay hom nay, tra dict/list san sang gui ve trinh
duyet. Tach rieng de test khong can bench (tests/test_domain.py) va de repository/service
khong phai chua quy tac nghiep vu.

Du lieu ca nhan: ngay sinh CHI ra khoi day duoi dang ngay/thang (vd "01/10") - khong bao gio
co nam sinh hay tuoi trong ket qua (brief NHIEU_LOP/brief_popup_su_kien.md, luat du lieu).
"""
import datetime
import re

from ecentric_workspace.home_today import constants as C

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ------------------------------------------------------------------ ngay thang ----
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


def _on_year(d, year):
    """Ngay d (thang/ngay) trong nam `year`. 29/02 o nam khong nhuan -> 28/02."""
    try:
        return d.replace(year=year)
    except ValueError:
        return datetime.date(year, 2, 28)


def next_occurrence(d, today):
    """Lan toi (>= hom nay) cua ngay/thang trong d."""
    d = as_date(d)
    if not d:
        return None
    nxt = _on_year(d, today.year)
    if nxt < today:
        nxt = _on_year(d, today.year + 1)
    return nxt


def dm(d):
    return "%02d/%02d" % (d.day, d.month)


def weekday(d):
    return C.WEEKDAYS[d.weekday()]


def full_label(d):
    return "%s, %02d/%02d/%d" % (weekday(d), d.day, d.month, d.year)


# ------------------------------------------------------------------ nguoi --------
def initials(name):
    words = [w for w in (name or "").split() if w]
    return "".join(w[0] for w in words[-2:]).upper() or "?"


def given_name(name):
    words = [w for w in (name or "").split() if w]
    return words[-1] if words else ""


def color_index(key, n=7):
    """Mau avatar on dinh theo ma nhan vien (cung nguoi -> cung mau moi ngay)."""
    return sum(ord(c) for c in str(key or "")) % n


def first_name_of(emp):
    """TEN goi (PO 29/09 16:32: chuc mung theo TEN, khong theo ho). Ho so nhan vien tren ERP ghi
    theo thu tu Ten - Dem - Ho ("Vinh Dinh Khanh Vu") -> lay Employee.first_name (chu dau); chua
    co first_name thi chu dau cua employee_name."""
    for v in (emp.get("first_name"), emp.get("employee_name"), emp.get("name")):
        words = [w for w in (v or "").split() if w]
        if words:
            return words[0]
    return ""


def person(emp, dept_names):
    dept = emp.get("department") or ""
    dept_label = dept_names.get(dept) or dept
    role = " · ".join(x for x in (emp.get("designation") or "", dept_label) if x)
    name = (emp.get("employee_name") or emp.get("name") or "").strip()
    given = first_name_of(emp)
    words = [w for w in name.split() if w]
    ini = ((given[:1] + (words[-1][:1] if len(words) > 1 else "")).upper()) or initials(name)
    return {"emp": emp.get("name"), "name": name, "given": given, "role": role,
            "initials": ini, "color": color_index(emp.get("name"))}


def bd_key(emp, today):
    return "bd:%s:%d" % (emp, today.year)


def ann_key(emp, today):
    return "ann:%s:%d" % (emp, today.year)


def new_key(nsp):
    return "new:%s" % nsp


# ------------------------------------------------------------------ sinh nhat ----
def birthdays(employees, today, dept_names, days_ahead=C.BIRTHDAY_DAYS_AHEAD):
    """(hom_nay, sap_toi). Chi nhan vien co ngay sinh; sap_toi xep theo ngay gan nhat.
    KHONG dua nam sinh / tuoi ra ngoai - chi ngay/thang."""
    today_list, soon = [], []
    for e in employees:
        nxt = next_occurrence(e.get("date_of_birth"), today)
        if not nxt:
            continue
        off = (nxt - today).days
        if off > days_ahead:
            continue
        p = person(e, dept_names)
        p["department"] = e.get("department") or ""
        if off == 0:
            p["key"] = bd_key(e.get("name"), today)
            today_list.append(p)
        else:
            p.update({"date": dm(nxt), "weekday": weekday(nxt), "offset": off})
            soon.append(p)
    today_list.sort(key=lambda p: p["name"])
    soon.sort(key=lambda p: (p["offset"], p["name"]))
    return today_list, soon


def anniversaries(employees, today, dept_names):
    """Ai tron N nam (N >= 1) lam o cong ty dung hom nay."""
    out = []
    for e in employees:
        j = as_date(e.get("date_of_joining"))
        if not j or j.year >= today.year or _on_year(j, today.year) != today:
            continue
        p = person(e, dept_names)
        p.update({"key": ann_key(e.get("name"), today), "years": today.year - j.year,
                  "joined": "%02d/%02d/%d" % (j.day, j.month, j.year)})
        out.append(p)
    out.sort(key=lambda p: (-p["years"], p["name"]))
    return out


# ------------------------------------------------------------------ nghi le -----
def plain_text(html, limit=None):
    t = _WS_RE.sub(" ", _TAG_RE.sub(" ", html or "")).strip()
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        t = t.replace(a, b)
    if limit and len(t) > limit:
        t = t[:limit - 1].rstrip() + "…"
    return t


def holidays(rows, today, limit=C.HOLIDAY_MAX):
    """Ngay nghi le sap toi (bo ngay nghi tuan). Trung ten lien tiep (Tet nghi 5 ngay) ->
    gop thanh 1 dong, ghi so ngay nghi."""
    items = []
    for r in sorted(rows, key=lambda r: as_date(r.get("holiday_date")) or today):
        d = as_date(r.get("holiday_date"))
        if not d or d < today or r.get("weekly_off"):
            continue
        name = plain_text(r.get("description")) or "Ngày nghỉ lễ"
        last = items[-1] if items else None
        if last and last["name"] == name and (d - last["_end"]).days <= 3:
            last["_end"] = d
            last["days_off"] += 1
            continue
        items.append({"name": name, "_end": d, "days_off": 1, "day": "%02d" % d.day,
                      "month": "TH %d" % d.month, "date_label": full_label(d),
                      "days_left": (d - today).days})
    for it in items:
        it.pop("_end", None)
    return items[:limit]


# ------------------------------------------------------------------ thong bao ---
def _safe_link(v):
    """Chi nhan duong dan trong site (/...) hoac http(s) - khong 'javascript:'."""
    v = (v or "").strip()
    if v.startswith("/") and not v.startswith("//"):
        return v
    if v.lower().startswith(("https://", "http://")):
        return v
    return ""


def announcements(rows, today, limit=C.NEWS_MAX):
    """Thong bao trang chu dang trong han (ngay bat dau <= hom nay <= ngay ket thuc; trong =
    7 ngay). "Chi anh" -> poster (o rieng, anh full); con lai gop vao o Thong bao."""
    out = []
    for r in rows:
        if not r.get("published"):
            continue
        start = as_date(r.get("start_date"))
        end = as_date(r.get("end_date")) or (start and start + datetime.timedelta(days=C.NEWS_DEFAULT_DAYS - 1))
        if not start or start > today or (end and end < today):
            continue
        tag, label = C.NEWS_TAGS.get((r.get("category") or "").strip(), C.NEWS_TAG_DEFAULT)
        img = r.get("image") or ""
        img = img if img.startswith("/files/") else ""
        poster = bool(img) and (r.get("display") or "") == C.DISPLAY_POSTER
        out.append({"key": "ann:%s" % r.get("name"), "tag": tag, "tag_label": label,
                    "title": (r.get("title") or "").strip(),
                    "date_label": "%s/%d" % (dm(start), start.year),
                    "excerpt": plain_text(r.get("summary") or r.get("content"), 220),
                    "content_html": r.get("content_html") or "",
                    "image": img, "poster": poster,
                    "url": _safe_link(r.get("link")), "link_label": (r.get("link_label") or "").strip(),
                    "_sort": (start, r.get("name") or "")})
    out.sort(key=lambda x: x["_sort"], reverse=True)
    for x in out:
        x.pop("_sort", None)
    return out[:limit]


# ------------------------------------------------------------------ trang tri ---
def celebration(bd_today, viewer, dept_names):
    """Muc trang tri trang chu cho NGUOI XEM (PO chot 29/09):
    nguoi sinh nhat -> Ruc ro; cung phong ban -> Vua; con lai -> Nhe; khong ai -> khong."""
    if not bd_today:
        return {"level": C.LEVEL_NONE, "badge": ""}
    viewer = viewer or {}
    if viewer.get("name") and any(p["emp"] == viewer["name"] for p in bd_today):
        return {"level": C.LEVEL_ME, "badge": "Chúc mừng sinh nhật bạn!"}
    dept = viewer.get("department")
    same = [p for p in bd_today if dept and p.get("department") == dept]
    if same:
        names = ", ".join(p.get("given") or given_name(p["name"]) for p in same[:3])
        label = dept_names.get(dept) or dept
        return {"level": C.LEVEL_DEPT, "badge": "Phòng %s có sinh nhật %s" % (label, names)}
    return {"level": C.LEVEL_LIGHT, "badge": "Hôm nay có %d sinh nhật" % len(bd_today)}


# ------------------------------------------------------------------ reaction ----
def reactions_view(rows, keys, me, full_names):
    """rows: [{target, kind, user}] -> {target: {kind: {n, names, mine}}} cho moi key."""
    out = {k: {kind: {"n": 0, "names": [], "mine": False} for kind in C.REACTION_KINDS} for k in keys}
    for r in rows:
        slot = out.get(r.get("target"), {}).get(r.get("kind"))
        if slot is None:
            continue
        slot["n"] += 1
        if r.get("user") == me:
            slot["mine"] = True
        else:
            slot["names"].append(full_names.get(r.get("user")) or r.get("user"))
    for per in out.values():
        for slot in per.values():
            slot["names"] = sorted(slot["names"])[:8]
    return out
