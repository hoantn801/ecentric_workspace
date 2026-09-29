# Copyright (c) 2026, eCentric and contributors
"""Idempotent Clearance Request Web Page sync (29/09/2026).

Trang MOI nhung co khoa chong troi ngay tu dau: BASELINE_SHA256 la sha cua HTML commit nay
ship. Lan sync dau tien (patch tao trang) TAO trang - khoa khong ap cho trang chua ton tai;
tu lan sau, ai sua tay tren site thi sync tu choi thay vi ghi de. Doi HTML = ba buoc:
patch resync -> patches.txt -> sha trong resync_manifest.json + BASELINE o day."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/clearance-request"
NAME = "clearance-request"
TITLE = "Clearance Request"

BASELINE_SHA256 = "730ad1ba443632ab1e513ebcf798552de80602d8040862223335c21522accb85"
SUPERSEDES_SHA256 = ()


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "ui", "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None, force=0):
    """Guarded create-or-update. force=1 bo DUY NHAT khoa chong troi, khong ep publish."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    if res.get("action") != "refused" and res.get("name") \
            and frappe.db.exists("Web Page", res["name"]):
        res["recorded_sha"] = page_sync_util.record_live_sha(ROUTE, res["name"])
    return res


@frappe.whitelist(methods=["POST"])
def sync_clearance_request_page():
    """Admin-safe re-sync (System Manager only)."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Clearance Request page."), frappe.PermissionError)
    return sync()
