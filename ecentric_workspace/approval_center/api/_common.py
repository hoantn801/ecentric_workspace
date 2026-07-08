# Copyright (c) 2026, eCentric and contributors
"""Shared read-side helpers for Approval Center list APIs (service-layer only; no raw client DB).
Used by every api/<form>.py to render the standard list columns (requested date + requester name)."""
import frappe


def requester_display(user):
    """Human-readable requester for the 'Nguoi request' list column: Employee.employee_name if the
    user is linked to an Employee, else User.full_name, else the user id/email. Never raises."""
    if not user:
        return None
    try:
        nm = frappe.db.get_value("Employee", {"user_id": user}, "employee_name")
        if nm:
            return nm
        return frappe.db.get_value("User", user, "full_name") or user
    except Exception:
        return user
