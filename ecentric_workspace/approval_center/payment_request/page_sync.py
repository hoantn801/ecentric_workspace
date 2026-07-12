# Copyright (c) 2026, eCentric and contributors
"""Idempotent Payment Request Web Page sync. Delegates to the shared ORM-only upsert
(no DuplicateEntryError) and strips any legacy Web Page shim via the shared
meta-driven helper. Publishes for UAT; never activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "approvals/payment-request"
NAME = "payment-request"
TITLE = "Payment Request"


def _esign_panel():
    """The governed SCTS signing panel, appended to the PR detail page (S2B-B). Idempotent
    by construction: the whole main_section is rebuilt from source on every sync, so the
    panel appears exactly once and only on the Payment Request page."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(base, "esign", "ui", "payment_request_signing.html"),
                  encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "payment_request.main_section.html"), encoding="utf-8") as fh:
        main = fh.read()
    retur