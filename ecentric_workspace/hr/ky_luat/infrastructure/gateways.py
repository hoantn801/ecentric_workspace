# Copyright (c) 2026, eCentric and contributors
"""Cong sang module khac - goi qua duong dan khai bao (frappe.get_attr), khong import thang.

  * Phieu CEO ky quyet dinh: approval_center/features/discipline_decision (cung nhanh nay).
  * Clearance khi sa thai: ham Clearance V2 cua Agent C
    `approval_center.features.clearance_request.application.service.tao_clearance(employee,
    ly_do, ngay_cuoi)`. Chua co (nhanh C chua gop) -> KHONG tu tao Clearance bang duong cu (duong
    cu bat buoc mot Don nghi viec da duyet) -> tra None + Error Log + bao HR tao tay.
"""
import frappe

DECISION_SERVICE = "ecentric_workspace.approval_center.features.discipline_decision.application.service"
CLEARANCE_FN = "ecentric_workspace.approval_center.features.clearance_request.application.service.tao_clearance"


def create_decision(case, actor):
    return frappe.get_attr(DECISION_SERVICE + ".tao_tu_ho_so")(case, actor)


def resubmit_decision(case, actor):
    return frappe.get_attr(DECISION_SERVICE + ".gui_lai_tu_ho_so")(case, actor)


def retitle_decision(case):
    """HR sua tieu de ho so dang trinh CEO -> doi tieu de phieu quyet dinh (ban chup)."""
    return frappe.get_attr(DECISION_SERVICE + ".doi_tieu_de_tu_ho_so")(case)


def create_clearance(employee, reason, last_day):
    """-> ten Clearance hoac None (chua co ham / loi) - khong bao gio nem loi."""
    try:
        fn = frappe.get_attr(CLEARANCE_FN)
    except Exception:
        frappe.log_error(title="ky_luat: chua co tao_clearance (Clearance V2)",
                         message="Sa thai %s ngay %s - HR tao Clearance tay." % (employee, last_day))
        return None
    try:
        return fn(employee, reason, last_day)
    except Exception:
        frappe.log_error(title="ky_luat: tao_clearance loi %s" % employee, message=frappe.get_traceback())
        return None
