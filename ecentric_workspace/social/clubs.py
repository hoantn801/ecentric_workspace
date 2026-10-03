# Copyright (c) 2026, eCentric and contributors
"""Cau lac bo (mockup v2, PO duyet 04/10/2026):

  * Nhan vien DE XUAT CLB (ten, bieu tuong, nhom, mo ta; nguoi de xuat la nguoi phu trach), HR duyet
    MOT lan. Trong luc cho duyet ai cung bam "Toi cung muon tham gia" (HR thay so nguoi muon vao).
  * Vao CLB tu do, khong can duyet. Nguoi phu trach khong roi CLB duoc (nho HR doi nguoi truoc).
  * Bai CLB hien ca o Bang tin chung (co nhan CLB); chuong su kien chi gui thanh vien.
  * Su kien: nguoi phu trach (hoac HR) tao trong trang CLB.
"""
import datetime

from ecentric_workspace.social import cards, notify
from ecentric_workspace.social import constants as C
from ecentric_workspace.social import domain as D
from ecentric_workspace.social import service as S
from ecentric_workspace.social.domain import Forbidden, NotFound, SocialError

TABS = ("bai-viet", "su-kien", "anh", "thanh-vien")
LIST_FILTERS = (("", "Tất cả"), ("da-tham-gia", "Đã tham gia"), ("the-thao", "Thể thao"), ("so-thich", "Sở thích"))


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.social import repository
    return repository


def _club_cards(repo, rows, user, now):
    names_ = [c["name"] for c in rows]
    counts = repo.member_counts(names_)
    samples = repo.member_samples(names_)
    mine = set(repo.clubs_of(user))
    users = [u for v in samples.values() for u in v]
    names = repo.full_names(users)
    out = []
    for c in rows:
        v = cards.club_view(c, counts.get(c["name"], 0))
        ev = repo.club_events(c["name"], now - datetime.timedelta(hours=C.EVENT_PAST_GRACE_HOURS), limit=1) \
            if c["status"] == C.CLUB_ACTIVE else []
        v.update({"joined": c["name"] in mine, "sample": [D.person(u, names) for u in samples.get(c["name"]) or []],
                  "next": {"short": D.event_short(ev[0]["event_start"]), "title": ev[0].get("event_title") or "",
                           "url": "%s/%s" % (C.POST_ROUTE, ev[0]["name"])} if ev else None,
                  "is_lead": c.get("lead") == user, "proposed_by_me": c.get("proposed_by") == user,
                  "note": c.get("decision_note") or ""})
        out.append(v)
    return out


def list_page(user, loc="", repo=None):
    repo = _repo(repo)
    cx = S.context(repo, user)
    now = repo.now()
    loc = loc if loc in dict(LIST_FILTERS) else ""
    active = _club_cards(repo, repo.clubs([C.CLUB_ACTIVE]), user, now)
    total, joined = len(active), sum(1 for c in active if c["joined"])
    if loc == "da-tham-gia":
        active = [c for c in active if c["joined"]]
    elif loc in ("the-thao", "so-thich"):
        cat = C.CLUB_CATEGORIES[0] if loc == "the-thao" else C.CLUB_CATEGORIES[1]
        active = [c for c in active if c["category"] == cat]
    pending = _club_cards(repo, repo.clubs([C.CLUB_PENDING]), user, now)
    mine_rejected = [c for c in _club_cards(repo, repo.clubs([C.CLUB_REJECTED]), user, now) if c["proposed_by_me"]]
    return {"loc": loc, "filters": [{"key": k, "label": lb, "n": total if k == "" else (joined if k == "da-tham-gia" else None)}
                                    for k, lb in LIST_FILTERS],
            "clubs": active, "pending": pending, "rejected": mine_rejected, "is_moderator": cx["moderator"],
            "categories": C.CLUB_CATEGORIES, "colors": C.CLUB_COLORS, "suggest_min": C.CLUB_SUGGEST_MIN}


