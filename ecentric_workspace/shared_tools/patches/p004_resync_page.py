# Copyright (c) 2026, eCentric and contributors
"""p004: dong bo lai trang /kalodata (asset ?v= doi: quy dinh xuat bang toi da 2500 trang, chia phan 50
trang). Idempotent, loi -> Error Log, khong chan migrate."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.shared_tools.pages import sync
        frappe.logger("shared_tools").info("p004 pages: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="shared_tools p004_resync_page")
