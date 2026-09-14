# Copyright (c) 2026, eCentric and contributors
"""Share weekly decks with the whole organisation.

Decks live in the `operation` SharePoint site, which most leaders outside that
site cannot open. Converting each deck URL into an organisation-scope share
link lets any signed-in tenant account view it (it is NOT public).

This replaces the `auto_convert_slides_org` Server Script, which matched only
`%/Shared%20Documents/%` and therefore never saw Office decks -- SharePoint
returns a `_layouts/Doc.aspx?...file=` URL for those. 43 .pptx decks from W34
onward had been silently unshared since 2026-07-31 as a result.

Public API:
  convert_pending(weeks=None, limit=25) -> dict
      weeks=None  -> recent submissions (rolling window), for the scheduler.
      weeks=[...] -> those week_labels only, for backfill.
      Idempotent: already-converted URLs are left alone.
"""

import frappe
from frappe.utils import add_days, nowdate

from ecentric_workspace.weekly_report import sharepoint


WTU = "Weekly Team Update"
TERMINAL_STATES = ("Submitted", "Reviewed")
RECENT_DAYS = 12

# A URL that already points at a share link rather than at the item itself.
ORG_MARKERS = ("/:b:/", "/:x:/", "/:p:/", "/:w:/", ":/s/")


def _is_org_link(url):
    for marker in ORG_MARKERS:
        if marker in url:
            return True
    return False


def _candidates(weeks, limit):
    """Only rows that still hold at least one UNCONVERTED url.

    Without this the query just returns the newest N rows -- which are usually
    already converted -- so a limited batch does nothing and older stuck decks
    are never reached. That is precisely how 43 .pptx decks stayed unshared.
    An org link contains neither marker below, so this selects exactly the work.
    """
    filters = {"status": ["in", TERMINAL_STATES], "slide_deck": ["!=", ""]}
    if weeks:
        filters["week_label"] = ["in", weeks]
    else:
        filters["submitted_at"] = [">", add_days(nowdate(), -RECENT_DAYS)]
    return frappe.get_all(
        WTU,
        filters=filters,
        or_filters=[
            ["slide_deck", "like", "%Shared%Documents%"],
            ["slide_deck", "like", "%layouts%"],
        ],
        fields=["name", "department", "slide_deck"],
        order_by="submitted_at desc",
        limit_page_length=limit,
    )


def _display_name(rel_path):
    """Kept as a #fragment so the UI shows a readable name instead of the
    share id. The browser strips the fragment before calling SharePoint."""
    name = rel_path.rsplit("/", 1)[-1]
    return name.replace("%", "%25").replace("#", "%23")


def _convert_row(row, token, stats):
    department = row.get("department")
    urls = [u.strip() for u in (row.get("slide_deck") or "").split("\n") if u.strip()]
    out = []
    changed = 0

    for url in urls:
        if _is_org_link(url):
            out.append(url)
            continue
        rel_path = sharepoint.rel_path_from_web_url(url, department)
        if not rel_path:
            out.append(url)
            stats["failed"] += 1
            stats["errors"].append("unparseable url: " + row["name"])
            continue
        try:
            link = sharepoint.create_org_link(rel_path, token)
        except Exception as exc:
            out.append(url)
            stats["failed"] += 1
            stats["errors"].append(row["name"] + ": " + str(exc)[:150])
            continue
        out.append(link + "#" + _display_name(rel_path))
        changed += 1

    if changed:
        doc = frappe.get_doc(WTU, row["name"])
        doc.slide_deck = "\n".join(out)
        doc.save(ignore_permissions=True)
    return changed


def convert_pending(weeks=None, limit=25):
    stats = {"scanned": 0, "converted": 0, "records": 0, "failed": 0, "errors": []}
    rows = _candidates(weeks, limit)
    stats["scanned"] = len(rows)
    if not rows:
        return stats

    token = sharepoint.get_app_token()
    for row in rows:
        try:
            changed = _convert_row(row, token, stats)
        except Exception as exc:
            # One bad record must not kill the batch.
            stats["failed"] += 1
            stats["errors"].append(row.get("name", "?") + " row: " + str(exc)[:150])
            continue
        if changed:
            stats["records"] += 1
            stats["converted"] += changed
    return stats
