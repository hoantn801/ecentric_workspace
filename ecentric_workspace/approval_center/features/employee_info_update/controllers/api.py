"""Stable compatibility API backed by the shared request application layer."""
import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.features.employee_info_update.application import service

globals().update(bind("EMPLOYEE_INFO_UPDATE"))


@frappe.whitelist()
def current_value_of(employee_email, field_to_update):
    """Gia tri hien tai tren ho so de dien san "Current value" (29/09/2026). Chi tra cho chinh
    nguoi do hoac C&B / HR Manager / SM; nguoi khac nhan chuoi rong."""
    return service.current_value_of(employee_email, field_to_update)
