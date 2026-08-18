# Copyright (c) 2026, eCentric and contributors
"""Versioned, idempotent AI Topup Web Page sync. Replaces reliance on the
run-once p006: a whitelisted admin-safe function + a versioned patch (p007) that
create/update the page from the current source HTML. Publishes the page for
controlled/direct UAT; NEVER activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/ai-topup"
NAME = "approval-center-ai-topup"
TITLE = "AI Topup"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "ai_topup", "ui", "main_section.html"), encoding="utf-8") as fh:
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
BASELINE_SHA256 = "674def069d7c1aa381c1ef8f4db0641bb9ab4decf3f59b6cccfb98247ad15a32"

# GiÃƒÆ’Ã‚Â¡ trÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¹ live mÃƒÆ’Ã‚Â  snapshot nÃƒÆ’Ã‚Â y Ãƒâ€žÃ¢â‚¬ËœÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Â£c phÃƒÆ’Ã‚Â©p ghi Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â¨.
#
# 1c56e03b... lÃƒÆ’Ã‚Â  bytes cÃƒÂ¡Ã‚Â»Ã‚Â§a d6d412c (GD2 C2 UAT fix), tÃƒÂ¡Ã‚Â»Ã‚Â©c lÃƒÆ’Ã‚Â  baseline Ãƒâ€žÃ‚ÂÃƒÆ’Ã…Â¡NG cho tÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºi khi
# PR #241 (b082c2a, ec-datepicker: thÃƒÆ’Ã‚Âªm data-ec-dp-range vÃƒÆ’Ã‚Â o form lÃƒÂ¡Ã‚Â»Ã‚Âc) sÃƒÂ¡Ã‚Â»Ã‚Â­a
# frontend/ai_topup.main_section.html mÃƒÆ’Ã‚Â  KHÃƒÆ’Ã¢â‚¬ÂNG bump hÃƒÂ¡Ã‚ÂºÃ‚Â±ng sÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ nÃƒÆ’Ã‚Â y. TÃƒÂ¡Ã‚Â»Ã‚Â« Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â³ BASELINE_SHA256
# khÃƒÆ’Ã‚Â´ng cÃƒÆ’Ã‚Â²n khÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºp HTML repo ship, nÃƒÆ’Ã‚Âªn sync ghi Ãƒâ€žÃ¢â‚¬ËœÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Â£c Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Âºng mÃƒÂ¡Ã‚Â»Ã¢â€žÂ¢t lÃƒÂ¡Ã‚ÂºÃ‚Â§n rÃƒÂ¡Ã‚Â»Ã¢â‚¬Å“i refused vÃƒâ€žÃ‚Â©nh viÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¦n.
# tools/ci/check.py (phÃƒÆ’Ã‚Â©p kiÃƒÂ¡Ã‚Â»Ã†â€™m `pagesync`) bÃƒÂ¡Ã‚ÂºÃ‚Â¯t Ãƒâ€žÃ¢â‚¬ËœÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Â£c sai lÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡ch Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â³.
#
# LiÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡t kÃƒÆ’Ã‚Âª ÃƒÂ¡Ã‚Â»Ã…Â¸ Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â¢y Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã†â€™ cÃƒÂ¡Ã‚ÂºÃ‚Â£ hai trÃƒÂ¡Ã‚ÂºÃ‚Â¡ng thÃƒÆ’Ã‚Â¡i live Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã‚Âu Ãƒâ€žÃ¢â‚¬Ëœi tiÃƒÂ¡Ã‚ÂºÃ‚Â¿p Ãƒâ€žÃ¢â‚¬ËœÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Â£c: mÃƒÆ’Ã‚Â´i trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Âng cÃƒÆ’Ã‚Â²n giÃƒÂ¡Ã‚Â»Ã‚Â¯ bytes
# d6d412c thÃƒÆ’Ã‚Â¬ sync tiÃƒÂ¡Ã‚ÂºÃ‚Â¿n lÃƒÆ’Ã‚Âªn, mÃƒÆ’Ã‚Â´i trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Âng Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â£ nhÃƒÂ¡Ã‚ÂºÃ‚Â­n bytes #241 thÃƒÆ’Ã‚Â¬ trÃƒÂ¡Ã‚ÂºÃ‚Â£ vÃƒÂ¡Ã‚Â»Ã‚Â "unchanged".
# BÃƒÂ¡Ã‚Â»Ã‚Â entry nÃƒÆ’Ã‚Â y khi Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â£ xÃƒÆ’Ã‚Â¡c nhÃƒÂ¡Ã‚ÂºÃ‚Â­n deploy trÃƒÆ’Ã‚Âªn mÃƒÂ¡Ã‚Â»Ã‚Âi mÃƒÆ’Ã‚Â´i trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Âng.
SUPERSEDES_SHA256 = (
    "2645973df8a3bcfad7c10b38e44119256e073144c6d4bfb5910a7ba2650e5457",  # superseded by 674def069d7c
    "1c56e03bccf777286e281dc39fafdd375610c2ebd14bb6c1978b467aa7fae802",
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
def sync_ai_topup_page():
    """Admin-safe re-sync (System Manager only). No manual Web Page edits needed."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the AI Topup page."), frappe.PermissionError)
    return sync()
