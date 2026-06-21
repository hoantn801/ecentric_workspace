# Copyright (c) 2026, eCentric and contributors
"""WR Hotfix scheduler: Employee-driven (no Weekly Report Schedule).

Source of truth chain:
    Active Employee
      -> Employee.department (primary, this phase only)
      -> Department Reporting Window (enabled=1)
      -> Weekly Team Update Draft
      -> native Assignment / ToDo

Weekly Report Schedule DocType + the Custom Field wr_schedule on WTU are
KEPT in the codebase as deprecated artifacts (non-destructive). This
scheduler no longer reads them.
"""

import re

import frappe

from ecentric_workspace.weekly_report import service
from ecentric_workspace.weekly_report import week_calendar
from ecentric_workspace.weekly_report.week_calendar import MissingReportingWindowError


def _sanitize_savepoint(name, index):
    safe = re.sub(r"[^A-Za-z0-9_]", "_", str(name))[:40]
    return "wr_obl_" + str(index) + "_" + safe


def generate_weekly_obligations(run_date=None, employee_names=None):
    """Daily idempotent generator.

    Args:
        run_date: ISO date/datetime string, datetime, date, or None (site tz).
        employee_names: list[str] | None. If set, restrict to those Employees.

    Returns:
        dict counters: processed, created, adopted, reused, skipped, errored,
        drw_missing.

    Behavior:
      For each Employee with status="Active":
        ensure_weekly_obligation validates User enabled + Department
        + DRW.enabled internally and returns "skipped" on any failure.
      Per-row savepoint isolates failures; savepoint/rollback API failure
      ABORTS the whole batch (no silent continue under broken isolation).
    """
    # Rollout kill-switch (site_config): the automatic batch path is OFF by
    # default. Manual pilot runs that pass `employee_names` always bypass the
    # switch -- that is the supported pre-rollout test path. The flag is read
    # via frappe.conf (site_config.json) so flipping it does NOT require code
    # push; cint() coerces unset / null / non-numeric values to 0.
    auto_enabled = frappe.utils.cint(
        frappe.conf.get("enable_weekly_report_auto_generation", 0)
    )
    if not employee_names and not auto_enabled:
        return {
            "processed": 0, "created": 0, "adopted": 0, "reused": 0,
            "skipped": 0, "errored": 0, "drw_missing": 0,
            "disabled": True,
        }

    now = week_calendar._now(run_date)
    week = week_calendar.compute_week_for(now=now)

    filters = {"status": "Active"}
    if employee_names:
        filters["name"] = ["in", list(employee_names)]
    employees = frappe.get_all(
        "Employee",
        filters=filters,
        fields=["name", "user_id", "department"],
    )

    stats = {
        "processed": 0, "created": 0, "adopted": 0, "reused": 0,
        "skipped": 0, "errored": 0, "drw_missing": 0,
    }

    for i, e in enumerate(employees):
        stats["processed"] += 1
        sp = _sanitize_savepoint(e["name"], i)
        try:
            frappe.db.savepoint(sp)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "wr.scheduler savepoint create failed: " + sp,
            )
            raise

        try:
            outcome = service.ensure_weekly_obligation(e["name"], week, now=now)
            stats[outcome] = stats.get(outcome, 0) + 1
        except MissingReportingWindowError as exc:
            try:
                frappe.db.rollback(save_point=sp)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "wr.scheduler rollback failed (DRW): " + sp,
                )
                raise
            # Hotfix classification: DRW missing / DRW disabled = controlled
            # SKIPPED (not errored). `errored` is reserved for unexpected DB /
            # assignment / rollback failure. drw_missing remains a stats
            # subcategory for observability.
            stats["drw_missing"] += 1
            stats["skipped"] += 1
            frappe.log_error(
                "wr.scheduler DRW missing employee=" + e["name"]
                + " dept=" + (e.get("department") or "")
                + " err=" + str(exc),
                "wr.drw_missing",
            )
            continue
        except Exception:
            try:
                frappe.db.rollback(save_point=sp)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "wr.scheduler rollback failed (generic): " + sp,
                )
                raise
            stats["errored"] += 1
            frappe.log_error(
                frappe.get_traceback(),
                "wr.scheduler emp=" + e["name"] + " week=" + week["week_label"],
            )
            continue

    return stats


def wr_due_overdue_scan(run_date=None):
    """Daily: for every non-terminal Weekly Team Update obligation, notify the submitter
    when it is due soon (<=24h) or overdue. Routes through the ONE central publish service
    with a STABLE dedupe key (event|wtu|user|due_at) so re-running the scheduler creates no
    duplicates, and terminal (Submitted/Reviewed) updates are never (re)notified.

    Distinct from generate_weekly_obligations (which CREATES obligations) -- this only
    notifies; no scheduler is duplicated."""
    from ecentric_workspace.notification_center import events as ncev
    from ecentric_workspace.action_center.resolvers import build_wtu_url

    now = frappe.utils.now_datetime()
    soon = frappe.utils.add_to_date(now, hours=24)
    wtus = frappe.get_all(
        "Weekly Team Update",
        filters={"status": ["not in", ["Submitted", "Reviewed"]]},
        fields=["name", "submitter", "week_label", "due_at"],
        limit_page_length=0)
    sent = 0
    for w in wtus:
        user = w.get("submitter")
        due = w.get("due_at")
        if not user or not due:
            continue
        due_dt = frappe.utils.get_datetime(due)
        label = str(w.get("week_label") or "")
        if due_dt < now:
            event = "task_overdue"
            subject = "[Quá hạn] Báo cáo tuần " + label
            message = "Báo cáo tuần " + label + " đã quá hạn nộp."
        elif due_dt <= soon:
            event = "task_due_soon"
            subject = "[Sắp đến hạn] Báo cáo tuần " + label
            message = "Báo cáo tuần " + label + " sắp đến hạn nộp."
        else:
            continue
        try:
            ncev.publish_notification_event(
                event, user, subject, message,
                action_url=build_wtu_url(label),
                reference_doctype="Weekly Team Update", reference_name=w["name"],
                actor="Administrator",
                dedupe_key=event + "|" + w["name"] + "|" + user + "|" + str(due))
            sent += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "wr_due_overdue_scan")
    return {"notified": sent}
