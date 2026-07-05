# Copyright (c) 2026, eCentric and contributors
"""Split activation for Daily Target: UAT-enable BOTH processes (Project +
Consolidated) Active with the catalog card kept INACTIVE, vs publish (card Active).
System-Manager only, dry-run by default, audited, never run at migrate."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.daily_target.setup import (
    validate_daily_target_v1, PROCESS_PROJECT, PROCESS_CONSOLIDATED)

TYPE = "DAILY_TARGET"
ROUTE = "approvals/daily-target"


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Daily Target activation."), frappe.PermissionError)


def _dry(dry_run, apply):
    return int(apply or 0) != 1


@frappe.whitelist()
def enable_daily_target_uat(dry_run=1, apply=0):
    """Both Daily Target processes Active; catalog card kept INACTIVE (direct-route UAT)."""
    _require_sm()
    dry = _dry(dry_run, apply)
    v = validate_daily_target_v1()
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    report = {"operation": "enable_uat", "mode": "dry_run" if dry else "apply",
              "validation": v, "blockers": blockers, "ready": v["ok"]}
    if not v["ok"]:
        report["result"] = ("BLOCKED (validation failed - nothing changed). Blockers: "
                            + (", ".join(blockers) or "unknown")
                            + ". Tip: run setup_daily_target_v1(apply=1) first if a process is missing.")
        return report
    if not dry:
        for code in (PROCESS_PROJECT, PROCESS_CONSOLIDATED):
            frappe.db.set_value("EC Approval Process", code, "status", "Active")
        report["result"] = "UAT_ENABLED"
    else:
        report["result"] = "DRY_RUN_OK"
    report["card_status"] = frappe.db.get_value("EC Approval Type", TYPE, "card_status")
    return report


@frappe.whitelist()
def publish_daily_target_after_uat(dry_run=1, apply=0):
    """Public go-live AFTER UAT: activate the catalog card. Blocked unless BOTH processes Active."""
    _require_sm()
    dry = _dry(dry_run, apply)
    v = validate_daily_target_v1()
    both_active = all(frappe.db.get_value("EC Approval Process", c, "status") == "Active"
                      for c in (PROCESS_PROJECT, PROCESS_CONSOLIDATED))
    ok = v["ok"] and both_active
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    if not both_active:
        blockers = blockers + ["both processes must be Active (run enable_daily_target_uat(apply=1) first)"]
    report = {"operation": "publish", "mode": "dry_run" if dry else "apply",
              "validation": v, "processes_active": both_active, "blockers": blockers, "ready": ok}
    if not ok:
        report["result"] = "BLOCKED (nothing changed). Blockers: " + (", ".join(blockers) or "unknown")
        return report
    if not dry:
        frappe.db.set_value("EC Approval Type", TYPE,
                            {"card_status": "Active", "process_status": "Live", "route": "/" + ROUTE})
        report["result"] = "PUBLISHED"
    else:
        report["result"] = "DRY_RUN_OK"
    return report


@frappe.whitelist()
def verify_activation():
    _require_sm()
    return {
        "project_status": frappe.db.get_value("EC Approval Process", PROCESS_PROJECT, "status"),
        "consolidated_status": frappe.db.get_value("EC Approval Process", PROCESS_CONSOLIDATED, "status"),
        "card_status": frappe.db.get_value("EC Approval Type", TYPE, "card_status"),
        "route": frappe.db.get_value("EC Approval Type", TYPE, "route"),
    }
