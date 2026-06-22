"""PM v2 - Batch G1: checklist READ services (foundation only).

Read-only template listing for the UI/admin. Service-layer permission
(require_pm_access). NO writes here: template CRUD + per-task checklist tick/
complete arrive in later phases (G2+). Manage templates in Desk for now.

Module path: ecentric_workspace.pm.api.checklist
"""

import json

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow

from ecentric_workspace.pm import permissions as pmperm

DT = "PM Checklist Template"


def _is_complete(required_total, required_done, total, done):
    """Required-driven rule: if any required items, all required done; else all items done."""
    if required_total > 0:
        return required_done == required_total
    return total > 0 and done == total


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
    # G4.2/G4.3: terminal tasks have IMMUTABLE checklists (audit-safe). Reopen is the
    # governed path. Uses the shared helper; exact message preserved from G4.2.
    pmperm.assert_task_not_terminal(
        doc, _("Không thể chỉnh checklist sau khi nhiệm vụ đã hoàn thành/huỷ. Vui lòng Reopen trước."))
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


@frappe.whitelist()
def counts(task_names):
    """G4: batch checklist progress for a list of task names (read-only, no N calls).
    Names come from already permission-scoped frontend lists; counts are non-sensitive."""
    pmperm.require_pm_access()
    if isinstance(task_names, str):
        try:
            task_names = json.loads(task_names)
        except Exception:
            task_names = [task_names]
    task_names = [t for t in (task_names or []) if t]
    out = {}
    if not task_names:
        return {"counts": out}
    rows = frappe.get_all(
        "PM Task Checklist Item",
        filters={"parent": ["in", task_names], "parenttype": "Task"},
        fields=["parent", "is_required", "is_done"], limit_page_length=0,
    )
    for r in rows:
        a = out.setdefault(r["parent"], {"total": 0, "done": 0,
                                         "required_total": 0, "required_done": 0})
        a["total"] += 1
        if r["is_required"]:
            a["required_total"] += 1
        if r["is_done"]:
            a["done"] += 1
            if r["is_required"]:
                a["required_done"] += 1
    for a in out.values():
        a["complete"] = _is_complete(a["required_total"], a["required_done"], a["total"], a["done"])
    return {"counts": out}


@frappe.whitelist()
def complete_task(task):
    """G4: mark a checklist task Done via the governed 'Hoàn thành' workflow transition.
    Re-validates checklist completion server-side (defense in depth) -> never trusts the
    client; never sets status directly. Notification = whatever the native Workflow does
    (send_email_alert=0 on PM Task Workflow)."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc("Task", task)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to complete this task."), frappe.PermissionError)
    items = doc.get("pm_checklist") or []
    if not items:
        frappe.throw(_("Nhiệm vụ này không có checklist."))
    required = [d for d in items if d.is_required]
    if required:
        undone = [d for d in required if not d.is_done]
        if undone:
            frappe.throw(_("Còn {0} mục bắt buộc chưa hoàn thành.").format(len(undone)))
    else:
        undone_all = [d for d in items if not d.is_done]
        if undone_all:
            frappe.throw(_("Còn {0} mục chưa hoàn thành.").format(len(undone_all)))
    doc = apply_workflow(doc, "Hoàn thành")  # governed + audited; condition re-checked too
    return {"name": doc.name, "workflow_state": doc.get("workflow_state")}
