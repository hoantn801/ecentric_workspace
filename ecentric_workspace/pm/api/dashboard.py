"""PM v2 - Dashboard summary service (PM1-T05).

Permission-scoped counts via ecentric_workspace.pm.permissions (service layer).
Definitions:
  my_tasks      - tasks assigned to the current user (_assign)
  team_tasks    - in-scope tasks (own / assigned / visible project)
  overdue       - in-scope, exp_end_date < today, status NOT IN (Completed, Cancelled)
  due_this_week - in-scope, today <= exp_end_date <= today + 7, not finished

Module path: ecentric_workspace.pm.api.dashboard
"""

import frappe

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm import task_flow as tflow

# PM workflow terminal states (PM1-T07). PM status is workflow_state, NOT native
# Task.status (which ERPNext manages on its own).
_FINISHED = ["Done", "Cancelled"]


def _mine_filter(user):
    """Quoted JSON match on _assign ('%"user"%'): the bare '%user%' form matched substrings
    (e.g. an@ inside tran@) - same canonical form as pm.permissions."""
    return ["_assign", "like", '%"{0}"%'.format(user)]


def _count(and_filters, or_filters, personal=None):
    rows = frappe.get_all(
        "Task", filters=and_filters or None, or_filters=or_filters,
        fields=["name", "project"], limit_page_length=0,
    )
    return len(tflow.drop_personal(rows, personal=personal or set()))


@frappe.whitelist()
def summary(include_personal=0):
    pmperm.require_pm_access()
    user = frappe.session.user
    today = frappe.utils.nowdate()
    week = frappe.utils.add_days(today, 7)

    scope = pmperm.task_scope_or_filters(user)  # None = all in PM
    mine = [_mine_filter(user)]
    personal = set() if tflow.truthy(include_personal) else tflow.personal_log_projects()

    overdue_f = {"exp_end_date": ["<", today], "workflow_state": ["not in", _FINISHED]}
    week_f = {"exp_end_date": ["between", [today, week]], "workflow_state": ["not in", _FINISHED]}

    return {
        "my_tasks": _count(None, mine, personal),
        "team_tasks": _count(None, scope, personal),
        "overdue": _count(overdue_f, scope, personal),
        "due_this_week": _count(week_f, scope, personal),
        "scope": "all" if scope is None else "department",
    }


def _assignees(t):
    try:
        return frappe.parse_json(t.get("_assign") or "[]") or []
    except Exception:
        return []


def _slim(rows):
    out = []
    for t in rows:
        out.append({
            "name": t["name"], "subject": t.get("subject"), "project": t.get("project"),
            "workflow_state": t.get("workflow_state"),
            "exp_end_date": str(t["exp_end_date"])[:10] if t.get("exp_end_date") else None,
            "_assign": t.get("_assign"), "priority": t.get("priority"),
        })
    return out


