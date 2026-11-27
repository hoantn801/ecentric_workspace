# Copyright (c) 2026, eCentric and contributors
"""p007: dong bo lai trang /kalodata (asset ?v= doi: bo cuc A theo Approval Center - bang trang thai, danh sach file loc + nhom ngay
. Idempotent, loi -> Error Log, khong chan migrate."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.shared_tools.pages import sync
        frappe.logger("shared_tools").info("p007 pages: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="shared_tools p007_resync_page")
