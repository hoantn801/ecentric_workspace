"""PM v2 - Batch G1: checklist READ services (foundation only).

Read-only template listing for the UI/admin. Service-layer permission
(require_pm_access). NO writes here: template CRUD + per-task checklist tick/
complete arrive in later phases (G2+). Manage templates in Desk for now.

Module path: ecentric_workspace.pm.api.checklist
"""

import frappe
from frappe import _

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
        {"name": i.name, "idx": i.idx, "item_label": i.item_label,
         "is_required": i.is_required, "item_description": i.get("item_description")}
        for i in (doc.get("items") or [])
    ]
    return {
        "name": doc.name, "template_name": doc.template_name,
        "department": doc.get("department"), "is_active": doc.is_active,
        "description": doc.get("description"), "items": items,
    }


# --------------------------------------------------------------------------
# G3: per-task checklist instance (read + tick). Service-layer permission via
# can_view_task (same gate as comments/worktime). No workflow/auto-complete here.
# --------------------------------------------------------------------------
def _summary(doc):
    rows, total, done, req_total, req_done = [], 0, 0, 0, 0
    for it in (doc.get("pm_checklist") or []):
        total += 1
        if it.is_required:
            req_total += 1
        if it.is_done:
            done += 1
            if it.is_required:
                req_done += 1
        rows.append({
            "name": it.name, "idx": it.idx, "item_label": it.item_label,
            "is_required": it.is_required, "is_done": it.is_done,
            "completed_by": it.get("completed_by"),
            "completed_at": str(it.completed_at) if it.get("completed_at") else None,
            "source_template_item": it.get("source_template_item"),
        })
    return {"rows": rows, "total": total, "done": done,
            "required_total": req_total, "required_done": req_done}


@frappe.whitelist()
def get_for_task(task):
    """Task's checklist instance rows + progress summary (read-only)."""
    pmperm.require_pm_access()
    doc = frappe.get_doc("Task", task)
    if not pmperm.can_view_task(doc.as_dict(), frappe.session.user):
        frappe.throw(_("Not permitted to view this task."), frappe.PermissionError)
    return _summary(doc)


@frappe.whitelist()
def set_item(task, row_name, is_done):
    """Tick/untick ONE checklist row (identified by child row name, NOT label).
    Sets/clears completed_by + completed_at for audit. No auto-complete (G4)."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", task)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to edit this task's checklist."), frappe.PermissionError)
    done = is_done in (1, "1", True, "true", "True", "yes")
    row = None
    for it in (doc.get("pm_checklist") or []):
        if it.name == row_name:
            row = it
            break
    if not row:
        frappe.throw(_("Checklist item not found."))
    row.is_done = 1 if done else 0
    if done:
        row.completed_by = user
        row.completed_at = frappe.utils.now_datetime()
    else:
        row.completed_by = None
        row.completed_at = None
    doc.save(ignore_permissions=True)  # service-layer gate above is the trust boundary
    return _summary(frappe.get_doc("Task", task))
