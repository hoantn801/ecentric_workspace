# Copyright (c) 2026, eCentric and contributors
"""API chot cong thang cho trang /ec-hr/attendance. Moi ham chi thao tac tren
chinh nguoi goi (hoac team ma nguoi goi la quan ly truc tiep / CnB-HR)."""
import frappe

from ecentric_workspace.hr.timesheet_close import service


def _user():
    u = frappe.session.user
    if not u or u == "Guest":
        frappe.throw("Bạn cần đăng nhập.", frappe.PermissionError)
    return u


@frappe.whitelist()
def get_state():
    return service.get_state(_user())


@frappe.whitelist(methods=["POST"])
def close_self():
    return service.close_self(_user())


@frappe.whitelist(methods=["POST"])
def close_team(group="team"):
    return service.close_team(_user(), group)


@frappe.whitelist(methods=["GET"])
def get_overview():
    u = _user()
    if not service.can_overview(u):
        frappe.throw("Bạn không có quyền xem mục này.", frappe.PermissionError)
    return service.overview(u)


@frappe.whitelist(methods=["POST"])
def remind_department(department=""):
    from ecentric_workspace.hr.timesheet_close import reminders
    return reminders.remind_department(_user(), department or None)
