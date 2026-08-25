# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub: popup mở thẳng nội dung thật; Brand (trường Data) hiện kèm tên."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p084 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p084 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p084 resync failed")
