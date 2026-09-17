# Copyright (c) 2026, eCentric and contributors
"""Chinh sach cho nhom Bao cao tuan + sua han cham cong tu 23:59 thanh 10:00.

HAI VIEC, MOT PATCH, vi ca hai deu chi la sua danh muc va khong dong vao du lieu
nghia vu nao (chua co nghia vu nao ton tai).

1) SLA-WR-EXPLICIT: han cua bao cao tuan do CHINH `Weekly Team Update` mang
   theo (tinh tu `Department Reporting Window` luc sinh nghia vu). Module SLA
   KHONG tinh lai. Tinh lai se tao ra kha nang hai con han khac nhau cho cung
   mot ban bao cao - mot tren phieu, mot tren bang diem - va khi hai con so noi
   hai dieu khac nhau thi ca hai deu mat gia tri.

2) SUA LOI CUA LO B1. Toi seed `SLA-ATT-CHECKOUT` = 23:59 va gan lam chinh sach
   mac dinh cho ngay cong. SAI. Han cham cong thuc te la 10:00, da chay tren ban
   song tu lau: `hr/checkin_reminder.py` nhac luc 08:30 (kem Teams) va 09:30,
   ca hai deu ghi "cham cong truoc 10:00". Chu so huu cung da noi dung cau do
   ("quen cham sau 10h la quen roi") - luc nghe toi hieu nham thanh gio check-OUT.

   Chinh sach cu KHONG bi xoa, chi bi tat va go khoi mac dinh: no chua tung
   sinh ra nghia vu nao, nhung xoa mot ban ghi da tung ton tai la viec khong bao
   gio can thiet o day.

FAIL-SAFE: moi buoc boc rieng, ghi Error Log, luon ket thuc xanh.
"""
import frappe

from ecentric_workspace.sla.constants import (
    DT_POLICY, DT_TYPE, DUE_EXPLICIT, DUE_FIXED_TIME, TYPE_ATTENDANCE_DAY,
    TYPE_WEEKLY_REPORT,
)

WR_POLICY = {
    "policy_code": "SLA-WR-EXPLICIT",
    "policy_name": "Báo cáo tuần - hạn theo Department Reporting Window",
    "due_rule": DUE_EXPLICIT,
    "grace_minutes": 0,
    "description": "Hạn do chính Weekly Team Update mang theo. Module SLA không tính lại.",
}

ATT_POLICY = {
    "policy_code": "SLA-ATT-CHECKIN-10H",
    "policy_name": "Chấm công - hạn 10:00 cùng ngày",
    "due_rule": DUE_FIXED_TIME,
    "fixed_time": "10:00:00",
    "offset_days": 0,
    "grace_minutes": 0,
    "description": "Hạn chấm công 10:00, khớp với lời nhắc 08:30 và 09:30 đang chạy.",
}

OLD_ATT_CODE = "SLA-ATT-CHECKOUT"


def _upsert_policy(spec):
    name = frappe.db.get_value(DT_POLICY, {"policy_code": spec["policy_code"]}, "name")
    if name:
        doc = frappe.get_doc(DT_POLICY, name)
        doc.update({k: v for k, v in spec.items() if k != "policy_code"})
        doc.active = 1
        doc.save(ignore_permissions=True)
        return name, "updated"
    doc = frappe.new_doc(DT_POLICY)
    doc.update(spec)
    doc.active = 1
    doc.insert(ignore_permissions=True)
    return doc.name, "created"


def _set_default(type_code, policy_name):
    t = frappe.db.get_value(DT_TYPE, {"type_code": type_code}, "name")
    if not t:
        return "khong thay loai %s" % type_code
    if frappe.db.get_value(DT_TYPE, t, "default_policy") == policy_name:
        return "da dung"
    frappe.db.set_value(DT_TYPE, t, "default_policy", policy_name)
    return "da gan %s" % policy_name


def execute():
    done = []
    try:
        name, how = _upsert_policy(WR_POLICY)
        done.append("WR policy %s (%s)" % (name, how))
        done.append("WR type: " + _set_default(TYPE_WEEKLY_REPORT, name))
    except Exception:
        frappe.log_error(title="p003 WR policy", message=frappe.get_traceback())

    try:
        name, how = _upsert_policy(ATT_POLICY)
        done.append("ATT policy %s (%s)" % (name, how))
        done.append("ATT type: " + _set_default(TYPE_ATTENDANCE_DAY, name))
    except Exception:
        frappe.log_error(title="p003 ATT policy", message=frappe.get_traceback())

    try:
        old = frappe.db.get_value(DT_POLICY, {"policy_code": OLD_ATT_CODE}, "name")
        if old:
            frappe.db.set_value(DT_POLICY, old, "active", 0)
            done.append("tat chinh sach cu %s" % OLD_ATT_CODE)
    except Exception:
        frappe.log_error(title="p003 tat SLA-ATT-CHECKOUT",
                         message=frappe.get_traceback())

    frappe.log_error(title="p003 seed weekly + fix attendance due",
                     message="\n".join(done) or "(khong co gi)")
