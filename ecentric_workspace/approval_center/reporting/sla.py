# Copyright (c) 2026, eCentric and contributors
"""SLA state for a request's active level (reporting only - never mutates workflow state).

Priority:
  1) configured_policy  : the level already has a persisted due_at (from an attached
                          EC Approval SLA Policy). Use it as-is.
  2) operational_default: no policy/due_at -> compute a reporting-only default of
                          DEFAULT_WORKING_HOURS working hours from the level's
                          activated_at, over a standard Mon-Fri 09:00-18:00 schedule
                          (reuses the engine business-hours algorithm; no calendar
                          record required). Labeled operational, NOT contractual.
  3) unavailable        : no due_at and no activation time -> cannot assess.
"""
from datetime import time

from frappe.utils import get_datetime, now_datetime

DEFAULT_WORKING_HOURS = 24
_STD_START = time(9, 0)
_STD_END = time(18, 0)


def _standard_periods():
    # Mon(0)..Fri(4) 09:00-18:00
    return {wd: [(_STD_START, _STD_END)] for wd in range(0, 5)}


def _operational_due(activated_at):
    from ecentric_workspace.approval_center.engine import business_hours as bh
    try:
        return bh.calculate_business_due_at(get_datetime(activated_at), DEFAULT_WORKING_HOURS,
                                            _standard_periods(), holidays=set())
    except Exception:
        return None


def sla_state(row, ref_now=None):
    """row: due_at, is_overdue, current_activated_at, approval_status.
    Returns {source, due_at, breached, applies}. `applies` is False for closed requests."""
    now = get_datetime(ref_now) if ref_now else now_datetime()
    is_open = row.get("approval_status") in ("Pending", "Information Required")

    due = row.get("due_at")
    if due:
        due = get_datetime(due)
        breached = is_open and now > due
        return {"source": "configured_policy", "due_at": due, "breached": bool(breached), "applies": is_open}

    activated = row.get("current_activated_at")
    if not activated:
        return {"source": "unavailable", "due_at": None, "breached": False, "applies": is_open}

    due = _operational_due(activated)
    if not due:
        return {"source": "unavailable", "due_at": None, "breached": False, "applies": is_open}
    breached = is_open and now > get_datetime(due)
    return {"source": "operational_default", "due_at": get_datetime(due), "breached": bool(breached), "applies": is_open}
