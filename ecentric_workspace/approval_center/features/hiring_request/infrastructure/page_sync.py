# Copyright (c) 2026, eCentric and contributors
"""Idempotent Hiring Request Web Page sync. Delegates to the shared ORM-only upsert
(no DuplicateEntryError) and strips any legacy Web Page shim via the shared
meta-driven helper. Publishes for UAT; never activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/hiring-request"
NAME = "hiring-request"
TITLE = "Hiring Request"


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
BASELINE_SHA256 = "226f09edf7b42a68a12d9dc1207b992256622210b1e0ecc25872f65a121664d9"
SUPERSEDES_SHA256 = (
    "46472858ecbf6ea3ade0fe21a4603ca83e72cf259d5f6c64f7fc68fb7f51bab2",  # superseded by 226f09edf7b4 (upload errors + brand list + layout)
    "ea9cb9755d82bdad29331643f547c402de1425bebc5f0dd210922bcd4a434634",  # superseded by 46472858ecbf (upload UX + tick)
    "78c67342e6a92fa429ba27f2f050dd2c1d77319d980b328996f700cef406fd5e",  # superseded by ea9cb9755d82 (nhớ tab khi quay lại hub)
    "d8b7391cda80ac09e003ae02999d135f17dd21b4a9b965210f2244b6e42fd033",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "e527395908a88cef99b103c00f16f518cd14a35b980fcc4bcf59664899202f49",
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
def sync_hiring_request_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Hiring Request page."), frappe.PermissionError)
    return sync()
