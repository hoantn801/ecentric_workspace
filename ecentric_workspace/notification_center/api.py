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
           "from_user", "read", "type", "creation", "link"]
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


@frappe.whitelist(methods=["GET"], allow_guest=True)
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
from ecentric_workspace.notification_center.events import publish_notification_event

_PREF_DT = "EC Notification Preference"
_PREF_BOOL = ("sound_enabled", "desktop_enabled", "teams_enabled", "webpush_enabled",
               "quiet_hours_enabled")
_PREF_OTHER = ("quiet_hours_start", "quiet_hours_end", "timezone",
               "minimum_severity", "enabled_event_types")


@frappe.whitelist(methods=["GET"], allow_guest=True)
def get_preferences():
    """Return the CURRENT user's notification preferences (defaults if none saved)."""
    user = _current_user()
    if not user:
        return {"success": False, "error": "Unauthorized"}
    return {"success": True, "preferences": _events.get_preference(user)}


@frappe.whitelist(methods=["POST"])
def set_preferences(sound_enabled=None, desktop_enabled=None, teams_enabled=None,
                    webpush_enabled=None,
                    quiet_hours_enabled=None, quiet_hours_start=None, quiet_hours_end=None,
                    timezone=None, minimum_severity=None, enabled_event_types=None):
    """Upsert the CURRENT user's preferences. Scoped strictly to frappe.session.user --
    the client can never pass a `user`; one record per user (name = user)."""
    user = _current_user()
    if not user:
        return {"success": False, "error": "Unauthorized"}
    incoming = {
        "sound_enabled": sound_enabled, "desktop_enabled": desktop_enabled,
        "teams_enabled": teams_enabled, "webpush_enabled": webpush_enabled,
        "quiet_hours_enabled": quiet_hours_enabled,
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


# ------------------------------------------------------------------ web push (PWA)
# Ba diem vao duy nhat cho trinh duyet. TAT CA deu ep `user = frappe.session.user`:
# client khong bao gio duoc phep noi no la ai, va khong bao gio doc duoc dang ky cua
# nguoi khac (doctype EC Web Push Subscription khong cap quyen cho role "All").

@frappe.whitelist(methods=["GET"], allow_guest=True)
def webpush_public_key():
    """Khoa cong khai VAPID + trang thai bat/tat. Khoa nay KHONG phai bi mat - trinh
    duyet bat buoc phai co no de tao dang ky."""
    from ecentric_workspace.notification_center.providers import webpush as _wp
    cfg = _wp.get_settings()
    return {"success": True, "enabled": bool(cfg["enabled"] and cfg["public_key"]),
            "public_key": cfg["public_key"]}


@frappe.whitelist(methods=["POST"])
def webpush_subscribe(endpoint=None, p256dh=None, auth=None, user_agent=None, platform=None):
    """Luu (hoac lam song lai) dang ky push cua TRINH DUYET hien tai.

    Khoa dinh danh la `endpoint` chu khong phai user: mot nguoi co nhieu thiet bi, va
    trinh duyet co the cap lai dung endpoint cu sau khi nguoi dung tat/bat quyen. Vi
    the day la UPSERT theo endpoint, khong phai INSERT."""
    user = _current_user()
    if not user:
        return {"success": False, "error": "Unauthorized"}
    endpoint = (endpoint or "").strip()
    if not endpoint.startswith("https://"):
        return {"success": False, "error": "Endpoint khong hop le"}
    existing = frappe.get_all("EC Web Push Subscription",
                              filters={"endpoint": endpoint}, pluck="name", limit=1)
    payload = {"user": user, "endpoint": endpoint, "p256dh": p256dh or "",
               "auth": auth or "", "user_agent": (user_agent or "")[:500],
               "platform": (platform or "")[:140], "active": 1,
               "failure_count": 0, "last_error": ""}
    if existing:
        doc = frappe.get_doc("EC Web Push Subscription", existing[0])
        doc.update(payload)
    else:
        payload["doctype"] = "EC Web Push Subscription"
        doc = frappe.get_doc(payload)
    doc.save(ignore_permissions=True)   # an toan: `user` bi ep = session user o tren
    frappe.db.commit()
    return {"success": True, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def webpush_unsubscribe(endpoint=None):
    """Nguoi dung tat thong bao tren thiet bi nay -> bo tich active (KHONG xoa ban ghi,
    de con dau vet chan doan). Chi tac dong len dang ky CUA CHINH ho."""
    user = _current_user()
    if not user:
        return {"success": False, "error": "Unauthorized"}
    names = frappe.get_all("EC Web Push Subscription",
                           filters={"endpoint": (endpoint or "").strip(), "user": user},
                           pluck="name", limit=5)
    for nm in names:
        frappe.db.set_value("EC Web Push Subscription", nm, "active", 0)
    frappe.db.commit()
    return {"success": True, "deactivated": len(names)}


# --------------------------------------------------------------- thong bao chung
@frappe.whitelist(methods=["POST"])
def announce(title=None, message=None, action_url=None, tag=None, users=None, dry_run=1,
             teams=0, reference_doctype=None, reference_name=None):
    """Gui MOT thong bao vao chuong ERP cua nhieu nguoi cung luc.

    VI SAO PHAI CO DIEM VAO NAY: `Notification Log` chi co dung mot quyen la
    "All: read". KHONG AI tao duoc no qua REST, ke ca System Manager - no chi sinh ra
    tu code chay phia server. Nen khong co ham nay thi khong co cach nao gui thong
    bao hang loat ma khong co shell (site chay tren Frappe Cloud).

    BA CHOT AN TOAN, vi mot lan gui la 73 nguoi va KHONG RUT LAI DUOC:
      1. dry_run MAC DINH BAT. Phai truyen dry_run=0 moi that su gui.
      2. event_type "announcement" co teams=False, webpush=False KHOA CUNG trong
         ROUTING_MATRIX - khong co tham so nao bat duoc chung, nen khong the lo tay
         ban 73 tin nhan rieng ra Teams.
      3. Idempotent theo `tag`: goi lai cung tag khong tao thong bao thu hai (dedupe
         cua publish_notification_event). Mac dinh tag = ngay hom nay.

    users: bo trong = moi Employee dang Active co user_id. Hoac truyen danh sach
    email (JSON array hoac chuoi ngan cach dau phay) de gui cho mot nhom nho.

    teams: mac dinh 0. Dat 1 de tin ra ca Teams (event type "announcement_urgent").
    PHAI GOI TEN moi co - khong bao gio xay ra do quen. Voi 73 nguoi thi day la 73
    tin nhan RIENG khong rut lai duoc, nen hay gui cho vai nguoi truoc.
    """
    caller = _current_user()
    if not caller:
        return {"success": False, "error": "Unauthorized"}
    if "System Manager" not in frappe.get_roles(caller):
        frappe.response["http_status_code"] = 403
        return {"success": False, "error": "Chi System Manager."}
    title = (title or "").strip()
    if not title:
        return {"success": False, "error": "Thieu tieu de."}

    # --- ai nhan ---
    recipients = []
    if users:
        if isinstance(users, str):
            raw = users.strip()
            if raw.startswith("["):
                import json as _json
                try:
                    recipients = [str(x).strip() for x in _json.loads(raw)]
                except Exception:
                    return {"success": False, "error": "users khong phai JSON hop le."}
            else:
                recipients = [x.strip() for x in raw.split(",")]
        elif isinstance(users, (list, tuple)):
            recipients = [str(x).strip() for x in users]
        recipients = [u for u in recipients if u and u != "Guest"]
        # Chi cho phep email co that, tranh tao thong bao mo coi khong ai doc duoc.
        recipients = [u for u in recipients if frappe.db.exists("User", u)]
    else:
        rows = frappe.get_all("Employee", filters={"status": "Active"},
                              fields=["user_id"], limit_page_length=0)
        seen = {}
        for r in rows:
            u = (r.get("user_id") or "").strip()
            if u and u != "Guest" and u not in seen:
                seen[u] = 1
                recipients.append(u)

    tag = (tag or frappe.utils.nowdate())
    want_teams = str(teams) in ("1", "true", "True", "yes", "on")
    event_type = "announcement_urgent" if want_teams else "announcement"
    if str(dry_run) not in ("0", "false", "False", "no"):
        return {"success": True, "dry_run": True, "count": len(recipients),
                "tag": tag, "teams": want_teams, "event_type": event_type,
                "sample": recipients[:10],
                "note": "Chua gui gi. Truyen dry_run=0 de gui that."}

    sent = failed = 0
    errors = []
    for u in recipients:
        try:
            publish_notification_event(
                event_type=event_type, recipient=u,
                title=title, message=message or "",
                action_url=action_url or None,
                reference_doctype=reference_doctype or None,
                reference_name=reference_name or None,
                actor="Administrator", from_user="Administrator",
                dedupe_key="|".join([event_type, u, str(tag)]),
            )
            sent += 1
        except Exception:
            failed += 1
            if len(errors) < 5:
                errors.append(u)
            frappe.log_error(frappe.get_traceback(), "notification_center.announce")
    frappe.db.commit()
    return {"success": True, "dry_run": False, "sent": sent, "failed": failed,
            "tag": tag, "teams": want_teams, "event_type": event_type,
            "failed_sample": errors}
