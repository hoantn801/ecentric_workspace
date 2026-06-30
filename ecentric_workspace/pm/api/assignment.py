"""PM v2 - Batch G5.0: Assignment Acceptance (service layer, trust boundary).

A requester proposes giving a Task to a recipient with a proposed schedule + message; the
recipient Accepts / Rejects (reason) / Proposes a new time (counter + reason). On mutual
agreement the Task is assigned, the agreed schedule written (G4.11 validation), and a Backlog
task is moved to To Do via the governed workflow. NOTHING about the Task changes before Accept.

Security (mirrors labels): the DocTypes carry System-Manager-READ-ONLY DocPerm and no PM-role
DocPerm, so every mutation must come through these whitelisted methods, each running its guard
chain before ignore_permissions writes. open_request_key (unique) blocks two concurrent OPEN
requests for the same (task, recipient). Audit is an append-only child table; history is never
mutated/deleted via generic CRUD (System Manager read-only + before_delete guard in hooks).

Module path: ecentric_workspace.pm.api.assignment
"""

import contextlib

import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime
from frappe.desk.form.assign_to import add as _assign_add
from frappe.model.workflow import apply_workflow

from ecentric_workspace.pm import permissions as pmperm

DT = "PM Assignment Request"
OPEN_STATUSES = ("Pending", "Reschedule Proposed")
_EVENT_FIELDS = ("event_time", "actor", "action", "detail",
                 "old_start", "old_end", "new_start", "new_end")


@contextlib.contextmanager
def _service():
    """B2: mark the current scope as a legitimate assignment.py mutation. The before_save guard
    rejects any PM Assignment Request write made OUTSIDE this scope (incl. Administrator generic
    CRUD). Set + restored in try/finally -> never a leaked permissive global."""
    prev = frappe.flags.get("pm_assignment_service")
    frappe.flags.pm_assignment_service = True
    try:
        yield
    finally:
        frappe.flags.pm_assignment_service = prev
TERMINAL_TASK_STATES = ("Backlog", "To Do")  # G5.0 v1: only delegate a fresh task


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _open_key(task, recipient):
    return "{0}::{1}".format(task, recipient)


def _set_open_keys(doc):
    """B3: both keys present only while OPEN; NULL otherwise (MariaDB allows multiple NULLs).
    open_request_key = '<task>::<recipient>' (one open request per pair); open_task_key = '<task>'
    (the canonical 'one OPEN request per TASK' invariant, any recipient). One canonical helper."""
    is_open = doc.status in OPEN_STATUSES
    doc.open_request_key = _open_key(doc.task, doc.recipient) if is_open else None
    doc.open_task_key = doc.task if is_open else None


def _event(doc, action, detail=None, old_start=None, old_end=None, new_start=None, new_end=None):
    doc.append("events", {
        "event_time": now_datetime(), "actor": frappe.session.user, "action": action,
        "detail": detail, "old_start": old_start, "old_end": old_end,
        "new_start": new_start, "new_end": new_end,
    })


def _recipient_eligible(recipient):
    """Enabled System User who can enter PM (not disabled, not Website User)."""
    u = frappe.db.get_value("User", recipient, ["enabled", "user_type"], as_dict=True)
    if not u or not u.get("enabled") or u.get("user_type") == "Website User":
        frappe.throw(_("Người nhận không hợp lệ (tài khoản bị khoá hoặc không phải người dùng hệ thống)."))
    if not pmperm.has_pm_module_access(recipient):
        frappe.throw(_("Người nhận không có quyền truy cập PM."))


def _existing_task_eligible(task_doc):
    """G5.0 v1: an existing task may be delegated only when fresh — not a transfer/reassignment."""
    if pmperm.is_task_terminal(task_doc):
        frappe.throw(_("Không thể giao nhiệm vụ đã hoàn thành/huỷ."))
    if task_doc.get("workflow_state") not in TERMINAL_TASK_STATES:
        frappe.throw(_("Chỉ có thể gửi yêu cầu khi nhiệm vụ đang ở Backlog hoặc To Do."))
    if (task_doc.get("_assign") or "").strip("[] "):
        frappe.throw(_("Nhiệm vụ đã được giao cho người khác."))
    if frappe.db.exists("PM Timer", {"task": task_doc.name}):
        frappe.throw(_("Nhiệm vụ đang có bộ đếm giờ — không thể gửi yêu cầu giao việc."))
    if frappe.db.exists(DT, {"task": task_doc.name, "status": ["in", OPEN_STATUSES]}):
        frappe.throw(_("Nhiệm vụ đã có một yêu cầu giao việc đang mở."))


