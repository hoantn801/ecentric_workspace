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


def fetch_rows_in_window(scope, filters, date_from, date_to):
    """Rows whose submission/creation falls strictly in [date_from, date_to] within scope +
    non-date filters (NO open-status union). Used for previous-period comparison and the
    volume/SLA time-series."""
    params = {"win_from": date_from, "win_to": date_to}
    where = ["1=1"]
    sp, sparams = _scope.scope_predicate(scope)
    where.append(sp)
    params.update(sparams)
    where.extend(_non_date_filters(filters, params))
    where.append("COALESCE(r.submitted_at, r.creation) BETWEEN %(win_from)s AND %(win_to)s")
    sql = "SELECT " + _FIELDS + _BASE + " WHERE " + " AND ".join(where) + " ORDER BY r.submitted_at ASC"
    return frappe.db.sql(sql, params, as_dict=True)


def fetch_levels_for_bottleneck(scope, filters, completed_from=None, completed_to=None):
    """Per-level rows for in-scope requests: completed durations + current pending, used
    to rank bottleneck levels. Skipped levels are excluded from duration by the caller.
    When completed_from/to are given, only levels COMPLETED in that window are returned
    (used for period-vs-previous bottleneck trend)."""
    params = {}
    where = ["1=1"]
    sp, sparams = _scope.scope_predicate(scope)
    where.append(sp)
    params.update(sparams)
    where.extend(_non_date_filters(filters, params))
    if completed_from and completed_to:
        params["lvl_from"] = completed_from
        params["lvl_to"] = completed_to
        where.append("rl.completed_at BETWEEN %(lvl_from)s AND %(lvl_to)s")
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


def _search_clause(search, params):
    if not search:
        return None
    params["search"] = "%" + str(search).strip() + "%"
    return ("(r.name LIKE %(search)s OR t.approval_title LIKE %(search)s "
            "OR r.requested_by LIKE %(search)s OR r.requester_department LIKE %(search)s)")


def _fulfillment_refs(me=None):
    """Business records that are MINE to work on, across every form.

    'Chờ tôi xử lý' means: still unclaimed (fulfillment_status=Assigned) on a form I am an
    eligible fulfiller for, OR already claimed BY ME (In Progress + owner=me). Work claimed
    by someone else is deliberately excluded -- it is not mine to act on.

    fulfillment_status lives on each business DocType (not on EC Approval Request) so it
    cannot be joined; open fulfillment work is small, so we collect names per registered form
    and the caller filters the list by reference_name."""
    import frappe as _f
    names = []
    if not me:
        return names
    try:
        from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS
        defs = list(APPROVAL_DEFINITIONS.values())
    except Exception:
        return names
    try:
        from ecentric_workspace.approval_center.shared.workflow import permissions as _perm
    except Exception:
        _perm = None
    seen = set()
    for d in defs:
        dt = getattr(d, "business_doctype", None)
        code = getattr(d, "code", None)
        if not dt or dt in seen:
            continue
        seen.add(dt)
        try:
            if not _f.get_meta(dt).has_field("fulfillment_status"):
                continue
            # already mine
            names += _f.get_all(dt, filters={"fulfillment_status": "In Progress",
                                             "fulfillment_owner": me},
                                pluck="name", limit_page_length=0)
            # unclaimed, but only on forms I may actually fulfil
            eligible = True
            if _perm is not None:
                try:
                    eligible = bool(_perm.is_eligible_fulfiller(me, code, dt))
                except Exception:
                    eligible = False
            if eligible:
                names += _f.get_all(dt, filters={"fulfillment_status": "Assigned"},
                                    pluck="name", limit_page_length=0)
        except Exception:
            continue
    return names


def _list_where(scope, filters, search, params):
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
        where.append("COALESCE(r.submitted_at, r.creation) BETWEEN %(date_from)s AND %(date_to)s")
    sc = _search_clause(search, params)
    if sc:
        where.append(sc)
    box = (filters or {}).get("box")
    me = (filters or {}).get("_me")
    if box == "sent" and me:
        params["_me_sent"] = me
        where.append("r.requested_by = %(_me_sent)s")
    elif box == "received" and me:
        params["_me_recv"] = me
        where.append("EXISTS (SELECT 1 FROM `tabEC Approval Request Approver` va "
                     "WHERE va.approval_request = r.name AND va.approver = %(_me_recv)s)")
    elif box == "fulfil":
        where.append(_my_todo_clause(me, params))
    return " AND ".join(where)


