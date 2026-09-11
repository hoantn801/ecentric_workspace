# Copyright (c) 2026, eCentric and contributors
"""Idempotent Booking Request Web Page sync (khuon chuan cua moi form).
Trang MOI nen chua co drift lock: baseline se duoc chot o lan sua HTML dau tien
sau khi trang da song tren production."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/booking-request"
NAME = "booking-request"
TITLE = "Booking Request"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "ui", "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None, force=0):
    """Create-or-update the Web Page from source. Idempotent."""
    html = html if html is not None else _html()
    return page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html, publish="preserve")


@frappe.whitelist(methods=["POST"])
def sync_booking_request_page():
    """Admin-safe re-sync (System Manager only)."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Booking Request page."),
                     frappe.PermissionError)
    return sync()
