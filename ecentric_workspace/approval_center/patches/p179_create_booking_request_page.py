# Copyright (c) 2026, eCentric and contributors
"""Tao/lam moi trang /approvals/booking-request tu ma nguon."""
import frappe

from ecentric_workspace.approval_center.features.booking_request.infrastructure import page_sync


def execute():
    try:
        frappe.log_error("p179 booking-request sync=%s" % (page_sync.sync() or {}).get("action"),
                         "p179 create page")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p179 create page failed")
