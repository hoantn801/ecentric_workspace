# Copyright (c) 2026, eCentric and contributors
"""Shared Action feed + classification service (Phase 1a).

THE single internal service behind every Action Center consumer
(get_action_items today; get_reminder_summary + the full page later). No
consumer re-implements counting, classification, due derivation, terminal
filtering, ordering or pagination -- they all call build_feed().

Invariants:
  - tabToDo is the ONLY action index (no separate Action DocType/table).
  - Every field is DERIVED from governed source records each call.
  - Session scope: the caller passes the resolved user; the whitelisted API
    layer forbids a client-supplied user.

Classification policy (PO-locked 2026-07-24):
    resolved/terminal source          -> excluded
    due date before today             -> overdue
    due date == today                 -> act_now
    explicit ACTIVE source state       -> act_now   (source-specific)
    future due date                   -> upcoming
    undated and not explicitly active -> undated

Deterministic order: bucket priority, due_at asc (undated last), source
priority, stable creation/name tie-break. NEVER by modified.
"""
import base64
import json

import frappe

from ecentric_workspace.action_center.resolvers import resolve_item, bucket_for

WTU = "Weekly Team Update"
TASK = "Task"
EC_REQUEST = "EC Approval Request"
EC_LEVEL = "EC Approval Request Level"

FEED_BUCKETS = ("overdue", "act_now", "upcoming", "undated")
_BUCKET_RANK = {b: i for i, b in enumerate(FEED_BUCKETS)}
_SOURCE_PRIORITY = {"approval": 0, "task": 1, "weekly_report": 2, "generic": 3}
_APPROVAL_TERMINAL = frozenset({"Approved", "Rejected", "Cancelled"})
_WTU_TERMINAL = frozenset({"Submitted", "Reviewed"})

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
_SCAN_CAP = 500


# ---- pure helpers (no frappe): classification + ordering + cursor ----------
def classify(due_at, today, active, terminal):
    """Bucket for one item, or None if it must be EXCLUDED (resolved/terminal)."""
    if terminal:
        return None
    b = bucket_for(due_at, today)
    if b == "overdue":
        return "overdue"
    if b == "today":
        return "act_now"
    if b == "upcoming":
        return "upcoming"
    return "act_now" if active else "undated"


def _sort_key(item):
    due = item.get("due_at") or ""
    return (
        _BUCKET_RANK.get(item.get("bucket"), 99),
        due if due else "9999-99-99 99:99:99",
        _SOURCE_PRIORITY.get(item.get("source_type"), 9),
        str(item.get("_creation") or ""),
        str(item.get("todo_name") or ""),
    )


def order_items(items):
    return sorted(items, key=_sort_key)


def encode_cursor(offset):
    return base64.urlsafe_b64encode(json.dumps({"o": int(offset)}).encode()).decode()


def decode_cursor(cursor):
    if not cursor:
        return 0
    try:
        o = int(json.loads(base64.urlsafe_b64decode(cursor.encode()).decode()).get("o", 0))
        return o if o >= 0 else 0
    except Exception:
        return 0


# ---- governed source lookups (batched; only the user's own queued docs) ----
def _approval_state(names):
    out = {}
    if not names:
        return out
    reqs = frappe.get_all(
        EC_REQUEST, filters={"reference_name": ["in", list(names)]},
        fields=["name", "reference_name", "approval_status"],
        ignore_permissions=True) or []
    by_ref = {}
    for r in reqs:
        by_ref.setdefault(r["reference_name"], []).append(r)
    for ref in names:
        rows = by_ref.get(ref) or []
        active_req = [r for r in rows if r["approval_status"] not in _APPROVAL_TERMINAL]
        if not active_req:
            out[ref] = (True, False, "")
            continue
        req = active_req[0]
        lv = frappe.get_all(
            EC_LEVEL,
            filters={"approval_request": req["name"], "level_status": "In Progress"},
            fields=["due_at"], limit=1, ignore_permissions=True) or []
        due = str(lv[0]["due_at"]) if (lv and lv[0].get("due_at")) else ""
        out[ref] = (False, bool(lv), due)
    return out


