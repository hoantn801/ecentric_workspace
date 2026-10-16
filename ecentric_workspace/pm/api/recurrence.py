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
from frappe.utils import nowdate, getdate, add_days, add_months, get_last_day

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm.api import notifications as pmnotif

DT = "PM Recurrence"
_DAYS = {"Daily": 1, "Weekly": 7, "Biweekly": 14}
_FREQ = ("Daily", "Weekly", "Biweekly", "Monthly")
_PRIORITIES = ("Low", "Medium", "High", "Urgent")

# PM redesign (16/10/2026, patch p028): completion flags a rule carries over to every occurrence,
# same meaning as the Task fields set by tasks.create (rule field -> Task field).
#   split_per_assignee -> parent gets ec_split_parent=1 + one child per assignee
#   auto_close         -> Task.ec_auto_close (split parent closes itself when the last child is Done)
#   review_required    -> Task.ec_review_required (non-giver's Xong goes to Review)
_FLAG_FIELDS = ("split_per_assignee", "auto_close", "review_required")

# NOTE: this module defines a whitelisted `list()` endpoint which shadows the builtin `list`.
# Capture the builtin here (before `def list`) so isinstance()/list() calls stay correct.
_LIST = list


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _clean_weekdays(v):
    """Normalize a weekday selection to a sorted list of ints Mon=0..Sun=6 (dedup, in-range)."""
    out = []
    for x in _load_list(v):
        try:
            n = int(x)
        except Exception:
            continue
        if 0 <= n <= 6 and n not in out:
            out.append(n)
    return sorted(out)


def _clean_monthday(v):
    if v in (None, ""):
        return None
    try:
        return min(max(int(v), 1), 31)
    except Exception:
        return None


def _weekly_days(r):
    """Selected weekdays for a Weekly rule; default = the rule's start weekday."""
    days = _clean_weekdays(r.get("weekly_days"))
    if not days:
        base = r.get("start_date") or r.get("next_run_date") or nowdate()
        days = [getdate(base).weekday()]
    return days


def _month_on_day(base, day):
    """`base`'s month with day-of-month `day`, clamped to that month's last day."""
    base = getdate(base)
    last = getdate(get_last_day(base)).day
    return base.replace(day=min(max(int(day or base.day), 1), last))


def _advance(r, current):
    """Next occurrence date strictly AFTER `current`, honoring frequency + interval + (weekly)
    selected weekdays + (monthly) day-of-month. Monthly anchors to the start month via
    occurrences_done so it never drifts. `r` is the rule doc/dict."""
    current = getdate(current)
    freq = r.get("frequency")
    interval = max(_clean_int(r.get("interval"), 1), 1)
    if freq == "Weekly":
        days = _weekly_days(r)
        anchor = getdate(r.get("start_date") or current)
        anchor_mon = add_days(anchor, -anchor.weekday())
        d = current
        for _ in range(400):  # bounded forward search
            d = add_days(d, 1)
            if d.weekday() in days:
                wk = (add_days(d, -d.weekday()) - anchor_mon).days // 7
                if wk % interval == 0:
                    return d
        return add_days(current, 7 * interval)  # safety net
    if freq == "Monthly":
        # next month after `current`, on the chosen day (clamped). Re-targeting monthly_day each
        # step means a 31st rule recovers to 31 in long months (no permanent Feb-drift).
        day = r.get("monthly_day") or getdate(r.get("start_date") or current).day
        return _month_on_day(add_months(current, interval), day)
    if freq == "Biweekly":  # legacy frequency kept for pre-existing rules
        return add_days(current, 14 * interval)
    return add_days(current, interval)  # Daily


def _first_occurrence(frequency, start, weekly_days=None, monthly_day=None):
    """First occurrence date ON/AFTER `start` that matches the pattern (so a Weekly rule starts on
    the first selected weekday, a Monthly rule on day-X of this month or next)."""
    start = getdate(start)
    if frequency == "Weekly":
        days = _clean_weekdays(weekly_days) or [start.weekday()]
        for i in range(7):
            d = add_days(start, i)
            if d.weekday() in days:
                return d
        return start
    if frequency == "Monthly":
        day = _clean_monthday(monthly_day) or start.day
        cand = _month_on_day(start, day)
        if cand < start:
            cand = _month_on_day(add_months(start, 1), day)
        return cand
    return start  # Daily


