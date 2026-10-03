# Copyright (c) 2026, eCentric and contributors
"""Gop y cong ty - thong bao (job nen) + nhac han (scheduler).

MOI HAM O DAY CHAY DUOI SYSTEM_USER (_system()). Job nen cua Frappe chay duoi ten nguoi da
xep job - tuc la nguoi gui gop y an danh - va Notification Log / Delivery Log tao trong job
se mang owner = ho, ma nguoi nhan doc duoc owner cua Notification Log cua chinh minh. Nen
truoc khi ghi bat cu gi: doi sang SYSTEM_USER.

Link trong thong bao tro /gop-y/... - KHONG BAO GIO /app (QC gate test_no_desk_urls).
Loi mot nguoi nhan khong giet ca dot. Dedupe theo khoa: job chay lai khong de ra tin trung.
"""
from ecentric_workspace.feedback import constants as C
from ecentric_workspace.feedback import domain as D
from ecentric_workspace.feedback import service as S

_SENDER_TITLES = {
    C.ST_VIEWING: "Góp ý của bạn đang được xem",
    C.ST_ANSWERED: "Góp ý của bạn đã có trả lời",
    C.ST_DONE: "Công ty đã làm theo góp ý của bạn",
    C.ST_DECLINED: "Góp ý của bạn: không làm",
}


def _boot(repo):
    if repo is not None:
        return repo
    import frappe
    frappe.set_user(C.SYSTEM_USER)
    from ecentric_workspace.feedback import repository
    return repository


def _send(repo, event, users, title, message, url, name, key):
    sent = failed = 0
    for u in users:
        try:
            repo.notify(event, u, title, message, url, name, "%s|%s" % (key, u))
            sent += 1
        except Exception:
            failed += 1
            repo.log_error("feedback.notify")
    return {"sent": sent, "failed": failed}


def _inbox_url(name):
    return "%s?gy=%s" % (C.ROUTE_INBOX, name)


def new_feedback(name, repo=None):
    """Gop y moi -> moi nguoi xu ly. Thong bao KHONG mang ten nguoi gui (ke ca gop y co ten: ten
    xem trong hop xu ly; mot luat cho moi gop y thi chuong khong phan biet duoc an danh)."""
    repo = _boot(repo)
    fb = repo.get(name)
    if not fb:
        return {"skipped": "missing"}
    topic = (S.topic_map(repo).get(fb["topic"]) or {}).get("label") or fb["topic"]
    return _send(repo, C.EV_NEW, repo.handlers(), "Góp ý mới: " + fb["title"],
                 "%s · %s · trả lời trước %s" % (topic, fb["kind"], D.fmt_date_full(fb.get("due_at"))),
                 _inbox_url(name), name, "feedback_new|" + name)


def sender_update(name, status="", text="", changed=True, stamp="", repo=None):
    """Bao NGUOI GUI: doi trang thai / co tra loi. Nguoi nhan la chinh ho - ten ho khong lo cho ai."""
    repo = _boot(repo)
    fb = repo.get(name)
    user = repo.sender_of(name)
    if not fb or not user:
        return {"skipped": "missing"}
    title = _SENDER_TITLES.get(status) if changed else None
    title = title or "Có trả lời mới cho góp ý của bạn"
    msg = fb["title"] + ((" — " + D.one_line(text, 160)) if text else "")
    return _send(repo, C.EV_SENDER, [user], title, msg, "%s/%s" % (C.ROUTE, name), name,
                 "feedback_upd|%s|%s" % (name, stamp))


def sender_wrote(name, kind=C.MSG_REPLY, repo=None, stamp=None):
    """Nguoi gui nhan them / mo lai -> nguoi dang nhan xu ly (chua ai nhan: ca nhom)."""
    repo = _boot(repo)
    fb = repo.get(name)
    if not fb:
        return {"skipped": "missing"}
    users = [fb["viewed_by"]] if fb.get("viewed_by") and kind != C.MSG_REOPEN else repo.handlers()
    title = ("Góp ý được mở lại: " if kind == C.MSG_REOPEN else "Người gửi nhắn thêm: ") + fb["title"]
    stamp = stamp or str(fb.get("last_activity_at") or "")
    return _send(repo, C.EV_HANDLER_UPDATE, users, title, fb["title"], _inbox_url(name), name,
                 "feedback_wrote|%s|%s" % (name, stamp))


def flush_pending(repo):
    """Gop y AN DANH: chuong "gop y moi" / "nhan them" / "mo lai" gui theo dot (moi gio) chu khong
    gui ngay - gio cua Notification Log khong con trung gio nguoi gui bam."""
    sent = 0
    for r in repo.pending_notify():
        try:
            kind = r.get("pending_event") or C.PENDING_NEW
            repo.set_fields(r["name"], {"notify_pending": 0, "pending_event": None})
            if kind == C.PENDING_NEW:
                new_feedback(r["name"], repo=repo)
            else:
                sender_wrote(r["name"], kind=C.MSG_REOPEN if kind == C.PENDING_REOPEN else C.MSG_REPLY,
                             repo=repo, stamp=str(repo.now()))
            sent += 1
        except Exception:
            repo.log_error("feedback.flush_pending")
    return sent


def remind(repo=None):
    """Scheduler (gio hanh chinh): gui chuong dang cho cua gop y an danh; con <= 1 ngay lam viec ->
    nhac; qua han -> bao ca nhom BGD. Moi gop y nhac MOT lan moi loai cho moi vong."""
    repo = _boot(repo)
    now = repo.now()
    out = {"soon": 0, "late": 0, "pending": flush_pending(repo)}
    for r in repo.open_unresponded():
        try:
            st = S.sla(repo, r, now)
            if st["key"] == "late" and not r.get("reminded_overdue_at"):
                _send(repo, C.EV_OVERDUE, repo.handlers(), "Góp ý quá hạn phản hồi: " + r["title"],
                      st["label"], _inbox_url(r["name"]), r["name"], "feedback_late|%s|%s" % (r["name"], r["due_at"]))
                repo.set_fields(r["name"], {"reminded_overdue_at": now})
                out["late"] += 1
            elif st["key"] == "soon" and not r.get("reminded_soon_at"):
                users = [r["viewed_by"]] if r.get("viewed_by") else repo.handlers()
                _send(repo, C.EV_DUE_SOON, users, "Sắp hết hạn trả lời góp ý: " + r["title"], st["label"],
                      _inbox_url(r["name"]), r["name"], "feedback_soon|%s|%s" % (r["name"], r["due_at"]))
                repo.set_fields(r["name"], {"reminded_soon_at": now})
                out["soon"] += 1
        except Exception:
            repo.log_error("feedback.remind")
    repo.commit()
    return out
