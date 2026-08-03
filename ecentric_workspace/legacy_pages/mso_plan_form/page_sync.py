# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the LEGACY /mso-plan-form Web Page.

This is the MSO plan creation/edit form. Reached from the sidebar ('MSO
Request') and from /approval when a KAM opens an MSO for editing; /mso-form
301-redirects here.

#61 repo-ization (2026-08-03): main_section.html was imported VERBATIM from
live team.ecentric.vn -- main_section == main_section_html, sha-verified -- so
this page stops being site-only. Until now it existed on the server and nowhere
else: a rebuild would have lost it, and nothing in review could see what it
contained. The first sync against unchanged live content MUST return
{"action": "unchanged"}; that is the drift-detection dry run.

The page ships HTML only. Every action it performs (create/edit/submit, the
GBS/boxme push, the resubmit round-trip) is executed by live Server Scripts and
whitelisted endpoints, which this module does not touch."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "mso-plan-form"
NAME = "mso-plan-form"
TITLE = "MSO Plan Form"  # exact live title -- required for the first sync to be "unchanged"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 of main_section.html as it ships in this commit == the live
# main_section_html at import time (5adb8dc45511b2182cfa4a1d64648f07377247239c85c79e0c0f714e3c9d60b2).
#
# upsert_web_page REFUSES to write (and changes nothing) when live hashes to
# none of the accepted values. This page has a history of being edited straight
# on the site, so without the lock a stray call to the endpoint below would
# silently revert those edits to whatever the repo happened to hold.
#
# Deliberate update = edit main_section.html, bump BASELINE_SHA256, and move the
# value it replaced into SUPERSEDES_SHA256 -- all in the same commit.
BASELINE_SHA256 = "5adb8dc45511b2182cfa4a1d64648f07377247239c85c79e0c0f714e3c9d60b2"
SUPERSEDES_SHA256 = ()


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
def sync_mso_plan_form_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /mso-plan-form page."), frappe.PermissionError)
    return sync()
