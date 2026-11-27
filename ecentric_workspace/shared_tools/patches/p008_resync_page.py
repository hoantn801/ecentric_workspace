# Copyright (c) 2026, eCentric and contributors
"""p008: dong bo lai trang /kalodata (asset ?v= doi: menu doi ten "Kalodata", an file chan doan, tieu de bang thong ke
. Idempotent, loi -> Error Log, khong chan migrate."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.shared_tools.pages import sync
        frappe.logger("shared_tools").info("p008 pages: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="shared_tools p008_resync_page")