def _split(dt):
    """Datetime -> ('YYYY-MM-DD', 'HH:MM:SS') or (None, None)."""
    if not dt:
        return None, None
    d = get_datetime(dt)
    return d.date().isoformat(), d.strftime("%H:%M:%S")


def _as_dict(doc):
    return {
        "name": doc.name, "task": doc.task, "recipient": doc.recipient,
        "requested_by": doc.requested_by, "status": doc.status,
        "proposed_start": str(doc.proposed_start) if doc.proposed_start else None,
        "proposed_end": str(doc.proposed_end) if doc.proposed_end else None,
        "message": doc.get("message"), "response_reason": doc.get("response_reason"),
        "counter_start": str(doc.counter_start) if doc.counter_start else None,
        "counter_end": str(doc.counter_end) if doc.counter_end else None,
        "decided_at": str(doc.decided_at) if doc.decided_at else None,
        "decided_by": doc.get("decided_by"),
        "events": [{"event_time": str(e.event_time), "actor": e.actor, "action": e.action,
                    "detail": e.get("detail")} for e in (doc.get("events") or [])],
    }


def _is_requester_or_leader(doc, user):
    return (doc.requested_by == user) or pmperm.can_see_all_pm_data(user) \
        or ("PM Manager" in pmperm._roles(user))


def _apply_acceptance(doc, agreed_start, agreed_end, actor):
    """Mutual agreement: assign the task (canonical), write the agreed schedule (G4.11 validation),
    and move a Backlog task to To Do via the governed workflow. No raw _assign / db_set."""
    from ecentric_workspace.pm.api import tasks as pmtasks
    task = doc.task
    _assign_add({"doctype": "Task", "name": task, "assign_to": [doc.recipient]})  # canonical
    sd, st = _split(agreed_start)
    ed, et = _split(agreed_end)
    if sd or ed or st or et:
        pmtasks._validate_time_window(sd, st, ed, et)  # G4.11 rule
        tdoc = frappe.get_doc("Task", task)
        tdoc.exp_start_date = sd or tdoc.exp_start_date
        tdoc.exp_end_date = ed or tdoc.exp_end_date
        tdoc.pm_start_time = st
        tdoc.pm_end_time = et
        tdoc.save(ignore_permissions=True)
    tdoc = frappe.get_doc("Task", task)
    if tdoc.get("workflow_state") == "Backlog":
        # B1: the actor may be the requester (not the assignee); a NARROWLY scoped flag lets the
        # Task before_save guard pass ONLY this governed Backlog->To Do for THIS task with the
        # recipient already assigned. Set + cleared in try/finally.
        prev = frappe.flags.get("pm_assignment_acceptance")
        frappe.flags.pm_assignment_acceptance = {"task": task, "recipient": doc.recipient}
        try:
            apply_workflow(tdoc, "Move to To Do")  # governed + audited (exact action)
        finally:
            frappe.flags.pm_assignment_acceptance = prev


# --------------------------------------------------------------------------
# create
# --------------------------------------------------------------------------
@frappe.whitelist()
def create_request(task, recipient, proposed_start=None, proposed_end=None, message=None):
    """Create a Pending request for an EXISTING eligible task. Only a delegator (owner / project
    manager / PM Manager / leader) may create one."""
    pmperm.require_pm_access()
    user = frappe.session.user
    tdoc = frappe.get_doc("Task", task)
    if not pmperm.can_request_task_assignment(tdoc.as_dict(), user):
        frappe.throw(_("Bạn không có quyền giao nhiệm vụ này."), frappe.PermissionError)
    _recipient_eligible(recipient)
    _existing_task_eligible(tdoc)
    doc = frappe.get_doc({
        "doctype": DT, "task": task, "recipient": recipient, "requested_by": user,
        "status": "Pending", "proposed_start": proposed_start, "proposed_end": proposed_end,
        "message": message,
    })
    _set_open_keys(doc)
    _event(doc, "Created", detail=message, new_start=proposed_start, new_end=proposed_end)
    try:
        with _service():
            doc.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        frappe.throw(_("Nhiệm vụ đã có một yêu cầu giao việc đang mở."))
    return _as_dict(doc)


