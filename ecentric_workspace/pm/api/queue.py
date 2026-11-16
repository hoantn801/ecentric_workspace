# Copyright (c) 2026, eCentric and contributors
"""Việc cần làm (PO 15/11/2026) - ONE ordered work queue per person.

The ordering rule lives HERE and only here, so the /pm page, the 08:30 Teams digest and a future
ERP MCP ("hôm nay tôi làm gì?") always agree:

    bucket (Quá hạn -> Hôm nay -> Ngày mai -> Còn lại tuần này -> Tuần sau trở đi -> Chưa có hạn)
    -> priority (Urgent -> High -> Medium -> Low)
    -> due date -> due time
    -> task name (QC 15/11: ties stay put between refreshes instead of following `modified`)

"Quá hạn" = due date before today, or due today with a time that has already passed.

QC2 15/11/2026 - who the queue is FOR (also only here):
    tab=me   main queue = what I must act on. A task I sent for review that waits for SOMEONE ELSE
             (Review, giver != me) is `waiting` (own list, never in counts / rank / top 3 / 08:30).
             A "Mỗi người một việc" parent I gave (ec_split_parent, giver = me) belongs to tab=give;
             it joins my main queue only in Review (I approve it).
    tab=give tasks I gave + my split parents (progress x/y) + tasks waiting for a recipient to accept
             my "Cần đồng ý" request (`awaiting`) + occurrences of my recurrence rules (givers_map).
             QC3: a recipient answered my request with "Đề xuất hạn khác" (Reschedule Proposed) ->
             `proposals` (own list on top, waits for ME: accept_counter / resend; never in rows/counts).
             QC4: a recipient's "Xin dời hạn" addressed to me (kind Deadline, recipient = me) joins
             `proposals` too (counter.kind = "deadline", answered with pm_inbox.answer_deadline).
    tab=me   QC4: a row I already asked to move ("Xin dời hạn" Pending) carries deadline_ask {due}.
    Rail badge "Việc cần làm" = main_count(user) = len(rows of tab=me) - same population (QC3).
    Up to 500 rows (`limit`), nearest due date first (an old overdue task is never the one cut); `truncated`.

Read-only service. Writes stay on the existing governed endpoints (tasks.create / mark_done /
set_status, assignment.*, pm_inbox.nudge / request_deadline) so permissions, audit and
notifications are unchanged."""
import datetime
import re

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate, now_datetime

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm import task_flow as tflow

BUCKETS = ("late", "today", "tomorrow", "week", "later", "none")
BUCKET_LABEL = {"late": "Quá hạn", "today": "Hôm nay", "tomorrow": "Ngày mai",
                "week": "Còn lại tuần này", "later": "Tuần sau trở đi", "none": "Chưa có hạn"}
PRIORITY_RANK = {"Urgent": 4, "High": 3, "Medium": 2, "Low": 1}
_FIELDS = ["name", "subject", "workflow_state", "status", "project", "parent_task", "is_group",
           "exp_end_date", "pm_end_time", "priority", "_assign", "owner", "modified",
           "ec_split_parent", "ec_review_required"]
_MAX_ROWS = 500
_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HM = re.compile(r"^\s*(\d{1,2})(?::(\d{1,2}))?(?::\d{1,2}(?:\.\d+)?)?\s*$")


# ------------------------------------------------------------------ the rule (pure)
def _ymd(v):
    """YYYY-MM-DD of a date / datetime / string, None when empty or not a real date
    (QC2: "16/10/2026" compared as text used to land in "Quá hạn")."""
    d = tflow.d10(v)
    if not d or not _YMD.match(d):
        return None
    try:
        datetime.date(int(d[:4]), int(d[5:7]), int(d[8:10]))
    except ValueError:
        return None
    return d


