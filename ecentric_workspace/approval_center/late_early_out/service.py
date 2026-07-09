# Copyright (c) 2026, eCentric and contributors
"""Late in - Early out orchestration over the shared engine. Single level: Direct Manager Review ->
Completed. Direct Manager resolves from Employee.reports_to (blocked if unresolved). check_time_other
required only when check_time == Other. Title auto-generated. Attachment optional."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Late Early Out Request"
APPROVAL_TYPE = "LATE_EARLY_OUT"
CHECK_TIMES = ["10 AM", "11 AM", "12 PM", "1 PM", "2 PM", "3 PM", "4 PM", "5 PM", "Other"]
REQUEST_TYPES = ["Đi trễ", "Về sớm"]
MATERIAL_FIELDS = ["request_type", "applied_date", "check_time", "check_time_other", "reason"]
REQUIRED_AT_SUBMIT = ["request_type", "applied_date", "check_time", "reason"]


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
    t = (doc.get("check_time_other") if doc.get("check_time") == "Other" else doc.get("check_time")) or "?"
    rt = doc.get("request_type")
    prefix = rt if rt in REQUEST_TYPES else "Late/Early"  # fallback keeps legacy records readable
    return ("%s - %s - %s" % (prefix, doc.get("applied_date") or "?", t))[:180]


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
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    if doc.get("request_type") not in REQUEST_TYPES:
        frappe.throw(_("Vui long chon Loai yeu cau (Di tre / Ve som)."))
    if doc.check_time not in CHECK_TIMES:
        frappe.throw(_("Gio check-in/check-out khong hop le."))
    if doc.check_time == "Other" and not (doc.check_time_other or "").strip():
        frappe.throw(_("Vui long nhap gio khac khi chon 'Other'."))
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
