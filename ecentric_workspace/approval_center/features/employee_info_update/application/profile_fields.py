# Copyright (c) 2026, eCentric and contributors
"""Truong ho so nhan vien duoc phep yeu cau cap nhat qua Employee Info Update (29/09/2026).

Hoan chot: lay cac truong trong HO SO NHAN VIEN (Employee) de nguoi dung chon, TRU tro cap /
luong; duyet xong thi GHI THANG vao ho so. Danh sach la allowlist tuong minh (label -> fieldname)
va chi hien truong nao Employee THAT SU co (meta) - them field moi vao ho so thi them mot dong
o day, khong mo cua cho moi truong cua Employee (status, reports_to, lich su luong...).

KHONG BAO GIO co o day: ec_allow_* (tro cap), bat ky gi thuoc Salary Structure Assignment,
status / relieving_date / reports_to / department (thay doi to chuc di qua quy trinh rieng).
"""
import frappe
from frappe import _
from frappe.utils import getdate

EMPLOYEE = "Employee"
OTHER = "Other"
#: Vai tro duoc xem gia tri ho so ca nhan cua NGUOI KHAC va duoc chon truong "chi C&B".
CNB_ROLES = ("EC CnB", "HR Manager", "System Manager")

#: (nhan hien tren form, fieldname tren Employee, chi C&B moi chon duoc)
FIELDS = (
    ("Personal email", "personal_email", False),
    ("Mobile phone", "cell_number", False),
    ("Date of birth", "date_of_birth", False),
    ("Marital status", "marital_status", False),
    ("Citizen ID number", "passport_number", False),
    ("Citizen ID issue date", "date_of_issue", False),
    ("Citizen ID issue place", "place_of_issue", False),
    ("Permanent address", "permanent_address", False),
    ("Temporary address", "current_address", False),
    ("Bank name", "bank_name", False),
    ("Bank account", "bank_ac_no", False),
    ("Social insurance ID", "health_insurance_no", False),
    ("Hospital code", "ec_ma_kcb", False),
    ("Hospital name", "ec_noi_kcb", False),
    ("License plate", "ec_bien_so_xe", False),
    ("Emergency contact name", "person_to_be_contacted", False),
    ("Emergency phone", "emergency_phone_number", False),
    ("Job title (C&B use only)", "designation", True),
    ("Position (C&B use only)", "grade", True),
)
_BY_LABEL = {lab: (fn, cnb) for lab, fn, cnb in FIELDS}


def is_cnb(user=None):
    return bool(set(frappe.get_roles(user or frappe.session.user)) & set(CNB_ROLES))


def spec(label):
    """(fieldname, cnb_only) cua mot nhan, hoac None (Other / nhan cu khong con ghi tu dong)."""
    return _BY_LABEL.get(label)


def options(user=None):
    """Danh sach cho o "Field to update": chi truong Employee dang co; truong C&B chi cho C&B.
    -> {"fields_to_update": [label...], "field_types": {label: {"type", "options"}}}"""
    meta = frappe.get_meta(EMPLOYEE)
    cnb = is_cnb(user)
    labels, types = [], {}
    for lab, fn, cnb_only in FIELDS:
        df = meta.get_field(fn)
        if not df or (cnb_only and not cnb):
            continue
        labels.append(lab)
        types[lab] = {"type": df.fieldtype,
                      "options": [o for o in (df.options or "").split("\n") if o]
                      if df.fieldtype == "Select" else []}
    labels.append(OTHER)
    return {"fields_to_update": labels, "field_types": types}


def resolve_employee(email):
    email = (email or "").strip()
    if not email:
        return None
    for f in ("user_id", "company_email", "personal_email", "prefered_email"):
        emp = frappe.db.get_value(EMPLOYEE, {f: email}, "name")
        if emp:
            return emp
    return None


def may_read_values(user, employee):
    """Gia tri ho so ca nhan chi tra cho CHINH nguoi do hoac C&B / HR Manager / SM."""
    if is_cnb(user):
        return True
    return bool(employee) and frappe.db.get_value(EMPLOYEE, employee, "user_id") == user


def current_value(user, email, label):
    """Gia tri hien tai tren ho so de dien san o "Current value". Rong neu khong duoc xem."""
    sp = spec(label)
    emp = resolve_employee(email)
    if not sp or not emp or not may_read_values(user, emp):
        return {"value": "", "readable": False, "auto_apply": bool(sp)}
    val = frappe.db.get_value(EMPLOYEE, emp, sp[0])
    return {"value": "" if val is None else str(val), "readable": True, "auto_apply": True}


def coerce(label, raw):
    """Gia tri moi -> dung kieu cua truong Employee. Nem loi than thien neu sai."""
    fn, _cnb = spec(label)
    df = frappe.get_meta(EMPLOYEE).get_field(fn)
    val = (raw or "").strip()
    if not df:
        frappe.throw(_("Hồ sơ nhân viên không còn trường này. Liên hệ C&B."))
    if df.fieldtype == "Date":
        try:
            return str(getdate(val))
        except Exception:
            frappe.throw(_("Giá trị mới phải là ngày hợp lệ (vd 2026-09-29)."))
    if df.fieldtype == "Select":
        opts = [o for o in (df.options or "").split("\n") if o]
        if val not in opts:
            frappe.throw(_("Giá trị mới phải là một trong: {0}").format(", ".join(opts)))
    if df.fieldtype == "Link" and not frappe.db.exists(df.options, val):
        frappe.throw(_("Không có {0} tên \"{1}\" trong danh mục.").format(df.options, val))
    return val
