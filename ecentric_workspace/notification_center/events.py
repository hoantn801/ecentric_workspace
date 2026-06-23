# Copyright (c) 2026, eCentric and contributors
"""Notification Delivery v1 -- ONE central publish service for multi-channel notifications.

publish_notification_event() is the single entry every module calls. One publish:
  1. creates/links a native Frappe Notification Log (inbox = source of truth);
  2. routes to channels (erp / toast / sound / desktop / teams) per the channel matrix
     x the recipient's EC Notification Preference x severity x quiet hours;
  3. writes an EC Notification Delivery Log per (event, recipient, channel) -- idempotent;
  4. publishes ONE realtime 'ec_notification' (full contract, superset of the legacy
     {item,unread}) to the recipient ONLY, AFTER commit;
  5. enqueues Teams delivery on a background queue (never in the request transaction).

Event-level idempotency: event_id = sha1(dedupe_key); a second publish with the same
dedupe_key finds the existing erp delivery row and returns early (no dup inbox/realtime/
delivery). Teams is never sent inline.
"""
import hashlib
import json

import frappe

from ecentric_workspace.notification_center.resolvers import resolve_notification

REALTIME_EVENT = "ec_notification"
CHANNELS = ("erp", "toast", "sound", "desktop", "teams")
EVENT_TYPES = ("task_assigned", "task_due_soon", "task_overdue",
               "approval_required", "mention", "system_critical")
SEVERITIES = ("info", "action_required", "urgent")
_SEV_RANK = {"info": 0, "action_required": 1, "urgent": 2}
_DEFAULT_SEVERITY = {
    "task_assigned": "action_required", "task_due_soon": "info",
    "task_overdue": "urgent", "approval_required": "action_required",
    "mention": "info", "system_critical": "urgent",
}
# matrix cell: True (always) | "pref" (depends on user preference) | False (never)
ROUTING_MATRIX = {
    "task_assigned":    {"erp": True, "toast": True, "sound": True,   "desktop": "pref", "teams": True},
    "task_due_soon":    {"erp": True, "toast": True, "sound": "pref", "desktop": "pref", "teams": "pref"},
    "task_overdue":     {"erp": True, "toast": True, "sound": True,   "desktop": "pref", "teams": True},
    "approval_required":{"erp": True, "toast": True, "sound": True,   "desktop": "pref", "teams": True},
    "mention":          {"erp": True, "toast": True, "sound": "pref", "desktop": "pref", "teams": "pref"},
    "system_critical":  {"erp": True, "toast": True, "sound": True,   "desktop": True,   "teams": True},
}
# severities that bypass quiet hours / minimum-severity / disabled-event suppression
_BYPASS_SEVERITY = ("urgent",)
PREF_DT = "EC Notification Preference"
DELIVERY_DT = "EC Notification Delivery Log"


# --------------------------------------------------------------------------- prefs
def get_preference(user):
    """Return a plain dict of the user's preferences with safe defaults (no write)."""
    d = {"user": user, "sound_enabled": 1, "desktop_enabled": 0, "teams_enabled": 0,
         "quiet_hours_enabled": 0, "quiet_hours_start": None, "quiet_hours_end": None,
         "timezone": None, "minimum_severity": "info", "enabled_event_types": "",
         "_exists": False}
    try:
        if frappe.db.exists(PREF_DT, user):
            rec = frappe.get_doc(PREF_DT, user)
            d["_exists"] = True
            for k in list(d.keys()):
                if k == "_exists":
                    continue
                v = getattr(rec, k, None)
                if v is not None:
                    d[k] = v
    except Exception:
        pass
    return d


def _enabled_event_set(pref):
    raw = (pref.get("enabled_event_types") or "").strip()
    if not raw:
        return None  # None = all enabled
    return set(x.strip() for x in raw.replace("\n", ",").split(",") if x.strip())


# --------------------------------------------------------------- quiet hours (tz, midnight)
def _now_minutes(tz=None):
    """Current local time as minutes-since-midnight, honouring the user's tz if given."""
    try:
        dt = frappe.utils.now_datetime()
        if tz:
            import pytz
            dt = frappe.utils.get_datetime(dt)
            try:
                dt = dt.astimezone(pytz.timezone(tz)) if dt.tzinfo else pytz.utc.localize(dt).astimezone(pytz.timezone(tz))
            except Exception:
                pass
        return dt.hour * 60 + dt.minute
    except Exception:
        return None


