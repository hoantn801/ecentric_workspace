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
#: item source_type -> the canonical source_counts key exposed to consumers.
SOURCE_COUNT_KEY = {"approval": "approval", "task": "pm",
                    "weekly_report": "weekly_update", "generic": "generic_todo"}
SOURCE_COUNT_KEYS = ("approval", "pm", "weekly_update", "generic_todo")
_APPROVAL_TERMINAL = frozenset({"Approved", "Rejected", "Cancelled"})
_WTU_TERMINAL = frozenset({"Submitted", "Reviewed"})

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
_SCAN_CAP = 500
#: default per-bucket preview size for the header reminder drawer.
PREVIEW_N = 4


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


def _classified_feed(user):
    """THE one classification + ordering pass. Loads the user's Open ToDos
    (bounded by _SCAN_CAP), resolves, derives governed due dates, terminal-
    filters, classifies and deterministically orders. Returns
    (ordered_items, counts, source_counts). Every consumer -- flat pagination
    (build_feed), per-bucket previews (bucket_previews) and per-bucket
    pagination (bucket_page) -- reuses THIS; no separate source queries, no
    duplicated classifier, no unbounded fetch."""
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
    source_counts = {k: 0 for k in SOURCE_COUNT_KEYS}
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
        sk = SOURCE_COUNT_KEY.get(it.get("source_type"), "generic_todo")
        source_counts[sk] += 1

    return order_items(items), counts, source_counts


def _clean(items):
    out = []
    for it in items:
        it = dict(it)
        it.pop("_creation", None)
        out.append(it)
    return out


def build_feed(user, cursor=None, limit=DEFAULT_LIMIT):
    """Flat, deterministically ordered, paginated feed (badge + 'Xem tất cả'
    consumers). Reuses _classified_feed."""
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    offset = decode_cursor(cursor)
    items, counts, source_counts = _classified_feed(user)
    total = len(items)
    page = _clean(items[offset:offset + limit])
    next_cursor = encode_cursor(offset + limit) if (offset + limit) < total else None
    return {
        "items": page,
        "counts": counts,
        "source_counts": source_counts,
        "total": total,
        "returned": len(page),
        "next_cursor": next_cursor,
        "generated_at": str(frappe.utils.now_datetime()),
    }


def bucket_previews(user, preview_n=PREVIEW_N):
    """PER-BUCKET previews: the FIRST `preview_n` items of EACH bucket from
    the ONE classified+ordered feed BEFORE any global pagination. A high-
    priority bucket can never starve a later one (fixes overdue eating the
    whole limit while upcoming has a count but no payload). No separate source
    queries; bounded scan."""
    preview_n = max(1, min(int(preview_n or PREVIEW_N), MAX_LIMIT))
    items, counts, source_counts = _classified_feed(user)
    bucket_items = {b: [] for b in FEED_BUCKETS}
    for it in items:
        b = it.get("bucket")
        if b in bucket_items and len(bucket_items[b]) < preview_n:
            bucket_items[b].append(it)
    bucket_items = {b: _clean(v) for b, v in bucket_items.items()}
    bucket_has_more = {b: counts.get(b, 0) > len(bucket_items[b]) for b in FEED_BUCKETS}
    return {
        "total": len(items),
        "counts": counts,
        "source_counts": source_counts,
        "bucket_items": bucket_items,
        "bucket_has_more": bucket_has_more,
        "preview_n": preview_n,
        "generated_at": str(frappe.utils.now_datetime()),
    }


def bucket_page(user, bucket, cursor=None, limit=DEFAULT_LIMIT):
    """Governed per-bucket pagination ('Xem thêm N việc'): items of ONE bucket,
    deterministically ordered, paged by cursor. Reuses _classified_feed
    (bounded scan; NEVER an unbounded ToDo fetch)."""
    if bucket not in FEED_BUCKETS:
        return {"bucket": bucket, "items": [], "count": 0, "returned": 0, "next_cursor": None}
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    offset = decode_cursor(cursor)
    items, counts, _ = _classified_feed(user)
    rows = [it for it in items if it.get("bucket") == bucket]
    total = len(rows)
    page = _clean(rows[offset:offset + limit])
    next_cursor = encode_cursor(offset + limit) if (offset + limit) < total else None
    return {
        "bucket": bucket,
        "items": page,
        "count": total,
        "returned": len(page),
        "next_cursor": next_cursor,
    }
