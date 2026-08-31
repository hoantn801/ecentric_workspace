# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for CONTRACT_REVIEW-V1 (Draft).

Hoàn chốt 2026-09-01:
L1 Trưởng phòng — động theo field `department` trên form (Reference Department Head;
   không dùng Requester Manager vì Sale admin có thể tạo giúp phòng ban khác),
L2 Finance Team — theo ROLE trên ERP (mặc định 'EC Finance'), Any One,
L3 Head of Finance — phuong.nguyen1, L4 CEO — lam.nguyen.
L4 để mandatory=0 vì hợp đồng sẵn-có-chỉ-điều-chỉnh được bỏ cấp CEO (engine chặn
bỏ cấp mandatory). Identities là seed args, không hardcode runtime. dry-run mặc định;
process để Draft, card inactive."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.workflow.user_rules import require_active_system_user

PROCESS_CODE = "CONTRACT_REVIEW-V1"
APPROVAL_TYPE = "CONTRACT_REVIEW"
DEPARTMENT_FIELD = "department"
DEFAULT_FINANCE_ROLE = "EC Finance"
DEFAULT_HOF = ["phuong.nguyen1@ecentric.vn"]
DEFAULT_CEO = ["lam.nguyen@ecentric.vn"]


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Contract Review setup."), frappe.PermissionError)


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


@frappe.whitelist()
def setup_contract_review_v1(finance_role=None, hof_reviewers=None, ceo_reviewers=None,
                             dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [],
           "warnings": [], "result": None}
    role = (finance_role or DEFAULT_FINANCE_ROLE).strip()
    hof = _parse(hof_reviewers, DEFAULT_HOF)
    ceo = _parse(ceo_reviewers, DEFAULT_CEO)
    _validate_users("Head of Finance", hof, rep)
    _validate_users("CEO", ceo, rep)
    if not frappe.db.exists("Role", role):
        rep["errors"].append("Role %s does not exist." % role)
    elif not frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, limit=1):
        rep["warnings"].append("Role %s has no users yet - L2 will block submit until it does." % role)
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (run seed patch first)." % APPROVAL_TYPE)
    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["errors"].append("%s is Active; setup refuses to overwrite an Active process." % PROCESS_CODE)

    rep["planned"] = [
        "process %s (Draft), no SLA policy (deadline tự tính ở service)" % PROCESS_CODE,
        "L1 Department Manager Review (Reference Department Head from %s, Any One)" % DEPARTMENT_FIELD,
        "L2 Finance Team Review (Role %s, Any One)" % role,
        "L3 Head of Finance Review (Any One)=%s" % hof,
        "L4 CEO Review (Any One, NOT mandatory - skippable for adjustments)=%s" % ceo,
    ]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (no writes)"
        return rep

    _upsert_process(role, hof, ceo)
    frappe.db.commit()
    rep["result"] = "APPLIED (process left Draft; card inactive)"
    return rep


def _upsert_process(role, hof, ceo):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "Contract Review V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.fulfillment_sla_policy = None
    proc.save(ignore_permissions=True)

    def _upsert_level(no, name, participants_rows, mandatory=1):
        existing = frappe.get_all("EC Approval Level",
                                  filters={"approval_process": PROCESS_CODE, "level_no": no},
                                  pluck="name")
        lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing \
            else frappe.new_doc("EC Approval Level")
        lvl.approval_process = PROCESS_CODE
        lvl.level_no = no
        lvl.level_name = name
        lvl.mandatory = mandatory
        lvl.approval_mode = "Any One"
        lvl.minimum_approvals = 1
        lvl.allows_amount_adjustment = 0
        lvl.sla_policy = None
        keep = [p for p in lvl.participants if p.participant_purpose != "Approver"]
        lvl.set("participants", keep)
        for i, row in enumerate(participants_rows):
            row = dict(row)
            row.update({"participant_purpose": "Approver", "sort_order": i})
            lvl.append("participants", row)
        lvl.save(ignore_permissions=True)

    _upsert_level(1, "Department Manager Review",
                  [{"source_type": "Reference Department Head", "department_field": DEPARTMENT_FIELD}])
    _upsert_level(2, "Finance Team Review", [{"source_type": "Role", "role": role}])
    _upsert_level(3, "Head of Finance Review",
                  [{"source_type": "User", "user": u} for u in hof])
    _upsert_level(4, "CEO Review",
                  [{"source_type": "User", "user": u} for u in ceo], mandatory=0)


@frappe.whitelist()
def validate_contract_review_v1():
    _require_sm()
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    chk("approval_type", frappe.db.exists("EC Approval Type", APPROVAL_TYPE))
    proc = frappe.db.get_value("EC Approval Process", PROCESS_CODE, ["status"], as_dict=True)
    chk("process_exists", bool(proc), PROCESS_CODE)
    levels = frappe.get_all("EC Approval Level", filters={"approval_process": PROCESS_CODE},
                            fields=["level_no", "level_name", "mandatory"], order_by="level_no")
    chk("has_4_levels", len(levels) == 4, json.dumps([l.level_name for l in levels]))
    chk("ceo_level_not_mandatory",
        any(l.level_no == 4 and not l.mandatory for l in levels),
        "L4 must be skippable for adjustment-only requests")
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
