# Copyright (c) 2026, eCentric and contributors
"""p002_retire_homepage_bell_loader: remove the homepage-only Notification Center
bell <script> loader that p001 inserted into the homepage Web Page record.

Why: the Notification Center asset is now loaded GLOBALLY for every website page via
the `web_include_js` hook (hooks.py). The per-homepage <script> that p001 injected is
therefore redundant; left in place it would load the asset TWICE on /home (once from
the Web Page record, once from web_include_js). We retire it so /home -- like every
other page -- loads the asset exactly once. (The single-install guard in the asset is
defence-in-depth, NOT the de-duplication mechanism.)

Deployment classification: DATA MIGRATION (listed in patches.txt; one-time
`bench migrate` runs it). NO schema change. Only the homepage Web Page record is
mutated, and ONLY the Notification Center loader block is removed.

Design (mirrors p001):
  * Removes exactly the block p001 inserted: the
        <script id="ec-notification-center" ...></script><!-- /ec-notification-center -->
    loader. The Action Center widget markup and any other content are untouched.
  * Idempotent: if the bell marker is absent -> no-op (safe to re-run / safe if p001
    never ran on this site).
  * Fail-safe sanity: after removal the bell marker must be gone and the Action Center
    anchor must still be present and unchanged in count.
  * Uses doc.save(ignore_permissions=True) so Web Page on_update hooks run once.
"""

import re

import frappe

WP_ROUTE = "home"
WP_NAME_KNOWN = "ecentric-workspace"

# Markers owned by notification_center p001.
BELL_MARKER = '<script id="ec-notification-center"'
BELL_CLOSE_COMMENT = "<!-- /ec-notification-center -->"
# Action Center anchor that must NEVER be touched by this patch.
AC_ANCHOR = "<!-- /ec-action-center-widget -->"

TARGET_FIELDS = ("main_section", "main_section_html")

# Remove the NC <script ...></script> plus an optional trailing close comment.
# Non-greedy to the first </script>; tolerant of attribute/whitespace variance.
_REMOVE_RE = re.compile(
    r'<script id="ec-notification-center".*?</script>\s*(?:<!-- /ec-notification-center -->)?',
    re.DOTALL,
)


def _resolve_wp_name():
    if frappe.db.exists("Web Page", WP_NAME_KNOWN):
        return WP_NAME_KNOWN
    rows = frappe.get_all("Web Page", filters={"route": WP_ROUTE},
                          fields=["name"], limit_page_length=1)
    if rows:
        return rows[0]["name"]
    # Nothing to clean (no homepage Web Page on this site) -> treat as no-op.
    return None


def _strip(body):
    """Return body with the NC loader block removed (idempotent)."""
    if BELL_MARKER not in body:
        return body, False
    ac_before = body.count(AC_ANCHOR)
    out = _REMOVE_RE.sub("", body)
    if BELL_MARKER in out:
        raise frappe.ValidationError(
            "p002_retire_bell: NC loader still present after strip -- aborting.")
    if out.count(AC_ANCHOR) != ac_before:
        raise frappe.ValidationError(
            "p002_retire_bell: Action Center anchor count changed -- aborting.")
    return out, True


def execute():
    wp_name = _resolve_wp_name()
    if not wp_name:
        _log("p002_retire_bell: no homepage Web Page; no-op")
        return
    wp = frappe.get_doc("Web Page", wp_name)

    changed_fields = []
    for f in TARGET_FIELDS:
        cur = getattr(wp, f, None) or ""
        new, changed = _strip(cur)
        if changed:
            setattr(wp, f, new)
            changed_fields.append(f)

    if not changed_fields:
        _log("p002_retire_bell: bell loader already absent; no-op on " + wp_name)
        return

    wp.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Web Page")
    _log("p002_retire_bell: removed homepage bell loader on " + wp_name
         + " (fields=" + str(changed_fields) + ")")


def _log(msg):
    try:
        frappe.logger("notification_center").info(msg)
    except Exception:
        pass
