# Copyright (c) 2026, eCentric and contributors
"""p003: cot `ref_doctype` moi cua EC Post Comment (04/10/2026, Bang tin dung chung bang binh luan).

Moi dong cu la binh luan bai Tin noi bo -> ref_doctype = 'EC Internal Post'. MariaDB thuong da
dien gia tri mac dinh luc them cot, patch nay chi chac chan. Chay lai bao nhieu lan cung duoc.
"""
import frappe


def execute():
    if not frappe.db.has_column("EC Post Comment", "ref_doctype"):
        return
    frappe.db.sql("update `tabEC Post Comment` set ref_doctype='EC Internal Post' where ifnull(ref_doctype, '') = ''")
