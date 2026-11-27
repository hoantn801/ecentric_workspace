# Copyright (c) 2026, eCentric and contributors
"""p583_tai_san_ngoai_te: dong bo lai 7 trang tai san 27/11/2026 - chi phi ban quyen nhieu tien te (USD
song song VND, ty gia go tay co goi y), nguoi quan ly tai san sua chi phi co nhat ky.
Nguon tai_san/pages/*, cach ghi xem tai_san/pages/sync.py."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.tai_san.pages import sync
        frappe.logger("approval_center").info("p583 tai_san: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p583_tai_san_ngoai_te")
