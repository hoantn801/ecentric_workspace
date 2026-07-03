# Copyright (c) 2026, eCentric and contributors
"""Shared validation for EC Approval Participant rows (used by EC Approval
Process and EC Approval Level). No hardcoded users/emails."""
import frappe
from frappe import _

_RELEVANT = {"User": "user", "Role": "role", "Department Manager": "department"}
# "Requester Manager" resolves dynamically (Employee.reports_to) -> no static field.


def validate_participants(doc, fieldname):
    seen = set()
    for p in (doc.get(fieldname) or []):
        st = p.source_type
        relevant = _RELEVANT.get(st)  # None for Requester Manager
        if relevant and not p.get(relevant):
            frappe.throw(_("Participant with source_type '{0}' requires '{1}'.").format(st, relevant))
        for f in ("user", "role", "department"):
            if f != relevant and p.get(f):
                frappe.throw(_("Participant source_type '{0}' must not populate '{1}'.").format(st, f))
        key = (p.participant_purpose, st, p.get("user"), p.get("role"), p.get("department"))
        if key in seen:
            frappe.throw(_("Duplicate participant within the same parent and purpose."))
        seen.add(key)
