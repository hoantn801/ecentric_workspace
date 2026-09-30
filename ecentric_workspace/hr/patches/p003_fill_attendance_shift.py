# Copyright (c) 2026, eCentric and contributors
"""Dien ca cho Attendance cu dang trong ca (Hoan duyet 30/09) - xem hr/attendance_shift.py.

Ngay 30/09 co 60 ban ghi (07-11/2026, phan lon On Leave tu duyet don nghi, mot so Present tu
duyet giai trinh). CHI dien cot `shift`: khong doi trang thai cong, khong xoa, khong cham
modified. Chay lai bao nhieu lan cung vo hai (chi lay ban ghi con trong ca).
"""
import frappe

from ecentric_workspace.hr.attendance_shift import shift_for


def execute():
    rows = frappe.get_all("Attendance", filters={"docstatus": ("<", 2), "shift": ("is", "not set")},
                          fields=["name", "employee"], limit_page_length=0)
    cache, done = {}, 0
    for r in rows:
        if r.employee not in cache:
            cache[r.employee] = shift_for(r.employee)
        s = cache[r.employee]
        if s:
            frappe.db.set_value("Attendance", r.name, "shift", s, update_modified=False)
            done += 1
    frappe.logger("hr").info("p003_fill_attendance_shift: %d/%d" % (done, len(rows)))