def _load_list(v):
    """Parse a JSON list (or already-list); anything else -> []."""
    if v in (None, ""):
        return []
    if isinstance(v, _LIST):
        return v
    try:
        out = json.loads(v)
        return out if isinstance(out, _LIST) else []
    except Exception:
        return []


def _clean_assignees(v):
    """Return the subset of `v` (JSON list / list of emails) that are enabled Users. Order kept,
    de-duped. Invalid/disabled entries are silently dropped (never a 500)."""
    raw = [u for u in _load_list(v) if u]
    if not raw:
        return []
    valid = set(u["name"] for u in frappe.get_all(
        "User", filters={"name": ["in", _LIST(set(raw))], "enabled": 1},
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
def _flag(v):
    return 0 if str(v if v is not None else "").strip().lower() in (
        "", "0", "false", "none", "null") else 1


def _apply_template(r, subject=None, description=None, priority=None, assignees=None,
                    template_start_time=None, template_end_time=None, duration_days=None,
                    project=None, checklist_items=None, subtasks=None, labels=None,
                    is_create=False, split_per_assignee=None, auto_close=None,
                    review_required=None):
    """Write template fields + child tables onto rule doc `r`. On update, a field left as None is
    UNCHANGED; child tables / labels are replaced only when a (possibly empty) list is supplied."""
    for f, v in (("split_per_assignee", split_per_assignee), ("auto_close", auto_close),
                 ("review_required", review_required)):
        if v is not None or is_create:
            r.set(f, _flag(v))
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
                "PM Task Label", filters={"name": ["in", _LIST(set(names))]},
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
        "split_per_assignee": _flag(r.get("split_per_assignee")),
        "auto_close": _flag(r.get("auto_close")),
        "review_required": _flag(r.get("review_required")),
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
        "interval": max(_clean_int(r.get("interval"), 1), 1),
        "weekly_days": _clean_weekdays(r.get("weekly_days")),
        "monthly_day": r.get("monthly_day") or None,
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
           start_date=None, end_date=None, max_occurrences=None,
           interval=None, weekly_days=None, monthly_day=None,
           split_per_assignee=None, auto_close=None, review_required=None):
    """Create a SELF-CONTAINED recurrence rule. No source task is created or referenced.
    split_per_assignee / auto_close / review_required (PM redesign) are applied to every
    generated occurrence (see _clone)."""
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
        "start_date": sd,
        "next_run_date": _first_occurrence(frequency, sd, weekly_days, monthly_day),
        "end_date": ed,
        "max_occurrences": mo, "occurrences_done": 0, "status": "Active",
        "interval": max(_clean_int(interval, 1), 1),
        "weekly_days": json.dumps(_clean_weekdays(weekly_days)),
        "monthly_day": _clean_monthday(monthly_day),
    })
    _apply_template(r, subject=subject, description=description, priority=priority,
                    assignees=assignees, template_start_time=template_start_time,
                    template_end_time=template_end_time, duration_days=duration_days,
                    project=project, checklist_items=checklist_items, subtasks=subtasks,
                    labels=labels, is_create=True, split_per_assignee=split_per_assignee,
                    auto_close=auto_close, review_required=review_required)
    r.insert(ignore_permissions=True)
    return _as_dict(r)


@frappe.whitelist()
def update_template(name, subject=None, description=None, priority=None, assignees=None,
                    project=None, template_start_time=None, template_end_time=None,
                    duration_days=None, checklist_items=None, subtasks=None, labels=None,
                    frequency=None, start_date=None, end_date=None, max_occurrences=None,
                    interval=None, weekly_days=None, monthly_day=None,
                    split_per_assignee=None, auto_close=None, review_required=None):
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
    if interval is not None:
        r.interval = max(_clean_int(interval, 1), 1)
    if weekly_days is not None:
        r.weekly_days = json.dumps(_clean_weekdays(weekly_days))
    if monthly_day is not None:
        r.monthly_day = _clean_monthday(monthly_day)
    _apply_template(r, subject=subject, description=description, priority=priority,
                    assignees=assignees, template_start_time=template_start_time,
                    template_end_time=template_end_time, duration_days=duration_days,
                    project=project, checklist_items=checklist_items, subtasks=subtasks,
                    labels=labels, is_create=False, split_per_assignee=split_per_assignee,
                    auto_close=auto_close, review_required=review_required)
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


