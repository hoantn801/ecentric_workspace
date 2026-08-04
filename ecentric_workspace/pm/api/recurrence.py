"""PM v2 - Recurring tasks (SELF-CONTAINED PM Recurrence + daily scheduler).

Redesign 2026-08-04 (Cách 2): a `PM Recurrence` rule now holds its OWN template
(subject, description, priority, assignees, time window, checklist items and
one level of sub-tasks) directly on the rule + its child tables. There is NO
`source_task` template any more — the daily scheduler (run_due) builds each
occurrence's Task purely from the rule's own data.

  * Frequencies: Daily / Weekly / Biweekly / Monthly (monthly anchored to start day).
  * Duplicate prevention: generate exactly when next_run_date <= today, then advance
    next_run_date + record last_run_date (idempotent guard).
  * NO native Auto Repeat; native Task is NOT modified.
  * Permission enforced in this service layer (require_pm_access + _manage).

Legacy `source_task` / `checklist_template` columns are kept for audit/rollback but
are no longer written or read by generation (see patch p017/p018 for the migration).
"""

import json
import re
import time

import frappe
from frappe import _
from frappe.exceptions import QueryDeadlockError
from frappe.desk.form.assign_to import add as _assign_add
from frappe.utils import nowdate, getdate, add_days, add_months

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm.api import notifications as pmnotif

DT = "PM Recurrence"
_DAYS = {"Daily": 1, "Weekly": 7, "Biweekly": 14}
_FREQ = ("Daily", "Weekly", "Biweekly", "Monthly")
_PRIORITIES = ("Low", "Medium", "High", "Urgent")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _advance(d, frequency, anchor=None, occ=None):
    d = getdate(d)
    if frequency == "Monthly":
        # audit D5: anchor monthly occurrences to the rule's start day-of-month (clamped per month)
        # so a rule starting on the 31st does not permanently drift to the 28th after February.
        if anchor and occ is not None:
            return add_months(getdate(anchor), int(occ))
        return add_months(d, 1)
    return add_days(d, _DAYS.get(frequency, 1))


def _load_list(v):
    """Parse a JSON list (or already-list); anything else -> []."""
    if v in (None, ""):
        return []
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def _clean_assignees(v):
    """Return the subset of `v` (JSON list / list of emails) that are enabled Users. Order kept,
    de-duped. Invalid/disabled entries are silently dropped (never a 500)."""
    raw = [u for u in _load_list(v) if u]
    if not raw:
        return []
    valid = set(u["name"] for u in frappe.get_all(
        "User", filters={"name": ["in", list(set(raw))], "enabled": 1},
        fields=["name"], limit_page_length=0, ignore_permissions=True))
    out = []
    for u in raw:
        if u in valid and u not in out:
            out.append(u)
    return out


def _clean_priority(v):
    return v if v in _PRIORITIES else None


def _safe_getdate(v, label):
    """G5.1: parse a date or friendly-throw (a malformed/impossible date must never 500)."""
    try:
        return getdate(v)
    except Exception:
        frappe.throw(_("{0} không hợp lệ.").format(label))


def _safe_max_occ(v):
    """max_occurrences is optional. Omitted/blank -> 0 (the 'unlimited' sentinel). When SUPPLIED it
    must be a POSITIVE integer (>=1); 0, negatives, floats and non-numerics are friendly-rejected."""
    if v in (None, ""):
        return 0
    s = str(v).strip()
    if not re.match(r"^\d+$", s) or int(s) < 1:
        frappe.throw(_("Số lần lặp tối đa phải là số nguyên dương."))
    return int(s)


def _clean_int(v, default=0):
    try:
        n = int(str(v).strip())
        return n if n >= 0 else default
    except Exception:
        return default