def _load_club(repo, cx, slug_or_name, by_slug=True):
    c = repo.club_by_slug(slug_or_name) if by_slug else repo.club(slug_or_name)
    if not c:
        raise NotFound("Không tìm thấy câu lạc bộ.")
    if c["status"] != C.CLUB_ACTIVE and not cx["moderator"] and c.get("proposed_by") != cx["user"]:
        if c["status"] != C.CLUB_PENDING:
            raise NotFound("Câu lạc bộ này đã ngừng hoạt động.")
    return c


def club_page(user, slug, tab="bai-viet", before="", repo=None):
    repo = _repo(repo)
    cx = S.context(repo, user)
    now = repo.now()
    c = _load_club(repo, cx, slug)
    tab = tab if tab in TABS else "bai-viet"
    view = _club_cards(repo, [c], user, now)[0]
    members = repo.members(c["name"])
    names = repo.full_names(members + [c.get("lead")] if c.get("lead") else members)
    depts = repo.user_departments(members)
    upcoming = repo.club_events(c["name"], now - datetime.timedelta(hours=C.EVENT_PAST_GRACE_HOURS), limit=10)
    upcoming = [r for r in upcoming if S.visible(cx, r)]
    ctx = {"club": view, "tab": tab, "is_moderator": cx["moderator"], "items": [], "next": "", "photos": [],
           "members": [D.person(u, names, depts) for u in members],
           "lead": D.person(c["lead"], names) if c.get("lead") else None,
           "can_event": c["status"] == C.CLUB_ACTIVE and (c.get("lead") == user or cx["moderator"]),
           "can_post": c["status"] == C.CLUB_ACTIVE and (view["joined"] or cx["moderator"]),
           "upcoming": cards.build(repo, cx, upcoming[:3], {c["name"]: c})}
    if tab == "su-kien":
        ctx["items"] = cards.build(repo, cx, upcoming, {c["name"]: c})
    elif tab in ("bai-viet", "anh"):
        cursor = D.parse_cursor(before)
        rows = [r for r in repo.feed_rows(before=cursor, limit=60, clubs=[c["name"]]) if S.visible(cx, r)]
        built = cards.build(repo, cx, rows[:C.FEED_PAGE], {c["name"]: c})
        if tab == "anh":
            ctx["photos"] = [dict(im, post=b["url"]) for b in built for im in b["images"]]
        else:
            ctx["items"] = [dict(b, type="post") for b in built]
        if len(rows) > C.FEED_PAGE and built:
            ctx["next"] = built[-1]["ts"]
    from ecentric_workspace.social import feed
    ctx["composer"] = feed.composer(repo, cx, club={"name": c["name"], "title": c["club_name"],
                                                    "emoji": c.get("emoji") or "", "can_event": ctx["can_event"]})
    return ctx


# ------------------------------------------------------------------ thao tac ---------
def join(user, club, repo=None):
    repo = _repo(repo)
    cx = S.context(repo, user)
    c = _load_club(repo, cx, club, by_slug=False)
    if c["status"] not in (C.CLUB_ACTIVE, C.CLUB_PENDING):
        raise SocialError("Câu lạc bộ này không nhận thành viên.")
    if not cx["employee"]:
        raise Forbidden("Chỉ nhân viên eCentric mới tham gia CLB được.")
    if not repo.find_member(c["name"], user):
        try:
            repo.add_member(c["name"], user)
        except Exception as exc:
            if not repo.is_duplicate(exc):
                raise
    return {"joined": True, "members": repo.member_counts([c["name"]])[c["name"]]}


def leave(user, club, repo=None):
    repo = _repo(repo)
    S.context(repo, user)
    c = repo.club(club)                     # CLB da ngung van roi duoc
    if not c:
        raise NotFound("Không tìm thấy câu lạc bộ.")
    if c.get("lead") == user and c["status"] == C.CLUB_ACTIVE:
        raise SocialError("Bạn đang phụ trách CLB này. Nhờ HR đổi người phụ trách trước khi rời.")
    m = repo.find_member(c["name"], user)
    if m:
        repo.remove_member(m)
    return {"joined": False, "members": repo.member_counts([c["name"]])[c["name"]]}


