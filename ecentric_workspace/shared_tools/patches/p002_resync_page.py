# Copyright (c) 2026, eCentric and contributors
"""p002: dong bo lai trang /kalodata (asset ?v= doi: nut nguy hiem giu trang thai "bam lan 2" qua cac lan
tu ve lai, 6 giay). Idempotent, loi -> Error Log, khong chan migrate."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.shared_tools.pages import sync
        frappe.logger("shared_tools").info("p002 pages: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="shared_tools p002_resync_page")
