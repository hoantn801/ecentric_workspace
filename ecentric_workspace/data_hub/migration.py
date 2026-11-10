# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu dot 3 - CHUYEN phieu Data Request cu sang EC Data Ticket + tro the "Data Request"
cua Approval Center sang /du-lieu.

  migrate_legacy(dry_run=1)  - doc moi EC Data Request, lap ke hoach bang legacy.build_ticket (quy tac
                               thuan, bang chuyen doi o legacy.py / README) va:
                                 dry_run=1 -> CHI tra bao cao (khong ghi gi);
                                 dry_run=0 -> tao ticket (legacy_ref = ma cu, gio tao = gio gui cu),
                                              gan LAI cac File cu (khong chep noi dung), ghi nhat ky
                                              tu EC Approval Action GIU GIO GOC; yeu cau Dang xu ly
                                              chua co task /pm -> tao task qua pm_sync (cong cua dot 1).
                               Chay lai bao nhieu lan cung duoc: phieu da co ticket (legacy_ref) -> bo qua.
                               Moi phieu mot savepoint: phieu loi khong de lai ticket do dang, khong
                               chan cac phieu khac. KHONG gui thong bao (chuyen hang loat), KHONG sua /
                               xoa phieu cu (giu nguyen de doi chieu).
  redirect_catalog()         - doi route the DATA_REQUEST (EC Approval Type) sang /du-lieu - cau hinh, khong
                               phai code. Chi doi khi route dang la route cu (khong de len route da chinh tay).
                               Tu luc nay: the trong /approvals mo /du-lieu; link cu `<route>?id=EC-DATA-...`
                               (thong bao, Viec cua toi) thanh /du-lieu?id=... va trang tu tim ticket theo
                               ma cu; Approval Center tu choi GUI phieu Data Request moi
                               (data_request.application.service.submit).
