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
#   3. ec-resubmit-repoll-v1 (previous commit): ensureButton() returned without
#      re-arming its 3s poll once the Resubmit button existed, so after a
#      resubmit flipped status to "Can sua" the stale button stayed on screen
#      next to the banner's "Sua & Submit lai" -- the "2 nut resubmit" report.
#      It now keeps polling, and restores the Submit-on-GBS button it hid.
#   4. ec-resubmit-merge-v1 (this commit): the two stages of the resubmit flow
#      rendered two DIFFERENT call-to-actions -- stage 1 (Approved + GBS
#      Rejected) injected a small orange "Resubmit" button at the BOTTOM next to
#      "Check Status", stage 2 ("Can sua") showed "Sua & Submit lai" in a yellow
#      banner at the TOP. Same flow, same destination (/gbs-so-form-v2?edit=...),
#      two names in two places; reported as "2 nut resubmit 1 duoi 1 tren khong
#      dong bo". Stage 1 now renders #ec-gbs-resubmit-banner at the top of
#      #content, styled to match #ec-can-sua-banner and carrying the same
#      "Sua & Submit lai" label, so the page does not visibly change shape as the
#      doc moves from one stage to the next. The insert path also re-arms the 3s
#      poll -- ec-resubmit-repoll-v1 only re-armed on the "already exists" branch,
#      which was unreachable because the insert path fell off the end of the
#      function, so the poll died after the very first insert.
#   5. ec-cansua-meta-v1 (this commit): the "Can sua" banner's meta line rendered
#      "Yeu cau boi - . - . Lan thu 0" for every doc that reached "Can sua" by way
#      of a GBS/boxme rejection. Two distinct routes land on that status: the
#      Finance send-back bumps `revision_count` and writes an approval_history
#      event 'send_back', while GBS reject + the user pressing "Sua & Submit lai"
#      bumps `resubmit_count` and writes 'resubmit_after_gbs_reject'. The banner
#      only ever scanned for 'send_back', so on the second route it found nothing
#      and fell back to its em-dash placeholders with a zero counter (live at the
#      time: GBS-SO-2026-07-22-00002, GBS-SO-2026-07-24-00004,
#      GBS-SO-2026-07-31-00016, GBS-PO-2026-07-09-00004). It now takes the NEWEST
#      of the two event kinds -- a doc can have travelled both roads -- reads
#      `resubmit_count` on the GBS route, and trims the microseconds off the
#      timestamp. Wording branches too: on the GBS route the person in `by` did
#      not request the change, GBS did, so it reads "GBS tu choi . Mo sua boi X"
#      instead of "Yeu cau boi X". Display-only; no stored value changed, so every
#      existing doc renders correctly with no backfill.
# upsert_web_page REFUSES to write when live hashes to none of the accepted
# values, so a repo snapshot can never silently revert a live edit. Deliberate
# update = edit main_section.html, bump this constant, and move the value it
# replaced into SUPERSEDES_SHA256 -- all in the same commit.
BASELINE_SHA256 = "52028d811c5cf18f705c062c8cc020f0ce16f5f0a2cdc47d63f3ef82d17504cf"

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
    # pre-merge-v1 bytes: what live held after ec-resubmit-repoll-v1 was applied
    # on the site (2026-08-03 16:20). team.ecentric.vn has since been written
    # forward to BASELINE_SHA256, so the first sync there returns "unchanged".
    "78298a9ec4ca4420b608625788ee30713c9ff222ffd2177a17df7bc14e5a81fa",  # repoll-v1
    # pre-cansua-meta-v1 bytes: what live held after ec-resubmit-merge-v1 was
    # written to the site (2026-08-03). team.ecentric.vn has since been written
    # forward to BASELINE_SHA256, so the first sync there returns "unchanged".
    "ef66131a5dded4e48cbe00e9235c9859a85b449135bc195bffc2b5f4dfaa8ab5",  # merge-v1
    # pre-mso-feedback-1 bytes: ban repo truoc round feedback MSO 1 (2026-08-04).
    # Round do sua rieng phan MSO cua trang duyet: bo dong Channel, doi nhan
    # GMV -> NMV (gia tri luu '% GMV' GIU NGUYEN vi ec_mso_before_save so sanh
    # bang chuoi do), tach % ra cot rieng trong bang Tai chinh, bubble chu cai
    # dau cho danh sach nguoi duyet, va them khoi #ec-mso-thread (tep dinh kem +
    # trao doi). Live team.ecentric.vn da duoc ghi thang len BASELINE_SHA256
    # cung ngay nen sync dau tien o do tra ve "unchanged".
    "4ed7fbdaf76a04ec440705e3f6f051205ff66347d93999faf2663a70dfb37d61",  # pre-mso-fb-1
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
