"""PM v2 - Notifications (basic, in-app only).

Uses NATIVE Frappe `Notification Log` (the desk bell / in-app notifications). NO
email in this phase. Triggers: task assigned, workflow transition, overdue (daily
scheduler), recurring task generated.

Anti-spam:
  - never notify the actor (from_user) or duplicates within a call,
  - overdue: deduped to once per day per task per user (dedup_key "[Overdue]"),
  - transition/assign: one-off events (fired only by the action itself).
"""

import frappe
from frappe import _
from frappe.utils import nowdate, getdate, today, add_days

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.notification_center import events as ncev
from ecentric_workspace.action_center.resolvers import build_task_url


def _stable_dedupe(event_type, task_name, user, suffix=None):
    """Stable dedupe key (NEVER a random timestamp): event|task|user[|window]."""
    parts = [event_type, task_name, user]
    if suffix:
        parts.append(str(suffix))
    return "|".join(parts)


def notify_users(users, subject, task_name, from_user=None, dedup_key=None,
                 event_type="task_assigned", severity=None, message="",
                 due_suffix=None, action_url=None):
    """Route PM task notifications through the ONE central publish service
    (ecentric_workspace.notification_center.events.publish_notification_event) so the
    native Notification Log has a SINGLE owner and every event also flows to
    toast/sound/desktop/Teams. Never notifies the actor, Administrator, duplicates within
    a call, or a task already Done/Cancelled. Idempotency is handled centrally by the
    stable dedupe key (the legacy same-day substring check is no longer needed)."""
    from_user = from_user or frappe.session.user
    # Never notify about a terminal task.
    try:
        if frappe.db.get_value("Task", task_name, "workflow_state") in ("Done", "Cancelled"):
            return
    except Exception:
        pass
    url = action_url or build_task_url(task_name)
    seen = set()
    for u in users or []:
        if not u or u == from_user or u in seen or u == "Administrator":
            continue
        seen.add(u)
        try:
            ncev.publish_notification_event(
                event_type, u, subject, message or "",
                severity=severity, action_url=url,
                reference_doctype="Task", reference_name=task_name,
                actor=from_user,
                dedupe_key=_stable_dedupe(event_type, task_name, u, due_suffix))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PM notify_users")


def _latest_native_log(recipient, task_name):
    """Newest Frappe native Assignment Notification Log for (recipient, Task, task_name)
    using deterministic filters (never timestamp-only). Returns the row or None."""
    rows = frappe.get_all(
        "Notification Log",
        filters={"for_user": recipient, "type": "Assignment",
                 "document_type": "Task", "document_name": task_name},
        fields=["name", "creation", "subject"],
        order_by="creation desc", limit_page_length=1)
    return rows[0] if rows else None


def capture_previous_native_logs(users, task_name):
    """BEFORE assign_to.add: snapshot the current newest native Assignment log name per user,
    so the post-commit job can tell the NEW log apart from any pre-existing one."""
    out = {}
    for u in users or []:
        if not u:
            continue
        cand = _latest_native_log(u, task_name)
        out[u] = cand.get("name") if cand else None
    return out


def enqueue_task_assignment_delivery(task_name, users, prev_map, actor=None):
    """AFTER assign_to.add: enqueue exactly one delivery job per real recipient (after the
    request commits). Skips actor/self, Administrator and terminal tasks. Frappe creates the
    native Assignment log asynchronously via a doc_event-bypassing insert, so a queued job
    (below) waits for it instead of binding to Notification Log.after_insert."""
    actor = actor or frappe.session.user
    try:
        if frappe.db.get_value("Task", task_name, "workflow_state") in ("Done", "Cancelled"):
            return
    except Exception:
        pass
    seen = set()
    for u in users or []:
        if not u or u == actor or u in seen or u == "Administrator":
            continue
        seen.add(u)
        try:
            frappe.enqueue(
                "ecentric_workspace.pm.api.notifications.route_native_assignment_delivery",
                queue="short", enqueue_after_commit=True,
                task_name=task_name, recipient=u, actor=actor,
                previous_native_log_name=(prev_map or {}).get(u),
                dedupe_key=_stable_dedupe("task_assigned", task_name, u))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PM enqueue_task_assignment_delivery")


# bounded poll: short backoff, ~10.5s total, finite (never infinite)
_NATIVE_LOG_BACKOFF = (0.5, 1, 1.5, 2, 2.5, 3)


