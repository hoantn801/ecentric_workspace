# Copyright (c) 2026, eCentric and contributors
"""Notification Center API — current-user-only, native Frappe Notification Log.

Endpoints (POST /api/method/ecentric_workspace.notification_center.api.<fn>):
    get_notifications(limit=20)
    get_unread_count()
    mark_read(notification_name)
    mark_all_read()

Security contract:
  * authenticated user only (Guest -> 401);
  * the user is ALWAYS read from frappe.session.user — the client cannot pass for_user;
  * every read/write is scoped to the current user's own Notification Log rows;
  * no system DocPerm is changed and no other user's notification is ever exposed;
  * items carry a server-built canonical action_url (frontend never builds routes).
"""

import frappe

from ecentric_workspace.notification_center.resolvers import resolve_notification

# Native Notification Log fields we read (all standard Frappe v15 fields).
_FIELDS = ["name", "subject", "email_content", "document_type", "document_name",
           "from_user", "read", "type", "creation"]
_MAX_LIMIT = 50


def _current_user():
    """Return the authenticated user, or None (and set 401) for Guest/unauthenticated."""
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.response["http_status_code"] = 401
        return None
    return user


@frappe.whitelist(methods=["GET"])
def get_notifications(limit=20):
    """Current user's latest notifications (canonical items) + unread count."""
    user = _current_user()
    if not user:
        return {"success": False, "error": "Unauthorized", "count": 0, "unread": 0, "items": []}
    try:
        n = max(1, min(int(limit or 20), _MAX_LIMIT))
    except (TypeError, ValueError):
        n = 20
    rows = frappe.get_all(
        "Notification Log", filters={"for_user": user},
        fields=_FIELDS, order_by="creation desc", limit_page_length=n)
    items = [resolve_notification(r) for r in rows]
    unread = frappe.db.count("Notification Log", {"for_user": user, "read": 0})
    return {"success": True, "count": len(items), "unread": unread, "items": items}


@frappe.whitelist(methods=["GET"])
def get_unread_count():
    """Current user's unread Notification Log count (badge source)."""
    user = _current_user()
    if not user:
        return {"success": False, "unread": 0}
    return {"success": True, "unread": frappe.db.count("Notification Log", {"for_user": user, "read": 0})}


@frappe.whitelist(methods=["POST"])
def mark_read(notification_name=None):
    """Mark ONE notification read. Idempotent. Only the current user's own row may be
    marked; another user's row (or a non-existent name) returns a non-leaking failure."""
    user = _current_user()
    if not user:
        return {"success": False, "error": "Unauthorized"}
    if not notification_name:
        return {"success": False, "error": "notification_name is required"}
    owner = frappe.db.get_value("Notification Log", notification_name, "for_user")
    if owner != user:
        # Never confirm existence of another user's (or a missing) notification.
        return {"success": False, "error": "Not found"}
    frappe.db.set_value("Notification Log", notification_name, "read", 1)
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist(methods=["POST"])
def mark_all_read():
    """Mark ALL of the current user's unread notifications read. Scoped strictly to
    for_user = the session user — never touches anyone else's rows."""
    user = _current_user()
    if not user:
        return {"success": False, "error": "Unauthorized"}
    frappe.db.sql(
        "UPDATE `tabNotification Log` SET `read`=1 WHERE for_user=%s AND `read`=0", user)
    frappe.db.commit()
    return {"success": True}
