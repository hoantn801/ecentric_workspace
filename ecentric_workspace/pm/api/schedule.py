# Copyright (c) 2026, eCentric and contributors
"""PM Time-blocking (Lịch làm việc) — thin CRUD over the EC PM Time Block store.

A "block" = one EC PM Time Block row (task, user, start, end, state). The /pm week
calendar is just a visual editor over the caller's own blocks. Block = planned time;
elapsed time becomes actual (computed client-side); the owner self-confirms (there is
NO manager approval — managers are read-only). Overlapping blocks are allowed (many
tasks in one slot), which is why this is a dedicated doctype and not Timesheet Detail
(Frappe Timesheet rejects overlapping logs).

Permission model (mirrors the rest of PM):
  - A user may only CREATE/MOVE/REMOVE/CONFIRM their OWN blocks (user == session user).
  - A leader (pmperm.can_see_all_pm_data) may READ another user's week (read-only).
  - Placing a block requires the caller to be able to view the task (pmperm.can_view_task).
All reads/writes use ignore_permissions with explicit user-scoping (same pattern as the
Task-backed PM endpoints); the DocType itself only grants System Manager.
"""
import json

import frappe
from frappe import _
from frappe.utils import (get_datetime, getdate, add_days, nowdate, now_datetime,
                          time_diff_in_hours)

from ecentric_workspace.pm import permissions as pmperm

BLOCK = "EC PM Time Block"
_TERMINAL_WF = ("Done", "Cancelled")
#: description tag on the "confirm your hours" reminder ToDo, so the Action Center can
#: route it to the week calendar (resolvers.resolve_item) and confirm() can close it.
NUDGE_TAG = "[XNGIO]"


def _monday(d):
    d = getdate(d)
    return add_days(d, -((d.weekday()) % 7))


def _task_view_dict(task_name):
    row = frappe.db.get_value(
        "Task", task_name, ["name", "owner", "project", "_assign"], as_dict=True)
    return row or {}


def _require_own(block, user):
    if not block or block.get("user") != user:
        frappe.throw(_("Không thể sửa lịch của người khác."), frappe.PermissionError)


