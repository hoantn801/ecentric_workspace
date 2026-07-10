# Copyright (c) 2026, eCentric and contributors
"""AI Topup activation tooling - SPLIT so UAT can run end-to-end while the catalog
card stays hidden:
  * enable_ai_topup_uat   -> process Active, catalog card kept INACTIVE (direct-route UAT)
  * publish_ai_topup_after_uat -> catalog card Active (public go-live), only after UAT
Both System-Manager-only, dry_run by default, explicit apply, idempotent, blocked on
any validation failure, audited. Never run during migrate or automatically."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.services.activation_flags import is_dry_run

CALENDAR = "EC_STANDARD_9_18"
PROCESS = "AI_TOPUP-V1"
TYPE = "AI_TOPUP"
ROUTE = "approvals/ai-topup"
API_METHODS = ["get_bootstrap", "get_request_detail", "submit_request", "approve", "reject",
               "request_information", "resubmit", "cancel", "claim_fulfillment", "complete_fulfillment"]


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run AI Topup activation."), frappe.PermissionError)


def _validation():
    """Full readiness = process/participant/SLA/calendar/finance-flag (validate_ai_topup_v1)
    + route exists + API methods reachable. Status-agnostic (Draft or Active)."""
    from ecentric_workspace.approval_center.ai_topup.setup import validate_ai_topup_v1
    v = validate_ai_topup_v1()
    checks = [{"status": st, "check": msg} for st, msg in v["checks"]]
    ok = bool(v["ready_for_activation"])

    def add(cond, msg):
        nonlocal ok
        checks.append({"status": "PASS" if cond else "FAIL", "check": msg})
        ok = ok and bool(cond)

    add(bool(frappe.db.exists("Web Page", {"route": ROUTE})), "frontend route /%s exists" % ROUTE)
    for m in API_METHODS:
        try:
            frappe.get_attr("ecentric_workspace.approval_center.api.ai_topup." + m)
            add(True, "API %s reachable" % m)
        except Exception:
            add(False, "API %s reachable" % m)
    return checks, ok


@frappe.whitelist()
def enable_ai_topup_uat(dry_run=1, apply=0, commit=0):
    """Activate AI_TOPUP-V1 so UAT can submit/approve/fulfil via the direct route,
    while the catalog card stays INACTIVE (hidden from ordinary users)."""
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    checks, ok = _validation()
    report = {"operation": "enable_uat", "mode": "dry_run" if dry else "commit", "checks": checks, "ready": ok}
    if not ok:
        report["result"] = "BLOCKED (validation failed - nothing changed)"
        return report
    if dry:
        report["result"] = "DRY_RUN_OK (ready to UAT-enable; nothing changed)"
        return report
    already = frappe.db.get_value("EC Approval Process", PROCESS, "status") == "Active"
    frappe.db.set_value("EC Approval Process", PROCESS, "status", "Active")   # process only
    # catalog card intentionally left as-is (inactive) so it stays hidden
    if not already:
        frappe.get_doc("EC Approval Process", PROCESS).add_comment(
            "Info", _("UAT enabled (process Active; catalog card kept inactive) by {0}").format(frappe.session.user))
    frappe.db.commit()
    report["result"] = "UAT_ENABLED (process Active; catalog card inactive)"
    report["card_status"] = frappe.db.get_value("EC Approval Type", TYPE, "card_status")
    return report


@frappe.whitelist()
def publish_ai_topup_after_uat(dry_run=1, apply=0, commit=0):
    """Public go-live AFTER UAT sign-off: activate the catalog card + route.
    Blocked unless the process is already Active (UAT-enabled) and validation passes."""
    _require_sm()
    dry = is_dry_run(dry_run, apply, commit)
    checks, ok = _validation()
    active = frappe.db.get_value("EC Approval Process", PROCESS, "status") == "Active"
    checks.append({"status": "PASS" if active else "FAIL", "check": "AI_TOPUP-V1 is Active (UAT-enabled)"})
    ok = ok and active
    report = {"operation": "publish", "mode": "dry_run" if dry else "commit", "checks": checks, "ready": ok}
    if not ok:
        report["result"] = "BLOCKED (UAT not enabled or validation failed - nothing changed)"
        return report
    if dry:
        report["result"] = "DRY_RUN_OK (ready to publish; nothing changed)"
        return report
    already = frappe.db.get_value("EC Approval Type", TYPE, "card_status") == "Active"
    frappe.db.set_value("EC Approval Type", TYPE, {
        "card_status": "Active", "process_status": "Live", "route": "/" + ROUTE})
    if not already:
        frappe.get_doc("EC Approval Type", TYPE).add_comment(
            "Info", _("AI Topup published (catalog card Active) by {0}").format(frappe.session.user))
    frappe.db.commit()
    report["result"] = "PUBLISHED (catalog card Active; route /%s)" % ROUTE
    return report


@frappe.whitelist()
def activate_ai_topup(dry_run=1, apply=0):
    """Combined convenience (internal). Production must use the split operations:
    enable_ai_topup_uat then publish_ai_topup_after_uat."""
    _require_sm()
    if is_dry_run(dry_run, apply, commit):
        r = enable_ai_topup_uat(dry_run=1, apply=0)
        r["note"] = "Combined helper is internal; production flow = enable_ai_topup_uat then publish_ai_topup_after_uat."
        return r
    r1 = enable_ai_topup_uat(dry_run=0, apply=1)
    if not r1["result"].startswith("UAT_ENABLED"):
        return r1
    return publish_ai_topup_after_uat(dry_run=0, apply=1)


@frappe.whitelist()
def verify_activation():
    _require_sm()
    return {
        "process": PROCESS,
        "process_status": frappe.db.get_value("EC Approval Process", PROCESS, "status"),
        "card_status": frappe.db.get_value("EC Approval Type", TYPE, "card_status"),
        "catalog_process_status": frappe.db.get_value("EC Approval Type", TYPE, "process_status"),
        "route": frappe.db.get_value("EC Approval Type", TYPE, "route"),
    }
