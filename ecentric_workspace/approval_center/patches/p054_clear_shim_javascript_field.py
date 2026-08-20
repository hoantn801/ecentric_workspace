# Copyright (c) 2026, eCentric and contributors
"""Clear the legacy shim stored in the Web Page `javascript` field on Approval Center pages.

p053 ran the shared meta-driven stripper, but the shim that actually breaks the page lives
in the Web Page's `javascript` field, which the stripper may skip depending on field meta --
so the popup survived. Verified on live (approvals/asset-request): that field holds ~17 KB of
legacy JS with the 'SHIM cho Web Page' banner calling frappe.db.get_doc("Asset Request", ...),
a doctype that does not exist (the real one is "EC Asset Request") -> DoesNotExistError, i.e.
the 'Asset Request <name> not found' + 'Not found' popup when a request is opened via its
deep link. main_section is clean and every other approvals/* page has an EMPTY javascript
field and works fine, so the field is pure leftover.

Safety: scoped to route 'approvals/%' AND gated on the unambiguous 'SHIM cho Web Page'
banner, so pages that legitimately use frappe.client / frappe.db.get_doc in their javascript
field (e.g. de-nghi-mua-hang, attendance-database, all-internal-requests) are never touched.
ORM-only; idempotent (re-running finds nothing to clear).
"""
import frappe

BANNER = "SHIM cho Web Page"


def execute():
    names = frappe.get_all("Web Page", filters={"route": ["like", "approvals/%"]}, pluck="name")
    cleared = []
    for name in names:
        try:
            js = frappe.db.get_value("Web Page", name, "javascript")
        except Exception:
            continue
        if js and BANNER in js:
            frappe.db.set_value("Web Page", name, "javascript", "")
            cleared.append(name)
    if cleared:
        frappe.db.commit()
    frappe.logger("approval_center").info(
        "p054 cleared legacy shim javascript on %d page(s): %s" % (len(cleared), cleared))
