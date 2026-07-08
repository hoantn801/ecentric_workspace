# Copyright (c) 2026, eCentric and contributors
"""Leave orchestration over the shared engine. Single level: Direct Manager Review -> Completed.
Direct Manager resolves from Employee.reports_to (blocked at submit if unresolved; never
requester-chosen). Title is auto-generated. Attachment optional. No hardcoded approvers."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Leave Request"
APPROVAL_TYPE = "LEAVE_REQUEST"
LEAVE_TYPES = ["Annual", "Sick", "Errand", "Maternity", "Paternity", "Marriage", "Bereavement"]
MATERIAL_FIELDS = ["leave_type", "start_date", "end_date", "duration_days", "remarks"]
REQUIRED_AT_SUBMIT = ["leave_type", "start_date", "end_date"]


def _signature(doc):
    return hashlib.sha1(json.dumps({f: str(doc.get(f) or "") for f in MATERIAL_FIELDS},
                                   sort_keys=True).encode("utf-8")).hexdigest()


def _ctx(user):
    return frappe.db.get_value("Employee", {"user_id": user}, ["name", "department", "company"], as_dict=True)


def _direct_manager_user(user):
    emp = frappe.db.get_value("Employee", {"user_id": user}, ["name", "reports_to"], as_dict=True)
    mgr = emp and emp.reports_to and frappe.db.get_value("Employee", emp.reports_to, "user_id")
    if mgr:
        row = frappe.db.get_value("User", mgr, ["enabled", "user_type"], as_dict=True)
        if row and row.enabled and row.user_type == "System User":
            return mgr
    return None


def gen_title(doc):
    lt = doc.get("leave_type") or "Leave"
    return ("Leave - %s - %s to %s" % (lt, doc.get("start_date") or "?", doc.get("end_date") or "?"))[:180]


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
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if doc.duration_days is None:
        missing.append("duration_days")
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    if doc.leave_type not in LEAVE_TYPES:
        frappe.throw(_("Loai nghi phep khong hop le."))
    if doc.end_date and doc.start_date and doc.end_date < doc.start_date:
        frappe.throw(_("Ngay ket thuc khong the truoc ngay bat dau."))
    try:
        if float(doc.duration_days) <= 0:
            frappe.throw(_("So ngay nghi phai lon hon 0."))
    except (TypeError, ValueError):
        frappe.throw(_("So ngay nghi phai la so."))
    doc.request_title = gen_title(doc)
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    if not _direct_manager_user(user):
        frappe.throw(_("Khong xac dinh duoc Quan ly truc tiep cua ban. Vui long lien he HR/Admin de cap "
                       "nhat 'Bao cao cho' (reports_to) trong ho so nhan su truoc khi gui yeu cau."))
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return req_name


@frappe.whitelist(methods=["POST"])
def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yeu cau chua duoc gui."))
    new_sig = _signature(doc)
    changed = new_sig != (doc.material_signature or "")
    frappe.db.set_value(BUSINESS_DT, doc.name, "request_title", gen_title(doc))
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": changed}
