# Copyright (c) 2026, eCentric and contributors
"""Lan giao khao sat ca nhan (EC Survey Assignment) - phan cua repository.py.

Tra dict thuan; service nhan repository qua tham so (test thay bang repo gia)."""
import frappe

from ecentric_workspace.surveys import constants as C

ASSIGN_FIELDS = ["name", "survey", "ma_mau", "user", "employee", "status", "assigned_on",
                 "due_date", "reminded_at", "viewer_roles", "ngu_canh", "dedupe_key", "creation"]


def today():
    from frappe.utils import getdate, nowdate
    return getdate(nowdate())


def survey_by_ma_mau(ma_mau):
    if not ma_mau:
        return None
    rows = frappe.get_all(C.SURVEY, filters={"ma_mau": ma_mau, "survey_kind": C.KIND_PERSONAL},
                          fields=["name"], order_by="creation asc", limit_page_length=1)
    if not rows:
        return None
    d = frappe.get_doc(C.SURVEY, rows[0].name).as_dict()
    d["modified"] = str(d.get("modified") or "")
    return d


def assignment_by_key(key):
    rows = frappe.get_all(C.ASSIGNMENT, filters={"dedupe_key": key}, fields=ASSIGN_FIELDS,
                          limit_page_length=1)
    return dict(rows[0]) if rows else None


def get_assignment(name):
    if not name:
        return None
    rows = frappe.get_all(C.ASSIGNMENT, filters={"name": name}, fields=ASSIGN_FIELDS,
                          limit_page_length=1)
    return dict(rows[0]) if rows else None


def insert_assignment(fields):
    doc = frappe.get_doc(dict(fields, doctype=C.ASSIGNMENT))
    doc.insert(ignore_permissions=True)
    return doc.name


def set_assignment(name, values):
    frappe.db.set_value(C.ASSIGNMENT, name, values, update_modified=False)


def open_assignments(limit=5000):
    return [dict(r) for r in frappe.get_all(C.ASSIGNMENT, filters={"status": C.ASSIGN_OPEN},
                                            fields=ASSIGN_FIELDS, order_by="creation asc",
                                            limit_page_length=limit)]


def assignments(filters=None, limit=2000):
    return [dict(r) for r in frappe.get_all(C.ASSIGNMENT, filters=filters or {},
                                            fields=ASSIGN_FIELDS, order_by="creation desc",
                                            limit_page_length=limit)]


def assigned_users(survey):
    return set(frappe.get_all(C.ASSIGNMENT, filters={"survey": survey, "status": C.ASSIGN_OPEN},
                              pluck="user", limit_page_length=0) or [])


def participants_of_pairs(pairs):
    """{(survey, user): participant dict} cho mot loat cap - mot truy van moi khao sat."""
    out = {}
    by_survey = {}
    for s, u in pairs:
        by_survey.setdefault(s, set()).add(u)
    for s, users in by_survey.items():
        for r in frappe.get_all(C.PARTICIPANT, filters={"survey": s, "user": ["in", list(users)]},
                                fields=["name", "survey", "user", "submitted_at", "response"],
                                limit_page_length=0):
            out[(r.survey, r.user)] = dict(r)
    return out


def ngay_le():
    from ecentric_workspace.approval_center.shared.workflow import ngay_lam_viec
    return ngay_lam_viec.ngay_le_cong_ty()


def nguoi_di_lam(users, day=None):
    from ecentric_workspace.approval_center.shared.workflow import ngay_lam_viec
    return ngay_lam_viec.nguoi_di_lam(users, day)


def employee_of_user(user):
    if not user:
        return None
    row = frappe.db.get_value(C.EMPLOYEE, {"user_id": user}, ["name", "employee_name", "reports_to",
                                                               "status"], as_dict=True)
    return dict(row) if row else None


def manager_of_user(user):
    """Quan ly truc tiep HIEN TAI (reports_to -> user_id) cua nguoi dung, hoac None."""
    emp = employee_of_user(user)
    rt = emp and emp.get("reports_to")
    return rt and frappe.db.get_value(C.EMPLOYEE, rt, "user_id") or None


def direct_report_users(manager_user):
    """User cua cap duoi truc tiep (Employee.reports_to = ho so cua manager_user)."""
    emp = employee_of_user(manager_user)
    if not emp:
        return set()
    return set(frappe.get_all(C.EMPLOYEE, filters={"reports_to": emp["name"],
                                                   "user_id": ["is", "set"]},
                              pluck="user_id", limit_page_length=0) or [])
