# Copyright (c) 2026, eCentric and contributors
"""Split activation for Outside Work: UAT-enable (process Active, card kept
INACTIVE for direct-route UAT) vs public publish (card Active). System-Manager
only, dry-run by default, audited, never run at migrate."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.outside_work.setup import validate_outside_work_v1

TYPE = "OUTSIDE_WORK"
PROCESS = "OUTSIDE_WORK-V1"
ROUTE = "approvals/outside-work"


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Outside Work activation."), frappe.PermissionError)


def _dry(dry_run, apply):
    return not (int(apply) == 1 and int(dry_run) == 0)


@frappe.whitelist()
def enable_outside_work_uat(dry_run=1, apply=0):
    """Process Active; catalog card kept INACTIVE (direct-route UAT)."""
    _require_sm()
    dry = _dry(dry_run, apply)
    v = validate_outside_work_v1()
    report = {"operation": "enable_uat", "mode": "dry_run" if dry else "apply",
              "validation": v, "ready": v["ok"]}
    if not v["ok"]:
        report["result"] = "BLOCKED (validation failed - nothing changed)"
        return report
    if not dry:
        frappe.db.set_value("EC Approval Process", PROCESS, "status", "Active")
        try:
            frappe.get_doc("EC Approval Process", PROCESS).add_comment(
                "Comment", _("Outside Work UAT enabled (process Active; catalog card kept inactive)."))
        except Exception:
            pass
        report["result"] = "UAT_ENABLED"
    else:
        report["result"] = "DRY_RUN_OK"
    report["card_status"] = frappe.db.get_value("EC Approval Type", TYPE, "card_status")
    return report


@frappe.whitelist()
def publish_outside_work_after_uat(dry_run=1, apply=0):
    """Public go-live AFTER UAT sign-off: activate the catalog card + route.
    Blocked unless the process is already Active."""
    _require_sm()
    dry = _dry(dry_run, apply)
    v = validate_outside_work_v1()
    active = frappe.db.get_value("EC Approval Process", PROCESS, "status") == "Active"
    ok = v["ok"] and active
    report = {"operation": "publish", "mode": "dry_run" if dry else "apply",
              "validation": v, "process_active": active, "ready": ok}
    if not ok:
        report["result"] = "BLOCKED (UAT not enabled or validation failed - nothing changed)"
        return report
    if not dry:
        frappe.db.set_value("EC Approval Type", TYPE,
                            {"card_status": "Active", "process_status": "Live", "route": "/" + ROUTE})
        try:
            frappe.get_doc("EC Approval Type", TYPE).add_comment(
                "Comment", _("Outside Work published (catalog card Active)."))
        except Exception:
            pass
        report["result"] = "PUBLISHED"
    else:
        report["result"] = "DRY_RUN_OK"
    return report


@frappe.whitelist()
def verify_activation():
    _require_sm()
    return {
        "process_status": frappe.db.get_value("EC Approval Process", PROCESS, "status"),
        "card_status": frappe.db.get_value("EC Approval Type", TYPE, "card_status"),
        "catalog_process_status": frappe.db.get_value("EC Approval Type", TYPE, "process_status"),
        "route": frappe.db.get_value("EC Approval Type", TYPE, "route"),
    }
