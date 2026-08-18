# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the LEGACY /docs/architecture Web Page (document page).

Repo-ization: main_section.html imported VERBATIM via a UTF-8-safe extraction
(main_section == main_section_html, sha-verified; 0 mojibake), NOT the PS5
snapshot pipeline. First sync against unchanged live content returns
{"action": "unchanged"}. All business/GBS/chain logic lives in the page body and
is governed by live Server Scripts; this module only ships HTML."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "docs/architecture"
NAME = "architecture-guide"
TITLE = "Architecture Guide"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# Live bytes this snapshot was taken from (re-snapshotted 2026-08-03, #138).
# upsert_web_page REFUSES to write when live no longer hashes to this, so a repo
# snapshot can never silently revert a live edit. Deliberate update = re-snapshot
# live into main_section.html, then bump this constant in the same commit.
BASELINE_SHA256 = "955e4ea6a3cf947af20e338916f68a12bacaf6ac8b703d83ba46ce6ab7f49659"
SUPERSEDES_SHA256 = (
    "1abf28fa26882727eecae687d3a0b7350183e8266d75674a5b2bc67b8e798e33",
    "6fc49bd561adac70fe1e02b1120fb51f8db69100b10cf8a8ca8ed6df49bedf0f",
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
def sync_docs_architecture_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /docs/architecture page."), frappe.PermissionError)
    return sync()
