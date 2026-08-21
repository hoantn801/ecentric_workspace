# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for /viec-cua-toi -- the full-page view of the action feed
that until now existed only inside the header inbox drawer.

WHY A PAGE AND NOT JUST THE DRAWER
  On a phone the drawer covers the screen it floats over, cannot be linked to,
  cannot be shared, and has no back button. Everything it shows is already a
  LINK to a destination page, so a page is the honest shape for it. The drawer
  stays on desktop where the overlay costs nothing.

NO NEW SURFACE, NO NEW LOGIC
  The page calls the EXISTING session-scoped endpoint
  action_center.api.get_action_items -- the same classification, ordering and
  cursor pagination the homepage widget and the drawer already use. No item is
  actionable here: every row is an <a> to the `action_url` the server built.
  Nothing on this page can mutate a request, so no new permission is exposed.

BYTES OWNED BY THE REPO
  Same deal as hr/pages/install_guide: this page is new, has no live history to
  preserve, so a plain upsert is correct and there is no drift lock. Do not
  hand-edit it in Desk -- edit main_section.html and re-run the sync.

PUBLISHED BUT NOT PUBLIC
  publish=1 makes the route resolve; the DATA behind it is session-scoped and
  the endpoint returns 401 for Guest. The page's own JS redirects an
  unauthenticated visitor to /login (same guard the /ec-hr pages use).
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "viec-cua-toi"
NAME = "viec-cua-toi"
TITLE = "Việc của tôi"


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
def sync_my_work_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /viec-cua-toi page."),
                     frappe.PermissionError)
    return sync()