def _to_minutes(t):
    """'HH:MM[:SS]' or timedelta -> minutes since midnight, or None."""
    if t is None:
        return None
    try:
        if hasattr(t, "total_seconds"):
            return int(t.total_seconds() // 60)
        parts = str(t).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return None


def in_quiet_hours(pref, now_min=None):
    """True if 'now' falls inside the user's quiet window. Handles windows that cross
    midnight (start > end)."""
    if not pref.get("quiet_hours_enabled"):
        return False
    s = _to_minutes(pref.get("quiet_hours_start"))
    e = _to_minutes(pref.get("quiet_hours_end"))
    if s is None or e is None or s == e:
        return False
    n = now_min if now_min is not None else _now_minutes(pref.get("timezone"))
    if n is None:
        return False
    if s < e:
        return s <= n < e            # same-day window
    return n >= s or n < e           # crosses midnight


# ------------------------------------------------------------------- channel resolution
def resolve_channels(event_type, severity, pref, now_min=None):
    """Return {channel: 'deliver'|'skip'|'suppress'}.

    Rules:
      * ERP inbox + in-app toast are the ALWAYS-ON baseline (never gated by master
        switch / quiet hours / minimum severity) -- they are the reliable record.
      * sound / desktop / teams: the matrix cell sets the DEFAULT (True = on, 'pref' =
        off). Once the user has SAVED a preference, their master switch is authoritative
        and may only REDUCE/raise that one channel. Then quiet hours, minimum severity,
        and enabled_event_types may SUPPRESS it. severity 'urgent' bypasses all three
        suppressors (system_critical defaults to urgent)."""
    matrix = ROUTING_MATRIX.get(event_type, ROUTING_MATRIX["task_assigned"])
    bypass = severity in _BYPASS_SEVERITY
    quiet = (not bypass) and in_quiet_hours(pref, now_min)
    below_min = (not bypass) and (_SEV_RANK.get(severity, 0) < _SEV_RANK.get(pref.get("minimum_severity") or "info", 0))
    enabled = _enabled_event_set(pref)
    event_disabled = (not bypass) and (enabled is not None) and (event_type not in enabled)
    has_pref = bool(pref.get("_exists"))
    switch = {"sound": bool(pref.get("sound_enabled")),
              "desktop": bool(pref.get("desktop_enabled")),
              "teams": bool(pref.get("teams_enabled"))}
    out = {}
    for ch in CHANNELS:
        cell = matrix.get(ch, False)
        if ch in ("erp", "toast"):
            out[ch] = "deliver" if cell else "skip"     # always-on baseline
            continue
        if cell is False:
            out[ch] = "skip"
            continue
        # default from matrix; a saved preference overrides this single channel.
        on = switch[ch] if has_pref else (cell is True)
        if not on:
            out[ch] = "skip"
            continue
        if below_min or event_disabled or quiet:
            out[ch] = "suppress"
            continue
        out[ch] = "deliver"
    return out


# ----------------------------------------------------------------------- core publish
def _event_id(dedupe_key):
    return hashlib.sha1(("ecnc:" + str(dedupe_key)).encode("utf-8")).hexdigest()[:16]


def _delivery(event_id, recipient, channel, status, **kw):
    idem = event_id + "|" + recipient + "|" + channel
    try:
        doc = frappe.get_doc(dict({
            "doctype": DELIVERY_DT, "idempotency_key": idem, "event_id": event_id,
            "recipient": recipient, "channel": channel, "status": status,
            "attempt_count": 0,
        }, **kw))
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        # unique idempotency_key -> already created for this (event,recipient,channel)
        return None


def route_delivery(event_id, recipient, routing, event_type, severity, dedupe_key,
                   notification_log=None, action_url=None, reference_doctype=None,
                   reference_name=None, title=None, message=None, actor=None):
    """Write one EC Notification Delivery Log per channel (idempotent) and enqueue Teams
    on the background queue (enqueue_after_commit -- never inline). Shared by
    publish_notification_event and the legacy emit() path."""
    teams_jobs = []
    common = {"event_type": event_type, "severity": severity, "dedupe_key": dedupe_key,
              "notification_log": notification_log or "", "action_url": action_url or "",
              "reference_doctype": reference_doctype or "", "reference_name": reference_name or "",
              "title": title or "", "message": message or "", "actor": actor or ""}
    for ch, decision in routing.items():
        if decision == "deliver":
            if ch == "teams":
                nm = _delivery(event_id, recipient, ch, "Pending", provider="", **common)
                if nm:
                    teams_jobs.append(nm)
            else:
                _delivery(event_id, recipient, ch, "Sent",
                          sent_at=frappe.utils.now_datetime(), **common)
        elif decision == "suppress":
            _delivery(event_id, recipient, ch, "Suppressed", **common)
        else:  # skip (channel turned off in preferences)
            _delivery(event_id, recipient, ch, "Skipped", **common)
    for nm in teams_jobs:
        try:
            frappe.enqueue(
                "ecentric_workspace.notification_center.providers.teams.deliver",
                queue="default", enqueue_after_commit=True, delivery_log=nm)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "route_delivery enqueue teams")
    return teams_jobs


