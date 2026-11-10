# Copyright (c) 2026, eCentric and contributors
"""Dong bo HAI CHIEU Trung tam Du lieu <-> /pm (PO chot 09/11/2026).

Trung tam Du lieu -> /pm (goi tu ops_service / service, qua pm_gateway):
  * team Data "Nhan" -> tao Task trong project Settings.pm_project: nguoi nhan, bat dau / han,
    uu tien (Khan=Urgent, Cao=High, Binh thuong=Medium, Thap=Low), mo ta co link /du-lieu?ma=...;
    luu ticket.pm_task. Task chuyen "In Progress".
  * doi han / ngay bat dau / uu tien / nguoi xu ly -> sua Task; Hoan tat -> Task Done;
    "Chua dat" (mo lai) -> Task In Progress; Huy -> Task Cancelled.
  * ticket Dang xu ly ma chua co task (lan tao truoc loi) -> lan cap nhat sau tao bu.
/pm -> Trung tam Du lieu (hook, hooks.py):
  * Task on_update (moi duong doc.save: tasks.update, Desk)          -> on_task_update
  * PM task_flow.write_state (db.set_value: set_status / mark_done)  -> on_task_state
    (khai bang hook `ec_pm_task_state_listeners` - PM khong biet gi ve Trung tam Du lieu)
  * ToDo after_insert (giao viec native tren /pm)                    -> on_todo_insert
  Task Done -> ticket Cho nghiem thu; Task mo lai khi ticket Cho nghiem thu -> Dang xu ly;
  doi exp_end_date -> doi han (nhat ky "tu /pm"); doi ngay bat dau; giao nguoi khac -> doi nguoi xu ly.

CHONG VONG LAP: moi lan Trung tam Du lieu ghi sang /pm (va moi lan ap thay doi tu /pm) dat
frappe.flags.ec_data_hub_pm_sync; ba hook phia /pm thay co do thi bo qua.
LOI KHONG LAM HONG THAO TAC CHINH: loi /pm -> Error Log + dong "Lỗi đồng bộ /pm" trong nhat ky +
canh bao nhe tra ve trang; thay doi o Trung tam Du lieu van luu. Hook phia /pm nuot moi loi
(khong bao gio lam hong thao tac luu Task cua nguoi dung /pm).
"""
from contextlib import contextmanager

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D

FLAG = "ec_data_hub_pm_sync"
WARN = "Đã lưu, nhưng chưa đồng bộ được task /pm ({0}). Team Data kiểm lại task trên /pm."


def _pm(pm):
    if pm is not None:
        return pm
    from ecentric_workspace.data_hub import pm_gateway
    return pm_gateway


def enabled(repo):
    s = repo.settings()
    return bool(int(s.get("pm_sync_enabled") or 0)) and bool(s.get("pm_project"))


@contextmanager
def guard(repo):
    flags = repo.flags()
    prev = getattr(flags, FLAG, None)
    setattr(flags, FLAG, True)
    try:
        yield
    finally:
        setattr(flags, FLAG, prev)


def busy(repo):
    return bool(getattr(repo.flags(), FLAG, None))


def _error(repo, t, actor, what, exc):
    from ecentric_workspace.data_hub import service as S
    repo.log_error("Data Hub /pm %s %s" % (what, t.get("name")))
    try:
        S.log(repo, t["name"], C.EV_PM_ERROR, actor, source=C.SRC_PM, from_value=what,
              note=str(exc)[:300])
    except Exception:
        repo.log_error("Data Hub /pm log %s" % t.get("name"))
    return WARN.format(what)


def subject(t):
    return "[%s] %s" % (t["name"], t.get("title") or "")


def description(t):
    link = "%s?ma=%s" % (C.ROUTE, t["name"])
    parts = ['<p>Yêu cầu dữ liệu <a href="%s">%s</a> (Trung tâm Dữ liệu).</p>' % (link, t["name"])]
    if t.get("description"):
        from html import escape
        parts.append("<p>%s</p>" % escape(t["description"][:1500]).replace("\n", "<br>"))
    parts.append("<p><em>Đổi hạn / hoàn tất ở đây hoặc ở Trung tâm Dữ liệu đều đồng bộ hai bên.</em></p>")
    return "".join(parts)