Patch data_hub/patches/p003 goi ca hai (dry_run=0). api.legacy_migration_report (System Manager) chay
lai dry run bat cu luc nao.
"""
from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import legacy as L
from ecentric_workspace.data_hub import service as S


def _flag(v):
    return v not in (0, "0", False, "false", "False", None, "")


def migrate_legacy(dry_run=1, repo=None, pm=None):
    """-> bao cao {dry_run, total, counts{trang thai}, created[], exists[], skipped[], errors[], pm_tasks}."""
    repo = S._repo(repo)
    dry = _flag(dry_run)
    rep = {"dry_run": dry, "total": 0, "counts": {}, "created": [], "exists": [], "skipped": [], "errors": [],
           "pm_tasks": 0, "pm_linked": 0}
    if not repo.legacy_ready():
        rep["note"] = "Không có DocType %s - không có gì để chuyển." % C.LEGACY_DT
        return rep
    rules = S.rules(repo)
    today, hol, now = repo.today(), repo.holidays(), repo.now()
    from ecentric_workspace.data_hub import pm_sync
    sync_on = pm_sync.enabled(repo)
    for rec in repo.legacy_requests():
        ref = rec.get("name")
        rep["total"] += 1
        code = repo.find_by_legacy(ref)
        if code:
            rep["exists"].append({"ref": ref, "code": code})
            continue
        try:
            actions = repo.legacy_actions(rec["approval_request"]) if rec.get("approval_request") else []
            plan = L.build_ticket(rec, actions, rules, today, hol, now=now)
            if plan.get("skip"):
                rep["skipped"].append({"ref": ref, "reason": plan["skip"]})
                continue
            files = repo.legacy_files(ref, [rec.get("request_attachment"), rec.get("output_attachment")])
        except Exception as e:
            repo.log_error("Data Hub legacy plan %s" % ref)
            rep["errors"].append({"ref": ref, "error": str(e)[:300]})
            continue
        v = plan["values"]
        item = {"ref": ref, "title": v["title"], "status": v["status"], "type": v["request_type"],
                "priority": v["proposed_priority"], "assignee": v.get("assignee") or "", "requester": v["requester"],
                "due": str(v.get("due_date") or ""), "files": len(files), "logs": len(plan["logs"]),
                "pm_task": "sẽ tạo" if (v["status"] == C.ST_DOING and sync_on) else ""}
        rep["counts"][v["status"]] = rep["counts"].get(v["status"], 0) + 1
        if dry:
            rep["created"].append(item)
            continue
        sp = repo.savepoint("edh_legacy")
        try:
            code = repo.insert_migrated(v, plan["created"])
            if files:
                repo.link_files(code, files)
            for lg in plan["logs"]:
                repo.insert_log_at({"ticket": code, "event": lg["event"], "actor": lg["actor"] or C.SYSTEM_USER,
                                    "source": C.SRC_SYSTEM, "from_value": str(lg["from_value"] or "")[:140],
                                    "to_value": str(lg["to_value"] or "")[:140], "note": lg["note"] or ""}, lg["at"])
        except Exception as e:
            repo.rollback_savepoint(sp)
            repo.log_error("Data Hub legacy insert %s" % ref)
            rep["counts"][v["status"]] -= 1
            rep["errors"].append({"ref": ref, "error": str(e)[:300]})
            continue
        item["code"] = code
        item["pm_task"] = ""
        if v["status"] == C.ST_DOING and sync_on:
            item["pm_task"] = _pm_task(repo, code, ref, pm, rep)
        rep["created"].append(item)
    return rep


def _pm_task(repo, code, ref, pm, rep):
    """Yeu cau Dang xu ly: task /pm cu da nhac ma phieu (go tay) -> gan vao; khong co -> tao qua
    pm_sync.push_accept (cung cong voi "Nhan viec"). Loi /pm khong lam hong viec chuyen."""
    from ecentric_workspace.data_hub import pm_sync
    try:
        existing = repo.task_for_legacy(ref)
        if existing:
            repo.set_fields(code, {"pm_task": existing})
            S.log(repo, code, C.EV_PM, C.SYSTEM_USER, source=C.SRC_PM, to_value="Gắn task /pm có sẵn " + existing)
            rep["pm_linked"] += 1
            return existing
        task, _warn = pm_sync.push_accept(repo, repo.get(code), C.SYSTEM_USER, pm=pm)
        if task:
            rep["pm_tasks"] += 1
        return task or ""
    except Exception:
        repo.log_error("Data Hub legacy pm %s" % code)
        return ""


def redirect_catalog(repo=None):
    """The "Data Request" trong Approval Center -> /du-lieu. -> {action, before, after}."""
    repo = S._repo(repo)
    before = repo.approval_type_route(C.LEGACY_APPROVAL_TYPE)
    if before is None:
        return {"action": "skipped", "reason": "Không có EC Approval Type %s" % C.LEGACY_APPROVAL_TYPE}
    if (before or "").rstrip("/") == C.ROUTE:
        return {"action": "unchanged", "before": before, "after": before}
    if (before or "") not in C.LEGACY_ROUTES:
        return {"action": "refused", "reason": "route đã bị chỉnh tay, không ghi đè", "before": before}
    repo.set_approval_type_route(C.LEGACY_APPROVAL_TYPE, C.ROUTE,
                                 "Data Request đã chuyển sang Trung tâm Dữ liệu (%s) - route cũ: %s" % (
                                     C.ROUTE, before or "(trống)"))
    return {"action": "updated", "before": before, "after": C.ROUTE}


def run_for(user, dry_run=1, repo=None, pm=None):
    """Cua cho api: CHI System Manager (chay lai dry run / chay that sau khi doc bao cao)."""
    repo = S._repo(repo)
    if not repo.is_admin(user):
        raise S.Forbidden("Chỉ quản trị hệ thống (System Manager) mới xem / chạy chuyển phiếu cũ.")
    return migrate_legacy(dry_run=dry_run, repo=repo, pm=pm)
