# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the LEGACY /all-ticket Web Page (ticket list).

Phase 2B.1 repo-ization: main_section.html was imported VERBATIM from the live
ground-truth snapshot 20260716_004227 (main_section == main_section_html,
sha-verified), converting this T4 live-only page to a repo-owned source. The
first sync against unchanged live content MUST return {"action": "unchanged"}
-- that is the drift-detection dry run. All approval/GBS/contract action logic
lives inside the page body and is governed by live Server Scripts; this module
only ships HTML."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "all-ticket"
NAME = "all-ticket"
TITLE = "All Ticket"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 of main_section.html as it ships in this commit (C4b, 2026-08-03: the
# ec-native-rows-v1 Desk redirect was removed so MSO/SO/PO rows open /approval
# again). upsert_web_page REFUSES to write when live hashes to none of the
# accepted values, so a repo snapshot can never silently revert a live edit.
# Deliberate update = edit main_section.html, bump this constant, and move the
# value it replaced into SUPERSEDES_SHA256 -- all in the same commit.
BASELINE_SHA256 = "c12f872cec6fe437b71c1b0289560e396032444f4e4b2da58d1c0a78dab778da"

# Live values this snapshot is allowed to overwrite. C4b was authored in the
# repo, not on the site, so at deploy time live still holds the #138 bytes
# (5f7809...) -- without listing them here the first sync would be refused and
# the only way through would be force=1, which disarms the drift lock entirely.
# After the first successful sync live holds BASELINE_SHA256 and re-runs are
# "unchanged". Prune entries once the deploy is confirmed on every environment.
SUPERSEDES_SHA256 = (
    "6a5009ad76abd904d60f72d41f36803551cfbec49d45721752dd08e2ec18d389",
    "5f78091710e070d8ced163351a1381f6e3ea2b9089b71b7d741411766df2843a",  # #138
)


def sync(html=None, force=0):
    """Guarded sync. publish=None never re-publishes a page an operator
    un-published; expect_sha refuses (writes nothing) on live drift.
    force=1 drops only the drift lock -- it never force-publishes."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish=None,
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    if res.get("action") == "refused":
        return res
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
        from ecentric_workspace.legacy_pages import serving
        res.update(serving.ensure_static_serving(res["name"], html))
    return res


@frappe.whitelist(methods=["POST"])
def sync_all_ticket_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /all-ticket page."), frappe.PermissionError)
    return sync()
