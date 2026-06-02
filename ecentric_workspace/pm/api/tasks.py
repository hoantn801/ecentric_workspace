"""PM v2 - Task services (read + write).

Real logic lands in:
  PM1-T07 list        - tasks for a project (kanban|list), permission-scoped
  PM1-T08 get         - task detail incl. sub-tasks, _assign, Comment, File
  PM1-T15 create      - create Task / sub-task (parent_task) within permission
  PM1-T16 set_status  - status change via Workflow apply_workflow (PM1-T04)
  PM1-T17 assign      - native assignment (ToDo / _assign)

Hierarchy (Phase 1): Project -> Task -> Sub-task (via native parent_task).
Module path: ecentric_workspace.pm.api.tasks
Status: PM1-T00 scaffold. NOT wired into hooks.py. NOT deployed.
"""

import frappe


@frappe.whitelist()
def list(project=None, view="list", start=0, page_length=20):
    """Stub for PM1-T07. No data access yet."""
    return {"ok": True, "service": "tasks.list", "implemented": False}


@frappe.whitelist()
def get(name=None):
    """Stub for PM1-T08. No data access yet."""
    return {"ok": True, "service": "tasks.get", "implemented": False}


@frappe.whitelist()
def create(project=None, subject=None, parent_task=None):
    """Stub for PM1-T15. No write yet."""
    return {"ok": True, "service": "tasks.create", "implemented": False}


@frappe.whitelist()
def set_status(name=None, action=None):
    """Stub for PM1-T16. Will use apply_workflow (no raw status write). No write yet."""
    return {"ok": True, "service": "tasks.set_status", "implemented": False}


@frappe.whitelist()
def assign(name=None, users=None):
    """Stub for PM1-T17. Will use native assign_to (ToDo / _assign). No write yet."""
    return {"ok": True, "service": "tasks.assign", "implemented": False}
