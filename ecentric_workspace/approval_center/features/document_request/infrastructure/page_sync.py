# Copyright (c) 2026, eCentric and contributors
"""Versioned, idempotent Document Request Web Page sync. The page patch creates the
page once at migrate (run-once); Frappe will not re-run it, so frontend changes
need this whitelisted, admin-safe re-sync. Publishes the page for controlled/direct
UAT; NEVER activates the catalog card. No Approval Engine change."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/document-request"
NAME = "approval-center-document-request"
TITLE = "Document Request"


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
BASELINE_SHA256 = "6716c3a63bcdf8f82edadc1205f442c292eb9937c31c321a37fe7db176becf27"
SUPERSEDES_SHA256 = (
    "1fa72da7e52ce1803a92f8e01bc910fcde56ebd06d94bdd9c226e8d7bc44ef3e",  # superseded by 6716c3a63bcd (upload UX + tick)
    "673bb39b24957d54d2e2c8ee9ab130d7ea63e0c94ae0828b64ac7cbb3f3f2fab",  # superseded by 1fa72da7e52c (nhớ tab khi quay lại hub)
    "3eecbc206fb2c85fe65aba86f2c204842f7417b934f521ef34d79c079a9de70f",  # superseded by the hub edit (bỏ 3 tab + upload nhiều tệp)
    "f7758081b542638563c75af704ecaeb055285e230efc762b9e18351e37360f53",
)


def sync(html=None, force=0):
    """Guarded sync (#144). Delegates to the shared upsert helper -- this module
    used to carry its own hand-rolled copy of the lookup/insert/update logic,
    which meant the drift lock and the publish-preserve rule could not reach it.

    publish="preserve" -- never re-publishes a page an operator un-published;
                          a page that does not exist yet is created published.
    expect_sha         -- refuses (writes nothing) when live has drifted away
                          from the snapshot this commit ships.
    force=1            -- drops ONLY the drift lock; it never force-publishes.

    Returns {action: created|updated|unchanged|skipped|refused, route, name}."""
    html = html if html is not None else _html()
    return page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )


@frappe.whitelist(methods=["POST"])
def sync_document_request_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Document Request page."), frappe.PermissionError)
    return sync()
