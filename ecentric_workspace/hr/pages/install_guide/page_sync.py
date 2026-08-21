# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for /ec-hr/huong-dan-cai-app -- the "cài app lên điện thoại"
guide shown to every employee.

WHY THIS ONE SHIPS ITS BYTES FROM THE REPO (unlike its /ec-hr siblings)
  Attendance / Leave / Salary carry live business logic that predates the repo,
  so hr/pages/shell_boundary.py governs a TRANSFORM of their live bytes and
  proves the business content is untouched. This page has no business content
  at all -- it is static instructions -- so the repo owns the whole file and a
  plain upsert is both simpler and safer. Editing the guide = edit
  main_section.html, re-run the sync.

  Consequence: there is no drift lock (`expect_sha`). If an operator edits this
  page live, the next sync overwrites it. That is the intended direction for a
  document whose source of truth is the repo; do NOT hand-edit it in Desk.

SHELL ZONES
  main_section.html already carries both canonical shell zones rendered from
  shell/nav.py, and hr/pages/install_guide is registered in
  shell.fallback.page_route_map(), so `python -m ecentric_workspace.shell.fallback`
  regenerates this page's sidebar together with every other migrated page. The
  page must never be edited so that it loses `data-ec-shell="1"` or the mount.

PERMISSION
  publish=1: the guide is deliberately readable without a session, so a new
  hire can follow it BEFORE their first login. It contains no business data --
  only public instructions and the public app icon.
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "ec-hr/huong-dan-cai-app"
NAME = "huong-dan-cai-app"
TITLE = "Cài app lên điện thoại"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html, publish=1)
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
    return res


@frappe.whitelist(methods=["POST"])
def sync_hr_install_guide_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the install guide page."),
                     frappe.PermissionError)
    return sync()
