# Copyright (c) 2026, eCentric and contributors
"""Moi ban ghi Attendance PHAI mang ca lam viec (Shift Type).

VI SAO (Hoan 30/09): bang cong (HRMS Monthly Attendance Sheet) tach MOI CA thanh mot dong.
Cham cong hang ngay (ec_hr_checkin) luon gan "EC Standard 9-18", nhung Attendance sinh ra tu
duong khac thi KHONG co ca:
    - duyet don nghi   -> HRMS LeaveApplication.create_or_update_attendance (On Leave / Half Day)
    - duyet giai trinh -> HRMS AttendanceRequest.create_attendance (Present)
Ket qua: 26 nguoi thang 9 hien HAI dong trong bang cong, trong nhu "cham cong trung".

`before_insert` chu khong `validate`: HRMS tao Attendance cho don nghi voi
flags.ignore_validate = True, tuc la bo qua ca before_validate/validate - chi before_insert
con chay. Loi o day KHONG duoc lam hong viec duyet don -> nuot va ghi log.
"""
import frappe

DEFAULT_SHIFT = "EC Standard 9-18"   # cung gia tri mac dinh cua ec_hr_checkin


def shift_for(employee):
    s = frappe.db.get_value("Employee", employee, "default_shift") if employee else None
    s = s or DEFAULT_SHIFT
    return s if frappe.db.exists("Shift Type", s) else None


def ensure_shift(doc, method=None):
    if doc.get("shift"):
        return
    try:
        s = shift_for(doc.get("employee"))
        if s:
            doc.shift = s
    except Exception:
        frappe.log_error(frappe.get_traceback(), "attendance_shift.ensure_shift")