def _hm(v):
    """HH:MM of a Frappe Time (str "9:05:00", "9:5:0", timedelta, time), None when empty,
    midnight or not a time of day (QC2: "9:5:0" used to become "09:5:")."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime.timedelta):
        secs = int(v.total_seconds())
        if secs < 0 or secs >= 86400:
            return None
        h, mi = secs // 3600, (secs % 3600) // 60
    elif isinstance(v, datetime.time):
        h, mi = v.hour, v.minute
    else:
        m = _HM.match(str(v))
        if not m:
            return None
        h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59 or (h == 0 and mi == 0):
        return None
    return "%02d:%02d" % (h, mi)


def due_parts(row):
    """(YYYY-MM-DD | None, HH:MM | None). Datetime due dates and the "0:00:00" empty time
    (Frappe Time) are normalised: midnight = no time. A time without a date is ignored."""
    d = _ymd(row.get("exp_end_date"))
    return d, (_hm(row.get("pm_end_time")) if d else None)


def bucket(row, today, now_hm):
    d, t = due_parts(row)
    if not d:
        return "none"
    if d < today or (d == today and t and t < now_hm):
        return "late"
    if d == today:
        return "today"
    if d == str(add_days(today, 1)):
        return "tomorrow"
    td = getdate(today)
    week_end = str(add_days(today, 6 - td.weekday()))   # Sunday of this week
    if d <= week_end:
        return "week"
    return "later"


def priority_rank(row):
    return PRIORITY_RANK.get(row.get("priority") or "Medium", 2)


def sort_key(row, today, now_hm):
    d, t = due_parts(row)
    return (BUCKETS.index(bucket(row, today, now_hm)), -priority_rank(row), d or "9999-99-99", t or "99:99",
            str(row.get("name") or ""))


def ordered(rows, today=None, now_hm=None):
    """Sort + annotate rows with bucket / rank / due / time (1-based rank = 'làm thứ mấy')."""
    today = str(today or nowdate())
    now_hm = now_hm or str(now_datetime())[11:16]
    rows = sorted(rows, key=lambda r: sort_key(r, today, now_hm))
    for i, r in enumerate(rows):
        r["bucket"] = bucket(r, today, now_hm)
        r["rank"] = i + 1
        r["due"], r["due_time"] = due_parts(r)
        r["priority_rank"] = priority_rank(r)
    return rows


# ------------------------------------------------------------------ data
def _like_me(user):
    return '%"{0}"%'.format(user)


def _open_filters(extra):
    return [*extra, ["workflow_state", "not in", [*tflow.FINISHED]]]


def _fetch(filters):
    """Open tasks matching `filters`, at most _MAX_ROWS, NEAREST DUE DATE FIRST: dated rows
    ascending, then undated ones (QC2 15/11: a plain limit returned an arbitrary 500 and could
    drop a task that is months overdue). 2 queries; -> (rows, truncated)."""
    flt = _open_filters(filters)
    rows = frappe.get_all("Task", filters=flt + [["exp_end_date", "is", "set"]], fields=_FIELDS,
                          order_by="exp_end_date asc, name asc", limit_page_length=_MAX_ROWS + 1)
    if len(rows) <= _MAX_ROWS:
        rows += frappe.get_all("Task", filters=flt + [["exp_end_date", "is", "not set"]],
                               fields=_FIELDS, order_by="name asc",
                               limit_page_length=_MAX_ROWS + 1 - len(rows))
    return rows[:_MAX_ROWS], len(rows) > _MAX_ROWS


def _by_names(names):
    names = sorted({n for n in names if n})
    if not names:
        return []
    return frappe.get_all("Task", filters=_open_filters([["name", "in", names]]), fields=_FIELDS,
                          limit_page_length=0)


def _mine(user):
    rows, truncated = _fetch([["_assign", "like", _like_me(user)]])
    return [r for r in rows if user in tflow.assignees(r)], truncated   # exact membership


def is_split_parent(row):
    return tflow.truthy(row.get("ec_split_parent"))


def split_me(rows, user, givers):
    """tab=me -> (main, waiting). Pure: the ONE rule for what is mine to do now.
      * my own split parent (giver = me) is coordination, it lives in tab=give - unless it is
        in Review: then approving it is my job;
      * Review whose giver is someone else = I already sent it, waiting for their check."""
    main, waiting = [], []
    for r in rows:
        mine_to_give = givers.get(r["name"]) == user
        review = r.get("workflow_state") == "Review"
        if is_split_parent(r) and mine_to_give and not review:
            continue
        (waiting if review and not mine_to_give else main).append(r)
    return main, waiting


def _pending_requests(user):
    """task -> recipient of my open "Cần đồng ý" requests (Pending, assignment kind)."""
    out = {}
    try:
        for r in frappe.get_all("PM Assignment Request",
                                filters={"requested_by": user, "status": "Pending"},
                                fields=["task", "recipient", "kind"], order_by="modified desc",
                                limit_page_length=_MAX_ROWS) or []:
            if (r.get("kind") or tflow.KIND_ASSIGNMENT) == tflow.KIND_DEADLINE:
                continue
            if r.get("task") and r.get("recipient"):
                out.setdefault(r["task"], r["recipient"])
    except Exception:
        return {}
    return out


def _counter_proposals(user):
    """task -> my request the recipient answered with "Đề xuất hạn khác" (status Reschedule
    Proposed, assignment kind). One query; newest first, one per task. Fail-safe -> {}."""
    out = {}
    try:
        for r in frappe.get_all("PM Assignment Request",
                                filters={"requested_by": user, "status": "Reschedule Proposed"},
                                fields=["name", "task", "recipient", "kind", "counter_start", "counter_end",
                                        "proposed_start", "proposed_end", "response_reason"],
                                order_by="modified desc", limit_page_length=_MAX_ROWS) or []:
            if (r.get("kind") or tflow.KIND_ASSIGNMENT) == tflow.KIND_DEADLINE:
                continue
            if r.get("task") and r.get("recipient"):
                out.setdefault(r["task"], r)
    except Exception:
        return {}
    return out


def _deadline_asks_to_me(user):
    """task -> a "Xin dời hạn" an assignee sent ME (kind Deadline, recipient = me, Pending; the giver
    answers with pm_inbox.answer_deadline). One query; newest first, one per task. Fail-safe -> {}."""
    out = {}
    try:
        for r in frappe.get_all("PM Assignment Request",
                                filters={"recipient": user, "status": "Pending", "kind": tflow.KIND_DEADLINE},
                                fields=["name", "task", "requested_by", "proposed_end", "message"],
                                order_by="modified desc", limit_page_length=_MAX_ROWS) or []:
            if r.get("task") and r.get("requested_by") and r["requested_by"] != user:
                out.setdefault(r["task"], r)
    except Exception:
        return {}
    return out


def _my_deadline_asks(user):
    """task -> new due date of MY pending "Xin dời hạn" (kind Deadline, requested_by = me). Fail-safe."""
    out = {}
    try:
        for r in frappe.get_all("PM Assignment Request",
                                filters={"requested_by": user, "status": "Pending", "kind": tflow.KIND_DEADLINE},
                                fields=["task", "proposed_end"], order_by="modified desc",
                                limit_page_length=_MAX_ROWS) or []:
            if r.get("task"):
                out.setdefault(r["task"], _ymd(r.get("proposed_end")))
    except Exception:
        return {}
    return out


def _when(v):
    """(YYYY-MM-DD | None, HH:MM | None) of a stored Datetime (proposal / counter schedule)."""
    d = _ymd(v)
    return d, (_hm(str(v)[11:19]) if d and len(str(v)) > 10 else None)


def _counter_info(req):
    due, tm = _when(req.get("counter_end"))
    start, _st = _when(req.get("counter_start"))
    old, old_tm = _when(req.get("proposed_end"))
    return {"request": req.get("name"), "recipient": req.get("recipient"), "due": due, "time": tm,
            "start": start, "old_due": old, "old_time": old_tm,
            "reason": (req.get("response_reason") or "").strip(), "kind": "counter"}


def _deadline_info(req, row):
    """Same shape as _counter_info for a "Xin dời hạn": the time of day stays (answer_deadline only
    moves the date); recipient = the assignee who asked."""
    old, old_tm = due_parts(row)
    return {"request": req.get("name"), "recipient": req.get("requested_by"), "due": _ymd(req.get("proposed_end")),
            "time": old_tm, "start": None, "old_due": old, "old_time": old_tm,
            "reason": (req.get("message") or "").strip(), "kind": "deadline"}


def _accepted_via_me(user):
    try:
        return [r.get("task") for r in frappe.get_all(
            "PM Assignment Request", filters={"requested_by": user, "status": "Accepted"},
            fields=["task", "kind"], limit_page_length=_MAX_ROWS) or []
            if (r.get("kind") or tflow.KIND_ASSIGNMENT) != tflow.KIND_DEADLINE]
    except Exception:
        return []


def _my_rule_tasks(user):
    """Latest occurrence of each recurrence rule I own (owner Administrator on the Task; the
    giver rule tflow.givers_map resolves it to me through PM Recurrence.last_task)."""
    try:
        return [t for t in frappe.get_all("PM Recurrence", filters={"owner": user},
                                          pluck="last_task", limit_page_length=0) or [] if t]
    except Exception:
        return []


def _split_children(parents):
    """parent -> [non-cancelled children (any state)] for progress "x/y người xong"."""
    out = {}
    if not parents:
        return out
    for k in frappe.get_all("Task", filters={"parent_task": ["in", sorted(parents)]},
                            fields=["name", "parent_task", "workflow_state", "_assign"],
                            order_by="name asc", limit_page_length=0):
        if k.get("workflow_state") != "Cancelled":
            out.setdefault(k["parent_task"], []).append(k)
    return out


def _given(user):
    """Open tasks I gave to someone else -> (rows, proposals, givers, truncated).
    giver = tflow.givers_map (the one rule): an accepted request only counts when it is an
    ASSIGNMENT request (QC1); recurrence occurrences of my rules resolve to me (QC2).
    QC2 15/11/2026 additions (no duplicates, never someone else's task):
      * my split parent ("Mỗi người một việc") with progress {done, total}; its children are
        folded into it, except a child in Review (I must approve that one);
      * a task waiting for the recipient of MY pending "Cần đồng ý" request -> awaiting;
      * QC3: a task whose recipient proposed another deadline (Reschedule Proposed) -> proposals
        (a split child stays folded in its parent's progress AND is listed there);
      * QC4: an assignee asked ME to move the deadline ("Xin dời hạn") -> proposals as well."""
    rows, truncated = _fetch([["owner", "=", user]])
    pending = _pending_requests(user)
    counters = _counter_proposals(user)
    dasks = _deadline_asks_to_me(user)
    rules = _my_rule_tasks(user)
    have = {r["name"] for r in rows}
    extra = [t for t in _accepted_via_me(user) + [*pending] + [*counters] + [*dasks] + rules if t and t not in have]
    rows += _by_names(extra)
    if rules:   # split children of a recurring split parent (owner Administrator)
        have = {r["name"] for r in rows}
        rows += [k for k in frappe.get_all("Task", filters=_open_filters([["parent_task", "in", sorted(set(rules))]]),
                                           fields=_FIELDS, limit_page_length=0) if k["name"] not in have]
    givers = tflow.givers_map(rows)
    splits = {r["name"] for r in rows if is_split_parent(r) and givers.get(r["name"]) == user}
    kids = _split_children(splits)
    out, proposals = [], []
    for r in rows:
        name = r["name"]
        req = counters.get(name)
        if req and req["recipient"] != user:
            p = dict(r)
            p["_people"] = [(req["recipient"], name, True, False)]
            p["counter"] = _counter_info(req)
            proposals.append(p)
        elif dasks.get(name):
            dq = dasks[name]
            p = dict(r)
            p["_people"] = [(dq["requested_by"], name, False, False)]
            p["counter"] = _deadline_info(dq, r)
            proposals.append(p)
        if r.get("parent_task") in splits and r.get("workflow_state") != "Review":
            continue                                   # folded into its split parent
        if name in splits:
            ks = kids.get(name, [])
            people = []
            for k in ks:
                a = [u for u in tflow.assignees(k) if u and u != user]
                done = k.get("workflow_state") == "Done"
                if a:
                    people += [(u, k["name"], False, done) for u in a]
                elif pending.get(k["name"]) or counters.get(k["name"]):
                    who_k = pending.get(k["name"]) or counters[k["name"]]["recipient"]
                    people.append((who_k, k["name"], True, False))
            r["_people"] = people
            r["progress"] = {"done": len([k for k in ks if k.get("workflow_state") == "Done"]),
                             "total": len(ks)}
            out.append(r)
            continue
        who = [a for a in tflow.assignees(r) if a and a != user]
        if givers.get(name) == user and who:
            r["_people"] = [(u, name, False, False) for u in who]
            out.append(r)
        elif name in pending and not who and pending[name] != user:
            r["_people"] = [(pending[name], name, True, False)]
            r["awaiting"] = pending[name]
            out.append(r)
    return out, proposals, givers, truncated


def _decorate(rows, user, tab, givers=None):
    if not rows:
        return rows
    givers = givers if givers is not None else tflow.givers_map(rows)
    people = {g for g in (givers.get(r["name"]) for r in rows) if g}
    for r in rows:
        people.update(tflow.assignees(r))
        people.update(p[0] for p in r.get("_people") or [])
    people = sorted(u for u in people if u)
    full, off = {}, set()
    if people:   # one query: names + who has left (disabled) - QC2 "người nhận đã nghỉ"
        for u in frappe.get_all("User", filters={"name": ["in", people]},
                                fields=["name", "full_name", "enabled"], limit_page_length=0):
            full[u["name"]] = u.get("full_name") or u["name"]
            if not tflow.truthy(u.get("enabled")):
                off.add(u["name"])
    pnames = {}
    projects = [*{r.get("project") for r in rows if r.get("project")}]
    if projects:
        for p in frappe.get_all("Project", filters={"name": ["in", projects]}, fields=["name", "project_name"]):
            pnames[p["name"]] = p.get("project_name") or p["name"]
    seen = set()
    if tab == "give":
        seen = tflow.seen_pairs(sorted({p[1] for r in rows for p in r.get("_people") or []}))
    for r in rows:
        g = givers.get(r["name"]) or r.get("owner")
        r["giver"] = g
        r["giver_name"] = "" if g == user else (full.get(g) or g)
        r["self"] = g == user and tab == "me"
        if tab == "give":
            # a pending recipient has nothing to open yet; a finished part was obviously opened
            r["assignees"] = [{"user": u, "name": full.get(u) or u, "opened": bool(wait or done) or (t, u) in seen,
                               "pending": 1 if wait else 0, "done": 1 if done else 0, "left": 1 if u in off else 0}
                              for u, t, wait, done in r.get("_people") or []]
        else:
            r["assignees"] = [{"user": a, "name": full.get(a) or a, "opened": True, "left": 1 if a in off else 0}
                              for a in tflow.assignees(r) if a]
        r["project_name"] = pnames.get(r.get("project")) or ""
        r["group"] = 1 if (is_split_parent(r) or tflow.truthy(r.get("is_group"))) else 0
        r["review"] = 1 if tflow.truthy(r.get("ec_review_required")) else 0
        r["unopened"] = tab == "give" and any(not a["opened"] for a in r["assignees"])
        r["giver_left"] = 1 if (tab == "me" and g and g != user and g in off) else 0
        r["awaiting"] = 1 if r.get("awaiting") else 0
        r["progress"] = r.get("progress") or None
        if r.get("counter"):
            c = r["counter"]
            c["recipient_name"] = full.get(c.get("recipient")) or c.get("recipient") or ""
        for k in ("_assign", "_others", "_people", "ec_split_parent", "ec_review_required", "is_group", "status",
                  "exp_end_date", "pm_end_time"):
            r.pop(k, None)
    return rows


@frappe.whitelist()
def list(tab="me", include_personal=0):
    """The caller's ordered queue.

    tab=me   : open tasks assigned to me (incl. the ones I wrote for myself)
    tab=give : open tasks I gave to others
    Returns {today, now, tab, rows (ordered, rank 1..n), counts {bucket: n}, buckets [{key, label}],
             asks (Cần đồng ý waiting for me, tab=me), personal_hidden,
             waiting (tab=me: I sent it for review, someone else checks; NOT in rows/counts),
             proposals (tab=give: recipient proposed another deadline, waits for MY decision;
                        row + counter {request, kind ("counter" = Đề xuất hạn khác -> assignment.
                        requester_action, "deadline" = Xin dời hạn -> pm_inbox.answer_deadline),
                        recipient, recipient_name, due, time, start, old_due, old_time, reason};
                        NOT in rows/counts),
             rows[].deadline_ask (tab=me: {due} of my pending "Xin dời hạn" on that task, else None),
             limit (max rows per list, 500), truncated (1 = more than `limit` open tasks, the furthest
             due dates were left out)}."""
    pmperm.require_pm_access()
    return build(frappe.session.user, tab, include_personal)


def _drop_personal(rows, personal):
    """-> (rows outside personal-log projects, how many were hidden)."""
    if not personal:
        return rows, 0
    keep = [r for r in rows if r.get("project") not in personal]
    return keep, len(rows) - len(keep)


def _me_rows(user, personal):
    """tab=me population -> (main, waiting, givers, hidden, truncated). The ONE place that decides
    what counts as "mine to do now": list(tab=me), the 08:30 digest and the rail badge
    (main_count) all go through here."""
    rows, truncated = _mine(user)
    rows, hidden = _drop_personal(rows, personal)
    givers = tflow.givers_map(rows)
    main, waiting = split_me(rows, user, givers)
    return main, waiting, givers, hidden, truncated


def main_count(user):
    """How many rows list(tab=me) shows with personal-log projects hidden (the default view) -
    the rail badge "Việc cần làm" (dashboard.rail_badges). No decoration: 2-4 queries, none per
    row. Capped at _MAX_ROWS like the list (the badge prints 99+ long before that)."""
    return len(_me_rows(user, tflow.personal_log_projects())[0])


def build(user, tab="me", include_personal=0):
    """Queue for `user` (no permission check: callers are list() for the session user and the
    scheduler digest for each recipient's OWN queue)."""
    tab = "give" if tab == "give" else "me"
    personal = set() if tflow.truthy(include_personal) else tflow.personal_log_projects()
    waiting, proposals = [], []
    if tab == "me":
        rows, waiting, givers, hidden, truncated = _me_rows(user, personal)
    else:
        rows, proposals, givers, truncated = _given(user)
        rows, hidden = _drop_personal(rows, personal)
        proposals, _n = _drop_personal(proposals, personal)
    if tab == "me":
        asked = _my_deadline_asks(user)
        for r in rows + waiting:
            d = asked.get(r["name"])
            r["deadline_ask"] = {"due": d} if d else None
    today, now_hm = nowdate(), str(now_datetime())[11:16]
    rows = _decorate(ordered(rows, today, now_hm), user, tab, givers)
    waiting = _decorate(ordered(waiting, today, now_hm), user, tab, givers)
    for r in waiting:
        r["waiting"] = 1
        r["rank"] = 0
    proposals = _decorate(ordered(proposals, today, now_hm), user, tab, givers)
    for r in proposals:
        r["rank"] = 0
    counts = {b: 0 for b in BUCKETS}
    for r in rows:
        counts[r["bucket"]] += 1
    asks = []
    if tab == "me":
        try:
            from ecentric_workspace.pm.api import pm_inbox
            asks = pm_inbox._needs_reply(user, {})
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PM queue asks")
    return {"today": str(today), "now": now_hm, "tab": tab, "rows": rows, "counts": counts,
            "buckets": [{"key": b, "label": BUCKET_LABEL[b]} for b in BUCKETS],
            "asks": asks, "personal_hidden": hidden, "waiting": waiting, "proposals": proposals,
            "limit": _MAX_ROWS, "truncated": 1 if truncated else 0}


# ------------------------------------------------------------------ 08:30 digest
_DIGEST_SUBJECT = 60


def _short(s, n=_DIGEST_SUBJECT):
    """One line, at most n characters (Teams shows the digest as one paragraph)."""
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _due_hint(r, today):
    """Short due note after a task name in the digest: trễ 2 ngày / hạn 15:00 / hạn hôm nay / hạn mai."""
    b, d, t = r.get("bucket"), r.get("due"), r.get("due_time")
    if b == "late":
        n = (getdate(today) - getdate(d)).days if d else 0
        return _("trễ {0} ngày").format(n) if n > 0 else _("quá hạn {0}").format(t or "")
    if b == "today":
        return _("hạn {0}").format(t) if t else _("hạn hôm nay")
    if b == "tomorrow":
        return _("hạn mai")
    return ""


def _digest_text(rows, asks, today=None):
    """(title, message) of the 08:30 Teams message. Plain text, one paragraph (the Teams card collapses
    line breaks). QC4 15/11: the top 3 get a lead-in ("Làm trước:") + a due note, long names are cut;
    a person with only requests waiting gets THOSE requests, not unrelated later tasks."""
    today = str(today or nowdate())
    late = [r for r in rows if r["bucket"] == "late"]
    due_today = [r for r in rows if r["bucket"] == "today"]
    if not (late or due_today):   # QC 15/11: only requests waiting -> never "Hôm nay có 0 việc cần xử lý"
        head = _("{0} việc chờ bạn nhận").format(len(asks))
        items = [_short(a.get("subject") or a.get("task")) + (" (%s)" % _("{0} giao").format(a["from_name"]) if a.get("from_name") else "")
                 for a in asks[:3]]
        if len(asks) > 3:
            items.append(_("và {0} việc khác").format(len(asks) - 3))
        return head, " · ".join(items) + ". " + _("Mở Việc cần làm để nhận việc, đề xuất hạn khác hoặc từ chối.")
    head = _("Hôm nay có {0} việc cần xử lý").format(len(late) + len(due_today))
    lines = []
    if late:
        lines.append(_("{0} việc quá hạn").format(len(late)))
    if due_today:
        lines.append(_("{0} việc hạn hôm nay").format(len(due_today)))
    if asks:
        lines.append(_("{0} việc chờ bạn nhận").format(len(asks)))
    top = []
    for r in rows[:3]:
        hint = _due_hint(r, today)
        top.append("{0}. {1}{2}".format(r["rank"], _short(r.get("subject") or r["name"]), " (%s)" % hint if hint else ""))
    return head, ", ".join(lines) + ". " + _("Làm trước:") + " " + " · ".join(top)


def morning_digest():
    """Cron 08:30 Mon-Sat: one message per person with late / due-today work or requests
    waiting for them, top 3 of their queue, link to /pm#mywork. OFF unless site_config
    `ec_pm_morning_digest` is truthy. One message per person per day (stable dedupe key)."""
    conf = frappe.get_conf() if hasattr(frappe, "get_conf") else {}
    if not tflow.truthy(conf.get("ec_pm_morning_digest")):
        return {"skipped": "disabled"}
    from ecentric_workspace.notification_center import events as ncev
    today = nowdate()
    users = set()
    for r in frappe.get_all("Task", filters=[["workflow_state", "not in", [*tflow.FINISHED]],
                                             ["exp_end_date", "<=", today], ["_assign", "is", "set"]],
                            fields=["_assign"], limit_page_length=0):
        users.update(a for a in tflow.assignees(r) if a)
    try:
        users.update(frappe.get_all("PM Assignment Request", filters={"status": "Pending"},
                                    pluck="recipient", limit_page_length=0) or [])
    except Exception:
        pass
    sent = 0
    for u in sorted(users):
        if u in ("Administrator", "Guest"):
            continue
        try:
            if not frappe.db.get_value("User", u, "enabled") or not pmperm.has_pm_module_access(u):
                continue
            data = build(u, "me")
            rows = [r for r in data["rows"] if r["bucket"] in ("late", "today")]
            if not rows and not data["asks"]:
                continue
            title, msg = _digest_text(data["rows"], data["asks"], today)
            ncev.publish_notification_event("task_due_soon", u, title, msg, action_url="/pm#mywork",
                                            actor="Administrator", dedupe_key="pm_digest|%s|%s" % (u, today))
            sent += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PM morning digest " + str(u))
    return {"sent": sent}
