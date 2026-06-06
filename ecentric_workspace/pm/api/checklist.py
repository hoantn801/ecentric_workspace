"""PM v2 - Batch G1: checklist READ services (foundation only).

Read-only template listing for the UI/admin. Service-layer permission
(require_pm_access). NO writes here: template CRUD + per-task checklist tick/
complete arrive in later phases (G2+). Manage templates in Desk for now.

Module path: ecentric_workspace.pm.api.checklist
"""

import frappe

from ecentric_workspace.pm import permissions as pmperm

DT = "PM Checklist Template"


@frappe.whitelist()
def list_templates(active_only=1):
    """Permission-scoped list of checklist templates (read-only)."""
    pmperm.require_pm_access()
    filters = {}
    if active_only in (1, "1", True, "true", "True"):
        filters["is_active"] = 1
    rows = frappe.get_all(
        DT, filters=filters or None,
        fields=["name", "template_name", "department", "is_active"],
        order_by="template_name asc", limit_page_length=200,
    )
    return {"rows": rows}


@frappe.whitelist()
def get_template(name):
    """One template + its items (read-only)."""
    pmperm.require_pm_access()
    doc = frappe.get_doc(DT, name)
    items = [
        {"idx": i.idx, "item_label": i.item_label,
         "is_required": i.is_required, "item_description": i.get("item_description")}
        for i in (doc.get("items") or [])
    ]
    return {
        "name": doc.name, "template_name": doc.template_name,
        "department": doc.get("department"), "is_active": doc.is_active,
        "description": doc.get("description"), "items": items,
    }
