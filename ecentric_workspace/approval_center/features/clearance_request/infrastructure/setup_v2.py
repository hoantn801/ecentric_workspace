# Copyright (c) 2026, eCentric and contributors
"""CLEARANCE_REQUEST-V2 (23/11/2026, Hoan chot). Mot cap "Bàn giao nghỉ việc", Each Group SONG SONG:
  Line Manager  quan ly truc tiep cua nguoi nghi (employee_email; khong co -> fallback seed)
  HR            nhom CnB/HR (Role EC CnB)
  HOF           Fin (Role EC HOF)
  Operation     Role EC Ops System
  Nguoi theo doi: Role EC CEO (participant_purpose="Notify" o process - engine Dot 0 doc dong nay;
  engine chua co thi dong chi nam cho, khong anh huong luong).
Han moi nhom = ngay lam viec cuoi (service._dat_han). Nguoi gui KHONG la nguoi nghi (service).

GIOI HAN ENGINE (ghi ro): o che do Each Group moi DONG la mot nhom, nen nhom HR chi nhan MOT nguon.
Muon nhom HR gom ca Role HR (luc.nguyen) thi engine phai gop cac dong cung group_label - viec cua
engine (Dot 0), khong lam o feature. Tam thoi: nhom HR = Role EC CnB; doi bang tham so `hr`."""
import json

import frappe

from ecentric_workspace.approval_center.shared import process_seed as ps

PROCESS_CODE = "CLEARANCE_REQUEST-V2"
APPROVAL_TYPE = "CLEARANCE_REQUEST"
LEVEL_NAME = "Bàn giao nghỉ việc"
LM_FIELD = "employee_email"
DEFAULT_LM_FALLBACK = "tuan.ly@ecentric.vn"
# TEMP-WORKAROUND (2026-11-23, engine Each Group: mot dong participant = mot nhom): nhom HR chi nhan
# Role EC CnB, CHUA gom Role HR (luc.nguyen). Rui ro: nguoi chi co role HR khong nhan viec nhom HR o
# NSP/Clearance (van nhan o Offer/Nghi viec vi cac cap Any One gom duoc nhieu dong). Sua goc: engine
# gop cac dong cung group_label thanh mot nhom (transitions._resolve_groups) roi them "role:HR" vao day.
GROUPS = (("HR", "hr", ["role:EC CnB"]),
          ("HOF", "hof", ["role:EC HOF"]),
          ("Operation", "operation", ["role:EC Ops System"]))
DEFAULT_WATCH = ["role:EC CEO"]


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


@frappe.whitelist()
def setup_clearance_request_v2(hr=None, hof=None, operation=None, line_manager_fallback=None,
                               watchers=None, dry_run=1, apply=0):
    ps.require_sm()
    dry = int(apply or 0) != 1
    rep = ps.new_report(dry)
    args = {"hr": hr, "hof": hof, "operation": operation}
    groups = []
    for label, key, default in GROUPS:
        entries = ps.check_entries(label, _parse(args[key], default), rep)
        if len(entries) > 1:
            rep["errors"].append("Nhóm %s: engine Each Group chỉ nhận MỘT nguồn mỗi nhóm." % label)
        groups.append((label, entries[:1]))
    fb = (line_manager_fallback or DEFAULT_LM_FALLBACK).strip()
    ok, why = ps.entry_ok(fb)
    if not ok:
        rep["errors"].append("Dự phòng Line Manager: %s" % why)
    watch = [w for w in _parse(watchers, DEFAULT_WATCH) if ps.entry_ok(w)[0]]
    if not watch:
        rep["warnings"].append("Không có người theo dõi hợp lệ (CEO) - vẫn tạo process.")
    rep["planned"] = ["process %s (Draft)" % PROCESS_CODE,
                      "L1 %s (Each Group): Line Manager (dự phòng %s) + %s" % (LEVEL_NAME, fb, groups),
                      "Người theo dõi: %s" % watch]

    def spec():
        parts = [{"participant_purpose": "Approver", "group_label": "Line Manager",
                  "source_type": "Reference Employee Manager", "reference_field": LM_FIELD,
                  "fallback_user": fb, "sort_order": 0}]
        for i, (label, entries) in enumerate(groups):
            parts += ps.rows(entries, group_label=label, start=i + 1)
        return {"code": PROCESS_CODE, "title": "Clearance Request V2", "approval_type": APPROVAL_TYPE,
                "version_no": 2, "description": "Bàn giao song song LM / HR / HOF / Operation; CEO theo dõi; "
                                                "người gửi là CnB, không phải người nghỉ.",
                "process_participants": ps.rows(watch, purpose="Notify", start=90),
                "levels": [{"level_no": 1, "level_name": LEVEL_NAME, "approval_mode": "Each Group",
                            "minimum_approvals": 0, "participants": parts}]}
    return ps.finish_setup(rep, dry, spec, APPROVAL_TYPE)


@frappe.whitelist()
def validate_clearance_request_v2():
    return ps.validate_process(PROCESS_CODE, expect_levels=1)


@frappe.whitelist()
def activate_clearance_request_v2(dry_run=1, apply=0):
    return ps.run_swap(APPROVAL_TYPE, PROCESS_CODE, dry_run=dry_run, apply=apply, expect_levels=1)
