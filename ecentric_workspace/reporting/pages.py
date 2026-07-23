# Copyright (c) 2026, eCentric and contributors
"""Reporting pages (/weekly-update, /team-pulse) -> Shared Shell (`reporting`).

Both pages carry a STALE clone of the old Homepage sidebar + a tiny legacy
topbar (breadcrumb only, NO bell). Business asides (`wu-roadmap`,
`tp-ai-panel`), heavy Jinja (wu: ~97 tags) and all wu-*/tp-* scripts sit
OUTSIDE the [sidebar..topbar] window and are reassembled from the ORIGINAL
byte slices. The canonical topbar ADDS the page's first NC bell.
`?week=` deep links are untouched (query never affects zone anchors)."""
import frappe
from frappe import _

from ecentric_workspace.shell import boundary

PAGES = {
    "weekly-update": {"name": "báo-cáo-tuần",
                      "scripts": ("ec-csrf-fetch-patch", "wu-week-nav-js", "ec-chatbot-js")},
    "team-pulse": {"name": "team-pulse",
                   "scripts": ("ec-csrf-fetch-patch", "tp-company-summary-js", "ec-chatbot-js")},
}


def transform(ms, route):
    cfg = PAGES[route]
    for sid in cfg["scripts"]:
        if '<script id="%s"' % sid not in ms:
            raise ValueError("business script missing on %s: %s" % (route, sid))
    if ms.count('data-ec-notification-bell="1"') > 1:
        raise ValueError("unexpected extra bell on %s" % route)
    s0, s1, t0, t1 = boundary.find_window(ms)
    # business asides must NOT be inside the replaced window
    for biz in ("wu-roadmap", "tp-ai-panel"):
        i = ms.find(biz)
        if i != -1 and s0 <= i < t1:
            raise ValueError("business aside %s inside shell window on %s" % (biz, route))
    new = (ms[:s0] + boundary.mount_html("/" + route) + ms[s1:t0]
           + boundary.topbar_html("/" + route) + ms[t1:])
    boundary.assert_post(new, route)
    for sid in cfg["scripts"]:
        if '<script id="%s"' % sid not in new:
            raise ValueError("business script lost on %s: %s" % (route, sid))
    return new


def _sync_one(route):
    name = PAGES[route]["name"]
    if not frappe.db.exists("Web Page", name):
        return {"route": route, "action": "skipped", "reason": "missing"}
    ms = frappe.db.get_value("Web Page", name, "main_section") or ""
    try:
        new = transform(ms, route)
    except ValueError as e:
        frappe.throw(_(str(e)))
    if new == ms:
        return {"route": route, "action": "unchanged"}
    doc = frappe.get_doc("Web Page", name)
    doc.main_section = new
    doc.main_section_html = new
    doc.save(ignore_permissions=True)
    return {"route": route, "action": "updated",
            "len_before": len(ms), "len_after": len(new)}


@frappe.whitelist(methods=["POST"])
def sync_reporting_pages():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync Reporting pages."), frappe.PermissionError)
    return [_sync_one(r) for r in PAGES]
