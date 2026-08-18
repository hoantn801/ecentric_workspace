"""Stable compatibility API for Document Request."""
import frappe

from ecentric_workspace.approval_center.shared.fulfillment_api_adapter import bind_fulfillment

globals().update(bind_fulfillment("DOCUMENT_REQUEST",
    ("name", "request_title", "requested_by", "request_type", "document_name",
     "owner_department", "expected_response_date", "fulfillment_status",
     "fulfillment_owner", "fulfillment_due_at"), "modified asc"))


@frappe.whitelist()
def search_departments(query=None):
    filters = {"disabled": 0}
    if query:
        filters["department_name"] = ["like", "%%%s%%" % query]
    departments = frappe.get_all(
        "Department", filters=filters, fields=["name", "department_name"],
        order_by="department_name asc", limit_page_length=20)
    return {"rows": [{"value": row.name, "label": row.department_name or row.name}
                     for row in departments]}
