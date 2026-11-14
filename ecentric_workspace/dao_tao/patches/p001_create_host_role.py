# Copyright (c) 2026, eCentric and contributors
"""Tao Role "EC Training Host" (Ban dao tao) - ai giu role nay thi soan bai, soan quiz, mo phong
quiz. HR Manager / HR User / System Manager lam duoc san, khong can role nay (Hoan 12/11:
"chi ban dao tao, team HR va minh truoc").

CHI tao role rong, KHONG tu gan cho ai. Idempotent."""
import frappe

from ecentric_workspace.dao_tao.constants import ROLE_HOST


def execute():
    try:
        if frappe.db.exists("Role", ROLE_HOST):
            return
        doc = frappe.new_doc("Role")
        doc.role_name = ROLE_HOST
        doc.desk_access = 0          # lam viec tren /dao-tao, /quiz - khong vao Desk
        doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "dao_tao p001 role THAT BAI")
