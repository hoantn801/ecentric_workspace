# Copyright (c) 2026, eCentric and contributors
"""Idempotent Budget Setting Web Page sync. Delegates to the shared ORM-only upsert
(no DuplicateEntryError) and strips any legacy Web Page shim via the shared
meta-driven helper. Publishes for UAT; never activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/budget-setting"
NAME = "budget-setting"
TITLE = "Budget Setting"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "ui", "main_section.html"), encoding="utf-8") as fh:
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
BASELINE_SHA256 = "66c9f2015849d9edf873353b15caee04efea75884f38fbe88b5908a937dff6f6"
SUPERSEDES_SHA256 = (
    "11fe4cee4ddc2dea00e3aa08702c0d04ad98be8615732b6d7bb0220e753149f4",  # superseded by 66c9f2015849 (upload errors + brand list + layout)
    "930e66100a299982c880ea55e67399dfbda5dff0d80f8f06f1c6a8d7b6b11d29",  # superseded by 11fe4cee4ddc (upload UX + tick)
    "681e041579d433e7bd9f0aedb3296033b159e47fb62fae8784c1ffd058f722e6",  # superseded by 930e66100a29 (nhớ tab khi quay lại hub)
    "3bbf66bca86394b2814cda6eeed2f06c9e0174eb654e0e9a74fb5bee867607de",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "8bdc823274a16dcf7e9db3b7d2673cbc52b358f9b4633af86fc15a3da0d92079",
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
def sync_budget_setting_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Budget Setting page."), frappe.PermissionError)
    return sync()
