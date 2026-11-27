# Copyright (c) 2026, eCentric and contributors
"""p005: dong bo lai trang /kalodata (asset ?v= doi: tai gop Excel cac phan + khoi Thong ke cho quan ly (ec_st_stats.js)
. Idempotent, loi -> Error Log, khong chan migrate."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.shared_tools.pages import sync
        frappe.logger("shared_tools").info("p005 pages: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="shared_tools p005_resync_page")
