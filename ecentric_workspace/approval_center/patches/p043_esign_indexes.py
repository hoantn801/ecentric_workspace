# Copyright (c) 2026, eCentric and contributors
"""esign S2A: secondary indexes for the digital-signature tables. Idempotent (add_index
is a no-op when the index exists). SEEDS NO ROWS - by design S2A ships zero profile
rows, so the signing layer (and the engine signature guard) is globally inert until a
profile is created and gates are opened in a later, separately approved phase.
The unique index on EC Digital Signature Request.idempotency_key comes from the field
schema (unique=1), not from this patch."""
import frappe


def execute():
    for doctype, fields in (
        ("EC Digital Signature Request", ["status"]),
        ("EC Digital Signature Request", ["approval_request"]),
        ("EC Digital Signature Request", ["package"]),
        ("EC Digital Signature Package", ["approval_request"]),
        ("EC Digital Signature Package", ["business_doctype", "business_name"]),
        ("EC Digital Signature File", ["package"]),
        ("EC Digital Signature Placement", ["package"]),
        ("EC Digital Signature Event", ["signature_request"]),
        ("EC Digital Signature Event", ["package"]),
        ("EC Digital Signature Profile", ["business_doctype", "approval_type"]),
    ):
        try:
            frappe.db.add_index(doctype, fields)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p043_esign_indexes %s" % doctype)
    frappe.db.commit()
