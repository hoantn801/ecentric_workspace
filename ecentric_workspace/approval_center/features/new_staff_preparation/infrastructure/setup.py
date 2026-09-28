# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for NEW_STAFF_PREPARATION-V1 (Draft) - 28/09/2026.

MOT cap "Chuẩn bị onboard", che do "Each Group" (moi nhom mot nguoi, cac nhom SONG SONG -
Hoan chot 28/09). Moi dong Approver la MOT nhom; ten nhom (group_label) hien tren phieu:
  Lead HR    = User tuan.ly            (trong PA cu: Tuan Ly)
  HOF        = Role EC HOF             (Phuong Nguyen)
  CnB        = Role EC CnB Payroll     (tai khoan CnB ECENTRIC)
  Operation  = Role EC Ops System      (Dong Diep)
Moi nhom nhan DUNG MOT muc (mot user hoac mot role): muon nhom co nhieu nguoi thi dung role.
Seed args cho phep doi (email hoac "role:<Role>"). dry-run default; apply=1 required. Never
overwrites an Active process."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.workflow.participants import (
    check_approver_parts, participant_rows, role_ref, validate_seed_entries)

PROCESS_CODE = "NEW_STAFF_PREPARATION-V1"
APPROVAL_TYPE = "NEW_STAFF_PREPARATION"
LEVEL_NAME = "Chuẩn bị onboard"
GROUPS = (("Lead HR", "lead_hr", ["tuan.ly@ecentric.vn"]),
          ("HOF", "hof", [role_ref("EC HOF")]),
          ("CnB", "cnb", [role_ref("EC CnB Payroll")]),
          ("Operation", "operation", [role_ref("EC Ops System")]))


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run New Staff Preparation setup."),
                     frappe.PermissionError)


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


@frappe.whitelist()
def setup_new_staff_preparation_v1(lead_hr=None, hof=None, cnb=None, operation=None,
                                   dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    args = {"lead_hr": lead_hr, "hof": hof, "cnb": cnb, "operation": operation}
    groups = []
    for label, key, default in GROUPS:
        entries = _parse(args[key], default)
        if len(entries) != 1:
            rep["errors"].append("Nhom %s phai co DUNG MOT muc (user hoac role:<Role>), dang co %d."
                                 % (label, len(entries)))
        validate_seed_entries(label, entries, rep)
        groups.append((label, entries))
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (seed first)." % APPROVAL_TYPE)
    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["notes"].append("ALREADY_ACTIVE %s (left unchanged)" % PROCESS_CODE)
        rep["result"] = "ALREADY_ACTIVE"
        rep["blockers"] = rep["errors"]
        return rep
    rep["planned"] = ["process %s (Draft)" % PROCESS_CODE,
                      "L1 %s (Each Group): %s" % (LEVEL_NAME, groups)]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (no writes)"
        return rep
    _upsert(groups)
    frappe.db.commit()
    rep["result"] = "APPLIED (process Draft)"
    return rep


def _upsert(groups):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "New Staff Preparation V1"
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
    for i, (label, entries) in enumerate(groups):
        row = participant_rows(entries)[0]
        row.update({"participant_purpose": "Approver", "group_label": label, "sort_order": i})
        lvl.append("participants", row)
    lvl.save(ignore_permissions=True)


@frappe.whitelist()
def validate_new_staff_preparation_v1():
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
                                   fields=["source_type", "user", "role", "group_label"])
            labels = [p.group_label for p in parts]
            c(len(parts) >= 2 and all(labels) and len(labels) == len(set(labels)),
              "moi nhom co ten rieng, >= 2 nhom")
            # Moi nhom phai co nguoi THAT: nhom rong se chan gui phieu (engine fail-closed).
            for p in parts:
                for ok, msg in check_approver_parts([p], l.level_no):
                    c(ok, "%s: %s" % (p.group_label, msg))
        c(not frappe.get_all("EC Approval Process",
                             filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                      "process_code": ["!=", PROCESS_CODE]}), "no OTHER Active process")
    return {"ok": all(x["ok"] for x in checks), "checks": checks}