def _task_state(names):
    out = {}
    if not names:
        return out
    from ecentric_workspace.pm import permissions as pmperm
    rows = frappe.get_all(
        TASK, filters={"name": ["in", list(names)]},
        fields=["name", "workflow_state", "status", "exp_end_date"],
        ignore_permissions=True) or []
    seen = set()
    for t in rows:
        seen.add(t["name"])
        terminal = pmperm.is_task_terminal(t)
        active = (t.get("workflow_state") == "In Progress")
        due = str(t.get("exp_end_date")) if t.get("exp_end_date") else ""
        out[t["name"]] = (terminal, active, due)
    for ref in names:
        if ref not in seen:
            out[ref] = (True, False, "")
    return out


def _wtu_state(names):
    out = {}
    if not names:
        return out
    rows = frappe.get_all(
        WTU, filters={"name": ["in", list(names)]},
        fields=["name", "status"], ignore_permissions=True) or []
    st = {r["name"]: r.get("status") for r in rows}
    for ref in names:
        s = st.get(ref)
        out[ref] = (s in _WTU_TERMINAL if s is not None else True, False, "")
    return out


# ---- the shared feed -------------------------------------------------------
def _load_open_todos(user):
    return frappe.db.sql(
        "SELECT name, description, reference_type, reference_name, "
        "       priority, modified, creation, date, status "
        "FROM `tabToDo` "
        "WHERE allocated_to=%s AND status=%s "
        "ORDER BY creation ASC, name ASC LIMIT %s",
        (user, "Open", _SCAN_CAP), as_dict=True) or []


def build_feed(user, cursor=None, limit=DEFAULT_LIMIT):
    """Classified, terminal-filtered, deterministically ordered, paginated
    feed for ONE user. counts are over the FULL filtered feed (a badge and a
    list can never disagree); items is the requested page."""
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    offset = decode_cursor(cursor)
    today = frappe.utils.getdate()

    rows = _load_open_todos(user)

    from ecentric_workspace.action_center.resolvers import APPROVAL_DOCTYPES
    approval_names, task_names, wtu_names = set(), set(), set()
    for r in rows:
        rt = (r.get("reference_type") or "").strip()
        rn = (r.get("reference_name") or "").strip()
        if not rn:
            continue
        if rt in APPROVAL_DOCTYPES:
            approval_names.add(rn)
        elif rt == TASK:
            task_names.add(rn)
        elif rt == WTU:
            wtu_names.add(rn)
    appr = _approval_state(approval_names)
    tsk = _task_state(task_names)
    wtu = _wtu_state(wtu_names)

    items = []
    counts = {b: 0 for b in FEED_BUCKETS}
    for r in rows:
        try:
            it = resolve_item(r)
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "action_center.feed resolve failed " + str(r.get("name")))
            continue
        st = it.get("source_type")
        rn = it.get("reference_name")
        terminal = active = False
        if st == "approval" and rn in appr:
            terminal, active, due = appr[rn]
            if due and not it.get("due_at"):
                it["due_at"] = due
        elif st == "task" and rn in tsk:
            terminal, active, due = tsk[rn]
            if due and not it.get("due_at"):
                it["due_at"] = due
        elif st == "weekly_report" and rn in wtu:
            terminal, active, _ = wtu[rn]
        bucket = classify(it.get("due_at"), today, active, terminal)
        if bucket is None:
            continue
        it["bucket"] = bucket
        it["active"] = bool(active)
        it["resolution_state"] = "open"
        it["_creation"] = str(r.get("creation") or "")
        items.append(it)
        counts[bucket] += 1

    items = order_items(items)
    total = len(items)
    page = items[offset:offset + limit]
    for it in page:
        it.pop("_creation", None)
    next_cursor = encode_cursor(offset + limit) if (offset + limit) < total else None

    return {
        "items": page,
        "counts": counts,
        "total": total,
        "returned": len(page),
        "next_cursor": next_cursor,
        "generated_at": str(frappe.utils.now_datetime()),
    }
