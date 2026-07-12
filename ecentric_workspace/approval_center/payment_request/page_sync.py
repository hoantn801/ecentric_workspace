# Copyright (c) 2026, eCentric and contributors
"""Idempotent Payment Request Web Page sync. Delegates to the shared ORM-only upsert
(no DuplicateEntryError) and strips any legacy Web Page shim via the shared
meta-driven helper. Publishes for UAT; never activates the catalog card.

S2B-B: the governed SCTS signing panel (esign/ui/payment_request_signing.html) is
appended to the main section exactly once, on the Payment Request page only. The whole
section is rebuilt from source on every sync, so installation is idempotent."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "approvals/payment-request"
NAME = "payment-request"
TITLE = "Payment Request"


def _esign_panel():
    """The governed SCTS signing panel appended to the PR detail page (S2B-B). Returns an
    empty string if the panel source is missing so a sync never fails on its absence."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # approval_center
    try:
        with open(os.path.join(base, "esign", "ui", "payment_request_signing.html"),
                  encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "payment_request.main_section.html"),
              encoding="utf-8") as fh:
        main = fh.read()
    return main + "\n" + _esign_panel()


def sync(html=None):
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
    return res


@frappe.whitelist(methods=["POST"])
def sync_payment_request_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Payment Request page."), frappe.PermissionError)
    return sync()
