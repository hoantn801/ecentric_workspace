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


# sha256 of main_section.html as it ships in this commit. 2026-08-03 (post-C4b):
# re-imported VERBATIM from live, which had moved ahead of the repo by three
# additive edits and one replaced line -- +23/-1 against the C4b baseline:
#   1. ec-resubmit-realuser-v1  (authored on the site by the GBS side): on the
#      portal getSessionEmail() comes back empty, so isSubmitter was false for
#      the real submitter and the banner showed the "chi submitter moi sua duoc"
#      note instead of the button. Falls back to frappe.auth.get_logged_user and
#      reveals the button for submitter/owner. Backend still gates the action.
#   2. ec-drift-settled-guard-v1 (also site-authored): item-level drift banner
#      now only renders when the doc has actually settled on both sides
#      (status Approved AND gbs_status Approved/Completed).
#   3. ec-resubmit-repoll-v1 (this commit): ensureButton() returned without
#      re-arming its 3s poll once the Resubmit button existed, so after a
#      resubmit flipped status to "Can sua" the stale button stayed on screen
#      next to the banner's "Sua & Submit lai" -- the "2 nut resubmit" report.
#      It now keeps polling, and restores the Submit-on-GBS button it hid.
# upsert_web_page REFUSES to write when live hashes to none of the accepted
# values, so a repo snapshot can never silently revert a live edit. Deliberate
# update = edit main_section.html, bump this constant, and move the value it
# replaced into SUPERSEDES_SHA256 -- all in the same commit.
BASELINE_SHA256 = "78298a9ec4ca4420b608625788ee30713c9ff222ffd2177a17df7bc14e5a81fa"

# Live values this snapshot is allowed to overwrite. C4b was authored in the
# repo, not on the site, so at deploy time live still holds the #138 bytes
# (3f825f...) -- without listing them here the first sync would be refused and
# the only way through would be force=1, which disarms the drift lock entirely.
# After the first successful sync live holds BASELINE_SHA256 and re-runs are
# "unchanged". Prune entries once the deploy is confirmed on every environment.
#
# 4d5ea1... is the C4b snapshot: it is what live would hold on any environment
# that deployed C4b but never received the three site-side edits above. Keeping
# it listed lets those environments sync forward; on team.ecentric.vn live is
# already at BASELINE_SHA256, so the first sync there returns "unchanged".
SUPERSEDES_SHA256 = (
    "3f825f4e4761a69d1cdb6033eeabbd1b8b23476c2fad33d9226b137c124a4454",  # #138
    "4d5ea138c4674b114df4451289d138ad80a9e512a37d705819b975dec13ef361",  # C4b (#64)
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
def sync_approval_inbox_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /approval page."), frappe.PermissionError)
    return sync()
