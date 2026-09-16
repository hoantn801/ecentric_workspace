# Copyright (c) 2026, eCentric and contributors
"""Seed 5 loai nghia vu SLA + chinh sach cham cong. Chay MOT lan.

FAIL-SAFE tuyet doi: mot patch hong chan CA BAN DEPLOY, va deploy bi chan thi ca
28 form duyet don dung theo. Mot danh muc thieu vai dong khong dang doi lay dieu
do. Nen moi thao tac o day deu boc try/except, ket qua ghi vao Error Log de doc
lai, va patch luon ket thuc xanh.

Patch nay KHONG mo mot nghia vu nao. No chi dung danh muc. Chua co nghia vu nao
chay vao he thong cho den khi cac diem cam duoc bat o dot sau - co y, de lo nay
khong the lam sai lech bat ky con so nao dang hien tren ban song.
"""
import frappe

from ecentric_workspace.sla.constants import (
    DT_POLICY, DT_TYPE, DUE_FIXED_TIME, GROUP_COUNTS_TOWARD_SLA, GROUP_MIN_SAMPLE,
    GROUP_SORT, GROUP_UNIT, TYPE_APPROVAL_STEP, TYPE_ATTENDANCE_DAY, TYPE_NAME,
    TYPE_RSVP, TYPE_TASK, TYPE_TO_GROUP, TYPE_WEEKLY_REPORT,
)

# Chinh sach cham cong la thu duy nhat seed duoc ma khong can ai nhap: han
# check-out = 23:59 cung ngay. Da chot 16/09 - "quen cham sau 10h la quen roi",
# khong co van tu bo sung truoc 23:59.
#
# Han CHECK-IN co y KHONG seed: no phu thuoc gio vao ca cua tung nguoi, ma du
# lieu ca lam viec chua duoc ra soat. Doan mot gio chung se tao ra mot bang diem
# sai ma trong nhu that - te hon nhieu so voi mot o trong co ten.
_ATTENDANCE_CHECKOUT = {
    "policy_code": "SLA-ATT-CHECKOUT",
    "policy_name": "Chấm công - hạn check-out trong ngày",
    "due_rule": DUE_FIXED_TIME,
    "fixed_time": "23:59:00",
    "offset_days": 0,
    "grace_minutes": 0,
    "description": "Hạn chấm công ra là 23:59 cùng ngày. Sau đó phải đi qua khiếu nại.",
}

_TYPES = (TYPE_APPROVAL_STEP, TYPE_ATTENDANCE_DAY, TYPE_RSVP, TYPE_WEEKLY_REPORT,
          TYPE_TASK)


def _seed_policy():
    if frappe.db.exists(DT_POLICY, {"policy_code": _ATTENDANCE_CHECKOUT["policy_code"]}):
        return None
    doc = frappe.get_doc(dict(doctype=DT_POLICY, active=1, **_ATTENDANCE_CHECKOUT))
    doc.insert(ignore_permissions=True)
    return doc.name


def _seed_type(type_code, policy_name):
    if frappe.db.exists(DT_TYPE, {"type_code": type_code}):
        return None
    group = TYPE_TO_GROUP[type_code]
    doc = frappe.get_doc({
        "doctype": DT_TYPE,
        "type_code": type_code,
        "type_name": TYPE_NAME[type_code],
        "group_key": group,
        "counts_toward_sla": GROUP_COUNTS_TOWARD_SLA.get(group, 1),
        "min_sample": GROUP_MIN_SAMPLE.get(group, 5),
        "unit_label": GROUP_UNIT.get(group, ""),
        "sort_order": GROUP_SORT.get(group, 100),
        "active": 1,
        "default_policy": policy_name if type_code == TYPE_ATTENDANCE_DAY else None,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def execute():
    created, failed = [], []
    policy_name = None
    try:
        policy_name = _seed_policy()
    except Exception:
        failed.append(_ATTENDANCE_CHECKOUT["policy_code"])
        frappe.log_error(frappe.get_traceback(), "p001 seed sla policy")
    if not policy_name:
        policy_name = frappe.db.get_value(
            DT_POLICY, {"policy_code": _ATTENDANCE_CHECKOUT["policy_code"]}, "name")

    for code in _TYPES:
        try:
            if _seed_type(code, policy_name):
                created.append(code)
        except Exception:
            failed.append(code)
            frappe.log_error(frappe.get_traceback(), "p001 seed sla type %s" % code)

    frappe.log_error(
        "tao moi: %s; da co san hoac bo qua: %s; loi: %s"
        % (created or "(khong)",
           [c for c in _TYPES if c not in created and c not in failed] or "(khong)",
           failed or "(khong)"),
        "p001 seed sla types")
