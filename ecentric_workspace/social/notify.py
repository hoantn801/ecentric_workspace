# Copyright (c) 2026, eCentric and contributors
"""Chuong cua Bang tin (PO 04/10: chuong CHI khi duoc gan ten, duoc khen, co binh luan vao bai cua
minh - binh luan do internal_posts/comments.py gui; CLB: su kien moi gui thanh vien). Event
"announcement" = chuong + day trinh duyet, KHONG Teams. Khong gui cho chinh minh. Loi gui chuong
khong lam hong thao tac (ghi Error Log)."""
from ecentric_workspace.social import constants as C
from ecentric_workspace.social import domain as D


def _send(repo, user, title, message, url, ref, dedupe, actor):
    try:
        repo.send_bell(user, title, message, url, ref, dedupe, actor=actor)
    except Exception:
        repo.log_error("social.notify")


def _snippet(text, n=140):
    t = str(text or "").replace("\n", " ").strip()
    return t if len(t) <= n else t[:n - 3].rsplit(" ", 1)[0] + "…"


def _can_see(repo, row, user):
    v = repo.viewer(user)
    return D.can_see(row, user, v and v.get("lft"), repo.dept_tree(), repo.is_moderator(user))


def new_post(repo, row, mentions, club):
    author = row.get("author")
    who = repo.full_names([author]).get(author) or author
    url = "%s/%s" % (C.POST_ROUTE, row["name"])
    body = _snippet(row.get("body"))
    sent = {author}
    to = row.get("kudos_to")
    if to and to not in sent and _can_see(repo, row, to):
        value = D.kudos_label(row.get("kudos_value"))
        _send(repo, to, "%s khen bạn%s" % (who, " · " + value if value else ""), body, url, row["name"],
              "social_kudos|%s" % row["name"], author)
        sent.add(to)
    for u in mentions or ():
        if u in sent or not _can_see(repo, row, u):
            continue
        _send(repo, u, "%s gắn tên bạn trong một bài trên Bảng tin" % who, body, url, row["name"],
              "social_tag|%s|%s" % (row["name"], u), author)
        sent.add(u)
    if row.get("kind") == C.KIND_EVENT and club:
        title = "%s %s có sự kiện mới: %s" % (club.get("emoji") or "", club.get("club_name") or "", row.get("event_title") or "")
        msg = " · ".join(x for x in (D.event_when(row.get("event_start")), row.get("event_place") or "") if x)
        for u in repo.members(club["name"]):
            if u in sent or not _can_see(repo, row, u):
                continue
            _send(repo, u, title.strip(), msg, url, row["name"], "social_event|%s|%s" % (row["name"], u), author)


def reported(repo, row, total=1):
    """Chuong HR khi bai co bao cao dau tien cua MOT dot (total = tong bao cao tung co -> khoa dedupe moi)."""
    url = C.MOD_ROUTE
    for u in repo.hr_managers():
        _send(repo, u, "Có bài trên Bảng tin bị báo cáo", _snippet(row.get("body") or row.get("event_title")), url,
              row["name"], "social_report|%s|%s|%s" % (row["name"], total, u), None)


def club_proposed(repo, club):
    who = repo.full_names([club.get("proposed_by")]).get(club.get("proposed_by")) or club.get("proposed_by")
    for u in repo.hr_managers():
        _send(repo, u, "%s đề xuất CLB mới: %s" % (who, club.get("club_name")), _snippet(club.get("description")),
              C.MOD_ROUTE + "?tab=clb", None, "social_club_new|%s|%s" % (club["name"], u), None)


def club_decided(repo, club, by):
    u = club.get("proposed_by")
    if not u or u == by:
        return
    if club["status"] == C.CLUB_ACTIVE:
        title, url = "HR đã duyệt CLB %s" % club.get("club_name"), "%s/%s" % (C.CLUBS_ROUTE, club.get("slug"))
    else:
        title, url = "HR chưa duyệt CLB %s" % club.get("club_name"), C.CLUBS_ROUTE
    _send(repo, u, title, _snippet(club.get("decision_note")), url, None,
          "social_club_done|%s" % club["name"], by)
