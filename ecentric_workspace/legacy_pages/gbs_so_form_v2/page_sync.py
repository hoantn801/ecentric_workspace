# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the LEGACY /gbs-so-form-v2 Web Page.

This is the GBS Sales Order creation/edit form. /so-form 301-redirects here.
Also the landing page for 'Sua & Submit lai' (?edit=<name>) after a Finance
send-back or a GBS/boxme rejection.

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

ROUTE = "gbs-so-form-v2"
NAME = "gbs-so-form-v2"
TITLE = "gbs-so-form-v2"  # exact live title -- required for the first sync to be "unchanged"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 of main_section.html as it ships in this commit == the live
# main_section_html at import time (01da088994cd5c4479d83b47b7f59b74989cc3721d39554a979de3f01abb6efc).
#
# upsert_web_page REFUSES to write (and changes nothing) when live hashes to
# none of the accepted values. This page has a history of being edited straight
# on the site, so without the lock a stray call to the endpoint below would
# silently revert those edits to whatever the repo happened to hold.
#
# Deliberate update = edit main_section.html, bump BASELINE_SHA256, and move the
# value it replaced into SUPERSEDES_SHA256 -- all in the same commit.
BASELINE_SHA256 = "252629aa972b5b2c1a18986fb424bb9dfcf526e53d36151ca80b54818f889665"
SUPERSEDES_SHA256 = (
    "01da088994cd5c4479d83b47b7f59b74989cc3721d39554a979de3f01abb6efc",
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
def sync_gbs_so_form_v2_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /gbs-so-form-v2 page."), frappe.PermissionError)
    return sync()
