"""Canonical read-side visibility and capability derivation."""
import frappe

from ecentric_workspace.approval_center.shared.workflow.permissions import can_view_request


OPEN_STATUSES = ("Pending", "Information Required")


def is_system_manager(user=None):
    return "System Manager" in frappe.get_roles(user or frappe.session.user)


def has_any_approver_row(user=None):
    user = user or frappe.session.user
    return bool(frappe.db.exists("EC Approval Request Approver", {"approver": user}))


def approval_request_for(definition, business_name):
    approval_request = frappe.db.get_value(
        definition.business_doctype, business_name, "approval_request")
    if not approval_request:
        return None
    return frappe.db.get_value(
        "EC Approval Request", approval_request,
        ["name", "approval_status", "current_level",
         "information_requested_from_level", "requested_by", "approval_type"], as_dict=True)


def can_view(user, business_doc, approval_request):
    # Single source of truth for "who may view a request" -- delegate to the canonical
    # engine check so form detail agrees with the Action Center feed (both allow the
    # requester, any approver, the fulfillment owner and eligible fulfillers). Forms
    # without a fulfillment_owner field -> getattr None, which can_view_request handles.
    return can_view_request(
        approval_request.name if approval_request else None,
        user,
        business_doctype=business_doc.doctype,
        requested_by=getattr(business_doc, "requested_by", None),
        fulfillment_owner=getattr(business_doc, "fulfillment_owner", None),
        approval_type=(approval_request.get("approval_type") if approval_request else None),
        # Ten phieu: bat buoc de duong "dang giu viec" chi mo dung phieu duoc giao.
        business_name=business_doc.name,
    )


def _pending_row(approval_request, user):
    if (not approval_request or approval_request.approval_status not in OPEN_STATUSES
            or not approval_request.current_level):
        return None
    return frappe.db.exists(
        "EC Approval Request Approver",
        {"approval_request": approval_request.name,
         "level_no": approval_request.current_level,
         "approver": user, "status": "Pending"})


def _has_decision(approval_request):
    if not approval_request:
        return False
    return bool(frappe.db.exists(
        "EC Approval Action",
        {"approval_request": approval_request.name,
         "action": ["in", ["Approved", "Rejected", "Information Requested"]]}))


def _is_fulfiller(user, business_doc, approval_request=None):
    """Canonical engine rule, mirrored from the ai_topup controller."""
    try:
        from ecentric_workspace.approval_center.shared.workflow import permissions as _perm
        atype = getattr(business_doc, "approval_type", None) or (
            approval_request.get("approval_type") if approval_request else None)
        return bool(_perm.is_eligible_fulfiller(user, atype, business_doc.doctype))
    except Exception:
        return False


def _can_claim(user, business_doc, approval_request=None):
    """Claim is offered only while the request is waiting to be picked up."""
    if getattr(business_doc, "fulfillment_status", None) != "Assigned":
        return False
    return _is_fulfiller(user, business_doc, approval_request)


def _can_complete(user, business_doc):
    if getattr(business_doc, "fulfillment_status", None) not in ("Assigned", "In Progress"):
        return False
    return bool(getattr(business_doc, "fulfillment_owner", None) == user or is_system_manager(user))


def _requires_signature(can_act, business_doc, approval_request):
    """Cap hien tai cua nguoi nay co phai KY SO khong (04/09). Hub "Tat ca yeu cau" dung de
    hien "Duyet & Ky" thay vi "Duyet" - bam "Duyet" tren cap ky so thi engine tu choi
    ("Cap duyet nay yeu cau ky so..."), nguoi dung khong biet phai lam gi. Chi hoi khi nguoi
    nay dang duoc duyet; hoi hong thi False, khong bao gio lam vo popup."""
    if not can_act or not approval_request or not approval_request.current_level:
        return False
    try:
        from ecentric_workspace.platform.esign import guard
        return bool(guard.level_requires_signature(
            business_doc.doctype, approval_request.approval_type, approval_request.current_level,
            final_level=guard.request_final_level(approval_request.name)))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "capabilities.requires_signature")
        return False


def derive(user, business_doc, approval_request):
    """Return advisory UI capabilities; write paths still revalidate authority."""
    requester = business_doc.requested_by == user
    open_request = bool(
        approval_request and approval_request.approval_status in OPEN_STATUSES)
    can_act = bool(_pending_row(approval_request, user))
    requester_cancel = requester and (
        approval_request is None
        or (approval_request.approval_status == "Pending" and not _has_decision(approval_request)))
    admin = is_system_manager(user)
    admin_approve = False
    if (admin and approval_request and approval_request.approval_status == "Pending"
            and approval_request.current_level):
        level_status = frappe.db.get_value(
            "EC Approval Request Level",
            {"approval_request": approval_request.name,
             "level_no": approval_request.current_level}, "level_status")
        admin_approve = level_status == "In Progress"
    return {
        "requires_signature": _requires_signature(can_act, business_doc, approval_request),
        "can_edit": requester and (
            approval_request is None
            or approval_request.approval_status == "Information Required"),
        "can_submit": requester and approval_request is None,
        "can_resubmit": requester and bool(approval_request)
        and approval_request.approval_status == "Information Required",
        "can_cancel": bool(requester_cancel or (admin and open_request)),
        "can_approve": can_act,
        "can_reject": can_act,
        "can_request_information": can_act,
        "can_admin_approve_current_level": admin_approve,
        "can_claim": _can_claim(user, business_doc, approval_request),
        "can_complete": _can_complete(user, business_doc),
        "can_view_fulfillment": bool(requester or admin or _is_fulfiller(user, business_doc, approval_request)),
    }


