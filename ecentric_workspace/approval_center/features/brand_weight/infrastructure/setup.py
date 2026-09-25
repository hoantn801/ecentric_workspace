# Copyright (c) 2026, eCentric and contributors
"""Setup idempotent cho BRAND_WEIGHT-V1: hai cap, ca hai mandatory=0.

Vi sao mandatory=0: engine chi cho bo cap KHONG mandatory (submit(skip_level_nos)).
Hai luat bo cap o application/routing.py - CEO khong co lead, va truong phong tu nop -
se nem loi 'Level is mandatory and cannot be skipped' neu de mandatory=1. Viec bo cap
van duoc ghi audit kem skip_reason, nen mandatory=0 KHONG co nghia la bo tuy tien.

Nguoi duyet resolve luc chay, khong hardcode ai: cap 1 tu Employee.reports_to,
cap 2 tu Department cua nguoi nop. Non-destructive, chay lai nhieu lan an toan."""
import frappe
from frappe import _

APPROVAL_TYPE = "BRAND_WEIGHT"
PROCESS_CODE = "BRAND_WEIGHT-V1"
LEVELS = (
    (1, "Direct Lead", "Requester Manager"),
    (2, "Department Manager Review", "Department Manager"),
)


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Brand Weight setup."),
                     frappe.PermissionError)


@frappe.whitelist()
def setup_brand_weight_v1(apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    steps = []

    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        return {"mode": "dry_run" if dry else "apply", "ok": False,
                "steps": ["[ERR] EC Approval Type %s chua ton tai" % APPROVAL_TYPE]}

    proc = frappe.db.get_value("EC Approval Process", {"process_code": PROCESS_CODE}, "name")
    if proc:
        steps.append("[OK] process %s da ton tai (khong sua)" % PROCESS_CODE)
    else:
        steps.append("[NEW] tao process %s (status Draft)" % PROCESS_CODE)
        if not dry:
            p = frappe.get_doc({
                "doctype": "EC Approval Process", "process_code": PROCESS_CODE,
                "title": "Brand Weight V1", "approval_type": APPROVAL_TYPE,
                "version_no": 1, "status": "Draft",
            }).insert(ignore_permissions=True)
            proc = p.name

    for no, name, source in LEVELS:
        if proc and frappe.db.exists("EC Approval Level",
                                     {"approval_process": proc, "level_no": no}):
            steps.append("[OK] cap %d (%s) da ton tai" % (no, name))
            continue
        steps.append("[NEW] tao cap %d %s <- %s (mandatory=0)" % (no, name, source))
        if not dry and proc:
            lvl = frappe.get_doc({
                "doctype": "EC Approval Level", "approval_process": proc, "level_no": no,
                "level_name": name, "mandatory": 0, "approval_mode": "Any One",
                "minimum_approvals": 1, "allows_amount_adjustment": 0,
            })
            lvl.append("participants", {"participant_purpose": "Approver",
                                        "source_type": source, "sort_order": 1})
            lvl.insert(ignore_permissions=True)
    return {"mode": "dry_run" if dry else "apply", "ok": True, "steps": steps}


@frappe.whitelist()
def validate_brand_weight_v1():
    proc = frappe.db.get_value("EC Approval Process", {"process_code": PROCESS_CODE},
                               ["name", "status"], as_dict=True)
    checks = [{"check": "process ton tai", "ok": bool(proc)}]
    if proc:
        checks.append({"check": "status Draft hoac Active",
                       "ok": proc.status in ("Draft", "Active")})
        levels = frappe.get_all("EC Approval Level", filters={"approval_process": proc.name},
                                fields=["level_no", "level_name", "mandatory"],
                                order_by="level_no asc")
        checks.append({"check": "dung 2 cap 1..2",
                       "ok": [l.level_no for l in levels] == [1, 2]})
        checks.append({"check": "ca hai cap mandatory=0 (de bo duoc cap)",
                       "ok": all(not l.mandatory for l in levels)})
        others = frappe.get_all("EC Approval Process",
                                filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                         "process_code": ["!=", PROCESS_CODE]}, pluck="name")
        checks.append({"check": "khong co process Active khac cho %s" % APPROVAL_TYPE,
                       "ok": not others})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
