"""PM redesign (16/10/2026) - inbox services behind the new /pm screens.

  received()          "Được giao cho tôi"  - negotiation box (needs reply / unopened / my deadline
                                              requests) + badge.
  given(tab)          "Tôi đã giao"        - deadline requests waiting for me + batches I gave
                                              (per-person progress) + recurrence rules (tab rep).
  coordinate()        "Điều phối"          - leader-only overview (pmperm.can_see_all_pm_data).
  request_deadline / answer_deadline / withdraw_deadline   - "Xin dời hạn" on ANY task, stored as
                                              PM Assignment Request kind=Deadline.
  nudge(task, users)  - remind people not done yet (1 / person / task / hour).
  close_parent(task)  - giver closes a task, or returns some people's parts to In Progress.

Permission: require_pm_access everywhere + per-endpoint role checks below (service layer is the
trust boundary, like the rest of pm.api). Notifications go through notification_center events
(task_deadline_requested / task_deadline_answered / task_nudge / task_ready_for_review).

Module path: ecentric_workspace.pm.api.pm_inbox
"""

import json

import frappe
from frappe import _
from frappe.utils import getdate

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm import task_flow as tflow

REQ_DT = tflow.REQ_DT
# Decided deadline requests stay visible to the requester for this many days.
RECENT_DECIDED_DAYS = 30
# Nudge rate limit: one reminder per (task, person) per this many seconds.
NUDGE_WINDOW_SEC = 3600
# Coordinate: cap per to-do kind (the screen is a worklist, not a report).
TODO_CAP = 20
# Coordinate "overload": open >= OVERLOAD_FACTOR x team median AND >= OVERLOAD_MIN_OPEN.
OVERLOAD_FACTOR = 2
OVERLOAD_MIN_OPEN = 5
# Coordinate "nodue": only tasks open (created) at least this many days without an end date -
# a task created this morning without a date is not yet a coordination problem.
NODUE_MIN_AGE_DAYS = 7

_TASK_FIELDS = ["name", "subject", "project", "parent_task", "owner", "workflow_state", "status",
                "exp_start_date", "exp_end_date", "completed_on", "_assign", "modified",
                "creation"]
_FREQ_LABEL = {"Daily": "Hằng ngày", "Weekly": "Hằng tuần", "Biweekly": "2 tuần một lần",
               "Monthly": "Hằng tháng"}
_WEEKDAY = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")


# --------------------------------------------------------------------------- helpers
def _like_me(user):
    return '%"{0}"%'.format(user)


def _project_names(rows):
    names = sorted({r.get("project") for r in rows if r.get("project")})
    if not names:
        return {}
    return {p["name"]: p.get("project_name") or p["name"]
            for p in frappe.get_all("Project", filters={"name": ["in", names]},
                                    fields=["name", "project_name"])}


def _load_task(name):
    if not name or not frappe.db.exists("Task", name):
        frappe.throw(_("Không tìm thấy việc."))
    return frappe.get_doc("Task", name)


def _task_ref(doc):
    return {"name": doc.name, "owner": doc.get("owner"), "parent_task": doc.get("parent_task")}


def _parse_users(users):
    if users in (None, "", "null"):
        return None
    if isinstance(users, str):
        try:
            users = json.loads(users)
        except Exception:
            users = [u for u in users.replace(";", ",").split(",")]
    if isinstance(users, str):
        users = [users]
    return [u.strip() for u in (users or []) if isinstance(u, str) and u.strip()]


def _is_late(row, today):
    return tflow.is_late(row, today)  # single definition in pm.task_flow


# --------------------------------------------------------------------------- received
def _needs_reply(user, pnames_cache):
    rows = frappe.get_all(REQ_DT, filters={"recipient": user, "status": "Pending"},
                          fields=["name", "task", "requested_by", "proposed_end", "message",
                                  "creation", "kind"],
                          order_by="creation desc", limit_page_length=200)
    rows = [r for r in rows if (r.get("kind") or tflow.KIND_ASSIGNMENT) != tflow.KIND_DEADLINE]
    tasks = {t["name"]: t for t in frappe.get_all(
        "Task", filters={"name": ["in", [r["task"] for r in rows] or [""]]},
        fields=["name", "subject", "project"], limit_page_length=0)}
    pnames_cache.update(_project_names(tasks.values()))
    names = tflow.full_names([r.get("requested_by") for r in rows])
    out = []
    for r in rows:
        t = tasks.get(r["task"]) or {}
        out.append({"request": r["name"], "task": r["task"], "subject": t.get("subject") or r["task"],
                    "project_name": pnames_cache.get(t.get("project")),
                    "from_user": r.get("requested_by"),
                    "from_name": names.get(r.get("requested_by")) or r.get("requested_by"),
                    "proposed_end": tflow.d10(r.get("proposed_end")),
                    "message": r.get("message"), "created": str(r.get("creation") or "")})
    return out


