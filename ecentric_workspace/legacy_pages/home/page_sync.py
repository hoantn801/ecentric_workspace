# Copyright (c) 2026, eCentric and contributors
"""GUARDED sync for the HOMEPAGE Web Page (/ -> `ecentric-workspace`).

HOMEPAGE SYNC SAFETY HOTFIX (2026-07-21). The Daily Cockpit replacement UX
was REJECTED by the PO; production was manually restored to the approved
original Homepage (Jinja portal: legacy sidebar, KPI cards, Check-in,
Truy cập nhanh, Tin nội bộ, Việc cần làm/Action Center widget, Lịch,
Chính sách, chatbot). The restored live page is the CANONICAL baseline.

This module therefore performs ZERO writes until an approved canonical
baseline is pinned:

  BASELINE_SHA256 = None  ->  sync() returns {"action": "guarded"} and
                              NEVER touches the Web Page.

Re-baselining (separate approved phase): capture the restored `/` through
the UTF-8-safe authenticated browser export on the user's machine (the
sandbox cannot extract page bytes), commit it as main_section.html
verbatim (BOM-strip + MojibakeGuard + ms==msh proof), then pin
BASELINE_SHA256 to that file's sha256. Only then does sync() become a
reproduce-only restore tool for the approved baseline.

NOTE: the homepage keeps `dynamic_template=1` (live Jinja) -- it is
EXEMPT from legacy_pages.serving static-serving. Website Settings
home_page is never touched.
"""
import hashlib
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "home"
NAME = "ecentric-workspace"
TITLE = "eCentric Workspace"

#: sha256 of the APPROVED canonical baseline main_section.html. None means
#: "no approved repo baseline exists" -> sync is a guarded no-op.
BASELINE_SHA256 = None


def _baseline_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "main_section.html")


def sync(html=None):
    if BASELINE_SHA256 is None:
        # HARD GUARD: no approved baseline pinned -> zero reads of the page,
        # zero writes. Production homepage stays exactly as restored.
        return {
            "action": "guarded",
            "route": ROUTE,
            "name": NAME,
            "reason": "homepage is live-canonical; no approved repo baseline pinned "
                      "(BASELINE_SHA256 is None) -- sync performs zero writes",
        }

    # Phase B path (inactive until a baseline is pinned): reproduce-only.
    if html is None:
        with open(_baseline_path(), encoding="utf-8") as fh:
            html = fh.read()
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    if digest != BASELINE_SHA256:
        frappe.throw(_("Homepage baseline sha mismatch: refusing to sync "
                       "(expected %s, got %s)") % (BASELINE_SHA256, digest))
    return page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)


@frappe.whitelist(methods=["POST"])
def sync_home_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the homepage."), frappe.PermissionError)
    return sync()
