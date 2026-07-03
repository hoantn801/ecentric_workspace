# Copyright (c) 2026, eCentric and contributors
"""Shared user/email validation helpers (no hardcoded identities)."""
import frappe
from frappe import _


def normalize_email(email):
    return (email or "").strip().lower()


def require_active_system_user(user, field_label="user", allow_admin_for_sysmanager=False):
    """Backend guard: enabled System User, not Guest. Administrator excluded
    unless the acting session user is a System Manager (frontend filter is not a
    security boundary)."""
    if not user:
        frappe.throw(_("{0} is required.").format(field_label))
    if user == "Guest":
        frappe.throw(_("{0} cannot be Guest.").format(field_label))
    if user == "Administrator" and not (
            allow_admin_for_sysmanager and "System Manager" in frappe.get_roles(frappe.session.user)):
        frappe.throw(_("Administrator cannot be selected as {0}.").format(field_label))
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    if not row:
        frappe.throw(_("{0} '{1}' does not exist.").format(field_label, user))
    if not row.enabled:
        frappe.throw(_("{0} '{1}' is disabled.").format(field_label, user))
    if row.user_type != "System User":
        frappe.throw(_("{0} '{1}' must be a System User.").format(field_label, user))
