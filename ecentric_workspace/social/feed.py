# Copyright (c) 2026, eCentric and contributors
"""Trang /bang-tin: tron bai Bang tin + bai Tin noi bo (the nhung) + khoanh khac hom nay theo thoi
gian; cot phai "Can ban" / "Hom nay" / "CLB cua ban" / "Gop y vua lam" / eCentric Hall.

?loc= loc (constants.FILTERS), ?truoc= con tro "Xem them" (thoi diem bai cuoi cua trang truoc).
"""
import datetime

from ecentric_workspace.social import cards, sources
from ecentric_workspace.social import constants as C
from ecentric_workspace.social import domain as D
from ecentric_workspace.social import service as S

FETCH = 60


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.social import repository
    return repository


def _social_rows(repo, cx, loc, cursor, my_clubs, now):
    if loc == "tin-hr":
        return [], False
    kw = {"before": cursor, "limit": FETCH}
    if loc == "loi-khen":
        kw["kinds"] = [C.KIND_KUDOS]
    elif loc == "phong-toi":
        if not cx["department"]:
            return [], False
        kw["department"] = cx["department"]
    elif loc == "clb-cua-toi":
        kw["clubs"] = my_clubs
    elif loc == "cua-toi":
        kw["mine"] = cx["user"]
    elif loc == "su-kien":
        kw = {"kinds": [C.KIND_EVENT], "limit": FETCH,
              "upcoming_after": now - datetime.timedelta(hours=C.EVENT_PAST_GRACE_HOURS)}
    rows, more = [], False
    for _ in range(4):                  # bai khong thay duoc (Chi phong khac) bi loc SAU khi doc: doc tiep
        batch = repo.feed_rows(**kw)
        rows += [r for r in batch if S.visible(cx, r)]
        more = len(batch) >= kw["limit"]
        if not more or len(rows) > C.FEED_PAGE or loc == "su-kien":
            break
        kw["before"] = batch[-1]["creation"]
    if loc == "su-kien":
        rows.sort(key=lambda r: D.ts(r.get("event_start")))
    return rows, more


def _hr_entry(c):
    return {"type": "hr", "ts": D.ts(c.get("ts")), "hr": dict(c, ago=c.get("date_label") or "",
                                                           rx_emojis="".join(C.RX_EMOJI.get(k, "") for k in (c.get("rx_kinds") or [])[:3]))}


def moments(repo, cx, people=None):
    """The khoanh khac hom nay (sinh nhat / ban moi / ky niem). Cam xuc dung KHOA cua popup."""
    people = people if people is not None else sources.people_today(repo)
    plist = [("bd", p) for p in people.get("birthdays") or []] + [("new", p) for p in people.get("onboard") or []] \
        + [("ann", p) for p in people.get("anniversaries") or []]
    if not plist:
        return []
    keys = [p["key"] for _, p in plist]
    rx_rows = repo.reactions(keys)
    posts = repo.moment_posts(keys)
    hidden = {k for k, p in posts.items() if p.get("hidden")}
    plist = [(mk, p) for mk, p in plist if p["key"] not in hidden]       # HR an khoanh khac: bo the
    counts = repo.comment_counts([p["name"] for p in posts.values()]) if posts else {}
    me = D.person(cx["user"], repo.full_names([cx["user"]]))
    out = []
    for mk, p in plist:
        post = posts.get(p["key"])
        role = p.get("role") or ""
        if mk == "bd":
            text = "sinh nhật hôm nay. Gửi một lời chúc nhé!"
        elif mk == "ann":
            text = "tròn %s năm gắn bó với eCentric (vào công ty %s)." % (p.get("years") or "", p.get("joined") or "")
        else:
            text = "hôm nay là ngày đầu tiên ở eCentric. Cả nhà cùng chào bạn nhé!"
        out.append({"type": "moment", "key": p["key"], "mk": mk, "anchor": "m-" + p["key"].replace(":", "-"),
                    "label": C.MOMENT_LABEL[mk], "icon": C.MOMENT_ICON[mk], "name": p.get("name") or "",
                    "given": p.get("given") or D.given(p.get("name")), "role": role, "text": text,
                    "intro": p.get("intro") or "", "initials": p.get("initials") or D.initials(p.get("name")),
                    "rx_kind": C.MOMENT_RX[mk], "rx_emoji": C.RX_EMOJI[C.MOMENT_RX[mk]],
                    "rx": D.rx_summary(rx_rows, p["key"], cx["user"], C.MOMENT_RX[mk]),
                    "post": post["name"] if post else "", "wishes": counts.get(post["name"], 0) if post else 0,
                    "act": "Chào" if mk == "new" else "Chúc", "me": me,
                    "short": ("%s năm gắn bó" % p.get("years")) if mk == "ann"
                    else " · ".join(x for x in (C.MOMENT_LABEL[mk], role.split(" · ")[-1] if role else "") if x)})
    return out