@frappe.whitelist()
def week(user=None, week_start=None):
    """Blocks for `user`'s week + that user's open tasks (backlog) + a name map.

    `user` defaults to the caller. Viewing SOMEONE ELSE (READ-ONLY) is allowed when the
    caller is a leader (whole company) or shares a team/department with the target.
    `week_start` is any date in the target week; range = that week's Monday 00:00 .. +7d."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    target = user or caller
    leader = pmperm.can_see_all_pm_data(caller)
    team = _team_user_ids(caller)
    readonly = False
    if target != caller:
        if leader or target in team:
            readonly = True
        else:
            frappe.throw(_("Không có quyền xem lịch người này."), frappe.PermissionError)

    mon = _monday(week_start or nowdate())
    start_dt = "%s 00:00:00" % mon
    end_dt = "%s 00:00:00" % add_days(mon, 7)

    blocks = frappe.get_all(
        BLOCK,
        filters={"user": target, "start": [">=", start_dt], "end": ["<", end_dt]},
        fields=["name", "task", "user", "start", "end", "hours", "state", "source_note"],
        order_by="start asc", ignore_permissions=True) or []

    scheduled = {b["task"] for b in blocks if b.get("task")}
    # When viewing SOMEONE ELSE (read-only), show free/busy only: blocks for tasks the
    # VIEWER cannot see (outside their project access) are masked to "Bận" (time + colour,
    # no task name / tooltip), and the target's unscheduled backlog is never exposed. This
    # keeps schedule visibility (coordination) from leaking task content beyond the
    # viewer's project permissions. `visible_task_subset` returns everything for leaders.
    if readonly:
        backlog = []
        viewable = set(pmperm.visible_task_subset(list(scheduled), caller)) if scheduled else set()
        for b in blocks:
            if b.get("task") not in viewable:
                b["masked"] = 1
    else:
        # Backlog = open tasks NOT already scheduled this week.
        backlog = [t for t in _open_tasks_for(target) if t["name"] not in scheduled]
        viewable = None

    task_names = list(scheduled | {t["name"] for t in backlog})
    meta = _task_meta(task_names)
    subj = {}
    for nm, m in meta.items():
        if viewable is not None and nm not in viewable:
            subj[nm] = "Bận"
        else:
            subj[nm] = m.get("subject") or nm
    if viewable is not None:
        meta = {k: v for k, v in meta.items() if k in viewable}

    return {
        "readonly": readonly,
        "is_leader": leader,
        "can_view_others": leader or bool(team),
        "user": target,
        "week_start": str(mon),
        "blocks": blocks,
        "backlog": backlog,
        "subjects": subj,
        "meta": meta,
        "meetings": _ms_meetings(target, start_dt, end_dt, mask=readonly),
    }


def _ms_meetings(email, start_dt, end_dt, mask=False):
    """Outlook/Teams calendar 'busy' blocks for `email` in [start_dt, end_dt] (naive
    site-local 'YYYY-MM-DD HH:MM:SS'). Overlaid on the week as read-only context so people
    don't schedule work over a meeting.

    GATED + FAIL-SAFE: returns [] unless site_config `ec_pm_calendar_sync` is truthy AND the
    Graph app is configured with Calendars.Read (Application) consent. ANY failure (not
    enabled, no token, 403 missing scope, network) -> [] so the schedule never breaks or
    slows down. Subjects are replaced with 'Họp' when `mask` (viewing someone else)."""
    try:
        conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
        if not conf.get("ec_pm_calendar_sync"):
            return []
        from ecentric_workspace.notification_center.providers import graph as msgraph
        if not msgraph.is_configured():
            return []
        ok, token = msgraph.get_app_token()
        if not ok:
            return []
        import requests
        url = ("https://graph.microsoft.com/v1.0/users/" + email + "/calendarView"
               "?startDateTime=" + start_dt.replace(" ", "T") + "%2B07:00"
               "&endDateTime=" + end_dt.replace(" ", "T") + "%2B07:00"
               "&$select=subject,start,end,showAs,isAllDay&$top=100&$orderby=start/dateTime")
        r = requests.get(url, headers={"Authorization": "Bearer " + token,
                         "Prefer": 'outlook.timezone="Asia/Ho_Chi_Minh"'}, timeout=12)
        if r.status_code != 200:
            return []
        out = []
        for ev in (r.json().get("value") or []):
            if ev.get("isAllDay") or (ev.get("showAs") or "busy") in ("free", "workingElsewhere"):
                continue
            st = ((ev.get("start") or {}).get("dateTime") or "")[:19].replace("T", " ")
            en = ((ev.get("end") or {}).get("dateTime") or "")[:19].replace("T", " ")
            if not st or not en:
                continue
            out.append({"subject": "Họp" if mask else (ev.get("subject") or "Họp"),
                        "start": st, "end": en, "showAs": ev.get("showAs") or "busy"})
        return out
    except Exception:
        return []


def _ms_today_events(email):
    """Today's Outlook/Teams meetings for `email` with the extra fields the home widget
    needs: `id` (for RSVP), join url, location, and the caller's own response status.
    GATED + FAIL-SAFE like _ms_meetings: returns [] unless ec_pm_calendar_sync is on and
    Graph is configured/authorized; any error -> []. Only the caller's OWN calendar is
    requested by callers of this helper."""
    try:
        conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
        if not conf.get("ec_pm_calendar_sync"):
            return []
        from ecentric_workspace.notification_center.providers import graph as msgraph
        if not msgraph.is_configured():
            return []
        ok, token = msgraph.get_app_token()
        if not ok:
            return []
        import requests
        day = nowdate()
        # NB: build these by concatenation, NOT %-formatting -- "%2B" (the URL-encoded
        # '+' of the +07:00 offset) is a format specifier to Python and raises
        # ValueError: unsupported format character 'B', which the outer except swallowed
        # into [] (the home widget showed 0 meetings while the week view worked).
        start_dt = str(day) + "T00:00:00%2B07:00"
        end_dt = str(add_days(day, 1)) + "T00:00:00%2B07:00"
        # NOTE: no $select here on purpose. A $select listing onlineMeeting/location/
        # responseStatus made Graph reject the whole request (400), which this helper
        # swallowed into [] -- the home widget showed 0 meetings while the week view
        # (which uses a short $select) showed them fine. The default projection already
        # includes every field read below.
        url = ("https://graph.microsoft.com/v1.0/users/" + email + "/calendarView"
               "?startDateTime=" + start_dt + "&endDateTime=" + end_dt +
               "&$top=50&$orderby=start/dateTime")
        r = requests.get(url, headers={"Authorization": "Bearer " + token,
                         "Prefer": 'outlook.timezone="Asia/Ho_Chi_Minh"'}, timeout=12)
        if r.status_code != 200:
            return []
        out = []
        for ev in (r.json().get("value") or []):
            if ev.get("isAllDay") or (ev.get("showAs") or "busy") in ("free", "workingElsewhere"):
                continue
            st = ((ev.get("start") or {}).get("dateTime") or "")[:19].replace("T", " ")
            en = ((ev.get("end") or {}).get("dateTime") or "")[:19].replace("T", " ")
            if not st or not en:
                continue
            join = ((ev.get("onlineMeeting") or {}) or {}).get("joinUrl") or ""
            loc = ((ev.get("location") or {}) or {}).get("displayName") or ""
            resp = ((ev.get("responseStatus") or {}) or {}).get("response") or "none"
            out.append({"id": ev.get("id") or "", "subject": ev.get("subject") or "Họp",
                        "start": st, "end": en, "join_url": join, "location": loc,
                        "response": resp, "showAs": ev.get("showAs") or "busy"})
        return out
    except Exception:
        return []


@frappe.whitelist()
def today():
    """Home 'Lịch hôm nay' widget data for the CALLER (own data only, read):
      - meetings: today's Outlook/Teams meetings (fail-safe [] when sync off/unauthorized)
      - blocks:   today's scheduled work blocks (EC PM Time Block)
      - due_unscheduled: count of tasks due today that aren't time-blocked today (the nudge)
    The client computes 'next up' + countdown from `now` + these lists."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
    day = nowdate()
    start_dt = "%s 00:00:00" % day
    end_dt = "%s 00:00:00" % add_days(day, 1)

    rows = frappe.get_all(
        BLOCK,
        filters=[["user", "=", caller], ["start", ">=", start_dt], ["start", "<", end_dt]],
        fields=["name", "task", "start", "end", "hours", "state"],
        order_by="start asc", ignore_permissions=True) or []

    scheduled_tasks = {b["task"] for b in rows if b.get("task")}
    meta = _task_meta(list(scheduled_tasks))
    blocks = []
    for b in rows:
        m = meta.get(b.get("task"), {})
        blocks.append({
            "name": b["name"], "task": b.get("task"),
            "subject": m.get("subject") or (b.get("task") or "Việc"),
            "project": m.get("project") or "",
            "start": str(b["start"]), "end": str(b["end"]),
            "state": b.get("state") or "", "hours": b.get("hours") or 0,
        })

    # Nudge: open tasks due TODAY that don't yet have a block today.
    due = frappe.get_all(
        "Task",
        or_filters=[["owner", "=", caller], ["_assign", "like", '%"{0}"%'.format(caller)]],
        filters=[["status", "not in", ["Completed", "Cancelled"]], ["exp_end_date", "=", day]],
        fields=["name", "workflow_state"], limit_page_length=0, ignore_permissions=True) or []
    due = [t for t in due if t.get("workflow_state") not in _TERMINAL_WF]
    due_unscheduled = len([t for t in due if t["name"] not in scheduled_tasks])

    return {
        "date": str(day),
        "now": str(now_datetime())[:19],
        "sync_on": bool(conf.get("ec_pm_calendar_sync")),
        "meetings": _ms_today_events(caller),
        "blocks": blocks,
        "due_unscheduled": due_unscheduled,
    }


