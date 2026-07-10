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
from ecentric_workspace.approval_center.reporting import series as _series
from ecentric_workspace.approval_center.reporting import insights as _insights

RECENT_REJECTED_DAYS = 7
NEAR_SLA_MINUTES = 240      # 'near SLA' window for card accenting
KANBAN_CARD_CAP = 20
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

    appr_map = _pending_approver_map(open_rows)
    kpis = _kpis(period, open_rows, sla_by_name, now)

    # ---- period comparison (equivalent previous window) ----
    comparison = {}
    if df and dt:
        p_from, p_to = _series.previous_window(df, dt)
        prev_rows = _q.fetch_rows_in_window(scope, filters, p_from, p_to)
        comparison = _comparison(period, open_rows, prev_rows, now)
        gran = _series.granularity_for(df, dt)
        volume_trend = {"granularity": gran,
                        "buckets": _series.build_time_buckets(period, df, dt, gran)}
        sla_compliance = _sla_compliance(open_rows, sla_by_name, period, df, dt, gran, now)
        bottleneck = _bottleneck(scope, filters, now, window=(df, dt), prev_window=(p_from, p_to))
    else:
        volume_trend = {"granularity": "day", "buckets": []}
        sla_compliance = _sla_compliance(open_rows, sla_by_name, period, None, None, "day", now)
        bottleneck = _bottleneck(scope, filters, now)

    dash = {
        "kpis": kpis,
        "comparison": comparison,
        "status_distribution": _status_distribution(period),
        "status_mix": _status_mix(period),
        "volume_trend": volume_trend,
        "sla_compliance": sla_compliance,
        "pending_by_type": _group_count(open_rows, lambda r: r.get("type_title") or r.get("approval_type")),
        "pending_by_department": _group_count(open_rows, lambda r: r.get("requester_department") or "— Unknown —"),
        "pending_by_approver": _pending_by_approver(open_rows, now, appr_map),
        "kanban": _kanban(open_rows, sla_by_name, appr_map, now),
        "department_performance": _department_performance(period, open_rows, sla_by_name),
        "aging_buckets": _aging(open_rows, now),
        "bottleneck_levels": bottleneck,
        "funnel": _funnel(period),
        "longest_pending": _longest_pending(open_rows, sla_by_name, now),
        "attention": _attention(period, open_rows, sla_by_name, now),
        "generated_at": str(now),
        "scope_mode": scope.get("mode"),
    }
    dash["insights"] = _insights.generate(dash, now=now)
    return dash


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


def _pending_approver_map(open_rows):
    """{request_name: [current-level pending approver users]} - fetched ONCE and reused by
    both the approver workload chart and the Kanban board (no per-card queries)."""
    if not open_rows:
        return {}
    import frappe
    names = [r["name"] for r in open_rows]
    rows = frappe.get_all("EC Approval Request Approver",
                          filters={"approval_request": ["in", names], "status": "Pending"},
                          fields=["approver", "approval_request", "level_no"])
    cur = {r["name"]: r["current_level"] for r in open_rows}
    m = defaultdict(list)
    for a in rows:
        if a["level_no"] == cur.get(a["approval_request"]):
            m[a["approval_request"]].append(a["approver"])
    return m


def _pending_by_approver(open_rows, now, appr_map):
    if not open_rows:
        return []
    age_by_req = {r["name"]: (_tm.pending_age_seconds(r, ref_now=now) or 0) for r in open_rows}
    cnt = defaultdict(int)
    oldest = defaultdict(float)
    for req, approvers in appr_map.items():
        for ap in approvers:
            cnt[ap] += 1
            oldest[ap] = max(oldest[ap], age_by_req.get(req, 0))
    out = [{"label": k, "count": cnt[k], "oldest_pending_seconds": oldest[k]} for k in cnt]
    out.sort(key=lambda x: (-x["count"], -(x["oldest_pending_seconds"] or 0)))
    return out


