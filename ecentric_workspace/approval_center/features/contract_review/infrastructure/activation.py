# Copyright (c) 2026, eCentric and contributors
"""Activation for Contract Review: UAT-enable (process Active, card inactive) vs
publish (card Active). System-Manager only, dry-run default, never run at migrate."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.activation_flags import is_dry_run

from ecentric_workspace.approval_center.features.contract_review.infrastructure.setup import (
    validate_contract_review_v1, PROCESS_CODE)

TYPE = "CONTRACT_REVIEW"
ROUTE = "approvals/contract-review"


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Contract Review activation."), frappe.PermissionError)


@frappe.whitelist()
def enable_contract_review_uat(dry_run=1, apply=0, commit=0):
    """Process Active; catalog card kept INACTIVE (direct-route UAT)."""
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    v = validate_contract_review_v1()
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    report = {"operation": "enable_uat", "mode": "dry_run" if dry else "commit",
              "validation": v, "blockers": blockers, "ready": v["ok"]}
    if dry or blockers:
        return report
    frappe.db.set_value("EC Approval Process", PROCESS_CODE, "status", "Active")
    frappe.db.commit()
    report["result"] = "%s Active (card inactive)" % PROCESS_CODE
    return report


@frappe.whitelist()
def publish_contract_review(dry_run=1, apply=0, commit=0):
    """Catalog card Active + route set — form appears for everyone in scope."""
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    v = validate_contract_review_v1()
    active = frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active"
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    if not active:
        blockers.append("process_not_active")
    report = {"operation": "publish", "mode": "dry_run" if dry else "commit",
              "validation": v, "blockers": blockers}
    if dry or blockers:
        return report
    frappe.db.set_value("EC Approval Type", TYPE,
                        {"card_status": "Active", "process_status": "Live", "route": ROUTE})
    frappe.db.commit()
    report["result"] = "card Active, route %s" % ROUTE
    return report