@frappe.whitelist()
def rsvp(event_id, response, comment=None):
    """Respond to a meeting invite from ERP — writes back to Outlook via Graph, on the
    CALLER'S OWN calendar only. `response` in accept|decline|tentative. Requires
    ec_pm_calendar_sync + Calendars.ReadWrite (Application) consent on the Graph app."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    if not event_id:
        frappe.throw(_("Thiếu sự kiện."))
    action = {"accept": "accept", "decline": "decline",
              "tentative": "tentativelyAccept"}.get((response or "").lower())
    if not action:
        frappe.throw(_("Phản hồi không hợp lệ."))
    conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
    if not conf.get("ec_pm_calendar_sync"):
        frappe.throw(_("Đồng bộ lịch chưa được bật."))
    from ecentric_workspace.notification_center.providers import graph as msgraph
    if not msgraph.is_configured():
        frappe.throw(_("Chưa cấu hình lịch."))
    ok, token = msgraph.get_app_token()
    if not ok:
        frappe.throw(_("Không lấy được token lịch."))
    from urllib.parse import quote
    import requests
    try:
        url = ("https://graph.microsoft.com/v1.0/users/" + caller +
               "/events/" + quote(event_id, safe="") + "/" + action)
        body = {"sendResponse": True}
        if comment:
            body["comment"] = comment
        r = requests.post(url, headers={"Authorization": "Bearer " + token,
                          "Content-Type": "application/json"}, json=body, timeout=12)
        if r.status_code in (200, 202, 204):
            return {"ok": True, "response": (response or "").lower()}
        return {"ok": False, "code": "RSVP_" + str(r.status_code)}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "schedule rsvp")
        return {"ok": False, "code": "RSVP_EXC"}


@frappe.whitelist()
def calendar_probe():
    """DIAGNOSTIC (own calendar only): pinpoints why the calendar overlay is empty.
    Returns ONLY status codes / counts / Graph error codes -- NEVER meeting content
    (no subjects, times, attendees). Safe to call; remove once verified."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
    res = {"user": caller, "sync_on": bool(conf.get("ec_pm_calendar_sync"))}
    from ecentric_workspace.notification_center.providers import graph as msgraph
    res["configured"] = bool(msgraph.is_configured())
    if not res["configured"]:
        res["stop"] = "NOT_CONFIGURED (missing ec_graph_client_id/secret/tenant)"
        return res
    ok, token = msgraph.get_app_token()
    res["token_ok"] = bool(ok)
    if not ok:
        res["token_code"] = token  # e.g. TOKEN_401 (bad secret) / TOKEN_403 / NO_GRAPH_CREDENTIAL
        return res
    import requests
    day = nowdate()
    url = ("https://graph.microsoft.com/v1.0/users/" + caller + "/calendarView"
           "?startDateTime=" + day + "T00:00:00%2B07:00"
           "&endDateTime=" + add_days(day, 1) + "T00:00:00%2B07:00&$select=id&$top=5")
    try:
        r = requests.get(url, headers={"Authorization": "Bearer " + token,
                         "Prefer": 'outlook.timezone="Asia/Ho_Chi_Minh"'}, timeout=12)
        res["http_status"] = r.status_code
        if r.status_code == 200:
            res["count_today"] = len(r.json().get("value") or [])
        else:
            try:
                res["graph_error_code"] = ((r.json().get("error") or {}) or {}).get("code")
            except Exception:
                res["graph_error_code"] = "PARSE_FAIL"
    except Exception as e:
        res["http_status"] = "EXC"
        res["exc"] = type(e).__name__
    # counts only -- confirms the helper the home widget actually uses
    res["today_helper_count"] = len(_ms_today_events(caller))

    return res