def route_native_assignment_delivery(task_name, recipient, actor,
                                     previous_native_log_name, dedupe_key):
    """Enqueued job: wait (bounded) for the NEW native Assignment log, then route the central
    delivery pipeline off it via route_existing_notification_log.

    Snapshot refresh: Frappe creates the native log in a SEPARATE job that commits after this
    job may have started. Under the worker's REPEATABLE READ transaction, repeated reads keep
    the original snapshot and never see that later commit. So after a MISS, we explicitly end
    the read transaction with frappe.db.rollback() before the next lookup, giving each retry a
    fresh snapshot. This is safe ONLY because no writes happen before the log is found; once
    found we do NOT rollback again and let the normal worker transaction commit the deliveries.

    The new log = newest matching row whose name != previous_native_log_name (deterministic
    filters + ordering, never timestamp-only). On timeout: structured warning + fail-open, NO
    Alert fallback. Idempotent via stable dedupe_key."""
    import time

    try:
        if frappe.db.get_value("Task", task_name, "workflow_state") in ("Done", "Cancelled"):
            return
    except Exception:
        pass

    def _found():
        cand = _latest_native_log(recipient, task_name)
        if cand and cand.get("name") != previous_native_log_name:
            return cand
        return None

    native = _found()                       # first attempt: current snapshot, NO rollback
    attempts = 0
    elapsed = 0.0
    if not native:
        for delay in _NATIVE_LOG_BACKOFF:
            time.sleep(delay)
            attempts += 1
            elapsed += delay
            # refresh the read snapshot AFTER a miss, BEFORE the next lookup (no writes yet)
            try:
                frappe.db.rollback()
            except Exception:
                pass
            native = _found()
            if native:
                break

    if not native:
        try:
            ctx = frappe.as_json({
                "event": "task_assigned_delivery_timeout", "task": task_name,
                "recipient": recipient, "previous_native_log": previous_native_log_name,
                "attempts": attempts, "elapsed_seconds": elapsed})
        except Exception:
            ctx = "task=%s recipient=%s prev=%s attempts=%s elapsed=%s" % (
                task_name, recipient, previous_native_log_name, attempts, elapsed)
        frappe.log_error(ctx, "PM route_native_assignment_delivery timeout")
        return                              # fail-open, NO Alert fallback

    # native found -> route delivery (writes begin here); MUST NOT rollback after this point.
    try:
        from ecentric_workspace.action_center.resolvers import build_task_url
        ncev.route_existing_notification_log(
            "task_assigned", recipient, native["name"], native.get("subject") or "",
            action_url=build_task_url(task_name), reference_doctype="Task",
            reference_name=task_name, actor=actor, created_at=native.get("creation"),
            dedupe_key=dedupe_key)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM route_native_assignment_delivery route")


def _task_recipients(doc, exclude=None):
    """Owner + assignees of a task, excluding `exclude` (e.g. the actor)."""
    users = []
    if doc.get("owner"):
        users.append(doc["owner"])
    if doc.get("_assign"):
        try:
            users += (frappe.parse_json(doc["_assign"]) or [])
        except Exception:
            pass
    return [u for u in users if u and u != exclude]


# --------------------------------------------------------------------------
# Read (PM "Thong bao" page)
# --------------------------------------------------------------------------
@frappe.whitelist()
def list_mine(limit=30):
    pmperm.require_pm_access()
    user = frappe.session.user
    rows = frappe.get_all(
        "Notification Log", filters={"for_user": user, "document_type": "Task"},
        fields=["name", "subject", "document_name", "read", "creation", "from_user", "type"],
        order_by="creation desc", limit_page_length=int(limit))
    unread = frappe.db.count("Notification Log", {"for_user": user, "document_type": "Task", "read": 0})
    return {"rows": rows, "unread": unread}


@frappe.whitelist()
def mark_read(name=None):
    user = frappe.session.user
    if name:
        if frappe.db.get_value("Notification Log", name, "for_user") == user:
            frappe.db.set_value("Notification Log", name, "read", 1)
    else:
        frappe.db.sql("update `tabNotification Log` set `read`=1 where for_user=%s and document_type='Task'", user)
    frappe.db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# Overdue daily scheduler
# --------------------------------------------------------------------------
def pm_overdue_scan():
    """Daily: notify assignees (or owner) of overdue tasks, once/day/task/user."""
    today_d = getdate(nowdate())
    tasks = frappe.get_all(
        "Task", filters={"exp_end_date": ["<", today_d],
                         "workflow_state": ["not in", ["Done", "Cancelled"]]},
        fields=["name", "subject", "_assign", "owner", "exp_end_date"], limit_page_length=0)
    for t in tasks:
        users = []
        if t.get("_assign"):
            try:
                users = frappe.parse_json(t["_assign"]) or []
            except Exception:
                users = []
        if not users and t.get("owner"):
            users = [t["owner"]]
        if not users:
            continue
        subject = "[Overdue] Nhiem vu qua han: " + (t.get("subject") or t["name"])
        notify_users(users, subject, t["name"], from_user="Administrator",
                     event_type="task_overdue", due_suffix=str(t.get("exp_end_date")))
    frappe.db.commit()


def pm_due_soon_scan(window_days=2):
    """Daily: notify assignees (or owner) of tasks due within `window_days` and not yet
    terminal. Idempotent: stable dedupe key includes the due date, so re-running the
    scheduler (same day) creates NO additional notifications."""
    today_d = getdate(nowdate())
    horizon = add_days(today_d, int(window_days))
    tasks = frappe.get_all(
        "Task", filters={"exp_end_date": ["between", [str(today_d), str(horizon)]],
                         "workflow_state": ["not in", ["Done", "Cancelled"]]},
        fields=["name", "subject", "_assign", "owner", "exp_end_date"], limit_page_length=0)
    for t in tasks:
        users = []
        if t.get("_assign"):
            try:
                users = frappe.parse_json(t["_assign"]) or []
            except Exception:
                users = []
        if not users and t.get("owner"):
            users = [t["owner"]]
        if not users:
            continue
        subject = "[Sap den han] Nhiem vu: " + (t.get("subject") or t["name"])
        notify_users(users, subject, t["name"], from_user="Administrator",
                     event_type="task_due_soon", due_suffix=str(t.get("exp_end_date")))
    frappe.db.commit()


@frappe.whitelist()
def due_soon_scan_once():
    """Admin/test trigger to run the due-soon scan now."""
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Admin only."), frappe.PermissionError)
    pm_due_soon_scan()
    return {"ok": True}


@frappe.whitelist()
def overdue_scan_once():
    """Admin/test trigger to run the overdue scan now (daily scheduler equivalent)."""
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Admin only."), frappe.PermissionError)
    pm_overdue_scan()
    return {"ok": True}
