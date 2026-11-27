# Copyright (c) 2026, eCentric and contributors
"""p006: dong bo lai trang /kalodata (asset ?v= doi: khung Quan ly: doi tai khoan Kalodata, mo / dong cong cu
. Idempotent, loi -> Error Log, khong chan migrate."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.shared_tools.pages import sync
        frappe.logger("shared_tools").info("p006 pages: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="shared_tools p006_resync_page")
