# Copyright (c) 2026, eCentric and contributors
"""Idempotent Asset Damage or Loss Web Page sync. Delegates to the shared ORM-only upsert
(no DuplicateEntryError) and strips any legacy Web Page shim via the shared
meta-driven helper. Publishes for UAT; never activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/asset-damage-loss"
NAME = "asset-damage-loss"
TITLE = "Asset Damage or Loss"


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
BASELINE_SHA256 = "fed64a07a50aa9d178ff176da45bd5952a4c81a24b5b64d718b61be3cee95c36"
SUPERSEDES_SHA256 = (
    "a6c0de25b4df619a8e3d0bfc6ef2ff8f442307452f81b8c889acaa560489de23",  # superseded by fed64a07a50a (upload errors + brand list + layout)
    "6e7b8eb498e35a97835dabc5c53dd061259998f98d63f1d0ea6bcec22fc7fe68",  # superseded by a6c0de25b4df (upload UX + tick)
    "3d9f367eb4686ade6716fdc09dafa031a9050fdd693203bdfb579d9536956e03",  # superseded by 6e7b8eb498e3 (nhớ tab khi quay lại hub)
    "fb7d960af7bcb6bb7a131caa9ca75d7595cee95dc6d12b492da9d49b4b6b6086",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "805290ddd78ba478e7d9a5fcf7baee7ddd8bcd38b9f88cb2dc6ecf5c5267f9a4",
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
def sync_asset_damage_loss_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Asset Damage or Loss page."), frappe.PermissionError)
    return sync()
