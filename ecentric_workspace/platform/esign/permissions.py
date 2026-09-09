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


def can_setup_package(business_doctype, business_name, user=None):
    """Ai duoc DUNG/SUA goi tai lieu ky so: nguoi tao yeu cau, SM, hoac nguoi duyet trong luong.

    Day la luat CU cua `can_view_business`, giu nguyen KHONG DOI. No o lai vi
    `api.upload_package_file` (POST, ghi that) chi gac bang dung mot cau nay - neu de no
    dung chung voi luat XEM da noi rong o duoi thi ban va quyen-xem se lang le bien thanh
    cap quyen-GHI cho moi nguoi xu ly. Tach ra de khong ai duoc them, khong ai mat di.
    """
    user = user or frappe.session.user
    requested_by = business_requested_by(business_doctype, business_name)
    if requested_by == user or is_system_manager(user):
        return True
    ar = business_approval_request(business_doctype, business_name)
    return bool(ar and frappe.db.exists("EC Approval Request Approver",
                                        {"approval_request": ar, "approver": user}))


def can_view_business(business_doctype, business_name, user=None):
    """AI DUOC XEM - uy quyen cho luat chinh thuc cua Approval Center, khong tu che ban sao.

    Vi sao doi (09/09, chi Dan bao loi). Ham nay tung ghi "Mirrors the per-form _can_view
    convention" va chep lai ba chan: nguoi tao / SM / nguoi duyet. Quy uoc do DA DOI tu lau:
    `shared.workflow.permissions.can_view_request` con cho fulfillment_owner va Fulfiller
    duoc CAU HINH xem. Ban chep o day bi bo lai phia sau, va khong ai biet cho toi khi no
    lam hong mot man hinh that.

    Trieu chung: chi Dan (Ke toan, Fulfiller cua PAYMENT_REQUEST) mo EC-PAYR-2026-00073 -
    than phieu ve binh thuong (`query_service.detail` da cho qua) nhung MOI endpoint ky so
    deu nem "Ban khong co quyen xem yeu cau nay", bung ra bon cap thong bao loi chong len
    trang. Day la lan THU BA trong mot ngay cung mot lop loi: mot he thong con giu ban sao
    rieng cua luat quyen xem roi lech khoi ban goc (truoc do: trang /all-requests, roi cong
    tep dinh kem).

    Nen tu nay hoi THANG ban goc. Fail-closed: nhap module khong duoc thi lui ve dung luat
    cu (`can_setup_package`) - hep hon, khong bao gio rong hon.
    """
    user = user or frappe.session.user
    if can_setup_package(business_doctype, business_name, user):
        return True
    try:
        from ecentric_workspace.approval_center.shared.workflow.permissions import (
            can_view_request)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign can_view_business: khong nap duoc luat goc")
        return False
    ar = business_approval_request(business_doctype, business_name)
    row = frappe.db.get_value(business_doctype, business_name,
                              ["requested_by", "fulfillment_owner", "approval_type"],
                              as_dict=True) or {}
    return bool(can_view_request(
        ar, user,
        business_doctype=business_doctype,
        requested_by=row.get("requested_by"),
        fulfillment_owner=row.get("fulfillment_owner"),
        approval_type=row.get("approval_type"),
        business_name=business_name))


def assert_can_setup_package(business_doctype, business_name, user=None):
    if not can_setup_package(business_doctype, business_name, user):
        frappe.throw(_("Chỉ người tạo yêu cầu hoặc người duyệt mới được sửa gói tài liệu."),
                     frappe.PermissionError)


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
