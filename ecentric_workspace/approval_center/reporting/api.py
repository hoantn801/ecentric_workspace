# Copyright (c) 2026, eCentric and contributors
"""Whitelisted read APIs for the Approval Center Operations Dashboard.

Every endpoint resolves the caller's scope server-side (reporting.scope) and passes it
to the governed service. Filters are validated/normalized here. There is NO unrestricted
frappe.client.get_list path for dashboard data, no DocPerm dependency, and nothing here
mutates workflow state.
"""
import json

import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day, nowdate, add_to_date

from ecentric_workspace.approval_center.reporting import scope as _scope
from ecentric_workspace.approval_center.reporting import service as _service
from ecentric_workspace.approval_center.reporting import status as _status

_ALLOWED_STATUS = set(_status.ENGINE_STATUSES)
_ALLOWED_SLA = {"breached", "configured_policy", "operational_default", "unavailable"}


def _parse_filters(filters):
    if isinstance(filters, str):
        try:
            filters = json.loads(filters or "{}")
        except Exception:
            filters = {}
    filters = filters or {}
    out = {}
    # date range: default = current month
    df = filters.get("date_from")
    dt = filters.get("date_to")
    if not (df and dt):
        df = str(get_first_day(nowdate()))
        dt = str(get_last_day(nowdate()))
    out["date_from"] = str(df) + " 00:00:00"
    out["date_to"] = str(dt) + " 23:59:59"
    for k in ("category", "approval_type", "department", "requester", "approver"):
        v = filters.get(k)
        if v not in (None, "", []):
            out[k] = v
    # status: accept normalized OR engine label; store engine value
    st = filters.get("status")
    if st:
        eng = _status.to_engine(st) if st in _status.NORMALIZED_STATUSES else st
        if eng in _ALLOWED_STATUS:
            out["status"] = eng
    cl = filters.get("current_level")
    if cl not in (None, ""):
        try:
            out["current_level"] = int(cl)
        except (TypeError, ValueError):
            pass
    sla = filters.get("sla_state")
    if sla in _ALLOWED_SLA:
        out["sla_state"] = sla
    if filters.get("view") in ("open", "period"):
        out["view"] = filters["view"]
    return out


@frappe.whitelist()
def get_dashboard(filters=None):
    scope = _scope.resolve_scope(frappe.session.user)
    return _service.build_dashboard(scope, _parse_filters(filters))


@frappe.whitelist()
def get_filter_options():
    from ecentric_workspace.approval_center.reporting import queries as _q
    scope = _scope.resolve_scope(frappe.session.user)
    opts = _q.distinct_filter_values(scope)
    opts["statuses"] = _status.NORMALIZED_STATUSES
    opts["sla_states"] = sorted(_ALLOWED_SLA)
    opts["scope_mode"] = scope.get("mode")
    opts["can_export"] = _scope.can_export(scope)
    return opts


@frappe.whitelist()
def drilldown(filters=None, limit=200):
    scope = _scope.resolve_scope(frappe.session.user)
    try:
        limit = min(int(limit), 500)
    except (TypeError, ValueError):
        limit = 200
    return {"rows": _service.drilldown(scope, _parse_filters(filters), limit=limit),
            "scope_mode": scope.get("mode")}
