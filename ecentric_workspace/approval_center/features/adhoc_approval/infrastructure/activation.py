# Copyright (c) 2026, eCentric and contributors
"""Kich hoat Phe duyet dot xuat: process Active + the Active (route). System-Manager only,
dry-run mac dinh. Goi tu patch p430 (mot lan) hoac tay."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.activation_flags import is_dry_run
from ecentric_workspace.approval_center.features.adhoc_approval.infrastructure.setup import (
    validate_adhoc_approval_v1, PROCESS_CODE)

TYPE = "ADHOC_APPROVAL"
ROUTE = "approvals/adhoc-approval"


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Adhoc Approval activation."),
                     frappe.PermissionError)


@frappe.whitelist()
def activate_adhoc_approval(dry_run=1, apply=0, commit=0):
    """Process V1 Active + the Active (Hoan chot 23/11: mo cho moi nguoi ngay khi deploy)."""
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    v = validate_adhoc_approval_v1()
    # role_has_members la CANH BAO (chua ai giu role CEO thi gui se bi chan voi cau ro rang).
    blockers = [c["check"] for c in v.get("checks", []) if not c.get("ok")
                and c["check"] != "role_has_members"]
    report = {"operation": "activate", "mode": "dry_run" if dry else "commit",
              "validation": v, "blockers": blockers}
    if dry or blockers:
        return report
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE)
    if proc.status != "Active":
        proc.status = "Active"                  # validate() dat active_process_key (khoa duy nhat)
        proc.save(ignore_permissions=True)
    frappe.db.set_value("EC Approval Type", TYPE,
                        {"card_status": "Active", "process_status": "Live",
                         "route": "/" + ROUTE, "private": 1})
    frappe.db.commit()
    report["result"] = "%s Active, the Active, route /%s" % (PROCESS_CODE, ROUTE)
    return report
