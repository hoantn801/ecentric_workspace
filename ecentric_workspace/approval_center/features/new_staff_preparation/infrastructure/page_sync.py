# Copyright (c) 2026, eCentric and contributors
"""Idempotent New Staff Preparation Web Page sync (28/09/2026).

Trang MOI nhung co khoa chong troi ngay tu dau: BASELINE_SHA256 la sha cua HTML commit nay
ship. Lan sync dau tien (patch tao trang) TAO trang - khoa khong ap cho trang chua ton tai;
tu lan sau, ai sua tay tren site thi sync tu choi thay vi ghi de. Doi HTML = ba buoc:
patch resync -> patches.txt -> sha trong resync_manifest.json + BASELINE o day."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/new-staff-preparation"
NAME = "new-staff-preparation"
TITLE = "New Staff Preparation"

BASELINE_SHA256 = "d9566b1a2d8e448471be653d97ef6f49b1d6b7280dc703f69438ca2a8765dff1"
SUPERSEDES_SHA256 = (
    "c2c2ac874b21f422816c5cf88bbe22ef433bd1efada1a8befd00fef5381027ba",  # truoc 26/11 gan phieu duyet cho nguoi lap (p561)
    "ea188285ed52936229ae3c216a3b1cae3d361c130cb302bac86e82ec9b7454be",  # truoc 24/11 tien trinh A + tom tat A1 + bang tinh B
    "9ef51d7643fc8ec2a967996447605106a9675dac90de8df53e8074b030e5fcdf",  # truoc p500 (quy trinh A-Z, 24/11)
    "dc6321fb19ec21068459a57a2fd8ab13b4f42b9ec4a7b4f7d1e09a141ed21d71",  # truoc p499 (dau trang thanh cong cu dinh, 23/11)
    "3fae36ba410555560bb1d6186ce55ff4943d57b0e6f9fe8cac298fdbd889a809",  # ban truoc dot HR v2 23/11 (p442)
    "607193e6d7e404d37e2d2e220a91c15e75736ec34fc8dbabefc5bb90612272eb",  # ban truoc dot UX lich su/tien trinh/loi 03/11
    "78e058a80de0472a5d2f7bb68283b198dbdad9a218259bb7c2ada4ef1648eaa4",  # ban truoc dot nut Nhac nguoi xu ly 01/10
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
def sync_new_staff_preparation_page():
    """Admin-safe re-sync (System Manager only)."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the New Staff Preparation page."), frappe.PermissionError)
    return sync()
