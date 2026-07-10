# Copyright (c) 2026, eCentric and contributors
"""KPI / breakdown computation for Approval Center reporting.

All functions take an already-resolved scope + validated filters and compute in Python
from the governed query layer. No DB access except via reporting.queries. No workflow
mutation. Callers are the whitelisted endpoints in reporting.api.
"""
from collections import defaultdict

from frappe.utils import get_datetime, now_datetime

from ecentric_workspace.approval_center.reporting import queries as _q
from ecentric_workspace.approval_center.reporting import sla as _sla
from ecentric_workspace.approval_center.reporting import status as _status
from ecentric_workspace.approval_center.reporting import time_metrics as _tm

RECENT_REJECTED_DAYS = 7
LONGEST_PENDING_LIMIT = 10
BOTTLENECK_LIMIT = 10


def _in_period(row, df, dt):
    if not (df and dt):
        return True
    ref = row.get("submitted_at") or row.get("creation")
    if not ref:
        return False
    ref = get_datetime(ref)
    return get_datetime(df) <= ref <= get_datetime(dt)


def _is_open(row):
    return row.get("approval_status") in _status.OPEN_ENGINE_STATUSES


def build_dashboard(scope, filters):
    now = now_datetime()
    df, dt = (filters or {}).get("date_from"), (filters or {}).get("date_to")
    rows = _q.fetch_scoped_rows(scope, filters)

    period = [r for r in rows if _in_period(r, df, dt)]
    open_rows = [r for r in rows if _is_open(r)]

    # optional sla_state filter (applied to open rows only)
    sla_filter = (filters or {}).get("sla_state")
    sla_by_name = {}
    for r in open_rows:
        st = _sla.sla_state(r, ref_now=now)
        sla_by_name[r["name"]] = st
    if sla_filter in ("breached", "configured_policy", "operational_default", "unavailable"):
        if sla_filter == "breached":
            open_rows = [r for r in open_rows if sla_by_name[r["name"]]["breached"]]
        else:
            open_rows = [r for r in open_rows if sla_by_name[r["name"]]["source"] == sla_filter]

    kpis = _kpis(period, open_rows, sla_by_name, now)
    return {
        "kpis": kpis,
        "status_distribution": _status_distribution(period),
        "pending_by_type": _group_count(open_rows, lambda r: r.get("type_title") or r.get("approval_type")),
        "pending_by_department": _group_count(open_rows, lambda r: r.get("requester_department") or "— Unknown —"),
        "pending_by_approver": _pending_by_approver(open_rows),
        "aging_buckets": _aging(open_rows, now),
        "bottleneck_levels": _bottleneck(scope, filters, now),
        "longest_pending": _longest_pending(open_rows, sla_by_name, now),
        "attention": _attention(period, open_rows, sla_by_name, now),
        "generated_at": str(now),
        "scope_mode": scope.get("mode"),
    }


def _kpis(period, open_rows, sla_by_name, now):
    total = len(period)
    completed = sum(1 for r in period if r["approval_status"] == "Approved")
    rejected = sum(1 for r in period if r["approval_status"] == "Rejected")
    cancelled = sum(1 for r in period if r["approval_status"] == "Cancelled")
    pending = sum(1 for r in open_rows if r["approval_status"] == "Pending")
    info_req = sum(1 for r in open_rows if r["approval_status"] == "Information Required")
    sla_breached = sum(1 for r in open_rows if sla_by_name.get(r["name"], {}).get("breached"))
    # average approval time (Approved only; Draft/Cancelled excluded by construction)
    durs = []
    for r in period:
        if r["approval_status"] == "Approved":
            d = _tm.approval_duration_seconds(r)
            if d is not None and d >= 0:
                durs.append(d)
    avg_secs = (sum(durs) / len(durs)) if durs else None
    return {
        "total": total, "pending": pending, "completed": completed, "rejected": rejected,
        "cancelled": cancelled, "information_required": info_req, "sla_breached": sla_breached,
        "avg_approval_seconds": avg_secs, "avg_approval_sample": len(durs),
    }


def _status_distribution(period):
    out = defaultdict(int)
    for r in period:
        out[_status.normalize(r["approval_status"])] += 1
    return [{"status": s, "count": out.get(s, 0)} for s in _status.NORMALIZED_STATUSES if out.get(s, 0)]


def _group_count(rows, keyfn, limit=None):
    out = defaultdict(int)
    for r in rows:
        out[keyfn(r)] += 1
    items = sorted(({"label": k, "count": v} for k, v in out.items()), key=lambda x: -x["count"])
    return items[:limit] if limit else items


def _pending_by_approver(open_rows):
    if not open_rows:
        return []
    import frappe
    names = [r["name"] for r in open_rows]
    # current-level pending approver rows for these requests
    rows = frappe.get_all("EC Approval Request Approver",
                          filters={"approval_request": ["in", names], "status": "Pending"},
                          fields=["approver", "approval_request", "level_no"])
    cur = {r["name"]: r["current_level"] for r in open_rows}
    out = defaultdict(int)
    for a in rows:
        if a["level_no"] == cur.get(a["approval_request"]):
            out[a["approver"]] += 1
    return sorted(({"label": k, "count": v} for k, v in out.items()), key=lambda x: -x["count"])