def _unopened(user, personal):
    """Open tasks someone else gave me that I have never opened (no PM Task Seen row)."""
    rows = frappe.get_all("Task", filters=[["_assign", "like", _like_me(user)],
                                           ["workflow_state", "not in", list(tflow.FINISHED)],
                                           ["owner", "!=", user]],
                          fields=_TASK_FIELDS, order_by="creation desc", limit_page_length=0)
    rows = tflow.drop_personal(rows, personal=personal)
    rows = [r for r in rows if user in tflow.assignees(r)]  # exact membership, not substring
    if not rows:
        return []
    seen = tflow.seen_pairs([r["name"] for r in rows])
    rows = [r for r in rows if (r["name"], user) not in seen]
    givers = tflow.givers_map(rows)
    names = tflow.full_names(givers.values())
    pnames = _project_names(rows)
    return [{"task": r["name"], "subject": r.get("subject"),
             "project_name": pnames.get(r.get("project")),
             "from_user": givers.get(r["name"]),
             "from_name": names.get(givers.get(r["name"])) or givers.get(r["name"]),
             "exp_end_date": tflow.d10(r.get("exp_end_date")),
             "workflow_state": r.get("workflow_state")} for r in rows]


def _my_deadline_requests(user):
    since = frappe.utils.add_days(frappe.utils.nowdate(), -RECENT_DECIDED_DAYS)
    rows = frappe.get_all(REQ_DT, filters={"requested_by": user, "kind": tflow.KIND_DEADLINE,
                                           "status": ["in", ["Pending", "Accepted", "Rejected"]]},
                          fields=["name", "task", "status", "proposed_end", "message",
                                  "response_reason", "decided_at", "creation"],
                          order_by="creation desc", limit_page_length=200)
    rows = [r for r in rows if r["status"] == "Pending"
            or tflow.d10(r.get("decided_at")) and tflow.d10(r.get("decided_at")) >= str(since)]
    tasks = {t["name"]: t for t in frappe.get_all(
        "Task", filters={"name": ["in", [r["task"] for r in rows] or [""]]},
        fields=["name", "subject", "exp_end_date"], limit_page_length=0)}
    seen = tflow.seen_pairs([r["task"] for r in rows])
    out = []
    for r in rows:
        t = tasks.get(r["task"]) or {}
        old_end = _created_old_end(r["name"]) or tflow.d10(t.get("exp_end_date"))
        last = seen.get((r["task"], user))
        unseen = (r["status"] == "Rejected" and
                  (not last or str(last) < str(r.get("decided_at") or "")))
        out.append({"request": r["name"], "task": r["task"],
                    "subject": t.get("subject") or r["task"], "old_end": old_end,
                    "new_end": tflow.d10(r.get("proposed_end")), "reason": r.get("message"),
                    "status": r["status"], "answer": r.get("response_reason"),
                    "answered_at": str(r["decided_at"]) if r.get("decided_at") else None,
                    "unseen": 1 if unseen else 0})
    return out


def _created_old_end(request):
    rows = frappe.get_all("PM Assignment Request Event",
                          filters={"parent": request, "parenttype": REQ_DT},
                          fields=["old_end", "idx"], order_by="idx asc", limit_page_length=1)
    return tflow.d10(rows[0].get("old_end")) if rows else None


def received_data(user):
    """Shared by received() and dashboard.rail_badges (badge = same numbers)."""
    personal = tflow.personal_log_projects()
    needs = _needs_reply(user, {})
    unopened = _unopened(user, personal)
    mine = _my_deadline_requests(user)
    rejected_unseen = len([m for m in mine if m.get("unseen")])
    return {"needs_reply": needs, "unopened": unopened, "my_deadline_requests": mine,
            "badge": len(needs) + len(unopened) + rejected_unseen}


@frappe.whitelist()
def received():
    pmperm.require_pm_access()
    return received_data(frappe.session.user)


