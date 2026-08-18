"""Stable compatibility API for Outside Work requests."""
import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind

globals().update(bind("OUTSIDE_WORK"))


@frappe.whitelist()
def check_overlap(start_date=None, end_date=None, exclude=None):
    """Return a non-blocking overlap warning count for the requester."""
    from ecentric_workspace.approval_center.outside_work import service
    return {"count": service.overlap_count(
        frappe.session.user, start_date, end_date, exclude=exclude)}
