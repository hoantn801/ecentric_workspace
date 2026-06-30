"""PM v2 - Recurring tasks (custom PM Recurrence + daily scheduler).

The custom DocType PM Recurrence holds the rule; a daily scheduler (run_due)
clones the source Task into a new Task per occurrence. NO native Auto Repeat;
native Task is NOT modified. Frequencies: Daily / Weekly / Biweekly / Monthly.

Duplicate prevention: generate exactly when next_run_date <= today, then advance
next_run_date + record last_run_date (idempotent guard). One active recurrence
per source_task. Permission enforced in this service layer.
"""

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as _assign_add
from frappe.utils import nowdate, getdate, add_days, add_months

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm.api import notifications as pmnotif

DT = "PM Recurrence"
_DAYS = {"Daily": 1, "Weekly": 7, "Biweekly": 14}
_FREQ = ("Daily", "Weekly", "Biweekly", "Monthly")


def _advance(d, frequency):
    d = getdate(d)
    if frequency == "Monthly":
        return add_months(d, 1)
    return add_days(d, _DAYS.get(frequency, 1))


def _active_rule_for(task):
    rows = frappe.get_all(DT, filters={"source_task": task, "status": ["in", ["Active", "Paused"]]},
                          fields=["name"], limit_page_length=1)
    return rows[0]["name"] if rows else None


def _as_dict(r):
    return {
        "name": r.name, "source_task": r.source_task, "project": r.project,
        "frequency": r.frequency, "status": r.status,
        "start_date": str(r.start_date) if r.start_date else None,
        "next_run_date": str(r.next_run_date) if r.next_run_date else None,
        "end_date": str(r.end_date) if r.end_date else None,
        "max_occurrences": r.max_occurrences or 0, "occurrences_done": r.occurrences_done or 0,
        "last_task": r.last_task, "last_run_date": str(r.last_run_date) if r.last_run_date else None,
        "checklist_template": r.get("checklist_template"),
    }


def _manage(name):
    pmperm.require_pm_access()
    r = frappe.get_doc(DT, name)
    me = frappe.session.user
    ok = (pmperm.can_see_all_pm_data(me) or r.owner == me
          or pmperm.can_view_task(frappe.get_doc("Task", r.source_task).as_dict(), me))
    if not ok:
        frappe.throw(_("Not permitted."), frappe.PermissionError)
    return r


# --------------------------------------------------------------------------
# CRUD / control (service-layer permission)
# --------------------------------------------------------------------------
@frappe.whitelist()
def create(source_task, frequency, start_date=None, end_date=None, max_occurrences=None,
           checklist_template=None):
    pmperm.require_pm_access()
    user = frappe.session.user
    if not source_task or not frequency:
        frappe.throw(_("Source task and frequency are required."))
    if frequency not in _FREQ:
        frappe.throw(_("Invalid frequency."))
    doc = frappe.get_doc("Task", source_task)
    if not pmperm.can_view_task(doc.as_dict(), user):
        frappe.throw(_("Not permitted to make this task recurring."), frappe.PermissionError)
    if _active_rule_for(source_task):
        frappe.throw(_("This task already has an active recurrence. Pause or cancel it first."))
    sd = getdate(start_date) if start_date else getdate(nowdate())
    r = frappe.get_doc({
        "doctype": DT, "source_task": source_task, "project": doc.get("project"),
        "frequency": frequency, "start_date": sd, "next_run_date": sd,
        "end_date": getdate(end_date) if end_date else None,
        "max_occurrences": int(max_occurrences) if max_occurrences else 0,
        "occurrences_done": 0, "status": "Active",
        "checklist_template": checklist_template or None,  # G2: optional; unchanged if None
    })
    r.insert(ignore_permissions=True)
    return _as_dict(r)


