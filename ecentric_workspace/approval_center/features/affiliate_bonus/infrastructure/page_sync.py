# Copyright (c) 2026, eCentric and contributors
"""Idempotent Affiliate Bonus Web Page sync. Delegates to the shared ORM-only upsert
(no DuplicateEntryError) and strips any legacy Web Page shim via the shared
meta-driven helper. Publishes for UAT; never activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/affiliate-bonus-request"
NAME = "affiliate-bonus-request"
TITLE = "Affiliate Bonus"


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
BASELINE_SHA256 = "e0450f42ece48ea27e43e18a13563897989efd3c255e93da07cb6b28d25cdf14"
SUPERSEDES_SHA256 = (
    "43fe58d9f99e5d152f19d111d71441e918813327c0c10a792eb07ea5e54289da",  # superseded by e0450f42ece4 (upload permission fix)
    "6396d355354162a907e2fb69554c7ce660e0a8ce2458baa1d9a1d351206ae403",  # superseded by 43fe58d9f99e (upload errors + brand list + layout)
    "2cf21ab875c37f0b8d30fab67974c3a8f9020e6079c0bc56ab80f0c94314d874",  # superseded by 6396d3553541 (upload UX + tick)
    "430e9015f7d69a4ca169df5a4691c129d137a51a93f56bb9e96d26a7ecdfe7d1",  # superseded by 2cf21ab875c3 (nhớ tab khi quay lại hub)
    "86c80b3abe3d7d95cdcf7c4bf9a4878fa638e00e912d0aed949c897a189f54c7",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "8839840bf294fb107a1f5b95c3982e4da501ba4d3acb6cda866c81f8c52bea67",
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
def sync_affiliate_bonus_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Affiliate Bonus page."), frappe.PermissionError)
    return sync()
