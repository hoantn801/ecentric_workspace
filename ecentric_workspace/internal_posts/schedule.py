# Copyright (c) 2026, eCentric and contributors
"""Hen gio dang (mockup v6, PO duyet 03/10/2026).

Bai hen gio = bai NHAP (published = 0) co publish_at. Truoc gio do chi HR thay (permission
query chi cho doc bai da dang). Job moi 5 phut (hooks: scheduler_events cron) lay cac bai toi
gio, bat "da dang" va luu - lifecycle lo phan con lai y nhu HR bam "Dang bai": ghi
published_on, xep job bao tin (chuong / Teams / popup tinh 7 ngay tu luc bai len).

Idempotent: bai da dang / da bo hen thi bo qua. Loi mot bai khong dung ca dot.
  * Loi NGHIEP VU (validate: thieu chuyen muc, han...) -> BO HEN + chuong bao nguoi hen (thu lai
    cung hong, khong de ra Error Log moi 5 phut).
  * Loi TAM THOI (khoa DB 1205, deadlock, mat ket noi - job chay dung khung :00/:15/:30/:45) ->
    rollback, GIU hen, lan sau thu lai; qua GIVE_UP_HOURS gio van hong thi moi bo hen.
"""
import datetime

from ecentric_workspace.internal_posts import constants as C
from ecentric_workspace.internal_posts import domain as D

GIVE_UP_HOURS = 6


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.internal_posts import repository
    return repository


def publish_due(repo=None):
    repo = _repo(repo)
    now = repo.now()
    out = {"published": [], "failed": []}
    for name in repo.due_scheduled(now):
        try:
            doc = repo.get_post(name)
            at = D.as_datetime(doc.get("publish_at"))
            if doc.get("published") or not at or at > now:
                continue
            doc.published = 1
            doc.publish_at = None
            repo.save_post_system(doc)
            repo.commit()
            out["published"].append(name)
        except Exception as exc:
            repo.rollback()
            repo.log_error("internal_posts.schedule.publish_due")
            out["failed"].append(name)
            try:
                at = D.as_datetime(repo.get_post(name).get("publish_at"))
            except Exception:
                continue                            # DB dang hong: de lan sau
            stale = not at or now - at > datetime.timedelta(hours=GIVE_UP_HOURS)
            if repo.is_validation_error(exc) or stale:
                _give_up(repo, name, exc)
    return out


def _give_up(repo, name, exc):
    """Bo hen + bao nguoi hen. Bai nam lai o tab Nhap de HR sua roi dang tay."""
    try:
        doc = repo.get_post(name)
        repo.set_post_fields(name, {"publish_at": None})
        repo.commit()
        msg = str(exc).replace("<br>", " ")[:300] or "Lỗi hệ thống."
        repo.send_bell(C.NOTIFY_EVENT, doc.get("owner"), "Bài hẹn giờ chưa đăng được: %s" % (doc.get("title") or ""),
                       msg + " Bài đang ở tab Nháp, sửa rồi đăng lại.",
                       "%s?bai=%s" % (C.ROUTE_COMPOSE, name), name, "internal_post_sched_fail|%s|%s" % (name, repo.now()))
        repo.commit()
    except Exception:
        repo.log_error("internal_posts.schedule.give_up")
