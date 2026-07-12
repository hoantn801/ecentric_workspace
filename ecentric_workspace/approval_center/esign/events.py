# Copyright (c) 2026, eCentric and contributors
"""Event + status helpers. Every state transition writes one append-only
EC Digital Signature Event; metadata is ALWAYS sanitized before persist."""
import frappe
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.esign import state as sm
from ecentric_workspace.approval_center.esign.sanitize import sanitize


def emit(event_type, signature_request=None, package=None, erp_actor=None,
         scts_effective_user=None, provider_txn_id=None, request_meta=None,
         response_meta=None, verification_result=None, retry_no=None, error_summary=None):
    """Insert one immutable event row. ignore_permissions: post-authorization system
    write to an SM-only DocType (house pattern - see engine.log_action)."""
    seq = 0
    if signature_request:
        seq = (frappe.db.count("EC Digital Signature Event",
                               {"signature_request": signature_request}) or 0) + 1
    prev = getattr(frappe.flags, "ec_esign_event_append", False)
    frappe.flags.ec_esign_event_append = True  # governed-append marker (controller gate)
    try:
        frappe.get_doc({
            "doctype": "EC Digital Signature Event",
            "signature_request": signature_request, "package": package, "seq": seq,
            "event_type": event_type, "event_time": now_datetime(),
            "erp_actor": erp_actor or frappe.session.user,
            "scts_effective_user": scts_effective_user, "provider_txn_id": provider_txn_id,
            "request_meta": frappe.as_json(sanitize(request_meta)) if request_meta else None,
            "response_meta": frappe.as_json(sanitize(response_meta)) if response_meta else None,
            "verification_result": verification_result, "retry_no": retry_no,
            "error_summary": (error_summary or "")[:140] or None,
        }).insert(ignore_permissions=True)
    finally:
        frappe.flags.ec_esign_event_append = prev


def set_package_status(pkg_name, to_status, **event_kw):
    """Guarded package transition: row lock -> assert legal edge -> write -> event."""
    frappe.db.get_value("EC Digital Signature Package", pkg_name, "name", for_update=True)
    cur = frappe.db.get_value("EC Digital Signature Package", pkg_name, "status")
    sm.assert_transition(sm.PACKAGE, cur, to_status)
    frappe.db.set_value("EC Digital Signature Package", pkg_name, "status", to_status)
    emit(event_kw.pop("event_type", to_status.replace(" ", "")), package=pkg_name, **event_kw)


def set_dsr_status(dsr_name, to_status, extra_fields=None, **event_kw):
    """Guarded DSR transition: row lock -> assert legal edge -> write -> event."""
    frappe.db.get_value("EC Digital Signature Request", dsr_name, "name", for_update=True)
    cur = frappe.db.get_value("EC Digital Signature Request", dsr_name, "status")
    sm.assert_transition(sm.DSR, cur, to_status)
    vals = {"status": to_status}
    vals.update(extra_fields or {})
    frappe.db.set_value("EC Digital Signature Request", dsr_name, vals)
    emit(event_kw.pop("event_type", to_status.replace(" ", "")),
         signature_request=dsr_name, **event_kw)
