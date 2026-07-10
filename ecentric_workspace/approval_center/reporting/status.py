# Copyright (c) 2026, eCentric and contributors
"""Normalized lifecycle-status helpers for Approval Center reporting.

Maps the engine's persisted `EC Approval Request.approval_status` values to the
dashboard's normalized vocabulary. No status names are invented.

Engine value            -> Normalized (dashboard)
  Pending               -> Pending
  Information Required   -> Information Required
  Approved               -> Completed          (workflow completed successfully)
  Rejected               -> Rejected
  Cancelled              -> Cancelled

Draft is NOT represented on EC Approval Request: a request row only exists after
governed submit (which sets status=Pending + submitted_at). Pre-submit drafts live
on the business document, so 'Draft' is a valid normalized label but never appears
in request-table results. This is why 'exclude Draft' KPIs are naturally satisfied.
"""

ENGINE_STATUSES = ["Pending", "Information Required", "Approved", "Rejected", "Cancelled"]
NORMALIZED_STATUSES = ["Draft", "Pending", "Information Required", "Completed", "Rejected", "Cancelled"]

# active = still awaiting action (used for pending / SLA / aging views)
OPEN_ENGINE_STATUSES = ["Pending", "Information Required"]
CLOSED_ENGINE_STATUSES = ["Approved", "Rejected", "Cancelled"]

_ENGINE_TO_NORM = {
    "Pending": "Pending",
    "Information Required": "Information Required",
    "Approved": "Completed",
    "Rejected": "Rejected",
    "Cancelled": "Cancelled",
}
_NORM_TO_ENGINE = {
    "Pending": "Pending",
    "Information Required": "Information Required",
    "Completed": "Approved",
    "Rejected": "Rejected",
    "Cancelled": "Cancelled",
    "Draft": None,  # not present in the request table
}


def normalize(engine_status):
    """Engine approval_status -> normalized dashboard label."""
    return _ENGINE_TO_NORM.get(engine_status, engine_status or "Draft")


def to_engine(normalized_status):
    """Normalized dashboard label -> engine approval_status (None for Draft)."""
    return _NORM_TO_ENGINE.get(normalized_status, normalized_status)


def is_open(engine_status):
    return engine_status in OPEN_ENGINE_STATUSES
