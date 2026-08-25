# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub: bảng 1 dòng/ô + kéo giãn cột, thanh lọc tự áp dụng, popup 2 cột."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p079 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p079 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p079 resync failed")