@frappe.whitelist()
def control_center(include_personal=0):
    """My Work (everyone) + Team Overview & Workload (leaders only). Permission-scoped.
    Personal-log projects are left out unless include_personal=1."""
    pmperm.require_pm_access()
    user = frappe.session.user
    today = frappe.utils.nowdate()
    week_end = frappe.utils.add_days(today, 7)
    FIELDS = ["name", "subject", "project", "workflow_state", "exp_end_date",
              "_assign", "priority", "modified"]

    def d10(t):
        v = t.get("exp_end_date")
        return str(v)[:10] if v else None

    def is_active(t):
        return t.get("workflow_state") not in _FINISHED

    def is_overdue(t):
        dd = d10(t)
        return bool(dd and dd < today and is_active(t))

    def is_today(t):
        return d10(t) == today and is_active(t)

    def is_week(t):
        dd = d10(t)
        return bool(dd and today <= dd <= week_end and is_active(t))

    personal = set() if tflow.truthy(include_personal) else tflow.personal_log_projects()
    mine = frappe.get_all("Task", filters=[_mine_filter(user)],
                          fields=FIELDS, limit_page_length=0)
    mine = tflow.drop_personal(mine, personal=personal)
    my_overdue = [t for t in mine if is_overdue(t)]
    my_review = [t for t in mine if t.get("workflow_state") == "Review"]
    my_blocked = [t for t in mine if t.get("workflow_state") == "Blocked"]
    my_counts = {
        "overdue": len(my_overdue),
        "today": len([t for t in mine if is_today(t)]),
        "week": len([t for t in mine if is_week(t)]),
        "review": len(my_review),
        "blocked": len(my_blocked),
    }

    timer = None
    if frappe.db.exists("PM Timer", user):
        tt = frappe.get_doc("PM Timer", user)
        timer = {"task": tt.task, "status": tt.status}
    unread = frappe.db.count("Notification Log",
                             {"for_user": user, "document_type": "Task", "read": 0})

    out = {
        "is_leader": pmperm.can_see_all_pm_data(user),
        "unread": unread, "timer": timer,
        "my": {"counts": my_counts, "overdue": _slim(my_overdue),
               "review": _slim(my_review), "blocked": _slim(my_blocked)},
    }

    scope = mine
    if pmperm.can_see_all_pm_data(user):
        allt = tflow.drop_personal(frappe.get_all("Task", fields=FIELDS, limit_page_length=0),
                                   personal=personal)
        scope = allt
        wstart = str(frappe.utils.add_days(today, -frappe.utils.getdate(today).weekday()))
        out["team"] = {
            "active": len([t for t in allt if is_active(t)]),
            "overdue": len([t for t in allt if is_overdue(t)]),
            "blocked": len([t for t in allt if t.get("workflow_state") == "Blocked"]),
            "review": len([t for t in allt if t.get("workflow_state") == "Review"]),
            "no_assignee": len([t for t in allt if not _assignees(t)]),
            "no_due": len([t for t in allt if not t.get("exp_end_date")]),
            "completed_week": len([t for t in allt if t.get("workflow_state") == "Done"
                                   and str(t.get("modified") or "")[:10] >= wstart]),
        }
        wl = {}
        for t in allt:
            for u in _assignees(t):
                w = wl.setdefault(u, {"assignee": u, "active": 0, "overdue": 0,
                                      "due_week": 0, "in_progress": 0, "blocked": 0})
                if is_active(t):
                    w["active"] += 1
                if is_overdue(t):
                    w["overdue"] += 1
                if is_week(t):
                    w["due_week"] += 1
                if t.get("workflow_state") == "In Progress":
                    w["in_progress"] += 1
                if t.get("workflow_state") == "Blocked":
                    w["blocked"] += 1
        out["workload"] = sorted(wl.values(), key=lambda x: -x["active"])
        out["attention"] = {
            "overdue": _slim([t for t in allt if is_overdue(t)][:10]),
            "blocked": _slim([t for t in allt if t.get("workflow_state") == "Blocked"][:10]),
            "review": _slim([t for t in allt if t.get("workflow_state") == "Review"][:10]),
        }
        # per-project risk (lightweight; aggregated from allt already fetched)
        prisk = {}
        for t in allt:
            p = t.get("project")
            if not p:
                continue
            a = prisk.setdefault(p, {"project": p, "total": 0, "overdue": 0,
                                     "blocked": 0, "review": 0})
            a["total"] += 1
            if is_overdue(t):
                a["overdue"] += 1
            if t.get("workflow_state") == "Blocked":
                a["blocked"] += 1
            if t.get("workflow_state") == "Review":
                a["review"] += 1
        pnames = {}
        if prisk:
            for r in frappe.get_all("Project", filters={"name": ["in", list(prisk.keys())]},
                                    fields=["name", "project_name"]):
                pnames[r["name"]] = r.get("project_name")
        project_risk = []
        for p, a in prisk.items():
            a["project_name"] = pnames.get(p) or p
            a["risk_level"] = "high" if (a["overdue"] > 0 or a["blocked"] > 0) else "low"
            project_risk.append(a)
        project_risk.sort(key=lambda x: (0 if x["risk_level"] == "high" else 1, -x["overdue"]))
        out["project_risk"] = project_risk

    # distributions over the relevant scope (team for leaders, own tasks otherwise)
    status_order = ["Backlog", "To Do", "In Progress", "Blocked", "Review", "Done", "Cancelled"]
    status_dist = {s: 0 for s in status_order}
    priority_dist = {"Urgent": 0, "High": 0, "Medium": 0, "Low": 0, "—": 0}
    for t in scope:
        ws = t.get("workflow_state") or "Backlog"
        status_dist[ws] = status_dist.get(ws, 0) + 1
        pr = t.get("priority") or "—"
        priority_dist[pr] = priority_dist.get(pr, 0) + 1
    out["status_dist"] = status_dist
    out["priority_dist"] = priority_dist
    return out