def _aging(open_rows, now):
    buckets = _tm.empty_bucket_counts()
    for r in open_rows:
        b = _tm.aging_bucket(_tm.pending_age_seconds(r, ref_now=now))
        if b:
            buckets[b] += 1
    return [{"bucket": b, "count": buckets[b]} for b in _tm.AGING_BUCKETS]


def _bottleneck(scope, filters, now, window=None, prev_window=None):
    """Rank levels by completed duration + current pending. Enriched with volume, median,
    P90, overdue count, active pending and trend vs previous period. `window`/`prev_window`
    (completed_at ranges) drive the volume + trend numbers when a date range is selected."""
    completed_from = completed_to = None
    if window:
        completed_from, completed_to = window
    levels = _q.fetch_levels_for_bottleneck(scope, filters, completed_from, completed_to)
    comp = defaultdict(list)     # completed durations (exclude Skipped)
    pend = defaultdict(list)     # current pending ages
    overdue = defaultdict(int)
    for l in levels:
        name = l.get("level_name") or ("Level %s" % l.get("level_no"))
        if l["level_status"] == "Approved" and l.get("activated_at") and l.get("completed_at"):
            d = _tm.seconds_between(l["activated_at"], l["completed_at"])
            if d is not None and d >= 0:
                comp[name].append(d)
        if l["approval_status"] in _status.OPEN_ENGINE_STATUSES and l["level_no"] == l["current_level"] \
                and l["level_status"] in ("In Progress", "Pending", "Information Requested"):
            age = _tm.pending_age_seconds({"current_activated_at": l.get("activated_at")}, ref_now=now)
            if age is not None:
                pend[name].append(age)
                if l.get("due_at") and now > l["due_at"]:
                    overdue[name] += 1
    prev_comp = defaultdict(list)
    if prev_window:
        for l in _q.fetch_levels_for_bottleneck(scope, filters, prev_window[0], prev_window[1]):
            if l["level_status"] == "Approved" and l.get("activated_at") and l.get("completed_at"):
                d = _tm.seconds_between(l["activated_at"], l["completed_at"])
                if d is not None and d >= 0:
                    prev_comp[l.get("level_name") or ("Level %s" % l.get("level_no"))].append(d)
    out = []
    for name in set(list(comp.keys()) + list(pend.keys())):
        cs = comp.get(name, [])
        avg_comp = (sum(cs) / len(cs)) if cs else None
        cur_pend = (sum(pend[name]) / len(pend[name])) if pend.get(name) else None
        prev_avg = (sum(prev_comp[name]) / len(prev_comp[name])) if prev_comp.get(name) else None
        trend_pct = None
        if prev_avg and avg_comp is not None:
            trend_pct = round((avg_comp - prev_avg) * 100.0 / prev_avg, 1)
        out.append({"level": name, "volume": len(cs),
                    "avg_completed_seconds": avg_comp,
                    "median_seconds": _series.median(cs),
                    "p90_seconds": _series.percentile(cs, 90),
                    "avg_pending_seconds": cur_pend,
                    "active_pending": len(pend.get(name, [])),
                    "overdue_count": overdue.get(name, 0),
                    "completed_sample": len(cs),
                    "pending_count": len(pend.get(name, [])),
                    "trend_pct": trend_pct})
    out.sort(key=lambda x: (-(x["avg_completed_seconds"] or 0), -(x["avg_pending_seconds"] or 0)))
    return out[:BOTTLENECK_LIMIT]


def _completion_rate(period):
    total = len(period)
    if not total:
        return 0.0
    done = sum(1 for r in period if r["approval_status"] == "Approved")
    return round(done * 100.0 / total, 1)


