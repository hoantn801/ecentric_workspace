# Copyright (c) 2026, eCentric and contributors
"""p001_homepage_notification_bell: inject the Notification Center bell asset loader
into the homepage Web Page.

Deployment classification: DATA MIGRATION (listed in patches.txt; `bench migrate` runs
it). NO schema change. The homepage Web Page record is mutated.

Design (mirrors action_center.patches.p001_homepage_action_center):
  * The bell JS is an app-owned asset
    (ecentric_workspace/public/js/notification_center.js); the patch only inserts a small
    <script src=...> loader, so future bell changes ship as asset updates, not Web Page
    mutations.
  * ADDITIVE: the loader is inserted right after the Action Center widget loader anchor,
    so both homepage assets coexist. The Action Center markup is never modified.
  * Idempotent: if the bell marker is already present -> no-op.
  * Fail-loud: if the anchor (Action Center loader) is not present in any target field,
    the patch refuses to guess and raises (production may have drifted).
  * Uses doc.save(ignore_permissions=True) so Web Page on_update hooks run once.
"""

import frappe

WP_ROUTE = "home"
WP_NAME_KNOWN = "ecentric-workspace"

# Anchor: the Action Center loader's closing marker (inserted by action_center p001).
ANCHOR = "<!-- /ec-action-center-widget -->"

# Bell loader to insert immediately AFTER the anchor.
BELL_LOADER = (
    '<script id="ec-notification-center" '
    'src="/assets/ecentric_workspace/js/notification_center.js" '
    'defer></script>'
    '<!-- /ec-notification-center -->'
)
BELL_MARKER = '<script id="ec-notification-center"'

TARGET_FIELDS = ("main_section", "main_section_html")


def _resolve_wp_name():
    if frappe.db.exists("Web Page", WP_NAME_KNOWN):
        return WP_NAME_KNOWN
    rows = frappe.get_all("Web Page", filters={"route": WP_ROUTE},
                          fields=["name"], limit_page_length=1)
    if rows:
        return rows[0]["name"]
    raise frappe.ValidationError(
        "p001_homepage_notification_bell: cannot find homepage Web Page "
        "(tried name=" + WP_NAME_KNOWN + " and route=" + WP_ROUTE + ")")


def _classify(value):
    """'empty' | 'already_migrated' | 'has_anchor' | 'unknown'."""
    if not value:
        return "empty"
    if BELL_MARKER in value:
        return "already_migrated"
    if ANCHOR in value:
        return "has_anchor"
    return "unknown"


def _insert_bell(body):
    """Insert the bell loader right after the FIRST anchor occurrence. Fail-loud if the
    anchor is missing or the result loses/duplicates the markers."""
    if ANCHOR not in body:
        raise frappe.ValidationError(
            "p001_bell: Action Center anchor not found -- refusing to mutate.")
    if BELL_MARKER in body:
        return body  # already present
    idx = body.find(ANCHOR) + len(ANCHOR)
    out = body[:idx] + BELL_LOADER + body[idx:]
    if out.count(BELL_MARKER) != 1 or ANCHOR not in out:
        raise frappe.ValidationError(
            "p001_bell: post-insert sanity check failed -- aborting save.")
    return out


def execute():
    wp_name = _resolve_wp_name()
    wp = frappe.get_doc("Web Page", wp_name)

    states = {f: _classify(getattr(wp, f, None) or "") for f in TARGET_FIELDS}

    non_empty = {f: s for f, s in states.items() if s != "empty"}
    # Idempotent: every non-empty field already has the bell -> no-op.
    if non_empty and all(s == "already_migrated" for s in non_empty.values()):
        _log("p001_bell: already installed; no-op on " + wp_name)
        return

    anchor_fields = [f for f, s in states.items() if s == "has_anchor"]
    unknown_fields = [f for f, s in states.items() if s == "unknown"]

    if not anchor_fields:
        raise frappe.ValidationError(
            "p001_bell: no field carries the Action Center anchor. States=" + str(states)
            + ". Refusing to guess (run action_center p001 first).")
    if unknown_fields:
        raise frappe.ValidationError(
            "p001_bell: field(s) " + str(unknown_fields) + " are in an unknown state. "
            "Refusing to mutate. Full states=" + str(states))

    # If both fields carry the anchor they should be identical (observed prod state).
    if len(anchor_fields) > 1:
        first = getattr(wp, anchor_fields[0], None) or ""
        for f in anchor_fields[1:]:
            if (getattr(wp, f, None) or "") != first:
                raise frappe.ValidationError(
                    "p001_bell: anchor fields " + str(anchor_fields)
                    + " diverge -- refusing to mutate.")

    for f in anchor_fields:
        setattr(wp, f, _insert_bell(getattr(wp, f, None) or ""))

    wp.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Web Page")
    _log("p001_bell: installed bell loader on " + wp_name + " (fields=" + str(anchor_fields) + ")")


def _log(msg):
    try:
        frappe.logger("notification_center").info(msg)
    except Exception:
        pass
