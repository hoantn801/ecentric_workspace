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

from ecentric_workspace.action_center.resolvers import (
    bucket_for,
    build_approval_url,
    resolve_item,
)


@frappe.whitelist(methods=["GET"])
def get_action_items():
    """Return canonical Action Center feed for the current user."""
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.response["http_status_code"] = 401
        return {"success": False, "error": "Unauthorized", "count": 0, "items": []}

    user = frappe.session.user
    rows = frappe.db.sql(
        "SELECT name, description, reference_type, reference_name, "
        "       priority, modified, date "
        "FROM `tabToDo` "
        "WHERE allocated_to=%s AND status=%s "
        "ORDER BY modified DESC LIMIT 20",
        (user, "Open"),
        as_dict=True,
    )

    items = []
    for r in rows:
        try:
            items.append(resolve_item(r))
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "action_center.resolve_item failed for ToDo " + str(r.get("name") or ""),
            )
            # Skip a single bad row; do not break the whole feed.
            continue

    # ---- v1 additive enrichment (2C.2): governed due dates + buckets ------
    # For engine-backed approval items the ToDo carries no date, but the
    # ACTIVE EC Approval Request Level does (SLA due_at). That is a governed
    # source record -- we derive, we never invent. Everything else keeps its
    # ToDo.date (WTU obligations set it; bare items stay "undated").
    today = frappe.utils.getdate()
    counts = {"overdue": 0, "today": 0, "upcoming": 0, "undated": 0}
    for it in items:
        if not it.get("due_at") and it.get("source_key") == "approval":
            due = _engine_level_due(it.get("reference_type"), it.get("reference_name"))
            if due:
                it["due_at"] = str(due)
        it["bucket"] = bucket_for(it.get("due_at"), today)
        counts[it["bucket"]] = counts.get(it["bucket"], 0) + 1

    # Backward-compatible: success/count/items unchanged; new keys additive.
    return {
        "success": True,
        "count": len(items),
        "items": items,
        "counts": counts,
        "generated_at": str(frappe.utils.now_datetime()),
    }


def _engine_level_due(ref_type, ref_name):
    """due_at of the ACTIVE approval level for a business doc, else None.

    Read-only, two indexed lookups; scope safety: the caller already holds an
    Open ToDo for this doc (engine granted read via DocShare), so exposing the
    level due date leaks nothing beyond the user's own queue.
    """
    if not (ref_type and ref_name):
        return None
    req = frappe.get_all(
        "EC Approval Request",
        filters={"reference_doctype": ref_type, "reference_name": ref_name,
                 "approval_status": ["in", ["Pending", "Information Required"]]},
        fields=["name"], limit=1, ignore_permissions=True)
    if not req:
        return None
    lv = frappe.get_all(
        "EC Approval Request Level",
        filters={"approval_request": req[0]["name"], "level_status": "In Progress"},
        fields=["due_at"], limit=1, ignore_permissions=True)
    return lv[0]["due_at"] if lv else None


@frappe.whitelist(methods=["GET"])
def get_my_requests_summary():
    """The current user's OWN submitted engine requests still in progress.

    Smallest governed aggregate (2C.2 locked scope): read-only over EC
    Approval Request, requester = SESSION user (client cannot pass a user),
    status Pending / Information Required only. Counts come from the SAME
    rows returned, so displayed counts can never drift from the list.
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
        order_by="submitted_at desc", limit=10, ignore_permissions=True)

    items = []
    counts = {"pending": 0, "information_required": 0}
    for r in rows:
        st = (r.get("approval_status") or "").strip()
        key = "information_required" if st == "Information Required" else "pending"
        counts[key] += 1
        title = ""
        try:
            title = frappe.db.get_value(
                r["reference_doctype"], r["reference_name"], "title") or ""
        except Exception:
            title = ""
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
    return {"success": True, "counts": counts, "count": len(items), "items": items}
