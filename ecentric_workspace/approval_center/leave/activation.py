# Copyright (c) 2026, eCentric and contributors
"""Split activation for Leave: UAT-enable (process Active, card kept INACTIVE for direct-route
UAT) vs public publish (card Active). System-Manager only, dry-run by default, never run at migrate."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.leave.setup import validate_leave_v1

TYPE = "LEAVE_REQUEST"
PROCESS = "LEAVE_REQUEST-V1"
ROUTE = "approvals/leave"


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Leave activation."), frappe.PermissionError)


def _dry(dry_run, apply):
    return int(apply or 0) != 1


@frappe.whitelist()
def enable_leave_uat(dry_run=1, apply=0):
    """Process Active; catalog card kept INACTIVE (direct-route UAT)."""
    _require_sm()
    dry = _dry(dry_run, apply)
    v = validate_leave_v1()
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    report = {"operation": "enable_uat", "mode": "dry_run" if dry else "apply",
              "validation": v, "blockers": blockers, "ready": v["ok"]}
    if not v["ok"]:
        report["result"] = ("BLOCKED (validation failed). Blockers: " + (", ".join(blockers) or "unknown")
                            + ". Tip: run setup_leave_v1(apply=1) first if the process is missing.")
        return report
    if not dry:
        frappe.db.set_value("EC Approval Process", PROCESS, "status", "Active")
        try:
            frappe.get_doc("EC Approval Process", PROCESS).add_comment(
                "Comment", _("Leave UAT enabled (process Active; catalog card kept inactive)."))
        except Exception:
            pass
        report["result"] = "UAT_ENABLED"
    else:
        report["result"] = "DRY_RUN_OK"
    report["card_status"] = frappe.db.get_value("EC Approval Type", TYPE, "card_status")
    return report


@frappe.whitelist()
def publish_leave_after_uat(dry_run=1, apply=0):
    """Public go-live AFTER UAT sign-off: activate the catalog card + route. Blocked unless Active."""
    _require_sm()
    dry = _dry(dry_run, apply)
    v = validate_leave_v1()
    active = frappe.db.get_value("EC Approval Process", PROCESS, "status") == "Active"
    ok = v["ok"] and active
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    if not active:
        blockers = blockers + ["process not Active (run enable_leave_uat(apply=1) first)"]
    report = {"operation": "publish", "mode": "dry_run" if dry else "apply",
              "validation": v, "process_active": active, "blockers": blockers, "ready": ok}
    if not ok:
        report["result"] = ("BLOCKED (nothing changed). Blockers: " + (", ".join(blockers) or "unknown"))
        return report
    if not dry:
        frappe.db.set_value("EC Approval Type", TYPE,
                            {"card_status": "Active", "process_status": "Live", "route": "/" + ROUTE})
        try:
            frappe.get_doc("EC Approval Type", TYPE).add_comment(
                "Comment", _("Leave published (catalog card Active)."))
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
