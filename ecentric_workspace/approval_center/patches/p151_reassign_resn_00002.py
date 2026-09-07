# Copyright (c) 2026, eCentric and contributors
"""Chuyen viec xu ly EC-RESN-2026-00002 tu hoan.tran sang tuan.ly (07/09, Hoan).

Hoan bam nham "Nhan xu ly" tren ho so nghi viec cua Chau Thuy Thao Nguyen. Nut do hien
voi anh vi `is_eligible_fulfiller` cho System Manager di qua vo dieu kien, trong khi
Fulfiller cau hinh cua RESIGNATION-V1 chi co tuan.ly@ecentric.vn.

Dung dung duong engine (`transitions.reassign_fulfillment`) chu KHONG set_value tay:
duong engine dong ToDo cua chu cu, mo dung mot ToDo cho chu moi, ghi audit "Assigned"
va bao Teams. set_value tay se de lai ToDo mo cua hoan.tran va tuan.ly khong nhan viec.

Actor = hoan.tran (chu hien tai) de so kiem toan ghi dung nguoi chuyen, khong phai
Administrator.

KHONG BAO GIO nem loi: patch chay trong `bench migrate`, mot exception o day lam chet
ca lan deploy (da dinh voi p116). Moi truong hop bat thuong deu chi log va bo qua.
"""
import frappe

from ecentric_workspace.approval_center.shared.workflow import transitions

DOCTYPE = "EC Resignation Request"
NAME = "EC-RESN-2026-00002"
NEW_OWNER = "tuan.ly@ecentric.vn"
OLD_OWNER = "hoan.tran@ecentric.vn"
_ACTIVE = ("Assigned", "In Progress")


def execute():
    try:
        snap = frappe.db.get_value(
            DOCTYPE, NAME, ["fulfillment_status", "fulfillment_owner"], as_dict=True)
        if not snap:
            frappe.log_error("p151: khong thay %s, bo qua." % NAME, "p151 reassign")
            return
        if snap.get("fulfillment_owner") == NEW_OWNER:
            frappe.log_error("p151: %s da thuoc %s, bo qua." % (NAME, NEW_OWNER), "p151 reassign")
            return
        if snap.get("fulfillment_status") not in _ACTIVE:
            frappe.log_error(
                "p151: %s fulfillment_status=%s (khong con active), bo qua."
                % (NAME, snap.get("fulfillment_status")), "p151 reassign")
            return
        actor = snap.get("fulfillment_owner") or OLD_OWNER
        transitions.reassign_fulfillment(DOCTYPE, NAME, NEW_OWNER, actor=actor)
        after = frappe.db.get_value(
            DOCTYPE, NAME, ["fulfillment_status", "fulfillment_owner"], as_dict=True) or {}
        frappe.log_error(
            "p151: %s -> owner=%s status=%s (truoc: owner=%s status=%s)"
            % (NAME, after.get("fulfillment_owner"), after.get("fulfillment_status"),
               snap.get("fulfillment_owner"), snap.get("fulfillment_status")),
            "p151 reassign")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p151 reassign FAILED")
