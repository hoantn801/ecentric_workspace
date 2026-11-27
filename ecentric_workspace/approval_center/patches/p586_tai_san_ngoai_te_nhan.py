# Copyright (c) 2026, eCentric and contributors
"""p586_tai_san_ngoai_te_nhan: dong bo lai 7 trang tai san 27/11/2026 - sua nhan o chi phi ngoai te (xuong
dong le "(USD)") va o tien trong hien "0".
Nguon tai_san/pages/*, cach ghi xem tai_san/pages/sync.py."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.tai_san.pages import sync
        frappe.logger("approval_center").info("p586 tai_san: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p586_tai_san_ngoai_te_nhan")
