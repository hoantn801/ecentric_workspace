# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub: popup hiện dứt khoát, không mờ dần và không đổi kích thước giữa chừng."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p083 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p083 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p083 resync failed")
