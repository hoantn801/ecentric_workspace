# Copyright (c) 2026, eCentric and contributors
"""Idempotent Asset Request Web Page sync. Delegates to the shared, ORM-only upsert
(approval_center.page_sync_util) so migrate re-runs / prior syncs never raise
DuplicateEntryError. Publishes the page for controlled/direct UAT; NEVER activates
the catalog card. No Approval Engine change."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/asset-request"
NAME = "asset-request"               # Web Page is named after the route slug by Frappe
TITLE = "Asset Request"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "asset_request", "ui", "main_section.html"), encoding="utf-8") as fh:
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
BASELINE_SHA256 = "80bab8244aa0f36a040ea526a9def042c691b928a46f0a6b3114a353dd0d6f72"
SUPERSEDES_SHA256 = ()


def sync(html=None, force=0):
    """Create-or-update the Web Page from source. Idempotent (safe to re-run / re-migrate).
    Returns {action: created|updated|unchanged, route, name}.

    Guarded (#144): publish="preserve" never re-publishes a page an
    operator un-published (a page that does not exist yet is created
    published); expect_sha refuses -- writing nothing -- when live has
    drifted away from the snapshot this commit ships. force=1 drops ONLY
    the drift lock; it never force-publishes.
    """
    html = html if html is not None else _html()
    return page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )


@frappe.whitelist(methods=["POST"])
def sync_asset_request_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Asset Request page."), frappe.PermissionError)
    return sync()
