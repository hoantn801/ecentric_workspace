# Copyright (c) 2026, eCentric and contributors
"""p002: cot `kind` moi cua EC Read Receipt (03/10/2026, them "Xac nhan da doc").

Dong cu deu la luot XEM -> kind = 'seen'. MariaDB thuong da dien gia tri mac dinh luc them
cot, patch nay chi chac chan (dong NULL / rong). Chay lai bao nhieu lan cung duoc.
"""
import frappe


def execute():
    if not frappe.db.has_column("EC Read Receipt", "kind"):
        return
    frappe.db.sql("update `tabEC Read Receipt` set kind='seen' where ifnull(kind, '') = ''")