# --------------------------------------------------------------------------- given
def _deadline_banner(user):
    rows = frappe.get_all(REQ_DT, filters={"recipient": user, "kind": tflow.KIND_DEADLINE,
                                           "status": "Pending"},
                          fields=["name", "task", "requested_by", "proposed_end", "message",
                                  "creation"], order_by="creation asc", limit_page_length=200)
    tasks = {t["name"]: t for t in frappe.get_all(
        "Task", filters={"name": ["in", [r["task"] for r in rows] or [""]]},
        fields=["name", "subject", "project", "exp_end_date"], limit_page_length=0)}
    pnames = _project_names(tasks.values())
    names = tflow.full_names([r.get("requested_by") for r in rows])
    out = []
    for r in rows:
        t = tasks.get(r["task"]) or {}
        out.append({"request": r["name"], "task": r["task"], "subject": t.get("subject") or r["task"],
                    "project_name": pnames.get(t.get("project")),
                    "from_user": r.get("requested_by"),
                    "from_name": names.get(r.get("requested_by")) or r.get("requested_by"),
                    "old_end": tflow.d10(t.get("exp_end_date")),
                    "new_end": tflow.d10(r.get("proposed_end")), "reason": r.get("message"),
                    "created": str(r.get("creation") or "")})
    return out


def _given_roots(user, tab, personal):
    """Top-level tasks I gave (owner or accepted-request requester), filtered by tab."""
    if tab == "done":
        state = [["workflow_state", "=", "Done"]]
    else:
        state = [["workflow_state", "not in", list(tflow.FINISHED)]]
    base = [["parent_task", "is", "not set"]]
    via_req = frappe.get_all(REQ_DT, filters={"requested_by": user, "status": "Accepted"},
                             fields=["task", "kind"], limit_page_length=0)
    req_tasks = [r["task"] for r in via_req
                 if (r.get("kind") or tflow.KIND_ASSIGNMENT) != tflow.KIND_DEADLINE]
    ors = [["owner", "=", user]]
    if req_tasks:
        ors.append(["name", "in", req_tasks])
    rows = frappe.get_all("Task", filters=base + state, or_filters=ors,
                          fields=_TASK_FIELDS + ["ec_auto_close", "ec_review_required",
                                                 "ec_split_parent"],
                          order_by="modified desc",
                          limit_page_length=50 if tab == "done" else 0)
    rows = [r for r in rows if not r.get("parent_task")]
    return tflow.drop_personal(rows, personal=personal)


def _checklist_steps(names):
    return tflow.checklist_steps(names)


def _recurrence_by_task(names):
    if not names:
        return {}
    out = {}
    for r in frappe.get_all("PM Recurrence", filters={"last_task": ["in", names]},
                            fields=["name", "last_task", "frequency", "interval", "weekly_days",
                                    "monthly_day"], limit_page_length=0):
        out[r["last_task"]] = {"name": r["name"], "label": _schedule_label(r)}
    return out


def _schedule_label(r):
    freq = r.get("frequency")
    n = int(r.get("interval") or 1)
    label = _(_FREQ_LABEL.get(freq, freq or ""))
    if freq == "Daily" and n > 1:
        label = _("Mỗi {0} ngày").format(n)
    elif freq == "Weekly":
        if n > 1:
            label = _("Mỗi {0} tuần").format(n)
        try:
            days = json.loads(r.get("weekly_days") or "[]") or []
        except Exception:
            days = []
        days = [_WEEKDAY[d] for d in days if isinstance(d, int) and 0 <= d <= 6]
        if days:
            label += " (" + ", ".join(days) + ")"
    elif freq == "Monthly":
        if n > 1:
            label = _("Mỗi {0} tháng").format(n)
        if r.get("monthly_day"):
            label += " " + _("ngày {0}").format(r.get("monthly_day"))
    return label


def _people_for(root, kids, seen, steps, today, user):
    """Per-person rows of one batch: split -> one row per child; else one row per assignee."""
    people = []
    if kids:
        for k in kids:
            asg = tflow.assignees(k)
            people.append(_person_row(asg[0] if asg else None, k, seen, steps, today))
        return people
    for u in tflow.assignees(root):
        if u == user and root.get("owner") == user:
            continue
        people.append(_person_row(u, root, seen, steps, today))
    return people


