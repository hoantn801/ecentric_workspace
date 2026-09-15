# Copyright (c) 2026, eCentric and contributors
"""Seed luong BOOKING_REQUEST-V1 (Draft), System-Manager only, dry-run mac dinh.

MOT cap duyet: L1 Account Lead = quan ly truc tiep cua nguoi gui (`Requester Manager`).
KHONG hardcode danh tinh ai ca - dung nguoi trong `Employee.reports_to`. Neu ve sau Hoan
muon Account Lead la MOT nguoi co dinh thi doi dong participant sang `source_type="User"`,
khong phai sua code.

Nguoi xu ly (Fulfiller) = Role EC Booking. Viec van di DICH DANH toi ban Booking phu trach
brand - phan do nam o service.on_final_approval; dong Role o day la QUYEN nhan viec, de nguoi
khac nhan ho duoc khi nguoi phu trach nghi."""
import json

import frappe
from frappe import _

PROCESS_CODE = "BOOKING_REQUEST-V1"
APPROVAL_TYPE = "BOOKING_REQUEST"
FULFILLER_ROLE = "EC Booking"


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Booking Request setup."), frappe.PermissionError)


@frappe.whitelist()
def setup_booking_request_v1(dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (chay patch seed truoc)." % APPROVAL_TYPE)
    if not frappe.db.exists("Role", FULFILLER_ROLE):
        rep["errors"].append("Role %s chua ton tai." % FULFILLER_ROLE)
    elif not frappe.db.exists("Has Role", {"role": FULFILLER_ROLE, "parenttype": "User"}):
        # CANH BAO chu khong CHAN: cau hinh luong va gan nguoi la hai viec, lam duoc roi
        # gan sau. Nhung phai noi ra, vi khong ai trong role thi luoi do khong do duoc gi.
        rep["warnings"].append("Chua ai duoc gan Role %s - luoi do se rong." % FULFILLER_ROLE)
    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["notes"].append("ALREADY_ACTIVE %s (khong doi gi)" % PROCESS_CODE)
        rep["result"] = "ALREADY_ACTIVE"
        rep["blockers"] = rep["errors"]
        return rep
    active = frappe.get_all("EC Approval Process",
                            filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                     "name": ["!=", PROCESS_CODE]}, pluck="name")
    if active:
        rep["warnings"].append("Da co luong Active khac cho %s: %s" % (APPROVAL_TYPE, active))
    rep["planned"] = [
        "process %s (Draft), khong SLA (v1)" % PROCESS_CODE,
        "L1 Account Lead Review (Requester Manager)",
        "Fulfiller = Role %s" % FULFILLER_ROLE,
    ]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (khong ghi gi)"
        return rep
    _upsert()
    frappe.db.commit()
    rep["result"] = "APPLIED (process Draft; the chua hien)"
    return rep


def _upsert():
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "Booking Request V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.set("participants", [])
    proc.append("participants", {"participant_purpose": "Fulfiller", "source_type": "Role",
                                 "role": FULFILLER_ROLE, "sort_order": 0})
    proc.save(ignore_permissions=True)

    existing = frappe.get_all("EC Approval Level",
                              filters={"approval_process": PROCESS_CODE, "level_no": 1},
                              pluck="name")
    lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing \
        else frappe.new_doc("EC Approval Level")
    lvl.approval_process = PROCESS_CODE
    lvl.level_no = 1
    lvl.level_name = "Account Lead Review"
    lvl.mandatory = 1
    lvl.approval_mode = "Any One"
    lvl.minimum_approvals = 1
    lvl.allows_amount_adjustment = 0
    lvl.sla_policy = None
    lvl.set("participants", [])
    lvl.append("participants", {"participant_purpose": "Approver",
                                "source_type": "Requester Manager", "sort_order": 0})
    lvl.save(ignore_permissions=True)


@frappe.whitelist()
def validate_booking_request_v1():
    _require_sm()
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    chk("approval_type", frappe.db.exists("EC Approval Type", APPROVAL_TYPE))
    chk("business_doctype", frappe.db.exists("DocType", "EC Booking Request"))
    proc = frappe.db.get_value("EC Approval Process", PROCESS_CODE, ["status"], as_dict=True)
    chk("process_exists", bool(proc), PROCESS_CODE)
    levels = frappe.get_all("EC Approval Level", filters={"approval_process": PROCESS_CODE},
                            fields=["level_no", "level_name"], order_by="level_no")
    chk("has_1_level", len(levels) == 1, json.dumps([l.level_name for l in levels]))
    if proc:
        fulfillers = frappe.get_all(
            "EC Approval Participant",
            filters={"parent": PROCESS_CODE, "participant_purpose": "Fulfiller"},
            fields=["source_type", "role"])
        chk("has_fulfiller_role",
            any(f.source_type == "Role" and f.role == FULFILLER_ROLE for f in fulfillers),
            json.dumps([dict(f) for f in fulfillers]))
    chk("role_has_members",
        bool(frappe.db.exists("Has Role", {"role": FULFILLER_ROLE, "parenttype": "User"})),
        "Role %s" % FULFILLER_ROLE)
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