# ------------------------------------------------------------------ Trung tam -> /pm --------
def push_accept(repo, t, actor, pm=None):
    """-> (ten task | None, canh bao | "")."""
    if not enabled(repo):
        return None, ""
    pm = _pm(pm)
    try:
        with guard(repo):
            task = pm.create_task(repo.settings().get("pm_project"), subject(t), description(t),
                                  t.get("assignee"), D.as_date(t.get("start_date")), D.as_date(t.get("due_date")),
                                  C.PM_PRIORITY.get(t.get("priority"), "Medium"))
            repo.set_fields(t["name"], {"pm_task": task})
            t["pm_task"] = task
            pm.set_state(task, "In Progress")
    except Exception as e:
        if t.get("pm_task"):
            # Task da tao, chi buoc doi trang thai loi: giu lien ket, bao canh bao.
            return t["pm_task"], _error(repo, t, actor, "đổi trạng thái task", e)
        return None, _error(repo, t, actor, "tạo task", e)
    from ecentric_workspace.data_hub import service as S
    S.log(repo, t["name"], C.EV_PM, actor, source=C.SRC_PM, to_value="Tạo task /pm " + task)
    return task, ""


def push_change(repo, t, actor, fields, pm=None, old_assignee=None):
    """fields gom "due" / "start" / "priority" / "assignee". -> [canh bao]."""
    if not enabled(repo):
        return []
    if not t.get("pm_task"):
        if t.get("status") in (C.ST_DOING, C.ST_PAUSED) and t.get("assignee"):
            return [w for w in [push_accept(repo, t, actor, pm=pm)[1]] if w]
        return []
    pm = _pm(pm)
    try:
        with guard(repo):
            task = t["pm_task"]
            upd = {}
            if "due" in fields or "start" in fields:
                upd["exp_start_date"] = D.as_date(t.get("start_date"))
                upd["exp_end_date"] = D.as_date(t.get("due_date"))
            if "priority" in fields:
                upd["priority"] = C.PM_PRIORITY.get(t.get("priority"), "Medium")
            if upd:
                pm.update_task(task, **upd)
            if "assignee" in fields:
                pm.set_assignee(task, t.get("assignee"), old_assignee)
    except Exception as e:
        return [_error(repo, t, actor, "cập nhật task", e)]
    return []


def push_state(repo, t, actor, state, pm=None):
    if not enabled(repo) or not t.get("pm_task"):
        return []
    pm = _pm(pm)
    try:
        with guard(repo):
            pm.set_state(t["pm_task"], state)
    except Exception as e:
        return [_error(repo, t, actor, "đổi trạng thái task", e)]
    return []


