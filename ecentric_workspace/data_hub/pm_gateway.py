# Copyright (c) 2026, eCentric and contributors
"""Cong noi /pm cho Trung tam Du lieu - CHO DUY NHAT goi sang module PM.

Moi thao tac di qua SERVICE cua PM (pm.api.tasks.create / update / set_status) de giu luat PM
(kiem lich, noi rong lich du an, giao viec qua assign_to native + ToDo, thong bao "Ban duoc giao",
Version, chot "con viec con dang mo / buoc bat buoc"). Khong ghi tabTask bang tay.

Chay duoi SYSTEM_USER (repository.as_system): quyen da kiem o Trung tam Du lieu (team Data /
nguoi gui) TRUOC khi goi vao day; nguoi gui nghiem thu "Chua dat" khong co quyen sua task cua
team Data tren /pm nhung task van phai mo lai. as_system() lam rong form_dict (frappe.set_user)
- quan trong: tasks.update doc form_dict de biet truong nao "duoc gui", form_dict cua request
Trung tam Du lieu (assignee=, priority=...) khong duoc lot sang.

pm_sync.py nhan module nay qua tham so `pm` - test thay bang PM gia (cung 5 ham).
"""
import frappe

from ecentric_workspace.data_hub import repository as R


def _iso(d):
    return d.isoformat() if hasattr(d, "isoformat") else (str(d)[:10] if d else None)


def _call(fn, *args, **kwargs):
    with R.as_system():
        frappe.local.form_dict = frappe._dict()
        return fn(*args, **kwargs)


def create_task(project, subject, description, assignee, start, due, priority):
    from ecentric_workspace.pm.api import tasks
    out = _call(tasks.create, project or None, subject, priority=priority, exp_start_date=_iso(start),
                exp_end_date=_iso(due), description=description, assignee=assignee, cc="[]")
    return out["name"]


def update_task(task, **fields):
    """fields: exp_start_date / exp_end_date (date) / priority / subject."""
    from ecentric_workspace.pm.api import tasks
    clean = {k: (_iso(v) if k in ("exp_start_date", "exp_end_date") else v) for k, v in fields.items()
             if v is not None}
    if clean:
        _call(tasks.update, task, **clean)


def set_assignee(task, new, old=None):
    """Doi nguoi nhan: go het nguoi cu (assign_to native) roi giao nguoi moi."""
    from ecentric_workspace.pm.api import tasks
    current = frappe.parse_json(frappe.db.get_value("Task", task, "_assign") or "[]") or []
    if current == [new]:
        return
    if current:
        _call(tasks.update, task, assignee="")
    if new:
        _call(tasks.update, task, assignee=new)


def set_state(task, state):
    """"In Progress" / "Done" / "Cancelled" qua tasks.set_status (giu chot cua PM)."""
    from ecentric_workspace.pm.api import tasks
    if frappe.db.get_value("Task", task, "workflow_state") == state:
        return
    _call(tasks.set_status, task, state)


def exists(task):
    return bool(task) and bool(frappe.db.exists("Task", task))
