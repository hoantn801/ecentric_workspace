"""Alert Center scheduler jobs (Phase E, decision D2-E).

Both jobs are DRY-RUN-SAFE by construction: process_pending_actions can only
end Pending -> Dry Run / Skipped (no HTTP client exists in alerts/), and pause
expiry only flips Active -> Expired. Kill switch: set
`ec_alerts_scheduler_disabled: 1` in site_config -> both jobs no-op instantly.
Fail-safe: any error reading config disables the run. Idempotent: re-runs
find nothing left to do. Per-row try/except + frappe.log_error - one bad row
never kills the batch.
"""
import frappe
from frappe.utils import now_datetime


def _disabled():
    try:
        return bool(frappe.conf.get("ec_alerts_scheduler_disabled"))
    except Exception:
        return True  # fail safe: cannot read config -> do nothing


def expire_automation_pauses():
    """Hourly: Active pauses past pause_until -> Expired (doc.save for the
    track_changes audit trail)."""
    if _disabled():
        return
    try:
        names = frappe.get_all(
            "EC Automation Pause",
            filters={"status": "Active", "pause_until": ("<", now_datetime())},
            pluck="name", limit_page_length=500)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "alerts.tasks.expire_pauses query")
        return
    expired = 0
    for name in names:
        try:
            doc = frappe.get_doc("EC Automation Pause", name)
            doc.status = "Expired"
            doc.save(ignore_permissions=True)
            expired += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "alerts.tasks.expire_pauses %s" % name)
    return {"expired": expired, "candidates": len(names)}


def process_action_queue_job():
    """Every 10 minutes: drain Pending Stock Safety Lock actions through the
    dry-run guard chain (pause -> credential -> Dry Run stamp)."""
    if _disabled():
        return
    try:
        from ecentric_workspace.alerts.services import action_queue
        return action_queue.process_pending_actions()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "alerts.tasks.process_action_queue_job")
