# Copyright (c) 2026, eCentric and contributors
"""Versioned, idempotent Service referral Web Page sync. The page patch creates the
page once at migrate; frontend changes need this admin-safe re-sync. Publishes the
Web Page for controlled/direct UAT; NEVER activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/service-referral"
NAME = "approval-center-service-referral"
TITLE = "Service Referral"


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
BASELINE_SHA256 = "a2fc7bb4cecc1fe8068bf1981e89d3885bbe1a1d5d3d60b8c416e3e568f06768"
SUPERSEDES_SHA256 = (
    "621d3240c8fa5730105140d33c7a35afbaa9d29feb53e0e28b9a803d3b97cf4c",  # superseded by a2fc7bb4cecc (upload UX + tick)
    "1cfb20570f02a2079f77b98f2736ccd87c2239992453a97eed25f90c257f6578",  # superseded by 621d3240c8fa (nhớ tab khi quay lại hub)
    "fdac82e1793cbf9c95642aaa4f0995a1a8ffb813716e1c8a99156beab89a5df0",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "c582bf68fd676342bb597d347397bacfc4a1944ba302c32ebcdc598193daaee3",
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
def sync_service_referral_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Service referral page."), frappe.PermissionError)
    return sync()