@frappe.whitelist()
def create_with_task(subject, frequency, project=None, assignee=None, description=None,
                     priority=None, exp_start_date=None, exp_end_date=None,
                     pm_start_time=None, pm_end_time=None, start_date=None, end_date=None,
                     max_occurrences=None, checklist_template=None, labels=None):
    """G4.11: create a NEW base task AND its recurrence rule in ONE transaction. If the rule
    fails to create, the base task insert is rolled back -> no partial state. Permission goes
    through tasks.create / labels.set_task_labels / create (each runs its own service guards).
    No subtree clone."""
    pmperm.require_pm_access()
    if not subject or not frequency:
        frappe.throw(_("Subject and frequency are required."))
    from ecentric_workspace.pm.api import tasks as pmtasks
    from ecentric_workspace.pm.api import labels as pmlabels
    try:
        t = pmtasks.create(
            project or "", subject, priority=priority,
            exp_start_date=exp_start_date, exp_end_date=exp_end_date,
            description=description, assignee=assignee,
            pm_start_time=pm_start_time, pm_end_time=pm_end_time)
        task_name = t["name"]
        if labels:
            pmlabels.set_task_labels(task_name, labels)
        rule = create(source_task=task_name, frequency=frequency, start_date=start_date,
                      end_date=end_date, max_occurrences=max_occurrences,
                      checklist_template=checklist_template)
    except Exception:
        frappe.db.rollback()
        raise
    return {"task": task_name, "rule": rule}


@frappe.whitelist()
def get_for_task(task):
    pmperm.require_pm_access()
    name = _active_rule_for(task)
    if not name:
        return {"exists": False}
    out = _as_dict(frappe.get_doc(DT, name))
    out["exists"] = True
    return out


@frappe.whitelist()
def list(task=None, project=None):
    pmperm.require_pm_access()
    me = frappe.session.user
    conds = {}
    if task:
        conds["source_task"] = task
    if project:
        conds["project"] = project
    rows = frappe.get_all(
        DT, filters=conds,
        fields=["name", "source_task", "project", "frequency", "next_run_date",
                "occurrences_done", "last_task", "status", "end_date", "max_occurrences",
                "last_run_date",  # lets the UI identify tasks generated TODAY
                "checklist_template"],  # G2: rule's linked checklist template
        order_by="modified desc", limit_page_length=200)
    if pmperm.can_see_all_pm_data(me):
        return {"rows": rows}
    out = [x for x in rows if (x.get("project") and pmperm.can_view_project(x["project"], me))
           or frappe.db.get_value("Task", x.get("source_task"), "owner") == me]
    return {"rows": out}


@frappe.whitelist()
def pause(name):
    r = _manage(name)
    if r.status == "Active":
        r.status = "Paused"
        r.save(ignore_permissions=True)
    return _as_dict(r)


@frappe.whitelist()
def resume(name):
    r = _manage(name)
    if r.status == "Paused":
        r.status = "Active"
        r.save(ignore_permissions=True)
    return _as_dict(r)


@frappe.whitelist()
def cancel(name):
    r = _manage(name)
    r.status = "Cancelled"
    r.save(ignore_permissions=True)
    return _as_dict(r)


