# Copyright (c) 2026, eCentric and contributors
"""p580_tai_san_giao_dien: dong bo lai 7 trang tai san 27/11/2026 - hoa phong cach Approval Center (the so
lieu co o icon, chip co so dem, o tim co kinh lup, nhan chu thuong; Tong quan khong de khoi trong).
Nguon tai_san/pages/*, cach ghi xem tai_san/pages/sync.py."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.tai_san.pages import sync
        frappe.logger("approval_center").info("p580 tai_san: %s" % sync.sync_all())
    except Exception:
        frappe.log_error(title="p580_tai_san_giao_dien")