def _clubs_rail(repo, user, my_clubs, now):
    if not my_clubs:
        return []
    out = []
    for name in my_clubs:
        c = repo.club(name)
        if not c or c["status"] != C.CLUB_ACTIVE:
            continue
        ev = repo.club_events(name, now - datetime.timedelta(hours=C.EVENT_PAST_GRACE_HOURS), limit=1)
        view = cards.club_view(c)
        view["next"] = ("Sự kiện %s · %s" % (D.event_short(ev[0]["event_start"]), ev[0].get("event_title") or "")) if ev else ""
        out.append(view)
    return out


def _todo(hr, surveys, now):
    out = [{"icon": "\U0001f4cc", "text": "Xác nhận đã đọc: " + c["title"], "url": c["url"], "act": "Mở"}
           for c in hr if c.get("need_ack")]
    for s in surveys:
        left = ""
        close = D.as_datetime(s.get("close_at"))
        if close:
            days = (close.date() - now.date()).days
            left = " · còn %d ngày" % days if days > 0 else " · hạn hôm nay"
        out.append({"icon": "\U0001f4cb", "text": "Khảo sát: " + s["title"] + left, "url": s["url"], "act": "Làm"})
    return out


def page(user, loc="", before="", repo=None):
    repo = _repo(repo)
    cx = S.context(repo, user)
    loc = loc if loc in C.FILTER_KEYS else ""
    now = repo.now()
    cursor = D.parse_cursor(before) if loc != "su-kien" else None
    my_clubs = repo.clubs_of(user)
    hr = sources.hr_cards(user, repo)
    rows, rows_more = _social_rows(repo, cx, loc, cursor, my_clubs, now)
    entries = [{"type": "post", "ts": D.ts(r.get("creation")), "row": r} for r in rows]
    if loc in ("", "tin-hr"):
        cut = D.ts(cursor) if cursor else None
        entries += [_hr_entry(c) for c in hr if not cut or D.ts(c.get("ts")) < cut]
    surveys = sources.open_surveys(user, repo)
    if loc != "su-kien":
        entries.sort(key=lambda e: e["ts"], reverse=True)
    top = []
    if loc == "":
        # Tin ghim con moi "noi" dau trang 1 - va KHONG lap lai o trang sau theo thoi gian.
        fresh = D.ts(now - datetime.timedelta(days=C.PIN_FLOAT_DAYS))
        top = [e for e in entries if e["type"] == "hr" and e["hr"].get("pinned") and e["ts"] >= fresh]
        entries = [e for e in entries if e not in top]
        if cursor:
            top = []
    page_entries = entries[:C.FEED_PAGE]
    more = len(entries) > C.FEED_PAGE or rows_more
    built = {c["name"]: c for c in cards.build(repo, cx, [e["row"] for e in page_entries if e["type"] == "post"])}
    items = []
    for e in top + page_entries:
        if e["type"] == "post":
            items.append(dict(built[e["row"]["name"]], type="post"))
        else:
            items.append(dict(e["hr"], type="hr"))
    people = sources.people_today(repo) if not cursor else {}
    mom = moments(repo, cx, people) if (not cursor and loc == "") else []
    if mom:
        items = items[:len(top)] + mom + items[len(top):]
    if loc == "su-kien":
        items = [{"type": "survey", **s} for s in surveys] + items
    nxt = page_entries[-1]["ts"] if (more and page_entries and loc != "su-kien") else ""
    return {
        "loc": loc, "filters": [{"key": k, "label": lb} for k, lb in C.FILTERS], "items": items,
        "next": nxt, "is_moderator": cx["moderator"], "is_employee": cx["employee"], "first_page": not cursor,
        "todo": _todo(hr, surveys, now) if not cursor else [],
        "today": (moments(repo, cx, people) if loc != "" else mom) if not cursor else [],
        "my_clubs": _clubs_rail(repo, user, my_clubs, now) if not cursor else [],
        "feedback_done": sources.feedback_done(user, repo=repo) if not cursor else [],
        "composer": composer(repo, cx),
    }


def composer(repo, cx, club=None):
    names = repo.full_names([cx["user"]])
    me = D.person(cx["user"], names)
    my = []
    for name in repo.clubs_of(cx["user"]):
        c = repo.club(name)
        if c and c["status"] == C.CLUB_ACTIVE:
            my.append({"name": c["name"], "title": c["club_name"], "emoji": c.get("emoji") or "",
                       "lead": c.get("lead") == cx["user"] or cx["moderator"]})
    return {"me": me, "given": D.given(me["name"]), "clubs": my, "club": club,
            "kudos_values": [{"key": k, "label": v} for k, v in C.KUDOS_VALUES],
            "can_post": cx["employee"] or cx["moderator"], "dept": bool(cx["department"]),
            "images_max": C.IMAGES_MAX, "body_max": C.BODY_MAX}