def _aging(open_rows, now):
    buckets = _tm.empty_bucket_counts()
    for r in open_rows:
        b = _tm.aging_bucket(_tm.pending_age_seconds(r, ref_now=now))
        if b:
            buckets[b] += 1
    return [{"bucket": b, "count": buckets[b]} for b in _tm.AGING_BUCKETS]


def _bottleneck(scope, filters, now):
    levels = _q.fetch_levels_for_bottleneck(scope, filters)
    comp = defaultdict(list)   # completed durations (exclude Skipped)
    pend = defaultdict(list)   # current pending ages
    for l in levels:
        name = l.get("level_name") or ("Level %s" % l.get("level_no"))
        if l["level_status"] == "Approved" and l.get("activated_at") and l.get("completed_at"):
            d = _tm.seconds_between(l["activated_at"], l["completed_at"])
            if d is not None and d >= 0:
                comp[name].append(d)
        # currently pending at this level
        if l["approval_status"] in _status.OPEN_ENGINE_STATUSES and l["level_no"] == l["current_level"] \
                and l["level_status"] in ("In Progress", "Pending", "Information Requested"):
            age = _tm.pending_age_seconds({"current_activated_at": l.get("activated_at")}, ref_now=now)
            if age is not None:
                pend[name].append(age)
    out = []
    for name in set(list(comp.keys()) + list(pend.keys())):
        avg_comp = (sum(comp[name]) / len(comp[name])) if comp.get(name) else None
        cur_pend = (sum(pend[name]) / len(pend[name])) if pend.get(name) else None
        out.append({"level": name, "avg_completed_seconds": avg_comp,
                    "avg_pending_seconds": cur_pend, "completed_sample": len(comp.get(name, [])),
                    "pending_count": len(pend.get(name, []))})
    out.sort(key=lambda x: (-(x["avg_completed_seconds"] or 0), -(x["avg_pending_seconds"] or 0)))
    return out[:BOTTLENECK_LIMIT]


def _detail_route(r):
    """Route into the EXISTING form detail page: '/<type route>?id=<business name>'.
    No duplicate detail UI. Returns None if the type has no published route yet."""
    route = r.get("type_route")
    ref = r.get("reference_name")
    if not route or not ref:
        return None
    route = route if route.startswith("/") else ("/" + route)
    return "%s?id=%s" % (route, ref)


def _row_view(r, sla_by_name, now):
    st = sla_by_name.get(r["name"], {})
    return {
        "name": r["name"], "type": r.get("type_title") or r.get("approval_type"),
        "approval_type": r.get("approval_type"),
        "reference_doctype": r.get("reference_doctype"), "reference_name": r.get("reference_name"),
        "detail_route": _detail_route(r), "requester": r.get("requested_by"),
        "department": r.get("requester_department"), "status": r["approval_status"],
        "status_label": _status.normalize(r["approval_status"]),
        "current_level": r.get("current_level"), "current_level_name": r.get("current_level_name"),
        "submitted_at": str(r.get("submitted_at") or ""),
        "pending_age_seconds": _tm.pending_age_seconds(r, ref_now=now) if _is_open(r) else None,
        "sla_source": st.get("source"), "sla_due_at": str(st.get("due_at") or "") if st else "",
        "sla_breached": bool(st.get("breached")),
    }


def _longest_pending(open_rows, sla_by_name, now):
    rows = sorted(open_rows, key=lambda r: -(_tm.pending_age_seconds(r, ref_now=now) or 0))
    return [_row_view(r, sla_by_name, now) for r in rows[:LONGEST_PENDING_LIMIT]]


def _attention(period, open_rows, sla_by_name, now):
    """Pending SLA-breached + Information Required + recently rejected (period)."""
    out = []
    seen = set()
    for r in sorted(open_rows, key=lambda r: -(_tm.pending_age_seconds(r, ref_now=now) or 0)):
        breached = sla_by_name.get(r["name"], {}).get("breached")
        if breached or r["approval_status"] == "Information Required":
            out.append(_row_view(r, sla_by_name, now))
            seen.add(r["name"])
    # remaining open (pending) after the priority ones, so the table is useful even with no breaches
    for r in sorted(open_rows, key=lambda r: -(_tm.pending_age_seconds(r, ref_now=now) or 0)):
        if r["name"] not in seen:
            out.append(_row_view(r, sla_by_name, now))
            seen.add(r["name"])
    return out


def drilldown(scope, filters, limit=200):
    """Governed filtered request list for KPI/chart drill-down + action table 'open detail'."""
    now = now_datetime()
    rows = _q.fetch_scoped_rows(scope, filters)
    df, dt = (filters or {}).get("date_from"), (filters or {}).get("date_to")
    view_status = (filters or {}).get("view")   # 'open' | 'period' | None
    if view_status == "open":
        rows = [r for r in rows if _is_open(r)]
    else:
        rows = [r for r in rows if _in_period(r, df, dt)]
    sla_by = {r["name"]: _sla.sla_state(r, ref_now=now) for r in rows}
    rows = rows[:limit]
    return [_row_view(r, sla_by, now) for r in rows]