def _team_user_ids(user):
    """User ids sharing at least one team/department with `user` (excludes self). Uses the
    same department resolution as pmperm.get_user_departments (Employee.department +
    Employee Department Membership). Fail-safe -> [] if unresolved."""
    try:
        depts = list(pmperm.get_user_departments(user) or [])
    except Exception:
        depts = []
    if not depts:
        return []
    emp_names = set()
    try:
        for e in frappe.get_all("Employee",
                                filters={"department": ["in", depts], "user_id": ["!=", ""]},
                                fields=["name", "user_id"], ignore_permissions=True) or []:
            if e.get("name"):
                emp_names.add(e["name"])
    except Exception:
        pass
    try:
        for m in frappe.get_all("Employee Department Membership",
                                filters={"department": ["in", depts]},
                                fields=["parent"], ignore_permissions=True) or []:
            if m.get("parent"):
                emp_names.add(m["parent"])
    except Exception:
        pass
    ids = set()
    if emp_names:
        for e in frappe.get_all("Employee", filters={"name": ["in", list(emp_names)],
                                "user_id": ["!=", ""]},
                                fields=["user_id"], ignore_permissions=True) or []:
            if e.get("user_id"):
                ids.add(e["user_id"])
    ids.discard(user)
    return list(ids)


@frappe.whitelist()
def viewable_users():
    """Internal users whose week the caller may open (read-only): a leader sees the whole
    company; everyone else sees their own team/department. Empty -> UI hides the picker."""
    caller = frappe.session.user
    if pmperm.can_see_all_pm_data(caller):
        flt = {"enabled": 1, "user_type": "System User",
               "name": ["not in", ["Administrator", "Guest"]]}
    else:
        ids = _team_user_ids(caller)
        if not ids:
            return {"users": []}
        flt = {"enabled": 1, "name": ["in", ids]}
    rows = frappe.get_all("User", filters=flt, fields=["name", "full_name"],
                          order_by="full_name asc", ignore_permissions=True) or []
    return {"users": rows}


