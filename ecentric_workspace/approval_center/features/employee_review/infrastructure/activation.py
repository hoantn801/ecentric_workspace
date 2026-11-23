# Copyright (c) 2026, eCentric and contributors
"""Kich hoat Danh gia nhan su: UAT (2 process Active, the an) vs publish (the hien voi C&B).
System-Manager only, dry-run mac dinh. Patch p450 goi ca hai trong mot buoc (brief 23/11:
"EC Approval Type (Active)"); validate khong qua thi de nguyen, ghi ly do."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.activation_flags import is_dry_run
from ecentric_workspace.approval_center.features.employee_review.infrastructure.setup import (
    PROCESSES, validate_employee_review_v1)

TYPE = "EMPLOYEE_REVIEW"
ROUTE = "approvals/employee-review"
#: The chi hien voi C&B / HR (nguoi gui). NV / LM / CEO vao phieu qua thong bao + "Cho toi duyet".
CARD_ROLES = ("EC CnB", "HR Manager", "System Manager")


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Employee Review activation."), frappe.PermissionError)


@frappe.whitelist()
def enable_employee_review_uat(dry_run=1, apply=0, commit=0):
    """Ca hai process Active; the tren cong van AN."""
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    v = validate_employee_review_v1()
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    report = {"operation": "enable_uat", "mode": "dry_run" if dry else "commit",
              "validation": v, "blockers": blockers, "ready": v["ok"]}
    if dry or blockers:
        return report
    for code, _t, _d in PROCESSES:
        frappe.db.set_value("EC Approval Process", code, "status", "Active")
    frappe.db.commit()
    report["result"] = "%s Active (the chua hien)" % [c for c, _t, _d in PROCESSES]
    return report


@frappe.whitelist()
def publish_employee_review(dry_run=1, apply=0, commit=0):
    """The Active + route, chi hien voi role C&B (Restricted Roles)."""
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    v = validate_employee_review_v1()
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    for code, _t, _d in PROCESSES:
        if frappe.db.get_value("EC Approval Process", code, "status") != "Active":
            blockers.append("process_not_active:%s" % code)
    report = {"operation": "publish", "mode": "dry_run" if dry else "commit",
              "validation": v, "blockers": blockers}
    if dry or blockers:
        return report
    doc = frappe.get_doc("EC Approval Type", TYPE)
    doc.card_status = "Active"
    doc.process_status = "Live"
    doc.route = ROUTE
    doc.visibility_mode = "Restricted Roles"
    have = {r.role for r in doc.get("allowed_roles") or []}
    for role in CARD_ROLES:
        if role not in have and frappe.db.exists("Role", role):
            doc.append("allowed_roles", {"role": role})
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    report["result"] = "the Active, route %s, chi %s" % (ROUTE, CARD_ROLES)
    return report
