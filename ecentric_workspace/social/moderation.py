# Copyright (c) 2026, eCentric and contributors
"""/bang-tin/quan-ly - HR kiem duyet: bai bi bao cao, bai da an, CLB (duyet de xuat, doi nguoi phu
trach, ngung / mo lai). Chi MODERATOR_ROLES."""
from ecentric_workspace.social import cards, clubs
from ecentric_workspace.social import constants as C
from ecentric_workspace.social import domain as D
from ecentric_workspace.social import service as S
from ecentric_workspace.social.domain import Forbidden

TABS = (("bao-cao", "Bị báo cáo"), ("da-an", "Bài đã ẩn"), ("clb", "Câu lạc bộ"))


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.social import repository
    return repository


def page(user, tab="bao-cao", repo=None):
    repo = _repo(repo)
    cx = S.context(repo, user)
    if not cx["moderator"]:
        raise Forbidden("Trang này dành cho HR.")
    tab = tab if tab in dict(TABS) else "bao-cao"
    now = repo.now()
    reports = repo.open_reports()
    pending = repo.clubs([C.CLUB_PENDING])
    ctx = {"tab": tab, "tabs": [{"key": k, "label": lb} for k, lb in TABS], "n_reports": len({r["post"] for r in reports}),
           "n_pending": len(pending), "groups": [], "hidden": [], "pending": [], "active": [], "archived": []}
    if tab == "bao-cao":
        by_post = {}
        for r in reports:
            by_post.setdefault(r["post"], []).append(r)
        rows = [p for p in (repo.post(n) for n in by_post) if p]
        names = repo.full_names([r["user"] for r in reports])
        built = {b["name"]: b for b in cards.build(repo, cx, rows)}
        for n, rs in by_post.items():
            if n in built:
                ctx["groups"].append({"post": dict(built[n], type="post"),
                                      "reports": [{"who": names.get(r["user"]) or r["user"], "reason": r.get("reason") or "",
                                                   "ago": D.ago(r.get("creation"), now)} for r in rs]})
    elif tab == "da-an":
        ctx["hidden"] = [dict(b, type="post") for b in cards.build(repo, cx, repo.hidden_posts())]
    else:
        every = clubs._club_cards(repo, pending + repo.clubs([C.CLUB_ACTIVE, C.CLUB_ARCHIVED]), user, now)
        leads = repo.full_names([c["lead"] for c in every if c.get("lead")] +
                                [c.get("proposed_by") for c in pending if c.get("proposed_by")])
        props = {c["name"]: c.get("proposed_by") for c in pending}
        for c in every:
            c["lead_name"] = leads.get(c.get("lead")) or ""
            c["proposer"] = leads.get(props.get(c["name"])) or ""
            key = {C.CLUB_PENDING: "pending", C.CLUB_ACTIVE: "active", C.CLUB_ARCHIVED: "archived"}[c["status"]]
            ctx[key].append(c)
    return ctx
