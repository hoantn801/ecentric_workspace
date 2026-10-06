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
