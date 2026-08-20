# Copyright (c) 2026, eCentric and contributors
"""Action Center: homepage feed API.

Endpoint:
  POST /api/method/ecentric_workspace.action_center.api.get_action_items
  body: {} (no parameters)

Returns the current user's open ToDos, each resolved into a canonical
action item with `action_url` already built (no frontend URL building).

Permission scope:
  - Guest -> 401
  - Authenticated user -> only their own Open ToDos (allocated_to = session user)
  - The current user is read from the session; the client CANNOT pass a user.
  - No new DocType permissions are exposed.
"""

import frappe

from ecentric_workspace.action_center import feed as ac_feed
from ecentric_workspace.action_center import resolvers as ac_resolvers
from ecentric_workspace.action_center.resolvers import build_approval_url

#: how many of the user's own open requests the summary lists (counts are NOT
#: derived from this page -- see get_my_requests_summary)
_MY_REQ_LIMIT = 10


def _require_user():
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.response["http_status_code"] = 401
        return None
    return frappe.session.user


@frappe.whitelist(methods=["GET"])
def get_action_items(cursor=None, limit=None):
    """Canonical Action Center feed for the current user (session-scoped).

    Delegates ALL counting / classification / due derivation / terminal
    filtering / ordering / pagination to the shared feed service -- no logic
    is duplicated here. Backward-compatible envelope: success/count/items/
    counts/generated_at are unchanged for the existing homepage widget; the
    `total` / `returned` / `next_cursor` keys are additive (cursor pagination
    for the future full Action Center). `cursor`/`limit` are optional (the
    widget passes neither -> the first page of DEFAULT_LIMIT)."""
    user = _require_user()
    if not user:
        return {"success": False, "error": "Unauthorized", "count": 0, "items": [], "counts": {}}

    res = ac_feed.build_feed(user, cursor=cursor, limit=limit or ac_feed.DEFAULT_LIMIT)
    return {
        "success": True,
        "count": res["returned"],          # backward-compat: items on this page
        "items": res["items"],
        "counts": res["counts"],
        "source_counts": res["source_counts"],
        "total": res["total"],
        "returned": res["returned"],
        "next_cursor": res["next_cursor"],
        "generated_at": res["generated_at"],
    }


#: how many top items the header drawer shows before "Xem tất cả".
REMINDER_TOP_N = 8


@frappe.whitelist(methods=["GET"])
def get_reminder_summary(limit=None):
    """Header Reminder drawer feed (Phase 1b). DELEGATES to the shared
    build_feed -- no classification/counting logic is duplicated here.

    Returns the SAME feed result's total + counts + top prioritized items,
    plus a derived attention_count = overdue + act_now (the header badge).
    Session-scoped; the client may only page (limit), never pass a user."""
    user = _require_user()
    if not user:
        return {"success": False, "error": "Unauthorized",
                "total": 0, "attention_count": 0, "counts": {}, "items": []}

    n = limit or ac_feed.PREVIEW_N
    res = ac_feed.bucket_previews(user, preview_n=n)
    counts = res["counts"]
    attention_count = counts.get("overdue", 0) + counts.get("act_now", 0)
    return {
        "success": True,
        "total": res["total"],             # ALL open actions (badge on the widget)
        "attention_count": attention_count,  # overdue + act_now (header badge)
        "counts": counts,                  # full-feed bucket counts
        "source_counts": res["source_counts"],  # SAME per-source counts (no dup query)
        # PER-BUCKET previews (1b.1): each bucket independently populated from
        # the ONE classified feed -> a high-priority bucket never starves a
        # later one. bucket_has_more drives the per-bucket "Xem thêm N việc".
        "bucket_items": res["bucket_items"],
        "bucket_has_more": res["bucket_has_more"],
        "preview_n": res["preview_n"],
        "generated_at": res["generated_at"],
    }


@frappe.whitelist(methods=["GET"])
def get_reminder_bucket(bucket=None, cursor=None, limit=None):
    """Governed per-bucket pagination for the header drawer's 'Xem thêm N
    việc'. Delegates to the shared bucket_page (one classified feed; bounded
    scan; NEVER an unbounded ToDo fetch). Session-scoped; the client may pass
    only bucket/cursor/limit, never a user."""
    user = _require_user()
    if not user:
        return {"success": False, "error": "Unauthorized", "items": [], "count": 0}
    res = ac_feed.bucket_page(user, bucket, cursor=cursor,
                              limit=limit or ac_feed.DEFAULT_LIMIT)
    res["success"] = True
    return res


@frappe.whitelist(methods=["GET"])
def get_my_requests_summary():
    """The current user's OWN submitted engine requests still in progress.

    Smallest governed aggregate (2C.2 locked scope): read-only over EC
    Approval Request, requester = SESSION user (client cannot pass a user),
    status Pending / Information Required only.

    Counts are computed over ALL matching rows (frappe.db.count), independent of
    the display limit -- deriving them from the limited page under-reported for
    any user with more than `_MY_REQ_LIMIT` open requests.
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.response["http_status_code"] = 401
        return {"success": False, "error": "Unauthorized", "counts": {}, "items": []}

    user = frappe.session.user
    rows = frappe.get_all(
        "EC Approval Request",
        filters={"requested_by": user,
                 "approval_status": ["in", ["Pending", "Information Required"]]},
        fields=["name", "approval_type", "reference_doctype", "reference_name",
                "approval_status", "current_level", "submitted_at"],
        order_by="submitted_at desc", limit=_MY_REQ_LIMIT, ignore_permissions=True)

    # counts over the FULL set, not just the displayed page
    counts = {
        "pending": frappe.db.count("EC Approval Request",
                                   {"requested_by": user, "approval_status": "Pending"}),
        "information_required": frappe.db.count(
            "EC Approval Request",
            {"requested_by": user, "approval_status": "Information Required"}),
    }

    items = []
    for r in rows:
        st = (r.get("approval_status") or "").strip()
        # metadata-driven title: NEVER SELECT a hard-coded `title` column (that
        # raised MySQL 1054 per row on DocTypes without one, silently swallowed)
        title = ac_resolvers.resolve_title(r.get("reference_doctype"),
                                           r.get("reference_name"))
        items.append({
            "request": r["name"],
            "source_type": "approval",
            "source_id": (r.get("reference_doctype") or "") + "/" + (r.get("reference_name") or ""),
            "title": title or r.get("reference_name") or r["name"],
            "subtitle": (r.get("approval_type") or "") ,
            "status": st,
            "current_level": r.get("current_level"),
            "submitted_at": str(r.get("submitted_at") or ""),
            "action_url": build_approval_url(r.get("reference_doctype"), r.get("reference_name")),
        })
    total = counts["pending"] + counts["information_required"]
    return {"success": True, "counts": counts,
            # `count` is the TRUE total; `shown` is how many rows this page holds
            "count": total, "shown": len(items),
            "truncated": total > len(items), "items": items}