# --------------------------------------------------------------------------
# Template <-> rule serialization
# --------------------------------------------------------------------------
def _apply_template(r, subject=None, description=None, priority=None, assignees=None,
                    template_start_time=None, template_end_time=None, duration_days=None,
                    project=None, checklist_items=None, subtasks=None, labels=None,
                    is_create=False):
    """Write template fields + child tables onto rule doc `r`. On update, a field left as None is
    UNCHANGED; child tables / labels are replaced only when a (possibly empty) list is supplied."""
    if subject is not None:
        subject = (subject or "").strip()
        if is_create and not subject:
            frappe.throw(_("Tên nhiệm vụ là bắt buộc."))
        if subject:
            r.template_subject = subject
    if description is not None:
        r.template_description = description
    if priority is not None:
        r.template_priority = _clean_priority(priority)
    if assignees is not None:
        r.template_assignees = json.dumps(_clean_assignees(assignees))
    if template_start_time is not None:
        r.template_start_time = template_start_time or None
    if template_end_time is not None:
        r.template_end_time = template_end_time or None
    if duration_days is not None:
        r.template_duration_days = _clean_int(duration_days, 0)
    if project is not None:
        r.project = project or None
    # child: checklist items (replace-all when a list is supplied)
    if checklist_items is not None:
        r.set("pm_checklist_items", [])
        for it in _load_list(checklist_items):
            lbl = (it.get("item_label") if isinstance(it, dict) else str(it)).strip() \
                if it is not None else ""
            if not lbl:
                continue
            req = 1
            if isinstance(it, dict) and it.get("is_required") in (0, "0", False, "false", "False"):
                req = 0
            r.append("pm_checklist_items", {"item_label": lbl, "is_required": req})
    # child: sub-tasks (one level; replace-all when supplied)
    if subtasks is not None:
        r.set("pm_subtasks", [])
        for st in _load_list(subtasks):
            if not isinstance(st, dict):
                continue
            subj = (st.get("subject") or "").strip()
            if not subj:
                continue
            r.append("pm_subtasks", {
                "subject": subj,
                "description": st.get("description") or None,
                "priority": _clean_priority(st.get("priority")),
                "assignees": json.dumps(_clean_assignees(st.get("assignees"))),
            })
    # labels (JSON list of PM Task Label names that still exist)
    if labels is not None:
        names = [l for l in _load_list(labels) if l]
        if names:
            exist = set(x["name"] for x in frappe.get_all(
                "PM Task Label", filters={"name": ["in", list(set(names))]},
                fields=["name"], limit_page_length=0, ignore_permissions=True))
            names = [l for l in names if l in exist]
        r.template_labels = json.dumps(names)


def _template_dict(r):
    """Serialize a rule's template (fields + child tables + labels) for the editor."""
    items = [{"item_label": c.item_label, "is_required": 1 if c.is_required else 0}
             for c in sorted(r.get("pm_checklist_items") or [], key=lambda x: (x.idx or 0))]
    subs = [{"subject": c.subject, "description": c.get("description"),
             "priority": c.get("priority"), "assignees": _load_list(c.get("assignees"))}
            for c in sorted(r.get("pm_subtasks") or [], key=lambda x: (x.idx or 0))]
    return {
        "template_subject": r.get("template_subject"),
        "template_description": r.get("template_description"),
        "template_priority": r.get("template_priority"),
        "assignees": _load_list(r.get("template_assignees")),
        "template_start_time": r.get("template_start_time"),
        "template_end_time": r.get("template_end_time"),
        "template_duration_days": r.get("template_duration_days") or 0,
        "checklist_items": items,
        "subtasks": subs,
        "labels": _load_list(r.get("template_labels")),
    }


def _as_dict(r):
    out = {
        "name": r.name, "project": r.project,
        "frequency": r.frequency, "status": r.status,
        "start_date": str(r.start_date) if r.start_date else None,
        "next_run_date": str(r.next_run_date) if r.next_run_date else None,
        "end_date": str(r.end_date) if r.end_date else None,
        "max_occurrences": r.max_occurrences or 0, "occurrences_done": r.occurrences_done or 0,
        "last_task": r.last_task, "last_run_date": str(r.last_run_date) if r.last_run_date else None,
    }
    out.update(_template_dict(r))
    return out


def _manage(name):
    """Permission gate for a single rule: PM leader / owner / project viewer. No source_task."""
    pmperm.require_pm_access()
    r = frappe.get_doc(DT, name)
    me = frappe.session.user
    ok = (pmperm.can_see_all_pm_data(me) or r.owner == me
          or (r.project and pmperm.can_view_project(r.project, me)))
    if not ok:
        frappe.throw(_("Not permitted."), frappe.PermissionError)
    return r


# --------------------------------------------------------------------------
# CRUD / control (service-layer permission)
# --------------------------------------------------------------------------
@frappe.whitelist()
def create(subject, frequency, description=None, priority=None, assignees=None, project=None,
           template_start_time=None, template_end_time=None, duration_days=None,
           checklist_items=None, subtasks=None, labels=None,
           start_date=None, end_date=None, max_occurrences=None):
    """Create a SELF-CONTAINED recurrence rule. No source task is created or referenced."""
    pmperm.require_pm_access()
    subject = (subject or "").strip()
    if not subject or not frequency:
        frappe.throw(_("Tên nhiệm vụ và tần suất là bắt buộc."))
    if frequency not in _FREQ:
        frappe.throw(_("Tần suất không hợp lệ."))
    sd = _safe_getdate(start_date, _("Ngày bắt đầu")) if start_date else getdate(nowdate())
    ed = _safe_getdate(end_date, _("Ngày kết thúc")) if end_date else None
    if ed and ed < sd:
        frappe.throw(_("Ngày kết thúc không được trước ngày bắt đầu."))
    mo = _safe_max_occ(max_occurrences)
    r = frappe.get_doc({
        "doctype": DT, "frequency": frequency,
        "start_date": sd, "next_run_date": sd, "end_date": ed,
        "max_occurrences": mo, "occurrences_done": 0, "status": "Active",
    })
    _apply_template(r, subject=subject, description=description, priority=priority,
                    assignees=assignees, template_start_time=template_start_time,
                    template_end_time=template_end_time, duration_days=duration_days,
                    project=project, checklist_items=checklist_items, subtasks=subtasks,
                    labels=labels, is_create=True)
    r.insert(ignore_permissions=True)
    return _as_dict(r)


