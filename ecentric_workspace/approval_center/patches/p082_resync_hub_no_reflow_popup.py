# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub: popup hết nháy (giữ nguyên phần tử thẻ, chỉ đổ nội dung)."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p082 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p082 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p082 resync failed")
