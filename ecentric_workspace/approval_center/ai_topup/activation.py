# Copyright (c) 2026, eCentric and contributors
"""AI Topup activation tooling. System-Manager-only, dry_run by default, explicit
apply required, idempotent, blocked on any validation failure. NEVER runs during
migrate or automatically after deploy. Activation sets AI_TOPUP-V1 Active + the
catalog card Active + route, and audits the action."""
import frappe
from frappe import _

CALENDAR = "EC_STANDARD_9_18"
PROCESS = "AI_TOPUP-V1"
TYPE = "AI_TOPUP"
ROUTE = "approvals/ai-topup"
POLICIES = ["AI_TOPUP_MANAGER_3H", "AI_TOPUP_OPERATION_REVIEW_3H",
            "AI_TOPUP_FINANCE_REVIEW_3H", "AI_TOPUP_FULFILLMENT_3H"]
API_METHODS = ["get_bootstrap", "get_request_detail", "submit_request", "approve", "reject",
               "request_information", "resubmit", "cancel", "claim_fulfillment", "complete_fulfillment"]


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run AI Topup activation."), frappe.PermissionError)


@frappe.whitelist()
def activate_ai_topup(dry_run=1, apply=0):
    _require_sm()
    dry = bool(int(dry_run)) and not bool(int(apply))
    checks, ok = [], True

    def c(cond, msg):
        nonlocal ok
        checks.append({"status": "PASS" if cond else "FAIL", "check": msg})
        ok = ok and bool(cond)

    # 1-2 reuse the readiness validator
    from ecentric_workspace.approval_center.ai_topup.setup import validate_ai_topup_v1
    v = validate_ai_topup_v1()
    for st, msg in v["checks"]:
        c(st == "PASS", msg)
    # 3 route / 4 API reachability
    c(bool(frappe.db.exists("Web Page", {"route": ROUTE})), "frontend route /%s exists" % ROUTE)
    for m in API_METHODS:
        try:
            frappe.get_attr("ecentric_workspace.approval_center.api.ai_topup." + m)
            c(True, "API %s reachable" % m)
        except Exception:
            c(False, "API %s reachable" % m)
    # 5 calendar + SLA
    c(bool(frappe.db.get_value("EC Approval Business Calendar", CALENDAR, "active")), "business calendar active")
    for p in POLICIES:
        c(bool(frappe.db.get_value("EC Approval SLA Policy", p, "active")), "SLA %s active" % p)
    # 8 finance amount adjustment (flag-based, not name)
    c(bool(frappe.get_all("EC Approval Level",
           filters={"approval_process": PROCESS, "allows_amount_adjustment": 1})),
      "an approval level has allows_amount_adjustment=1 (Finance)")
    # 9 catalog type
    c(bool(frappe.db.exists("EC Approval Type", TYPE)), "catalog Approval Type %s exists" % TYPE)
    # no other active process
    others = frappe.get_all("EC Approval Process",
                            filters={"approval_type": TYPE, "status": "Active", "name": ["!=", PROCESS]}, pluck="name")
    c(not others, "no other Active process for %s" % TYPE)

    report = {"mode": "dry_run" if dry else "apply", "checks": checks, "ready": ok}
    if not ok:
        report["result"] = "BLOCKED (validation failed - not activated)"
        return report
    if dry:
        report["result"] = "DRY_RUN_OK (ready to activate; nothing changed)"
        return report

    # apply - explicit activation only
    frappe.db.set_value("EC Approval Process", PROCESS, "status", "Active")
    frappe.db.set_value("EC Approval Type", TYPE, {
        "card_status": "Active", "process_status": "Live", "route": "/" + ROUTE})
    frappe.get_doc("EC Approval Process", PROCESS).add_comment(
        "Info", _("AI Topup activated by {0}").format(frappe.session.user))
    frappe.db.commit()
    report["result"] = "ACTIVATED"
    return report


@frappe.whitelist()
def verify_activation():
    _require_sm()
    return {
        "process": PROCESS,
        "process_status": frappe.db.get_value("EC Approval Process", PROCESS, "status"),
        "card_status": frappe.db.get_value("EC Approval Type", TYPE, "card_status"),
        "process_status_field": frappe.db.get_value("EC Approval Type", TYPE, "process_status"),
        "route": frappe.db.get_value("EC Approval Type", TYPE, "route"),
    }