def _task_meta(task_names):
    """name -> {subject, project, state, end, assignees, attach} for tooltips/labels."""
    out = {}
    if not task_names:
        return out
    rows = frappe.get_all(
        "Task", filters={"name": ["in", task_names]},
        fields=["name", "subject", "project", "workflow_state", "status", "exp_end_date", "_assign"],
        ignore_permissions=True) or []
    pids = list({r.get("project") for r in rows if r.get("project")})
    pnames = {}
    if pids:
        for p in frappe.get_all("Project", filters={"name": ["in", pids]},
                                fields=["name", "project_name"], ignore_permissions=True) or []:
            pnames[p["name"]] = p.get("project_name") or p["name"]
    att = {}
    for f in frappe.get_all("File", filters={"attached_to_doctype": "Task",
                                             "attached_to_name": ["in", task_names]},
                            fields=["attached_to_name"], ignore_permissions=True) or []:
        k = f.get("attached_to_name")
        att[k] = att.get(k, 0) + 1
    for r in rows:
        out[r["name"]] = {
            "subject": r.get("subject") or r["name"],
            "project": pnames.get(r.get("project")) or (r.get("project") or ""),
            "state": r.get("workflow_state") or r.get("status") or "",
            "end": str(r.get("exp_end_date")) if r.get("exp_end_date") else "",
            "assignees": [u for u in (frappe.parse_json(r.get("_assign") or "[]") or []) if u],
            "attach": att.get(r["name"], 0),
        }
    return out


def _open_tasks_for(user):
    """Non-terminal tasks the user owns or is assigned — the drag backlog."""
    rows = frappe.get_all(
        "Task",
        or_filters=[["owner", "=", user], ["_assign", "like", '%"{0}"%'.format(user)]],
        filters={"status": ["not in", ["Completed", "Cancelled"]]},
        fields=["name", "subject", "project", "workflow_state", "exp_end_date"],
        order_by="modified desc", limit_page_length=200, ignore_permissions=True) or []
    return [r for r in rows if r.get("workflow_state") not in _TERMINAL_WF]


