# Copyright (c) 2026, eCentric and contributors
"""p021_home_calendar_widget: inject the "Lich hom nay" calendar-widget asset loader into
the homepage Web Page.

Deployment classification: DATA MIGRATION (listed in patches.txt; `bench migrate` runs it,
which on Frappe Cloud happens on redeploy). NO schema change. The homepage Web Page record
is mutated.

Design (mirrors notification_center.patches.p001_homepage_notification_bell):
  * The widget JS is an app-owned asset
    (ecentric_workspace/public/js/pm_home_calendar.js); this patch inserts only a small
    <script src=...> loader, so future widget changes ship as asset updates, not Web Page
    mutations.
  * ADDITIVE + ANCHOR-FREE: the loader is APPENDED to the end of each non-empty target
    field. Ordering does not matter -- the widget finds the "Lich hom nay" panel and fills
    it at runtime -- so it does NOT depend on any other homepage marker existing (an earlier
    anchor-based version wrongly assumed the notification-center marker was present and
    aborted the whole migration).
  * Idempotent: if the loader marker is already present in a field -> that field is skipped.
  * Safe: the loader carries no Jinja tokens, and a <script> at the end of a page section is
    inert until the panel exists (findPanel returns null otherwise). Only raises if the
    homepage Web Page record itself cannot be found.
  * Uses doc.save(ignore_permissions=True) so Web Page on_update hooks run once.
"""

import frappe

WP_ROUTE = "home"
WP_NAME_KNOWN = "ecentric-workspace"

LOADER = (
    '<script id="ec-lich-hom-nay-loader" '
    'src="/assets/ecentric_workspace/js/pm_home_calendar.js" '
    'defer></script>'
    '<!-- /ec-lich-hom-nay-loader -->'
)
MARKER = '<script id="ec-lich-hom-nay-loader"'

TARGET_FIELDS = ("main_section", "main_section_html")


def _resolve_wp_name():
    if frappe.db.exists("Web Page", WP_NAME_KNOWN):
        return WP_NAME_KNOWN
    rows = frappe.get_all("Web Page", filters={"route": WP_ROUTE},
                          fields=["name"], limit_page_length=1)
    if rows:
        return rows[0]["name"]
    raise frappe.ValidationError(
        "p021_home_calendar_widget: cannot find homepage Web Page "
        "(tried name=" + WP_NAME_KNOWN + " and route=" + WP_ROUTE + ")")


def execute():
    wp_name = _resolve_wp_name()
    wp = frappe.get_doc("Web Page", wp_name)

    changed = []
    for f in TARGET_FIELDS:
        val = getattr(wp, f, None) or ""
        if not val:
            continue          # nothing to append to
        if MARKER in val:
            continue          # idempotent: already installed on this field
        setattr(wp, f, val + "\n" + LOADER)
        changed.append(f)

    if not changed:
        _log("p021_home_calendar_widget: no-op (already installed / empty) on " + wp_name)
        return

    wp.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Web Page")
    _log("p021_home_calendar_widget: appended loader on " + wp_name
         + " (fields=" + str(changed) + ")")


def _log(msg):
    try:
        frappe.logger("pm").info(msg)
    except Exception:
        pass
