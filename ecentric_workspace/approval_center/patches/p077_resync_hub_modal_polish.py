# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub: popup mở tức thì, báo kết quả thao tác, gấp bớt trường phụ."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p077 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p077 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p077 resync failed")