def awaiting_my_decision_sql(param_name):
    """Hồ sơ ĐANG chờ chính người này bấm duyệt.

    Dùng đúng định nghĩa của engine (transitions._level_pending_approvers): dòng approver ở
    ĐÚNG cấp hiện tại và còn status='Pending'. Không dùng "là approver bất kỳ" — như vậy sẽ
    kéo cả hồ sơ mình đã duyệt xong hoặc còn ở cấp người khác."""
    return ("(r.approval_status IN " + _OPEN + " AND EXISTS ("
            "SELECT 1 FROM `tabEC Approval Request Approver` va "
            "WHERE va.approval_request = r.name AND va.approver = %(" + param_name + ")s "
            "AND va.level_no = r.current_level AND va.status = 'Pending'))")


def _my_todo_clause(me, params):
    """Tab 'Chờ tôi xử lý' = MỌI việc đang chờ tôi ra tay.

    Trước đây tab này chỉ có phần Operation nhận xử lý SAU khi duyệt xong, nên hồ sơ đang chờ
    chính mình bấm duyệt lại không xuất hiện — đúng thứ người dùng vào tab này để tìm.
    Nay là hợp của hai vế: (a) chờ tôi duyệt, (b) việc fulfilment của tôi."""
    parts = []
    if me:
        params["_me_todo"] = me
        parts.append(awaiting_my_decision_sql("_me_todo"))
    refs = _fulfillment_refs(me)
    if refs:
        keys = []
        for i, nm in enumerate(refs):
            k = "_ff%d" % i
            params[k] = nm
            keys.append("%%(%s)s" % k)
        parts.append("r.reference_name IN (" + ", ".join(keys) + ")")
    if not parts:
        return "1=0"
    return "(" + " OR ".join(parts) + ")"


def fetch_requests_page(scope, filters, start, page_length, search=None):
    """One governed, scoped, paginated page of requests across all forms (all statuses)."""
    params = {}
    where = _list_where(scope, filters, search, params)
    params["_start"] = int(start)
    params["_len"] = int(page_length)
    sql = ("SELECT " + _FIELDS + _BASE + " WHERE " + where +
           " ORDER BY COALESCE(r.submitted_at, r.creation) DESC LIMIT %(_start)s, %(_len)s")
    return frappe.db.sql(sql, params, as_dict=True)


def count_requests(scope, filters, search=None):
    params = {}
    where = _list_where(scope, filters, search, params)
    row = frappe.db.sql("SELECT COUNT(*) AS c FROM `tabEC Approval Request` r "
                        "LEFT JOIN `tabEC Approval Type` t ON t.name = r.approval_type "
                        "WHERE " + where, params, as_dict=True)
    return row[0]["c"] if row else 0


def is_visible(scope, request_name):
    """True iff `request_name` falls within the caller's scope. Used to gate the timeline
    drawer without any DocPerm dependency."""
    sp, params = _scope.scope_predicate(scope)
    params["vis_name"] = request_name
    row = frappe.db.sql("SELECT 1 FROM `tabEC Approval Request` r WHERE " + sp +
                        " AND r.name = %(vis_name)s LIMIT 1", params)
    return bool(row)


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


def fetch_my_drafts(me):
    """Ban nhap CUA TOI o moi loai yeu cau da dang ky (05/09, Hoan): phieu "Luu nhap" xong bien
    mat - khong co EC Approval Request nen khong nam trong bat ky tab nao. Ban nhap = ban ghi
    nghiep vu docstatus 0, owner = toi, CHUA co approval_request. Doctype khong co cot
    approval_request thi bo qua (khong doan)."""
    from ecentric_workspace.approval_center.shared.registry import BUSINESS_DOCTYPE_DEFINITIONS
    out = []
    for dt, definition in BUSINESS_DOCTYPE_DEFINITIONS.items():
        if not frappe.db.table_exists(dt) or not frappe.db.has_column(dt, "approval_request"):
            continue
        filters = {"owner": me, "docstatus": 0, "approval_request": ["is", "not set"]}
        if frappe.db.has_column(dt, "status"):
            filters["status"] = ["not in", ["Cancelled", "Rejected"]]
        for r in frappe.get_all(dt, filters=filters, fields=["name", "modified", "creation"],
                                order_by="modified desc", limit_page_length=50):
            out.append({"doctype": dt, "name": r.name, "approval_type": definition.code,
                        "modified": r.modified, "creation": r.creation})
    out.sort(key=lambda r: r["modified"] or "", reverse=True)
    return out
