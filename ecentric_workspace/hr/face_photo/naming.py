# Copyright (c) 2026, eCentric and contributors
"""Ma tren may + ten file cho iVMS-4200 ("Ma nguoi_Ten.jpg"). Thuan, khong frappe.

Ma tren may PHAI trung quy uoc cua hr/face_device: Attendance Device ID neu co, khong thi phan
so cua ma nhan vien (HR-EMP-00070 -> 70). Lech quy uoc = luot quet ve ERP khong khop nguoi.
"""
import re
import unicodedata

from ecentric_workspace.hr.face_photo import constants as C


def device_no(employee, attendance_device_id=None):
    if (attendance_device_id or "").strip():
        return attendance_device_id.strip()
    s = str(employee or "")
    if s.startswith(C.EMPLOYEE_SERIES):
        digits = s[len(C.EMPLOYEE_SERIES):]
        if digits.isdigit():
            return str(int(digits))
    return re.sub(r"[^0-9A-Za-z]", "", s)


def ascii_name(name):
    s = (name or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^A-Za-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip() or "NV"


def file_name(no, name):
    return "%s_%s.jpg" % (no, ascii_name(name))
