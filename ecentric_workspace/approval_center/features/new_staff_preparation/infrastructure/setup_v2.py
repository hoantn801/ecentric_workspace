# Copyright (c) 2026, eCentric and contributors
"""NEW_STAFF_PREPARATION-V2 (23/11/2026, Hoan chot). Mot cap "Chuẩn bị onboard", Each Group SONG SONG:
  HR         nhom CnB/HR (Role EC CnB) - thay user Lead HR co dinh cua V1 (review F17)
  HOF        Fin (Role EC HOF)
  CnB        Role EC CnB Payroll (giu nhu V1)
  Operation  Role EC Ops System
  Nguoi theo doi: Role EC CEO (participant_purpose="Notify" o process).
Han moi nhom: truoc ngay onboard 1 ngay lam viec, toi thieu 2 ngay lam viec tu luc tao (service).
Gioi han engine Each Group (mot dong = mot nhom): xem clearance_request/infrastructure/setup_v2.py."""
import json

import frappe

from ecentric_workspace.approval_center.shared import process_seed as ps

PROCESS_CODE = "NEW_STAFF_PREPARATION-V2"
APPROVAL_TYPE = "NEW_STAFF_PREPARATION"
LEVEL_NAME = "Chuẩn bị onboard"
HR_GROUP = "HR"
# TEMP-WORKAROUND (2026-11-23, engine Each Group: mot dong participant = mot nhom): nhom HR chi nhan
# Role EC CnB, CHUA gom Role HR (luc.nguyen). Rui ro: nguoi chi co role HR khong nhan viec nhom HR o
# NSP/Clearance (van nhan o Offer/Nghi viec vi cac cap Any One gom duoc nhieu dong). Sua goc: engine
# gop cac dong cung group_label thanh mot nhom (transitions._resolve_groups) roi them "role:HR" vao day.
GROUPS = ((HR_GROUP, "hr", ["role:EC CnB"]),
          ("HOF", "hof", ["role:EC HOF"]),
          ("CnB", "cnb", ["role:EC CnB Payroll"]),
          ("Operation", "operation", ["role:EC Ops System"]))
DEFAULT_WATCH = ["role:EC CEO"]


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


@frappe.whitelist()
def setup_new_staff_preparation_v2(hr=None, hof=None, cnb=None, operation=None, watchers=None,
                                   dry_run=1, apply=0):
    ps.require_sm()
    dry = int(apply or 0) != 1
    rep = ps.new_report(dry)
    args = {"hr": hr, "hof": hof, "cnb": cnb, "operation": operation}
    groups = []
    for label, key, default in GROUPS:
        entries = ps.check_entries(label, _parse(args[key], default), rep)
        if len(entries) > 1:
            rep["errors"].append("Nhóm %s: engine Each Group chỉ nhận MỘT nguồn mỗi nhóm." % label)
        groups.append((label, entries[:1]))
    watch = [w for w in _parse(watchers, DEFAULT_WATCH) if ps.entry_ok(w)[0]]
    if not watch:
        rep["warnings"].append("Không có người theo dõi hợp lệ (CEO) - vẫn tạo process.")
    rep["planned"] = ["process %s (Draft)" % PROCESS_CODE,
                      "L1 %s (Each Group): %s" % (LEVEL_NAME, groups), "Người theo dõi: %s" % watch]

    def spec():
        parts = []
        for i, (label, entries) in enumerate(groups):
            parts += ps.rows(entries, group_label=label, start=i)
        return {"code": PROCESS_CODE, "title": "New Staff Preparation V2", "approval_type": APPROVAL_TYPE,
                "version_no": 2, "description": "HR / HOF / CnB / Operation song song; CEO theo dõi.",
                "process_participants": ps.rows(watch, purpose="Notify", start=90),
                "levels": [{"level_no": 1, "level_name": LEVEL_NAME, "approval_mode": "Each Group",
                            "minimum_approvals": 0, "participants": parts}]}
    return ps.finish_setup(rep, dry, spec, APPROVAL_TYPE)


@frappe.whitelist()
def validate_new_staff_preparation_v2():
    return ps.validate_process(PROCESS_CODE, expect_levels=1)


@frappe.whitelist()
def activate_new_staff_preparation_v2(dry_run=1, apply=0):
    return ps.run_swap(APPROVAL_TYPE, PROCESS_CODE, dry_run=dry_run, apply=apply, expect_levels=1)
