# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub: bỏ nút 'Xem thêm', popup hiện đủ trường."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p078 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p078 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p078 resync failed")
