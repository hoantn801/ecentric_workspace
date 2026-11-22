# Copyright (c) 2026, eCentric and contributors
"""An phan "danh gia kieu khao sat" cua Don nghi viec voi nguoi xem khong phai HR (23/11/2026).

Truoc V2, don nghi viec hoi luon 5 cau khao sat (moi truong, phuc loi, van hoa, gioi thieu ban be,
loi nhan cuoi) va LINE MANAGER doc duoc het - trai muc dich "NLD tra loi that". Tu V2 khao sat tach
sang module Khao sat (chi HR xem); con DON CU van mang cac truong nay -> an o day, ap cho MOI don
(cu va moi) vi redactor chay tren moi duong doc chi tiet (query_service.detail).

Ai van thay: chinh nguoi nghi viec / nguoi lap don, nhom CnB/HR (role EC CnB, HR, HR Manager),
System Manager. Loi -> AN (fail-closed)."""
import frappe

SURVEY_FIELDS = ("workplace_environment_rating", "benefit_policy_rating", "corporate_culture_rating",
                 "recommend_to_friend", "final_message")
HR_VIEW_ROLES = ("EC CnB", "HR", "HR Manager", "System Manager")


def may_see_survey(business, user=None):
    user = user or frappe.session.user
    if user in (business.get("requested_by"), business.get("employee_email")):
        return True
    return bool(set(frappe.get_roles(user)) & set(HR_VIEW_ROLES))


def redact(business, request=None):
    try:
        ok = may_see_survey(business)
    except Exception:
        ok = False
    if not ok:
        for f in SURVEY_FIELDS:
            if f in business:
                business[f] = None
        business["survey_hidden"] = 1
    return business
