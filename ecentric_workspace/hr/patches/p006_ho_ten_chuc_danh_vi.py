# Copyright (c) 2026, eCentric and contributors
"""p006: them cot "Ho ten (tieng Viet)" + "Chuc danh (tieng Viet)" vao report "Ho so nhan su".

13/10/2026, CnB nho: can ho ten co dau va chuc danh tieng Viet tren ho so de dien (hop dong,
giay to). Hai Custom Field Employee.ec_ho_ten_vi / ec_chuc_danh_vi di theo fixtures
(custom_field.json). Patch nay CHI chen hai cot vao report Report Builder ma CnB dang dung de
dien hang loat - ngay sau cot ho ten / chuc danh tieng Anh.

Chi THEM cot con thieu, khong doi gi khac cua report (HR co the da sua cot / bo loc tren site).
Report chua co (bench moi, p002 chua tao) -> bo qua. Loi -> Error Log, khong chan migrate.
"""
import json

import frappe

REPORT = "Hồ sơ nhân sự"
EMPLOYEE = "Employee"
INSERTS = (("employee_name", "ec_ho_ten_vi"), ("designation", "ec_chuc_danh_vi"))


def add_columns(fields):
    """[[field, doctype], ...] -> danh sach moi co them hai cot. Thuan, khong frappe."""
    out = [list(f) for f in fields]
    have = {(f[0], f[1]) for f in out}
    for after, new in INSERTS:
        if (new, EMPLOYEE) in have:
            continue
        pos = next((i + 1 for i, f in enumerate(out) if f[0] == after and f[1] == EMPLOYEE),
                   len(out))
        out.insert(pos, [new, EMPLOYEE])
        have.add((new, EMPLOYEE))
    return out


def execute():
    try:
        if not frappe.db.exists("Report", REPORT):
            return
        spec = json.loads(frappe.db.get_value("Report", REPORT, "json") or "{}")
        fields = spec.get("fields") or []
        new = add_columns(fields)
        if new != fields:
            spec["fields"] = new
            frappe.db.set_value("Report", REPORT, "json", json.dumps(spec, ensure_ascii=False))
    except Exception:
        frappe.log_error(title="p006 ho ten chuc danh vi", message=frappe.get_traceback())
