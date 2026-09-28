# Copyright (c) 2026, eCentric and contributors
"""permission_query_conditions cho Employee: nguoi ngoai HR chi thay CHINH MINH trong
list / report / search / Link.

VI SAO (VA_BAO_MAT_2026-09-25.md muc 2)
    Frappe v16 KHONG chan filter tren field permlevel cao. Nhan vien goi
    /api/resource/Employee?filters=[["bank_ac_no","like","9%"]] van biet duoc dong nao khop,
    tuc la do ra so tai khoan / CCCD / phu cap cua nguoi khac tung ky tu mot.

    Ban dau la Server Script `ec_employee_list_scope` (chat Phan quyen, 28/09). Day la ban
    trong code, cung luat. Sau khi deploy, DISABLE script do (khong xoa) - hai dieu kien giong
    het nhau duoc Frappe AND lai nen de ca hai cung khong sai, chi thua.

KHONG CHAN: mo form qua link (van thay field L0), va code cua app dung frappe.get_all
(bo qua quyen) - portal /ec-hr, luong duyet, Team Pulse khong bi anh huong.
"""
import frappe

FULL_ACCESS_ROLES = frozenset({"System Manager", "HR Manager", "HR User", "EC CnB"})


def employee_query_conditions(user=None, doctype=None, **kwargs):
    user = user or frappe.session.user
    if user == "Administrator" or FULL_ACCESS_ROLES.intersection(frappe.get_roles(user)):
        return ""
    return "`tabEmployee`.`user_id` = {}".format(frappe.db.escape(user))
