# Copyright (c) 2026, eCentric and contributors
"""Doc du lieu HR cho Don nghi viec (23/11/2026): ho so Employee + bang HD `ec_contracts`.

Chi DOC. `ec_contracts` la permlevel 2 tren Employee - doc o day bang truy van may chu (khong qua
quyen nguoi xem); ket qua chi duoc tra ra cho nguoi duoc phep (xem service.notice_info)."""
import frappe

CONTRACT_DT = "EC Employee Contract"
CONTRACT_FIELDS = ("loai_hop_dong", "tu_ngay", "den_ngay", "khong_thoi_han")


def employee_of(email):
    email = (email or "").strip()
    if not email:
        return None
    for f in ("user_id", "company_email", "personal_email"):
        row = frappe.db.get_value("Employee", {f: email},
                                  ["name", "employee_name", "user_id", "reports_to", "status",
                                   "company", "department"], as_dict=True)
        if row:
            return row
    return None


def contracts_of(employee):
    if not employee:
        return []
    return frappe.get_all(CONTRACT_DT, filters={"parent": employee, "parenttype": "Employee",
                                                "parentfield": "ec_contracts"},
                          fields=list(CONTRACT_FIELDS), order_by="tu_ngay asc",
                          limit_page_length=0)


def manager_user_of(employee_row):
    if not (employee_row and employee_row.get("reports_to")):
        return None
    return frappe.db.get_value("Employee", employee_row.reports_to, "user_id")
