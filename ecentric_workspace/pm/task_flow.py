"""PM redesign (16/10/2026) - shared task-flow services (NOT whitelisted).

One home for the rules that tasks.py (mark_done / set_status / get) and pm_inbox.py
(received / given / deadline / nudge / close_parent) both need, so the two never drift:

  * giver_of / is_giver_or_leader  - who "gave" a task (Task.owner, or the requester of the
    accepted assignment request); leaders (pmperm.can_see_all_pm_data) act as givers.
  * write_state                     - the ONE audited state write (workflow_state + native
    status + completed_on/completed_by + Version row + ToDo close + notify).
  * rollup_parent                   - "Mỗi người một việc": last child Done -> parent Review
    (+ task_ready_for_review to the giver) or Done when the parent has ec_auto_close=1.
  * deadline requests               - PM Assignment Request kind=Deadline lookups/withdraw.
  * seen tracking                   - PM Task Seen (first_seen / last_seen per task+user).
  * emit                            - notification_center events via pmnotif.notify_users.
  * followers (CC)                  - PM Task Follower: suggest_cc / add_followers / notices.

Module path: ecentric_workspace.pm.task_flow
"""

import json

import frappe
from frappe import _

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm.api import notifications as pmnotif

REQ_DT = "PM Assignment Request"
SEEN_DT = "PM Task Seen"
FOLLOW_DT = "PM Task Follower"
SRC_AUTO = "Tự động"
SRC_MANUAL = "Thêm tay"
KIND_DEADLINE = "Deadline"
KIND_ASSIGNMENT = "Assignment"
FINISHED = ("Done", "Cancelled")
# FREE-STATUS model: native `status` synced for terminal states; every other state -> Open.
STATE_STATUS = {"Done": "Completed", "Cancelled": "Cancelled"}
# Owners that are system accounts, never a real "người giao" (recurrence scheduler, patches).
_SYSTEM_USERS = ("Administrator", "Guest", "")

EV_DEADLINE_REQUESTED = "task_deadline_requested"
EV_DEADLINE_ANSWERED = "task_deadline_answered"
EV_NUDGE = "task_nudge"
EV_READY_FOR_REVIEW = "task_ready_for_review"


def truthy(v):
    return str(v if v is not None else "").strip().lower() not in ("", "0", "false", "none", "null")


def d10(v):
    return str(v)[:10] if v else None


def assignees(task):
    return pmperm.assignees_of(task)


def full_names(users):
    """email -> full_name (one query)."""
    users = [u for u in set(users or []) if u]
    if not users:
        return {}
    out = {}
    for u in frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"]):
        out[u["name"]] = u.get("full_name") or u["name"]
    return out


def person(user, names=None):
    if not user:
        return None
    names = names if names is not None else full_names([user])
    return {"user": user, "full_name": names.get(user) or user}


# --------------------------------------------------------------------------- personal log
def personal_log_projects():
    """Names of Projects flagged ec_personal_log=1 (worklog projects, hidden by default on every
    PM screen + badge). Fail-safe: before the p024 custom field exists -> nothing is hidden."""
    try:
        return set(frappe.get_all("Project", filters={"ec_personal_log": 1}, pluck="name") or [])
    except Exception:
        return set()


def drop_personal(rows, include_personal=None, personal=None, key="project"):
    """Filter task/project rows that belong to a personal-log project. Done in Python (not
    `project not in (...)`) so tasks WITHOUT a project are never dropped by SQL NULL logic."""
    if truthy(include_personal):
        return rows
    personal = personal_log_projects() if personal is None else personal
    if not personal:
        return rows
    return [r for r in rows if r.get(key) not in personal]


# --------------------------------------------------------------------------- giver
def _accepted_requesters(task_names):
    """task -> requested_by of its latest ACCEPTED assignment-kind request (batch)."""
    task_names = [t for t in (task_names or []) if t]
    if not task_names:
        return {}
    out = {}
    rows = frappe.get_all(REQ_DT, filters={"task": ["in", task_names], "status": "Accepted"},
                          fields=["task", "requested_by", "kind", "modified"],
                          order_by="modified desc", limit_page_length=0)
    for r in rows:
        if (r.get("kind") or KIND_ASSIGNMENT) == KIND_DEADLINE:
            continue
        out.setdefault(r["task"], r.get("requested_by"))
    return out


