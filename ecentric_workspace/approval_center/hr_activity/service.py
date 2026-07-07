# Copyright (c) 2026, eCentric and contributors
"""HR Activity orchestration over the shared engine. Multi-level (HR Manager ->
HOF -> CEO), User participants from process config. No fulfillment; final approval
= Completed (engine terminal 'Approved'). No hardcoded runtime approvers."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC HR Activity Request"
APPROVAL_TYPE = "HR_ACTIVITY"

MATERIAL_FIELDS = ["activity_type", "activity_type_other", "detail", "start_date", "end_date",
                   "participants", "justification", "estimated_budget", "vendor_trainer_partner_info"]
# estimated_budget handled separately (0 is a valid value, not "missing")
REQUIRED_AT_SUBMIT = ["request_title", "activity_type", "detail", "start_date", "end_date",
                      "participants", "justification", "vendor_trainer_partner_info", "request_attachment"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _ctx(user):
    return frappe.db.get_value("Employee", {"user_id": user}, ["name", "department", "company"], as_dict=True)


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
    if doc.estimated_budget is None:
        missing.append("estimated_budget")
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc (bao gom tep dinh kem) truoc khi gui."))
    if doc.activity_type == "Other" and not (doc.activity_type_other or "").strip():
        frappe.throw(_("Vui long nhap loai hoat dong khac khi chon 'Other'."))
    if doc.end_date and doc.start_date and doc.end_date < doc.start_date:
        frappe.throw(_("Ngay ket thuc khong the truoc ngay bat dau."))
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
