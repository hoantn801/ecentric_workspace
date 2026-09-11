# Copyright (c) 2026, eCentric and contributors
"""Kich hoat Booking Request: UAT (process Active, the chua hien) vs publish (the hien).
System-Manager only, dry-run mac dinh, KHONG bao gio chay luc migrate."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.activation_flags import is_dry_run
from ecentric_workspace.approval_center.features.booking_request.infrastructure.setup import (
    validate_booking_request_v1, PROCESS_CODE)

TYPE = "BOOKING_REQUEST"
ROUTE = "approvals/booking-request"


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Booking Request activation."),
                     frappe.PermissionError)


@frappe.whitelist()
def enable_booking_request_uat(dry_run=1, apply=0, commit=0):
    """Process Active; the tren cong van AN (UAT bang duong dan thang)."""
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    v = validate_booking_request_v1()
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    report = {"operation": "enable_uat", "mode": "dry_run" if dry else "commit",
              "validation": v, "blockers": blockers, "ready": v["ok"]}
    if dry or blockers:
        return report
    frappe.db.set_value("EC Approval Process", PROCESS_CODE, "status", "Active")
    frappe.db.commit()
    report["result"] = "%s Active (the chua hien)" % PROCESS_CODE
    return report


@frappe.whitelist()
def publish_booking_request(dry_run=1, apply=0, commit=0):
    """The tren cong Active + gan route - form hien cho moi nguoi trong pham vi."""
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    v = validate_booking_request_v1()
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
    report["result"] = "the Active, route %s" % ROUTE
    return report
