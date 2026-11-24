# Copyright (c) 2026, eCentric and contributors
"""Kich hoat BBNT tung dot (KOL_ACCEPTANCE): process V1 Active + loai phieu Live, route ve trang Hop
dong. System-Manager only, dry-run mac dinh. Goi tu patch p520 (mot lan) hoac tay.

The tren danh muc = "Disabled": dot nghiem thu KHONG tao tu danh muc (chi tu the KOL cua hop dong);
route van dung cho link "mo trang day du" / nhac viec (khong doc card_status) - trang Hop dong nhan
?id=EC-BBNT-... va mo dung hop dong (kol_round_contract)."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import process_seed as ps
from ecentric_workspace.approval_center.features.kol_acceptance.infrastructure.setup import (
    APPROVAL_TYPE, LEVELS, PROCESS_CODE)

ROUTE = "/approvals/contract-review"


@frappe.whitelist()
def activate_kol_acceptance(dry_run=1, apply=0):
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ System Manager được bật quy trình BBNT."), frappe.PermissionError)
    rep = ps.run_swap(APPROVAL_TYPE, PROCESS_CODE, dry_run=dry_run, apply=apply, expect_levels=LEVELS)
    if int(apply or 0) == 1 and rep.get("result") in ("SWAPPED", "ALREADY_ACTIVE"):
        frappe.db.set_value("EC Approval Type", APPROVAL_TYPE,
                            {"card_status": "Disabled", "process_status": "Live", "route": ROUTE})
        frappe.db.commit()
        rep["type"] = "card Disabled, process Live, route %s" % ROUTE
    return rep
