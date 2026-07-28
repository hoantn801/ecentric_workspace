# Copyright (c) 2026, eCentric and contributors
"""Approval Engine -- canonical visibility / actionability service.

ONE definition of "who may view a governed request", shared by every consumer
so the permission rule is never duplicated:
  - the approval-center form APIs (``api/*.py`` ``_can_view``);
  - the Action Center feed (``action_center.feed._engine_link_state``), which
    normalizes engine-linked business documents and must gate the canonical
    Approval Center URL on the SAME rule (never a second, divergent definition).

The rule is the union previously encoded inline in the per-form ``_can_view`` /
``_is_fulfiller`` helpers: System Manager, the requester, any approver on the
request, the fulfillment owner, or an eligible fulfiller (a configured Fulfiller
on an Active process of the request's approval type, or a user holding an Open
ToDo on the business DocType).
"""
import frappe

#: request statuses that are still open/actionable (mirrors service.OPEN_STATUSES).
OPEN_STATUSES = ("Pending", "Information Required")


def is_system_manager(user=None):
    return "System Manager" in frappe.get_roles(user or frappe.session.user)


def is_eligible_fulfiller(user, approval_type=None, business_doctype=None):
    """Matches the approval APIs' ``_is_fulfiller``: a System Manager, a
    configured Fulfiller participant on an Active process of ``approval_type``,
    or a user holding an Open ToDo on ``business_doctype``."""
    if is_system_manager(user):
        return True
    if approval_type:
        procs = frappe.get_all(
            "EC Approval Process",
            filters={"approval_type": approval_type, "status": "Active"},
            pluck="name") or []
        for p in procs:
            if frappe.db.exists("EC Approval Participant",
                                {"parent": p, "parenttype": "EC Approval Process",
                                 "participant_purpose": "Fulfiller", "user": user}):
                return True
    if business_doctype and frappe.db.exists(
            "ToDo", {"reference_type": business_doctype,
                     "allocated_to": user, "status": "Open"}):
        return True
    return False


def can_view_request(request_name, user=None, business_doctype=None,
                     requested_by=None, fulfillment_owner=None, approval_type=None):
    """THE canonical Approval Engine visibility check.

    A user may view a governed request if they are a System Manager, the
    requester, any approver on the request, the fulfillment owner, or an
    eligible fulfiller. Inputs are primitives (already-loaded business fields +
    the linked request name) so BOTH the form APIs and the Action Center feed
    can call it without re-deriving anything.
    """
    user = user or frappe.session.user
    if is_system_manager(user):
        return True
    if requested_by and requested_by == user:
        return True
    if request_name and frappe.db.exists(
            "EC Approval Request Approver",
            {"approval_request": request_name, "approver": user}):
        return True
    if fulfillment_owner and fulfillment_owner == user:
        return True
    return is_eligible_fulfiller(user, approval_type, business_doctype)


def is_actionable(request_name, current_level, user=None, approval_status=None):
    """Canonical actionability check: the user is a Pending approver on the
    request's CURRENT level and the request is still open. Mirrors the approval
    APIs' ``_pending_row``."""
    if approval_status is not None and approval_status not in OPEN_STATUSES:
        return False
    if not request_name or not current_level:
        return False
    return bool(frappe.db.exists(
        "EC Approval Request Approver",
        {"approval_request": request_name, "level_no": current_level,
         "approver": user or frappe.session.user, "status": "Pending"}))
