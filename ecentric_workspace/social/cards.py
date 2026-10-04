# Copyright (c) 2026, eCentric and contributors
"""Ve du lieu THE BAI Bang tin (bai thuong / loi khen / su kien) cho template - dung chung cho bang
tin, trang CLB, trang mot bai. Gom truy van theo LO (anh, gan ten, cam xuc, binh luan, tham gia,
CLB, ten nguoi) - khong truy van tung bai."""
from ecentric_workspace.social import constants as C
from ecentric_workspace.social import domain as D

IMAGE_URL = "/api/method/ecentric_workspace.social.api.image?post=%s&i=%d"


def club_view(c, count=None):
    if not c:
        return None
    return {"name": c["name"], "title": c.get("club_name") or "", "slug": c.get("slug") or "",
            "emoji": c.get("emoji") or "✨", "color": c.get("color") if c.get("color") in C.CLUB_COLORS else "green",
            "url": "%s/%s" % (C.CLUBS_ROUTE, c.get("slug")), "category": c.get("category") or "",
            "description": c.get("description") or "", "status": c.get("status") or "",
            "lead": c.get("lead") or "", "members": count}


def event_view(row, rsvp_rows, user, names, now):
    going = [r["user"] for r in rsvp_rows if r["answer"] == C.RSVP_GOING]
    maybe = [r["user"] for r in rsvp_rows if r["answer"] == C.RSVP_MAYBE]
    mine = next((r["answer"] for r in rsvp_rows if r["user"] == user), "")
    sample = [D.person(u, names) for u in going[:3]]
    who = (["Bạn"] if mine == C.RSVP_GOING else []) + [D.given(names.get(u) or u) for u in going if u != user]
    shown = who[:2]
    rest = len(going) - len(shown)
    line = ", ".join(shown) + (" và %d người khác" % rest if rest > 0 else "") if going else ""
    state = D.event_state(row.get("event_start"), now)
    return {"title": row.get("event_title") or "", "when": D.event_when(row.get("event_start")),
            "short": D.event_short(row.get("event_start")), "date": D.date_block(row.get("event_start")),
            "place": row.get("event_place") or "", "going": len(going), "maybe": len(maybe), "mine": mine,
            "sample": sample, "line": line, "state": state, "open": state != "past",
            "start": D.ts(row.get("event_start"))}


def build(repo, cx, rows, clubs_map=None):
    """rows: dong EC Social Post (da loc nguoi xem duoc). -> [the]."""
    if not rows:
        return []
    user, now = cx["user"], repo.now()
    names_ = [r["name"] for r in rows]
    images = repo.images_of(names_)
    mentions = repo.mentions_of(names_)
    targets = [C.RX_PREFIX + n for n in names_] + [r["moment_key"] for r in rows if r.get("moment_key")]
    rx_rows = repo.reactions(targets)
    cmts = repo.comment_counts(names_)
    ev_names = [r["name"] for r in rows if r.get("kind") == C.KIND_EVENT]
    rsvp_rows = repo.rsvps(ev_names) if ev_names else []
    by_post = {}
    for r in rsvp_rows:
        by_post.setdefault(r["post"], []).append(r)
    users = set()
    for r in rows:
        users.update(x for x in (r.get("author"), r.get("kudos_to"), r.get("hidden_by")) if x)
        users.update(mentions.get(r["name"]) or [])
    users.update(r["user"] for r in rsvp_rows)
    names = repo.full_names(list(users))
    depts = repo.user_departments([r.get("author") for r in rows if r.get("author")])
    if clubs_map is None:
        ids = list({r["club"] for r in rows if r.get("club")})
        clubs_map = {i: repo.club(i) for i in ids}
    out = []
    for r in rows:
        n = r["name"]
        mine = r.get("author") == user
        imgs = [{"src": IMAGE_URL % (n, i), "w": im.get("width") or 0, "h": im.get("height") or 0}
                for i, im in enumerate(images.get(n) or [])]
        card = {
            "name": n, "kind": r.get("kind"), "url": "%s/%s" % (C.POST_ROUTE, n),
            "author": D.person(r.get("author"), names, depts), "mine": mine,
            "club": club_view(clubs_map.get(r.get("club"))) if r.get("club") else None,
            "dept_only": bool(r.get("dept_only")),
            "dept_label": (cx.get("tree", {}).get(r.get("department")) or (None, None, r.get("department") or ""))[2]
            if r.get("dept_only") else "",
            "body": r.get("body") or "", "images": imgs, "n_images": len(imgs),
            "mentions": [D.person(u, names) for u in mentions.get(n) or []],
            "ago": D.ago(r.get("creation"), now), "edited": bool(r.get("edited_on")),
            "ts": D.ts(r.get("creation")),
            "rx": D.rx_summary(rx_rows, C.RX_PREFIX + n, user),
            "comments": cmts.get(n, 0),
            "hidden": bool(r.get("hidden")), "hidden_reason": r.get("hidden_reason") or "",
            "can_edit": mine and not r.get("hidden"), "can_delete": mine or cx["moderator"],
            "can_report": not mine, "can_hide": cx["moderator"],
            "kudos": None, "event": None, "moment": None,
        }
        if r.get("kind") == C.KIND_KUDOS and r.get("kudos_to"):
            card["kudos"] = {"to": D.person(r["kudos_to"], names), "value": D.kudos_label(r.get("kudos_value")),
                             "to_me": r["kudos_to"] == user}
        if r.get("kind") == C.KIND_EVENT:
            card["event"] = event_view(r, by_post.get(n) or [], user, names, now)
        if r.get("kind") == C.KIND_MOMENT:
            mk = D.moment_kind(r.get("moment_key"))
            kind = C.MOMENT_RX.get(mk, C.RX_KIND)
            card.update(can_edit=False, can_delete=False, can_report=False,
                        rx=D.rx_summary(rx_rows, r.get("moment_key"), user, kind))
            card["moment"] = {"key": r.get("moment_key"), "mk": mk, "label": C.MOMENT_LABEL.get(mk, ""),
                              "icon": C.MOMENT_ICON.get(mk, ""), "rx_kind": kind, "rx_emoji": C.RX_EMOJI[kind]}
        out.append(card)
    return out
