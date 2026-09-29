# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for CLEARANCE_REQUEST-V1 (Draft) - 29/09/2026.

MOT cap "Bàn giao nghỉ việc", che do "Each Group" (cac nhom SONG SONG, moi nhom mot nguoi
xac nhan - file Excel sheet Clearance Request). Moi dong Approver la MOT nhom:
  Line Manager = quan ly truc tiep (Employee.reports_to) cua nguoi nghi viec - doc tu truong
                 employee_email cua phieu; khong co quan ly thi fallback Lead HR
  Operation    = Role EC Ops System
  HR           = User tuan.ly (Lead HR - cung cach New Staff Preparation)
  HOF          = Role EC HOF
Seed args doi duoc (email hoac "role:<Role>") cho Operation / HR / HOF; line_manager_fallback
la email. dry-run default; apply=1 required. Never overwrites an Active process."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.workflow.participants import (
    check_approver_parts, participant_rows, role_ref, validate_seed_entries)

PROCESS_CODE = "CLEARANCE_REQUEST-V1"
APPROVAL_TYPE = "CLEARANCE_REQUEST"
LEVEL_NAME = "Bàn giao nghỉ việc"
LM_LABEL = "Line Manager"
LM_FIELD = "employee_email"
LM_FALLBACK = "tuan.ly@ecentric.vn"
GROUPS = (("Operation", "operation", [role_ref("EC Ops System")]),
          ("HR", "hr", ["tuan.ly@ecentric.vn"]),
          ("HOF", "hof", [role_ref("EC HOF")]))


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Clearance Request setup."),
                     frappe.PermissionError)


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


@frappe.whitelist()
def setup_clearance_request_v1(operation=None, hr=None, hof=None, line_manager_fallback=None,
                               dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    args = {"operation": operation, "hr": hr, "hof": hof}
    groups = []
    for label, key, default in GROUPS:
        entries = _parse(args[key], default)
        if len(entries) != 1:
            rep["errors"].append("Nhom %s phai co DUNG MOT muc (user hoac role:<Role>), dang co %d."
                                 % (label, len(entries)))
        validate_seed_entries(label, entries, rep)
        groups.append((label, entries))
    fb = (line_manager_fallback or LM_FALLBACK).strip()
    validate_seed_entries("Line Manager fallback", [fb], rep)
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (seed first)." % APPROVAL_TYPE)
    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["notes"].append("ALREADY_ACTIVE %s (left unchanged)" % PROCESS_CODE)
        rep["result"] = "ALREADY_ACTIVE"
        rep["blockers"] = rep["errors"]
        return rep
    rep["planned"] = ["process %s (Draft)" % PROCESS_CODE,
                      "L1 %s (Each Group): Line Manager (reports_to, fallback %s) + %s"
                      % (LEVEL_NAME, fb, groups)]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (no writes)"
        return rep
    _upsert(groups, fb)
    frappe.db.commit()
    rep["result"] = "APPLIED (process Draft)"
    return rep


def _upsert(groups, fb):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "Clearance Request V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.set("participants", [])
    proc.save(ignore_permissions=True)
    existing = frappe.get_all("EC Approval Level",
                              filters={"approval_process": PROCESS_CODE, "level_no": 1}, pluck="name")
    lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing else frappe.new_doc("EC Approval Level")
    lvl.approval_process = PROCESS_CODE
    lvl.level_no = 1
    lvl.level_name = LEVEL_NAME
    lvl.mandatory = 1
    lvl.approval_mode = "Each Group"
    lvl.minimum_approvals = 0
    lvl.allows_amount_adjustment = 0
    lvl.sla_policy = None
    lvl.set("participants", [])
    lvl.append("participants", {"participant_purpose": "Approver", "group_label": LM_LABEL,
                                "source_type": "Reference Employee Manager",
                                "reference_field": LM_FIELD, "fallback_user": fb, "sort_order": 0})
    for i, (label, entries) in enumerate(groups):
        row = participant_rows(entries)[0]
        row.update({"participant_purpose": "Approver", "group_label": label, "sort_order": i + 1})
        lvl.append("participants", row)
    lvl.save(ignore_permissions=True)


@frappe.whitelist()
def validate_clearance_request_v1():
    proc = frappe.db.get_value("EC Approval Process", {"process_code": PROCESS_CODE},
                               ["name", "status"], as_dict=True)
    checks = []

    def c(cond, msg):
        checks.append({"check": msg, "ok": bool(cond)})

    c(bool(proc), "process %s exists" % PROCESS_CODE)
    if proc:
        c(proc.status in ("Draft", "Active"), "status Draft/Active")
        levels = frappe.get_all("EC Approval Level", filters={"approval_process": proc.name},
                                fields=["name", "level_no", "level_name", "approval_mode"],
                                order_by="level_no asc")
        c([l.level_no for l in levels] == [1], "exactly one level")
        c(bool(levels) and levels[0].approval_mode == "Each Group", "L1 Each Group")
        for l in levels:
            parts = frappe.get_all("EC Approval Participant",
                                   filters={"parent": l.name, "participant_purpose": "Approver"},
                                   fields=["source_type", "user", "role", "group_label",
                                           "reference_field", "fallback_user"])
            labels = [p.group_label for p in parts]
            c(len(parts) >= 2 and all(labels) and len(labels) == len(set(labels)),
              "moi nhom co ten rieng, >= 2 nhom")
            lm = [p for p in parts if p.source_type == "Reference Employee Manager"]
            c(len(lm) == 1 and lm[0].reference_field == LM_FIELD, "nhom Line Manager doc %s" % LM_FIELD)
            for p in lm:
                for ok, msg in check_approver_parts([frappe._dict(source_type="User", user=p.fallback_user)],
                                                    l.level_no):
                    c(ok, "Line Manager fallback: %s" % msg)
            for p in parts:
                if p.source_type in ("User", "Role"):
                    for ok, msg in check_approver_parts([p], l.level_no):
                        c(ok, "%s: %s" % (p.group_label, msg))
        c(not frappe.get_all("EC Approval Process",
                             filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                      "process_code": ["!=", PROCESS_CODE]}), "no OTHER Active process")
    return {"ok": all(x["ok"] for x in checks), "checks": checks}
