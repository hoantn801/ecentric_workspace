"""PM v2 - Project read services.

Real logic lands in PM1-T05 (list) and PM1-T06 (get). These are scaffold stubs:
they take the planned signatures, perform NO data access, and return a marker so
the wiring can be smoke-tested without exposing any data.

Module path: ecentric_workspace.pm.api.projects
Status: PM1-T00 scaffold. NOT wired into hooks.py. NOT deployed.
"""

import frappe


@frappe.whitelist()
def list(filters=None, start=0, page_length=20):
    """Stub for PM1-T05 (paginated, permission-scoped project list).

    Will use frappe.get_list("Project", ...) so permission query conditions
    (PM1-T03) apply automatically. No data access yet.
    """
    return {"ok": True, "service": "projects.list", "implemented": False}


@frappe.whitelist()
def get(name=None):
    """Stub for PM1-T06 (project detail + task status breakdown).

    Will re-check permission on the record before returning. No data access yet.
    """
    return {"ok": True, "service": "projects.get", "implemented": False}
