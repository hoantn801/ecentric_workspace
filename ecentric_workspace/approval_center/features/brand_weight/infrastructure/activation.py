# Copyright (c) 2026, eCentric and contributors
"""Bat BRAND_WEIGHT: process Active + gan route cho EC Approval Type (de link tu hub
'Cho duyet' mo dung trang). Chi System Manager, mac dinh dry-run, khong chay luc migrate.
The trong danh muc phe duyet GIU NGUYEN: nguoi dung vao qua menu Nhan su."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.activation_flags import is_dry_run
from ecentric_workspace.approval_center.features.brand_weight.infrastructure.setup import (
    PROCESS_CODE, SELF_PROCESS_CODE, validate_brand_weight_v1,
)

TYPE = "BRAND_WEIGHT"
ROUTE = "ec-hr/phan-bo-cong-viec"


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Brand Weight activation."), frappe.PermissionError)


@frappe.whitelist()
def enable_brand_weight(dry_run=1, apply=0, commit=0):
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    v = validate_brand_weight_v1()
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")]
    report = {"operation": "enable", "mode": "dry_run" if dry else "commit",
              "validation": v, "blockers": blockers}
    if not v["ok"]:
        report["result"] = "BLOCKED: " + ", ".join(blockers) + ". Chay setup_brand_weight_v1(apply=1) truoc."
        return report
    if dry:
        report["result"] = "DRY_RUN_OK"
        return report
    for code in (PROCESS_CODE, SELF_PROCESS_CODE):
        frappe.db.set_value("EC Approval Process", code, "status", "Active")
    frappe.db.set_value("EC Approval Type", TYPE, "route", ROUTE)
    report["result"] = "ENABLED"
    return report
