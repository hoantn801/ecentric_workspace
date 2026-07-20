# Copyright (c) 2026, eCentric and contributors
"""Static serving for legacy Web Pages (Smoothness Stabilization, part D).

MEASURED root cause of inconsistent navigation: Web Pages with
dynamic_template=1 are served `Cache-Control: no-store,...` (browser may not
reuse anything -- every click is a full re-download), while dynamic_template=0
pages get Frappe's website cache + `private,max-age=300,
stale-while-revalidate=10800` (x-from-cache) -- the exact serving path the 28
approval pages and /docs/gbs-flow already use in production.

All 13 legacy page sources are PROVEN Jinja-free (0 `{{`/`{%` occurrences,
test-enforced): identical HTML for every user; all personalized/business data
loads client-side through authenticated APIs. Flipping dynamic_template=0 is
therefore safe: PRIVATE browser caching + Frappe's shared server-side page
cache of user-invariant HTML. No public/shared proxy caching is introduced.

Kill switch: site_config `ec_legacy_static_serving_disabled: 1` -> no-op."""
import frappe

JINJA_TOKENS = ("{{", "{%")


def ensure_static_serving(page_name, html):
    """Called by each legacy page_sync after upsert. Refuses to flip a page
    whose CURRENT html carries Jinja tags (defense in depth on top of tests)."""
    try:
        if frappe.conf.get("ec_legacy_static_serving_disabled"):
            return {"static_serving": "disabled"}
        for tok in JINJA_TOKENS:
            if tok in html:
                return {"static_serving": "skipped: jinja token %r present" % tok}
        if frappe.db.get_value("Web Page", page_name, "dynamic_template"):
            frappe.db.set_value("Web Page", page_name, "dynamic_template", 0)
            return {"static_serving": "enabled (dynamic_template -> 0)"}
        return {"static_serving": "already static"}
    except Exception:
        # fail-open to current behavior; never break a sync over serving mode
        return {"static_serving": "error (left unchanged)"}
