# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub sau khi thêm popup chi tiết (bỏ cột Thao tác ngoài danh sách).
Chỉ trang all-requests đổi; các form không đụng."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p074 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p074 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p074 resync failed")
