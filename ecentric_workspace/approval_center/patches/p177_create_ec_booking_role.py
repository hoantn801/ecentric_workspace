# Copyright (c) 2026, eCentric and contributors
"""Tao Role "EC Booking" cho form Booking Request (11/09, Hoan).

Role nay la LUOI DO: viec di dich danh toi ban Booking phu trach brand
(`Brand.ec_booking_owner`), con role quyet dinh AI DUOC NHAN - de nguoi khac nhan ho khi
nguoi phu trach nghi, va de phieu cua brand chua gan nguoi khong bi roi.

CHI tao role rong. KHONG tu gan cho ai: gan role la quyet dinh nhan su, khong phai viec cua
mot patch. Chua ai duoc gan thi validate_booking_request_v1 se bao "role_has_members" do -
do la canh bao co chu dich, khong phai loi.

Idempotent: co roi thi khong dung toi (khong ghi de desk_access / disabled cua ban da co)."""
import frappe

ROLE = "EC Booking"


def execute():
    try:
        if frappe.db.exists("Role", ROLE):
            frappe.log_error("Role %s da ton tai - khong doi gi" % ROLE, "p177 booking role")
            return
        doc = frappe.new_doc("Role")
        doc.role_name = ROLE
        doc.desk_access = 0          # nguoi dung thuong lam viec tren cong, khong vao Desk
        doc.insert(ignore_permissions=True)
        frappe.log_error("Da tao Role %s (chua gan cho ai)" % ROLE, "p177 booking role")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p177 booking role THAT BAI")