# --------------------------------------------------------------------------
# Scheduler (daily) - idempotent generation
# --------------------------------------------------------------------------
def _clone(r, occ_date):
    src = frappe.get_doc("Task", r.source_task)
    fields = {
        "doctype": "Task", "subject": src.subject, "description": src.get("description"),
        "priority": src.get("priority"), "project": src.get("project"),
        "parent_task": src.get("parent_task"), "exp_start_date": occ_date,
        # G4.11: snapshot the source task's optional time-of-day window onto each generated task.
        "pm_start_time": src.get("pm_start_time"), "pm_end_time": src.get("pm_end_time"),
    }
    if src.get("exp_start_date") and src.get("exp_end_date"):
        dur = (getdate(src.exp_end_date) - getdate(src.exp_start_date)).days
        fields["exp_end_date"] = add_days(occ_date, max(0, dur))
    t = frappe.get_doc(fields)
    t.insert(ignore_permissions=True)  # active workflow sets workflow_state=Backlog on insert
    # F1: inherit the source task's assignee(s) so the generated daily task lands in the
    # right person's "Việc của tôi". notify=0 -> no daily assignment spam (the recurring
    # notification below still goes to the rule owner). Never fail generation on assign error.
    try:
        users = [u for u in frappe.parse_json(src.get("_assign") or "[]") if u]
        if users:
            _assign_add({"doctype": "Task", "name": t.name, "assign_to": users, "notify": 0})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Recurring assignment failed: " + t.name)
    # G2: snapshot the rule's checklist template into the generated task's pm_checklist.
    # SNAPSHOT (copy) -> later template edits never mutate past generated tasks (auditable).
    # Missing/inactive/empty template -> task still created (never fail generation).
    try:
        tmpl_name = r.get("checklist_template")
        if tmpl_name and frappe.db.exists("PM Checklist Template", tmpl_name):
            tmpl = frappe.get_doc("PM Checklist Template", tmpl_name)
            if tmpl.get("is_active"):
                items = sorted(tmpl.get("items") or [], key=lambda x: (x.idx or 0))
                for it in items:
                    t.append("pm_checklist", {
                        "item_label": it.item_label,
                        "is_required": it.is_required,
                        "is_done": 0,
                        # G2.1: store the template item ROW ID for stable traceability;
                        # fall back to the label only if the row name is missing.
                        "source_template_item": (it.name or it.item_label),
                    })
                if items:
                    t.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Recurring checklist copy failed: " + t.name)
    # G4.9: snapshot the source task's labels onto the generated task (copy, not a live link;
    # later catalogue edits never mutate past generated tasks). Inactive labels already on the
    # source are preserved. Never fail generation on a label-copy error.
    try:
        seen = set()
        for a in frappe.get_all("PM Task Label Assignment", filters={"task": r.source_task},
                                fields=["label"], limit_page_length=0):
            lid = a.get("label")
            if not lid or lid in seen:
                continue
            seen.add(lid)
            frappe.get_doc({"doctype": "PM Task Label Assignment",
                            "task": t.name, "label": lid}).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Recurring label copy failed: " + t.name)
    return t.name


def _process(name, today):
    r = frappe.get_doc(DT, name)
    if r.status != "Active" or not r.next_run_date:
        return
    nrd = getdate(r.next_run_date)
    if nrd > today:
        return
    if r.end_date and nrd > getdate(r.end_date):
        r.status = "Completed"; r.save(ignore_permissions=True); return
    if r.max_occurrences and (r.occurrences_done or 0) >= r.max_occurrences:
        r.status = "Completed"; r.save(ignore_permissions=True); return
    # idempotent guard: never generate twice for the same date
    if r.last_run_date and getdate(r.last_run_date) == nrd:
        r.next_run_date = _advance(nrd, r.frequency)
        r.save(ignore_permissions=True)
        return
    new_task = _clone(r, nrd)
    try:
        pmnotif.notify_users([r.owner], "Recurring tao nhiem vu moi: " +
                             (frappe.db.get_value("Task", new_task, "subject") or new_task),
                             new_task, from_user="Administrator")
    except Exception:
        pass
    r.occurrences_done = (r.occurrences_done or 0) + 1
    r.last_task = new_task
    r.last_run_date = nrd
    r.next_run_date = _advance(nrd, r.frequency)
    if (r.end_date and getdate(r.next_run_date) > getdate(r.end_date)) or \
       (r.max_occurrences and r.occurrences_done >= r.max_occurrences):
        r.status = "Completed"
    r.save(ignore_permissions=True)


def run_due():
    """Daily scheduler entry point (registered in hooks scheduler_events)."""
    today = getdate(nowdate())
    rules = frappe.get_all(DT, filters={"status": "Active", "next_run_date": ["<=", today]},
                           fields=["name"])
    for row in rules:
        try:
            _process(row["name"], today)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "PM Recurrence run_due")


@frappe.whitelist()
def run_due_once():
    """Admin/test trigger to run the scheduler now."""
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Admin only."), frappe.PermissionError)
    run_due()
    return {"ok": True}
