# Copyright (c) 2026, eCentric and contributors
"""Noi phieu ty trong brand vao engine duyet chung (submitter/resubmitter cua definition).

VI SAO resubmit LUON restart=False. engine.resubmit(restart=True) luon quay ve cap 1.
Nhung cap 1 co the DA BI BO luc nop (CEO khong co lead, xem routing.py) - khi do cap 1
khong co trong snapshot cua phieu, va phieu nop lai se kich hoat mot cap khong ton tai:
treo, khong ai bam duoc. restart=False quay ve dung cap da tra lai phieu
(information_requested_from_level) - cap do chac chan co trong snapshot. Ve nghiep vu
cung dung hon: truong phong tra lai thi truong phong xem lai, khong bat lead duyet lai."""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine
from ecentric_workspace.approval_center.features.brand_weight.application.routing import (
    ResolveBrandWeightSkipLevelsService, is_self_final,
)
from ecentric_workspace.approval_center.features.brand_weight.infrastructure.setup import (
    PROCESS_CODE, SELF_PROCESS_CODE,
)
from ecentric_workspace.approval_center.features.brand_weight.infrastructure import (
    brand_weight_repository as repo,
)

APPROVAL_TYPE = "BRAND_WEIGHT"
SELF_FINAL_COMMENT = "Tự chốt: thành viên phòng Management, không qua duyệt."
MSG_NO_EMPLOYEE = ("Tài khoản của bạn chưa gắn với hồ sơ nhân viên đang làm việc. "
                   "Nhờ HR kiểm tra trước khi nộp.")


def submit(name):
    doc = repo.get_doc(name)
    if doc.approval_request:
        frappe.throw(_("Phiếu này đã được nộp."))
    user = doc.requested_by or frappe.session.user
    if user != frappe.session.user and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Bạn chỉ nộp được phiếu của chính mình."))
    emp = repo.employee_of(user)
    if not emp:
        frappe.throw(_(MSG_NO_EMPLOYEE))
    doc.requested_by, doc.employee = user, emp.name
    doc.department = doc.department or emp.department
    doc.company = doc.company or emp.company
    doc.direct_manager = repo.user_of_employee(emp.reports_to)
    doc.submitted_at = now_datetime()
    repo.save_doc(doc)
    # LUON truyen process_code: BRAND_WEIGHT co hai process Active (xem setup.py).
    if is_self_final(doc.department):
        req = engine.submit(repo.BUSINESS_DT, doc.name, APPROVAL_TYPE, user,
                            process_code=SELF_PROCESS_CODE)
        repo.link_request(doc.name, req)
        # Cap duy nhat co nguoi duyet = chinh nguoi nop, nen engine cho approve that su,
        # co dong nhat ky rieng. Khong gia chu ky cua ai khac.
        engine.approve(req, actor=user, comment=SELF_FINAL_COMMENT)
        return req
    skip, reason = ResolveBrandWeightSkipLevelsService().execute(emp.name, doc.department, user)
    req = engine.submit(repo.BUSINESS_DT, doc.name, APPROVAL_TYPE, user, process_code=PROCESS_CODE,
                        skip_level_nos=skip or None, skip_reason=reason or None)
    repo.link_request(doc.name, req)
    return req


def resubmit(name, actor=None, payload=None):
    doc = repo.get_doc(name)
    if not doc.approval_request:
        frappe.throw(_("Phiếu chưa được nộp."))
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=False)
    return {"restarted": False}
