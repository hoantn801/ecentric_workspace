# Copyright (c) 2026, eCentric and contributors
"""Xac nhan da doc (mockup v6, PO duyet 03/10/2026).

Chi bai HR bat "Bat buoc xac nhan da doc" (quy che, chinh sach). Khac "Luot xem" (mo bai la
tinh): o day nguoi doc CHU DONG bam "Toi da doc va hieu". Luu chung bang EC Read Receipt voi
kind = "ack" (platform/read_receipt.py) - khong lam bang moi.

  * view()       : so da / chua xac nhan, han, ten nguoi CHUA xac nhan (chi HR).
  * ack()        : nguoi trong pham vi bam xac nhan (bai da dang). Bam lai = khong doi gi.
  * remind()     : HR nhac tay nguoi chua xac nhan - toi da 1 lan / bai / ngay.
  * remind_due() : job 09:00 hang ngay - tu nhac 1 ngay truoc han va dung ngay han.
  * export()     : danh sach cho Excel (ai, phong nao, xac nhan luc nao).
Chuong di qua notification_center (event "announcement": chuong, KHONG Teams). Link tro
/tin-noi-bo/<slug>, khong bao gio /app.
"""
import datetime

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import domain as D
from ecentric_workspace.internal_posts.audience import audience
from ecentric_workspace.internal_posts.errors import Forbidden, NotFound, PostError


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.internal_posts import repository
    return repository


def _depts(doc):
    return [r.get("department") for r in (doc.get("departments") or []) if r.get("department")]


def view(repo, doc, user, editor):
    """Khoi "Xac nhan da doc" tren trang bai. None khi bai khong bat buoc xac nhan."""
    if not doc.get("require_ack"):
        return None
    today = repo.today()
    aud = audience(repo, _depts(doc))
    acked = repo.ack_users(doc.get("name"))
    names = repo.full_names(list(acked) + (list(aud) if editor else []))
    s = D.seen_summary(aud, acked, names, user, editor)
    dl = doc.get("ack_deadline")
    reminded = D.as_date(doc.get("ack_reminded_on"))
    s.update({
        "deadline_label": D.date_label(dl), "deadline_short": D.short_date(dl),
        "days_left": D.ack_days_left(dl, today), "overdue": bool(D.as_date(dl) and D.as_date(dl) < today),
        "auto_label": " và ".join(D.short_date(x) for x in D.ack_remind_dates(dl)),
        "reminded_today": bool(reminded and reminded == today),
        "reminded_label": D.date_label(reminded) if reminded else "",
        "can_ack": bool(doc.get("published")) and s["me_in_audience"] and not s["me_seen"],
        "acked": s["seen"], "not_acked": s["not_seen"],
    })
    return s


def _load(repo, user, name):
    if not user or user == "Guest":
        raise PostError("Cần đăng nhập")
    if not name or not repo.post_exists(name):
        raise NotFound(name)
    return repo.get_post(name)


def ack(user, name, repo=None):
    """Nguoi dang dang nhap bam "Toi da doc va hieu"."""
    repo = _repo(repo)
    doc = _load(repo, user, name)
    if not repo.can(doc, "read", user):
        raise PostError("Bạn không có quyền xem bài này")
    if not doc.get("published") or not doc.get("require_ack"):
        raise PostError("Bài này không cần xác nhận.")
    if user not in set(audience(repo, _depts(doc))):
        raise PostError("Bài này không yêu cầu bạn xác nhận.")
    repo.mark_seen(name, user)           # xac nhan thi chac chan da mo bai
    first = repo.mark_ack(name, user)
    v = view(repo, doc, user, False)
    return {"first": bool(first), "acked": v["acked"], "total": v["total"], "not_acked": v["not_acked"],
            "pct": v["pct"]}


def _not_acked(repo, doc):
    acked = repo.ack_users(doc.get("name"))
    return [u for u in audience(repo, _depts(doc)) if u not in acked]