@frappe.whitelist()
def update_template(name, subject=None, description=None, priority=None, assignees=None,
                    project=None, template_start_time=None, template_end_time=None,
                    duration_days=None, checklist_items=None, subtasks=None, labels=None,
                    frequency=None, start_date=None, end_date=None, max_occurrences=None):
    """Edit a rule's template (fields + checklist + sub-tasks) AND/OR its schedule, inline. Only
    supplied arguments are changed. This is the 'sửa task/subtask ngay trong quy tắc' entry point."""
    r = _manage(name)
    if frequency is not None:
        if frequency not in _FREQ:
            frappe.throw(_("Tần suất không hợp lệ."))
        r.frequency = frequency
    if start_date is not None:
        r.start_date = _safe_getdate(start_date, _("Ngày bắt đầu")) if start_date else None
    if end_date is not None:
        r.end_date = _safe_getdate(end_date, _("Ngày kết thúc")) if end_date else None
    if r.start_date and r.end_date and getdate(r.end_date) < getdate(r.start_date):
        frappe.throw(_("Ngày kết thúc không được trước ngày bắt đầu."))
    if max_occurrences is not None:
        r.max_occurrences = _safe_max_occ(max_occurrences)
    _apply_template(r, subject=subject, description=description, priority=priority,
                    assignees=assignees, template_start_time=template_start_time,
                    template_end_time=template_end_time, duration_days=duration_days,
                    project=project, checklist_items=checklist_items, subtasks=subtasks,
                    labels=labels, is_create=False)
    r.save(ignore_permissions=True)
    return _as_dict(r)


@frappe.whitelist()
def get(name):
    """Full rule detail (template fields + checklist + sub-tasks + labels + meta) for the editor."""
    r = _manage(name)
    out = _as_dict(r)
    out["owner"] = r.owner
    out["creation"] = str(r.creation) if r.get("creation") else None
    out["modified"] = str(r.modified) if r.get("modified") else None
    out["modified_by"] = r.modified_by
    return out


