# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for BUDGET_SETTING-V1 (Draft): sequential
L1 HOF Review -> L2 CEO Review (each one User approver, ordered). Identities are config seed args
(emails allowed here only). No Direct Manager level. No fulfillment; no SLA. dry-run default; apply=1."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.engine.user_rules import require_active_system_user

PROCESS_CODE = "BUDGET_SETTING-V1"
APPROVAL_TYPE = "BUDGET_SETTING"
DEFAULT_HOF = ["phuong.nguyen1@ecentric.vn"]
DEFAULT_CEO = ["lam.nguyen@ecentric.vn"]


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Budget Setting setup."), frappe.PermissionError)


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


def _validate(label, users, rep):
    if not users:
        rep["errors"].append("No %s users supplied." % label)
    for u in users:
        try:
            require_active_system_user(u, label)
        except Exception as e:
            rep["errors"].append("%s: %s" % (label, str(e)))


@frappe.whitelist()
def setup_budget_setting_v1(hof=None, ceo=None, dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    users = {1: _parse(hof, DEFAULT_HOF), 2: _parse(ceo, DEFAULT_CEO)}
    _validate("HOF", users[1], rep)
    _validate("CEO", users[2], rep)
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (run seed first)." % APPROVAL_TYPE)
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
    rep["planned"] = ["process %s (Draft), no SLA (v1)" % PROCESS_CODE,
                      "L1 HOF Review=%s" % users[1], "L2 CEO Review=%s" % users[2]]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (no writes)"
        return rep
    _upsert(users)
    frappe.db.commit()
    rep["result"] = "APPLIED (process Draft; card inactive)"
    return rep


def _upsert(users):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "Budget Setting V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.set("participants", [])
    proc.save(ignore_permissions=True)

    def _upsert_level(no, name, ulist):
        existing = frappe.get_all("EC Approval Level",
                                  filters={"approval_process": PROCESS_CODE, "level_no": no}, pluck="name")
        lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing else frappe.new_doc("EC Approval Level")
        lvl.approval_process = PROCESS_CODE
        lvl.level_no = no
        lvl.level_name = name
        lvl.mandatory = 1
        lvl.approval_mode = "Any One"
        lvl.minimum_approvals = 1
        lvl.allows_amount_adjustment = 0
        lvl.sla_policy = None
        lvl.set("participants", [])
        for i, u in enumerate(ulist or []):
            lvl.append("participants", {"participant_purpose": "Approver", "source_type": "User",
                                        "user": u, "sort_order": i})
        lvl.save(ignore_permissions=True)

    _upsert_level(1, "HOF Review", users[1])
    _upsert_level(2, "CEO Review", users[2])


@frappe.whitelist()
def validate_budget_setting_v1():
    proc = frappe.db.get_value("EC Approval Process", {"process_code": PROCESS_CODE},
                               ["name", "status"], as_dict=True)
    checks = []

    def c(cond, msg):
        checks.append({"check": msg, "ok": bool(cond)})

    c(bool(proc), "process %s exists" % PROCESS_CODE)
    if proc:
        c(proc.status in ("Draft", "Active"), "status Draft/Active")
        levels = frappe.get_all("EC Approval Level", filters={"approval_process": proc.name},
                                fields=["name", "level_no", "level_name"], order_by="level_no asc")
        c([l.level_no for l in levels] == [1, 2], "levels 1,2 present")
        names = {l.level_no: l.level_name for l in levels}
        c(names.get(1) == "HOF Review", "L1 HOF Review")
        c(names.get(2) == "CEO Review", "L2 CEO Review")
        for l in levels:
            us = frappe.get_all("EC Approval Participant",
                                filters={"parent": l.name, "participant_purpose": "Approver"}, pluck="user")
            c(bool(us) and len(us) == len(set(us)), "L%s approvers, no dup" % l.level_no)
            for u in us:
                c(_active(u), "L%s approver %s active" % (l.level_no, u))
        c(not frappe.get_all("EC Approval Process",
                             filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                      "process_code": ["!=", PROCESS_CODE]}), "no OTHER Active process")
    return {"ok": all(x["ok"] for x in checks), "checks": checks}


def _active(u):
    r = frappe.db.get_value("User", u, ["enabled", "user_type"], as_dict=True)
    return bool(r and r.enabled and r.user_type == "System User")
