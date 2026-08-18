"""Stable compatibility API for Payment Request."""
import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind

globals().update(bind("PAYMENT_REQUEST"))


@frappe.whitelist()
def list_approved_purchase_requests():
    """Return the requester's approved Purchase Requests for the Link picker."""
    output = []
    for row in frappe.get_all(
            "EC Purchase Request", filters={"requested_by": frappe.session.user},
            fields=["name", "request_title", "approval_request"],
            order_by="modified desc", limit_page_length=200):
        status = row.approval_request and frappe.db.get_value(
            "EC Approval Request", row.approval_request, "approval_status")
        if status == "Approved":
            output.append({"value": row.name, "label": row.request_title or row.name})
    return {"rows": output}
