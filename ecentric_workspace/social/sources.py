# Copyright (c) 2026, eCentric and contributors
"""Bang tin doc du lieu cua module KHAC qua ham khai bao cua ho - KHONG cham DocType cua ho, KHONG
luu ban sao (tranh "double thong tin"):

  * Tin noi bo  -> internal_posts.service.feed_cards: the bai HR (tim / binh luan cua chinh bai).
  * Hom nay     -> home_today.service.people_today: sinh nhat / ban moi / ky niem, cung khoa cam xuc
                   voi popup.
  * Khao sat    -> surveys respond_service.hub: khao sat dang mo ma nguoi xem chua lam.
  * Gop y       -> feedback.service.board: muc "Da lam" tren bang chung.

Nguoc lai, popup trang chu doc Bang tin qua popup_events / wish_counts o day.
Moi ham bat loi cua ben kia: mot module hong khong lam hong Bang tin (tra rong + Error Log).
"""
import datetime

from ecentric_workspace.social import constants as C
from ecentric_workspace.social import domain as D


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.social import repository
    return repository


def _safe(repo, title, fn, default):
    try:
        return fn()
    except Exception:
        try:
            repo.log_error(title)
        except Exception:
            pass
        return default


# ------------------------------------------------------------------ doc module khac ----
def hr_cards(user, repo=None):
    repo = _repo(repo)

    def run():
        from ecentric_workspace.internal_posts import service
        return service.feed_cards(user)
    return _safe(repo, "social.sources.hr_cards", run, [])


def people_today(repo=None):
    repo = _repo(repo)

    def run():
        from ecentric_workspace.home_today import service
        return service.people_today()
    return _safe(repo, "social.sources.people_today", run, {"birthdays": [], "onboard": [], "anniversaries": []})


def toggle_moment(user, key, kind):
    from ecentric_workspace.home_today import service
    try:
        return service.toggle(user, key, kind)
    except service.HomeTodayError as e:
        raise D.SocialError(str(e))


def open_surveys(user, repo=None):
    repo = _repo(repo)

    def run():
        import frappe
        from ecentric_workspace.surveys import constants as SC
        from ecentric_workspace.surveys.application import respond_service
        from ecentric_workspace.surveys.application.access import Ctx
        hub = respond_service.hub(Ctx(user, frappe.get_roles(user)))
        out = []
        for s in hub.get("open") or []:
            if s.get("effective") != SC.EFFECTIVE_OPEN:         # hen gio mo: chua lam duoc, chua nhac
                continue
            out.append({"name": s["name"], "title": s.get("title") or "", "url": SC.fill_url(s["name"]),
                        "close_at": s.get("close_at") or ""})
        return out
    return _safe(repo, "social.sources.open_surveys", run, [])


def feedback_done(user, limit=3, repo=None):
    repo = _repo(repo)

    def run():
        from ecentric_workspace.feedback import service
        cards = service.board(user, sort="moi-nhat", flt="da-lam")["cards"]
        return [{"title": c["title"], "date": c["date"], "topic": c["topic"]} for c in cards[:limit]]
    return _safe(repo, "social.sources.feedback_done", run, [])


# ------------------------------------------------------------------ cho popup trang chu --
def popup_events(user, day, repo=None):
    """Su kien CLB tu `day` toi POPUP_EVENT_DAYS ngay sau, nguoi xem thay duoc."""
    repo = _repo(repo)
    start = datetime.datetime.combine(day, datetime.time(0, 0))
    rows = repo.events_between(start, start + datetime.timedelta(days=C.POPUP_EVENT_DAYS))
    if not rows:
        return []
    tree = repo.dept_tree()
    v = repo.viewer(user)
    mod = repo.is_moderator(user)
    rows = [r for r in rows if D.can_see(r, user, v and v.get("lft"), tree, mod)][:C.POPUP_EVENT_MAX]
    if not rows:
        return []
    going = {}
    for r in repo.rsvps([r["name"] for r in rows]):
        if r["answer"] == C.RSVP_GOING:
            going[r["post"]] = going.get(r["post"], 0) + 1
    clubs = {c: repo.club(c) for c in {r["club"] for r in rows if r.get("club")}}
    rows = [r for r in rows if not r.get("club") or (clubs.get(r["club"]) or {}).get("status") == C.CLUB_ACTIVE]
    out = []
    for r in rows:
        c = clubs.get(r.get("club")) or {}
        out.append({"name": r["name"], "title": r.get("event_title") or "", "url": "%s/%s" % (C.POST_ROUTE, r["name"]),
                    "when": D.event_when(r.get("event_start")), "day": D.date_block(r.get("event_start"))["day"],
                    "month": "Th%d" % D.as_datetime(r.get("event_start")).month,
                    "place": r.get("event_place") or "", "club": c.get("club_name") or "",
                    "emoji": c.get("emoji") or "", "going": going.get(r["name"], 0),
                    "days_left": (D.as_date(r.get("event_start")) - day).days})
    return out


def wish_counts(keys, repo=None):
    """{khoa khoanh khac: so loi chuc} - chi khoa da co loi chuc."""
    repo = _repo(repo)
    posts = {k: p for k, p in repo.moment_posts(keys or []).items() if not p.get("hidden")}
    if not posts:
        return {}
    counts = repo.comment_counts([p["name"] for p in posts.values()])
    return {k: counts.get(p["name"], 0) for k, p in posts.items() if counts.get(p["name"], 0)}
