# Copyright (c) 2026, eCentric and contributors
"""Resync trang hub sau khi tab 'Chá» tÃ´i xá»­ lÃ½' gá»™p thÃªm há»“ sÆ¡ chá» tÃ´i duyá»‡t."""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync


def execute():
    try:
        frappe.log_error("p092 hub sync=%s" % (page_sync.sync() or {}).get("action"), "p092 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p092 resync failed")
