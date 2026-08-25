# Copyright (c) 2026, eCentric and contributors
"""Idempotent Livestream Sample Web Page sync. Delegates to the shared ORM-only upsert
(no DuplicateEntryError) and strips any legacy Web Page shim via the shared
meta-driven helper. Publishes for UAT; never activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/livestream-sample"
NAME = "livestream-sample"
TITLE = "Livestream Sample"


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
BASELINE_SHA256 = "59e5eacf90f6fd8ae71b075427bce8a5291c4ea0b5e2561ae98a27098e1322c1"
SUPERSEDES_SHA256 = (
    "b2880075fb611e852fc0e9397bcdc4e106f3d6a1a1a403f3e946d1a5ea71aebb",  # superseded by 59e5eacf90f6 (upload UX + tick)
    "baa864588b20ab4019b7ded34a9c3f513ffb9b8b66a9fcc06f9562d7b100c779",  # superseded by b2880075fb61 (nhớ tab khi quay lại hub)
    "4f71794250ada2c8e2f84c604d8c1b315f024bcf0ff598484fbab18a1c057f88",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "fec7a29cc69daca86b2836b7a0e4c2a23122aa2e55eeee0d9d8f4808d9c5ba60",
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
def sync_livestream_sample_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Livestream Sample page."), frappe.PermissionError)
    return sync()
