# Copyright (c) 2026, eCentric and contributors
"""Dong bo Web Page /ec-hr/phan-bo-cong-viec (Nhan su > Phan bo cong viec) tu repo.

Route nam duoi /ec-hr chu khong phai /approvals: trang nay la cong viec hang thang cua
nhan vien (menu Nhan su), khong phai mot the trong danh muc phe duyet. shell.fallback
biet route nay qua _ROUTE_ALIASES["brand_weight"] - doi ROUTE thi doi ca cho do.

KHOA DRIFT: giong 26 page_sync khac (#144). Lan sync dau tao trang moi, khong bi chan.
Cap nhat sau nay: sua ui/main_section.html, doi BASELINE_SHA256 thanh sha moi, day gia
tri cu xuong SUPERSEDES_SHA256, trong CUNG mot commit (tools/ci/check.py --only pagesync)."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "ec-hr/phan-bo-cong-viec"
NAME = "phan-bo-cong-viec"
TITLE = "Phân bổ công việc"

BASELINE_SHA256 = "5eafeeb20759329d869dba284339a34da5613ca583d5182cdd758596ec12b75f"
SUPERSEDES_SHA256 = (
    "1d01c501aa16b106e59fc86b5fa92d344facbb508771671479e15212c85ee684",  # ban live dau tien (p211, 26/09) - truoc khi them luong tu chot Management
)


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "ui", "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None, force=0):
    """publish="preserve": trang chua co thi tao o trang thai published; trang da bi
    nguoi van hanh tat publish thi giu nguyen. force=1 chi bo khoa drift."""
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
def sync_brand_weight_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the brand weight page."), frappe.PermissionError)
    return sync()
