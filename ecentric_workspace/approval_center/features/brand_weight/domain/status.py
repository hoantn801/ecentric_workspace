# Copyright (c) 2026, eCentric and contributors
"""Trang thai hien thi cua mot phieu ty trong - ham thuan, khong cham DB.

Doc tu trang thai that tren EC Approval Request (nguon su that duy nhat), khong luu
trang thai rieng tren phieu nghiep vu. Cap duoc doc theo `current_level` chu khong
dem so cap con lai: phieu bo cap 1 (khong co lead) di thang vao cap 2 van phai hien
la 'cho truong phong', khong phai 'cho lead'."""

LEVEL_LEAD = 1
LEVEL_HEAD = 2


def status_of(p):
    if not p:
        return "none"
    st = p.get("approval_status")
    if not st:
        return "draft"
    if st == "Pending":
        return "wait_head" if p.get("current_level") == LEVEL_HEAD else "wait_lead"
    return {"Information Required": "returned", "Approved": "final",
            "Rejected": "rejected", "Cancelled": "cancelled"}.get(st, "draft")


def stage_of_level(level_no):
    return "head" if level_no == LEVEL_HEAD else "lead"
