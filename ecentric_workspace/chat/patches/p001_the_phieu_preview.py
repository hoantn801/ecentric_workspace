# Copyright (c) 2026, eCentric and contributors
"""Phieu trong chat (07/10/2026): chon cac dong hien tren THE PHIEU trong chat Raven.

Raven ve the chung tu bang cac truong `in_preview` cua DocType; khong khai thi lay moi truong
BAT BUOC - voi De nghi thanh toan la ly do (Long Text), so tai khoan ngan hang, 3 o Co/Khong...
Patch nay bat `in_preview` (Property Setter, khong sua JSON DocType cua Approval Center) cho:
nguoi de nghi, phong ban, ngay gui va o so tien dau tien co mat. Tieu de phieu Raven tu lay.
`in_preview` chi dung cho the xem truoc (Raven, va o hover link tren Desk). Chay lai vo hai.
"""
import frappe

PREVIEW = ("requested_by", "department", "submitted_at")
AMOUNTS = ("payment_amount", "requested_amount", "total_amount", "amount", "approved_amount",
           "budget")


def fields_for(fieldnames):
    have = set(fieldnames)
    out = [f for f in PREVIEW if f in have]
    amount = next((f for f in AMOUNTS if f in have), None)
    if amount:
        out.append(amount)
    return out


def execute():
    from ecentric_workspace.approval_center.shared.registry import BUSINESS_DOCTYPE_DEFINITIONS
    for doctype in BUSINESS_DOCTYPE_DEFINITIONS:
        if not frappe.db.exists("DocType", doctype):
            continue
        meta = frappe.get_meta(doctype)
        for fieldname in fields_for([f.fieldname for f in meta.fields]):
            frappe.make_property_setter(
                {"doctype": doctype, "fieldname": fieldname, "property": "in_preview",
                 "value": "1", "property_type": "Check"},
                validate_fields_for_doctype=False)
        frappe.clear_cache(doctype=doctype)
