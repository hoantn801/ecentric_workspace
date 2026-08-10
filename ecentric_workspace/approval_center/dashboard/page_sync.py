# Copyright (c) 2026, eCentric and contributors
"""Idempotent Web Page sync for the Approval Center Operations Dashboard.
Route /approvals/dashboard. Delegates to the shared ORM-only upsert + legacy-shim strip.
Published for use; this is a reporting page (no catalog card involved)."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "approvals/dashboard"
NAME = "approvals-dashboard"
TITLE = "Approval Center Dashboard"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "approvals_dashboard.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# --- drift lock (#144, 2026-08-03) -------------------------------------------
# sha256 of the exact HTML this commit ships. Verified equal to the live
# main_section_html on team.ecentric.vn at the time of the commit, so the first
# sync after deploy returns "unchanged".
#
# upsert_web_page REFUSES to write (and changes nothing) when live hashes to
# none of the accepted values below. That is the whole point: several of these
# pages have been edited directly on the site in the past, and without the lock
# a stray call to the whitelisted sync endpoint would silently revert live to
# whatever the repo happened to hold.
#
# Deliberate update = edit the frontend source, bump BASELINE_SHA256 to the new
# sha, and move the value it replaced into SUPERSEDES_SHA256 -- all in the same
# commit. SUPERSEDES_SHA256 exists for repo-authored edits: at deploy time live
# still holds the bytes being superseded, and after the first successful write
# it holds the new snapshot; both are "not drifted", so both must be accepted.
BASELINE_SHA256 = "b49848db98abac2b5662695c9d80a9ddedf0f0546850b7f42fd09c09d0ccab00"

# Giá trị live mà snapshot này được phép ghi đè.
#
# 5c6b19cb... là bytes của d6d412c (GD2 C2 UAT fix), tức là baseline ĐÚNG cho tới khi
# PR #241 (b082c2a, ec-datepicker: thêm data-ec-dp-range vào form lọc) sửa
# frontend/approvals_dashboard.main_section.html mà KHÔNG bump hằng số này. Từ đó
# BASELINE_SHA256 không còn khớp HTML repo ship, nên sync ghi được đúng một lần rồi
# refused vĩnh viễn. tools/ci/check.py (phép kiểm `pagesync`) bắt được sai lệch đó.
#
# Liệt kê ở đây để cả hai trạng thái live đều đi tiếp được: môi trường còn giữ bytes
# d6d412c thì sync tiến lên, môi trường đã nhận bytes #241 thì trả về "unchanged".
# Bỏ entry này khi đã xác nhận deploy trên mọi môi trường.
SUPERSEDES_SHA256 = (
    "5c6b19cb4355d31589cc57b8a6287b8cc74035c5728477554eb719c3eae7e074",
)


def sync(html=None, force=0):
    """Guarded sync (#144).

    publish="preserve" -- never re-publishes a page an operator un-published;
                          a page that does not exist yet is created published.
    expect_sha         -- refuses (writes nothing) when live has drifted away
                          from the snapshot this commit ships.
    force=1            -- drops ONLY the drift lock; it never force-publishes.
    """
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    if res.get("action") != "refused" and res.get("name") \
            and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
    return res


@frappe.whitelist(methods=["POST"])
def sync_dashboard_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Approval Center Dashboard page."), frappe.PermissionError)
    return sync()
