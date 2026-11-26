# Copyright (c) 2026, eCentric and contributors
"""p575_tai_san_ban_quyen: dua trang /tai-san/ban-quyen (dot 4) len site va dong bo lai 6 trang tai
san (asset doi ?v=: Tong quan / Cua toi / Luan chuyen co khoi ban quyen). Hoan 26/11/2026.
Nguon tai_san/pages/*, cach ghi xem tai_san/pages/sync.py."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.tai_san.pages import sync
        frappe.logger("approval_center").info("p575 tai_san: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p575_tai_san_ban_quyen")
