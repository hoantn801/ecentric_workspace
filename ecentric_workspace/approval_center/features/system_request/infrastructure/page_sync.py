# Copyright (c) 2026, eCentric and contributors
"""Idempotent System Request Web Page sync. Delegates to the shared, ORM-only upsert
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

ROUTE = "approvals/system-request"
NAME = "system-request"               # Web Page is named after the route slug by Frappe
TITLE = "System Request"

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
BASELINE_SHA256 = "d3a77df5b2e0a8626f6713a48b1cbe21ddfee0265bda49482ff59b66f92f5436"
SUPERSEDES_SHA256 = (
    "c15dbe49280903e41f9ed4dfb586eefcedfc636f464adeea3faff475ce75637b",  # superseded by d3a77df5b2e0 (upload errors + brand list + layout)
    "533dd29fb6ab5f9e4299adf1d68a94fb2fedc1425e1679bef1b194b195ce2b8c",  # superseded by c15dbe492809 (upload UX + tick)
    "7f97baed16ad38f526d306f656025c6627f83ba6958de5da420811b73ac20e7f",  # superseded by 533dd29fb6ab (nhớ tab khi quay lại hub)
    "8e20aa7b9f14d4f035a6cb47cc09369af88aa7f2057598514bab2a96991a6573",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "747f9555d170ff04bb3af5dd5ed01aba5fc15b00d43e1420fd469e0d510c5304",
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
def sync_system_request_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the System Request page."), frappe.PermissionError)
    return sync()
