# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for ASSET_REQUEST-V1 (Draft):
L1 Direct Manager Review (Requester Manager, resolved at runtime from Employee.reports_to),
L2 Operation Review (Any One) + process Fulfillers (Operation). Operation/Fulfiller
identities are config seed args (emails allowed here only); L1 is fully dynamic.
dry-run default; apply=1 required. Process left Draft; catalog card inactive. No SLA."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.engine.user_rules import require_active_system_user

PROCESS_CODE = "ASSET_REQUEST-V1"
APPROVAL_TYPE = "ASSET_REQUEST"
DEFAULT_OPERATION = ["hoan.tran@ecentric.vn", "thuong.nguyen@ecentric.vn"]
DEFAULT_FULFILLERS = ["hoan.tran@ecentric.vn", "thuong.nguyen@ecentric.vn"]


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Asset Request setup."), frappe.PermissionError)


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
def setup_asset_request_v1(operation_reviewers=None, fulfillers=None, dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    op = _parse(operation_reviewers, DEFAULT_OPERATION)
    ff = _parse(fulfillers, DEFAULT_FULFILLERS)
    _validate_users("Operation Reviewer", op, rep)
    _validate_users("Asset Fulfiller", ff, rep)
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
        "L1 Direct Manager Review (Requester Manager, Any One)",
        "L2 Operation Review (Any One)=%s" % op,
        "process Fulfillers (Operation)=%s" % ff,
    ]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (no writes)"
        return rep
    _upsert_process(op, ff)
    frappe.db.commit()
    rep["result"] = "APPLIED (process Draft; card inactive)"
    return rep


def _upsert_process(op, ff):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "Asset Request V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.fulfillment_sla_policy = None
    _set_user_participants(proc, "Fulfiller", ff)
    proc.save(ignore_permissions=True)

    def _upsert_level(no, name, source, users):
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
        keep = [p for p in lvl.participants if p.participant_purpose != "Approver"]
        lvl.set("participants", keep)
        if source == "manager":
            lvl.append("participants", {"participant_purpose": "Approver",
                                        "source_type": "Requester Manager", "sort_order": 0})
        else:
            for i, u in enumerate(users or []):
                lvl.append("participants", {"participant_purpose": "Approver", "source_type": "User",
                                            "user": u, "sort_order": i})
        lvl.save(ignore_permissions=True)

    _upsert_level(1, "Direct Manager Review", "manager", None)
    _upsert_level(2, "Operation Review", "user", op)


@frappe.whitelist()
def validate_asset_request_v1():
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
        c([l.level_no for l in levels] == [1, 2], "levels 1,2 present in order")
        names = {l.level_no: l.level_name for l in levels}
        c(names.get(1) == "Direct Manager Review", "L1 Direct Manager Review")
        c(names.get(2) == "Operation Review", "L2 Operation Review")
        for l in levels:
            parts = frappe.get_all("EC Approval Participant",
                                   filters={"parent": l.name, "participant_purpose": "Approver"},
                                   fields=["source_type", "user"])
            if l.level_no == 1:
                c(any(p.source_type == "Requester Manager" for p in parts), "L1 Requester Manager source")
            else:
                users = [p.user for p in parts if p.source_type == "User"]
                c(bool(users) and len(users) == len(set(users)), "L2 reviewers present, no dup")
                for u in users:
                    c(_active(u), "L2 reviewer %s active System User" % u)
        ffs = frappe.get_all("EC Approval Participant",
                             filters={"parent": PROCESS_CODE, "parenttype": "EC Approval Process",
                                      "participant_purpose": "Fulfiller"}, pluck="user")
        c(bool(ffs), "at least one Fulfiller")
        for u in ffs:
            c(_active(u), "fulfiller %s active System User" % u)
        c(not frappe.get_all("EC Approval Process",
                             filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                      "process_code": ["!=", PROCESS_CODE]}),
          "no OTHER Active process for %s" % APPROVAL_TYPE)
    return {"ok": all(x["ok"] for x in checks), "checks": checks}


def _active(user):
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")
