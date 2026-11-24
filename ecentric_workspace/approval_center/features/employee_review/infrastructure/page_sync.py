# Copyright (c) 2026, eCentric and contributors
"""Idempotent Danh gia nhan su Web Page sync (23/11/2026).

Trang MOI nhung co khoa chong troi ngay tu dau: BASELINE_SHA256 la sha cua HTML commit nay ship
(tools/ci/check.py in gia tri dung). Lan sync dau (patch p450) TAO trang; tu lan sau ai sua tay
tren site thi sync tu choi thay vi ghi de. Doi HTML = ba buoc: patch resync -> patches.txt ->
sha trong resync_manifest.json + BASELINE o day."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/employee-review"
NAME = "employee-review"
TITLE = "Đánh giá nhân sự"

BASELINE_SHA256 = "965596e72a9d17bd56770a608818e01fe514898be225c64e7cf5f34b01818bf6"
SUPERSEDES_SHA256 = ("e4794020d97b8a5de15d381f7f8a586379f8c97e269168bbe507c2342493fc26", "c4292dbf3a1272a8cdc01e4edd2936010b8dea5b52b219c38b54f8c443b3590f", "55f99ebc7e2a3537c059c9c577af1c112893a8a47c9fd4c8d8cbb2e1e34eb4d1", "ad06cd7796421cdd434249c06f89f68dd3a59eca754ba31f3735e5f446e307a4",)


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
def sync_employee_review_page():
    """Admin-safe re-sync (System Manager only)."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Employee Review page."), frappe.PermissionError)
    return sync()