def _person_row(u, t, seen, steps, today):
    return tflow.person_row(u, t, seen, steps, today)  # shared with tasks.get children_progress


def _batches(roots, user, today):
    names = [r["name"] for r in roots]
    kids_by_parent = {}
    if names:
        for k in frappe.get_all("Task", filters={"parent_task": ["in", names]},
                                fields=_TASK_FIELDS, order_by="creation asc", limit_page_length=0):
            if k.get("workflow_state") != "Cancelled":
                kids_by_parent.setdefault(k["parent_task"], []).append(k)
    all_names = names + [k["name"] for ks in kids_by_parent.values() for k in ks]
    seen = tflow.seen_pairs(all_names)
    steps = _checklist_steps(all_names)
    recur = _recurrence_by_task(names)
    pnames = _project_names(roots)
    out = []
    for r in roots:
        kids = kids_by_parent.get(r["name"], [])
        people = _people_for(r, kids, seen, steps, today, user)
        if not people:
            continue  # a task only I hold is my own to-do, not something I gave
        out.append({"task": r["name"], "subject": r.get("subject"),
                    "project_name": pnames.get(r.get("project")),
                    "split": bool(kids) or tflow.truthy(r.get("ec_split_parent")),
                    "auto_close": 1 if tflow.truthy(r.get("ec_auto_close")) else 0,
                    "review_required": 1 if tflow.truthy(r.get("ec_review_required")) else 0,
                    "recurrence": recur.get(r["name"]),
                    "exp_end_date": tflow.d10(r.get("exp_end_date")),
                    "workflow_state": r.get("workflow_state"), "people": people,
                    "done_count": len([p for p in people if p["state"] == "Done"]),
                    "total": len(people)})
    names_map = tflow.full_names([p["user"] for b in out for p in b["people"]])
    for b in out:
        for p in b["people"]:
            p["full_name"] = names_map.get(p["user"]) or p["user"]
    return out


def _rules(user):
    rows = frappe.get_all("PM Recurrence", filters={"owner": user, "status": ["!=", "Cancelled"]},
                          fields=["name", "template_subject", "frequency", "interval",
                                  "weekly_days", "monthly_day", "template_assignees",
                                  "next_run_date", "status"],
                          order_by="modified desc", limit_page_length=200)
    users = []
    for r in rows:
        try:
            r["_asg"] = [u for u in (json.loads(r.get("template_assignees") or "[]") or [])
                         if isinstance(u, str)]
        except Exception:
            r["_asg"] = []
        users += r["_asg"]
    names = tflow.full_names(users)
    return [{"name": r["name"], "subject": r.get("template_subject"),
             "schedule_label": _schedule_label(r),
             "assignees": [tflow.person(u, names) for u in r["_asg"]],
             "next_run": tflow.d10(r.get("next_run_date")), "status": r.get("status")}
            for r in rows]


@frappe.whitelist()
def given(tab="run"):
    pmperm.require_pm_access()
    user = frappe.session.user
    if tab not in ("run", "rep", "done"):
        frappe.throw(_("Tab không hợp lệ."))
    out = {"banner": _deadline_banner(user), "batches": [], "rules": []}
    if tab == "rep":
        out["rules"] = _rules(user)
        return out
    roots = _given_roots(user, tab, tflow.personal_log_projects())
    out["batches"] = _batches(roots, user, frappe.utils.nowdate())
    return out


# --------------------------------------------------------------------------- coordinate
def _week_start(today):
    d = getdate(today)
    return str(frappe.utils.add_days(d, -d.weekday()))


def _done_day(t):
    return tflow.d10(t.get("completed_on")) or tflow.d10(t.get("modified"))


def _kpi(rows, today):
    active = [t for t in rows if t.get("workflow_state") not in tflow.FINISHED]
    wstart = _week_start(today)
    since30 = str(frappe.utils.add_days(today, -30))
    done = [t for t in rows if t.get("workflow_state") == "Done"]
    measured = [t for t in done if t.get("completed_on") and t.get("exp_end_date")
                and tflow.d10(t["completed_on"]) >= since30]
    on_time = [t for t in measured if tflow.d10(t["completed_on"]) <= tflow.d10(t["exp_end_date"])]
    return {"open": len(active),
            "late": len([t for t in active if _is_late(t, today)]),
            "unassigned": len([t for t in active if not tflow.assignees(t)]),
            "done_week": len([t for t in done if (_done_day(t) or "") >= wstart]),
            "on_time_pct_30d": (int(round(100.0 * len(on_time) / len(measured)))
                                if measured else None)}


