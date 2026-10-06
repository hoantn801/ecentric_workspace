# Copyright (c) 2026, eCentric and contributors
"""Thu vien tai lieu ISO - thong bao khi tai lieu chuyen buoc (job nen sau commit).

service.on_update xep job state_changed (enqueue_after_commit) moi khi trang thai doi qua luong
duyet - bam tren /tai-lieu/quan-ly, /tai-lieu/soan hay tren desk deu vao day. Nhap file cu
(repository.force_published, db.set_value) khong qua on_update -> khong bao ai.

Ai nhan, noi dung gi: domain.notify_plan (thuan, co test). Link tro /tai-lieu/... - KHONG BAO
GIO /app (QC gate test_no_desk_urls). Loi mot nguoi nhan khong chan nguoi khac; loi job khong
anh huong tai lieu (da luu xong tu truoc). Dedupe theo (tai lieu, trang thai, lan luu).
"""
from ecentric_workspace.iso_docs import constants as C
from ecentric_workspace.iso_docs import domain as D


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.iso_docs import repository
    return repository


def state_changed(name, before, after, actor, stamp="", repo=None):
    """-> {"sent": n, "failed": m} hoac {"skipped": ly do}."""
    repo = _repo(repo)
    if repo.conf_flag("ec_iso_notify_disabled"):
        return {"skipped": "disabled"}
    doc = repo.get_doc_any(name)
    if not doc:
        return {"skipped": "missing"}
    if not D.is_state(doc.get(C.STATE_FIELD), after):
        return {"skipped": "moved"}          # da chuyen buoc tiep truoc khi job chay
    note = ""
    if D.is_state(after, C.S_DRAFT):
        note = repo.last_note(name, actor)
    plan = D.notify_plan(before, after, doc, actor, repo.role_users(C.ROLE_ISO),
                         repo.role_users(C.ROLE_CEO), note)
    sent = failed = 0
    for n in plan:
        try:
            repo.notify(n["event"], n["to"], n["title"], n["message"], n["url"], name, actor,
                        "iso|%s|%s|%s|%s" % (name, D.norm_state(after), stamp, n["to"]))
            sent += 1
        except Exception:
            failed += 1
            repo.log_error("iso_docs.notify")
    return {"sent": sent, "failed": failed}


def review_digest(repo=None):
    """MOT tin gom cho moi nguoi Ban ISO - bao nhieu tai lieu qua han / sap den han ra soat (30 ngay).
    CHUA GAN LICH: PO 06/10 chon "chua nhac" (56/60 tai lieu chuyen tu SharePoint deu qua han).
    Khi can bat: them vao hooks.py
        scheduler_events["cron"].setdefault("40 8 * * 1", []).append(
            "ecentric_workspace.iso_docs.notify.review_digest")
    Khong co gi -> khong gui. Tat: site_config ec_iso_review_reminder_disabled = 1."""
    from ecentric_workspace.iso_docs import view as V
    repo = _repo(repo)
    if repo.conf_flag("ec_iso_review_reminder_disabled"):
        return {"skipped": "disabled"}
    today = repo.today()
    rows = repo.all_docs_for_review()
    over = sorted(r.get("ec_doc_code") or r.get("name") for r in rows if V.review_due(r, today) == "qua-han")
    soon = sorted(r.get("ec_doc_code") or r.get("name") for r in rows if V.review_due(r, today) == "sap-den-han")
    if not over and not soon:
        return {"skipped": "none"}
    parts = []
    if over:
        parts.append("%d quá hạn" % len(over))
    if soon:
        parts.append("%d sắp đến hạn" % len(soon))
    title = "Tài liệu ISO cần rà soát: " + ", ".join(parts)
    sample = (soon + over)[:6]
    msg = "Ví dụ: %s%s. Rà soát xong mà nội dung vẫn đúng thì bấm \"Đã rà soát, giữ nguyên\"." % (
        ", ".join(sample), "…" if len(over) + len(soon) > len(sample) else "")
    y, w, _d = today.isocalendar()
    sent = failed = 0
    for u in repo.role_users(C.ROLE_ISO):
        try:
            repo.notify("task_due_soon", u, title, msg, "/tai-lieu/quan-ly?loc=ra-soat", None, "Administrator",
                        "iso_review|%d-W%02d|%s" % (y, w, u))
            sent += 1
        except Exception:
            failed += 1
            repo.log_error("iso_docs.review_digest")
    return {"sent": sent, "failed": failed, "over": len(over), "soon": len(soon)}
