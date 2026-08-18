# Copyright (c) 2026, eCentric and contributors
"""Read-only drift check: does the live EC Digital Signature Profile for Payment Request
still match what ``flow.payment_request.EXPECTED_PROFILE_POLICY`` assumes?

This makes flow.payment_request a real, checkable claim instead of a comment that can
silently go stale. It never writes anything and is not on any scheduler - call it by
hand (System Manager only) after touching the Profile record, or before relying on the
flow declaration for something new.
"""
import frappe
from frappe import _

from ecentric_workspace.approval_center.esign import guard
from ecentric_workspace.approval_center.esign.flow.payment_request import (
    APPROVAL_TYPE, BUSINESS_DOCTYPE, EXPECTED_PROFILE_POLICY,
)


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run the esign flow drift check."),
                     frappe.PermissionError)


def _normalize(field, value):
    # Check fields round-trip as 0/1/None from the DB; Select fields are plain strings.
    if field in ("requester_signature_required",):
        return int(value or 0)
    return value


@frappe.whitelist()
def check():
    """Compares the live enabled Profile row against EXPECTED_PROFILE_POLICY. Fails
    closed the same way guard.get_enabled_profile does: more than one enabled profile
    for the pair is reported as a mismatch, not silently resolved."""
    _require_sm()
    try:
        profile_name = guard.get_enabled_profile(BUSINESS_DOCTYPE, APPROVAL_TYPE)
    except Exception as e:
        return {"ok": False, "profile": None, "mismatches": [],
                "error": "ambiguous_or_lookup_failed: %s" % e}
    if not profile_name:
        return {"ok": None, "profile": None, "mismatches": [],
                "note": "No enabled EC Digital Signature Profile for (%s, %s) - flow is "
                        "inert, nothing to compare." % (BUSINESS_DOCTYPE, APPROVAL_TYPE)}
    row = frappe.db.get_value("EC Digital Signature Profile", profile_name,
                              list(EXPECTED_PROFILE_POLICY.keys()), as_dict=True) or {}
    mismatches = []
    for field, expected in EXPECTED_PROFILE_POLICY.items():
        live = _normalize(field, row.get(field))
        if live != expected:
            mismatches.append({"field": field, "expected": expected, "live": live})
    return {"ok": not mismatches, "profile": profile_name, "mismatches": mismatches}
