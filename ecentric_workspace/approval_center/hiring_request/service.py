# Copyright (c) 2026, eCentric and contributors
"""Hiring orchestration over the shared engine. Direct Manager -> HR -> CEO (User participants
from process config; no fulfillment). Governance: the Direct Manager approver resolves from
Employee.reports_to (blocked at submit if unresolved; never requester-chosen). Department must be
a real Department master record. line_manager is BUSINESS INFO about the future hire's manager and
must be an active System User - it is NOT used as an approval resolver. No hardcoded approvers."""
import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Hiring Request"
APPROVAL_TYPE = "HIRING_REQUEST"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MATERIAL_FIELDS = ["position", "number_of_vacancy", "reason", "employment_type", "education",
                   "department", "line_manager", "suggested_salary"]
REQUIRED_AT_SUBMIT = ["request_title", "position", "reason", "employment_type", "education",
                      "department", "line_manager"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _ctx(user):
    return frappe.db.get_value("Employee", {"user_id": user}, ["name", "department", "company"], as_dict=True)


def _is_active_system_user(user):
    row = user and frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")


def _direct_manager_user(user):
    emp = frappe.db.get_value("Employee", {"user_id": user}, ["name", "reports_to"], as_dict=True)
    mgr = emp and emp.reports_to and frappe.db.get_value("Employee", emp.reports_to, "user_id")
    return mgr if (mgr and _is_active_system_user(mgr)) else None


@frappe.whitelist(methods=["POST"])
def submit(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yeu cau nay da duoc gui."))
    if doc.requested_by and doc.requested_by != frappe.session.user \
            and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Ban chi co the gui yeu cau cua chinh minh."))
    user = doc.requested_by or frappe.session.user
    doc.requested_by = user
    emp = _ctx(user)
    if emp:
        doc.employee = emp.name
        doc.company = doc.company or emp.company
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if doc.number_of_vacancy is None:
        missing.append("number_of_vacancy")
    if doc.suggested_salary is None:
        missing.append("suggested_salary")
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    if not frappe.db.exists("Department", doc.department):
        frappe.throw(_("Phong ban khong hop le. Vui long chon phong ban tu danh sach."))
    try:
        if int(doc.number_of_vacancy) <= 0:
            frappe.throw(_("So luong tuyen dung phai lon hon 0."))
    except (TypeError, ValueError):
        frappe.throw(_("So luong tuyen dung phai la so nguyen."))
    try:
        if float(doc.suggested_salary) <= 0:
            frappe.throw(_("Muc luong de xuat phai lon hon 0."))
    except (TypeError, ValueError):
        frappe.throw(_("Muc luong de xuat phai la so."))
    # line_manager is business info about the future hire; validate it is an active System User.
    lm = (doc.line_manager or "").strip()
    if not _EMAIL_RE.match(lm):
        frappe.throw(_("Email quan ly truc tiep (Line manager) khong hop le."))
    if not _is_active_system_user(lm):
        frappe.throw(_("Quan ly truc tiep (Line manager) phai la nguoi dung dang hoat dong trong he thong."))
    # Approval L1 Direct Manager must resolve (never requester-chosen).
    if not _direct_manager_user(user):
        frappe.throw(_("Khong xac dinh duoc Quan ly truc tiep cua ban. Vui long lien he HR/Admin de cap "
                       "nhat 'Bao cao cho' (reports_to) trong ho so nhan su truoc khi gui yeu cau."))
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return req_name


@frappe.whitelist(methods=["POST"])
def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yeu cau chua duoc gui."))
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}
