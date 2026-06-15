# Copyright (c) 2026, eCentric and contributors
"""WR1A scheduler entry point.

Registered in hooks.py:
  scheduler_events.daily += "ecentric_workspace.weekly_report.scheduler.generate_weekly_obligations"

Daily cadence: a missed Saturday/Sunday run self-recovers on Monday because
ensure_weekly_obligation is idempotent (canonical lookup by obligation_key
prevents duplicates).

WR1A-V FIX 2: savepoint create failure and rollback failure both raise to
abort the batch. We never run further rows under a transaction state we
cannot guarantee. Silent continue is a correctness hazard, not robustness.
"""

import re

import frappe

from ecentric_workspace.weekly_report import service
from ecentric_workspace.weekly_report import week_calendar
from ecentric_workspace.weekly_report.week_calendar import MissingReportingWindowError


def _sanitize_savepoint(name, index):
    """Savepoint names: alphanumeric + underscore, capped length."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", str(name))[:40]
    return "wr_obl_" + str(index) + "_" + safe


def _in_effective_range(schedule, week):
    """Schedule active iff effective_from overlaps the current week."""
    ws = week["week_start_date"]
    we = week["week_end_date"]
    ef = schedule.get("effective_from")
    et = schedule.get("effective_to")
    if ef is None:
        return False  # effective_from is reqd; defensive
    ef = frappe.utils.getdate(ef)
    if ef > we:
        return False
    if et is not None:
        et = frappe.utils.getdate(et)
        if et < ws:
            return False
    return True


def generate_weekly_obligations(run_date=None, schedule_names=None):
    """Daily idempotent generator.

    Args:
        run_date: ISO date/datetime string, datetime, date, or None (site tz).
        schedule_names: list[str] | None.

    Returns:
        dict counters: processed, created, adopted, reused, skipped, errored,
        drw_missing.

    FIX 2: A savepoint API failure or rollback failure RAISES, aborting the
    batch. We never proceed when transaction isolation cannot be guaranteed.
    """
    now = week_calendar._now(run_date)
    week = week_calendar.compute_week_for(now=now)

    filters = {"enabled": 1}
    if schedule_names:
        filters["name"] = ["in", list(schedule_names)]
    schedules = frappe.get_all(
        "Weekly Report Schedule",
        filters=filters,
        fields=[
            "name", "employee", "user", "reporting_department",
            "effective_from", "effective_to", "last_generated_week",
        ],
    )

    stats = {
        "processed": 0, "created": 0, "adopted": 0, "reused": 0,
        "skipped": 0, "errored": 0, "drw_missing": 0,
    }

    for i, s in enumerate(schedules):
        stats["processed"] += 1
        sp = _sanitize_savepoint(s["name"], i)

        # FIX 2: savepoint create failure -> abort batch (no silent continue).
        try:
            frappe.db.savepoint(sp)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "wr.scheduler savepoint create failed: " + sp,
            )
            raise

        try:
            if not _in_effective_range(s, week):
                stats["skipped"] += 1
                continue
            outcome = service.ensure_weekly_obligation(s, week, now=now)
            stats[outcome] = stats.get(outcome, 0) + 1
            if outcome in ("created", "adopted", "reused"):
                frappe.db.set_value(
                    "Weekly Report Schedule", s["name"],
                    "last_generated_week", week["week_label"],
                    update_modified=False,
                )
        except MissingReportingWindowError as e:
            # FIX 2: rollback failure -> abort batch.
            try:
                frappe.db.rollback(save_point=sp)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "wr.scheduler rollback failed (DRW path): " + sp,
                )
                raise
            stats["drw_missing"] += 1
            stats["errored"] += 1
            frappe.log_error(
                "wr.scheduler DRW missing for schedule=" + s["name"]
                + " dept=" + (s.get("reporting_department") or "")
                + " err=" + str(e),
                "wr.drw_missing",
            )
            continue
        except Exception:
            try:
                frappe.db.rollback(save_point=sp)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "wr.scheduler rollback failed (generic path): " + sp,
                )
                raise
            stats["errored"] += 1
            frappe.log_error(
                frappe.get_traceback(),
                "wr.scheduler row=" + s["name"] + " week=" + week["week_label"],
            )
            continue

    return stats