def _bell(repo, doc, users, dedupe, actor=None):
    """Gui chuong nhac; -> so nguoi gui duoc. Loi tung nguoi khong dung ca dot."""
    url = "%s/%s" % (C.ROUTE, doc.get("slug"))
    dl = D.date_label(doc.get("ack_deadline"))
    left = D.ack_days_left(doc.get("ack_deadline"), repo.today())
    title = "Nhắc xác nhận đã đọc: %s" % (doc.get("title") or "")
    msg = ("Hạn xác nhận %s (%s). " % (dl, left) if dl else "") + "Mở bài, đọc hết rồi bấm \"Tôi đã đọc và hiểu\"."
    sent = 0
    for u in users:
        try:
            repo.send_bell(C.NOTIFY_EVENT, u, title, msg, url, doc.get("name"), dedupe % u, actor=actor)
            sent += 1
        except Exception:
            repo.log_error("internal_posts.ack.bell")
    return sent


def remind(user, name, repo=None):
    """HR bam "Nhac N nguoi chua xac nhan" - toi da 1 lan / bai / ngay."""
    repo = _repo(repo)
    if not repo.is_editor(user):
        raise Forbidden("Chỉ HR được nhắc xác nhận.")
    doc = _load(repo, user, name)
    if not doc.get("published") or not doc.get("require_ack"):
        raise PostError("Bài chưa đăng hoặc không bắt buộc xác nhận.")
    today = repo.today()
    if D.as_date(doc.get("ack_reminded_on")) == today:
        raise PostError("Hôm nay đã nhắc bài này rồi. Mai nhắc tiếp được.")
    targets = _not_acked(repo, doc)
    if not targets:
        raise PostError("Mọi người đã xác nhận, không còn ai để nhắc.")
    sent = _bell(repo, doc, targets, "internal_post_ack|%s|manual|%s|%%s" % (name, today), actor=user)
    repo.set_post_fields(name, {"ack_reminded_on": today})
    return {"sent": sent, "reminded_label": D.date_label(today)}


def remind_due(repo=None):
    """Job 09:00 moi ngay: bai bat buoc xac nhan co han la ngay mai / hom nay -> nhac nguoi chua
    xac nhan. Idempotent (dedupe theo bai + nguoi + ngay). Loi mot bai khong dung ca dot."""
    repo = _repo(repo)
    today = repo.today()
    dates = [today, today + datetime.timedelta(days=C.ACK_REMIND_DAYS_BEFORE)]
    out = {"posts": 0, "sent": 0}
    for name in repo.ack_due_posts(dates):
        try:
            doc = repo.get_post(name)
            if not D.ack_remind_due(doc.get("ack_deadline"), today) or D.expired(doc, today):
                continue
            out["posts"] += 1
            out["sent"] += _bell(repo, doc, _not_acked(repo, doc), "internal_post_ack|%s|auto|%s|%%s" % (name, today))
        except Exception:
            repo.log_error("internal_posts.ack.remind_due")
    repo.commit()
    return out


EXPORT_HEADER = ["Họ tên", "Email", "Phòng ban", "Đã mở bài", "Đã xác nhận", "Xác nhận lúc"]


def export(user, name, repo=None):
    """HR tai danh sach xac nhan. -> (ten_tep, rows) - nguoi chua xac nhan len truoc."""
    repo = _repo(repo)
    if not repo.is_editor(user):
        raise Forbidden("Chỉ HR được tải danh sách.")
    doc = _load(repo, user, name)
    aud = audience(repo, _depts(doc))
    times = repo.ack_times(name)
    seen = set(repo.seen_users(name))
    names = repo.full_names(aud)
    depts = repo.user_departments(aud)
    rows = []
    for u in aud:
        at = D.as_datetime(times.get(u))
        rows.append([names.get(u) or u, u, depts.get(u) or "", "Có" if u in seen else "Chưa",
                     "Có" if u in times else "Chưa", at.strftime("%d/%m/%Y %H:%M") if at else ""])
    rows.sort(key=lambda r: (r[4] == "Có", (r[2] or "").lower(), (r[0] or "").lower()))
    return "xac-nhan-%s.xlsx" % (doc.get("slug") or name), [EXPORT_HEADER] + [[_cell(c) for c in r] for r in rows]


def _cell(v):
    """Chan cong thuc Excel tu du lieu nguoi dung (ten '=HYPERLINK(...)')."""
    v = str(v or "")
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v