@frappe.whitelist()
def create_with_task(subject, recipient, project=None, description=None, priority=None,
                     proposed_start=None, proposed_end=None, message=None,
                     checklist_template=None, labels=None):
    """G5.0 primary flow: create a NEW UNASSIGNED Backlog task + its assignment request in ONE
    transaction. The task stays unassigned in Backlog until Accepted. Rolls back on any failure."""
    pmperm.require_pm_access()
    user = frappe.session.user
    if not subject:
        frappe.throw(_("Tên nhiệm vụ là bắt buộc."))
    _recipient_eligible(recipient)
    from ecentric_workspace.pm.api import tasks as pmtasks
    from ecentric_workspace.pm.api import labels as pmlabels
    sd, st = _split(proposed_start)
    ed, et = _split(proposed_end)
    try:
        t = pmtasks.create(project or "", subject, priority=priority, description=description,
                           exp_start_date=sd, exp_end_date=ed, pm_start_time=st, pm_end_time=et)
        task_name = t["name"]
        if labels:
            pmlabels.set_task_labels(task_name, labels)
        if checklist_template:
            tmpl = frappe.get_doc("PM Checklist Template", checklist_template)
            if tmpl.get("is_active"):
                tdoc = frappe.get_doc("Task", task_name)
                for it in sorted(tmpl.get("items") or [], key=lambda x: (x.idx or 0)):
                    tdoc.append("pm_checklist", {"item_label": it.item_label,
                                                 "is_required": it.is_required, "is_done": 0})
                tdoc.save(ignore_permissions=True)
        req = create_request(task_name, recipient, proposed_start, proposed_end, message)
    except Exception:
        frappe.db.rollback()
        raise
    return {"task": task_name, "request": req}