@frappe.whitelist()
def my_tasklist(include_personal=0):
    """Daily execution view for the CURRENT session user: ONLY tasks assigned to them,
    grouped + de-duplicated (each task in exactly one group). Additive, no schema, no
    scheduler, no custom field. Groups:
      attention = overdue / due-today / blocked / waiting-review (active)
      week      = due-this-week / in-progress (active, not already in attention)
      nodue     = assigned, active, no due date
      done      = recently-modified Done (max 10)
    Active future-dated To-Do tasks are intentionally NOT surfaced here (use Nhiem vu).
    PM redesign: personal-log projects are hidden unless include_personal=1 (the "Hiện" toggle).
    """
    pmperm.require_pm_access()
    user = frappe.session.user
    today = frappe.utils.nowdate()
    week_end = frappe.utils.add_days(today, 7)
    FIELDS = ["name", "subject", "project", "workflow_state", "exp_start_date",
              "exp_end_date", "_assign", "priority", "modified"]
    rows = frappe.get_all(
        "Task", filters=[_mine_filter(user)],
        fields=FIELDS, limit_page_length=0, order_by="modified desc",
    )
    rows = tflow.drop_personal(rows, include_personal)

    def d10(t):
        v = t.get("exp_end_date")
        return str(v)[:10] if v else None

    def active(t):
        return t.get("workflow_state") not in _FINISHED

    def is_overdue(t):
        dd = d10(t)
        return bool(dd and dd < today and active(t))

    def is_today(t):
        return d10(t) == today and active(t)

    def is_week(t):
        dd = d10(t)
        return bool(dd and today <= dd <= week_end and active(t))

    attention, week, nodue, done = [], [], [], []
    for t in rows:
        ws = t.get("workflow_state")
        if ws == "Done":
            done.append(t)
            continue
        if not active(t):
            continue
        if is_overdue(t) or is_today(t) or ws == "Blocked" or ws == "Review":
            attention.append(t)
        elif is_week(t) or ws == "In Progress":
            week.append(t)
        elif not t.get("exp_end_date"):
            nodue.append(t)

    attention.sort(key=lambda t: d10(t) or "9999-12-31")
    week.sort(key=lambda t: d10(t) or "9999-12-31")
    done = done[:10]

    timer = None
    if frappe.db.exists("PM Timer", user):
        tt = frappe.get_doc("PM Timer", user)
        timer = {"task": tt.task, "status": tt.status}

    return {
        "user": user, "timer": timer,
        "counts": {"attention": len(attention), "week": len(week),
                   "nodue": len(nodue), "done": len(done)},
        "attention": _slim(attention), "week": _slim(week),
        "nodue": _slim(nodue), "done": _slim(done),
    }


@frappe.whitelist()
def rail_badges():
    """Session-scoped counts for the shared-shell rail badges (A73). Deliberately takes
    NO parameters: the user is ALWAYS frappe.session.user, so one person can never read
    another person's numbers. Called once per pageview by ec_shell.js bindBadges()
    (BADGE_SOURCES keys pm.mywork / pm.assignments share this one request).

      mywork      - open tasks assigned to me (_assign), workflow_state not in _FINISHED;
                    same population my_tasklist() shows (overdue is a subset of open).
      assignments - PM Assignment Request rows waiting for MY answer (recipient = me,
                    status still open: Pending / Reschedule Proposed).
      received    - PM redesign: "Được giao cho tôi" badge = pm_inbox.received().badge.
                    mywork leaves personal-log projects out (same rule as every PM screen).

    Badges are cosmetic: any failure must stay silent client-side, so this never throws
    for non-PM users - it just returns zeros."""
    user = frappe.session.user
    zero = {"mywork": 0, "assignments": 0, "received": 0}
    if not user or user == "Guest":
        return zero
    try:
        pmperm.require_pm_access()
    except Exception:
        return zero
    mywork = len(tflow.drop_personal(frappe.get_all(
        "Task",
        filters=[_mine_filter(user),
                 ["workflow_state", "not in", _FINISHED]],
        fields=["name", "project"], limit_page_length=0,
    )))
    assignments = len([r for r in frappe.get_all(
        "PM Assignment Request",
        filters=[["recipient", "=", user],
                 ["status", "in", ["Pending", "Reschedule Proposed"]]],
        fields=["name", "kind"], limit_page_length=0,
    ) if (r.get("kind") or "Assignment") != "Deadline"])
    received = 0
    try:
        from ecentric_workspace.pm.api import pm_inbox
        received = pm_inbox.received_data(user)["badge"]
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM rail_badges received")
    return {"mywork": mywork, "assignments": assignments, "received": received}
