# Copyright (c) 2026, eCentric and contributors
"""Kich hoat Discipline Decision: process Active + the AN tren cong (phieu chi sinh tu ho so ky
luat, khong ai tao tu cong). System-Manager only, dry-run mac dinh. Patch p460 goi ham nay."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.activation_flags import is_dry_run
from ecentric_workspace.approval_center.features.discipline_decision.infrastructure.setup import (
    PROCESS_CODE, validate_discipline_decision_v1)

TYPE = "DISCIPLINE_DECISION"
ROUTE = "/ky-luat/quyet-dinh"


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Discipline Decision activation."), frappe.PermissionError)


@frappe.whitelist()
def activate_discipline_decision(dry_run=1, apply=0, commit=0):
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    v = validate_discipline_decision_v1()
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    report = {"operation": "activate", "mode": "dry_run" if dry else "commit", "validation": v,
              "blockers": blockers}
    if dry or blockers:
        return report
    frappe.db.set_value("EC Approval Process", PROCESS_CODE, "status", "Active")
    # The KHONG hien tren cong (Coming Soon = khong co nut tao) nhung route van dung cho link
    # thong bao / hub "Tat ca yeu cau" mo dung trang quyet dinh.
    frappe.db.set_value("EC Approval Type", TYPE, {"process_status": "Live", "route": ROUTE})
    frappe.db.commit()
    report["result"] = "%s Active, route %s" % (PROCESS_CODE, ROUTE)
    return report
