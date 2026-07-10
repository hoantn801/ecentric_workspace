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
    """Departments whose department_head is an Employee of this user. Fail-closed -> []."""
    emps = frappe.get_all("Employee", filters={"user_id": user}, pluck="name")
    if not emps:
        return []
    return frappe.get_all("Department", filters={"department_head": ["in", emps]}, pluck="name")


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
