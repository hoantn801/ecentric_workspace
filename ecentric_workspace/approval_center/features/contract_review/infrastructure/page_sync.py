# Copyright (c) 2026, eCentric and contributors
"""Idempotent Contract Review Web Page sync (khuôn chuẩn của mọi form — see #144).
Trang MỚI nên chưa có drift lock: baseline sẽ được chốt ở lần sửa HTML đầu tiên
sau khi trang đã sống trên production."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/contract-review"
NAME = "contract-review"
TITLE = "Contract Review"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "ui", "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None, force=0):
    """Create-or-update the Web Page from source. Idempotent."""
    html = html if html is not None else _html()
    return page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html, publish="preserve")


@frappe.whitelist(methods=["POST"])
def sync_contract_review_page():
    """Admin-safe re-sync (System Manager only)."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the Contract Review page."), frappe.PermissionError)
    return sync()
