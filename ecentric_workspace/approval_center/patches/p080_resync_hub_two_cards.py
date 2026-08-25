# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub: popup tách thành 2 thẻ rời (nội dung | lịch sử xử lý)."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p080 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p080 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p080 resync failed")