def _recurrence_owner(task_name):
    try:
        return frappe.db.get_value("PM Recurrence", {"last_task": task_name}, "owner")
    except Exception:
        return None


def givers_map(tasks):
    """Batch giver resolution for task dicts (name, owner, parent_task). Rules, in order:
    1. requester of the accepted assignment request (task went through "Cần đồng ý");
    2. Task.owner when it is a real person;
    3. system-owned (recurrence scheduler) -> parent's owner, else the recurrence rule owner."""
    tasks = [t for t in (tasks or []) if t and t.get("name")]
    req = _accepted_requesters([t["name"] for t in tasks])
    out = {}
    for t in tasks:
        g = req.get(t["name"])
        if not g:
            g = t.get("owner") or ""
        if g in _SYSTEM_USERS:
            parent = t.get("parent_task")
            g = (frappe.db.get_value("Task", parent, "owner") if parent else None) or ""
            if g in _SYSTEM_USERS:
                # recurrence occurrence: the rule owner; a split child of a recurring parent
                # resolves through its parent (only the parent is the rule's last_task).
                g = (_recurrence_owner(t["name"])
                     or (_recurrence_owner(parent) if parent else None)
                     or t.get("owner") or "")
        out[t["name"]] = g or None
    return out


def giver_of(task):
    return givers_map([task]).get(task.get("name"))


def is_giver_or_leader(task, user):
    if pmperm.can_see_all_pm_data(user):
        return True
    return bool(user) and giver_of(task) == user


EDIT_DENIED_MSG = ("Bạn chỉ xem được việc này. Chỉ người nhận, người giao, quản lý dự án, "
                   "trưởng phòng của người nhận hoặc quản trị PM mới thay đổi được.")


def can_edit_task(task, user=None):
    """PO 16/10/2026 ("siết lại"): who may CHANGE a task (status, due, assignees, steps,
    sub-tasks, labels, recurrence). Viewing stays can_view_task (project / department
    visibility); editing is limited to the people actually responsible:
      * PM leaders + PM Manager role (pmperm.can_transition_any_task);
      * the task owner, its assignees and its giver (giver_of: accepted requester / owner);
      * the Project's ec_manager;
      * the department head (Department.manager_email) of the assignees / unassigned owner;
      * for a sub-task: anyone who may edit the parent (owner / giver / assignees / manager).
    `task` is a dict/doc with at least `name`; missing fields are read from the DB."""
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    if pmperm.can_transition_any_task(user):
        return True
    t = dict(task or {})
    name = t.get("name")
    if name and not all(k in t for k in ("owner", "project", "parent_task", "_assign")):
        row = frappe.db.get_value("Task", name, ["owner", "project", "parent_task", "_assign"],
                                  as_dict=True) or {}
        for k in ("owner", "project", "parent_task", "_assign"):
            if t.get(k) is None:
                t[k] = row.get(k)
    if t.get("owner") == user:
        return True
    raw = t.get("_assign")
    assignees = raw if isinstance(raw, (list, tuple)) else (frappe.parse_json(raw or "[]") or [])
    if user in assignees:
        return True
    if name and giver_of({"name": name, "owner": t.get("owner"),
                          "parent_task": t.get("parent_task")}) == user:
        return True
    if t.get("project") and frappe.db.get_value("Project", t.get("project"), "ec_manager") == user:
        return True
    # PO 16/10/2026: the department head of the assignee(s) (or of the owner when unassigned)
    if pmperm.is_department_head_of_any(user, assignees or [t.get("owner")]):
        return True
    parent = t.get("parent_task")
    if parent and parent != name:
        return can_edit_task({"name": parent}, user)
    return False


def require_edit(task, user=None):
    if not can_edit_task(task, user):
        frappe.throw(_(EDIT_DENIED_MSG), frappe.PermissionError)


