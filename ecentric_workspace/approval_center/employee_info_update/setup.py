# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for EMPLOYEE_INFO_UPDATE-V1 (Draft): one fixed-participant
level "HR Review" (Any One, min 1). Also upserts the EC Approval Type catalog card
as **Coming Soon** (never Active). Approver identities are config seed INPUTS - never
hardcoded in engine runtime logic. dry-run by default; apply=1 required. Non-destructive."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.engine.user_rules import require_active_system_user

PROCESS_CODE = "EMPLOYEE_INFO_UPDATE-V1"
APPROVAL_TYPE = "EMPLOYEE_INFO_UPDATE"
CATEGORY = "ADMINISTRATION"
CARD_TITLE = "Employee information update"
DESCRIPTION = "Request to update employee information"
PROC_TITLE = "Employee Information Update V1"
LEVEL_NAME = "HR Review"
DEFAULT_APPROVERS = ["tuan.ly@ecentric.vn"]


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Employee information update setup."), frappe.PermissionError)


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


def _set_participants(doc, purpose, users):
    keep = [p for p in doc.participants if p.participant_purpose != purpose]
    doc.set("participants", keep)
    for i, u in enumerate(users or []):
        doc.append("participants", {"participant_purpose": purpose, "source_type": "User",
                                    "user": u, "sort_order": i})


def _upsert_type():
    """Create the catalog card as Coming Soon if missing. Never flips an existing card to Active."""
    if frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        return "exists"
    doc = frappe.new_doc("EC Approval Type")
    doc.approval_code = APPROVAL_TYPE
    doc.approval_title = CARD_TITLE
    if frappe.db.exists("EC Approval Category", CATEGORY):
        doc.category = CATEGORY
    doc.description = DESCRIPTION
    doc.card_status = "Coming Soon"
    doc.process_status = "UAT"
    doc.visibility_mode = "All Internal Users"
    doc.route = ""
    doc.insert(ignore_permissions=True)
    return "created"


@frappe.whitelist()
def setup_employee_info_update_v1(review_approvers=None, dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [], "result": None}
    rev = _parse(review_approvers, DEFAULT_APPROVERS)
    _validate_users("HR Review Approver", rev, rep)

    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["errors"].append("%s is Active; setup refuses to overwrite an Active process." % PROCESS_CODE)
    active = frappe.get_all("EC Approval Process",
                            filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                     "name": ["!=", PROCESS_CODE]}, pluck="name")
    if active:
        rep["warnings"].append("Another Active process exists for %s: %s" % (APPROVAL_TYPE, active))

    rep["planned"] = [
        "catalog card %s (Coming Soon, category %s)" % (APPROVAL_TYPE, CATEGORY),
        "process %s (Draft)" % PROCESS_CODE,
        "L1 %s (Any One) approvers=%s" % (LEVEL_NAME, rev),
    ]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (no writes)"
        return rep

    rep["type"] = _upsert_type()
    _upsert_process(rev)
    frappe.db.commit()
    rep["result"] = "APPLIED (process Draft; card Coming Soon)"
    return rep


def _upsert_process(rev):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = PROC_TITLE
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.fulfillment_sla_policy = None
    proc.save(ignore_permissions=True)

    existing = frappe.get_all("EC Approval Level",
                              filters={"approval_process": PROCESS_CODE, "level_no": 1}, pluck="name")
    lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing else frappe.new_doc("EC Approval Level")
    lvl.approval_process = PROCESS_CODE
    lvl.level_no = 1
    lvl.level_name = LEVEL_NAME
    lvl.mandatory = 1
    lvl.approval_mode = "Any One"
    lvl.minimum_approvals = 1
    lvl.allows_amount_adjustment = 0
    lvl.sla_policy = None
    _set_participants(lvl, "Approver", rev)
    lvl.save(ignore_permissions=True)


@frappe.whitelist()
def validate_employee_info_update_v1():
    proc = frappe.db.get_value("EC Approval Process", {"process_code": PROCESS_CODE},
                               ["name", "status"], as_dict=True)
    checks = []

    def c(cond, msg):
        checks.append({"check": msg, "ok": bool(cond)})

    c(frappe.db.exists("EC Approval Type", APPROVAL_TYPE), "catalog card %s exists" % APPROVAL_TYPE)
    c(bool(proc), "process %s exists" % PROCESS_CODE)
    if proc:
        c(proc.status in ("Draft", "Active"), "status is Draft or Active")
        levels = frappe.get_all("EC Approval Level", filters={"approval_process": proc.name},
                                fields=["level_no", "level_name", "approval_mode"], order_by="level_no asc")
        c([l.level_no for l in levels] == [1], "exactly one level")
        c(bool(levels) and levels[0].level_name == LEVEL_NAME and levels[0].approval_mode == "Any One",
          "L1 %s Any One" % LEVEL_NAME)
        for l in frappe.get_all("EC Approval Level", filters={"approval_process": proc.name}, pluck="name"):
            users = frappe.get_all("EC Approval Participant",
                                   filters={"parent": l, "participant_purpose": "Approver"}, pluck="user")
            c(bool(users) and len(users) == len(set(users)), "approvers present, no duplicates")
            for u in users:
                c(_active(u), "approver %s active System User" % u)
        c(not frappe.get_all("EC Approval Process",
                             filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                      "process_code": ["!=", PROCESS_CODE]}),
          "no OTHER Active process for %s" % APPROVAL_TYPE)
    return {"ok": all(x["ok"] for x in checks), "checks": checks}


def _active(user):
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")
