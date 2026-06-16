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

from ecentric_workspace.action_center.resolvers import resolve_item


@frappe.whitelist(methods=["POST"])
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

    return {"success": True, "count": len(items), "items": items}
