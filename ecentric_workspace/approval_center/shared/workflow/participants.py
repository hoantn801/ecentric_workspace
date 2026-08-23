# Copyright (c) 2026, eCentric and contributors
"""Shared validation for EC Approval Participant rows (used by EC Approval
Process and EC Approval Level). No hardcoded users/emails."""
import frappe
from frappe import _

_REQUIRED = {"User": "user", "Role": "role"}
# "Requester Manager" resolves dynamically (Employee.reports_to) -> no static field.
# "Department Manager": 'department' is OPTIONAL - empty means "the requester's own
# department", resolved at submit time (transitions.resolve_participants line ~189).
_OPTIONAL = {"Department Manager": "department"}


def validate_participants(doc, fieldname):
    seen = set()
    for p in (doc.get(fieldname) or []):
        st = p.source_type
        required = _REQUIRED.get(st)
        allowed = {required, _OPTIONAL.get(st)} - {None}
        if required and not p.get(required):
            frappe.throw(_("Participant with source_type '{0}' requires '{1}'.").format(st, required))
        for f in ("user", "role", "department"):
            if f not in allowed and p.get(f):
                frappe.throw(_("Participant source_type '{0}' must not populate '{1}'.").format(st, f))
        if st == "Reference Department Head" and not p.get("department_field"):
            frappe.throw(_("Participant source_type 'Reference Department Head' requires 'department_field'."))
        key = (p.participant_purpose, st, p.get("user"), p.get("role"), p.get("department"))
        if key in seen:
            frappe.throw(_("Duplicate participant within the same parent and purpose."))
        seen.add(key)


