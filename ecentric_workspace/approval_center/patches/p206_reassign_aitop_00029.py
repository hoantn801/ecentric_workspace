# Copyright (c) 2026, eCentric and contributors
"""Chuyen viec xu ly EC-AITOP-2026-00029 tu lam.nguyen ve dong.diep (24/09, Hoan).

Anh Lam bam "Nhan xu ly" luc 24/09 15:14 tren phieu nap Gemini cua Operation. Nut do hien voi
anh vi anh mang System Manager, ma `is_eligible_fulfiller` cho System Manager di qua vo dieu
kien - hop "Cho toi xu ly" cua anh chua MOI viec chua ai nhan o moi phong. Luc anh nhan, ToDo
hang doi cua dong.diep va hoan.tran bi dong; phieu dang qua han tu 21/09.

Form AI Topup KHONG co nut "Chuyen nguoi xu ly": nut do chi co o 5 form dung
fulfillment_api_adapter (p152); AI Topup co controller rieng. Nen chuyen bang patch, dung
khuon p151.

Dung duong engine `transitions.reassign_fulfillment`, KHONG set_value tay: engine kiem nguoi
nhan co du dieu kien, dong ToDo cua chu cu, mo dung mot ToDo cho chu moi, ghi audit "Assigned"
va bao ca ba ben. Actor = hoan.tran - nguoi quyet dinh chuyen, de so kiem toan ghi dung nguoi.

Idempotent: da thuoc dong.diep, hoac khong con active, thi bo qua.
KHONG BAO GIO nem loi: patch chay trong migrate (p116).
"""
import frappe

from ecentric_workspace.approval_center.shared.workflow import transitions

DOCTYPE = "EC AI Topup Request"
NAME = "EC-AITOP-2026-00029"
NEW_OWNER = "dong.diep@ecentric.vn"
ACTOR = "hoan.tran@ecentric.vn"
_ACTIVE = ("Assigned", "In Progress")


def execute():
    try:
        snap = frappe.db.get_value(
            DOCTYPE, NAME, ["fulfillment_status", "fulfillment_owner"], as_dict=True)
        if not snap:
            frappe.log_error("p206: khong thay %s, bo qua." % NAME, "p206 reassign")
            return
        if snap.get("fulfillment_owner") == NEW_OWNER:
            return
        if snap.get("fulfillment_status") not in _ACTIVE:
            frappe.log_error("p206: %s fulfillment_status=%s, bo qua."
                             % (NAME, snap.get("fulfillment_status")), "p206 reassign")
            return
        transitions.reassign_fulfillment(DOCTYPE, NAME, NEW_OWNER, actor=ACTOR)
        after = frappe.db.get_value(
            DOCTYPE, NAME, ["fulfillment_status", "fulfillment_owner"], as_dict=True) or {}
        frappe.log_error("p206: %s -> owner=%s status=%s (truoc: owner=%s)"
                         % (NAME, after.get("fulfillment_owner"), after.get("fulfillment_status"),
                            snap.get("fulfillment_owner")), "p206 reassign")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p206 reassign FAILED")
