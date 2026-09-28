# Copyright (c) 2026, eCentric and contributors
"""Nguoi hoi AI duoc xem du lieu cua AI. DUNG CHUNG cho tro ly chat + tong hop cong ty.

LUAT A14: KHONG suy quyen tu chuc danh. Ban `gemini_chat` cu (Server Script) cho "ca cong ty"
bat ky ai co chu "lead", "head", "manager", "truong"... trong chuc danh - vd mot "Team Lead"
doc duoc tam trang, vuong mac cua moi nguoi trong cong ty. `gemini_company_summary` da bo
cach do tu 23/05; chat thi chua (phat hien 28/09).

Thu tu:
  1. Administrator                                  -> all
  2. EC Viewer Permission: scope=all                -> all
                           scope=dept + phong ban   -> dept (phong do)
  3. Nhan vien thuoc "Management - EC" (chinh hoac kiem nhiem) -> all
  4. Nhan vien co phong ban                         -> dept (phong chinh + phong minh la
                                                       truong - Department.manager_email)
  5. Con lai                                        -> self
"""
import frappe

MGMT_DEPT = "Management - EC"
ALL, DEPT, SELF = "all", "dept", "self"


def decide(user, viewer_perm, employee, extra_depts, managed_depts):
    """PURE. -> {"scope", "depts", "employee"}.

    viewer_perm   : {"scope", "custom_department"} hoac None
    employee      : {"name", "department"} hoac None
    extra_depts   : phong kiem nhiem (Employee Department Membership)
    managed_depts : phong ma user la manager_email
    """
    emp_name = (employee or {}).get("name") or ""
    if not user or user == "Guest":
        return {"scope": SELF, "depts": [], "employee": ""}
    if user == "Administrator":
        return {"scope": ALL, "depts": [], "employee": emp_name}
    vp = viewer_perm or {}
    if vp.get("scope") == ALL:
        return {"scope": ALL, "depts": [], "employee": emp_name}
    if vp.get("scope") == DEPT and vp.get("custom_department"):
        return {"scope": DEPT, "depts": [vp["custom_department"]], "employee": emp_name}
    home = (employee or {}).get("department") or ""
    if home == MGMT_DEPT or MGMT_DEPT in (extra_depts or []):
        return {"scope": ALL, "depts": [], "employee": emp_name}
    depts = []
    for d in [home] + list(managed_depts or []):
        if d and d not in depts:
            depts.append(d)
    if depts:
        return {"scope": DEPT, "depts": depts, "employee": emp_name}
    return {"scope": SELF, "depts": [], "employee": emp_name}


def resolve(user=None):
    """Doc du lieu roi goi `decide`. Loi doc bang nao thi coi nhu bang do rong - khong
    bao gio noi rong quyen vi mot loi doc."""
    user = user or frappe.session.user
    viewer_perm = employee = None
    extra, managed = [], []
    try:
        if frappe.db.exists("EC Viewer Permission", user):
            viewer_perm = frappe.db.get_value("EC Viewer Permission", user,
                                              ["scope", "custom_department"], as_dict=True)
    except Exception:
        viewer_perm = None
    try:
        employee = frappe.db.get_value("Employee", {"user_id": user},
                                       ["name", "department"], as_dict=True)
    except Exception:
        employee = None
    if employee:
        try:
            extra = frappe.get_all("Employee Department Membership",
                                   filters={"parent": employee["name"]}, pluck="department")
        except Exception:
            extra = []
    try:
        managed = frappe.get_all("Department", filters={"manager_email": user}, pluck="name")
    except Exception:
        managed = []
    return decide(user, viewer_perm, employee, extra, managed)
