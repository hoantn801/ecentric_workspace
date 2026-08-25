# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub: popup căn giữa màn hình + trường Link hiện kèm tên."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p081 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p081 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p081 resync failed")
