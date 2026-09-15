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
BASELINE_SHA256 = "eba729dabca9899317bf859f9badb18f8be75979d737c2af1ba0ed34592670c9"
SUPERSEDES_SHA256 = (
    "f1b7d169efb96aacddebff13e273d2b1d75663c734dc5194a04404558047ddd6",  # ban dang chay tren main truoc dot nay (cap Bo qua hien ten nguoi duyet)
    "589e1e9a38cd1941fea31c93c2c175e02efe9d63bb46e088f02ea8c940166cb4",  # ban dang chay tren main truoc dot nay (bo doctype/docname khi upload)
    "44effd3a1990cc2c8635469961d0981d9eff2b73e1b09f138978b66f7df1ce2b",  # superseded by 589e1e9a38cd (doReassign: refreshDetail khi form khong co applyDetail)
    "043f7b438de929a25e08cf2ab880a031a623cc662cf59fb7158c03c554b0858d",  # ban THAT dang chay tren production truoc dot nay (07/09)
    "ca1260d46cb2d5346716a740648defa64e560ee87561ff20af6703a10818f422",  # superseded by 44effd3a1990 (nut Chuyen nguoi xu ly + hoi lai khi quan tri nhan viec)
    "9edab6d743c95a8fa61a6970d20a724bbd4543d7130d5c672f1d73758362d1f3",  # superseded by ca1260d46cb2 (upload permission fix)
    "6716c3a63bcdf8f82edadc1205f442c292eb9937c31c321a37fe7db176becf27",  # superseded by 9edab6d743c9 (upload errors + brand list + layout)
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
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    if res.get("action") != "refused" and res.get("name") \
            and frappe.db.exists("Web Page", res["name"]):
        # Ghi lai sha SAU khi may chu xu ly (sanitize + strip shim) de lan sync sau nhan ra
        # chinh ban ghi cua minh. Khong co dong nay thi moi lan sua giao dien deu phai chep
        # tay sha live vao SUPERSEDES - dung cai da lam p152 refused ca 5 trang (07/09).
        res["recorded_sha"] = page_sync_util.record_live_sha(ROUTE, res["name"])
    return res


@frappe.whitelist(methods=["POST"])
def sync_document_request_page():
    """Admin-safe re-sync (System Manager only). Never publishes the catalog card."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Document Request page."), frappe.PermissionError)
    return sync()
