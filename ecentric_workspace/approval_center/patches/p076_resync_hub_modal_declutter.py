# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub: popup rút gọn (bỏ trường trùng header, nhãn tiếng Việt, gộp cặp Other)."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p076 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p076 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p076 resync failed")
