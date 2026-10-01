# Copyright (c) 2026, eCentric and contributors
"""Tao Role "EC Survey Creator" - ai giu role nay thi tao duoc khao sat o /khao-sat/quan-ly
(HR Manager va System Manager tao duoc san, khong can role nay).

CHI tao role rong, KHONG tu gan cho ai: ai duoc tao khao sat cho ca cong ty la quyet dinh cua
HR / PO. Idempotent: co roi thi khong dung toi."""
import frappe

from ecentric_workspace.surveys.constants import ROLE_CREATOR


def execute():
    try:
        if frappe.db.exists("Role", ROLE_CREATOR):
            return
        doc = frappe.new_doc("Role")
        doc.role_name = ROLE_CREATOR
        doc.desk_access = 0          # lam viec tren cong /khao-sat, khong vao Desk
        doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "surveys p001 role THAT BAI")