@frappe.whitelist()
def list(project=None):
    pmperm.require_pm_access()
    me = frappe.session.user
    conds = {}
    if project:
        conds["project"] = project
    rows = frappe.get_all(
        DT, filters=conds,
        fields=["name", "template_subject", "project", "frequency", "next_run_date",
                "occurrences_done", "last_task", "status", "end_date", "max_occurrences",
                "last_run_date"],
        order_by="modified desc", limit_page_length=200)
    if pmperm.can_see_all_pm_data(me):
        return {"rows": rows}
    out = [x for x in rows if (x.get("project") and pmperm.can_view_project(x["project"], me))
           or frappe.db.get_value(DT, x["name"], "owner") == me]
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
# Scheduler (daily) - idempotent generation, built purely from the rule's template
# --------------------------------------------------------------------------
def _clone(r, occ_date):
    """Build ONE occurrence Task (+ checklist + labels + one level of sub-tasks) from rule `r`.
    Every side-part is wrapped so a partial failure never aborts the whole generation."""
    fields = {
        "doctype": "Task", "subject": r.get("template_subject") or "(no subject)",
        "description": r.get("template_description"),
        "priority": _clean_priority(r.get("template_priority")),
        "project": r.get("project"), "parent_task": None, "exp_start_date": occ_date,
        "pm_start_time": r.get("template_start_time"), "pm_end_time": r.get("template_end_time"),
    }
    dur = _clean_int(r.get("template_duration_days"), 0)
    if dur > 0:
        fields["exp_end_date"] = add_days(occ_date, dur)
    t = frappe.get_doc(fields)
    t.insert(ignore_permissions=True)  # active workflow sets workflow_state=Backlog on insert
    # assignees (notify=0 -> no daily assignment spam; recurring notice below goes to owner)
    try:
        users = _load_list(r.get("template_assignees"))
        if users:
            _assign_add({"doctype": "Task", "name": t.name, "assign_to": users, "notify": 0})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Recurring assignment failed: " + t.name)
    # checklist snapshot
    try:
        citems = sorted(r.get("pm_checklist_items") or [], key=lambda x: (x.idx or 0))
        for it in citems:
            t.append("pm_checklist", {
                "item_label": it.item_label, "is_required": it.is_required, "is_done": 0,
                "source_template_item": (it.name or it.item_label),
            })
        if citems:
            t.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Recurring checklist copy failed: " + t.name)
    # labels snapshot (attach existing labels; missing labels skipped)
    try:
        want = [l for l in _load_list(r.get("template_labels")) if l]
        if want:
            exist = set(x["name"] for x in frappe.get_all(
                "PM Task Label", filters={"name": ["in", list(set(want))]},
                fields=["name"], limit_page_length=0))
            seen = set()
            for lid in want:
                if lid in exist and lid not in seen:
                    seen.add(lid)
                    frappe.get_doc({"doctype": "PM Task Label Assignment",
                                    "task": t.name, "label": lid}).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Recurring label copy failed: " + t.name)
    # sub-tasks (one level); nested-set writes covered by run_due's deadlock retry
    try:
        for st in sorted(r.get("pm_subtasks") or [], key=lambda x: (x.idx or 0)):
            child = frappe.get_doc({
                "doctype": "Task", "subject": st.subject,
                "description": st.get("description"),
                "priority": _clean_priority(st.get("priority")),
                "project": r.get("project"), "parent_task": t.name,
                "exp_start_date": occ_date,
            })
            child.insert(ignore_permissions=True)
            try:
                cu = _clean_assignees(st.get("assignees")) or _load_list(r.get("template_assignees"))
                if cu:
                    _assign_add({"doctype": "Task", "name": child.name,
                                 "assign_to": cu, "notify": 0})
            except Exception:
                pass
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Recurring subtask copy failed: " + t.name)
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
        r.next_run_date = _advance(nrd, r.frequency, r.start_date, r.occurrences_done)
        r.save(ignore_permissions=True)
        return
    new_task = _clone(r, nrd)
    try:
        pmnotif.notify_users([r.owner], "Recurring tao nhiem vu moi: " +
                             (frappe.db.get_value("Task", new_task, "subject") or new_task),
                             new_task, from_user="Administrator")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM Recurrence notify")
    r.occurrences_done = (r.occurrences_done or 0) + 1
    r.last_task = new_task
    r.last_run_date = nrd
    r.next_run_date = _advance(nrd, r.frequency, r.start_date, r.occurrences_done)
    if (r.end_date and getdate(r.next_run_date) > getdate(r.end_date)) or \
       (r.max_occurrences and r.occurrences_done >= r.max_occurrences):
        r.status = "Completed"
    r.save(ignore_permissions=True)


def _process_with_retry(name, today, attempts=4):
    """Generate for one rule, retrying on transient DB deadlocks (MySQL 1213). ERPNext Task
    nested-set updates can deadlock under contention. Non-deadlock errors are logged + skipped."""
    for i in range(attempts):
        try:
            _process(name, today)
            frappe.db.commit()
            return True
        except QueryDeadlockError:
            frappe.db.rollback()
            if i == attempts - 1:
                frappe.log_error(frappe.get_traceback(),
                                 "PM Recurrence run_due deadlock (gave up): " + str(name))
            else:
                time.sleep(0.4 * (i + 1))
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "PM Recurrence run_due")
            return False
    return False


def run_due():
    """Daily scheduler entry point (registered in hooks scheduler_events)."""
    today = getdate(nowdate())
    rules = frappe.get_all(DT, filters={"status": "Active", "next_run_date": ["<=", today]},
                           fields=["name"])
    for row in rules:
        _process_with_retry(row["name"], today)


@frappe.whitelist()
def generate_now():
    """On-demand catch-up generation (same idempotent logic as the 00:00 scheduler), scoped to
    rules the caller owns, or all for a PM leader. Catches up missed days up to today (capped)."""
    pmperm.require_pm_access()
    user = frappe.session.user
    leader = pmperm.can_transition_any_task(user)
    today = getdate(nowdate())
    rules = frappe.get_all(DT, filters={"status": "Active", "next_run_date": ["<=", today]},
                           fields=["name", "owner"])
    generated = 0
    for row in rules:
        if not (leader or row.get("owner") == user):
            continue
        for _n in range(60):  # catch up missed occurrences, capped to avoid runaway
            b = frappe.db.get_value(DT, row["name"],
                                    ["occurrences_done", "next_run_date", "status"], as_dict=True)
            if (not b or b.status != "Active" or not b.next_run_date
                    or getdate(b.next_run_date) > today):
                break
            if not _process_with_retry(row["name"], today):
                break
            after = frappe.db.get_value(DT, row["name"], "occurrences_done") or 0
            if after > (b.occurrences_done or 0):
                generated += 1
    return {"generated": generated}


@frappe.whitelist()
def run_due_once():
    """Admin/test trigger to run the scheduler now."""
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Admin only."), frappe.PermissionError)
    run_due()
    return {"ok": True}