def _comparison(period, open_rows, prev_rows, now):
    def cnt(rows, st):
        return sum(1 for r in rows if r["approval_status"] == st)
    cur_completed = cnt(period, "Approved")
    prev_completed = cnt(prev_rows, "Approved")
    cur_avg = _avg_duration(period)
    prev_avg = _avg_duration(prev_rows)
    return {
        "total": _series.delta(len(period), len(prev_rows)),
        "completed": _series.delta(cur_completed, prev_completed),
        "rejected": _series.delta(cnt(period, "Rejected"), cnt(prev_rows, "Rejected")),
        "pending": _series.delta(sum(1 for r in open_rows if r["approval_status"] == "Pending"),
                                 cnt(prev_rows, "Pending")),
        "avg_approval_seconds": _series.delta(round(cur_avg) if cur_avg else 0,
                                              round(prev_avg) if prev_avg else 0),
        "completion_rate": _series.delta(_completion_rate(period), _completion_rate(prev_rows)),
    }


def _avg_duration(rows):
    durs = []
    for r in rows:
        if r["approval_status"] == "Approved":
            d = _tm.approval_duration_seconds(r)
            if d is not None and d >= 0:
                durs.append(d)
    return (sum(durs) / len(durs)) if durs else None


def _status_mix(period):
    total = len(period)
    dist = _status_distribution(period)
    for d in dist:
        d["percent"] = round(d["count"] * 100.0 / total, 1) if total else 0.0
    return {"total": total, "segments": dist}


def _sla_compliance(open_rows, sla_by_name, period, df, dt, gran, now):
    breached = configured = operational = unavailable = 0
    for r in open_rows:
        st = sla_by_name.get(r["name"], {})
        src = st.get("source")
        if st.get("breached"):
            breached += 1
        if src == "configured_policy":
            configured += 1
        elif src == "operational_default":
            operational += 1
        elif src == "unavailable":
            unavailable += 1
    compliant = max(0, len(open_rows) - breached)
    trend = []
    if df and dt:
        # submission-cohort breach rate per bucket (documented approximation)
        buckets = _series.build_time_buckets(period, df, dt, gran)
        by_bucket = {b["label"]: {"total": 0, "breach": 0} for b in buckets}
        from frappe.utils import get_datetime
        for r in period:
            ref = r.get("submitted_at") or r.get("creation")
            if not ref:
                continue
            key = _series._bucket_key(ref, gran)
            if key in by_bucket:
                by_bucket[key]["total"] += 1
                if sla_by_name.get(r["name"], {}).get("breached"):
                    by_bucket[key]["breach"] += 1
        for b in buckets:
            v = by_bucket.get(b["label"], {"total": 0, "breach": 0})
            rate = round((v["total"] - v["breach"]) * 100.0 / v["total"], 1) if v["total"] else 100.0
            trend.append({"label": b["label"], "compliant_pct": rate})
    return {"compliant": compliant, "breached": breached,
            "configured_policy": configured, "operational_default": operational,
            "unavailable": unavailable, "trend": trend}


def _department_performance(period, open_rows, sla_by_name):
    vol = defaultdict(int)
    durs = defaultdict(list)
    for r in period:
        dept = r.get("requester_department") or "— Unknown —"
        vol[dept] += 1
        if r["approval_status"] == "Approved":
            d = _tm.approval_duration_seconds(r)
            if d is not None and d >= 0:
                durs[dept].append(d)
    breach = defaultdict(int)
    for r in open_rows:
        if sla_by_name.get(r["name"], {}).get("breached"):
            breach[r.get("requester_department") or "— Unknown —"] += 1
    out = []
    for dept in set(list(vol.keys()) + list(breach.keys())):
        ds = durs.get(dept, [])
        out.append({"department": dept, "volume": vol.get(dept, 0),
                    "avg_duration_seconds": (sum(ds) / len(ds)) if ds else None,
                    "breaches": breach.get(dept, 0)})
    out.sort(key=lambda x: -x["volume"])
    return out