def propose(user, data, repo=None):
    """Nhan vien de xuat CLB moi. HR de xuat = mo luon (khong can tu duyet chinh minh)."""
    repo = _repo(repo)
    cx = S.context(repo, user)
    if not cx["employee"] and not cx["moderator"]:
        raise Forbidden("Chỉ nhân viên eCentric mới đề xuất CLB được.")
    title = D.clean_text(data.get("club_name"), C.CLUB_NAME_MAX, "Đặt tên cho CLB nhé.")
    desc = D.clean_text(data.get("description"), C.CLUB_DESC_MAX, "Viết một câu mô tả CLB làm gì.")
    cat = data.get("category") if data.get("category") in C.CLUB_CATEGORIES else C.CLUB_CATEGORIES[0]
    color = data.get("color") if data.get("color") in C.CLUB_COLORS else C.CLUB_COLORS[0]
    emoji = D.clean_text(data.get("emoji"), 8) or "✨"
    if not cx["moderator"] and repo.open_proposals_of(user) >= C.CLUB_PROPOSE_MAX_OPEN:
        raise SocialError("Bạn đang có %d đề xuất chờ HR duyệt. Đợi HR xem xong nhé." % C.CLUB_PROPOSE_MAX_OPEN)
    base = D.slugify(title)
    slug, i = base, 2
    while repo.slug_taken(slug):
        slug, i = "%s-%d" % (base, i), i + 1
    now = repo.now()
    values = {"club_name": title, "slug": slug, "emoji": emoji, "color": color, "category": cat, "description": desc,
              "lead": user, "proposed_by": user, "status": C.CLUB_PENDING}
    if cx["moderator"]:
        values.update(status=C.CLUB_ACTIVE, decided_by=user, decided_on=now)
    name = repo.insert_club(values)
    if cx["employee"]:
        repo.add_member(name, user)
    if not cx["moderator"]:
        notify.club_proposed(repo, repo.club(name))
    return {"name": name, "slug": slug, "status": values["status"], "url": "%s/%s" % (C.CLUBS_ROUTE, slug)}


def _moderate(repo, user, club):
    cx = S.context(repo, user)
    if not cx["moderator"]:
        raise Forbidden("Chỉ HR quản lý câu lạc bộ.")
    c = repo.club(club)
    if not c:
        raise NotFound("Không tìm thấy câu lạc bộ.")
    return cx, c


def decide(user, club, approve, note="", repo=None):
    repo = _repo(repo)
    cx, c = _moderate(repo, user, club)
    if c["status"] != C.CLUB_PENDING:
        raise SocialError("Đề xuất này đã được xử lý.")
    note = D.clean_text(note, C.CLUB_DESC_MAX)
    if not approve and not note:
        raise SocialError("Ghi lý do từ chối để người đề xuất biết.")
    status = C.CLUB_ACTIVE if approve else C.CLUB_REJECTED
    repo.update_club(c["name"], {"status": status, "decided_by": user, "decided_on": repo.now(), "decision_note": note})
    notify.club_decided(repo, repo.club(c["name"]), user)
    return {"name": c["name"], "status": status}


def set_lead(user, club, lead, repo=None):
    repo = _repo(repo)
    cx, c = _moderate(repo, user, club)
    valid = {p["user"] for p in repo.people()}
    if lead not in valid:
        raise SocialError("Chọn một nhân viên đang làm việc.")
    repo.update_club(c["name"], {"lead": lead})
    if not repo.find_member(c["name"], lead):
        repo.add_member(c["name"], lead)
    return {"name": c["name"], "lead": lead}


def set_status(user, club, active, repo=None):
    """HR ngung / mo lai CLB (bai cu van con, khong dang moi duoc)."""
    repo = _repo(repo)
    cx, c = _moderate(repo, user, club)
    if c["status"] not in (C.CLUB_ACTIVE, C.CLUB_ARCHIVED):
        raise SocialError("Chỉ ngừng / mở lại CLB đang hoạt động.")
    repo.update_club(c["name"], {"status": C.CLUB_ACTIVE if active else C.CLUB_ARCHIVED})
    return {"name": c["name"], "status": C.CLUB_ACTIVE if active else C.CLUB_ARCHIVED}
