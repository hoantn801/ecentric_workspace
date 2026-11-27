"""Stable compatibility API backed by the shared request application layer."""
import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.features.promotion.application import employee_snapshot as snap
from ecentric_workspace.approval_center.features.promotion.application import service as promotion_service

globals().update(bind("PROMOTION_REQUEST"))


@frappe.whitelist()
def promotion_candidates():
    """Nhan su nguoi dang nhap duoc de xuat = nguoi ho XEM DUOC LUONG (quyen SSA, 29/09) HOP cap duoi
    truc tiep + gian tiep (27/11). Moi dong co `salary_visible`."""
    return {"rows": snap.candidates()}


@frappe.whitelist()
def promotion_employee(employee):
    """Thong tin hien tai (vi tri, luong tham khao...) cua mot nhan su - kiem pham vi de xuat truoc;
    luong tham khao chi tra cho nguoi xem duoc luong."""
    return snap.snapshot(employee)


@frappe.whitelist(methods=["POST"])
def fill_salary(name, current_salary=None, proposed_salary=None, incentives=None):
    """27/11/2026: nguoi duyet Pending cua cap hien tai + xem duoc luong dien luong cho phieu Lead lap
    (salary_pending). Quyen kiem trong service theo session user."""
    return promotion_service.fill_salary(name, current_salary=current_salary,
                                         proposed_salary=proposed_salary, incentives=incentives)
