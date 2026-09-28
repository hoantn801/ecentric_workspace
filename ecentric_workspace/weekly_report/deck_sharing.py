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
from ecentric_workspace.weekly_report.permissions import MANAGEMENT_DEPARTMENT


WTU = "Weekly Team Update"
TERMINAL_STATES = ("Submitted", "Reviewed")
RECENT_DAYS = 12

# Phong ban KHONG duoc chia se deck ra toan to chuc (2026-09-28).
#
# Link organization-scope mo duoc bang BAT KY tai khoan nao trong tenant, khong
# di qua quyen cua Frappe. Nen voi bao cao Management, chuyen deck sang link do
# chinh la vuot mat luat vua dat o `permissions.py`: danh sach an ban ghi di,
# nhung deck van mo duoc neu co URL.
#
# Lay hang so tu `permissions` chu khong go lai chuoi: hai noi dinh nghia roi
# mot noi doi ten phong ban la lo ra ngay, va khong ai biet.
PRIVATE_DEPARTMENTS = (MANAGEMENT_DEPARTMENT,)

# Kept as a name for readability; the rule itself lives in sharepoint so that
# the parser and the converter can never disagree about what a share link is.
_is_org_link = sharepoint.is_share_url


def _candidates(weeks, limit):
    """Only rows that still hold at least one UNCONVERTED url.

    Without this the query just returns the newest N rows -- which are usually
    already converted -- so a limited batch does nothing and older stuck decks
    are never reached. That is precisely how 43 .pptx decks stayed unshared.
    An org link contains neither marker below, so this selects exactly the work.
    """
    filters = {"status": ["in", TERMINAL_STATES], "slide_deck": ["!=", ""],
               "department": ["not in", list(PRIVATE_DEPARTMENTS)]}
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
    # Chan LAN HAI, ngay tai cho ghi.
    #
    # `_candidates` da loc roi, nhung bo loc do o mot ham khac va nguoi sau co
    # the goi `_convert_row` tu cho khac, hoac noi long bo loc de "chay lai cho
    # du". Cho duy nhat khong the di vong la ngay truoc khi tao link.
    if department in PRIVATE_DEPARTMENTS:
        stats["skipped_private"] = stats.get("skipped_private", 0) + 1
        return 0
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
    stats = {"scanned": 0, "converted": 0, "records": 0, "failed": 0,
             "skipped_private": 0, "errors": []}
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
