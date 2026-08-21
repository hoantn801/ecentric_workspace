# Copyright (c) 2026, eCentric and contributors
"""Idempotent Payment Request Web Page sync. Delegates to the shared ORM-only upsert
(no DuplicateEntryError) and strips any legacy Web Page shim via the shared
meta-driven helper. Publishes for UAT; never activates the catalog card.

S2B-B: the governed SCTS signing panel (esign/ui/payment_request_signing.html) is
appended to the main section exactly once, on the Payment Request page only. The whole
section is rebuilt from source on every sync, so installation is idempotent."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/payment-request"
NAME = "payment-request"
TITLE = "Payment Request"

# .../ecentric_workspace/approval_center/features/payment_request/infrastructure/page_sync.py
# -> 5 dirname = .../ecentric_workspace (REORG FIX: 3 dirname trỏ nhầm features/platform -> panel rỗng)
_PLATFORM_ESIGN_UI = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))),
    "platform", "esign", "ui")


def _esign_panel():
    """The governed SCTS signing panel appended to the PR detail page (S2B-B). Returns an
    empty string if the panel source is missing so a sync never fails on its absence."""
    try:
        with open(os.path.join(_PLATFORM_ESIGN_UI, "payment_request_signing.html"),
                  encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _esign_editor_panel():
    """The bundled PDF placement editor, appended once. coords.js is loaded LOCALLY (served
    from /assets/ecentric_workspace/) BEFORE the editor so window.ECoords exists; PDF.js is
    loaded locally by the editor itself. Returns '' if the source is missing so a sync never
    fails on its absence. EC_PPH_CONFIG is resolved by the editor from the backend."""
    try:
        with open(os.path.join(_PLATFORM_ESIGN_UI, "pdf_placement_editor.html"),
                  encoding="utf-8") as fh:
            editor = fh.read()
    except OSError:
        return ""
    coords = ('<script id="ec-pph-coords" '
              'src="/assets/ecentric_workspace/esign/coords.js"></script>')
    return coords + "\n" + editor


def _esign_requester_panel():
    """The requester pre-approval Prepare/Lock entry point, appended once. Visibility + status
    are decided by the governed backend readiness; the actions are local (no SCTS/DSR). Returns
    '' if the source is missing so a sync never fails on its absence."""
    try:
        with open(os.path.join(_PLATFORM_ESIGN_UI, "requester_signing_panel.html"),
                  encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _document_signing_section():
    """Phase A2 unified 'Tai lieu & ky so' section. Consumes the deployed A1/B1 read endpoints;
    replaces the requester raw signing panel + inline placement editor for the document-setup
    stage. Returns '' if the source is missing so a sync never fails on its absence."""
    try:
        with open(os.path.join(_PLATFORM_ESIGN_UI, "document_signing_section.html"),
                  encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "ui", "main_section.html"),
              encoding="utf-8") as fh:
        main = fh.read()
    # Whole section is rebuilt from source on every sync, so appending each panel exactly
    # once is idempotent by construction.
    # Shell-v1 main is preserved verbatim. The approver signing panel is injected inside a
    # DEFAULT-HIDDEN wrapper (ec-approver-wrap): the unified section reveals it from the
    # server-computed A1 state (can_classify), so a requester never sees a flash of the raw
    # SCTS block, while an actual approver still gets it. The requester raw panel + inline
    # editor are replaced by the unified section (+ drawer shell); Phase C re-introduces a
    # governed editor inside the drawer.
    return (main + "\n"
            + '<div id="ec-approver-wrap" style="display:none">\n'
            + _esign_panel()
            + '\n</div>\n'
            + _document_signing_section())

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
BASELINE_SHA256 = "2915800cd5728d45414833dfcae5574fff42b12dadea18468974d7b23de4278a"
SUPERSEDES_SHA256 = (
    "df5e328b9a4d842f63a6941c5416877b36df47bc80b32e4caa4720fb8530e52c",   # compose trước fix header-summary
    "9ce2d2e5f38b6e897daf5c8092bf4b561ad1ba1ed6b71aa96bba9ad98be9324c",   # compose trước fix delete-race (raw)
    # Điểm bất động sau server-side write: upsert ghi compose repo -> Frappe sanitize +
    # strip_legacy_shims biến đổi -> live luôn ổn định ở sha này (quan sát live 2026-08-21,
    # 2 lần sync liên tiếp cùng giá trị). Mọi resync sau so live với sha này.
    "c3483243b11defa236ad778ee123769867adfa6b285d704bd38e9ad933cc2b0c",
    "61526b3fb36c365c33ef9bebf0881f17a332c5c0c7cdd7ce0ae32942d46191ae",   # baseline trước fix path (compose thiếu panel do bug reorg)
    "402a09e9930947a9700d50c95ca5a7d078ead062edbe3a18e0af841eaf67c116",   # live sau lần resync 2026-08-21 (panel esign rỗng)
    "b143bbcf4adc1f7f197376785b9d0e036835f3807381342c7ab72675ebbc828e",
    "d8f7d3572013ea4ec4f4b2c2997659a229b18979576cc9e9f939de8fc00ed68a",
    "77a9a462aef1ab9e353784518aa880491fac5a29a53c0c8564e5309ab58c76c4",
)


def sync(html=None, force=0):
    """Guarded sync (#144).

    publish="preserve" -- never re-publishes a page an operator un-published;
                          a page that does not exist yet is created published.
    expect_sha         -- refuses (writes nothing) when live has drifted away
                          from the snapshot this commit ships.
    force=1            -- drops ONLY the drift lock; it never force-publishes.
    """
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    if res.get("action") != "refused" and res.get("name") \
            and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
        res["recorded_sha"] = page_sync_util.record_live_sha(ROUTE, res["name"])
    return res


@frappe.whitelist(methods=["POST"])
def sync_payment_request_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Payment Request page."), frappe.PermissionError)
    return sync()
