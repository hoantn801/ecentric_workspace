# Copyright (c) 2026, eCentric and contributors
"""Idempotent Resignation Web Page sync. Delegates to the shared, ORM-only upsert
(approval_center.page_sync_util) so migrate re-runs / prior syncs never raise
DuplicateEntryError, then removes any legacy Desk-style shim left on the live Web Page.

The shim (`// ===== SHIM cho Web Page ... frappe.db.get_doc ...`) POSTs to "/" on a
website page and pops a false "not found". It is NOT in our source and its location
varies by site, so we detect it dynamically via Web Page meta (never a hardcoded
column - this site's Web Page has no `head_html`). Publishes for UAT; never activates
the catalog card. No Approval Engine change."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/resignation"
NAME = "resignation"               # Web Page is named after the route slug by Frappe
TITLE = "Resignation"

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
BASELINE_SHA256 = "8bdab20ff0c250528390da2b3ea37e6a3a99bce6998a840abe1a2dd0028884ba"
SUPERSEDES_SHA256 = (
    "6006d54760f0348ce0e1e0c27a1a34c3472bf2e41a94a5a541809a7da7845d25",  # superseded by 8bdab20ff0c2 (upload UX + tick)
    "b26e4be49eb2f3f35a62fbf20537f32bc65d5279bc4e63afb02e5b684477d4fe",  # superseded by 6006d54760f0 (nhớ tab khi quay lại hub)
    "7920cf3e8f3fb80ee4dc08ef83142c1df7cb024ae0c0a10f1c700741ca488a4e",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "05630031fd7a3065b8412a0c00c014b11b4b1d0b02ca6be749272266a219ea18",
)


def sync(html=None, force=0):
    """Create-or-update the Web Page from clean source (idempotent), then strip any legacy shim
    found in a real Web Page field. Returns {action, route, name, inspected_fields,
    shim_fields_stripped, has_legacy_shim}.

    Guarded (#144): publish="preserve" never re-publishes a page an
    operator un-published (a page that does not exist yet is created
    published); expect_sha refuses -- writing nothing -- when live has
    drifted away from the snapshot this commit ships. force=1 drops ONLY
    the drift lock; it never force-publishes.
    """
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )   # main_section replaced with clean source
    if res.get("action") != "refused" and res.get("name") \
            and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
    else:
        res.update({"inspected_fields": [], "shim_fields_stripped": [], "has_legacy_shim": False})
    return res


@frappe.whitelist(methods=["POST"])
def sync_resignation_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Resignation page."), frappe.PermissionError)
    return sync()