def _funnel(period):
    """Status-snapshot funnel (not a time-ordered funnel - documented). Stages use only
    states derivable from the shared model. 'In Approval' = currently Pending."""
    submitted = len(period)
    pending = sum(1 for r in period if r["approval_status"] == "Pending")
    info = sum(1 for r in period if r["approval_status"] == "Information Required")
    completed = sum(1 for r in period if r["approval_status"] == "Approved")
    rejcan = sum(1 for r in period if r["approval_status"] in ("Rejected", "Cancelled"))
    return [
        {"stage": "Đã gửi", "count": submitted},
        {"stage": "Đang duyệt", "count": pending},
        {"stage": "Cần bổ sung", "count": info},
        {"stage": "Hoàn tất", "count": completed},
        {"stage": "Từ chối/Hủy", "count": rejcan},
    ]


def _kanban_card(r, sla_by_name, appr_map, now):
    st = sla_by_name.get(r["name"], {})
    age = _tm.pending_age_seconds(r, ref_now=now) or 0
    due = st.get("due_at")
    remaining = None
    if due:
        remaining = int((get_datetime(due) - now).total_seconds() // 60)
    if st.get("breached"):
        sla = "breached"
    elif remaining is not None and 0 <= remaining <= NEAR_SLA_MINUTES:
        sla = "near"
    elif st.get("source") == "unavailable":
        sla = "unavailable"
    else:
        sla = "normal"
    return {
        "request_name": r["name"],
        "title": r.get("type_title") or r.get("approval_type"),
        "approval_type": r.get("approval_type"),
        "requester": r.get("requested_by"),
        "department": r.get("requester_department"),
        "current_level": r.get("current_level"),
        "current_level_name": r.get("current_level_name"),
        "pending_approvers": appr_map.get(r["name"], []),
        "pending_age_minutes": int(age // 60),
        "sla_state": sla,
        "sla_source": st.get("source"),
        "sla_remaining_minutes": remaining,
        "detail_route": _detail_route(r),
        "status": r["approval_status"],
    }


def _card_rank(card):
    # priority inside a column: breached -> near -> (oldest first) -> newest
    order = {"breached": 0, "near": 1}.get(card["sla_state"], 2)
    return (order, -(card["pending_age_minutes"] or 0))


def _kanban_columns(cards_by_key, labels):
    cols = []
    for key, cards in cards_by_key.items():
        cards.sort(key=_card_rank)
        overdue = sum(1 for c in cards if c["sla_state"] == "breached")
        oldest = max((c["pending_age_minutes"] or 0) for c in cards) if cards else 0
        cols.append({
            "key": key, "label": labels.get(key, key), "count": len(cards),
            "overdue_count": overdue, "oldest_age_minutes": oldest,
            "cards": cards[:KANBAN_CARD_CAP],
        })
    # most critical columns first: overdue, then size, then oldest
    cols.sort(key=lambda c: (-c["overdue_count"], -c["count"], -c["oldest_age_minutes"]))
    return cols


def _kanban(open_rows, sla_by_name, appr_map, now):
    """Governed Kanban dataset built ENTIRELY from the already-scoped open rows + the shared
    pending-approver map (no extra queries). Only columns with pending cards are returned.
    Cards are capped per column; `count` carries the true column size for the 'X more' hint."""
    by_level = defaultdict(list)
    level_labels = {}
    by_approver = defaultdict(list)
    approver_labels = {}
    UNASSIGNED = "__unassigned__"
    for r in open_rows:
        card = _kanban_card(r, sla_by_name, appr_map, now)
        lvl_key = str(r.get("current_level"))
        by_level[lvl_key].append(card)
        level_labels[lvl_key] = r.get("current_level_name") or ("Cấp %s" % r.get("current_level"))
        approvers = appr_map.get(r["name"], [])
        if approvers:
            for ap in approvers:
                by_approver[ap].append(dict(card))
                approver_labels[ap] = ap
        else:
            by_approver[UNASSIGNED].append(dict(card))
            approver_labels[UNASSIGNED] = "— Chưa phân công —"
    return {
        "by_level": {"columns": _kanban_columns(by_level, level_labels)},
        "by_approver": {"columns": _kanban_columns(by_approver, approver_labels)},
    }


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
