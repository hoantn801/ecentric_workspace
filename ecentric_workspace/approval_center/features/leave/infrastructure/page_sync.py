# Copyright (c) 2026, eCentric and contributors
"""Idempotent Leave Web Page sync via the shared ORM-only upsert + meta-driven shim strip.
Publishes for UAT; never activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/leave"
NAME = "leave"
TITLE = "Leave"


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
BASELINE_SHA256 = "a228026edc838c8c09c5c01e43abe689042687cd17853f17f97a9e5690cb28c2"
SUPERSEDES_SHA256 = (
    "2f66e600f62437ef2cd771bf717000852f5ba90243eb425896ec45a2bb40f404",  # superseded by a228026edc83 (upload errors + brand list + layout)
    "b8ebbd3af9b4c4ba1b78143cc6303eea7931b748c79d6deb1df44a87bdaa535e",  # superseded by 2f66e600f624 (upload UX + tick)
    "a8e0fb4ea0ef2e55e66774fcbab98766f54b3ad72acd5b7bd91d38eab4dff2c6",  # superseded by b8ebbd3af9b4 (nhớ tab khi quay lại hub)
    "9076b6b12e8653354f1ea2c0ca39c4cedc0d00a240d6d3ceb35375cb0709b2fb",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "2dfbf7906db77eb8f39d6d40bc4bbe992b670248310366c9f4ca72131cc08d33",
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
    else:
        res.update({"inspected_fields": [], "shim_fields_stripped": [], "has_legacy_shim": False})
    return res


@frappe.whitelist(methods=["POST"])
def sync_leave_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Leave page."), frappe.PermissionError)
    return sync()
