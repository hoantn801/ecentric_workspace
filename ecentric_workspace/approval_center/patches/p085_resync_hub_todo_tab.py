# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub sau khi tab 'Chờ tôi xử lý' gộp thêm hồ sơ chờ tôi duyệt."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p085 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p085 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p085 resync failed")
