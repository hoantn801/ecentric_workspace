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
from frappe.utils import get_datetime, getdate, add_days, nowdate, time_diff_in_hours

from ecentric_workspace.pm import permissions as pmperm

BLOCK = "EC PM Time Block"
_TERMINAL_WF = ("Done", "Cancelled")


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

    `user` defaults to the caller. Viewing SOMEONE ELSE is allowed only for leaders and
    is READ-ONLY (readonly=True in the response). `week_start` is any date in the target
    week (defaults to today); the range is that week's Monday 00:00 .. +7 days."""
    pmperm.require_pm_access()
    caller = frappe.session.user
    target = user or caller
    readonly = False
    if target != caller:
        if not pmperm.can_see_all_pm_data(caller):
            frappe.throw(_("Không có quyền xem lịch người này."), frappe.PermissionError)
        readonly = True

    mon = _monday(week_start or nowdate())
    start_dt = "%s 00:00:00" % mon
    end_dt = "%s 00:00:00" % add_days(mon, 7)

    blocks = frappe.get_all(
        BLOCK,
        filters={"user": target, "start": [">=", start_dt], "end": ["<", end_dt]},
        fields=["name", "task", "user", "start", "end", "hours", "state", "source_note"],
        order_by="start asc", ignore_permissions=True) or []

    # Backlog = open tasks NOT already scheduled this week (once a task has a block this
    # week it leaves the "chưa xếp lịch" tray).
    scheduled = {b["task"] for b in blocks if b.get("task")}
    backlog = [t for t in _open_tasks_for(target) if t["name"] not in scheduled]

    # Enriched meta (label + tooltip info) for every task shown: blocks + backlog.
    task_names = list(scheduled | {t["name"] for t in backlog})
    subj, meta = {}, _task_meta(task_names)
    for nm, m in meta.items():
        subj[nm] = m.get("subject") or nm

    return {
        "readonly": readonly,
        "user": target,
        "week_start": str(mon),
        "blocks": blocks,
        "backlog": backlog,
        "subjects": subj,
        "meta": meta,
    }


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
