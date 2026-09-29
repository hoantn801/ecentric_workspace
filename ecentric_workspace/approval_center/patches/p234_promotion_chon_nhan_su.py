# Copyright (c) 2026, eCentric and contributors
"""Resync trang /approvals/promotion (29/09/2026): chon nhan su tu danh sach (chi nguoi minh
xem duoc luong), vi tri / luong hien tai do server dien, bang ket qua cap nhat ho so sau duyet.
Schema (promoted_employee, applied_at, apply_result) do bench migrate tu lam. Khong nem loi."""
import frappe

PAGE = "ecentric_workspace.approval_center.features.promotion.infrastructure.page_sync"


def execute():
    try:
        res = frappe.get_module(PAGE).sync() or {}
        msg = "promotion: %s" % res.get("action")
    except Exception:
        msg = "promotion: LOI\n" + frappe.get_traceback()
    frappe.log_error(title="p234 promotion chon nhan su", message=msg)