# --------------------------------------------------------------------------- notify
def emit(event_type, users, task_name, title, message="", actor=None, suffix=None,
         action_task=None):
    """Publish one notification_center event per recipient (actor/Administrator/dupes skipped
    by notify_users). action_url = /pm#task/<id> (build_pm_task_url inside notify_users).
    `suffix` makes the dedupe key unique per occurrence (request name, hour bucket, ...)."""
    users = [u for u in (users or []) if u]
    if not users:
        return
    try:
        pmnotif.notify_users(users, title, action_task or task_name, from_user=actor,
                             event_type=event_type, message=message or "",
                             due_suffix=suffix)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM emit " + str(event_type))


# --------------------------------------------------------------------------- state write
def _version(name, changes):
    """Manual Version row: db.set_value bypasses doc.save(), so the timeline would otherwise
    lose the state change (audit gap found 07/10). Best-effort, never blocks the write."""
    try:
        frappe.get_doc({
            "doctype": "Version", "ref_doctype": "Task", "docname": name,
            "data": json.dumps({"added": [], "changed": changes, "removed": [],
                                "row_changed": []}, default=str),
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM state version " + str(name))


def _close_open_todos(name):
    """Closing the task clears it from everyone's Nhắc việc (native assign_to ToDos)."""
    try:
        for t in frappe.get_all("ToDo", filters={"reference_type": "Task", "reference_name": name,
                                                 "status": "Open"}, pluck="name"):
            frappe.db.set_value("ToDo", t, "status", "Closed")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM set_status close todos")


def write_state(name, target, user, notify=True):
    """THE audited state write used by set_status / mark_done / roll-up / close_parent.
    Free-status by design (no workflow transition graph) -> db.set_value, plus:
    completed_on/completed_by set on -> Done and cleared on leaving Done, a Version row,
    ToDo close on terminal, and the legacy 'mention' notice to owner + assignees.
    Returns the previous state (unchanged task -> no write, returns target)."""
    row = frappe.db.get_value("Task", name, ["workflow_state", "completed_on", "completed_by"],
                              as_dict=True) or {}
    cur = row.get("workflow_state")
    if cur == target:
        return cur
    values = {"workflow_state": target, "status": STATE_STATUS.get(target, "Open")}
    if target == "Done":
        values["completed_on"] = frappe.utils.nowdate()
        values["completed_by"] = user
    elif cur == "Done":
        values["completed_on"] = None
        values["completed_by"] = None
    frappe.db.set_value("Task", name, values)
    changes = [["workflow_state", cur, target]]
    for f in ("completed_on", "completed_by"):
        if f in values and str(row.get(f) or "") != str(values[f] or ""):
            changes.append([f, row.get(f), values[f]])
    _version(name, changes)
    if target in FINISHED:
        _close_open_todos(name)
    if notify:
        try:
            d2 = frappe.get_doc("Task", name).as_dict()
            pmnotif.notify_users(pmnotif._task_recipients(d2, exclude=user),
                                 "Nhiem vu '" + (d2.get("subject") or name) + "' -> " + target,
                                 name, event_type="mention", severity="info", due_suffix=target)
        except Exception:
            pass
        if target == "Done":
            notify_followers_done(name, user)   # người theo dõi (CC) biết việc đã xong
    return cur


def add_comment(name, text, comment_type="Info"):
    try:
        frappe.get_doc("Task", name).add_comment(comment_type, text)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM add_comment " + str(name))


# --------------------------------------------------------------------------- roll-up
def children_progress(name):
    """{done, total, open} over DIRECT children (Cancelled children excluded from total)."""
    kids = frappe.get_all("Task", filters={"parent_task": name},
                          fields=["name", "workflow_state", "status"], limit_page_length=0)
    if not kids:
        return None
    live = [k for k in kids if k.get("workflow_state") != "Cancelled"]
    done = len([k for k in live if k.get("workflow_state") == "Done"])
    open_ = len([k for k in kids if not pmperm.is_task_terminal(k)])
    return {"done": done, "total": len(live), "open": open_}


def rollup_parent(child_name, user):
    """After a child reaches a terminal state: if its parent is a split parent
    (ec_split_parent=1, "Mỗi người một việc") and no child is open any more, move the parent to
    Review and tell the giver (task_ready_for_review), or straight to Done when the parent has
    ec_auto_close=1. Logged via write_state (Version) + an Info comment. Returns the new parent
    state or None when nothing changed."""
    parent = frappe.db.get_value("Task", child_name, "parent_task")
    if not parent:
        return None
    p = frappe.db.get_value("Task", parent, ["name", "subject", "owner", "parent_task",
                                             "workflow_state", "status", "ec_split_parent",
                                             "ec_auto_close"], as_dict=True)
    if not p or not truthy(p.get("ec_split_parent")):
        return None
    if pmperm.is_task_terminal(p) or p.get("workflow_state") == "Review":
        return None
    prog = children_progress(parent)
    if not prog or prog["open"] or not prog["done"]:
        return None
    target = "Done" if truthy(p.get("ec_auto_close")) else "Review"
    write_state(parent, target, user, notify=False)
    summary = "{0}/{1}".format(prog["done"], prog["total"])
    if target == "Done":
        add_comment(parent, _("Tự đóng: {0} người đã xong.").format(summary))
    else:
        add_comment(parent, _("Chờ duyệt: {0} người đã xong.").format(summary))
        modified = frappe.db.get_value("Task", parent, "modified")
        emit(EV_READY_FOR_REVIEW, [giver_of(p)], parent,
             _("Đủ người xong: {0}").format(p.get("subject") or parent),
             _("{0} đã xong, việc đang chờ bạn duyệt.").format(summary),
             actor=user, suffix="review|" + str(modified or ""))
    return target


# --------------------------------------------------------------------------- deadline requests
def deadline_keys(task, requester, is_open):
    """Open keys for a Deadline request: distinct namespace from assignment requests so a
    deadline request never collides with the 'one open assignment request per task' key."""
    if not is_open:
        return None, None
    return "DL::{0}::{1}".format(task, requester), "DL::{0}".format(task)


def open_deadline_request(task_name):
    rows = frappe.get_all(REQ_DT, filters={"task": task_name, "kind": KIND_DEADLINE,
                                           "status": "Pending"},
                          fields=["name", "requested_by", "recipient", "proposed_end",
                                  "message", "creation"],
                          order_by="creation desc", limit_page_length=1)
    return rows[0] if rows else None


def close_deadline_request(doc, status, action, detail=None):
    """Mutate + save a Deadline request inside the assignment service scope (the
    pm_assignment_request_guard rejects writes made outside it)."""
    from ecentric_workspace.pm.api import assignment as pmasg
    doc.status = status
    doc.open_request_key, doc.open_task_key = deadline_keys(doc.task, doc.requested_by, False)
    if status in ("Accepted", "Rejected"):
        doc.decided_at = frappe.utils.now_datetime()
        doc.decided_by = frappe.session.user
        doc.response_reason = detail
    pmasg._event(doc, action, detail=detail)
    with pmasg._service():
        doc.save(ignore_permissions=True)
    return doc


def withdraw_open_deadline(task_name, detail):
    """Cancel the task's pending Deadline request (e.g. the assignee pressed Xong)."""
    row = open_deadline_request(task_name)
    if not row:
        return None
    doc = frappe.get_doc(REQ_DT, row["name"])
    close_deadline_request(doc, "Cancelled", "Withdrawn", detail)
    return doc.name


# --------------------------------------------------------------------------- seen tracking
def seen_key(task, user):
    return "{0}::{1}".format(task, user)


def record_seen(task, user):
    """First open stamps first_seen; every open refreshes last_seen. tasks.get may arrive as
    GET (pm_app apiFetch), so ask Frappe to commit this tracking write (flags.commit)."""
    now = frappe.utils.now_datetime()
    key = seen_key(task, user)
    try:
        if frappe.db.exists(SEEN_DT, key):
            frappe.db.set_value(SEEN_DT, key, "last_seen", now, update_modified=False)
        else:
            frappe.get_doc({"doctype": SEEN_DT, "name": key, "task": task, "user": user,
                            "first_seen": now, "last_seen": now}).insert(ignore_permissions=True)
        frappe.local.flags.commit = True
    except frappe.DuplicateEntryError:
        return
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM record_seen " + str(task))
        return
    # Durable on GET: tasks.get is a read (pm_app sends it as GET, which Frappe does not commit),
    # so commit the tracking row explicitly. tasks.get makes no other write before this point.
    # Never allowed to break the read that triggered it.
    try:
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM record_seen commit " + str(task))


def seen_pairs(task_names):
    """{(task, user): last_seen} for the given tasks (one query)."""
    task_names = [t for t in (task_names or []) if t]
    if not task_names:
        return {}
    out = {}
    for r in frappe.get_all(SEEN_DT, filters={"task": ["in", task_names]},
                            fields=["task", "user", "last_seen", "first_seen"],
                            limit_page_length=0):
        out[(r["task"], r["user"])] = r.get("last_seen") or r.get("first_seen")
    return out


# --------------------------------------------------------------------------- per-person rows
def is_late(row, today):
    """Late = open past its end date, or Done after its end date (completed_on > end)."""
    end = d10(row.get("exp_end_date"))
    if not end:
        return False
    if row.get("workflow_state") == "Done":
        done = d10(row.get("completed_on"))
        return bool(done and done > end)
    return row.get("workflow_state") != "Cancelled" and end < str(today)


def checklist_steps(names):
    """task -> "done/total" checklist summary (one query)."""
    out = {}
    if not names:
        return out
    for r in frappe.get_all("PM Task Checklist Item",
                            filters={"parent": ["in", list(names)], "parenttype": "Task"},
                            fields=["parent", "is_done"], limit_page_length=0):
        a = out.setdefault(r["parent"], [0, 0])
        a[1] += 1
        if r.get("is_done"):
            a[0] += 1
    return {k: "{0}/{1}".format(v[0], v[1]) for k, v in out.items()}


def person_row(user, t, seen, steps, today):
    """ONE shape for "a person's part" - used by pm_inbox.given batches[].people[] and by
    tasks.get children_progress.people[] (contract: test_contract_shapes.PERSON_KEYS)."""
    return {"user": user, "full_name": None, "task": t["name"], "state": t.get("workflow_state"),
            "opened": bool(user and (t["name"], user) in seen),
            "done_on": d10(t.get("completed_on")) if t.get("workflow_state") == "Done" else None,
            "late": is_late(t, today), "steps": steps.get(t["name"])}


def children_people(name):
    """Per-child person rows (live children only) for the task-detail "Từng người" tab."""
    kids = [k for k in frappe.get_all("Task", filters={"parent_task": name},
                                      fields=["name", "workflow_state", "_assign",
                                              "exp_end_date", "completed_on"],
                                      order_by="creation asc", limit_page_length=0)
            if k.get("workflow_state") != "Cancelled"]
    if not kids:
        return []
    names = [k["name"] for k in kids]
    seen, steps, today = seen_pairs(names), checklist_steps(names), frappe.utils.nowdate()
    rows = []
    for k in kids:
        asg = assignees(k)
        rows.append(person_row(asg[0] if asg else None, k, seen, steps, today))
    fn = full_names([r["user"] for r in rows])
    for r in rows:
        r["full_name"] = fn.get(r["user"]) or r["user"]
    return rows


# --------------------------------------------------------------------------- audit history
HISTORY_LIMIT = 20


def state_history(name, limit=HISTORY_LIMIT):
    """Recent workflow_state changes of a task, newest first, read back from the Version rows
    that write_state (and any validated save) leaves: [{at, by, by_name, from, to}].
    Read-only + fail-safe: an unreadable Version row is skipped, never raised."""
    try:
        rows = frappe.get_all("Version", filters={"ref_doctype": "Task", "docname": name},
                              fields=["name", "owner", "creation", "data"],
                              order_by="creation desc", limit_page_length=limit * 3)
    except Exception:
        return []
    out = []
    for v in rows:
        try:
            data = json.loads(v.get("data") or "{}")
        except Exception:
            continue
        for ch in (data.get("changed") or []):
            if isinstance(ch, (list, tuple)) and len(ch) >= 3 and ch[0] == "workflow_state":
                out.append({"at": str(v.get("creation") or ""), "by": v.get("owner"),
                            "by_name": None, "from": ch[1], "to": ch[2]})
        if len(out) >= limit:
            break
    out = out[:limit]
    fn = full_names([h["by"] for h in out])
    for h in out:
        h["by_name"] = fn.get(h["by"]) or h["by"]
    return out


# --------------------------------------------------------------------------- checklist
def missing_required_steps(doc):
    """Count of required checklist steps not ticked (mark_done blocks on > 0)."""
    return len([d for d in (doc.get("pm_checklist") or [])
                if d.get("is_required") and not d.get("is_done")])


# --------------------------------------------------------------------------- followers (CC)
# PO 20/10/2026: "giao việc cho member của team khác thì CC thêm manager của bạn đó".
#   * auto-CC = department head(s) (Department.manager_email) of each assignee, ONLY when the
#     giver works in a different department (same-team work stays quiet);
#   * an assignee who is a department head themselves is a manager -> never CC upwards (CEO);
#   * never the giver, never someone who is already an assignee.
# A follower can view + comment (pmperm.can_view_task), is not an assignee (never in Việc của
# tôi), and gets a notice when CC'd, when the work is done and when it runs late.
def _norm_user(u):
    return (u or "").strip().lower()


def _user_depts(user):
    return set(pmperm.get_user_departments(user) or [])


def is_department_head(user):
    """True when `user` heads at least one department (= a manager)."""
    if not user:
        return False
    try:
        return bool(frappe.db.exists("Department", {"manager_email": user}))
    except Exception:
        return False


def _heads_of_depts(depts):
    if not depts:
        return []
    rows = frappe.get_all("Department", filters={"name": ["in", sorted(depts)]},
                          fields=["manager_email"], ignore_permissions=True) or []
    heads = []
    for r in rows:
        h = (r.get("manager_email") or "").strip()
        if h and h not in heads:
            heads.append(h)
    if not heads:
        return []
    ok = set(frappe.get_all("User", filters={"name": ["in", heads], "enabled": 1}, pluck="name") or [])
    return [h for h in heads if h in ok]


def suggest_cc(giver, assignees_list):
    """[{user, for: [assignees]}] - automatic CC for a giver handing work to `assignees_list`."""
    asg = [a for a in (assignees_list or []) if a]
    asg_set = set(_norm_user(a) for a in asg)
    gdepts = _user_depts(giver)
    out, order = {}, []
    for a in asg:
        if _norm_user(a) == _norm_user(giver) or is_department_head(a):
            continue  # own task / a manager: no CC upwards
        ad = _user_depts(a)
        if not ad or (ad & gdepts):
            continue  # same department (or unknown): no automatic CC
        for h in _heads_of_depts(ad):
            if _norm_user(h) in asg_set or _norm_user(h) == _norm_user(giver):
                continue
            if h not in out:
                out[h] = []
                order.append(h)
            if a not in out[h]:
                out[h].append(a)
    return [{"user": h, "for": out[h]} for h in order]


def head_conflicts(assignees_list):
    """[{head, members}] - an assignee who is the department head of other assignees (the
    "Thai Cao + his team" case): the form suggests moving the head to CC."""
    asg = [a for a in (assignees_list or []) if a]
    out = []
    for h in asg:
        if not is_department_head(h):
            continue
        members = [m for m in asg if m != h and h in _heads_of_depts(_user_depts(m))]
        if members:
            out.append({"head": h, "members": members})
    return out


def follower_rows(task_names):
    names = [t for t in (task_names or []) if t]
    if not names:
        return []
    return frappe.get_all(FOLLOW_DT, filters={"task": ["in", names]},
                          fields=["task", "user", "source", "for_users", "added_by"],
                          order_by="creation asc", limit_page_length=0) or []


def followers_of(task_name):
    return [r["user"] for r in follower_rows([task_name])]


def _for_list(row):
    try:
        v = json.loads(row.get("for_users") or "[]") or []
    except Exception:
        v = []
    return [u for u in v if isinstance(u, str)]


def add_followers(task_name, items, actor, source=SRC_MANUAL, notify=True, assignees_list=None):
    """Attach followers to `task_name`. items: list of email or {user, for}. Skips assignees,
    the actor's own row is allowed (self-follow). Audited with an Info comment. Returns the
    users actually added."""
    if not task_name or not items:
        return []
    asg = set(_norm_user(a) for a in (assignees_list or []))
    asg |= set(_norm_user(a) for a in assignees({"name": task_name}))
    for k in frappe.get_all("Task", filters={"parent_task": task_name}, fields=["_assign"],
                            limit_page_length=0) or []:
        asg |= set(_norm_user(a) for a in assignees(k))   # split parts: their people are doers
    existing = set(_norm_user(u) for u in followers_of(task_name))
    added = []
    for it in items:
        u = it.get("user") if isinstance(it, dict) else it
        fu = (it.get("for") if isinstance(it, dict) else None) or []
        if not u or _norm_user(u) in asg or _norm_user(u) in existing or u in _SYSTEM_USERS:
            continue
        if not frappe.db.exists("User", {"name": u, "enabled": 1}):
            continue
        try:
            frappe.get_doc({"doctype": FOLLOW_DT, "name": "{0}::{1}".format(task_name, u),
                            "task": task_name, "user": u, "source": source,
                            "for_users": json.dumps(fu) if fu else None,
                            "added_by": actor}).insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            continue
        existing.add(_norm_user(u))
        added.append(u)
    if added:
        names = full_names(added)
        add_comment(task_name, "Thêm người theo dõi (CC): " + ", ".join(names.get(u) or u for u in added))
        if notify:
            _notify_cc(task_name, added, actor)
    return added


def remove_follower(task_name, user, actor):
    key = "{0}::{1}".format(task_name, user)
    if not frappe.db.exists(FOLLOW_DT, key):
        return False
    frappe.delete_doc(FOLLOW_DT, key, ignore_permissions=True)
    add_comment(task_name, "Bỏ người theo dõi (CC): " + (full_names([user]).get(user) or user))
    return True


def relevant_followers(task_row):
    """Followers to tell about `task_row` (dict with name, parent_task, _assign): the task's own
    followers + its parent's followers (split part); a parent follower with `for_users` only
    hears about the parts of the people they were CC'd for."""
    own = follower_rows([task_row.get("name")])
    users = [r["user"] for r in own]
    parent = task_row.get("parent_task")
    if parent:
        asg = set(assignees(task_row))
        for r in follower_rows([parent]):
            fu = set(_for_list(r))
            if (not fu or (fu & asg)) and r["user"] not in users:
                users.append(r["user"])
    return [u for u in users if u not in assignees(task_row)]


def _notify_cc(task_name, users, actor):
    try:
        t = frappe.db.get_value("Task", task_name, ["subject", "_assign"], as_dict=True) or {}
        kids = frappe.get_all("Task", filters={"parent_task": task_name}, fields=["_assign"],
                              limit_page_length=0) or []
        who = assignees({"name": task_name, "_assign": t.get("_assign")})
        for k in kids:
            who += [u for u in assignees(k) if u not in who]
        who = [u for u in who if u != actor]
        names = full_names(who + [actor])
        title = "Bạn được CC: {0} giao “{1}”{2}".format(
            names.get(actor) or actor, t.get("subject") or task_name,
            (" cho " + ", ".join(names.get(u) or u for u in who[:4]) + ("…" if len(who) > 4 else "")) if who else "")
        pmnotif.notify_users(users, title, task_name, from_user=actor, event_type="task_assigned",
                             severity="info", due_suffix="cc")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM notify cc " + str(task_name))


def notify_followers_done(task_name, actor):
    """Task reached Done -> tell its followers (and the parent's followers CC'd for this person)."""
    try:
        row = frappe.db.get_value("Task", task_name, ["name", "subject", "parent_task", "_assign"],
                                  as_dict=True) or {}
        users = [u for u in relevant_followers(row) if u != actor]
        if not users:
            return
        doer = assignees(row)
        names = full_names(doer + [actor])
        title = "Đã xong: “{0}”{1}".format(row.get("subject") or task_name,
                                         (" · " + ", ".join(names.get(u) or u for u in doer[:3])) if doer else "")
        pmnotif.notify_users(users, title, task_name, from_user=actor, event_type="mention",
                             severity="info", due_suffix="cc-done", allow_terminal=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "PM notify followers done " + str(task_name))


def followed_task_names(user):
    return frappe.get_all(FOLLOW_DT, filters={"user": user}, pluck="task", limit_page_length=0) or []

