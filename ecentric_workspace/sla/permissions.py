# Copyright (c) 2026, eCentric and contributors
"""Pham vi xem bang diem SLA. Quyet dinh cua chu so huu 16/09:

  * ai cung vao duoc trang /sla va thay diem CUA MINH;
  * xep hang: thay ca phong minh - ke ca diem cua truong phong ("phong nho, ca
    phong biet nhau, khong van de");
  * phong Ban Giam doc (`Management - EC`) va System Manager: thay tat ca.

KHONG dung `reports_to` hay `designation` de suy ra "quan ly". Hai truong do
khong dang tin trong du lieu hien tai va da tung dan den quyet dinh sai o cho
khac. Quan ly = thuoc phong `Management - EC`, dung mot nguon, kiem tra duoc.

KHONG tao Custom DocPerm. Mo rong pham vi bang query condition o day; DocPerm
chuan trong JSON da cho Employee quyen doc, phan con lai la LOC.

Toan bo file fail-safe theo huong HEP: moi loi tra ve dieu kien chi thay chinh
minh. Mot bang Employee hong khong duoc bien thanh mot vu lo diem toan cong ty.
"""
import frappe

from ecentric_workspace.sla.constants import (
    MANAGEMENT_DEPARTMENT_CONF_KEY, MANAGEMENT_DEPARTMENT_DEFAULT,
    SCOPE_ALL, SCOPE_DEPARTMENT, SCOPE_SELF,
)


def _management_department():
    return frappe.conf.get(MANAGEMENT_DEPARTMENT_CONF_KEY) or MANAGEMENT_DEPARTMENT_DEFAULT


def is_global_viewer(user=None):
    """Thay tat ca. System Manager la nang luc he thong; phong Ban Giam doc la
    pham vi DU LIEU. Hai thu khac nhau, gop o day vi ket qua giong nhau."""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    if "System Manager" in frappe.get_roles(user):
        return True
    try:
        return bool(frappe.get_all("Employee", limit=1, pluck="name", filters={
            "user_id": user, "status": "Active", "department": _management_department()}))
    except Exception:
        frappe.log_error(title="sla.is_global_viewer", message=frappe.get_traceback())
        return False


def user_departments(user=None):
    """Phong ban cua mot user. Fail-safe -> [] chu khong bao gio nem loi."""
    user = user or frappe.session.user
    try:
        rows = frappe.get_all("Employee", filters={"user_id": user, "status": "Active"},
                              pluck="department")
    except Exception:
        frappe.log_error(title="sla.user_departments", message=frappe.get_traceback())
        return []
    return sorted({d for d in rows if d})


def get_scope(user=None):
    """('all'|'department'|'self', [departments])."""
    user = user or frappe.session.user
    if is_global_viewer(user):
        return SCOPE_ALL, []
    depts = user_departments(user)
    if depts:
        return SCOPE_DEPARTMENT, depts
    return SCOPE_SELF, []


def obligation_query_conditions(user=None):
    """Dieu kien SQL cho `EC SLA Obligation`. Dang ky trong hooks.py.

    Loc theo cot `department` DA CHUP tren tung nghia vu, khong join sang
    Employee. Co y: mot nguoi chuyen phong thang nay khong duoc lam lo - hay
    lam an - diem cua ho o phong cu.
    """
    user = user or frappe.session.user
    scope, depts = get_scope(user)
    if scope == SCOPE_ALL:
        return ""
    own = "`tabEC SLA Obligation`.`owner_user` = %s" % frappe.db.escape(user)
    if scope == SCOPE_DEPARTMENT and depts:
        in_list = ", ".join(frappe.db.escape(d) for d in depts)
        return "(%s or `tabEC SLA Obligation`.`department` in (%s))" % (own, in_list)
    return own


def can_view_user(target_user, user=None):
    """Nguoi dang dang nhap co duoc xem diem cua `target_user` khong."""
    user = user or frappe.session.user
    if target_user == user:
        return True
    scope, depts = get_scope(user)
    if scope == SCOPE_ALL:
        return True
    if scope != SCOPE_DEPARTMENT:
        return False
    return bool(set(depts) & set(user_departments(target_user)))


def can_adjust(user=None):
    """Sua diem bang tay: chi HR Manager / System Manager. Truong phong KHONG -
    nguoi duoc cham diem va nguoi cham diem khong duoc la cung mot chuoi chi huy."""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    roles = frappe.get_roles(user)
    return "System Manager" in roles or "HR Manager" in roles
