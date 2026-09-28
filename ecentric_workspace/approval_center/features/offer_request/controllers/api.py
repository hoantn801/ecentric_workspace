"""Stable compatibility API cho Offer Request (28/09/2026)."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.features.offer_request.application import service

globals().update(bind("OFFER_REQUEST"))


@frappe.whitelist()
def hiring_prefill(hiring):
    """Thong tin vi tri de form Offer dien san khi mo tu nut "Tao Offer" tren Hiring.

    CHI tra cho nguoi duoc tao Offer tu Hiring do (cung cong voi luc luu/gui) - khong phai
    cua sau de doc noi dung Hiring. Khong tra muc luong de xuat cua Hiring."""
    service._assert_may_create(hiring)
    snap = service.hiring_snapshot(hiring)
    from ecentric_workspace.approval_center.features.hiring_request.application import (
        service as hiring_service)
    offers = hiring_service.offers_of(hiring)
    return {"hiring_request": snap.name, "hiring_title": snap.request_title,
            "position": snap.position, "employment_type": snap.employment_type,
            "line_manager": snap.line_manager, "department": snap.department,
            "number_of_vacancy": snap.number_of_vacancy,
            "offered": len([o for o in offers
                            if o["approval_status"] in ("Pending", "Information Required", "Approved")])}


@frappe.whitelist(methods=["POST"])
def retry_new_staff_preparation(name):
    """Tao lai New Staff Preparation cho mot Offer DA DUYET ma tao tu dong bi loi (vd role
    Operation chua ai giu luc do). Nguoi gui Offer hoac System Manager; idempotent."""
    doc = frappe.get_doc(service.BUSINESS_DT, name)
    user = frappe.session.user
    if doc.requested_by != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Chỉ người gửi Offer hoặc System Manager mới tạo lại được."), frappe.PermissionError)
    st = doc.approval_request and frappe.db.get_value("EC Approval Request", doc.approval_request,
                                                      "approval_status")
    if st != "Approved":
        frappe.throw(_("Offer chưa được duyệt xong."))
    from ecentric_workspace.approval_center.features.new_staff_preparation.application import (
        service as nsp_service)
    nsp = nsp_service.create_from_offer(name, raise_errors=True)
    return {"new_staff_preparation": nsp}
