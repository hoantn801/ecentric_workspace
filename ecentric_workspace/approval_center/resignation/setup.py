# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for RESIGNATION-V1 (Draft):
L1 Direct Manager Review (Reference Employee Manager from employee_email, with a config
fallback_user), + process Fulfillers (HR fulfillment queue). Identities are config seed
args (emails allowed here only) - never hardcoded in engine runtime. dry-run default;
apply=1 required. Never overwrites an Active process. No SLA in v1."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.engine.user_rules import require_active_system_user

PROCESS_CODE = "RESIGNATION-V1"
APPROVAL_TYPE = "RESIGNATION"
# Config seed defaults (overridable by args). Emails allowed in setup/config only, never in code paths.
DEFAULT_HR = ["tuan.ly@ecentric.vn"]
DEFAULT_FALLBACK = "tuan.ly@ecentric.vn"
MANAGER_FIELD = "employee_email"   # business field the Reference Employee Manager resolver reads


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Resignation setup."), frappe.PermissionError)


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


def _validate_users(label, users, rep):
    if not users:
        rep["errors"].append("No %s users supplied." % label)
    for u in users:
        try:
            require_active_system_user(u, label)
        except Exception as e:
            rep["errors"].append("%s: %s" % (label, str(e)))


def _set_user_participants(doc, purpose, users):
    keep = [p for p in doc.participants if p.participant_purpose != purpose]
    doc.set("participants", keep)
    for i, u in enumerate(users or []):
        doc.append("participants", {"participant_purpose": purpose, "source_type": "User",
                                    "user": u, "sort_order": i})


@frappe.whitelist()
def setup_resignation_v1(hr_fulfillers=None, fallback_user=None, dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    hr = _parse(hr_fulfillers, DEFAULT_HR)
    fb = (fallback_user or DEFAULT_FALLBACK) or None
    _validate_users("HR Fulfiller", hr, rep)
    if fb:
        try:
            require_active_system_user(fb, "Fallback User")
        except Exception as e:
            rep["errors"].append("Fallback User: %s" % str(e))
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (run p002 seed first)." % APPROVAL_TYPE)
    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["notes"].append("ALREADY_ACTIVE %s (left unchanged)" % PROCESS_CODE)
        rep["result"] = "ALREADY_ACTIVE"
        rep["blockers"] = rep["errors"]
        return rep
    active = frappe.get_all("EC Approval Process",
                            filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                     "name": ["!=", PROCESS_CODE]}, pluck="name")
    if active:
        rep["warnings"].append("Another Active process exists for %s: %s" % (APPROVAL_TYPE, active))
    rep["planned"] = [
        "process %s (Draft), no SLA policy (v1)" % PROCESS_CODE,
        "L1 Direct Manager Review (Reference Employee Manager on %s, fallback=%s, Any One)" % (MANAGER_FIELD, fb),
        "process Fulfillers (HR fulfillment)=%s" % hr,
    ]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (no writes)"
        return rep
    _upsert_process(hr, fb)
    frappe.db.commit()
    rep["result"] = "APPLIED (process Draft; card inactive)"
    return rep


def _upsert_process(hr, fb):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "Resignation V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.fulfillment_sla_policy = None
    _set_user_participants(proc, "Fulfiller", hr)
    proc.save(ignore_permissions=True)

    existing = frappe.get_all("EC Approval Level",
                              filters={"approval_process": PROCESS_CODE, "level_no": 1}, pluck="name")
    lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing else frappe.new_doc("EC Approval Level")
    lvl.approval_process = PROCESS_CODE
    lvl.level_no = 1
    lvl.level_name = "Direct Manager Review"
    lvl.mandatory = 1
    lvl.approval_mode = "Any One"
    lvl.minimum_approvals = 1
    lvl.allows_amount_adjustment = 0
    lvl.sla_policy = None
    lvl.set("participants", [])
    lvl.append("participants", {"participant_purpose": "Approver",
                                "source_type": "Reference Employee Manager",
                                "reference_field": MANAGER_FIELD, "fallback_user": fb, "sort_order": 0})
    lvl.save(ignore_permissions=True)


@frappe.whitelist()
def validate_resignation_v1():
    proc = frappe.db.get_value("EC Approval Process", {"process_code": PROCESS_CODE},
                               ["name", "status"], as_dict=True)
    checks = []

    def c(cond, msg):
        checks.append({"check": msg, "ok": bool(cond)})

    c(bool(proc), "process %s exists" % PROCESS_CODE)
    if proc:
        c(proc.status in ("Draft", "Active"), "status is Draft or Active")
        levels = frappe.get_all("EC Approval Level", filters={"approval_process": proc.name},
                                fields=["name", "level_no", "level_name"], order_by="level_no asc")
        c([l.level_no for l in levels] == [1], "exactly one approval level")
        c(bool(levels) and levels[0].level_name == "Direct Manager Review", "L1 Direct Manager Review")
        if levels:
            parts = frappe.get_all("EC Approval Participant",
                                   filters={"parent": levels[0].name, "participant_purpose": "Approver"},
                                   fields=["source_type", "reference_field", "fallback_user"])
            c(any(p.source_type == "Reference Employee Manager" and p.reference_field == MANAGER_FIELD
                  for p in parts), "L1 source Reference Employee Manager on %s" % MANAGER_FIELD)
            c(any(p.fallback_user for p in parts), "L1 has a configured fallback_user")
        ffs = frappe.get_all("EC Approval Participant",
                             filters={"parent": PROCESS_CODE, "parenttype": "EC Approval Process",
                                      "participant_purpose": "Fulfiller"}, pluck="user")
        c(bool(ffs), "at least one HR Fulfiller")
        for u in ffs:
            c(_active(u), "HR fulfiller %s active System User" % u)
        c(not frappe.get_all("EC Approval Process",
                             filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                      "process_code": ["!=", PROCESS_CODE]}),
          "no OTHER Active process for %s" % APPROVAL_TYPE)
    return {"ok": all(x["ok"] for x in checks), "checks": checks}


def _active(user):
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")
