# Copyright (c) 2026, eCentric and contributors
"""Permission service for the esign layer. Backend-authoritative, service-layer
enforcement (house convention: DocPerm on esign DocTypes is SM-full-only and end-user
access NEVER goes through DocPerm). Every check fails closed."""
import frappe
from frappe import _


def is_system_manager(user=None):
    return "System Manager" in frappe.get_roles(user or frappe.session.user)


def assert_system_manager():
    if not is_system_manager():
        frappe.throw(_("Chỉ System Manager mới được thực hiện thao tác này."), frappe.PermissionError)


def business_requested_by(business_doctype, business_name):
    if not frappe.db.has_column(business_doctype, "requested_by"):
        return None
    return frappe.db.get_value(business_doctype, business_name, "requested_by")


def business_approval_request(business_doctype, business_name):
    if not frappe.db.has_column(business_doctype, "approval_request"):
        frappe.throw(_("DocType {0} is not an Approval Center form.").format(business_doctype))
    return frappe.db.get_value(business_doctype, business_name, "approval_request")


def can_view_business(business_doctype, business_name, user=None):
    """Mirrors the per-form _can_view convention: requester OR SM OR snapshot approver."""
    user = user or frappe.session.user
    requested_by = business_requested_by(business_doctype, business_name)
    if requested_by == user or is_system_manager(user):
        return True
    ar = business_approval_request(business_doctype, business_name)
    return bool(ar and frappe.db.exists("EC Approval Request Approver",
                                        {"approval_request": ar, "approver": user}))


def assert_can_view_business(business_doctype, business_name, user=None):
    if not can_view_business(business_doctype, business_name, user):
        frappe.throw(_("Bạn không có quyền xem yêu cầu này."), frappe.PermissionError)


def assert_requester_draft_package(pkg, user=None):
    """Package mutations (upload/flags/order/placements/replace/delete) are allowed only
    to the requester (or SM) and only while the package is Draft."""
    user = user or frappe.session.user
    if pkg.status != "Draft":
        frappe.throw(_("Gói tài liệu đã khóa - không thể thay đổi. Cần thay đổi thì tạo phiên bản mới."))
    requested_by = business_requested_by(pkg.business_doctype, pkg.business_name)
    if requested_by != user and not is_system_manager(user):
        frappe.throw(_("Chỉ người tạo yêu cầu được chỉnh gói tài liệu."), frappe.PermissionError)


def pending_approver_row(approval_request, level_no, user):
    return frappe.db.get_value("EC Approval Request Approver",
                               {"approval_request": approval_request, "level_no": level_no,
                                "approver": user, "status": "Pending"}, "name")


def assert_pending_approver(req, user=None):
    """The session user must hold a Pending approver row at the request's current level.
    Same predicate the engine re-runs authoritatively under lock inside approve()."""
    user = user or frappe.session.user
    if req.approval_status != "Pending" or not req.current_level:
        frappe.throw(_("Yêu cầu không ở trạng thái chờ duyệt."))
    row = pending_approver_row(req.name, req.current_level, user)
    if not row:
        frappe.throw(_("Bạn không phải người duyệt của cấp hiện tại."), frappe.PermissionError)
    return row


def assert_allowed_signer(settings, user=None):
    """UAT tester allowlist on the settings row. EMPTY LIST = NOBODY (fail-closed)."""
    user = user or frappe.session.user
    raw = (settings.get("allowed_signing_users") or "").replace(",", "\n")
    allowed = {u.strip().lower() for u in raw.splitlines() if u.strip()}
    if user.lower() not in allowed:
        frappe.throw(_("Bạn chưa được cấp quyền ký số (UAT allowlist)."), frappe.PermissionError)


def verified_mapping(user, environment):
    """Active + Verified mapping row for (user, environment) or None. The ONLY source
    of effective SCTS identity - never the frontend."""
    return frappe.db.get_value("EC SCTS User Mapping",
                               {"frappe_user": user, "environment": environment,
                                "active": 1, "mapping_status": "Verified"},
                               ["name", "scts_user_id", "signature_id", "signature_type",
                                "company_id", "modified"], as_dict=True)
