# Copyright (c) 2026, eCentric and contributors
"""Doc "Danh sach di lam ngay nghi" (EC Holiday Work) - MOT cho cho moi noi can hoi.

24/11/2026 (Hoan): ngay Van hoa Viet Nam ca cong ty nghi, 23 ban dang ky di lam campaign
"tinh nhu ngay lam binh thuong, thuong 500K + 2 ngay phep". Lich nghi (Holiday List) la
lich CHUNG nen khong the "bo ngay le" cho rieng 23 nguoi. Thay vao do, moi cho dang hoi
"hom nay co phai ngay nghi cua nguoi nay khong" hoi them mot cau: nguoi nay co nam trong
danh sach di lam ngay do (counts_as_workday = 1) khong. Co -> la ngay lam.

Cung luat do phai ap o MOI cho: cham cong app (ec_hr_checkin), may khuon mat
(face_device), nhac cham cong, SLA cham cong, bang cong (ec_hr_attendance_data), trang
thai hom nay, giai trinh cham cong. Python doc qua file nay; Server Script khong import
duoc module nen viet lai dung cau SQL `WORKDAY_SQL` ben duoi.

Bang chua ton tai (truoc migrate) -> coi nhu khong ai dang ky. Khong bao gio nem loi.
"""
import frappe

DT = "EC Holiday Work"
DT_ROW = "EC Holiday Work Member"

WORKDAY_SQL = (
    "select 1 from `tabEC Holiday Work Member` m"
    " inner join `tabEC Holiday Work` w on w.name = m.parent"
    " where m.employee=%s and w.work_date=%s and ifnull(w.counts_as_workday,0)=1 limit 1"
)


def _ready():
    try:
        return bool(frappe.db.table_exists(DT)) and bool(frappe.db.table_exists(DT_ROW))
    except Exception:
        return False


def workday_dates(employee, start=None, end=None):
    """Tap ngay (date) ma `employee` di lam theo danh sach va duoc tinh la ngay lam."""
    if not employee or not _ready():
        return set()
    from frappe.utils import getdate
    q = ("select w.work_date from `tabEC Holiday Work Member` m"
         " inner join `tabEC Holiday Work` w on w.name = m.parent"
         " where m.employee=%s and ifnull(w.counts_as_workday,0)=1")
    args = [employee]
    if start:
        q += " and w.work_date >= %s"
        args.append(str(getdate(start)))
    if end:
        q += " and w.work_date <= %s"
        args.append(str(getdate(end)))
    try:
        return {getdate(r[0]) for r in frappe.db.sql(q, tuple(args))}
    except Exception:
        frappe.log_error(title="holiday_work.workday_dates", message=frappe.get_traceback())
        return set()


def is_workday(employee, day):
    """True khi ngay `day` la ngay LAM cua `employee` du lich nghi ghi la ngay nghi."""
    if not employee or not day or not _ready():
        return False
    from frappe.utils import getdate
    try:
        return bool(frappe.db.sql(WORKDAY_SQL, (employee, str(getdate(day)))))
    except Exception:
        frappe.log_error(title="holiday_work.is_workday", message=frappe.get_traceback())
        return False
