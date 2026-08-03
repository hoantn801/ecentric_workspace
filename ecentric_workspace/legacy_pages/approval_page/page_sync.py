# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the LEGACY /approval Web Page (document approval inbox).

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

ROUTE = "approval"
NAME = "approval-page"
TITLE = "Approval"  # exact live title (snapshot _full.json) -- required for first-sync "unchanged"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# Live bytes this snapshot was taken from (re-snapshotted 2026-08-03, #138).
# upsert_web_page REFUSES to write when live no longer hashes to this, so a repo
# snapshot can never silently revert a live edit. Deliberate update = re-snapshot
# live into main_section.html, then bump this constant in the same commit.
BASELINE_SHA256 = "3f825f4e4761a69d1cdb6033eeabbd1b8b23476c2fad33d9226b137c124a4454"


def sync(html=None, force=0):
    """Guarded sync. publish=None never re-publishes a page an operator
    un-published; expect_sha refuses (writes nothing) on live drift.
    force=1 drops only the drift lock -- it never force-publishes."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish=None,
        expect_sha=None if force else BASELINE_SHA256,
    )
    if res.get("action") == "refused":
        return res
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
        from ecentric_workspace.legacy_pages import serving
        res.update(serving.ensure_static_serving(res["name"], html))
    return res


@frappe.whitelist(methods=["POST"])
def sync_approval_inbox_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /approval page."), frappe.PermissionError)
    return sync()
