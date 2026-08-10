"""PM UI meta helpers — field hints synced from DocType `EC Field Description`.

Read-only, PM-access gated. Uses `frappe.get_all` (which bypasses per-user DocType
read permissions) so EVERY PM user sees the ⓘ hints without needing a direct read
DocPerm on `EC Field Description`. Content is edited at Desk; no code change needed.

Module path: ecentric_workspace.pm.api.meta
"""

import frappe

from ecentric_workspace.pm import permissions as pmperm


@frappe.whitelist()
def field_hints(ref_doctype):
    """Active field-hint descriptions for a ref_doctype. Returns {rows:[{fieldname, description}]}."""
    pmperm.require_pm_access()
    rows = frappe.get_all(
        "EC Field Description",
        filters={"ref_doctype": ref_doctype, "is_active": 1},
        fields=["fieldname", "description"],
        limit_page_length=0,
    )
    return {"rows": rows}
