# Copyright (c) 2026, eCentric and contributors
"""p003: Trung tam Du lieu dot 3 - Data Request cua Approval Center chuyen sang /du-lieu.

  1. The "Data Request" (EC Approval Type DATA_REQUEST) tro /du-lieu - DOI DU LIEU route, khong sua
     code trang catalog. Lam TRUOC buoc 2: tu luc nay Approval Center tu choi gui phieu Data Request
     moi (features/data_request/application/service.submit), nen khong con phieu moi lot giua chung.
  2. migration.migrate_legacy(dry_run=0): moi EC Data Request -> EC Data Ticket (legacy_ref = ma cu,
     giu nguoi gui / phong ban / mo ta / tep (gan lai File cu, khong chep) / lich su duyet voi gio goc).
     Yeu cau Dang xu ly chua co task /pm -> tao task qua pm_sync. Phieu cu GIU NGUYEN (khong sua, khong
     xoa) de doi chieu.
Chay lai bao nhieu lan cung duoc (phieu da chuyen -> bo qua; route da doi -> khong ghi). FAIL-SAFE: moi
buoc trong try, loi -> Error Log, KHONG BAO GIO chan migrate. Bao cao ghi vao logger "data_hub";
System Manager xem lai bang api.legacy_migration_report (dry run).
"""
import json

import frappe

TITLE = "data_hub p003 chuyen phieu Data Request cu"


def _try(step, fn):
    try:
        return fn()
    except Exception:
        frappe.log_error(title="%s: %s" % (TITLE, step), message=frappe.get_traceback())
        return None


def _short(rep):
    if not isinstance(rep, dict):
        return rep
    out = {k: rep.get(k) for k in ("dry_run", "total", "counts", "pm_tasks", "pm_linked", "note")}
    for k in ("created", "exists", "skipped", "errors"):
        out[k] = len(rep.get(k) or ())
    out["skipped_detail"] = rep.get("skipped") or []
    out["errors_detail"] = rep.get("errors") or []
    return out


def execute():
    from ecentric_workspace.data_hub import constants as C
    if not frappe.db.exists("DocType", C.TICKET_DT):
        return
    from ecentric_workspace.data_hub import migration
    catalog = _try("catalog route", migration.redirect_catalog)
    report = _try("migrate", lambda: migration.migrate_legacy(dry_run=0))
    msg = json.dumps({"catalog": catalog, "migration": _short(report)}, ensure_ascii=False, default=str)
    try:
        frappe.logger("data_hub").info("p003: " + msg[:4000])
    except Exception:
        pass
    if report and report.get("errors"):
        frappe.log_error(title="%s: %d phieu loi" % (TITLE, len(report["errors"])), message=msg[:10000])
