# Copyright (c) 2026, eCentric and contributors
"""Remove the legacy Desk-style shim from Approval Center Web Pages (route approvals/*).

Symptom: opening a request via its deep link (e.g. the Teams notification link) popped
'Asset Request EC-ASSR-2026-00003 not found' + 'Not found'. Verified on live: the shim
lives in the Web Page's `javascript` field (approvals/asset-request, ~17 KB, contains the
'SHIM cho Web Page' banner) and calls frappe.db.get_doc("Asset Request", ...) -- a doctype
that does not exist (the real one is "EC Asset Request"), so Frappe throws DoesNotExistError
on page load. The page content itself (main_section) is clean and every other approvals/*
page has an EMPTY javascript field and works fine, so the field is pure legacy leftover.

Scope + safety:
  * only Web Pages whose route starts with 'approvals/' (other pages that legitimately use
    frappe.client / frappe.db.get_doc in their javascript field are never touched);
  * only when the unambiguous 'SHIM cho Web Page' banner is present;
  * clears just that field, ORM-only, and also runs the shared meta-driven stripper for any
    other field that carries a shim marker.
"""
import frappe

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

BANNER = "SHIM cho Web Page"


def execute():
    names = frappe.get_all("Web Page", filters={"route": ["like", "approvals/%"]}, pluck="name")
    cleared = []
    for name in names:
        try:
            js = frappe.db.get_value("Web Page", name, "javascript")
        except Exception:
            js = None
        if js and BANNER in js:
            frappe.db.set_value("Web Page", name, "javascript", "")
            cleared.append(name)
        try:
            page_sync_util.strip_legacy_shims(name)
        except Exception:
            frappe.logger("approval_center").warning("p053: strip_legacy_shims failed on %s" % name)
    if cleared:
        frappe.db.commit()
    frappe.logger("approval_center").info(
        "p053 cleared legacy shim javascript on %d page(s): %s" % (len(cleared), cleared))
