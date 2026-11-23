# Copyright (c) 2026, eCentric and contributors
"""RESIGNATION-V2 (23/11/2026, Hoan chot): NV -> Quan ly truc tiep -> CnB/HR -> CEO.

  L1 Quản lý trực tiếp  Reference Employee Manager tu `employee_email` (+ fallback_user seed)
  L2 CnB/HR             Role EC CnB + Role HR (Any One; role HR chua co nguoi -> bo + canh bao)
  L3 CEO                Role EC CEO
  SLA moi cap 2 ngay lam viec (policy HR_2_NGAY_LV, chi gan khi an toan - xem sla_ngay_lam_viec).
Khong co Fulfiller: V2 di thang Clearance sau khi duyet. Bat V2 (activation_v2) CHI khi hang doi
"HR xu ly" cu cua V1 khong con don (Assigned / In Progress). Email chi o seed mac dinh duoi day.
dry-run mac dinh; apply=1 moi ghi; khong bao gio ghi de process dang Active."""
import json

import frappe

from ecentric_workspace.approval_center.shared import process_seed as ps
from ecentric_workspace.approval_center.shared import sla_ngay_lam_viec as sla

PROCESS_CODE = "RESIGNATION-V2"
APPROVAL_TYPE = "RESIGNATION"
MANAGER_FIELD = "employee_email"
LEVEL_NAMES = ("Quản lý trực tiếp", "CnB/HR xác nhận", "CEO xác nhận")
# Seed mac dinh (doi duoc qua tham so) - email CHI duoc o day.
DEFAULT_FALLBACK = "tuan.ly@ecentric.vn"
DEFAULT_CNB = ["role:EC CnB", "role:HR"]
OPTIONAL = ("role:HR",)
DEFAULT_CEO = ["role:EC CEO"]
SLA_DAYS = 2


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


@frappe.whitelist()
def setup_resignation_v2(cnb=None, ceo=None, fallback_user=None, dry_run=1, apply=0):
    ps.require_sm()
    dry = int(apply or 0) != 1
    rep = ps.new_report(dry)
    fb = (fallback_user or DEFAULT_FALLBACK).strip()
    ok, why = ps.entry_ok(fb)
    if not ok:
        rep["errors"].append("Dự phòng quản lý trực tiếp: %s" % why)
    cnb_e = ps.check_entries("CnB/HR", _parse(cnb, DEFAULT_CNB), rep, optional=OPTIONAL)
    ceo_e = ps.check_entries("CEO", _parse(ceo, DEFAULT_CEO), rep)
    rep["planned"] = ["process %s (Draft)" % PROCESS_CODE,
                      "L1 %s (employee_email, dự phòng %s)" % (LEVEL_NAMES[0], fb),
                      "L2 %s %s" % (LEVEL_NAMES[1], cnb_e), "L3 %s %s" % (LEVEL_NAMES[2], ceo_e),
                      "SLA %d ngày làm việc mỗi cấp" % SLA_DAYS]

    def spec():
        pol = sla.ensure_policy(SLA_DAYS, rep)
        return {"code": PROCESS_CODE, "title": "Resignation V2", "approval_type": APPROVAL_TYPE,
                "version_no": 2,
                "description": "NV -> Quản lý trực tiếp -> CnB/HR -> CEO; không có Từ chối; duyệt xong mở Clearance.",
                "levels": [
                    {"level_no": 1, "level_name": LEVEL_NAMES[0], "sla_policy": pol,
                     "participants": [{"participant_purpose": "Approver",
                                       "source_type": "Reference Employee Manager",
                                       "reference_field": MANAGER_FIELD, "fallback_user": fb,
                                       "sort_order": 0}]},
                    {"level_no": 2, "level_name": LEVEL_NAMES[1], "sla_policy": pol,
                     "participants": ps.rows(cnb_e)},
                    {"level_no": 3, "level_name": LEVEL_NAMES[2], "sla_policy": pol,
                     "participants": ps.rows(ceo_e)},
                ]}
    return ps.finish_setup(rep, dry, spec, APPROVAL_TYPE)


@frappe.whitelist()
def validate_resignation_v2():
    return ps.validate_process(PROCESS_CODE, expect_levels=3)


def old_queue_open():
    """So don V1 con trong hang doi "HR xu ly" (chua Completed)."""
    return frappe.db.count("EC Resignation Request",
                           {"fulfillment_status": ["in", ["Assigned", "In Progress"]]})


@frappe.whitelist()
def activate_resignation_v2(dry_run=1, apply=0):
    """V1 -> Retired, V2 -> Active (mot giao dich). CHAN khi hang doi HR xu ly cu con viec: V1 Retired
    thi nguoi xu ly cu van nhan viec duoc (is_active_process_fulfiller doc ca Draft/Active) NHUNG chi
    khi V1 con o Draft/Active - nen doi hang doi rong roi moi ngung V1."""
    n = old_queue_open()
    extra = ["Hàng đợi HR xử lý cũ (V1) còn %d đơn - xử lý xong rồi mới ngừng V1." % n] if n else []
    rep = ps.run_swap(APPROVAL_TYPE, PROCESS_CODE, dry_run=dry_run, apply=apply,
                      extra_blockers=extra, expect_levels=3)
    rep["old_queue_open"] = n
    return rep
