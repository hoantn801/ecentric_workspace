# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the Approval Center hub Web Page (/approvals).

The hub was historically shipped by data patches p003-p005; Phase 1B gives it
the same SM-gated, migrate-free sync path every /approvals/<type> page already
has (mirrors leave/page_sync.py; shared ORM-only upsert)."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals"
NAME = "approval-center"
TITLE = "Approval Center"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# --- drift lock (#144, 2026-08-03) -------------------------------------------
# sha256 of the exact HTML this commit ships. Verified equal to the live
# main_section_html of /approvals (Web Page "approval-center") on
# team.ecentric.vn at the time of the commit, so the first sync after deploy
# returns "unchanged".
#
# This module was the ONE page_sync that lived directly under approval_center/
# instead of in a per-type subfolder, so the first sweep of #144 -- which walked
# approval_center/<type>/page_sync.py -- did not reach it. It was still calling
# upsert_web_page with both guards off, which made the Approval Center HUB the
# single most exposed page on the site: a stray POST to sync_approvals_page
# would have reverted /approvals to the repo snapshot and re-published it even
# if an operator had deliberately turned it off. The census test in
# shell/tests/test_legacy_pages_shell.py now globs this file too.
#
# Deliberate update = edit frontend/approvals.main_section.html, bump
# BASELINE_SHA256, move the value it replaced into SUPERSEDES_SHA256 -- all in
# the same commit.
BASELINE_SHA256 = "33d085101f325df205d1b8fd973f8e3e77b9a0d214cf6b86021e3450258ff9c0"
SUPERSEDES_SHA256 = (
    # baseline truoc p164 (o vuong bo goc chi co dau "?", bo chu "Huong dan").
    "9725820a47b9e9cff1b5fb9eaea5c393f78570a8f5133296951c2718c0b920d9",
    # baseline truoc p162 (loi vao huong dan chuyen xuong hang chan the).
    "7152df6588aa2449d047608b495da579cbd013bc77a8205f90ac0a9294c991f7",
    # baseline truoc p161 (icon "?" dan toi bai huong dan cua tung loai yeu cau).
    # Luc deploy, live VAN dang giu dung ban nay - khong khai o day thi khoa
    # chong troi tu choi ghi va patch chet, y het p134/p135.
    "8535d4deb3377399724dd855077f6ce9c359fadf1bbbecfa98c37d7fae0fdd2e",
    "243836867f03377a37c3542a52a10a9b287475c3574019b7d34d1ac3447eb392",
    "167633893d650b0d186e9eb4f638a8dc10478119d10610fb4e166d6088f0a191",   # baseline truoc p140
    # DO tren prod 04/09 14:40 (Web Page approval-center, modified 25/08 14:59): live khong bang
    # baseline cu -> khong them thi p140 bi khoa chong troi tu choi y het p134. Them gia tri DO
    # duoc, KHONG force=1 (bai hoc p135).
    "0a0283916444d73cbebb401f89146a9235e0a89268ba34dda68235120b055a81",
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
    else:
        res.update({"inspected_fields": [], "shim_fields_stripped": [], "has_legacy_shim": False})
    return res


@frappe.whitelist(methods=["POST"])
def sync_approvals_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Approval Center page."), frappe.PermissionError)
    return sync()



