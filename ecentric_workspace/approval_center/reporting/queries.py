# Copyright (c) 2026, eCentric and contributors
"""Governed, parameterized query layer for Approval Center reporting.

The ONLY place that touches the DB for the dashboard. Every query ANDs the scope
predicate (scope.scope_predicate) and uses %(name)s parameters - never string-formatted
values. Callers pass a resolved scope + a validated filter dict.
"""
import frappe

from ecentric_workspace.approval_center.reporting import scope as _scope

# Fetch union of (rows whose submission/creation is in the date range) and (all currently
# open rows), so period KPIs and current pending/SLA views can be computed from one result.
_BASE = """
    FROM `tabEC Approval Request` r
    LEFT JOIN `tabEC Approval Type` t ON t.name = r.approval_type
    LEFT JOIN `tabEC Approval Request Level` cl
           ON cl.approval_request = r.name AND cl.level_no = r.current_level
"""
_FIELDS = """
    r.name AS name, r.approval_type AS approval_type, t.approval_title AS type_title,
    t.category AS category, r.requested_by AS requested_by,
    r.requester_department AS requester_department, r.submitted_at AS submitted_at,
    r.creation AS creation, r.completed_at AS completed_at,
    r.approval_status AS approval_status, r.current_level AS current_level,
    cl.level_name AS current_level_name, cl.activated_at AS current_activated_at,
    cl.due_at AS due_at, cl.is_overdue AS is_overdue, cl.sla_policy AS sla_policy,
    r.reference_doctype AS reference_doctype, r.reference_name AS reference_name,
    t.route AS type_route
"""

_OPEN = "('Pending','Information Required')"


def _non_date_filters(filters, params):
    """Build filter fragments (excluding date range) into a list; mutate params."""
    frag = []
    m = {
        "category": "t.category",
        "approval_type": "r.approval_type",
        "department": "r.requester_department",
        "requester": "r.requested_by",
        "status": "r.approval_status",
        "current_level": "r.current_level",
    }
    for key, col in m.items():
        val = (filters or {}).get(key)
        if val in (None, "", []):
            continue
        pk = "f_" + key
        params[pk] = val
        frag.append("%s = %%(%s)s" % (col, pk))
    # approver filter -> membership on the approver child
    approver = (filters or {}).get("approver")
    if approver:
        params["f_approver"] = approver
        frag.append("EXISTS (SELECT 1 FROM `tabEC Approval Request Approver` fa "
                    "WHERE fa.approval_request = r.name AND fa.approver = %(f_approver)s)")
    return frag


def fetch_scoped_rows(scope, filters):
    """Rows in the date range OR currently open, within scope + non-date filters.
    Each row is tagged by the caller (service) for period/open membership."""
    params = {}
    where = ["1=1"]
    sp, sparams = _scope.scope_predicate(scope)
    where.append(sp)
    params.update(sparams)
    where.extend(_non_date_filters(filters, params))

    df = (filters or {}).get("date_from")
    dt = (filters or {}).get("date_to")
    if df and dt:
        params["date_from"] = df
        params["date_to"] = dt
        date_clause = ("(COALESCE(r.submitted_at, r.creation) BETWEEN %(date_from)s AND %(date_to)s "
                       "OR r.approval_status IN " + _OPEN + ")")
        where.append(date_clause)

    sql = "SELECT " + _FIELDS + _BASE + " WHERE " + " AND ".join(where) + " ORDER BY r.submitted_at DESC"
    return frappe.db.sql(sql, params, as_dict=True)


def fetch_levels_for_bottleneck(scope, filters):
    """Per-level rows for in-scope requests: completed durations + current pending, used
    to rank bottleneck levels. Skipped levels are excluded from duration by the caller."""
    params = {}
    where = ["1=1"]
    sp, sparams = _scope.scope_predicate(scope)
    where.append(sp)
    params.update(sparams)
    where.extend(_non_date_filters(filters, params))
    sql = """
        SELECT rl.level_name AS level_name, rl.level_status AS level_status,
               rl.activated_at AS activated_at, rl.completed_at AS completed_at,
               r.approval_status AS approval_status, r.current_level AS current_level,
               rl.level_no AS level_no
        FROM `tabEC Approval Request Level` rl
        JOIN `tabEC Approval Request` r ON r.name = rl.approval_request
        LEFT JOIN `tabEC Approval Type` t ON t.name = r.approval_type
        WHERE %s
    """ % " AND ".join(where)
    return frappe.db.sql(sql, params, as_dict=True)


def distinct_filter_values(scope):
    """Scoped distinct values for filter dropdowns (types, categories, departments)."""
    sp, params = _scope.scope_predicate(scope)
    types = frappe.db.sql(
        "SELECT DISTINCT r.approval_type AS v, t.approval_title AS label "
        "FROM `tabEC Approval Request` r LEFT JOIN `tabEC Approval Type` t ON t.name=r.approval_type "
        "WHERE " + sp + " AND r.approval_type IS NOT NULL ORDER BY t.approval_title", params, as_dict=True)
    cats = frappe.db.sql(
        "SELECT DISTINCT t.category AS v FROM `tabEC Approval Request` r "
        "LEFT JOIN `tabEC Approval Type` t ON t.name=r.approval_type "
        "WHERE " + sp + " AND t.category IS NOT NULL ORDER BY t.category", params, as_dict=True)
    depts = frappe.db.sql(
        "SELECT DISTINCT r.requester_department AS v FROM `tabEC Approval Request` r "
        "WHERE " + sp + " AND r.requester_department IS NOT NULL ORDER BY r.requester_department",
        params, as_dict=True)
    return {"types": types, "categories": [c["v"] for c in cats], "departments": [d["v"] for d in depts]}
