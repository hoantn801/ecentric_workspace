# Copyright (c) 2026, eCentric and contributors
"""Idempotent setup of the OUTSIDE_WORK-V1 process: one Direct Manager level
(Requester Manager, Any One), no fulfillment. Users are resolved at runtime from
Employee.reports_to - nothing hardcoded. Non-destructive; safe to re-run."""
import frappe
from frappe import _

APPROVAL_TYPE = "OUTSIDE_WORK"
PROCESS_CODE = "OUTSIDE_WORK-V1"


@frappe.whitelist()
def setup_outside_work_v1(dry_run=1, apply=0):
    # apply=1 is the authoritative "go" switch; dry_run kept for backward-compat.
    # Applies when apply=1 (with any dry_run) OR the legacy dry_run=0+apply=1; otherwise dry-run.
    dry = int(apply or 0) != 1
    steps = []

    def add(msg):
        steps.append(msg)

    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        return {"mode": "dry_run" if dry else "apply", "ok": False,
                "steps": ["[ERR] EC Approval Type OUTSIDE_WORK missing (run p002 seed first)"]}

    proc = frappe.db.get_value("EC Approval Process",
                               {"process_code": PROCESS_CODE}, "name")
    if proc:
        add("[OK] process %s already exists" % PROCESS_CODE)
    else:
        add("[NEW] create process %s (status Draft)" % PROCESS_CODE)
        if not dry:
            p = frappe.get_doc({
                "doctype": "EC Approval Process", "process_code": PROCESS_CODE,
                "title": "Outside Work V1", "approval_type": APPROVAL_TYPE,
                "version_no": 1, "status": "Draft",
            })
            p.insert(ignore_permissions=True)
            lvl = frappe.get_doc({
                "doctype": "EC Approval Level", "approval_process": p.name, "level_no": 1,
                "level_name": "Direct Manager", "mandatory": 1, "approval_mode": "Any One",
                "minimum_approvals": 1, "allows_amount_adjustment": 0,
            })
            lvl.append("participants", {"participant_purpose": "Approver",
                                        "source_type": "Requester Manager", "sort_order": 1})
            lvl.insert(ignore_permissions=True)
            add("[OK] created Direct Manager level (Requester Manager, Any One)")
    return {"mode": "dry_run" if dry else "apply", "ok": True, "steps": steps}


@frappe.whitelist()
def validate_outside_work_v1():
    proc = frappe.db.get_value("EC Approval Process", {"process_code": PROCESS_CODE},
                               ["name", "status"], as_dict=True)
    checks = []
    checks.append({"check": "process exists", "ok": bool(proc)})
    if proc:
        checks.append({"check": "status is Draft or Active", "ok": proc.status in ("Draft", "Active")})
        levels = frappe.get_all("EC Approval Level", filters={"approval_process": proc.name},
                                fields=["level_no", "level_name", "approval_mode"])
        checks.append({"check": "exactly one level (Direct Manager)",
                       "ok": len(levels) == 1 and levels[0].level_name == "Direct Manager"})
        others = frappe.get_all("EC Approval Process",
                                filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                         "process_code": ["!=", PROCESS_CODE]}, pluck="name")
        checks.append({"check": "no OTHER Active process for OUTSIDE_WORK", "ok": not others})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
