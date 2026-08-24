# Copyright (c) 2026, eCentric and contributors
"""Versioned, idempotent Livestream supplies request Web Page sync. The page patch creates the
page once at migrate; frontend changes need this admin-safe re-sync. Publishes the
Web Page for controlled/direct UAT; NEVER activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/livestream-supplies"
NAME = "approval-center-livestream-supplies"
TITLE = "Livestream Supplies Request"


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
BASELINE_SHA256 = "5a96867b08211cfd06ac186b45c8c5d915876084d60348bc8155c578b43cb0aa"
SUPERSEDES_SHA256 = (
    "d480d3c94c5c52a897a29499c0c8bce5d08468891c10e2e7f7978f4057088f85",  # superseded by 5a96867b0821 (nhớ tab khi quay lại hub)
    "84d032ed87f173bb9a4ea405983373267a99e13c920077a6132dfd15f6732157",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "1e37c4d9f00cb6cb3fa02c415134cb0bdcecdf165eeb91a218bfe060b8c5d423",
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
def sync_livestream_supplies_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Livestream supplies request page."), frappe.PermissionError)
    return sync()
