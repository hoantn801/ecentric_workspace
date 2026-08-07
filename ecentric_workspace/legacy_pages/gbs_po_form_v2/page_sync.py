# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the LEGACY /gbs-po-form-v2 Web Page.

This is the GBS Purchase Order creation/edit form. /form-po 301-redirects
here. Also the landing page for 'Sua & Submit lai' (?edit=<name>).

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

ROUTE = "gbs-po-form-v2"
NAME = "gbs-po-form-v2"
TITLE = "gbs-po-form-v2"  # exact live title -- required for the first sync to be "unchanged"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 of main_section.html as it ships in this commit == the live
# main_section_html at import time (bccf9fbded81630c3e3d23bcf94d1055e5c47d7fbed669bdb9ea6c27d62483db).
#
# upsert_web_page REFUSES to write (and changes nothing) when live hashes to
# none of the accepted values. This page has a history of being edited straight
# on the site, so without the lock a stray call to the endpoint below would
# silently revert those edits to whatever the repo happened to hold.
#
# Deliberate update = edit main_section.html, bump BASELINE_SHA256, and move the
# value it replaced into SUPERSEDES_SHA256 -- all in the same commit.
BASELINE_SHA256 = "9b09857c96014bf1fced44368d64f8e8e7f4f2dd27d102a0ba72f5293b661302"
SUPERSEDES_SHA256 = (
    # bytes truoc FIX 8 (2026-08-07): file dinh kem cua PO so EC chi len SharePoint
    # theo phien upload, Purchase Order chi luu ma phien -> trang /approval doc bang
    # File nen luon "Khong co file dinh kem". Sua: giu lai doi tuong File luc upload
    # va sau khi tao PO thi dinh kem NATIVE (/api/method/upload_file, is_private=1)
    # vao chinh PO, dung cach /mso-plan-form lam. Duong SharePoint giu nguyen.
    # Chi nhanh ecbuy goi ham nay; nhanh GBS khong doi hanh vi.
    "c835882aab6a9e8c64a29876c41f580f6cf07724c433ef6eb8396e8781717505",
    # bytes truoc khi doi widget "Muc uu tien" cua PO tu 3 nac sang 2 nac
    # (2026-08-04). Ban cu: Thap/TB/Cao = Low/Medium/High, mac dinh Medium.
    # Ban moi: Normal (xanh la) / Urgent (do), mac dinh Normal, gui dung chuoi
    # Normal/Urgent trong payload submit_gbs_po va resubmit_gbs_po. Field
    # priority cua GBS Purchase Order da duoc doi options bang Property Setter
    # (GBS Purchase Order-priority-options = "Normal\nUrgent"), va
    # sync_gbs_po_outgoing day gia tri nay sang boxme thanh
    # custom_approval_priority. Live team.ecentric.vn da duoc ghi thang len
    # BASELINE_SHA256 cung ngay nen sync dau tien o do tra ve "unchanged".
    "1644261f5858fc2b42068f70d5ab7b305147cc03f16214320d08efca37fdc904",  # pre-po-priority-2steps
    "6b018840a200452851c1d70f7be0f3cdb51d5d362cbd415745046223ca4d81bd",
    "4bab5c38fbb0789695858ac532342b9a3eaaad63b878667e8ce847f21f784982",
    "bccf9fbded81630c3e3d23bcf94d1055e5c47d7fbed669bdb9ea6c27d62483db",
    "314352e40235f532b64ad87f03a2d949d63c5f87d35e2ba6d00ae2542ad2e7d7",
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
def sync_gbs_po_form_v2_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /gbs-po-form-v2 page."), frappe.PermissionError)
    return sync()
