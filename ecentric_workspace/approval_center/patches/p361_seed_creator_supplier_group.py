# Copyright (c) 2026, eCentric and contributors
"""Tao Supplier Group "KOL/KOC Creator" cho creator master (11/11/2026).

Creator KOL/KOC la Supplier cua ERPNext trong nhom nay (plan "Hop dong KOL/KOC len ERP",
giai doan 1). Moi truy van cua `shared.creators` loc theo nhom -> thieu nhom thi khong tao duoc
creator nao. Idempotent: co roi thi bo qua, khong sua gi nhom da co.
"""
import frappe

from ecentric_workspace.approval_center.shared.creators.domain import CREATOR_GROUP


def execute():
    if frappe.db.exists("Supplier Group", CREATOR_GROUP):
        return
    parent = "All Supplier Groups"
    if not frappe.db.exists("Supplier Group", parent):
        parent = frappe.db.get_value("Supplier Group", {"is_group": 1}, "name")
    frappe.get_doc({"doctype": "Supplier Group", "supplier_group_name": CREATOR_GROUP,
                    "parent_supplier_group": parent, "is_group": 0}).insert(ignore_permissions=True)
