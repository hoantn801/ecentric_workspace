# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for OFFER_REQUEST-V1 (Draft) - 28/09/2026.

L1 Line Manager Review  (Reference User Field `line_manager` - chep tu Hiring, nguoi gui khong chon)
L2 HR & CnB Review      (Role EC CnB)
L3 HOF Review           (Role EC HOF)
L4 CEO Review           (Role EC CEO)
Moi cap Any One. Hoan chot 28/09: "LM -> HR/CnB -> HOF -> CEO" (Excel de xuat them Lead HR, CnB,
HOF o giua de nam chi luong). Duyet xong: tu tao New Staff Preparation (handler, khong phai
fulfillment). dry-run default; apply=1 required. Never overwrites an Active process."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.workflow.participants import (
    CNB_ROLE, check_approver_parts, participant_rows, role_ref, validate_seed_entries)

PROCESS_CODE = "OFFER_REQUEST-V1"
APPROVAL_TYPE = "OFFER_REQUEST"
LM_FIELD = "line_manager"
DEFAULT_CNB = [role_ref(CNB_ROLE)]
DEFAULT_HOF = [role_ref("EC HOF")]
DEFAULT_CEO = [role_ref("EC CEO")]
LEVELS = ((1, "Line Manager Review"), (2, "HR & CnB Review"), (3, "HOF Review"), (4, "CEO Review"))


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Offer Request setup."), frappe.PermissionError)


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


@frappe.whitelist()
def setup_offer_request_v1(cnb=None, hof=None, ceo=None, dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    users = {2: _parse(cnb, DEFAULT_CNB), 3: _parse(hof, DEFAULT_HOF), 4: _parse(ceo, DEFAULT_CEO)}
    validate_seed_entries("HR & CnB", users[2], rep)
    validate_seed_entries("HOF", users[3], rep)
    validate_seed_entries("CEO", users[4], rep)
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (seed first)." % APPROVAL_TYPE)
    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["notes"].append("ALREADY_ACTIVE %s (left unchanged)" % PROCESS_CODE)
        rep["result"] = "ALREADY_ACTIVE"
        rep["blockers"] = rep["errors"]
        return rep
    rep["planned"] = [
        "process %s (Draft), no SLA (v1)" % PROCESS_CODE,
        "L1 Line Manager Review (Reference User Field on %s, Any One)" % LM_FIELD,
        "L2 HR & CnB Review (Any One)=%s" % users[2],
        "L3 HOF Review (Any One)=%s" % users[3],
        "L4 CEO Review (Any One)=%s" % users[4],
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
    rep["result"] = "APPLIED (process Draft)"
    return rep


def _upsert(users):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "Offer Request V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.set("participants", [])
    proc.save(ignore_permissions=True)
    for no, name in LEVELS:
        existing = frappe.get_all("EC Approval Level",
                                  filters={"approval_process": PROCESS_CODE, "level_no": no}, pluck="name")
        lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing else frappe.new_doc("EC Approval Level")
        lvl.approval_process = PROCESS_CODE
        lvl.level_no = no
        lvl.level_name = name
        lvl.mandatory = 1
        lvl.approval_mode = "Any One"
        lvl.minimum_approvals = 0
        lvl.allows_amount_adjustment = 0
        lvl.sla_policy = None
        lvl.set("participants", [])
        if no == 1:
            lvl.append("participants", {"participant_purpose": "Approver",
                                        "source_type": "Reference User Field",
                                        "reference_field": LM_FIELD, "sort_order": 0})
        else:
            for i, row in enumerate(participant_rows(users[no])):
                row.update({"participant_purpose": "Approver", "sort_order": i})
                lvl.append("participants", row)
        lvl.save(ignore_permissions=True)


@frappe.whitelist()
def validate_offer_request_v1():
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
        for no, nm in LEVELS:
            c(names.get(no) == nm, "L%s is %s" % (no, nm))
        for l in levels:
            parts = frappe.get_all("EC Approval Participant",
                                   filters={"parent": l.name, "participant_purpose": "Approver"},
                                   fields=["source_type", "reference_field", "user", "role"])
            if l.level_no == 1:
                c(any(p.source_type == "Reference User Field" and p.reference_field == LM_FIELD
                      for p in parts), "L1 Reference User Field on %s" % LM_FIELD)
            else:
                for ok, msg in check_approver_parts(parts, l.level_no):
                    c(ok, msg)
        c(not frappe.get_all("EC Approval Process",
                             filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                      "process_code": ["!=", PROCESS_CODE]}), "no OTHER Active process")
    return {"ok": all(x["ok"] for x in checks), "checks": checks}
