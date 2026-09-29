# Copyright (c) 2026, eCentric and contributors
"""Popup "Hom nay o eCentric" - ghep du lieu cho NGUOI DANG DANG NHAP.

Ba loi vao, deu lay nguoi dung tu phien (khong nhan tham so user tu HTTP - A66 §7):
  * today(user)          -> du lieu popup (api.get_today)
  * toggle(user, ...)    -> bat/tat mot cam xuc (api.toggle_reaction, POST)
  * celebration(user)    -> muc trang tri + co noi dung khong (ham Jinja cua trang chu)

`repo` tiem vao duoc: test chay bang repo gia, khong can bench.
"""
import datetime

from ecentric_workspace.home_today import constants as C
from ecentric_workspace.home_today import domain as D


class HomeTodayError(Exception):
    """Loi nguoi dung gay ra (tham so sai) - api tra 417, khong ghi Error Log."""


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.home_today import repository
    return repository


def _shared(repo, today):
    """Phan KHONG phu thuoc nguoi xem, cache theo ngay (moi lan mo trang chu khong phai quet
    lai ~100 nhan vien). Het han sau CACHE_TTL de nhan vien moi / tin moi len trong vai phut."""
    key = C.CACHE_KEY + today.isoformat()
    hit = repo.cache_get(key)
    if hit:
        return hit
    depts = repo.department_names()
    emps = repo.active_employees()
    bd_today, bd_soon = D.birthdays(emps, today, depts)
    data = {"depts": depts, "bd_today": bd_today, "bd_soon": bd_soon,
            "anniv": D.anniversaries(emps, today, depts),
            "news": D.news_items(repo.news_rows(today), repo.policy_rows(today), today)}
    repo.cache_set(key, data, C.CACHE_TTL)
    return data


def _holidays(repo, viewer, today):
    hl = repo.holiday_list_for(viewer)
    if not hl:
        return []
    key = C.CACHE_KEY + "hol:" + today.isoformat() + ":" + hl
    hit = repo.cache_get(key)
    if hit is None:
        hit = D.holidays(repo.holidays(hl, today, C.HOLIDAY_DAYS_AHEAD), today)
        repo.cache_set(key, hit, C.CACHE_TTL)
    return hit


def _onboard_rows(repo, day):
    key = C.CACHE_KEY + "onb:" + day.isoformat()
    rows = repo.cache_get(key)
    if rows is None:
        rows = list(repo.onboard_rows())
        repo.cache_set(key, rows, C.ONBOARD_TTL)
    return rows


def _onboard(repo, day):
    out = []
    for r in _onboard_rows(repo, day):
        name = (r.get("candidate_name") or "").strip()
        if not r.get("name") or not name:
            continue
        role = " · ".join(x for x in (r.get("position") or "", r.get("department") or "") if x)
        out.append({"key": D.new_key(r["name"]), "name": name, "role": role,
                    "intro": (r.get("welcome_intro") or "").strip(),
                    "initials": D.initials(name), "color": D.color_index(r["name"])})
    return out


def _public(p):
    """Bo ma nhan vien / ma phong ban khoi du lieu gui trinh duyet - popup khong can."""
    return {k: v for k, v in p.items() if k not in ("emp", "department", "offset")}


def _today(repo, now):
    """Ngay hom nay theo MUI GIO SITE (Asia/Ho_Chi_Minh) - khong dung datetime.now() cua may chu."""
    now = now or repo.now()
    return now.date() if isinstance(now, datetime.datetime) else now


def today(user, now=None, repo=None):
    repo = _repo(repo)
    if not user or user == "Guest":
        return {"has_content": False}
    day = _today(repo, now)
    sh = _shared(repo, day)
    viewer = repo.viewer_employee(user)
    onboard = _onboard(repo, day)
    react_keys = [p["key"] for p in sh["bd_today"]] + [p["key"] for p in onboard] + [p["key"] for p in sh["anniv"]]
    rows = repo.reactions(react_keys)
    names = repo.full_names([r.get("user") for r in rows])
    news = sh["news"]
    fresh = [n["key"] for n in news] + react_keys
    return {
        "has_content": bool(news or sh["bd_today"] or sh["bd_soon"] or onboard or sh["anniv"]),
        "date": day.isoformat(), "date_label": D.full_label(day),
        "news": news,
        "birthdays": {"today": [_public(p) for p in sh["bd_today"]], "soon": [_public(p) for p in sh["bd_soon"]]},
        "onboard": onboard,
        "anniversaries": [_public(p) for p in sh["anniv"]],
        "holidays": _holidays(repo, viewer, day),
        "event_coming_soon": True,
        "reactions": D.reactions_view(rows, react_keys, user, names),
        "keys": fresh,
    }


def toggle(user, target, kind, now=None, repo=None):
    """Bat/tat MOT cam xuc cua nguoi dang dang nhap tren MOT muc cua hom nay.
    Chi nhan target cua hom nay (sinh nhat / ban moi / ky niem) - khong ghi rac vao bang."""
    repo = _repo(repo)
    if not user or user == "Guest":
        raise HomeTodayError("Cần đăng nhập")
    if kind not in C.REACTION_KINDS:
        raise HomeTodayError("Cảm xúc không hợp lệ")
    day = _today(repo, now)
    sh = _shared(repo, day)
    valid = {p["key"] for p in sh["bd_today"]} | {p["key"] for p in sh["anniv"]} | {p["key"] for p in _onboard(repo, day)}
    if target not in valid:
        raise HomeTodayError("Mục này không còn trong ngày hôm nay")
    existing = repo.find_reaction(target, kind, user)
    if existing not in (None, ""):
        repo.remove_reaction(existing)
    else:
        try:
            repo.add_reaction(target, kind, user, day)
        except Exception as exc:      # bam 2 tab cung luc: ban ghi da co -> coi nhu da bat
            if not repo.is_duplicate(exc):
                raise
    rows = repo.reactions([target])
    names = repo.full_names([r.get("user") for r in rows])
    return {"target": target, "reactions": D.reactions_view(rows, [target], user, names)[target]}


def celebration(user, now=None, repo=None):
    """Cho trang chu (Jinja, render theo tung nguoi): muc trang tri + popup co gi de hien khong.
    KHONG BAO GIO nem loi - loi o day la trang chu 500 cho ca cong ty. Loi -> muc 0, ghi log."""
    off = {"level": C.LEVEL_NONE, "badge": "", "has_content": False}
    fail_key = C.CACHE_KEY + "fail"
    try:
        repo = _repo(repo)
        if not user or user == "Guest" or repo.cache_get(fail_key):
            return off
        day = _today(repo, now)
        sh = _shared(repo, day)
        viewer = repo.viewer_employee(user) if sh["bd_today"] else None
        out = D.celebration(sh["bd_today"], viewer, sh["depts"])
        out["has_content"] = bool(sh["news"] or sh["bd_today"] or sh["bd_soon"] or sh["anniv"]) or bool(_onboard_rows(repo, day))
        return out
    except Exception:
        # Ghi log MOT lan moi FAIL_TTL, trong luc do tra muc 0 ngay (khong truy van lai):
        # moi lan mo trang chu ma ghi Error Log = bao Error Log nhu vu scheduler GBS.
        try:
            repo.cache_set(fail_key, 1, C.FAIL_TTL)
            repo.log_error("home_today.celebration")
        except Exception:
            pass
        return off