def publish_notification_event(event_type, recipient, title, message="",
                               severity=None, action_url=None, reference_doctype=None,
                               reference_name=None, actor=None, dedupe_key=None,
                               metadata=None, from_user=None):
    """Publish ONE notification event across all permitted channels. Idempotent by
    dedupe_key. Returns a dict describing the event + routing."""
    if not recipient or recipient == "Guest":
        return {"ok": False, "reason": "no recipient"}
    if event_type not in EVENT_TYPES:
        event_type = "task_assigned"
    severity = severity if severity in SEVERITIES else _DEFAULT_SEVERITY.get(event_type, "info")
    from_user = from_user or actor or frappe.session.user
    if not dedupe_key:
        dedupe_key = "|".join([event_type, recipient, str(reference_doctype or ""), str(reference_name or "")])
    event_id = _event_id(dedupe_key)

    # event-level idempotency: same dedupe_key already published -> no-op
    try:
        if frappe.db.exists(DELIVERY_DT, {"event_id": event_id, "channel": "erp"}):
            return {"ok": True, "duplicate": True, "event_id": event_id, "dedupe_key": dedupe_key}
    except Exception:
        pass

    # 1) inbox = Notification Log (this path OWNS the log)
    log = frappe.get_doc({
        "doctype": "Notification Log", "for_user": recipient, "from_user": from_user,
        "subject": title or "", "email_content": message or "", "type": "Alert",
        "document_type": reference_doctype or "", "document_name": reference_name or "",
    }).insert(ignore_permissions=True)

    # 2+3) delivery audit + realtime, referencing the log just created
    routing = _route_and_publish(
        event_id, recipient, event_type, severity, title, message, action_url,
        reference_doctype, reference_name, from_user, dedupe_key, log.name, log.creation,
        log_type="Alert")
    return {"ok": True, "event_id": event_id, "dedupe_key": dedupe_key,
            "notification_log": log.name, "routing": routing, "severity": severity}


