# Copyright (c) 2026, eCentric and contributors
"""Seed luong DISCIPLINE_DECISION-V1 (Draft), System-Manager only, dry-run mac dinh.

MOT cap: "CEO ký quyết định" - Role lay tu EC Discipline Settings.signer_role (mac dinh EC CEO).
Noi quy uy quyen nguoi khac ky: doi signer_role trong Settings roi dung luong V2 (khong sua V1
dang chay - phieu dang cho giu snapshot cu). Khong hardcode danh tinh ai.
Khong SLA engine o v1: han "CEO ky trong 2 ngay LV sau hop" nam tren ho so (ceo_due) va job
hr/ky_luat nhac. Ky so: cau hinh EC Digital Signature Profile cho cap nay (khong code)."""
import json

import frappe
from frappe import _

PROCESS_CODE = "DISCIPLINE_DECISION-V1"
APPROVAL_TYPE = "DISCIPLINE_DECISION"
BUSINESS_DT = "EC Discipline Decision Request"
SETTINGS = "EC Discipline Settings"
DEFAULT_ROLE = "EC CEO"
LEVEL_NAME = "CEO ký quyết định"


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Discipline Decision setup."), frappe.PermissionError)


def signer_role():
    try:
        return frappe.db.get_single_value(SETTINGS, "signer_role") or DEFAULT_ROLE
    except Exception:
        return DEFAULT_ROLE


@frappe.whitelist()
def setup_discipline_decision_v1(dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    role = signer_role()
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (chay patch seed truoc)." % APPROVAL_TYPE)
    if not frappe.db.exists("Role", role):
        rep["errors"].append("Role %s chua ton tai." % role)
    elif not frappe.db.exists("Has Role", {"role": role, "parenttype": "User"}):
        rep["warnings"].append("Chua ai duoc gan Role %s - cap ky se khong co nguoi." % role)
    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["notes"].append("ALREADY_ACTIVE %s (khong doi gi)" % PROCESS_CODE)
        rep["result"] = "ALREADY_ACTIVE"
        rep["blockers"] = rep["errors"]
        return rep
    rep["planned"] = ["process %s (Draft), khong SLA engine (v1)" % PROCESS_CODE,
                      "L1 %s (Role %s, Any One)" % (LEVEL_NAME, role)]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (khong ghi gi)"
        return rep
    _upsert(role)
    frappe.db.commit()
    rep["result"] = "APPLIED (process Draft)"
    return rep


def _upsert(role):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "Discipline Decision V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.set("participants", [])
    proc.save(ignore_permissions=True)
    existing = frappe.get_all("EC Approval Level", filters={"approval_process": PROCESS_CODE, "level_no": 1},
                              pluck="name")
    lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing else frappe.new_doc("EC Approval Level")
    lvl.approval_process = PROCESS_CODE
    lvl.level_no = 1
    lvl.level_name = LEVEL_NAME
    lvl.mandatory = 1
    lvl.approval_mode = "Any One"
    lvl.minimum_approvals = 1
    lvl.allows_amount_adjustment = 0
    lvl.sla_policy = None
    lvl.set("participants", [])
    lvl.append("participants", {"participant_purpose": "Approver", "source_type": "Role", "role": role,
                                "sort_order": 0})
    lvl.save(ignore_permissions=True)


@frappe.whitelist()
def validate_discipline_decision_v1():
    _require_sm()
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    role = signer_role()
    chk("approval_type", frappe.db.exists("EC Approval Type", APPROVAL_TYPE))
    chk("business_doctype", frappe.db.exists("DocType", BUSINESS_DT))
    chk("process_exists", frappe.db.exists("EC Approval Process", PROCESS_CODE), PROCESS_CODE)
    levels = frappe.get_all("EC Approval Level", filters={"approval_process": PROCESS_CODE},
                            fields=["level_no", "level_name"], order_by="level_no")
    chk("has_1_level", len(levels) == 1, json.dumps([l.level_name for l in levels]))
    chk("role_exists", frappe.db.exists("Role", role), role)
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