def _todo_task(kind, t, pnames, names, today, seen=None):
    """One per-task to-do row (kind "late"). `user`/`full_name`/`opened` describe the FIRST
    assignee (the person the leader would nudge); `assignees` keeps the full list."""
    end = tflow.d10(t.get("exp_end_date"))
    asg = tflow.assignees(t)
    first = asg[0] if asg else None
    item = {"kind": kind, "task": t["name"], "subject": t.get("subject"),
            "project": t.get("project"), "project_name": pnames.get(t.get("project")),
            "exp_end_date": end, "workflow_state": t.get("workflow_state"),
            "assignees": [tflow.person(u, names) for u in asg],
            "user": first, "full_name": (names.get(first) or first) if first else None,
            "opened": bool(first and seen is not None and (t["name"], first) in seen)}
    if kind == "late" and end:
        item["days_late"] = (getdate(today) - getdate(end)).days
    return item


def _todo_group(kind, rows, pnames):
    """ONE aggregated to-do row for "unassigned" / "nodue": {kind, count, projects:[{project,
    project_name, count}], tasks:[names]} - the screen shows a single line with a link to the
    filtered list, not one line per task. Projects sorted by count desc (capped)."""
    if not rows:
        return None
    by = {}
    for t in rows:
        by[t.get("project") or ""] = by.get(t.get("project") or "", 0) + 1
    projects = [{"project": p or None, "project_name": pnames.get(p) if p else None, "count": n}
                for p, n in sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))][:TODO_CAP]
    return {"kind": kind, "count": len(rows), "projects": projects,
            "tasks": [t["name"] for t in rows[:TODO_CAP]]}


def _people_stats(rows, today):
    wstart = _week_start(today)
    stats = {}
    for t in rows:
        for u in tflow.assignees(t):
            s = stats.setdefault(u, {"user": u, "open": 0, "late": 0, "done_week": 0})
            ws = t.get("workflow_state")
            if ws not in tflow.FINISHED:
                s["open"] += 1
                if _is_late(t, today):
                    s["late"] += 1
            elif ws == "Done" and (_done_day(t) or "") >= wstart:
                s["done_week"] += 1
    return stats


