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


# --------------------------------------------------------------------------- preferences
from ecentric_workspace.notification_center import events as _events

_PREF_DT = "EC Notification Preference"
_PREF_BOOL = ("sound_enabled", "desktop_enabled", "teams_enabled", "quiet_hours_enabled")
_PREF_OTHER = ("quiet_hours_start", "quiet_hours_end", "timezone",
               "minimum_severity", "enabled_event_types")


@frappe.whitelist(methods=["GET"])
def get_preferences():
    """Return the CURRENT user's notification preferences (defaults if none saved)."""
    user = _current_user()
    if not user:
        return {"success": False, "error": "Unauthorized"}
    return {"success": True, "preferences": _events.get_preference(user)}


@frappe.whitelist(methods=["POST"])
def set_preferences(sound_enabled=None, desktop_enabled=None, teams_enabled=None,
                    quiet_hours_enabled=None, quiet_hours_start=None, quiet_hours_end=None,
                    timezone=None, minimum_severity=None, enabled_event_types=None):
    """Upsert the CURRENT user's preferences. Scoped strictly to frappe.session.user --
    the client can never pass a `user`; one record per user (name = user)."""
    user = _current_user()
    if not user:
        return {"success": False, "error": "Unauthorized"}
    incoming = {
        "sound_enabled": sound_enabled, "desktop_enabled": desktop_enabled,
        "teams_enabled": teams_enabled, "quiet_hours_enabled": quiet_hours_enabled,
        "quiet_hours_start": quiet_hours_start, "quiet_hours_end": quiet_hours_end,
        "timezone": timezone, "minimum_severity": minimum_severity,
        "enabled_event_types": enabled_event_types,
    }
    if frappe.db.exists(_PREF_DT, user):
        doc = frappe.get_doc(_PREF_DT, user)
    else:
        doc = frappe.get_doc({"doctype": _PREF_DT, "user": user})
    for k, v in incoming.items():
        if v is None:
            continue
        if k in _PREF_BOOL:
            doc.set(k, 1 if str(v) in ("1", "true", "True", "yes", "on") else 0)
        else:
            doc.set(k, v)
    doc.save(ignore_permissions=True)  # safe: user value is forced to session user
    frappe.db.commit()
    return {"success": True, "preferences": _events.get_preference(user)}


@frappe.whitelist(methods=["POST"])
def save_teams_conversation(user=None, reference=None, aad_object_id=None):
    """Ingest a Bot Framework conversationReference captured by the eCentric ERP Bot web
    service (when a user installs/opens the bot). Restricted to System Manager -- the bot
    service authenticates with an API key bound to a service user holding that role. Stores
    only non-secret conversation identifiers (no bot password / Graph secret)."""
    caller = _current_user()
    if not caller:
        return {"success": False, "error": "Unauthorized"}
    if "System Manager" not in frappe.get_roles(caller):
        frappe.response["http_status_code"] = 403
        return {"success": False, "error": "Forbidden"}
    if not user or not reference:
        return {"success": False, "error": "user and reference are required"}
    from ecentric_workspace.notification_center.providers import teams_bot
    name = teams_bot.save_conversation_reference(user, reference, aad_object_id=aad_object_id)
    return {"success": True, "name": name}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def teams_bot_messages():
    """Azure Bot Framework messaging endpoint -- SECURED with inbound Bot Connector auth.

    Every inbound activity must carry a valid `Authorization: Bearer <JWT>` issued by the Bot
    Connector. The token is validated (signature against the Bot Connector JWKS, issuer,
    audience == ec_teams_bot_app_id, expiry, serviceUrl claim == activity.serviceUrl, Teams
    channel endorsement) before anything is parsed. Missing/invalid -> 401. There is NO config
    switch to bypass validation. On success the endpoint ACKs 200 and, for personal-scope
    lifecycle activities, captures/updates the conversation reference (now trusted because the
    request is authenticated). Tokens/secrets are never logged."""
    from ecentric_workspace.notification_center.providers import bot_auth, teams_bot

    app_id = teams_bot.bot_config().get("app_id")
    auth = frappe.get_request_header("Authorization") if hasattr(frappe, "get_request_header") else None
    try:
        activity = (frappe.request.get_json(silent=True) if getattr(frappe, "request", None) else None) or {}
    except Exception:
        activity = {}

    ok, reason = bot_auth.validate_bot_request(auth, activity, app_id)
    if not ok:
        frappe.local.response["http_status_code"] = 401
        frappe.log_error("teams_bot_messages rejected (" + str(reason)[:60] + ")", "teams bot auth")
        return {"error": "unauthorized"}

    try:
        _capture_conversation_from_activity(activity)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "teams_bot_messages capture")

    frappe.local.response["http_status_code"] = 200
    return {}


def _capture_conversation_from_activity(activity):
    """Best-effort, TRUSTED (post-validation) capture of the conversation reference for a
    personal-scope lifecycle activity. Maps the activity user (aadObjectId) -> ERP email via
    Graph; stores only when a matching Frappe User exists. Never required for delivery
    (proactive provisioning via Graph remains the primary path)."""
    if not activity or activity.get("type") not in ("conversationUpdate", "installationUpdate", "message"):
        return
    frm = activity.get("from") or {}
    aad = frm.get("aadObjectId")
    if not aad:
        return
    from ecentric_workspace.notification_center.providers import teams_bot, graph as graphmod
    ok, email = graphmod.aad_object_id_to_email(aad)
    if not ok or not email or not frappe.db.exists("User", email):
        return
    conv = activity.get("conversation") or {}
    tenant = conv.get("tenantId") or ((activity.get("channelData") or {}).get("tenant") or {}).get("id")
    ref = {"serviceUrl": activity.get("serviceUrl"),
           "conversation": {"id": conv.get("id"), "tenantId": tenant},
           "bot": {"id": (activity.get("recipient") or {}).get("id")}}
    teams_bot.save_conversation_reference(email, ref, aad_object_id=aad, installed=1)
