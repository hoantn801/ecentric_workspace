"""PM v2 - Worktime timer services (Day 2 item 5 redesign).

Active-timer state is held in a minimal custom DocType `PM Timer` (one record
per user, autoname=field:user -> guarantees a single active timer per user).
On Stop, a NATIVE Timesheet log is created (via timesheet._create_timesheet) and
the PM Timer is deleted. So the durable, auditable worktime stays in native
Timesheet; PM Timer only holds the transient running state (survives refresh).

Permission enforced in this service layer (require_pm_access + can_view_task).
"""

import frappe
from frappe import _

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm.api import timesheet as pmts

TIMER_DT = "PM Timer"


def _now():
    return frappe.utils.now_datetime()


def _active(user):
    if frappe.db.exists(TIMER_DT, user):
        return frappe.get_doc(TIMER_DT, user)
    return None


def _elapsed(t):
    secs = int(t.accumulated_seconds or 0)
    if t.status == "Running" and t.start_time:
        secs += int((_now() - frappe.utils.get_datetime(t.start_time)).total_seconds())
    return max(0, secs)


@frappe.whitelist()
def get_active():
    """Return the current user's running/paused timer (to restore after refresh)."""
    pmperm.require_pm_access()
    t = _active(frappe.session.user)
    if not t:
        return {"active": False}
    return {"active": True, "task": t.task, "project": t.project,
            "status": t.status, "elapsed_seconds": _elapsed(t)}


@frappe.whitelist()
def start(task):
    pmperm.require_pm_access()
    user = frappe.session.user
    if not task:
        frappe.throw(_("Task is required."))
    doc = frappe.get_doc("Task", task)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to start a timer on this task."), frappe.PermissionError)
    # G4.3: cannot start new worktime on a terminal task. Reopen first.
    pmperm.assert_task_not_terminal(
        doc, _("Không thể bắt đầu giờ trên nhiệm vụ đã hoàn thành/huỷ. Vui lòng Reopen trước."))
    existing = _active(user)
    if existing:
        frappe.throw(_("You already have a running timer on task {0}. Stop it first.").format(existing.task))
    t = frappe.get_doc({
        "doctype": TIMER_DT, "user": user, "task": task,
        "project": doc.get("project"), "start_time": _now(),
        "accumulated_seconds": 0, "status": "Running",
    })
    t.insert(ignore_permissions=True)
    return get_active()


@frappe.whitelist()
def pause():
    pmperm.require_pm_access()
    t = _active(frappe.session.user)
    if not t:
        frappe.throw(_("No active timer."))
    if t.status == "Running":
        t.accumulated_seconds = _elapsed(t)
        t.start_time = None
        t.status = "Paused"
        t.save(ignore_permissions=True)
    return get_active()


@frappe.whitelist()
def resume():
    pmperm.require_pm_access()
    t = _active(frappe.session.user)
    if not t:
        frappe.throw(_("No active timer."))
    # G4.3: cannot resume a paused timer once its task is terminal. Stop is still
    # allowed (to flush already-accumulated time); resume is not.
    pmperm.assert_task_not_terminal(
        frappe.get_doc("Task", t.task),
        _("Nhiệm vụ đã hoàn thành/huỷ — không thể tiếp tục timer. Vui lòng Reopen trước."))
    if t.status == "Paused":
        t.start_time = _now()
        t.status = "Running"
        t.save(ignore_permissions=True)
    return get_active()


@frappe.whitelist()
def stop(description=None):
    pmperm.require_pm_access()
    user = frappe.session.user
    t = _active(user)
    if not t:
        frappe.throw(_("No active timer."))
    total_secs = _elapsed(t)
    hours = round(total_secs / 3600.0, 4)
    task, project, started = t.task, t.project, t.start_time
    # Durable worktime -> native Timesheet (from_time = when the timer started).
    ts_name = pmts._create_timesheet(user, task, project, hours, description,
                                     from_time=started or _now())
    frappe.delete_doc(TIMER_DT, t.name, ignore_permissions=True, force=True)
    frappe.db.commit()
    return {"timesheet": ts_name, "task": task, "hours": hours, "seconds": total_secs}