def _overload(stats):
    opens = sorted(s["open"] for s in stats.values() if s["open"])
    if not opens:
        return []
    median = opens[len(opens) // 2]
    floor = max(OVERLOAD_MIN_OPEN, OVERLOAD_FACTOR * median)
    return [s for s in stats.values() if s["open"] >= floor]


def _project_stats(rows, today):
    out = {}
    for t in rows:
        p = t.get("project")
        if not p or t.get("workflow_state") == "Cancelled":
            continue
        a = out.setdefault(p, {"name": p, "done": 0, "total": 0, "open": 0, "late": 0,
                               "unassigned": 0})
        a["total"] += 1
        if t.get("workflow_state") == "Done":
            a["done"] += 1
            continue
        a["open"] += 1
        if _is_late(t, today):
            a["late"] += 1
        if not tflow.assignees(t):
            a["unassigned"] += 1
    if out:
        for p in frappe.get_all("Project", filters={"name": ["in", sorted(out)]},
                                fields=["name", "project_name", "ec_manager", "owner"]):
            out[p["name"]]["project_name"] = p.get("project_name") or p["name"]
            out[p["name"]]["owner"] = p.get("ec_manager") or p.get("owner")
        owners = tflow.full_names([a.get("owner") for a in out.values()])
        for a in out.values():
            a.setdefault("project_name", a["name"])
            a.setdefault("owner", None)
            a["owner_name"] = owners.get(a["owner"]) if a.get("owner") else None
    return sorted(out.values(), key=lambda a: (-a["late"], -a["open"]))


@frappe.whitelist()
def coordinate(include_personal=0):
    """Leader-only overview. No per-person on-time %, only the team-level KPI (PO point 10).
    Split parents are coordination rows (assigned to the giver) -> excluded from all counts."""
    pmperm.require_pm_access()
    user = frappe.session.user
    if not pmperm.can_see_all_pm_data(user):
        frappe.throw(_("Chỉ leader xem được Điều phối."), frappe.PermissionError)
    today = frappe.utils.nowdate()
    personal = tflow.personal_log_projects()
    rows = frappe.get_all("Task", fields=_TASK_FIELDS + ["ec_split_parent"], limit_page_length=0)
    rows = [t for t in tflow.drop_personal(rows, include_personal, personal=personal)
            if not tflow.truthy(t.get("ec_split_parent"))]
    active = [t for t in rows if t.get("workflow_state") not in tflow.FINISHED]
    stats = _people_stats(rows, today)
    names = tflow.full_names(list(stats.keys()))
    pnames = _project_names(active)
    late = sorted([t for t in active if _is_late(t, today)],
                  key=lambda t: tflow.d10(t["exp_end_date"]))[:TODO_CAP]
    seen = tflow.seen_pairs([t["name"] for t in late])
    todo = [_todo_task("late", t, pnames, names, today, seen) for t in late]
    old = str(frappe.utils.add_days(today, -NODUE_MIN_AGE_DAYS))
    for grp in (_todo_group("unassigned", [t for t in active if not tflow.assignees(t)], pnames),
                _todo_group("nodue", [t for t in active if tflow.assignees(t)
                                      and not t.get("exp_end_date")
                                      and (tflow.d10(t.get("creation")) or today) <= old],
                            pnames)):
        if grp:
            todo.append(grp)
    todo += [{"kind": "overload", "user": s["user"], "full_name": names.get(s["user"]) or s["user"],
              "open": s["open"], "late": s["late"]} for s in _overload(stats)]
    people = sorted(stats.values(), key=lambda s: -s["open"])
    for s in people:
        s["full_name"] = names.get(s["user"]) or s["user"]
    return {"kpi": _kpi(rows, today), "todo": todo, "people": people,
            "projects": _project_stats(rows, today),
            "personal_hidden": 0 if tflow.truthy(include_personal) else len(personal)}


# --------------------------------------------------------------------------- deadline flow
def _clean_new_end(doc, new_end):
    from ecentric_workspace.pm.api import tasks as pmtasks
    ne = pmtasks._parse_date_or_throw(new_end, _("Hạn mới"))
    if not ne:
        frappe.throw(_("Vui lòng chọn hạn mới."))
    cur = tflow.d10(doc.get("exp_end_date"))
    if cur and ne == cur:
        frappe.throw(_("Hạn mới trùng hạn hiện tại."))
    start = tflow.d10(doc.get("exp_start_date"))
    if start and ne < start:
        frappe.throw(_("Hạn mới không được trước ngày bắt đầu."))
    return ne


@frappe.whitelist()
def request_deadline(task, new_end, reason=None):
    """Assignee asks the giver for a new deadline (any task). Nothing about the task changes
    until the giver accepts (answer_deadline)."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = _load_task(task)
    if not pmperm.is_task_assignee({"_assign": frappe.db.get_value("Task", doc.name, "_assign")}, user):
        frappe.throw(_("Chỉ người được giao mới xin dời hạn được."), frappe.PermissionError)
    pmperm.assert_task_not_terminal(doc, _("Việc đã xong hoặc đã huỷ, không xin dời hạn được."))
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Vui lòng nhập lý do xin dời hạn."))
    ne = _clean_new_end(doc, new_end)
    giver = tflow.giver_of(_task_ref(doc))
    if not giver or giver == user:
        frappe.throw(_("Bạn là người giao việc này, hãy sửa hạn trực tiếp."))
    if tflow.open_deadline_request(doc.name):
        frappe.throw(_("Việc này đã có đề xuất dời hạn đang chờ trả lời."))
    old_end = tflow.d10(doc.get("exp_end_date"))
    req = frappe.get_doc({"doctype": REQ_DT, "kind": tflow.KIND_DEADLINE, "task": doc.name,
                          "recipient": giver, "requested_by": user, "status": "Pending",
                          "proposed_end": ne + " 00:00:00", "message": reason})
    req.open_request_key, req.open_task_key = tflow.deadline_keys(doc.name, user, True)
    from ecentric_workspace.pm.api import assignment as pmasg
    pmasg._event(req, "Deadline Requested", detail=reason,
                 old_end=(old_end + " 00:00:00") if old_end else None, new_end=ne + " 00:00:00")
    try:
        with pmasg._service():
            req.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        frappe.throw(_("Việc này đã có đề xuất dời hạn đang chờ trả lời."))
    who = frappe.db.get_value("User", user, "full_name") or user
    tflow.emit(tflow.EV_DEADLINE_REQUESTED, [giver], doc.name,
               _("Xin dời hạn: {0}").format(doc.get("subject") or doc.name),
               _("{0} xin dời hạn từ {1} sang {2}. Lý do: {3}").format(who, old_end or "-", ne, reason),
               actor=user, suffix=req.name)
    return {"request": req.name, "task": doc.name, "status": "Pending",
            "old_end": old_end, "new_end": ne}


def _load_deadline_request(request):
    if not request or not frappe.db.exists(REQ_DT, request):
        frappe.throw(_("Không tìm thấy đề xuất dời hạn."))
    req = frappe.get_doc(REQ_DT, request)
    if (req.get("kind") or tflow.KIND_ASSIGNMENT) != tflow.KIND_DEADLINE:
        frappe.throw(_("Đây không phải đề xuất dời hạn."))
    return req


def _extend_for_deadline(tdoc, new_end, user):
    """GATED widening (only after the giver accepted): project end first, then the parent chain
    only when the new date really passes the parent's end. Returns True if a parent was widened.
    Normal create/update keep their own immediate _expand_ancestor_dates behaviour."""
    from ecentric_workspace.pm.api import tasks as pmtasks
    if tdoc.get("project"):
        pmtasks._expand_project_dates(tdoc.get("project"), None, new_end, user)
    parent = tdoc.get("parent_task")
    if not parent:
        return False
    pend = tflow.d10(frappe.db.get_value("Task", parent, "exp_end_date"))
    if pend and new_end <= pend:
        return False
    pmtasks._expand_ancestor_dates(parent, None, new_end, user)
    return True


@frappe.whitelist()
def answer_deadline(request, accept, note=None):
    """Giver (task giver / the request's recipient) or a leader accepts or keeps the old date."""
    pmperm.require_pm_access()
    user = frappe.session.user
    req = _load_deadline_request(request)
    tdoc = _load_task(req.task)
    if not (user == req.recipient or tflow.is_giver_or_leader(_task_ref(tdoc), user)):
        frappe.throw(_("Chỉ người giao việc hoặc leader mới trả lời được."), frappe.PermissionError)
    if req.status != "Pending":
        frappe.throw(_("Đề xuất này không còn chờ trả lời."))
    ok = tflow.truthy(accept)
    extended = False
    if ok:
        pmperm.assert_task_not_terminal(tdoc, _("Việc đã xong hoặc đã huỷ."))
        from ecentric_workspace.pm.api import tasks as pmtasks
        ne = tflow.d10(req.proposed_end)
        pmtasks._clean_schedule(tflow.d10(tdoc.get("exp_start_date")), tdoc.get("pm_start_time"),
                                ne, tdoc.get("pm_end_time"))
        extended = _extend_for_deadline(tdoc, ne, user)
        tdoc = frappe.get_doc("Task", tdoc.name)
        tdoc.exp_end_date = ne
        tdoc.save(ignore_permissions=True)  # validated save -> Version audit; gate is above
    tflow.close_deadline_request(req, "Accepted" if ok else "Rejected",
                                 "Deadline Accepted" if ok else "Deadline Rejected",
                                 (note or "").strip() or None)
    title = _("Đồng ý dời hạn: {0}") if ok else _("Giữ hạn cũ: {0}")
    tflow.emit(tflow.EV_DEADLINE_ANSWERED, [req.requested_by], tdoc.name,
               title.format(tdoc.get("subject") or tdoc.name), (note or "").strip(),
               actor=user, suffix=req.name + "|" + req.status)
    return {"request": req.name, "status": req.status, "task": tdoc.name,
            "exp_end_date": tflow.d10(frappe.db.get_value("Task", tdoc.name, "exp_end_date")),
            "parent_extended": extended}


@frappe.whitelist()
def withdraw_deadline(request):
    pmperm.require_pm_access()
    user = frappe.session.user
    req = _load_deadline_request(request)
    if req.requested_by != user:
        frappe.throw(_("Chỉ người xin dời hạn mới rút được."), frappe.PermissionError)
    if req.status != "Pending":
        frappe.throw(_("Đề xuất này không còn chờ trả lời."))
    tflow.close_deadline_request(req, "Cancelled", "Withdrawn")
    return {"request": req.name, "status": "Cancelled"}


# --------------------------------------------------------------------------- nudge
def _not_done_people(doc):
    """[(user, task)] still owing work: open children's assignees, else the task's own."""
    kids = frappe.get_all("Task", filters={"parent_task": doc.name},
                          fields=["name", "workflow_state", "status", "_assign"],
                          limit_page_length=0)
    if kids:
        return [(u, k["name"]) for k in kids if not pmperm.is_task_terminal(k)
                for u in tflow.assignees(k)]
    if pmperm.is_task_terminal(doc):
        return []
    raw = {"_assign": frappe.db.get_value("Task", doc.name, "_assign")}
    return [(u, doc.name) for u in tflow.assignees(raw)]


@frappe.whitelist()
def nudge(task, users=None):
    """Remind people who are not done (users=None -> all of them). Max one reminder per
    person per task per hour (cache); a rate-limited person is reported in `skipped`."""
    pmperm.require_pm_access()
    me = frappe.session.user
    doc = _load_task(task)
    if not tflow.is_giver_or_leader(_task_ref(doc), me):
        frappe.throw(_("Chỉ người giao việc hoặc leader mới nhắc được."), frappe.PermissionError)
    wanted = _parse_users(users)
    targets = [(u, t) for u, t in _not_done_people(doc)
               if u != me and (wanted is None or u in wanted)]
    if not targets:
        frappe.throw(_("Không còn ai cần nhắc."))
    bucket = str(frappe.utils.now_datetime())[:13]
    who = frappe.db.get_value("User", me, "full_name") or me
    sent, skipped, cache = [], [], frappe.cache()
    for u, t in targets:
        key = "pm_nudge::{0}::{1}".format(doc.name, u)
        if cache.get_value(key):
            skipped.append(u)
            continue
        cache.set_value(key, 1, expires_in_sec=NUDGE_WINDOW_SEC)
        tflow.emit(tflow.EV_NUDGE, [u], t, _("Nhắc việc: {0}").format(doc.get("subject") or doc.name),
                   _("{0} nhắc bạn hoàn thành việc này.").format(who), actor=me, suffix=bucket)
        sent.append(u)
    return {"task": doc.name, "sent": sent, "skipped": skipped}


# --------------------------------------------------------------------------- close parent
@frappe.whitelist()
def close_parent(task, return_users=None, note=None):
    """Giver closes the task (Done), or returns the parts of `return_users` to In Progress with
    a comment (split parent -> those children; plain task -> the task itself)."""
    pmperm.require_pm_access()
    me = frappe.session.user
    doc = _load_task(task)
    if not tflow.is_giver_or_leader(_task_ref(doc), me):
        frappe.throw(_("Chỉ người giao việc hoặc leader mới đóng được."), frappe.PermissionError)
    back = _parse_users(return_users)
    if not back:
        if pmperm.has_open_children(doc.name):
            frappe.throw(_("Còn việc con chưa xong, chưa đóng được."))
        tflow.withdraw_open_deadline(doc.name, _("Tự rút vì việc đã đóng."))
        tflow.write_state(doc.name, "Done", me)
        if note:
            tflow.add_comment(doc.name, note, "Comment")
        try:
            tflow.rollup_parent(doc.name, me)  # closing one person's part may finish a split parent
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PM close_parent rollup " + str(doc.name))
        return {"task": doc.name, "state": "Done", "returned": []}
    return _return_parts(doc, back, note, me)


def _return_parts(doc, users, note, me):
    kids = frappe.get_all("Task", filters={"parent_task": doc.name},
                          fields=["name", "workflow_state", "_assign"], limit_page_length=0)
    pool = kids or [{"name": doc.name, "workflow_state": doc.get("workflow_state"),
                     "_assign": frappe.db.get_value("Task", doc.name, "_assign")}]
    picked = [k for k in pool if k.get("workflow_state") != "Cancelled"
              and set(tflow.assignees(k)) & set(users)]
    if not picked:
        frappe.throw(_("Không tìm thấy phần việc của người được chọn."))
    text = (note or "").strip() or _("Người giao trả lại, cần làm tiếp.")
    for k in picked:
        tflow.write_state(k["name"], "In Progress", me)
        tflow.add_comment(k["name"], text, "Comment")
    if kids and doc.get("workflow_state") in ("Review", "Done"):
        tflow.write_state(doc.name, "In Progress", me, notify=False)
    return {"task": doc.name, "state": frappe.db.get_value("Task", doc.name, "workflow_state"),
            "returned": [k["name"] for k in picked]}
