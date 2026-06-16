# Copyright (c) 2026, eCentric and contributors
"""p001_homepage_action_center: swap legacy ec-home-todo-widget for an
asset-loader script tag on the homepage Web Page.

Deployment classification: DATA MIGRATION (lives in patches.txt). Frappe
Cloud `bench migrate` runs this. NO schema change. The Web Page record is
mutated; the rollback source is the Web Page snapshot taken on 2026-06-16:
    C:\\dev\\erp-inspection\\snapshots\\action_center_v2_20260616_164850\\
        01_wp_ecentric_workspace_full.json

Hardening (vs initial commit):
  - Widget JS is now an app-owned asset
    (ecentric_workspace/public/js/action_center_widget.js). The patch only
    inserts a small <script src=...> loader; future widget changes ship as
    asset updates, not Web Page mutations.
  - Defensive field handling: the patch detects which of `main_section` and
    `main_section_html` carries the legacy markers and updates only the
    fields that need it. If the two fields drift in an unexpected way,
    the patch refuses to mutate (fail-loud).
  - Uses doc.save(ignore_permissions=True) instead of multiple set_value
    calls so the standard Web Page on_update hooks run once with the new
    content.
"""

import frappe


WP_ROUTE = "home"
WP_NAME_KNOWN = "ecentric-workspace"  # 2026-06-16 snapshot

OLD_TITLE = '<div class="panel-title">Chờ phê duyệt'
NEW_TITLE = '<div class="panel-title">Việc cần làm'

OLD_WIDGET_START = '<script id="ec-home-todo-widget">'
OLD_WIDGET_END   = '</script><!-- /ec-home-todo-widget -->'

# Asset loader replaces the entire legacy script block.
NEW_WIDGET_LOADER = (
    '<script id="ec-action-center-widget" '
    'src="/assets/ecentric_workspace/js/action_center_widget.js" '
    'defer></script>'
    '<!-- /ec-action-center-widget -->'
)

# Marker we use to recognise the patch has already been applied.
NEW_WIDGET_MARKER = '<script id="ec-action-center-widget"'


# Fields that may carry the homepage HTML on the Web Page record.
TARGET_FIELDS = ("main_section", "main_section_html")


def _resolve_wp_name():
    """Find the homepage Web Page. Prefer known name, fall back to route."""
    if frappe.db.exists("Web Page", WP_NAME_KNOWN):
        return WP_NAME_KNOWN
    rows = frappe.get_all(
        "Web Page", filters={"route": WP_ROUTE},
        fields=["name"], limit_page_length=1,
    )
    if rows:
        return rows[0]["name"]
    raise frappe.ValidationError(
        "p001_homepage_action_center: cannot find Web Page "
        "(tried name=" + WP_NAME_KNOWN + " and route=" + WP_ROUTE + ")"
    )


def _transform(body):
    """Run the two surgical replacements. Return new body string.

    Raises ValidationError if required markers are missing.
    """
    missing = []
    if OLD_TITLE not in body:
        missing.append("OLD_TITLE")
    if OLD_WIDGET_START not in body:
        missing.append("OLD_WIDGET_START")
    if OLD_WIDGET_END not in body:
        missing.append("OLD_WIDGET_END")
    if missing:
        raise frappe.ValidationError(
            "p001: required OLD markers not found: " + ", ".join(missing)
            + ". Refusing to mutate (production may have drifted)."
        )

    out = body.replace(OLD_TITLE, NEW_TITLE, 1)

    s = out.find(OLD_WIDGET_START)
    e = out.find(OLD_WIDGET_END, s)
    if s < 0 or e < 0:
        raise frappe.ValidationError(
            "p001: widget markers not found in expected order after title "
            "replace -- refusing to mutate.")
    e_full = e + len(OLD_WIDGET_END)
    out = out[:s] + NEW_WIDGET_LOADER + out[e_full:]

    # Post-substitution sanity.
    if (NEW_WIDGET_MARKER not in out
            or OLD_WIDGET_START in out
            or OLD_WIDGET_END in out):
        raise frappe.ValidationError(
            "p001: post-substitution sanity check failed -- aborting save.")
    return out


def _field_classify(value):
    """Categorise a field's current content.

    Returns one of: 'empty', 'already_migrated', 'legacy', 'unknown'.
    """
    if not value:
        return "empty"
    if NEW_WIDGET_MARKER in value:
        return "already_migrated"
    has_old = (OLD_TITLE in value
               and OLD_WIDGET_START in value
               and OLD_WIDGET_END in value)
    if has_old:
        return "legacy"
    return "unknown"


def execute():
    wp_name = _resolve_wp_name()
    wp = frappe.get_doc("Web Page", wp_name)

    states = {f: _field_classify(getattr(wp, f, None) or "") for f in TARGET_FIELDS}

    # Idempotent: if ALL non-empty fields are already migrated -> no-op.
    non_empty = {f: s for f, s in states.items() if s != "empty"}
    if non_empty and all(s == "already_migrated" for s in non_empty.values()):
        try:
            frappe.logger("action_center").info(
                "p001: already migrated; no-op on Web Page " + wp_name)
        except Exception:
            pass
        return

    # Identify fields that need transforming.
    legacy_fields = [f for f, s in states.items() if s == "legacy"]
    unknown_fields = [f for f, s in states.items() if s == "unknown"]

    if not legacy_fields:
        # No field has the OLD markers -> nothing safe to transform.
        raise frappe.ValidationError(
            "p001: no field carries the legacy widget. Field states = "
            + str(states) + ". Refusing to guess.")

    if unknown_fields:
        # A non-legacy non-migrated field is in an unexpected state.
        raise frappe.ValidationError(
            "p001: Web Page field(s) " + str(unknown_fields)
            + " are in an unknown state (not empty, not migrated, not "
            "matching legacy markers). Refusing to mutate. Full states = "
            + str(states))

    # Cross-check: if both fields are legacy, they should be identical (the
    # observed production state). Diverging legacy content suggests upstream
    # tampering we must not blindly overwrite.
    legacy_values = {f: (getattr(wp, f, None) or "") for f in legacy_fields}
    if len(legacy_fields) > 1:
        first_value = legacy_values[legacy_fields[0]]
        for f in legacy_fields[1:]:
            if legacy_values[f] != first_value:
                raise frappe.ValidationError(
                    "p001: legacy fields " + str(legacy_fields)
                    + " diverge -- refusing to mutate.")

    # Transform each legacy field individually.
    new_values = {f: _transform(legacy_values[f]) for f in legacy_fields}

    # If there is an 'already_migrated' field alongside legacy ones, keep it
    # as-is (it's already where we want to land).
    for f, new_val in new_values.items():
        setattr(wp, f, new_val)

    wp.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Web Page")
    try:
        frappe.logger("action_center").info(
            "p001: migrated Web Page " + wp_name + " (fields=" + str(legacy_fields)
            + ") to Action Center asset loader")
    except Exception:
        pass
