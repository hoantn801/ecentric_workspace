# Copyright (c) 2026, eCentric and contributors
"""Doc du lieu cho the Nhan su. NOI DUY NHAT cua tinh nang nay goi frappe.db / get_all.

Chi doc, khong ghi. Tra ve dict thuan. Cac truong duoc doc do tang goi quyet dinh
(theo permlevel cua nguoi xem) - repository KHONG tu mo rong danh sach truong."""
import frappe

from ecentric_workspace.hr.overview import constants as C


def user_roles(user):
    return set(frappe.get_roles(user))


def readable_fields():
    """(field Employee doc duoc, {bang con: cot doc duoc}) cua nguoi dang dang nhap.
    Dung lai hr.privacy.permlevels - CUNG luat voi form Desk va bo loc lich su thay doi
    (permlevel + field bi mask), khong viet luat thu hai."""
    from ecentric_workspace.hr.privacy.permlevels import readable_fields as _rf
    return _rf(C.EMPLOYEE)


def can_read(doctype):
    return bool(frappe.has_permission(doctype, "read"))


def _existing(doctype, fields):
    meta = frappe.get_meta(doctype)
    return [f for f in fields if f == "name" or meta.has_field(f)]


def employees(fields, active_only=True):
    filters = {"status": C.ACTIVE} if active_only else {}
    return frappe.get_all(C.EMPLOYEE, filters=filters, fields=_existing(C.EMPLOYEE, fields),
                          order_by="employee_name asc", limit_page_length=0)


def employee(name, fields):
    rows = frappe.get_all(C.EMPLOYEE, filters={"name": name},
                          fields=_existing(C.EMPLOYEE, fields), limit_page_length=1)
    return rows[0] if rows else None


def contracts(parents=None):
    if not frappe.db.exists("DocType", C.CONTRACT):
        return []
    filters = {"parenttype": C.EMPLOYEE, "parentfield": "ec_contracts"}
    if parents is not None:
        filters["parent"] = ["in", list(parents) or [""]]
    return frappe.get_all(C.CONTRACT, filters=filters, parent_doctype=C.EMPLOYEE,
                          fields=["parent", "loai_hop_dong", "so_hop_dong", "tu_ngay",
                                  "den_ngay", "khong_thoi_han"],
                          order_by="tu_ngay desc", limit_page_length=0)


def departments():
    return frappe.get_all(C.DEPARTMENT, filters={"disabled": 0, "is_group": 0},
                          fields=["name", "department_name", "manager_email"],
                          order_by="department_name asc", limit_page_length=0)


def management_memberships():
    """Nguoi co phong phu = Management (mo hinh 8 quan ly: phong chinh Management,
    phong phu la phong that ho phu trach) - dung de ghi 'phu trach phong nao'."""
    return frappe.get_all("Employee Department Membership",
                          filters={"parenttype": C.EMPLOYEE},
                          parent_doctype=C.EMPLOYEE,
                          fields=["parent", "department"], limit_page_length=0)
