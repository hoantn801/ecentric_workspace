# Copyright (c) 2026, eCentric and contributors
"""Seed luong ADHOC_APPROVAL-V1 (Draft) - Phe duyet dot xuat gui CEO. System-Manager only,
dry-run mac dinh. KHONG ghi de process Active.

MOT cap: "CEO duyệt" = Role EC CEO (Any One). Khong ten ai trong code - doi nguoi duyet thi doi
nguoi giu role / doi dong participant.
SLA (lich lam viec EC_STANDARD_9_18 = 8 gio/ngay): Binh thuong 2 ngay lam viec = 16 gio lam viec
(policy cua cap); Gap 4 gio lam viec (service truyen sla_overrides khi gui).
Khong tim duoc Holiday List cho tinh gio lam viec -> policy de gio LICH (48h / 4h) + canh bao, de
viec gui phieu khong bao gio bi chan vi thieu lich nghi."""
import json

import frappe
from frappe import _

PROCESS_CODE = "ADHOC_APPROVAL-V1"
APPROVAL_TYPE = "ADHOC_APPROVAL"
CEO_ROLE = "EC CEO"
CALENDAR_CODE = "EC_STANDARD_9_18"
POLICIES = {   # code -> (nhan, gio lam viec, gio lich khi khong co lich nghi)
    "ADHOC_APPROVAL_NORMAL_2D": ("Phê duyệt đột xuất - Bình thường 2 ngày làm việc", 16, 48),
    "ADHOC_APPROVAL_URGENT_4H": ("Phê duyệt đột xuất - Gấp 4 giờ làm việc", 4, 4),
}
NORMAL_POLICY = "ADHOC_APPROVAL_NORMAL_2D"
_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Adhoc Approval setup."), frappe.PermissionError)


def _holiday_list():
    try:
        company = frappe.defaults.get_global_default("company")
        if company and frappe.db.has_column("Company", "default_holiday_list"):
            return frappe.db.get_value("Company", company, "default_holiday_list")
    except Exception:
        return None
    return None


@frappe.whitelist()
def setup_adhoc_approval_v1(dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [],
           "notes": [], "result": None}
    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (chay patch seed truoc)." % APPROVAL_TYPE)
    if not frappe.db.exists("Role", CEO_ROLE):
        rep["errors"].append("Role %s chua ton tai." % CEO_ROLE)
    elif not frappe.db.exists("Has Role", {"role": CEO_ROLE, "parenttype": "User"}):
        rep["warnings"].append("Chua ai giu Role %s - cap CEO se khong co nguoi duyet." % CEO_ROLE)
    hl = _holiday_list()
    if not hl:
        rep["warnings"].append("Khong tim duoc Holiday List mac dinh - SLA tinh theo gio lich.")
    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["notes"].append("ALREADY_ACTIVE %s (khong doi gi)" % PROCESS_CODE)
        rep["result"] = "ALREADY_ACTIVE"
        rep["blockers"] = rep["errors"]
        return rep
    rep["planned"] = [
        "SLA %s" % ", ".join(POLICIES),
        "process %s (Draft)" % PROCESS_CODE,
        "L1 CEO duyệt (Role %s, Any One, SLA %s)" % (CEO_ROLE, NORMAL_POLICY),
    ]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (khong ghi gi)"
        return rep
    _ensure_calendar()
    _upsert_policies(hl)
    _upsert_process()
    frappe.db.commit()
    rep["result"] = "APPLIED (process Draft)"
    return rep


def _ensure_calendar():
    """Chi TAO khi chua co - lich chung dang dung cho form khac thi khong dung toi."""
    if frappe.db.exists("EC Approval Business Calendar", CALENDAR_CODE):
        return
    cal = frappe.new_doc("EC Approval Business Calendar")
    cal.calendar_code = CALENDAR_CODE
    cal.calendar_name = "eCentric Standard Working Calendar"
    cal.active = 1
    for d in _WEEK:
        cal.append("working_periods", {"weekday": d, "start_time": "09:00:00", "end_time": "12:00:00"})
        cal.append("working_periods", {"weekday": d, "start_time": "13:00:00", "end_time": "18:00:00"})
    cal.insert(ignore_permissions=True)


def _upsert_policies(holiday_list):
    for code, (label, biz_hours, cal_hours) in POLICIES.items():
        pol = frappe.get_doc("EC Approval SLA Policy", code) if frappe.db.exists(
            "EC Approval SLA Policy", code) else frappe.new_doc("EC Approval SLA Policy")
        if not pol.policy_code:
            pol.policy_code = code
        pol.policy_name = label
        pol.active = 1
        if holiday_list:
            pol.use_business_hours = 1
            pol.duration_hours = biz_hours
            pol.business_calendar = CALENDAR_CODE
            pol.holiday_list = holiday_list
        else:
            pol.use_business_hours = 0
            pol.duration_hours = cal_hours
        pol.save(ignore_permissions=True)


def _upsert_process():
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "Phê duyệt đột xuất V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.set("participants", [])
    proc.save(ignore_permissions=True)
    existing = frappe.get_all("EC Approval Level",
                              filters={"approval_process": PROCESS_CODE, "level_no": 1}, pluck="name")
    lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing \
        else frappe.new_doc("EC Approval Level")
    lvl.approval_process = PROCESS_CODE
    lvl.level_no = 1
    lvl.level_name = "CEO duyệt"
    lvl.mandatory = 1
    lvl.approval_mode = "Any One"
    lvl.minimum_approvals = 1
    lvl.allows_amount_adjustment = 0
    lvl.sla_policy = NORMAL_POLICY
    lvl.set("participants", [])
    lvl.append("participants", {"participant_purpose": "Approver", "source_type": "Role",
                                "role": CEO_ROLE, "sort_order": 0})
    lvl.save(ignore_permissions=True)


@frappe.whitelist()
def validate_adhoc_approval_v1():
    _require_sm()
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    chk("approval_type", frappe.db.exists("EC Approval Type", APPROVAL_TYPE))
    chk("business_doctype", frappe.db.exists("DocType", "EC Adhoc Approval Request"))
    chk("private_flag", frappe.db.get_value("EC Approval Type", APPROVAL_TYPE, "private") == 1)
    proc = frappe.db.get_value("EC Approval Process", PROCESS_CODE, ["status"], as_dict=True)
    chk("process_exists", bool(proc), PROCESS_CODE)
    levels = frappe.get_all("EC Approval Level", filters={"approval_process": PROCESS_CODE},
                            fields=["level_no", "level_name", "sla_policy"], order_by="level_no")
    chk("has_1_level", len(levels) == 1, json.dumps([l.level_name for l in levels]))
    for code in POLICIES:
        chk("sla_%s" % code, frappe.db.get_value("EC Approval SLA Policy", code, "active"))
    chk("role_has_members",
        bool(frappe.db.exists("Has Role", {"role": CEO_ROLE, "parenttype": "User"})),
        "Role %s" % CEO_ROLE)
    return {"ok": all(c["ok"] for c in checks), "checks": checks}
