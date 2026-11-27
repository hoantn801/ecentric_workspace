# Copyright (c) 2026, eCentric and contributors
"""p579_tai_san_danh_muc: dong bo lai 7 trang tai san 27/11/2026 - danh muc phan mem + mau thiet bi (chon
dropdown + them moi, gop theo phan mem), form nam tren thanh tren cung, menu khong nhay.
Nguon tai_san/pages/*, cach ghi xem tai_san/pages/sync.py."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.tai_san.pages import sync
        frappe.logger("approval_center").info("p579 tai_san: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p579_tai_san_danh_muc")
