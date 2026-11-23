# Copyright (c) 2026, eCentric and contributors
"""Idempotent Web Page sync cho /approvals/adhoc-approval (khuon chuan cua moi form) - co khoa lech
(drift lock #144) ngay tu dau: trang chua ton tai thi tao; da ton tai ma live khac ban repo (ai sua
tay tren site) thi TU CHOI ghi."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/adhoc-approval"
NAME = "adhoc-approval"
TITLE = "Phê duyệt đột xuất"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "ui", "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 cua HTML (da compose) ma commit nay ship. Sua HTML = bump gia tri nay + chuyen gia tri cu
# vao SUPERSEDES_SHA256 trong CUNG commit (tools/ci/check.py in gia tri dung).
BASELINE_SHA256 = "0a11f15d8cdb0ab240941491f29bee395dc6126b83ba3de35d5c65337a855421"
SUPERSEDES_SHA256 = ("f6e49ed92ea1d8f63a3327296d35f68cf2885174de539ead0db783bca502036a", "ad79d2b27a980e0b2b4db6abd3575f24391f385e3b1f6f30e25dbd35a5494794", "feff18fc547871c795614bb1a54cb7bb8679c76a334987f411c74b208b449d3a")


def sync(html=None, force=0):
    """Guarded create-or-update (drift lock). force=1 chi bo khoa lech, khong ep publish."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html, publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256))
    if res.get("action") != "refused" and res.get("name") \
            and frappe.db.exists("Web Page", res["name"]):
        res["recorded_sha"] = page_sync_util.record_live_sha(ROUTE, res["name"])
    return res


@frappe.whitelist(methods=["POST"])
def sync_adhoc_approval_page():
    """Admin-safe re-sync (System Manager only)."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Adhoc Approval page."),
                     frappe.PermissionError)
    return sync()
