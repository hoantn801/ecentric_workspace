# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for the two Daily Target processes:
DAILY_TARGET_PROJECT-V1 (Commercial Manager) and DAILY_TARGET_CONSOLIDATED-V1 (CEO),
both under approval_type DAILY_TARGET. Approver identities are config-seed args
(emails allowed here only). dry-run default; apply=1 required. Never overwrites an
Active process (reports ALREADY_ACTIVE). Processes left Draft; catalog card inactive."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.engine.user_rules import require_active_system_user

APPROVAL_TYPE = "DAILY_TARGET"
PROCESS_PROJECT = "DAILY_TARGET_PROJECT-V1"
PROCESS_CONSOLIDATED = "DAILY_TARGET_CONSOLIDATED-V1"
DEFAULT_PROJECT_APPROVERS = ["linh.ngo@ecentric.vn"]        # Commercial Manager
DEFAULT_CONSOLIDATED_APPROVERS = ["lam.nguyen@ecentric.vn"]  # CEO


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Daily Target setup."), frappe.PermissionError)


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


def _upsert_single_level(code, title, level_name, approvers, rep):
    if frappe.db.get_value("EC Approval Process", code, "status") == "Active":
        rep["notes"].append("ALREADY_ACTIVE %s (left unchanged)" % code)
        return
    proc = frappe.get_doc("EC Approval Process", code) if frappe.db.exists(
        "EC Approval Process", code) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = code
    proc.title = title
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.set("participants", [])
    proc.save(ignore_permissions=True)
    existing = frappe.get_all("EC Approval Level",
                              filters={"approval_process": code, "level_no": 1}, pluck="name")
    lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing else frappe.new_doc("EC Approval Level")
    lvl.approval_process = code
    lvl.level_no = 1
    lvl.level_name = level_name
    lvl.mandatory = 1
    lvl.approval_mode = "Any One"
    lvl.minimum_approvals = 1
    lvl.allows_amount_adjustment = 0
    lvl.sla_policy = None
    lvl.set("participants", [])
    for i, u in enumerate(approvers or []):
        lvl.append("participants", {"participant_purpose": "Approver", "source_type": "User",
                                    "user": u, "sort_order": i})
    lvl.save(ignore_permissions=True)


@frappe.whitelist()
def setup_daily_target_v1(project_approvers=None, consolidated_approvers=None, dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    proj = _parse(project_approvers, DEFAULT_PROJECT_APPROVERS)
    cons = _parse(consolidated_approvers, DEFAULT_CONSOLIDATED_APPROVERS)
    _validate_users("Project Commercial Manager", proj, rep)
    _validate_users("Consolidated CEO", cons, rep)
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (run p002 seed first)." % APPROVAL_TYPE)
    rep["planned"] = [
        "%s (Draft): L1 Commercial Manager Review (Any One)=%s" % (PROCESS_PROJECT, proj),
        "%s (Draft): L1 CEO Review (Any One)=%s" % (PROCESS_CONSOLIDATED, cons),
    ]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (no writes)"
        return rep
    _upsert_single_level(PROCESS_PROJECT, "Daily Target Project V1", "Commercial Manager Review", proj, rep)
    _upsert_single_level(PROCESS_CONSOLIDATED, "Daily Target Consolidated V1", "CEO Review", cons, rep)
    frappe.db.commit()
    rep["result"] = "APPLIED (processes Draft; card inactive)" + (" | " + "; ".join(rep["notes"]) if rep["notes"] else "")
    return rep


@frappe.whitelist()
def validate_daily_target_v1():
    checks = []

    def c(cond, msg):
        checks.append({"check": msg, "ok": bool(cond)})

    for code, lname in ((PROCESS_PROJECT, "Commercial Manager Review"), (PROCESS_CONSOLIDATED, "CEO Review")):
        proc = frappe.db.get_value("EC Approval Process", code, ["name", "status", "approval_type"], as_dict=True)
        c(bool(proc), "process %s exists" % code)
        if proc:
            c(proc.status in ("Draft", "Active"), "%s status Draft/Active" % code)
            c(proc.approval_type == APPROVAL_TYPE, "%s approval_type DAILY_TARGET" % code)
            levels = frappe.get_all("EC Approval Level", filters={"approval_process": code},
                                    fields=["name", "level_no", "level_name"], order_by="level_no asc")
            c([l.level_no for l in levels] == [1], "%s has exactly one level" % code)
            c(bool(levels) and levels[0].level_name == lname, "%s L1 is %s" % (code, lname))
            for l in levels:
                users = frappe.get_all("EC Approval Participant",
                                       filters={"parent": l.name, "participant_purpose": "Approver"}, pluck="user")
                c(bool(users) and len(users) == len(set(users)), "%s approvers present, no dup" % code)
                for u in users:
                    c(_active(u), "%s approver %s active System User" % (code, u))
    # only the two known DAILY_TARGET processes may be Active (intentional pair)
    active = set(frappe.get_all("EC Approval Process",
                                filters={"approval_type": APPROVAL_TYPE, "status": "Active"}, pluck="name"))
    c(active.issubset({PROCESS_PROJECT, PROCESS_CONSOLIDATED}),
      "no unexpected Active DAILY_TARGET process")
    return {"ok": all(x["ok"] for x in checks), "checks": checks}


def _active(user):
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")
