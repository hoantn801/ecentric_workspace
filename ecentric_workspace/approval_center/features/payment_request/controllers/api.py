"""Stable compatibility API for Payment Request."""
import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.features.payment_request.application import funding

globals().update(bind("PAYMENT_REQUEST"))


@frappe.whitelist()
def list_approved_purchase_requests():
    """Legacy shape kept for older clients: approved ĐNMH as {value,label} only.

    New clients call `list_funding_sources`, which also returns the amounts needed to
    autofill and to show the remaining balance. Delegates so both paths share one filter.
    """
    rows = funding.list_sources("EC Purchase Request")
    return {"rows": [{"value": r["value"], "label": r["label"]} for r in rows]}


@frappe.whitelist()
def list_funding_sources(source_doctype=None):
    """Approved commitments of the caller, each with total / paid / remaining.

    Read-only and permission-aware (see funding.list_sources). Returns the source-type
    catalog too, so the form does not hardcode the list of supported types.
    """
    if not source_doctype:
        return {"types": funding.supported_sources(), "rows": []}
    return {"types": funding.supported_sources(),
            "rows": funding.list_sources(source_doctype)}


@frappe.whitelist()
def funding_source_summary(source_doctype, source_name, exclude_request=None):
    """Fresh total/paid/remaining for one commitment.

    The form calls this when a source is picked, so the number shown is current even if
    somebody else charged the same commitment while this form was open.
    """
    if not frappe.has_permission(source_doctype, "read", doc=source_name):
        frappe.throw(frappe._("Bạn không có quyền xem chứng từ nguồn này."))
    return funding.describe_source(source_doctype, source_name, exclude_request or None)
