# Copyright (c) 2026, eCentric and contributors
"""Force-sync the form pages whose LIVE copy is still on the old 3-tab layout.

p064/p065 re-synced every form page, but 20 of 26 were REFUSED by the #144 drift lock: the
live HTML does not hash to BASELINE_SHA256 nor to any SUPERSEDES entry (measured on
approvals/daily-target: live differs from the repo snapshot by ~12 characters, i.e. the page
was last written by a slightly different revision/stamper). The lock is doing its job -- but
the effect is that those pages keep serving the OLD UI forever: 'Yêu cầu của tôi' /
'Cần tôi duyệt' still show, and attachments still accept a single file.

Rather than blanket-forcing every page, this patch only overwrites a page that DEMONSTRABLY
still runs the old layout: the tab bar has more than the single 'Tạo yêu cầu' entry. Pages
already on the new layout are left untouched, whatever their drift. Idempotent: after the
write the marker matches and a re-run does nothing.

sync(force=1) drops ONLY the drift lock; publish state is still 'preserve', so a page an
operator un-published stays un-published."""
import re

import frappe

from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS

_MODULE = "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync"
# New layout ships exactly one tab; the old one carried my-requests / my-approvals / fulfillment.
_NEW_TABS = re.compile(r'var defs=\[\["create","[^"]+",true\]\];')
# Hub marker: tab memory helper added in the same batch.
_HUB_MARKER = "function withFrom("


def _live_html(route):
    name = frappe.db.get_value("Web Page", {"route": route}, "name")
    if not name:
        return None, None
    return name, (frappe.db.get_value("Web Page", name, "main_section") or "")


def execute():
    forced, skipped = [], []
    # 1) form pages
    seen = set()
    for definition in APPROVAL_DEFINITIONS.values():
        feature = getattr(definition, "feature", "") or ""
        if not feature or feature in seen:
            continue
        seen.add(feature)
        try:
            module = frappe.get_module(_MODULE % feature)
        except Exception:
            continue
        route = getattr(module, "ROUTE", None)
        if not route:
            continue
        name, html = _live_html(route)
        if not name:
            continue
        if _NEW_TABS.search(html or ""):
            skipped.append(feature)
            continue
        try:
            module.sync(force=1)
            forced.append(feature)
        except Exception:
            frappe.logger("approval_center").warning("p066: force sync failed for %s" % feature)

    # 2) hub page (same drift risk)
    try:
        from ecentric_workspace.approval_center.ui.all_requests import page_sync as hub
        name, html = _live_html(getattr(hub, "ROUTE", "approvals/all-requests"))
        if name and _HUB_MARKER not in (html or ""):
            hub.sync(force=1) if "force" in hub.sync.__code__.co_varnames else hub.sync()
            forced.append("all_requests(hub)")
    except Exception:
        frappe.logger("approval_center").warning("p066: hub force sync failed")

    frappe.logger("approval_center").info(
        "p066 forced=%s skipped(already new)=%s" % (forced, skipped))
