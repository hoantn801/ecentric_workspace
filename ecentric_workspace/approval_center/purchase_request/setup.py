# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for PURCHASE_REQUEST-V1 (Draft): sequential
L1 Direct Manager Review (Requester Manager) -> L2 Finance Review -> L3 HOF Review -> L4 CEO Review
(each Any One / one approver, so ordered). Finance/HOF/CEO identities are config seed args (emails
allowed here only); L1 is dynamic. No fulfillment; no SLA. dry-run default; apply=1 required."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.engine.user_rules import require_active_system_user

PROCESS_CODE = "PURCHASE_REQUEST-V1"
APPROVAL_TYPE = "PURCHASE_REQUEST"
DEFAULT_FINANCE = ["lien.vu@ecentric.vn"]
DEFAULT_HOF = ["phuong.nguyen1@ecentric.vn"]
DEFAULT_CEO = ["lam.nguyen@ecentric.vn"]


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Purchase Request setup."), frappe.PermissionError)


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
def setup_purchase_request_v1(finance=None, hof=None, ceo=None, dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    users = {2: _parse(finance, DEFAULT_FINANCE), 3: _parse(hof, DEFAULT_HOF), 4: _parse(ceo, DEFAULT_CEO)}
    _validate("Finance", users[2], rep)
    _validate("HOF", users[3], rep)
    _validate("CEO", users[4], rep)
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
        "process %s (Draft), no SLA (v1)" % PROCESS_CODE,
        "L1 Direct Manager Review (Requester Manager)",
        "L2 Finance Review=%s" % users[2], "L3 HOF Review=%s" % users[3], "L4 CEO Review=%s" % users[4],
    ]
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
    proc.title = "Purchase Request V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.set("participants", [])
    proc.save(ignore_permissions=True)

    def _upsert_level(no, name, source, ulist):
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
        if source == "manager":
            lvl.append("participants", {"participant_purpose": "Approver",
                                        "source_type": "Requester Manager", "sort_order": 0})
        else:
            for i, u in enumerate(ulist or []):
                lvl.append("participants", {"participant_purpose": "Approver", "source_type": "User",
                                            "user": u, "sort_order": i})
        lvl.save(ignore_permissions=True)

    _upsert_level(1, "Direct Manager Review", "manager", None)
    _upsert_level(2, "Finance Review", "user", users[2])
    _upsert_level(3, "HOF Review", "user", users[3])
    _upsert_level(4, "CEO Review", "user", users[4])


@frappe.whitelist()
def validate_purchase_request_v1():
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
        c([l.level_no for l in levels] == [1, 2, 3, 4], "levels 1..4 present")
        names = {l.level_no: l.level_name for l in levels}
        for no, nm in [(1, "Direct Manager Review"), (2, "Finance Review"), (3, "HOF Review"), (4, "CEO Review")]:
            c(names.get(no) == nm, "L%s is %s" % (no, nm))
        for l in levels:
            parts = frappe.get_all("EC Approval Participant",
                                   filters={"parent": l.name, "participant_purpose": "Approver"},
                                   fields=["source_type", "user"])
            if l.level_no == 1:
                c(any(p.source_type == "Requester Manager" for p in parts), "L1 Requester Manager source")
            else:
                us = [p.user for p in parts if p.source_type == "User"]
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
