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

BASELINE_SHA256 = "e6ab8761fa0f08347592f70de940145337f0774af1dc8c487c18c9d6a1abfc8d"
SUPERSEDES_SHA256 = (
    "6c00f24974e933d3d35ebd611b771ad4052cfeac551f628a1e8b7adc0fd338bf",  # truoc 24/11 tien trinh A + tom tat A1 + bang tinh B
    "066d013e45a8f2241d903d6f8e65c805f839204d308285a5f9e0f11105d04a92",  # truoc p500 (quy trinh A-Z, 24/11)
    "138eee910db27ba465e900f0a1ef5cbe7eafbfc49756123eb2fa04dd1317f166",  # truoc p499 (dau trang thanh cong cu dinh, 23/11)
    "30ea2f62193d68623b68c5723e61d9dd0802b490f80720c20ce8b37126c179a6",  # ban truoc dot UX lich su/tien trinh/loi 03/11
    "730ad1ba443632ab1e513ebcf798552de80602d8040862223335c21522accb85",  # ban truoc dot nut Nhac nguoi xu ly 01/10
)


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
