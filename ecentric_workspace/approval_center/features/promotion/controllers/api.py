"""Stable compatibility API backed by the shared request application layer."""
import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.features.promotion.application import employee_snapshot as snap

globals().update(bind("PROMOTION_REQUEST"))


@frappe.whitelist()
def promotion_candidates():
    """29/09/2026: nhan su nguoi dang nhap duoc de xuat = nguoi ho XEM DUOC LUONG (quyen SSA)."""
    return {"rows": snap.candidates()}


@frappe.whitelist()
def promotion_employee(employee):
    """Thong tin hien tai (vi tri, luong...) cua mot nhan su - kiem quyen xem luong truoc."""
    return snap.snapshot(employee)
