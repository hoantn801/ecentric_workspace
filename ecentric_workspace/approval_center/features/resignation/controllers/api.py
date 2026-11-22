"""Stable compatibility API for Resignation Request."""
from ecentric_workspace.approval_center.shared.fulfillment_api_adapter import bind_fulfillment

globals().update(bind_fulfillment("RESIGNATION",
    ("name", "request_title", "requested_by", "resignation_for", "resignation_reason",
     "last_working_day", "fulfillment_status", "fulfillment_owner", "fulfillment_due_at"),
    "last_working_day asc"))

import frappe  # noqa: E402

from ecentric_workspace.approval_center.features.resignation.application import service as _svc  # noqa: E402


@frappe.whitelist()
def get_notice_info(employee_email=None):
    """Ngay lam viec cuoi som nhat hop le (Dieu 35) cho form. Chi tra chi tiet cho chinh NV,
    quan ly truc tiep, nhom HR - nguoi khac nhan {"known": False}."""
    return _svc.notice_info(employee_email)


@frappe.whitelist(methods=["POST"])
def withdraw(name, reason=None):
    """NV "Rut don" truoc ngay lam viec cuoi (23/11/2026). Luat o service.withdraw_state."""
    out = _svc.withdraw(name, reason=reason, actor=frappe.session.user)
    out["detail"] = globals()["get_detail"](name)
    return out