@frappe.whitelist()
def create_from_task(task, frequency, start_date=None, end_date=None, max_occurrences=None,
                     interval=None, weekly_days=None, monthly_day=None, duration_days=None):
    """Make an EXISTING top-level task recurring: SNAPSHOT its content (subject/desc/priority/
    assignees/project/time window/duration + its checklist + one level of sub-tasks + labels) into a
    NEW self-contained rule. The task itself is left untouched. Sub-tasks cannot be made recurring
    (2-level cap)."""
    pmperm.require_pm_access()
    user = frappe.session.user
    t = frappe.get_doc("Task", task)
    if not pmperm.can_view_task(t.as_dict(), user):
        frappe.throw(_("Not permitted."), frappe.PermissionError)
    from ecentric_workspace.pm import task_flow as _tflow   # lazy: avoid import cycle
    _tflow.require_edit(t.as_dict(), user)
    if t.get("parent_task"):
        frappe.throw(_("Chỉ nhiệm vụ cấp 1 mới tạo được định kỳ (nhiệm vụ con thì không)."))
    dur = 0
    if t.get("exp_start_date") and t.get("exp_end_date"):
        dur = max(0, (getdate(t.exp_end_date) - getdate(t.exp_start_date)).days)
    if duration_days not in (None, ""):
        dur = _clean_int(duration_days, dur)  # monthly "từ ngày X đến ngày Y" overrides task span
    citems = [{"item_label": c.get("item_label"), "is_required": 1 if c.get("is_required") else 0}
              for c in (t.get("pm_checklist") or []) if c.get("item_label")]
    kids = frappe.get_all("Task", filters={"parent_task": task},
                          fields=["name", "subject", "description", "priority", "_assign",
                                  "workflow_state"],
                          order_by="creation asc", limit_page_length=0)
    split = _flag(t.get("ec_split_parent"))
    if split:
        # "Mỗi người một việc" source: the children ARE the per-person parts, not template
        # sub-tasks (otherwise every occurrence would get them twice). The people come from the
        # live children (the parent itself is assigned to the giver); steps from the first child
        # when the parent has none (pm_redesign adds form steps to each child).
        live = [k for k in kids if k.get("workflow_state") != "Cancelled"]
        people = []
        for k in live:
            for u in _people_of(k):
                if u not in people:
                    people.append(u)
        if not citems and live:
            first = frappe.get_doc("Task", live[0]["name"])
            citems = [{"item_label": c.get("item_label"),
                       "is_required": 1 if c.get("is_required") else 0}
                      for c in (first.get("pm_checklist") or []) if c.get("item_label")]
        subs = []
    else:
        people = _people_of({"name": task, "_assign": t.get("_assign")})
        subs = [{"subject": k.get("subject"), "description": k.get("description"),
                 "priority": k.get("priority"), "assignees": _people_of(k)} for k in kids]
    lbls = [a["label"] for a in frappe.get_all(
        "PM Task Label Assignment", filters={"task": task}, fields=["label"],
        limit_page_length=0) if a.get("label")]
    sd = start_date or (str(t.get("exp_start_date")) if t.get("exp_start_date") else None)
    out = create(
        subject=t.get("subject") or task, frequency=frequency,
        description=t.get("description"), priority=t.get("priority"),
        assignees=json.dumps(people), project=t.get("project"),
        template_start_time=t.get("pm_start_time"), template_end_time=t.get("pm_end_time"),
        duration_days=dur, checklist_items=json.dumps(citems), subtasks=json.dumps(subs),
        labels=json.dumps(lbls), start_date=sd, end_date=end_date,
        max_occurrences=max_occurrences, interval=interval, weekly_days=weekly_days,
        monthly_day=monthly_day, split_per_assignee=split,
        auto_close=_flag(t.get("ec_auto_close")),
        review_required=_flag(t.get("ec_review_required")))
    # The source task is the series' first occurrence: link it as last_task so "Tôi đã giao" and
    # tasks.get show the "Lặp lại" tag right away (run_due overwrites it with each new occurrence).
    try:
        frappe.db.set_value(DT, out["name"], "last_task", task, update_modified=False)
        out["last_task"] = task
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM create_from_task link " + str(task))
    return out