@frappe.whitelist()
def place(task, start, end, note=None):
    """Create a block for the CALLER on `task` at [start, end]. Caller must be able to
    view the task."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    if not task or not start or not end:
        frappe.throw(_("Thiếu dữ liệu."))
    if not pmperm.can_view_task(_task_view_dict(task), caller):
        frappe.throw(_("Không có quyền xếp lịch cho việc này."), frappe.PermissionError)
    if get_datetime(end) <= get_datetime(start):
        frappe.throw(_("Giờ kết thúc phải sau giờ bắt đầu."))
    doc = frappe.get_doc({
        "doctype": BLOCK, "task": task, "user": caller,
        "start": start, "end": end, "state": "Dự kiến",
        "hours": round(time_diff_in_hours(end, start), 2),
        "source_note": note or "",
    })
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "task": task, "user": caller,
            "start": str(doc.start), "end": str(doc.end),
            "hours": doc.hours, "state": doc.state}


@frappe.whitelist()
def move(name, start, end):
    """Move/resize the caller's OWN block."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    b = frappe.db.get_value(BLOCK, name, ["name", "user"], as_dict=True)
    _require_own(b, caller)
    if get_datetime(end) <= get_datetime(start):
        frappe.throw(_("Giờ kết thúc phải sau giờ bắt đầu."))
    frappe.db.set_value(BLOCK, name, {
        "start": start, "end": end,
        "hours": round(time_diff_in_hours(end, start), 2),
    }, update_modified=True)
    return {"name": name, "start": str(start), "end": str(end)}


@frappe.whitelist()
def remove(name):
    """Delete the caller's OWN block."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    b = frappe.db.get_value(BLOCK, name, ["name", "user", "timesheet"], as_dict=True)
    _require_own(b, caller)
    # clean up the materialized Draft Timesheet (if any) so removing a block also
    # removes the hours it logged; best-effort, only Draft (docstatus 0).
    ts = b.get("timesheet")
    if ts:
        try:
            if frappe.db.exists("Timesheet", ts) and int(
                    frappe.db.get_value("Timesheet", ts, "docstatus") or 0) == 0:
                frappe.delete_doc("Timesheet", ts, ignore_permissions=True, force=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "schedule remove timesheet")
    frappe.delete_doc(BLOCK, name, ignore_permissions=True)
    return {"ok": True, "name": name}


@frappe.whitelist()
def confirm(names, hours_map=None):
    """Self-confirm the caller's OWN blocks (no manager approval). Sets state and,
    optionally, an edited `hours` per block. `names` = JSON list; `hours_map` = JSON
    {block_name: hours}."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    if isinstance(names, str):
        names = frappe.parse_json(names) or []
    hmap = frappe.parse_json(hours_map) if isinstance(hours_map, str) else (hours_map or {})
    done = []
    for nm in names:
        b = frappe.db.get_value(
            BLOCK, nm, ["name", "user", "task", "start", "hours", "timesheet"], as_dict=True)
        if not b or b.get("user") != caller:
            continue
        hrs = b.get("hours") or 0
        if hmap and nm in hmap:
            try:
                hrs = round(float(hmap[nm]), 2)
            except Exception:
                pass
        ts = _sync_timesheet(caller, b, hrs)
        vals = {"state": "Đã xác nhận", "hours": hrs}
        if ts:
            vals["timesheet"] = ts
        frappe.db.set_value(BLOCK, nm, vals, update_modified=True)
        done.append(nm)
    # if nothing is left elapsed-and-unconfirmed, clear the morning reminder.
    try:
        if not _pending_names_for(caller):
            _close_nudge_todo(caller)
    except Exception:
        pass
    return {"confirmed": done}