def _route_and_publish(event_id, recipient, event_type, severity, title, message,
                       action_url, reference_doctype, reference_name, from_user,
                       dedupe_key, notification_log_name, created_at, log_type="Alert"):
    """Shared tail: write delivery audit rows (idempotent) + enqueue Teams + publish the
    full-contract realtime to the recipient (after commit), all referencing
    `notification_log_name`. Used by publish_notification_event (which creates the log)."""
    pref = get_preference(recipient)
    routing = resolve_channels(event_type, severity, pref)
    route_delivery(event_id, recipient, routing, event_type, severity, dedupe_key,
                   notification_log_name, action_url, reference_doctype, reference_name,
                   title, message, from_user)
    try:
        item = resolve_notification({
            "name": notification_log_name, "subject": title, "email_content": message,
            "document_type": reference_doctype, "document_name": reference_name,
            "from_user": from_user, "read": 0, "type": log_type, "creation": created_at,
        })
        unread = frappe.db.count("Notification Log", {"for_user": recipient, "read": 0})
        payload = {
            "event_id": event_id, "notification_name": notification_log_name,
            "event_type": event_type, "severity": severity, "title": title or "",
            "message": message or "",
            "action_url": item.get("action_url") if isinstance(item, dict) else (action_url or ""),
            "created_at": str(created_at), "unread_count": unread,
            # legacy-compatible keys so the existing frontend keeps working unchanged:
            "item": item, "unread": unread,
        }
        frappe.publish_realtime(event=REALTIME_EVENT, message=payload,
                                user=recipient, after_commit=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ec notification realtime")
    return routing


# ------------------------------------------------------------------- typed helpers
def notify_task_assigned(recipient, task_name, title, message="", action_url=None, actor=None):
    return publish_notification_event("task_assigned", recipient, title, message,
                                      action_url=action_url, reference_doctype="Task",
                                      reference_name=task_name, actor=actor)


def notify_task_due_soon(recipient, task_name, title, message="", action_url=None):
    return publish_notification_event("task_due_soon", recipient, title, message,
                                      action_url=action_url, reference_doctype="Task",
                                      reference_name=task_name)


def notify_task_overdue(recipient, task_name, title, message="", action_url=None):
    return publish_notification_event("task_overdue", recipient, title, message,
                                      action_url=action_url, reference_doctype="Task",
                                      reference_name=task_name)


def notify_approval_required(recipient, doctype, name, title, message="", action_url=None, actor=None):
    return publish_notification_event("approval_required", recipient, title, message,
                                      action_url=action_url, reference_doctype=doctype,
                                      reference_name=name, actor=actor)


def publish_task_assignment_delivery(recipient, task_name, title, message="",
                                     action_url=None, actor=None, dedupe_key=None):
    """SYNCHRONOUS task_assigned delivery from the controlled PM assignment transaction.

    Decoupled from the async native Assignment log + RQ worker: this runs INSIDE the
    assignment request, writes idempotent Delivery Log rows synchronously, and publishes the
    `ec_notification` realtime ONLY via frappe.db.after_commit -- so toast/sound/desktop fire
    immediately from the WEB process after the transaction commits (no worker, no queue, no
    polling). It does NOT create a Notification Log: the native Frappe Assignment log remains
    the inbox source (created asynchronously) and owns the badge. `notification_log` is left
    blank/pending on the delivery rows (an optional later reconciliation may link them).

    Idempotent by dedupe_key (task_assigned|<task>|<recipient>): repeated API calls / frontend
    retries never duplicate. If the assignment transaction rolls back, the Delivery Log rows
    roll back with it and after_commit is reset, so no realtime fires."""
    if not recipient or recipient == "Guest":
        return {"ok": False, "reason": "no recipient"}
    event_type = "task_assigned"
    severity = _DEFAULT_SEVERITY[event_type]
    actor = actor or frappe.session.user
    if not dedupe_key:
        dedupe_key = "|".join([event_type, task_name, recipient])
    event_id = _event_id(dedupe_key)

    # idempotency: same event already delivered -> no-op
    try:
        if frappe.db.exists(DELIVERY_DT, {"event_id": event_id, "channel": "erp"}):
            return {"ok": True, "duplicate": True, "event_id": event_id, "dedupe_key": dedupe_key}
    except Exception:
        pass

    pref = get_preference(recipient)
    routing = resolve_channels(event_type, severity, pref)

    # Teams only enqueues when an actual provider is configured; when disabled it is recorded
    # synchronously as Skipped so ERP delivery never depends on a background worker.
    try:
        from ecentric_workspace.notification_center.providers import teams as _teams
        _teams_send = _teams.get_config().get("provider") in ("teams_bot", "webhook", "power_automate_copilot")
    except Exception:
        _teams_send = False

    common = {"event_type": event_type, "severity": severity, "dedupe_key": dedupe_key,
              "notification_log": "",            # pending: native Assignment log is the inbox
              "action_url": action_url or "", "reference_doctype": "Task",
              "reference_name": task_name, "title": title or "", "message": message or "",
              "actor": actor or ""}
    teams_jobs = []
    for ch, decision in routing.items():
        if decision == "deliver":
            if ch == "erp":
                # inbox delivered by the native Frappe Assignment log -> audit marker only
                _delivery(event_id, recipient, "erp", "Sent", provider="native",
                          sent_at=frappe.utils.now_datetime(), **common)
            elif ch == "teams":
                if _teams_send:
                    nm = _delivery(event_id, recipient, "teams", "Pending", provider="", **common)
                    if nm:
                        teams_jobs.append(nm)
                else:
                    _delivery(event_id, recipient, "teams", "Skipped", provider="dryrun",
                              error_code="NO_CREDENTIAL", **common)
            else:
                _delivery(event_id, recipient, ch, "Sent",
                          sent_at=frappe.utils.now_datetime(), **common)
        elif decision == "suppress":
            _delivery(event_id, recipient, ch, "Suppressed", **common)
        else:
            _delivery(event_id, recipient, ch, "Skipped", **common)

    # Teams (only if a provider is configured) -> background; NEVER blocks ERP delivery
    for nm in teams_jobs:
        try:
            frappe.enqueue("ecentric_workspace.notification_center.providers.teams.deliver",
                           queue="default", enqueue_after_commit=True, delivery_log=nm)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "publish_task_assignment_delivery teams")

    # realtime AFTER commit only (web process) -> toast/sound/desktop fire immediately.
    # Badge is owned by the native Assignment log -> update_badge False (no double-increment).
    payload = {
        "event_id": event_id, "notification_name": "", "event_type": event_type,
        "severity": severity, "title": title or "", "message": message or "",
        "action_url": action_url or "", "created_at": str(frappe.utils.now_datetime()),
        "update_badge": False, "inbox_managed_by_native": True,
    }
    try:
        frappe.publish_realtime(event=REALTIME_EVENT, message=payload,
                                user=recipient, after_commit=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "publish_task_assignment_delivery realtime")

    return {"ok": True, "event_id": event_id, "dedupe_key": dedupe_key, "routing": routing}
