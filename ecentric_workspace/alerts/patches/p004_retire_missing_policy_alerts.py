"""Retire operational missing_policy EC Alerts (2026-06-14).

Decision (batch "Retire missing_policy from operational Alerts"): missing_policy
is a SETUP/COVERAGE gap tracked by Price Setup (order-derived coverage in
services.policy_coverage), NOT an operational price alert. The engine no longer
creates these records (alert_engine), and the API/KPIs exclude them. This patch
terminalizes the EXISTING active missing_policy records so they leave the
operational list/KPI, leaving a full audit trail.

Properties:
  * NO hard delete - records are TRANSITIONED to status `Closed` (terminal) with
    a resolution_note. Audit is the controller's: EC Alert has track_changes=1 so
    save() writes a Version (status + resolution_note change) and
    _stamp_resolution() sets resolved_by/resolved_at. No manual Comment -> no
    duplicate timeline event.
  * Controller path (frappe.get_doc + doc.save), NOT raw SQL UPDATE - so
    on_update / audit / case recompute fire correctly and the no-reopen guard is
    respected. (Contrast p002, a same-state terminal->terminal data fix that
    intentionally used raw SQL.)
  * IDEMPOTENT - only ACTIVE (Open / In Review) missing_policy rows are touched;
    a re-run finds 0 active rows and is a no-op. Records already in a terminal
    state (Closed / Ignored / Cancelled / legacy Resolved) are left untouched.
  * Per-alert ToDo recompute is SUSPENDED during the loop (autosync_suspended)
    and the aggregated Setup ToDo is recomputed ONCE per affected brand AFTER,
    from the canonical order-derived coverage - so retiring alerts does NOT
    wrongly zero a brand's Setup ToDo (the ToDo reflects real coverage, not the
    presence of these records).
  * Reports the closed count + per-brand recompute + remaining active (printed
    and returned).

Rollback: a plain code revert does NOT reopen these records (the controller's
no-reopen guard blocks Closed->Open and the data is already converted). To
restore, either re-enable creation in alert_engine and let the next ingestion
re-raise the gaps, or restore EC Alert from a pre-patch backup. The records are
fully preserved (no delete), so the audit history survives a code rollback.
"""
import frappe

from ecentric_workspace.alerts.services import case_lifecycle as cl
from ecentric_workspace.alerts.services import case_todo

_RULE = "missing_policy"
_CLOSE_STATUS = "Closed"
_NOTE = "Retired: coverage gap is now tracked through Price Setup."


def _active_missing_policy():
    """ACTIVE (Open / In Review) missing_policy alerts. _dict rows."""
    return frappe.get_all(
        "EC Alert",
        filters={"rule_code": _RULE, "status": ("in", list(cl.ACTIVE_STATUSES))},
        fields=["name", "brand"])


def _close_one(name):
    """Terminalize ONE alert via the controller. Idempotent + guard-aware.

    Audit is left ENTIRELY to the controller, with NO manual Comment (which
    would be a duplicate timeline event): EC Alert has track_changes=1, so
    doc.save() records a Version capturing the status -> Closed and the
    resolution_note change, and ECAlert._stamp_resolution() stamps resolved_by
    (= the migration user, Administrator under `bench migrate`) and resolved_at.
    The reason lives in resolution_note. One action -> one audit event."""
    doc = frappe.get_doc("EC Alert", name)
    if cl.is_terminal(doc.status):
        return False  # already terminal - skip
    if not cl.can_transition(doc.status, _CLOSE_STATUS):
        return False
    doc.status = _CLOSE_STATUS
    doc.resolution_note = _NOTE
    doc.save(ignore_permissions=True)   # controller stamps resolved_by/resolved_at + Version
    return True


def execute():
    rows = _active_missing_policy()
    if not rows:
        print("p004_retire_missing_policy_alerts: 0 active missing_policy alerts - no-op")
        return {"closed": 0, "brands": []}

    brands = sorted({(r.get("brand") or "") for r in rows if r.get("brand")})
    closed = 0
    # Suspend per-row ToDo recompute; we recompute each brand exactly ONCE after.
    with case_todo.autosync_suspended():
        for r in rows:
            try:
                if _close_one(r["name"]):
                    closed += 1
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "p004_retire_missing_policy_alerts close %s" % r.get("name"))
    frappe.db.commit()

    # Recompute the aggregated Setup ToDo per affected brand from the CANONICAL
    # order-derived coverage (NOT from these now-closed records). Fail-open.
    for b in brands:
        try:
            case_todo.sync_brand_setup(b)
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "p004_retire_missing_policy_alerts recompute %s" % b)
    frappe.db.commit()

    remaining = len(_active_missing_policy())
    print("p004_retire_missing_policy_alerts: closed %d missing_policy alert(s) "
          "across %d brand(s); remaining active: %d"
          % (closed, len(brands), remaining))
    return {"closed": closed, "brands": brands, "remaining": remaining}