# ------------------------------------------------------------------ /pm -> Trung tam --------
def apply_task(repo, code, task, actor, pm=None):
    """Ap thay doi cua Task (dict: workflow_state / status / exp_start_date / exp_end_date) len ticket.
    Khong day nguoc sang /pm (push=False) + dat co chong vong lap. -> [thay doi]."""
    from ecentric_workspace.data_hub import ops_service as O
    from ecentric_workspace.data_hub import service as S
    t = repo.lock(code)
    if not t or t.get("status") in C.CLOSED or t.get("status") == C.ST_WAITING:
        return []
    out = []
    with guard(repo):
        state = task.get("workflow_state")
        if not state and task.get("status") == "Completed":
            state = "Done"
        due = D.as_date(task.get("exp_end_date")) if "exp_end_date" in task else None
        start = D.as_date(task.get("exp_start_date")) if "exp_start_date" in task else None
        if start and t.get("status") in (C.ST_DOING, C.ST_PAUSED) and start != D.as_date(t.get("start_date")):
            old = t.get("start_date")
            repo.set_fields(code, {"start_date": start})
            t["start_date"] = start
            S.log(repo, code, C.EV_START, actor, source=C.SRC_PM, from_value=D.iso(old), to_value=start.isoformat())
            out.append("start")
        if due and t.get("status") in (C.ST_DOING, C.ST_PAUSED) and due != D.as_date(t.get("due_date")):
            O.apply_due(repo, t, actor, due, "Đổi hạn trên /pm", source=C.SRC_PM, push=False)
            out.append("due")
        if state == "Done" and t.get("status") in (C.ST_DOING, C.ST_PAUSED):
            O.apply_done(repo, t, actor, note="Hoàn tất trên /pm", source=C.SRC_PM, push=False)
            out.append("done")
        elif state and state not in ("Done", "Cancelled") and t.get("status") == C.ST_REVIEW:
            O.apply_reopen(repo, t, actor, "Task /pm được mở lại", source=C.SRC_PM, push=False, by_team=True)
            out.append("reopen")
        elif state == "Cancelled" and t.get("status") in (C.ST_DOING, C.ST_PAUSED, C.ST_REVIEW):
            # Huy yeu cau can ly do + bao nguoi gui: khong tu huy theo /pm, chi ghi lai de team Data xu ly.
            S.log(repo, code, C.EV_PM, actor, source=C.SRC_PM, from_value="Task /pm bị huỷ",
                  to_value="Yêu cầu vẫn mở - team Data huỷ ở đây nếu cần")
            out.append("pm_cancelled")
    return out


def apply_todo(repo, code, allocated_to, actor):
    """Giao viec tren /pm (ToDo moi) -> doi nguoi xu ly cua ticket."""
    from ecentric_workspace.data_hub import ops_service as O
    t = repo.lock(code)
    if not t or t.get("status") not in (C.ST_DOING, C.ST_PAUSED, C.ST_REVIEW):
        return False
    if not allocated_to or allocated_to == t.get("assignee"):
        return False
    with guard(repo):
        O.apply_assignee(repo, t, actor, allocated_to, source=C.SRC_PM, push=False)
    return True


# ------------------------------------------------------------------ hook (frappe) -----------
def _session_user():
    import frappe
    return frappe.session.user


def on_task_update(doc, method=None):
    """doc_events Task on_update (sau hook PM). Nuot moi loi."""
    from ecentric_workspace.data_hub import repository as R
    try:
        if busy(R):
            return
        code = R.find_by_pm_task(doc.name)
        if not code:
            return
        apply_task(R, code, {"workflow_state": doc.get("workflow_state"), "status": doc.get("status"),
                             "exp_start_date": doc.get("exp_start_date"), "exp_end_date": doc.get("exp_end_date")},
                   _session_user())
    except Exception:
        R.log_error("Data Hub on_task_update %s" % getattr(doc, "name", ""))


def on_task_state(name, cur, target, user=None):
    """Listener `ec_pm_task_state_listeners` (pm.task_flow.write_state - ghi bang db.set_value nen
    Task on_update khong chay). Nuot moi loi."""
    from ecentric_workspace.data_hub import repository as R
    try:
        if busy(R):
            return
        code = R.find_by_pm_task(name)
        if not code:
            return
        apply_task(R, code, {"workflow_state": target}, user or _session_user())
    except Exception:
        R.log_error("Data Hub on_task_state %s" % name)


def on_todo_insert(doc, method=None):
    """doc_events ToDo after_insert: giao Task cho nguoi khac tren /pm. Nuot moi loi."""
    from ecentric_workspace.data_hub import repository as R
    try:
        if busy(R) or doc.get("reference_type") != "Task" or doc.get("status") != "Open":
            return
        code = R.find_by_pm_task(doc.get("reference_name"))
        if not code:
            return
        apply_todo(R, code, doc.get("allocated_to"), _session_user())
    except Exception:
        R.log_error("Data Hub on_todo_insert %s" % getattr(doc, "name", ""))
