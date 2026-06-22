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
                queue="default", enqueue_after_commit=True,
                task_name=task_name, recipient=u, actor=actor,
                previous_native_log_name=(prev_map or {}).get(u),
                dedupe_key=_stable_dedupe("task_assigned", task_name, u), attempt=1)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PM enqueue_task_assignment_delivery")


# Re-enqueue retry (queue-aligned): each attempt is a NEW RQ job on the SAME `default`
# queue Frappe uses for the native Assignment Notification Log job. Finite attempts, short
# leading backoff per retry, NO in-job poll loop and NO snapshot rollback (a fresh job is
# a fresh transaction/snapshot by construction).
_NATIVE_MAX_ATTEMPTS = 8
_NATIVE_BACKOFF = (1, 1, 2, 2, 3, 3, 3)   # seconds; leading delay applied on attempt > 1


def route_native_assignment_delivery(task_name, recipient, actor,
                                     previous_native_log_name, dedupe_key, attempt=1):
    """Enqueued delivery job (one attempt). Performs ONE deterministic native-log lookup in a
    fresh transaction. If found -> route_existing_notification_log (delivery + realtime
    reference the native log; NO Alert log). If not found and attempts remain -> re-enqueue
    ITSELF on `default` with attempt+1 after a short bounded backoff (each retry is a new RQ
    job/transaction, so it sees rows committed by Frappe's separate async native-log job
    without any snapshot manipulation). After the final attempt -> structured warning +
    fail-open (NO Alert fallback). Idempotent via the stable dedupe_key."""
    import time

    # leading bounded backoff for retries (gives the async native-log job time to commit)
    if attempt and attempt > 1:
        try:
            time.sleep(_NATIVE_BACKOFF[min(attempt - 2, len(_NATIVE_BACKOFF) - 1)])
        except Exception:
            pass

    try:
        if frappe.db.get_value("Task", task_name, "workflow_state") in ("Done", "Cancelled"):
            return
    except Exception:
        pass

    native = _latest_native_log(recipient, task_name)
    if native and native.get("name") != previous_native_log_name:
        try:
            from ecentric_workspace.action_center.resolvers import build_task_url
            ncev.route_existing_notification_log(
                "task_assigned", recipient, native["name"], native.get("subject") or "",
                action_url=build_task_url(task_name), reference_doctype="Task",
                reference_name=task_name, actor=actor, created_at=native.get("creation"),
                dedupe_key=dedupe_key)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PM route_native_assignment_delivery route")
        return

    if (attempt or 1) >= _NATIVE_MAX_ATTEMPTS:
        try:
            ctx = frappe.as_json({
                "event": "task_assigned_delivery_timeout", "task": task_name,
                "recipient": recipient, "previous_native_log": previous_native_log_name,
                "attempts": attempt})
        except Exception:
            ctx = "task=%s recipient=%s prev=%s attempts=%s" % (
                task_name, recipient, previous_native_log_name, attempt)
        frappe.log_error(ctx, "PM route_native_assignment_delivery timeout")
        return                              # fail-open, NO Alert fallback

    # not found yet -> re-enqueue a NEW job (new transaction/snapshot) on `default`
    try:
        frappe.enqueue(
            "ecentric_workspace.pm.api.notifications.route_native_assignment_delivery",
            queue="default",
            task_name=task_name, recipient=recipient, actor=actor,
            previous_native_log_name=previous_native_log_name, dedupe_key=dedupe_key,
            attempt=(attempt or 1) + 1)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM route_native_assignment_delivery requeue")


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
