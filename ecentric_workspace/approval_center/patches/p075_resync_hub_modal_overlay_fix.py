# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub: sửa lệch id lớp phủ popup (#ec-apl-ov) khiến popup không hiện."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p075 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p075 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p075 resync failed")