# --------------------------------------------------------------------------
# recipient response
# --------------------------------------------------------------------------
@frappe.whitelist()
def respond(name, decision, reason=None, counter_start=None, counter_end=None):
    """Recipient-only: accept / reject(reason) / reschedule(counter + reason)."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc(DT, name)
    if doc.recipient != user:
        frappe.throw(_("Bạn chỉ có thể phản hồi yêu cầu giao việc của mình."), frappe.PermissionError)
    if doc.status not in OPEN_STATUSES:
        frappe.throw(_("Yêu cầu này không còn mở."))

    if decision == "accept":
        agreed_start = doc.counter_start or doc.proposed_start
        agreed_end = doc.counter_end or doc.proposed_end
        _apply_acceptance(doc, agreed_start, agreed_end, user)
        doc.status = "Accepted"
        doc.decided_at = now_datetime()
        doc.decided_by = user
        _event(doc, "Accepted", new_start=agreed_start, new_end=agreed_end)
    elif decision == "reject":
        if not (reason or "").strip():
            frappe.throw(_("Vui lòng nhập lý do từ chối."))
        doc.status = "Rejected"
        doc.response_reason = reason
        doc.decided_at = now_datetime()
        doc.decided_by = user
        _event(doc, "Rejected", detail=reason)
    elif decision == "reschedule":
        if not (reason or "").strip():
            frappe.throw(_("Vui lòng nhập lý do đề xuất lịch khác."))
        if not (counter_start or counter_end):
            frappe.throw(_("Vui lòng nhập thời gian đề xuất mới."))
        doc.status = "Reschedule Proposed"
        doc.response_reason = reason
        doc.counter_start = counter_start
        doc.counter_end = counter_end
        _event(doc, "Reschedule Proposed", detail=reason,
               old_start=doc.proposed_start, old_end=doc.proposed_end,
               new_start=counter_start, new_end=counter_end)
    else:
        frappe.throw(_("Phản hồi không hợp lệ."))
    _set_open_keys(doc)
    with _service():
        doc.save(ignore_permissions=True)
    return _as_dict(doc)


# --------------------------------------------------------------------------
# requester / leader actions
# --------------------------------------------------------------------------
@frappe.whitelist()
def requester_action(name, action, proposed_start=None, proposed_end=None, message=None):
    """Requester (or leader): accept_counter / resend / cancel."""
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc(DT, name)
    if not _is_requester_or_leader(doc, user):
        frappe.throw(_("Bạn không có quyền quản lý yêu cầu này."), frappe.PermissionError)

    if action == "accept_counter":
        if doc.status != "Reschedule Proposed":
            frappe.throw(_("Không có lịch đề xuất để chấp nhận."))
        _apply_acceptance(doc, doc.counter_start, doc.counter_end, user)
        doc.status = "Accepted"
        doc.decided_at = now_datetime()
        doc.decided_by = user
        _event(doc, "Counter Accepted", new_start=doc.counter_start, new_end=doc.counter_end)
    elif action == "resend":
        if doc.status not in ("Rejected", "Cancelled", "Reschedule Proposed"):
            frappe.throw(_("Chỉ có thể gửi lại yêu cầu đã bị từ chối/huỷ hoặc đang đề xuất lịch."))
        # reuse the SAME document to keep one audit timeline.
        was = doc.status
        if proposed_start is not None:
            doc.proposed_start = proposed_start
        if proposed_end is not None:
            doc.proposed_end = proposed_end
        if message is not None:
            doc.message = message
        doc.status = "Pending"
        doc.response_reason = None
        doc.counter_start = None
        doc.counter_end = None
        doc.decided_at = None
        doc.decided_by = None
        _event(doc, "Resent" if was != "Cancelled" else "Reopened",
               new_start=doc.proposed_start, new_end=doc.proposed_end)
    elif action == "cancel":
        if doc.status not in OPEN_STATUSES:
            frappe.throw(_("Yêu cầu này không còn mở."))
        doc.status = "Cancelled"
        _event(doc, "Cancelled")
    else:
        frappe.throw(_("Thao tác không hợp lệ."))
    _set_open_keys(doc)
    try:
        with _service():
            doc.save(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        frappe.throw(_("Nhiệm vụ đã có một yêu cầu giao việc đang mở."))
    return _as_dict(doc)


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------
def _list(filters):
    rows = frappe.get_all(DT, filters=filters, fields=[
        "name", "task", "recipient", "requested_by", "status", "proposed_start",
        "proposed_end", "counter_start", "counter_end", "message", "response_reason", "modified"],
        order_by="modified desc", limit_page_length=200, ignore_permissions=True)
    names = list({r["task"] for r in rows if r.get("task")})
    subj = {}
    if names:
        for t in frappe.get_all("Task", filters={"name": ["in", tuple(names)]},
                                fields=["name", "subject"], ignore_permissions=True):
            subj[t["name"]] = t.get("subject")
    for r in rows:
        r["task_subject"] = subj.get(r.get("task")) or r.get("task")
    return {"rows": rows}


@frappe.whitelist()
def list_incoming():
    """Requests addressed to me (recipient)."""
    pmperm.require_pm_access()
    return _list({"recipient": frappe.session.user})


@frappe.whitelist()
def list_outgoing():
    """Requests I created; leaders see all."""
    pmperm.require_pm_access()
    user = frappe.session.user
    if pmperm.can_see_all_pm_data(user) or ("PM Manager" in pmperm._roles(user)):
        return _list(None)
    return _list({"requested_by": user})


@frappe.whitelist()
def get_request(name):
    pmperm.require_pm_access()
    user = frappe.session.user
    doc = frappe.get_doc(DT, name)
    if not (doc.recipient == user or _is_requester_or_leader(doc, user)):
        frappe.throw(_("Không có quyền xem yêu cầu này."), frappe.PermissionError)
    return _as_dict(doc)


def pm_assignment_request_guard(doc, method=None):
    """B2: PM Assignment Request is service-only. Reject ANY insert/update not made through
    assignment.py (incl. Administrator generic save) and enforce append-only event history."""
    if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
        return
    if not frappe.flags.get("pm_assignment_service"):
        frappe.throw(_("Yêu cầu giao việc chỉ được thay đổi qua dịch vụ PM."), frappe.PermissionError)
    before = doc.get_doc_before_save()
    if not before:
        return  # service insert
    oldmap = {e.name: e for e in (before.get("events") or [])}
    newmap = {e.name: e for e in (doc.get("events") or [])}
    for nm, o in oldmap.items():
        if nm not in newmap:
            frappe.throw(_("Không thể xoá lịch sử sự kiện."), frappe.PermissionError)
        n = newmap[nm]
        for f in _EVENT_FIELDS:
            if str(n.get(f)) != str(o.get(f)):
                frappe.throw(_("Không thể sửa lịch sử sự kiện."), frappe.PermissionError)


def pm_assignment_request_before_delete(doc, method=None):
    """G5.0: never let generic CRUD erase decided audit history. A request that was Accepted or
    Rejected (or carries audit events) cannot be hard-deleted — even by Administrator."""
    if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
        return
    if doc.get("status") in ("Accepted", "Rejected") or (doc.get("events") or []):
        frappe.throw(_("Yêu cầu đã có lịch sử và không thể xoá."), frappe.PermissionError)
