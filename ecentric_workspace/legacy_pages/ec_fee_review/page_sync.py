# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the /ec-fee-review Web Page (GBS: ra ma phi GBS SO chua map vao EC).

Repo-ization 29/09/2026 (A65): ban LIVE nguyen van vao repo o commit truoc (BASELINE
5986e908...). p225 (NHIEU_LOP/brief_gbs.md muc 6): khoi "Tao Item EC" len tren bang +
cot bang co dinh -> khong con bi day lech khi danh sach tai xong.
The page reads/writes through live Server Scripts `ec_fee_item_audit` and
`ec_fee_item_create`; this module only ships HTML."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "ec-fee-review"
NAME = "ec-\u2014-r\u00e0-m\u00e3-ph\u00ed-gbs-ch\u01b0a-map"
TITLE = "EC \u2014 R\u00e0 m\u00e3 ph\u00ed GBS ch\u01b0a map"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# upsert_web_page REFUSES to write when live no longer hashes to one of these, so a
# repo snapshot can never silently revert a live edit.
BASELINE_SHA256 = "b9212c8a8d104fa4c4a0eae91abcf63b6caf2bb85ca011c0039bb2fc63a77927"
SUPERSEDES_SHA256 = (
    # 29/09: ban live nguyen van (modified 2026-07-25), = BASELINE cua commit dua nguon ve repo.
    "5986e90892652f1719c8f007a6c0b1ac86502dcdfce4b524b43bcf1b7b607241",
)


def sync(html=None, force=0):
    """Guarded sync. publish=None never re-publishes a page an operator
    un-published; expect_sha refuses (writes nothing) on live drift.
    force=1 drops only the drift lock -- it never force-publishes."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish=None,
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    if res.get("action") == "refused":
        return res
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
        from ecentric_workspace.legacy_pages import serving
        res.update(serving.ensure_static_serving(res["name"], html))
    return res


@frappe.whitelist(methods=["POST"])
def sync_ec_fee_review_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /ec-fee-review page."), frappe.PermissionError)
    return sync()
