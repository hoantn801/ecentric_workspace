"""Stable API cho Phe duyet dot xuat (23/11/2026)."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import people
from ecentric_workspace.approval_center.shared.api_adapter import bind

globals().update(bind("ADHOC_APPROVAL"))


@frappe.whitelist()
def search_cc_users(q=None):
    """O CC: tim nguoi dung noi bo dang hoat dong (email / ho ten). Chi tra truong cong khai."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Vui lòng đăng nhập."), frappe.PermissionError)
    return people.search_internal_users(q)
