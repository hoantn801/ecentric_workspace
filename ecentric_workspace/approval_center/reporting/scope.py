# Copyright (c) 2026, eCentric and contributors
"""Backend-authoritative visibility scope for Approval Center reporting.

resolve_scope(user) classifies the caller and scope_predicate(scope) returns a
parameterized SQL fragment (referencing request alias `r`) that MUST be ANDed into
every reporting query. Frontend filters are UX only and are never a substitute for
this predicate.

Tiers (broadest wins for classification; department/approver also see own + assigned):
  admin      : System Manager or 'Approval Admin' role -> organization-wide.
  department : head of one or more Departments -> those depts' requests + own + assigned.
  approver   : appears as an approver on any request -> assigned/historical + own.
  requester  : everyone else -> own requests only.

Governance role names (Finance/HR/Operations) do NOT grant org-wide access on their
own; broader access must come from an explicit admin role (or a future governed
'Approval Dashboard Access' config - deferred to D3).
"""
import frappe

ADMIN_ROLES = ("System Manager", "Approval Admin")


def _managed_departments(user):
    """Departments this user heads. Fail-closed -> [].

    #139 (2026-08-03): this used to query Department.department_head unconditionally.
    That column does not exist on this site -- Department here is stock ERPNext plus a
    local set of Custom Fields, and the head is recorded on `manager_email` (a User
    email), not on an Employee link. Every call therefore raised
    (1054, "Unknown column 'department_head' in 'WHERE'"), which propagated out of
    resolve_scope and killed reporting.api.get_dashboard for EVERY non-admin caller
    (admins return before this line). 418 Error Log rows between 2026-07-19 and
    2026-08-03 are exactly this.

    The lookup is now meta-driven and never assumes a column. It reads the SAME two
    sources, in the SAME order, as engine.service.resolve_department_manager_user --
    Department.department_head -> Employee.user_id first, then Department.manager_email
    as a direct user -- so "who the dashboard treats as head of a department" can never
    disagree with "who the engine routes that department's approvals to". A field that
    does not exist is skipped, not queried; when neither exists the result is []
    (fail-closed) and the caller falls through to the approver/requester tier.
    """
    if not user or user == "Guest":
        return []
    meta = frappe.get_meta("Department")
    found = []
    if meta.has_field("department_head"):
        emps = frappe.get_all("Employee", filters={"user_id": user}, pluck="name")
        if emps:
            found += frappe.get_all(
                "Department",
                filters={"department_head": ["in", emps], "disabled": 0},
                pluck="name",
            )
    if meta.has_field("manager_email"):
        found += frappe.get_all(
            "Department",
            filters={"manager_email": user, "disabled": 0},
            pluck="name",
        )
    seen, out = set(), []
    for d in found:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def resolve_scope(user=None):
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if roles.intersection(ADMIN_ROLES):
        return {"mode": "admin", "user": user, "departments": []}
    depts = _managed_departments(user)
    if depts:
        return {"mode": "department", "user": user, "departments": depts}
    if frappe.db.exists("EC Approval Request Approver", {"approver": user}):
        return {"mode": "approver", "user": user, "departments": []}
    return {"mode": "requester", "user": user, "departments": []}


def scope_predicate(scope):
    """Return (sql_fragment, params) to AND into a query using request alias `r`."""
    mode = scope.get("mode")
    if mode == "admin":
        return ("1=1", {})
    user = scope.get("user")
    params = {"scope_user": user}
    own = "r.requested_by = %(scope_user)s"
    assigned = ("EXISTS (SELECT 1 FROM `tabEC Approval Request Approver` ra "
                "WHERE ra.approval_request = r.name AND ra.approver = %(scope_user)s)")
    if mode == "requester":
        return (own, params)
    if mode == "approver":
        return ("(%s OR %s)" % (own, assigned), params)
    if mode == "department":
        depts = scope.get("departments") or []
        if depts:
            keys = []
            for i, d in enumerate(depts):
                k = "scope_dept_%d" % i
                params[k] = d
                keys.append("%%(%s)s" % k)
            deptpred = "r.requester_department IN (%s)" % ", ".join(keys)
        else:
            deptpred = "0=1"
        return ("(%s OR %s OR %s)" % (deptpred, own, assigned), params)
    # unknown -> safest (own only)
    return (own, params)


def can_export(scope):
    """MVP: only org-wide admins may export the full dataset; others export own scope."""
    return scope.get("mode") == "admin"