def _people_of(task_row):
    """Assignees of a task; when it is still unassigned because it went through "Cần đồng ý",
    the recipients of its open / accepted assignment requests (occurrences are then assigned
    directly - a recurring series does not re-ask every period)."""
    users = [u for u in _load_list(task_row.get("_assign")) if u]
    if users or not task_row.get("name"):
        return users
    try:
        rows = frappe.get_all("PM Assignment Request",
                              filters={"task": task_row["name"],
                                       "status": ["in", ["Pending", "Reschedule Proposed",
                                                         "Accepted"]]},
                              fields=["recipient", "kind"], limit_page_length=0)
    except Exception:
        return []
    out = []
    for r in rows:
        if (r.get("kind") or "Assignment") != "Deadline" and r.get("recipient") \
                and r["recipient"] not in out:
            out.append(r["recipient"])
    return out


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
    users = _load_list(r.get("template_assignees"))
    split = bool(_flag(r.get("split_per_assignee")) and len(users) > 1)
    fields["ec_review_required"] = _flag(r.get("review_required"))
    fields["ec_auto_close"] = _flag(r.get("auto_close"))
    if split:
        fields["is_group"] = 1
        fields["ec_split_parent"] = 1
    t = frappe.get_doc(fields)
    t.insert(ignore_permissions=True)  # active workflow sets workflow_state=Backlog on insert
    if split:
        _clone_split_children(r, t, occ_date, users, fields)
    # assignees (notify=0 -> no daily assignment spam; recurring notice below goes to owner)
    try:
        # split: the parent is the giver's coordination row (as in tasks.create split)
        asg = [r.get("owner")] if split and r.get("owner") else ([] if split else users)
        if asg:
            _assign_add({"doctype": "Task", "name": t.name, "assign_to": asg, "notify": 0})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Recurring assignment failed: " + t.name)
    # checklist snapshot (split: the steps live on each person's child, see _clone_split_children)
    try:
        citems = [] if split else sorted(r.get("pm_checklist_items") or [],
                                         key=lambda x: (x.idx or 0))
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
                "PM Task Label", filters={"name": ["in", _LIST(set(want))]},
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
        # split: the per-person children replace template sub-tasks (extra children would keep
        # the split parent from ever rolling up)
        for st in ([] if split else sorted(r.get("pm_subtasks") or [], key=lambda x: (x.idx or 0))):
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


def _clone_split_children(r, t, occ_date, users, fields):
    """"Mỗi người một việc" occurrence: one child per template assignee (same naming as
    tasks.create split), each with the rule's checklist + review flag. Best-effort per child."""
    citems = sorted(r.get("pm_checklist_items") or [], key=lambda x: (x.idx or 0))
    for em in users:
        try:
            who = frappe.db.get_value("User", em, "full_name") or em.split("@")[0]
            child = frappe.get_doc({
                "doctype": "Task", "subject": (fields.get("subject") or "")[:120] + " — " + who,
                "description": fields.get("description"), "priority": fields.get("priority"),
                "project": fields.get("project"), "parent_task": t.name,
                "exp_start_date": occ_date, "exp_end_date": fields.get("exp_end_date"),
                "pm_start_time": fields.get("pm_start_time"),
                "pm_end_time": fields.get("pm_end_time"),
                "ec_review_required": fields.get("ec_review_required") or 0,
            })
            for it in citems:
                child.append("pm_checklist", {
                    "item_label": it.item_label, "is_required": it.is_required, "is_done": 0,
                    "source_template_item": (it.name or it.item_label)})
            child.insert(ignore_permissions=True)
            _assign_add({"doctype": "Task", "name": child.name, "assign_to": [em], "notify": 0})
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Recurring split child failed: " + t.name)


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
        r.next_run_date = _advance(r, nrd)
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
    # BUGFIX (16/10/2026): was _advance(nrd, r.frequency, r.start_date, r.occurrences_done) - a
    # stale call from before 30a42d22 changed the signature to _advance(r, current); it raised
    # TypeError after _clone, so _process_with_retry rolled back every generated occurrence.
    r.next_run_date = _advance(r, nrd)
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
