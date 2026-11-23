# Copyright (c) 2026, eCentric and contributors
"""Danh ba noi bo cho o "chon nguoi" dung chung tren moi form (24/11/2026, asset
public/js/ec_people_picker.bundle.js). Chi doc; chi nguoi dung noi bo da dang nhap goi duoc; chi tra
email / ho ten / phong ban cua System User dang bat (shared/people.search_internal_users)."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import catalog_permissions as perms
from ecentric_workspace.approval_center.shared import people


@frappe.whitelist(methods=["GET"])
def search_users(q=None):
    user = frappe.session.user
    if not user or user == "Guest" or not perms.is_internal_system_user(user):
        frappe.throw(_("Vui lòng đăng nhập bằng tài khoản nội bộ."), frappe.PermissionError)
    return people.search_internal_users(q)
