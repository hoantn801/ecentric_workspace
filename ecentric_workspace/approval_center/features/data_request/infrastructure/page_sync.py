# Copyright (c) 2026, eCentric and contributors
"""Versioned, idempotent Data Request Web Page sync. The page patch creates the
page once at migrate (run-once); Frappe will not re-run it, so frontend changes
need this whitelisted, admin-safe re-sync. Publishes the page for controlled/direct
UAT; NEVER activates the catalog card. No Approval Engine change."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/data-request"
NAME = "approval-center-data-request"
TITLE = "Data Request"


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
BASELINE_SHA256 = "74b0691b073f68c0a9977a6726ff51d1b4ca0119edeb48a0296393e6690e8404"
SUPERSEDES_SHA256 = (
    "043db98e117a66dd4387c8c7c1c2aa4573ca2907e1bcc5c7abc1c9c3cf4f800d",  # superseded by 74b0691b073f (upload UX + tick)
    "2c96aa55fe2e3cb5bad4138a82e8b9d8950cd98808c0b8febbe950fc3edf968b",  # superseded by 043db98e117a (nhớ tab khi quay lại hub)
    "2a54e49e4cbb53cff9c40857a8e0e6fae9b18f213f2969340e1b8081e23e223b",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "5ecd1b7b0bd0371d86957c1249a62535cf3d1db08106b6331c3586d84ffe44de",
)


def sync(html=None, force=0):
    """Guarded sync (#144). Delegates to the shared upsert helper -- this module
    used to carry its own hand-rolled copy of the lookup/insert/update logic,
    which meant the drift lock and the publish-preserve rule could not reach it.

    publish="preserve" -- never re-publishes a page an operator un-published;
                          a page that does not exist yet is created published.
    expect_sha         -- refuses (writes nothing) when live has drifted away
                          from the snapshot this commit ships.
    force=1            -- drops ONLY the drift lock; it never force-publishes.

    Returns {action: created|updated|unchanged|skipped|refused, route, name}."""
    html = html if html is not None else _html()
    return page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )


@frappe.whitelist(methods=["POST"])
def sync_data_request_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Data Request page."), frappe.PermissionError)
    return sync()
