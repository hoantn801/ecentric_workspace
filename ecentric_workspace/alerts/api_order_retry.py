# Copyright (c) 2026, eCentric
"""Manual EC Order Retry service boundary (Hotfix B, 2026-06-13).

Thin whitelisted layer over services.order_retry for ops escalation. NO UI in
this phase. The DocType ships System-Manager-only DocPerm, so all non-SM access
flows through here. Each mutating endpoint: (1) permission-checks via
alerts.permissions, (2) drives a SANCTIONED service transition (the controller
state-machine guard rejects the same status edit from a raw Desk/API call),
(3) leaves a track_changes Version trail (trigger_source="Manual").

Boundary kept deliberately small (binding 2026-06-13):
  get_retry  - read one item (+ resolved owner)               : manage perm
  retry_now  - Pending -> attempt now (no bump)                : manage perm
  requeue    - Completed/Dead -> Pending (fresh cycle)         : manage perm
  mark_dead  - Pending/Processing -> Dead (stop retrying)      : SM/Admin only
"""
import frappe
from frappe import _

from ecentric_workspace.alerts import permissions
from ecentric_workspace.alerts.services import order_retry


def _load(name):
    if not name:
        frappe.throw(_("name is required."))
    if not frappe.db.exists("EC Order Retry", name):
        frappe.throw(_("EC Order Retry {0} not found.").format(name), frappe.DoesNotExistError)
    return frappe.get_doc("EC Order Retry", name)


def _require_manage(doc):
    if not permissions.can_manage_order_retry(frappe.session.user, doc.brand):
        frappe.throw(_("You do not have permission to manage this order retry."),
                     frappe.PermissionError)


@frappe.whitelist()
def get_retry(name):
    """Read one retry item. Manage permission (brand-scoped). Returns a
    safe projection - last_error is already sanitized at write time."""
    doc = _load(name)
    _require_manage(doc)
    return {
        "name": doc.name, "retry_key": doc.retry_key, "brand": doc.brand,
        "source": doc.source, "order_number": doc.order_number,
        "status": doc.status, "attempt_count": doc.attempt_count,
        "max_attempts": doc.max_attempts, "trigger_source": doc.trigger_source,
        "error_type": doc.error_type, "error_code": doc.error_code,
        "last_error": doc.last_error, "next_retry_at": doc.next_retry_at,
        "first_failed_at": doc.first_failed_at, "last_attempt_at": doc.last_attempt_at,
        "completed_at": doc.completed_at,
    }


@frappe.whitelist()
def retry_now(name):
    """Pending item: bring next attempt forward to now. Manage permission."""
    doc = _load(name)
    _require_manage(doc)
    new_at = order_retry.manual_retry_now(name)
    return {"name": name, "status": "Pending", "next_retry_at": new_at}


@frappe.whitelist()
def requeue(name):
    """Completed/Dead item -> Pending, fresh cycle. The only sanctioned exit
    from a terminal state. Manage permission."""
    doc = _load(name)
    _require_manage(doc)
    status = order_retry.manual_requeue(name)
    return {"name": name, "status": status}


@frappe.whitelist()
def mark_dead(name, reason=None):
    """Force an active item to Dead (stop retrying). System Manager / Admin
    only - it suppresses automated recovery."""
    doc = _load(name)
    if not permissions.can_mark_order_retry_dead(frappe.session.user):
        frappe.throw(_("Only a System Manager can mark an order retry Dead."),
                     frappe.PermissionError)
    status = order_retry.manual_mark_dead(name, reason)
    return {"name": name, "status": status}
