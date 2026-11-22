"""Stable compatibility API cho Clearance Request (29/09/2026)."""
from ecentric_workspace.approval_center.shared.api_adapter import bind

globals().update(bind("CLEARANCE_REQUEST"))

import frappe  # noqa: E402
from frappe import _  # noqa: E402


@frappe.whitelist(methods=["POST"])
def tao_bu_clearance(dry_run=1, names=None, include_past=0):
    """Tao bu Clearance cho Don nghi viec da duyet xong ma chua co (23/11/2026). CHI System Manager.
    dry_run=1 (mac dinh): chi chan doan tung don, khong ghi gi. names: JSON list / chuoi phay; trong =
    moi don thieu. include_past=1: tao ca don da qua ngay lam viec cuoi (mac dinh bo qua)."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ System Manager được tạo bù Clearance."), frappe.PermissionError)
    from ecentric_workspace.approval_center.features.clearance_request.application import service
    if isinstance(names, str):
        names = frappe.parse_json(names) if names.strip().startswith("[") else [
            x.strip() for x in names.split(",") if x.strip()]
    return service.tao_bu(dry_run=dry_run, names=names, include_past=include_past)
