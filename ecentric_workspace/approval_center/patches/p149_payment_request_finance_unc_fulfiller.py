# Copyright (c) 2026, eCentric and contributors
"""Buoc 6 "Finance xu ly UNC" cho Payment Request (07/09, Hoan).

Engine fulfillment lay nguoi xu ly tu EC Approval Process.participants (purpose Fulfiller).
Process PAYMENT_REQUEST dang Active tren production duoc tao boi setup.py ban "no fulfillment"
nen khong co dong Fulfiller nao -> sau CEO duyet, on_final_approval khong giao duoc ai.
Patch nay them MOT dong Fulfiller = Role "EC Finance" (ca phong Finance, ai ranh nhan) vao
moi process Active cua loai PAYMENT_REQUEST chua co Fulfiller. Idempotent; khong dung
level/approver (hash cau truc goi ky khong doi - Fulfiller nam o process, khong o level).

Neu Role EC Finance chua co nguoi -> log_error de admin gan role; phieu van sang Assigned
(System Manager thay tren hub) chu khong ket.
"""
import frappe

FULFILLER_ROLE = "EC Finance"
APPROVAL_TYPE = "PAYMENT_REQUEST"


def execute():
    if not frappe.db.exists("Role", FULFILLER_ROLE):
        frappe.log_error("Role %s khong ton tai - khong them Fulfiller" % FULFILLER_ROLE,
                         "p149 payment_request fulfiller")
        return
    procs = frappe.get_all("EC Approval Process",
                           filters={"approval_type": APPROVAL_TYPE, "status": "Active"}, pluck="name")
    for name in procs:
        proc = frappe.get_doc("EC Approval Process", name)
        if any(p.participant_purpose == "Fulfiller" for p in proc.participants):
            frappe.log_error("%s da co Fulfiller, bo qua" % name, "p149 payment_request fulfiller")
            continue
        proc.append("participants", {"participant_purpose": "Fulfiller", "source_type": "Role",
                                     "role": FULFILLER_ROLE, "sort_order": 0})
        proc.save(ignore_permissions=True)
        frappe.log_error("%s: them Fulfiller Role %s" % (name, FULFILLER_ROLE),
                         "p149 payment_request fulfiller")
    n = frappe.db.count("Has Role", {"role": FULFILLER_ROLE, "parenttype": "User"})
    if not n:
        frappe.log_error("Role %s chua gan cho ai - Finance se khong nhan duoc ToDo UNC"
                         % FULFILLER_ROLE, "p149 payment_request fulfiller")
