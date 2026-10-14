# Copyright (c) 2026, eCentric and contributors
"""Truy cap du lieu cho may cham cong khuon mat. Chi doc / ghi, khong quyet dinh."""
import frappe

from ecentric_workspace.hr.face_device import constants as C

_EMP_FIELDS = ["name", "employee_name", "default_shift", "holiday_list", "company"]


class FaceCheckinRepository:
    # --- nhan vien ---------------------------------------------------------
    def employee_by_device_no(self, no):
        return frappe.db.get_value(
            C.DT_EMPLOYEE, {"attendance_device_id": no, "status": "Active"},
            _EMP_FIELDS, as_dict=True)

    def employee_by_name_unmapped(self, name):
        rows = frappe.db.sql(
            "select name, employee_name, default_shift, holiday_list, company"
            " from `tabEmployee` where name=%s and status='Active'"
            " and ifnull(attendance_device_id, '')=''", (name,), as_dict=True)
        return rows[0] if rows else None

    # --- cham cong ---------------------------------------------------------
    def checkin_exists(self, employee, t):
        return bool(frappe.db.exists(C.DT_CHECKIN, {"employee": employee, "time": t}))

    def first_in(self, employee, day):
        rows = frappe.db.sql(
            "select name, time from `tabEmployee Checkin` where employee=%s"
            " and log_type=%s and date(time)=%s order by time asc limit 1",
            (employee, C.LOG_IN, day), as_dict=True)
        return rows[0] if rows else None

    def insert_checkin(self, employee, t, log_type, shift, device_id):
        doc = frappe.get_doc({"doctype": C.DT_CHECKIN, "employee": employee,
                              "log_type": log_type, "time": t, "shift": shift,
                              "device_id": device_id})
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        return doc.name

    def set_log_type(self, name, log_type):
        frappe.db.set_value(C.DT_CHECKIN, name, "log_type", log_type)

    def month_closed(self, employee, period_month):
        return bool(frappe.db.sql(
            "select 1 from `tabEC Timesheet Close` where employee=%s"
            " and period_month=%s and status in %s limit 1",
            (employee, period_month, C.TS_CLOSED_STATES)))

    # --- ngay cong ---------------------------------------------------------
    def shift_cutoff(self, shift):
        return frappe.db.get_value(C.DT_SHIFT, shift, "ec_checkin_cutoff") if shift else None

    def is_holiday(self, emp, day):
        hl = emp.get("holiday_list") or frappe.db.get_value(
            "Company", emp.get("company"), "default_holiday_list")
        if not hl:
            return False
        return bool(frappe.db.sql(
            "select 1 from `tabHoliday` where parent=%s and holiday_date=%s limit 1",
            (hl, day)))

    def on_leave(self, employee, day):
        return bool(frappe.db.sql(
            "select 1 from `tabLeave Application` where employee=%s and status='Approved'"
            " and docstatus=1 and %s between from_date and to_date limit 1",
            (employee, day)))

    def attendance_exists(self, employee, day):
        return bool(frappe.db.sql(
            "select 1 from `tabAttendance` where employee=%s and attendance_date=%s"
            " and docstatus < 2 limit 1", (employee, day)))

    def insert_present(self, emp, day, shift):
        doc = frappe.get_doc({"doctype": C.DT_ATTENDANCE, "employee": emp["name"],
                              "attendance_date": day, "status": "Present",
                              "shift": shift, "company": emp.get("company")})
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc.name

    # --- giao dich & nhat ky -----------------------------------------------
    def savepoint(self, name):
        frappe.db.savepoint(name)

    def rollback(self, name):
        frappe.db.rollback(save_point=name)

    def log_error(self, title):
        frappe.log_error(title=title[:140], message=frappe.get_traceback())

    def log_once(self, key, title, message):
        """Mot loi giong nhau chi ghi MOT lan moi ngay - may day lien tuc."""
        ck = "ec_face_once:%s:%s" % (frappe.utils.nowdate(), key)
        if frappe.cache().get_value(ck):
            return
        frappe.cache().set_value(ck, 1, expires_in_sec=86400)
        frappe.log_error(title=title[:140], message=message)
