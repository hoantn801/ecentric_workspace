# Copyright (c) 2026, eCentric and contributors
"""Employee Referral orchestration over the shared engine. Two levels (Careers ->
CEO), User participants from process config (Careers is NOT a Department). No
fulfillment; final approval = Completed. No hardcoded runtime approvers."""
import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine

BUSINESS_DT = "EC Employee Referral Request"
APPROVAL_TYPE = "EMPLOYEE_REFERRAL"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MATERIAL_FIELDS = ["candidate_full_name", "candidate_email", "position_applied_for", "hiring_department",
                   "relationship_with_referrer", "relationship_other", "referral_justification"]
REQUIRED_AT_SUBMIT = ["request_title", "candidate_full_name", "candidate_email", "position_applied_for",
                      "hiring_department", "relationship_with_referrer", "referral_justification",
                      "request_attachment"]


def _signature(doc):
    return hashlib.sha1(json.dumps({f: str(doc.get(f) or "") for f in MATERIAL_FIELDS},
                                   sort_keys=True).encode("utf-8")).hexdigest()


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
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc (bao gom CV dinh kem) truoc khi gui."))
    if not _EMAIL_RE.match((doc.candidate_email or "").strip()):
        frappe.throw(_("Email ung vien khong hop le."))
    if doc.relationship_with_referrer == "Other" and not (doc.relationship_other or "").strip():
        frappe.throw(_("Vui long nhap moi quan he khac khi chon 'Other'."))
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