def _sync_timesheet(user, block, hours):
    """Materialize a confirmed block into a native Draft Timesheet (best-effort).

    Reuses pm.api.timesheet._create_timesheet -> ONE Draft Timesheet with a single
    time log, so there is no cross-log overlap validation (overlapping planned blocks
    can each still produce their own confirmed log). On re-confirm the existing
    (Draft) timesheet's hours are updated instead of duplicating. Never breaks the
    confirm flow: a Timesheet failure is logged and the block still confirms."""
    from ecentric_workspace.pm.api import timesheet as pmts
    try:
        existing = block.get("timesheet")
        if existing and frappe.db.exists("Timesheet", existing):
            doc = frappe.get_doc("Timesheet", existing)
            if int(getattr(doc, "docstatus", 0) or 0) == 0 and doc.get("time_logs"):
                doc.time_logs[0].hours = hours
                doc.save(ignore_permissions=True)
            return existing
        proj = frappe.db.get_value("Task", block.get("task"), "project")
        return pmts._create_timesheet(user, block.get("task"), proj, hours,
                                      "Lịch làm việc", from_time=block.get("start"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "schedule confirm timesheet")
        return None


@frappe.whitelist()
def task_history(task):
    """All blocks logged for one task (for the 'Xong' panel): rows + total hours.
    Visible only if the caller can view the task."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    if not pmperm.can_view_task(_task_view_dict(task), caller):
        frappe.throw(_("Không có quyền."), frappe.PermissionError)
    rows = frappe.get_all(
        BLOCK, filters={"task": task},
        fields=["name", "user", "start", "end", "hours", "state"],
        order_by="start asc", ignore_permissions=True) or []
    total = round(sum((r.get("hours") or 0) for r in rows), 2)
    return {"rows": rows, "total": total}


# ---- morning nudge: remind users to confirm elapsed unconfirmed hours ----------
def _pending_names_for(user):
    """Block names for `user` that have already elapsed but are still 'Dự kiến'."""
    now = str(frappe.utils.now_datetime())
    return frappe.get_all(
        BLOCK, filters={"user": user, "state": "Dự kiến", "end": ["<", now]},
        pluck="name", ignore_permissions=True) or []


def _close_nudge_todo(user):
    for n in frappe.get_all(
            "ToDo", filters={"allocated_to": user, "status": "Open",
                             "description": ["like", "%" + NUDGE_TAG + "%"]},
            pluck="name", ignore_permissions=True) or []:
        frappe.db.set_value("ToDo", n, "status", "Closed")


def _ensure_nudge_todo(user, count):
    """Upsert ONE open reminder ToDo (tagged NUDGE_TAG) for `user`. Idempotent:
    updates the existing one's count/date and cancels any duplicates."""
    desc = "%s Xác nhận giờ đã làm (%d mục) — mở Lịch làm việc" % (NUDGE_TAG, count)
    existing = frappe.get_all(
        "ToDo", filters={"allocated_to": user, "status": "Open",
                         "description": ["like", "%" + NUDGE_TAG + "%"]},
        pluck="name", ignore_permissions=True) or []
    if existing:
        frappe.db.set_value("ToDo", existing[0],
                            {"description": desc, "date": frappe.utils.nowdate()})
        for extra in existing[1:]:
            frappe.db.set_value("ToDo", extra, "status", "Cancelled")
        return existing[0]
    try:
        d = frappe.get_doc({
            "doctype": "ToDo", "allocated_to": user, "status": "Open",
            "priority": "Medium", "date": frappe.utils.nowdate(), "description": desc})
        d.insert(ignore_permissions=True)
        return d.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "schedule nudge todo")
        return None


def nudge_unconfirmed():
    """Scheduler (daily, morning): for every user with elapsed-but-unconfirmed blocks,
    ensure a 'Xác nhận giờ' reminder ToDo (shows in Nhắc việc -> /pm#schedule); clear the
    reminder for users who have nothing pending. Fully idempotent."""
    now = str(frappe.utils.now_datetime())
    counts = {}
    for r in frappe.get_all(BLOCK, filters={"state": "Dự kiến", "end": ["<", now]},
                            fields=["user"], ignore_permissions=True) or []:
        u = r.get("user")
        if u:
            counts[u] = counts.get(u, 0) + 1
    for u, c in counts.items():
        _ensure_nudge_todo(u, c)
    for t in frappe.get_all(
            "ToDo", filters={"status": "Open", "description": ["like", "%" + NUDGE_TAG + "%"]},
            fields=["name", "allocated_to"], ignore_permissions=True) or []:
        if t.get("allocated_to") not in counts:
            frappe.db.set_value("ToDo", t["name"], "status", "Closed")
    frappe.db.commit()
